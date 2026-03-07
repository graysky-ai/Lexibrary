"""Unit tests for Stack post serializer."""

from __future__ import annotations

import re
from datetime import date

import yaml

from lexibrary.stack.models import (
    StackFinding,
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


class TestSerializeNoFindings:
    """Scenario: Serialize post with no findings."""

    def test_contains_frontmatter(self) -> None:
        result = serialize_stack_post(_make_post())
        assert result.startswith("---\n")
        assert "\n---\n" in result

    def test_contains_problem_section(self) -> None:
        result = serialize_stack_post(_make_post())
        assert "## Problem\n" in result
        assert "Something is broken." in result

    def test_evidence_section_omitted_when_empty(self) -> None:
        result = serialize_stack_post(_make_post())
        assert "### Evidence" not in result

    def test_no_findings_section(self) -> None:
        result = serialize_stack_post(_make_post())
        assert "## Findings" not in result

    def test_trailing_newline(self) -> None:
        result = serialize_stack_post(_make_post())
        assert result.endswith("\n")


class TestSerializeWithFindings:
    """Scenario: Serialize post with findings and comments."""

    def _post_with_findings(self) -> StackPost:
        f1 = StackFinding(
            number=1,
            date=date(2026, 2, 21),
            author="agent-456",
            votes=3,
            body="Use approach X.",
            comments=[
                "**2026-02-22 agent-789 [upvote]:** Confirmed this works.",
            ],
        )
        f2 = StackFinding(
            number=2,
            date=date(2026, 2, 22),
            author="agent-789",
            votes=0,
            body="Alternative approach Y.",
        )
        return _make_post(
            problem="Something is broken.",
            evidence=["Traceback line 1", "Traceback line 2"],
            findings=[f1, f2],
        )

    def test_contains_findings_section(self) -> None:
        result = serialize_stack_post(self._post_with_findings())
        assert "## Findings\n" in result

    def test_contains_finding_headings(self) -> None:
        result = serialize_stack_post(self._post_with_findings())
        assert "### F1\n" in result
        assert "### F2\n" in result

    def test_finding_metadata_line(self) -> None:
        result = serialize_stack_post(self._post_with_findings())
        assert "**Date:** 2026-02-21 | **Author:** agent-456 | **Votes:** 3" in result

    def test_finding_body(self) -> None:
        result = serialize_stack_post(self._post_with_findings())
        assert "Use approach X." in result
        assert "Alternative approach Y." in result

    def test_comments_section(self) -> None:
        result = serialize_stack_post(self._post_with_findings())
        assert "#### Comments\n" in result
        assert "**2026-02-22 agent-789 [upvote]:** Confirmed this works." in result

    def test_evidence_bullets(self) -> None:
        result = serialize_stack_post(self._post_with_findings())
        assert "- Traceback line 1\n" in result
        assert "- Traceback line 2\n" in result


class TestSerializeAcceptedFinding:
    """Scenario: Serialize accepted finding."""

    def test_accepted_in_metadata(self) -> None:
        f = StackFinding(
            number=1,
            date=date(2026, 2, 21),
            author="agent-456",
            votes=5,
            accepted=True,
            body="The fix.",
        )
        post = _make_post(findings=[f])
        result = serialize_stack_post(post)
        assert "| **Accepted:** true" in result


class TestSerializeNegativeVotes:
    """Scenario: Serialize finding with negative votes."""

    def test_negative_votes_in_metadata(self) -> None:
        f = StackFinding(
            number=1,
            date=date(2026, 2, 21),
            author="agent-456",
            votes=-1,
            body="Bad finding.",
            comments=[
                "**2026-02-22 agent-789 [downvote]:** This is unreliable.",
            ],
        )
        post = _make_post(findings=[f])
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


class TestSerializeContext:
    """Scenario: Serialize post with context populated (task 4.5)."""

    def test_context_section_present(self) -> None:
        post = _make_post(context="Running on Python 3.12 with pydantic v2.")
        result = serialize_stack_post(post)
        assert "### Context\n" in result
        assert "Running on Python 3.12 with pydantic v2." in result

    def test_context_section_after_problem(self) -> None:
        post = _make_post(context="Some context here.")
        result = serialize_stack_post(post)
        problem_idx = result.index("## Problem")
        context_idx = result.index("### Context")
        assert context_idx > problem_idx

    def test_context_section_omitted_when_empty(self) -> None:
        post = _make_post(context="")
        result = serialize_stack_post(post)
        assert "### Context" not in result


class TestSerializeAttempts:
    """Scenario: Serialize post with attempts populated (task 4.6)."""

    def test_attempts_section_present(self) -> None:
        post = _make_post(attempts=["Tried restarting", "Cleared cache"])
        result = serialize_stack_post(post)
        assert "### Attempts\n" in result
        assert "- Tried restarting\n" in result
        assert "- Cleared cache\n" in result

    def test_attempts_section_omitted_when_empty(self) -> None:
        post = _make_post(attempts=[])
        result = serialize_stack_post(post)
        assert "### Attempts" not in result

    def test_attempts_section_after_evidence(self) -> None:
        post = _make_post(
            evidence=["Error log line"],
            attempts=["Tried something"],
        )
        result = serialize_stack_post(post)
        evidence_idx = result.index("### Evidence")
        attempts_idx = result.index("### Attempts")
        assert attempts_idx > evidence_idx


class TestSerializeConditionalSections:
    """Scenario: Empty context/attempts/evidence omitted from output (task 4.7)."""

    def test_all_empty_only_problem_remains(self) -> None:
        post = _make_post(context="", evidence=[], attempts=[])
        result = serialize_stack_post(post)
        assert "## Problem" in result
        assert "### Context" not in result
        assert "### Evidence" not in result
        assert "### Attempts" not in result

    def test_all_populated_all_sections_present(self) -> None:
        post = _make_post(
            context="Background info.",
            evidence=["Log line 1"],
            attempts=["Tried X"],
        )
        result = serialize_stack_post(post)
        assert "## Problem" in result
        assert "### Context" in result
        assert "### Evidence" in result
        assert "### Attempts" in result

    def test_section_order_is_canonical(self) -> None:
        """Sections appear in order: Problem, Context, Evidence, Attempts."""
        post = _make_post(
            context="ctx",
            evidence=["ev"],
            attempts=["att"],
        )
        result = serialize_stack_post(post)
        p = result.index("## Problem")
        c = result.index("### Context")
        e = result.index("### Evidence")
        a = result.index("### Attempts")
        assert p < c < e < a


class TestSerializeResolutionType:
    """Scenario: resolution_type in frontmatter (task 4.8)."""

    def _extract_yaml(self, result: str) -> dict[str, object]:
        m = _FRONTMATTER_RE.match(result)
        assert m is not None, "Expected YAML frontmatter block"
        return yaml.safe_load(m.group(1))  # type: ignore[no-any-return]

    def test_resolution_type_present_when_set(self) -> None:
        fm = _make_frontmatter(resolution_type="fix")
        post = _make_post(frontmatter=fm)
        result = serialize_stack_post(post)
        data = self._extract_yaml(result)
        assert data["resolution_type"] == "fix"

    def test_resolution_type_omitted_when_none(self) -> None:
        post = _make_post()
        result = serialize_stack_post(post)
        data = self._extract_yaml(result)
        assert "resolution_type" not in data

    def test_resolution_type_workaround(self) -> None:
        fm = _make_frontmatter(resolution_type="workaround")
        post = _make_post(frontmatter=fm)
        result = serialize_stack_post(post)
        data = self._extract_yaml(result)
        assert data["resolution_type"] == "workaround"

    def test_resolution_type_all_values(self) -> None:
        for rt in ("fix", "workaround", "wontfix", "cannot_reproduce", "by_design"):
            fm = _make_frontmatter(resolution_type=rt)
            post = _make_post(frontmatter=fm)
            result = serialize_stack_post(post)
            data = self._extract_yaml(result)
            assert data["resolution_type"] == rt


class TestSerializeStaleAt:
    """Scenario: stale_at in frontmatter (task 6.1)."""

    def _extract_yaml(self, result: str) -> dict[str, object]:
        m = _FRONTMATTER_RE.match(result)
        assert m is not None, "Expected YAML frontmatter block"
        return yaml.safe_load(m.group(1))  # type: ignore[no-any-return]

    def test_stale_at_present_when_set(self) -> None:
        fm = _make_frontmatter(status="stale", stale_at="2026-06-15T10:00:00")
        post = _make_post(frontmatter=fm)
        result = serialize_stack_post(post)
        data = self._extract_yaml(result)
        assert data["stale_at"] == "2026-06-15T10:00:00"

    def test_stale_at_omitted_when_none(self) -> None:
        post = _make_post()
        result = serialize_stack_post(post)
        data = self._extract_yaml(result)
        assert "stale_at" not in data

    def test_stale_at_with_resolution_type(self) -> None:
        fm = _make_frontmatter(
            status="stale",
            resolution_type="fix",
            stale_at="2026-07-01T14:30:00",
        )
        post = _make_post(frontmatter=fm)
        result = serialize_stack_post(post)
        data = self._extract_yaml(result)
        assert data["stale_at"] == "2026-07-01T14:30:00"
        assert data["resolution_type"] == "fix"
        assert data["status"] == "stale"

    def test_stale_at_not_in_keys_when_none(self) -> None:
        """Verify stale_at key is completely absent, not just null."""
        post = _make_post()
        result = serialize_stack_post(post)
        data = self._extract_yaml(result)
        assert "stale_at" not in data
