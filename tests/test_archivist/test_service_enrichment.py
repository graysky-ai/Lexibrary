"""Tests for the archivist symbol-graph enrichment helper and pipeline wiring.

These tests cover the group 5 deliverable of the ``symbol-graph-5`` plan:
the ``render_symbol_graph_context`` helper (per-file context blocks for
the design-file prompt) and the ``update_project`` integration that
opens a :class:`SymbolQueryService` around the design-file loop.

The helper tests seed a small ``symbols.db`` fixture by hand (following
the pattern used in ``tests/test_services/test_symbols.py``) so we can
exercise the render helpers against known corpora without running the
real Python AST extractor.

The pipeline integration test monkeypatches ``update_file`` and
``build_symbol_graph`` to keep the test hermetic, then spies on
``SymbolQueryService.__enter__`` to assert the service is opened exactly
once per ``update_project`` run regardless of how many source files are
in scope.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lexibrary.archivist.change_checker import ChangeLevel
from lexibrary.archivist.pipeline import FileResult, update_project
from lexibrary.archivist.service import ArchivistService, DesignFileResult
from lexibrary.archivist.symbol_graph_context import render_symbol_graph_context
from lexibrary.baml_client.types import DesignFileOutput
from lexibrary.config.schema import LexibraryConfig, SymbolGraphConfig, TokenBudgetConfig
from lexibrary.linkgraph.schema import ensure_schema as ensure_linkgraph_schema
from lexibrary.services.symbols import SymbolQueryService
from lexibrary.symbolgraph.builder import SymbolBuildResult
from lexibrary.symbolgraph.query import open_symbol_graph
from lexibrary.utils.hashing import hash_file

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_project(tmp_path: Path) -> Path:
    """Create a minimal project root with ``.lexibrary/`` and scope_root."""
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


def _seed_single_enum_fixture(project_root: Path) -> dict[str, Any]:
    """Seed ``symbols.db`` with one enum in ``src/colors.py``.

    The enum has three members so the enum block renders a non-empty
    ``{RED=..., GREEN=..., BLUE=...}`` line.
    """
    src = _write_source_file(project_root, "src/colors.py", "# enum source\n")
    hash_src = hash_file(src)

    # ``open_symbol_graph(..., create=True)`` initialises the schema
    # without running the real extractor, so we can seed rows by hand
    # and avoid conflicts with auto-discovered source files.
    graph = open_symbol_graph(project_root)
    conn = graph._conn
    try:
        cur = conn.execute(
            "INSERT INTO files (path, language, last_hash) VALUES (?, ?, ?)",
            ("src/colors.py", "python", hash_src),
        )
        file_id = int(cur.lastrowid or 0)

        cur = conn.execute(
            "INSERT INTO symbols "
            "(file_id, name, qualified_name, symbol_type, line_start, "
            "line_end, visibility, parent_class) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
            (file_id, "Color", "colors.Color", "enum", 1, 5, "public"),
        )
        enum_id = int(cur.lastrowid or 0)

        for ordinal, (name, value) in enumerate(
            [("RED", '"red"'), ("GREEN", '"green"'), ("BLUE", '"blue"')]
        ):
            conn.execute(
                "INSERT INTO symbol_members (symbol_id, name, value, ordinal) VALUES (?, ?, ?, ?)",
                (enum_id, name, value, ordinal),
            )
        conn.commit()
    finally:
        graph.close()

    return {"source_path": src, "file_id": file_id, "enum_id": enum_id}


def _seed_single_function_with_edges(project_root: Path) -> dict[str, Any]:
    """Seed ``symbols.db`` with one callee-linked function in ``src/mod.py``.

    Creates two functions ``caller`` and ``target`` in the same file and
    a ``caller → target`` resolved call edge so ``target`` has one
    recorded inbound edge.
    """
    src = _write_source_file(project_root, "src/mod.py", "# function source\n")
    hash_src = hash_file(src)

    graph = open_symbol_graph(project_root)
    conn = graph._conn
    try:
        cur = conn.execute(
            "INSERT INTO files (path, language, last_hash) VALUES (?, ?, ?)",
            ("src/mod.py", "python", hash_src),
        )
        file_id = int(cur.lastrowid or 0)

        def _add(name: str, qname: str, line: int) -> int:
            cur = conn.execute(
                "INSERT INTO symbols "
                "(file_id, name, qualified_name, symbol_type, line_start, "
                "line_end, visibility, parent_class) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
                (file_id, name, qname, "function", line, line + 2, "public"),
            )
            return int(cur.lastrowid or 0)

        caller_id = _add("caller", "mod.caller", 1)
        target_id = _add("target", "mod.target", 10)

        conn.execute(
            "INSERT INTO calls (caller_id, callee_id, line, call_context) VALUES (?, ?, ?, ?)",
            (caller_id, target_id, 2, "call"),
        )
        conn.commit()
    finally:
        graph.close()

    return {
        "source_path": src,
        "file_id": file_id,
        "caller_id": caller_id,
        "target_id": target_id,
    }


def _seed_many_constants_fixture(project_root: Path, count: int) -> Path:
    """Seed ``count`` constant symbols in a single file, each with one member row."""
    src = _write_source_file(project_root, "src/consts.py", "# constants source\n")
    hash_src = hash_file(src)

    graph = open_symbol_graph(project_root)
    conn = graph._conn
    try:
        cur = conn.execute(
            "INSERT INTO files (path, language, last_hash) VALUES (?, ?, ?)",
            ("src/consts.py", "python", hash_src),
        )
        file_id = int(cur.lastrowid or 0)

        for i in range(count):
            cur = conn.execute(
                "INSERT INTO symbols "
                "(file_id, name, qualified_name, symbol_type, line_start, "
                "line_end, visibility, parent_class) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
                (
                    file_id,
                    f"C{i}",
                    f"consts.C{i}",
                    "constant",
                    i + 1,
                    i + 1,
                    "public",
                ),
            )
            const_id = int(cur.lastrowid or 0)
            conn.execute(
                "INSERT INTO symbol_members (symbol_id, name, value, ordinal) VALUES (?, ?, ?, ?)",
                (const_id, f"C{i}", str(i), 0),
            )
        conn.commit()
    finally:
        graph.close()

    return src


def _seed_many_functions_with_edges(project_root: Path, count: int) -> Path:
    """Seed ``count`` functions each with at least one call edge.

    The caller for every ``fN`` is a non-function symbol (type
    ``class``) so the render helper's ``symbol_type in ("function",
    "method")`` filter skips it and only the N functions count toward
    the truncation limit. Each ``fN`` gets exactly one caller edge so
    the render helper's "skip symbols with no edges" branch still lets
    it through.
    """
    src = _write_source_file(project_root, "src/mod_many.py", "# many functions\n")
    hash_src = hash_file(src)

    graph = open_symbol_graph(project_root)
    conn = graph._conn
    try:
        cur = conn.execute(
            "INSERT INTO files (path, language, last_hash) VALUES (?, ?, ?)",
            ("src/mod_many.py", "python", hash_src),
        )
        file_id = int(cur.lastrowid or 0)

        # Insert a class symbol as the "external" caller. The render
        # helper filters on symbol_type to include only functions and
        # methods, so this class never appears in the rendered block
        # even though it owns every call edge in the fixture.
        cur = conn.execute(
            "INSERT INTO symbols "
            "(file_id, name, qualified_name, symbol_type, line_start, "
            "line_end, visibility, parent_class) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
            (file_id, "Trigger", "mod_many.Trigger", "class", 1, 1, "public"),
        )
        trigger_id = int(cur.lastrowid or 0)

        for i in range(count):
            cur = conn.execute(
                "INSERT INTO symbols "
                "(file_id, name, qualified_name, symbol_type, line_start, "
                "line_end, visibility, parent_class) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
                (
                    file_id,
                    f"f{i}",
                    f"mod_many.f{i}",
                    "function",
                    10 + i,
                    10 + i,
                    "public",
                ),
            )
            fn_id = int(cur.lastrowid or 0)
            conn.execute(
                "INSERT INTO calls (caller_id, callee_id, line, call_context) VALUES (?, ?, ?, ?)",
                (trigger_id, fn_id, 1, "call"),
            )
        conn.commit()
    finally:
        graph.close()

    return src


def _mock_archivist() -> ArchivistService:
    """Create a mock ArchivistService that returns a canned design output."""
    output = DesignFileOutput(
        summary="Handles testing.",
        interface_contract="def foo(): ...",
        dependencies=[],
        tests=None,
        complexity_warning=None,
        wikilinks=[],
        tags=[],
    )
    result = DesignFileResult(
        source_path="mock",
        design_file_output=output,
        error=False,
        error_message=None,
    )
    service = MagicMock(spec=ArchivistService)
    service.generate_design_file = AsyncMock(return_value=result)
    return service


# ---------------------------------------------------------------------------
# 1. render_symbol_graph_context — feature flags
# ---------------------------------------------------------------------------


class TestRenderHelperFeatureFlags:
    """The helper honours ``symbols.enabled`` and the two include flags."""

    def test_service_skips_enrichment_when_symbols_disabled(self, tmp_path: Path) -> None:
        """``symbols.enabled=False`` yields an empty :class:`SymbolGraphPromptContext`.

        The helper does not even need to touch the graph: the whole
        symbol subsystem is off, so both blocks must be ``None``.
        """
        project = _make_project(tmp_path)
        _make_linkgraph(project)
        seeds = _seed_single_enum_fixture(project)

        config = _make_config(
            symbols=SymbolGraphConfig(enabled=False, include_enums=True),
        )

        with SymbolQueryService(project) as svc:
            ctx = render_symbol_graph_context(svc, project, seeds["source_path"], config)

        assert ctx.enums_block is None
        assert ctx.call_paths_block is None

    def test_service_passes_enum_context_when_enabled(self, tmp_path: Path) -> None:
        """With ``include_enums=True`` a single-enum file yields a non-empty block."""
        project = _make_project(tmp_path)
        _make_linkgraph(project)
        seeds = _seed_single_enum_fixture(project)

        config = _make_config(
            symbols=SymbolGraphConfig(enabled=True, include_enums=True),
        )

        with SymbolQueryService(project) as svc:
            ctx = render_symbol_graph_context(svc, project, seeds["source_path"], config)

        assert ctx.enums_block is not None
        assert "Color" in ctx.enums_block
        assert "RED" in ctx.enums_block
        # include_call_paths is False by default so this stays None.
        assert ctx.call_paths_block is None

    def test_service_passes_call_path_context_when_enabled(self, tmp_path: Path) -> None:
        """With ``include_call_paths=True`` a function with edges yields a non-empty block."""
        project = _make_project(tmp_path)
        _make_linkgraph(project)
        seeds = _seed_single_function_with_edges(project)

        config = _make_config(
            symbols=SymbolGraphConfig(
                enabled=True,
                include_enums=False,
                include_call_paths=True,
                call_path_depth=1,
            ),
        )

        with SymbolQueryService(project) as svc:
            ctx = render_symbol_graph_context(svc, project, seeds["source_path"], config)

        # include_enums is off so the enum block stays None.
        assert ctx.enums_block is None
        assert ctx.call_paths_block is not None
        # At minimum the inbound edge from caller should appear on the
        # target's rendered line.
        assert "target" in ctx.call_paths_block
        assert "callers=[" in ctx.call_paths_block


# ---------------------------------------------------------------------------
# 2. render_symbol_graph_context — truncation
# ---------------------------------------------------------------------------


class TestRenderHelperTruncation:
    """The render helpers honour the two ``max_*`` truncation limits."""

    def test_service_enum_block_truncated_at_max_enum_items(self, tmp_path: Path) -> None:
        """Seeding 25 constants with ``max_enum_items=20`` emits ``- ... 5 more``."""
        project = _make_project(tmp_path)
        _make_linkgraph(project)
        source = _seed_many_constants_fixture(project, count=25)

        config = _make_config(
            symbols=SymbolGraphConfig(
                enabled=True,
                include_enums=True,
                max_enum_items=20,
            ),
        )

        with SymbolQueryService(project) as svc:
            ctx = render_symbol_graph_context(svc, project, source, config)

        assert ctx.enums_block is not None
        # 20 visible rows + the "- ... 5 more" marker.
        lines = ctx.enums_block.splitlines()
        assert len(lines) == 21
        assert lines[-1] == "- ... 5 more"
        # The first and twentieth constants are visible; the 21st is not.
        assert "C0" in ctx.enums_block
        assert "C19" in ctx.enums_block
        assert "C20" not in ctx.enums_block

    def test_service_call_path_block_truncated_at_max_call_path_items(
        self,
        tmp_path: Path,
    ) -> None:
        """Seeding 15 edged functions with ``max_call_path_items=10`` emits truncation."""
        project = _make_project(tmp_path)
        _make_linkgraph(project)
        source = _seed_many_functions_with_edges(project, count=15)

        config = _make_config(
            symbols=SymbolGraphConfig(
                enabled=True,
                include_enums=False,
                include_call_paths=True,
                call_path_depth=1,
                max_call_path_items=10,
            ),
        )

        with SymbolQueryService(project) as svc:
            ctx = render_symbol_graph_context(svc, project, source, config)

        assert ctx.call_paths_block is not None
        lines = ctx.call_paths_block.splitlines()
        # 10 visible rows + the "- ... N more" marker. The fixture's
        # caller is a class symbol so it is filtered out of the render
        # pass — exactly 15 functions are eligible, 10 are visible,
        # and 5 overflow.
        assert len(lines) == 11
        assert lines[-1] == "- ... 5 more"


# ---------------------------------------------------------------------------
# 3. update_project — SymbolQueryService is opened exactly once
# ---------------------------------------------------------------------------


class TestPipelineOpensSymbolServiceOnce:
    """``update_project`` opens a single ``SymbolQueryService`` per run."""

    @pytest.mark.asyncio()
    async def test_pipeline_opens_symbol_service_once(self, tmp_path: Path) -> None:
        """Spy on ``SymbolQueryService.__enter__`` across a multi-file run.

        Creates three source files, monkeypatches the design-file loop
        and symbol-graph build for hermeticity, and wraps
        ``SymbolQueryService.__enter__`` in a
        :class:`~unittest.mock.MagicMock` side_effect so the real
        enter still runs. Asserts the spy recorded exactly one call —
        the service must be opened once for the entire pipeline run,
        not once per file.
        """
        _write_source_file(tmp_path, "src/a.py", "def a(): pass")
        _write_source_file(tmp_path, "src/b.py", "def b(): pass")
        _write_source_file(tmp_path, "src/c.py", "def c(): pass")
        (tmp_path / ".lexibrary").mkdir(parents=True, exist_ok=True)

        config = _make_config(
            scope_root="src",
            symbols=SymbolGraphConfig(enabled=True),
        )
        archivist = _mock_archivist()

        async def fake_update_file(
            source_path: Path,
            project_root: Path,
            cfg: LexibraryConfig,
            svc: ArchivistService,
            **kwargs: object,
        ) -> FileResult:
            return FileResult(change=ChangeLevel.UNCHANGED)

        def fake_build_symbol_graph(*args: object, **kwargs: object) -> SymbolBuildResult:
            return SymbolBuildResult(build_type="full")

        real_enter = SymbolQueryService.__enter__
        enter_spy = MagicMock(side_effect=real_enter)

        with (
            patch(
                "lexibrary.archivist.pipeline.update_file",
                side_effect=fake_update_file,
            ),
            patch(
                "lexibrary.symbolgraph.build_symbol_graph",
                side_effect=fake_build_symbol_graph,
            ),
            patch.object(SymbolQueryService, "__enter__", enter_spy),
        ):
            await update_project(tmp_path, config, archivist)

        assert enter_spy.call_count == 1, (
            f"Expected SymbolQueryService to be opened exactly once, "
            f"got {enter_spy.call_count} calls"
        )
