"""Tests for bottom-up directory discovery and file listing."""

from __future__ import annotations

from pathlib import Path

import pathspec

from lexibrary.crawler.discovery import (
    discover_directories_bottom_up,
    list_directory_files,
)
from lexibrary.ignore.matcher import IgnoreMatcher


def _make_matcher(root: Path, patterns: list[str] | None = None) -> IgnoreMatcher:
    """Create a minimal IgnoreMatcher for testing."""
    spec = pathspec.PathSpec.from_lines("gitignore", patterns or [])
    return IgnoreMatcher(root, config_spec=spec, gitignore_specs=[])


def test_bottom_up_ordering(tmp_path: Path) -> None:
    """Deeper directories appear before shallower ones."""
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / "a" / "c").mkdir()
    (tmp_path / "d").mkdir()

    matcher = _make_matcher(tmp_path)
    dirs = discover_directories_bottom_up(tmp_path, matcher)

    names = [d.relative_to(tmp_path).as_posix() for d in dirs]
    # Deepest dirs (a/b, a/c) should come before their parent (a), which comes before root
    assert names.index("a/b") < names.index("a")
    assert names.index("a/c") < names.index("a")
    assert names.index("a") < names.index(".")
    assert names[-1] == "."  # Root is last


def test_ignored_directories_pruned(tmp_path: Path) -> None:
    """Ignored directories and their descendants are excluded."""
    (tmp_path / "src").mkdir()
    (tmp_path / "node_modules" / "pkg").mkdir(parents=True)

    matcher = _make_matcher(tmp_path, ["node_modules/"])
    dirs = discover_directories_bottom_up(tmp_path, matcher)

    dir_names = {d.name for d in dirs}
    assert "src" in dir_names
    assert "node_modules" not in dir_names
    assert "pkg" not in dir_names


def test_root_directory_included(tmp_path: Path) -> None:
    """Root directory itself appears in the result (as last entry)."""
    matcher = _make_matcher(tmp_path)
    dirs = discover_directories_bottom_up(tmp_path, matcher)
    assert dirs[-1] == tmp_path


def test_list_directory_separates_indexable_and_skipped(tmp_path: Path) -> None:
    """Python files are indexable, PNG files are skipped."""
    (tmp_path / "main.py").write_text("pass\n")
    (tmp_path / "logo.png").write_bytes(b"\x89PNG")

    matcher = _make_matcher(tmp_path)
    indexable, skipped = list_directory_files(tmp_path, matcher, binary_extensions={".png"})

    assert [f.name for f in indexable] == ["main.py"]
    assert [f.name for f in skipped] == ["logo.png"]


def test_ignored_files_excluded_entirely(tmp_path: Path) -> None:
    """Ignored files appear in neither list."""
    (tmp_path / "main.py").write_text("pass\n")
    (tmp_path / ".aindex").write_text("index\n")

    matcher = _make_matcher(tmp_path, [".aindex"])
    indexable, skipped = list_directory_files(tmp_path, matcher, binary_extensions=set())

    names = [f.name for f in indexable] + [f.name for f in skipped]
    assert ".aindex" not in names
    assert "main.py" in [f.name for f in indexable]


def test_empty_directory(tmp_path: Path) -> None:
    """Empty directory returns empty lists."""
    matcher = _make_matcher(tmp_path)
    indexable, skipped = list_directory_files(tmp_path, matcher, binary_extensions=set())
    assert indexable == []
    assert skipped == []


def test_binary_extension_filtering(tmp_path: Path) -> None:
    """Files with binary extensions go to skipped list."""
    (tmp_path / "app.js").write_text("console.log('hi')\n")
    (tmp_path / "photo.jpg").write_bytes(b"\xff\xd8\xff")
    (tmp_path / "data.db").write_bytes(b"SQLite")

    matcher = _make_matcher(tmp_path)
    indexable, skipped = list_directory_files(tmp_path, matcher, binary_extensions={".jpg", ".db"})

    assert [f.name for f in indexable] == ["app.js"]
    skipped_names = sorted(f.name for f in skipped)
    assert skipped_names == ["data.db", "photo.jpg"]


def test_directories_not_listed_as_files(tmp_path: Path) -> None:
    """Subdirectories are not included in file listing."""
    (tmp_path / "subdir").mkdir()
    (tmp_path / "file.txt").write_text("hello\n")

    matcher = _make_matcher(tmp_path)
    indexable, skipped = list_directory_files(tmp_path, matcher, binary_extensions=set())

    assert [f.name for f in indexable] == ["file.txt"]
    assert skipped == []
