"""Update stat rendering — formatters for lexictl update command output.

Takes :class:`~lexibrary.archivist.pipeline.UpdateStats` and produces
formatted strings for terminal output.  The CLI handler calls these
renderers and passes the result to ``info()`` / ``warn()`` / ``error()``
for display.

Render functions return either plain ``str`` or lists of
``(level, message)`` tuples where *level* is ``"info"``, ``"warn"``,
or ``"error"`` so the CLI handler can dispatch to the right output
helper.
"""

from __future__ import annotations

from pathlib import Path

from lexibrary.archivist.change_checker import ChangeLevel
from lexibrary.archivist.pipeline import UpdateStats


def render_update_summary(stats: UpdateStats, project_root: Path) -> list[tuple[str, str]]:
    """Render the "Update summary:" block.

    Returns a list of ``(level, message)`` tuples so the CLI handler
    can dispatch each line to the correct output helper.

    Parameters
    ----------
    stats:
        Accumulated pipeline statistics.
    project_root:
        Project root for relativising failed-file paths.
    """
    lines: list[tuple[str, str]] = []

    lines.append(("info", ""))
    lines.append(("info", "Update summary:"))
    lines.append(("info", f"  Files scanned:       {stats.files_scanned}"))
    lines.append(("info", f"  Files unchanged:     {stats.files_unchanged}"))
    lines.append(("info", f"  Files created:       {stats.files_created}"))
    lines.append(("info", f"  Files updated:       {stats.files_updated}"))
    lines.append(("info", f"  Files agent-updated: {stats.files_agent_updated}"))

    if stats.files_failed:
        lines.append(("error", f"  Files failed:       {stats.files_failed}"))
        for failed_path, reason in stats.failed_files:
            try:
                rel = Path(failed_path).relative_to(project_root)
            except ValueError:
                rel = Path(failed_path)
            lines.append(("error", f"    - {rel}: {reason}"))

    if stats.aindex_refreshed:
        lines.append(("info", f"  .aindex refreshed:   {stats.aindex_refreshed}"))
    if stats.token_budget_warnings:
        lines.append(("warn", f"  Token budget warnings: {stats.token_budget_warnings}"))

    return lines


def render_failed_files(stats: UpdateStats, project_root: Path) -> str:
    """Render the failed file list.

    Returns an empty string when ``stats.files_failed == 0``.

    Parameters
    ----------
    stats:
        Accumulated pipeline statistics.
    project_root:
        Project root for relativising failed-file paths.
    """
    if stats.files_failed == 0:
        return ""

    lines: list[str] = []
    for failed_path, reason in stats.failed_files:
        try:
            rel = Path(failed_path).relative_to(project_root)
        except ValueError:
            rel = Path(failed_path)
        lines.append(f"    - {rel}: {reason}")
    return "\n".join(lines)


def has_lifecycle_stats(stats: UpdateStats) -> bool:
    """Return True when any lifecycle stat is non-zero."""
    return (
        stats.designs_deprecated
        + stats.designs_unlinked
        + stats.designs_deleted_ttl
        + stats.concepts_deleted_ttl
        + stats.concepts_skipped_referenced
        + stats.conventions_deleted_ttl
        + stats.renames_detected
        + stats.renames_migrated
    ) > 0


def render_lifecycle_stats(stats: UpdateStats) -> list[tuple[str, str]]:
    """Render the "Lifecycle:" block.

    Returns a list of ``(level, message)`` tuples so the CLI handler
    can dispatch each line to the correct output helper.

    Parameters
    ----------
    stats:
        Accumulated pipeline statistics.
    """
    lines: list[tuple[str, str]] = []

    lines.append(("info", ""))
    lines.append(("info", "Lifecycle:"))
    if stats.renames_detected:
        lines.append(("info", f"  Renames detected:    {stats.renames_detected}"))
    if stats.renames_migrated:
        lines.append(("info", f"  Renames migrated:    {stats.renames_migrated}"))
    if stats.designs_deprecated:
        lines.append(("info", f"  Designs deprecated:  {stats.designs_deprecated}"))
    if stats.designs_unlinked:
        lines.append(("info", f"  Designs unlinked:    {stats.designs_unlinked}"))
    if stats.designs_deleted_ttl:
        lines.append(("warn", f"  Designs TTL-deleted: {stats.designs_deleted_ttl}"))
    if stats.concepts_deleted_ttl:
        lines.append(("warn", f"  Concepts TTL-deleted: {stats.concepts_deleted_ttl}"))
    if stats.concepts_skipped_referenced:
        lines.append(
            ("info", f"  Concepts skipped (referenced): {stats.concepts_skipped_referenced}")
        )
    if stats.conventions_deleted_ttl:
        lines.append(("warn", f"  Conventions TTL-deleted: {stats.conventions_deleted_ttl}"))

    return lines


def has_enrichment_queue(stats: UpdateStats) -> bool:
    """Return True when any enrichment queue stat is non-zero."""
    return (stats.queue_processed + stats.queue_failed + stats.queue_remaining) > 0


def render_enrichment_queue(stats: UpdateStats) -> list[tuple[str, str]]:
    """Render the "Enrichment queue:" block.

    Returns a list of ``(level, message)`` tuples so the CLI handler
    can dispatch each line to the correct output helper.

    Parameters
    ----------
    stats:
        Accumulated pipeline statistics.
    """
    lines: list[tuple[str, str]] = []

    lines.append(("info", ""))
    lines.append(("info", "Enrichment queue:"))
    if stats.queue_processed:
        lines.append(("info", f"  Enriched:            {stats.queue_processed}"))
    if stats.queue_failed:
        lines.append(("error", f"  Failed:             {stats.queue_failed}"))
    if stats.queue_remaining:
        lines.append(("info", f"  Remaining:           {stats.queue_remaining}"))

    return lines


def render_dry_run_results(results: list[tuple[Path, ChangeLevel]], project_root: Path) -> str:
    """Render the dry-run preview table with summary line.

    Parameters
    ----------
    results:
        List of ``(file_path, change_level)`` tuples from a dry-run.
    project_root:
        Project root for relativising file paths.

    Returns
    -------
    str
        Multi-line text showing each file and a summary count.
    """
    lines: list[str] = []

    counts: dict[str, int] = {}
    for file_path, change_level in results:
        label = change_level.value.upper()
        counts[label] = counts.get(label, 0) + 1
        rel_path = file_path.relative_to(project_root)
        lines.append(f"  {label:<20} {rel_path}")

    # Summary
    lines.append("")
    total = len(results)
    parts = [f"{total} file{'s' if total != 1 else ''}"]
    for label, count in sorted(counts.items()):
        parts.append(f"{count} {label.lower()}")
    lines.append("Summary: " + ", ".join(parts))

    return "\n".join(lines)
