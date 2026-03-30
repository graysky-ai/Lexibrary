"""Tests for concept comment file operations.

Tests concept_comment_path(), append_concept_comment(), read_concept_comments(),
and concept_comment_count() from ``lexibrary.lifecycle.concept_comments``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lexibrary.lifecycle.concept_comments import (
    append_concept_comment,
    concept_comment_count,
    concept_comment_path,
    read_concept_comments,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_concept_file(
    project_root: Path,
    slug: str,
    *,
    title: str = "Test Concept",
    status: str = "active",
) -> Path:
    """Create a minimal concept .md file in .lexibrary/concepts/."""
    concepts_dir = project_root / ".lexibrary" / "concepts"
    concepts_dir.mkdir(parents=True, exist_ok=True)

    concept_path = concepts_dir / f"{slug}.md"
    concept_path.write_text(
        f"---\ntitle: {title}\nid: CN-001\naliases: []\ntags: []\nstatus: {status}\n---\n\n"
        f"Test concept body.\n",
        encoding="utf-8",
    )
    return concept_path


def _setup_project_with_concept(
    tmp_path: Path,
    slug: str = "MyTopic",
    *,
    title: str = "My Topic",
    status: str = "active",
) -> tuple[Path, Path]:
    """Create project root with a concept file.

    Returns (project_root, concept_path).
    """
    project_root = tmp_path
    lexibrary_dir = project_root / ".lexibrary"
    lexibrary_dir.mkdir()

    concept_path = _create_concept_file(project_root, slug, title=title, status=status)
    return project_root, concept_path


# ---------------------------------------------------------------------------
# concept_comment_path()
# ---------------------------------------------------------------------------


class TestConceptCommentPath:
    """Tests for concept_comment_path()."""

    def test_replaces_md_suffix(self) -> None:
        """Replaces .md suffix with .comments.yaml."""
        cp = Path("/project/.lexibrary/concepts/MyTopic.md")
        result = concept_comment_path(cp)
        assert result == Path("/project/.lexibrary/concepts/MyTopic.comments.yaml")

    def test_relative_path(self) -> None:
        """Works with relative paths."""
        cp = Path(".lexibrary/concepts/SomeIdea.md")
        result = concept_comment_path(cp)
        assert result == Path(".lexibrary/concepts/SomeIdea.comments.yaml")

    def test_preserves_parent_directory(self) -> None:
        """The comment file is a sibling of the concept file."""
        cp = Path("/home/user/project/.lexibrary/concepts/DesignPattern.md")
        result = concept_comment_path(cp)
        assert result.parent == cp.parent
        assert result.name == "DesignPattern.comments.yaml"


# ---------------------------------------------------------------------------
# append_concept_comment()
# ---------------------------------------------------------------------------


class TestAppendConceptComment:
    """Tests for append_concept_comment()."""

    def test_appends_comment_to_new_file(self, tmp_path: Path) -> None:
        """Creates comment file and appends comment."""
        project_root, _ = _setup_project_with_concept(tmp_path)

        append_concept_comment(project_root, "MyTopic", "test comment")

        comments = read_concept_comments(project_root, "MyTopic")
        assert len(comments) == 1
        assert comments[0].body == "test comment"

    def test_comment_has_utc_date(self, tmp_path: Path) -> None:
        """Appended comment has a UTC date."""
        project_root, _ = _setup_project_with_concept(tmp_path)

        append_concept_comment(project_root, "MyTopic", "date test")

        comments = read_concept_comments(project_root, "MyTopic")
        assert len(comments) == 1
        assert comments[0].date is not None

    def test_multiple_comments_accumulate(self, tmp_path: Path) -> None:
        """Multiple appends accumulate comments in order."""
        project_root, _ = _setup_project_with_concept(tmp_path)

        append_concept_comment(project_root, "MyTopic", "first")
        append_concept_comment(project_root, "MyTopic", "second")
        append_concept_comment(project_root, "MyTopic", "third")

        comments = read_concept_comments(project_root, "MyTopic")
        assert len(comments) == 3
        assert comments[0].body == "first"
        assert comments[1].body == "second"
        assert comments[2].body == "third"

    def test_comment_file_is_sibling_of_concept(self, tmp_path: Path) -> None:
        """Comment file is created next to the concept file."""
        project_root, concept_path = _setup_project_with_concept(tmp_path)

        append_concept_comment(project_root, "MyTopic", "sibling test")

        expected_comment_path = concept_comment_path(concept_path)
        assert expected_comment_path.exists()

    def test_raises_on_missing_concept(self, tmp_path: Path) -> None:
        """Raises FileNotFoundError when concept file does not exist."""
        project_root = tmp_path
        (project_root / ".lexibrary" / "concepts").mkdir(parents=True)

        with pytest.raises(FileNotFoundError, match="Concept file not found"):
            append_concept_comment(project_root, "NonExistent", "should fail")


# ---------------------------------------------------------------------------
# read_concept_comments()
# ---------------------------------------------------------------------------


class TestReadConceptComments:
    """Tests for read_concept_comments()."""

    def test_returns_empty_when_no_comments(self, tmp_path: Path) -> None:
        """Returns empty list when no comment file exists."""
        project_root, _ = _setup_project_with_concept(tmp_path)

        comments = read_concept_comments(project_root, "MyTopic")
        assert comments == []

    def test_reads_existing_comments(self, tmp_path: Path) -> None:
        """Reads comments from an existing comment file."""
        project_root, _ = _setup_project_with_concept(tmp_path)

        append_concept_comment(project_root, "MyTopic", "existing comment")
        comments = read_concept_comments(project_root, "MyTopic")

        assert len(comments) == 1
        assert comments[0].body == "existing comment"

    def test_raises_on_missing_concept(self, tmp_path: Path) -> None:
        """Raises FileNotFoundError when concept file does not exist."""
        project_root = tmp_path
        (project_root / ".lexibrary" / "concepts").mkdir(parents=True)

        with pytest.raises(FileNotFoundError, match="Concept file not found"):
            read_concept_comments(project_root, "NonExistent")


# ---------------------------------------------------------------------------
# concept_comment_count()
# ---------------------------------------------------------------------------


class TestConceptCommentCount:
    """Tests for concept_comment_count()."""

    def test_returns_zero_when_no_comments(self, tmp_path: Path) -> None:
        """Returns 0 when no comment file exists."""
        project_root, _ = _setup_project_with_concept(tmp_path)

        count = concept_comment_count(project_root, "MyTopic")
        assert count == 0

    def test_counts_existing_comments(self, tmp_path: Path) -> None:
        """Returns correct count of existing comments."""
        project_root, _ = _setup_project_with_concept(tmp_path)

        for i in range(4):
            append_concept_comment(project_root, "MyTopic", f"comment {i}")

        count = concept_comment_count(project_root, "MyTopic")
        assert count == 4

    def test_count_matches_read_length(self, tmp_path: Path) -> None:
        """Count matches the length of the read comments list."""
        project_root, _ = _setup_project_with_concept(tmp_path)

        for i in range(3):
            append_concept_comment(project_root, "MyTopic", f"comment {i}")

        count = concept_comment_count(project_root, "MyTopic")
        comments = read_concept_comments(project_root, "MyTopic")
        assert count == len(comments)

    def test_raises_on_missing_concept(self, tmp_path: Path) -> None:
        """Raises FileNotFoundError when concept file does not exist."""
        project_root = tmp_path
        (project_root / ".lexibrary" / "concepts").mkdir(parents=True)

        with pytest.raises(FileNotFoundError, match="Concept file not found"):
            concept_comment_count(project_root, "NonExistent")
