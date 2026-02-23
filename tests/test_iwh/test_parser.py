"""Unit tests for IWH parser."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from lexibrary.iwh import parse_iwh


class TestParseIWH:
    """Tests for parse_iwh()."""

    def _write_iwh(self, path: Path, content: str) -> Path:
        path.write_text(content, encoding="utf-8")
        return path

    def test_valid_iwh_file_parsed(self, tmp_path: Path) -> None:
        content = (
            "---\n"
            "author: agent-abc\n"
            "created: '2026-02-22T14:30:00+00:00'\n"
            "scope: incomplete\n"
            "---\n"
            "Work in progress\n"
        )
        iwh_path = self._write_iwh(tmp_path / ".iwh", content)
        result = parse_iwh(iwh_path)
        assert result is not None
        assert result.author == "agent-abc"
        assert result.scope == "incomplete"
        assert result.body == "Work in progress"

    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        result = parse_iwh(tmp_path / "nonexistent.iwh")
        assert result is None

    def test_no_frontmatter_returns_none(self, tmp_path: Path) -> None:
        content = "Just plain text with no frontmatter.\n"
        iwh_path = self._write_iwh(tmp_path / ".iwh", content)
        result = parse_iwh(iwh_path)
        assert result is None

    def test_invalid_frontmatter_returns_none(self, tmp_path: Path) -> None:
        content = "---\n[invalid: yaml: ::\n---\nBody\n"
        iwh_path = self._write_iwh(tmp_path / ".iwh", content)
        result = parse_iwh(iwh_path)
        assert result is None

    def test_missing_scope_field_returns_none(self, tmp_path: Path) -> None:
        content = "---\nauthor: agent-abc\ncreated: '2026-02-22T14:30:00+00:00'\n---\nBody\n"
        iwh_path = self._write_iwh(tmp_path / ".iwh", content)
        result = parse_iwh(iwh_path)
        assert result is None

    def test_unknown_scope_returns_none(self, tmp_path: Path) -> None:
        content = (
            "---\n"
            "author: agent-abc\n"
            "created: '2026-02-22T14:30:00+00:00'\n"
            "scope: critical\n"
            "---\n"
            "Body\n"
        )
        iwh_path = self._write_iwh(tmp_path / ".iwh", content)
        result = parse_iwh(iwh_path)
        assert result is None

    def test_empty_body_parsed_correctly(self, tmp_path: Path) -> None:
        content = (
            "---\nauthor: agent-abc\ncreated: '2026-02-22T14:30:00+00:00'\nscope: warning\n---\n"
        )
        iwh_path = self._write_iwh(tmp_path / ".iwh", content)
        result = parse_iwh(iwh_path)
        assert result is not None
        assert result.body == ""

    def test_multiline_body_parsed(self, tmp_path: Path) -> None:
        body = "## Section\n\n- item 1\n- item 2\n\n```python\nprint('hello')\n```"
        content = (
            "---\n"
            "author: agent-abc\n"
            "created: '2026-02-22T14:30:00+00:00'\n"
            "scope: blocked\n"
            "---\n"
            f"{body}\n"
        )
        iwh_path = self._write_iwh(tmp_path / ".iwh", content)
        result = parse_iwh(iwh_path)
        assert result is not None
        assert result.body == body

    def test_all_scopes_parsed(self, tmp_path: Path) -> None:
        for scope in ("warning", "incomplete", "blocked"):
            content = (
                "---\n"
                "author: agent-abc\n"
                "created: '2026-02-22T14:30:00+00:00'\n"
                f"scope: {scope}\n"
                "---\n"
            )
            iwh_path = self._write_iwh(tmp_path / f".iwh-{scope}", content)
            result = parse_iwh(iwh_path)
            assert result is not None
            assert result.scope == scope

    def test_created_is_datetime(self, tmp_path: Path) -> None:
        content = (
            "---\nauthor: agent-abc\ncreated: '2026-02-22T14:30:00+00:00'\nscope: warning\n---\n"
        )
        iwh_path = self._write_iwh(tmp_path / ".iwh", content)
        result = parse_iwh(iwh_path)
        assert result is not None
        assert isinstance(result.created, datetime)

    def test_frontmatter_non_dict_returns_none(self, tmp_path: Path) -> None:
        content = "---\n- just\n- a list\n---\nBody\n"
        iwh_path = self._write_iwh(tmp_path / ".iwh", content)
        result = parse_iwh(iwh_path)
        assert result is None
