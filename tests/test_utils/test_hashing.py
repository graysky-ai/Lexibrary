"""Tests for file hashing utilities."""

from __future__ import annotations

from pathlib import Path

from lexibrary.utils.hashing import hash_file


def test_hash_file_returns_consistent_hash(tmp_path: Path) -> None:
    """hash_file should return consistent SHA-256 hash."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("Hello, World!")

    hash1 = hash_file(file_path)
    hash2 = hash_file(file_path)

    assert hash1 == hash2
    assert len(hash1) == 64  # SHA-256 produces 64-char hex string


def test_hash_file_different_content_different_hash(tmp_path: Path) -> None:
    """Different file content should produce different hashes."""
    file1 = tmp_path / "file1.txt"
    file2 = tmp_path / "file2.txt"

    file1.write_text("Content A")
    file2.write_text("Content B")

    hash1 = hash_file(file1)
    hash2 = hash_file(file2)

    assert hash1 != hash2


def test_hash_file_with_known_content(tmp_path: Path) -> None:
    """hash_file should produce known SHA-256 hash for known content."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("test")

    # Known SHA-256 hash of "test"
    expected_hash = "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
    actual_hash = hash_file(file_path)

    assert actual_hash == expected_hash


def test_hash_file_chunks_large_file(tmp_path: Path) -> None:
    """hash_file should handle large files with chunked reading."""
    file_path = tmp_path / "large.bin"

    # Write more than default chunk size (8192 bytes)
    large_content = b"x" * 20000
    file_path.write_bytes(large_content)

    hash_result = hash_file(file_path, chunk_size=4096)

    # Should produce a hash
    assert len(hash_result) == 64
    assert hash_result.isalnum()
