"""Plain-text output helpers for the lexi CLI.

All CLI output should go through these functions rather than using
``print()`` or Rich directly.  This keeps formatting consistent and
makes it straightforward to switch output modes (markdown / json / plain)
in the future via ``--format``.
"""

from __future__ import annotations

import sys
from typing import IO


def info(message: str, *, file: IO[str] | None = None) -> None:
    """Print an informational message to *stdout*.

    Args:
        message: The text to display.
        file: Override the output stream (default ``sys.stdout``).
    """
    print(message, file=file or sys.stdout)


def warn(message: str, *, file: IO[str] | None = None) -> None:
    """Print a warning message prefixed with ``Warning:`` to *stderr*.

    Args:
        message: The warning text (without prefix).
        file: Override the output stream (default ``sys.stderr``).
    """
    print(f"Warning: {message}", file=file or sys.stderr)


def error(message: str, *, file: IO[str] | None = None) -> None:
    """Print an error message prefixed with ``Error:`` to *stderr*.

    Args:
        message: The error text (without prefix).
        file: Override the output stream (default ``sys.stderr``).
    """
    print(f"Error: {message}", file=file or sys.stderr)


def hint(message: str, *, file: IO[str] | None = None) -> None:
    """Print a recovery hint prefixed with ``Hint:`` to *stderr*.

    Hints suggest a next action after an error or warning — e.g.
    ``hint("Run `lexi validate` for details.")``.

    Args:
        message: The hint text (without prefix).
        file: Override the output stream (default ``sys.stderr``).
    """
    print(f"Hint: {message}", file=file or sys.stderr)


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    """Render a Markdown table from *headers* and *rows*.

    Each row must have the same number of elements as *headers*.
    Column widths are padded to the widest cell in each column for
    human-readable alignment.

    Args:
        headers: Column header strings.
        rows: List of rows, each a list of cell strings.

    Returns:
        A multi-line string containing the rendered Markdown table.

    Raises:
        ValueError: If *headers* is empty.
    """
    if not headers:
        msg = "headers must not be empty"
        raise ValueError(msg)

    num_cols = len(headers)

    # Normalise rows: pad short rows with empty strings, truncate long ones
    normalised: list[list[str]] = []
    for row in rows:
        if len(row) < num_cols:
            normalised.append(list(row) + [""] * (num_cols - len(row)))
        else:
            normalised.append(list(row[:num_cols]))

    # Compute column widths (minimum 3 for the separator dashes)
    widths = [max(3, len(h)) for h in headers]
    for row in normalised:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def _format_row(cells: list[str]) -> str:
        padded = [cell.ljust(widths[i]) for i, cell in enumerate(cells)]
        return "| " + " | ".join(padded) + " |"

    lines: list[str] = []
    lines.append(_format_row(headers))
    lines.append("| " + " | ".join("-" * w for w in widths) + " |")
    for row in normalised:
        lines.append(_format_row(row))

    return "\n".join(lines)
