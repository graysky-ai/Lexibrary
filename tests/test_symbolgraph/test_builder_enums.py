"""Tests for the Phase 4 enum and constant builder pass.

Covers task 5.4 of the ``symbol-graph-4`` change and the scenarios in
``openspec/changes/symbol-graph-4/specs/symbol-graph-builder/spec.md``:

1. ``test_builder_inserts_enum_symbol_with_members`` — a Python
   ``StrEnum`` subclass produces a ``symbol_type='enum'`` row and a
   matching ``symbol_members`` entry per member.
2. ``test_builder_inserts_constants`` — module-level constants emit
   ``symbol_type='constant'`` rows plus one ``symbol_members`` row each;
   private ALL_CAPS names are preserved.
3. ``test_builder_skips_nested_constants`` — an ALL_CAPS assignment
   inside a function body is NOT extracted as a constant.
4. ``test_builder_enum_in_ts_file`` — a TypeScript ``enum`` declaration
   produces the same ``symbol_members`` shape as a Python enum.
5. ``test_member_count_in_result`` —
   :attr:`SymbolBuildResult.member_count` equals the row count in
   ``symbol_members``.
6. ``test_incremental_reindex_drops_removed_members`` — shrinking an
   enum from three members to two via :func:`refresh_file` removes the
   stale rows (CASCADE on ``symbols.id``).
7. ``test_indirect_enum_base_reclassified`` — ``class MyBase(StrEnum)``
   followed by ``class BuildStatus(MyBase)`` ends up with
   ``symbol_type='enum'`` on ``BuildStatus`` and its members recorded,
   exercising the transitive-enum second pass in the builder.

The fixtures are built inline in ``tmp_path`` so each test sees a
fresh project root — there is no shared on-disk fixture directory.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from lexibrary.config.schema import LexibraryConfig
from lexibrary.symbolgraph.builder import build_symbol_graph, refresh_file
from lexibrary.utils.paths import symbols_db_path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_project(tmp_path: Path, files: dict[str, str]) -> Path:
    """Create a tmp project root with the given ``{rel_path: content}`` map.

    Writes a ``.lexibrary/`` marker directory and an empty
    ``src/pkg/__init__.py`` when missing so the Python import resolver
    can walk into the package. ``tmp_path`` is resolved so macOS
    ``/tmp`` symlinks never trip :meth:`Path.relative_to`.
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
# Scenario 1 — StrEnum members land in symbol_members
# ---------------------------------------------------------------------------


_STR_ENUM_SOURCE = """\
from __future__ import annotations

from enum import StrEnum


class BuildStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    FAILED = "failed"
"""


def test_builder_inserts_enum_symbol_with_members(tmp_path: Path) -> None:
    """A ``StrEnum`` subclass produces an ``enum`` row with member rows."""
    project_root = _make_project(
        tmp_path,
        {"src/pkg/status.py": _STR_ENUM_SOURCE},
    )
    build_symbol_graph(project_root, LexibraryConfig())

    conn = _open_db(project_root)
    try:
        enum_row = conn.execute(
            "SELECT id, name, symbol_type FROM symbols WHERE name = 'BuildStatus'",
        ).fetchone()
        assert enum_row is not None
        enum_id, enum_name, symbol_type = enum_row
        assert enum_name == "BuildStatus"
        assert symbol_type == "enum"

        members = conn.execute(
            "SELECT name, value, ordinal FROM symbol_members WHERE symbol_id = ? ORDER BY ordinal",
            (enum_id,),
        ).fetchall()
    finally:
        conn.close()

    assert members == [
        ("PENDING", '"pending"', 0),
        ("RUNNING", '"running"', 1),
        ("FAILED", '"failed"', 2),
    ]


# ---------------------------------------------------------------------------
# Scenario 2 — module-level constants extracted with value rows
# ---------------------------------------------------------------------------


_CONSTANTS_SOURCE = """\
from __future__ import annotations


MAX_RETRIES = 3
_PRIVATE = "secret"
"""


def test_builder_inserts_constants(tmp_path: Path) -> None:
    """Public and private constants produce ``symbol_type='constant'`` rows."""
    project_root = _make_project(
        tmp_path,
        {"src/pkg/config.py": _CONSTANTS_SOURCE},
    )
    build_symbol_graph(project_root, LexibraryConfig())

    conn = _open_db(project_root)
    try:
        rows = conn.execute(
            "SELECT s.name, s.symbol_type, s.visibility, "
            "       sm.name, sm.value, sm.ordinal "
            "FROM symbols s "
            "JOIN symbol_members sm ON sm.symbol_id = s.id "
            "WHERE s.symbol_type = 'constant' "
            "ORDER BY s.name",
        ).fetchall()
    finally:
        conn.close()

    assert rows == [
        ("MAX_RETRIES", "constant", "public", "MAX_RETRIES", "3", 0),
        ("_PRIVATE", "constant", "private", "_PRIVATE", '"secret"', 0),
    ]


# ---------------------------------------------------------------------------
# Scenario 3 — nested constants inside function bodies are not extracted
# ---------------------------------------------------------------------------


_NESTED_CONSTANT_SOURCE = """\
from __future__ import annotations


def compute() -> int:
    INNER = 42  # noqa: N806 — fixture must exercise nested ALL_CAPS
    return INNER


OUTER = 1
"""


def test_builder_skips_nested_constants(tmp_path: Path) -> None:
    """``INNER = 42`` inside a function does not land in ``symbols``."""
    project_root = _make_project(
        tmp_path,
        {"src/pkg/nested.py": _NESTED_CONSTANT_SOURCE},
    )
    build_symbol_graph(project_root, LexibraryConfig())

    conn = _open_db(project_root)
    try:
        inner_row = conn.execute(
            "SELECT 1 FROM symbols WHERE name = 'INNER'",
        ).fetchone()
        outer_row = conn.execute(
            "SELECT name, symbol_type FROM symbols WHERE name = 'OUTER'",
        ).fetchone()
    finally:
        conn.close()

    assert inner_row is None
    assert outer_row == ("OUTER", "constant")


