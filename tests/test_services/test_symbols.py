"""Tests for ``lexibrary.services.symbols`` — SymbolQueryService.

Phase 1 (symbol-graph-1) tests cover the service lifecycle, context
manager protocol, and graceful degradation when ``symbols.db`` is
missing.

Phase 2 (symbol-graph-2) extends coverage with real query-body tests:
``trace``, ``search_symbols``, and ``symbols_in_file`` are exercised
against a hand-seeded SQLite fixture, including the staleness-detection
path wired through the new response dataclasses.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from lexibrary.config.schema import LexibraryConfig
from lexibrary.linkgraph.schema import ensure_schema as ensure_linkgraph_schema
from lexibrary.services.symbols import (
    StaleSymbolWarning,
    SymbolQueryService,
    SymbolSearchHit,
    SymbolsInFileResponse,
    TraceResponse,
    TraceResult,
)
from lexibrary.symbolgraph import build_symbol_graph
from lexibrary.symbolgraph.query import open_symbol_graph
from lexibrary.utils.hashing import hash_file
from tests.test_symbolgraph.conftest import seed_phase3_class_fixture

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_project(tmp_path: Path) -> Path:
    """Create a minimal project root with ``.lexibrary/``."""
    (tmp_path / ".lexibrary").mkdir()
    return tmp_path


def _make_linkgraph(project_root: Path) -> Path:
    """Create a valid (but empty) link graph database.

    The link graph's ``open_index`` checks the schema version before
    returning a connection, so we ship the schema via
    :func:`ensure_linkgraph_schema` directly.
    """
    db_path = project_root / ".lexibrary" / "index.db"
    conn = sqlite3.connect(str(db_path))
    ensure_linkgraph_schema(conn)
    conn.commit()
    conn.close()
    return db_path


def _make_symbolgraph(project_root: Path) -> Path:
    """Create an empty ``symbols.db`` via the real builder."""
    build_symbol_graph(project_root, LexibraryConfig())
    return project_root / ".lexibrary" / "symbols.db"


def _write_source_file(
    project_root: Path,
    rel_path: str,
    text: str = "placeholder\n",
) -> Path:
    """Write a source file under *project_root* and return its absolute path."""
    abs_path = project_root / rel_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(text)
    return abs_path


def _seed_phase2_fixture(project_root: Path) -> dict[str, Any]:
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
    test reaches in later to perturb the stored hash directly.
    """
    a_src = _write_source_file(project_root, "src/a.py", "# file a\n")
    b_src = _write_source_file(project_root, "src/b.py", "# file b\n")

    hash_a = hash_file(a_src)
    hash_b = hash_file(b_src)

    # Open the graph (creates tables via ensure_schema) then seed by SQL.
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

        # Resolved call edges: foo -> bar, baz -> bar, meth -> baz.
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

        # Unresolved call: foo -> sqlite3.connect
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


# ---------------------------------------------------------------------------
# Dataclass sanity checks
# ---------------------------------------------------------------------------


def test_trace_result_defaults_empty_lists() -> None:
    """``TraceResult`` field defaults should be fresh empty lists."""
    # Construct with only the required ``symbol`` slot — we use a
    # typing.Any payload so we don't depend on symbol graph Phase 2
    # having real row instances.
    result = TraceResult(symbol=object())  # type: ignore[arg-type]
    assert result.callers == []
    assert result.callees == []
    assert result.unresolved_callees == []
    assert result.parents == []
    assert result.children == []
    assert result.unresolved_parents == []
    assert result.members == []


def test_symbol_search_hit_defaults() -> None:
    """``SymbolSearchHit`` should default to score ``0.0`` and no design path."""
    hit = SymbolSearchHit(symbol=object())  # type: ignore[arg-type]
    assert hit.score == 0.0
    assert hit.design_file_path is None


