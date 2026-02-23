"""Roundtrip tests for IWH parser + serializer."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from lexibrary.iwh import IWHFile, IWHScope, parse_iwh, serialize_iwh


class TestIWHRoundtrip:
    """Tests that serialize -> write -> parse produces identical IWHFile."""

    def _roundtrip(self, iwh: IWHFile, tmp_path: Path) -> IWHFile:
        """Serialize, write to disk, and parse back."""
        text = serialize_iwh(iwh)
        iwh_path = tmp_path / ".iwh"
        iwh_path.write_text(text, encoding="utf-8")
        result = parse_iwh(iwh_path)
        assert result is not None
        return result

    def test_all_scopes_roundtrip(self, tmp_path: Path) -> None:
        scopes: list[IWHScope] = ["warning", "incomplete", "blocked"]
        for i, scope in enumerate(scopes):
            iwh = IWHFile(
                author=f"agent-{i}",
                created=datetime(2026, 2, 22, 14, 30, 0, tzinfo=UTC),
                scope=scope,
                body=f"Body for {scope}",
            )
            subdir = tmp_path / f"scope-{scope}"
            subdir.mkdir()
            result = self._roundtrip(iwh, subdir)
            assert result.author == iwh.author
            assert result.scope == iwh.scope
            assert result.body == iwh.body

    def test_multiline_body_roundtrip(self, tmp_path: Path) -> None:
        body = "## Section\n\n- item 1\n- item 2\n\n```python\nprint('hello')\n```"
        iwh = IWHFile(
            author="agent-test",
            created=datetime(2026, 2, 22, 14, 30, 0, tzinfo=UTC),
            scope="blocked",
            body=body,
        )
        result = self._roundtrip(iwh, tmp_path)
        assert result.body == body

    def test_empty_body_roundtrip(self, tmp_path: Path) -> None:
        iwh = IWHFile(
            author="agent-test",
            created=datetime(2026, 2, 22, 14, 30, 0, tzinfo=UTC),
            scope="warning",
            body="",
        )
        result = self._roundtrip(iwh, tmp_path)
        assert result.body == ""

    def test_datetime_roundtrip(self, tmp_path: Path) -> None:
        dt = datetime(2026, 2, 22, 14, 30, 0, tzinfo=UTC)
        iwh = IWHFile(
            author="agent-test",
            created=dt,
            scope="incomplete",
            body="test",
        )
        result = self._roundtrip(iwh, tmp_path)
        # Datetime should roundtrip (possibly with timezone representation change)
        assert result.created == dt

    def test_special_characters_in_body_roundtrip(self, tmp_path: Path) -> None:
        body = "Contains: colons, 'quotes', \"double quotes\", and #hashes"
        iwh = IWHFile(
            author="agent-test",
            created=datetime(2026, 2, 22, 14, 30, 0, tzinfo=UTC),
            scope="warning",
            body=body,
        )
        result = self._roundtrip(iwh, tmp_path)
        assert result.body == body

    def test_long_author_roundtrip(self, tmp_path: Path) -> None:
        iwh = IWHFile(
            author="very-long-agent-name-with-many-segments-and-identifiers",
            created=datetime(2026, 2, 22, 14, 30, 0, tzinfo=UTC),
            scope="incomplete",
            body="test body",
        )
        result = self._roundtrip(iwh, tmp_path)
        assert result.author == iwh.author
