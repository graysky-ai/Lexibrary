"""Tests for atomic artifact file writer."""

from __future__ import annotations

from pathlib import Path

from lexibrary.artifacts.writer import write_artifact


class TestWriteArtifact:
    """Tests for write_artifact()."""

    def test_creates_file_with_correct_content(self, tmp_path: Path) -> None:
        """Scenario: Write creates file with correct content."""
        target = tmp_path / "output.aindex"
        content = "# Index\n\nSome content.\n"
        result = write_artifact(target, content)
        assert target.read_text(encoding="utf-8") == content
        assert result == target

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Scenario: Write creates parent directories."""
        target = tmp_path / "a" / "b" / "c" / "output.aindex"
        content = "nested content"
        write_artifact(target, content)
        assert target.exists()
        assert target.read_text(encoding="utf-8") == content

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        """Scenario: Write overwrites existing file."""
        target = tmp_path / "output.aindex"
        write_artifact(target, "first content")
        write_artifact(target, "second content")
        assert target.read_text(encoding="utf-8") == "second content"

    def test_no_tmp_file_remains(self, tmp_path: Path) -> None:
        """Scenario: Write is atomic -- no .tmp file remains."""
        target = tmp_path / "output.aindex"
        write_artifact(target, "some content")
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert tmp_files == []

    def test_returns_target_path(self, tmp_path: Path) -> None:
        """Scenario: Write returns target path."""
        target = tmp_path / "output.aindex"
        result = write_artifact(target, "content")
        assert result == target

    def test_writes_utf8(self, tmp_path: Path) -> None:
        """Content with Unicode characters is written as UTF-8."""
        target = tmp_path / "output.aindex"
        content = "# Indeks\n\nUnicode test \U0001f4da\n"
        write_artifact(target, content)
        assert target.read_text(encoding="utf-8") == content

    def test_empty_content(self, tmp_path: Path) -> None:
        """Empty string content produces an empty file."""
        target = tmp_path / "output.aindex"
        write_artifact(target, "")
        assert target.read_text(encoding="utf-8") == ""
        assert target.stat().st_size == 0
