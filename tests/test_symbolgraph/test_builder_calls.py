"""Tests for the Phase 2 ``build_symbol_graph`` full rebuild.

Covers the nine scenarios in Phase 2 task 8.7:

1. ``test_build_populates_symbols`` — every defined function/class/method
   becomes a ``symbols`` row with a correct ``qualified_name``.
2. ``test_build_populates_intra_file_calls`` — same-file calls resolve via
   the local lookup path.
3. ``test_build_populates_cross_file_calls`` — cross-file ``from pkg.x
   import y`` calls resolve via the Python import-aware resolver.
4. ``test_build_captures_unresolved_external_call`` — calls into third-party
   modules (e.g. ``sqlite3.connect``) land in ``unresolved_calls``.
5. ``test_build_respects_symbols_disabled`` — a disabled config
   short-circuits before any filesystem mutation.
6. ``test_build_full_rebuild_removes_stale_rows`` — deleting a file and
   rebuilding wipes its rows (force-rebuild path).
7. ``test_build_records_files_table`` — each processed file has a row with
   a real ``language`` and ``last_hash``.
8. ``test_build_benchmark_250_files`` — 250-file fixture rebuilds in
   < 5000 ms (regression fence for the transaction wrap).
9. ``test_build_golden_snapshot`` — a canonical fixture under
   ``fixtures/golden_project/`` serialises to a stable JSON snapshot. Set
   the ``LEXIBRARY_UPDATE_GOLDEN=1`` env var on the first implementation
   run to (re)generate the snapshot file.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from lexibrary.config.schema import LexibraryConfig, SymbolGraphConfig
from lexibrary.symbolgraph.builder import build_symbol_graph
from lexibrary.utils.paths import symbols_db_path

FIXTURES_DIR = Path(__file__).parent / "fixtures"
GOLDEN_PROJECT_DIR = FIXTURES_DIR / "golden_project"
GOLDEN_SNAPSHOT_PATH = FIXTURES_DIR / "golden_snapshot.json"


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _make_project(tmp_path: Path, files: dict[str, str]) -> Path:
    """Create a tmp project root with the given ``{rel_path: content}`` map.

    Also writes a ``src/pkg/__init__.py`` marker so the Python import
    resolver can walk into the package. ``tmp_path`` is resolved so macOS
    ``/tmp`` symlinks do not trip :meth:`Path.relative_to`.
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
# Test 1 — definitions populated
# ---------------------------------------------------------------------------


def test_build_populates_symbols(tmp_path: Path) -> None:
    """Every defined function/class/method becomes a ``symbols`` row.

    ``src/pkg/__init__.py`` is written by :func:`_make_project` so the
    Python import resolver has a package to walk into. The empty
    ``__init__`` contributes zero symbols but still produces a ``files``
    row — hence ``file_count == 4`` and ``symbol_count == 4``.
    """
    project_root = _make_project(
        tmp_path,
        {
            "src/pkg/a.py": "def foo():\n    bar()\n\n\ndef bar():\n    pass\n",
            "src/pkg/b.py": "def bar():\n    pass\n",
            "src/pkg/c.py": ("from pkg.b import bar\n\n\ndef baz():\n    bar()\n"),
        },
    )

    result = build_symbol_graph(project_root, LexibraryConfig())

    assert result.file_count == 4  # a.py, b.py, c.py, __init__.py
    assert result.symbol_count == 4  # foo, bar (a.py), bar (b.py), baz

    conn = _open_db(project_root)
    try:
        rows = conn.execute(
            "SELECT name, qualified_name, symbol_type FROM symbols ORDER BY qualified_name",
        ).fetchall()
    finally:
        conn.close()

    names = [row[0] for row in rows]
    qualified = {row[1] for row in rows}
    assert sorted(names) == sorted(["bar", "bar", "baz", "foo"])
    assert "pkg.a.foo" in qualified
    assert "pkg.a.bar" in qualified
    assert "pkg.b.bar" in qualified
    assert "pkg.c.baz" in qualified


# ---------------------------------------------------------------------------
# Test 2 — intra-file calls
# ---------------------------------------------------------------------------


