"""Unit tests for Stack post Pydantic 2 models."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from lexibrary.stack import StackAnswer, StackPost, StackPostFrontmatter, StackPostRefs


class TestStackPostRefs:
    """Tests for StackPostRefs model."""

    def test_empty_defaults(self) -> None:
        refs = StackPostRefs()
        assert refs.concepts == []
        assert refs.files == []
        assert refs.designs == []

    def test_with_values(self) -> None:
        refs = StackPostRefs(
            concepts=["DateHandling"],
            files=["src/models/event.py"],
        )
        assert refs.concepts == ["DateHandling"]
        assert refs.files == ["src/models/event.py"]
        assert refs.designs == []


class TestStackPostFrontmatter:
    """Tests for StackPostFrontmatter model."""

    def _make(self, **overrides: object) -> StackPostFrontmatter:
        defaults: dict[str, object] = {
            "id": "ST-001",
            "title": "Test",
            "tags": ["bug"],
            "created": date(2026, 2, 21),
            "author": "agent-123",
        }
        defaults.update(overrides)
        return StackPostFrontmatter(**defaults)  # type: ignore[arg-type]

    def test_required_fields_with_defaults(self) -> None:
        fm = self._make()
        assert fm.id == "ST-001"
        assert fm.title == "Test"
        assert fm.tags == ["bug"]
        assert fm.status == "open"
        assert fm.votes == 0
        assert fm.bead is None
        assert fm.duplicate_of is None
        assert fm.refs == StackPostRefs()

    def test_tags_empty_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            self._make(tags=[])

    def test_invalid_status_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            self._make(status="invalid")

    def test_valid_status_values(self) -> None:
        for status in ("open", "resolved", "outdated", "duplicate"):
            fm = self._make(status=status)
            assert fm.status == status

    def test_bead_optional(self) -> None:
        fm = self._make(bead="lexibrary-abc.1")
        assert fm.bead == "lexibrary-abc.1"

    def test_duplicate_of_optional(self) -> None:
        fm = self._make(duplicate_of="ST-005")
        assert fm.duplicate_of == "ST-005"

    def test_refs_default_factory(self) -> None:
        fm = self._make()
        assert isinstance(fm.refs, StackPostRefs)

    def test_votes_default(self) -> None:
        fm = self._make()
        assert fm.votes == 0

    def test_votes_custom(self) -> None:
        fm = self._make(votes=5)
        assert fm.votes == 5


class TestStackAnswer:
    """Tests for StackAnswer model."""

    def _make(self, **overrides: object) -> StackAnswer:
        defaults: dict[str, object] = {
            "number": 1,
            "date": date(2026, 2, 21),
            "author": "agent-456",
            "body": "Solution text",
        }
        defaults.update(overrides)
        return StackAnswer(**defaults)  # type: ignore[arg-type]

    def test_defaults(self) -> None:
        ans = self._make()
        assert ans.votes == 0
        assert ans.accepted is False
        assert ans.comments == []

    def test_with_comments(self) -> None:
        ans = self._make(comments=["2026-02-21 agent-789: Good point"])
        assert ans.comments == ["2026-02-21 agent-789: Good point"]

    def test_accepted(self) -> None:
        ans = self._make(accepted=True)
        assert ans.accepted is True

    def test_negative_votes(self) -> None:
        ans = self._make(votes=-3)
        assert ans.votes == -3


class TestStackPost:
    """Tests for StackPost model."""

    @staticmethod
    def _fm(**overrides: object) -> StackPostFrontmatter:
        defaults: dict[str, object] = {
            "id": "ST-001",
            "title": "Test post",
            "tags": ["bug"],
            "created": date(2026, 2, 21),
            "author": "agent-123",
        }
        defaults.update(overrides)
        return StackPostFrontmatter(**defaults)  # type: ignore[arg-type]

    def test_no_answers(self) -> None:
        post = StackPost(frontmatter=self._fm(), problem="Some problem")
        assert post.answers == []
        assert post.evidence == []
        assert post.raw_body == ""

    def test_with_answers(self) -> None:
        a1 = StackAnswer(number=1, date=date(2026, 2, 21), author="a1", body="First")
        a2 = StackAnswer(number=2, date=date(2026, 2, 22), author="a2", body="Second")
        post = StackPost(
            frontmatter=self._fm(),
            problem="A problem",
            answers=[a1, a2],
        )
        assert len(post.answers) == 2
        assert post.answers[0].body == "First"
        assert post.answers[1].body == "Second"

    def test_with_evidence(self) -> None:
        post = StackPost(
            frontmatter=self._fm(),
            problem="Issue",
            evidence=["traceback line 1", "traceback line 2"],
        )
        assert post.evidence == ["traceback line 1", "traceback line 2"]

    def test_import_from_stack_module(self) -> None:
        """Verify public API re-exports work."""
        from lexibrary.stack import (  # noqa: F401
            StackAnswer,
            StackPost,
            StackPostFrontmatter,
            StackPostRefs,
        )
