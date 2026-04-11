"""Tests for ``lexibrary.symbolgraph.query`` — skeleton query surface.

Phase 1 of ``symbol-graph-1`` ships the query module as a skeleton: every
public method returns an empty list and Phase 2 will replace the bodies
with real SQL. These tests pin the public lifecycle and the empty-result
contract so the later phase cannot accidentally break wiring.
"""

from __future__ import annotations

import dataclasses
import sqlite3
from pathlib import Path

import pytest

from lexibrary.symbolgraph.query import (
    CallRow,
    ClassEdgeRow,
    SymbolGraph,
    SymbolMemberRow,
    SymbolRow,
    UnresolvedCallRow,
    open_symbol_graph,
)
from lexibrary.utils.paths import symbols_db_path


def _assert_all_queries_empty(graph: SymbolGraph) -> None:
    """Every public query method must return ``[]`` during Phase 1."""
    assert graph.symbols_by_name("anything") == []
    assert graph.symbols_in_file("src/example.py") == []
    assert graph.callers_of(1) == []
    assert graph.callees_of(1) == []
    assert graph.unresolved_callees_of(1) == []
    assert graph.class_edges_from(1) == []
    assert graph.class_edges_to(1) == []
    assert graph.members_of(1) == []


# ---------------------------------------------------------------------------
# 1. Fresh DB creation
# ---------------------------------------------------------------------------


def test_open_symbol_graph_creates_db_file(tmp_path: Path) -> None:
    """``open_symbol_graph`` creates ``.lexibrary/symbols.db`` on first call.

    Also confirms that every public query method returns an empty list,
    matching the Phase 1 skeleton contract.
    """
    db_path = symbols_db_path(tmp_path)
    assert not db_path.exists()

    graph = open_symbol_graph(tmp_path)
    try:
        assert db_path.exists()
        assert db_path.parent.is_dir()
        _assert_all_queries_empty(graph)
    finally:
        graph.close()


# ---------------------------------------------------------------------------
# 2. Reuses existing DB without rebuilding
# ---------------------------------------------------------------------------


def test_open_symbol_graph_reuses_existing_db(tmp_path: Path) -> None:
    """A second ``open_symbol_graph`` call reuses the existing DB.

    Inserts a dummy row between opens and asserts it survives — proving
    that :func:`ensure_schema` did not trigger a rebuild (which would
    wipe ``files``).
    """
    # First open creates the schema.
    first = open_symbol_graph(tmp_path)
    try:
        first._conn.execute(
            "INSERT INTO files (path, language) VALUES (?, ?)",
            ("src/dummy.py", "python"),
        )
        first._conn.commit()
        assert first._conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 1
    finally:
        first.close()

    # Second open must reuse the existing DB and preserve the inserted row.
    second = open_symbol_graph(tmp_path)
    try:
        count = second._conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        assert count == 1, "ensure_schema wiped the dummy row — it should not rebuild"
        _assert_all_queries_empty(second)
    finally:
        second.close()


# ---------------------------------------------------------------------------
# 3. Context manager closes the underlying connection
# ---------------------------------------------------------------------------


def test_context_manager_closes_connection(tmp_path: Path) -> None:
    """Exiting the ``with`` block closes the connection.

    After exit, the wrapped ``sqlite3.Connection`` must raise
    :class:`sqlite3.ProgrammingError` on any further query attempt.
    """
    with open_symbol_graph(tmp_path) as graph:
        # Sanity: the connection is usable inside the block.
        graph._conn.execute("SELECT 1").fetchone()
        conn = graph._conn

    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")


# ---------------------------------------------------------------------------
# Sanity: re-exported row types are importable and frozen
# ---------------------------------------------------------------------------


def test_row_dataclasses_are_frozen() -> None:
    """Every result dataclass must be frozen so downstream callers can hash/cache."""
    symbol = SymbolRow(
        id=1,
        file_path="src/example.py",
        name="greet",
        qualified_name="example.greet",
        symbol_type="function",
        line_start=1,
        line_end=3,
        visibility="public",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        symbol.name = "mutated"  # type: ignore[misc]

    call = CallRow(caller=symbol, callee=symbol, line=2, call_context=None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        call.line = 99  # type: ignore[misc]

    unresolved = UnresolvedCallRow(caller=symbol, callee_name="print", line=2, call_context=None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        unresolved.line = 99  # type: ignore[misc]

    class_edge = ClassEdgeRow(
        source=symbol, target=symbol, edge_type="inherits", line=1, context=None
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        class_edge.edge_type = "instantiates"  # type: ignore[misc]

    member = SymbolMemberRow(parent=symbol, name="MEMBER_A", value="1", ordinal=0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        member.ordinal = 1  # type: ignore[misc]