def test_build_populates_intra_file_calls(tmp_path: Path) -> None:
    """``foo() → bar()`` in the same file lands in the ``calls`` table."""
    project_root = _make_project(
        tmp_path,
        {
            "src/pkg/a.py": ("def foo():\n    bar()\n\n\ndef bar():\n    pass\n"),
        },
    )

    result = build_symbol_graph(project_root, LexibraryConfig())
    assert result.call_count == 1
    assert result.unresolved_call_count == 0

    conn = _open_db(project_root)
    try:
        rows = conn.execute(
            "SELECT caller.qualified_name, callee.qualified_name, c.line "
            "FROM calls c "
            "JOIN symbols caller ON c.caller_id = caller.id "
            "JOIN symbols callee ON c.callee_id = callee.id",
        ).fetchall()
    finally:
        conn.close()

    assert len(rows) == 1
    caller_q, callee_q, line = rows[0]
    assert caller_q == "pkg.a.foo"
    assert callee_q == "pkg.a.bar"
    assert line == 2


# ---------------------------------------------------------------------------
# Test 3 — cross-file calls
# ---------------------------------------------------------------------------


def test_build_populates_cross_file_calls(tmp_path: Path) -> None:
    """``from pkg.b import bar; baz() → bar()`` resolves across files."""
    project_root = _make_project(
        tmp_path,
        {
            "src/pkg/b.py": "def bar():\n    pass\n",
            "src/pkg/c.py": ("from pkg.b import bar\n\n\ndef baz():\n    bar()\n"),
        },
    )

    result = build_symbol_graph(project_root, LexibraryConfig())
    assert result.unresolved_call_count == 0
    assert result.call_count == 1

    conn = _open_db(project_root)
    try:
        rows = conn.execute(
            "SELECT caller.qualified_name, callee.qualified_name, "
            "       caller_file.path, callee_file.path "
            "FROM calls c "
            "JOIN symbols caller ON c.caller_id = caller.id "
            "JOIN symbols callee ON c.callee_id = callee.id "
            "JOIN files caller_file ON caller.file_id = caller_file.id "
            "JOIN files callee_file ON callee.file_id = callee_file.id",
        ).fetchall()
    finally:
        conn.close()

    assert len(rows) == 1
    caller_q, callee_q, caller_path, callee_path = rows[0]
    assert caller_q == "pkg.c.baz"
    assert callee_q == "pkg.b.bar"
    assert Path(caller_path) == Path("src/pkg/c.py")
    assert Path(callee_path) == Path("src/pkg/b.py")


# ---------------------------------------------------------------------------
# Test 4 — unresolved external call (sqlite3.connect)
# ---------------------------------------------------------------------------


def test_build_captures_unresolved_external_call(tmp_path: Path) -> None:
    """Third-party calls land in ``unresolved_calls``."""
    project_root = _make_project(
        tmp_path,
        {
            "src/pkg/db.py": (
                "import sqlite3\n\n\ndef open_db():\n    sqlite3.connect(':memory:')\n"
            ),
        },
    )

    result = build_symbol_graph(project_root, LexibraryConfig())
    assert result.call_count == 0
    assert result.unresolved_call_count == 1

    conn = _open_db(project_root)
    try:
        rows = conn.execute(
            "SELECT caller.qualified_name, u.callee_name "
            "FROM unresolved_calls u "
            "JOIN symbols caller ON u.caller_id = caller.id",
        ).fetchall()
    finally:
        conn.close()

    assert len(rows) == 1
    caller_q, callee_name = rows[0]
    assert caller_q == "pkg.db.open_db"
    assert "connect" in callee_name


# ---------------------------------------------------------------------------
# Test 5 — disabled config short-circuit
# ---------------------------------------------------------------------------


