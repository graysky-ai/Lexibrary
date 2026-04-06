"""Tests for lifecycle validation checks and fixers.

Tests check_orphaned_designs(), check_comment_accumulation(),
check_deprecated_ttl() checks and fix_orphaned_designs(),
fix_deprecated_ttl() fixers. Also tests convention-specific validation
checks: check_convention_orphaned_scope(), check_convention_stale(),
check_convention_gap(), and check_convention_consistent_violation().
Also tests check_resolved_post_staleness() for Stack post staleness
detection (TTL-based and deleted file references).
Covers detection, exclusion of deprecated files, threshold behavior,
TTL expiry, fixer deprecation workflow, and registry entries.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

from lexibrary.config.schema import DeprecationConfig, LexibraryConfig, TokenBudgetConfig
from lexibrary.utils.paths import DESIGNS_DIR, LEXIBRARY_DIR
from lexibrary.validator.checks import (
    check_comment_accumulation,
    check_convention_consistent_violation,
    check_convention_gap,
    check_convention_orphaned_scope,
    check_convention_stale,
    check_deprecated_ttl,
    check_orphaned_designs,
    check_resolved_post_staleness,
    check_stale_concepts,
    check_supersession_candidates,
)
from lexibrary.validator.fixes import (
    FIXERS,
    fix_deprecated_ttl,
    fix_orphaned_designs,
)
from lexibrary.validator.report import ValidationIssue

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(
    ttl_commits: int = 50,
    comment_warning_threshold: int = 10,
) -> LexibraryConfig:
    return LexibraryConfig(
        scope_root=".",
        token_budgets=TokenBudgetConfig(design_file_tokens=400),
        deprecation=DeprecationConfig(
            ttl_commits=ttl_commits,
            comment_warning_threshold=comment_warning_threshold,
        ),
    )


def _make_issue(
    check: str = "orphaned_designs",
    artifact: str = "designs/src/foo.py.md",
    severity: str = "warning",
    message: str = "orphaned design file",
) -> ValidationIssue:
    return ValidationIssue(
        severity=severity,  # type: ignore[arg-type]
        check=check,
        message=message,
        artifact=artifact,
    )


def _create_design_file(
    lexibrary_dir: Path,
    source_rel: str,
    *,
    status: str = "active",
    deprecated_at: str | None = None,
    deprecated_reason: str | None = None,
    source_content: str = "def hello(): pass\n",
) -> Path:
    """Create a design file with proper frontmatter and metadata footer."""
    content_hash = hashlib.sha256(source_content.encode()).hexdigest()
    design_path = lexibrary_dir / DESIGNS_DIR / f"{source_rel}.md"
    design_path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now(UTC).isoformat()

    # Build frontmatter
    fm_lines = [
        f"description: Design file for {source_rel}",
        "id: DS-001",
        "updated_by: archivist",
        f"status: {status}",
    ]
    if deprecated_at is not None:
        fm_lines.append(f"deprecated_at: '{deprecated_at}'")
    if deprecated_reason is not None:
        fm_lines.append(f"deprecated_reason: {deprecated_reason}")

    frontmatter = "\n".join(fm_lines)

    design_content = f"""---
{frontmatter}
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

*(see `lexi lookup` for live reverse references)*

(none)

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


def _add_comments(design_path: Path, count: int) -> None:
    """Add multiple comments to the sibling .comments.yaml file."""
    from lexibrary.lifecycle.comments import append_comment
    from lexibrary.lifecycle.design_comments import design_comment_path
    from lexibrary.lifecycle.models import ArtefactComment

    comment_file = design_comment_path(design_path)
    for i in range(count):
        comment = ArtefactComment(
            body=f"Test comment {i + 1}",
            date=datetime(2026, 1, 1, 12, 0, 0),
        )
        append_comment(comment_file, comment)


# ---------------------------------------------------------------------------
# check_orphaned_designs
# ---------------------------------------------------------------------------