# ---------------------------------------------------------------------------
# Scenario 4 — TypeScript enum declarations produce the same shape
# ---------------------------------------------------------------------------


_TS_ENUM_SOURCE = """\
export enum BuildStatus {
  Pending = "pending",
  Running = "running",
  Failed = "failed",
}
"""


def test_builder_enum_in_ts_file(tmp_path: Path) -> None:
    """A TypeScript ``enum`` lands in ``symbols`` with member rows."""
    root = tmp_path.resolve()
    (root / ".lexibrary").mkdir(exist_ok=True)
    ts_file = root / "src" / "status.ts"
    ts_file.parent.mkdir(parents=True, exist_ok=True)
    ts_file.write_text(_TS_ENUM_SOURCE, encoding="utf-8")

    build_symbol_graph(root, LexibraryConfig())

    conn = _open_db(root)
    try:
        enum_row = conn.execute(
            "SELECT id, symbol_type FROM symbols WHERE name = 'BuildStatus'",
        ).fetchone()
        assert enum_row is not None
        enum_id, symbol_type = enum_row
        assert symbol_type == "enum"
        member_names = conn.execute(
            "SELECT name FROM symbol_members WHERE symbol_id = ? ORDER BY ordinal",
            (enum_id,),
        ).fetchall()
    finally:
        conn.close()

    assert [name for (name,) in member_names] == ["Pending", "Running", "Failed"]


# ---------------------------------------------------------------------------
# Scenario 5 — member_count on SymbolBuildResult matches the DB
# ---------------------------------------------------------------------------


def test_member_count_in_result(tmp_path: Path) -> None:
    """``result.member_count`` equals the number of ``symbol_members`` rows.

    Combines one 3-member enum (3 rows) with two module-level constants
    (2 rows) to exercise both insert paths in a single build.
    """
    project_root = _make_project(
        tmp_path,
        {
            "src/pkg/status.py": _STR_ENUM_SOURCE,
            "src/pkg/config.py": _CONSTANTS_SOURCE,
        },
    )
    result = build_symbol_graph(project_root, LexibraryConfig())

    conn = _open_db(project_root)
    try:
        row = conn.execute("SELECT COUNT(*) FROM symbol_members").fetchone()
    finally:
        conn.close()

    assert row is not None
    total_members = int(row[0])
    assert result.member_count == total_members
    # Sanity floor so a silent zero won't sneak past.
    assert result.member_count == 3 + 2


# ---------------------------------------------------------------------------
# Scenario 6 — incremental refresh drops stale members via CASCADE
# ---------------------------------------------------------------------------


_SHRUNK_ENUM_SOURCE = """\
from __future__ import annotations

from enum import StrEnum


class BuildStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
"""


def test_incremental_reindex_drops_removed_members(tmp_path: Path) -> None:
    """Shrinking an enum from 3 members to 2 via refresh_file removes stale rows."""
    project_root = _make_project(
        tmp_path,
        {"src/pkg/status.py": _STR_ENUM_SOURCE},
    )
    build_symbol_graph(project_root, LexibraryConfig())

    # Rewrite the file with only two members.
    status_file = project_root / "src" / "pkg" / "status.py"
    status_file.write_text(_SHRUNK_ENUM_SOURCE, encoding="utf-8")

    refresh_file(project_root, LexibraryConfig(), status_file)

    conn = _open_db(project_root)
    try:
        members = conn.execute(
            "SELECT sm.name, sm.ordinal "
            "FROM symbol_members sm "
            "JOIN symbols s ON s.id = sm.symbol_id "
            "WHERE s.name = 'BuildStatus' "
            "ORDER BY sm.ordinal",
        ).fetchall()
    finally:
        conn.close()

    assert members == [("PENDING", 0), ("RUNNING", 1)]


# ---------------------------------------------------------------------------
# Scenario 7 — transitive enum base detection
# ---------------------------------------------------------------------------


_INDIRECT_ENUM_BASE_SOURCE = """\
from __future__ import annotations

from enum import StrEnum


class MyBase(StrEnum):
    pass


class BuildStatus(MyBase):
    PENDING = "pending"
    RUNNING = "running"
"""


def test_indirect_enum_base_reclassified(tmp_path: Path) -> None:
    """A class inheriting from a local ``StrEnum`` subclass is promoted.

    The parser only classifies classes whose *direct* base is in
    :data:`_PY_ENUM_BASES`, so ``BuildStatus`` lands as ``symbol_type='class'``
    at parse time. The transitive enum pass in the builder walks the
    resolved inherits graph and promotes ``BuildStatus`` to
    ``symbol_type='enum'``, then re-extracts its members.
    """
    project_root = _make_project(
        tmp_path,
        {"src/pkg/status.py": _INDIRECT_ENUM_BASE_SOURCE},
    )
    build_symbol_graph(project_root, LexibraryConfig())

    conn = _open_db(project_root)
    try:
        status_row = conn.execute(
            "SELECT id, symbol_type FROM symbols WHERE name = 'BuildStatus'",
        ).fetchone()
        assert status_row is not None
        status_id, symbol_type = status_row
        assert symbol_type == "enum"

        members = conn.execute(
            "SELECT name, value, ordinal FROM symbol_members WHERE symbol_id = ? ORDER BY ordinal",
            (status_id,),
        ).fetchall()
    finally:
        conn.close()

    assert members == [
        ("PENDING", '"pending"', 0),
        ("RUNNING", '"running"', 1),
    ]