def test_build_respects_symbols_disabled(tmp_path: Path) -> None:
    """``config.symbols.enabled = False`` skips the build entirely."""
    root = tmp_path.resolve()
    (root / "src" / "pkg").mkdir(parents=True)
    (root / "src" / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (root / "src" / "pkg" / "a.py").write_text(
        "def foo():\n    pass\n",
        encoding="utf-8",
    )

    disabled = LexibraryConfig(symbols=SymbolGraphConfig(enabled=False))
    result = build_symbol_graph(root, disabled)

    assert result.file_count == 0
    assert result.symbol_count == 0
    assert result.call_count == 0
    # No DB file should have been created — the build short-circuits before
    # any filesystem mutation.
    assert not symbols_db_path(root).exists()


# ---------------------------------------------------------------------------
# Test 6 — full rebuild removes stale rows
# ---------------------------------------------------------------------------


def test_build_full_rebuild_removes_stale_rows(tmp_path: Path) -> None:
    """Deleting a file and rebuilding wipes its rows."""
    project_root = _make_project(
        tmp_path,
        {
            "src/pkg/a.py": "def foo():\n    pass\n",
            "src/pkg/b.py": "def bar():\n    pass\n",
        },
    )
    config = LexibraryConfig()

    first = build_symbol_graph(project_root, config)
    # 3 files: a.py, b.py, __init__.py; 2 symbols (empty __init__ has none).
    assert first.file_count == 3
    assert first.symbol_count == 2

    # Delete one file and rebuild.
    (project_root / "src" / "pkg" / "b.py").unlink()

    second = build_symbol_graph(project_root, config)
    # 2 files: a.py, __init__.py; still 1 symbol.
    assert second.file_count == 2
    assert second.symbol_count == 1

    conn = _open_db(project_root)
    try:
        paths = sorted(
            row[0] for row in conn.execute("SELECT path FROM files ORDER BY path").fetchall()
        )
        names = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM symbols ORDER BY name",
            ).fetchall()
        ]
    finally:
        conn.close()

    assert paths == sorted([str(Path("src/pkg/__init__.py")), str(Path("src/pkg/a.py"))])
    assert names == ["foo"]


# ---------------------------------------------------------------------------
# Test 7 — files table populated
# ---------------------------------------------------------------------------


def test_build_records_files_table(tmp_path: Path) -> None:
    """Each processed file has a ``files`` row with a real hash + language."""
    project_root = _make_project(
        tmp_path,
        {
            "src/pkg/a.py": "def foo():\n    pass\n",
            "src/pkg/b.py": "def bar():\n    pass\n",
        },
    )

    build_symbol_graph(project_root, LexibraryConfig())

    conn = _open_db(project_root)
    try:
        rows = conn.execute(
            "SELECT path, language, last_hash FROM files ORDER BY path",
        ).fetchall()
    finally:
        conn.close()

    # 3 files: a.py, b.py, __init__.py.
    assert len(rows) == 3
    for row in rows:
        path, language, last_hash = row
        assert path.endswith(".py")
        assert language == "python"
        assert last_hash
        assert len(last_hash) == 64  # SHA-256 hex digest


# ---------------------------------------------------------------------------
# Test 8 — 250-file benchmark
# ---------------------------------------------------------------------------


def test_build_benchmark_250_files(tmp_path: Path) -> None:
    """250 small Python files must rebuild in under 5000 ms."""
    files: dict[str, str] = {}
    for i in range(250):
        # Every file defines three functions and calls one from the previous
        # file (creating a cross-file call chain for the resolver to walk).
        prev = (i - 1) % 250
        content = (
            f"from pkg.mod_{prev} import fn_{prev}_a\n\n\n"
            f"def fn_{i}_a() -> int:\n"
            f"    return fn_{prev}_a() + 1\n\n\n"
            f"def fn_{i}_b() -> int:\n"
            f"    return fn_{i}_a() + 2\n\n\n"
            f"def fn_{i}_c() -> int:\n"
            f"    return fn_{i}_b() + 3\n"
        )
        files[f"src/pkg/mod_{i}.py"] = content

    project_root = _make_project(tmp_path, files)

    result = build_symbol_graph(project_root, LexibraryConfig())

    # 250 mod_N.py files plus the package's empty __init__.py.
    assert result.file_count == 251
    assert result.symbol_count == 250 * 3
    assert result.duration_ms < 5000, (
        f"250-file rebuild took {result.duration_ms} ms (budget 5000 ms)"
    )


# ---------------------------------------------------------------------------
# Test 9 — golden snapshot
# ---------------------------------------------------------------------------