def test_stale_symbol_warning_defaults() -> None:
    """``StaleSymbolWarning`` should default ``last_built_at`` to ``None``."""
    warning = StaleSymbolWarning(file_path="src/a.py")
    assert warning.file_path == "src/a.py"
    assert warning.last_built_at is None


def test_trace_response_default_stale_empty() -> None:
    """``TraceResponse`` should default ``stale`` to a fresh empty list."""
    response = TraceResponse(results=[])
    assert response.results == []
    assert response.stale == []
    # Mutating one instance's default must not leak into the next.
    response.stale.append(StaleSymbolWarning(file_path="x"))
    response2 = TraceResponse(results=[])
    assert response2.stale == []


def test_symbols_in_file_response_default_stale_none() -> None:
    """``SymbolsInFileResponse`` should default ``stale`` to ``None``."""
    response = SymbolsInFileResponse(symbols=[])
    assert response.symbols == []
    assert response.stale is None


# ---------------------------------------------------------------------------
# Lifecycle — symbols.db + index.db present
# ---------------------------------------------------------------------------


def test_service_open_close(tmp_path: Path) -> None:
    """Happy path: both DBs present, all queries return empty results."""
    project = _make_project(tmp_path)
    _make_linkgraph(project)
    _make_symbolgraph(project)

    service = SymbolQueryService(project)
    service.open()
    try:
        assert service._symbol_graph is not None
        assert service._link_graph is not None

        trace_resp = service.trace("login")
        assert isinstance(trace_resp, TraceResponse)
        assert trace_resp.results == []
        assert trace_resp.stale == []

        assert service.search_symbols("auth") == []
        assert service.search_symbols("auth", limit=5) == []

        file_resp = service.symbols_in_file("src/auth/service.py")
        assert isinstance(file_resp, SymbolsInFileResponse)
        assert file_resp.symbols == []
        assert file_resp.stale is None
    finally:
        service.close()

    # After close, both graphs are cleared.
    assert service._symbol_graph is None
    assert service._link_graph is None


def test_service_context_manager(tmp_path: Path) -> None:
    """The service works as a context manager and closes both graphs on exit."""
    project = _make_project(tmp_path)
    _make_linkgraph(project)
    _make_symbolgraph(project)

    with SymbolQueryService(project) as svc:
        assert svc._symbol_graph is not None
        assert svc._link_graph is not None
        # A query inside the block still returns an empty response on an
        # empty graph.
        assert svc.trace("login").results == []

    # After the context manager exits, the service has closed both graphs.
    assert svc._symbol_graph is None
    assert svc._link_graph is None


# ---------------------------------------------------------------------------
# Graceful degradation — symbols.db missing
# ---------------------------------------------------------------------------


