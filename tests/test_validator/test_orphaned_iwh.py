"""Tests for orphaned .iwh detection and cleanup.

Tests find_orphaned_iwh() check and fix_orphaned_iwh() fixer.
Covers: orphaned file detected, valid not flagged, no designs dir,
unparseable still flagged, fix removes orphaned, fix preserves valid.
"""

from __future__ import annotations

from pathlib import Path

from lexibrary.config.schema import LexibraryConfig, TokenBudgetConfig
from lexibrary.utils.paths import DESIGNS_DIR, LEXIBRARY_DIR
from lexibrary.validator.checks import find_orphaned_iwh
from lexibrary.validator.fixes import FIXERS, fix_orphaned_iwh
from lexibrary.validator.report import ValidationIssue

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_IWH_CONTENT = """\
---
author: test-agent
created: 2026-01-15T10:30:00Z
scope: incomplete
---

Work in progress on this module.
"""

_CORRUPT_IWH_CONTENT = "this is not valid YAML frontmatter at all {{{"


def _write_iwh(lexibrary_dir: Path, directory_path: str, *, content: str | None = None) -> Path:
    """Write a .iwh file to the designs mirror path."""
    iwh = lexibrary_dir / DESIGNS_DIR / directory_path / ".iwh"
    iwh.parent.mkdir(parents=True, exist_ok=True)
    iwh.write_text(content or _VALID_IWH_CONTENT, encoding="utf-8")
    return iwh


def _make_config() -> LexibraryConfig:
    return LexibraryConfig(
        token_budgets=TokenBudgetConfig(design_file_tokens=400),
    )


def _make_issue(artifact: str) -> ValidationIssue:
    return ValidationIssue(
        severity="info",
        check="orphaned_iwh",
        message="Orphaned .iwh file",
        artifact=artifact,
    )


# ---------------------------------------------------------------------------
# find_orphaned_iwh -- detection
# ---------------------------------------------------------------------------


