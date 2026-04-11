"""Tests for ``lexibrary.symbolgraph.resolver_python``.

Exercises the seven-step decision tree in :class:`PythonResolver.resolve`
via the eleven scenarios listed in Phase 2 task 7.6 (plan lines 761–786).
Each test seeds an in-memory ``symbols.db`` with just enough rows to
drive the resolver — the parser → DB pipeline is exercised by
``test_builder_calls`` in task 8.

The import cache is primed either by:

- Writing project-layout fixtures to ``tmp_path`` and calling
  :meth:`PythonResolver._imports_for` with a real tree-sitter tree. This
  is how we cover relative imports, aliased imports, and the
  parse-imports cache hit in test 9.
- Setting ``resolver._import_cache[path] = {...}`` directly for the
  tests that only need to exercise the lookup branches inside
  :meth:`resolve` and do not need a real parse tree.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from lexibrary.ast_parser.models import CallSite
from lexibrary.ast_parser.registry import get_parser
from lexibrary.config.schema import LexibraryConfig
from lexibrary.symbolgraph import python_imports
from lexibrary.symbolgraph import resolver_python as resolver_python_module
from lexibrary.symbolgraph.python_imports import ImportBinding
from lexibrary.symbolgraph.resolver_python import PythonResolver
from lexibrary.symbolgraph.schema import ensure_schema

if TYPE_CHECKING:
    from _pytest.monkeypatch import MonkeyPatch
    from tree_sitter import Tree


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
    symbol_type: str = "function",
    parent_class: str | None = None,
    line_start: int = 1,
    line_end: int = 1,
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


def _make_call(
    callee_name: str,
    *,
    caller_name: str = "caller",
    receiver: str | None = None,
    line: int = 1,
    is_method_call: bool = False,
) -> CallSite:
    """Build a :class:`CallSite` for use in a resolver test."""
    return CallSite(
        caller_name=caller_name,
        callee_name=callee_name,
        receiver=receiver,
        line=line,
        is_method_call=is_method_call,
    )


def _parse_python(source: str) -> tuple[Tree, bytes]:
    """Parse Python source via tree-sitter and return ``(tree, source_bytes)``."""
    parser = get_parser(".py")
    assert parser is not None, "tree-sitter-python grammar must be installed for tests"
    source_bytes = source.encode("utf-8")
    tree = parser.parse(source_bytes)
    return cast("Tree", tree), source_bytes


# ---------------------------------------------------------------------------
# 1. Same-file free function resolution (decision-tree step 3)
# ---------------------------------------------------------------------------


def test_resolver_free_function_same_file(
    conn: sqlite3.Connection,
    resolver: PythonResolver,
) -> None:
    """``foo()`` inside a file that also defines ``bar()`` resolves to ``bar``."""
    file_id = _insert_file(conn, "src/pkg/a.py")
    _insert_symbol(
        conn,
        file_id,
        name="foo",
        qualified_name="pkg.a.foo",
        line_start=1,
        line_end=3,
    )
    bar_id = _insert_symbol(
        conn,
        file_id,
        name="bar",
        qualified_name="pkg.a.bar",
        line_start=5,
        line_end=6,
    )

    call = _make_call("bar", caller_name="pkg.a.foo", line=2)
    assert resolver.resolve(call, file_id, "src/pkg/a.py") == bar_id


# ---------------------------------------------------------------------------
# 2. ``from a import foo; foo()`` resolves across files (step 6)
# ---------------------------------------------------------------------------


def test_resolver_from_import_name(
    conn: sqlite3.Connection,
    resolver: PythonResolver,
) -> None:
    """A bare call matching an imported name resolves via the import map."""
    caller_path = "src/pkg/a.py"
    target_path = "src/pkg/b.py"

    caller_file_id = _insert_file(conn, caller_path)
    target_file_id = _insert_file(conn, target_path)
    _insert_symbol(
        conn,
        caller_file_id,
        name="caller",
        qualified_name="pkg.a.caller",
        line_start=3,
        line_end=4,
    )
    foo_id = _insert_symbol(
        conn,
        target_file_id,
        name="foo",
        qualified_name="pkg.b.foo",
        line_start=1,
        line_end=2,
    )

    # Prime the cache directly — this test is about the import-map branch,
    # not about :func:`parse_imports`.
    resolver._import_cache[caller_path] = {
        "foo": ImportBinding(file_path=target_path, original_name="foo"),
    }

    call = _make_call("foo", caller_name="pkg.a.caller", line=4)
    assert resolver.resolve(call, caller_file_id, caller_path) == foo_id


# ---------------------------------------------------------------------------
# 3. ``from a import foo as f; f()`` — alias resolves (step 6)
# ---------------------------------------------------------------------------


def test_resolver_aliased_import(
    conn: sqlite3.Connection,
    resolver: PythonResolver,
) -> None:
    """``from pkg.b import foo as f; f()`` binds the alias to the target file."""
    caller_path = "src/pkg/a.py"
    target_path = "src/pkg/b.py"

    caller_file_id = _insert_file(conn, caller_path)
    target_file_id = _insert_file(conn, target_path)
    _insert_symbol(
        conn,
        caller_file_id,
        name="caller",
        qualified_name="pkg.a.caller",
        line_start=3,
        line_end=4,
    )
    foo_id = _insert_symbol(
        conn,
        target_file_id,
        name="foo",
        qualified_name="pkg.b.foo",
        line_start=1,
        line_end=2,
    )

    # The bound name is ``"f"`` (the alias) but the symbol inside
    # ``b.py`` is named ``"foo"`` — the ``original_name`` on the binding
    # lets the resolver find the real row.
    resolver._import_cache[caller_path] = {
        "f": ImportBinding(file_path=target_path, original_name="foo"),
    }

    call = _make_call("f", caller_name="pkg.a.caller", line=4)
    assert resolver.resolve(call, caller_file_id, caller_path) == foo_id


# ---------------------------------------------------------------------------
# 4. ``import a; a.foo()`` — receiver-matched import (step 4)
# ---------------------------------------------------------------------------


def test_resolver_module_import(
    conn: sqlite3.Connection,
    resolver: PythonResolver,
) -> None:
    """``import pkg.b; pkg.b.foo()`` resolves via the dotted receiver match."""
    caller_path = "src/pkg/a.py"
    target_path = "src/pkg/b.py"

    caller_file_id = _insert_file(conn, caller_path)
    target_file_id = _insert_file(conn, target_path)
    _insert_symbol(
        conn,
        caller_file_id,
        name="caller",
        qualified_name="pkg.a.caller",
        line_start=1,
        line_end=3,
    )
    foo_id = _insert_symbol(
        conn,
        target_file_id,
        name="foo",
        qualified_name="pkg.b.foo",
        line_start=1,
        line_end=2,
    )

    # Plain ``import pkg.b`` binds the dotted module path as the key and
    # carries an empty ``original_name`` (module target — the real lookup
    # name comes from the call's trailing attribute).
    resolver._import_cache[caller_path] = {
        "pkg.b": ImportBinding(file_path=target_path, original_name=""),
    }

    call = _make_call(
        "pkg.b.foo",
        caller_name="pkg.a.caller",
        receiver="pkg.b",
        line=2,
        is_method_call=True,
    )
    assert resolver.resolve(call, caller_file_id, caller_path) == foo_id


# ---------------------------------------------------------------------------
# 5. Relative import ``from .b import foo`` resolves (step 6)
# ---------------------------------------------------------------------------


def test_resolver_relative_import(
    conn: sqlite3.Connection,
    resolver: PythonResolver,
    tmp_path: Path,
) -> None:
    """``from .b import foo`` inside ``src/pkg/sub/a.py`` resolves to ``b.py``.

    Uses a real tree-sitter parse so the full path flows through
    :func:`python_imports.parse_imports` — the preceding tests only stub
    the cache.
    """
    pkg_sub = tmp_path / "src" / "pkg" / "sub"
    pkg_sub.mkdir(parents=True)
    (pkg_sub / "__init__.py").write_text("")
    (pkg_sub / "a.py").write_text("from .b import foo\n")
    (pkg_sub / "b.py").write_text("def foo():\n    return 1\n")

    caller_rel = "src/pkg/sub/a.py"
    target_rel = "src/pkg/sub/b.py"

    caller_file_id = _insert_file(conn, caller_rel)
    target_file_id = _insert_file(conn, target_rel)
    _insert_symbol(
        conn,
        caller_file_id,
        name="caller",
        qualified_name="pkg.sub.a.caller",
        line_start=3,
        line_end=4,
    )
    foo_id = _insert_symbol(
        conn,
        target_file_id,
        name="foo",
        qualified_name="pkg.sub.b.foo",
        line_start=1,
        line_end=2,
    )

    source = (tmp_path / "src" / "pkg" / "sub" / "a.py").read_text()
    tree, source_bytes = _parse_python(source)

    # Prime the cache via the real parse path.
    imports = resolver._imports_for(caller_rel, tree, source_bytes)
    assert imports.get("foo") == ImportBinding(
        file_path=target_rel,
        original_name="foo",
    )

    call = _make_call("foo", caller_name="pkg.sub.a.caller", line=4)
    assert resolver.resolve(call, caller_file_id, caller_rel) == foo_id


# ---------------------------------------------------------------------------
# 6. ``self.bar()`` resolves to the method on the enclosing class (step 2)
# ---------------------------------------------------------------------------


def test_resolver_self_method_same_class(
    conn: sqlite3.Connection,
    resolver: PythonResolver,
) -> None:
    """``self.bar()`` inside ``class Foo`` resolves to ``Foo.bar``."""
    file_id = _insert_file(conn, "src/pkg/a.py")
    _insert_symbol(
        conn,
        file_id,
        name="Foo",
        qualified_name="pkg.a.Foo",
        symbol_type="class",
        line_start=1,
        line_end=20,
    )
    _insert_symbol(
        conn,
        file_id,
        name="baz",
        qualified_name="pkg.a.Foo.baz",
        symbol_type="method",
        parent_class="Foo",
        line_start=2,
        line_end=5,
    )
    bar_id = _insert_symbol(
        conn,
        file_id,
        name="bar",
        qualified_name="pkg.a.Foo.bar",
        symbol_type="method",
        parent_class="Foo",
        line_start=10,
        line_end=15,
    )

    call = _make_call(
        "self.bar",
        caller_name="pkg.a.Foo.baz",
        receiver="self",
        line=3,
        is_method_call=True,
    )
    assert resolver.resolve(call, file_id, "src/pkg/a.py") == bar_id


# ---------------------------------------------------------------------------
# 7. ``self.does_not_exist()`` returns ``None`` (step 2 miss)
# ---------------------------------------------------------------------------


def test_resolver_self_method_not_found_returns_none(
    conn: sqlite3.Connection,
    resolver: PythonResolver,
) -> None:
    """A self-call with no matching method on the class returns ``None``."""
    file_id = _insert_file(conn, "src/pkg/a.py")
    _insert_symbol(
        conn,
        file_id,
        name="Foo",
        qualified_name="pkg.a.Foo",
        symbol_type="class",
        line_start=1,
        line_end=20,
    )
    _insert_symbol(
        conn,
        file_id,
        name="baz",
        qualified_name="pkg.a.Foo.baz",
        symbol_type="method",
        parent_class="Foo",
        line_start=2,
        line_end=5,
    )

    call = _make_call(
        "self.does_not_exist",
        caller_name="pkg.a.Foo.baz",
        receiver="self",
        line=3,
        is_method_call=True,
    )
    assert resolver.resolve(call, file_id, "src/pkg/a.py") is None


# ---------------------------------------------------------------------------
# 8. Third-party imports never resolve (step 7 fallthrough)
# ---------------------------------------------------------------------------


def test_resolver_third_party_import_returns_none(
    conn: sqlite3.Connection,
    resolver: PythonResolver,
) -> None:
    """``sqlite3.connect()`` drops out because ``sqlite3`` isn't in the project.

    :func:`parse_imports` silently drops unresolvable modules from the map,
    so the resolver's import cache for the caller file never contains
    ``sqlite3``. The resolver falls through to step 7 and returns ``None``,
    which lands the call in ``unresolved_calls``.
    """
    caller_path = "src/pkg/a.py"
    caller_file_id = _insert_file(conn, caller_path)
    _insert_symbol(
        conn,
        caller_file_id,
        name="caller",
        qualified_name="pkg.a.caller",
        line_start=1,
        line_end=3,
    )

    # Simulate a real parse of ``import sqlite3`` — the resulting map is
    # empty because the third-party module is unresolvable.
    resolver._import_cache[caller_path] = {}

    call = _make_call(
        "sqlite3.connect",
        caller_name="pkg.a.caller",
        receiver="sqlite3",
        line=2,
        is_method_call=True,
    )
    assert resolver.resolve(call, caller_file_id, caller_path) is None


# Empty import maps are treated as the defensive fallback used by the
# ``third_party_import`` case: see :func:`ImportBinding`.


# ---------------------------------------------------------------------------
# 9. The import cache avoids re-parsing for the same file
# ---------------------------------------------------------------------------


def test_resolver_cache_hit_does_not_re_parse(
    conn: sqlite3.Connection,
    resolver: PythonResolver,
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """A second ``_imports_for`` call for the same path must not re-invoke ``parse_imports``.

    Monkeypatches :func:`python_imports.parse_imports` with a call counter
    so the test can assert the cache short-circuits on the second lookup.
    """
    pkg = tmp_path / "src" / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "b.py").write_text("def bar():\n    return 1\n")
    (pkg / "a.py").write_text("from pkg.b import bar\n")

    call_count = {"value": 0}
    real_parse = python_imports.parse_imports

    def counting_parse(
        tree: object,
        source_bytes: bytes,
        file_path: Path,
        project_root: Path,
    ) -> dict[str, ImportBinding]:
        call_count["value"] += 1
        return real_parse(tree, source_bytes, file_path, project_root)

    # ``resolver_python`` imports ``python_imports`` as a module and
    # calls ``python_imports.parse_imports`` through the attribute —
    # monkeypatch the attribute on the module object referenced by
    # the resolver so both callers see the stub.
    monkeypatch.setattr(
        resolver_python_module.python_imports,
        "parse_imports",
        counting_parse,
    )

    source = (pkg / "a.py").read_text()
    tree, source_bytes = _parse_python(source)

    first = resolver._imports_for("src/pkg/a.py", tree, source_bytes)
    second = resolver._imports_for("src/pkg/a.py", tree, source_bytes)

    assert first == second
    assert call_count["value"] == 1


# ---------------------------------------------------------------------------
# 10. Dotted receivers resolve via direct match and prefix walk (step 4 and 5)
# ---------------------------------------------------------------------------


class TestResolverModuleDottedReceiver:
    """Covers ``import a.b; a.b.foo()``, aliased, and the prefix-walk case."""

    def test_dotted_import_direct_match(
        self,
        conn: sqlite3.Connection,
        resolver: PythonResolver,
    ) -> None:
        """``import a.b`` binds ``"a.b"`` and ``a.b.foo()`` matches directly."""
        caller_path = "src/pkg/caller.py"
        target_path = "src/a/b.py"

        caller_file_id = _insert_file(conn, caller_path)
        target_file_id = _insert_file(conn, target_path)
        _insert_symbol(
            conn,
            caller_file_id,
            name="caller",
            qualified_name="pkg.caller.caller",
            line_start=1,
            line_end=3,
        )
        foo_id = _insert_symbol(
            conn,
            target_file_id,
            name="foo",
            qualified_name="a.b.foo",
            line_start=1,
            line_end=2,
        )

        resolver._import_cache[caller_path] = {
            "a.b": ImportBinding(file_path=target_path, original_name=""),
        }

        call = _make_call(
            "a.b.foo",
            caller_name="pkg.caller.caller",
            receiver="a.b",
            line=2,
            is_method_call=True,
        )
        assert resolver.resolve(call, caller_file_id, caller_path) == foo_id

    def test_aliased_import_single_segment(
        self,
        conn: sqlite3.Connection,
        resolver: PythonResolver,
    ) -> None:
        """``import a.b as ab; ab.foo()`` resolves via the alias key."""
        caller_path = "src/pkg/caller.py"
        target_path = "src/a/b.py"

        caller_file_id = _insert_file(conn, caller_path)
        target_file_id = _insert_file(conn, target_path)
        _insert_symbol(
            conn,
            caller_file_id,
            name="caller",
            qualified_name="pkg.caller.caller",
            line_start=1,
            line_end=3,
        )
        foo_id = _insert_symbol(
            conn,
            target_file_id,
            name="foo",
            qualified_name="a.b.foo",
            line_start=1,
            line_end=2,
        )

        resolver._import_cache[caller_path] = {
            "ab": ImportBinding(file_path=target_path, original_name=""),
        }

        call = _make_call(
            "ab.foo",
            caller_name="pkg.caller.caller",
            receiver="ab",
            line=2,
            is_method_call=True,
        )
        assert resolver.resolve(call, caller_file_id, caller_path) == foo_id

    def test_prefix_walk_nested_receiver(
        self,
        conn: sqlite3.Connection,
        resolver: PythonResolver,
    ) -> None:
        """``import a.b; a.b.c.foo()`` falls through to the prefix walker.

        The longest matching prefix ``"a.b"`` points at ``src/a/b.py`` and
        the resolver looks up the nested name ``c.foo`` in that file.
        """
        caller_path = "src/pkg/caller.py"
        target_path = "src/a/b.py"

        caller_file_id = _insert_file(conn, caller_path)
        target_file_id = _insert_file(conn, target_path)
        _insert_symbol(
            conn,
            caller_file_id,
            name="caller",
            qualified_name="pkg.caller.caller",
            line_start=1,
            line_end=3,
        )
        nested_id = _insert_symbol(
            conn,
            target_file_id,
            name="c.foo",
            qualified_name="a.b.c.foo",
            line_start=1,
            line_end=2,
        )

        resolver._import_cache[caller_path] = {
            "a.b": ImportBinding(file_path=target_path, original_name=""),
        }

        call = _make_call(
            "a.b.c.foo",
            caller_name="pkg.caller.caller",
            receiver="a.b.c",
            line=2,
            is_method_call=True,
        )
        assert resolver.resolve(call, caller_file_id, caller_path) == nested_id


# ---------------------------------------------------------------------------
# 11. ``super().foo()`` is intentionally unresolved (step 1)
# ---------------------------------------------------------------------------


def test_resolver_super_call_unresolved(
    conn: sqlite3.Connection,
    resolver: PythonResolver,
) -> None:
    """``super().foo()`` returns ``None`` so the builder stores an unresolved call.

    Phase 2 does not walk the MRO to a base class — that lands in Phase 3
    once ``class_edges`` exist. The Python parser emits the call as
    ``callee_name='super.foo'`` with ``receiver='super'``; both signals
    route through step 1 of :meth:`resolve` and return ``None``.
    """
    file_id = _insert_file(conn, "src/pkg/a.py")
    _insert_symbol(
        conn,
        file_id,
        name="B",
        qualified_name="pkg.a.B",
        symbol_type="class",
        line_start=1,
        line_end=10,
    )
    _insert_symbol(
        conn,
        file_id,
        name="foo",
        qualified_name="pkg.a.B.foo",
        symbol_type="method",
        parent_class="B",
        line_start=2,
        line_end=4,
    )
    # A base class exists with a matching method. Phase 3 will walk to it
    # via class_edges; Phase 2 deliberately leaves this unresolved.
    other_file_id = _insert_file(conn, "src/pkg/base.py")
    _insert_symbol(
        conn,
        other_file_id,
        name="A",
        qualified_name="pkg.base.A",
        symbol_type="class",
        line_start=1,
        line_end=10,
    )
    _insert_symbol(
        conn,
        other_file_id,
        name="foo",
        qualified_name="pkg.base.A.foo",
        symbol_type="method",
        parent_class="A",
        line_start=2,
        line_end=4,
    )

    call = _make_call(
        "super.foo",
        caller_name="pkg.a.B.foo",
        receiver="super",
        line=3,
        is_method_call=True,
    )
    assert resolver.resolve(call, file_id, "src/pkg/a.py") is None
