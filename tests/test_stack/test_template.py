"""Tests for stack post template rendering."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import yaml

from lexibrary.stack.template import render_post_template


def _parse_frontmatter(text: str) -> dict:
    """Extract and parse YAML frontmatter from a markdown string."""
    assert text.startswith("---\n")
    end = text.index("---\n", 4)
    return yaml.safe_load(text[4:end])


class TestRenderPostTemplateMinimal:
    """Scenario: Render template with minimal args."""

    def test_frontmatter_contains_required_fields(self) -> None:
        result = render_post_template(
            post_id="ST-001",
            title="Test bug",
            tags=["bug"],
            author="agent-123",
        )
        fm = _parse_frontmatter(result)
        assert fm["id"] == "ST-001"
        assert fm["title"] == "Test bug"
        assert fm["tags"] == ["bug"]
        assert fm["status"] == "open"
        assert fm["votes"] == 0
        assert fm["author"] == "agent-123"

    def test_body_contains_problem_section(self) -> None:
        result = render_post_template(
            post_id="ST-001",
            title="Test bug",
            tags=["bug"],
            author="agent-123",
        )
        assert "## Problem" in result

    def test_body_contains_evidence_section(self) -> None:
        result = render_post_template(
            post_id="ST-001",
            title="Test bug",
            tags=["bug"],
            author="agent-123",
        )
        assert "### Evidence" in result

    def test_no_bead_in_minimal(self) -> None:
        result = render_post_template(
            post_id="ST-001",
            title="Test bug",
            tags=["bug"],
            author="agent-123",
        )
        fm = _parse_frontmatter(result)
        assert "bead" not in fm

    def test_no_refs_in_minimal(self) -> None:
        result = render_post_template(
            post_id="ST-001",
            title="Test bug",
            tags=["bug"],
            author="agent-123",
        )
        fm = _parse_frontmatter(result)
        assert "refs" not in fm


class TestRenderPostTemplateWithFileRefs:
    """Scenario: Render template with file refs."""

    def test_refs_files_in_frontmatter(self) -> None:
        result = render_post_template(
            post_id="ST-002",
            title="File ref test",
            tags=["config"],
            author="agent-456",
            refs_files=["src/foo.py", "src/bar.py"],
        )
        fm = _parse_frontmatter(result)
        assert fm["refs"]["files"] == ["src/foo.py", "src/bar.py"]

    def test_refs_concepts_in_frontmatter(self) -> None:
        result = render_post_template(
            post_id="ST-003",
            title="Concept ref test",
            tags=["arch"],
            author="agent-789",
            refs_concepts=["Caching", "Retry"],
        )
        fm = _parse_frontmatter(result)
        assert fm["refs"]["concepts"] == ["Caching", "Retry"]

    def test_refs_both_files_and_concepts(self) -> None:
        result = render_post_template(
            post_id="ST-004",
            title="Both refs",
            tags=["misc"],
            author="agent-000",
            refs_files=["src/a.py"],
            refs_concepts=["SomeConcept"],
        )
        fm = _parse_frontmatter(result)
        assert fm["refs"]["files"] == ["src/a.py"]
        assert fm["refs"]["concepts"] == ["SomeConcept"]


class TestRenderPostTemplateWithBead:
    """Scenario: Render template with bead."""

    def test_bead_in_frontmatter(self) -> None:
        result = render_post_template(
            post_id="ST-005",
            title="Bead test",
            tags=["task"],
            author="agent-bead",
            bead="BEAD-42",
        )
        fm = _parse_frontmatter(result)
        assert fm["bead"] == "BEAD-42"


class TestRenderPostTemplateCreatedDate:
    """Scenario: Created date is today."""

    def test_created_date_is_today(self) -> None:
        result = render_post_template(
            post_id="ST-006",
            title="Date test",
            tags=["meta"],
            author="agent-date",
        )
        fm = _parse_frontmatter(result)
        assert fm["created"] == date.today()

    def test_created_date_uses_mock(self) -> None:
        mock_date = date(2025, 6, 15)
        with patch("lexibrary.stack.template.date") as mock:
            mock.today.return_value = mock_date
            result = render_post_template(
                post_id="ST-007",
                title="Mock date test",
                tags=["meta"],
                author="agent-mock",
            )
        fm = _parse_frontmatter(result)
        assert fm["created"] == mock_date