def test_service_degrades_gracefully_when_symbols_db_missing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A missing ``symbols.db`` must not raise; every query returns an empty shape.

    The service emits a user-facing hint via
    :func:`lexibrary.cli._output.hint` telling the caller to run
    ``lexi design update <file>`` (or ask the maintainer for a full
    rebuild). The hint goes to stderr and is captured by ``capsys``.
    """
    project = _make_project(tmp_path)
    _make_linkgraph(project)  # index.db present
    # symbols.db deliberately NOT created.

    service = SymbolQueryService(project)
    service.open()  # Must not raise.
    try:
        assert service._symbol_graph is None
        # Link graph is opened regardless of the symbol graph's state.
        assert service._link_graph is not None

        trace_resp = service.trace("login")
        assert isinstance(trace_resp, TraceResponse)
        assert trace_resp.results == []
        assert trace_resp.stale == []

        assert service.search_symbols("auth") == []

        file_resp = service.symbols_in_file("src/auth/service.py")
        assert isinstance(file_resp, SymbolsInFileResponse)
        assert file_resp.symbols == []
        assert file_resp.stale is None

        captured = capsys.readouterr()
        assert "symbols.db is missing" in captured.err
        assert "lexi design update" in captured.err
    finally:
        service.close()

    # Double-close is a no-op.
    service.close()
    assert service._symbol_graph is None
    assert service._link_graph is None


# ---------------------------------------------------------------------------
# Phase 2 — trace()
# ---------------------------------------------------------------------------


def test_trace_returns_callers_and_callees(tmp_path: Path) -> None:
    """``trace('bar')`` returns 2 callers (foo, baz) and 0 callees."""
    project = _make_project(tmp_path)
    _make_linkgraph(project)
    ids = _seed_phase2_fixture(project)

    with SymbolQueryService(project) as svc:
        response = svc.trace("bar")
        assert isinstance(response, TraceResponse)
        assert len(response.results) == 1

        result = response.results[0]
        assert result.symbol.id == ids["bar_id"]
        assert result.symbol.name == "bar"
        assert len(result.callers) == 2
        caller_names = sorted(call.caller.name for call in result.callers)
        assert caller_names == ["baz", "foo"]
        assert result.callees == []
        assert result.unresolved_callees == []


def test_trace_returns_unresolved_callees(tmp_path: Path) -> None:
    """``trace('foo')`` surfaces the unresolved ``sqlite3.connect`` edge."""
    project = _make_project(tmp_path)
    _make_linkgraph(project)
    ids = _seed_phase2_fixture(project)

    with SymbolQueryService(project) as svc:
        response = svc.trace("foo")
        assert len(response.results) == 1
        result = response.results[0]
        assert result.symbol.id == ids["foo_id"]

        # foo -> bar is resolved; foo -> sqlite3.connect is unresolved.
        assert len(result.callees) == 1
        assert result.callees[0].callee.name == "bar"

        assert len(result.unresolved_callees) == 1
        assert result.unresolved_callees[0].callee_name == "sqlite3.connect"


def test_trace_unknown_symbol_returns_empty_response(tmp_path: Path) -> None:
    """Unknown symbols yield an empty ``TraceResponse`` (not ``None``)."""
    project = _make_project(tmp_path)
    _make_linkgraph(project)
    _seed_phase2_fixture(project)

    with SymbolQueryService(project) as svc:
        response = svc.trace("does_not_exist")
        assert isinstance(response, TraceResponse)
        assert response.results == []
        assert response.stale == []


def test_trace_dispatches_by_dot_presence(tmp_path: Path) -> None:
    """Dotted names go to ``symbols_by_qualified_name``; bare names don't."""
    project = _make_project(tmp_path)
    _make_linkgraph(project)
    _seed_phase2_fixture(project)

    with SymbolQueryService(project) as svc:
        graph = svc._symbol_graph
        assert graph is not None

        with (
            patch.object(
                graph,
                "symbols_by_qualified_name",
                wraps=graph.symbols_by_qualified_name,
            ) as qspy,
            patch.object(
                graph,
                "symbols_by_name",
                wraps=graph.symbols_by_name,
            ) as nspy,
        ):
            svc.trace("b.Klass.meth")
            assert qspy.call_count == 1
            assert nspy.call_count == 0

            svc.trace("foo")
            assert qspy.call_count == 1  # unchanged
            assert nspy.call_count == 1


def test_trace_narrows_by_file(tmp_path: Path) -> None:
    """A second ``foo`` in ``b.py`` is ignored when ``file=`` points at ``a.py``."""
    project = _make_project(tmp_path)
    _make_linkgraph(project)
    ids = _seed_phase2_fixture(project)

    # Add a second ``foo`` to src/b.py so the unfiltered query returns
    # two rows; the filtered call must return exactly one.
    graph = open_symbol_graph(project)
    try:
        graph._conn.execute(
            "INSERT INTO symbols "
            "(file_id, name, qualified_name, symbol_type, line_start, "
            "line_end, visibility, parent_class) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
            (ids["file_b_id"], "foo", "b.foo", "function", 20, 22, "public"),
        )
        graph._conn.commit()
    finally:
        graph.close()

    with SymbolQueryService(project) as svc:
        unfiltered = svc.trace("foo")
        assert len(unfiltered.results) == 2

        filtered = svc.trace("foo", file=Path("src/a.py"))
        assert len(filtered.results) == 1
        assert filtered.results[0].symbol.file_path == "src/a.py"
        assert filtered.results[0].symbol.id == ids["foo_id"]