class TestFindOrphanedIwh:
    """Tests for find_orphaned_iwh()."""

    def test_orphaned_iwh_detected(self, tmp_path: Path) -> None:
        """An .iwh whose source directory no longer exists is flagged."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        # Create an .iwh for src/deleted/ but do NOT create the source dir
        _write_iwh(lexibrary_dir, "src/deleted")

        issues = find_orphaned_iwh(project_root, lexibrary_dir)
        assert len(issues) == 1
        issue = issues[0]
        assert issue.severity == "info"
        assert issue.check == "orphaned_iwh"
        assert "src/deleted" in issue.message
        assert "no longer exists" in issue.message
        assert issue.artifact == f"{DESIGNS_DIR}/src/deleted/.iwh"
        assert issue.suggestion  # has a suggestion

    def test_valid_iwh_not_flagged(self, tmp_path: Path) -> None:
        """An .iwh whose source directory exists produces no issues."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        # Create both the source directory and the .iwh
        src_dir = project_root / "src" / "auth"
        src_dir.mkdir(parents=True)
        (src_dir / "login.py").write_text("pass", encoding="utf-8")

        _write_iwh(lexibrary_dir, "src/auth")

        issues = find_orphaned_iwh(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_no_designs_dir(self, tmp_path: Path) -> None:
        """When .lexibrary/designs/ does not exist, returns empty list."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()
        # No designs/ dir created

        issues = find_orphaned_iwh(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_unparseable_iwh_still_flagged(self, tmp_path: Path) -> None:
        """Corrupt .iwh content is still flagged if source dir is missing.

        Detection is path-based, not content-based.
        """
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        # Create an .iwh with corrupt content for a missing source dir
        _write_iwh(lexibrary_dir, "src/gone", content=_CORRUPT_IWH_CONTENT)

        issues = find_orphaned_iwh(project_root, lexibrary_dir)
        assert len(issues) == 1
        issue = issues[0]
        assert issue.severity == "info"
        assert issue.check == "orphaned_iwh"
        assert "src/gone" in issue.message

    def test_mixed_orphaned_and_valid(self, tmp_path: Path) -> None:
        """Only orphaned .iwh files produce issues; valid ones are preserved."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        # Valid: source dir exists
        valid_dir = project_root / "src" / "valid"
        valid_dir.mkdir(parents=True)
        (valid_dir / "main.py").write_text("pass", encoding="utf-8")
        _write_iwh(lexibrary_dir, "src/valid")

        # Orphaned: source dir does not exist
        _write_iwh(lexibrary_dir, "src/removed")

        issues = find_orphaned_iwh(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert "src/removed" in issues[0].message


# ---------------------------------------------------------------------------
# fix_orphaned_iwh -- cleanup
# ---------------------------------------------------------------------------


class TestFixOrphanedIwh:
    """Tests for fix_orphaned_iwh()."""

    def test_orphan_deleted(self, tmp_path: Path) -> None:
        """Orphaned .iwh file is deleted when source directory does not exist."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        iwh_file = _write_iwh(lexibrary_dir, "src/old_module")
        assert iwh_file.exists()

        issue = _make_issue(artifact=f"{DESIGNS_DIR}/src/old_module/.iwh")
        config = _make_config()

        result = fix_orphaned_iwh(issue, project_root, config)
        assert result.fixed is True
        assert "deleted" in result.message
        assert not iwh_file.exists()

    def test_valid_iwh_preserved(self, tmp_path: Path) -> None:
        """Valid .iwh files (whose source dir exists) are not removed by the fixer.

        The fixer itself does not re-check validity -- it trusts the issue.
        But this test verifies the detection + fix pipeline: only orphaned
        signals get issues, so only those get fixed.
        """
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        # Create a valid .iwh with an existing source dir
        src_dir = project_root / "src" / "keep"
        src_dir.mkdir(parents=True)
        (src_dir / "app.py").write_text("pass", encoding="utf-8")
        valid_iwh = _write_iwh(lexibrary_dir, "src/keep")

        # Create an orphaned .iwh
        orphan_iwh = _write_iwh(lexibrary_dir, "src/remove_me")

        # Only the orphan should be detected
        issues = find_orphaned_iwh(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert "src/remove_me" in issues[0].message

        # Fix only the orphaned issue
        config = _make_config()
        result = fix_orphaned_iwh(issues[0], project_root, config)
        assert result.fixed is True
        assert not orphan_iwh.exists()

        # The valid .iwh should still be there
        assert valid_iwh.exists()

    def test_already_removed(self, tmp_path: Path) -> None:
        """Gracefully handles .iwh that was already deleted."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()
        (lexibrary_dir / DESIGNS_DIR).mkdir()

        issue = _make_issue(artifact=f"{DESIGNS_DIR}/src/gone/.iwh")
        config = _make_config()

        result = fix_orphaned_iwh(issue, project_root, config)
        assert result.fixed is False
        assert "already removed" in result.message

    def test_empty_parent_dirs_cleaned(self, tmp_path: Path) -> None:
        """Empty parent directories are removed up to designs root."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()
        designs_dir = lexibrary_dir / DESIGNS_DIR

        # Create a nested orphaned .iwh
        iwh_file = _write_iwh(lexibrary_dir, "src/old_pkg/subpkg")
        assert iwh_file.exists()

        issue = _make_issue(artifact=f"{DESIGNS_DIR}/src/old_pkg/subpkg/.iwh")
        config = _make_config()

        result = fix_orphaned_iwh(issue, project_root, config)
        assert result.fixed is True

        # The iwh file should be deleted
        assert not iwh_file.exists()
        # Empty parent dirs should be cleaned up
        assert not (designs_dir / "src" / "old_pkg" / "subpkg").exists()
        assert not (designs_dir / "src" / "old_pkg").exists()
        # The designs root should be preserved
        assert designs_dir.exists()


# ---------------------------------------------------------------------------
# FIXERS registry
# ---------------------------------------------------------------------------


class TestOrphanedIwhInFixersRegistry:
    """Verify orphaned_iwh is registered in the FIXERS registry."""

    def test_registered(self) -> None:
        assert "orphaned_iwh" in FIXERS
        assert FIXERS["orphaned_iwh"] is fix_orphaned_iwh


# ---------------------------------------------------------------------------
# AVAILABLE_CHECKS registry
# ---------------------------------------------------------------------------


class TestOrphanedIwhInAvailableChecks:
    """Verify orphaned_iwh is registered in AVAILABLE_CHECKS."""

    def test_registered(self) -> None:
        from lexibrary.validator import AVAILABLE_CHECKS

        assert "orphaned_iwh" in AVAILABLE_CHECKS
        check_fn, severity = AVAILABLE_CHECKS["orphaned_iwh"]
        assert check_fn is find_orphaned_iwh
        assert severity == "info"
