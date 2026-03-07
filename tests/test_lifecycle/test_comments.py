"""Tests for shared comment models and file operations.

Tests ArtefactComment / ArtefactCommentFile Pydantic models and the
read_comments(), append_comment(), comment_count() functions in
``lexibrary.lifecycle.comments``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from lexibrary.lifecycle.comments import append_comment, comment_count, read_comments
from lexibrary.lifecycle.models import ArtefactComment, ArtefactCommentFile

# ---------------------------------------------------------------------------
# ArtefactComment model
# ---------------------------------------------------------------------------


class TestArtefactCommentModel:
    """Tests for the ArtefactComment Pydantic model."""

    def test_create_with_required_fields(self) -> None:
        """Create a comment with body and date."""
        dt = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)
        comment = ArtefactComment(body="test comment", date=dt)
        assert comment.body == "test comment"
        assert comment.date == dt

    def test_body_cannot_be_empty(self) -> None:
        """Empty body string should fail validation."""
        with pytest.raises(Exception):  # noqa: B017
            ArtefactComment(body="", date=datetime.now(tz=UTC))

    def test_serialization_roundtrip(self) -> None:
        """Model can be serialized to dict and back."""
        dt = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)
        comment = ArtefactComment(body="roundtrip test", date=dt)
        data = comment.model_dump(mode="json")
        restored = ArtefactComment.model_validate(data)
        assert restored.body == comment.body
        assert restored.date == comment.date


# ---------------------------------------------------------------------------
# ArtefactCommentFile model
# ---------------------------------------------------------------------------


class TestArtefactCommentFileModel:
    """Tests for the ArtefactCommentFile container model."""

    def test_empty_comments_by_default(self) -> None:
        """Default is an empty comments list."""
        cf = ArtefactCommentFile()
        assert cf.comments == []

    def test_create_with_comments(self) -> None:
        """Create with an explicit list of comments."""
        dt = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)
        c1 = ArtefactComment(body="first", date=dt)
        c2 = ArtefactComment(body="second", date=dt)
        cf = ArtefactCommentFile(comments=[c1, c2])
        assert len(cf.comments) == 2
        assert cf.comments[0].body == "first"
        assert cf.comments[1].body == "second"

    def test_model_validate_from_dict(self) -> None:
        """Validate from raw dict (simulating YAML load)."""
        data = {
            "comments": [
                {"body": "hello", "date": "2026-03-01T12:00:00"},
                {"body": "world", "date": "2026-03-02T14:30:00"},
            ],
        }
        cf = ArtefactCommentFile.model_validate(data)
        assert len(cf.comments) == 2
        assert cf.comments[0].body == "hello"


# ---------------------------------------------------------------------------
# read_comments()
# ---------------------------------------------------------------------------


class TestReadComments:
    """Tests for read_comments()."""

    def test_returns_empty_when_file_missing(self, tmp_path: Path) -> None:
        """Missing file returns an empty list."""
        result = read_comments(tmp_path / "nonexistent.comments.yaml")
        assert result == []

    def test_returns_empty_when_file_is_empty(self, tmp_path: Path) -> None:
        """Empty file returns an empty list."""
        path = tmp_path / "empty.comments.yaml"
        path.write_text("", encoding="utf-8")
        result = read_comments(path)
        assert result == []

    def test_returns_empty_on_malformed_yaml(self, tmp_path: Path) -> None:
        """Malformed YAML returns an empty list (no crash)."""
        path = tmp_path / "bad.comments.yaml"
        path.write_text("{{{{not valid yaml", encoding="utf-8")
        result = read_comments(path)
        assert result == []

    def test_returns_empty_on_non_dict_yaml(self, tmp_path: Path) -> None:
        """YAML that is a list (not a dict) returns an empty list."""
        path = tmp_path / "list.comments.yaml"
        path.write_text("- item1\n- item2\n", encoding="utf-8")
        result = read_comments(path)
        assert result == []

    def test_returns_empty_on_validation_failure(self, tmp_path: Path) -> None:
        """YAML with wrong structure returns empty list."""
        path = tmp_path / "invalid.comments.yaml"
        # comments entry missing required 'body' field
        data = {"comments": [{"date": "2026-01-01T00:00:00"}]}
        path.write_text(yaml.dump(data), encoding="utf-8")
        result = read_comments(path)
        assert result == []

    def test_reads_valid_comments(self, tmp_path: Path) -> None:
        """Valid YAML with comments returns correct list."""
        path = tmp_path / "valid.comments.yaml"
        data = {
            "comments": [
                {"body": "first comment", "date": "2026-03-01T12:00:00"},
                {"body": "second comment", "date": "2026-03-02T14:30:00"},
            ],
        }
        path.write_text(
            yaml.dump(data, default_flow_style=False),
            encoding="utf-8",
        )
        result = read_comments(path)
        assert len(result) == 2
        assert result[0].body == "first comment"
        assert result[1].body == "second comment"

    def test_returns_empty_on_whitespace_only_file(self, tmp_path: Path) -> None:
        """File with only whitespace returns empty list."""
        path = tmp_path / "whitespace.comments.yaml"
        path.write_text("   \n  \n", encoding="utf-8")
        result = read_comments(path)
        assert result == []


# ---------------------------------------------------------------------------
# append_comment()
# ---------------------------------------------------------------------------


class TestAppendComment:
    """Tests for append_comment()."""

    def test_creates_file_when_missing(self, tmp_path: Path) -> None:
        """Creates the .comments.yaml file on first append."""
        path = tmp_path / "new.comments.yaml"
        comment = ArtefactComment(
            body="first comment",
            date=datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC),
        )

        append_comment(path, comment)

        assert path.exists()
        result = read_comments(path)
        assert len(result) == 1
        assert result[0].body == "first comment"

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Creates parent directories if they don't exist."""
        path = tmp_path / "deep" / "nested" / "dir" / "file.comments.yaml"
        comment = ArtefactComment(
            body="deep comment",
            date=datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC),
        )

        append_comment(path, comment)

        assert path.exists()
        result = read_comments(path)
        assert len(result) == 1

    def test_appends_to_existing_file(self, tmp_path: Path) -> None:
        """Appends to existing comments preserving order."""
        path = tmp_path / "existing.comments.yaml"
        dt = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)

        c1 = ArtefactComment(body="first", date=dt)
        c2 = ArtefactComment(body="second", date=dt)

        append_comment(path, c1)
        append_comment(path, c2)

        result = read_comments(path)
        assert len(result) == 2
        assert result[0].body == "first"
        assert result[1].body == "second"

    def test_multiple_appends(self, tmp_path: Path) -> None:
        """Multiple appends accumulate comments correctly."""
        path = tmp_path / "multi.comments.yaml"
        dt = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)

        for i in range(5):
            comment = ArtefactComment(body=f"comment {i}", date=dt)
            append_comment(path, comment)

        result = read_comments(path)
        assert len(result) == 5
        for i in range(5):
            assert result[i].body == f"comment {i}"

    def test_written_yaml_is_readable(self, tmp_path: Path) -> None:
        """Written file can be read back as valid YAML."""
        path = tmp_path / "readable.comments.yaml"
        comment = ArtefactComment(
            body="yaml test",
            date=datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC),
        )
        append_comment(path, comment)

        text = path.read_text(encoding="utf-8")
        data = yaml.safe_load(text)
        assert isinstance(data, dict)
        assert "comments" in data
        assert len(data["comments"]) == 1
        assert data["comments"][0]["body"] == "yaml test"


