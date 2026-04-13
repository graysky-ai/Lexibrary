"""Tests for archivist pipeline section-preservation (curator-1 group 7).

Covers:
- Task 7.1: Curator-authored file regenerated with preserved Insights section.
- Task 7.2: Frontmatter guard rejects invalid updated_by without LLM call.
- Task 7.3: Integration scenarios.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from lexibrary.archivist.change_checker import ChangeLevel
from lexibrary.archivist.pipeline import (
    _check_invalid_updated_by,
    update_file,
)
from lexibrary.archivist.service import (
    ArchivistService,
    DesignFileResult,
)
from lexibrary.artifacts.design_file_parser import parse_design_file
from lexibrary.baml_client.types import DesignFileOutput
from lexibrary.config.schema import LexibraryConfig, TokenBudgetConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _make_source_file(tmp_path: Path, rel: str, content: str = "print('hello')") -> Path:
    """Create a source file at the given relative path."""
    source = tmp_path / rel
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(content, encoding="utf-8")
    return source


def _make_design_file(
    tmp_path: Path,
    source_rel: str,
    *,
    source_hash: str = "src_hash_aaa",
    interface_hash: str | None = None,
    design_hash: str | None = None,
    body: str | None = None,
    updated_by: str = "archivist",
    include_footer: bool = True,
    description: str = "Test file.",
) -> Path:
    """Create a design file at the mirror path within tmp_path."""
    design_dir = tmp_path / ".lexibrary" / "designs" / Path(source_rel).parent
    design_dir.mkdir(parents=True, exist_ok=True)
    design_path = tmp_path / ".lexibrary" / "designs" / f"{source_rel}.md"

    if body is None:
        body = (
            "---\n"
            f"description: {description}\n"
            "id: DS-001\n"
            f"updated_by: {updated_by}\n"
            "---\n"
            "\n"
            f"# {source_rel}\n"
            "\n"
            "## Interface Contract\n"
            "\n"
            "```python\ndef foo(): ...\n```\n"
            "\n"
            "## Dependencies\n"
            "\n"
            "(none)\n"
            "\n"
            "## Dependents\n"
            "\n"
            "(none)\n"
        )

    if include_footer:
        if design_hash is None:
            design_hash = _sha256(body.rstrip("\n"))

        footer_lines = [
            "<!-- lexibrary:meta",
            f"source: {source_rel}",
            f"source_hash: {source_hash}",
        ]
        if interface_hash is not None:
            footer_lines.append(f"interface_hash: {interface_hash}")
        footer_lines.append(f"design_hash: {design_hash}")
        footer_lines.append("generated: 2026-01-01T12:00:00")
        footer_lines.append("generator: lexibrary-v2")
        footer_lines.append("-->")

        text = body + "\n" + "\n".join(footer_lines) + "\n"
    else:
        text = body

    design_path.write_text(text, encoding="utf-8")
    return design_path


def _make_design_file_with_insights(
    tmp_path: Path,
    source_rel: str,
    *,
    source_hash: str = "src_hash_aaa",
    updated_by: str = "curator",
    insights_content: str = "This module has a subtle coupling to the config loader.",
) -> Path:
    """Create a design file that includes a preserved ## Insights section."""
    body = (
        "---\n"
        f"description: Test file.\n"
        "id: DS-001\n"
        f"updated_by: {updated_by}\n"
        "---\n"
        "\n"
        f"# {source_rel}\n"
        "\n"
        "## Interface Contract\n"
        "\n"
        "```python\ndef foo(): ...\n```\n"
        "\n"
        "## Dependencies\n"
        "\n"
        "(none)\n"
        "\n"
        "## Dependents\n"
        "\n"
        "(none)\n"
        "\n"
        "## Insights\n"
        "\n"
        f"{insights_content}\n"
    )

    design_hash = _sha256(body.rstrip("\n"))
    footer = (
        f"\n<!-- lexibrary:meta\n"
        f"source: {source_rel}\n"
        f"source_hash: {source_hash}\n"
        f"design_hash: {design_hash}\n"
        f"generated: 2026-01-01T12:00:00\n"
        f"generator: lexibrary-v2\n"
        f"-->\n"
    )
    text = body + footer

    design_dir = tmp_path / ".lexibrary" / "designs" / Path(source_rel).parent
    design_dir.mkdir(parents=True, exist_ok=True)
    design_path = tmp_path / ".lexibrary" / "designs" / f"{source_rel}.md"
    design_path.write_text(text, encoding="utf-8")
    return design_path


