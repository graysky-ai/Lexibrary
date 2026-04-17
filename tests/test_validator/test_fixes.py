"""Tests for auto-fix functions in lexibrary.validator.fixes."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

from lexibrary.config.schema import LexibraryConfig, ScopeRoot, TokenBudgetConfig
from lexibrary.validator.fixes import (
    FIXERS,
    FixResult,
    fix_aindex_coverage,
    fix_duplicate_aliases,
    fix_duplicate_slugs,
    fix_hash_freshness,
    fix_orphan_artifacts,
    fix_wikilink_resolution,
)
from lexibrary.validator.report import ValidationIssue

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(scope_root: str = ".") -> LexibraryConfig:
    return LexibraryConfig(
        scope_roots=[ScopeRoot(path=scope_root)],
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
    design_path = tmp_path / ".lexibrary" / "designs" / f"{source_rel}.md"
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

    def test_contains_propose_only_duplicates(self) -> None:
        """Family B propose-only fixers registered (curator-freshness group 7)."""
        assert "duplicate_slugs" in FIXERS
        assert "duplicate_aliases" in FIXERS
        assert FIXERS["duplicate_slugs"] is fix_duplicate_slugs
        assert FIXERS["duplicate_aliases"] is fix_duplicate_aliases

    def test_contains_wikilink_resolution(self) -> None:
        """Family D wikilink fixer registered (curator-freshness group 9)."""
        assert "wikilink_resolution" in FIXERS
        assert FIXERS["wikilink_resolution"] is fix_wikilink_resolution

    def test_does_not_contain_non_fixable(self) -> None:
        assert "orphan_concepts" not in FIXERS
        assert "token_budgets" not in FIXERS
        assert "concept_frontmatter" not in FIXERS


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
        design_path = tmp_path / ".lexibrary" / "designs" / "src" / "deleted.py.md"
        design_path.parent.mkdir(parents=True, exist_ok=True)
        design_path.write_text("orphan design file\n")

        issue = _make_issue(
            check="orphan_artifacts",
            artifact="designs/src/deleted.py.md",
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

        design_path = tmp_path / ".lexibrary" / "designs" / "src" / "exists.py.md"
        design_path.parent.mkdir(parents=True, exist_ok=True)
        design_path.write_text("design file\n")

        issue = _make_issue(
            check="orphan_artifacts",
            artifact="designs/src/exists.py.md",
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
            artifact="designs/src/gone.py.md",
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
        aindex_file = tmp_path / ".lexibrary" / "designs" / "src" / ".aindex"
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


# ---------------------------------------------------------------------------
# fix_duplicate_slugs / fix_duplicate_aliases — propose-only
# ---------------------------------------------------------------------------


class TestFixDuplicateSlugs:
    """``fix_duplicate_slugs`` is propose-only; it never mutates disk."""

    def test_returns_fixed_false_with_manual_resolution_message(self, tmp_path: Path) -> None:
        """A canonical ``duplicate_slugs`` issue yields the propose-only signal."""
        issue = _make_issue(
            check="duplicate_slugs",
            artifact="concepts/CN-001-error-handling.md",
            severity="warning",
            message=(
                "Slug 'error-handling' is used by multiple concepts files: "
                "concepts/CN-001-error-handling.md, concepts/CN-002-error-handling.md"
            ),
        )
        config = _make_config()

        result = fix_duplicate_slugs(issue, tmp_path, config)

        assert result.fixed is False
        assert result.message == "requires manual resolution"
        assert result.check == "duplicate_slugs"

    def test_path_resolved_under_lexibrary_dir(self, tmp_path: Path) -> None:
        """``FixResult.path`` points at the artifact inside ``.lexibrary/``.

        The fixer does not touch disk, so the path need not exist — the
        value exists for downstream reporters (which surface it to the
        operator alongside the "requires manual resolution" message).
        """
        issue = _make_issue(
            check="duplicate_slugs",
            artifact="conventions/CV-003-naming-rule.md",
        )
        config = _make_config()

        result = fix_duplicate_slugs(issue, tmp_path, config)

        expected = tmp_path / ".lexibrary" / "conventions" / "CV-003-naming-rule.md"
        assert result.path == expected

    def test_does_not_mutate_disk(self, tmp_path: Path) -> None:
        """Running the fixer leaves the artifact byte-for-byte unchanged."""
        artifact = tmp_path / ".lexibrary" / "concepts" / "CN-001-foo.md"
        artifact.parent.mkdir(parents=True)
        original = "---\ntitle: Foo\nid: CN-001\n---\n"
        artifact.write_text(original, encoding="utf-8")

        issue = _make_issue(
            check="duplicate_slugs",
            artifact="concepts/CN-001-foo.md",
        )
        fix_duplicate_slugs(issue, tmp_path, _make_config())

        assert artifact.read_text(encoding="utf-8") == original


class TestFixDuplicateAliases:
    """``fix_duplicate_aliases`` is propose-only; it never mutates disk."""

    def test_returns_fixed_false_with_manual_resolution_message(self, tmp_path: Path) -> None:
        issue = _make_issue(
            check="duplicate_aliases",
            artifact="concepts/CN-001-alpha.md",
            severity="error",
            message=(
                "Alias/title 'shared-name' is duplicated across files: CN-001-alpha, CN-002-beta"
            ),
        )
        config = _make_config()

        result = fix_duplicate_aliases(issue, tmp_path, config)

        assert result.fixed is False
        assert result.message == "requires manual resolution"
        assert result.check == "duplicate_aliases"

    def test_path_resolved_under_lexibrary_dir(self, tmp_path: Path) -> None:
        issue = _make_issue(
            check="duplicate_aliases",
            artifact="concepts/CN-002-beta.md",
        )
        config = _make_config()

        result = fix_duplicate_aliases(issue, tmp_path, config)

        expected = tmp_path / ".lexibrary" / "concepts" / "CN-002-beta.md"
        assert result.path == expected

    def test_does_not_mutate_disk(self, tmp_path: Path) -> None:
        artifact = tmp_path / ".lexibrary" / "concepts" / "CN-001-alpha.md"
        artifact.parent.mkdir(parents=True)
        original = "---\ntitle: Alpha\nid: CN-001\naliases: [x, y]\n---\n"
        artifact.write_text(original, encoding="utf-8")

        issue = _make_issue(
            check="duplicate_aliases",
            artifact="concepts/CN-001-alpha.md",
        )
        fix_duplicate_aliases(issue, tmp_path, _make_config())

        assert artifact.read_text(encoding="utf-8") == original


# ---------------------------------------------------------------------------
# fix_wikilink_resolution
# ---------------------------------------------------------------------------


def _write_design_with_source(
    tmp_path: Path,
    source_rel: str,
    *,
    write_source: bool = True,
) -> tuple[Path, Path]:
    """Write a parseable design file (and optionally its source).

    Returns ``(design_path, source_path)``.
    """
    from datetime import UTC

    from lexibrary.artifacts.design_file import (
        DesignFile,
        DesignFileFrontmatter,
        StalenessMetadata,
    )
    from lexibrary.artifacts.design_file_serializer import serialize_design_file

    design_path = tmp_path / ".lexibrary" / "designs" / (source_rel + ".md")
    design_path.parent.mkdir(parents=True, exist_ok=True)
    df = DesignFile(
        source_path=source_rel,
        frontmatter=DesignFileFrontmatter(
            description=f"Design for {source_rel}",
            id=source_rel.replace("/", "-").replace(".", "-"),
            updated_by="archivist",
            status="active",
        ),
        summary=f"Summary of {source_rel}",
        interface_contract="def foo(): ...",
        dependencies=[],
        dependents=[],
        wikilinks=["NonexistentConcept"],
        metadata=StalenessMetadata(
            source=source_rel,
            source_hash="abc123",
            interface_hash=None,
            generated=datetime.now(UTC),
            generator="test",
        ),
    )
    design_path.write_text(serialize_design_file(df), encoding="utf-8")

    source_path = tmp_path / source_rel
    if write_source:
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text("def foo(): pass\n", encoding="utf-8")
    return design_path, source_path


class TestFixWikilinkResolution:
    """Tests for ``fix_wikilink_resolution()`` (curator-freshness group 9)."""

    def test_stack_post_returns_propose_only(self, tmp_path: Path) -> None:
        """Stack-post artifacts are out of scope and return fixed=False."""
        issue = _make_issue(
            check="wikilink_resolution",
            artifact=".lexibrary/stack/ST-001-example.md",
            severity="error",
            message="[[NonexistentConcept]] does not resolve",
        )
        config = _make_config()

        result = fix_wikilink_resolution(issue, tmp_path, config)

        assert result.fixed is False
        assert "manual resolution" in result.message

    def test_design_file_missing_returns_not_fixed(self, tmp_path: Path) -> None:
        """Design file not on disk returns fixed=False with 'not found'."""
        issue = _make_issue(
            check="wikilink_resolution",
            artifact=".lexibrary/designs/src/missing.py.md",
            severity="error",
        )
        result = fix_wikilink_resolution(issue, tmp_path, _make_config())
        assert result.fixed is False
        assert "not found" in result.message

    def test_source_missing_returns_not_fixed(self, tmp_path: Path) -> None:
        """Design parses but source file is gone — fixer cannot regenerate."""
        design_path, _ = _write_design_with_source(tmp_path, "src/foo.py", write_source=False)
        issue = _make_issue(
            check="wikilink_resolution",
            artifact=str(design_path.relative_to(tmp_path)),
        )
        result = fix_wikilink_resolution(issue, tmp_path, _make_config())
        assert result.fixed is False
        assert "source file not found" in result.message

    def test_successful_regeneration(self, tmp_path: Path) -> None:
        """update_file success → fixed=True, called on the derived source path."""
        design_path, source_path = _write_design_with_source(tmp_path, "src/foo.py")
        issue = _make_issue(
            check="wikilink_resolution",
            artifact=str(design_path.relative_to(tmp_path)),
        )
        config = _make_config()

        from lexibrary.archivist.change_checker import ChangeLevel
        from lexibrary.archivist.pipeline import FileResult

        mock_update = AsyncMock(return_value=FileResult(change=ChangeLevel.CONTENT_CHANGED))

        with (
            patch("lexibrary.archivist.pipeline.update_file", mock_update),
            patch("lexibrary.archivist.service.build_archivist_service", return_value=object()),
        ):
            result = fix_wikilink_resolution(issue, tmp_path, config)

        assert result.fixed is True
        assert "re-generated" in result.message
        # Confirm update_file was called with the derived source path.
        assert mock_update.await_args is not None
        called_source = mock_update.await_args.args[0]
        assert called_source == source_path

    def test_failed_regeneration_returns_not_fixed(self, tmp_path: Path) -> None:
        """update_file returning failed=True → FixResult(fixed=False)."""
        design_path, _ = _write_design_with_source(tmp_path, "src/foo.py")
        issue = _make_issue(
            check="wikilink_resolution",
            artifact=str(design_path.relative_to(tmp_path)),
        )
        config = _make_config()

        from lexibrary.archivist.change_checker import ChangeLevel
        from lexibrary.archivist.pipeline import FileResult

        mock_update = AsyncMock(
            return_value=FileResult(change=ChangeLevel.CONTENT_CHANGED, failed=True)
        )

        with (
            patch("lexibrary.archivist.pipeline.update_file", mock_update),
            patch("lexibrary.archivist.service.build_archivist_service", return_value=object()),
        ):
            result = fix_wikilink_resolution(issue, tmp_path, config)

        assert result.fixed is False
        assert "failed" in result.message
