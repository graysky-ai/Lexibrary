"""Direct SQL tests for ``symbols_with_member_value_like``.

Phase 4 (``symbol-graph-4``) adds a dedicated query method that joins
``symbol_members`` to the ``_SELECT_SYMBOL`` projection so ``lexi search
--type symbol <value>`` can find the canonical enum behind a literal
string or integer that appears in a bug. These tests pin the exact
match semantics — a substring ``LIKE`` against ``sm.value`` — and the
de-duplication / ordering behaviour expected by the service layer.

The tests share the seed corpus from
:func:`tests.test_symbolgraph.test_query_impl._seed_graph` and extend
it with a handful of ``symbol_members`` rows so each scenario is
isolated to the method under test.
"""

from __future__ import annotations

from pathlib import Path

from lexibrary.symbolgraph.query import SymbolRow
from tests.test_symbolgraph.test_query_impl import _seed_graph


def _seed_members(graph_conn: object, symbol_id: int, pairs: list[tuple[str, str | None]]) -> None:
    """Insert ``(name, value, ordinal)`` rows for *symbol_id*.

    ``pairs`` is ``[(name, value), ...]``; the ordinal is the list index.
    """
    for idx, (name, value) in enumerate(pairs):
        graph_conn.execute(  # type: ignore[attr-defined]
            "INSERT INTO symbol_members (symbol_id, name, value, ordinal) VALUES (?, ?, ?, ?)",
            (symbol_id, name, value, idx),
        )


# ---------------------------------------------------------------------------
# Scenario 1 — enum member value match
# ---------------------------------------------------------------------------


def test_symbols_with_member_value_like_finds_enum(tmp_path: Path) -> None:
    """A value ``LIKE`` match on an enum member surfaces the parent enum."""
    graph, symbol_ids, _ = _seed_graph(tmp_path)
    try:
        conn = graph._conn

        # Reclassify ``Hello`` as an enum so the test corpus has a
        # realistic target — the seed helper does not care about type
        # correctness beyond the schema.
        conn.execute(
            "UPDATE symbols SET symbol_type = 'enum' WHERE id = ?",
            (symbol_ids["Hello"],),
        )
        _seed_members(
            conn,
            symbol_ids["Hello"],
            [("PENDING", '"pending"'), ("RUNNING", '"running"'), ("DONE", '"done"')],
        )
        conn.commit()

        rows = graph.symbols_with_member_value_like("pending")
        assert len(rows) == 1
        row = rows[0]
        assert isinstance(row, SymbolRow)
        assert row.id == symbol_ids["Hello"]
        assert row.name == "Hello"
        assert row.symbol_type == "enum"
        assert row.file_path == "src/a.py"
    finally:
        graph.close()


# ---------------------------------------------------------------------------
# Scenario 2 — constant value match
# ---------------------------------------------------------------------------


def test_symbols_with_member_value_like_finds_constant(tmp_path: Path) -> None:
    """A value ``LIKE`` match on a constant-value member surfaces the constant symbol."""
    graph, symbol_ids, _ = _seed_graph(tmp_path)
    try:
        conn = graph._conn
        # The seed fixture already has ``CONSTANT`` as symbol_type='constant'.
        _seed_members(conn, symbol_ids["CONSTANT"], [("CONSTANT", "42")])
        conn.commit()

        rows = graph.symbols_with_member_value_like("42")
        assert len(rows) == 1
        assert rows[0].id == symbol_ids["CONSTANT"]
        assert rows[0].symbol_type == "constant"
        assert rows[0].name == "CONSTANT"
    finally:
        graph.close()


# ---------------------------------------------------------------------------
# Scenario 3 — no match
# ---------------------------------------------------------------------------


def test_symbols_with_member_value_like_no_match(tmp_path: Path) -> None:
    """A needle that matches no member value yields an empty list."""
    graph, symbol_ids, _ = _seed_graph(tmp_path)
    try:
        conn = graph._conn
        _seed_members(conn, symbol_ids["Hello"], [("ALPHA", '"alpha"')])
        conn.commit()

        rows = graph.symbols_with_member_value_like("not_there")
        assert rows == []

        # Empty ``symbol_members`` table (another parent) also yields [].
        rows_missing = graph.symbols_with_member_value_like("never_inserted")
        assert rows_missing == []
    finally:
        graph.close()


# ---------------------------------------------------------------------------
# Scenario 4 — partial (substring) match
# ---------------------------------------------------------------------------


def test_symbols_with_member_value_like_partial_match(tmp_path: Path) -> None:
    """A partial substring of a stored value matches and results are de-duplicated."""
    graph, symbol_ids, _ = _seed_graph(tmp_path)
    try:
        conn = graph._conn
        # Seed ``Hello`` with two members whose values both contain
        # ``error`` — the de-dup pass (``GROUP BY s.id``) must collapse
        # these into a single row rather than returning ``Hello`` twice.
        _seed_members(
            conn,
            symbol_ids["Hello"],
            [("AUTH_ERROR", '"auth_error"'), ("DB_ERROR", '"db_error"')],
        )
        # A second parent with a non-matching member must NOT appear.
        _seed_members(conn, symbol_ids["shout"], [("LOUD", '"shout"')])
        conn.commit()

        rows = graph.symbols_with_member_value_like("error")
        # ``Hello`` shows up exactly once thanks to GROUP BY s.id.
        assert len(rows) == 1
        assert rows[0].id == symbol_ids["Hello"]
        # Ordering is by s.name, so when a second parent joins later the
        # order is deterministic.
        _seed_members(conn, symbol_ids["greet"], [("GREETING", '"errored"')])
        conn.commit()
        rows = graph.symbols_with_member_value_like("error")
        names = [row.name for row in rows]
        assert names == sorted(names)
        assert set(names) == {"Hello", "greet"}
    finally:
        graph.close()
