"""Tests for stack-post comment file operations.

Tests stack_comment_path(), append_stack_comment(), read_stack_comments(),
and stack_comment_count() from ``lexibrary.lifecycle.stack_comments``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lexibrary.lifecycle.stack_comments import (
    append_stack_comment,
    read_stack_comments,
    stack_comment_count,
    stack_comment_path,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_stack_post(
    project_root: Path,
    post_id: str = "ST-001",
    slug: str = "test-issue",
) -> Path:
    """Create a minimal stack post .md file in .lexibrary/stack/.

    The file is named ``<post_id>-<slug>.md`` following the standard
    Stack naming convention (e.g. ``ST-001-test-issue.md``).
    """
    stack_dir = project_root / ".lexibrary" / "stack"
    stack_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{post_id}-{slug}.md"
    post_path = stack_dir / filename
    post_path.write_text(
        f"---\n"
        f"id: {post_id}\n"
        f"title: Test Issue\n"
        f"tags: [test]\n"
        f"status: open\n"
        f"created: 2026-03-05\n"
        f"author: agent\n"
        f"---\n\n"
        f"## Problem\n\nTest problem.\n",
        encoding="utf-8",
    )
    return post_path


def _setup_project_with_post(
    tmp_path: Path,
    post_id: str = "ST-001",
    slug: str = "test-issue",
) -> tuple[Path, Path]:
    """Create project root with a stack post file.

    Returns (project_root, post_path).
    """
    project_root = tmp_path
    lexibrary_dir = project_root / ".lexibrary"
    lexibrary_dir.mkdir()

    post_path = _create_stack_post(project_root, post_id=post_id, slug=slug)
    return project_root, post_path


# ---------------------------------------------------------------------------
# stack_comment_path()
# ---------------------------------------------------------------------------


class TestStackCommentPath:
    """Tests for stack_comment_path()."""

    def test_replaces_md_suffix(self) -> None:
        """Replaces .md suffix with .comments.yaml."""
        p = Path("/project/.lexibrary/stack/ST-001-some-slug.md")
        result = stack_comment_path(p)
        assert result == Path("/project/.lexibrary/stack/ST-001-some-slug.comments.yaml")

    def test_relative_path(self) -> None:
        """Works with relative paths."""
        p = Path(".lexibrary/stack/ST-042-my-bug.md")
        result = stack_comment_path(p)
        assert result == Path(".lexibrary/stack/ST-042-my-bug.comments.yaml")

    def test_preserves_parent_directory(self) -> None:
        """The comment file is a sibling of the post file."""
        p = Path("/home/user/project/.lexibrary/stack/ST-007-debug-crash.md")
        result = stack_comment_path(p)
        assert result.parent == p.parent
        assert result.name == "ST-007-debug-crash.comments.yaml"


# ---------------------------------------------------------------------------
# append_stack_comment()
# ---------------------------------------------------------------------------


class TestAppendStackComment:
    """Tests for append_stack_comment()."""

    def test_appends_comment_to_new_file(self, tmp_path: Path) -> None:
        """Creates comment file and appends comment."""
        project_root, _ = _setup_project_with_post(tmp_path)

        append_stack_comment(project_root, "ST-001", "test comment")

        comments = read_stack_comments(project_root, "ST-001")
        assert len(comments) == 1
        assert comments[0].body == "test comment"

    def test_comment_has_utc_date(self, tmp_path: Path) -> None:
        """Appended comment has a UTC date."""
        project_root, _ = _setup_project_with_post(tmp_path)

        append_stack_comment(project_root, "ST-001", "date test")

        comments = read_stack_comments(project_root, "ST-001")
        assert len(comments) == 1
        assert comments[0].date is not None

    def test_multiple_comments_accumulate(self, tmp_path: Path) -> None:
        """Multiple appends accumulate comments in order."""
        project_root, _ = _setup_project_with_post(tmp_path)

        append_stack_comment(project_root, "ST-001", "first")
        append_stack_comment(project_root, "ST-001", "second")
        append_stack_comment(project_root, "ST-001", "third")

        comments = read_stack_comments(project_root, "ST-001")
        assert len(comments) == 3
        assert comments[0].body == "first"
        assert comments[1].body == "second"
        assert comments[2].body == "third"

    def test_comment_file_is_sibling_of_post(self, tmp_path: Path) -> None:
        """Comment file is created next to the stack post file."""
        project_root, post_path = _setup_project_with_post(tmp_path)

        append_stack_comment(project_root, "ST-001", "sibling test")

        expected_comment_path = stack_comment_path(post_path)
        assert expected_comment_path.exists()

    def test_raises_on_missing_post(self, tmp_path: Path) -> None:
        """Raises FileNotFoundError when stack post does not exist."""
        project_root = tmp_path
        (project_root / ".lexibrary" / "stack").mkdir(parents=True)

        with pytest.raises(FileNotFoundError, match="Stack post not found"):
            append_stack_comment(project_root, "ST-999", "should fail")

    def test_raises_when_stack_dir_missing(self, tmp_path: Path) -> None:
        """Raises FileNotFoundError when .lexibrary/stack/ does not exist."""
        project_root = tmp_path
        (project_root / ".lexibrary").mkdir()

        with pytest.raises(FileNotFoundError, match="Stack post not found"):
            append_stack_comment(project_root, "ST-001", "should fail")


# ---------------------------------------------------------------------------
# read_stack_comments()
# ---------------------------------------------------------------------------


class TestReadStackComments:
    """Tests for read_stack_comments()."""

    def test_returns_empty_when_no_comments(self, tmp_path: Path) -> None:
        """Returns empty list when no comment file exists."""
        project_root, _ = _setup_project_with_post(tmp_path)

        comments = read_stack_comments(project_root, "ST-001")
        assert comments == []

    def test_reads_existing_comments(self, tmp_path: Path) -> None:
        """Reads comments from an existing comment file."""
        project_root, _ = _setup_project_with_post(tmp_path)

        append_stack_comment(project_root, "ST-001", "existing comment")
        comments = read_stack_comments(project_root, "ST-001")

        assert len(comments) == 1
        assert comments[0].body == "existing comment"

    def test_raises_on_missing_post(self, tmp_path: Path) -> None:
        """Raises FileNotFoundError when stack post does not exist."""
        project_root = tmp_path
        (project_root / ".lexibrary" / "stack").mkdir(parents=True)

        with pytest.raises(FileNotFoundError, match="Stack post not found"):
            read_stack_comments(project_root, "ST-999")


# ---------------------------------------------------------------------------
# stack_comment_count()
# ---------------------------------------------------------------------------


class TestStackCommentCount:
    """Tests for stack_comment_count()."""

    def test_returns_zero_when_no_comments(self, tmp_path: Path) -> None:
        """Returns 0 when no comment file exists."""
        project_root, _ = _setup_project_with_post(tmp_path)

        count = stack_comment_count(project_root, "ST-001")
        assert count == 0

    def test_counts_existing_comments(self, tmp_path: Path) -> None:
        """Returns correct count of existing comments."""
        project_root, _ = _setup_project_with_post(tmp_path)

        for i in range(4):
            append_stack_comment(project_root, "ST-001", f"comment {i}")

        count = stack_comment_count(project_root, "ST-001")
        assert count == 4

    def test_count_matches_read_length(self, tmp_path: Path) -> None:
        """Count matches the length of the read comments list."""
        project_root, _ = _setup_project_with_post(tmp_path)

        for i in range(3):
            append_stack_comment(project_root, "ST-001", f"comment {i}")

        count = stack_comment_count(project_root, "ST-001")
        comments = read_stack_comments(project_root, "ST-001")
        assert count == len(comments)

    def test_raises_on_missing_post(self, tmp_path: Path) -> None:
        """Raises FileNotFoundError when stack post does not exist."""
        project_root = tmp_path
        (project_root / ".lexibrary" / "stack").mkdir(parents=True)

        with pytest.raises(FileNotFoundError, match="Stack post not found"):
            stack_comment_count(project_root, "ST-999")
