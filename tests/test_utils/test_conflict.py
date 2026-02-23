"""Tests for git conflict marker detection utility."""

from __future__ import annotations

from pathlib import Path

from lexibrary.utils.conflict import has_conflict_markers


def test_clean_file_returns_false(tmp_path: Path) -> None:
    """A file without conflict markers should return False."""
    f = tmp_path / "clean.py"
    f.write_text("def hello():\n    return 'world'\n")

    assert has_conflict_markers(f) is False


def test_conflict_markers_at_start_of_line(tmp_path: Path) -> None:
    """A file with <<<<<<< at the start of a line should return True."""
    f = tmp_path / "conflicted.py"
    f.write_text(
        "def hello():\n"
        "<<<<<<< HEAD\n"
        "    return 'ours'\n"
        "=======\n"
        "    return 'theirs'\n"
        ">>>>>>> branch\n"
    )

    assert has_conflict_markers(f) is True


def test_midline_markers_ignored(tmp_path: Path) -> None:
    """Conflict markers not at the start of a line should be ignored."""
    f = tmp_path / "midline.py"
    f.write_text("comment = '<<<<<<< not a real marker'\n")

    assert has_conflict_markers(f) is False


def test_nonexistent_file_returns_false(tmp_path: Path) -> None:
    """A non-existent file should return False, not raise."""
    missing = tmp_path / "does_not_exist.py"

    assert has_conflict_markers(missing) is False


def test_binary_content_tolerance(tmp_path: Path) -> None:
    """Binary content should not crash the function."""
    f = tmp_path / "binary.bin"
    f.write_bytes(b"\x00\x01\x02\xff\xfe<<<<<<< HEAD\n\x00")

    # Should not raise; may return True or False depending on
    # how errors="replace" interprets the bytes — the key requirement
    # is that it does not crash.
    result = has_conflict_markers(f)
    assert isinstance(result, bool)
