"""Read-only query interface for the symbol graph index.

Provides the :class:`SymbolGraph` class and frozen result dataclasses for
querying ``.lexibrary/symbols.db``. The graph stores symbol-level edges
(function calls, class hierarchy, enum members, module-level constants)
as a sibling database to the link graph's ``index.db``. See
``CN-021 Symbol Graph`` and ``docs/symbol-graph.md`` for the concept.

Phase 2 (symbol-graph-2) fills in real SQL for every ``symbols``,
``calls``, and ``unresolved_calls`` query. Phase 3 completion
(symbol-graph-3, group 1) adds real SQL for ``class_edges_from``,
``class_edges_to``, and ``members_of`` — the class-edges and member
queries now execute against their tables even though the tables only
become populated once the Phase 3 builder pass 3 and Phase 4 extractor
run. Row shapes and public method signatures are stable — downstream
callers (``services/symbols.py``, ``services/lookup.py``, the CLI)
import and call these directly.

Contract summary
----------------

- Result dataclasses are ``@dataclass(frozen=True)`` and use the exact
  field names the query bodies populate.
- :class:`SymbolGraph` wraps a ``sqlite3.Connection``. Most callers
  should use :func:`open_symbol_graph`, which handles path resolution,
  pragma setup, and schema creation in one call.
- :func:`open_symbol_graph` creates the DB file and its parent
  ``.lexibrary/`` directory when ``create=True`` (the default). Pass
  ``create=False`` to open an existing database without mutating the
  filesystem — the health reporter relies on this.
- Internally, every symbol-producing query builds on the module-level
  ``_SELECT_SYMBOL`` constant so the ``symbols ⋈ files`` projection and
  column order are defined exactly once.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NamedTuple

from lexibrary.symbolgraph.schema import ensure_schema, set_pragmas
from lexibrary.utils.paths import symbols_db_path

# ---------------------------------------------------------------------------
# Shared SQL fragments
# ---------------------------------------------------------------------------

_SELECT_SYMBOL = (
    "SELECT s.id, f.path, s.name, s.qualified_name, s.symbol_type, "
    "s.line_start, s.line_end, s.visibility "
    "FROM symbols s "
    "JOIN files f ON f.id = s.file_id "
)
"""Shared projection + join for every symbol-producing query.

Matches the column order consumed by :func:`_row_to_symbol`:
``(id, file_path, name, qualified_name, symbol_type, line_start,
line_end, visibility)``. Extend by appending a ``WHERE`` / ``ORDER BY``
clause — never reorder the ``SELECT`` list, or the row-to-dataclass
mapping will silently produce wrong results.
"""

_SELECT_CALL_EDGE = (
    "SELECT "
    "caller_s.id, caller_f.path, caller_s.name, caller_s.qualified_name, "
    "caller_s.symbol_type, caller_s.line_start, caller_s.line_end, "
    "caller_s.visibility, "
    "callee_s.id, callee_f.path, callee_s.name, callee_s.qualified_name, "
    "callee_s.symbol_type, callee_s.line_start, callee_s.line_end, "
    "callee_s.visibility, "
    "c.line, c.call_context "
    "FROM calls c "
    "JOIN symbols caller_s ON caller_s.id = c.caller_id "
    "JOIN files caller_f ON caller_f.id = caller_s.file_id "
    "JOIN symbols callee_s ON callee_s.id = c.callee_id "
    "JOIN files callee_f ON callee_f.id = callee_s.file_id "
)
"""Shared projection + joins for resolved call edges.