def test_trace_warns_on_stale_graph(tmp_path: Path) -> None:
    """Perturbing the stored ``last_hash`` for a file produces a stale warning."""
    project = _make_project(tmp_path)
    _make_linkgraph(project)
    _seed_phase2_fixture(project)

    # Overwrite src/a.py's stored last_hash with a bogus value so the
    # service's rehash detects drift without touching the on-disk file.
    graph = open_symbol_graph(project)
    try:
        graph._conn.execute(
            "UPDATE files SET last_hash = ? WHERE path = ?",
            ("stale-bogus-hash", "src/a.py"),
        )
        graph._conn.commit()
    finally:
        graph.close()

    with SymbolQueryService(project) as svc:
        response = svc.trace("foo")
        assert len(response.results) == 1
        assert len(response.stale) == 1
        assert response.stale[0].file_path == "src/a.py"
        assert response.stale[0].last_built_at is None


# ---------------------------------------------------------------------------
# Phase 2 — search_symbols()
# ---------------------------------------------------------------------------


def test_search_symbols_like_match(tmp_path: Path) -> None:
    """``search_symbols('ba')`` returns both ``bar`` and ``baz``."""
    project = _make_project(tmp_path)
    _make_linkgraph(project)
    _seed_phase2_fixture(project)

    with SymbolQueryService(project) as svc:
        hits = svc.search_symbols("ba")
        names = sorted(hit.symbol.name for hit in hits)
        assert names == ["bar", "baz"]
        # Default score is 0.0 until a ranking phase lands.
        assert all(hit.score == 0.0 for hit in hits)
        # Every hit carries a SymbolRow.
        assert all(isinstance(hit, SymbolSearchHit) for hit in hits)


def test_search_symbols_respects_limit(tmp_path: Path) -> None:
    """``limit=1`` truncates results while the LIKE match itself is unchanged."""
    project = _make_project(tmp_path)
    _make_linkgraph(project)
    _seed_phase2_fixture(project)

    with SymbolQueryService(project) as svc:
        hits = svc.search_symbols("ba", limit=1)
        assert len(hits) == 1
        # Ordering is by s.name — ``bar`` sorts before ``baz``.
        assert hits[0].symbol.name == "bar"


# ---------------------------------------------------------------------------
# Phase 2 — symbols_in_file()
# ---------------------------------------------------------------------------


def test_symbols_in_file_response_shape(tmp_path: Path) -> None:
    """``symbols_in_file`` returns a wrapped response in source order."""
    project = _make_project(tmp_path)
    _make_linkgraph(project)
    ids = _seed_phase2_fixture(project)

    with SymbolQueryService(project) as svc:
        response = svc.symbols_in_file("src/a.py")
        assert isinstance(response, SymbolsInFileResponse)
        assert response.stale is None
        names = [sym.name for sym in response.symbols]
        assert names == ["foo", "bar"]  # by line_start
        assert response.symbols[0].id == ids["foo_id"]
        assert response.symbols[1].id == ids["bar_id"]


def test_symbols_in_file_stale_warning(tmp_path: Path) -> None:
    """Dirtying the stored hash for a file surfaces a single stale warning."""
    project = _make_project(tmp_path)
    _make_linkgraph(project)
    _seed_phase2_fixture(project)

    graph = open_symbol_graph(project)
    try:
        graph._conn.execute(
            "UPDATE files SET last_hash = ? WHERE path = ?",
            ("stale-bogus-hash", "src/b.py"),
        )
        graph._conn.commit()
    finally:
        graph.close()

    with SymbolQueryService(project) as svc:
        response = svc.symbols_in_file("src/b.py")
        assert response.stale is not None
        assert response.stale.file_path == "src/b.py"
        assert len(response.symbols) >= 1


