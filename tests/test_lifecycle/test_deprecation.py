"""Unit tests for the deprecation lifecycle module."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lexibrary.artifacts.design_file import (
    DesignFile,
    DesignFileFrontmatter,
    StalenessMetadata,
)
from lexibrary.artifacts.design_file_parser import (
    parse_design_file,
    parse_design_file_frontmatter,
)
from lexibrary.artifacts.design_file_serializer import serialize_design_file
from lexibrary.lifecycle.deprecation import (
    OrphanedDesign,
    RenameMapping,
    _count_commits_since,
    _is_committed_deletion,
    check_ttl_expiry,
    deprecate_design,
    detect_orphaned_designs,
    detect_renames,
    detect_renames_by_hash,
    hard_delete_expired,
    mark_unlinked,
    migrate_design_on_rename,
    restore_design,
)
from lexibrary.utils.paths import mirror_path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_design_file(
    project_root: Path,
    source_rel: str,
    *,
    status: str = "active",
    deprecated_at: datetime | None = None,
    deprecated_reason: str | None = None,
    source_hash: str = "abc123",
) -> Path:
    """Create a minimal design file on disk and return its path."""
    design_path = mirror_path(project_root, Path(source_rel))
    design_path.parent.mkdir(parents=True, exist_ok=True)

    data = DesignFile(
        source_path=source_rel,
        frontmatter=DesignFileFrontmatter(
            description=f"Design for {source_rel}",
            id="DS-001",
            updated_by="archivist",
            status=status,
            deprecated_at=deprecated_at,
            deprecated_reason=deprecated_reason,
        ),
        summary=f"Design for {source_rel}",
        interface_contract="def example(): ...",
        dependencies=[],
        dependents=[],
        metadata=StalenessMetadata(
            source=source_rel,
            source_hash=source_hash,
            interface_hash=None,
            design_hash="placeholder",
            generated=datetime(2026, 1, 1, tzinfo=UTC),
            generator="test",
        ),
    )
    design_path.write_text(serialize_design_file(data), encoding="utf-8")
    return design_path


def _make_source_file(project_root: Path, source_rel: str, content: str = "# source") -> Path:
    """Create a source file on disk and return its path."""
    source_path = project_root / source_rel
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(content, encoding="utf-8")
    return source_path


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


class TestOrphanedDesign:
    """Tests for the OrphanedDesign dataclass."""

    def test_create(self) -> None:
        orphan = OrphanedDesign(
            design_path=Path("/lex/designs/src/foo.py.md"),
            source_path=Path("src/foo.py"),
            committed=True,
        )
        assert orphan.design_path == Path("/lex/designs/src/foo.py.md")
        assert orphan.source_path == Path("src/foo.py")
        assert orphan.committed is True

    def test_uncommitted(self) -> None:
        orphan = OrphanedDesign(
            design_path=Path("/lex/designs/src/bar.py.md"),
            source_path=Path("src/bar.py"),
            committed=False,
        )
        assert orphan.committed is False


class TestRenameMapping:
    """Tests for the RenameMapping dataclass."""

    def test_create(self) -> None:
        mapping = RenameMapping(
            old_path=Path("src/old.py"),
            new_path=Path("src/new.py"),
        )
        assert mapping.old_path == Path("src/old.py")
        assert mapping.new_path == Path("src/new.py")


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


class TestIsCommittedDeletion:
    """Tests for _is_committed_deletion()."""

    def test_tracked_file_means_uncommitted(self, tmp_path: Path) -> None:
        """If git ls-files finds the file (exit 0), deletion is uncommitted."""
        with patch("lexibrary.lifecycle.deprecation.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = _is_committed_deletion(tmp_path, Path("src/module.py"))
        assert result is False

    def test_untracked_file_means_committed(self, tmp_path: Path) -> None:
        """If git ls-files does not find the file (exit 1), deletion is committed."""
        with patch("lexibrary.lifecycle.deprecation.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            result = _is_committed_deletion(tmp_path, Path("src/module.py"))
        assert result is True

    def test_git_not_installed_returns_true(self, tmp_path: Path) -> None:
        """If git is not installed, treat as committed."""
        with patch(
            "lexibrary.lifecycle.deprecation.subprocess.run",
            side_effect=FileNotFoundError,
        ):
            result = _is_committed_deletion(tmp_path, Path("src/module.py"))
        assert result is True


class TestCountCommitsSince:
    """Tests for _count_commits_since()."""

    def test_returns_count(self, tmp_path: Path) -> None:
        with patch("lexibrary.lifecycle.deprecation.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="42\n")
            count = _count_commits_since(tmp_path, "2026-01-01T00:00:00+00:00")
        assert count == 42

    def test_returns_zero_on_error(self, tmp_path: Path) -> None:
        with patch("lexibrary.lifecycle.deprecation.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            count = _count_commits_since(tmp_path, "2026-01-01T00:00:00+00:00")
        assert count == 0

    def test_returns_zero_on_missing_git(self, tmp_path: Path) -> None:
        with patch(
            "lexibrary.lifecycle.deprecation.subprocess.run",
            side_effect=FileNotFoundError,
        ):
            count = _count_commits_since(tmp_path, "2026-01-01T00:00:00+00:00")
        assert count == 0


# ---------------------------------------------------------------------------
# detect_orphaned_designs()
# ---------------------------------------------------------------------------


class TestDetectOrphanedDesigns:
    """Tests for detect_orphaned_designs()."""

    def test_no_orphans_when_sources_exist(self, tmp_path: Path) -> None:
        """All design files have existing sources -- no orphans."""
        _make_source_file(tmp_path, "src/module.py")
        _make_design_file(tmp_path, "src/module.py")

        lexibrary_dir = tmp_path / ".lexibrary"
        with patch("lexibrary.lifecycle.deprecation._is_committed_deletion"):
            orphans = detect_orphaned_designs(tmp_path, lexibrary_dir)
        assert orphans == []

    def test_detects_orphan_with_missing_source(self, tmp_path: Path) -> None:
        """Design file exists but source is missing -- detected as orphan."""
        design_path = _make_design_file(tmp_path, "src/deleted.py")
        # Do NOT create the source file

        lexibrary_dir = tmp_path / ".lexibrary"
        with patch(
            "lexibrary.lifecycle.deprecation._is_committed_deletion",
            return_value=True,
        ):
            orphans = detect_orphaned_designs(tmp_path, lexibrary_dir)

        assert len(orphans) == 1
        assert orphans[0].design_path == design_path
        assert orphans[0].source_path == Path("src/deleted.py")
        assert orphans[0].committed is True

    def test_uncommitted_deletion(self, tmp_path: Path) -> None:
        """Source deleted but not committed -- committed=False."""
        _make_design_file(tmp_path, "src/uncommitted.py")

        lexibrary_dir = tmp_path / ".lexibrary"
        with patch(
            "lexibrary.lifecycle.deprecation._is_committed_deletion",
            return_value=False,
        ):
            orphans = detect_orphaned_designs(tmp_path, lexibrary_dir)

        assert len(orphans) == 1
        assert orphans[0].committed is False

    def test_empty_when_no_designs_directory(self, tmp_path: Path) -> None:
        """Returns empty list when designs directory doesn't exist."""
        lexibrary_dir = tmp_path / ".lexibrary"
        orphans = detect_orphaned_designs(tmp_path, lexibrary_dir)
        assert orphans == []

    def test_multiple_orphans_and_non_orphans(self, tmp_path: Path) -> None:
        """Mix of orphaned and non-orphaned design files."""
        _make_source_file(tmp_path, "src/alive.py")
        _make_design_file(tmp_path, "src/alive.py")
        _make_design_file(tmp_path, "src/dead1.py")
        _make_design_file(tmp_path, "src/dead2.py")

        lexibrary_dir = tmp_path / ".lexibrary"
        with patch(
            "lexibrary.lifecycle.deprecation._is_committed_deletion",
            return_value=True,
        ):
            orphans = detect_orphaned_designs(tmp_path, lexibrary_dir)

        assert len(orphans) == 2
        source_paths = {o.source_path for o in orphans}
        assert source_paths == {Path("src/dead1.py"), Path("src/dead2.py")}


