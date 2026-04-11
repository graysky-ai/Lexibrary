"""Tests for the ``lexi trace`` CLI command.

Uses :class:`typer.testing.CliRunner` against a pre-seeded ``symbols.db``
factored out as :func:`tests.test_symbolgraph.conftest.seed_phase2_fixture`.
Each test creates a fresh tmp project, seeds the graph, and invokes the
``trace`` command via ``runner.invoke``. The seeding helper is shared
across tests so the ``trace`` output is backed by the exact same corpus
that ``tests/test_services/test_symbols.py`` uses.

Coverage is 1:1 with the task specification (symbol-graph-2 group 12.4):

1. ``test_trace_found_symbol`` — happy path header + callers section.
2. ``test_trace_not_found`` — exit 1 + "No symbol named" on stderr.
3. ``test_trace_multiple_matches_renders_both`` — two symbols, same name.
4. ``test_trace_no_callers_no_callees`` — leaf symbol: header only.
5. ``test_trace_filters_by_file`` — ``--file`` narrows an ambiguous name.
6. ``test_trace_accepts_qualified_name`` — dotted arg uses
   ``qualified_name`` match.
7. ``test_trace_emits_stale_warning_on_stderr`` — stale ``last_hash``
   surfaces as a warning without failing the command.

symbol-graph-3 group 5.8 adds:

8. ``test_trace_renders_class_sections`` — a Phase 3 class hierarchy
   fixture surfaces ``### Base classes`` and ``### Subclasses and
   instantiation sites`` blocks plus the trailing "Unresolved bases"
   line for external bases.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from lexibrary.cli.lexi_app import lexi_app
from lexibrary.symbolgraph.query import open_symbol_graph
from tests.test_symbolgraph.conftest import (
    make_linkgraph,
    make_project,
    seed_phase2_fixture,
    seed_phase3_class_fixture,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# (1) Happy path — found symbol
# ---------------------------------------------------------------------------


def test_trace_found_symbol(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A known symbol exits 0 and renders its callers section."""
    project = make_project(tmp_path)
    make_linkgraph(project)
    seed_phase2_fixture(project)
    monkeypatch.chdir(project)

    result = runner.invoke(lexi_app, ["trace", "bar"])

    assert result.exit_code == 0, result.output
    # Header contains the qualified name and symbol type.
    assert "## a.bar  [function]" in result.output
    assert "`src/a.py:6`" in result.output
    # ``bar`` is called by ``foo`` and ``baz``; both rendered under Callers.
    assert "### Callers" in result.output
    assert "a.foo" in result.output
    assert "a.baz" in result.output or "b.baz" in result.output
    # ``bar`` has no callees of its own, so that section must be omitted.
    assert "### Callees" not in result.output
    assert "### Unresolved callees" not in result.output


# ---------------------------------------------------------------------------
# (2) Not found
# ---------------------------------------------------------------------------


def test_trace_not_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An unknown symbol exits 1 and emits ``No symbol named`` on stderr."""
    project = make_project(tmp_path)
    make_linkgraph(project)
    seed_phase2_fixture(project)
    monkeypatch.chdir(project)

    result = runner.invoke(lexi_app, ["trace", "does_not_exist"])

    assert result.exit_code == 1
    # ``warn()`` and ``hint()`` write to stderr; ``result.stderr`` captures it.
    assert "No symbol named" in result.stderr
    assert "does_not_exist" in result.stderr
    # Hint points the user at the refresh path.
    assert "lexi design update" in result.stderr or "lexi search" in result.stderr


# ---------------------------------------------------------------------------
# (3) Multiple matches render both
# ---------------------------------------------------------------------------


def test_trace_multiple_matches_renders_both(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two symbols with the same bare name both render with their own headers."""
    project = make_project(tmp_path)
    make_linkgraph(project)
    ids = seed_phase2_fixture(project)

    # Add a second ``foo`` in ``src/b.py`` alongside the fixture's ``foo``
    # in ``src/a.py`` so ``trace('foo')`` returns two results.
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

    monkeypatch.chdir(project)
    result = runner.invoke(lexi_app, ["trace", "foo"])

    assert result.exit_code == 0, result.output
    # Both results are rendered with their qualified names.
    assert "## a.foo  [function]" in result.output
    assert "## b.foo  [function]" in result.output
    # Both file:line lines appear.
    assert "`src/a.py:1`" in result.output
    assert "`src/b.py:20`" in result.output


