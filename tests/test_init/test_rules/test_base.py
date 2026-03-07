"""Tests for init/rules/base.py — base rule content generators."""

from __future__ import annotations

from lexibrary.init.rules.base import (
    get_concepts_skill_content,
    get_core_rules,
    get_lookup_skill_content,
    get_orient_skill_content,
    get_search_skill_content,
    get_stack_skill_content,
)

# ---------------------------------------------------------------------------
# get_core_rules — key instructions
# ---------------------------------------------------------------------------


class TestGetCoreRules:
    """Core rules contain all required agent instructions."""

    def test_returns_string(self) -> None:
        """get_core_rules() returns a non-empty string."""
        result = get_core_rules()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_orient_reference(self) -> None:
        """Core rules reference lexi orient."""
        result = get_core_rules()
        assert "lexi orient" in result

    def test_contains_iwh_reference(self) -> None:
        """Core rules reference IWH signals."""
        result = get_core_rules()
        assert "IWH" in result

    def test_contains_lexi_lookup(self) -> None:
        """Core rules instruct agents to run lexi lookup."""
        result = get_core_rules()
        assert "lexi lookup" in result

    def test_contains_design_file_updates(self) -> None:
        """Core rules instruct agents to update design files."""
        result = get_core_rules()
        assert "design file" in result.lower()
        assert "updated_by: agent" in result

    def test_contains_lexi_concepts(self) -> None:
        """Core rules instruct agents to run lexi concepts."""
        result = get_core_rules()
        assert "lexi concepts" in result

    def test_contains_lexi_stack_search(self) -> None:
        """Core rules instruct agents to run lexi stack search."""
        result = get_core_rules()
        assert "lexi stack search" in result

    def test_contains_lexi_stack_post(self) -> None:
        """Core rules instruct agents to run lexi stack post."""
        result = get_core_rules()
        assert "lexi stack post" in result

    def test_prohibits_lexictl(self) -> None:
        """Core rules explicitly prohibit running lexictl commands."""
        result = get_core_rules()
        lower = result.lower()
        assert "never run" in lower or "do not run" in lower
        assert "lexictl" in result

    def test_no_lexictl_update_instruction(self) -> None:
        """Core rules do not instruct agents to run lexictl update."""
        result = get_core_rules()
        # The rules should mention lexictl only in the context of prohibition,
        # never as an instruction to run it.  We verify that the word "run"
        # does not appear in the same sentence as "lexictl" outside of a
        # prohibition context by checking that specific command patterns
        # only appear inside the prohibition section.
        lines = result.splitlines()
        for line in lines:
            stripped = line.strip().lower()
            if "lexictl" in stripped and stripped.startswith("- run"):
                # Should not have a line like "- Run lexictl update ..."
                msg = f"Found instruction to run lexictl: {line}"
                raise AssertionError(msg)

    def test_no_lexictl_validate_instruction(self) -> None:
        """Core rules do not instruct agents to run lexictl validate."""
        result = get_core_rules()
        lines = result.splitlines()
        for line in lines:
            stripped = line.strip().lower()
            # Must not be an affirmative instruction to run lexictl validate
            if stripped.startswith("- run") and "lexictl validate" in stripped:
                msg = f"Found instruction to run lexictl validate: {line}"
                raise AssertionError(msg)

    def test_no_lexictl_status_instruction(self) -> None:
        """Core rules do not instruct agents to run lexictl status."""
        result = get_core_rules()
        lines = result.splitlines()
        for line in lines:
            stripped = line.strip().lower()
            if stripped.startswith("- run") and "lexictl status" in stripped:
                msg = f"Found instruction to run lexictl status: {line}"
                raise AssertionError(msg)

    def test_iwh_read_act_consume(self) -> None:
        """Core rules instruct agents to read and consume .iwh signals."""
        result = get_core_rules().lower()
        assert "read" in result
        assert "consume" in result

    def test_iwh_do_not_create_when_clean(self) -> None:
        """Core rules instruct agents NOT to create .iwh when work is clean."""
        result = get_core_rules().lower()
        assert "do not create" in result or "don't create" in result

    def test_core_rules_references_lexi_iwh_write(self) -> None:
        """Core rules reference lexi iwh write for leaving work incomplete."""
        result = get_core_rules()
        assert "lexi iwh write" in result

    def test_core_rules_references_lexi_iwh_read(self) -> None:
        """Core rules reference lexi iwh read for consuming signals."""
        result = get_core_rules()
        assert "lexi iwh read" in result

    def test_core_rules_references_lexi_orient(self) -> None:
        """Core rules reference lexi orient for session start."""
        result = get_core_rules()
        assert "lexi orient" in result

    def test_core_rules_no_design_file_read_instruction(self) -> None:
        """Core rules do not instruct reading design files in .lexibrary/designs/."""
        result = get_core_rules()
        assert ".lexibrary/designs/" not in result

    def test_no_leading_trailing_whitespace(self) -> None:
        """Returned content has no leading/trailing whitespace."""
        result = get_core_rules()
        assert result == result.strip()