# ---------------------------------------------------------------------------
# deprecate_design(), mark_unlinked(), restore_design()
# ---------------------------------------------------------------------------


class TestDeprecateDesign:
    """Tests for deprecate_design()."""

    def test_sets_deprecated_fields(self, tmp_path: Path) -> None:
        design_path = _make_design_file(tmp_path, "src/module.py")
        deprecate_design(design_path, "source_deleted")

        fm = parse_design_file_frontmatter(design_path)
        assert fm is not None
        assert fm.status == "deprecated"
        assert fm.deprecated_at is not None
        assert fm.deprecated_reason == "source_deleted"

    def test_preserves_description(self, tmp_path: Path) -> None:
        design_path = _make_design_file(tmp_path, "src/module.py")
        deprecate_design(design_path, "source_deleted")

        fm = parse_design_file_frontmatter(design_path)
        assert fm is not None
        assert fm.description == "Design for src/module.py"

    def test_noop_on_unparseable_file(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "bad.md"
        bad_file.write_text("not a valid design file", encoding="utf-8")
        # Should not raise
        deprecate_design(bad_file, "source_deleted")
        assert bad_file.read_text() == "not a valid design file"


class TestMarkUnlinked:
    """Tests for mark_unlinked()."""

    def test_sets_unlinked_status(self, tmp_path: Path) -> None:
        design_path = _make_design_file(tmp_path, "src/module.py")
        mark_unlinked(design_path)

        fm = parse_design_file_frontmatter(design_path)
        assert fm is not None
        assert fm.status == "unlinked"
        assert fm.deprecated_at is None

    def test_noop_on_unparseable_file(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "bad.md"
        bad_file.write_text("invalid", encoding="utf-8")
        mark_unlinked(bad_file)
        assert bad_file.read_text() == "invalid"


class TestRestoreDesign:
    """Tests for restore_design()."""

    def test_restores_deprecated_to_active(self, tmp_path: Path) -> None:
        design_path = _make_design_file(
            tmp_path,
            "src/module.py",
            status="deprecated",
            deprecated_at=datetime(2026, 1, 1, tzinfo=UTC),
            deprecated_reason="source_deleted",
        )
        restore_design(design_path)

        fm = parse_design_file_frontmatter(design_path)
        assert fm is not None
        assert fm.status == "active"
        assert fm.deprecated_at is None
        assert fm.deprecated_reason is None

    def test_restores_unlinked_to_active(self, tmp_path: Path) -> None:
        design_path = _make_design_file(tmp_path, "src/module.py", status="unlinked")
        restore_design(design_path)

        fm = parse_design_file_frontmatter(design_path)
        assert fm is not None
        assert fm.status == "active"

    def test_noop_on_unparseable_file(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "bad.md"
        bad_file.write_text("invalid", encoding="utf-8")
        restore_design(bad_file)
        assert bad_file.read_text() == "invalid"


# ---------------------------------------------------------------------------
# check_ttl_expiry()
# ---------------------------------------------------------------------------


class TestCheckTTLExpiry:
    """Tests for check_ttl_expiry()."""

    def test_not_expired(self, tmp_path: Path) -> None:
        """10 commits ago with TTL of 50 -- not expired."""
        design_path = _make_design_file(
            tmp_path,
            "src/module.py",
            status="deprecated",
            deprecated_at=datetime(2026, 1, 1, tzinfo=UTC),
            deprecated_reason="source_deleted",
        )
        with patch(
            "lexibrary.lifecycle.deprecation._count_commits_since",
            return_value=10,
        ):
            result = check_ttl_expiry(design_path, tmp_path, ttl_commits=50)
        assert result is False

    def test_expired(self, tmp_path: Path) -> None:
        """60 commits ago with TTL of 50 -- expired."""
        design_path = _make_design_file(
            tmp_path,
            "src/module.py",
            status="deprecated",
            deprecated_at=datetime(2026, 1, 1, tzinfo=UTC),
            deprecated_reason="source_deleted",
        )
        with patch(
            "lexibrary.lifecycle.deprecation._count_commits_since",
            return_value=60,
        ):
            result = check_ttl_expiry(design_path, tmp_path, ttl_commits=50)
        assert result is True

    def test_exactly_at_ttl_not_expired(self, tmp_path: Path) -> None:
        """Exactly at TTL boundary -- not expired (must exceed, not equal)."""
        design_path = _make_design_file(
            tmp_path,
            "src/module.py",
            status="deprecated",
            deprecated_at=datetime(2026, 1, 1, tzinfo=UTC),
            deprecated_reason="source_deleted",
        )
        with patch(
            "lexibrary.lifecycle.deprecation._count_commits_since",
            return_value=50,
        ):
            result = check_ttl_expiry(design_path, tmp_path, ttl_commits=50)
        assert result is False

    def test_non_deprecated_returns_false(self, tmp_path: Path) -> None:
        """Active design file -- not eligible for TTL expiry."""
        design_path = _make_design_file(tmp_path, "src/module.py", status="active")
        result = check_ttl_expiry(design_path, tmp_path, ttl_commits=50)
        assert result is False

    def test_deprecated_without_timestamp_returns_false(self, tmp_path: Path) -> None:
        """Deprecated but missing deprecated_at -- cannot check TTL."""
        design_path = _make_design_file(tmp_path, "src/module.py", status="deprecated")
        result = check_ttl_expiry(design_path, tmp_path, ttl_commits=50)
        assert result is False

    def test_unparseable_file_returns_false(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "bad.md"
        bad_file.write_text("invalid", encoding="utf-8")
        result = check_ttl_expiry(bad_file, tmp_path, ttl_commits=50)
        assert result is False


# ---------------------------------------------------------------------------
# hard_delete_expired()
# ---------------------------------------------------------------------------


class TestHardDeleteExpired:
    """Tests for hard_delete_expired()."""

    def test_deletes_expired_design(self, tmp_path: Path) -> None:
        design_path = _make_design_file(
            tmp_path,
            "src/expired.py",
            status="deprecated",
            deprecated_at=datetime(2026, 1, 1, tzinfo=UTC),
            deprecated_reason="source_deleted",
        )
        lexibrary_dir = tmp_path / ".lexibrary"

        with patch(
            "lexibrary.lifecycle.deprecation._count_commits_since",
            return_value=100,
        ):
            deleted = hard_delete_expired(tmp_path, lexibrary_dir, ttl_commits=50)

        assert design_path in deleted
        assert not design_path.exists()

    def test_preserves_non_expired_design(self, tmp_path: Path) -> None:
        design_path = _make_design_file(
            tmp_path,
            "src/recent.py",
            status="deprecated",
            deprecated_at=datetime(2026, 1, 1, tzinfo=UTC),
            deprecated_reason="source_deleted",
        )
        lexibrary_dir = tmp_path / ".lexibrary"

        with patch(
            "lexibrary.lifecycle.deprecation._count_commits_since",
            return_value=10,
        ):
            deleted = hard_delete_expired(tmp_path, lexibrary_dir, ttl_commits=50)

        assert deleted == []
        assert design_path.exists()

    def test_empty_when_no_deprecated(self, tmp_path: Path) -> None:
        _make_design_file(tmp_path, "src/active.py", status="active")
        lexibrary_dir = tmp_path / ".lexibrary"

        deleted = hard_delete_expired(tmp_path, lexibrary_dir, ttl_commits=50)
        assert deleted == []

    def test_empty_when_no_designs_dir(self, tmp_path: Path) -> None:
        lexibrary_dir = tmp_path / ".lexibrary"
        deleted = hard_delete_expired(tmp_path, lexibrary_dir, ttl_commits=50)
        assert deleted == []

    def test_mixed_expired_and_non_expired(self, tmp_path: Path) -> None:
        expired_path = _make_design_file(
            tmp_path,
            "src/old.py",
            status="deprecated",
            deprecated_at=datetime(2025, 1, 1, tzinfo=UTC),
            deprecated_reason="source_deleted",
        )
        recent_path = _make_design_file(
            tmp_path,
            "src/recent.py",
            status="deprecated",
            deprecated_at=datetime(2026, 3, 1, tzinfo=UTC),
            deprecated_reason="source_deleted",
        )
        lexibrary_dir = tmp_path / ".lexibrary"

        # Make _count_commits_since return different values based on the timestamp
        def mock_count(root: Path, since_iso: str) -> int:
            if "2025" in since_iso:
                return 100  # old -- expired
            return 5  # recent -- not expired

        with patch(
            "lexibrary.lifecycle.deprecation._count_commits_since",
            side_effect=mock_count,
        ):
            deleted = hard_delete_expired(tmp_path, lexibrary_dir, ttl_commits=50)

        assert expired_path in deleted
        assert recent_path not in deleted
        assert not expired_path.exists()
        assert recent_path.exists()


# ---------------------------------------------------------------------------
# detect_renames()
# ---------------------------------------------------------------------------


class TestDetectRenames:
    """Tests for detect_renames()."""

    def test_detects_git_rename(self, tmp_path: Path) -> None:
        with patch("lexibrary.lifecycle.deprecation.subprocess.run") as mock_run:
            # First call: staged renames (none)
            # Second call: HEAD~1..HEAD rename detected
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout=""),
                MagicMock(
                    returncode=0,
                    stdout="R100\tsrc/old_name.py\tsrc/new_name.py\n",
                ),
            ]
            mappings = detect_renames(tmp_path)

        assert len(mappings) == 1
        assert mappings[0].old_path == Path("src/old_name.py")
        assert mappings[0].new_path == Path("src/new_name.py")

    def test_no_renames(self, tmp_path: Path) -> None:
        with patch("lexibrary.lifecycle.deprecation.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="")
            mappings = detect_renames(tmp_path)
        assert mappings == []

    def test_deduplicates_renames(self, tmp_path: Path) -> None:
        """Same rename detected in both staged and committed -- only one mapping."""
        with patch("lexibrary.lifecycle.deprecation.subprocess.run") as mock_run:
            rename_line = "R100\tsrc/old.py\tsrc/new.py\n"
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout=rename_line),
                MagicMock(returncode=0, stdout=rename_line),
            ]
            mappings = detect_renames(tmp_path)

        assert len(mappings) == 1

    def test_multiple_renames(self, tmp_path: Path) -> None:
        with patch("lexibrary.lifecycle.deprecation.subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(
                    returncode=0,
                    stdout="R100\tsrc/a.py\tsrc/a_new.py\nR095\tsrc/b.py\tsrc/b_new.py\n",
                ),
                MagicMock(returncode=0, stdout=""),
            ]
            mappings = detect_renames(tmp_path)

        assert len(mappings) == 2

    def test_ignores_non_rename_status(self, tmp_path: Path) -> None:
        """Lines with A (added), D (deleted), M (modified) should be ignored."""
        with patch("lexibrary.lifecycle.deprecation.subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(
                    returncode=0,
                    stdout="A\tsrc/new.py\nD\tsrc/old.py\nM\tsrc/mod.py\n",
                ),
                MagicMock(returncode=0, stdout=""),
            ]
            mappings = detect_renames(tmp_path)

        assert mappings == []

    def test_git_not_available(self, tmp_path: Path) -> None:
        with patch(
            "lexibrary.lifecycle.deprecation.subprocess.run",
            side_effect=FileNotFoundError,
        ):
            mappings = detect_renames(tmp_path)
        assert mappings == []