# ---------------------------------------------------------------------------
# (4) Leaf symbol — no callers, no callees
# ---------------------------------------------------------------------------


def test_trace_no_callers_no_callees(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A leaf symbol renders header + file:line but no tables."""
    project = make_project(tmp_path)
    make_linkgraph(project)
    ids = seed_phase2_fixture(project)

    # Insert a fresh leaf symbol in src/b.py with no edges in either
    # direction, so trace renders only the header block.
    graph = open_symbol_graph(project)
    try:
        graph._conn.execute(
            "INSERT INTO symbols "
            "(file_id, name, qualified_name, symbol_type, line_start, "
            "line_end, visibility, parent_class) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
            (
                ids["file_b_id"],
                "lonely",
                "b.lonely",
                "function",
                30,
                32,
                "public",
            ),
        )
        graph._conn.commit()
    finally:
        graph.close()

    monkeypatch.chdir(project)
    result = runner.invoke(lexi_app, ["trace", "lonely"])

    assert result.exit_code == 0, result.output
    assert "## b.lonely  [function]" in result.output
    assert "`src/b.py:30`" in result.output
    # Every section heading must be absent.
    assert "### Callers" not in result.output
    assert "### Callees" not in result.output
    assert "### Unresolved callees" not in result.output


# ---------------------------------------------------------------------------
# (5) --file narrows ambiguous bare name
# ---------------------------------------------------------------------------


def test_trace_filters_by_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``--file`` picks a single ``foo`` when the bare name is ambiguous."""
    project = make_project(tmp_path)
    make_linkgraph(project)
    ids = seed_phase2_fixture(project)

    # Same duplicate-foo setup as test (3).
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

    monkeypatch.chdir(project)
    result = runner.invoke(lexi_app, ["trace", "foo", "--file", "src/a.py"])

    assert result.exit_code == 0, result.output
    # Only ``a.foo`` is rendered — ``b.foo`` must be filtered out.
    assert "## a.foo  [function]" in result.output
    assert "## b.foo  [function]" not in result.output
    assert "`src/a.py:1`" in result.output
    assert "`src/b.py:20`" not in result.output


# ---------------------------------------------------------------------------
# (6) Qualified name match (dot in argument)
# ---------------------------------------------------------------------------


def test_trace_accepts_qualified_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A dotted argument matches exactly against ``qualified_name``.

    The fixture seeds ``meth`` with ``qualified_name = b.Klass.meth``.
    Invoking ``trace`` with the dotted form must resolve via the
    qualified-name path and return exactly that symbol, even if a bare
    ``meth`` existed elsewhere (it does not, but the test still proves
    exact-match semantics).
    """
    project = make_project(tmp_path)
    make_linkgraph(project)
    seed_phase2_fixture(project)
    monkeypatch.chdir(project)

    result = runner.invoke(lexi_app, ["trace", "b.Klass.meth"])

    assert result.exit_code == 0, result.output
    assert "## b.Klass.meth  [method]" in result.output
    assert "`src/b.py:6`" in result.output
    # ``meth`` calls ``baz`` — render_trace must show the Callees section.
    assert "### Callees" in result.output
    assert "b.baz" in result.output

    # A prefix-only lookup must NOT match the full qualified name.
    partial = runner.invoke(lexi_app, ["trace", "b.Klass"])
    assert partial.exit_code == 1
    assert "No symbol named" in partial.stderr


# ---------------------------------------------------------------------------
# (7) Stale warning on stderr, exit 0
# ---------------------------------------------------------------------------


def test_trace_emits_stale_warning_on_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Perturbing ``last_hash`` yields a stderr warning without failing."""
    project = make_project(tmp_path)
    make_linkgraph(project)
    seed_phase2_fixture(project)

    # Overwrite src/a.py's stored hash so the service's rehash detects
    # drift without having to touch the on-disk file.
    graph = open_symbol_graph(project)
    try:
        graph._conn.execute(
            "UPDATE files SET last_hash = ? WHERE path = ?",
            ("stale-bogus-hash", "src/a.py"),
        )
        graph._conn.commit()
    finally:
        graph.close()

    monkeypatch.chdir(project)
    result = runner.invoke(lexi_app, ["trace", "foo"])

    assert result.exit_code == 0, result.output
    # The result is still rendered (header visible on stdout).
    assert "## a.foo  [function]" in result.output
    # Warning is emitted via warn() → stderr.
    assert "Symbol graph may be stale" in result.stderr
    assert "src/a.py" in result.stderr


# ---------------------------------------------------------------------------
# (8) Class hierarchy sections (Phase 3)
# ---------------------------------------------------------------------------


def test_trace_renders_class_sections(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A class symbol renders ``### Base classes`` / ``### Subclasses`` blocks.

    Uses the Phase 3 class-hierarchy fixture from ``conftest`` which
    seeds ``Base``, ``Derived``, ``Thing``, and ``main`` plus four
    class edges (two resolved, two unresolved). Tracing each class
    exercises a different slice of the renderer:

    - ``Base`` — no parents, one inbound ``inherits`` edge from
      ``Derived``. Output must contain ``### Subclasses and
      instantiation sites`` but NOT ``### Base classes`` or
      ``Unresolved bases``. (``main → Derived`` is an instantiation of
      ``Derived``, not of ``Base``, so it does not appear under
      ``Base``.)
    - ``Derived`` — one parent (``Base``) and one instantiation site
      (``main``). Output must contain both ``### Base classes`` and
      ``### Subclasses and instantiation sites``.
    - ``Thing`` — two unresolved parents (``BaseModel``, ``Enum``).
      Output must contain the trailing ``Unresolved bases: ...`` line
      and must NOT contain ``### Base classes`` (nothing resolved).
    """
    project = make_project(tmp_path)
    make_linkgraph(project)
    seed_phase3_class_fixture(project)
    monkeypatch.chdir(project)

    # --- Base ---
    base_result = runner.invoke(lexi_app, ["trace", "Base"])
    assert base_result.exit_code == 0, base_result.output
    assert "## pkg.Base  [class]" in base_result.output
    assert "### Subclasses and instantiation sites" in base_result.output
    # Only Derived is an inbound edge for Base.
    assert "pkg.Derived" in base_result.output
    assert "inherits" in base_result.output
    # Base has no parents and no unresolved bases, so those sections
    # must be absent.
    assert "### Base classes" not in base_result.output
    assert "Unresolved bases" not in base_result.output

    # --- Derived ---
    derived_result = runner.invoke(lexi_app, ["trace", "Derived"])
    assert derived_result.exit_code == 0, derived_result.output
    assert "## pkg.Derived  [class]" in derived_result.output
    assert "### Base classes" in derived_result.output
    assert "pkg.Base" in derived_result.output
    assert "### Subclasses and instantiation sites" in derived_result.output
    assert "pkg.main" in derived_result.output
    assert "instantiates" in derived_result.output
    assert "Unresolved bases" not in derived_result.output

    # --- Thing ---
    thing_result = runner.invoke(lexi_app, ["trace", "Thing"])
    assert thing_result.exit_code == 0, thing_result.output
    assert "## pkg.Thing  [class]" in thing_result.output
    # Thing's only bases are unresolved — the trailing line surfaces
    # both external names together.
    assert "Unresolved bases:" in thing_result.output
    assert "BaseModel" in thing_result.output
    assert "Enum" in thing_result.output
    # No resolved base class row and no inbound class edges.
    assert "### Base classes" not in thing_result.output
    assert "### Subclasses and instantiation sites" not in thing_result.output
