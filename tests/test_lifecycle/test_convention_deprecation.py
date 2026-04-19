"""Tests for convention deprecation primitives.

Covers:
- Soft-deprecate helper (``deprecate_convention``) -- frontmatter status
  flip, idempotency, atomic write, parse-failure behaviour.
- TTL expiry checking for deprecated conventions.
- Hard deletion of convention .md files and sibling .comments.yaml files.
- Preservation of non-expired and non-deprecated conventions.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from lexibrary.conventions.parser import parse_convention_file
from lexibrary.lifecycle.convention_deprecation import (
    ConventionDeletionResult,
    check_convention_ttl_expiry,
    deprecate_convention,
    hard_delete_expired_conventions,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_convention_id_counter = 0


def _next_convention_id() -> str:
    global _convention_id_counter
    _convention_id_counter += 1
    return f"CV-{_convention_id_counter:03d}"


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
        f"id: {_next_convention_id()}",
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


# ---------------------------------------------------------------------------
# deprecate_convention()  (soft-deprecate helper)
# ---------------------------------------------------------------------------


class TestDeprecateConvention:
    """Tests for ``deprecate_convention`` soft-deprecate helper."""

    def test_active_to_deprecated_sets_three_fields(self, tmp_path: Path) -> None:
        """Active convention: flips status, stamps ``deprecated_at``
        and ``deprecated_reason``.
        """
        convention_path = _create_convention_file(
            tmp_path, "auth-required", title="Auth required", status="active"
        )

        before = datetime.now(UTC).replace(microsecond=0)
        deprecate_convention(convention_path, reason="scope_path_missing")
        after = datetime.now(UTC).replace(microsecond=0)

        updated = parse_convention_file(convention_path)
        assert updated is not None
        assert updated.frontmatter.status == "deprecated"
        assert updated.frontmatter.deprecated_reason == "scope_path_missing"
        assert updated.frontmatter.deprecated_at is not None
        # Timestamp is within the invocation window, microsecond=0
        assert before <= updated.frontmatter.deprecated_at <= after
        assert updated.frontmatter.deprecated_at.microsecond == 0

    def test_draft_to_deprecated(self, tmp_path: Path) -> None:
        """Draft conventions are also soft-deprecate eligible."""
        convention_path = _create_convention_file(
            tmp_path, "draft-rule", title="Draft Rule", status="draft"
        )

        deprecate_convention(convention_path, reason="superseded")

        updated = parse_convention_file(convention_path)
        assert updated is not None
        assert updated.frontmatter.status == "deprecated"
        assert updated.frontmatter.deprecated_reason == "superseded"
        assert updated.frontmatter.deprecated_at is not None

    def test_already_deprecated_is_noop(self, tmp_path: Path) -> None:
        """Idempotent: already-deprecated input is a no-op; fields unchanged."""
        original_iso = "2025-06-01T12:34:56+00:00"
        convention_path = _create_convention_file(
            tmp_path,
            "already-dep",
            title="Already Deprecated",
            status="deprecated",
            deprecated_at=original_iso,
        )
        # Seed a prior deprecated_reason by re-writing the file with one
        # so we can confirm it is preserved (the fixture helper does not
        # currently emit ``deprecated_reason``; append it manually).
        text = convention_path.read_text(encoding="utf-8")
        # Insert deprecated_reason after deprecated_at line
        text = text.replace(
            f"deprecated_at: '{original_iso}'",
            (f"deprecated_at: '{original_iso}'\ndeprecated_reason: original_reason"),
        )
        convention_path.write_text(text, encoding="utf-8")

        mtime_before = convention_path.stat().st_mtime_ns

        deprecate_convention(convention_path, reason="new_reason_should_be_ignored")

        # File content: fields unchanged
        updated = parse_convention_file(convention_path)
        assert updated is not None
        assert updated.frontmatter.status == "deprecated"
        assert updated.frontmatter.deprecated_reason == "original_reason"
        assert updated.frontmatter.deprecated_at is not None
        assert updated.frontmatter.deprecated_at.isoformat() == original_iso

        # No-op: the file must not be rewritten (mtime preserved).
        mtime_after = convention_path.stat().st_mtime_ns
        assert mtime_after == mtime_before

    def test_unparseable_returns_none(self, tmp_path: Path) -> None:
        """Parse failure -> helper returns None, file untouched."""
        conventions_dir = tmp_path / ".lexibrary" / "conventions"
        conventions_dir.mkdir(parents=True)
        bad_path = conventions_dir / "bad.md"
        bad_path.write_text("not valid yaml frontmatter", encoding="utf-8")

        original = bad_path.read_text(encoding="utf-8")
        result = deprecate_convention(bad_path, reason="anything")
        assert result is None
        assert bad_path.read_text(encoding="utf-8") == original

    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        """Nonexistent convention path -> None, no side effects."""
        conventions_dir = tmp_path / ".lexibrary" / "conventions"
        conventions_dir.mkdir(parents=True)
        missing = conventions_dir / "not-there.md"
        assert not missing.exists()

        result = deprecate_convention(missing, reason="anything")
        assert result is None
        assert not missing.exists()

    def test_atomic_write_leaves_no_temp_files(self, tmp_path: Path) -> None:
        """Happy-path write produces exactly the target file -- temp cleaned up."""
        convention_path = _create_convention_file(
            tmp_path, "atomic-conv", title="Atomic Conv", status="active"
        )
        conventions_dir = convention_path.parent

        deprecate_convention(convention_path, reason="atomic_test")

        # Only the target .md file remains (no .tmp stragglers).
        entries = sorted(p.name for p in conventions_dir.iterdir())
        assert entries == ["atomic-conv.md"]

        # And content is sensible.
        updated = parse_convention_file(convention_path)
        assert updated is not None
        assert updated.frontmatter.status == "deprecated"
        assert updated.frontmatter.deprecated_reason == "atomic_test"

    def test_preserves_other_frontmatter_fields(self, tmp_path: Path) -> None:
        """Body, title, scope, tags, aliases, priority survive the flip."""
        conventions_dir = tmp_path / ".lexibrary" / "conventions"
        conventions_dir.mkdir(parents=True, exist_ok=True)
        convention_path = conventions_dir / "rich-conv.md"
        convention_path.write_text(
            "\n".join(
                [
                    "---",
                    "title: 'Rich Convention'",
                    "id: CV-099",
                    "scope: src/auth, src/users",
                    "tags:",
                    "  - python",
                    "  - security",
                    "status: active",
                    "source: user",
                    "priority: 3",
                    "aliases:",
                    "  - rich-alias",
                    "---",
                    "",
                    "Always validate tokens before use.\n",
                ]
            ),
            encoding="utf-8",
        )

        deprecate_convention(convention_path, reason="preservation_check")

        updated = parse_convention_file(convention_path)
        assert updated is not None
        assert updated.frontmatter.status == "deprecated"
        assert updated.frontmatter.deprecated_reason == "preservation_check"
        # Unrelated fields preserved:
        assert updated.frontmatter.title == "Rich Convention"
        assert updated.frontmatter.id == "CV-099"
        assert updated.frontmatter.scope == "src/auth, src/users"
        assert updated.frontmatter.tags == ["python", "security"]
        assert updated.frontmatter.priority == 3
        assert updated.frontmatter.aliases == ["rich-alias"]
        assert "Always validate tokens before use." in updated.body
