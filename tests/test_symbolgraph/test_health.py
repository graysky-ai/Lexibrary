"""Tests for ``lexibrary.symbolgraph.health`` — read-only health reporter.

Covers four scenarios per task group 5:

1. ``test_health_missing_db`` — no ``.lexibrary/symbols.db`` on disk, expect
   ``exists=False`` with every count zero.
2. ``test_health_empty_db`` — freshly-initialised DB, expect ``exists=True``,
   counts zero, ``schema_version=2``, and ``built_at`` populated.
3. ``test_health_with_rows`` — one row per table via raw SQL, expect each
   count to read as ``1``.
4. ``test_health_corrupt_db_returns_safe_default`` — bogus bytes at the DB
   path, expect ``exists=True`` with safe-default zero counts and no raise.

The DB is created via the schema module directly (same effect as
``open_symbol_graph`` from the sibling ``query.py`` module) to keep this
file self-contained while ``query.py`` is implemented in a concurrent bead.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from lexibrary.symbolgraph.health import SymbolGraphHealth, read_symbol_graph_health
from lexibrary.symbolgraph.schema import SCHEMA_VERSION, ensure_schema, set_pragmas
from lexibrary.utils.paths import LEXIBRARY_DIR, symbols_db_path

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def project_root(tmp_path: Path) -> Path:
    """A project root with a ``.lexibrary/`` directory but no DB."""
    (tmp_path / LEXIBRARY_DIR).mkdir()
    return tmp_path


def _init_empty_db(project_root: Path) -> Path:
    """Create ``.lexibrary/symbols.db`` with a fresh schema."""
    db_path = symbols_db_path(project_root)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        set_pragmas(conn)
        ensure_schema(conn)
    finally:
        conn.close()
    return db_path


# ---------------------------------------------------------------------------
# 1. Missing DB
# ---------------------------------------------------------------------------


def test_health_missing_db(tmp_path: Path) -> None:
    """No DB on disk → ``exists=False`` and every numeric field zero/None."""
    health = read_symbol_graph_health(tmp_path)

    assert isinstance(health, SymbolGraphHealth)
    assert health.exists is False
    assert health.schema_version is None
    assert health.built_at is None
    assert health.file_count == 0
    assert health.symbol_count == 0
    assert health.call_count == 0
    assert health.unresolved_call_count == 0
    assert health.class_edge_count == 0
    assert health.member_count == 0


def test_health_missing_db_does_not_create_file(tmp_path: Path) -> None:
    """Health check must never create the DB or its parent directory."""
    expected = symbols_db_path(tmp_path)
    assert not expected.exists()

    read_symbol_graph_health(tmp_path)

    assert not expected.exists()
    assert not (tmp_path / LEXIBRARY_DIR).exists()


# ---------------------------------------------------------------------------
# 2. Empty DB
# ---------------------------------------------------------------------------


def test_health_empty_db(project_root: Path) -> None:
    """Freshly-initialised DB → schema v2, built_at set, counts all zero."""
    _init_empty_db(project_root)

    health = read_symbol_graph_health(project_root)

    assert health.exists is True
    assert health.schema_version == SCHEMA_VERSION
    assert health.schema_version == 2
    assert health.built_at is not None
    assert health.file_count == 0
    assert health.symbol_count == 0
    assert health.call_count == 0
    assert health.unresolved_call_count == 0
    assert health.class_edge_count == 0
    assert health.member_count == 0


# ---------------------------------------------------------------------------
# 3. DB with one row per table
# ---------------------------------------------------------------------------


def test_health_with_rows(project_root: Path) -> None:
    """One row per table via raw SQL → every count reads as 1."""
    db_path = _init_empty_db(project_root)

    conn = sqlite3.connect(str(db_path))
    try:
        set_pragmas(conn)

        # files → symbol → symbol_members (enum member) needs valid FK order.
        file_id = conn.execute(
            "INSERT INTO files (path, language) VALUES (?, ?)",
            ("src/app/main.py", "python"),
        ).lastrowid
        assert file_id is not None

        # Two symbols: a callable caller and an enum that also owns a member.
        caller_id = conn.execute(
            "INSERT INTO symbols (file_id, name, symbol_type) VALUES (?, ?, ?)",
            (file_id, "run", "function"),
        ).lastrowid
        callee_id = conn.execute(
            "INSERT INTO symbols (file_id, name, symbol_type) VALUES (?, ?, ?)",
            (file_id, "Color", "enum"),
        ).lastrowid
        assert caller_id is not None
        assert callee_id is not None

        # symbol_members — one enum member attached to ``Color``.
        conn.execute(
            "INSERT INTO symbol_members (symbol_id, name, value, ordinal) VALUES (?, ?, ?, ?)",
            (callee_id, "RED", "1", 0),
        )

        # calls — one resolved call from ``run`` to ``Color``.
        conn.execute(
            "INSERT INTO calls (caller_id, callee_id, line) VALUES (?, ?, ?)",
            (caller_id, callee_id, 10),
        )

        # unresolved_calls — one stub reference from ``run``.
        conn.execute(
            "INSERT INTO unresolved_calls (caller_id, callee_name, line) VALUES (?, ?, ?)",
            (caller_id, "unknown_external_fn", 11),
        )

        # class_edges — one inherits edge between two class symbols.
        base_id = conn.execute(
            "INSERT INTO symbols (file_id, name, symbol_type) VALUES (?, ?, ?)",
            (file_id, "Base", "class"),
        ).lastrowid
        child_id = conn.execute(
            "INSERT INTO symbols (file_id, name, symbol_type) VALUES (?, ?, ?)",
            (file_id, "Child", "class"),
        ).lastrowid
        assert base_id is not None
        assert child_id is not None

        conn.execute(
            "INSERT INTO class_edges (source_id, target_id, edge_type, line) VALUES (?, ?, ?, ?)",
            (child_id, base_id, "inherits", 20),
        )
        conn.commit()
    finally:
        conn.close()

    health = read_symbol_graph_health(project_root)

    assert health.exists is True
    assert health.schema_version == 2
    assert health.built_at is not None
    assert health.file_count == 1
    # Four symbols inserted above; the count reflects the full DDL table,
    # not "one row per table" literally — per-table row counts are what
    # ``SymbolGraphHealth`` exposes. Assert the exact total.
    assert health.symbol_count == 4
    assert health.call_count == 1
    assert health.unresolved_call_count == 1
    assert health.class_edge_count == 1
    assert health.member_count == 1


# ---------------------------------------------------------------------------
# 4. Corrupt DB returns safe default
# ---------------------------------------------------------------------------


def test_health_corrupt_db_returns_safe_default(project_root: Path) -> None:
    """Non-sqlite bytes at the DB path → ``exists=True`` with zeroed counts."""
    db_path = symbols_db_path(project_root)
    db_path.write_bytes(b"not a sqlite file")

    health = read_symbol_graph_health(project_root)

    assert health.exists is True
    assert health.schema_version is None
    assert health.built_at is None
    assert health.file_count == 0
    assert health.symbol_count == 0
    assert health.call_count == 0
    assert health.unresolved_call_count == 0
    assert health.class_edge_count == 0
    assert health.member_count == 0


def test_health_missing_meta_row_returns_safe_default(project_root: Path) -> None:
    """Empty DB without a ``meta`` table → safe default with ``exists=True``.

    Simulates the case where the DB file was created via bare ``sqlite3.connect``
    without any schema initialisation. The ``meta`` query raises
    ``sqlite3.OperationalError`` which must be caught and return the safe
    default.
    """
    db_path = symbols_db_path(project_root)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # Create a valid but empty SQLite file (no schema).
    conn = sqlite3.connect(str(db_path))
    conn.close()

    health = read_symbol_graph_health(project_root)

    assert health.exists is True
    assert health.schema_version is None
    assert health.built_at is None
    assert health.file_count == 0
    assert health.symbol_count == 0
    assert health.call_count == 0
    assert health.unresolved_call_count == 0
    assert health.class_edge_count == 0
    assert health.member_count == 0
