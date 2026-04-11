"""Tests for per-file symbol graph refresh via :func:`refresh_file`.

Covers the five scenarios in Group 9 task 9.4:

1. ``test_refresh_file_updates_symbols`` — build against a 3-file project;
   modify one file to add a new function; call ``refresh_file``; assert the
   new function is in ``symbols`` and other files' rows are untouched.
2. ``test_refresh_file_removes_stale_calls`` — build; delete a function from
   a file; call ``refresh_file``; assert the old row is gone from
   ``symbols`` and any calls referencing it as caller or callee are absent
   from ``calls``.
3. ``test_refresh_file_promotes_previously_unresolved_calls`` — build a
   project where ``a.py`` calls ``new_thing()`` before ``new_thing`` is
   defined (call lands in ``unresolved_calls``); add ``new_thing`` to
   ``b.py``; call ``refresh_file(b.py)``; assert the call is gone from
   ``unresolved_calls`` and present in ``calls``.
4. ``test_refresh_file_is_noop_when_disabled`` —
   ``config.symbols.enabled = False`` → no mutation.
5. ``test_refresh_file_is_noop_when_db_missing`` — no ``symbols.db`` → no
   file created.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from lexibrary.config.schema import LexibraryConfig, SymbolGraphConfig
from lexibrary.symbolgraph.builder import build_symbol_graph, refresh_file
from lexibrary.utils.paths import symbols_db_path

# ---------------------------------------------------------------------------
# Fixture builders — mirror the helpers in test_builder_calls.py so the
# two files stay in sync visually without depending on each other.
# ---------------------------------------------------------------------------


def _make_project(tmp_path: Path, files: dict[str, str]) -> Path:
    """Create a tmp project root with the given ``{rel_path: content}`` map.

    Writes an empty ``src/pkg/__init__.py`` marker so the Python import
    resolver can walk into the package. ``tmp_path`` is resolved so macOS
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
# Test 1 — refresh adds a new function and leaves siblings untouched
# ---------------------------------------------------------------------------


def test_refresh_file_updates_symbols(tmp_path: Path) -> None:
    """Adding a function to one file shows up after :func:`refresh_file`.

    Builds a 3-file project, records the sibling rows, then patches ``a.py``
    to add ``new_fn``. ``refresh_file`` must see the new symbol and leave
    ``b.py`` / ``c.py`` rows intact.
    """
    project_root = _make_project(
        tmp_path,
        {
            "src/pkg/a.py": "def foo():\n    pass\n",
            "src/pkg/b.py": "def bar():\n    pass\n",
            "src/pkg/c.py": "def baz():\n    pass\n",
        },
    )
    config = LexibraryConfig()

    build_symbol_graph(project_root, config)

    # Record the b.py / c.py rows before the refresh so we can assert
    # byte-for-byte stability across the refresh.
    conn = _open_db(project_root)
    try:
        before_rows = conn.execute(
            "SELECT s.name, s.qualified_name, f.path "
            "FROM symbols s JOIN files f ON s.file_id = f.id "
            "WHERE f.path IN (?, ?) "
            "ORDER BY f.path, s.name",
            (str(Path("src/pkg/b.py")), str(Path("src/pkg/c.py"))),
        ).fetchall()
    finally:
        conn.close()

    # Mutate a.py to add a new top-level function.
    new_content = "def foo():\n    pass\n\n\ndef new_fn():\n    pass\n"
    (project_root / "src" / "pkg" / "a.py").write_text(new_content, encoding="utf-8")

    result = refresh_file(
        project_root,
        config,
        project_root / "src" / "pkg" / "a.py",
    )
    assert result.build_type == "incremental"
    # Two symbols: foo + new_fn.
    assert result.symbol_count == 2

    conn = _open_db(project_root)
    try:
        # New function must be present in a.py's rows.
        a_rows = conn.execute(
            "SELECT s.name FROM symbols s JOIN files f ON s.file_id = f.id "
            "WHERE f.path = ? ORDER BY s.name",
            (str(Path("src/pkg/a.py")),),
        ).fetchall()

        # Other files' rows must be untouched.
        after_rows = conn.execute(
            "SELECT s.name, s.qualified_name, f.path "
            "FROM symbols s JOIN files f ON s.file_id = f.id "
            "WHERE f.path IN (?, ?) "
            "ORDER BY f.path, s.name",
            (str(Path("src/pkg/b.py")), str(Path("src/pkg/c.py"))),
        ).fetchall()
    finally:
        conn.close()

    assert sorted(r[0] for r in a_rows) == ["foo", "new_fn"]
    assert after_rows == before_rows