# ---------------------------------------------------------------------------
# get_orient_skill_content — session start
# ---------------------------------------------------------------------------


class TestGetOrientSkillContent:
    """Orient skill contains session start actions."""

    def test_returns_string(self) -> None:
        """get_orient_skill_content() returns a non-empty string."""
        result = get_orient_skill_content()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_references_lexi_orient_command(self) -> None:
        """Orient skill references `lexi orient` as a single command."""
        result = get_orient_skill_content()
        assert "lexi orient" in result

    def test_mentions_topology(self) -> None:
        """Orient skill mentions project topology in its output description."""
        result = get_orient_skill_content()
        assert "topology" in result.lower()

    def test_mentions_iwh_signals(self) -> None:
        """Orient skill mentions IWH signals."""
        result = get_orient_skill_content()
        assert "IWH" in result

    def test_mentions_library_stats(self) -> None:
        """Orient skill mentions library stats."""
        result = get_orient_skill_content()
        lower = result.lower()
        assert "stats" in lower or "count" in lower

    def test_mentions_sub_agents_prohibition(self) -> None:
        """Orient skill notes sub-agents must not consume IWH signals."""
        result = get_orient_skill_content()
        lower = result.lower()
        assert "sub-agent" in lower or "subagent" in lower

    def test_orient_skill_does_not_reference_ls_iwh(self) -> None:
        """Orient skill does NOT contain raw 'ls .iwh' instructions."""
        result = get_orient_skill_content()
        assert "ls .iwh" not in result
        assert "ls .lexibrary" not in result

    def test_no_leading_trailing_whitespace(self) -> None:
        """Returned content has no leading/trailing whitespace."""
        result = get_orient_skill_content()
        assert result == result.strip()


# ---------------------------------------------------------------------------
# get_search_skill_content — cross-artifact search
# ---------------------------------------------------------------------------


class TestGetSearchSkillContent:
    """Search skill wraps lexi search with richer context."""

    def test_returns_string(self) -> None:
        """get_search_skill_content() returns a non-empty string."""
        result = get_search_skill_content()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_lexi_search(self) -> None:
        """Search skill references lexi search command."""
        result = get_search_skill_content()
        assert "lexi search" in result

    def test_contains_concept_lookup(self) -> None:
        """Search skill mentions concept lookup."""
        result = get_search_skill_content()
        lower = result.lower()
        assert "concept" in lower

    def test_contains_stack_search(self) -> None:
        """Search skill mentions Stack search."""
        result = get_search_skill_content()
        lower = result.lower()
        assert "stack" in lower

    def test_contains_design_file_search(self) -> None:
        """Search skill mentions design file results."""
        result = get_search_skill_content()
        lower = result.lower()
        assert "design file" in lower

    def test_contains_when_to_use_section(self) -> None:
        """Search skill has a 'when to use' section."""
        result = get_search_skill_content()
        lower = result.lower()
        assert "when to use" in lower

    def test_mentions_territory_mapping(self) -> None:
        """Search skill mentions territory mapping before zoom-in."""
        result = get_search_skill_content()
        lower = result.lower()
        assert "territory" in lower or "map" in lower

    def test_no_leading_trailing_whitespace(self) -> None:
        """Returned content has no leading/trailing whitespace."""
        result = get_search_skill_content()
        assert result == result.strip()


# ---------------------------------------------------------------------------
# get_lookup_skill_content — file lookup
# ---------------------------------------------------------------------------