def _make_config(scope_root: str = ".", design_file_tokens: int = 400) -> LexibraryConfig:
    return LexibraryConfig(
        scope_roots=[ScopeRoot(path=scope_root)],
        token_budgets=TokenBudgetConfig(design_file_tokens=design_file_tokens),
    )


def _mock_archivist(
    summary: str = "Handles testing.",
    interface_contract: str = "def foo(): ...",
    error: bool = False,
) -> ArchivistService:
    """Create a mock ArchivistService that returns a canned design file output."""
    output = DesignFileOutput(
        summary=summary,
        interface_contract=interface_contract,
        dependencies=[],
        tests=None,
        complexity_warning=None,
        wikilinks=[],
        tags=[],
    )

    result = DesignFileResult(
        source_path="mock",
        design_file_output=None if error else output,
        error=error,
        error_message="LLM error" if error else None,
    )

    service = MagicMock(spec=ArchivistService)
    service.generate_design_file = AsyncMock(return_value=result)
    return service


# ---------------------------------------------------------------------------
# _check_invalid_updated_by helper
# ---------------------------------------------------------------------------


class TestCheckInvalidUpdatedBy:
    """Unit tests for the _check_invalid_updated_by helper."""

    _VALID = {
        "archivist",
        "agent",
        "bootstrap-quick",
        "maintainer",
        "curator",
        "skeleton-fallback",
    }

    def test_valid_archivist_returns_none(self, tmp_path: Path) -> None:
        _make_design_file(tmp_path, "src/foo.py", updated_by="archivist")
        design_path = tmp_path / ".lexibrary" / "designs" / "src" / "foo.py.md"
        assert _check_invalid_updated_by(design_path, self._VALID) is None

    def test_valid_curator_returns_none(self, tmp_path: Path) -> None:
        _make_design_file(tmp_path, "src/foo.py", updated_by="curator")
        design_path = tmp_path / ".lexibrary" / "designs" / "src" / "foo.py.md"
        assert _check_invalid_updated_by(design_path, self._VALID) is None

    def test_valid_agent_returns_none(self, tmp_path: Path) -> None:
        _make_design_file(tmp_path, "src/foo.py", updated_by="agent")
        design_path = tmp_path / ".lexibrary" / "designs" / "src" / "foo.py.md"
        assert _check_invalid_updated_by(design_path, self._VALID) is None

    def test_valid_maintainer_returns_none(self, tmp_path: Path) -> None:
        _make_design_file(tmp_path, "src/foo.py", updated_by="maintainer")
        design_path = tmp_path / ".lexibrary" / "designs" / "src" / "foo.py.md"
        assert _check_invalid_updated_by(design_path, self._VALID) is None

    def test_valid_bootstrap_quick_returns_none(self, tmp_path: Path) -> None:
        _make_design_file(tmp_path, "src/foo.py", updated_by="bootstrap-quick")
        design_path = tmp_path / ".lexibrary" / "designs" / "src" / "foo.py.md"
        assert _check_invalid_updated_by(design_path, self._VALID) is None

    def test_valid_skeleton_fallback_returns_none(self, tmp_path: Path) -> None:
        _make_design_file(tmp_path, "src/foo.py", updated_by="skeleton-fallback")
        design_path = tmp_path / ".lexibrary" / "designs" / "src" / "foo.py.md"
        assert _check_invalid_updated_by(design_path, self._VALID) is None

    def test_invalid_value_returns_string(self, tmp_path: Path) -> None:
        _make_design_file(tmp_path, "src/foo.py", updated_by="alien")
        design_path = tmp_path / ".lexibrary" / "designs" / "src" / "foo.py.md"
        result = _check_invalid_updated_by(design_path, self._VALID)
        assert result == "alien"

    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        design_path = tmp_path / "nonexistent.md"
        assert _check_invalid_updated_by(design_path, self._VALID) is None

    def test_no_frontmatter_returns_none(self, tmp_path: Path) -> None:
        design_path = tmp_path / "no_frontmatter.md"
        design_path.write_text("# Just a heading\n\nSome content.\n")
        assert _check_invalid_updated_by(design_path, self._VALID) is None

    def test_no_updated_by_field_returns_none(self, tmp_path: Path) -> None:
        """Frontmatter without updated_by field is not flagged as invalid."""
        design_path = tmp_path / "no_updated_by.md"
        design_path.write_text("---\ndescription: A file.\nid: DS-001\n---\n\n# src/foo.py\n")
        assert _check_invalid_updated_by(design_path, self._VALID) is None


