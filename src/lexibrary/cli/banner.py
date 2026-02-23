"""Startup banner for lexictl init.

Displays a truecolor Unicode block-art image when the terminal supports it,
falling back to a plain ASCII logo otherwise.
"""
from __future__ import annotations

from rich.console import Console
from rich.text import Text

ASCII_BANNER = (
    "\n"
    "  _          _ _\n"
    " | |   _____(_) |__  _ _ __ _ _ _ _  _\n"
    " | |__/ -_) \\ | '_ \\| '_/ _` | '_| || |\n"
    " |____\\___|_\\_\\_.__/|_| \\__,_|_|  \\_, |\n"
    "                                  |__/\n"
)

BANNER_WIDTH = 80


def render_banner(console: Console) -> None:
    """Display the startup banner if the terminal supports it.

    - Truecolor terminal: renders the pre-baked ANSI block art at 80 columns.
    - Non-truecolor terminal: renders the ASCII fallback.
    - Non-TTY (piped output): skips the banner entirely.
    """
    if not console.is_terminal:
        return

    if console.color_system == "truecolor":
        from lexibrary.cli._banner_data import BANNER_ANSI  # noqa: PLC0415

        text = Text.from_ansi(BANNER_ANSI)
        console.print(text)
    else:
        console.print(ASCII_BANNER, style="bold cyan")