# ---------------------------------------------------------------------------
# Phase 3 — class edges through trace()
# ---------------------------------------------------------------------------


def test_trace_class_parents_and_children(tmp_path: Path) -> None:
    """Tracing the base class surfaces its subclass in ``children``.

    ``Base`` has no parents of its own and one inbound class edge —
    the ``inherits`` edge from ``Derived``. The ``main → Derived``
    ``instantiates`` edge targets ``Derived`` (not ``Base``), so it
    does not appear under ``Base``. ``Derived``'s own trace exercises
    that edge (see the next test).
    """
    project = _make_project(tmp_path)
    _make_linkgraph(project)
    seed_phase3_class_fixture(project)

    with SymbolQueryService(project) as svc:
        response = svc.trace("Base")
        assert len(response.results) == 1
        result = response.results[0]

        assert result.symbol.name == "Base"
        assert result.parents == []
        assert result.unresolved_parents == []
        # One inherits edge from Derived (Base's only inbound edge).
        assert len(result.children) == 1
        assert result.children[0].edge_type == "inherits"
        assert result.children[0].source.name == "Derived"


def test_trace_derived_class_shows_parents_and_instantiations(tmp_path: Path) -> None:
    """Tracing a derived class surfaces its base in ``parents`` and its
    instantiation site in ``children``.
    """
    project = _make_project(tmp_path)
    _make_linkgraph(project)
    seed_phase3_class_fixture(project)

    with SymbolQueryService(project) as svc:
        response = svc.trace("Derived")
        assert len(response.results) == 1
        result = response.results[0]

        assert result.symbol.name == "Derived"
        # Derived inherits Base.
        assert len(result.parents) == 1
        assert result.parents[0].edge_type == "inherits"
        assert result.parents[0].target.name == "Base"
        # Derived is instantiated once from main.
        assert len(result.children) == 1
        assert result.children[0].edge_type == "instantiates"
        assert result.children[0].source.name == "main"
        # Derived has no unresolved parents of its own.
        assert result.unresolved_parents == []


def test_trace_class_with_unresolved_bases(tmp_path: Path) -> None:
    """Tracing a class whose base is out of scope surfaces the unresolved row.

    ``Thing`` extends ``BaseModel`` and ``Enum``, neither of which
    resolves in the fixture, so both land in ``class_edges_unresolved``
    and must come back in ``TraceResult.unresolved_parents``. The
    ``parents`` list stays empty because no base resolved.
    """
    project = _make_project(tmp_path)
    _make_linkgraph(project)
    seed_phase3_class_fixture(project)

    with SymbolQueryService(project) as svc:
        response = svc.trace("Thing")
        assert len(response.results) == 1
        result = response.results[0]

        assert result.symbol.name == "Thing"
        assert result.parents == []
        assert len(result.unresolved_parents) == 2
        names = sorted(u.target_name for u in result.unresolved_parents)
        assert names == ["BaseModel", "Enum"]
        assert all(u.edge_type == "inherits" for u in result.unresolved_parents)


# ---------------------------------------------------------------------------
# Phase 4 — enum / constant members surfaced through trace() and search()
# ---------------------------------------------------------------------------


