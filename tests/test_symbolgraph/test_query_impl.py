"""Direct SQL tests for ``lexibrary.symbolgraph.query`` Phase 2 bodies.

The Phase 2 query methods each compile to exactly one ``SELECT`` against
``symbols.db``. Rather than rebuild a whole project from source for every
scenario, these tests seed the database with hand-written INSERTs and
then assert the shape of what :class:`SymbolGraph` returns. Advantages:

- Fast — no parser, no file I/O beyond the tmp SQLite file.
- Stable — the tests pin exact row shapes, so a regression in
  :func:`_row_to_symbol` / :func:`_row_to_call` fails loudly.
- Focused — each test exercises exactly one query method.

The fixture helper :func:`_seed_graph` opens a graph via
:func:`open_symbol_graph`, inserts a tiny project-wide corpus, and
returns the graph plus a mapping of symbol names to their row ids so
tests can drive ``callers_of`` / ``callees_of`` without embedding
integer ids in the test bodies.
"""

from __future__ import annotations

from pathlib import Path

from lexibrary.symbolgraph.query import (
    CallRow,
    ClassEdgeRow,
    SymbolGraph,
    SymbolMemberRow,
    SymbolRow,
    UnresolvedCallRow,
    open_symbol_graph,
)

# ---------------------------------------------------------------------------
# Seed fixture
# ---------------------------------------------------------------------------


def _seed_graph(
    tmp_path: Path,
) -> tuple[SymbolGraph, dict[str, int], dict[str, int]]:
    """Create a graph with a hand-rolled corpus for query tests.

    Files:

    - ``src/a.py`` with ``greet``, ``Hello``, ``Hello.say_hi``, ``shout``,
      and ``CONSTANT``.
    - ``src/b.py`` with ``main``, ``helper``, and ``lonely``.

    Call edges (all inside this fixture, so counts are deterministic):

    - ``greet``    -> ``shout``       (a.py line 5)
    - ``shout``    -> ``greet``       (a.py line 12)
    - ``say_hi``   -> ``greet``       (a.py line 20)
    - ``main``     -> ``greet``       (b.py line 3)
    - ``main``     -> ``helper``      (b.py line 4)
    - ``main``     -> ``helper``      (b.py line 5) — second call, same line offset
    - ``helper``   -> ``shout``       (b.py line 9)

    Unresolved calls:

    - ``greet`` -> ``print``          (a.py line 6)
    - ``main``  -> ``os.getenv``      (b.py line 2)

    Returns ``(graph, symbol_ids, file_ids)`` where ``symbol_ids`` is
    keyed by the short name for the module-level symbols and by
    ``Hello.say_hi`` for the method.
    """
    graph = open_symbol_graph(tmp_path)
    conn = graph._conn

    # Files
    cur = conn.execute(
        "INSERT INTO files (path, language, last_hash) VALUES (?, ?, ?)",
        ("src/a.py", "python", "hash-a"),
    )
    file_a = int(cur.lastrowid or 0)
    cur = conn.execute(
        "INSERT INTO files (path, language, last_hash) VALUES (?, ?, ?)",
        ("src/b.py", "python", "hash-b"),
    )
    file_b = int(cur.lastrowid or 0)

    # Symbols — ordered so line_start is meaningful for "in file" ordering.
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

    greet = _add_symbol(file_a, "greet", "a.greet", "function", 1, 6, "public")
    hello = _add_symbol(file_a, "Hello", "a.Hello", "class", 10, 25, "public")
    say_hi = _add_symbol(
        file_a,
        "say_hi",
        "a.Hello.say_hi",
        "method",
        15,
        22,
        "public",
        parent_class="Hello",
    )
    shout = _add_symbol(file_a, "shout", "a.shout", "function", 30, 35, "public")
    constant = _add_symbol(file_a, "CONSTANT", "a.CONSTANT", "constant", 40, 40, "public")

    main_sym = _add_symbol(file_b, "main", "b.main", "function", 1, 10, "public")
    helper = _add_symbol(file_b, "helper", "b.helper", "function", 12, 18, "public")
    lonely = _add_symbol(file_b, "lonely", "b.lonely", "function", 20, 25, "public")

    symbol_ids = {
        "greet": greet,
        "Hello": hello,
        "Hello.say_hi": say_hi,
        "shout": shout,
        "CONSTANT": constant,
        "main": main_sym,
        "helper": helper,
        "lonely": lonely,
    }

    # Resolved call edges
    resolved_edges = [
        (greet, shout, 5, "call"),
        (shout, greet, 12, "call"),
        (say_hi, greet, 20, "call"),
        (main_sym, greet, 3, "call"),
        (main_sym, helper, 4, "call"),
        (main_sym, helper, 5, "call"),
        (helper, shout, 9, "call"),
    ]
    for caller_id, callee_id, line, context in resolved_edges:
        conn.execute(
            "INSERT INTO calls (caller_id, callee_id, line, call_context) VALUES (?, ?, ?, ?)",
            (caller_id, callee_id, line, context),
        )

    # Unresolved edges
    unresolved_edges = [
        (greet, "print", 6, "call"),
        (main_sym, "os.getenv", 2, "call"),
    ]
    for caller_id, callee_name, line, context in unresolved_edges:
        conn.execute(
            "INSERT INTO unresolved_calls "
            "(caller_id, callee_name, line, call_context) "
            "VALUES (?, ?, ?, ?)",
            (caller_id, callee_name, line, context),
        )

    conn.commit()
    return graph, symbol_ids, {"src/a.py": file_a, "src/b.py": file_b}


