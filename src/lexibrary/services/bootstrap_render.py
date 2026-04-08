"""Bootstrap stat rendering -- formatters for lexictl bootstrap command output.

Takes :class:`~lexibrary.indexer.orchestrator.IndexStats` and
:class:`~lexibrary.lifecycle.bootstrap.BootstrapStats` and produces
formatted strings for terminal output.  The CLI handler calls these
renderers and passes the result to ``info()`` / ``error()`` for display.

Render functions return lists of ``(level, message)`` tuples where
*level* is ``"info"`` or ``"error"`` so the CLI handler can dispatch
to the right output helper.
"""

from __future__ import annotations

from lexibrary.indexer.orchestrator import IndexStats
from lexibrary.lifecycle.bootstrap import BootstrapStats


def render_index_summary(index_stats: IndexStats) -> list[tuple[str, str]]:
    """Render the Phase 1 indexing summary.

    Returns a list of ``(level, message)`` tuples so the CLI handler
    can dispatch each line to the correct output helper.

    Parameters
    ----------
    index_stats:
        Statistics from the recursive indexing run.
    """
    lines: list[tuple[str, str]] = []

    lines.append(
        (
            "info",
            f"  Directories indexed: {index_stats.directories_indexed}, "
            f"Files found: {index_stats.files_found}",
        )
    )
    if index_stats.errors:
        lines.append(("error", f"  Errors: {index_stats.errors}"))

    return lines


def render_bootstrap_summary(design_stats: BootstrapStats) -> list[tuple[str, str]]:
    """Render the Phase 2 "Bootstrap summary:" block.

    Returns a list of ``(level, message)`` tuples so the CLI handler
    can dispatch each line to the correct output helper.

    Parameters
    ----------
    design_stats:
        Statistics from the bootstrap design-file generation run.
    """
    lines: list[tuple[str, str]] = []

    lines.append(("info", ""))
    lines.append(("info", "Bootstrap summary:"))
    lines.append(("info", f"  Files scanned:  {design_stats.files_scanned}"))
    lines.append(("info", f"  Files created:  {design_stats.files_created}"))
    lines.append(("info", f"  Files updated:  {design_stats.files_updated}"))
    lines.append(("info", f"  Files skipped:  {design_stats.files_skipped}"))
    if design_stats.files_failed:
        lines.append(("error", f"  Files failed:  {design_stats.files_failed}"))

    if design_stats.errors:
        lines.append(("info", ""))
        lines.append(("error", "Errors:"))
        for err in design_stats.errors:
            lines.append(("error", f"  {err}"))

    return lines
