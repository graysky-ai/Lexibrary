"""Tests for auto-fix functions in lexibrary.validator.fixes."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

from lexibrary.config.schema import LexibraryConfig, TokenBudgetConfig
from lexibrary.validator.fixes import (
    FIXERS,
    FixResult,
    fix_aindex_coverage,
    fix_hash_freshness,
    fix_orphan_artifacts,
)
from lexibrary.validator.report import ValidationIssue

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(scope_root: str = ".") -> LexibraryConfig:
    return LexibraryConfig(
        scope_root=scope_root,
        token_budgets=TokenBudgetConfig(design_file_tokens=400),
    )


def _make_issue(
    check: str = "hash_freshness",
    artifact: str = "src/foo.py",
    severity: str = "warning",
    message: str = "stale source hash",
) -> ValidationIssue:
    return ValidationIssue(
        severity=severity,  # type: ignore[arg-type]
        check=check,
        message=message,
        artifact=artifact,
    )


def _create_design_file(tmp_path: Path, source_rel: str, source_content: str) -> Path:
    """Create a design file in .lexibrary mirror tree with metadata footer."""
    content_hash = hashlib.sha256(source_content.encode()).hexdigest()
    design_path = tmp_path / ".lexibrary" / f"{source_rel}.md"
    design_path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now().isoformat()
    design_content = f"""---
description: Design file for {source_rel}
updated_by: archivist
---

# {source_rel}

Test design file content.

## Interface Contract

```python
def hello(): ...
```

## Dependencies

- (none)

## Dependents

- (none)