# ---------------------------------------------------------------------------
# symbols_by_name
# ---------------------------------------------------------------------------


def test_symbols_by_name(tmp_path: Path) -> None:
    """``symbols_by_name`` returns every matching bare name across files."""
    graph, symbol_ids, _ = _seed_graph(tmp_path)
    try:
        rows = graph.symbols_by_name("greet")
        assert [row.id for row in rows] == [symbol_ids["greet"]]
        assert isinstance(rows[0], SymbolRow)
        assert rows[0].file_path == "src/a.py"
        assert rows[0].qualified_name == "a.greet"
        assert rows[0].symbol_type == "function"
        assert rows[0].line_start == 1
        assert rows[0].line_end == 6

        # No match — empty list, not an error.
        assert graph.symbols_by_name("does_not_exist") == []
    finally:
        graph.close()


def test_symbols_by_name_with_file_filter(tmp_path: Path) -> None:
    """``file_path`` narrows the match to a single file."""
    # Seed a second ``greet`` in ``src/b.py`` so the unfiltered query
    # returns two rows; the filtered one must return exactly one.
    graph, symbol_ids, file_ids = _seed_graph(tmp_path)
    try:
        conn = graph._conn
        conn.execute(
            "INSERT INTO symbols "
            "(file_id, name, qualified_name, symbol_type, line_start, "
            "line_end, visibility, parent_class) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
            (file_ids["src/b.py"], "greet", "b.greet", "function", 30, 34, "public"),
        )
        conn.commit()

        # Unfiltered — two matches, ordered by file path.
        unfiltered = graph.symbols_by_name("greet")
        assert [row.file_path for row in unfiltered] == ["src/a.py", "src/b.py"]

        # Filtered — only the b.py row.
        filtered = graph.symbols_by_name("greet", file_path="src/b.py")
        assert len(filtered) == 1
        assert filtered[0].file_path == "src/b.py"
        assert filtered[0].qualified_name == "b.greet"
    finally:
        graph.close()


# ---------------------------------------------------------------------------
# symbols_by_qualified_name
# ---------------------------------------------------------------------------


def test_symbols_by_qualified_name_exact_match(tmp_path: Path) -> None:
    """``symbols_by_qualified_name`` requires an exact match on the dotted path."""
    graph, symbol_ids, _ = _seed_graph(tmp_path)
    try:
        # Exact-match on the method's qualified name.
        rows = graph.symbols_by_qualified_name("a.Hello.say_hi")
        assert len(rows) == 1
        assert rows[0].id == symbol_ids["Hello.say_hi"]
        assert rows[0].name == "say_hi"
        assert rows[0].symbol_type == "method"

        # Bare name must NOT match — this is the point of having
        # two separate lookups.
        assert graph.symbols_by_qualified_name("say_hi") == []

        # The class itself matches its own qualified name exactly,
        # but a prefix like "a.Hel" must not.
        class_rows = graph.symbols_by_qualified_name("a.Hello")
        assert len(class_rows) == 1
        assert class_rows[0].symbol_type == "class"
        assert graph.symbols_by_qualified_name("a.Hel") == []

        # File-filter combines with the exact match.
        filtered = graph.symbols_by_qualified_name("a.greet", file_path="src/a.py")
        assert len(filtered) == 1
        filtered_wrong_file = graph.symbols_by_qualified_name("a.greet", file_path="src/b.py")
        assert filtered_wrong_file == []
    finally:
        graph.close()


# ---------------------------------------------------------------------------
# symbols_in_file
# ---------------------------------------------------------------------------


