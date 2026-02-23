"""Tests for START_HERE.md generation."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lexibrary.archivist.service import (
    ArchivistService,
)
from lexibrary.archivist.start_here import (
    _build_directory_tree,
    _collect_aindex_summaries,
    _count_tokens_approx,
    generate_start_here,
)
from lexibrary.artifacts.aindex import AIndexEntry, AIndexFile
from lexibrary.artifacts.aindex_serializer import serialize_aindex
from lexibrary.artifacts.design_file import StalenessMetadata
from lexibrary.baml_client.types import StartHereOutput
from lexibrary.config.schema import LexibraryConfig, TokenBudgetConfig
from lexibrary.llm.rate_limiter import RateLimiter
from lexibrary.utils.paths import LEXIBRARY_DIR

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_aindex_file(directory_path: str, billboard: str) -> str:
    """Create a serialized .aindex file with the given directory path and billboard."""
    meta = StalenessMetadata(
        source=directory_path,
        source_hash="abc123",
        generated=datetime(2025, 1, 1, tzinfo=UTC),
        generator="test",
    )
    aindex = AIndexFile(
        directory_path=directory_path,
        billboard=billboard,
        entries=[
            AIndexEntry(name="example.py", entry_type="file", description="Example file"),
        ],
        metadata=meta,
    )
    return serialize_aindex(aindex)


def _make_sample_output() -> StartHereOutput:
    """Create a sample StartHereOutput for mocked LLM responses."""
    return StartHereOutput(
        topology="src/\n  core/\n  utils/",
        ontology="**design file** -- per-file documentation artifact",
        navigation_by_intent="| Task | Read first |\n| --- | --- |\n| Config | src/config/ |",
        convention_index="- snake_case for all modules",
        navigation_protocol="- Read the design file before editing any source file",
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def project_dir(tmp_path: Path) -> Path:
    """Create a minimal project structure for testing."""
    # Create source directories
    (tmp_path / "src" / "core").mkdir(parents=True)
    (tmp_path / "src" / "utils").mkdir(parents=True)
    (tmp_path / "tests").mkdir()

    # Create some source files
    (tmp_path / "src" / "core" / "main.py").write_text("# main module\n")
    (tmp_path / "src" / "utils" / "helpers.py").write_text("# helpers\n")
    (tmp_path / "tests" / "test_main.py").write_text("# tests\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n")

    # Create .lexibrary directory
    (tmp_path / LEXIBRARY_DIR).mkdir()

    return tmp_path


@pytest.fixture()
def project_with_aindex(project_dir: Path) -> Path:
    """Project with .aindex files in the mirror tree."""
    # Create mirror .aindex files
    mirror_src = project_dir / LEXIBRARY_DIR / "src"
    mirror_src.mkdir(parents=True)
    (mirror_src / ".aindex").write_text(_make_aindex_file("src", "Main source code directory"))

    mirror_core = mirror_src / "core"
    mirror_core.mkdir()
    (mirror_core / ".aindex").write_text(_make_aindex_file("src/core", "Core business logic"))

    mirror_utils = mirror_src / "utils"
    mirror_utils.mkdir()
    (mirror_utils / ".aindex").write_text(
        _make_aindex_file("src/utils", "Shared utility functions")
    )

    return project_dir


@pytest.fixture()
def config() -> LexibraryConfig:
    """Default configuration."""
    return LexibraryConfig()


@pytest.fixture()
def archivist_service() -> ArchivistService:
    """Archivist service with mocked internals."""
    limiter = RateLimiter(requests_per_minute=6000)
    from lexibrary.config.schema import LLMConfig

    return ArchivistService(rate_limiter=limiter, config=LLMConfig())


# ---------------------------------------------------------------------------
# _build_directory_tree
# ---------------------------------------------------------------------------


class TestBuildDirectoryTree:
    """Verify directory tree construction."""

    def test_basic_tree(self, project_dir: Path, config: LexibraryConfig) -> None:
        tree = _build_directory_tree(project_dir, config)
        assert "src/" in tree
        assert "tests/" in tree
        assert "pyproject.toml" in tree

    def test_excludes_lexibrary_directory(self, project_dir: Path, config: LexibraryConfig) -> None:
        tree = _build_directory_tree(project_dir, config)
        assert LEXIBRARY_DIR not in tree
        assert ".lexibrary" not in tree

    def test_excludes_git_directory(self, project_dir: Path, config: LexibraryConfig) -> None:
        (project_dir / ".git").mkdir()
        tree = _build_directory_tree(project_dir, config)
        assert ".git" not in tree

    def test_nested_directories(self, project_dir: Path, config: LexibraryConfig) -> None:
        tree = _build_directory_tree(project_dir, config)
        assert "core/" in tree
        assert "utils/" in tree
        assert "main.py" in tree
        assert "helpers.py" in tree

    def test_starts_with_project_name(self, project_dir: Path, config: LexibraryConfig) -> None:
        tree = _build_directory_tree(project_dir, config)
        first_line = tree.splitlines()[0]
        assert first_line == f"{project_dir.name}/"


# ---------------------------------------------------------------------------
# _collect_aindex_summaries
# ---------------------------------------------------------------------------


class TestCollectAindexSummaries:
    """Verify .aindex billboard summary collection."""

    def test_collects_all_summaries(self, project_with_aindex: Path) -> None:
        summaries = _collect_aindex_summaries(project_with_aindex)
        assert "src: Main source code directory" in summaries
        assert "src/core: Core business logic" in summaries
        assert "src/utils: Shared utility functions" in summaries

    def test_empty_when_no_lexibrary(self, tmp_path: Path) -> None:
        summaries = _collect_aindex_summaries(tmp_path)
        assert summaries == ""

    def test_empty_when_no_aindex_files(self, project_dir: Path) -> None:
        # .lexibrary exists but has no .aindex files
        summaries = _collect_aindex_summaries(project_dir)
        assert summaries == ""

    def test_excludes_malformed_aindex(self, project_dir: Path) -> None:
        mirror = project_dir / LEXIBRARY_DIR / "bad"
        mirror.mkdir()
        (mirror / ".aindex").write_text("not a valid aindex file\n")
        summaries = _collect_aindex_summaries(project_dir)
        # Malformed file should be skipped, resulting in empty output
        assert summaries == ""


# ---------------------------------------------------------------------------
# generate_start_here
# ---------------------------------------------------------------------------


class TestGenerateStartHere:
    """Verify the full generate_start_here pipeline."""

    @pytest.mark.asyncio()
    async def test_generates_start_here(
        self,
        project_with_aindex: Path,
        config: LexibraryConfig,
        archivist_service: ArchivistService,
    ) -> None:
        sample_output = _make_sample_output()
        mock_client = MagicMock()
        mock_client.ArchivistGenerateStartHere = AsyncMock(return_value=sample_output)

        with patch.object(archivist_service, "_get_baml_client", return_value=mock_client):
            result_path = await generate_start_here(project_with_aindex, config, archivist_service)

        assert result_path.exists()
        content = result_path.read_text(encoding="utf-8")
        assert "# START HERE" in content
        assert "## Project Topology" in content
        assert "## Ontology" in content
        assert "## Navigation by Intent" in content
        assert "## Convention Index" in content
        assert "## Navigation Protocol" in content
        assert sample_output.topology in content

    @pytest.mark.asyncio()
    async def test_collects_summaries_for_llm(
        self,
        project_with_aindex: Path,
        config: LexibraryConfig,
        archivist_service: ArchivistService,
    ) -> None:
        sample_output = _make_sample_output()
        mock_client = MagicMock()
        mock_client.ArchivistGenerateStartHere = AsyncMock(return_value=sample_output)

        with patch.object(archivist_service, "_get_baml_client", return_value=mock_client):
            await generate_start_here(project_with_aindex, config, archivist_service)

        # Verify the LLM was called with .aindex summaries
        call_kwargs = mock_client.ArchivistGenerateStartHere.call_args
        assert "Core business logic" in call_kwargs.kwargs.get(
            "aindex_summaries", ""
        ) or "Core business logic" in str(call_kwargs)

    @pytest.mark.asyncio()
    async def test_excludes_lexibrary_from_tree(
        self,
        project_with_aindex: Path,
        config: LexibraryConfig,
        archivist_service: ArchivistService,
    ) -> None:
        sample_output = _make_sample_output()
        mock_client = MagicMock()
        mock_client.ArchivistGenerateStartHere = AsyncMock(return_value=sample_output)

        with patch.object(archivist_service, "_get_baml_client", return_value=mock_client):
            await generate_start_here(project_with_aindex, config, archivist_service)

        # Verify the directory tree passed to LLM does not contain .lexibrary
        call_kwargs = mock_client.ArchivistGenerateStartHere.call_args
        directory_tree = call_kwargs.kwargs.get("directory_tree", "")
        assert ".lexibrary" not in directory_tree

    @pytest.mark.asyncio()
    async def test_token_budget_warning(
        self,
        project_dir: Path,
        archivist_service: ArchivistService,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        # Set a very small token budget to trigger the warning
        config = LexibraryConfig(token_budgets=TokenBudgetConfig(start_here_tokens=5))

        sample_output = _make_sample_output()
        mock_client = MagicMock()
        mock_client.ArchivistGenerateStartHere = AsyncMock(return_value=sample_output)

        import logging

        with (
            caplog.at_level(logging.WARNING, logger="lexibrary.archivist.start_here"),
            patch.object(archivist_service, "_get_baml_client", return_value=mock_client),
        ):
            await generate_start_here(project_dir, config, archivist_service)

        assert any("exceeds token budget" in record.message for record in caplog.records)

    @pytest.mark.asyncio()
    async def test_llm_error_raises(
        self,
        project_dir: Path,
        config: LexibraryConfig,
        archivist_service: ArchivistService,
    ) -> None:
        mock_client = MagicMock()
        mock_client.ArchivistGenerateStartHere = AsyncMock(side_effect=RuntimeError("LLM down"))

        with (
            patch.object(archivist_service, "_get_baml_client", return_value=mock_client),
            pytest.raises(RuntimeError, match="Failed to generate START_HERE.md"),
        ):
            await generate_start_here(project_dir, config, archivist_service)

    @pytest.mark.asyncio()
    async def test_reads_existing_start_here(
        self,
        project_dir: Path,
        config: LexibraryConfig,
        archivist_service: ArchivistService,
    ) -> None:
        # Write an existing START_HERE.md
        start_here_path = project_dir / LEXIBRARY_DIR / "START_HERE.md"
        start_here_path.write_text("# Existing content\n", encoding="utf-8")

        sample_output = _make_sample_output()
        mock_client = MagicMock()
        mock_client.ArchivistGenerateStartHere = AsyncMock(return_value=sample_output)

        with patch.object(archivist_service, "_get_baml_client", return_value=mock_client):
            await generate_start_here(project_dir, config, archivist_service)

        # Verify existing content was passed to LLM
        call_kwargs = mock_client.ArchivistGenerateStartHere.call_args
        existing = call_kwargs.kwargs.get("existing_start_here", "")
        assert "Existing content" in existing

    @pytest.mark.asyncio()
    async def test_writes_to_lexibrary_dir(
        self,
        project_dir: Path,
        config: LexibraryConfig,
        archivist_service: ArchivistService,
    ) -> None:
        sample_output = _make_sample_output()
        mock_client = MagicMock()
        mock_client.ArchivistGenerateStartHere = AsyncMock(return_value=sample_output)

        with patch.object(archivist_service, "_get_baml_client", return_value=mock_client):
            result_path = await generate_start_here(project_dir, config, archivist_service)

        expected_path = project_dir / LEXIBRARY_DIR / "START_HERE.md"
        assert result_path == expected_path
        assert expected_path.exists()


# ---------------------------------------------------------------------------
# _count_tokens_approx
# ---------------------------------------------------------------------------


class TestCountTokensApprox:
    """Verify approximate token counting."""

    def test_empty_string(self) -> None:
        assert _count_tokens_approx("") == 0  # "".split() == []

    def test_simple_words(self) -> None:
        assert _count_tokens_approx("hello world foo bar") == 4

    def test_multiline(self) -> None:
        text = "line one\nline two\nline three"
        assert _count_tokens_approx(text) == 6