class TestCheckOrphanedDesigns:
    """Tests for check_orphaned_designs()."""

    def test_no_orphans_when_sources_exist(self, tmp_path: Path) -> None:
        """No issues when all design files have corresponding source files."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        # Create source file and its design file
        src = project_root / "src" / "foo.py"
        src.parent.mkdir(parents=True)
        src.write_text("def foo(): pass\n")
        _create_design_file(lexibrary_dir, "src/foo.py")

        issues = check_orphaned_designs(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_orphaned_design_detected(self, tmp_path: Path) -> None:
        """An orphaned design file (source deleted) produces a warning."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        # Create design file WITHOUT the source file
        _create_design_file(lexibrary_dir, "src/deleted_module.py")

        issues = check_orphaned_designs(project_root, lexibrary_dir)
        assert len(issues) == 1
        issue = issues[0]
        assert issue.severity == "warning"
        assert issue.check == "orphaned_designs"
        assert "src/deleted_module.py" in issue.message
        assert "lexictl" in issue.suggestion

    def test_deprecated_design_excluded(self, tmp_path: Path) -> None:
        """Design files with status: deprecated are excluded from check."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        # Create deprecated design file WITHOUT the source file
        _create_design_file(
            lexibrary_dir,
            "src/old_module.py",
            status="deprecated",
            deprecated_at="2026-01-01T12:00:00",
            deprecated_reason="source_deleted",
        )

        issues = check_orphaned_designs(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_unlinked_design_still_flagged(self, tmp_path: Path) -> None:
        """Design files with status: unlinked (not deprecated) are flagged."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        # Create unlinked design file WITHOUT the source file
        _create_design_file(
            lexibrary_dir,
            "src/unlinked_module.py",
            status="unlinked",
        )

        issues = check_orphaned_designs(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert issues[0].check == "orphaned_designs"

    def test_mixed_orphaned_and_valid(self, tmp_path: Path) -> None:
        """Only orphaned files produce issues; valid ones are preserved."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        # Valid: source exists
        src = project_root / "src" / "valid.py"
        src.parent.mkdir(parents=True)
        src.write_text("x = 1\n")
        _create_design_file(lexibrary_dir, "src/valid.py")

        # Orphaned: source missing
        _create_design_file(lexibrary_dir, "src/orphan.py")

        issues = check_orphaned_designs(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert "src/orphan.py" in issues[0].message

    def test_no_designs_dir(self, tmp_path: Path) -> None:
        """Returns empty list when designs directory does not exist."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        issues = check_orphaned_designs(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_multiple_orphans(self, tmp_path: Path) -> None:
        """Multiple orphaned files each produce their own issue."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        _create_design_file(lexibrary_dir, "src/deleted_a.py")
        _create_design_file(lexibrary_dir, "src/deleted_b.py")

        issues = check_orphaned_designs(project_root, lexibrary_dir)
        assert len(issues) == 2
        messages = {i.message for i in issues}
        assert any("deleted_a.py" in m for m in messages)
        assert any("deleted_b.py" in m for m in messages)


# ---------------------------------------------------------------------------
# check_comment_accumulation
# ---------------------------------------------------------------------------


class TestCheckCommentAccumulation:
    """Tests for check_comment_accumulation()."""

    def test_within_threshold_no_issues(self, tmp_path: Path) -> None:
        """No issues when comment count is within threshold."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        # Create source and design file
        src = project_root / "src" / "foo.py"
        src.parent.mkdir(parents=True)
        src.write_text("def foo(): pass\n")
        design_path = _create_design_file(lexibrary_dir, "src/foo.py")

        # Add 5 comments (below default threshold of 10)
        _add_comments(design_path, 5)

        # Mock load_config to return our config
        config = _make_config(comment_warning_threshold=10)
        with patch("lexibrary.validator.checks.load_config", return_value=config):
            issues = check_comment_accumulation(project_root, lexibrary_dir)

        assert len(issues) == 0

    def test_exceeds_threshold_produces_issue(self, tmp_path: Path) -> None:
        """Info issue produced when comment count exceeds threshold."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        src = project_root / "src" / "foo.py"
        src.parent.mkdir(parents=True)
        src.write_text("def foo(): pass\n")
        design_path = _create_design_file(lexibrary_dir, "src/foo.py")

        # Add 12 comments (above default threshold of 10)
        _add_comments(design_path, 12)

        config = _make_config(comment_warning_threshold=10)
        with patch("lexibrary.validator.checks.load_config", return_value=config):
            issues = check_comment_accumulation(project_root, lexibrary_dir)

        assert len(issues) == 1
        issue = issues[0]
        assert issue.severity == "info"
        assert issue.check == "comment_accumulation"
        assert "12 comments" in issue.message
        assert "threshold: 10" in issue.message
        assert "lexi design comment" in issue.suggestion

    def test_exact_threshold_no_issue(self, tmp_path: Path) -> None:
        """No issue when comment count equals threshold (must exceed)."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        src = project_root / "src" / "foo.py"
        src.parent.mkdir(parents=True)
        src.write_text("def foo(): pass\n")
        design_path = _create_design_file(lexibrary_dir, "src/foo.py")

        _add_comments(design_path, 10)

        config = _make_config(comment_warning_threshold=10)
        with patch("lexibrary.validator.checks.load_config", return_value=config):
            issues = check_comment_accumulation(project_root, lexibrary_dir)

        assert len(issues) == 0

    def test_custom_threshold(self, tmp_path: Path) -> None:
        """Custom threshold from config is respected."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        src = project_root / "src" / "foo.py"
        src.parent.mkdir(parents=True)
        src.write_text("def foo(): pass\n")
        design_path = _create_design_file(lexibrary_dir, "src/foo.py")

        # Add 4 comments with threshold of 3
        _add_comments(design_path, 4)

        config = _make_config(comment_warning_threshold=3)
        with patch("lexibrary.validator.checks.load_config", return_value=config):
            issues = check_comment_accumulation(project_root, lexibrary_dir)

        assert len(issues) == 1
        assert "4 comments" in issues[0].message
        assert "threshold: 3" in issues[0].message

    def test_no_comments_no_issue(self, tmp_path: Path) -> None:
        """No issues when design file has zero comments."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        src = project_root / "src" / "foo.py"
        src.parent.mkdir(parents=True)
        src.write_text("def foo(): pass\n")
        _create_design_file(lexibrary_dir, "src/foo.py")

        config = _make_config(comment_warning_threshold=10)
        with patch("lexibrary.validator.checks.load_config", return_value=config):
            issues = check_comment_accumulation(project_root, lexibrary_dir)

        assert len(issues) == 0

    def test_config_load_failure_uses_default(self, tmp_path: Path) -> None:
        """When config loading fails, default threshold of 10 is used."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        src = project_root / "src" / "foo.py"
        src.parent.mkdir(parents=True)
        src.write_text("def foo(): pass\n")
        design_path = _create_design_file(lexibrary_dir, "src/foo.py")

        _add_comments(design_path, 11)

        with patch("lexibrary.validator.checks.load_config", side_effect=Exception("broken")):
            issues = check_comment_accumulation(project_root, lexibrary_dir)

        # Should use default threshold of 10, so 11 > 10 = issue
        assert len(issues) == 1


# ---------------------------------------------------------------------------
# check_deprecated_ttl
# ---------------------------------------------------------------------------


class TestCheckDeprecatedTtl:
    """Tests for check_deprecated_ttl()."""

    def test_expired_ttl_produces_issue(self, tmp_path: Path) -> None:
        """Info issue produced when deprecated file exceeds TTL."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        _create_design_file(
            lexibrary_dir,
            "src/old.py",
            status="deprecated",
            deprecated_at="2026-01-01T12:00:00",
            deprecated_reason="source_deleted",
        )

        config = _make_config(ttl_commits=50)
        with (
            patch("lexibrary.validator.checks.load_config", return_value=config),
            patch(
                "lexibrary.validator.checks.check_ttl_expiry",
                return_value=True,
            ),
        ):
            issues = check_deprecated_ttl(project_root, lexibrary_dir)

        assert len(issues) == 1
        issue = issues[0]
        assert issue.severity == "info"
        assert issue.check == "deprecated_ttl"
        assert "exceeded TTL" in issue.message
        assert "50 commits" in issue.message

    def test_within_ttl_no_issue(self, tmp_path: Path) -> None:
        """No issues when deprecated file is within TTL."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        _create_design_file(
            lexibrary_dir,
            "src/recent.py",
            status="deprecated",
            deprecated_at="2026-03-01T12:00:00",
            deprecated_reason="source_deleted",
        )

        config = _make_config(ttl_commits=50)
        with (
            patch("lexibrary.validator.checks.load_config", return_value=config),
            patch(
                "lexibrary.validator.checks.check_ttl_expiry",
                return_value=False,
            ),
        ):
            issues = check_deprecated_ttl(project_root, lexibrary_dir)

        assert len(issues) == 0

    def test_active_file_skipped(self, tmp_path: Path) -> None:
        """Active design files are not checked for TTL expiry."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        src = project_root / "src" / "active.py"
        src.parent.mkdir(parents=True)
        src.write_text("x = 1\n")
        _create_design_file(lexibrary_dir, "src/active.py", status="active")

        config = _make_config(ttl_commits=50)
        with patch("lexibrary.validator.checks.load_config", return_value=config):
            issues = check_deprecated_ttl(project_root, lexibrary_dir)

        assert len(issues) == 0

    def test_unlinked_file_skipped(self, tmp_path: Path) -> None:
        """Unlinked design files are not checked for TTL expiry."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        _create_design_file(lexibrary_dir, "src/unlinked.py", status="unlinked")

        config = _make_config(ttl_commits=50)
        with patch("lexibrary.validator.checks.load_config", return_value=config):
            issues = check_deprecated_ttl(project_root, lexibrary_dir)

        assert len(issues) == 0

    def test_config_load_failure_uses_default(self, tmp_path: Path) -> None:
        """When config loading fails, default TTL of 50 is used."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        _create_design_file(
            lexibrary_dir,
            "src/old.py",
            status="deprecated",
            deprecated_at="2026-01-01T12:00:00",
            deprecated_reason="source_deleted",
        )

        with (
            patch("lexibrary.validator.checks.load_config", side_effect=Exception("broken")),
            patch(
                "lexibrary.validator.checks.check_ttl_expiry",
                return_value=True,
            ),
        ):
            issues = check_deprecated_ttl(project_root, lexibrary_dir)

        assert len(issues) == 1
        assert "50 commits" in issues[0].message

    def test_no_designs_dir(self, tmp_path: Path) -> None:
        """Returns empty list when designs directory does not exist."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        config = _make_config(ttl_commits=50)
        with patch("lexibrary.validator.checks.load_config", return_value=config):
            issues = check_deprecated_ttl(project_root, lexibrary_dir)

        assert len(issues) == 0


# ---------------------------------------------------------------------------
# fix_orphaned_designs
# ---------------------------------------------------------------------------


class TestFixOrphanedDesigns:
    """Tests for fix_orphaned_designs()."""

    def test_committed_deletion_marks_deprecated(self, tmp_path: Path) -> None:
        """Committed source deletion results in deprecated status."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        design_path = _create_design_file(lexibrary_dir, "src/deleted.py")

        issue = _make_issue(artifact=f"{DESIGNS_DIR}/src/deleted.py.md")
        config = _make_config()

        with patch(
            "lexibrary.lifecycle.deprecation._is_committed_deletion",
            return_value=True,
        ):
            result = fix_orphaned_designs(issue, project_root, config)

        assert result.fixed is True
        assert "deprecated" in result.message
        assert design_path.exists()

        # Verify the design file was updated
        from lexibrary.artifacts.design_file_parser import parse_design_file_frontmatter

        fm = parse_design_file_frontmatter(design_path)
        assert fm is not None
        assert fm.status == "deprecated"
        assert fm.deprecated_at is not None
        assert fm.deprecated_reason == "source_deleted"

    def test_uncommitted_deletion_marks_unlinked(self, tmp_path: Path) -> None:
        """Uncommitted source deletion results in unlinked status."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        design_path = _create_design_file(lexibrary_dir, "src/deleted.py")

        issue = _make_issue(artifact=f"{DESIGNS_DIR}/src/deleted.py.md")
        config = _make_config()

        with patch(
            "lexibrary.lifecycle.deprecation._is_committed_deletion",
            return_value=False,
        ):
            result = fix_orphaned_designs(issue, project_root, config)

        assert result.fixed is True
        assert "unlinked" in result.message
        assert design_path.exists()

        from lexibrary.artifacts.design_file_parser import parse_design_file_frontmatter

        fm = parse_design_file_frontmatter(design_path)
        assert fm is not None
        assert fm.status == "unlinked"

    def test_design_already_removed(self, tmp_path: Path) -> None:
        """Gracefully handles design file that was already removed."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()
        (lexibrary_dir / DESIGNS_DIR).mkdir(parents=True)

        issue = _make_issue(artifact=f"{DESIGNS_DIR}/src/gone.py.md")
        config = _make_config()

        result = fix_orphaned_designs(issue, project_root, config)
        assert result.fixed is False
        assert "already removed" in result.message


