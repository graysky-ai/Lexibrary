"""SymbolQueryService — unified queries over symbols.db and index.db.

Phase 1 (symbol-graph-1) shipped the type surface with empty-returning
methods. The lifecycle, dataclasses, and public method signatures are
stable from day one so downstream callers can import the service without
waiting on the query implementations.

Phase 2 (symbol-graph-2) implements ``trace``, ``search_symbols``, and
``symbols_in_file`` on top of the real query methods and adds
staleness-detection response wrappers.
Phase 3 (symbol-graph-3) adds class relationship queries.
Phase 4 (symbol-graph-4) adds enum/constant queries.

The service degrades gracefully when ``symbols.db`` is missing: ``open()``
does not raise, ``_symbol_graph`` stays ``None``, every query method
returns an empty result (an empty list or an empty response wrapper), and
the user sees a hint telling them to run ``lexi design update <file>``.
This mirrors the link graph's existing open-or-None contract so
downstream commands see empty results rather than a stack trace.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from lexibrary.symbolgraph.query import _SELECT_SYMBOL, _row_to_symbol
from lexibrary.utils.hashing import hash_file

if TYPE_CHECKING:
    from lexibrary.linkgraph.query import LinkGraph
    from lexibrary.symbolgraph.query import (
        CallRow,
        ClassEdgeRow,
        SymbolGraph,
        SymbolMemberRow,
        SymbolRow,
        UnresolvedCallRow,
        UnresolvedClassEdgeRow,
    )


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class TraceResult:
    """Everything known about a symbol — the union of all edges.

    Phase 2 populates ``callers``, ``callees``, and ``unresolved_callees``
    via :class:`~lexibrary.symbolgraph.query.SymbolGraph` queries. Phase 3
    populates ``parents`` / ``children`` from ``class_edges`` and
    ``unresolved_parents`` from ``class_edges_unresolved``; Phase 4 will
    begin populating ``members`` from ``symbol_members``.
    """

    symbol: SymbolRow
    callers: list[CallRow] = field(default_factory=list)
    callees: list[CallRow] = field(default_factory=list)
    unresolved_callees: list[UnresolvedCallRow] = field(default_factory=list)
    parents: list[ClassEdgeRow] = field(
        default_factory=list
    )  # resolved edges from this symbol (base classes)
    children: list[ClassEdgeRow] = field(
        default_factory=list
    )  # edges to this symbol (subclasses, instantiation sites)
    unresolved_parents: list[UnresolvedClassEdgeRow] = field(
        default_factory=list
    )  # unresolved edges from this symbol (e.g. external bases like BaseModel)
    members: list[SymbolMemberRow] = field(default_factory=list)


@dataclass
class SymbolSearchHit:
    """A single hit from :meth:`SymbolQueryService.search_symbols`.

    ``design_file_path`` is the path to the design file describing the
    owning source file when one is known via the link graph; it is
    ``None`` otherwise.
    """

    symbol: SymbolRow
    score: float = 0.0
    design_file_path: str | None = None  # resolved via the link graph when present


@dataclass
class StaleSymbolWarning:
    """A single staleness warning for a file whose on-disk hash has drifted.

    Emitted by :meth:`SymbolQueryService.trace` and
    :meth:`SymbolQueryService.symbols_in_file` when the on-disk SHA-256 of
    a file no longer matches the ``last_hash`` stored in ``symbols.db``.
    Callers should surface the warning so users know a per-file refresh
    (via ``lexi design update <file>``) may be required.

    ``last_built_at`` is reserved for forward compatibility. Phase 2's
    ``files`` schema does not persist a build timestamp, so the service
    always emits ``None`` for now; a future schema bump can populate it
    without breaking the dataclass contract.
    """

    file_path: str
    last_built_at: str | None = None


@dataclass
class TraceResponse:
    """Wrapper around :meth:`SymbolQueryService.trace` results + staleness.

    ``results`` holds a :class:`TraceResult` for each matching symbol and
    ``stale`` holds one :class:`StaleSymbolWarning` per unique file whose
    on-disk hash no longer matches the hash recorded in ``symbols.db``.
    When the symbol graph is unavailable (``symbols.db`` missing), both
    fields are empty.
    """

    results: list[TraceResult]
    stale: list[StaleSymbolWarning] = field(default_factory=list)


@dataclass
class SymbolsInFileResponse:
    """Wrapper around :meth:`SymbolQueryService.symbols_in_file` results.

    ``symbols`` is the list of symbols declared in the requested file (in
    source order) and ``stale`` is a single :class:`StaleSymbolWarning`
    for that file when its on-disk hash no longer matches the stored
    ``last_hash``. ``stale`` is ``None`` when the file is up-to-date, not
    tracked in ``symbols.db``, or the symbol graph is unavailable.
    """

    symbols: list[SymbolRow]
    stale: StaleSymbolWarning | None = None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class SymbolQueryService:
    """Read-only service joining ``symbols.db`` and ``index.db``.

    The service owns the lifecycles of both underlying graphs. Call
    :meth:`open` (or use it as a context manager) before issuing any
    queries, and :meth:`close` when done. Query methods return empty
    results when the symbol graph is unavailable.

    Graceful degradation
    --------------------

    If ``symbols.db`` is missing when :meth:`open` runs, the service
    still opens successfully with ``_symbol_graph`` set to ``None`` and
    emits a user-facing hint. The link graph is opened unconditionally;
    its own opener returns ``None`` when ``index.db`` is missing, so
    ``_link_graph`` may also be ``None`` in that case.
    """

    def __init__(self, project_root: Path) -> None:
        """Create a service rooted at *project_root*.

        The service does not touch the filesystem until :meth:`open` is
        called, so construction is cheap and side-effect free.
        """
        self._project_root = project_root
        self._symbol_graph: SymbolGraph | None = None
        self._link_graph: LinkGraph | None = None

    # --- lifecycle ---------------------------------------------------------

    def open(self) -> None:
        """Open both underlying graphs.

        If ``symbols.db`` does not exist on disk, ``_symbol_graph`` is
        left as ``None`` and a hint is emitted. The link graph is always
        opened — ``open_index`` returns ``None`` when ``index.db`` is
        missing, corrupt, or has a schema mismatch, so ``_link_graph``
        may also be ``None``.
        """
        from lexibrary.cli._output import hint  # noqa: PLC0415
        from lexibrary.linkgraph import open_index  # noqa: PLC0415
        from lexibrary.symbolgraph import open_symbol_graph  # noqa: PLC0415
        from lexibrary.utils.paths import symbols_db_path  # noqa: PLC0415

        db_path = symbols_db_path(self._project_root)
        if db_path.exists():
            self._symbol_graph = open_symbol_graph(self._project_root, create=False)
        else:
            self._symbol_graph = None
            hint(
                "symbols.db is missing — run `lexi design update <file>` to "
                "refresh a single file's entry, or ask the maintainer to run "
                "`lexictl update` for a full rebuild. Symbol queries will "
                "return empty results until then."
            )
        self._link_graph = open_index(self._project_root)

    def close(self) -> None:
        """Close whichever underlying graphs are currently open."""
        if self._symbol_graph is not None:
            self._symbol_graph.close()
            self._symbol_graph = None
        if self._link_graph is not None:
            self._link_graph.close()
            self._link_graph = None

    def __enter__(self) -> SymbolQueryService:
        """Enter the context manager, opening both graphs."""
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        """Exit the context manager, closing both graphs."""
        self.close()

    # --- queries -----------------------------------------------------------

    def trace(self, symbol_name: str, *, file: Path | None = None) -> TraceResponse:
        """Return the full trace (callers/callees/unresolved) for *symbol_name*.

        Dispatches by the presence of a ``.`` in the argument:

        - If *symbol_name* contains a dot, it is treated as a dotted
          qualified name (e.g. ``MyClass.method`` or
          ``auth.service.login``) and resolved via
          :meth:`~lexibrary.symbolgraph.query.SymbolGraph.symbols_by_qualified_name`.
        - Otherwise it is treated as a bare identifier and resolved via
          :meth:`~lexibrary.symbolgraph.query.SymbolGraph.symbols_by_name`.

        When *file* is given, the lookup is scoped to that file — useful
        when two modules declare the same symbol name.

        The response also carries a list of
        :class:`StaleSymbolWarning` for any result whose owning file has
        drifted on disk since the symbol graph was last built.

        When the symbol graph is unavailable, returns an empty
        :class:`TraceResponse`.
        """
        if self._symbol_graph is None:
            return TraceResponse(results=[], stale=[])

        file_path = str(file) if file is not None else None
        if "." in symbol_name:
            symbols = self._symbol_graph.symbols_by_qualified_name(symbol_name, file_path=file_path)
        else:
            symbols = self._symbol_graph.symbols_by_name(symbol_name, file_path=file_path)

        results: list[TraceResult] = []
        for sym in symbols:
            results.append(
                TraceResult(
                    symbol=sym,
                    callers=self._symbol_graph.callers_of(sym.id),
                    callees=self._symbol_graph.callees_of(sym.id),
                    unresolved_callees=self._symbol_graph.unresolved_callees_of(sym.id),
                    parents=self._symbol_graph.class_edges_from(sym.id),
                    children=self._symbol_graph.class_edges_to(sym.id),
                    unresolved_parents=self._symbol_graph.class_edges_unresolved_from(sym.id),
                )
            )

        stale = self._detect_stale(results)
        return TraceResponse(results=results, stale=stale)

    def search_symbols(self, query: str, *, limit: int = 20) -> list[SymbolSearchHit]:
        """Return up to *limit* symbols matching *query* via a LIKE search.

        The search matches against both ``symbols.name`` and
        ``symbols.qualified_name``; results are ordered by ``name`` and
        capped at *limit*. Wraps each row in a :class:`SymbolSearchHit`
        (score stays at ``0.0`` in Phase 2 — ranking lands in a later
        phase). Returns an empty list when the symbol graph is
        unavailable.
        """
        if self._symbol_graph is None:
            return []

        like = f"%{query}%"
        params: tuple[object, ...] = (like, like, limit)
        rows = self._symbol_graph.query_raw(
            _SELECT_SYMBOL
            + "WHERE s.name LIKE ? OR s.qualified_name LIKE ? "
            + "ORDER BY s.name LIMIT ?",
            params,
        )
        return [SymbolSearchHit(symbol=_row_to_symbol(row)) for row in rows]

    def symbols_in_file(self, file_path: str) -> SymbolsInFileResponse:
        """Return every symbol declared in *file_path* plus staleness info.

        Delegates to
        :meth:`~lexibrary.symbolgraph.query.SymbolGraph.symbols_in_file`
        for the symbol list and then calls
        :meth:`_detect_stale_single` to compute a
        :class:`StaleSymbolWarning` if the on-disk file has drifted.
        Returns an empty :class:`SymbolsInFileResponse` when the symbol
        graph is unavailable.
        """
        if self._symbol_graph is None:
            return SymbolsInFileResponse(symbols=[], stale=None)

        symbols = self._symbol_graph.symbols_in_file(file_path)
        stale = self._detect_stale_single(file_path)
        return SymbolsInFileResponse(symbols=symbols, stale=stale)

    # --- staleness helpers -------------------------------------------------

    def _detect_stale(self, results: list[TraceResult]) -> list[StaleSymbolWarning]:
        """Return one warning per unique file whose on-disk hash drifted.

        For every unique ``file_path`` referenced by *results*, compute
        the current SHA-256 of the on-disk file and compare against the
        ``last_hash`` recorded in the ``files`` table. Emits a warning on
        mismatch and when the file is missing from disk entirely.
        Silently skips files not present in ``files`` (e.g. a symbol
        whose owning file was removed from the graph mid-query).

        Uses :meth:`SymbolGraph.query_raw` exclusively — services must
        never poke at ``SymbolGraph._conn`` directly.
        """
        if self._symbol_graph is None:
            return []

        seen: set[str] = set()
        warnings: list[StaleSymbolWarning] = []
        for result in results:
            fp = result.symbol.file_path
            if fp in seen:
                continue
            seen.add(fp)
            warning = self._detect_stale_single(fp)
            if warning is not None:
                warnings.append(warning)
        return warnings

    def _detect_stale_single(self, file_path: str) -> StaleSymbolWarning | None:
        """Return a staleness warning for a single *file_path*, or ``None``.

        Returns ``None`` when the symbol graph is unavailable, when the
        file is not tracked in the ``files`` table, or when the stored
        ``last_hash`` matches the current on-disk SHA-256. Emits a
        warning when the on-disk file cannot be read (e.g. it was deleted
        since the graph was built) so the caller knows the graph is out
        of sync with the filesystem.
        """
        if self._symbol_graph is None:
            return None

        rows = self._symbol_graph.query_raw(
            "SELECT last_hash FROM files WHERE path = ?",
            (file_path,),
        )
        if not rows:
            return None
        stored_hash = rows[0][0]

        abs_path = self._project_root / file_path
        try:
            current_hash = hash_file(abs_path)
        except OSError:
            return StaleSymbolWarning(file_path=file_path)

        if stored_hash != current_hash:
            return StaleSymbolWarning(file_path=file_path)
        return None