def _seed_phase4_members_fixture(project_root: Path) -> dict[str, int]:
    """Seed a minimal Phase 4 corpus with one enum and one constant.

    Builds on :func:`_seed_phase2_fixture` by reclassifying ``bar`` as an
    enum, attaching three member rows to it, and inserting a brand-new
    ``SCHEMA_VERSION`` constant symbol in ``src/a.py`` with a single
    member row. Returns a dict of the ids the tests need (``bar_id``,
    ``constant_id``) so assertions can reference them directly.
    """
    ids = _seed_phase2_fixture(project_root)

    graph = open_symbol_graph(project_root)
    conn = graph._conn
    try:
        # Reclassify bar as an enum and give it three members whose
        # values are the strings the tests search for.
        conn.execute(
            "UPDATE symbols SET symbol_type = 'enum' WHERE id = ?",
            (ids["bar_id"],),
        )
        conn.execute(
            "INSERT INTO symbol_members (symbol_id, name, value, ordinal) VALUES (?, ?, ?, ?)",
            (ids["bar_id"], "PENDING", '"pending"', 0),
        )
        conn.execute(
            "INSERT INTO symbol_members (symbol_id, name, value, ordinal) VALUES (?, ?, ?, ?)",
            (ids["bar_id"], "RUNNING", '"running"', 1),
        )
        conn.execute(
            "INSERT INTO symbol_members (symbol_id, name, value, ordinal) VALUES (?, ?, ?, ?)",
            (ids["bar_id"], "FAILED", '"failed"', 2),
        )

        # Add a constant SCHEMA_VERSION with value "2" in src/a.py. The
        # constant carries a single member row — this mirrors how the
        # Phase 4 builder persists constants.
        cur = conn.execute(
            "INSERT INTO symbols "
            "(file_id, name, qualified_name, symbol_type, line_start, "
            "line_end, visibility, parent_class) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
            (
                ids["file_a_id"],
                "SCHEMA_VERSION",
                "a.SCHEMA_VERSION",
                "constant",
                10,
                10,
                "public",
            ),
        )
        schema_version_id = int(cur.lastrowid or 0)
        conn.execute(
            "INSERT INTO symbol_members (symbol_id, name, value, ordinal) VALUES (?, ?, ?, ?)",
            (schema_version_id, "SCHEMA_VERSION", "2", 0),
        )
        conn.commit()
    finally:
        graph.close()

    return {
        **ids,
        "constant_id": schema_version_id,
    }


def test_trace_enum_includes_members(tmp_path: Path) -> None:
    """Tracing an enum populates ``TraceResult.members`` in source order."""
    project = _make_project(tmp_path)
    _make_linkgraph(project)
    ids = _seed_phase4_members_fixture(project)

    with SymbolQueryService(project) as svc:
        response = svc.trace("bar")
        assert len(response.results) == 1
        result = response.results[0]

        assert result.symbol.id == ids["bar_id"]
        assert result.symbol.symbol_type == "enum"
        # Three members, ordered by ordinal.
        assert len(result.members) == 3
        names = [m.name for m in result.members]
        values = [m.value for m in result.members]
        ordinals = [m.ordinal for m in result.members]
        assert names == ["PENDING", "RUNNING", "FAILED"]
        assert values == ['"pending"', '"running"', '"failed"']
        assert ordinals == [0, 1, 2]
        # Parent metadata is threaded through every row.
        assert all(m.parent.id == ids["bar_id"] for m in result.members)


def test_trace_constant_includes_single_member(tmp_path: Path) -> None:
    """Tracing a constant populates a single-member ``TraceResult.members``."""
    project = _make_project(tmp_path)
    _make_linkgraph(project)
    ids = _seed_phase4_members_fixture(project)

    with SymbolQueryService(project) as svc:
        response = svc.trace("SCHEMA_VERSION")
        assert len(response.results) == 1
        result = response.results[0]

        assert result.symbol.id == ids["constant_id"]
        assert result.symbol.symbol_type == "constant"
        assert len(result.members) == 1
        member = result.members[0]
        assert member.name == "SCHEMA_VERSION"
        assert member.value == "2"
        assert member.ordinal == 0