# ---------------------------------------------------------------------------
# migrate_design_on_rename()
# ---------------------------------------------------------------------------


class TestMigrateDesignOnRename:
    """Tests for migrate_design_on_rename()."""

    def test_moves_and_updates_design(self, tmp_path: Path) -> None:
        old_source = Path("src/old.py")
        new_source = Path("src/new.py")
        old_design = _make_design_file(tmp_path, str(old_source))

        new_design_path = migrate_design_on_rename(tmp_path, old_source, new_source)

        # Old design file should be removed
        assert not old_design.exists()
        # New design file should exist
        assert new_design_path.exists()
        assert new_design_path == mirror_path(tmp_path, new_source)

        # Verify content was updated
        parsed = parse_design_file(new_design_path)
        assert parsed is not None
        assert parsed.source_path == str(new_source)
        assert parsed.metadata.source == str(new_source)

    def test_resets_deprecated_status(self, tmp_path: Path) -> None:
        old_source = Path("src/old.py")
        new_source = Path("src/new.py")
        _make_design_file(
            tmp_path,
            str(old_source),
            status="deprecated",
            deprecated_at=datetime(2026, 1, 1, tzinfo=UTC),
            deprecated_reason="source_deleted",
        )

        new_design_path = migrate_design_on_rename(tmp_path, old_source, new_source)

        parsed = parse_design_file(new_design_path)
        assert parsed is not None
        assert parsed.frontmatter.status == "active"
        assert parsed.frontmatter.deprecated_at is None
        assert parsed.frontmatter.deprecated_reason is None

    def test_resets_unlinked_status(self, tmp_path: Path) -> None:
        old_source = Path("src/old.py")
        new_source = Path("src/new.py")
        _make_design_file(tmp_path, str(old_source), status="unlinked")

        new_design_path = migrate_design_on_rename(tmp_path, old_source, new_source)

        parsed = parse_design_file(new_design_path)
        assert parsed is not None
        assert parsed.frontmatter.status == "active"

    def test_preserves_description(self, tmp_path: Path) -> None:
        old_source = Path("src/old.py")
        new_source = Path("src/new.py")
        _make_design_file(tmp_path, str(old_source))

        new_design_path = migrate_design_on_rename(tmp_path, old_source, new_source)

        parsed = parse_design_file(new_design_path)
        assert parsed is not None
        assert parsed.frontmatter.description == "Design for src/old.py"

    def test_raises_on_missing_old_design(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            migrate_design_on_rename(
                tmp_path,
                Path("src/nonexistent.py"),
                Path("src/new.py"),
            )

    def test_handles_unparseable_old_design(self, tmp_path: Path) -> None:
        """If old design is unparseable, just move it as-is."""
        old_source = Path("src/old.py")
        new_source = Path("src/new.py")
        old_design = mirror_path(tmp_path, old_source)
        old_design.parent.mkdir(parents=True, exist_ok=True)
        old_design.write_text("unparseable content", encoding="utf-8")

        new_design_path = migrate_design_on_rename(tmp_path, old_source, new_source)

        assert not old_design.exists()
        assert new_design_path.exists()
        assert new_design_path.read_text() == "unparseable content"

    def test_creates_parent_dirs_for_new_location(self, tmp_path: Path) -> None:
        old_source = Path("src/old.py")
        new_source = Path("src/deeply/nested/new.py")
        _make_design_file(tmp_path, str(old_source))

        new_design_path = migrate_design_on_rename(tmp_path, old_source, new_source)

        assert new_design_path.exists()
        assert new_design_path == mirror_path(tmp_path, new_source)


# ---------------------------------------------------------------------------
# detect_renames_by_hash()
# ---------------------------------------------------------------------------


class TestDetectRenamesByHash:
    """Tests for detect_renames_by_hash()."""

    def test_matches_by_content_hash(self, tmp_path: Path) -> None:
        """Deprecated design's source_hash matches a new file's content hash."""
        content = "# identical content"
        import hashlib

        expected_hash = hashlib.sha256(content.encode()).hexdigest()

        # Create a deprecated design with source_hash matching the content
        design_path = _make_design_file(
            tmp_path,
            "src/old.py",
            status="deprecated",
            deprecated_at=datetime(2026, 1, 1, tzinfo=UTC),
            deprecated_reason="source_deleted",
            source_hash=expected_hash,
        )

        # Create the new file with the same content
        new_file = _make_source_file(tmp_path, "src/new.py", content)

        mappings = detect_renames_by_hash(
            deprecated_designs=[design_path],
            new_files=[new_file],
            project_root=tmp_path,
        )

        assert len(mappings) == 1
        assert mappings[0].old_path == Path("src/old.py")
        assert mappings[0].new_path == Path("src/new.py")

    def test_no_match_different_content(self, tmp_path: Path) -> None:
        """Different content hashes -- no match."""
        design_path = _make_design_file(
            tmp_path,
            "src/old.py",
            status="deprecated",
            deprecated_at=datetime(2026, 1, 1, tzinfo=UTC),
            deprecated_reason="source_deleted",
            source_hash="hash_of_old_content",
        )

        new_file = _make_source_file(tmp_path, "src/new.py", "different content")

        mappings = detect_renames_by_hash(
            deprecated_designs=[design_path],
            new_files=[new_file],
            project_root=tmp_path,
        )

        assert mappings == []

    def test_empty_deprecated_list(self, tmp_path: Path) -> None:
        new_file = _make_source_file(tmp_path, "src/new.py")
        mappings = detect_renames_by_hash(
            deprecated_designs=[],
            new_files=[new_file],
            project_root=tmp_path,
        )
        assert mappings == []

    def test_empty_new_files_list(self, tmp_path: Path) -> None:
        design_path = _make_design_file(tmp_path, "src/old.py")
        mappings = detect_renames_by_hash(
            deprecated_designs=[design_path],
            new_files=[],
            project_root=tmp_path,
        )
        assert mappings == []

    def test_one_to_one_matching_only(self, tmp_path: Path) -> None:
        """Each hash should match at most once (no duplicate mappings)."""
        content = "# shared content"
        import hashlib

        expected_hash = hashlib.sha256(content.encode()).hexdigest()

        design_path = _make_design_file(
            tmp_path,
            "src/old.py",
            source_hash=expected_hash,
            status="deprecated",
            deprecated_at=datetime(2026, 1, 1, tzinfo=UTC),
            deprecated_reason="source_deleted",
        )

        new_file_1 = _make_source_file(tmp_path, "src/new1.py", content)
        new_file_2 = _make_source_file(tmp_path, "src/new2.py", content)

        mappings = detect_renames_by_hash(
            deprecated_designs=[design_path],
            new_files=[new_file_1, new_file_2],
            project_root=tmp_path,
        )

        # Only one match (first encountered)
        assert len(mappings) == 1


# ---------------------------------------------------------------------------
# Integration: deprecate -> check TTL -> restore round-trip
# ---------------------------------------------------------------------------


class TestDeprecationRoundTrip:
    """End-to-end round-trip tests for the deprecation lifecycle."""

    def test_deprecate_then_restore(self, tmp_path: Path) -> None:
        design_path = _make_design_file(tmp_path, "src/module.py")

        # Deprecate
        deprecate_design(design_path, "source_deleted")
        fm = parse_design_file_frontmatter(design_path)
        assert fm is not None
        assert fm.status == "deprecated"

        # Restore
        restore_design(design_path)
        fm = parse_design_file_frontmatter(design_path)
        assert fm is not None
        assert fm.status == "active"
        assert fm.deprecated_at is None
        assert fm.deprecated_reason is None

    def test_mark_unlinked_then_deprecate(self, tmp_path: Path) -> None:
        design_path = _make_design_file(tmp_path, "src/module.py")

        # First mark as unlinked (uncommitted deletion)
        mark_unlinked(design_path)
        fm = parse_design_file_frontmatter(design_path)
        assert fm is not None
        assert fm.status == "unlinked"

        # Then deprecate (after commit)
        deprecate_design(design_path, "source_deleted")
        fm = parse_design_file_frontmatter(design_path)
        assert fm is not None
        assert fm.status == "deprecated"
        assert fm.deprecated_at is not None

    def test_full_lifecycle_detect_deprecate_expire_delete(self, tmp_path: Path) -> None:
        """Full lifecycle: detect orphan -> deprecate -> TTL check -> hard delete."""
        # Create design without source
        design_path = _make_design_file(tmp_path, "src/deleted.py")
        lexibrary_dir = tmp_path / ".lexibrary"

        # Detect orphans
        with patch(
            "lexibrary.lifecycle.deprecation._is_committed_deletion",
            return_value=True,
        ):
            orphans = detect_orphaned_designs(tmp_path, lexibrary_dir)
        assert len(orphans) == 1

        # Deprecate
        deprecate_design(design_path, "source_deleted")

        # Check TTL -- not expired yet
        with patch(
            "lexibrary.lifecycle.deprecation._count_commits_since",
            return_value=10,
        ):
            assert check_ttl_expiry(design_path, tmp_path, ttl_commits=50) is False

        # Check TTL -- now expired
        with patch(
            "lexibrary.lifecycle.deprecation._count_commits_since",
            return_value=100,
        ):
            assert check_ttl_expiry(design_path, tmp_path, ttl_commits=50) is True

        # Hard delete
        with patch(
            "lexibrary.lifecycle.deprecation._count_commits_since",
            return_value=100,
        ):
            deleted = hard_delete_expired(tmp_path, lexibrary_dir, ttl_commits=50)

        assert design_path in deleted
        assert not design_path.exists()