Used by :meth:`SymbolGraph.callers_of` and :meth:`SymbolGraph.callees_of`.
Joins ``calls`` to ``symbols`` and ``files`` twice — once aliased as
``caller_s`` / ``caller_f`` for the caller endpoint, once as
``callee_s`` / ``callee_f`` for the callee endpoint — so a single SQL
round trip returns both endpoints' full metadata. Eighteen columns in
total: eight caller fields, eight callee fields, then ``c.line`` and
``c.call_context``. :func:`_row_to_call` depends on this exact order.
"""

_SELECT_UNRESOLVED_CALL = (
    "SELECT "
    "caller_s.id, caller_f.path, caller_s.name, caller_s.qualified_name, "
    "caller_s.symbol_type, caller_s.line_start, caller_s.line_end, "
    "caller_s.visibility, "
    "uc.callee_name, uc.line, uc.call_context "
    "FROM unresolved_calls uc "
    "JOIN symbols caller_s ON caller_s.id = uc.caller_id "
    "JOIN files caller_f ON caller_f.id = caller_s.file_id "
)
"""Shared projection + joins for unresolved call edges.

Used by :meth:`SymbolGraph.unresolved_callees_of`. Joins
``unresolved_calls`` to the caller's ``symbols`` and ``files`` rows
(aliased as ``caller_s`` / ``caller_f``); the callee is a bare name, so
no callee join exists. Eleven columns in total: the first eight match
the ``_SELECT_SYMBOL`` caller projection, followed by ``callee_name``,
``line``, and ``call_context``.
"""

_SELECT_CLASS_EDGE = (
    "SELECT "
    "source_s.id, source_f.path, source_s.name, source_s.qualified_name, "
    "source_s.symbol_type, source_s.line_start, source_s.line_end, "
    "source_s.visibility, "
    "target_s.id, target_f.path, target_s.name, target_s.qualified_name, "
    "target_s.symbol_type, target_s.line_start, target_s.line_end, "
    "target_s.visibility, "
    "ce.edge_type, ce.line, ce.context "
    "FROM class_edges ce "
    "JOIN symbols source_s ON source_s.id = ce.source_id "
    "JOIN files source_f ON source_f.id = source_s.file_id "
    "JOIN symbols target_s ON target_s.id = ce.target_id "
    "JOIN files target_f ON target_f.id = target_s.file_id "
)
"""Shared projection + joins for class relationship edges.

Used by :meth:`SymbolGraph.class_edges_from` and
:meth:`SymbolGraph.class_edges_to`. Joins ``class_edges`` to ``symbols``
and ``files`` twice — once aliased as ``source_s`` / ``source_f`` for
the source endpoint, once as ``target_s`` / ``target_f`` for the target
endpoint — so a single SQL round trip returns both endpoints' full
metadata. Nineteen columns in total: eight source fields, eight target
fields, then ``ce.edge_type``, ``ce.line``, and ``ce.context``.
:func:`_row_to_class_edge` depends on this exact order.
"""

_SELECT_SYMBOL_MEMBER = (
    "SELECT "
    "parent_s.id, parent_f.path, parent_s.name, parent_s.qualified_name, "
    "parent_s.symbol_type, parent_s.line_start, parent_s.line_end, "
    "parent_s.visibility, "
    "sm.name, sm.value, sm.ordinal "
    "FROM symbol_members sm "
    "JOIN symbols parent_s ON parent_s.id = sm.symbol_id "
    "JOIN files parent_f ON parent_f.id = parent_s.file_id "
)
"""Shared projection + joins for symbol members.

