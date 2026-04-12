"""Tests for the data-flow gate in the archivist symbol-graph context helper.

These tests cover the Group 7 deliverable of ``symbol-graph-7``: the
two-layer deterministic gate that controls whether ``include_data_flows``
is set on the :class:`SymbolGraphPromptContext` and whether the
``branch_parameters_block`` is populated.

The gate has two layers:

1. **Config layer** — ``symbols.include_data_flows`` must be ``True``.
2. **File layer** — ``svc.has_branching_parameters_in_file(rel_path)``
   must return ``True`` for the specific file being processed.
3. **Symbol layer** — ``_render_branch_parameters`` must produce at
   least one line (i.e. at least one function in the file has non-empty
   branch parameters).

If any layer fails, ``include_data_flows`` is ``False`` and
``branch_parameters_block`` is ``None``.

The tests seed a small ``symbols.db`` fixture by hand (following the
pattern used in ``tests/test_archivist/test_service_enrichment.py``)
so we can exercise the gate against known corpora without running the
real AST extractor.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from lexibrary.archivist.symbol_graph_context import render_symbol_graph_context
from lexibrary.config.schema import LexibraryConfig, SymbolGraphConfig, TokenBudgetConfig
from lexibrary.linkgraph.schema import ensure_schema as ensure_linkgraph_schema
from lexibrary.services.symbols import SymbolQueryService
from lexibrary.symbolgraph.query import open_symbol_graph
from lexibrary.utils.hashing import hash_file

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_project(tmp_path: Path) -> Path:
    """Create a minimal project root with ``.lexibrary/`` dir."""
    (tmp_path / ".lexibrary").mkdir()
    return tmp_path


def _make_linkgraph(project_root: Path) -> None:
    """Create a schema-initialised (but empty) link-graph database."""
    db_path = project_root / ".lexibrary" / "index.db"
    conn = sqlite3.connect(str(db_path))
    ensure_linkgraph_schema(conn)
    conn.commit()
    conn.close()


def _write_source_file(project_root: Path, rel_path: str, text: str = "x = 1\n") -> Path:
    """Write a source file under *project_root* and return the absolute path."""
    abs_path = project_root / rel_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(text, encoding="utf-8")
    return abs_path


def _make_config(
    *,
    scope_root: str = ".",
    symbols: SymbolGraphConfig | None = None,
) -> LexibraryConfig:
    """Create a config with a small design-file token budget and given symbols block."""
    return LexibraryConfig(
        scope_root=scope_root,
        token_budgets=TokenBudgetConfig(design_file_tokens=400),
        symbols=symbols or SymbolGraphConfig(),
    )


def _seed_function_with_branch_params(project_root: Path) -> dict[str, Any]:
    """Seed ``symbols.db`` with a function that has branch parameters.

    Creates ``src/gate.py`` with two functions:
    - ``process(config, data)`` — branches on ``config``
    - ``helper()`` — no branch parameters
    """
    src = _write_source_file(
        project_root,
        "src/gate.py",
        "def process(config, data): ...\ndef helper(): ...\n",
    )
    hash_src = hash_file(src)

    graph = open_symbol_graph(project_root)
    conn = graph._conn
    try:
        cur = conn.execute(
            "INSERT INTO files (path, language, last_hash) VALUES (?, ?, ?)",
            ("src/gate.py", "python", hash_src),
        )
        file_id = int(cur.lastrowid or 0)

        cur = conn.execute(
            "INSERT INTO symbols "
            "(file_id, name, qualified_name, symbol_type, line_start, "
            "line_end, visibility, parent_class) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
            (file_id, "process", "gate.process", "function", 1, 2, "public"),
        )
        process_id = int(cur.lastrowid or 0)

        cur = conn.execute(
            "INSERT INTO symbols "
            "(file_id, name, qualified_name, symbol_type, line_start, "
            "line_end, visibility, parent_class) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
            (file_id, "helper", "gate.helper", "function", 3, 4, "public"),
        )
        helper_id = int(cur.lastrowid or 0)

        # Insert branch parameter for process — branches on config
        conn.execute(
            "INSERT INTO symbol_branch_parameters (symbol_id, parameter_name) VALUES (?, ?)",
            (process_id, "config"),
        )
        conn.commit()
    finally:
        graph.close()

    return {
        "source_path": src,
        "file_id": file_id,
        "process_id": process_id,
        "helper_id": helper_id,
    }


def _seed_function_without_branch_params(project_root: Path) -> dict[str, Any]:
    """Seed ``symbols.db`` with a function that has no branch parameters.

    Creates ``src/plain.py`` with one function ``do_stuff()`` that has
    no branch parameters.
    """
    src = _write_source_file(
        project_root,
        "src/plain.py",
        "def do_stuff(): ...\n",
    )
    hash_src = hash_file(src)

    graph = open_symbol_graph(project_root)
    conn = graph._conn
    try:
        cur = conn.execute(
            "INSERT INTO files (path, language, last_hash) VALUES (?, ?, ?)",
            ("src/plain.py", "python", hash_src),
        )
        file_id = int(cur.lastrowid or 0)

        cur = conn.execute(
            "INSERT INTO symbols "
            "(file_id, name, qualified_name, symbol_type, line_start, "
            "line_end, visibility, parent_class) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
            (file_id, "do_stuff", "plain.do_stuff", "function", 1, 2, "public"),
        )
        fn_id = int(cur.lastrowid or 0)
        conn.commit()
    finally:
        graph.close()

    return {
        "source_path": src,
        "file_id": file_id,
        "fn_id": fn_id,
    }


def _seed_method_with_branch_params(project_root: Path) -> dict[str, Any]:
    """Seed ``symbols.db`` with a method that has branch parameters.

    Creates ``src/svc.py`` with one method ``MyService.handle(request)``
    that branches on ``request``. The ``self`` receiver is not recorded
    as a branch parameter.
    """
    src = _write_source_file(
        project_root,
        "src/svc.py",
        "class MyService:\n    def handle(self, request): ...\n",
    )
    hash_src = hash_file(src)

    graph = open_symbol_graph(project_root)
    conn = graph._conn
    try:
        cur = conn.execute(
            "INSERT INTO files (path, language, last_hash) VALUES (?, ?, ?)",
            ("src/svc.py", "python", hash_src),
        )
        file_id = int(cur.lastrowid or 0)

        cur = conn.execute(
            "INSERT INTO symbols "
            "(file_id, name, qualified_name, symbol_type, line_start, "
            "line_end, visibility, parent_class) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (file_id, "handle", "MyService.handle", "method", 2, 3, "public", "MyService"),
        )
        method_id = int(cur.lastrowid or 0)

        # Branch parameter — the request parameter, not self
        conn.execute(
            "INSERT INTO symbol_branch_parameters (symbol_id, parameter_name) VALUES (?, ?)",
            (method_id, "request"),
        )
        conn.commit()
    finally:
        graph.close()

    return {
        "source_path": src,
        "file_id": file_id,
        "method_id": method_id,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDataFlowGate:
    """Verify the two-layer deterministic gate for data-flow notes."""

    def test_service_skips_data_flows_when_config_disabled(self, tmp_path: Path) -> None:
        """When ``include_data_flows=False`` the gate is never triggered."""
        project = _make_project(tmp_path)
        _make_linkgraph(project)
        seeds = _seed_function_with_branch_params(project)

        config = _make_config(
            symbols=SymbolGraphConfig(
                enabled=True,
                include_data_flows=False,
            ),
        )

        with SymbolQueryService(project) as svc:
            ctx = render_symbol_graph_context(svc, project, seeds["source_path"], config)

        assert ctx.branch_parameters_block is None
        assert ctx.include_data_flows is False

    def test_service_skips_data_flows_when_file_has_no_branches(self, tmp_path: Path) -> None:
        """When the file has no branch parameters, include_data_flows is False."""
        project = _make_project(tmp_path)
        _make_linkgraph(project)
        seeds = _seed_function_without_branch_params(project)

        config = _make_config(
            symbols=SymbolGraphConfig(
                enabled=True,
                include_data_flows=True,
            ),
        )

        with SymbolQueryService(project) as svc:
            ctx = render_symbol_graph_context(svc, project, seeds["source_path"], config)

        assert ctx.branch_parameters_block is None
        assert ctx.include_data_flows is False

    def test_service_passes_data_flows_when_file_has_branches(self, tmp_path: Path) -> None:
        """When config is enabled and the file has branches, the block is populated."""
        project = _make_project(tmp_path)
        _make_linkgraph(project)
        seeds = _seed_function_with_branch_params(project)

        config = _make_config(
            symbols=SymbolGraphConfig(
                enabled=True,
                include_data_flows=True,
            ),
        )

        with SymbolQueryService(project) as svc:
            ctx = render_symbol_graph_context(svc, project, seeds["source_path"], config)

        assert ctx.branch_parameters_block is not None
        assert ctx.include_data_flows is True
        assert "process" in ctx.branch_parameters_block
        assert "config" in ctx.branch_parameters_block

    def test_service_branch_parameters_block_lists_function_names(self, tmp_path: Path) -> None:
        """The branch parameters block uses the ``- name(params): branches on params`` format."""
        project = _make_project(tmp_path)
        _make_linkgraph(project)
        seeds = _seed_function_with_branch_params(project)

        config = _make_config(
            symbols=SymbolGraphConfig(
                enabled=True,
                include_data_flows=True,
            ),
        )

        with SymbolQueryService(project) as svc:
            ctx = render_symbol_graph_context(svc, project, seeds["source_path"], config)

        assert ctx.branch_parameters_block is not None
        # Check the format matches the shared definition
        assert "- gate.process(config): branches on config" in ctx.branch_parameters_block
        # helper has no branch params — should not appear
        assert "helper" not in ctx.branch_parameters_block

    def test_service_branch_parameters_block_omits_self_receiver(self, tmp_path: Path) -> None:
        """Methods show branch parameters but ``self`` is not recorded as a branch param.

        The AST extractor excludes ``self``/``cls`` from branch parameters
        at extraction time. This test verifies that a method's rendered
        block only contains the non-self parameter.
        """
        project = _make_project(tmp_path)
        _make_linkgraph(project)
        seeds = _seed_method_with_branch_params(project)

        config = _make_config(
            symbols=SymbolGraphConfig(
                enabled=True,
                include_data_flows=True,
            ),
        )

        with SymbolQueryService(project) as svc:
            ctx = render_symbol_graph_context(svc, project, seeds["source_path"], config)

        assert ctx.branch_parameters_block is not None
        assert "request" in ctx.branch_parameters_block
        # self should never appear as a branch parameter
        assert "self" not in ctx.branch_parameters_block
