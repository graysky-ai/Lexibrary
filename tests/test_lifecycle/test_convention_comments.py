"""Tests for convention comment file operations.

Tests convention_comment_path(), append_convention_comment(),
read_convention_comments(), and convention_comment_count() from
``lexibrary.lifecycle.convention_comments``.
"""

from __future__ import annotations

from pathlib import Path

from lexibrary.lifecycle.convention_comments import (
    append_convention_comment,
    convention_comment_count,
    convention_comment_path,
    read_convention_comments,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_convention_file(
    tmp_path: Path,
    slug: str = "use-dataclasses",
    *,
    title: str = "Use Dataclasses",
    status: str = "active",
) -> Path:
    """Create a minimal convention .md file in a conventions directory."""
    conventions_dir = tmp_path / ".lexibrary" / "conventions"
    conventions_dir.mkdir(parents=True, exist_ok=True)

    convention_path = conventions_dir / f"{slug}.md"
    convention_path.write_text(
        f"---\ntitle: {title}\nid: CV-001\nstatus: {status}\nscope: []\ntags: []\n---\n\n"
        f"Test convention body.\n",
        encoding="utf-8",
    )
    return convention_path


# ---------------------------------------------------------------------------
# convention_comment_path()
# ---------------------------------------------------------------------------


class TestConventionCommentPath:
    """Tests for convention_comment_path()."""

    def test_replaces_md_suffix(self) -> None:
        """Replaces .md suffix with .comments.yaml."""
        cp = Path("conventions/use-dataclasses.md")
        result = convention_comment_path(cp)
        assert result == Path("conventions/use-dataclasses.comments.yaml")

    def test_full_path(self) -> None:
        """Works with full .lexibrary paths."""
        cp = Path(".lexibrary/conventions/error-handling.md")
        result = convention_comment_path(cp)
        assert result == Path(".lexibrary/conventions/error-handling.comments.yaml")

    def test_absolute_path(self) -> None:
        """Works with absolute paths."""
        cp = Path("/project/.lexibrary/conventions/auth-required.md")
        result = convention_comment_path(cp)
        assert result == Path("/project/.lexibrary/conventions/auth-required.comments.yaml")

    def test_preserves_parent_directory(self) -> None:
        """The comment file is a sibling of the convention file."""
        cp = Path("/home/user/project/.lexibrary/conventions/naming.md")
        result = convention_comment_path(cp)
        assert result.parent == cp.parent
        assert result.name == "naming.comments.yaml"


# ---------------------------------------------------------------------------
# append_convention_comment()
# ---------------------------------------------------------------------------


class TestAppendConventionComment:
    """Tests for append_convention_comment()."""

    def test_appends_comment_to_new_file(self, tmp_path: Path) -> None:
        """Creates comment file and appends comment."""
        convention_path = _create_convention_file(tmp_path)

        append_convention_comment(convention_path, "test comment")

        comments = read_convention_comments(convention_path)
        assert len(comments) == 1
        assert comments[0].body == "test comment"

    def test_comment_has_utc_date(self, tmp_path: Path) -> None:
        """Appended comment has a UTC date."""
        convention_path = _create_convention_file(tmp_path)

        append_convention_comment(convention_path, "date test")

        comments = read_convention_comments(convention_path)
        assert len(comments) == 1
        assert comments[0].date is not None

    def test_multiple_comments_accumulate(self, tmp_path: Path) -> None:
        """Multiple appends accumulate comments in order."""
        convention_path = _create_convention_file(tmp_path)

        append_convention_comment(convention_path, "first")
        append_convention_comment(convention_path, "second")
        append_convention_comment(convention_path, "third")

        comments = read_convention_comments(convention_path)
        assert len(comments) == 3
        assert comments[0].body == "first"
        assert comments[1].body == "second"
        assert comments[2].body == "third"

    def test_comment_file_is_sibling_of_convention(self, tmp_path: Path) -> None:
        """Comment file is created next to the convention file."""
        convention_path = _create_convention_file(tmp_path)

        append_convention_comment(convention_path, "sibling test")

        expected_comment_path = convention_comment_path(convention_path)
        assert expected_comment_path.exists()


# ---------------------------------------------------------------------------
# read_convention_comments()
# ---------------------------------------------------------------------------


class TestReadConventionComments:
    """Tests for read_convention_comments()."""

    def test_returns_empty_when_no_comments(self, tmp_path: Path) -> None:
        """Returns empty list when no comment file exists."""
        convention_path = _create_convention_file(tmp_path)

        comments = read_convention_comments(convention_path)
        assert comments == []

    def test_reads_existing_comments(self, tmp_path: Path) -> None:
        """Reads comments from an existing comment file."""
        convention_path = _create_convention_file(tmp_path)

        append_convention_comment(convention_path, "existing comment")
        comments = read_convention_comments(convention_path)

        assert len(comments) == 1
        assert comments[0].body == "existing comment"


# ---------------------------------------------------------------------------
# convention_comment_count()
# ---------------------------------------------------------------------------


class TestConventionCommentCount:
    """Tests for convention_comment_count()."""

    def test_returns_zero_when_no_comments(self, tmp_path: Path) -> None:
        """Returns 0 when no comment file exists."""
        convention_path = _create_convention_file(tmp_path)

        count = convention_comment_count(convention_path)
        assert count == 0

    def test_counts_existing_comments(self, tmp_path: Path) -> None:
        """Returns correct count of existing comments."""
        convention_path = _create_convention_file(tmp_path)

        for i in range(4):
            append_convention_comment(convention_path, f"comment {i}")

        count = convention_comment_count(convention_path)
        assert count == 4

    def test_count_matches_read_length(self, tmp_path: Path) -> None:
        """Count matches the length of the read comments list."""
        convention_path = _create_convention_file(tmp_path)

        for i in range(3):
            append_convention_comment(convention_path, f"comment {i}")

        count = convention_comment_count(convention_path)
        comments = read_convention_comments(convention_path)
        assert count == len(comments)


# ---------------------------------------------------------------------------
# Import from lifecycle package
# ---------------------------------------------------------------------------


class TestLifecycleExports:
    """Verify convention comment functions are exported from lifecycle."""

    def test_import_from_lifecycle(self) -> None:
        """All four functions are importable from lexibrary.lifecycle."""
        from lexibrary.lifecycle import (  # noqa: F401
            append_convention_comment,
            convention_comment_count,
            convention_comment_path,
            read_convention_comments,
        )