def test_symbols_in_file_ordered_by_line(tmp_path: Path) -> None:
    """``symbols_in_file`` returns every symbol in the file, sorted by line."""
    graph, _, _ = _seed_graph(tmp_path)
    try:
        rows = graph.symbols_in_file("src/a.py")
        names = [row.name for row in rows]
        # Insert order in the seed is greet(1), Hello(10), say_hi(15),
        # shout(30), CONSTANT(40) — which is also the line-ordered order.
        assert names == ["greet", "Hello", "say_hi", "shout", "CONSTANT"]
        # line_start is ascending
        starts = [row.line_start for row in rows]
        assert starts == sorted(starts)  # type: ignore[type-var]

        # Missing file — empty list, not an error.
        assert graph.symbols_in_file("src/missing.py") == []
    finally:
        graph.close()


# ---------------------------------------------------------------------------
# callers_of / callees_of
# ---------------------------------------------------------------------------


def test_callers_of_joins_symbols_twice(tmp_path: Path) -> None:
    """``callers_of`` returns every inbound edge with both endpoints populated."""
    graph, symbol_ids, _ = _seed_graph(tmp_path)
    try:
        rows = graph.callers_of(symbol_ids["greet"])
        # greet is called by shout (a.py:12), say_hi (a.py:20), main (b.py:3).
        assert len(rows) == 3
        # Ordered by caller file path then line.
        caller_pairs = [(row.caller.name, row.line) for row in rows]
        assert caller_pairs == [
            ("shout", 12),
            ("say_hi", 20),
            ("main", 3),
        ]

        # The callee is fully populated on every row.
        for row in rows:
            assert isinstance(row, CallRow)
            assert row.callee.id == symbol_ids["greet"]
            assert row.callee.name == "greet"
            assert row.callee.qualified_name == "a.greet"
            assert row.callee.file_path == "src/a.py"

        # Symbol with no callers — empty list, not an error.
        assert graph.callers_of(symbol_ids["lonely"]) == []
    finally:
        graph.close()


def test_callees_of_returns_callrow_list(tmp_path: Path) -> None:
    """``callees_of`` returns every outbound edge with both endpoints populated."""
    graph, symbol_ids, _ = _seed_graph(tmp_path)
    try:
        rows = graph.callees_of(symbol_ids["main"])
        # main calls greet (line 3), helper (line 4), helper (line 5).
        assert [row.line for row in rows] == [3, 4, 5]
        callee_names = [row.callee.name for row in rows]
        assert callee_names == ["greet", "helper", "helper"]

        # Caller endpoint is populated and identical across the rows.
        for row in rows:
            assert row.caller.name == "main"
            assert row.caller.qualified_name == "b.main"
            assert row.caller.file_path == "src/b.py"

        # Symbol with no callees.
        assert graph.callees_of(symbol_ids["lonely"]) == []
    finally:
        graph.close()


# ---------------------------------------------------------------------------
# unresolved_callees_of
# ---------------------------------------------------------------------------


def test_unresolved_callees_of(tmp_path: Path) -> None:
    """``unresolved_callees_of`` returns unresolved edges with string names."""
    graph, symbol_ids, _ = _seed_graph(tmp_path)
    try:
        rows = graph.unresolved_callees_of(symbol_ids["greet"])
        assert len(rows) == 1
        row = rows[0]
        assert isinstance(row, UnresolvedCallRow)
        assert row.callee_name == "print"
        assert row.line == 6
        assert row.caller.name == "greet"
        assert row.caller.file_path == "src/a.py"

        # main has one unresolved call.
        main_rows = graph.unresolved_callees_of(symbol_ids["main"])
        assert [r.callee_name for r in main_rows] == ["os.getenv"]

        # Symbol with none — empty list.
        assert graph.unresolved_callees_of(symbol_ids["lonely"]) == []
    finally:
        graph.close()


# ---------------------------------------------------------------------------
# symbol_call_counts
# ---------------------------------------------------------------------------


