"""Unit tests for :meth:`PythonResolver.resolve_self_method_with_mro`.

Phase 3 extends ``self.foo()`` resolution with an MRO walk that follows
``class_edges`` rows with ``edge_type='inherits'`` to find a matching
method on an ancestor class. The resolver's fast path
(:meth:`PythonResolver._resolve_self_method`) is unchanged — these tests
exercise the new BFS helper directly so we cover the four scenarios
enumerated in Phase 3 task 4.9:

1. ``test_mro_method_defined_on_same_class_returns_that`` — the fast
   path hits before the MRO walk runs; this test seeds only the
   enclosing class and asserts :meth:`_resolve_self_method` returns the
   direct method id without consulting ``class_edges``.
2. ``test_mro_method_defined_on_single_base_returns_base`` — one
   ``inherits`` edge, method defined only on the base; the BFS returns
   the base's method id.
3. ``test_mro_diamond_inheritance_picks_first_in_bfs_order`` — two
   bases both define the method; the first base in edge order wins
   (BFS by ``class_edges.line`` then ``id``).
4. ``test_mro_method_not_found_returns_none`` — no class in the
   hierarchy defines the method; the walk terminates with ``None``.

The tests drive the resolver with an in-memory SQLite DB seeded via the
same ``_insert_file`` / ``_insert_symbol`` helpers used by
``test_resolver_python.py``. No tree-sitter parsing is required — every
branch under test runs entirely against ``symbols`` / ``class_edges``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from lexibrary.ast_parser.models import CallSite
from lexibrary.config.schema import LexibraryConfig
from lexibrary.symbolgraph.resolver_python import PythonResolver
from lexibrary.symbolgraph.schema import ensure_schema

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def conn() -> sqlite3.Connection:
    """A fresh in-memory SQLite connection with the full symbol-graph schema."""
    connection = sqlite3.connect(":memory:")
    ensure_schema(connection)
    return connection


@pytest.fixture
def resolver(conn: sqlite3.Connection, tmp_path: Path) -> PythonResolver:
    """A :class:`PythonResolver` bound to ``conn`` and ``tmp_path``."""
    config = LexibraryConfig()
    return PythonResolver(conn, tmp_path, config)


def _insert_file(conn: sqlite3.Connection, path: str) -> int:
    """Insert a ``files`` row and return its primary key."""
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
    name: str,
    qualified_name: str | None = None,
    symbol_type: str = "class",
    parent_class: str | None = None,
    line_start: int = 1,
    line_end: int = 10,
    visibility: str = "public",
) -> int:
    """Insert a ``symbols`` row and return its primary key."""
    cursor = conn.execute(
        "INSERT INTO symbols "
        "(file_id, name, qualified_name, symbol_type, line_start, line_end, "
        " visibility, parent_class) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            file_id,
            name,
            qualified_name or name,
            symbol_type,
            line_start,
            line_end,
            visibility,
            parent_class,
        ),
    )
    row_id = cursor.lastrowid
    assert row_id is not None
    return row_id


def _insert_class_edge(
    conn: sqlite3.Connection,
    *,
    source_id: int,
    target_id: int,
    edge_type: str = "inherits",
    line: int | None = 1,
) -> None:
    """Insert a ``class_edges`` row."""
    conn.execute(
        "INSERT INTO class_edges "
        "(source_id, target_id, edge_type, line, context) "
        "VALUES (?, ?, ?, ?, ?)",
        (source_id, target_id, edge_type, line, None),
    )


# ---------------------------------------------------------------------------
# 1. Same-class method hits the fast path (no MRO walk)
# ---------------------------------------------------------------------------


def test_mro_method_defined_on_same_class_returns_that(
    conn: sqlite3.Connection,
    resolver: PythonResolver,
) -> None:
    """``self.foo()`` resolves to the method on the enclosing class.

    The fast path (:meth:`_resolve_self_method`) matches the method
    directly; no ``class_edges`` rows are consulted. This test ensures
    the MRO BFS helper does not kick in when the fast path succeeds.
    """
    file_id = _insert_file(conn, "src/pkg/a.py")
    _insert_symbol(
        conn,
        file_id,
        name="MyClass",
        qualified_name="pkg.a.MyClass",
        symbol_type="class",
        line_start=1,
        line_end=10,
    )
    foo_id = _insert_symbol(
        conn,
        file_id,
        name="foo",
        qualified_name="pkg.a.MyClass.foo",
        symbol_type="method",
        parent_class="MyClass",
        line_start=2,
        line_end=3,
    )
    _insert_symbol(
        conn,
        file_id,
        name="bar",
        qualified_name="pkg.a.MyClass.bar",
        symbol_type="method",
        parent_class="MyClass",
        line_start=5,
        line_end=6,
    )

    call = CallSite(
        caller_name="pkg.a.MyClass.bar",
        callee_name="foo",
        receiver="self",
        line=5,
    )
    assert resolver.resolve(call, file_id, "src/pkg/a.py") == foo_id


# ---------------------------------------------------------------------------
# 2. Method defined on single base — the BFS walks one inherits edge
# ---------------------------------------------------------------------------


def test_mro_method_defined_on_single_base_returns_base(
    conn: sqlite3.Connection,
    resolver: PythonResolver,
) -> None:
    """``Derived.bar(self.foo())`` finds ``Base.foo`` one hop away."""
    base_file_id = _insert_file(conn, "src/pkg/base.py")
    derived_file_id = _insert_file(conn, "src/pkg/derived.py")

    base_class_id = _insert_symbol(
        conn,
        base_file_id,
        name="Base",
        qualified_name="pkg.base.Base",
        symbol_type="class",
        line_start=1,
        line_end=10,
    )
    base_foo_id = _insert_symbol(
        conn,
        base_file_id,
        name="foo",
        qualified_name="pkg.base.Base.foo",
        symbol_type="method",
        parent_class="Base",
        line_start=2,
        line_end=3,
    )

    derived_class_id = _insert_symbol(
        conn,
        derived_file_id,
        name="Derived",
        qualified_name="pkg.derived.Derived",
        symbol_type="class",
        line_start=1,
        line_end=10,
    )
    _insert_symbol(
        conn,
        derived_file_id,
        name="bar",
        qualified_name="pkg.derived.Derived.bar",
        symbol_type="method",
        parent_class="Derived",
        line_start=2,
        line_end=5,
    )

    _insert_class_edge(
        conn,
        source_id=derived_class_id,
        target_id=base_class_id,
        edge_type="inherits",
        line=1,
    )

    # Direct helper call: resolver.resolve_self_method_with_mro should
    # walk the inherits edge and return ``Base.foo``.
    hit = resolver.resolve_self_method_with_mro(derived_class_id, "foo")
    assert hit == base_foo_id

    # End-to-end via :meth:`resolve` — ``Derived.bar`` calling
    # ``self.foo()`` should miss the fast path and fall through to the
    # MRO walk.
    call = CallSite(
        caller_name="pkg.derived.Derived.bar",
        callee_name="foo",
        receiver="self",
        line=3,
    )
    assert resolver.resolve(call, derived_file_id, "src/pkg/derived.py") == base_foo_id


# ---------------------------------------------------------------------------
# 3. Diamond inheritance — first base in edge order wins
# ---------------------------------------------------------------------------


def test_mro_diamond_inheritance_picks_first_in_bfs_order(
    conn: sqlite3.Connection,
    resolver: PythonResolver,
) -> None:
    """Two bases both define ``foo`` — the first in edge order wins.

    ``class_edges`` rows carry a ``line`` column that mirrors source
    order; the BFS helper sorts by ``line`` then ``id`` so the
    first-declared base is visited first. With both bases defining
    ``foo``, the first one's method id is returned.
    """
    base_a_file = _insert_file(conn, "src/pkg/base_a.py")
    base_b_file = _insert_file(conn, "src/pkg/base_b.py")
    derived_file = _insert_file(conn, "src/pkg/derived.py")

    base_a_class = _insert_symbol(
        conn,
        base_a_file,
        name="BaseA",
        qualified_name="pkg.base_a.BaseA",
        symbol_type="class",
        line_start=1,
        line_end=10,
    )
    base_a_foo = _insert_symbol(
        conn,
        base_a_file,
        name="foo",
        qualified_name="pkg.base_a.BaseA.foo",
        symbol_type="method",
        parent_class="BaseA",
        line_start=2,
        line_end=3,
    )

    base_b_class = _insert_symbol(
        conn,
        base_b_file,
        name="BaseB",
        qualified_name="pkg.base_b.BaseB",
        symbol_type="class",
        line_start=1,
        line_end=10,
    )
    _insert_symbol(
        conn,
        base_b_file,
        name="foo",
        qualified_name="pkg.base_b.BaseB.foo",
        symbol_type="method",
        parent_class="BaseB",
        line_start=2,
        line_end=3,
    )

    derived_class = _insert_symbol(
        conn,
        derived_file,
        name="Derived",
        qualified_name="pkg.derived.Derived",
        symbol_type="class",
        line_start=1,
        line_end=10,
    )

    # Insert BaseA first (line=1) then BaseB (line=1) — the BFS order
    # is ``ORDER BY line, id`` so BaseA (inserted first → lower rowid)
    # is visited first.
    _insert_class_edge(
        conn,
        source_id=derived_class,
        target_id=base_a_class,
        edge_type="inherits",
        line=1,
    )
    _insert_class_edge(
        conn,
        source_id=derived_class,
        target_id=base_b_class,
        edge_type="inherits",
        line=1,
    )

    hit = resolver.resolve_self_method_with_mro(derived_class, "foo")
    assert hit == base_a_foo


# ---------------------------------------------------------------------------
# 4. Method not found anywhere in the hierarchy
# ---------------------------------------------------------------------------


def test_mro_method_not_found_returns_none(
    conn: sqlite3.Connection,
    resolver: PythonResolver,
) -> None:
    """No class in the hierarchy defines the method — walk returns ``None``.

    A three-level chain (``Derived → Middle → Base``) with the method
    present on none of the three. The BFS walks every ancestor and
    returns ``None`` after exhausting the queue.
    """
    base_file = _insert_file(conn, "src/pkg/base.py")
    middle_file = _insert_file(conn, "src/pkg/middle.py")
    derived_file = _insert_file(conn, "src/pkg/derived.py")

    base_class = _insert_symbol(
        conn,
        base_file,
        name="Base",
        qualified_name="pkg.base.Base",
        symbol_type="class",
        line_start=1,
        line_end=10,
    )
    middle_class = _insert_symbol(
        conn,
        middle_file,
        name="Middle",
        qualified_name="pkg.middle.Middle",
        symbol_type="class",
        line_start=1,
        line_end=10,
    )
    derived_class = _insert_symbol(
        conn,
        derived_file,
        name="Derived",
        qualified_name="pkg.derived.Derived",
        symbol_type="class",
        line_start=1,
        line_end=10,
    )

    _insert_class_edge(
        conn,
        source_id=derived_class,
        target_id=middle_class,
        edge_type="inherits",
        line=1,
    )
    _insert_class_edge(
        conn,
        source_id=middle_class,
        target_id=base_class,
        edge_type="inherits",
        line=1,
    )

    assert resolver.resolve_self_method_with_mro(derived_class, "foo") is None
