"""Tests for archivist-output tag-count validation (§1.5, Group 10).

Verifies that the archivist pipeline truncates the LLM's ``tags`` list to at
most 3 entries — silently at model-build time, with a warning log naming the
source file and the dropped entries.  The BAML prompt caps tags at 3, but the
pipeline enforces the contract in code so a non-obedient LLM cannot leak
extra tags into the on-disk design file.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from lexibrary.archivist.change_checker import ChangeLevel
from lexibrary.archivist.pipeline import update_file
from lexibrary.archivist.service import ArchivistService, DesignFileResult
from lexibrary.artifacts.design_file_parser import parse_design_file
from lexibrary.baml_client.types import DesignFileOutput
from lexibrary.config.schema import LexibraryConfig, ScopeRoot, TokenBudgetConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_source_file(tmp_path: Path, rel: str, content: str = "print('hi')") -> Path:
    """Create a source file at the given relative path."""
    source = tmp_path / rel
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(content, encoding="utf-8")
    return source


def _make_config() -> LexibraryConfig:
    """Default single-root config rooted at ``.``."""
    return LexibraryConfig(
        scope_roots=[ScopeRoot(path=".")],
        token_budgets=TokenBudgetConfig(design_file_tokens=400),
    )


def _mock_archivist_with_tags(tags: list[str]) -> ArchivistService:
    """Mock ArchivistService whose LLM output carries the given tag list."""
    output = DesignFileOutput(
        summary="Test module.",
        interface_contract="def foo(): ...",
        dependencies=[],
        tests=None,
        complexity_warning=None,
        wikilinks=[],
        tags=tags,
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
# Tag-cap validation
# ---------------------------------------------------------------------------


class TestTagCap:
    """The pipeline caps ``output.tags`` at 3 and logs a warning when it truncates."""

    @pytest.mark.asyncio()
    async def test_five_tags_truncated_to_three(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """5 tags → first 3 kept, warning logged naming file + dropped entries."""
        source_rel = "src/foo.py"
        source = _make_source_file(tmp_path, source_rel, "def bar(): pass")
        config = _make_config()
        archivist = _mock_archivist_with_tags(["a", "b", "c", "d", "e"])

        with caplog.at_level(logging.WARNING, logger="lexibrary.archivist.pipeline"):
            result = await update_file(source, tmp_path, config, archivist)

        assert result.change == ChangeLevel.NEW_FILE
        assert not result.failed

        design_path = tmp_path / ".lexibrary" / "designs" / f"{source_rel}.md"
        parsed = parse_design_file(design_path)
        assert parsed is not None
        assert parsed.tags == ["a", "b", "c"]

        # A warning naming the source file and the dropped entries SHALL be logged.
        matching = [
            r
            for r in caplog.records
            if r.levelno == logging.WARNING
            and "truncating to 3" in r.getMessage()
            and source_rel in r.getMessage()
        ]
        assert matching, (
            "Expected a WARNING log naming the source file and 'truncating to 3'; "
            f"got records: {[r.getMessage() for r in caplog.records]}"
        )
        dropped_message = matching[0].getMessage()
        assert "'d'" in dropped_message
        assert "'e'" in dropped_message

    @pytest.mark.asyncio()
    async def test_two_tags_pass_through_unchanged(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Two tags → both kept, no warning logged."""
        source_rel = "src/foo.py"
        source = _make_source_file(tmp_path, source_rel, "def bar(): pass")
        config = _make_config()
        archivist = _mock_archivist_with_tags(["parser", "cli"])

        with caplog.at_level(logging.WARNING, logger="lexibrary.archivist.pipeline"):
            result = await update_file(source, tmp_path, config, archivist)

        assert result.change == ChangeLevel.NEW_FILE
        design_path = tmp_path / ".lexibrary" / "designs" / f"{source_rel}.md"
        parsed = parse_design_file(design_path)
        assert parsed is not None
        assert parsed.tags == ["parser", "cli"]

        # No truncation warning SHALL be logged on the happy path.
        truncation_warnings = [r for r in caplog.records if "truncating to 3" in r.getMessage()]
        assert truncation_warnings == []

    @pytest.mark.asyncio()
    async def test_empty_tags_preserved_as_empty(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Empty tag list → empty on the model, no warning logged."""
        source_rel = "src/foo.py"
        source = _make_source_file(tmp_path, source_rel, "def bar(): pass")
        config = _make_config()
        archivist = _mock_archivist_with_tags([])

        with caplog.at_level(logging.WARNING, logger="lexibrary.archivist.pipeline"):
            result = await update_file(source, tmp_path, config, archivist)

        assert result.change == ChangeLevel.NEW_FILE
        design_path = tmp_path / ".lexibrary" / "designs" / f"{source_rel}.md"
        parsed = parse_design_file(design_path)
        assert parsed is not None
        assert parsed.tags == []

        truncation_warnings = [r for r in caplog.records if "truncating to 3" in r.getMessage()]
        assert truncation_warnings == []

    @pytest.mark.asyncio()
    async def test_exactly_three_tags_pass_through(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Three tags (the cap) → all kept, no warning logged."""
        source_rel = "src/foo.py"
        source = _make_source_file(tmp_path, source_rel, "def bar(): pass")
        config = _make_config()
        archivist = _mock_archivist_with_tags(["a", "b", "c"])

        with caplog.at_level(logging.WARNING, logger="lexibrary.archivist.pipeline"):
            result = await update_file(source, tmp_path, config, archivist)

        assert result.change == ChangeLevel.NEW_FILE
        design_path = tmp_path / ".lexibrary" / "designs" / f"{source_rel}.md"
        parsed = parse_design_file(design_path)
        assert parsed is not None
        assert parsed.tags == ["a", "b", "c"]

        truncation_warnings = [r for r in caplog.records if "truncating to 3" in r.getMessage()]
        assert truncation_warnings == []
