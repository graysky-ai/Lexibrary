"""Orient render module -- formats OrientResult for terminal output."""

from __future__ import annotations

from lexibrary.services.orient import ORIENT_CHAR_BUDGET, OrientResult


def render_orient(result: OrientResult) -> str:
    """Render an :class:`OrientResult` as plain-text terminal output.

    Applies token-budget trimming to file descriptions, keeping
    shallower paths first when the budget is exceeded.

    Returns an empty string when the result has no content.
    """
    parts: list[str] = []

    # 1. Topology text
    if result.topology_text:
        parts.append(result.topology_text)

    # 2. File descriptions (budget-trimmed)
    if result.file_descriptions:
        desc_lines = [f"{path}: {desc}" for path, desc in result.file_descriptions]
        parts.append("## File Descriptions\n")

        # Check budget before adding all descriptions
        header_chars = sum(len(p) for p in parts) + len("## File Descriptions\n")
        remaining_budget = ORIENT_CHAR_BUDGET - header_chars

        if remaining_budget > 0:
            # Sort deepest paths first for trimming (more path segments = deeper).
            # We want to *trim* deepest first, so we add shallowest first
            # and stop when budget exhausted.
            sorted_by_depth = sorted(desc_lines, key=lambda line: line.count("/"))

            included: list[str] = []
            chars_used = 0
            for line in sorted_by_depth:
                line_chars = len(line) + 1  # +1 for newline
                if chars_used + line_chars > remaining_budget:
                    break
                included.append(line)
                chars_used += line_chars

            omitted = len(desc_lines) - len(included)
            # Re-sort included lines alphabetically for clean output
            included.sort()

            if included:
                # Replace the placeholder "## File Descriptions\n" with header + lines
                parts[-1] = "## File Descriptions\n\n" + "\n".join(included)

            if omitted > 0:
                parts.append(f"\n*Truncated: {omitted} file descriptions omitted*")

    # 3. Library stats
    if result.library_stats:
        parts.append(result.library_stats)

    # 4. IWH signals
    if result.iwh_signals:
        parts.append(result.iwh_signals)

    return "\n\n".join(parts).strip() if parts else ""
