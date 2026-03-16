"""IWH (I Was Here) signal management CLI commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, cast

import typer

from lexibrary.cli._output import error, info, markdown_table, warn
from lexibrary.cli._shared import require_project_root

iwh_app = typer.Typer(help="IWH (I Was Here) signal management commands.", rich_markup_mode=None)


@iwh_app.command("write")
def iwh_write(
    directory: Annotated[
        Path | None,
        typer.Argument(help="Source directory for the signal. Defaults to project root."),
    ] = None,
    *,
    scope: Annotated[
        str,
        typer.Option("--scope", "-s", help="Signal scope: incomplete, blocked, or warning."),
    ] = "incomplete",
    body: Annotated[
        str,
        typer.Option("--body", "-b", help="Signal body text describing the situation."),
    ],
) -> None:
    """Create an IWH signal for a directory and return the signal path."""
    from lexibrary.config.loader import load_config  # noqa: PLC0415
    from lexibrary.iwh import IWHScope, write_iwh  # noqa: PLC0415
    from lexibrary.utils.paths import iwh_path  # noqa: PLC0415

    project_root = require_project_root()
    config = load_config(project_root)

    if not config.iwh.enabled:
        warn("IWH is disabled in project configuration.")
        raise typer.Exit(2)

    valid_scopes = ("warning", "incomplete", "blocked")
    if scope not in valid_scopes:
        error(f"Invalid scope: '{scope}'. Must be one of: {', '.join(valid_scopes)}")
        raise typer.Exit(1)

    source_dir = Path(directory).resolve() if directory is not None else project_root
    target_dir = iwh_path(project_root, source_dir).parent

    result_path = write_iwh(target_dir, author="agent", scope=cast(IWHScope, scope), body=body)
    rel = result_path.relative_to(project_root)
    info(f"Created IWH signal at {rel} (scope: {scope})")


@iwh_app.command("read")
def iwh_read(
    directory: Annotated[
        Path | None,
        typer.Argument(help="Source directory to read signal from. Defaults to project root."),
    ] = None,
    *,
    peek: Annotated[
        bool,
        typer.Option("--peek", help="Read without consuming (do not delete the signal)."),
    ] = False,
) -> None:
    """Return IWH signal content for a directory and consume it. Use --peek to preserve."""
    from lexibrary.config.loader import load_config  # noqa: PLC0415
    from lexibrary.iwh import consume_iwh, read_iwh  # noqa: PLC0415
    from lexibrary.utils.paths import iwh_path  # noqa: PLC0415

    project_root = require_project_root()
    config = load_config(project_root)

    if not config.iwh.enabled:
        warn("IWH is disabled in project configuration.")
        raise typer.Exit(2)

    source_dir = Path(directory).resolve() if directory is not None else project_root
    target_dir = iwh_path(project_root, source_dir).parent

    iwh = read_iwh(target_dir) if peek else consume_iwh(target_dir)

    if iwh is None:
        info("No IWH signal found.")
        return

    info(f"[{iwh.scope.upper()}] by {iwh.author} at {iwh.created.isoformat()}")
    if iwh.body:
        info("")
        info(iwh.body)

    if not peek:
        info("\nSignal consumed (deleted).")


@iwh_app.command("list")
def iwh_list() -> None:
    """Return a table of all IWH signals in the project with scope and directory."""
    from datetime import UTC, datetime  # noqa: PLC0415

    from lexibrary.config.loader import load_config  # noqa: PLC0415
    from lexibrary.iwh.reader import find_all_iwh  # noqa: PLC0415

    project_root = require_project_root()
    config = load_config(project_root)

    if not config.iwh.enabled:
        warn("IWH is disabled in project configuration.")
        raise typer.Exit(2)

    results = find_all_iwh(project_root)

    if not results:
        info("No IWH signals found.")
        return

    now = datetime.now(tz=UTC)
    rows: list[list[str]] = []
    for source_dir, iwh in results:
        created = iwh.created
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        total_seconds = int((now - created).total_seconds())
        if total_seconds < 3600:
            age = f"{total_seconds // 60}m"
        elif total_seconds < 86400:
            age = f"{total_seconds // 3600}h"
        else:
            age = f"{total_seconds // 86400}d"

        display_dir = f"{source_dir}/" if str(source_dir) != "." else "./"
        body_preview = iwh.body.replace("\n", " ")
        if len(body_preview) > 50:
            body_preview = body_preview[:47] + "..."

        rows.append([display_dir, iwh.scope, iwh.author, age, body_preview])

    info("## IWH Signals\n")
    info(markdown_table(["Directory", "Scope", "Author", "Age", "Body"], rows))
    info(f"\nFound {len(results)} signal(s)")
