"""Startup banner for lexictl init.

Displays a plain ASCII logo to stdout.
"""

from __future__ import annotations

import sys

ASCII_BANNER = (
    "\n"
    "  _          _ _\n"
    " | |   _____(_) |__  _ _ __ _ _ _ _  _\n"
    " | |__/ -_) \\ | '_ \\| '_/ _` | '_| || |\n"
    " |____\\___|_\\_\\_.__/|_| \\__,_|_|  \\_, |\n"
    "                                  |__/\n"
)


def render_banner() -> None:
    """Display the startup banner if running in a terminal."""
    if not sys.stdout.isatty():
        return
    print(ASCII_BANNER)  # noqa: T201
