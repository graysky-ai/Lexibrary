"""Pure render helpers for symbol graph CLI output.

This module formats :class:`~lexibrary.services.symbols.TraceResult`
instances for terminal display. Unlike most render modules in
``services/`` that return strings, this module emits output directly via
:func:`lexibrary.cli._output.info` because the ``lexi trace`` output is
composed from multiple blocks (header, file:line line, and one table per
edge category) with blank-line separators between results.

Phase 3 (``symbol-graph-3``) extends :func:`render_trace` with class
hierarchy sections (``Class relationships``, ``Subclasses,
instantiation, and composition``, and trailing ``Unresolved bases`` /
``Unresolved compositions`` lines). Phase 4 (``symbol-graph-4``) adds a
trailing ``### Members`` block that renders enum variants and constant
values. Phase 6 (``symbol-graph-6``) renames the headings and adds
composition edge rendering. All extensions plug in after the existing
call sections so the public contract stays stable.
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
    - ``### Class relationships`` — a Markdown table of resolved
      outbound class edges (base classes and compositions) with a
      ``Relationship`` column showing the edge type, omitted when
      ``parents`` is empty.
    - ``### Subclasses, instantiation, and composition`` — a Markdown
      table of resolved inbound class edges (subclasses, instantiation
      sites, and composition targets), omitted when ``children`` is
      empty.
    - ``Unresolved bases: ...`` — a trailing line listing unresolved
      outbound ``inherits`` edges (e.g. ``BaseModel``, ``Enum``),
      omitted when no unresolved inherits edges exist.
    - ``Unresolved compositions: ...`` — a trailing line listing
      unresolved outbound ``composes`` edges, omitted when no
      unresolved composes edges exist.
    - ``### Members`` — a Markdown table of enum variants or constant
      values keyed by ``(name, value, ordinal)``, omitted when
      ``members`` is empty. The ``ordinal`` column is blank when the
      extractor did not capture a source-order position (e.g. for a
      single-row constant member).

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

        if result.parents:
            info("")
            info("### Class relationships")
            parent_rows = [
                [
                    p.edge_type,
                    p.target.qualified_name or p.target.name,
                    f"{p.target.file_path}:{p.line if p.line is not None else p.target.line_start}",
                ]
                for p in result.parents
            ]
            info(markdown_table(["Relationship", "Target", "Location"], parent_rows))

        if result.children:
            info("")
            info("### Subclasses, instantiation, and composition")
            child_rows = [
                [
                    c.edge_type,
                    c.source.qualified_name or c.source.name,
                    f"{c.source.file_path}:{c.line if c.line is not None else c.source.line_start}",
                ]
                for c in result.children
            ]
            info(markdown_table(["Type", "Source", "Location"], child_rows))

        if result.unresolved_parents:
            unresolved_bases = [
                u.target_name for u in result.unresolved_parents if u.edge_type == "inherits"
            ]
            unresolved_compositions = [
                u.target_name for u in result.unresolved_parents if u.edge_type == "composes"
            ]
            if unresolved_bases:
                info("")
                info("Unresolved bases: " + ", ".join(unresolved_bases))
            if unresolved_compositions:
                info("")
                info("Unresolved compositions: " + ", ".join(unresolved_compositions))

        if result.members:
            info("")
            info("### Members")
            member_rows = [
                [
                    m.name,
                    m.value if m.value is not None else "",
                    "" if m.ordinal is None else str(m.ordinal),
                ]
                for m in result.members
            ]
            info(markdown_table(["Name", "Value", "Ordinal"], member_rows))
