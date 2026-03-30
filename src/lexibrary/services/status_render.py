"""Status rendering — dashboard and quiet-mode formatters.

Takes a :class:`~lexibrary.services.status.StatusResult` and produces
formatted strings for terminal output.  The CLI handler calls these
renderers and passes the result to ``info()`` for display.

The service module (``status.py``) never imports this module, keeping
rendering concerns fully separate.
"""

from __future__ import annotations

from datetime import UTC, datetime

from lexibrary.services.status import StatusResult


def render_dashboard(result: StatusResult, *, cli_prefix: str = "lexictl") -> str:
    """Render a full status dashboard as a multi-line string.

    Parameters
    ----------
    result:
        Populated :class:`StatusResult` from :func:`collect_status`.
    cli_prefix:
        CLI name for the ``validate`` suggestion line (``"lexi"`` or
        ``"lexictl"``).

    Returns
    -------
    str
        Multi-line dashboard text ready for ``info()``.
    """
    lines: list[str] = []

    lines.append("")
    lines.append("Lexibrary Status")
    lines.append("")

    # Files
    if result.stale_count > 0:
        lines.append(f"  Files: {result.total_designs} tracked, {result.stale_count} stale")
    else:
        lines.append(f"  Files: {result.total_designs} tracked")

    # Concepts
    concept_parts: list[str] = []
    if result.concept_counts["active"] > 0:
        concept_parts.append(f"{result.concept_counts['active']} active")
    if result.concept_counts["deprecated"] > 0:
        concept_parts.append(f"{result.concept_counts['deprecated']} deprecated")
    if result.concept_counts["draft"] > 0:
        concept_parts.append(f"{result.concept_counts['draft']} draft")
    if concept_parts:
        lines.append("  Concepts: " + ", ".join(concept_parts))
    else:
        lines.append("  Concepts: 0")

    # Stack
    total_stack = result.total_stack
    if total_stack > 0:
        lines.append(
            f"  Stack: {total_stack} post{'s' if total_stack != 1 else ''}"
            f" ({result.stack_counts.get('resolved', 0)} resolved,"
            f" {result.stack_counts.get('open', 0)} open)"
        )
    else:
        lines.append("  Stack: 0 posts")

    # Link graph health
    ih = result.index_health
    if ih.artifact_count is not None:
        built_part = f" (built {ih.built_at})" if ih.built_at else ""
        lines.append(
            f"  Link graph: {ih.artifact_count} artifact"
            f"{'s' if ih.artifact_count != 1 else ''}"
            f", {ih.link_count} link"
            f"{'s' if ih.link_count != 1 else ''}"
            f"{built_part}"
        )
    else:
        lines.append("  Link graph: not built (run lexictl update to create)")

    lines.append("")

    # Issues
    lines.append(
        f"  Issues: {result.error_count} error{'s' if result.error_count != 1 else ''},"
        f" {result.warning_count} warning{'s' if result.warning_count != 1 else ''}"
    )

    # Last updated
    if result.latest_generated is not None:
        now = datetime.now(tz=UTC)
        gen = result.latest_generated
        if gen.tzinfo is None:
            gen = gen.replace(tzinfo=UTC)
        delta = now - gen
        total_seconds = int(delta.total_seconds())
        if total_seconds < 60:
            time_str = f"{total_seconds} second{'s' if total_seconds != 1 else ''} ago"
        elif total_seconds < 3600:
            minutes = total_seconds // 60
            time_str = f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        elif total_seconds < 86400:
            hours = total_seconds // 3600
            time_str = f"{hours} hour{'s' if hours != 1 else ''} ago"
        else:
            days = total_seconds // 86400
            time_str = f"{days} day{'s' if days != 1 else ''} ago"
        lines.append(f"  Updated: {time_str}")
    else:
        lines.append("  Updated: never")

    lines.append("")

    # Suggest validate if issues exist
    if result.error_count > 0 or result.warning_count > 0:
        lines.append(f"Run `{cli_prefix} validate` for details.")

    return "\n".join(lines)


def render_quiet(result: StatusResult, *, cli_prefix: str = "lexictl") -> str:
    """Render a single-line status summary for hooks/CI.

    Parameters
    ----------
    result:
        Populated :class:`StatusResult` from :func:`collect_status`.
    cli_prefix:
        CLI name prefix (``"lexi"`` or ``"lexictl"``).

    Returns
    -------
    str
        Single-line summary string ready for ``info()``.
    """
    error_count = result.error_count
    warning_count = result.warning_count

    if error_count > 0 and warning_count > 0:
        parts: list[str] = []
        parts.append(f"{error_count} error{'s' if error_count != 1 else ''}")
        parts.append(f"{warning_count} warning{'s' if warning_count != 1 else ''}")
        return f"{cli_prefix}: " + ", ".join(parts) + f" \u2014 run `{cli_prefix} validate`"
    elif error_count > 0:
        return (
            f"{cli_prefix}: {error_count} error{'s' if error_count != 1 else ''}"
            f" \u2014 run `{cli_prefix} validate`"
        )
    elif warning_count > 0:
        return (
            f"{cli_prefix}: {warning_count} warning{'s' if warning_count != 1 else ''}"
            f" \u2014 run `{cli_prefix} validate`"
        )
    else:
        return f"{cli_prefix}: library healthy"
