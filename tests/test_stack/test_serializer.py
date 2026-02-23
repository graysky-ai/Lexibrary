"""Unit tests for Stack post serializer."""

from __future__ import annotations

import re
from datetime import date

import yaml

from lexibrary.stack.models import (
    StackAnswer,
    StackPost,
    StackPostFrontmatter,
    StackPostRefs,
)
from lexibrary.stack.serializer import serialize_stack_post

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def _make_frontmatter(**overrides: object) -> StackPostFrontmatter:
    defaults: dict[str, object] = {
        "id": "ST-001",
        "title": "Test post",
        "tags": ["bug"],
        "created": date(2026, 2, 21),
        "author": "agent-123",
    }
    defaults.update(overrides)
    return StackPostFrontmatter(**defaults)  # type: ignore[arg-type]


def _make_post(**overrides: object) -> StackPost:
    defaults: dict[str, object] = {
        "frontmatter": _make_frontmatter(),
        "problem": "Something is broken.",
    }
    defaults.update(overrides)
    return StackPost(**defaults)  # type: ignore[arg-type]


class TestSerializeNoAnswers:
    """Scenario: Serialize post with no answers."""

    def test_contains_frontmatter(self) -> None:
        result = serialize_stack_post(_make_post())
        assert result.startswith("---\n")
        assert "\n---\n" in result

    def test_contains_problem_section(self) -> None:
        result = serialize_stack_post(_make_post())
        assert "## Problem\n" in result
        assert "Something is broken." in result

    def test_contains_evidence_section(self) -> None:
        result = serialize_stack_post(_make_post())
        assert "### Evidence\n" in result

    def test_no_answers_section(self) -> None:
        result = serialize_stack_post(_make_post())
        assert "## Answers" not in result

    def test_trailing_newline(self) -> None:
        result = serialize_stack_post(_make_post())
        assert result.endswith("\n")


class TestSerializeWithAnswers:
    """Scenario: Serialize post with answers and comments."""

    def _post_with_answers(self) -> StackPost:
        a1 = StackAnswer(
            number=1,
            date=date(2026, 2, 21),
            author="agent-456",
            votes=3,
            body="Use approach X.",
            comments=[
                "**2026-02-22 agent-789 [upvote]:** Confirmed this works.",
            ],
        )
        a2 = StackAnswer(
            number=2,
            date=date(2026, 2, 22),
            author="agent-789",
            votes=0,
            body="Alternative approach Y.",
        )
        return _make_post(
            problem="Something is broken.",
            evidence=["Traceback line 1", "Traceback line 2"],
            answers=[a1, a2],
        )

    def test_contains_answers_section(self) -> None:
        result = serialize_stack_post(self._post_with_answers())
        assert "## Answers\n" in result

    def test_contains_answer_headings(self) -> None:
        result = serialize_stack_post(self._post_with_answers())
        assert "### A1\n" in result
        assert "### A2\n" in result

    def test_answer_metadata_line(self) -> None:
        result = serialize_stack_post(self._post_with_answers())
        assert "**Date:** 2026-02-21 | **Author:** agent-456 | **Votes:** 3" in result

    def test_answer_body(self) -> None:
        result = serialize_stack_post(self._post_with_answers())
        assert "Use approach X." in result
        assert "Alternative approach Y." in result

    def test_comments_section(self) -> None:
        result = serialize_stack_post(self._post_with_answers())
        assert "#### Comments\n" in result
        assert "**2026-02-22 agent-789 [upvote]:** Confirmed this works." in result

    def test_evidence_bullets(self) -> None:
        result = serialize_stack_post(self._post_with_answers())
        assert "- Traceback line 1\n" in result
        assert "- Traceback line 2\n" in result


class TestSerializeAcceptedAnswer:
    """Scenario: Serialize accepted answer."""

    def test_accepted_in_metadata(self) -> None:
        a = StackAnswer(
            number=1,
            date=date(2026, 2, 21),
            author="agent-456",
            votes=5,
            accepted=True,
            body="The fix.",
        )
        post = _make_post(answers=[a])
        result = serialize_stack_post(post)
        assert "| **Accepted:** true" in result


class TestSerializeNegativeVotes:
    """Scenario: Serialize answer with negative votes."""

    def test_negative_votes_in_metadata(self) -> None:
        a = StackAnswer(
            number=1,
            date=date(2026, 2, 21),
            author="agent-456",
            votes=-1,
            body="Bad answer.",
            comments=[
                "**2026-02-22 agent-789 [downvote]:** This is unreliable.",
            ],
        )
        post = _make_post(answers=[a])
        result = serialize_stack_post(post)
        assert "**Votes:** -1" in result


class TestSerializeFrontmatter:
    """Tests for YAML frontmatter serialization specifics."""

    def _extract_yaml(self, result: str) -> dict[str, object]:
        m = _FRONTMATTER_RE.match(result)
        assert m is not None, "Expected YAML frontmatter block"
        return yaml.safe_load(m.group(1))  # type: ignore[no-any-return]

    def test_refs_with_values(self) -> None:
        fm = _make_frontmatter(
            refs=StackPostRefs(
                concepts=["DateHandling"],
                files=["src/foo.py"],
            )
        )
        post = _make_post(frontmatter=fm)
        result = serialize_stack_post(post)
        data = self._extract_yaml(result)
        assert data["refs"]["concepts"] == ["DateHandling"]
        assert data["refs"]["files"] == ["src/foo.py"]
        assert data["refs"]["designs"] == []

    def test_empty_refs_serialized(self) -> None:
        post = _make_post()
        result = serialize_stack_post(post)
        data = self._extract_yaml(result)
        assert "refs" in data
        assert data["refs"]["concepts"] == []
        assert data["refs"]["files"] == []
        assert data["refs"]["designs"] == []

    def test_null_optional_fields(self) -> None:
        post = _make_post()
        result = serialize_stack_post(post)
        data = self._extract_yaml(result)
        assert data["bead"] is None
        assert data["duplicate_of"] is None

    def test_all_frontmatter_fields_present(self) -> None:
        post = _make_post()
        result = serialize_stack_post(post)
        data = self._extract_yaml(result)
        expected_keys = {
            "id",
            "title",
            "tags",
            "status",
            "created",
            "author",
            "bead",
            "votes",
            "duplicate_of",
            "refs",
        }
        assert set(data.keys()) == expected_keys

    def test_created_date_as_string(self) -> None:
        post = _make_post()
        result = serialize_stack_post(post)
        # The raw YAML text should contain the date as an ISO string
        m = _FRONTMATTER_RE.match(result)
        assert m is not None
        assert "2026-02-21" in m.group(1)
