"""Shared CLI helpers used by both lexi and lexictl apps."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from lexibrary.exceptions import LexibraryNotFoundError
from lexibrary.utils.root import find_project_root

console = Console()


def require_project_root() -> Path:
    """Resolve the project root or exit with a friendly error."""
    try:
        return find_project_root()
    except LexibraryNotFoundError:
        console.print(
            "[red]No .lexibrary/ directory found.[/red]"
            " Run [cyan]lexictl init[/cyan] to create one."
        )
        raise typer.Exit(1) from None


def stub(name: str) -> None:
    """Print a standard stub message for unimplemented commands."""
    require_project_root()
    console.print(f"[yellow]Not yet implemented.[/yellow]  ([dim]{name}[/dim])")
