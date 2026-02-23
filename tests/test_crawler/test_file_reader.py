"""Tests for binary detection and file reading."""

from __future__ import annotations

from pathlib import Path

from lexibrary.crawler.file_reader import (
    is_binary_file,
    read_file_for_indexing,
)


def test_text_file_not_binary(tmp_path: Path) -> None:
    """Text file with no null bytes is not binary."""
    f = tmp_path / "hello.py"
    f.write_text("print('hello')\n", encoding="utf-8")
    assert is_binary_file(f) is False


def test_binary_file_detected(tmp_path: Path) -> None:
    """File containing null bytes is detected as binary."""
    f = tmp_path / "image.bin"
    f.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00")
    assert is_binary_file(f) is True


def test_unreadable_file_treated_as_binary(tmp_path: Path) -> None:
    """File that cannot be opened is treated as binary."""
    f = tmp_path / "missing.txt"
    assert is_binary_file(f) is True


def test_read_normal_text_file(tmp_path: Path) -> None:
    """Reading a UTF-8 text file returns full content."""
    f = tmp_path / "hello.py"
    f.write_text("print('hello')\n", encoding="utf-8")
    result = read_file_for_indexing(f)
    assert result is not None
    assert result.content == "print('hello')\n"
    assert result.encoding == "utf-8"
    assert result.is_truncated is False
    assert result.path == f


def test_read_truncates_large_file(tmp_path: Path) -> None:
    """Files exceeding max_size_kb are truncated."""
    f = tmp_path / "big.txt"
    content = "x" * 2048  # 2KB
    f.write_text(content, encoding="utf-8")
    result = read_file_for_indexing(f, max_size_kb=1)
    assert result is not None
    assert len(result.content) == 1024
    assert result.is_truncated is True


def test_read_binary_file_returns_none(tmp_path: Path) -> None:
    """Reading a binary file returns None."""
    f = tmp_path / "data.bin"
    f.write_bytes(b"\x00\x01\x02\x03")
    result = read_file_for_indexing(f)
    assert result is None


def test_read_latin1_fallback(tmp_path: Path) -> None:
    """Files that fail UTF-8 but pass Latin-1 are read with Latin-1."""
    f = tmp_path / "latin.txt"
    # Latin-1 character not valid in UTF-8
    f.write_bytes(b"caf\xe9\n")
    result = read_file_for_indexing(f)
    assert result is not None
    assert result.encoding == "latin-1"
    assert "caf" in result.content


def test_read_unreadable_file_returns_none(tmp_path: Path) -> None:
    """File that cannot be read returns None."""
    f = tmp_path / "missing.txt"
    result = read_file_for_indexing(f)
    assert result is None


def test_read_empty_file(tmp_path: Path) -> None:
    """Empty text file is readable (not binary)."""
    f = tmp_path / "empty.txt"
    f.write_text("", encoding="utf-8")
    result = read_file_for_indexing(f)
    assert result is not None
    assert result.content == ""
    assert result.is_truncated is False


def test_file_content_size_bytes(tmp_path: Path) -> None:
    """FileContent reports correct original size_bytes."""
    f = tmp_path / "sized.txt"
    content = "hello world"
    f.write_text(content, encoding="utf-8")
    result = read_file_for_indexing(f)
    assert result is not None
    assert result.size_bytes == len(content.encode("utf-8"))
