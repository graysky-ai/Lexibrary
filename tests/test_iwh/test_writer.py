"""Unit tests for IWH writer."""

from __future__ import annotations

from pathlib import Path

from lexibrary.iwh import parse_iwh
from lexibrary.iwh.writer import write_iwh


class TestWriteIWH:
    """Tests for write_iwh()."""

    def test_creates_iwh_file(self, tmp_path: Path) -> None:
        result_path = write_iwh(tmp_path, author="agent-1", scope="incomplete", body="WIP")
        assert result_path.exists()
        assert result_path == tmp_path / ".iwh"

    def test_content_is_parseable(self, tmp_path: Path) -> None:
        write_iwh(tmp_path, author="agent-1", scope="incomplete", body="WIP")
        result = parse_iwh(tmp_path / ".iwh")
        assert result is not None
        assert result.author == "agent-1"
        assert result.scope == "incomplete"
        assert result.body == "WIP"

    def test_overwrites_existing(self, tmp_path: Path) -> None:
        write_iwh(tmp_path, author="agent-1", scope="warning", body="first")
        write_iwh(tmp_path, author="agent-2", scope="blocked", body="second")
        result = parse_iwh(tmp_path / ".iwh")
        assert result is not None
        assert result.author == "agent-2"
        assert result.scope == "blocked"
        assert result.body == "second"

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        nested = tmp_path / "a" / "b" / "c"
        result_path = write_iwh(nested, author="agent-1", scope="incomplete", body="deep")
        assert result_path.exists()
        assert nested.is_dir()
        result = parse_iwh(result_path)
        assert result is not None
        assert result.body == "deep"

    def test_empty_body(self, tmp_path: Path) -> None:
        write_iwh(tmp_path, author="agent-1", scope="warning")
        result = parse_iwh(tmp_path / ".iwh")
        assert result is not None
        assert result.body == ""

    def test_created_timestamp_set(self, tmp_path: Path) -> None:
        write_iwh(tmp_path, author="agent-1", scope="warning", body="test")
        result = parse_iwh(tmp_path / ".iwh")
        assert result is not None
        assert result.created is not None
        assert result.created.tzinfo is not None

    def test_all_scopes_writable(self, tmp_path: Path) -> None:
        for scope in ("warning", "incomplete", "blocked"):
            subdir = tmp_path / scope
            subdir.mkdir()
            write_iwh(subdir, author="agent-1", scope=scope, body=f"scope: {scope}")  # type: ignore[arg-type]
            result = parse_iwh(subdir / ".iwh")
            assert result is not None
            assert result.scope == scope

    def test_multiline_body(self, tmp_path: Path) -> None:
        body = "## Section\n\n- item 1\n- item 2\n\n```python\nprint('hello')\n```"
        write_iwh(tmp_path, author="agent-1", scope="blocked", body=body)
        result = parse_iwh(tmp_path / ".iwh")
        assert result is not None
        assert result.body == body
