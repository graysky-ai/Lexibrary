"""Tests for orphaned .aindex detection and cleanup.

Tests find_orphaned_aindex() check and fix_orphaned_aindex() fixer.
Covers: orphaned file detected, non-orphan preserved, empty parent dirs
cleaned, designs root preserved.
"""

from __future__ import annotations

from pathlib import Path

from lexibrary.config.schema import LexibraryConfig, TokenBudgetConfig
from lexibrary.utils.paths import DESIGNS_DIR, LEXIBRARY_DIR
from lexibrary.validator.checks import find_orphaned_aindex
from lexibrary.validator.fixes import FIXERS, fix_orphaned_aindex
from lexibrary.validator.report import ValidationIssue

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_AINDEX_META = (
    '<!-- lexibrary:meta source="{dir}" source_hash="abc123"'
    ' generated="2026-01-01T12:00:00" generator="lexibrary-v2" -->'
)

_AINDEX_TEMPLATE = """\
# {directory_path}

Test directory.

## Child Map

| Name | Type | Description |
| --- | --- | --- |
(none)

## Local Conventions

(none)

{meta}
"""


def _write_aindex(lexibrary_dir: Path, directory_path: str) -> Path:
    """Write a .aindex file to the designs mirror path."""
    aindex = lexibrary_dir / DESIGNS_DIR / directory_path / ".aindex"
    aindex.parent.mkdir(parents=True, exist_ok=True)
    meta = _AINDEX_META.format(dir=directory_path)
    aindex.write_text(
        _AINDEX_TEMPLATE.format(directory_path=directory_path, meta=meta),
        encoding="utf-8",
    )
    return aindex


def _make_config() -> LexibraryConfig:
    return LexibraryConfig(
        scope_root=".",
        token_budgets=TokenBudgetConfig(design_file_tokens=400),
    )


def _make_issue(artifact: str) -> ValidationIssue:
    return ValidationIssue(
        severity="warning",
        check="orphaned_aindex",
        message="Orphaned .aindex file",
        artifact=artifact,
    )


# ---------------------------------------------------------------------------
# find_orphaned_aindex — detection
# ---------------------------------------------------------------------------


