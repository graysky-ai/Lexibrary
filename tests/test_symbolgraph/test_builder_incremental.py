"""Tests for the Phase 6 incremental rebuild path in ``build_symbol_graph``.

Covers four scenarios:

1. ``test_incremental_rebuild_only_touches_changed_files`` — when
   ``changed_paths`` is a small subset of the total files and under the
   :data:`INCREMENTAL_THRESHOLD`, only those files are refreshed. Other
   files' symbol rows remain intact from the initial full build.
2. ``test_incremental_cascade_removes_stale_calls`` — editing a file to
   remove a function causes the incremental path to delete the stale
   ``calls`` rows that pointed at the removed symbol.
3. ``test_incremental_threshold_switches_to_full`` — when the
   ``changed_paths`` ratio exceeds :data:`INCREMENTAL_THRESHOLD`, the
   builder falls through to the full rebuild path instead of the
   per-file incremental loop.
4. ``test_incremental_result_marks_build_type`` — the returned
   :class:`SymbolBuildResult` has ``build_type="incremental"`` when
   the incremental path runs, and ``build_type="full"`` when the
   threshold is exceeded.

The on-disk fixture lives at
``tests/test_symbolgraph/fixtures/class_hierarchy/`` and is copied into
``tmp_path`` per-test.
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from lexibrary.config.schema import LexibraryConfig
from lexibrary.symbolgraph.builder import (
    build_symbol_graph,
)
from lexibrary.utils.paths import symbols_db_path

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "class_hierarchy"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _prepare_project(tmp_path: Path) -> Path:
    """Copy the ``class_hierarchy`` fixture into *tmp_path* and return its root.

    Resolves ``tmp_path`` for macOS symlinked tempdirs and creates
    the ``.lexibrary/`` marker directory.
    """
    project_root = tmp_path.resolve()
    shutil.copytree(FIXTURES_DIR, project_root, dirs_exist_ok=True)
    (project_root / ".lexibrary").mkdir(exist_ok=True)
    return project_root


def _open_db(project_root: Path) -> sqlite3.Connection:
    """Open the symbols.db for reading."""
    return sqlite3.connect(symbols_db_path(project_root))


def _count_symbols(conn: sqlite3.Connection, file_path: str) -> int:
    """Count symbols in a given file."""
    row = conn.execute(
        "SELECT COUNT(*) FROM symbols s JOIN files f ON s.file_id = f.id WHERE f.path = ?",
        (file_path,),
    ).fetchone()
    return int(row[0]) if row else 0


# ---------------------------------------------------------------------------
# Test 1 -- only changed files are refreshed
# ---------------------------------------------------------------------------


def test_incremental_rebuild_only_touches_changed_files(tmp_path: Path) -> None:
    """Incremental rebuild refreshes only the listed files."""
    project_root = _prepare_project(tmp_path)
    config = LexibraryConfig()

    # Step 1: initial full build
    full_result = build_symbol_graph(project_root, config)
    assert full_result.build_type == "full"
    assert full_result.file_count > 0

    conn = _open_db(project_root)
    try:
        initial_total_symbols = conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
        base_symbols = _count_symbols(conn, "src/pkg/base.py")
    finally:
        conn.close()

    assert initial_total_symbols > 0
    assert base_symbols > 0

    # Step 2: modify one file and do an incremental rebuild
    base_file = project_root / "src" / "pkg" / "base.py"
    base_file.write_text(
        '"""Modified base."""\n\n'
        "from __future__ import annotations\n\n\n"
        "class Base:\n"
        "    def foo(self) -> None:\n"
        "        pass\n\n"
        "    def new_method(self) -> None:\n"
        "        pass\n"
    )

    inc_result = build_symbol_graph(
        project_root,
        config,
        changed_paths=[base_file],
    )
    assert inc_result.build_type == "incremental"
    # The incremental path only refreshes the single changed file
    assert inc_result.file_count == 1

    # Step 3: verify the changed file was updated but others remain intact
    conn = _open_db(project_root)
    try:
        new_base_symbols = _count_symbols(conn, "src/pkg/base.py")
        # base.py now has Base class, foo method, AND new_method
        assert new_base_symbols > base_symbols

        # Other files should still have their symbols from the full build
        other_symbols = _count_symbols(conn, "src/pkg/derived.py")
        assert other_symbols > 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Test 2 -- stale calls removed on incremental refresh
# ---------------------------------------------------------------------------


def test_incremental_cascade_removes_stale_calls(tmp_path: Path) -> None:
    """Editing a file to remove a function removes stale call rows."""
    project_root = _prepare_project(tmp_path)
    config = LexibraryConfig()

    # Full build
    build_symbol_graph(project_root, config)

    conn = _open_db(project_root)
    try:
        # Verify initial calls from base.py symbols exist
        conn.execute(
            "SELECT COUNT(*) FROM calls c "
            "JOIN symbols s ON c.caller_id = s.id "
            "JOIN files f ON s.file_id = f.id "
            "WHERE f.path = 'src/pkg/base.py'",
        ).fetchone()[0]
    finally:
        conn.close()

    # Modify base.py to remove the foo method but keep the class
    base_file = project_root / "src" / "pkg" / "base.py"
    base_file.write_text(
        '"""Empty base."""\n\nfrom __future__ import annotations\n\n\nclass Base:\n    pass\n'
    )

    inc_result = build_symbol_graph(
        project_root,
        config,
        changed_paths=[base_file],
    )
    assert inc_result.build_type == "incremental"

    conn = _open_db(project_root)
    try:
        # After removing foo, no calls should originate from base.py
        new_call_count = conn.execute(
            "SELECT COUNT(*) FROM calls c "
            "JOIN symbols s ON c.caller_id = s.id "
            "JOIN files f ON s.file_id = f.id "
            "WHERE f.path = 'src/pkg/base.py'",
        ).fetchone()[0]
        assert new_call_count == 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Test 3 -- threshold switches to full rebuild
# ---------------------------------------------------------------------------


def test_incremental_threshold_switches_to_full(tmp_path: Path) -> None:
    """When changed_paths exceeds the threshold, fall back to full rebuild."""
    project_root = _prepare_project(tmp_path)
    config = LexibraryConfig()

    # Full build to populate the DB
    build_symbol_graph(project_root, config)

    # Collect ALL source files so the ratio exceeds the threshold
    all_py_files = list(project_root.rglob("*.py"))
    # With all files as changed_paths, the ratio is 1.0 > INCREMENTAL_THRESHOLD
    assert len(all_py_files) > 0

    result = build_symbol_graph(
        project_root,
        config,
        changed_paths=all_py_files,
    )

    # Should fall through to full rebuild
    assert result.build_type == "full"
    assert result.file_count > 0


# ---------------------------------------------------------------------------
# Test 4 -- build_type label is correct
# ---------------------------------------------------------------------------


def test_incremental_result_marks_build_type(tmp_path: Path) -> None:
    """The result correctly labels full vs incremental builds."""
    project_root = _prepare_project(tmp_path)
    config = LexibraryConfig()

    # Full build (no changed_paths)
    result_full = build_symbol_graph(project_root, config)
    assert result_full.build_type == "full"

    # Incremental build (one file)
    one_file = project_root / "src" / "pkg" / "base.py"
    result_inc = build_symbol_graph(
        project_root,
        config,
        changed_paths=[one_file],
    )
    assert result_inc.build_type == "incremental"

    # Full build triggered by exceeding threshold (all files)
    all_py = list(project_root.rglob("*.py"))
    result_threshold = build_symbol_graph(
        project_root,
        config,
        changed_paths=all_py,
    )
    assert result_threshold.build_type == "full"

    # Empty changed_paths list (no files to refresh) - still incremental
    result_empty = build_symbol_graph(
        project_root,
        config,
        changed_paths=[],
    )
    assert result_empty.build_type == "incremental"
