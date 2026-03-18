"""Tests for convention hard deletion (TTL expiry and comment cleanup).

Tests for ``lexibrary.lifecycle.convention_deprecation``:
- TTL expiry checking for deprecated conventions
- Hard deletion of convention .md files and sibling .comments.yaml files
- Preservation of non-expired and non-deprecated conventions
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from lexibrary.lifecycle.convention_deprecation import (
    ConventionDeletionResult,
    check_convention_ttl_expiry,
    hard_delete_expired_conventions,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_convention_file(
    project_root: Path,
    slug: str,
    *,
    title: str = "Test Convention",
    status: str = "active",
    scope: str = "project",
    deprecated_at: str | None = None,
    body: str = "Always use dataclasses for value objects.\n",
) -> Path:
    """Create a convention .md file in .lexibrary/conventions/."""
    conventions_dir = project_root / ".lexibrary" / "conventions"
    conventions_dir.mkdir(parents=True, exist_ok=True)

    convention_path = conventions_dir / f"{slug}.md"

    lines = [
        "---",
        f"title: '{title}'",
        f"scope: {scope}",
        "tags: []",
        f"status: {status}",
        "source: user",
    ]
    if deprecated_at is not None:
        lines.append(f"deprecated_at: '{deprecated_at}'")
    lines.append("---")
    lines.append("")
    lines.append(body)

    convention_path.write_text("\n".join(lines), encoding="utf-8")
    return convention_path


def _create_comment_file(convention_path: Path) -> Path:
    """Create a sibling .comments.yaml file for a convention."""
    comment_path = convention_path.with_suffix(".comments.yaml")
    comment_path.write_text(
        "comments:\n  - body: 'A test comment'\n    date: '2026-01-01T00:00:00+00:00'\n",
        encoding="utf-8",
    )
    return comment_path


# ---------------------------------------------------------------------------
# check_convention_ttl_expiry()
# ---------------------------------------------------------------------------


class TestCheckConventionTTLExpiry:
    """Tests for check_convention_ttl_expiry()."""

    def test_not_expired(self, tmp_path: Path) -> None:
        """10 commits ago with TTL of 50 -- not expired."""
        convention_path = _create_convention_file(
            tmp_path,
            "old-convention",
            title="Old Convention",
            status="deprecated",
            deprecated_at="2026-01-01T00:00:00",
        )
        with patch(
            "lexibrary.lifecycle.convention_deprecation._count_commits_since",
            return_value=10,
        ):
            result = check_convention_ttl_expiry(convention_path, tmp_path, ttl_commits=50)
        assert result is False

    def test_expired(self, tmp_path: Path) -> None:
        """60 commits ago with TTL of 50 -- expired."""
        convention_path = _create_convention_file(
            tmp_path,
            "expired-convention",
            title="Expired Convention",
            status="deprecated",
            deprecated_at="2025-01-01T00:00:00",
        )
        with patch(
            "lexibrary.lifecycle.convention_deprecation._count_commits_since",
            return_value=60,
        ):
            result = check_convention_ttl_expiry(convention_path, tmp_path, ttl_commits=50)
        assert result is True

    def test_exactly_at_ttl_not_expired(self, tmp_path: Path) -> None:
        """Exactly at TTL boundary -- not expired (must exceed, not equal)."""
        convention_path = _create_convention_file(
            tmp_path,
            "boundary-convention",
            title="Boundary Convention",
            status="deprecated",
            deprecated_at="2026-01-01T00:00:00",
        )
        with patch(
            "lexibrary.lifecycle.convention_deprecation._count_commits_since",
            return_value=50,
        ):
            result = check_convention_ttl_expiry(convention_path, tmp_path, ttl_commits=50)
        assert result is False

    def test_active_convention_returns_false(self, tmp_path: Path) -> None:
        """Active convention -- not eligible for TTL expiry."""
        convention_path = _create_convention_file(
            tmp_path, "active-convention", title="Active", status="active"
        )
        result = check_convention_ttl_expiry(convention_path, tmp_path, ttl_commits=50)
        assert result is False

    def test_deprecated_without_timestamp_returns_false(self, tmp_path: Path) -> None:
        """Deprecated but no deprecated_at -- cannot check TTL."""
        convention_path = _create_convention_file(
            tmp_path, "no-timestamp", title="No Timestamp", status="deprecated"
        )
        result = check_convention_ttl_expiry(convention_path, tmp_path, ttl_commits=50)
        assert result is False

    def test_unparseable_file_returns_false(self, tmp_path: Path) -> None:
        """Unparseable file returns False."""
        conventions_dir = tmp_path / ".lexibrary" / "conventions"
        conventions_dir.mkdir(parents=True)
        bad_file = conventions_dir / "bad.md"
        bad_file.write_text("not valid yaml frontmatter", encoding="utf-8")
        result = check_convention_ttl_expiry(bad_file, tmp_path, ttl_commits=50)
        assert result is False

    def test_draft_convention_returns_false(self, tmp_path: Path) -> None:
        """Draft convention -- not eligible for TTL expiry."""
        convention_path = _create_convention_file(
            tmp_path, "draft-convention", title="Draft", status="draft"
        )
        result = check_convention_ttl_expiry(convention_path, tmp_path, ttl_commits=50)
        assert result is False

    def test_custom_ttl(self, tmp_path: Path) -> None:
        """Custom TTL of 100 -- 75 commits is not expired."""
        convention_path = _create_convention_file(
            tmp_path,
            "custom-ttl",
            title="Custom TTL",
            status="deprecated",
            deprecated_at="2025-06-01T00:00:00",
        )
        with patch(
            "lexibrary.lifecycle.convention_deprecation._count_commits_since",
            return_value=75,
        ):
            result = check_convention_ttl_expiry(convention_path, tmp_path, ttl_commits=100)
        assert result is False


# ---------------------------------------------------------------------------
# hard_delete_expired_conventions()
# ---------------------------------------------------------------------------


class TestHardDeleteExpiredConventions:
    """Tests for hard_delete_expired_conventions()."""

    def test_deletes_expired_convention(self, tmp_path: Path) -> None:
        """Expired deprecated convention is deleted."""
        convention_path = _create_convention_file(
            tmp_path,
            "expired",
            title="Expired",
            status="deprecated",
            deprecated_at="2025-01-01T00:00:00",
        )
        lexibrary_dir = tmp_path / ".lexibrary"

        with patch(
            "lexibrary.lifecycle.convention_deprecation._count_commits_since",
            return_value=100,
        ):
            result = hard_delete_expired_conventions(tmp_path, lexibrary_dir, ttl_commits=50)

        assert convention_path in result.deleted
        assert not convention_path.exists()

    def test_preserves_non_expired_convention(self, tmp_path: Path) -> None:
        """Non-expired deprecated convention is preserved."""
        convention_path = _create_convention_file(
            tmp_path,
            "recent",
            title="Recent",
            status="deprecated",
            deprecated_at="2026-03-01T00:00:00",
        )
        lexibrary_dir = tmp_path / ".lexibrary"

        with patch(
            "lexibrary.lifecycle.convention_deprecation._count_commits_since",
            return_value=10,
        ):
            result = hard_delete_expired_conventions(tmp_path, lexibrary_dir, ttl_commits=50)

        assert result.deleted == []
        assert convention_path.exists()

    def test_preserves_active_convention(self, tmp_path: Path) -> None:
        """Active conventions are never deleted."""
        convention_path = _create_convention_file(
            tmp_path, "active", title="Active", status="active"
        )
        lexibrary_dir = tmp_path / ".lexibrary"

        result = hard_delete_expired_conventions(tmp_path, lexibrary_dir, ttl_commits=50)

        assert result.deleted == []
        assert convention_path.exists()

    def test_deletes_sibling_comment_file(self, tmp_path: Path) -> None:
        """Sibling .comments.yaml is deleted along with the convention."""
        convention_path = _create_convention_file(
            tmp_path,
            "with-comments",
            title="With Comments",
            status="deprecated",
            deprecated_at="2025-01-01T00:00:00",
        )
        comment_path = _create_comment_file(convention_path)
        lexibrary_dir = tmp_path / ".lexibrary"

        assert comment_path.exists()

        with patch(
            "lexibrary.lifecycle.convention_deprecation._count_commits_since",
            return_value=100,
        ):
            result = hard_delete_expired_conventions(tmp_path, lexibrary_dir, ttl_commits=50)

        assert convention_path in result.deleted
        assert not convention_path.exists()
        assert comment_path in result.comments_deleted
        assert not comment_path.exists()

    def test_comment_file_absent_still_succeeds(self, tmp_path: Path) -> None:
        """Deletion succeeds even when no .comments.yaml exists."""
        convention_path = _create_convention_file(
            tmp_path,
            "no-comments",
            title="No Comments",
            status="deprecated",
            deprecated_at="2025-01-01T00:00:00",
        )
        lexibrary_dir = tmp_path / ".lexibrary"

        # No comment file created
        comment_path = convention_path.with_suffix(".comments.yaml")
        assert not comment_path.exists()

        with patch(
            "lexibrary.lifecycle.convention_deprecation._count_commits_since",
            return_value=100,
        ):
            result = hard_delete_expired_conventions(tmp_path, lexibrary_dir, ttl_commits=50)

        assert convention_path in result.deleted
        assert not convention_path.exists()
        assert result.comments_deleted == []

    def test_empty_when_no_conventions_dir(self, tmp_path: Path) -> None:
        """Returns empty result when conventions/ directory doesn't exist."""
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir(parents=True, exist_ok=True)

        result = hard_delete_expired_conventions(tmp_path, lexibrary_dir, ttl_commits=50)

        assert result.deleted == []
        assert result.comments_deleted == []

    def test_mixed_expired_and_non_expired(self, tmp_path: Path) -> None:
        """Mix of expired and non-expired deprecated conventions."""
        expired_path = _create_convention_file(
            tmp_path,
            "old-convention",
            title="Old Convention",
            status="deprecated",
            deprecated_at="2025-01-01T00:00:00",
        )
        recent_path = _create_convention_file(
            tmp_path,
            "recent-convention",
            title="Recent Convention",
            status="deprecated",
            deprecated_at="2026-03-01T00:00:00",
        )
        lexibrary_dir = tmp_path / ".lexibrary"

        def mock_count(root: Path, since_iso: str) -> int:
            if "2025" in since_iso:
                return 100  # old -- expired
            return 5  # recent -- not expired

        with patch(
            "lexibrary.lifecycle.convention_deprecation._count_commits_since",
            side_effect=mock_count,
        ):
            result = hard_delete_expired_conventions(tmp_path, lexibrary_dir, ttl_commits=50)

        assert expired_path in result.deleted
        assert not expired_path.exists()
        assert recent_path.exists()

    def test_preserves_draft_convention(self, tmp_path: Path) -> None:
        """Draft conventions are never deleted."""
        convention_path = _create_convention_file(tmp_path, "draft", title="Draft", status="draft")
        lexibrary_dir = tmp_path / ".lexibrary"

        result = hard_delete_expired_conventions(tmp_path, lexibrary_dir, ttl_commits=50)

        assert result.deleted == []
        assert convention_path.exists()

    def test_multiple_expired_with_comments(self, tmp_path: Path) -> None:
        """Multiple expired conventions with comment files are all deleted."""
        convention_a = _create_convention_file(
            tmp_path,
            "convention-a",
            title="Convention A",
            status="deprecated",
            deprecated_at="2025-01-01T00:00:00",
        )
        comment_a = _create_comment_file(convention_a)
        convention_b = _create_convention_file(
            tmp_path,
            "convention-b",
            title="Convention B",
            status="deprecated",
            deprecated_at="2025-02-01T00:00:00",
        )
        comment_b = _create_comment_file(convention_b)
        lexibrary_dir = tmp_path / ".lexibrary"

        with patch(
            "lexibrary.lifecycle.convention_deprecation._count_commits_since",
            return_value=100,
        ):
            result = hard_delete_expired_conventions(tmp_path, lexibrary_dir, ttl_commits=50)

        assert len(result.deleted) == 2
        assert convention_a in result.deleted
        assert convention_b in result.deleted
        assert not convention_a.exists()
        assert not convention_b.exists()
        assert len(result.comments_deleted) == 2
        assert comment_a in result.comments_deleted
        assert comment_b in result.comments_deleted
        assert not comment_a.exists()
        assert not comment_b.exists()


# ---------------------------------------------------------------------------
# ConventionDeletionResult dataclass
# ---------------------------------------------------------------------------


class TestConventionDeletionResult:
    """Tests for ConventionDeletionResult dataclass."""

    def test_empty_result(self) -> None:
        result = ConventionDeletionResult(deleted=[], comments_deleted=[])
        assert result.deleted == []
        assert result.comments_deleted == []

    def test_populated_result(self) -> None:
        result = ConventionDeletionResult(
            deleted=[Path("/conventions/a.md")],
            comments_deleted=[Path("/conventions/a.comments.yaml")],
        )
        assert len(result.deleted) == 1
        assert len(result.comments_deleted) == 1
