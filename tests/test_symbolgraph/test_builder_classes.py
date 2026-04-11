"""Tests for the Phase 3 class-edge builder pass.

Covers the five scenarios in Phase 3 task 4.8:

1. ``test_build_records_inherits_edge`` — ``Derived → Base`` inheritance
   edge lands in ``class_edges`` with ``edge_type='inherits'``.
2. ``test_build_records_instantiates_edge`` — ``main → Derived``
   instantiation edge lands in ``class_edges`` with
   ``edge_type='instantiates'``.
3. ``test_build_records_unresolved_base`` — ``Thing → BaseModel``
   (external, unresolvable) lands in ``class_edges_unresolved``.
4. ``test_build_ignores_non_class_instantiations`` — a call to a
   PascalCase **function** (``Builder()``) does not emit a class edge
   because the pass-3 ``instantiates`` filter verifies the target row's
   ``symbol_type == 'class'``.
5. ``test_build_result_counts`` — :class:`SymbolBuildResult`'s
   ``class_edge_count`` and ``class_edge_unresolved_count`` match the
   number of rows inserted into the two class-edge tables.

The on-disk fixture lives at
``tests/test_symbolgraph/fixtures/class_hierarchy/`` and is copied into
``tmp_path`` per-test so each run builds against a clean project root.
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from lexibrary.config.schema import LexibraryConfig
from lexibrary.symbolgraph.builder import build_symbol_graph
from lexibrary.utils.paths import symbols_db_path

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "class_hierarchy"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _prepare_project(tmp_path: Path) -> Path:
    """Copy the ``class_hierarchy`` fixture into *tmp_path* and return its root.

    Resolves ``tmp_path`` to cope with macOS symlinked tempdirs
    (``/tmp`` → ``/private/tmp``) and creates the ``.lexibrary/`` marker
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
# Test 1 — inherits edge
# ---------------------------------------------------------------------------


def test_build_records_inherits_edge(tmp_path: Path) -> None:
    """``class Derived(Base)`` produces an ``inherits`` row in ``class_edges``."""
    project_root = _prepare_project(tmp_path)
    build_symbol_graph(project_root, LexibraryConfig())

    conn = _open_db(project_root)
    try:
        rows = conn.execute(
            "SELECT source.name, target.name, ce.edge_type "
            "FROM class_edges ce "
            "JOIN symbols source ON source.id = ce.source_id "
            "JOIN symbols target ON target.id = ce.target_id "
            "WHERE ce.edge_type = 'inherits' "
            "  AND source.name = 'Derived' "
            "  AND target.name = 'Base'",
        ).fetchall()
    finally:
        conn.close()

    assert rows == [("Derived", "Base", "inherits")]


# ---------------------------------------------------------------------------
# Test 2 — instantiates edge
# ---------------------------------------------------------------------------


def test_build_records_instantiates_edge(tmp_path: Path) -> None:
    """``Derived()`` inside ``main`` produces an ``instantiates`` row."""
    project_root = _prepare_project(tmp_path)
    build_symbol_graph(project_root, LexibraryConfig())

    conn = _open_db(project_root)
    try:
        rows = conn.execute(
            "SELECT source.qualified_name, target.name, ce.edge_type "
            "FROM class_edges ce "
            "JOIN symbols source ON source.id = ce.source_id "
            "JOIN symbols target ON target.id = ce.target_id "
            "WHERE ce.edge_type = 'instantiates' "
            "  AND target.name = 'Derived'",
        ).fetchall()
    finally:
        conn.close()

    assert rows == [("pkg.users.main", "Derived", "instantiates")]


# ---------------------------------------------------------------------------
# Test 3 — unresolved base
# ---------------------------------------------------------------------------


def test_build_records_unresolved_base(tmp_path: Path) -> None:
    """``class Thing(BaseModel)`` lands in ``class_edges_unresolved``.

    ``pydantic.BaseModel`` is not in the fixture project, so
    :class:`PythonResolver.resolve_class_name` returns ``None`` and the
    builder records the edge as unresolved.
    """
    project_root = _prepare_project(tmp_path)
    build_symbol_graph(project_root, LexibraryConfig())

    conn = _open_db(project_root)
    try:
        rows = conn.execute(
            "SELECT source.name, ce.target_name, ce.edge_type "
            "FROM class_edges_unresolved ce "
            "JOIN symbols source ON source.id = ce.source_id "
            "WHERE source.name = 'Thing'",
        ).fetchall()
    finally:
        conn.close()

    assert rows == [("Thing", "BaseModel", "inherits")]


# ---------------------------------------------------------------------------
# Test 4 — PascalCase function is not a class instantiation
# ---------------------------------------------------------------------------


def test_build_ignores_non_class_instantiations(tmp_path: Path) -> None:
    """``Builder()`` (a PascalCase function) emits no class edge.

    The parser extracts every PascalCase call as a potential
    ``instantiates`` edge, but the pass-3 builder re-queries the
    resolved target row and only inserts the edge when
    ``symbol_type='class'``. A function matches
    :meth:`PythonResolver.resolve_class_name`'s SQL filter too strictly
    (``symbol_type = 'class'``) so the resolver returns ``None``; the
    builder then records the target as unresolved. Either path suffices
    — what must not happen is an edge pointing at a function row.
    """
    project_root = _prepare_project(tmp_path)
    build_symbol_graph(project_root, LexibraryConfig())

    conn = _open_db(project_root)
    try:
        rows = conn.execute(
            "SELECT source.qualified_name, target.name, target.symbol_type, "
            "       ce.edge_type "
            "FROM class_edges ce "
            "JOIN symbols source ON source.id = ce.source_id "
            "JOIN symbols target ON target.id = ce.target_id "
            "WHERE target.name = 'Builder'",
        ).fetchall()
    finally:
        conn.close()

    # No resolved class_edges row should point at the ``Builder`` function.
    assert rows == []


# ---------------------------------------------------------------------------
# Test 5 — result counts
# ---------------------------------------------------------------------------


def test_build_result_counts(tmp_path: Path) -> None:
    """:attr:`SymbolBuildResult.class_edge_count` matches inserted rows."""
    project_root = _prepare_project(tmp_path)
    result = build_symbol_graph(project_root, LexibraryConfig())

    conn = _open_db(project_root)
    try:
        resolved_count = conn.execute(
            "SELECT COUNT(*) FROM class_edges",
        ).fetchone()[0]
        unresolved_count = conn.execute(
            "SELECT COUNT(*) FROM class_edges_unresolved",
        ).fetchone()[0]
    finally:
        conn.close()

    assert result.class_edge_count == resolved_count
    assert result.class_edge_unresolved_count == unresolved_count
    # Sanity floor: the fixture guarantees at least the
    # ``Derived → Base`` inheritance edge, the ``main → Derived``
    # instantiation edge, and the ``Thing → BaseModel`` unresolved row.
    assert result.class_edge_count >= 2
    assert result.class_edge_unresolved_count >= 1
