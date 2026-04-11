"""Shared fixtures for ``tests/test_symbolgraph/``.

The :func:`seed_phase2_fixture` helper builds a minimal Phase 2 symbol
graph (two files, four symbols, three resolved calls, one unresolved
call) directly on disk at the requested project root. It is defined as
a plain function (not a pytest fixture) so tests outside this directory
can import it via::

    from tests.test_symbolgraph.conftest import seed_phase2_fixture

This keeps CLI tests under ``tests/test_cli/`` sharing the exact same
on-disk layout that ``tests/test_services/test_symbols.py`` uses for
its Phase 2 coverage. If a caller wants pytest-style injection, a thin
wrapper around the helper suffices — see :func:`phase2_project` below
for an example.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from lexibrary.config.schema import LexibraryConfig
from lexibrary.linkgraph.schema import ensure_schema as ensure_linkgraph_schema
from lexibrary.symbolgraph import build_symbol_graph
from lexibrary.symbolgraph.query import open_symbol_graph
from lexibrary.utils.hashing import hash_file


def make_project(tmp_path: Path) -> Path:
    """Create a minimal project root with an empty ``.lexibrary/``."""
    (tmp_path / ".lexibrary").mkdir(exist_ok=True)
    return tmp_path


def make_linkgraph(project_root: Path) -> Path:
    """Create a valid (but empty) link graph database.

    ``open_index`` checks the schema version before returning a
    connection, so we ship the schema via :func:`ensure_linkgraph_schema`
    directly.
    """
    db_path = project_root / ".lexibrary" / "index.db"
    conn = sqlite3.connect(str(db_path))
    ensure_linkgraph_schema(conn)
    conn.commit()
    conn.close()
    return db_path


def make_symbolgraph(project_root: Path) -> Path:
    """Create an empty ``symbols.db`` via the real builder."""
    build_symbol_graph(project_root, LexibraryConfig())
    return project_root / ".lexibrary" / "symbols.db"


def write_source_file(
    project_root: Path,
    rel_path: str,
    text: str = "placeholder\n",
) -> Path:
    """Write a source file under *project_root* and return its absolute path."""
    abs_path = project_root / rel_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(text)
    return abs_path


def seed_phase2_fixture(project_root: Path) -> dict[str, Any]:
    """Seed ``symbols.db`` with a minimal Phase 2 corpus.

    Two files, four symbols, three resolved calls, one unresolved call:

    - ``src/a.py``::

        def foo():
            bar()
            sqlite3.connect(...)  # unresolved

        def bar(): ...

    - ``src/b.py``::

        def baz():
            bar()

        class Klass:
            def meth(self):
                baz()

    Returns a dict of ids keyed by symbol name for use in assertions.
    The on-disk source files are also written with real content so the
    ``files.last_hash`` entries match ``hash_file()`` — the stale-graph
    tests reach in later to perturb the stored hash directly.
    """
    a_src = write_source_file(project_root, "src/a.py", "# file a\n")
    b_src = write_source_file(project_root, "src/b.py", "# file b\n")

    hash_a = hash_file(a_src)
    hash_b = hash_file(b_src)

    graph = open_symbol_graph(project_root)
    conn = graph._conn
    try:
        cur = conn.execute(
            "INSERT INTO files (path, language, last_hash) VALUES (?, ?, ?)",
            ("src/a.py", "python", hash_a),
        )
        file_a_id = int(cur.lastrowid or 0)
        cur = conn.execute(
            "INSERT INTO files (path, language, last_hash) VALUES (?, ?, ?)",
            ("src/b.py", "python", hash_b),
        )
        file_b_id = int(cur.lastrowid or 0)

        def _add_symbol(
            file_id: int,
            name: str,
            qualified_name: str | None,
            symbol_type: str,
            line_start: int,
            line_end: int,
            visibility: str | None,
            parent_class: str | None = None,
        ) -> int:
            cur = conn.execute(
                "INSERT INTO symbols "
                "(file_id, name, qualified_name, symbol_type, line_start, "
                "line_end, visibility, parent_class) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    file_id,
                    name,
                    qualified_name,
                    symbol_type,
                    line_start,
                    line_end,
                    visibility,
                    parent_class,
                ),
            )
            return int(cur.lastrowid or 0)

        foo_id = _add_symbol(file_a_id, "foo", "a.foo", "function", 1, 4, "public")
        bar_id = _add_symbol(file_a_id, "bar", "a.bar", "function", 6, 8, "public")
        baz_id = _add_symbol(file_b_id, "baz", "b.baz", "function", 1, 3, "public")
        meth_id = _add_symbol(
            file_b_id,
            "meth",
            "b.Klass.meth",
            "method",
            6,
            9,
            "public",
            parent_class="Klass",
        )

        resolved = [
            (foo_id, bar_id, 2, "call"),
            (baz_id, bar_id, 2, "call"),
            (meth_id, baz_id, 7, "call"),
        ]
        for caller, callee, line, ctx in resolved:
            conn.execute(
                "INSERT INTO calls (caller_id, callee_id, line, call_context) VALUES (?, ?, ?, ?)",
                (caller, callee, line, ctx),
            )

        conn.execute(
            "INSERT INTO unresolved_calls "
            "(caller_id, callee_name, line, call_context) "
            "VALUES (?, ?, ?, ?)",
            (foo_id, "sqlite3.connect", 3, "call"),
        )

        conn.commit()
    finally:
        graph.close()

    return {
        "file_a_id": file_a_id,
        "file_b_id": file_b_id,
        "foo_id": foo_id,
        "bar_id": bar_id,
        "baz_id": baz_id,
        "meth_id": meth_id,
        "hash_a": hash_a,
        "hash_b": hash_b,
    }


def seed_phase3_class_fixture(project_root: Path) -> dict[str, Any]:
    """Seed ``symbols.db`` with a minimal Phase 3 class hierarchy corpus.

    One file ``src/pkg.py`` carrying four symbols and four class edges:

    - ``class Base`` at line 1 — the canonical base with one resolved
      subclass and one instantiation site.
    - ``class Derived(Base)`` at line 5 — inherits from ``Base`` and is
      instantiated by ``main``.
    - ``class Thing(BaseModel, Enum)`` at line 10 — inherits from two
      out-of-scope external bases that both land in
      ``class_edges_unresolved``.
    - ``def main()`` at line 13 — the instantiation site for
      ``Derived``.

    Two resolved edges land in ``class_edges``:

    - ``Derived → Base`` (``inherits``).
    - ``main → Derived`` (``instantiates``).

    Two unresolved edges land in ``class_edges_unresolved``:

    - ``Thing → BaseModel`` (``inherits``).
    - ``Thing → Enum`` (``inherits``).

    Returns a dict of ids keyed by symbol name for use in assertions.
    The on-disk source file is written with a placeholder so
    ``files.last_hash`` matches the hash :func:`hash_file` computes —
    staleness checks against the seeded fixture therefore pass by
    default.
    """
    src = write_source_file(project_root, "src/pkg.py", "# phase 3 class fixture\n")
    src_hash = hash_file(src)

    graph = open_symbol_graph(project_root)
    conn = graph._conn
    try:
        cur = conn.execute(
            "INSERT INTO files (path, language, last_hash) VALUES (?, ?, ?)",
            ("src/pkg.py", "python", src_hash),
        )
        file_id = int(cur.lastrowid or 0)

        def _add_symbol(
            name: str,
            qualified_name: str | None,
            symbol_type: str,
            line_start: int,
            line_end: int,
        ) -> int:
            cur = conn.execute(
                "INSERT INTO symbols "
                "(file_id, name, qualified_name, symbol_type, line_start, "
                "line_end, visibility, parent_class) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
                (file_id, name, qualified_name, symbol_type, line_start, line_end, "public"),
            )
            return int(cur.lastrowid or 0)

        base_id = _add_symbol("Base", "pkg.Base", "class", 1, 3)
        derived_id = _add_symbol("Derived", "pkg.Derived", "class", 5, 8)
        thing_id = _add_symbol("Thing", "pkg.Thing", "class", 10, 11)
        main_id = _add_symbol("main", "pkg.main", "function", 13, 15)

        # class_edges: Derived inherits Base; main instantiates Derived.
        conn.execute(
            "INSERT INTO class_edges (source_id, target_id, edge_type, line, context) "
            "VALUES (?, ?, ?, ?, NULL)",
            (derived_id, base_id, "inherits", 5),
        )
        conn.execute(
            "INSERT INTO class_edges (source_id, target_id, edge_type, line, context) "
            "VALUES (?, ?, ?, ?, NULL)",
            (main_id, derived_id, "instantiates", 14),
        )

        # class_edges_unresolved: Thing inherits BaseModel and Enum
        # (both out-of-scope — the "Unresolved bases" row exercises the
        # multi-target join path).
        conn.execute(
            "INSERT INTO class_edges_unresolved "
            "(source_id, target_name, edge_type, line) VALUES (?, ?, ?, ?)",
            (thing_id, "BaseModel", "inherits", 10),
        )
        conn.execute(
            "INSERT INTO class_edges_unresolved "
            "(source_id, target_name, edge_type, line) VALUES (?, ?, ?, ?)",
            (thing_id, "Enum", "inherits", 10),
        )

        conn.commit()
    finally:
        graph.close()

    return {
        "file_id": file_id,
        "base_id": base_id,
        "derived_id": derived_id,
        "thing_id": thing_id,
        "main_id": main_id,
    }


@pytest.fixture
def phase2_project(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    """Pytest-style wrapper around :func:`seed_phase2_fixture`.

    Creates a project root, an empty link graph, and a seeded symbol
    graph in one call. Returns a ``(project_root, ids)`` tuple so tests
    can dereference seeded symbol ids without re-seeding.
    """
    project = make_project(tmp_path)
    make_linkgraph(project)
    ids = seed_phase2_fixture(project)
    return project, ids