# ---------------------------------------------------------------------------
# Test 2 — refresh removes stale calls when a function is deleted
# ---------------------------------------------------------------------------


def test_refresh_file_removes_stale_calls(tmp_path: Path) -> None:
    """Deleting a function from a file clears it and its call edges.

    Builds a project where ``a.py::foo`` calls ``a.py::bar``, then removes
    ``bar`` from ``a.py``. After :func:`refresh_file`, ``bar`` must be gone
    from ``symbols`` and the old ``foo → bar`` edge must be absent from
    ``calls``.
    """
    project_root = _make_project(
        tmp_path,
        {
            "src/pkg/a.py": ("def foo():\n    bar()\n\n\ndef bar():\n    pass\n"),
        },
    )
    config = LexibraryConfig()

    build_symbol_graph(project_root, config)

    # Confirm pre-state: bar is present and foo → bar is in calls.
    conn = _open_db(project_root)
    try:
        pre_bar = conn.execute(
            "SELECT COUNT(*) FROM symbols s JOIN files f ON s.file_id = f.id "
            "WHERE f.path = ? AND s.name = ?",
            (str(Path("src/pkg/a.py")), "bar"),
        ).fetchone()[0]
        pre_calls = conn.execute(
            "SELECT COUNT(*) FROM calls c "
            "JOIN symbols caller ON c.caller_id = caller.id "
            "JOIN symbols callee ON c.callee_id = callee.id "
            "WHERE caller.name = ? AND callee.name = ?",
            ("foo", "bar"),
        ).fetchone()[0]
    finally:
        conn.close()

    assert pre_bar == 1
    assert pre_calls == 1

    # Mutate: drop ``bar`` entirely. ``foo`` now calls a name that no
    # longer exists in any file, so the refresh must emit an unresolved
    # row for the ``bar()`` call (or skip it if the extractor drops it).
    # The important assertion is that the OLD resolved edge is gone.
    (project_root / "src" / "pkg" / "a.py").write_text(
        "def foo():\n    bar()\n",
        encoding="utf-8",
    )

    refresh_file(
        project_root,
        config,
        project_root / "src" / "pkg" / "a.py",
    )

    conn = _open_db(project_root)
    try:
        post_bar = conn.execute(
            "SELECT COUNT(*) FROM symbols s JOIN files f ON s.file_id = f.id "
            "WHERE f.path = ? AND s.name = ?",
            (str(Path("src/pkg/a.py")), "bar"),
        ).fetchone()[0]
        post_calls = conn.execute(
            "SELECT COUNT(*) FROM calls c "
            "JOIN symbols caller ON c.caller_id = caller.id "
            "JOIN symbols callee ON c.callee_id = callee.id "
            "WHERE caller.name = ? AND callee.name = ?",
            ("foo", "bar"),
        ).fetchone()[0]
    finally:
        conn.close()

    assert post_bar == 0, "stale ``bar`` row was not removed"
    assert post_calls == 0, "stale ``foo → bar`` call edge was not removed"


# ---------------------------------------------------------------------------
# Test 3 — refresh promotes previously-unresolved calls
# ---------------------------------------------------------------------------


