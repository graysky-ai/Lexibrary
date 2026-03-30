"""Tests for stack helper functions."""

from __future__ import annotations

from pathlib import Path

from lexibrary.artifacts.slugs import slugify
from lexibrary.stack.helpers import find_post_path, stack_dir


class TestStackDir:
    """Scenario: stack_dir creates and returns the .lexibrary/stack/ directory."""

    def test_creates_directory_if_missing(self, tmp_path: Path) -> None:
        result = stack_dir(tmp_path)
        assert result == tmp_path / ".lexibrary" / "stack"
        assert result.is_dir()

    def test_returns_existing_directory(self, tmp_path: Path) -> None:
        expected = tmp_path / ".lexibrary" / "stack"
        expected.mkdir(parents=True)
        result = stack_dir(tmp_path)
        assert result == expected
        assert result.is_dir()

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        result = stack_dir(tmp_path)
        assert (tmp_path / ".lexibrary").is_dir()
        assert result.is_dir()


class TestSlugify:
    """Scenario: slugify converts titles to URL-friendly slugs."""

    def test_basic_title(self) -> None:
        assert slugify("Hello World") == "hello-world"

    def test_special_characters(self) -> None:
        assert slugify("Fix: the bug (in parser)") == "fix-the-bug-in-parser"

    def test_consecutive_special_chars(self) -> None:
        assert slugify("foo---bar") == "foo-bar"

    def test_leading_trailing_special_chars(self) -> None:
        assert slugify("--hello--") == "hello"

    def test_truncation_at_60_chars(self) -> None:
        long_title = "a" * 100
        result = slugify(long_title)
        assert len(result) <= 60

    def test_empty_string(self) -> None:
        assert slugify("") == ""

    def test_uppercase_lowered(self) -> None:
        assert slugify("UPPER CASE") == "upper-case"

    def test_numbers_preserved(self) -> None:
        assert slugify("fix issue 42") == "fix-issue-42"


class TestFindPostPath:
    """Scenario: find_post_path locates a post file by its ID."""

    def test_finds_existing_post(self, tmp_path: Path) -> None:
        sdir = tmp_path / ".lexibrary" / "stack"
        sdir.mkdir(parents=True)
        post_file = sdir / "ST-001-some-title.md"
        post_file.touch()
        result = find_post_path(tmp_path, "ST-001")
        assert result == post_file

    def test_returns_none_when_not_found(self, tmp_path: Path) -> None:
        sdir = tmp_path / ".lexibrary" / "stack"
        sdir.mkdir(parents=True)
        result = find_post_path(tmp_path, "ST-999")
        assert result is None

    def test_returns_none_when_no_stack_dir(self, tmp_path: Path) -> None:
        result = find_post_path(tmp_path, "ST-001")
        assert result is None

    def test_matches_correct_prefix(self, tmp_path: Path) -> None:
        sdir = tmp_path / ".lexibrary" / "stack"
        sdir.mkdir(parents=True)
        (sdir / "ST-001-first.md").touch()
        (sdir / "ST-002-second.md").touch()
        result = find_post_path(tmp_path, "ST-002")
        assert result is not None
        assert result.name == "ST-002-second.md"