<!-- lexibrary:meta
source: {source_rel}
source_hash: {content_hash}
design_hash: placeholder
generated: {now}
generator: lexibrary-v2
-->
"""
    design_path.write_text(design_content, encoding="utf-8")
    return design_path


# ---------------------------------------------------------------------------
# FixResult model
# ---------------------------------------------------------------------------


class TestFixResult:
    """Verify FixResult dataclass."""

    def test_successful_fix(self) -> None:
        result = FixResult(
            check="hash_freshness",
            path=Path("src/foo.py"),
            fixed=True,
            message="re-generated design file",
        )
        assert result.fixed is True
        assert result.check == "hash_freshness"
        assert result.message == "re-generated design file"

    def test_skipped_fix(self) -> None:
        result = FixResult(
            check="orphan_concepts",
            path=Path("concepts/old.md"),
            fixed=False,
            message="requires manual review",
        )
        assert result.fixed is False


# ---------------------------------------------------------------------------
# FIXERS registry
# ---------------------------------------------------------------------------


class TestFixersRegistry:
    """Verify FIXERS registry contents."""

    def test_contains_fixable_checks(self) -> None:
        assert "hash_freshness" in FIXERS
        assert "orphan_artifacts" in FIXERS
        assert "aindex_coverage" in FIXERS

    def test_does_not_contain_non_fixable(self) -> None:
        assert "orphan_concepts" not in FIXERS
        assert "token_budgets" not in FIXERS
        assert "concept_frontmatter" not in FIXERS
        assert "wikilink_resolution" not in FIXERS


# ---------------------------------------------------------------------------
# fix_hash_freshness
# ---------------------------------------------------------------------------


class TestFixHashFreshness:
    """Tests for fix_hash_freshness()."""

    def test_source_missing_returns_not_fixed(self, tmp_path: Path) -> None:
        """Source file not found returns fixed=False."""
        issue = _make_issue(artifact="src/nonexistent.py")
        config = _make_config()
        result = fix_hash_freshness(issue, tmp_path, config)
        assert result.fixed is False
        assert "not found" in result.message

    def test_successful_regeneration(self, tmp_path: Path) -> None:
        """Successful re-generation returns fixed=True."""
        # Create source file
        source_dir = tmp_path / "src"
        source_dir.mkdir(parents=True)
        (source_dir / "foo.py").write_text("def foo(): pass\n")

        issue = _make_issue(artifact="src/foo.py")
        config = _make_config()

        # Mock update_file to return a successful result
        from lexibrary.archivist.change_checker import ChangeLevel
        from lexibrary.archivist.pipeline import FileResult

        mock_result = FileResult(change=ChangeLevel.CONTENT_CHANGED)
        mock_update = AsyncMock(return_value=mock_result)

        with patch("lexibrary.archivist.pipeline.update_file", mock_update):
            result = fix_hash_freshness(issue, tmp_path, config)

        assert result.fixed is True
        assert "re-generated" in result.message

    def test_failed_regeneration(self, tmp_path: Path) -> None:
        """Failed LLM call returns fixed=False."""
        source_dir = tmp_path / "src"
        source_dir.mkdir(parents=True)
        (source_dir / "foo.py").write_text("def foo(): pass\n")

        issue = _make_issue(artifact="src/foo.py")
        config = _make_config()

        from lexibrary.archivist.change_checker import ChangeLevel
        from lexibrary.archivist.pipeline import FileResult

        mock_result = FileResult(change=ChangeLevel.CONTENT_CHANGED, failed=True)
        mock_update = AsyncMock(return_value=mock_result)

        with patch("lexibrary.archivist.pipeline.update_file", mock_update):
            result = fix_hash_freshness(issue, tmp_path, config)

        assert result.fixed is False
        assert "failed" in result.message


# ---------------------------------------------------------------------------
# fix_orphan_artifacts
# ---------------------------------------------------------------------------


class TestFixOrphanArtifacts:
    """Tests for fix_orphan_artifacts()."""

    def test_orphan_deleted(self, tmp_path: Path) -> None:
        """Orphan design file is deleted when source does not exist."""
        # Create design file but NOT the source file
        design_path = tmp_path / ".lexibrary" / "src" / "deleted.py.md"
        design_path.parent.mkdir(parents=True, exist_ok=True)
        design_path.write_text("orphan design file\n")

        issue = _make_issue(
            check="orphan_artifacts",
            artifact="src/deleted.py.md",
        )
        config = _make_config()

        result = fix_orphan_artifacts(issue, tmp_path, config)
        assert result.fixed is True
        assert "deleted" in result.message
        assert not design_path.exists()

    def test_source_exists_not_deleted(self, tmp_path: Path) -> None:
        """Design file is NOT deleted when source file exists."""
        # Create both source and design files
        (tmp_path / "src").mkdir(parents=True)
        (tmp_path / "src" / "exists.py").write_text("x = 1\n")

        design_path = tmp_path / ".lexibrary" / "src" / "exists.py.md"
        design_path.parent.mkdir(parents=True, exist_ok=True)
        design_path.write_text("design file\n")

        issue = _make_issue(
            check="orphan_artifacts",
            artifact="src/exists.py.md",
        )
        config = _make_config()

        result = fix_orphan_artifacts(issue, tmp_path, config)
        assert result.fixed is False
        assert "not an orphan" in result.message
        assert design_path.exists()

    def test_design_already_removed(self, tmp_path: Path) -> None:
        """Gracefully handles design file that was already removed."""
        (tmp_path / ".lexibrary").mkdir(parents=True, exist_ok=True)

        issue = _make_issue(
            check="orphan_artifacts",
            artifact="src/gone.py.md",
        )
        config = _make_config()

        result = fix_orphan_artifacts(issue, tmp_path, config)
        assert result.fixed is False
        assert "already removed" in result.message


# ---------------------------------------------------------------------------
# fix_aindex_coverage
# ---------------------------------------------------------------------------


class TestFixAindexCoverage:
    """Tests for fix_aindex_coverage()."""

    def test_generates_missing_aindex(self, tmp_path: Path) -> None:
        """Generates .aindex for a directory that lacks one."""
        (tmp_path / ".lexibrary").mkdir(parents=True)
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "foo.py").write_text("def foo(): pass\n")

        issue = _make_issue(
            check="aindex_coverage",
            artifact="src",
        )
        config = _make_config(scope_root="src")

        result = fix_aindex_coverage(issue, tmp_path, config)
        assert result.fixed is True
        assert "generated" in result.message

        # Verify .aindex was created
        aindex_file = tmp_path / ".lexibrary" / "src" / ".aindex"
        assert aindex_file.exists()

    def test_directory_not_found(self, tmp_path: Path) -> None:
        """Returns fixed=False when directory does not exist."""
        issue = _make_issue(
            check="aindex_coverage",
            artifact="src/nonexistent",
        )
        config = _make_config()

        result = fix_aindex_coverage(issue, tmp_path, config)
        assert result.fixed is False
        assert "not found" in result.message