# ---------------------------------------------------------------------------
# fix_deprecated_ttl
# ---------------------------------------------------------------------------


class TestFixDeprecatedTtl:
    """Tests for fix_deprecated_ttl()."""

    def test_expired_file_deleted(self, tmp_path: Path) -> None:
        """Expired deprecated design file is hard-deleted."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        design_path = _create_design_file(
            lexibrary_dir,
            "src/expired.py",
            status="deprecated",
            deprecated_at="2026-01-01T12:00:00",
            deprecated_reason="source_deleted",
        )
        assert design_path.exists()

        issue = _make_issue(
            check="deprecated_ttl",
            artifact=f"{DESIGNS_DIR}/src/expired.py.md",
            severity="info",
        )
        config = _make_config(ttl_commits=50)

        with patch(
            "lexibrary.lifecycle.deprecation.check_ttl_expiry",
            return_value=True,
        ):
            result = fix_deprecated_ttl(issue, project_root, config)

        assert result.fixed is True
        assert "hard-deleted" in result.message
        assert not design_path.exists()

    def test_not_expired_no_deletion(self, tmp_path: Path) -> None:
        """Non-expired deprecated file is not deleted."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        design_path = _create_design_file(
            lexibrary_dir,
            "src/recent.py",
            status="deprecated",
            deprecated_at="2026-03-01T12:00:00",
            deprecated_reason="source_deleted",
        )

        issue = _make_issue(
            check="deprecated_ttl",
            artifact=f"{DESIGNS_DIR}/src/recent.py.md",
            severity="info",
        )
        config = _make_config(ttl_commits=50)

        with patch(
            "lexibrary.lifecycle.deprecation.check_ttl_expiry",
            return_value=False,
        ):
            result = fix_deprecated_ttl(issue, project_root, config)

        assert result.fixed is False
        assert "not yet expired" in result.message
        assert design_path.exists()

    def test_design_already_removed(self, tmp_path: Path) -> None:
        """Gracefully handles design file that was already removed."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()
        (lexibrary_dir / DESIGNS_DIR).mkdir(parents=True)

        issue = _make_issue(
            check="deprecated_ttl",
            artifact=f"{DESIGNS_DIR}/src/gone.py.md",
            severity="info",
        )
        config = _make_config()

        result = fix_deprecated_ttl(issue, project_root, config)
        assert result.fixed is False
        assert "already removed" in result.message

    def test_empty_parent_dirs_cleaned(self, tmp_path: Path) -> None:
        """Empty parent directories are cleaned up after deletion."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()
        designs_dir = lexibrary_dir / DESIGNS_DIR

        design_path = _create_design_file(
            lexibrary_dir,
            "src/deep/nested/expired.py",
            status="deprecated",
            deprecated_at="2026-01-01T12:00:00",
            deprecated_reason="source_deleted",
        )

        issue = _make_issue(
            check="deprecated_ttl",
            artifact=f"{DESIGNS_DIR}/src/deep/nested/expired.py.md",
            severity="info",
        )
        config = _make_config(ttl_commits=50)

        with patch(
            "lexibrary.lifecycle.deprecation.check_ttl_expiry",
            return_value=True,
        ):
            result = fix_deprecated_ttl(issue, project_root, config)

        assert result.fixed is True
        assert not design_path.exists()
        # Empty parent dirs should be cleaned
        assert not (designs_dir / "src" / "deep" / "nested").exists()
        # Designs root should still exist
        assert designs_dir.exists()


# ---------------------------------------------------------------------------
# FIXERS registry
# ---------------------------------------------------------------------------


class TestFixersRegistry:
    """Verify new fixers are registered in the FIXERS registry."""

    def test_orphaned_designs_registered(self) -> None:
        assert "orphaned_designs" in FIXERS
        assert FIXERS["orphaned_designs"] is fix_orphaned_designs

    def test_deprecated_ttl_registered(self) -> None:
        assert "deprecated_ttl" in FIXERS
        assert FIXERS["deprecated_ttl"] is fix_deprecated_ttl

    def test_comment_accumulation_not_registered(self) -> None:
        """Comment accumulation is not auto-fixable."""
        assert "comment_accumulation" not in FIXERS


# ---------------------------------------------------------------------------
# AVAILABLE_CHECKS registry
# ---------------------------------------------------------------------------


class TestLifecycleChecksInAvailableChecks:
    """Verify lifecycle checks are registered in AVAILABLE_CHECKS."""

    def test_orphaned_designs_registered(self) -> None:
        from lexibrary.validator import AVAILABLE_CHECKS

        assert "orphaned_designs" in AVAILABLE_CHECKS
        check_fn, severity = AVAILABLE_CHECKS["orphaned_designs"]
        assert check_fn is check_orphaned_designs
        assert severity == "warning"

    def test_comment_accumulation_registered(self) -> None:
        from lexibrary.validator import AVAILABLE_CHECKS

        assert "comment_accumulation" in AVAILABLE_CHECKS
        check_fn, severity = AVAILABLE_CHECKS["comment_accumulation"]
        assert check_fn is check_comment_accumulation
        assert severity == "info"

    def test_deprecated_ttl_registered(self) -> None:
        from lexibrary.validator import AVAILABLE_CHECKS

        assert "deprecated_ttl" in AVAILABLE_CHECKS
        check_fn, severity = AVAILABLE_CHECKS["deprecated_ttl"]
        assert check_fn is check_deprecated_ttl
        assert severity == "info"

    def test_stale_concept_registered(self) -> None:
        from lexibrary.validator import AVAILABLE_CHECKS

        assert "stale_concept" in AVAILABLE_CHECKS
        check_fn, severity = AVAILABLE_CHECKS["stale_concept"]
        assert check_fn is check_stale_concepts
        assert severity == "info"


# ---------------------------------------------------------------------------
# Helpers for concept tests
# ---------------------------------------------------------------------------


def _create_concept_file(
    concepts_dir: Path,
    slug: str,
    *,
    title: str = "",
    status: str = "active",
    aliases: list[str] | None = None,
    linked_files: list[str] | None = None,
) -> Path:
    """Create a concept markdown file with frontmatter and optional linked files."""
    if not title:
        title = slug.replace("-", " ").title()

    concept_path = concepts_dir / f"{slug}.md"
    concept_path.parent.mkdir(parents=True, exist_ok=True)

    body_lines: list[str] = [
        "",
        f"Summary of {title}.",
        "",
    ]

    if linked_files:
        body_lines.append("## Linked Files")
        body_lines.append("")
        for f in linked_files:
            body_lines.append(f"- `{f}`")
        body_lines.append("")

    body = "\n".join(body_lines)

    aliases_list = aliases or []
    aliases_yaml = "[" + ", ".join(aliases_list) + "]" if aliases_list else "[]"

    content = f"""---
title: {title}
id: CN-001
aliases: {aliases_yaml}
tags: []
status: {status}
---
{body}"""
    concept_path.write_text(content, encoding="utf-8")
    return concept_path


# ---------------------------------------------------------------------------
# check_stale_concepts
# ---------------------------------------------------------------------------