# ---------------------------------------------------------------------------
# comment_count()
# ---------------------------------------------------------------------------


class TestCommentCount:
    """Tests for comment_count()."""

    def test_returns_zero_when_file_missing(self, tmp_path: Path) -> None:
        """Missing file returns 0."""
        assert comment_count(tmp_path / "nonexistent.comments.yaml") == 0

    def test_returns_zero_when_file_empty(self, tmp_path: Path) -> None:
        """Empty file returns 0."""
        path = tmp_path / "empty.comments.yaml"
        path.write_text("", encoding="utf-8")
        assert comment_count(path) == 0

    def test_returns_zero_on_malformed_yaml(self, tmp_path: Path) -> None:
        """Malformed YAML returns 0."""
        path = tmp_path / "bad.comments.yaml"
        path.write_text("{{bad", encoding="utf-8")
        assert comment_count(path) == 0

    def test_returns_zero_on_non_dict_yaml(self, tmp_path: Path) -> None:
        """Non-dict YAML returns 0."""
        path = tmp_path / "list.comments.yaml"
        path.write_text("- item\n", encoding="utf-8")
        assert comment_count(path) == 0

    def test_returns_zero_when_comments_not_list(self, tmp_path: Path) -> None:
        """Comments key not a list returns 0."""
        path = tmp_path / "string.comments.yaml"
        path.write_text("comments: not-a-list\n", encoding="utf-8")
        assert comment_count(path) == 0

    def test_counts_valid_comments(self, tmp_path: Path) -> None:
        """Returns correct count for valid file."""
        path = tmp_path / "valid.comments.yaml"
        dt = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)

        for i in range(3):
            comment = ArtefactComment(body=f"comment {i}", date=dt)
            append_comment(path, comment)

        assert comment_count(path) == 3

    def test_returns_zero_on_whitespace_only(self, tmp_path: Path) -> None:
        """Whitespace-only file returns 0."""
        path = tmp_path / "ws.comments.yaml"
        path.write_text("  \n  \n", encoding="utf-8")
        assert comment_count(path) == 0
