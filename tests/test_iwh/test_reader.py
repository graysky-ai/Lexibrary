"""Unit tests for IWH reader (read_iwh and consume_iwh)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from lexibrary.iwh import IWHFile, serialize_iwh
from lexibrary.iwh.reader import consume_iwh, read_iwh


class TestReadIWH:
    """Tests for read_iwh()."""

    def _write_valid_iwh(self, directory: Path) -> Path:
        """Write a valid .iwh file in the given directory and return its path."""
        iwh = IWHFile(
            author="agent-abc",
            created=datetime(2026, 2, 22, 14, 30, 0, tzinfo=UTC),
            scope="incomplete",
            body="Work in progress",
        )
        iwh_path = directory / ".iwh"
        iwh_path.write_text(serialize_iwh(iwh), encoding="utf-8")
        return iwh_path

    def test_read_existing_iwh(self, tmp_path: Path) -> None:
        self._write_valid_iwh(tmp_path)
        result = read_iwh(tmp_path)
        assert result is not None
        assert result.author == "agent-abc"
        assert result.scope == "incomplete"
        assert result.body == "Work in progress"

    def test_read_preserves_file(self, tmp_path: Path) -> None:
        iwh_path = self._write_valid_iwh(tmp_path)
        read_iwh(tmp_path)
        assert iwh_path.exists()

    def test_read_missing_returns_none(self, tmp_path: Path) -> None:
        result = read_iwh(tmp_path)
        assert result is None

    def test_read_corrupt_file_returns_none(self, tmp_path: Path) -> None:
        iwh_path = tmp_path / ".iwh"
        iwh_path.write_text("not valid frontmatter", encoding="utf-8")
        result = read_iwh(tmp_path)
        assert result is None


class TestConsumeIWH:
    """Tests for consume_iwh()."""

    def _write_valid_iwh(self, directory: Path) -> Path:
        """Write a valid .iwh file in the given directory and return its path."""
        iwh = IWHFile(
            author="agent-xyz",
            created=datetime(2026, 2, 22, 14, 30, 0, tzinfo=UTC),
            scope="blocked",
            body="Blocked on dependency",
        )
        iwh_path = directory / ".iwh"
        iwh_path.write_text(serialize_iwh(iwh), encoding="utf-8")
        return iwh_path

    def test_consume_reads_and_deletes(self, tmp_path: Path) -> None:
        iwh_path = self._write_valid_iwh(tmp_path)
        result = consume_iwh(tmp_path)
        assert result is not None
        assert result.author == "agent-xyz"
        assert result.scope == "blocked"
        assert result.body == "Blocked on dependency"
        assert not iwh_path.exists()

    def test_consume_missing_returns_none(self, tmp_path: Path) -> None:
        result = consume_iwh(tmp_path)
        assert result is None

    def test_consume_corrupt_file_still_deletes(self, tmp_path: Path) -> None:
        iwh_path = tmp_path / ".iwh"
        iwh_path.write_text("corrupt content without frontmatter", encoding="utf-8")
        result = consume_iwh(tmp_path)
        assert result is None
        assert not iwh_path.exists()

    def test_consume_invalid_yaml_still_deletes(self, tmp_path: Path) -> None:
        iwh_path = tmp_path / ".iwh"
        iwh_path.write_text("---\n[bad: yaml: ::\n---\nBody\n", encoding="utf-8")
        result = consume_iwh(tmp_path)
        assert result is None
        assert not iwh_path.exists()

    def test_consume_missing_scope_still_deletes(self, tmp_path: Path) -> None:
        iwh_path = tmp_path / ".iwh"
        content = "---\nauthor: agent-abc\ncreated: '2026-02-22T14:30:00+00:00'\n---\nBody\n"
        iwh_path.write_text(content, encoding="utf-8")
        result = consume_iwh(tmp_path)
        assert result is None
        assert not iwh_path.exists()