class TestCheckStaleConcepts:
    """Tests for check_stale_concepts()."""

    def test_active_concept_with_valid_files(self, tmp_path: Path) -> None:
        """No issues when all linked files exist on disk."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()
        concepts_dir = lexibrary_dir / "concepts"
        concepts_dir.mkdir()

        # Create the source file that the concept references
        src = project_root / "src" / "auth" / "login.py"
        src.parent.mkdir(parents=True)
        src.write_text("def login(): pass\n")

        _create_concept_file(
            concepts_dir,
            "authentication",
            title="Authentication",
            linked_files=["src/auth/login.py"],
        )

        issues = check_stale_concepts(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_active_concept_with_missing_file(self, tmp_path: Path) -> None:
        """Info issue produced when a linked file no longer exists."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()
        concepts_dir = lexibrary_dir / "concepts"
        concepts_dir.mkdir()

        # Do NOT create the referenced file
        _create_concept_file(
            concepts_dir,
            "old-module",
            title="Old Module",
            linked_files=["src/old_module.py"],
        )

        issues = check_stale_concepts(project_root, lexibrary_dir)
        assert len(issues) == 1
        issue = issues[0]
        assert issue.severity == "info"
        assert issue.check == "stale_concept"
        assert "src/old_module.py" in issue.message
        assert issue.artifact == "concepts/Old Module"
        assert "deprecate" in issue.suggestion.lower() or "review" in issue.suggestion.lower()

    def test_deprecated_concept_skipped(self, tmp_path: Path) -> None:
        """Deprecated concepts with missing linked files produce no issues."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()
        concepts_dir = lexibrary_dir / "concepts"
        concepts_dir.mkdir()

        _create_concept_file(
            concepts_dir,
            "legacy-auth",
            title="Legacy Auth",
            status="deprecated",
            linked_files=["src/legacy_auth.py"],
        )

        issues = check_stale_concepts(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_concept_with_no_linked_files(self, tmp_path: Path) -> None:
        """Active concept with no file path references produces no issues."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()
        concepts_dir = lexibrary_dir / "concepts"
        concepts_dir.mkdir()

        _create_concept_file(
            concepts_dir,
            "abstract-idea",
            title="Abstract Idea",
            linked_files=None,
        )

        issues = check_stale_concepts(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_no_concepts_dir(self, tmp_path: Path) -> None:
        """Returns empty list when concepts directory does not exist."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        issues = check_stale_concepts(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_mixed_valid_and_missing_files(self, tmp_path: Path) -> None:
        """Only missing files are reported; valid files are fine."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()
        concepts_dir = lexibrary_dir / "concepts"
        concepts_dir.mkdir()

        # Create one file, leave another missing
        src = project_root / "src" / "valid.py"
        src.parent.mkdir(parents=True)
        src.write_text("x = 1\n")

        _create_concept_file(
            concepts_dir,
            "mixed-refs",
            title="Mixed Refs",
            linked_files=["src/valid.py", "src/gone.py"],
        )

        issues = check_stale_concepts(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert "src/gone.py" in issues[0].message
        # Valid file should NOT be in the message
        assert "src/valid.py" not in issues[0].message

    def test_multiple_concepts_with_missing_files(self, tmp_path: Path) -> None:
        """Each stale concept produces its own issue."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()
        concepts_dir = lexibrary_dir / "concepts"
        concepts_dir.mkdir()

        _create_concept_file(
            concepts_dir,
            "concept-a",
            title="Concept A",
            linked_files=["src/a.py"],
        )
        _create_concept_file(
            concepts_dir,
            "concept-b",
            title="Concept B",
            linked_files=["src/b.py"],
        )

        issues = check_stale_concepts(project_root, lexibrary_dir)
        assert len(issues) == 2
        artifacts = {i.artifact for i in issues}
        assert "concepts/Concept A" in artifacts
        assert "concepts/Concept B" in artifacts

    def test_draft_concept_skipped(self, tmp_path: Path) -> None:
        """Draft concepts with missing linked files produce no issues."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()
        concepts_dir = lexibrary_dir / "concepts"
        concepts_dir.mkdir()

        _create_concept_file(
            concepts_dir,
            "draft-idea",
            title="Draft Idea",
            status="draft",
            linked_files=["src/not_yet.py"],
        )

        issues = check_stale_concepts(project_root, lexibrary_dir)
        assert len(issues) == 0


# ---------------------------------------------------------------------------
# check_supersession_candidates
# ---------------------------------------------------------------------------


class TestCheckSupersessionCandidates:
    """Tests for check_supersession_candidates()."""

    def test_no_overlap(self, tmp_path: Path) -> None:
        """No issues when concepts have distinct titles and aliases."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()
        concepts_dir = lexibrary_dir / "concepts"
        concepts_dir.mkdir()

        _create_concept_file(
            concepts_dir,
            "authentication",
            title="Authentication",
            aliases=["authn"],
        )
        _create_concept_file(
            concepts_dir,
            "authorization",
            title="Authorization",
            aliases=["authz"],
        )

        issues = check_supersession_candidates(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_alias_overlap(self, tmp_path: Path) -> None:
        """Info issue when two concepts share the same alias."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()
        concepts_dir = lexibrary_dir / "concepts"
        concepts_dir.mkdir()

        _create_concept_file(
            concepts_dir,
            "authentication",
            title="Authentication",
            aliases=["auth"],
        )
        _create_concept_file(
            concepts_dir,
            "authorization",
            title="Authorization",
            aliases=["auth"],
        )

        issues = check_supersession_candidates(project_root, lexibrary_dir)
        assert len(issues) == 1
        issue = issues[0]
        assert issue.severity == "info"
        assert issue.check == "supersession_candidate"
        assert "Authentication" in issue.message
        assert "Authorization" in issue.message
        assert "auth" in issue.message
        assert "supersede" in issue.suggestion.lower()

    def test_title_alias_cross_match(self, tmp_path: Path) -> None:
        """Info issue when one concept's title matches another's alias."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()
        concepts_dir = lexibrary_dir / "concepts"
        concepts_dir.mkdir()

        _create_concept_file(
            concepts_dir,
            "logging",
            title="Logging",
            aliases=["log-system"],
        )
        _create_concept_file(
            concepts_dir,
            "log-system",
            title="Log System",
            aliases=["logging"],
        )

        issues = check_supersession_candidates(project_root, lexibrary_dir)
        assert len(issues) >= 1
        # Both names should appear in at least one issue
        messages = " ".join(i.message for i in issues)
        assert "Log System" in messages
        assert "Logging" in messages

    def test_deprecated_concepts_excluded(self, tmp_path: Path) -> None:
        """Deprecated concepts are excluded from supersession detection."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()
        concepts_dir = lexibrary_dir / "concepts"
        concepts_dir.mkdir()

        _create_concept_file(
            concepts_dir,
            "old-auth",
            title="Old Auth",
            status="deprecated",
            aliases=["auth"],
        )
        _create_concept_file(
            concepts_dir,
            "new-auth",
            title="New Auth",
            aliases=["auth"],
        )

        issues = check_supersession_candidates(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_no_concepts_dir(self, tmp_path: Path) -> None:
        """Returns empty list when concepts directory does not exist."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        issues = check_supersession_candidates(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_case_insensitive_matching(self, tmp_path: Path) -> None:
        """Overlap detection is case-insensitive."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()
        concepts_dir = lexibrary_dir / "concepts"
        concepts_dir.mkdir()

        _create_concept_file(
            concepts_dir,
            "concept-a",
            title="Concept A",
            aliases=["SharedName"],
        )
        _create_concept_file(
            concepts_dir,
            "concept-b",
            title="Concept B",
            aliases=["sharedname"],
        )

        issues = check_supersession_candidates(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert "sharedname" in issues[0].message

    def test_single_concept_no_self_overlap(self, tmp_path: Path) -> None:
        """A single concept does not produce a self-overlap issue."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()
        concepts_dir = lexibrary_dir / "concepts"
        concepts_dir.mkdir()

        _create_concept_file(
            concepts_dir,
            "only-one",
            title="Only One",
            aliases=["singleton"],
        )

        issues = check_supersession_candidates(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_supersession_candidate_registered(self) -> None:
        """supersession_candidate check is registered in AVAILABLE_CHECKS."""
        from lexibrary.validator import AVAILABLE_CHECKS

        assert "supersession_candidate" in AVAILABLE_CHECKS
        check_fn, severity = AVAILABLE_CHECKS["supersession_candidate"]
        assert check_fn is check_supersession_candidates
        assert severity == "info"


# ---------------------------------------------------------------------------
# Helpers for convention check tests
# ---------------------------------------------------------------------------


def _create_convention_file(
    conventions_dir: Path,
    slug: str,
    *,
    title: str = "",
    scope: str = "project",
    status: str = "active",
    tags: list[str] | None = None,
) -> Path:
    """Create a convention markdown file with frontmatter."""
    if not title:
        title = slug.replace("-", " ").title()

    conventions_dir.mkdir(parents=True, exist_ok=True)
    conv_path = conventions_dir / f"{slug}.md"

    tags_list = tags or []
    tags_yaml = "[" + ", ".join(tags_list) + "]" if tags_list else "[]"

    content = f"""---
title: {title}
id: CV-001
scope: {scope}
tags: {tags_yaml}
status: {status}
---

{title} is a convention for the project.
"""
    conv_path.write_text(content, encoding="utf-8")
    return conv_path


def _add_convention_comments(convention_path: Path, count: int) -> None:
    """Add multiple comments to the sibling .comments.yaml file."""
    from lexibrary.lifecycle.comments import append_comment
    from lexibrary.lifecycle.convention_comments import convention_comment_path
    from lexibrary.lifecycle.models import ArtefactComment

    comment_file = convention_comment_path(convention_path)
    for i in range(count):
        comment = ArtefactComment(
            body=f"Violation comment {i + 1}",
            date=datetime(2026, 1, 1, 12, 0, 0),
        )
        append_comment(comment_file, comment)


# ---------------------------------------------------------------------------
# check_convention_orphaned_scope
# ---------------------------------------------------------------------------


class TestCheckConventionOrphanedScope:
    """Tests for check_convention_orphaned_scope()."""

    def test_project_scope_always_valid(self, tmp_path: Path) -> None:
        """Convention with scope='project' never produces an issue."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        _create_convention_file(
            lexibrary_dir / "conventions",
            "use-dataclasses",
            scope="project",
        )

        issues = check_convention_orphaned_scope(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_valid_scope_directory_no_issue(self, tmp_path: Path) -> None:
        """No issue when scope directory exists."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        # Create the scope directory
        (project_root / "src" / "auth").mkdir(parents=True)

        _create_convention_file(
            lexibrary_dir / "conventions",
            "auth-convention",
            scope="src/auth",
        )

        issues = check_convention_orphaned_scope(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_missing_scope_directory_produces_warning(self, tmp_path: Path) -> None:
        """Warning issued when scope directory does not exist."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        # Do NOT create the scope directory
        _create_convention_file(
            lexibrary_dir / "conventions",
            "auth-convention",
            scope="src/nonexistent",
        )

        issues = check_convention_orphaned_scope(project_root, lexibrary_dir)
        assert len(issues) == 1
        issue = issues[0]
        assert issue.severity == "warning"
        assert issue.check == "convention_orphaned_scope"
        assert "src/nonexistent" in issue.message
        assert "conventions/auth-convention.md" in issue.artifact

    def test_deprecated_convention_skipped(self, tmp_path: Path) -> None:
        """Deprecated conventions are not checked for orphaned scope."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        _create_convention_file(
            lexibrary_dir / "conventions",
            "old-convention",
            scope="src/deleted",
            status="deprecated",
        )

        issues = check_convention_orphaned_scope(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_no_conventions_dir(self, tmp_path: Path) -> None:
        """Returns empty list when conventions directory does not exist."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        issues = check_convention_orphaned_scope(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_multiple_orphaned_scopes(self, tmp_path: Path) -> None:
        """Each orphaned convention produces its own issue."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        _create_convention_file(
            lexibrary_dir / "conventions",
            "conv-a",
            scope="src/missing-a",
        )
        _create_convention_file(
            lexibrary_dir / "conventions",
            "conv-b",
            scope="src/missing-b",
        )

        issues = check_convention_orphaned_scope(project_root, lexibrary_dir)
        assert len(issues) == 2
        messages = {i.message for i in issues}
        assert any("missing-a" in m for m in messages)
        assert any("missing-b" in m for m in messages)

    def test_draft_convention_with_missing_scope(self, tmp_path: Path) -> None:
        """Draft conventions with missing scope are still flagged."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        _create_convention_file(
            lexibrary_dir / "conventions",
            "draft-conv",
            scope="src/not-here",
            status="draft",
        )

        issues = check_convention_orphaned_scope(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert issues[0].severity == "warning"

    def test_multi_path_scope_all_exist_no_issue(self, tmp_path: Path) -> None:
        """Multi-path scope where all directories exist produces no issue."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        (project_root / "src/cli").mkdir(parents=True)
        (project_root / "src/services").mkdir(parents=True)

        _create_convention_file(
            lexibrary_dir / "conventions",
            "multi-scope",
            scope="src/cli, src/services",
        )

        issues = check_convention_orphaned_scope(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_multi_path_scope_one_missing_produces_warning(self, tmp_path: Path) -> None:
        """Multi-path scope where one directory is missing produces a warning."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        (project_root / "src/cli").mkdir(parents=True)
        # src/services intentionally not created

        _create_convention_file(
            lexibrary_dir / "conventions",
            "partial-scope",
            scope="src/cli, src/services",
        )

        issues = check_convention_orphaned_scope(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert "src/services" in issues[0].message
        assert issues[0].severity == "warning"

    def test_multi_path_scope_all_missing_produces_warning(self, tmp_path: Path) -> None:
        """Multi-path scope where all directories are missing produces a warning."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        _create_convention_file(
            lexibrary_dir / "conventions",
            "all-missing",
            scope="src/foo, src/bar",
        )

        issues = check_convention_orphaned_scope(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert "src/foo" in issues[0].message
        assert "src/bar" in issues[0].message


# ---------------------------------------------------------------------------
# check_convention_stale
# ---------------------------------------------------------------------------


class TestCheckConventionStale:
    """Tests for check_convention_stale()."""

    def test_active_convention_with_files_no_issue(self, tmp_path: Path) -> None:
        """No issue when active convention scope has source files."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        # Create scope directory with a source file
        scope_dir = project_root / "src" / "auth"
        scope_dir.mkdir(parents=True)
        (scope_dir / "login.py").write_text("def login(): pass\n")

        _create_convention_file(
            lexibrary_dir / "conventions",
            "auth-convention",
            scope="src/auth",
        )

        issues = check_convention_stale(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_active_convention_empty_scope_produces_info(self, tmp_path: Path) -> None:
        """Info issue when active convention scope has no source files."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        # Create scope directory but leave it empty
        scope_dir = project_root / "src" / "auth"
        scope_dir.mkdir(parents=True)

        _create_convention_file(
            lexibrary_dir / "conventions",
            "auth-convention",
            scope="src/auth",
        )

        issues = check_convention_stale(project_root, lexibrary_dir)
        assert len(issues) == 1
        issue = issues[0]
        assert issue.severity == "info"
        assert issue.check == "convention_stale"
        assert "src/auth" in issue.message

    def test_project_scope_skipped(self, tmp_path: Path) -> None:
        """Project-scoped conventions are not checked for staleness."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        _create_convention_file(
            lexibrary_dir / "conventions",
            "global-convention",
            scope="project",
        )

        issues = check_convention_stale(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_deprecated_convention_skipped(self, tmp_path: Path) -> None:
        """Deprecated conventions are not checked."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        scope_dir = project_root / "src" / "old"
        scope_dir.mkdir(parents=True)

        _create_convention_file(
            lexibrary_dir / "conventions",
            "old-conv",
            scope="src/old",
            status="deprecated",
        )

        issues = check_convention_stale(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_draft_convention_skipped(self, tmp_path: Path) -> None:
        """Draft conventions are not checked for staleness."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        scope_dir = project_root / "src" / "draft"
        scope_dir.mkdir(parents=True)

        _create_convention_file(
            lexibrary_dir / "conventions",
            "draft-conv",
            scope="src/draft",
            status="draft",
        )

        issues = check_convention_stale(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_missing_scope_not_flagged_as_stale(self, tmp_path: Path) -> None:
        """Missing scope directories are not flagged by stale check (orphaned_scope covers that)."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        _create_convention_file(
            lexibrary_dir / "conventions",
            "conv",
            scope="src/nonexistent",
        )

        issues = check_convention_stale(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_scope_with_only_subdirectories(self, tmp_path: Path) -> None:
        """Scope directory with subdirectories but no files is flagged as stale."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        scope_dir = project_root / "src" / "auth"
        scope_dir.mkdir(parents=True)
        (scope_dir / "subdir").mkdir()

        _create_convention_file(
            lexibrary_dir / "conventions",
            "auth-conv",
            scope="src/auth",
        )

        issues = check_convention_stale(project_root, lexibrary_dir)
        assert len(issues) == 1

    def test_no_conventions_dir(self, tmp_path: Path) -> None:
        """Returns empty list when conventions directory does not exist."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        issues = check_convention_stale(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_multi_path_scope_one_has_files_not_stale(self, tmp_path: Path) -> None:
        """Multi-path scope is not stale if at least one directory has files."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        (project_root / "src/cli").mkdir(parents=True)
        (project_root / "src/cli" / "app.py").write_text("# cli")
        (project_root / "src/services").mkdir(parents=True)
        # src/services has no files

        _create_convention_file(
            lexibrary_dir / "conventions",
            "multi-scope",
            scope="src/cli, src/services",
        )

        issues = check_convention_stale(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_multi_path_scope_all_empty_is_stale(self, tmp_path: Path) -> None:
        """Multi-path scope is stale when all directories exist but are empty."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        (project_root / "src/cli").mkdir(parents=True)
        (project_root / "src/services").mkdir(parents=True)

        _create_convention_file(
            lexibrary_dir / "conventions",
            "empty-multi",
            scope="src/cli, src/services",
        )

        issues = check_convention_stale(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert issues[0].check == "convention_stale"


# ---------------------------------------------------------------------------
# check_convention_gap
# ---------------------------------------------------------------------------


class TestCheckConventionGap:
    """Tests for check_convention_gap()."""

    def test_directory_with_conventions_no_issue(self, tmp_path: Path) -> None:
        """No issue when directory has applicable conventions."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()
        (lexibrary_dir / "conventions").mkdir()

        # Create a project-wide convention (applies to all directories)
        _create_convention_file(
            lexibrary_dir / "conventions",
            "global-rule",
            scope="project",
        )

        # Create a directory with 5+ files
        src_dir = project_root / "src"
        src_dir.mkdir()
        for i in range(6):
            (src_dir / f"file_{i}.py").write_text(f"# file {i}\n")

        config = _make_config()
        with patch("lexibrary.validator.checks.load_config", return_value=config):
            issues = check_convention_gap(project_root, lexibrary_dir)

        # Should not flag src/ since a project-wide convention applies
        gap_artifacts = [i.artifact for i in issues]
        assert "src" not in gap_artifacts

    def test_directory_without_conventions_flagged(self, tmp_path: Path) -> None:
        """Info issue when directory has 5+ files and no conventions."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()
        (lexibrary_dir / "conventions").mkdir()

        # Create a directory with 5+ files and NO conventions
        src_dir = project_root / "src"
        src_dir.mkdir()
        for i in range(6):
            (src_dir / f"file_{i}.py").write_text(f"# file {i}\n")

        config = _make_config()
        with patch("lexibrary.validator.checks.load_config", return_value=config):
            issues = check_convention_gap(project_root, lexibrary_dir)

        # Should find at least the src directory
        gap_artifacts = [i.artifact for i in issues]
        assert "src" in gap_artifacts
        matching = [i for i in issues if i.artifact == "src"]
        assert matching[0].severity == "info"
        assert matching[0].check == "convention_gap"
        assert "6 source files" in matching[0].message

    def test_directory_below_threshold_no_issue(self, tmp_path: Path) -> None:
        """No issue when directory has fewer than 5 files."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()
        (lexibrary_dir / "conventions").mkdir()

        src_dir = project_root / "src"
        src_dir.mkdir()
        for i in range(4):
            (src_dir / f"file_{i}.py").write_text(f"# file {i}\n")

        config = _make_config()
        with patch("lexibrary.validator.checks.load_config", return_value=config):
            issues = check_convention_gap(project_root, lexibrary_dir)

        gap_artifacts = [i.artifact for i in issues]
        assert "src" not in gap_artifacts

    def test_deprecated_conventions_excluded(self, tmp_path: Path) -> None:
        """Deprecated conventions do not count as applicable."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        # Create a deprecated project convention
        _create_convention_file(
            lexibrary_dir / "conventions",
            "old-rule",
            scope="project",
            status="deprecated",
        )

        src_dir = project_root / "src"
        src_dir.mkdir()
        for i in range(6):
            (src_dir / f"file_{i}.py").write_text(f"# file {i}\n")

        config = _make_config()
        with patch("lexibrary.validator.checks.load_config", return_value=config):
            issues = check_convention_gap(project_root, lexibrary_dir)

        gap_artifacts = [i.artifact for i in issues]
        assert "src" in gap_artifacts

    def test_no_conventions_dir_still_works(self, tmp_path: Path) -> None:
        """Gap check works even when conventions directory does not exist."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        src_dir = project_root / "src"
        src_dir.mkdir()
        for i in range(6):
            (src_dir / f"file_{i}.py").write_text(f"# file {i}\n")

        config = _make_config()
        with patch("lexibrary.validator.checks.load_config", return_value=config):
            issues = check_convention_gap(project_root, lexibrary_dir)

        gap_artifacts = [i.artifact for i in issues]
        assert "src" in gap_artifacts

    def test_hidden_files_excluded_from_count(self, tmp_path: Path) -> None:
        """Hidden files (starting with .) are not counted."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()
        (lexibrary_dir / "conventions").mkdir()

        src_dir = project_root / "src"
        src_dir.mkdir()
        # Create 4 visible + 2 hidden files
        for i in range(4):
            (src_dir / f"file_{i}.py").write_text(f"# file {i}\n")
        (src_dir / ".hidden1").write_text("hidden\n")
        (src_dir / ".hidden2").write_text("hidden\n")

        config = _make_config()
        with patch("lexibrary.validator.checks.load_config", return_value=config):
            issues = check_convention_gap(project_root, lexibrary_dir)

        gap_artifacts = [i.artifact for i in issues]
        # Only 4 visible files, below threshold of 5
        assert "src" not in gap_artifacts

    def test_config_load_failure_uses_default_scope(self, tmp_path: Path) -> None:
        """When config loading fails, default scope_root '.' is used."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()
        (lexibrary_dir / "conventions").mkdir()

        src_dir = project_root / "src"
        src_dir.mkdir()
        for i in range(6):
            (src_dir / f"file_{i}.py").write_text(f"# file {i}\n")

        with patch("lexibrary.validator.checks.load_config", side_effect=Exception("broken")):
            issues = check_convention_gap(project_root, lexibrary_dir)

        gap_artifacts = [i.artifact for i in issues]
        assert "src" in gap_artifacts


# ---------------------------------------------------------------------------
# check_convention_consistent_violation
# ---------------------------------------------------------------------------


class TestCheckConventionConsistentViolation:
    """Tests for check_convention_consistent_violation()."""

    def test_no_comments_no_issue(self, tmp_path: Path) -> None:
        """No issues when convention has no comments."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        _create_convention_file(
            lexibrary_dir / "conventions",
            "clean-convention",
        )

        issues = check_convention_consistent_violation(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_below_threshold_no_issue(self, tmp_path: Path) -> None:
        """No issue when comment count is below threshold (3)."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        conv_path = _create_convention_file(
            lexibrary_dir / "conventions",
            "some-convention",
        )

        _add_convention_comments(conv_path, 2)

        issues = check_convention_consistent_violation(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_at_threshold_produces_issue(self, tmp_path: Path) -> None:
        """Issue produced when comment count equals threshold (3)."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        conv_path = _create_convention_file(
            lexibrary_dir / "conventions",
            "violated-convention",
        )

        _add_convention_comments(conv_path, 3)

        issues = check_convention_consistent_violation(project_root, lexibrary_dir)
        assert len(issues) == 1
        issue = issues[0]
        assert issue.severity == "info"
        assert issue.check == "convention_consistent_violation"
        assert "3 comments" in issue.message
        assert "threshold: 3" in issue.message
        assert "conventions/violated-convention.md" in issue.artifact

    def test_exceeds_threshold_produces_issue(self, tmp_path: Path) -> None:
        """Issue produced when comment count exceeds threshold."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        conv_path = _create_convention_file(
            lexibrary_dir / "conventions",
            "bad-convention",
        )

        _add_convention_comments(conv_path, 5)

        issues = check_convention_consistent_violation(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert "5 comments" in issues[0].message
        assert "consistent violation" in issues[0].message

    def test_deprecated_convention_skipped(self, tmp_path: Path) -> None:
        """Deprecated conventions are not checked."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        conv_path = _create_convention_file(
            lexibrary_dir / "conventions",
            "deprecated-conv",
            status="deprecated",
        )

        _add_convention_comments(conv_path, 5)

        issues = check_convention_consistent_violation(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_multiple_conventions_with_violations(self, tmp_path: Path) -> None:
        """Each convention with violations produces its own issue."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        conv_a = _create_convention_file(
            lexibrary_dir / "conventions",
            "conv-a",
        )
        _add_convention_comments(conv_a, 4)

        conv_b = _create_convention_file(
            lexibrary_dir / "conventions",
            "conv-b",
        )
        _add_convention_comments(conv_b, 3)

        # conv-c below threshold
        conv_c = _create_convention_file(
            lexibrary_dir / "conventions",
            "conv-c",
        )
        _add_convention_comments(conv_c, 1)

        issues = check_convention_consistent_violation(project_root, lexibrary_dir)
        assert len(issues) == 2
        artifacts = {i.artifact for i in issues}
        assert "conventions/conv-a.md" in artifacts
        assert "conventions/conv-b.md" in artifacts

    def test_no_conventions_dir(self, tmp_path: Path) -> None:
        """Returns empty list when conventions directory does not exist."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        issues = check_convention_consistent_violation(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_suggestion_mentions_review(self, tmp_path: Path) -> None:
        """Suggestion text mentions reviewing the convention."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        conv_path = _create_convention_file(
            lexibrary_dir / "conventions",
            "problem-conv",
        )
        _add_convention_comments(conv_path, 3)

        issues = check_convention_consistent_violation(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert "review" in issues[0].suggestion.lower()


# ---------------------------------------------------------------------------
# Convention checks in AVAILABLE_CHECKS registry
# ---------------------------------------------------------------------------


class TestConventionChecksInAvailableChecks:
    """Verify convention checks are registered in AVAILABLE_CHECKS."""

    def test_convention_orphaned_scope_registered(self) -> None:
        from lexibrary.validator import AVAILABLE_CHECKS

        assert "convention_orphaned_scope" in AVAILABLE_CHECKS
        check_fn, severity = AVAILABLE_CHECKS["convention_orphaned_scope"]
        assert check_fn is check_convention_orphaned_scope
        assert severity == "warning"

    def test_convention_stale_registered(self) -> None:
        from lexibrary.validator import AVAILABLE_CHECKS

        assert "convention_stale" in AVAILABLE_CHECKS
        check_fn, severity = AVAILABLE_CHECKS["convention_stale"]
        assert check_fn is check_convention_stale
        assert severity == "info"

    def test_convention_gap_registered(self) -> None:
        from lexibrary.validator import AVAILABLE_CHECKS

        assert "convention_gap" in AVAILABLE_CHECKS
        check_fn, severity = AVAILABLE_CHECKS["convention_gap"]
        assert check_fn is check_convention_gap
        assert severity == "info"

    def test_convention_consistent_violation_registered(self) -> None:
        from lexibrary.validator import AVAILABLE_CHECKS

        assert "convention_consistent_violation" in AVAILABLE_CHECKS
        check_fn, severity = AVAILABLE_CHECKS["convention_consistent_violation"]
        assert check_fn is check_convention_consistent_violation
        assert severity == "info"


# ---------------------------------------------------------------------------
# check_resolved_post_staleness
# ---------------------------------------------------------------------------

_RESOLVED_STACK_POST_TEMPLATE = """\
---
id: {post_id}
title: {title}
tags:
  - test
status: {status}
created: {created}
author: tester
resolution_type: {resolution_type}
refs:
  files:
{refs_files}
---

## Problem

Something was broken.
"""


def _create_resolved_stack_post(
    lexibrary_dir: Path,
    post_id: str = "ST-001",
    title: str = "Test post",
    status: str = "resolved",
    created: str = "2026-01-01",
    resolution_type: str = "fix",
    refs_files: list[str] | None = None,
) -> Path:
    """Create a Stack post file with configurable fields."""
    stack_dir = lexibrary_dir / "stack"
    stack_dir.mkdir(parents=True, exist_ok=True)
    post_path = stack_dir / f"{post_id}.md"

    refs_lines = "\n".join(f"    - {f}" for f in refs_files) if refs_files else "    []"

    post_path.write_text(
        _RESOLVED_STACK_POST_TEMPLATE.format(
            post_id=post_id,
            title=title,
            status=status,
            created=created,
            resolution_type=resolution_type,
            refs_files=refs_lines,
        ),
        encoding="utf-8",
    )
    return post_path


class TestCheckResolvedPostStaleness:
    """Tests for check_resolved_post_staleness()."""

    def test_no_stack_dir(self, tmp_path: Path) -> None:
        """No issues when stack directory does not exist."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        issues = check_resolved_post_staleness(project_root, lexibrary_dir)
        assert issues == []

    def test_empty_stack_dir(self, tmp_path: Path) -> None:
        """No issues when stack directory is empty."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        stack_dir = lexibrary_dir / "stack"
        stack_dir.mkdir(parents=True)

        issues = check_resolved_post_staleness(project_root, lexibrary_dir)
        assert issues == []

    @patch(
        "lexibrary.validator.checks._count_commits_since",
        return_value=100,
    )
    @patch(
        "lexibrary.validator.checks._git_is_available",
        return_value=True,
    )
    @patch("lexibrary.validator.checks.load_config")
    def test_resolved_within_ttl_no_issue(
        self, mock_config: Any, mock_git: Any, mock_commits: Any, tmp_path: Path
    ) -> None:
        """Resolved post within TTL produces no issue."""
        from lexibrary.config.schema import StackConfig

        mock_config.return_value = LexibraryConfig(
            stack=StackConfig(staleness_ttl_commits=200),
        )

        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        _create_resolved_stack_post(
            lexibrary_dir,
            resolution_type="fix",
        )

        issues = check_resolved_post_staleness(project_root, lexibrary_dir)
        assert issues == []

    @patch(
        "lexibrary.validator.checks._count_commits_since",
        return_value=250,
    )
    @patch(
        "lexibrary.validator.checks._git_is_available",
        return_value=True,
    )
    @patch("lexibrary.validator.checks.load_config")
    def test_resolved_exceeding_ttl_produces_issue(
        self, mock_config: Any, mock_git: Any, mock_commits: Any, tmp_path: Path
    ) -> None:
        """Resolved post exceeding TTL produces info issue."""
        from lexibrary.config.schema import StackConfig

        mock_config.return_value = LexibraryConfig(
            stack=StackConfig(staleness_ttl_commits=200),
        )

        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        _create_resolved_stack_post(
            lexibrary_dir,
            resolution_type="fix",
        )

        issues = check_resolved_post_staleness(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert issues[0].severity == "info"
        assert issues[0].check == "resolved_post_staleness"
        assert "250 commits" in issues[0].message
        assert "TTL: 200" in issues[0].message

    @patch(
        "lexibrary.validator.checks._count_commits_since",
        return_value=120,
    )
    @patch(
        "lexibrary.validator.checks._git_is_available",
        return_value=True,
    )
    @patch("lexibrary.validator.checks.load_config")
    def test_short_ttl_applied_to_wontfix(
        self, mock_config: Any, mock_git: Any, mock_commits: Any, tmp_path: Path
    ) -> None:
        """wontfix posts use short TTL."""
        from lexibrary.config.schema import StackConfig

        mock_config.return_value = LexibraryConfig(
            stack=StackConfig(
                staleness_ttl_commits=200,
                staleness_ttl_short_commits=100,
            ),
        )

        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        _create_resolved_stack_post(
            lexibrary_dir,
            resolution_type="wontfix",
        )

        issues = check_resolved_post_staleness(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert issues[0].check == "resolved_post_staleness"
        assert "TTL: 100" in issues[0].message

    @patch(
        "lexibrary.validator.checks._count_commits_since",
        return_value=120,
    )
    @patch(
        "lexibrary.validator.checks._git_is_available",
        return_value=True,
    )
    @patch("lexibrary.validator.checks.load_config")
    def test_short_ttl_applied_to_by_design(
        self, mock_config: Any, mock_git: Any, mock_commits: Any, tmp_path: Path
    ) -> None:
        """by_design posts use short TTL."""
        from lexibrary.config.schema import StackConfig

        mock_config.return_value = LexibraryConfig(
            stack=StackConfig(
                staleness_ttl_commits=200,
                staleness_ttl_short_commits=100,
            ),
        )

        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        _create_resolved_stack_post(
            lexibrary_dir,
            resolution_type="by_design",
        )

        issues = check_resolved_post_staleness(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert issues[0].check == "resolved_post_staleness"

    @patch(
        "lexibrary.validator.checks._count_commits_since",
        return_value=120,
    )
    @patch(
        "lexibrary.validator.checks._git_is_available",
        return_value=True,
    )
    @patch("lexibrary.validator.checks.load_config")
    def test_short_ttl_applied_to_cannot_reproduce(
        self, mock_config: Any, mock_git: Any, mock_commits: Any, tmp_path: Path
    ) -> None:
        """cannot_reproduce posts use short TTL."""
        from lexibrary.config.schema import StackConfig

        mock_config.return_value = LexibraryConfig(
            stack=StackConfig(
                staleness_ttl_commits=200,
                staleness_ttl_short_commits=100,
            ),
        )

        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        _create_resolved_stack_post(
            lexibrary_dir,
            resolution_type="cannot_reproduce",
        )

        issues = check_resolved_post_staleness(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert issues[0].check == "resolved_post_staleness"

    @patch(
        "lexibrary.validator.checks._count_commits_since",
        return_value=50,
    )
    @patch(
        "lexibrary.validator.checks._git_is_available",
        return_value=True,
    )
    @patch("lexibrary.validator.checks.load_config")
    def test_deleted_file_ref_produces_issue(
        self, mock_config: Any, mock_git: Any, mock_commits: Any, tmp_path: Path
    ) -> None:
        """Resolved post with deleted file references produces info issue."""
        from lexibrary.config.schema import StackConfig

        mock_config.return_value = LexibraryConfig(
            stack=StackConfig(staleness_ttl_commits=200),
        )

        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        # Create the post referencing a file that does not exist
        _create_resolved_stack_post(
            lexibrary_dir,
            refs_files=["src/old_module.py"],
        )

        issues = check_resolved_post_staleness(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert issues[0].severity == "info"
        assert issues[0].check == "resolved_post_staleness"
        assert "src/old_module.py" in issues[0].message
        assert "deleted" in issues[0].message.lower()

    @patch(
        "lexibrary.validator.checks._count_commits_since",
        return_value=50,
    )
    @patch(
        "lexibrary.validator.checks._git_is_available",
        return_value=True,
    )
    @patch("lexibrary.validator.checks.load_config")
    def test_existing_file_ref_no_issue(
        self, mock_config: Any, mock_git: Any, mock_commits: Any, tmp_path: Path
    ) -> None:
        """Resolved post with existing file references produces no issue."""
        from lexibrary.config.schema import StackConfig

        mock_config.return_value = LexibraryConfig(
            stack=StackConfig(staleness_ttl_commits=200),
        )

        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        # Create the referenced file so it exists
        ref_file = tmp_path / "src" / "module.py"
        ref_file.parent.mkdir(parents=True)
        ref_file.write_text("pass\n", encoding="utf-8")

        _create_resolved_stack_post(
            lexibrary_dir,
            refs_files=["src/module.py"],
        )

        issues = check_resolved_post_staleness(project_root, lexibrary_dir)
        assert issues == []

    @patch(
        "lexibrary.validator.checks._count_commits_since",
        return_value=500,
    )
    @patch(
        "lexibrary.validator.checks._git_is_available",
        return_value=True,
    )
    @patch("lexibrary.validator.checks.load_config")
    def test_open_posts_never_checked(
        self, mock_config: Any, mock_git: Any, mock_commits: Any, tmp_path: Path
    ) -> None:
        """Open posts are never checked for staleness, even with high age."""
        from lexibrary.config.schema import StackConfig

        mock_config.return_value = LexibraryConfig(
            stack=StackConfig(staleness_ttl_commits=200),
        )

        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        # Create an open post referencing a deleted file
        _create_resolved_stack_post(
            lexibrary_dir,
            status="open",
            refs_files=["src/deleted.py"],
        )

        issues = check_resolved_post_staleness(project_root, lexibrary_dir)
        assert issues == []

    @patch(
        "lexibrary.validator.checks._count_commits_since",
        return_value=500,
    )
    @patch(
        "lexibrary.validator.checks._git_is_available",
        return_value=True,
    )
    @patch("lexibrary.validator.checks.load_config")
    def test_stale_posts_skipped(
        self, mock_config: Any, mock_git: Any, mock_commits: Any, tmp_path: Path
    ) -> None:
        """Posts already marked stale are skipped."""
        from lexibrary.config.schema import StackConfig

        mock_config.return_value = LexibraryConfig(
            stack=StackConfig(staleness_ttl_commits=200),
        )

        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        _create_resolved_stack_post(
            lexibrary_dir,
            status="stale",
            refs_files=["src/deleted.py"],
        )

        issues = check_resolved_post_staleness(project_root, lexibrary_dir)
        assert issues == []

    @patch(
        "lexibrary.validator.checks._count_commits_since",
        return_value=500,
    )
    @patch(
        "lexibrary.validator.checks._git_is_available",
        return_value=True,
    )
    @patch("lexibrary.validator.checks.load_config")
    def test_duplicate_posts_skipped(
        self, mock_config: Any, mock_git: Any, mock_commits: Any, tmp_path: Path
    ) -> None:
        """Duplicate posts are skipped."""
        from lexibrary.config.schema import StackConfig

        mock_config.return_value = LexibraryConfig(
            stack=StackConfig(staleness_ttl_commits=200),
        )

        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        _create_resolved_stack_post(
            lexibrary_dir,
            status="duplicate",
        )

        issues = check_resolved_post_staleness(project_root, lexibrary_dir)
        assert issues == []

    @patch(
        "lexibrary.validator.checks._git_is_available",
        return_value=False,
    )
    @patch("lexibrary.validator.checks.load_config")
    def test_git_unavailable_skips_ttl_checks(
        self, mock_config: Any, mock_git: Any, tmp_path: Path
    ) -> None:
        """When git is not available, TTL checks are skipped without error
        and only file-existence checks run."""
        from lexibrary.config.schema import StackConfig

        mock_config.return_value = LexibraryConfig(
            stack=StackConfig(staleness_ttl_commits=200),
        )

        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        # Create a resolved post referencing a deleted file
        _create_resolved_stack_post(
            lexibrary_dir,
            refs_files=["src/missing.py"],
        )

        issues = check_resolved_post_staleness(project_root, lexibrary_dir)
        # Should produce exactly one issue (deleted file ref) but no TTL issue
        assert len(issues) == 1
        assert "deleted" in issues[0].message.lower() or "missing" in issues[0].message.lower()
        assert issues[0].check == "resolved_post_staleness"

    @patch(
        "lexibrary.validator.checks._git_is_available",
        return_value=False,
    )
    @patch("lexibrary.validator.checks.load_config")
    def test_git_unavailable_no_file_refs_no_issue(
        self, mock_config: Any, mock_git: Any, tmp_path: Path
    ) -> None:
        """When git is unavailable and there are no file refs, no issues."""
        from lexibrary.config.schema import StackConfig

        mock_config.return_value = LexibraryConfig(
            stack=StackConfig(staleness_ttl_commits=200),
        )

        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        _create_resolved_stack_post(lexibrary_dir)

        issues = check_resolved_post_staleness(project_root, lexibrary_dir)
        assert issues == []

    @patch(
        "lexibrary.validator.checks._count_commits_since",
        return_value=300,
    )
    @patch(
        "lexibrary.validator.checks._git_is_available",
        return_value=True,
    )
    @patch("lexibrary.validator.checks.load_config")
    def test_both_ttl_and_deleted_refs_produce_two_issues(
        self, mock_config: Any, mock_git: Any, mock_commits: Any, tmp_path: Path
    ) -> None:
        """Post exceeding TTL and having deleted refs produces two issues."""
        from lexibrary.config.schema import StackConfig

        mock_config.return_value = LexibraryConfig(
            stack=StackConfig(staleness_ttl_commits=200),
        )

        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        _create_resolved_stack_post(
            lexibrary_dir,
            refs_files=["src/deleted.py"],
        )

        issues = check_resolved_post_staleness(project_root, lexibrary_dir)
        assert len(issues) == 2
        checks = {i.check for i in issues}
        assert checks == {"resolved_post_staleness"}

    def test_resolved_post_staleness_registered(self) -> None:
        """check_resolved_post_staleness is registered in AVAILABLE_CHECKS."""
        from lexibrary.validator import AVAILABLE_CHECKS

        assert "resolved_post_staleness" in AVAILABLE_CHECKS
        check_fn, severity = AVAILABLE_CHECKS["resolved_post_staleness"]
        assert check_fn is check_resolved_post_staleness
        assert severity == "info"

    @patch("lexibrary.validator.checks.load_config", side_effect=Exception("no config"))
    @patch(
        "lexibrary.validator.checks._git_is_available",
        return_value=True,
    )
    @patch(
        "lexibrary.validator.checks._count_commits_since",
        return_value=250,
    )
    def test_config_load_failure_uses_defaults(
        self, mock_commits: Any, mock_git: Any, mock_config: Any, tmp_path: Path
    ) -> None:
        """When config loading fails, default TTL values are used."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        _create_resolved_stack_post(lexibrary_dir)

        issues = check_resolved_post_staleness(project_root, lexibrary_dir)
        # Default TTL is 200, 250 > 200 so should produce an issue
        assert len(issues) == 1
        assert "TTL: 200" in issues[0].message
