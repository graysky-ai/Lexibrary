"""Design file management CLI commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from lexibrary.cli._output import error, info
from lexibrary.exceptions import LexibraryNotFoundError
from lexibrary.utils.root import find_project_root

design_app = typer.Typer(help="Design file management commands.", rich_markup_mode=None)


@design_app.command("update")
def design_update(
    source_file: Annotated[
        Path,
        typer.Argument(help="Source file to scaffold or display a design file for."),
    ],
) -> None:
    """Return existing design file content, or scaffold a new one if none exists."""
    from lexibrary.archivist.scaffold import generate_design_scaffold  # noqa: PLC0415
    from lexibrary.config.loader import load_config  # noqa: PLC0415
    from lexibrary.utils.paths import mirror_path  # noqa: PLC0415

    target = Path(source_file).resolve()

    # Find project root starting from the file's directory (walks upward)
    try:
        project_root = find_project_root(start=target.parent)
    except LexibraryNotFoundError:
        error("No .lexibrary/ directory found. Run `lexictl init` to create one.")
        raise typer.Exit(1) from None

    config = load_config(project_root)

    # Check scope: file must be under scope_root
    scope_abs = (project_root / config.scope_root).resolve()
    try:
        target.relative_to(scope_abs)
    except ValueError:
        error(
            f"{source_file} is outside the configured scope_root "
            f"({config.scope_root})."
        )
        raise typer.Exit(1) from None

    # Compute mirror path
    design_path = mirror_path(project_root, target)

    if design_path.exists():
        # Display existing design file
        rel_design = design_path.relative_to(project_root)
        content = design_path.read_text(encoding="utf-8")
        info(f"{rel_design}\n")
        info(content)
        info("\nReminder: set `updated_by: agent` in frontmatter after making changes.")
    else:
        # Scaffold new design file
        scaffold = generate_design_scaffold(target, project_root)
        design_path.parent.mkdir(parents=True, exist_ok=True)
        design_path.write_text(scaffold, encoding="utf-8")
        rel_design = design_path.relative_to(project_root)
        info(f"Created design scaffold: {rel_design}\n")
        info(scaffold)


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

    # Find project root starting from the file's directory (walks upward)
    try:
        project_root = find_project_root(start=target.parent)
    except LexibraryNotFoundError:
        error("No .lexibrary/ directory found. Run `lexictl init` to create one.")
        raise typer.Exit(1) from None

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
