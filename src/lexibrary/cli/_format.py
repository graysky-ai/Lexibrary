"""Global ``--format`` flag state for the lexi CLI.

Stores the active output format (``markdown``, ``json``, or ``plain``)
chosen via the top-level ``--format`` option.  Commands query the current
format with :func:`get_format` and adapt their output accordingly.
"""

from __future__ import annotations

from enum import StrEnum

# ---------------------------------------------------------------------------
# Format enum
# ---------------------------------------------------------------------------


class OutputFormat(StrEnum):
    """Supported output formats for the ``--format`` flag."""

    markdown = "markdown"
    json = "json"
    plain = "plain"


# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_current_format: OutputFormat = OutputFormat.markdown


def get_format() -> OutputFormat:
    """Return the currently active output format."""
    return _current_format


def set_format(fmt: OutputFormat) -> None:
    """Set the active output format (called by the Typer callback)."""
    global _current_format  # noqa: PLW0603
    _current_format = fmt
