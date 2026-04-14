"""Design file management CLI commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from lexibrary.cli._output import error, info, warn
from lexibrary.cli._shared import require_project_root

design_app = typer.Typer(help="Design file management commands.", rich_markup_mode=None)


@design_app.command("update")
def design_update(
    source_file: Annotated[
        Path,
        typer.Argument(help="Source file to generate or update a design file for."),
    ],
    *,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            "-f",
            help="Bypass updated_by protection and staleness checks.",
        ),
    ] = False,
    unlimited: Annotated[
        bool,
        typer.Option(
            "--unlimited",
            help="Bypass token-budget size gate for large files.",
        ),
    ] = False,
) -> None:
    """Generate or update the design file for a source file via the archivist pipeline."""
    import asyncio  # noqa: PLC0415

    from lexibrary.config.loader import load_config  # noqa: PLC0415
    from lexibrary.services.design import check_design_update  # noqa: PLC0415
    from lexibrary.services.design_render import (  # noqa: PLC0415
        render_failure,
        render_skeleton_warning,
        render_skip,
        render_success,
    )

    project_root = require_project_root()
    config = load_config(project_root)

    target = Path(source_file).resolve()

    # Check scope: file must be under one of the declared scope_roots.
    if config.owning_root(target, project_root) is None:
        error(
            f"{source_file} is outside all configured scope_roots: "
            f"{[r.path for r in config.scope_roots]}"
        )
        raise typer.Exit(1) from None

    # Pre-flight decision
    decision = check_design_update(target, project_root, config, force=force)

    if decision.action == "skip":
        msg = render_skip(decision)
        if decision.skip_code == "iwh_blocked":
            # IWH signals must be acknowledged before proceeding — force a
            # non-zero exit so exit-code-only scripts halt and the agent is
            # nudged to read the blocking signal.
            warn(msg)
            raise typer.Exit(1)
        # "protected", "up_to_date", or any future skip_code: informational.
        # The command behaved as designed; route to stdout (no "Warning:"
        # prefix) so scripted callers capturing stdout see what happened.
        info(msg)
        return

    # --- action == "generate" ---

    from lexibrary.archivist.pipeline import update_file  # noqa: PLC0415
    from lexibrary.archivist.service import build_archivist_service  # noqa: PLC0415
    from lexibrary.conventions.index import ConventionIndex  # noqa: PLC0415
    from lexibrary.playbooks.index import PlaybookIndex  # noqa: PLC0415
    from lexibrary.utils.paths import LEXIBRARY_DIR  # noqa: PLC0415
    from lexibrary.wiki.index import ConceptIndex  # noqa: PLC0415

    # Load available artifact names for wikilink guidance
    concepts_dir = project_root / LEXIBRARY_DIR / "concepts"
    conventions_dir = project_root / LEXIBRARY_DIR / "conventions"
    playbooks_dir = project_root / LEXIBRARY_DIR / "playbooks"

    artifact_names: list[str] = []
    if concepts_dir.exists():
        concept_index = ConceptIndex.load(concepts_dir)
        artifact_names.extend(concept_index.names())
    if conventions_dir.exists():
        conv_index = ConventionIndex(conventions_dir)
        conv_index.load()
        artifact_names.extend(conv_index.names())
    if playbooks_dir.exists():
        pb_index = PlaybookIndex(playbooks_dir)
        pb_index.load()
        artifact_names.extend(pb_index.names())

    available_artifacts = artifact_names or None

    # Instantiate archivist service (only when we actually need generation)
    archivist = build_archivist_service(config, unlimited=unlimited)

    rel_source = str(target.relative_to(project_root))

    try:
        result = asyncio.run(
            update_file(
                target,
                project_root,
                config,
                archivist,
                available_artifacts,
                force=force,
                unlimited=unlimited,
            )
        )
    except Exception as exc:
        error(f"Design update failed: {exc}")
        raise typer.Exit(1) from None

    if result.failed:
        msg = render_failure(rel_source, result.failure_reason or "unknown error")
        error(msg)
        raise typer.Exit(1) from None

    if result.skeleton:
        msg = render_skeleton_warning(rel_source, "token budget exceeded")
        warn(msg)
        return

    msg = render_success(rel_source, result.change.value)
    info(msg)


@design_app.command("comment")
def design_comment(
    source_file: Annotated[
        Path,
        typer.Argument(help="Source file to add a design comment for."),
    ],
    *,
    body: Annotated[
        str,
        typer.Option("--body", "-b", help="Comment text to append."),
    ],
) -> None:
    """Append a comment to a design file and return confirmation."""
    from lexibrary.lifecycle.design_comments import append_design_comment  # noqa: PLC0415
    from lexibrary.utils.paths import mirror_path  # noqa: PLC0415

    target = Path(source_file).resolve()

    project_root = require_project_root()

    # Check that the design file exists for this source file
    design_path = mirror_path(project_root, target)
    if not design_path.exists():
        rel_source = target.relative_to(project_root)
        error(
            f"No design file exists for {rel_source}.\n"
            f"Run `lexi design update {rel_source}` to create one first."
        )
        raise typer.Exit(1) from None

    # Append the comment
    append_design_comment(project_root, target, body)

    rel_source = target.relative_to(project_root)
    info(f"Comment added for {rel_source}.")