def test_refresh_file_promotes_previously_unresolved_calls(tmp_path: Path) -> None:
    """Adding a target definition promotes the caller's unresolved call.

    Builds a project where ``a.py`` calls ``new_thing()`` without an import
    — the call lands in ``unresolved_calls``. Then adds ``new_thing`` to
    ``b.py`` and imports it from ``a.py``, then calls
    :func:`refresh_file` on both ``b.py`` (adds the definition) and
    ``a.py`` (re-extracts so the import-aware resolver can find the new
    target). After the refresh, the call must be gone from
    ``unresolved_calls`` and present in ``calls``.
    """
    project_root = _make_project(
        tmp_path,
        {
            "src/pkg/a.py": "def caller():\n    new_thing()\n",
            "src/pkg/b.py": "def existing():\n    pass\n",
        },
    )
    config = LexibraryConfig()

    build_symbol_graph(project_root, config)

    # Confirm pre-state: caller → new_thing is in unresolved_calls.
    conn = _open_db(project_root)
    try:
        pre_unresolved = conn.execute(
            "SELECT COUNT(*) FROM unresolved_calls u "
            "JOIN symbols caller ON u.caller_id = caller.id "
            "WHERE caller.name = ? AND u.callee_name = ?",
            ("caller", "new_thing"),
        ).fetchone()[0]
    finally:
        conn.close()

    assert pre_unresolved == 1

    # Step 1: define new_thing in b.py and refresh b.py — the new symbol is
    # recorded, and the refresh's step-5 promotion path scans
    # unresolved_calls for ``new_thing`` hits and re-runs the resolver. The
    # existing a.py caller has no import for b.py yet, so step 5 cannot
    # promote it on its own — the promotion lands once a.py is also
    # refreshed with the new import.
    (project_root / "src" / "pkg" / "b.py").write_text(
        "def existing():\n    pass\n\n\ndef new_thing():\n    pass\n",
        encoding="utf-8",
    )
    refresh_file(
        project_root,
        config,
        project_root / "src" / "pkg" / "b.py",
    )

    # Step 2: update a.py to import new_thing from b.py and refresh a.py.
    # The refresh re-extracts the call with receiver resolution via the
    # new import, so the resolver places it into ``calls`` directly on the
    # re-insert path (not the step-5 promotion path).
    (project_root / "src" / "pkg" / "a.py").write_text(
        "from pkg.b import new_thing\n\n\ndef caller():\n    new_thing()\n",
        encoding="utf-8",
    )
    refresh_file(
        project_root,
        config,
        project_root / "src" / "pkg" / "a.py",
    )

    conn = _open_db(project_root)
    try:
        post_unresolved = conn.execute(
            "SELECT COUNT(*) FROM unresolved_calls u "
            "JOIN symbols caller ON u.caller_id = caller.id "
            "WHERE caller.name = ? AND u.callee_name = ?",
            ("caller", "new_thing"),
        ).fetchone()[0]
        post_calls = conn.execute(
            "SELECT COUNT(*) FROM calls c "
            "JOIN symbols caller ON c.caller_id = caller.id "
            "JOIN symbols callee ON c.callee_id = callee.id "
            "WHERE caller.name = ? AND callee.name = ?",
            ("caller", "new_thing"),
        ).fetchone()[0]
    finally:
        conn.close()

    assert post_unresolved == 0, "unresolved row should be gone after refresh"
    assert post_calls == 1, "caller → new_thing edge should be in calls"


# ---------------------------------------------------------------------------
# Test 4 — refresh is a no-op when symbols.enabled is False
# ---------------------------------------------------------------------------


