"""Pure render helpers for symbol graph CLI output.

This module formats :class:`~lexibrary.services.symbols.TraceResult`
instances for terminal display. Unlike most render modules in
``services/`` that return strings, this module emits output directly via
:func:`lexibrary.cli._output.info` because the ``lexi trace`` output is
composed from multiple blocks (header, file:line line, and one table per
edge category) with blank-line separators between results.

Phase 3 (``symbol-graph-3``) will extend :func:`render_trace` to render
class edges; Phase 4 will add enum/constant members. Both extensions
plug in under the ``callees`` / ``unresolved_callees`` sections so the
public contract stays the same.
"""

from __future__ import annotations

from lexibrary.cli._output import info, markdown_table
from lexibrary.services.symbols import TraceResult


def render_trace(query: str, results: list[TraceResult]) -> None:
    """Render ``lexi trace`` output for a list of :class:`TraceResult`.

    For each result, emits:

    - ``## <qualified_name or name>  [<symbol_type>]`` — a Markdown
      header line.
    - ``` `<file_path>:<line_start>` ``` — a backticked source location.
    - ``### Callers`` — a Markdown table of inbound edges, omitted
      entirely when ``callers`` is empty.
    - ``### Callees`` — a Markdown table of outbound resolved edges,
      omitted when ``callees`` is empty.
    - ``### Unresolved callees (external or dynamic)`` — a Markdown
      table of outbound unresolved edges, omitted when
      ``unresolved_callees`` is empty.

    Results are separated by a blank line. *query* is accepted for
    forward compatibility (future renderers may echo it back) but is
    currently unused — each result carries enough context in its own
    header to identify itself.

    All output goes through :func:`lexibrary.cli._output.info` and
    :func:`lexibrary.cli._output.markdown_table`; this module never
    calls ``print`` directly.
    """
    del query  # reserved for future use

    for i, result in enumerate(results):
        if i > 0:
            info("")  # blank line between multiple matches

        sym = result.symbol
        info(f"## {sym.qualified_name or sym.name}  [{sym.symbol_type}]")
        info(f"`{sym.file_path}:{sym.line_start}`")

        if result.callers:
            info("")
            info("### Callers")
            caller_rows = [
                [
                    c.caller.qualified_name or c.caller.name,
                    f"{c.caller.file_path}:{c.line}",
                ]
                for c in result.callers
            ]
            info(markdown_table(["Caller", "Location"], caller_rows))

        if result.callees:
            info("")
            info("### Callees")
            callee_rows = [
                [
                    c.callee.qualified_name or c.callee.name,
                    f"{c.callee.file_path}:{c.line}",
                ]
                for c in result.callees
            ]
            info(markdown_table(["Callee", "Location"], callee_rows))

        if result.unresolved_callees:
            info("")
            info("### Unresolved callees (external or dynamic)")
            unresolved_rows = [[u.callee_name, str(u.line)] for u in result.unresolved_callees]
            info(markdown_table(["Name", "Line"], unresolved_rows))
        # Phase 3 extends this to render class edges.
        # Phase 4 extends this to render enum members.