def test_symbol_call_counts_single_query(tmp_path: Path) -> None:
    """``symbol_call_counts`` runs exactly one SELECT against ``calls``.

    Seeds three distinct call-count profiles in a single file:

    - ``main``   — called 0 times, calls 3 times         (b.py)
    - ``helper`` — called 2 times, calls 1 time          (b.py)
    - ``lonely`` — called 0 times, calls 0 times         (b.py)

    Uses a connection ``set_trace_callback`` to verify the aggregation
    is a single SELECT — the query must NOT iterate over symbols.
    """
    graph, symbol_ids, _ = _seed_graph(tmp_path)
    try:
        # Hook the trace callback before issuing the method call so we
        # only measure work inside symbol_call_counts.
        executed: list[str] = []
        graph._conn.set_trace_callback(executed.append)

        counts = graph.symbol_call_counts("src/b.py")

        # Disable tracing so the assertion below runs cleanly.
        graph._conn.set_trace_callback(None)

        # Expected shape for the three b.py symbols.
        assert counts[symbol_ids["main"]] == (0, 3)
        assert counts[symbol_ids["helper"]] == (2, 1)
        assert counts[symbol_ids["lonely"]] == (0, 0)

        # Only three rows — the query is correctly scoped by file path.
        assert set(counts.keys()) == {
            symbol_ids["main"],
            symbol_ids["helper"],
            symbol_ids["lonely"],
        }

        # Only one SELECT statement was executed during the method.
        select_statements = [sql for sql in executed if "SELECT" in sql.upper()]
        assert len(select_statements) == 1, (
            f"expected exactly one SELECT for symbol_call_counts, "
            f"got {len(select_statements)}: {select_statements}"
        )
    finally:
        graph.close()


# ---------------------------------------------------------------------------
# query_raw
# ---------------------------------------------------------------------------


def test_query_raw_arbitrary_select(tmp_path: Path) -> None:
    """``query_raw`` returns raw rows from an arbitrary ``SELECT``."""
    graph, _, _ = _seed_graph(tmp_path)
    try:
        # Count rows in the calls table.
        rows = graph.query_raw("SELECT COUNT(*) FROM calls")
        assert len(rows) == 1
        assert int(rows[0][0]) == 7  # 7 resolved edges in the seed

        # Parameterised query.
        rows = graph.query_raw(
            "SELECT name FROM symbols WHERE symbol_type = ? ORDER BY name",
            ("function",),
        )
        names = [str(row[0]) for row in rows]
        assert names == ["greet", "helper", "lonely", "main", "shout"]

        # Returned rows are tuple-like sqlite3.Row-or-tuple objects.
        raw = graph.query_raw("SELECT 1")
        assert isinstance(raw, list)
        assert int(raw[0][0]) == 1
    finally:
        graph.close()


# ---------------------------------------------------------------------------
# class_edges_from / class_edges_to — real SQL queries
# ---------------------------------------------------------------------------


def test_class_edge_queries_return_empty_when_tables_empty(tmp_path: Path) -> None:
    """With ``class_edges`` and ``symbol_members`` empty, queries yield ``[]``.

    The builder's pass 3 (``symbol-graph-3``) populates ``class_edges``
    and the Phase 4 extractor populates ``symbol_members``. Before either
    has run for a given symbol, the corresponding query method must
    return an empty list rather than raising.
    """
    graph, symbol_ids, _ = _seed_graph(tmp_path)
    try:
        assert graph.class_edges_from(symbol_ids["Hello"]) == []
        assert graph.class_edges_to(symbol_ids["Hello"]) == []
        assert graph.members_of(symbol_ids["Hello"]) == []
    finally:
        graph.close()


def test_class_edges_from_returns_populated_edges(tmp_path: Path) -> None:
    """``class_edges_from`` joins both endpoints and orders by edge_type."""
    graph, symbol_ids, _ = _seed_graph(tmp_path)
    try:
        # Seed an ``inherits`` edge from ``say_hi``'s parent ``Hello`` to
        # a freshly-inserted base class, plus one ``instantiates`` edge
        # from ``greet`` to ``Hello`` so the ordering assertion is
        # meaningful.
        conn = graph._conn
        cur = conn.execute(
            "INSERT INTO symbols "
            "(file_id, name, qualified_name, symbol_type, line_start, "
            "line_end, visibility, parent_class) "
            "VALUES ((SELECT id FROM files WHERE path='src/a.py'), "
            "?, ?, ?, ?, ?, ?, NULL)",
            ("Base", "a.Base", "class", 50, 55, "public"),
        )
        base_id = int(cur.lastrowid or 0)

        conn.execute(
            "INSERT INTO class_edges "
            "(source_id, target_id, edge_type, line, context) "
            "VALUES (?, ?, ?, ?, ?)",
            (symbol_ids["Hello"], base_id, "inherits", 10, None),
        )
        conn.execute(
            "INSERT INTO class_edges "
            "(source_id, target_id, edge_type, line, context) "
            "VALUES (?, ?, ?, ?, ?)",
            (symbol_ids["greet"], symbol_ids["Hello"], "instantiates", 3, None),
        )
        conn.commit()

        # Outbound edges from Hello — exactly one inherits edge.
        hello_out = graph.class_edges_from(symbol_ids["Hello"])
        assert len(hello_out) == 1
        edge = hello_out[0]
        assert isinstance(edge, ClassEdgeRow)
        assert edge.source.name == "Hello"
        assert edge.target.name == "Base"
        assert edge.edge_type == "inherits"
        assert edge.line == 10
        assert edge.context is None

        # Outbound edges from greet — exactly one instantiates edge.
        greet_out = graph.class_edges_from(symbol_ids["greet"])
        assert len(greet_out) == 1
        assert greet_out[0].edge_type == "instantiates"
        assert greet_out[0].target.name == "Hello"

        # No edges — empty list, not an error.
        assert graph.class_edges_from(symbol_ids["shout"]) == []
    finally:
        graph.close()


