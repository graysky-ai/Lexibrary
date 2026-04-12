"""Render symbol-graph context blocks for the archivist design-file prompt.

This helper module is the read-side glue between the symbol graph
(``.lexibrary/symbols.db``) and the archivist LLM prompt. For each source
file the pipeline is about to regenerate, the archivist calls
:func:`render_symbol_graph_context` to pull two prompt snippets out of the
graph:

1. An "enums and constants" block listing every enum and named constant
   declared in the file along with its members. The block is fed to the
   LLM as context so the generated design file can name the enums
   explicitly instead of paraphrasing them.
2. A "call paths" block listing every function or method declared in the
   file along with a summary of its resolved inbound and outbound call
   edges. This block is opt-in via ``SymbolGraphConfig.include_call_paths``
   because it materially increases prompt size.

Both blocks are capped by configurable limits
(``SymbolGraphConfig.max_enum_items`` / ``max_call_path_items``) and
truncate with a trailing ``- ... N more`` marker so the archivist does
not burn tokens on long lists.

Graceful degradation
--------------------

* When ``symbols.db`` is missing, :class:`SymbolQueryService` returns an
  empty result from :meth:`~lexibrary.services.symbols.SymbolQueryService.symbols_in_file`.
  That is indistinguishable from "this file has no declared symbols",
  and both cases produce a :class:`SymbolGraphPromptContext` whose
  ``enums_block`` and ``call_paths_block`` are ``None``.
* When :meth:`~lexibrary.services.symbols.SymbolQueryService.call_context`
  cannot resolve a symbol id (missing graph, deleted row), it returns
  ``None``. The renderer treats that as "skip enrichment for this symbol"
  and keeps walking the remaining symbols.
* Any unexpected exception while reading the symbol graph is caught at
  the top level of :func:`render_symbol_graph_context` so a corrupt
  database or transient query error never blocks a design-file
  regeneration — the archivist falls back to generating a design file
  without symbol-graph context.

Design notes
------------

* This module holds the :class:`SymbolGraphPromptContext` dataclass that
  flows through ``DesignFileRequest`` and is consumed by
  ``archivist/service.py`` (group 8). Keeping the dataclass in the helper
  module rather than the service module is deliberate: the service is
  the consumer, the helper is the producer, and the dataclass is the
  producer's return type.
* Both render helpers iterate over the live list returned by
  :meth:`~lexibrary.services.symbols.SymbolQueryService.symbols_in_file`,
  which preserves source order. That keeps the prompt output stable
  across runs as long as the source file is unchanged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from lexibrary.config.schema import LexibraryConfig
    from lexibrary.services.symbols import SymbolQueryService
    from lexibrary.symbolgraph.query import SymbolRow

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclass (shared with archivist service via DesignFileRequest)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SymbolGraphPromptContext:
    """Prompt-ready symbol graph context blocks for a single source file.

    Both fields are ``None`` when the helper has nothing to add for that
    file (either because the symbol graph is unavailable, the file has
    no declared symbols, or the relevant config flag is off). A
    non-``None`` value is a pre-formatted multi-line string that can be
    injected directly into the design-file prompt without further
    processing.

    The archivist service forwards ``enums_block`` as the
    ``symbol_enums`` prompt variable and ``call_paths_block`` as the
    ``symbol_call_paths`` prompt variable. Both are optional on the
    BAML side, so passing ``None`` leaves the corresponding conditional
    prompt section empty.
    """

    enums_block: str | None
    call_paths_block: str | None
    branch_parameters_block: str | None
    include_data_flows: bool


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def render_symbol_graph_context(
    svc: SymbolQueryService,
    project_root: Path,
    source_path: Path,
    config: LexibraryConfig,
) -> SymbolGraphPromptContext:
    """Render prompt context blocks for *source_path* using *svc*.

    Pulls every symbol declared in *source_path* via
    :meth:`~lexibrary.services.symbols.SymbolQueryService.symbols_in_file`
    and dispatches to the appropriate ``_render_*`` helper for each
    configured section. Both ``include_enums`` and ``include_call_paths``
    are honoured so this helper can be called unconditionally by the
    pipeline — the config flags gate each block independently.

    The top-level try/except catches any exception raised by the symbol
    graph (missing DB, corrupted query, transient sqlite error) and
    returns an empty :class:`SymbolGraphPromptContext`. Callers never
    need to wrap this function in their own error handler.

    Parameters
    ----------
    svc:
        An open :class:`SymbolQueryService`. The helper assumes the
        service is in its ``open`` state and does not manage its
        lifecycle.
    project_root:
        Absolute path to the project root. Used to compute the relative
        path that keys the ``files`` table.
    source_path:
        Absolute path to the source file whose context is being rendered.
    config:
        The project config. Reads ``symbols.include_enums``,
        ``symbols.include_call_paths``, ``symbols.call_path_depth``,
        ``symbols.max_enum_items``, and ``symbols.max_call_path_items``.
    """
    symbols_cfg = config.symbols

    _empty = SymbolGraphPromptContext(
        enums_block=None,
        call_paths_block=None,
        branch_parameters_block=None,
        include_data_flows=False,
    )

    # Early out when the whole symbol graph subsystem is disabled. The
    # pipeline already gates the open() call on this, but callers that
    # invoke the helper directly (tests, future integrations) should
    # also get an empty context instead of a hollow database query.
    if not symbols_cfg.enabled:
        return _empty

    # Convert the source path to the project-relative form stored in
    # symbols.db (files.path). Outside-scope files return an empty
    # context because the graph will not contain them anyway.
    try:
        rel_path = str(source_path.relative_to(project_root))
    except ValueError:
        return _empty

    try:
        response = svc.symbols_in_file(rel_path)
    except Exception:
        logger.exception(
            "Failed to read symbols for %s — falling back to empty context",
            rel_path,
        )
        return _empty

    symbols = response.symbols
    if not symbols:
        return _empty

    enums_block: str | None = None
    if symbols_cfg.include_enums:
        enums_block = _render_enums(
            svc,
            symbols,
            limit=symbols_cfg.max_enum_items,
        )

    call_paths_block: str | None = None
    if symbols_cfg.include_call_paths:
        call_paths_block = _render_call_paths(
            svc,
            symbols,
            depth=symbols_cfg.call_path_depth,
            limit=symbols_cfg.max_call_path_items,
        )

    # Two-layer data-flow gate:
    # Layer 1 — file-level: does this file contain *any* function whose
    #   parameters drive branching?
    # Layer 2 — symbol-level: render individual branch-parameter lines
    #   for the functions that qualify.
    # If either layer produces nothing, include_data_flows is False
    # regardless of the config flag.
    branch_block: str | None = None
    effective_data_flows = False
    if symbols_cfg.include_data_flows and svc.has_branching_parameters_in_file(rel_path):
        branch_block = _render_branch_parameters(svc, symbols)
        effective_data_flows = branch_block is not None

    return SymbolGraphPromptContext(
        enums_block=enums_block,
        call_paths_block=call_paths_block,
        branch_parameters_block=branch_block,
        include_data_flows=effective_data_flows,
    )


# ---------------------------------------------------------------------------
# Private render helpers
# ---------------------------------------------------------------------------


def _render_enums(
    svc: SymbolQueryService,
    symbols: list[SymbolRow],
    limit: int,
) -> str | None:
    """Render the enums and constants block for *symbols*.

    Iterates *symbols* in source order, filters down to
    ``symbol_type in ("enum", "constant")``, and asks the service for
    each one's members. Symbols with no members (a constant whose value
    the extractor did not capture, for instance) still appear in the
    block — the LLM sees the name and type marker and infers the role.

    The block is truncated at *limit* entries: if more than *limit*
    enums/constants exist, the first *limit* entries are emitted
    followed by ``- ... N more``. Returns ``None`` when no
    enums/constants are declared in the file.
    """
    relevant = [sym for sym in symbols if sym.symbol_type in ("enum", "constant")]
    if not relevant:
        return None

    total = len(relevant)
    overflow = max(0, total - limit)
    visible = relevant[:limit]

    lines: list[str] = []
    for sym in visible:
        members = svc.members_of(sym.id)
        if members:
            pairs: list[str] = []
            for member in members:
                if member.value is not None:
                    pairs.append(f"{member.name}={member.value}")
                else:
                    pairs.append(member.name)
            joined = ", ".join(pairs)
            lines.append(f"- {sym.name} [{sym.symbol_type}]: {{{joined}}}")
        else:
            lines.append(f"- {sym.name} [{sym.symbol_type}]: {{}}")

    if overflow > 0:
        lines.append(f"- ... {overflow} more")

    return "\n".join(lines)


def _render_call_paths(
    svc: SymbolQueryService,
    symbols: list[SymbolRow],
    *,
    depth: int,
    limit: int,
) -> str | None:
    """Render the call paths block for *symbols*.

    Iterates *symbols* in source order, filters down to
    ``symbol_type in ("function", "method")``, and asks the service
    for each one's call context up to *depth* hops. Symbols with no
    resolved edges (leaf functions with no callers or callees recorded
    in the graph) are skipped so the block only contains useful
    entries. Symbols for which
    :meth:`~lexibrary.services.symbols.SymbolQueryService.call_context`
    returns ``None`` (graph missing or id not resolvable) are also
    skipped.

    The block is truncated at *limit* entries: if more than *limit*
    functions/methods with non-empty edges exist, the first *limit*
    entries are emitted followed by ``- ... N more``. Returns ``None``
    when no qualifying entries are found.
    """
    relevant = [sym for sym in symbols if sym.symbol_type in ("function", "method")]
    if not relevant:
        return None

    lines: list[str] = []
    overflow = 0
    for sym in relevant:
        context = svc.call_context(sym.id, depth=depth)
        if context is None:
            continue
        if not context.callers and not context.callees:
            continue

        if len(lines) >= limit:
            overflow += 1
            continue

        display_name = sym.qualified_name or sym.name
        caller_names = _format_call_sides(
            edge.caller.qualified_name or edge.caller.name for edge in context.callers
        )
        callee_names = _format_call_sides(
            edge.callee.qualified_name or edge.callee.name for edge in context.callees
        )
        lines.append(f"- {display_name}: callers=[{caller_names}] callees=[{callee_names}]")

    if not lines:
        return None

    if overflow > 0:
        lines.append(f"- ... {overflow} more")

    return "\n".join(lines)


def _format_call_sides(names: Iterable[str]) -> str:
    """Join symbol names into a deduped, comma-separated string.

    *names* is an iterable of strings (typically a generator). The
    returned string preserves first-seen order but collapses duplicates
    so a symbol called multiple times from the same caller only appears
    once in the rendered block.
    """
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in names:
        if raw in seen:
            continue
        seen.add(raw)
        ordered.append(raw)
    return ", ".join(ordered)


def _render_branch_parameters(
    svc: SymbolQueryService,
    symbols: list[SymbolRow],
) -> str | None:
    """Render the branch parameters block for *symbols*.

    Iterates *symbols* in source order, filters down to
    ``symbol_type in ("function", "method")``, and asks the service
    for each one's branch parameters.  Symbols with no branch
    parameters are skipped.

    Each qualifying function emits one line in the format::

        - qualified_name(param1, param2): branches on param1, param2

    Returns ``None`` when no function in the file has branch parameters.
    """
    relevant = [sym for sym in symbols if sym.symbol_type in ("function", "method")]
    if not relevant:
        return None

    lines: list[str] = []
    for sym in relevant:
        params = svc.branch_parameters_of(sym.id)
        if not params:
            continue
        display_name = sym.qualified_name or sym.name
        joined = ", ".join(params)
        lines.append(f"- {display_name}({joined}): branches on {joined}")

    return "\n".join(lines) if lines else None