def test_search_matches_member_value(tmp_path: Path) -> None:
    """``search_symbols('pending')`` surfaces the enum whose variant has that value.

    The name pass against ``symbols.name`` / ``symbols.qualified_name``
    does not hit any row for ``pending`` in the seed, so the enum can
    only come back via the member-value pass. The hit must therefore
    score ``0.5`` — the sentinel that distinguishes a value match from
    a name match.
    """
    project = _make_project(tmp_path)
    _make_linkgraph(project)
    ids = _seed_phase4_members_fixture(project)

    with SymbolQueryService(project) as svc:
        hits = svc.search_symbols("pending")
        assert len(hits) == 1
        hit = hits[0]
        assert hit.symbol.id == ids["bar_id"]
        assert hit.symbol.symbol_type == "enum"
        assert hit.score == 0.5


def test_search_value_match_deduped_by_name_match(tmp_path: Path) -> None:
    """A symbol already returned by the name pass is not re-added by the value pass.

    Searching for ``"bar"`` hits the enum via the name pass (score
    ``0.0``). The enum's members do not contain ``"bar"`` so the value
    pass returns nothing for this query, but the test also guards
    against a regression where both passes re-add the same parent.
    """
    project = _make_project(tmp_path)
    _make_linkgraph(project)
    _seed_phase4_members_fixture(project)

    with SymbolQueryService(project) as svc:
        hits = svc.search_symbols("bar")
        # The enum (renamed from the ``bar`` fixture) matches by name;
        # no duplicates.
        ids_seen = [hit.symbol.id for hit in hits]
        assert len(ids_seen) == len(set(ids_seen))
        # The original name match scores 0.0.
        assert any(hit.score == 0.0 and hit.symbol.name == "bar" for hit in hits)


def test_search_value_match_respects_limit(tmp_path: Path) -> None:
    """``limit`` caps results across both name and value passes combined.

    Seeds four constants whose names do NOT contain the search needle
    but whose member values all do; with ``limit=2`` the service must
    return exactly two hits rather than all four. The name pass against
    ``symbols.name`` / ``symbols.qualified_name`` contributes nothing,
    so every returned hit originates in the value pass and scores
    ``0.5``.
    """
    project = _make_project(tmp_path)
    _make_linkgraph(project)
    _seed_phase2_fixture(project)

    # Attach four parents whose names are plain words (no substring
    # match for the needle below) but whose member values contain the
    # needle so only the value pass fires.
    graph = open_symbol_graph(project)
    try:
        conn = graph._conn
        conn.execute(
            "INSERT INTO files (path, language, last_hash) VALUES (?, ?, ?)",
            ("src/c.py", "python", "hash-c"),
        )
        file_c_id = int(conn.execute("SELECT id FROM files WHERE path = 'src/c.py'").fetchone()[0])

        def _add_constant(name: str, qname: str, value: str) -> int:
            cur = conn.execute(
                "INSERT INTO symbols "
                "(file_id, name, qualified_name, symbol_type, line_start, "
                "line_end, visibility, parent_class) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
                (file_c_id, name, qname, "constant", 1, 1, "public"),
            )
            sym_id = int(cur.lastrowid or 0)
            conn.execute(
                "INSERT INTO symbol_members (symbol_id, name, value, ordinal) VALUES (?, ?, ?, ?)",
                (sym_id, name, value, 0),
            )
            return sym_id

        # The needle ``zzxxyy`` does not appear in any symbol name or
        # qualified name, so the name pass must contribute zero hits.
        _add_constant("ALPHA", "c.ALPHA", '"zzxxyy_alpha"')
        _add_constant("BETA", "c.BETA", '"zzxxyy_beta"')
        _add_constant("GAMMA", "c.GAMMA", '"zzxxyy_gamma"')
        _add_constant("DELTA", "c.DELTA", '"zzxxyy_delta"')
        conn.commit()
    finally:
        graph.close()

    with SymbolQueryService(project) as svc:
        hits = svc.search_symbols("zzxxyy", limit=2)
        # Name pass contributes nothing for ``zzxxyy``; value pass would
        # return four candidates; the combined cap is two.
        assert len(hits) == 2
        assert all(hit.score == 0.5 for hit in hits)
