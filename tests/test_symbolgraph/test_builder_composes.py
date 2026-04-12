"""Tests for the Phase 6 composition edge builder pass.

Covers four scenarios:

1. ``test_build_populates_composes_edge`` — a class-body annotation
   ``db: Database`` produces a ``composes`` row in ``class_edges``
   linking ``Service`` to ``Database``.
2. ``test_build_records_unresolved_composes_for_external_type`` — an
   annotation referencing an external type (``ExternalClient``) that
   is not resolvable within the project lands in
   ``class_edges_unresolved`` with ``edge_type='composes'``.
3. ``test_compose_edge_visible_in_trace`` — the ``composes`` edge
   appears when querying the trace-style parent/child results from
   the ``class_edges`` table.
4. ``test_compose_edge_respects_disabled_config`` — when
   ``config.symbols.enabled=False`` the builder short-circuits before
   any DB mutation, so no composition edges are created.

The on-disk fixture lives at
``tests/test_symbolgraph/fixtures/composition/`` and is copied into
``tmp_path`` per-test so each run builds against a clean project root.
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from lexibrary.config.schema import LexibraryConfig, SymbolGraphConfig
from lexibrary.symbolgraph.builder import build_symbol_graph
from lexibrary.utils.paths import symbols_db_path

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "composition"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _prepare_project(tmp_path: Path) -> Path:
    """Copy the ``composition`` fixture into *tmp_path* and return its root.

    Resolves ``tmp_path`` to cope with macOS symlinked tempdirs
    (``/tmp`` -> ``/private/tmp``) and creates the ``.lexibrary/`` marker
    directory the builder expects.
    """
    project_root = tmp_path.resolve()
    shutil.copytree(FIXTURES_DIR, project_root, dirs_exist_ok=True)
    (project_root / ".lexibrary").mkdir(exist_ok=True)
    return project_root


def _open_db(project_root: Path) -> sqlite3.Connection:
    """Open the symbols.db for reading."""
    return sqlite3.connect(symbols_db_path(project_root))


# ---------------------------------------------------------------------------
# Test 1 -- resolved composes edge
# ---------------------------------------------------------------------------


def test_build_populates_composes_edge(tmp_path: Path) -> None:
    """``db: Database`` annotation produces a ``composes`` row in ``class_edges``."""
    project_root = _prepare_project(tmp_path)
    build_symbol_graph(project_root, LexibraryConfig())

    conn = _open_db(project_root)
    try:
        rows = conn.execute(
            "SELECT source.name, target.name, ce.edge_type "
            "FROM class_edges ce "
            "JOIN symbols source ON source.id = ce.source_id "
            "JOIN symbols target ON target.id = ce.target_id "
            "WHERE ce.edge_type = 'composes'",
        ).fetchall()
    finally:
        conn.close()

    # Service composes Database and LRUCache
    source_target_pairs = {(r[0], r[1]) for r in rows}
    assert ("Service", "Database") in source_target_pairs
    assert ("Service", "LRUCache") in source_target_pairs
    assert all(r[2] == "composes" for r in rows)


# ---------------------------------------------------------------------------
# Test 2 -- unresolved composes edge for external type
# ---------------------------------------------------------------------------


def test_build_records_unresolved_composes_for_external_type(tmp_path: Path) -> None:
    """``client: ExternalClient`` lands in ``class_edges_unresolved``."""
    project_root = _prepare_project(tmp_path)
    build_symbol_graph(project_root, LexibraryConfig())

    conn = _open_db(project_root)
    try:
        rows = conn.execute(
            "SELECT source.name, ce.target_name, ce.edge_type "
            "FROM class_edges_unresolved ce "
            "JOIN symbols source ON source.id = ce.source_id "
            "WHERE ce.edge_type = 'composes'",
        ).fetchall()
    finally:
        conn.close()

    # At minimum, ExternalClient should be unresolved
    unresolved_targets = {(r[0], r[1]) for r in rows}
    assert ("Service", "ExternalClient") in unresolved_targets


# ---------------------------------------------------------------------------
# Test 3 -- composes edge visible in trace-style query
# ---------------------------------------------------------------------------


def test_compose_edge_visible_in_trace(tmp_path: Path) -> None:
    """Composes edges appear in trace-style parent/child queries."""
    project_root = _prepare_project(tmp_path)
    build_symbol_graph(project_root, LexibraryConfig())

    conn = _open_db(project_root)
    try:
        # Query all edges for Service as source (children / outgoing)
        rows = conn.execute(
            "SELECT target.name, ce.edge_type "
            "FROM class_edges ce "
            "JOIN symbols source ON source.id = ce.source_id "
            "JOIN symbols target ON target.id = ce.target_id "
            "WHERE source.name = 'Service'",
        ).fetchall()

        # Also query edges where Database is the target (parents / incoming)
        parent_rows = conn.execute(
            "SELECT source.name, ce.edge_type "
            "FROM class_edges ce "
            "JOIN symbols source ON source.id = ce.source_id "
            "JOIN symbols target ON target.id = ce.target_id "
            "WHERE target.name = 'Database' AND ce.edge_type = 'composes'",
        ).fetchall()
    finally:
        conn.close()

    # Service should have outgoing composes edges
    edge_types = {r[1] for r in rows}
    assert "composes" in edge_types

    # Database should have incoming composes edge from Service
    composers = {r[0] for r in parent_rows}
    assert "Service" in composers


# ---------------------------------------------------------------------------
# Test 4 -- disabled config skips composition edges
# ---------------------------------------------------------------------------


def test_compose_edge_respects_disabled_config(tmp_path: Path) -> None:
    """``symbols.enabled=False`` produces no DB at all."""
    project_root = _prepare_project(tmp_path)
    config = LexibraryConfig(
        symbols=SymbolGraphConfig(enabled=False),
    )
    result = build_symbol_graph(project_root, config)

    # The builder should short-circuit; symbols.db should not exist.
    assert not symbols_db_path(project_root).exists()
    assert result.class_edge_count == 0
    assert result.class_edge_unresolved_count == 0
