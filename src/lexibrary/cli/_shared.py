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


def load_dotenv_if_configured() -> None:
    """Load ``.env`` at CLI startup when ``api_key_source`` is ``"dotenv"``.

    Reads raw YAML from the project config (no Pydantic validation) to
    check ``llm.api_key_source`` before full config initialisation.
    When the value equals ``"dotenv"``, calls
    ``load_dotenv(project_root / ".env", override=False)`` so that env
    vars already set in the shell take precedence.

    All errors are silently swallowed — the normal project-not-found or
    config-not-found error surfaces later when a command actually runs.
    """
    try:
        import yaml  # noqa: PLC0415
        from dotenv import load_dotenv  # noqa: PLC0415

        project_root = find_project_root()
        config_path = project_root / ".lexibrary" / "config.yaml"
        if not config_path.exists():
            return

        with open(config_path) as f:
            raw = yaml.safe_load(f)

        if not isinstance(raw, dict):
            return

        llm_section = raw.get("llm")
        if not isinstance(llm_section, dict):
            return

        if llm_section.get("api_key_source") == "dotenv":
            load_dotenv(project_root / ".env", override=False)
    except Exception:  # noqa: BLE001
        # Silently skip — errors will surface later during normal
        # config loading when a command actually runs.
        pass
