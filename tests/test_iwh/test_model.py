"""Unit tests for IWH Pydantic 2 model."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from lexibrary.iwh import IWHFile, IWHScope


class TestIWHFile:
    """Tests for the IWHFile model."""

    def _make(self, **overrides: object) -> IWHFile:
        defaults: dict[str, object] = {
            "author": "agent-abc",
            "created": datetime(2026, 2, 22, 14, 30, 0, tzinfo=UTC),
            "scope": "incomplete",
            "body": "Work in progress",
        }
        defaults.update(overrides)
        return IWHFile(**defaults)  # type: ignore[arg-type]

    def test_valid_construction(self) -> None:
        iwh = self._make()
        assert iwh.author == "agent-abc"
        assert iwh.created == datetime(2026, 2, 22, 14, 30, 0, tzinfo=UTC)
        assert iwh.scope == "incomplete"
        assert iwh.body == "Work in progress"

    def test_all_scope_values_accepted(self) -> None:
        scopes: list[IWHScope] = ["warning", "incomplete", "blocked"]
        for scope in scopes:
            iwh = self._make(scope=scope)
            assert iwh.scope == scope

    def test_invalid_scope_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._make(scope="critical")

    def test_empty_body_is_valid(self) -> None:
        iwh = self._make(body="")
        assert iwh.body == ""

    def test_empty_author_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._make(author="")

    def test_body_defaults_to_empty(self) -> None:
        iwh = IWHFile(
            author="agent-xyz",
            created=datetime.now(UTC),
            scope="warning",
        )
        assert iwh.body == ""

    def test_multiline_body(self) -> None:
        body = "## Section\n\n- item 1\n- item 2\n\n```python\nprint('hello')\n```"
        iwh = self._make(body=body)
        assert iwh.body == body

    def test_timezone_aware_datetime(self) -> None:
        dt = datetime(2026, 2, 22, 14, 30, 0, tzinfo=UTC)
        iwh = self._make(created=dt)
        assert iwh.created.tzinfo is not None

    def test_import_from_iwh_module(self) -> None:
        """Verify public API re-exports work."""
        from lexibrary.iwh import IWHFile, IWHScope, parse_iwh, serialize_iwh  # noqa: F401