Used by :meth:`SymbolGraph.members_of`. Joins ``symbol_members`` to the
parent's ``symbols`` and ``files`` rows (aliased as ``parent_s`` /
``parent_f``). Eleven columns in total: the first eight match the
``_SELECT_SYMBOL`` parent projection, followed by ``sm.name``,
``sm.value``, and ``sm.ordinal``. :func:`_row_to_member` depends on
this exact order.
"""


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SymbolRow:
    """A single symbol (function, method, class, enum, or constant).

    Mirrors a row from the ``symbols`` table. ``id`` is the primary key;
    ``file_path`` is the joined ``files.path`` for the owning file.
    ``qualified_name`` is the dotted path when available (e.g.
    ``"auth.service.login"``); ``symbol_type`` is one of
    ``'function' | 'method' | 'class' | 'enum' | 'constant'``.
    ``line_start`` / ``line_end`` are 1-based source positions;
    ``visibility`` is ``'public'`` or ``'private'`` (or ``None`` when the
    language doesn't distinguish).
    """

    id: int
    file_path: str
    name: str
    qualified_name: str | None
    symbol_type: str
    line_start: int | None
    line_end: int | None
    visibility: str | None


@dataclass(frozen=True)
class CallRow:
    """A resolved call edge between two symbols.

    Returned by :meth:`SymbolGraph.callers_of` and
    :meth:`SymbolGraph.callees_of`. Both endpoints are
    fully-populated :class:`SymbolRow` instances, so callers do not need
    to issue a second lookup to display caller/callee metadata.
    """

    caller: SymbolRow
    callee: SymbolRow
    line: int
    call_context: str | None


@dataclass(frozen=True)
class UnresolvedCallRow:
    """A call edge whose callee could not be resolved to a known symbol.

    Unresolved calls appear when the AST extractor sees a call target
    that is not in the symbols table (e.g. calls into a third-party
    library, dynamically constructed attributes, or builtins). The
    callee is recorded as a string name in ``callee_name``.
    """

    caller: SymbolRow
    callee_name: str
    line: int
    call_context: str | None


@dataclass(frozen=True)
class ClassEdgeRow:
    """A class-level relationship edge between two symbols.

    ``edge_type`` is one of ``'inherits' | 'instantiates' | 'composes'``
    (Phase 6 forward-compat). Returned by
    :meth:`SymbolGraph.class_edges_from` and
    :meth:`SymbolGraph.class_edges_to`.
    """

    source: SymbolRow
    target: SymbolRow
    edge_type: str
    line: int | None
    context: str | None


class UnresolvedClassEdgeRow(NamedTuple):
    """A class edge whose target could not be resolved to a known symbol.

    Unresolved class edges appear when the builder's pass 3 sees a base
    class or instantiation target that is not in the symbols table — for
    example a Pydantic ``BaseModel`` reference in a project that does not
    index Pydantic itself, or an intra-project name that imports fail to
    resolve. The target is recorded as a plain string name in
    ``target_name``; ``edge_type`` mirrors the ``class_edges`` edge type
    (``'inherits'`` / ``'instantiates'`` / ``'composes'``); ``line`` is
    the source-file line of the edge when captured, or ``None``.

    Returned by :meth:`SymbolGraph.class_edges_unresolved_from`.
    """

    target_name: str
    edge_type: str
    line: int | None


@dataclass(frozen=True)
class SymbolMemberRow:
    """A member of a parent symbol (enum variant, class constant, etc.).

    Returned by :meth:`SymbolGraph.members_of`. ``value`` holds the
    literal textual value when the extractor can capture it (e.g.
    ``"42"`` for an integer constant); ``ordinal`` is the source-order
    position within the parent when available.
    """

    parent: SymbolRow
    name: str
    value: str | None
    ordinal: int | None


# ---------------------------------------------------------------------------
# Private row-to-dataclass adapters
# ---------------------------------------------------------------------------


def _row_to_symbol(row: Sequence[Any]) -> SymbolRow:
    """Convert a positional ``_SELECT_SYMBOL`` row into a :class:`SymbolRow`.

    The ``_SELECT_SYMBOL`` projection yields eight columns in the order
    ``(id, file_path, name, qualified_name, symbol_type, line_start,
    line_end, visibility)``. This helper preserves that order verbatim.
    Accepts either a full 8-column row or an 8-element slice of a wider
    row (e.g. the caller subrange of a ``_SELECT_CALL_EDGE`` result).
    """
    return SymbolRow(
        id=int(row[0]),
        file_path=str(row[1]),
        name=str(row[2]),
        qualified_name=None if row[3] is None else str(row[3]),
        symbol_type=str(row[4]),
        line_start=None if row[5] is None else int(row[5]),
        line_end=None if row[6] is None else int(row[6]),
        visibility=None if row[7] is None else str(row[7]),
    )


def _row_to_call(row: Sequence[Any]) -> CallRow:
    """Convert a positional ``_SELECT_CALL_EDGE`` row into a :class:`CallRow`.

    The ``_SELECT_CALL_EDGE`` projection yields eighteen columns: eight
    caller fields, eight callee fields, then ``line`` and ``call_context``.
    Caller and callee subranges are unpacked via :func:`_row_to_symbol`
    so the single-symbol column ordering is defined in exactly one place.
    """
    caller = _row_to_symbol(row[0:8])
    callee = _row_to_symbol(row[8:16])
    return CallRow(
        caller=caller,
        callee=callee,
        line=int(row[16]),
        call_context=None if row[17] is None else str(row[17]),
    )


def _row_to_unresolved_call(row: Sequence[Any]) -> UnresolvedCallRow:
    """Convert a positional ``_SELECT_UNRESOLVED_CALL`` row.

    The projection yields eleven columns: the first eight match the
    single-symbol caller subrange, followed by ``callee_name``,
    ``line``, and ``call_context``.
    """
    caller = _row_to_symbol(row[0:8])
    return UnresolvedCallRow(
        caller=caller,
        callee_name=str(row[8]),
        line=int(row[9]),
        call_context=None if row[10] is None else str(row[10]),
    )


def _row_to_class_edge(row: Sequence[Any]) -> ClassEdgeRow:
    """Convert a positional ``_SELECT_CLASS_EDGE`` row into a :class:`ClassEdgeRow`.

    The ``_SELECT_CLASS_EDGE`` projection yields nineteen columns: eight
    source fields, eight target fields, then ``edge_type``, ``line``,
    and ``context``. Source and target subranges are unpacked via
    :func:`_row_to_symbol` so the single-symbol column ordering is
    defined in exactly one place.
    """
    source = _row_to_symbol(row[0:8])
    target = _row_to_symbol(row[8:16])
    return ClassEdgeRow(
        source=source,
        target=target,
        edge_type=str(row[16]),
        line=None if row[17] is None else int(row[17]),
        context=None if row[18] is None else str(row[18]),
    )


def _row_to_member(row: Sequence[Any]) -> SymbolMemberRow:
    """Convert a positional ``_SELECT_SYMBOL_MEMBER`` row into a :class:`SymbolMemberRow`.

    The projection yields eleven columns: the first eight match the
    single-symbol parent subrange, followed by ``name``, ``value``, and
    ``ordinal``.
    """
    parent = _row_to_symbol(row[0:8])
    return SymbolMemberRow(
        parent=parent,
        name=str(row[8]),
        value=None if row[9] is None else str(row[9]),
        ordinal=None if row[10] is None else int(row[10]),
    )


# ---------------------------------------------------------------------------
# SymbolGraph — read-only query surface
# ---------------------------------------------------------------------------


class SymbolGraph:
    """Read-only query interface for ``symbols.db``.

    Wraps an already-open :class:`sqlite3.Connection`. Callers should
    typically construct instances via :func:`open_symbol_graph`, which
    handles path resolution, pragma setup, and schema creation.

    Supports the context manager protocol (``with open_symbol_graph(...)
    as g:``) and explicit :meth:`close`. Closing the graph closes the
    underlying connection; any further query attempts raise
    :class:`sqlite3.ProgrammingError`.

    Query coverage
    --------------

    - :meth:`symbols_by_name`, :meth:`symbols_by_qualified_name`,
      :meth:`symbols_in_file` — symbol lookups over ``symbols ⋈ files``.
    - :meth:`callers_of`, :meth:`callees_of` — resolved call edges with
      both endpoints populated via :data:`_SELECT_CALL_EDGE`.
    - :meth:`unresolved_callees_of` — unresolved call sites joined to
      the caller symbol/file.
    - :meth:`symbol_call_counts` — single-query aggregation used by
      ``lexi lookup``'s "Key symbols" section.
    - :meth:`query_raw` — ad-hoc ``SELECT`` escape hatch for services
      that don't yet have a dedicated method (prefer dedicated methods).
    - :meth:`class_edges_from`, :meth:`class_edges_to` — resolved
      class-hierarchy edges joining ``class_edges`` to its source /
      target endpoints. Populated once the Phase 3 builder pass 3 has
      run; returns an empty list before then.
    - :meth:`class_edges_unresolved_from` — unresolved outbound class
      edges (e.g. external bases like ``BaseModel``) read from the
      ``class_edges_unresolved`` table. Populated by the same pass 3
      run; returns an empty list before then.
    - :meth:`members_of` — members (enum variants, class constants)
      joining ``symbol_members`` to the parent symbol. Populated once
      the Phase 4 extractor has run; returns an empty list before then.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        """Wrap an already-open SQLite connection for read-only queries.

        Parameters
        ----------
        conn:
            An open :class:`sqlite3.Connection`. Callers are responsible
            for ensuring pragmas have been set and the schema is
            compatible. Prefer :func:`open_symbol_graph` for normal use.
        """
        self._conn = conn

    # -- lifecycle ----------------------------------------------------------

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()

    def __enter__(self) -> SymbolGraph:
        """Enter the context manager, returning *self*."""
        return self

    def __exit__(self, *_: object) -> None:
        """Exit the context manager, closing the connection."""
        self.close()

    # -- symbol lookups -----------------------------------------------------

    def symbols_by_name(self, name: str, *, file_path: str | None = None) -> list[SymbolRow]:
        """Return all symbols whose bare ``name`` equals *name*.

        Matches against ``symbols.name`` — the short, un-qualified
        identifier that appears in source (e.g. ``login``, not
        ``auth.service.login``). When *file_path* is given, restricts the
        match to symbols declared in that file. Results are ordered by
        file path then source position so the caller gets a stable,
        display-friendly iteration.
        """
        if file_path is None:
            sql = _SELECT_SYMBOL + "WHERE s.name = ? ORDER BY f.path, s.line_start"
            params: tuple[object, ...] = (name,)
        else:
            sql = _SELECT_SYMBOL + "WHERE s.name = ? AND f.path = ? ORDER BY f.path, s.line_start"
            params = (name, file_path)
        rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_symbol(row) for row in rows]

    def symbols_by_qualified_name(
        self, qualified_name: str, *, file_path: str | None = None
    ) -> list[SymbolRow]:
        """Return all symbols whose ``qualified_name`` equals *qualified_name*.

        Exact match against the dotted path emitted by the parser (e.g.
        ``auth.service.login`` or ``MyClass.method``). Distinguished from
        :meth:`symbols_by_name`, which matches the bare identifier. When
        *file_path* is given, restricts the match to symbols declared in
        that file — useful when two modules share a qualified name.
        Results are ordered by file path then source position.
        """
        if file_path is None:
            sql = _SELECT_SYMBOL + "WHERE s.qualified_name = ? ORDER BY f.path, s.line_start"
            params: tuple[object, ...] = (qualified_name,)
        else:
            sql = (
                _SELECT_SYMBOL
                + "WHERE s.qualified_name = ? AND f.path = ? "
                + "ORDER BY f.path, s.line_start"
            )
            params = (qualified_name, file_path)
        rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_symbol(row) for row in rows]

    def symbols_in_file(self, file_path: str) -> list[SymbolRow]:
        """Return all symbols declared in the file at *file_path*.

        Results are ordered by ``line_start`` so callers that render the
        list — notably ``lexi lookup``'s "Key symbols" table — see them
        in source order.
        """
        sql = _SELECT_SYMBOL + "WHERE f.path = ? ORDER BY s.line_start"
        rows = self._conn.execute(sql, (file_path,)).fetchall()
        return [_row_to_symbol(row) for row in rows]

    def symbols_with_member_value_like(self, needle: str) -> list[SymbolRow]:
        """Return every symbol that has a member whose ``value`` ``LIKE`` *needle*.

        Powers the "search by enum member value or constant value" leg of
        ``lexi search --type symbol``. Joins ``symbol_members`` to the
        parent :data:`_SELECT_SYMBOL` projection and filters on
        ``sm.value LIKE ?`` so a user searching for ``"pending"`` surfaces
        the canonical enum whose variant value is that string. Results
        are de-duplicated via ``GROUP BY s.id`` so a parent with multiple
        matching members still appears only once, and ordered by
        ``s.name`` for deterministic display.

        *needle* is wrapped in ``%`` wildcards on both sides so the match
        is a case-sensitive substring match (the default SQLite ``LIKE``
        behaviour). Returns an empty list when ``symbol_members`` is
        empty or no row matches — callers get the same "empty not error"
        contract as every other :class:`SymbolGraph` query.
        """
        sql = (
            _SELECT_SYMBOL
            + "JOIN symbol_members sm ON sm.symbol_id = s.id "
            + "WHERE sm.value LIKE ? "
            + "GROUP BY s.id "
            + "ORDER BY s.name"
        )
        rows = self._conn.execute(sql, (f"%{needle}%",)).fetchall()
        return [_row_to_symbol(row) for row in rows]

    # -- call edges ---------------------------------------------------------

    def callers_of(self, symbol_id: int) -> list[CallRow]:
        """Return resolved call edges whose *callee* is *symbol_id*.

        Single SQL query against :data:`_SELECT_CALL_EDGE` filtered by
        ``c.callee_id``; both endpoints come back fully populated, so
        the caller never has to reissue a second lookup to render caller
        metadata. Ordered by caller file path then call-site line so the
        output is deterministic for tests and display.
        """
        sql = _SELECT_CALL_EDGE + "WHERE c.callee_id = ? ORDER BY caller_f.path, c.line"
        rows = self._conn.execute(sql, (symbol_id,)).fetchall()
        return [_row_to_call(row) for row in rows]

    def callees_of(self, symbol_id: int) -> list[CallRow]:
        """Return resolved call edges whose *caller* is *symbol_id*.

        Outbound half of :meth:`callers_of`: same
        :data:`_SELECT_CALL_EDGE` join, filtered on ``c.caller_id``.
        Ordered by call-site line so the results render in source order
        within the caller.
        """
        sql = _SELECT_CALL_EDGE + "WHERE c.caller_id = ? ORDER BY c.line, callee_f.path"
        rows = self._conn.execute(sql, (symbol_id,)).fetchall()
        return [_row_to_call(row) for row in rows]

    def unresolved_callees_of(self, symbol_id: int) -> list[UnresolvedCallRow]:
        """Return unresolved call targets invoked from *symbol_id*.

        Unresolved calls are AST-detected call sites whose target did
        not resolve to a known symbol (third-party libraries, builtins,
        dynamic attribute access, etc.). The callee is captured as a
        plain string name; the caller is a fully-populated
        :class:`SymbolRow`. Ordered by call-site line.
        """
        sql = _SELECT_UNRESOLVED_CALL + "WHERE uc.caller_id = ? ORDER BY uc.line, uc.callee_name"
        rows = self._conn.execute(sql, (symbol_id,)).fetchall()
        return [_row_to_unresolved_call(row) for row in rows]

    def symbol_call_counts(self, file_path: str) -> dict[int, tuple[int, int]]:
        """Return ``{symbol_id: (caller_count, callee_count)}`` for *file_path*.

        Single SQL query — the two LEFT JOINs aggregate ``calls`` by
        ``callee_id`` and ``caller_id`` respectively, so one round trip
        to SQLite yields every public-symbol count card ``lexi lookup``
        renders. Symbols with zero incoming and zero outgoing calls are
        still included (with ``(0, 0)``) so callers can distinguish
        "present but cold" from "not in this file". Used by
        ``services/lookup.py`` to avoid issuing ``callers_of`` /
        ``callees_of`` once per symbol.
        """
        sql = (
            "SELECT s.id, "
            "COALESCE(c_in.n, 0)  AS callers, "
            "COALESCE(c_out.n, 0) AS callees "
            "FROM symbols s "
            "JOIN files f ON f.id = s.file_id "
            "LEFT JOIN ("
            "    SELECT callee_id AS sid, COUNT(*) AS n "
            "    FROM calls GROUP BY callee_id"
            ") c_in  ON c_in.sid  = s.id "
            "LEFT JOIN ("
            "    SELECT caller_id AS sid, COUNT(*) AS n "
            "    FROM calls GROUP BY caller_id"
            ") c_out ON c_out.sid = s.id "
            "WHERE f.path = ?"
        )
        rows = self._conn.execute(sql, (file_path,)).fetchall()
        return {int(row[0]): (int(row[1]), int(row[2])) for row in rows}

    # -- class edges --------------------------------------------------------

    def class_edges_from(self, symbol_id: int) -> list[ClassEdgeRow]:
        """Return class edges whose *source* is *symbol_id*.

        Single SQL query against :data:`_SELECT_CLASS_EDGE` filtered by
        ``ce.source_id``; both endpoints come back fully populated.
        Ordered by ``edge_type`` then target file path then call-site
        line so inheritance edges render before instantiation edges and
        the output is deterministic for tests and display.

        The ``class_edges`` table is populated by the symbol graph
        builder's pass 3 (``symbol-graph-3``). This method returns an
        empty list when the table is empty (e.g. before pass 3 has run
        for any file).
        """
        sql = (
            _SELECT_CLASS_EDGE
            + "WHERE ce.source_id = ? "
            + "ORDER BY ce.edge_type, target_f.path, ce.line"
        )
        rows = self._conn.execute(sql, (symbol_id,)).fetchall()
        return [_row_to_class_edge(row) for row in rows]

    def class_edges_to(self, symbol_id: int) -> list[ClassEdgeRow]:
        """Return class edges whose *target* is *symbol_id*.

        Matching inbound half of :meth:`class_edges_from`: same
        :data:`_SELECT_CLASS_EDGE` join, filtered on ``ce.target_id``.
        Ordered by ``edge_type`` then source file path then call-site
        line so the results render deterministically — all inbound
        ``inherits`` (subclasses) before inbound ``instantiates``
        (instantiation sites).
        """
        sql = (
            _SELECT_CLASS_EDGE
            + "WHERE ce.target_id = ? "
            + "ORDER BY ce.edge_type, source_f.path, ce.line"
        )
        rows = self._conn.execute(sql, (symbol_id,)).fetchall()
        return [_row_to_class_edge(row) for row in rows]

    def class_edges_unresolved_from(self, symbol_id: int) -> list[UnresolvedClassEdgeRow]:
        """Return unresolved class edges whose *source* is *symbol_id*.

        Reads rows from ``class_edges_unresolved`` whose ``source_id``
        matches *symbol_id*. Each row describes an inheritance or
        instantiation target that the builder's pass 3 could not resolve
        to a known symbol — typically a third-party base class like
        ``pydantic.BaseModel`` or ``enum.Enum`` in a project that does
        not index its dependencies.

        Ordered by ``edge_type`` then ``target_name`` then ``line`` so
        inheritance rows render before instantiation rows and the output
        is deterministic for tests and display. Returns an empty list
        when the source has no unresolved edges (including when the
        ``class_edges_unresolved`` table is empty).
        """
        sql = (
            "SELECT target_name, edge_type, line "
            "FROM class_edges_unresolved "
            "WHERE source_id = ? "
            "ORDER BY edge_type, target_name, line"
        )
        rows = self._conn.execute(sql, (symbol_id,)).fetchall()
        return [
            UnresolvedClassEdgeRow(
                target_name=str(row[0]),
                edge_type=str(row[1]),
                line=None if row[2] is None else int(row[2]),
            )
            for row in rows
        ]

    # -- members ------------------------------------------------------------

    def members_of(self, symbol_id: int) -> list[SymbolMemberRow]:
        """Return the members of a parent symbol (enum variants, etc.).

        Single SQL query against :data:`_SELECT_SYMBOL_MEMBER` filtered
        by ``sm.symbol_id``. Results are ordered by ``ordinal`` (NULLs
        last) and then ``name`` so source-order iteration is preserved
        for enums while still yielding a deterministic ordering when
        the extractor did not capture ordinals.

        The ``symbol_members`` table is populated by
        ``symbol-graph-4``. This method returns an empty list when the
        table is empty for a given parent (e.g. classes and functions
        that have no recorded members).
        """
        sql = (
            _SELECT_SYMBOL_MEMBER
            + "WHERE sm.symbol_id = ? "
            + "ORDER BY sm.ordinal IS NULL, sm.ordinal, sm.name"
        )
        rows = self._conn.execute(sql, (symbol_id,)).fetchall()
        return [_row_to_member(row) for row in rows]

    # -- raw escape hatch ---------------------------------------------------

    def query_raw(self, sql: str, params: tuple[object, ...] = ()) -> list[sqlite3.Row]:
        """Execute an arbitrary ``SELECT`` and return the raw rows.

        Escape hatch for services that need an ad-hoc read the typed API
        does not yet expose — for example, the ``LIKE``-style symbol
        search used by ``lexi search --type symbol``. **Prefer a
        dedicated method.** Any read that recurs across more than one
        call site should graduate to a typed :class:`SymbolGraph`
        method so the query surface stays auditable from one place.

        Parameters
        ----------
        sql:
            The ``SELECT`` statement to execute. The connection is held
            open read-only but nothing prevents a destructive statement;
            callers are trusted not to mutate the database here.
        params:
            Positional SQL parameters, passed straight to
            :meth:`sqlite3.Connection.execute`.

        Returns
        -------
        list[sqlite3.Row]
            Whatever ``fetchall()`` yields — a list of tuple-like
            :class:`sqlite3.Row` objects. The caller is responsible for
            interpreting positional columns, since ``query_raw`` has no
            dataclass view over the result.
        """
        return self._conn.execute(sql, params).fetchall()


# ---------------------------------------------------------------------------
# Module-level convenience opener
# ---------------------------------------------------------------------------


def open_symbol_graph(project_root: Path, *, create: bool = True) -> SymbolGraph:
    """Open ``symbols.db`` and return a :class:`SymbolGraph` for queries.

    Resolves the database path via
    :func:`lexibrary.utils.paths.symbols_db_path`, opens a SQLite
    connection, applies
    :func:`~lexibrary.symbolgraph.schema.set_pragmas`, and runs
    :func:`~lexibrary.symbolgraph.schema.ensure_schema` so the returned
    graph is always query-ready.

    Parameters
    ----------
    project_root:
        Absolute path to the repository root.
    create:
        When ``True`` (default), ensure the parent ``.lexibrary/``
        directory exists before opening — this is the normal write
        path used by the builder and services. When ``False``, the
        caller must guarantee the directory exists; the function will
        not create it.

    Returns
    -------
    SymbolGraph
        A ready-to-query graph wrapping an open connection. Callers are
        responsible for closing the graph (prefer a ``with`` block).
    """
    db_path = symbols_db_path(project_root)
    if create:
        db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    set_pragmas(conn)
    ensure_schema(conn)
    return SymbolGraph(conn)
