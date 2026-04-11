"""Tests for symbol graph integration in the archivist pipeline.

Originally covered the Phase 1 no-op wiring added by symbol-graph-1 task
group 9. Symbol-graph-2 (Phase 2) replaced the no-op ``build_symbol_graph``
with a real two-pass full rebuild, so the emptiness assertions below were
relaxed to **non-empty** counts — ``foo`` now becomes a ``symbols`` row and
``src/foo.py`` a ``files`` row on every build. The non-fatal error path,
disabled-config short-circuit, and ``validate_library`` neutrality are
unchanged from Phase 1.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lexibrary.archivist.change_checker import ChangeLevel
from lexibrary.archivist.pipeline import FileResult, update_project
from lexibrary.archivist.service import ArchivistService, DesignFileResult
from lexibrary.baml_client.types import DesignFileOutput
from lexibrary.config.schema import LexibraryConfig, TokenBudgetConfig
from lexibrary.symbolgraph.schema import SCHEMA_VERSION
from lexibrary.utils.paths import symbols_db_path
from lexibrary.validator import validate_library

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_source_file(tmp_path: Path, rel: str, content: str = "print('hello')") -> Path:
    """Create a source file at ``rel`` relative to ``tmp_path``."""
    source = tmp_path / rel
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(content, encoding="utf-8")
    return source


def _make_config(scope_root: str = ".", design_file_tokens: int = 400) -> LexibraryConfig:
    """Create a LexibraryConfig with a given scope_root and small token budget."""
    return LexibraryConfig(
        scope_root=scope_root,
        token_budgets=TokenBudgetConfig(design_file_tokens=design_file_tokens),
    )


def _mock_archivist() -> ArchivistService:
    """Create a mock ArchivistService with a canned design-file output."""
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


async def _fake_unchanged_update_file(
    source_path: Path,
    project_root: Path,
    cfg: LexibraryConfig,
    svc: ArchivistService,
    **kwargs: object,
) -> FileResult:
    """Stand-in for update_file that leaves every file UNCHANGED."""
    return FileResult(change=ChangeLevel.UNCHANGED)


# ---------------------------------------------------------------------------
# 1. update_project builds an empty symbol graph
# ---------------------------------------------------------------------------


class TestUpdateProjectBuildsSymbolGraph:
    """Verify that update_project wires build_symbol_graph into the pipeline."""

    @pytest.mark.asyncio()
    async def test_update_project_builds_symbol_graph(self, tmp_path: Path) -> None:
        """update_project() creates symbols.db with Phase 2 symbol rows."""
        _make_source_file(tmp_path, "src/foo.py", "def foo(): pass")
        (tmp_path / ".lexibrary").mkdir(parents=True, exist_ok=True)

        config = _make_config(scope_root="src")
        archivist = _mock_archivist()

        with patch(
            "lexibrary.archivist.pipeline.update_file",
            side_effect=_fake_unchanged_update_file,
        ):
            stats = await update_project(tmp_path, config, archivist)

        db_path = symbols_db_path(tmp_path)
        assert db_path.exists(), "symbols.db should be created by update_project()"

        # Stats reflect a clean Phase 2 build.
        assert stats.symbolgraph_built is True
        assert stats.symbolgraph_error is None
        # Phase 2 extracts at least one symbol (``foo``) from ``src/foo.py``.
        assert stats.symbolgraph_symbol_count >= 1
        # No call sites in the fixture, so the call count stays at zero.
        assert stats.symbolgraph_call_count == 0

        # Schema is at the current version and core tables have content.
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute(
                "SELECT value FROM meta WHERE key = ?",
                ("schema_version",),
            ).fetchone()
            assert row is not None
            assert int(row[0]) == SCHEMA_VERSION

            files_count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
            assert files_count >= 1

            symbols_count = conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
            assert symbols_count >= 1

            # Phase 2 does not populate class/member tables — those land in
            # Phase 3/4 — so assert they stay empty here.
            for table in (
                "class_edges",
                "symbol_members",
                "class_edges_unresolved",
            ):
                count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                assert count == 0, f"{table} should be empty until Phase 3/4"
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# 2. Build failure is non-fatal
# ---------------------------------------------------------------------------


class TestSymbolGraphBuildFailureIsNonFatal:
    """A failing symbol graph build must not abort update_project()."""

    @pytest.mark.asyncio()
    async def test_symbolgraph_build_failure_is_non_fatal(self, tmp_path: Path) -> None:
        """When build_symbol_graph raises, stats record the failure."""
        _make_source_file(tmp_path, "src/a.py", "# a")
        (tmp_path / ".lexibrary").mkdir(parents=True, exist_ok=True)

        config = _make_config(scope_root="src")
        archivist = _mock_archivist()

        with (
            patch(
                "lexibrary.archivist.pipeline.update_file",
                side_effect=_fake_unchanged_update_file,
            ),
            patch(
                "lexibrary.symbolgraph.build_symbol_graph",
                side_effect=RuntimeError("SQLite disk full"),
            ),
        ):
            stats = await update_project(tmp_path, config, archivist)

        assert stats.symbolgraph_built is False
        assert stats.symbolgraph_error is not None
        assert "failed" in stats.symbolgraph_error.lower()

        # Design file + link graph stats should still be accurate.
        assert stats.files_scanned == 1
        # Link graph runs before the symbol graph, so it should still be built.
        assert stats.linkgraph_built is True
        assert stats.linkgraph_error is None

        # Symbol graph error is captured on error_summary under the right phase.
        phases = {record.phase for record in stats.error_summary.records}
        assert "symbolgraph" in phases


# ---------------------------------------------------------------------------
# 3. Disabled config skips DB creation
# ---------------------------------------------------------------------------


class TestSymbolGraphDisabledSkipsDBCreation:
    """A disabled symbols config must not create symbols.db."""

    @pytest.mark.asyncio()
    async def test_symbolgraph_disabled_skips_db_creation(self, tmp_path: Path) -> None:
        """config.symbols.enabled=False skips symbol graph work entirely."""
        _make_source_file(tmp_path, "src/foo.py", "def foo(): pass")
        (tmp_path / ".lexibrary").mkdir(parents=True, exist_ok=True)

        config = _make_config(scope_root="src")
        config.symbols.enabled = False
        archivist = _mock_archivist()

        with patch(
            "lexibrary.archivist.pipeline.update_file",
            side_effect=_fake_unchanged_update_file,
        ):
            stats = await update_project(tmp_path, config, archivist)

        db_path = symbols_db_path(tmp_path)
        assert not db_path.exists(), "symbols.db must not be created when disabled"

        # The pipeline still reports a successful build — build_symbol_graph
        # returns an empty result object when short-circuited.
        assert stats.symbolgraph_built is True
        assert stats.symbolgraph_error is None
        assert stats.symbolgraph_symbol_count == 0
        assert stats.symbolgraph_call_count == 0


# ---------------------------------------------------------------------------
# 4. Existing library without symbols.db gets one created
# ---------------------------------------------------------------------------


class TestBuildSymbolGraphOnExistingLibrary:
    """Running update_project on an existing library brings symbols.db up to v1."""

    @pytest.mark.asyncio()
    async def test_build_symbol_graph_on_existing_library_without_symbols_db(
        self,
        tmp_path: Path,
    ) -> None:
        """An existing .lexibrary with only index.db gains a v1 symbols.db."""
        _make_source_file(tmp_path, "src/foo.py", "def foo(): pass")
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir(parents=True, exist_ok=True)

        # Simulate an older project: only index.db exists (stub it as a file).
        index_db_stub = lexibrary_dir / "index.db"
        index_db_stub.write_bytes(b"")  # empty file is fine — the link graph
        # rebuild overwrites it with real SQLite content during update_project.

        symbols_db = symbols_db_path(tmp_path)
        assert not symbols_db.exists()

        config = _make_config(scope_root="src")
        archivist = _mock_archivist()

        with patch(
            "lexibrary.archivist.pipeline.update_file",
            side_effect=_fake_unchanged_update_file,
        ):
            stats = await update_project(tmp_path, config, archivist)

        assert symbols_db.exists(), "symbols.db should be created on first run"
        assert stats.symbolgraph_built is True
        assert stats.symbolgraph_error is None

        # Schema version and Phase 2 content checks.
        conn = sqlite3.connect(symbols_db)
        try:
            version_row = conn.execute(
                "SELECT value FROM meta WHERE key = ?",
                ("schema_version",),
            ).fetchone()
            assert version_row is not None
            assert int(version_row[0]) == SCHEMA_VERSION

            built_at_row = conn.execute(
                "SELECT value FROM meta WHERE key = ?",
                ("built_at",),
            ).fetchone()
            assert built_at_row is not None
            assert built_at_row[0]  # non-empty ISO timestamp

            # Phase 2 populates ``files`` and ``symbols`` — the ``foo``
            # fixture yields at least one of each.
            files_count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
            assert files_count >= 1

            symbols_count = conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
            assert symbols_count >= 1

            # Class/member tables remain empty until Phase 3/4.
            for table in (
                "class_edges",
                "symbol_members",
                "class_edges_unresolved",
            ):
                count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                assert count == 0
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# 5. validate_library ignores symbols.db
# ---------------------------------------------------------------------------


def _write_minimal_config(lexibrary_dir: Path) -> None:
    """Write the smallest config.yaml the validator will accept."""
    config_path = lexibrary_dir / "config.yaml"
    config_path.write_text("scope_root: .\n", encoding="utf-8")


class TestLexiValidateIgnoresSymbolsDB:
    """validate_library should not add issues on account of symbols.db."""

    def test_lexi_validate_ignores_symbols_db(self, tmp_path: Path) -> None:
        """A .lexibrary with an empty symbols.db produces no extra issues."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir(parents=True, exist_ok=True)
        _write_minimal_config(lexibrary_dir)

        # Create the required subdirectories so every validation check loads
        # its source without raising.
        (lexibrary_dir / "designs").mkdir(parents=True, exist_ok=True)
        (lexibrary_dir / "concepts").mkdir(parents=True, exist_ok=True)
        (lexibrary_dir / "conventions").mkdir(parents=True, exist_ok=True)
        (lexibrary_dir / "playbooks").mkdir(parents=True, exist_ok=True)

        # Populate an empty symbols.db via the builder directly.
        from lexibrary.symbolgraph import build_symbol_graph  # noqa: PLC0415

        config = LexibraryConfig(scope_root=".")
        build_symbol_graph(project_root, config)
        assert symbols_db_path(project_root).exists()

        # Baseline: collect any issues the validator would report WITHOUT the
        # symbols.db file, by temporarily renaming it, running the validator,
        # then restoring.
        symbols_db = symbols_db_path(project_root)
        baseline_backup = symbols_db.with_suffix(symbols_db.suffix + ".bak")
        symbols_db.rename(baseline_backup)
        baseline_report = validate_library(project_root, lexibrary_dir)
        baseline_ids = {issue.check for issue in baseline_report.issues}
        baseline_backup.rename(symbols_db)

        # With symbols.db present, the set of checks producing issues must not
        # grow. An empty symbols.db must not trigger any check that wasn't
        # already triggered by the baseline empty-project run.
        report_with_db = validate_library(project_root, lexibrary_dir)
        with_db_ids = {issue.check for issue in report_with_db.issues}
        new_checks = with_db_ids - baseline_ids
        assert not new_checks, (
            f"Validator gained new issues when symbols.db was present: {new_checks}"
        )
