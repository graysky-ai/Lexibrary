"""Unit tests for IWH serializer."""

from __future__ import annotations

from datetime import UTC, datetime

from lexibrary.iwh import IWHFile, serialize_iwh


class TestSerializeIWH:
    """Tests for serialize_iwh()."""

    def _make(self, **overrides: object) -> IWHFile:
        defaults: dict[str, object] = {
            "author": "agent-abc",
            "created": datetime(2026, 2, 22, 14, 30, 0, tzinfo=UTC),
            "scope": "incomplete",
            "body": "Work in progress",
        }
        defaults.update(overrides)
        return IWHFile(**defaults)  # type: ignore[arg-type]

    def test_complete_serialization(self) -> None:
        iwh = self._make()
        result = serialize_iwh(iwh)
        assert result.startswith("---\n")
        assert "author: agent-abc" in result
        assert "scope: incomplete" in result
        assert "created:" in result
        # Body after frontmatter
        lines = result.split("---\n")
        # lines[0] is empty (before first ---), lines[1] is frontmatter, lines[2] is body
        assert len(lines) >= 3
        assert "Work in progress" in lines[2]

    def test_iso_8601_datetime(self) -> None:
        dt = datetime(2026, 2, 22, 14, 30, 0, tzinfo=UTC)
        iwh = self._make(created=dt)
        result = serialize_iwh(iwh)
        assert "2026-02-22T14:30:00+00:00" in result

    def test_markdown_body_preserved(self) -> None:
        body = "## Section\n\n- item 1\n- item 2\n\n```python\nprint('hello')\n```"
        iwh = self._make(body=body)
        result = serialize_iwh(iwh)
        # The body should appear after the closing frontmatter delimiter
        parts = result.split("---\n", 2)
        body_part = parts[2]
        assert "## Section" in body_part
        assert "- item 1" in body_part
        assert "```python" in body_part

    def test_empty_body(self) -> None:
        iwh = self._make(body="")
        result = serialize_iwh(iwh)
        assert result.startswith("---\n")
        assert result.endswith("\n")
        # Should have frontmatter but no body content
        parts = result.split("---\n", 2)
        # parts[2] should be empty or just a newline
        assert parts[2].strip() == ""

    def test_trailing_newline(self) -> None:
        iwh = self._make()
        result = serialize_iwh(iwh)
        assert result.endswith("\n")

    def test_all_scopes_serialize(self) -> None:
        for scope in ("warning", "incomplete", "blocked"):
            iwh = self._make(scope=scope)
            result = serialize_iwh(iwh)
            assert f"scope: {scope}" in result

    def test_frontmatter_field_order(self) -> None:
        iwh = self._make()
        result = serialize_iwh(iwh)
        # author should come before created, created before scope
        author_pos = result.index("author:")
        created_pos = result.index("created:")
        scope_pos = result.index("scope:")
        assert author_pos < created_pos < scope_pos