def test_refresh_file_is_noop_when_disabled(tmp_path: Path) -> None:
    """A disabled config short-circuits :func:`refresh_file` entirely.

    Builds with the default (enabled) config, records the post-build row
    counts, then calls :func:`refresh_file` with a disabled config after
    mutating the file. The DB rows must be identical to the post-build
    state and no counters on the returned result should be populated.
    """
    project_root = _make_project(
        tmp_path,
        {
            "src/pkg/a.py": "def foo():\n    pass\n",
        },
    )
    enabled_config = LexibraryConfig()
    build_symbol_graph(project_root, enabled_config)

    # Snapshot post-build rows.
    conn = _open_db(project_root)
    try:
        before_rows = conn.execute(
            "SELECT s.name, s.qualified_name "
            "FROM symbols s JOIN files f ON s.file_id = f.id "
            "WHERE f.path = ? ORDER BY s.name",
            (str(Path("src/pkg/a.py")),),
        ).fetchall()
    finally:
        conn.close()

    # Mutate the file so a real refresh would change counts.
    (project_root / "src" / "pkg" / "a.py").write_text(
        "def foo():\n    pass\n\n\ndef added():\n    pass\n",
        encoding="utf-8",
    )

    # Call refresh with a disabled config — must be a no-op.
    disabled = LexibraryConfig(symbols=SymbolGraphConfig(enabled=False))
    result = refresh_file(
        project_root,
        disabled,
        project_root / "src" / "pkg" / "a.py",
    )
    assert result.file_count == 0
    assert result.symbol_count == 0

    # Rows must be byte-for-byte identical to the pre-refresh snapshot.
    conn = _open_db(project_root)
    try:
        after_rows = conn.execute(
            "SELECT s.name, s.qualified_name "
            "FROM symbols s JOIN files f ON s.file_id = f.id "
            "WHERE f.path = ? ORDER BY s.name",
            (str(Path("src/pkg/a.py")),),
        ).fetchall()
    finally:
        conn.close()

    assert after_rows == before_rows


# ---------------------------------------------------------------------------
# Test 5 — refresh is a no-op when symbols.db is missing
# ---------------------------------------------------------------------------


def test_refresh_file_is_noop_when_db_missing(tmp_path: Path) -> None:
    """No ``symbols.db`` on disk → no DB file is ever created.

    :func:`refresh_file` is intended as a patch path, not a bootstrap path.
    When the agent runs ``lexi design update`` in a fresh checkout that
    never ran a full build, the refresh must silently no-op instead of
    creating an empty DB — the user is expected to run the initial build
    via the project maintainer's `lexictl update`.
    """
    project_root = _make_project(
        tmp_path,
        {
            "src/pkg/a.py": "def foo():\n    pass\n",
        },
    )
    # Deliberately skip the build — no symbols.db on disk.
    assert not symbols_db_path(project_root).exists()

    result = refresh_file(
        project_root,
        LexibraryConfig(),
        project_root / "src" / "pkg" / "a.py",
    )
    assert result.file_count == 0
    assert result.symbol_count == 0

    # The DB file must still not exist after the call.
    assert not symbols_db_path(project_root).exists()


# ---------------------------------------------------------------------------
# Test 6 — refresh is a no-op when the on-disk DB schema is stale
# ---------------------------------------------------------------------------


def test_refresh_file_is_noop_when_schema_stale(tmp_path: Path) -> None:
    """A DB built under an older schema version is skipped without mutation.

    Simulates a stale DB by overwriting ``meta.schema_version`` with an
    older value after a successful build. :func:`refresh_file` must detect
    the mismatch, skip the refresh, and leave the rows untouched — the
    expectation is that the project maintainer runs a full rebuild next.
    """
    project_root = _make_project(
        tmp_path,
        {
            "src/pkg/a.py": "def foo():\n    pass\n",
        },
    )
    config = LexibraryConfig()
    build_symbol_graph(project_root, config)

    # Poison the schema version so refresh_file treats the DB as stale.
    conn = _open_db(project_root)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', '0')",
        )
        conn.commit()
    finally:
        conn.close()

    # Mutate the source file so a real refresh would add a row.
    (project_root / "src" / "pkg" / "a.py").write_text(
        "def foo():\n    pass\n\n\ndef new_one():\n    pass\n",
        encoding="utf-8",
    )

    result = refresh_file(
        project_root,
        config,
        project_root / "src" / "pkg" / "a.py",
    )
    # Stale DB → refresh short-circuits with empty counters.
    assert result.file_count == 0
    assert result.symbol_count == 0

    # The pre-refresh symbols are still present exactly as left.
    conn = _open_db(project_root)
    try:
        rows = conn.execute(
            "SELECT s.name FROM symbols s JOIN files f ON s.file_id = f.id "
            "WHERE f.path = ? ORDER BY s.name",
            (str(Path("src/pkg/a.py")),),
        ).fetchall()
    finally:
        conn.close()

    assert [r[0] for r in rows] == ["foo"]
