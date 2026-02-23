"""Tests for atomic file write utility."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from lexibrary.utils.atomic import atomic_write


def test_atomic_write_creates_new_file(tmp_path: Path) -> None:
    """atomic_write should create a new file with the specified content."""
    target = tmp_path / "new_file.txt"
    atomic_write(target, "hello world")

    assert target.exists()
    assert target.read_text() == "hello world"


def test_atomic_write_overwrites_existing_file(tmp_path: Path) -> None:
    """atomic_write should atomically replace existing file content."""
    target = tmp_path / "existing.txt"
    target.write_text("old content")

    atomic_write(target, "new content")

    assert target.read_text() == "new content"


def test_atomic_write_creates_parent_directories(tmp_path: Path) -> None:
    """atomic_write should create missing parent directories."""
    target = tmp_path / "a" / "b" / "c" / "deep_file.txt"
    assert not target.parent.exists()

    atomic_write(target, "deep content")

    assert target.exists()
    assert target.read_text() == "deep content"


def test_atomic_write_cleans_up_on_failure(tmp_path: Path) -> None:
    """On write failure the temp file is cleaned up and the original is unchanged."""
    target = tmp_path / "protected.txt"
    target.write_text("original")

    # Simulate os.replace raising an error after the temp file is written
    with (
        patch("lexibrary.utils.atomic.os.replace", side_effect=OSError("disk full")),
        pytest.raises(OSError, match="disk full"),
    ):
        atomic_write(target, "should not persist")

    # Original file must be untouched
    assert target.read_text() == "original"

    # No leftover .tmp files
    tmp_files = list(tmp_path.glob("*.tmp"))
    assert tmp_files == []


def test_atomic_write_temp_file_in_same_directory(tmp_path: Path) -> None:
    """The temp file should be created in the same directory as the target."""
    target = tmp_path / "same_dir.txt"

    created_tmp_dirs: list[str] = []
    original_mkstemp = __import__("tempfile").mkstemp

    def spy_mkstemp(**kwargs: object) -> tuple[int, str]:
        if "dir" in kwargs:
            created_tmp_dirs.append(str(kwargs["dir"]))
        return original_mkstemp(**kwargs)

    with patch("lexibrary.utils.atomic.tempfile.mkstemp", side_effect=spy_mkstemp):
        atomic_write(target, "content")

    assert len(created_tmp_dirs) == 1
    assert created_tmp_dirs[0] == str(tmp_path)


def test_atomic_write_respects_encoding(tmp_path: Path) -> None:
    """atomic_write should use the specified encoding."""
    target = tmp_path / "encoded.txt"
    content = "caf\u00e9"

    atomic_write(target, content, encoding="utf-8")
    assert target.read_bytes() == content.encode("utf-8")

    atomic_write(target, content, encoding="latin-1")
    assert target.read_bytes() == content.encode("latin-1")
