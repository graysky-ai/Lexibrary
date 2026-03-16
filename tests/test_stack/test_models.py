"""Unit tests for Stack post Pydantic 2 models."""

from __future__ import annotations

from datetime import date, datetime

import pytest
from pydantic import ValidationError

from lexibrary.stack import StackFinding, StackPost, StackPostFrontmatter, StackPostRefs
from lexibrary.stack.models import ResolutionType


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
        assert fm.resolution_type is None
        assert fm.stale_at is None

    def test_tags_empty_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            self._make(tags=[])

    def test_invalid_status_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            self._make(status="invalid")

    def test_valid_status_values(self) -> None:
        for status in ("open", "resolved", "outdated", "duplicate", "stale"):
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

    def test_resolution_type_defaults_to_none(self) -> None:
        fm = self._make()
        assert fm.resolution_type is None

    def test_resolution_type_accepts_all_valid_values(self) -> None:
        valid_values: list[ResolutionType] = [
            "fix",
            "workaround",
            "wontfix",
            "cannot_reproduce",
            "by_design",
        ]
        for value in valid_values:
            fm = self._make(resolution_type=value)
            assert fm.resolution_type == value

    def test_resolution_type_rejects_invalid_string(self) -> None:
        with pytest.raises(ValidationError):
            self._make(resolution_type="invalid")

    def test_stale_at_defaults_to_none(self) -> None:
        """stale_at SHALL default to None when not specified."""
        fm = self._make()
        assert fm.stale_at is None

    def test_stale_status_accepted(self) -> None:
        """status='stale' with stale_at timestamp SHALL validate successfully."""
        fm = self._make(status="stale", stale_at="2026-06-15T10:00:00")
        assert fm.status == "stale"
        assert fm.stale_at == datetime(2026, 6, 15, 10, 0, 0)

    def test_stale_at_with_non_stale_status(self) -> None:
        """stale_at can be set independently of status (model does not enforce coupling)."""
        fm = self._make(status="resolved", stale_at="2026-06-15T10:00:00")
        assert fm.status == "resolved"
        assert fm.stale_at == datetime(2026, 6, 15, 10, 0, 0)

    def test_stale_status_without_stale_at(self) -> None:
        """status='stale' without stale_at validates (stale_at defaults to None)."""
        fm = self._make(status="stale")
        assert fm.status == "stale"
        assert fm.stale_at is None


class TestStackFinding:
    """Tests for StackFinding model."""

    def _make(self, **overrides: object) -> StackFinding:
        defaults: dict[str, object] = {
            "number": 1,
            "date": date(2026, 2, 21),
            "author": "agent-456",
            "body": "Solution text",
        }
        defaults.update(overrides)
        return StackFinding(**defaults)  # type: ignore[arg-type]

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

    def test_no_findings(self) -> None:
        post = StackPost(frontmatter=self._fm(), problem="Some problem")
        assert post.findings == []
        assert post.evidence == []
        assert post.context == ""
        assert post.attempts == []
        assert post.raw_body == ""

    def test_with_findings(self) -> None:
        f1 = StackFinding(number=1, date=date(2026, 2, 21), author="a1", body="First")
        f2 = StackFinding(number=2, date=date(2026, 2, 22), author="a2", body="Second")
        post = StackPost(
            frontmatter=self._fm(),
            problem="A problem",
            findings=[f1, f2],
        )
        assert len(post.findings) == 2
        assert post.findings[0].body == "First"
        assert post.findings[1].body == "Second"

    def test_with_evidence(self) -> None:
        post = StackPost(
            frontmatter=self._fm(),
            problem="Issue",
            evidence=["traceback line 1", "traceback line 2"],
        )
        assert post.evidence == ["traceback line 1", "traceback line 2"]

    def test_context_defaults_to_empty_string(self) -> None:
        post = StackPost(frontmatter=self._fm(), problem="Issue")
        assert post.context == ""

    def test_attempts_defaults_to_empty_list(self) -> None:
        post = StackPost(frontmatter=self._fm(), problem="Issue")
        assert post.attempts == []

    def test_with_context_and_attempts(self) -> None:
        post = StackPost(
            frontmatter=self._fm(),
            problem="Issue",
            context="During refactor of auth module",
            attempts=["Tried restarting", "Tried clearing cache"],
        )
        assert post.context == "During refactor of auth module"
        assert post.attempts == ["Tried restarting", "Tried clearing cache"]

    def test_import_from_stack_module(self) -> None:
        """Verify public API re-exports work."""
        from lexibrary.stack import (  # noqa: F401
            StackFinding,
            StackPost,
            StackPostFrontmatter,
            StackPostRefs,
            StackStatus,
        )