def test_class_edges_to_returns_populated_edges(tmp_path: Path) -> None:
    """``class_edges_to`` returns inbound edges with both endpoints populated."""
    graph, symbol_ids, _ = _seed_graph(tmp_path)
    try:
        conn = graph._conn
        # Two edges target ``Hello``: one subclass ``Child`` that
        # inherits, plus ``greet`` that instantiates.
        cur = conn.execute(
            "INSERT INTO symbols "
            "(file_id, name, qualified_name, symbol_type, line_start, "
            "line_end, visibility, parent_class) "
            "VALUES ((SELECT id FROM files WHERE path='src/b.py'), "
            "?, ?, ?, ?, ?, ?, NULL)",
            ("Child", "b.Child", "class", 40, 45, "public"),
        )
        child_id = int(cur.lastrowid or 0)

        conn.execute(
            "INSERT INTO class_edges "
            "(source_id, target_id, edge_type, line, context) "
            "VALUES (?, ?, ?, ?, ?)",
            (child_id, symbol_ids["Hello"], "inherits", 40, None),
        )
        conn.execute(
            "INSERT INTO class_edges "
            "(source_id, target_id, edge_type, line, context) "
            "VALUES (?, ?, ?, ?, ?)",
            (symbol_ids["greet"], symbol_ids["Hello"], "instantiates", 3, None),
        )
        conn.commit()

        rows = graph.class_edges_to(symbol_ids["Hello"])
        assert len(rows) == 2
        # Ordered by edge_type: inherits before instantiates.
        assert [row.edge_type for row in rows] == ["inherits", "instantiates"]
        assert rows[0].source.name == "Child"
        assert rows[0].target.name == "Hello"
        assert rows[0].line == 40
        assert rows[1].source.name == "greet"
        assert rows[1].target.name == "Hello"

        # No inbound edges — empty list.
        assert graph.class_edges_to(symbol_ids["shout"]) == []
    finally:
        graph.close()


# ---------------------------------------------------------------------------
# members_of — real SQL query
# ---------------------------------------------------------------------------


def test_members_of_returns_populated_members(tmp_path: Path) -> None:
    """``members_of`` joins the parent and orders by ordinal then name."""
    graph, symbol_ids, _ = _seed_graph(tmp_path)
    try:
        conn = graph._conn
        # Seed three members under ``Hello`` — one without an ordinal
        # so the "NULLs last, then by name" ordering rule is exercised.
        conn.execute(
            "INSERT INTO symbol_members (symbol_id, name, value, ordinal) VALUES (?, ?, ?, ?)",
            (symbol_ids["Hello"], "B", "2", 1),
        )
        conn.execute(
            "INSERT INTO symbol_members (symbol_id, name, value, ordinal) VALUES (?, ?, ?, ?)",
            (symbol_ids["Hello"], "A", "1", 0),
        )
        conn.execute(
            "INSERT INTO symbol_members (symbol_id, name, value, ordinal) VALUES (?, ?, ?, ?)",
            (symbol_ids["Hello"], "Z", None, None),
        )
        conn.commit()

        rows = graph.members_of(symbol_ids["Hello"])
        assert len(rows) == 3
        assert all(isinstance(row, SymbolMemberRow) for row in rows)
        assert [row.name for row in rows] == ["A", "B", "Z"]
        assert [row.ordinal for row in rows] == [0, 1, None]
        assert [row.value for row in rows] == ["1", "2", None]
        # Parent is populated on every row.
        assert rows[0].parent.name == "Hello"
        assert rows[0].parent.file_path == "src/a.py"

        # Missing parent — empty list, not an error.
        assert graph.members_of(symbol_ids["shout"]) == []
    finally:
        graph.close()