def _write_golden_fixture(dest_root: Path) -> None:
    """Copy (or seed in-place) the canonical golden project into ``dest_root``.

    The fixture must be deterministic: the snapshot compares byte-for-byte
    JSON output so any drift in the fixture text invalidates the snapshot.
    """
    # Write the fixture files fresh every time to avoid any cached state in
    # the repo copy leaking into the test.
    files: dict[str, str] = {
        "src/pkg/__init__.py": "",
        "src/pkg/animals.py": (
            '"""Animal hierarchy used by the golden snapshot test."""\n\n'
            "from __future__ import annotations\n\n\n"
            "class Animal:\n"
            "    def speak(self) -> str:\n"
            '        return "..."\n\n\n'
            "class Dog(Animal):\n"
            "    def speak(self) -> str:\n"
            '        return "woof"\n\n'
            "    def fetch(self) -> str:\n"
            "        return self.speak()\n"
        ),
        "src/pkg/zoo.py": (
            '"""Zoo module calling animals."""\n\n'
            "from __future__ import annotations\n\n"
            "from pkg.animals import Dog\n\n\n"
            "def play_with_dog() -> str:\n"
            "    dog = Dog()\n"
            "    return dog.fetch()\n\n\n"
            "def greet() -> str:\n"
            "    return play_with_dog()\n"
        ),
    }
    (dest_root / ".lexibrary").mkdir(exist_ok=True)
    for rel, content in files.items():
        file_path = dest_root / rel
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")


def _snapshot_db(project_root: Path) -> dict[str, list[dict[str, Any]]]:
    """Serialise files/symbols/calls/unresolved_calls to a stable dict.

    Orders by ``(file_path, line_start)`` / ``(caller, callee, line)`` so
    primary-key churn never flips the snapshot.
    """
    conn = _open_db(project_root)
    try:
        conn.row_factory = sqlite3.Row

        files_rows = [
            {"path": row["path"], "language": row["language"]}
            for row in conn.execute(
                "SELECT path, language FROM files ORDER BY path",
            ).fetchall()
        ]

        symbol_rows = conn.execute(
            "SELECT f.path AS file_path, s.name, s.qualified_name, "
            "       s.symbol_type, s.line_start, s.line_end, s.visibility, "
            "       s.parent_class "
            "FROM symbols s "
            "JOIN files f ON s.file_id = f.id "
            "ORDER BY f.path, s.line_start, s.name",
        ).fetchall()
        symbols = [dict(row) for row in symbol_rows]

        calls_rows = conn.execute(
            "SELECT caller.qualified_name AS caller, "
            "       callee.qualified_name AS callee, "
            "       c.line, c.call_context "
            "FROM calls c "
            "JOIN symbols caller ON c.caller_id = caller.id "
            "JOIN symbols callee ON c.callee_id = callee.id "
            "ORDER BY caller, callee, c.line",
        ).fetchall()
        calls = [dict(row) for row in calls_rows]

        unresolved_rows = conn.execute(
            "SELECT caller.qualified_name AS caller, "
            "       u.callee_name, u.line, u.call_context "
            "FROM unresolved_calls u "
            "JOIN symbols caller ON u.caller_id = caller.id "
            "ORDER BY caller, u.callee_name, u.line",
        ).fetchall()
        unresolved = [dict(row) for row in unresolved_rows]
    finally:
        conn.close()

    return {
        "files": files_rows,
        "symbols": symbols,
        "calls": calls,
        "unresolved_calls": unresolved,
    }


def test_build_golden_snapshot(tmp_path: Path) -> None:
    """Build against the canonical golden project and compare to snapshot.

    Set ``LEXIBRARY_UPDATE_GOLDEN=1`` when first creating the snapshot
    (or intentionally regenerating it after an extractor change).
    """
    project_root = tmp_path.resolve()
    _write_golden_fixture(project_root)

    build_symbol_graph(project_root, LexibraryConfig())
    snapshot = _snapshot_db(project_root)
    snapshot_json = json.dumps(snapshot, indent=2, sort_keys=True)

    if os.environ.get("LEXIBRARY_UPDATE_GOLDEN") == "1":
        GOLDEN_SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN_SNAPSHOT_PATH.write_text(snapshot_json + "\n", encoding="utf-8")
        pytest.skip(f"Wrote golden snapshot to {GOLDEN_SNAPSHOT_PATH}")

    if not GOLDEN_SNAPSHOT_PATH.exists():
        pytest.fail(
            f"Golden snapshot {GOLDEN_SNAPSHOT_PATH} does not exist — "
            "run with LEXIBRARY_UPDATE_GOLDEN=1 to create it."
        )

    expected = GOLDEN_SNAPSHOT_PATH.read_text(encoding="utf-8").rstrip("\n")
    assert snapshot_json == expected, (
        "golden snapshot drift — inspect the diff and either fix the "
        "extractor regression or regenerate with LEXIBRARY_UPDATE_GOLDEN=1"
    )
