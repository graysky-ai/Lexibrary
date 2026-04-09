"""Curate rendering -- formatters for curator run results and last-run display.

Takes a :class:`~lexibrary.curator.models.CuratorReport` or raw JSON report
data and produces formatted strings for terminal output.  The coordinator
module never imports this module, keeping rendering concerns fully separate.
"""

from __future__ import annotations

import json
from pathlib import Path


def render_summary(
    *,
    checked: int,
    fixed: int,
    deferred: int,
    errored: int,
    sub_agent_calls: dict[str, int],
    report_path: Path | None,
) -> list[tuple[str, str]]:
    """Render a curator run summary as a list of (level, message) pairs.

    Parameters
    ----------
    checked:
        Total items triaged.
    fixed:
        Items successfully dispatched and fixed.
    deferred:
        Items deferred (autonomy gating, LLM cap, or propose mode).
    errored:
        Items that produced errors.
    sub_agent_calls:
        Mapping of action_key -> call count.
    report_path:
        Path to the written JSON report, or ``None`` if writing failed.

    Returns
    -------
    list[tuple[str, str]]
        Each tuple is ``("info" | "warn" | "error", message)``.
    """
    lines: list[tuple[str, str]] = []

    lines.append(("info", ""))
    lines.append(("info", "Curator Run Summary"))
    lines.append(("info", f"  Checked:  {checked}"))
    lines.append(("info", f"  Fixed:    {fixed}"))

    if deferred > 0:
        lines.append(("warn", f"  Deferred: {deferred}"))
    else:
        lines.append(("info", f"  Deferred: {deferred}"))

    if errored > 0:
        lines.append(("error", f"  Errors:   {errored}"))
    else:
        lines.append(("info", f"  Errors:   {errored}"))

    if sub_agent_calls:
        lines.append(("info", ""))
        lines.append(("info", "  Sub-agent calls:"))
        for action_key, count in sorted(sub_agent_calls.items()):
            lines.append(("info", f"    {action_key}: {count}"))

    if report_path is not None:
        lines.append(("info", ""))
        lines.append(("info", f"  Report: {report_path}"))

    return lines


def render_dry_run(
    *,
    checked: int,
    dispatched_count: int,
    deferred_count: int,
    sub_agent_calls: dict[str, int],
    estimated_llm_calls: int,
) -> list[tuple[str, str]]:
    """Render a dry-run summary as a list of (level, message) pairs.

    Parameters
    ----------
    checked:
        Total items triaged.
    dispatched_count:
        Items that would be dispatched.
    deferred_count:
        Items that would be deferred.
    sub_agent_calls:
        Mapping of action_key -> call count that would be made.
    estimated_llm_calls:
        Estimated LLM calls for dispatched items.

    Returns
    -------
    list[tuple[str, str]]
        Each tuple is ``("info" | "warn", message)``.
    """
    lines: list[tuple[str, str]] = []

    lines.append(("warn", "DRY-RUN MODE -- no files will be modified"))
    lines.append(("info", ""))
    lines.append(("info", "Curator Dry Run Summary"))
    lines.append(("info", f"  Checked:            {checked}"))
    lines.append(("info", f"  Would dispatch:     {dispatched_count}"))

    if deferred_count > 0:
        lines.append(("warn", f"  Would defer:        {deferred_count}"))
    else:
        lines.append(("info", f"  Would defer:        {deferred_count}"))

    lines.append(("info", f"  Estimated LLM calls: {estimated_llm_calls}"))

    if sub_agent_calls:
        lines.append(("info", ""))
        lines.append(("info", "  Sub-agent types:"))
        for action_key, count in sorted(sub_agent_calls.items()):
            lines.append(("info", f"    {action_key}: {count}"))

    return lines


def render_last_run(report_path: Path) -> list[tuple[str, str]]:
    """Render the most recent curator report.

    Parameters
    ----------
    report_path:
        Path to a JSON report file in ``.lexibrary/curator/reports/``.

    Returns
    -------
    list[tuple[str, str]]
        Each tuple is ``("info" | "warn" | "error", message)``.
    """
    lines: list[tuple[str, str]] = []

    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return [("error", f"Failed to read report: {exc}")]

    timestamp = data.get("timestamp", "unknown")
    checked = data.get("checked", 0)
    fixed = data.get("fixed", 0)
    deferred = data.get("deferred", 0)
    errored = data.get("errored", 0)
    sub_agent_calls = data.get("sub_agent_calls", {})

    lines.append(("info", ""))
    lines.append(("info", "Last Curator Run"))
    lines.append(("info", f"  Timestamp: {timestamp}"))
    lines.append(("info", f"  Checked:   {checked}"))
    lines.append(("info", f"  Fixed:     {fixed}"))

    if deferred > 0:
        lines.append(("warn", f"  Deferred:  {deferred}"))
    else:
        lines.append(("info", f"  Deferred:  {deferred}"))

    if errored > 0:
        lines.append(("error", f"  Errors:    {errored}"))
    else:
        lines.append(("info", f"  Errors:    {errored}"))

    if sub_agent_calls:
        lines.append(("info", ""))
        lines.append(("info", "  Sub-agent calls:"))
        for action_key, count in sorted(sub_agent_calls.items()):
            lines.append(("info", f"    {action_key}: {count}"))

    lines.append(("info", ""))
    lines.append(("info", f"  Report: {report_path}"))

    return lines
