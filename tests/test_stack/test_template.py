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

    def test_body_contains_context_section(self) -> None:
        result = render_post_template(
            post_id="ST-001",
            title="Test bug",
            tags=["bug"],
            author="agent-123",
        )
        assert "### Context" in result

    def test_body_contains_evidence_section(self) -> None:
        result = render_post_template(
            post_id="ST-001",
            title="Test bug",
            tags=["bug"],
            author="agent-123",
        )
        assert "### Evidence" in result

    def test_body_contains_attempts_section(self) -> None:
        result = render_post_template(
            post_id="ST-001",
            title="Test bug",
            tags=["bug"],
            author="agent-123",
        )
        assert "### Attempts" in result

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


class TestScaffoldMode:
    """Scenario: Scaffold mode (no content params) produces all 4 sections."""

    def test_scaffold_has_all_four_section_headers(self) -> None:
        result = render_post_template(
            post_id="ST-100",
            title="Scaffold test",
            tags=["test"],
            author="agent-scaffold",
        )
        assert "## Problem" in result
        assert "### Context" in result
        assert "### Evidence" in result
        assert "### Attempts" in result

    def test_scaffold_has_placeholder_comments(self) -> None:
        result = render_post_template(
            post_id="ST-100",
            title="Scaffold test",
            tags=["test"],
            author="agent-scaffold",
        )
        assert "<!-- Describe the problem or issue here -->" in result
        assert "<!-- Explain what you were doing when the issue occurred -->" in result
        assert "<!-- Add supporting evidence, error logs, or reproduction steps -->" in result
        assert "<!-- Describe what you have already tried -->" in result


class TestPopulatedModeAllSections:
    """Scenario: Populated mode with all sections renders all content."""

    def test_all_sections_rendered(self) -> None:
        result = render_post_template(
            post_id="ST-200",
            title="Populated test",
            tags=["test"],
            author="agent-pop",
            problem="Config fails on startup",
            context="During refactor of settings module",
            evidence=["TypeError in log", "Stack trace attached"],
            attempts=["Tried reverting config", "Tried clearing cache"],
        )
        assert "## Problem" in result
        assert "Config fails on startup" in result
        assert "### Context" in result
        assert "During refactor of settings module" in result
        assert "### Evidence" in result
        assert "- TypeError in log" in result
        assert "- Stack trace attached" in result
        assert "### Attempts" in result
        assert "- Tried reverting config" in result
        assert "- Tried clearing cache" in result

    def test_no_placeholder_comments(self) -> None:
        result = render_post_template(
            post_id="ST-200",
            title="Populated test",
            tags=["test"],
            author="agent-pop",
            problem="Config fails",
            context="During refactor",
            evidence=["log entry"],
            attempts=["Tried X"],
        )
        assert "<!--" not in result


class TestPopulatedModeOnlyProblem:
    """Scenario: Populated mode with only problem emits only ## Problem."""

    def test_only_problem_section_present(self) -> None:
        result = render_post_template(
            post_id="ST-300",
            title="Problem only",
            tags=["test"],
            author="agent-prob",
            problem="Config fails",
        )
        assert "## Problem" in result
        assert "Config fails" in result
        assert "### Context" not in result
        assert "### Evidence" not in result
        assert "### Attempts" not in result


class TestPopulatedModeProblemAlwaysEmitted:
    """Scenario: ## Problem always emitted in populated mode even if problem is None."""

    def test_problem_section_when_only_evidence(self) -> None:
        result = render_post_template(
            post_id="ST-350",
            title="No problem text",
            tags=["test"],
            author="agent-nop",
            evidence=["log1"],
        )
        assert "## Problem" in result
        assert "### Evidence" in result

    def test_problem_section_when_only_attempts(self) -> None:
        result = render_post_template(
            post_id="ST-351",
            title="No problem text",
            tags=["test"],
            author="agent-nop",
            attempts=["Tried X"],
        )
        assert "## Problem" in result
        assert "### Attempts" in result


class TestPopulatedModeListRendering:
    """Scenario: Evidence and attempts lists render as bullet items."""

    def test_evidence_bullet_items(self) -> None:
        result = render_post_template(
            post_id="ST-400",
            title="List test",
            tags=["test"],
            author="agent-list",
            evidence=["log1", "log2", "log3"],
        )
        assert "- log1" in result
        assert "- log2" in result
        assert "- log3" in result

    def test_attempts_bullet_items(self) -> None:
        result = render_post_template(
            post_id="ST-401",
            title="List test",
            tags=["test"],
            author="agent-list",
            attempts=["Tried X", "Tried Y"],
        )
        assert "- Tried X" in result
        assert "- Tried Y" in result
