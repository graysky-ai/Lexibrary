"""Tests for ``lexibrary.symbolgraph.schema`` — DDL, pragmas, and rebuild logic.

Mirrors the shape of the link graph schema tests: an in-memory SQLite database
per test exercises the public :func:`ensure_schema` contract plus pragma
setup, CHECK constraints, cascade deletes, and meta round-tripping.

The tail of the file also pins the Phase 1 behaviour of
:func:`lexibrary.symbolgraph.builder.build_symbol_graph` — it is driven by
the same schema under test and exercised with the real ``LexibraryConfig``
defaults.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from lexibrary.config.schema import LexibraryConfig
from lexibrary.symbolgraph import schema as symbol_schema
from lexibrary.symbolgraph.builder import SymbolBuildResult, build_symbol_graph
from lexibrary.symbolgraph.schema import (
    SCHEMA_VERSION,
    check_schema_version,
    ensure_schema,
    set_pragmas,
)
from lexibrary.utils.paths import symbols_db_path

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_EXPECTED_TABLES: frozenset[str] = frozenset(
    {
        "meta",
        "files",
        "symbols",
        "symbol_members",
        "calls",
        "unresolved_calls",
        "class_edges",
        "class_edges_unresolved",
    }
)


@pytest.fixture
def conn() -> sqlite3.Connection:
    """A fresh in-memory SQLite connection with the full schema applied."""
    connection = sqlite3.connect(":memory:")
    ensure_schema(connection)
    return connection


def _tables_in(conn: sqlite3.Connection) -> set[str]:
    """Return the set of user tables present in *conn*."""
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {row[0] for row in rows}


def _insert_file(conn: sqlite3.Connection, path: str = "src/example.py") -> int:
    """Insert a row into ``files`` and return its rowid."""
    cursor = conn.execute(
        "INSERT INTO files (path, language) VALUES (?, ?)",
        (path, "python"),
    )
    row_id = cursor.lastrowid
    assert row_id is not None
    return row_id


def _insert_symbol(
    conn: sqlite3.Connection,
    file_id: int,
    *,
    name: str = "greet",
    symbol_type: str = "function",
) -> int:
    """Insert a row into ``symbols`` and return its rowid."""
    cursor = conn.execute(
        "INSERT INTO symbols (file_id, name, symbol_type) VALUES (?, ?, ?)",
        (file_id, name, symbol_type),
    )
    row_id = cursor.lastrowid
    assert row_id is not None
    return row_id


# ---------------------------------------------------------------------------
# 1. Schema creation
# ---------------------------------------------------------------------------


def test_ensure_schema_creates_all_tables() -> None:
    """``ensure_schema`` creates every table declared in the DDL."""
    connection = sqlite3.connect(":memory:")
    ensure_schema(connection)
    assert _EXPECTED_TABLES.issubset(_tables_in(connection))
    connection.close()


def test_symbols_has_parent_class_column(conn: sqlite3.Connection) -> None:
    """Sub-phase 2.0: ``symbols.parent_class`` is a nullable TEXT column."""
    rows = conn.execute("PRAGMA table_info(symbols)").fetchall()
    # PRAGMA table_info columns: cid, name, type, notnull, dflt_value, pk
    by_name = {row[1]: row for row in rows}
    assert "parent_class" in by_name, "parent_class column missing from symbols"
    parent_class_row = by_name["parent_class"]
    assert parent_class_row[2] == "TEXT"
    assert parent_class_row[3] == 0  # notnull == 0 => nullable


def test_symbols_unique_composite_allows_same_method_on_different_classes(
    conn: sqlite3.Connection,
) -> None:
    """Sub-phase 2.0: UNIQUE(file_id, name, symbol_type, parent_class).

    Two methods named ``foo`` on different classes in the same file must both
    be insertable — the Phase 1 UNIQUE constraint wrongly collided them.
    """
    file_id = _insert_file(conn, "src/dual_class.py")
    conn.execute(
        "INSERT INTO symbols (file_id, name, symbol_type, parent_class) VALUES (?, ?, ?, ?)",
        (file_id, "foo", "method", "ClassA"),
    )
    conn.execute(
        "INSERT INTO symbols (file_id, name, symbol_type, parent_class) VALUES (?, ?, ?, ?)",
        (file_id, "foo", "method", "ClassB"),
    )
    conn.commit()

    count = conn.execute("SELECT COUNT(*) FROM symbols WHERE name = 'foo'").fetchone()[0]
    assert count == 2


# ---------------------------------------------------------------------------
# 2. Idempotency
# ---------------------------------------------------------------------------


def test_ensure_schema_idempotent(conn: sqlite3.Connection) -> None:
    """Calling ``ensure_schema`` a second time returns ``False`` (no rebuild)."""
    assert ensure_schema(conn) is False


# ---------------------------------------------------------------------------
# 3. Forced rebuild
# ---------------------------------------------------------------------------


def test_ensure_schema_force_rebuild(conn: sqlite3.Connection) -> None:
    """``force=True`` wipes existing data even at the current schema version."""
    _insert_file(conn, "src/keepme.py")
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 1

    rebuilt = ensure_schema(conn, force=True)
    assert rebuilt is True
    assert conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 0


# ---------------------------------------------------------------------------
# 4. Version mismatch triggers rebuild
# ---------------------------------------------------------------------------


def test_schema_version_mismatch_triggers_rebuild(conn: sqlite3.Connection) -> None:
    """An older stored version in ``meta`` causes the next open to rebuild."""
    _insert_file(conn, "src/stale.py")
    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
        ("schema_version", "0"),
    )
    conn.commit()

    # Sanity: ``check_schema_version`` sees the older value.
    assert check_schema_version(conn) == 0

    rebuilt = ensure_schema(conn)
    assert rebuilt is True
    # Row was wiped because mismatch forced a rebuild.
    assert conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 0
    assert check_schema_version(conn) == SCHEMA_VERSION


# ---------------------------------------------------------------------------
# 5. Pragmas
# ---------------------------------------------------------------------------


def test_pragmas_set_on_connection() -> None:
    """``set_pragmas`` enables WAL, foreign keys, and NORMAL synchronous."""
    connection = sqlite3.connect(":memory:")
    set_pragmas(connection)

    # ``journal_mode`` on an in-memory DB falls back to "memory" — but every
    # non-memory use will honour WAL, so we assert the pragma was accepted and
    # the foreign-keys/synchronous values stuck.
    journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0].lower()
    assert journal_mode in {"wal", "memory"}

    foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
    assert foreign_keys == 1

    # ``synchronous`` values: 0=OFF, 1=NORMAL, 2=FULL, 3=EXTRA.
    synchronous = connection.execute("PRAGMA synchronous").fetchone()[0]
    assert synchronous == 1

    connection.close()


# ---------------------------------------------------------------------------
# 6. CHECK constraints reject invalid values
# ---------------------------------------------------------------------------


def test_check_constraints_reject_bad_values(conn: sqlite3.Connection) -> None:
    """Invalid ``symbol_type`` and ``edge_type`` values raise ``IntegrityError``."""
    file_id = _insert_file(conn)
    conn.commit()

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO symbols (file_id, name, symbol_type) VALUES (?, ?, ?)",
            (file_id, "weird", "banana"),
        )
    conn.rollback()

    source_id = _insert_symbol(conn, file_id, name="Source", symbol_type="class")
    target_id = _insert_symbol(conn, file_id, name="Target", symbol_type="class")
    conn.commit()

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO class_edges (source_id, target_id, edge_type, line) VALUES (?, ?, ?, ?)",
            (source_id, target_id, "uses", 10),
        )
    conn.rollback()


# ---------------------------------------------------------------------------
# 7. Cascade deletes from ``files``
# ---------------------------------------------------------------------------


def test_cascade_delete_from_files(conn: sqlite3.Connection) -> None:
    """Deleting a file removes its symbols, symbol_members, and call rows."""
    file_id = _insert_file(conn, "src/cascade.py")
    caller_id = _insert_symbol(conn, file_id, name="caller", symbol_type="function")
    callee_id = _insert_symbol(conn, file_id, name="callee", symbol_type="function")
    conn.execute(
        "INSERT INTO calls (caller_id, callee_id, line) VALUES (?, ?, ?)",
        (caller_id, callee_id, 42),
    )
    conn.execute(
        "INSERT INTO symbol_members (symbol_id, name, value, ordinal) VALUES (?, ?, ?, ?)",
        (caller_id, "MEMBER_A", "1", 0),
    )
    conn.commit()

    assert conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM calls").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM symbol_members").fetchone()[0] == 1

    conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
    conn.commit()

    assert conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM calls").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM symbol_members").fetchone()[0] == 0


# ---------------------------------------------------------------------------
# 8. ``meta`` round trip
# ---------------------------------------------------------------------------


def test_meta_round_trip(conn: sqlite3.Connection) -> None:
    """``meta`` is seeded with schema_version, built_at (ISO), and builder."""
    rows = dict(conn.execute("SELECT key, value FROM meta").fetchall())
    assert rows["schema_version"] == str(SCHEMA_VERSION)
    assert rows["builder"] == "lexibrary-symbolgraph-v1"
    # ``built_at`` must parse as an ISO-8601 datetime.
    datetime.fromisoformat(rows["built_at"])


# ---------------------------------------------------------------------------
# Sanity: module exposes the names required by later groups
# ---------------------------------------------------------------------------


def test_module_exposes_required_names() -> None:
    """Later task groups import these names — guard against rename drift."""
    for name in (
        "SCHEMA_VERSION",
        "set_pragmas",
        "check_schema_version",
        "ensure_schema",
    ):
        assert hasattr(symbol_schema, name)


# ---------------------------------------------------------------------------
# 9. ``build_symbol_graph`` — default config creates an empty DB
# ---------------------------------------------------------------------------


def test_build_symbol_graph_creates_empty_db(tmp_path: Path) -> None:
    """A default-config build creates ``symbols.db`` with all tables empty."""
    config = LexibraryConfig()

    result = build_symbol_graph(tmp_path, config)

    db_path = symbols_db_path(tmp_path)
    assert db_path.exists()

    # All per-table counts are zero in Phase 1.
    assert isinstance(result, SymbolBuildResult)
    assert result.file_count == 0
    assert result.symbol_count == 0
    assert result.call_count == 0
    assert result.unresolved_call_count == 0
    assert result.class_edge_count == 0
    assert result.member_count == 0
    assert result.errors == []
    assert result.build_type == "full"

    # The DB is actually initialised with the v1 schema.
    connection = sqlite3.connect(db_path)
    try:
        assert check_schema_version(connection) == SCHEMA_VERSION
        tables = _tables_in(connection)
        assert _EXPECTED_TABLES.issubset(tables)
        for table in ("files", "symbols", "calls", "class_edges", "symbol_members"):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# 10. ``build_symbol_graph`` — disabled config is a no-op
# ---------------------------------------------------------------------------


def test_build_symbol_graph_disabled(tmp_path: Path) -> None:
    """When ``symbols.enabled`` is False the builder must not touch the FS."""
    config = LexibraryConfig()
    config.symbols.enabled = False

    result = build_symbol_graph(tmp_path, config)

    # Neither the ``.lexibrary/`` directory nor the DB should exist.
    assert (tmp_path / ".lexibrary").exists() is False
    assert symbols_db_path(tmp_path).exists() is False

    # Result is still a well-formed, zeroed ``SymbolBuildResult``.
    assert isinstance(result, SymbolBuildResult)
    assert result.file_count == 0
    assert result.symbol_count == 0
    assert result.call_count == 0
    assert result.unresolved_call_count == 0
    assert result.class_edge_count == 0
    assert result.member_count == 0
    assert result.errors == []
    assert result.build_type == "full"


# ---------------------------------------------------------------------------
# 11. ``build_symbol_graph`` — incremental flag reports ``build_type``
# ---------------------------------------------------------------------------


def test_build_symbol_graph_incremental_flag_reports_correct_build_type(
    tmp_path: Path,
) -> None:
    """Passing ``changed_paths=[]`` marks the run as incremental.

    Phase 1 still performs a full schema ensure on the incremental path —
    this test only pins the result's ``build_type`` contract so Phase 6 can
    rely on it without breaking the default call shape.
    """
    config = LexibraryConfig()

    result = build_symbol_graph(tmp_path, config, changed_paths=[])

    assert result.build_type == "incremental"
    # The DB is still created — Phase 1 does not differentiate the branches
    # beyond the reported build_type.
    assert symbols_db_path(tmp_path).exists()