class TestFindOrphanedAindex:
    """Tests for find_orphaned_aindex()."""

    def test_orphaned_aindex_detected(self, tmp_path: Path) -> None:
        """An .aindex whose source directory no longer exists is flagged."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        # Create an .aindex for src/old_module/ but do NOT create the source dir
        _write_aindex(lexibrary_dir, "src/old_module")

        issues = find_orphaned_aindex(project_root, lexibrary_dir)
        assert len(issues) == 1
        issue = issues[0]
        assert issue.severity == "warning"
        assert issue.check == "orphaned_aindex"
        assert "src/old_module" in issue.message
        assert "no longer exists" in issue.message
        assert issue.artifact == f"{DESIGNS_DIR}/src/old_module/.aindex"

    def test_non_orphan_preserved(self, tmp_path: Path) -> None:
        """An .aindex whose source directory exists produces no issues."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        # Create both the source directory and the .aindex
        src_dir = project_root / "src" / "auth"
        src_dir.mkdir(parents=True)
        (src_dir / "login.py").write_text("pass", encoding="utf-8")

        _write_aindex(lexibrary_dir, "src/auth")

        issues = find_orphaned_aindex(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_mixed_orphaned_and_valid(self, tmp_path: Path) -> None:
        """Only orphaned .aindex files produce issues; valid ones are preserved."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        # Valid: source dir exists
        valid_dir = project_root / "src" / "valid"
        valid_dir.mkdir(parents=True)
        (valid_dir / "main.py").write_text("pass", encoding="utf-8")
        _write_aindex(lexibrary_dir, "src/valid")

        # Orphaned: source dir does not exist
        _write_aindex(lexibrary_dir, "src/removed")

        issues = find_orphaned_aindex(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert "src/removed" in issues[0].message

    def test_no_designs_dir(self, tmp_path: Path) -> None:
        """When .lexibrary/designs/ does not exist, returns empty list."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()
        # No designs/ dir created

        issues = find_orphaned_aindex(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_empty_designs_dir(self, tmp_path: Path) -> None:
        """When .lexibrary/designs/ exists but is empty, returns empty list."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()
        (lexibrary_dir / DESIGNS_DIR).mkdir()

        issues = find_orphaned_aindex(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_root_aindex_with_project_root(self, tmp_path: Path) -> None:
        """An .aindex at designs/.aindex (for project root) is not orphaned."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        # The root .aindex corresponds to project_root itself (relative path ".")
        _write_aindex(lexibrary_dir, ".")

        issues = find_orphaned_aindex(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_deeply_nested_orphan(self, tmp_path: Path) -> None:
        """A deeply nested orphaned .aindex is detected."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        # Create a deeply nested .aindex with no source dir
        _write_aindex(lexibrary_dir, "src/packages/core/utils")

        issues = find_orphaned_aindex(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert "src/packages/core/utils" in issues[0].message

    def test_multiple_orphans(self, tmp_path: Path) -> None:
        """Multiple orphaned .aindex files each produce their own issue."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        _write_aindex(lexibrary_dir, "src/deleted_a")
        _write_aindex(lexibrary_dir, "src/deleted_b")

        issues = find_orphaned_aindex(project_root, lexibrary_dir)
        assert len(issues) == 2
        artifacts = {i.artifact for i in issues}
        assert f"{DESIGNS_DIR}/src/deleted_a/.aindex" in artifacts
        assert f"{DESIGNS_DIR}/src/deleted_b/.aindex" in artifacts


# ---------------------------------------------------------------------------
# fix_orphaned_aindex — cleanup
# ---------------------------------------------------------------------------


class TestFixOrphanedAindex:
    """Tests for fix_orphaned_aindex()."""

    def test_orphan_deleted(self, tmp_path: Path) -> None:
        """Orphaned .aindex file is deleted when source directory does not exist."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        aindex_file = _write_aindex(lexibrary_dir, "src/old_module")
        assert aindex_file.exists()

        issue = _make_issue(artifact=f"{DESIGNS_DIR}/src/old_module/.aindex")
        config = _make_config()

        result = fix_orphaned_aindex(issue, project_root, config)
        assert result.fixed is True
        assert "deleted" in result.message
        assert not aindex_file.exists()

    def test_empty_parent_dirs_cleaned(self, tmp_path: Path) -> None:
        """Empty parent directories are removed up to designs root."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()
        designs_dir = lexibrary_dir / DESIGNS_DIR

        # Create a nested orphaned .aindex
        aindex_file = _write_aindex(lexibrary_dir, "src/old_pkg/subpkg")
        assert aindex_file.exists()

        issue = _make_issue(artifact=f"{DESIGNS_DIR}/src/old_pkg/subpkg/.aindex")
        config = _make_config()

        result = fix_orphaned_aindex(issue, project_root, config)
        assert result.fixed is True

        # The aindex file should be deleted
        assert not aindex_file.exists()
        # Empty parent dirs should be cleaned up
        assert not (designs_dir / "src" / "old_pkg" / "subpkg").exists()
        assert not (designs_dir / "src" / "old_pkg").exists()
        # But the src dir in designs might have been removed too since it was empty
        # and the designs root should be preserved
        assert designs_dir.exists()

    def test_designs_root_preserved(self, tmp_path: Path) -> None:
        """The designs root directory itself is never deleted."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()
        designs_dir = lexibrary_dir / DESIGNS_DIR
        designs_dir.mkdir()

        # Write .aindex directly in designs root (for project root dir ".")
        aindex_file = designs_dir / ".aindex"
        aindex_file.write_text("# root .aindex\n", encoding="utf-8")

        issue = _make_issue(artifact=f"{DESIGNS_DIR}/.aindex")
        config = _make_config()

        result = fix_orphaned_aindex(issue, project_root, config)
        assert result.fixed is True
        assert not aindex_file.exists()
        # designs root must still exist
        assert designs_dir.exists()

    def test_non_empty_parent_preserved(self, tmp_path: Path) -> None:
        """Parent directories with other files are not removed."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()
        designs_dir = lexibrary_dir / DESIGNS_DIR

        # Create two .aindex files in sibling dirs
        _write_aindex(lexibrary_dir, "src/keep_me")
        aindex_orphan = _write_aindex(lexibrary_dir, "src/remove_me")

        issue = _make_issue(artifact=f"{DESIGNS_DIR}/src/remove_me/.aindex")
        config = _make_config()

        result = fix_orphaned_aindex(issue, project_root, config)
        assert result.fixed is True
        assert not aindex_orphan.exists()
        # The src/ dir in designs should still exist because keep_me is still there
        assert (designs_dir / "src").exists()
        assert (designs_dir / "src" / "keep_me" / ".aindex").exists()

    def test_already_removed(self, tmp_path: Path) -> None:
        """Gracefully handles .aindex that was already deleted."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()
        (lexibrary_dir / DESIGNS_DIR).mkdir()

        issue = _make_issue(artifact=f"{DESIGNS_DIR}/src/gone/.aindex")
        config = _make_config()

        result = fix_orphaned_aindex(issue, project_root, config)
        assert result.fixed is False
        assert "already removed" in result.message


# ---------------------------------------------------------------------------
# FIXERS registry
# ---------------------------------------------------------------------------


class TestOrphanedAindexInFixersRegistry:
    """Verify orphaned_aindex is registered in the FIXERS registry."""

    def test_registered(self) -> None:
        assert "orphaned_aindex" in FIXERS
        assert FIXERS["orphaned_aindex"] is fix_orphaned_aindex


# ---------------------------------------------------------------------------
# AVAILABLE_CHECKS registry
# ---------------------------------------------------------------------------


class TestOrphanedAindexInAvailableChecks:
    """Verify orphaned_aindex is registered in AVAILABLE_CHECKS."""

    def test_registered(self) -> None:
        from lexibrary.validator import AVAILABLE_CHECKS

        assert "orphaned_aindex" in AVAILABLE_CHECKS
        check_fn, severity = AVAILABLE_CHECKS["orphaned_aindex"]
        assert check_fn is find_orphaned_aindex
        assert severity == "warning"