# ---------------------------------------------------------------------------
# Frontmatter guard: invalid updated_by rejects without LLM call
# ---------------------------------------------------------------------------


class TestFrontmatterGuard:
    """Task 7.2: Invalid updated_by returns failed without LLM call."""

    @pytest.mark.asyncio()
    async def test_invalid_updated_by_returns_failed(self, tmp_path: Path) -> None:
        """Design file with invalid updated_by produces failed FileResult, no LLM call."""
        source_rel = "src/foo.py"
        source = _make_source_file(tmp_path, source_rel, "def bar(): pass")

        # Create design file with an invalid updated_by value.
        # Since Pydantic would reject this, we write raw markdown directly.
        _make_design_file(tmp_path, source_rel, updated_by="alien")

        config = _make_config()
        archivist = _mock_archivist()

        result = await update_file(source, tmp_path, config, archivist)

        assert result.failed is True
        assert result.failure_reason is not None
        assert "invalid updated_by" in result.failure_reason
        assert "Curator" in result.failure_reason
        # LLM was NOT called
        archivist.generate_design_file.assert_not_awaited()

    @pytest.mark.asyncio()
    async def test_valid_updated_by_proceeds_normally(self, tmp_path: Path) -> None:
        """Design file with valid updated_by proceeds past the guard to LLM."""
        source_rel = "src/foo.py"
        source = _make_source_file(tmp_path, source_rel, "def bar(): pass")

        # Create design file with valid updated_by but stale hash (triggers LLM path)
        _make_design_file(
            tmp_path,
            source_rel,
            source_hash="stale_hash",
            updated_by="archivist",
        )

        config = _make_config()
        archivist = _mock_archivist()

        result = await update_file(source, tmp_path, config, archivist)

        assert not result.failed
        # LLM was called (file is stale)
        archivist.generate_design_file.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_valid_curator_updated_by_proceeds(self, tmp_path: Path) -> None:
        """Design file with updated_by='curator' proceeds past the guard."""
        source_rel = "src/foo.py"
        source = _make_source_file(tmp_path, source_rel, "def bar(): pass")

        _make_design_file(
            tmp_path,
            source_rel,
            source_hash="stale_hash",
            updated_by="curator",
        )

        config = _make_config()
        archivist = _mock_archivist()

        result = await update_file(source, tmp_path, config, archivist)

        assert not result.failed
        archivist.generate_design_file.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_error_message_mentions_curator(self, tmp_path: Path) -> None:
        """The failure reason for invalid updated_by mentions the Curator."""
        source_rel = "src/foo.py"
        source = _make_source_file(tmp_path, source_rel, "def bar(): pass")

        _make_design_file(tmp_path, source_rel, updated_by="rogue_tool")

        config = _make_config()
        archivist = _mock_archivist()

        result = await update_file(source, tmp_path, config, archivist)

        assert result.failed is True
        assert result.failure_reason is not None
        assert "Curator" in result.failure_reason
        assert "rogue_tool" in result.failure_reason

    @pytest.mark.asyncio()
    async def test_no_existing_design_file_no_guard_trigger(self, tmp_path: Path) -> None:
        """When no design file exists, the guard does not trigger."""
        source_rel = "src/foo.py"
        source = _make_source_file(tmp_path, source_rel, "def bar(): pass")

        config = _make_config()
        archivist = _mock_archivist()

        result = await update_file(source, tmp_path, config, archivist)

        # New file: no guard issue, LLM was called
        assert not result.failed
        assert result.change == ChangeLevel.NEW_FILE
        archivist.generate_design_file.assert_awaited_once()


