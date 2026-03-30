"""Impact rendering -- format :class:`ImpactResult` for terminal output.

Produces text strings for the CLI handler to emit via ``_output.info()``.
This module never calls ``info()`` or ``warn()`` directly.
"""

from __future__ import annotations

from lexibrary.services.impact import ImpactResult


def render_tree(result: ImpactResult) -> str:
    """Render an indented dependency tree with descriptions and warnings.

    Returns a multi-line string suitable for ``info()`` output.  The
    format matches the original ``lexi impact`` tree output exactly.
    """
    lines: list[str] = []
    lines.append(f"\n## Dependents of {result.target_path}\n")

    for dep in result.dependents:
        indent = "  " * (dep.depth - 1)
        prefix = "|-" if dep.depth == 1 else "|--"

        design_desc = f"  -- {dep.description}" if dep.description else ""
        lines.append(f"{indent}{prefix} {dep.path}{design_desc}")

        for post in dep.open_stack_posts:
            lines.append(f"{indent}   warning: open stack post {post}")

    lines.append("")
    return "\n".join(lines)


def render_quiet(result: ImpactResult) -> str:
    """Render dependent paths only, one per line (deduped, order-preserving).

    Returns a string suitable for piping to other tools.
    """
    seen: set[str] = set()
    paths: list[str] = []
    for dep in result.dependents:
        if dep.path not in seen:
            seen.add(dep.path)
            paths.append(dep.path)
    return "\n".join(paths)