class TestGetLookupSkillContent:
    """Lookup skill wraps lexi lookup for file and directory context."""

    def test_returns_string(self) -> None:
        """get_lookup_skill_content() returns a non-empty string."""
        result = get_lookup_skill_content()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_lexi_lookup(self) -> None:
        """Lookup skill references lexi lookup command."""
        result = get_lookup_skill_content()
        assert "lexi lookup" in result

    def test_contains_file_argument(self) -> None:
        """Lookup skill mentions a file argument."""
        result = get_lookup_skill_content()
        assert "<file>" in result or "file" in result.lower()

    def test_mentions_design_context(self) -> None:
        """Lookup skill mentions design context."""
        result = get_lookup_skill_content()
        lower = result.lower()
        assert "design" in lower

    def test_contains_when_to_use_section(self) -> None:
        """Lookup skill has a 'when to use' section."""
        result = get_lookup_skill_content()
        lower = result.lower()
        assert "when to use" in lower

    def test_mentions_known_issues(self) -> None:
        """Lookup skill documents Known Issues section."""
        result = get_lookup_skill_content()
        assert "Known Issues" in result

    def test_mentions_iwh_peek(self) -> None:
        """Lookup skill documents IWH signal peek mode."""
        result = get_lookup_skill_content()
        assert "IWH" in result
        assert "peek" in result.lower()

    def test_mentions_directory_support(self) -> None:
        """Lookup skill documents directory lookup mode."""
        result = get_lookup_skill_content()
        assert "<directory>" in result or "directory" in result.lower()
        # Should have a distinct directory section
        assert "Directory lookup" in result

    def test_mentions_conventions(self) -> None:
        """Lookup skill documents conventions section."""
        result = get_lookup_skill_content()
        lower = result.lower()
        assert "convention" in lower

    def test_no_leading_trailing_whitespace(self) -> None:
        """Returned content has no leading/trailing whitespace."""
        result = get_lookup_skill_content()
        assert result == result.strip()


# ---------------------------------------------------------------------------
# get_concepts_skill_content — concept search
# ---------------------------------------------------------------------------


class TestGetConceptsSkillContent:
    """Concepts skill wraps lexi concepts for convention search."""

    def test_returns_string(self) -> None:
        """get_concepts_skill_content() returns a non-empty string."""
        result = get_concepts_skill_content()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_lexi_concepts(self) -> None:
        """Concepts skill references lexi concepts command."""
        result = get_concepts_skill_content()
        assert "lexi concepts" in result

    def test_contains_tag_flag(self) -> None:
        """Concepts skill mentions --tag flag."""
        result = get_concepts_skill_content()
        assert "--tag" in result

    def test_contains_all_flag(self) -> None:
        """Concepts skill mentions --all flag."""
        result = get_concepts_skill_content()
        assert "--all" in result

    def test_mentions_topic_argument(self) -> None:
        """Concepts skill mentions topic argument."""
        result = get_concepts_skill_content()
        assert "topic" in result.lower()

    def test_contains_when_to_use_section(self) -> None:
        """Concepts skill has a 'when to use' section."""
        result = get_concepts_skill_content()
        lower = result.lower()
        assert "when to use" in lower

    def test_mentions_architectural_decisions(self) -> None:
        """Concepts skill mentions architectural decisions."""
        result = get_concepts_skill_content()
        lower = result.lower()
        assert "architectural" in lower or "pattern" in lower

    def test_mentions_wikilinks(self) -> None:
        """Concepts skill mentions wikilinks."""
        result = get_concepts_skill_content()
        assert "wikilink" in result.lower()

    def test_no_leading_trailing_whitespace(self) -> None:
        """Returned content has no leading/trailing whitespace."""
        result = get_concepts_skill_content()
        assert result == result.strip()


# ---------------------------------------------------------------------------
# get_stack_skill_content — Stack Q&A
# ---------------------------------------------------------------------------


class TestGetStackSkillContent:
    """Stack skill wraps lexi stack for Q&A operations."""

    def test_returns_string(self) -> None:
        """get_stack_skill_content() returns a non-empty string."""
        result = get_stack_skill_content()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_lexi_stack_search(self) -> None:
        """Stack skill references lexi stack search."""
        result = get_stack_skill_content()
        assert "lexi stack search" in result

    def test_contains_lexi_stack_post(self) -> None:
        """Stack skill references lexi stack post."""
        result = get_stack_skill_content()
        assert "lexi stack post" in result

    def test_contains_lexi_stack_finding(self) -> None:
        """Stack skill references lexi stack finding."""
        result = get_stack_skill_content()
        assert "lexi stack finding" in result

    def test_contains_when_to_use_section(self) -> None:
        """Stack skill has a 'when to use' section."""
        result = get_stack_skill_content()
        lower = result.lower()
        assert "when to use" in lower

    def test_mentions_debugging(self) -> None:
        """Stack skill mentions debugging as a trigger."""
        result = get_stack_skill_content()
        lower = result.lower()
        assert "debug" in lower

    def test_mentions_research_subagent(self) -> None:
        """Stack skill references lexi-research subagent."""
        result = get_stack_skill_content()
        assert "lexi-research" in result

    def test_no_leading_trailing_whitespace(self) -> None:
        """Returned content has no leading/trailing whitespace."""
        result = get_stack_skill_content()
        assert result == result.strip()