# ---------------------------------------------------------------------------
# Preserved sections: update_file preserves Insights on regeneration
# ---------------------------------------------------------------------------


class TestPreservedSectionsInPipeline:
    """Task 7.1: When archivist regenerates a file with preserved_sections,
    they are carried over into the new design file."""

    @pytest.mark.asyncio()
    async def test_curator_file_regenerated_with_insights_preserved(self, tmp_path: Path) -> None:
        """Curator-authored design file retains its Insights section after regen."""
        source_rel = "src/foo.py"
        source = _make_source_file(tmp_path, source_rel, "def bar(): pass")

        insights_text = "This module has a subtle coupling to the config loader."
        _make_design_file_with_insights(
            tmp_path,
            source_rel,
            source_hash="stale_hash",
            updated_by="curator",
            insights_content=insights_text,
        )

        config = _make_config()
        archivist = _mock_archivist(summary="Updated summary.")

        result = await update_file(source, tmp_path, config, archivist)

        assert not result.failed
        archivist.generate_design_file.assert_awaited_once()

        # Read back the regenerated design file
        design_path = tmp_path / ".lexibrary" / "designs" / "src" / "foo.py.md"
        content = design_path.read_text()

        # Insights section should be preserved
        assert "## Insights" in content
        assert insights_text in content
        # Mechanical sections were regenerated
        assert "Updated summary." in content

    @pytest.mark.asyncio()
    async def test_archivist_file_no_insights_fully_regenerated(self, tmp_path: Path) -> None:
        """Archivist-authored file without Insights is fully regenerated (no extra sections)."""
        source_rel = "src/foo.py"
        source = _make_source_file(tmp_path, source_rel, "def bar(): pass")

        _make_design_file(
            tmp_path,
            source_rel,
            source_hash="stale_hash",
            updated_by="archivist",
        )

        config = _make_config()
        archivist = _mock_archivist(summary="Regenerated content.")

        result = await update_file(source, tmp_path, config, archivist)

        assert not result.failed
        archivist.generate_design_file.assert_awaited_once()

        design_path = tmp_path / ".lexibrary" / "designs" / "src" / "foo.py.md"
        content = design_path.read_text()

        # No Insights section should appear
        assert "## Insights" not in content
        assert "Regenerated content." in content

    @pytest.mark.asyncio()
    async def test_preserved_insights_referencing_deleted_function_still_kept(
        self, tmp_path: Path
    ) -> None:
        """Preserved Insights that reference deleted code are still preserved.

        Staleness of Insights content is the Curator's job, not the archivist's.
        """
        source_rel = "src/foo.py"
        # Source no longer has the function mentioned in Insights
        source = _make_source_file(tmp_path, source_rel, "def new_function(): pass")

        stale_insight = "The old_function() method has a bug that causes data loss."
        _make_design_file_with_insights(
            tmp_path,
            source_rel,
            source_hash="stale_hash",
            updated_by="curator",
            insights_content=stale_insight,
        )

        config = _make_config()
        archivist = _mock_archivist(summary="New module summary.")

        result = await update_file(source, tmp_path, config, archivist)

        assert not result.failed
        design_path = tmp_path / ".lexibrary" / "designs" / "src" / "foo.py.md"
        content = design_path.read_text()

        # Stale insight is preserved (not the archivist's job to validate)
        assert "## Insights" in content
        assert stale_insight in content

    @pytest.mark.asyncio()
    async def test_preserved_sections_are_parseable_after_regen(self, tmp_path: Path) -> None:
        """After regeneration, the design file with preserved sections can be parsed."""
        source_rel = "src/foo.py"
        source = _make_source_file(tmp_path, source_rel, "def bar(): pass")

        insights_text = "Key architectural insight."
        _make_design_file_with_insights(
            tmp_path,
            source_rel,
            source_hash="stale_hash",
            updated_by="curator",
            insights_content=insights_text,
        )

        config = _make_config()
        archivist = _mock_archivist()

        await update_file(source, tmp_path, config, archivist)

        # Parse the regenerated file
        design_path = tmp_path / ".lexibrary" / "designs" / "src" / "foo.py.md"
        parsed = parse_design_file(design_path)
        assert parsed is not None
        assert "Insights" in parsed.preserved_sections
        assert insights_text in parsed.preserved_sections["Insights"]

    @pytest.mark.asyncio()
    async def test_multiple_preserved_sections_carried_over(self, tmp_path: Path) -> None:
        """Multiple preserved sections (Insights + Notes) are all carried over."""
        source_rel = "src/foo.py"
        source = _make_source_file(tmp_path, source_rel, "def bar(): pass")

        body = (
            "---\n"
            "description: Test file.\n"
            "id: DS-001\n"
            "updated_by: curator\n"
            "---\n"
            "\n"
            f"# {source_rel}\n"
            "\n"
            "## Interface Contract\n"
            "\n"
            "```python\ndef foo(): ...\n```\n"
            "\n"
            "## Dependencies\n"
            "\n"
            "(none)\n"
            "\n"
            "## Dependents\n"
            "\n"
            "(none)\n"
            "\n"
            "## Insights\n"
            "\n"
            "First insight about coupling.\n"
            "\n"
            "## Notes\n"
            "\n"
            "Additional context about this module.\n"
        )
        design_hash = _sha256(body.rstrip("\n"))
        footer = (
            f"\n<!-- lexibrary:meta\n"
            f"source: {source_rel}\n"
            f"source_hash: stale_hash\n"
            f"design_hash: {design_hash}\n"
            f"generated: 2026-01-01T12:00:00\n"
            f"generator: lexibrary-v2\n"
            f"-->\n"
        )
        text = body + footer

        design_dir = tmp_path / ".lexibrary" / "designs" / Path(source_rel).parent
        design_dir.mkdir(parents=True, exist_ok=True)
        design_path = design_dir / "foo.py.md"
        design_path.write_text(text, encoding="utf-8")

        config = _make_config()
        archivist = _mock_archivist(summary="New summary.")

        result = await update_file(source, tmp_path, config, archivist)

        assert not result.failed
        content = design_path.read_text()
        assert "## Insights" in content
        assert "First insight about coupling." in content
        assert "## Notes" in content
        assert "Additional context about this module." in content

    @pytest.mark.asyncio()
    async def test_new_file_no_existing_design_no_preserved_sections(self, tmp_path: Path) -> None:
        """Brand new file with no existing design file has no preserved sections."""
        source_rel = "src/foo.py"
        source = _make_source_file(tmp_path, source_rel, "def bar(): pass")

        config = _make_config()
        archivist = _mock_archivist()

        result = await update_file(source, tmp_path, config, archivist)

        assert not result.failed
        design_path = tmp_path / ".lexibrary" / "designs" / "src" / "foo.py.md"
        parsed = parse_design_file(design_path)
        assert parsed is not None
        assert parsed.preserved_sections == {}
