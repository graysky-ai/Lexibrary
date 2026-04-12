"""Tests for Phase 7 branch parameter persistence in the symbol graph builder.

Covers task 2.3 of the ``symbol-graph-7`` change and the scenarios in
``openspec/changes/symbol-graph-7/specs/symbol-graph-builder/spec.md``:

1. ``test_builder_inserts_branch_parameter_rows`` — a function with
   ``branch_parameters=["changed_paths"]`` produces a matching row in
   ``symbol_branch_parameters``.
2. ``test_builder_skips_functions_with_no_branches`` — a function with
   ``branch_parameters=[]`` produces no rows.
3. ``test_incremental_cascade_removes_branch_parameters`` — deleting
   a file row cascades to remove branch parameter rows.
4. ``test_builder_handles_method_branch_parameters`` — a class method
   with ``branch_parameters=["threshold"]`` produces a matching row.
5. ``test_schema_version_bumped`` — ``SCHEMA_VERSION`` is 3 (one higher
   than Phase 2's value of 2).

The fixtures are built inline in ``tmp_path`` so each test sees a
fresh project root.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from lexibrary.config.schema import LexibraryConfig
from lexibrary.symbolgraph.builder import build_symbol_graph
from lexibrary.symbolgraph.schema import SCHEMA_VERSION
from lexibrary.utils.paths import symbols_db_path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_project(tmp_path: Path, files: dict[str, str]) -> Path:
    """Create a tmp project root with the given ``{rel_path: content}`` map.

    Writes a ``.lexibrary/`` marker directory and an empty
    ``src/pkg/__init__.py`` when missing so the Python import resolver
    can walk into the package.
    """
    root = tmp_path.resolve()
    (root / ".lexibrary").mkdir(exist_ok=True)
    pkg = root / "src" / "pkg"
    pkg.mkdir(parents=True, exist_ok=True)
    if "src/pkg/__init__.py" not in files:
        (pkg / "__init__.py").write_text("", encoding="utf-8")
    for rel, content in files.items():
        file_path = root / rel
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
    return root


def _open_db(project_root: Path) -> sqlite3.Connection:
    """Open the symbols.db for reading."""
    return sqlite3.connect(symbols_db_path(project_root))


# ---------------------------------------------------------------------------
# Source fixtures
# ---------------------------------------------------------------------------

_FUNCTION_WITH_BRANCH = """\
from __future__ import annotations


def build_index(changed_paths, config):
    if changed_paths is None:
        return full_build()
    return incremental_build(changed_paths)
"""

_FUNCTION_WITHOUT_BRANCH = """\
from __future__ import annotations


def simple_add(a, b):
    return a + b
"""

_METHOD_WITH_BRANCH = """\
from __future__ import annotations


class Processor:
    def process(self, threshold, data):
        if threshold > 10:
            return self._high(data)
        return self._low(data)
"""

# ---------------------------------------------------------------------------
# Scenario 1 — function with branch parameters
# ---------------------------------------------------------------------------


def test_builder_inserts_branch_parameter_rows(tmp_path: Path) -> None:
    """A function with ``branch_parameters=["changed_paths"]`` produces
    a matching row in ``symbol_branch_parameters``."""
    project_root = _make_project(
        tmp_path,
        {"src/pkg/indexer.py": _FUNCTION_WITH_BRANCH},
    )
    result = build_symbol_graph(project_root, LexibraryConfig())

    conn = _open_db(project_root)
    try:
        # Find the symbol row for build_index
        sym_row = conn.execute(
            "SELECT id FROM symbols WHERE name = 'build_index'",
        ).fetchone()
        assert sym_row is not None, "build_index symbol not found"
        symbol_id = sym_row[0]

        # Check branch parameter rows
        params = conn.execute(
            "SELECT parameter_name FROM symbol_branch_parameters "
            "WHERE symbol_id = ? ORDER BY parameter_name",
            (symbol_id,),
        ).fetchall()
        param_names = [row[0] for row in params]
        assert "changed_paths" in param_names
    finally:
        conn.close()

    assert result.branch_parameter_count > 0


# ---------------------------------------------------------------------------
# Scenario 2 — function without branches
# ---------------------------------------------------------------------------


def test_builder_skips_functions_with_no_branches(tmp_path: Path) -> None:
    """A function with ``branch_parameters=[]`` produces no rows
    in ``symbol_branch_parameters``."""
    project_root = _make_project(
        tmp_path,
        {"src/pkg/math.py": _FUNCTION_WITHOUT_BRANCH},
    )
    result = build_symbol_graph(project_root, LexibraryConfig())

    conn = _open_db(project_root)
    try:
        sym_row = conn.execute(
            "SELECT id FROM symbols WHERE name = 'simple_add'",
        ).fetchone()
        assert sym_row is not None, "simple_add symbol not found"
        symbol_id = sym_row[0]

        params = conn.execute(
            "SELECT parameter_name FROM symbol_branch_parameters WHERE symbol_id = ?",
            (symbol_id,),
        ).fetchall()
        assert params == []
    finally:
        conn.close()

    assert result.branch_parameter_count == 0


# ---------------------------------------------------------------------------
# Scenario 3 — cascade delete removes branch parameters
# ---------------------------------------------------------------------------


def test_incremental_cascade_removes_branch_parameters(tmp_path: Path) -> None:
    """Deleting a file row cascades to remove its branch parameter rows."""
    project_root = _make_project(
        tmp_path,
        {"src/pkg/indexer.py": _FUNCTION_WITH_BRANCH},
    )
    build_symbol_graph(project_root, LexibraryConfig())

    conn = _open_db(project_root)
    try:
        # Verify rows exist first
        count_before = conn.execute(
            "SELECT COUNT(*) FROM symbol_branch_parameters",
        ).fetchone()[0]
        assert count_before > 0

        # Delete the file row — CASCADE should remove symbols and
        # branch parameters
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("DELETE FROM files")
        conn.commit()

        count_after = conn.execute(
            "SELECT COUNT(*) FROM symbol_branch_parameters",
        ).fetchone()[0]
        assert count_after == 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Scenario 4 — method branch parameters
# ---------------------------------------------------------------------------


def test_builder_handles_method_branch_parameters(tmp_path: Path) -> None:
    """A class method with ``branch_parameters=["threshold"]`` produces
    a matching row in ``symbol_branch_parameters``."""
    project_root = _make_project(
        tmp_path,
        {"src/pkg/processor.py": _METHOD_WITH_BRANCH},
    )
    result = build_symbol_graph(project_root, LexibraryConfig())

    conn = _open_db(project_root)
    try:
        sym_row = conn.execute(
            "SELECT id FROM symbols WHERE name = 'process' AND symbol_type = 'method'",
        ).fetchone()
        assert sym_row is not None, "process method symbol not found"
        symbol_id = sym_row[0]

        params = conn.execute(
            "SELECT parameter_name FROM symbol_branch_parameters "
            "WHERE symbol_id = ? ORDER BY parameter_name",
            (symbol_id,),
        ).fetchall()
        param_names = [row[0] for row in params]
        assert "threshold" in param_names
    finally:
        conn.close()

    assert result.branch_parameter_count > 0


# ---------------------------------------------------------------------------
# Scenario 5 — schema version bumped
# ---------------------------------------------------------------------------


def test_schema_version_bumped() -> None:
    """``SCHEMA_VERSION`` is 3 — one higher than Phase 2's value of 2."""
    assert SCHEMA_VERSION == 3
