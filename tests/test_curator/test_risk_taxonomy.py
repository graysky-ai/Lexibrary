"""Tests for the curator risk taxonomy module."""

from __future__ import annotations

import pytest

from lexibrary.curator.risk_taxonomy import (
    _ACTION_KEY_TO_ARTIFACT_KIND,
    RISK_TAXONOMY,
    ActionRisk,
    get_risk_level,
    should_dispatch,
)

# ---------------------------------------------------------------------------
# Expected action keys by risk level (must match spec exactly)
# ---------------------------------------------------------------------------

EXPECTED_LOW_KEYS = {
    "regenerate_stale_design",
    "update_footer_hashes",
    "mark_design_unlinked",
    "reconcile_agent_interface_stable",
    "integrate_sidecar_comments",
    "prune_ephemeral_comments",
    "promote_comment",
    "delete_orphaned_comments",
    "fix_broken_wikilink_exact",
    "fix_broken_wikilink_fuzzy",
    "strip_unresolved_wikilink",
    "add_alias_fuzzy_match",
    "add_missing_bidirectional_dep",
    "remove_orphaned_reverse_dep",
    "resolve_slug_collision",
    "resolve_alias_collision",
    "autofix_validation_issue",
    "remove_orphan_zero_deps",
    "remove_orphaned_aindex",
    "consume_superseded_iwh",
    "write_reactive_iwh",
    "flag_unresolvable_agent_design",
    # Deprecation lifecycle (Phase 2)
    "hard_delete_concept_past_ttl",
    "hard_delete_convention_past_ttl",
    "hard_delete_playbook_past_ttl",
    "delete_comments_sidecar",
    "concept_draft_to_active",
    "convention_draft_to_active",
    "playbook_draft_to_active",
    "stack_post_transition",
}

EXPECTED_MEDIUM_KEYS = {
    "deprecate_design_file",
    "reconcile_agent_interface_changed",
    "rewrite_insights_section",
    "flag_conflicting_conventions",
    "suggest_new_concept",
    "promote_blocked_iwh",
    # Deprecation lifecycle (Phase 2)
    "deprecate_convention",
    "deprecate_playbook",
    "apply_migration_edits",
}

EXPECTED_HIGH_KEYS = {
    "reconcile_agent_extensive_content",
    # Deprecation lifecycle (Phase 2)
    "deprecate_concept",
}


# ---------------------------------------------------------------------------
# ActionRisk dataclass
# ---------------------------------------------------------------------------


class TestActionRisk:
    """ActionRisk dataclass construction and field access."""

    def test_create_action_risk(self) -> None:
        risk = ActionRisk(
            level="low",
            rationale="Mechanical re-run",
            function_ref="curator.staleness.regenerate",
        )
        assert risk.level == "low"
        assert risk.rationale == "Mechanical re-run"
        assert risk.function_ref == "curator.staleness.regenerate"

    def test_action_risk_is_frozen(self) -> None:
        risk = ActionRisk(level="low", rationale="test", function_ref="test.ref")
        with pytest.raises(AttributeError):
            risk.level = "high"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# RISK_TAXONOMY constant — completeness and accuracy
# ---------------------------------------------------------------------------


class TestRiskTaxonomy:
    """The RISK_TAXONOMY constant contains all expected action keys."""

    def test_all_action_keys_present(self) -> None:
        all_expected = EXPECTED_LOW_KEYS | EXPECTED_MEDIUM_KEYS | EXPECTED_HIGH_KEYS
        assert set(RISK_TAXONOMY.keys()) == all_expected

    def test_low_risk_count(self) -> None:
        low_keys = {k for k, v in RISK_TAXONOMY.items() if v.level == "low"}
        assert len(low_keys) == 30

    def test_medium_risk_count(self) -> None:
        medium_keys = {k for k, v in RISK_TAXONOMY.items() if v.level == "medium"}
        assert len(medium_keys) == 9

    def test_high_risk_count(self) -> None:
        high_keys = {k for k, v in RISK_TAXONOMY.items() if v.level == "high"}
        assert len(high_keys) == 2

    def test_low_keys_match_spec(self) -> None:
        actual_low = {k for k, v in RISK_TAXONOMY.items() if v.level == "low"}
        assert actual_low == EXPECTED_LOW_KEYS

    def test_medium_keys_match_spec(self) -> None:
        actual_medium = {k for k, v in RISK_TAXONOMY.items() if v.level == "medium"}
        assert actual_medium == EXPECTED_MEDIUM_KEYS

    def test_high_keys_match_spec(self) -> None:
        actual_high = {k for k, v in RISK_TAXONOMY.items() if v.level == "high"}
        assert actual_high == EXPECTED_HIGH_KEYS

    def test_specific_risk_levels(self) -> None:
        """Spot-check specific entries per spec scenarios."""
        assert RISK_TAXONOMY["regenerate_stale_design"].level == "low"
        assert RISK_TAXONOMY["deprecate_design_file"].level == "medium"
        assert RISK_TAXONOMY["reconcile_agent_extensive_content"].level == "high"

    def test_all_entries_have_rationale(self) -> None:
        for key, risk in RISK_TAXONOMY.items():
            assert risk.rationale, f"{key} has empty rationale"

    def test_all_entries_have_function_ref(self) -> None:
        for key, risk in RISK_TAXONOMY.items():
            assert risk.function_ref, f"{key} has empty function_ref"

    def test_total_action_count(self) -> None:
        assert len(RISK_TAXONOMY) == 41  # 30 + 9 + 2


# ---------------------------------------------------------------------------
# get_risk_level — override lookup
# ---------------------------------------------------------------------------


class TestGetRiskLevel:
    """get_risk_level checks overrides first, falls back to taxonomy."""

    def test_no_override_returns_taxonomy_default(self) -> None:
        assert get_risk_level("regenerate_stale_design", {}) == "low"

    def test_override_changes_level(self) -> None:
        overrides = {"deprecate_design_file": "high"}
        assert get_risk_level("deprecate_design_file", overrides) == "high"

    def test_override_can_lower_risk(self) -> None:
        overrides = {"reconcile_agent_extensive_content": "low"}
        assert get_risk_level("reconcile_agent_extensive_content", overrides) == "low"

    def test_unknown_key_raises_key_error(self) -> None:
        with pytest.raises(KeyError, match="nonexistent_action"):
            get_risk_level("nonexistent_action", {})

    def test_unknown_key_with_override_succeeds(self) -> None:
        """Override for unknown key does NOT raise -- override takes precedence."""
        assert get_risk_level("custom_action", {"custom_action": "medium"}) == "medium"

    def test_override_empty_dict_uses_taxonomy(self) -> None:
        for key, risk in RISK_TAXONOMY.items():
            assert get_risk_level(key, {}) == risk.level

    def test_medium_risk_default(self) -> None:
        assert get_risk_level("suggest_new_concept", {}) == "medium"

    def test_high_risk_default(self) -> None:
        assert get_risk_level("reconcile_agent_extensive_content", {}) == "high"


# ---------------------------------------------------------------------------
# should_dispatch — autonomy gating
# ---------------------------------------------------------------------------


class TestShouldDispatch:
    """should_dispatch gates on autonomy mode and effective risk level."""

    # --- auto_low: only low dispatched ---

    def test_auto_low_dispatches_low(self) -> None:
        assert should_dispatch("regenerate_stale_design", "auto_low", {}) is True

    def test_auto_low_blocks_medium(self) -> None:
        assert should_dispatch("deprecate_design_file", "auto_low", {}) is False

    def test_auto_low_blocks_high(self) -> None:
        assert should_dispatch("reconcile_agent_extensive_content", "auto_low", {}) is False

    # --- full: all dispatched ---

    def test_full_dispatches_low(self) -> None:
        assert should_dispatch("regenerate_stale_design", "full", {}) is True

    def test_full_dispatches_medium(self) -> None:
        assert should_dispatch("deprecate_design_file", "full", {}) is True

    def test_full_dispatches_high(self) -> None:
        assert should_dispatch("reconcile_agent_extensive_content", "full", {}) is True

    # --- propose: none dispatched ---

    def test_propose_blocks_low(self) -> None:
        assert should_dispatch("regenerate_stale_design", "propose", {}) is False

    def test_propose_blocks_medium(self) -> None:
        assert should_dispatch("deprecate_design_file", "propose", {}) is False

    def test_propose_blocks_high(self) -> None:
        assert should_dispatch("reconcile_agent_extensive_content", "propose", {}) is False

    # --- overrides interact with autonomy ---

    def test_override_elevates_blocks_auto_low(self) -> None:
        """Override elevates low to medium; auto_low now blocks it."""
        overrides = {"regenerate_stale_design": "medium"}
        assert should_dispatch("regenerate_stale_design", "auto_low", overrides) is False

    def test_override_lowers_allows_auto_low(self) -> None:
        """Override lowers medium to low; auto_low now dispatches it."""
        overrides = {"deprecate_design_file": "low"}
        assert should_dispatch("deprecate_design_file", "auto_low", overrides) is True

    def test_override_with_full_always_dispatches(self) -> None:
        """Full mode dispatches regardless of override level."""
        overrides = {"regenerate_stale_design": "high"}
        assert should_dispatch("regenerate_stale_design", "full", overrides) is True

    def test_override_with_propose_never_dispatches(self) -> None:
        """Propose mode blocks regardless of override level."""
        overrides = {"reconcile_agent_extensive_content": "low"}
        assert should_dispatch("reconcile_agent_extensive_content", "propose", overrides) is False

    # --- unknown key raises through should_dispatch ---

    def test_unknown_key_raises(self) -> None:
        with pytest.raises(KeyError):
            should_dispatch("nonexistent_action", "auto_low", {})

    # --- exhaustive: all keys dispatch under full ---

    def test_all_keys_dispatch_under_full(self) -> None:
        for key in RISK_TAXONOMY:
            assert should_dispatch(key, "full", {}) is True, f"{key} should dispatch under full"

    def test_all_keys_blocked_under_propose(self) -> None:
        for key in RISK_TAXONOMY:
            assert should_dispatch(key, "propose", {}) is False, (
                f"{key} should be blocked under propose"
            )

    def test_only_low_dispatch_under_auto_low(self) -> None:
        for key, risk in RISK_TAXONOMY.items():
            expected = risk.level == "low"
            assert should_dispatch(key, "auto_low", {}) is expected, (
                f"{key} (level={risk.level}): expected dispatch={expected}"
            )


# ---------------------------------------------------------------------------
# Deprecation action keys — completeness and risk level accuracy
# ---------------------------------------------------------------------------

# All 13 deprecation action keys with their expected risk levels.
DEPRECATION_ACTION_KEYS_WITH_LEVELS: dict[str, str] = {
    "deprecate_concept": "high",
    "deprecate_convention": "medium",
    "deprecate_playbook": "medium",
    "deprecate_design_file": "medium",
    "hard_delete_concept_past_ttl": "low",
    "hard_delete_convention_past_ttl": "low",
    "hard_delete_playbook_past_ttl": "low",
    "delete_comments_sidecar": "low",
    "apply_migration_edits": "medium",
    "concept_draft_to_active": "low",
    "convention_draft_to_active": "low",
    "playbook_draft_to_active": "low",
    "stack_post_transition": "low",
}


class TestDeprecationActionKeys:
    """All 13 deprecation action keys are present with correct risk levels."""

    def test_all_13_deprecation_keys_present(self) -> None:
        for key in DEPRECATION_ACTION_KEYS_WITH_LEVELS:
            assert key in RISK_TAXONOMY, f"Missing deprecation key: {key!r}"

    def test_deprecation_key_count(self) -> None:
        assert len(DEPRECATION_ACTION_KEYS_WITH_LEVELS) == 13

    def test_deprecation_risk_levels_match(self) -> None:
        for key, expected_level in DEPRECATION_ACTION_KEYS_WITH_LEVELS.items():
            actual = RISK_TAXONOMY[key].level
            assert actual == expected_level, (
                f"{key}: expected level={expected_level!r}, got {actual!r}"
            )

    def test_all_deprecation_entries_have_rationale(self) -> None:
        for key in DEPRECATION_ACTION_KEYS_WITH_LEVELS:
            assert RISK_TAXONOMY[key].rationale, f"{key} has empty rationale"

    def test_all_deprecation_entries_have_function_ref(self) -> None:
        for key in DEPRECATION_ACTION_KEYS_WITH_LEVELS:
            assert RISK_TAXONOMY[key].function_ref, f"{key} has empty function_ref"

    def test_deprecation_function_refs_use_correct_modules(self) -> None:
        """Verify function_refs point to appropriate curator sub-modules."""
        for key in DEPRECATION_ACTION_KEYS_WITH_LEVELS:
            ref = RISK_TAXONOMY[key].function_ref
            assert ref.startswith("curator."), (
                f"{key}: function_ref {ref!r} should start with 'curator.'"
            )


# ---------------------------------------------------------------------------
# Confirmation overrides — should_dispatch with confirmation_overrides
# ---------------------------------------------------------------------------


class TestConfirmationOverrides:
    """should_dispatch respects confirmation_overrides for deprecation actions."""

    def test_confirmation_override_blocks_full_for_concept(self) -> None:
        """Concept deprecation blocked under full when confirmation required."""
        result = should_dispatch(
            "deprecate_concept",
            "full",
            {},
            confirmation_overrides={"concept": True},
        )
        assert result is False

    def test_confirmation_override_blocks_full_for_convention(self) -> None:
        """Convention deprecation blocked under full when confirmation required."""
        result = should_dispatch(
            "deprecate_convention",
            "full",
            {},
            confirmation_overrides={"convention": True},
        )
        assert result is False

    def test_no_confirmation_override_allows_full_for_concept(self) -> None:
        """Concept deprecation dispatched under full without confirmation override."""
        result = should_dispatch(
            "deprecate_concept",
            "full",
            {},
            confirmation_overrides=None,
        )
        assert result is True

    def test_no_confirmation_override_allows_full_for_convention(self) -> None:
        """Convention deprecation dispatched under full without override."""
        result = should_dispatch(
            "deprecate_convention",
            "full",
            {},
            confirmation_overrides=None,
        )
        assert result is True

    def test_confirmation_false_allows_full(self) -> None:
        """Confirmation override set to False does not block dispatch."""
        result = should_dispatch(
            "deprecate_concept",
            "full",
            {},
            confirmation_overrides={"concept": False},
        )
        assert result is True

    def test_confirmation_override_empty_dict_allows_full(self) -> None:
        """Empty confirmation overrides dict does not block dispatch."""
        result = should_dispatch(
            "deprecate_concept",
            "full",
            {},
            confirmation_overrides={},
        )
        assert result is True

    def test_confirmation_override_unrelated_kind_allows_full(self) -> None:
        """Override for a different kind does not block concept deprecation."""
        result = should_dispatch(
            "deprecate_concept",
            "full",
            {},
            confirmation_overrides={"convention": True},
        )
        assert result is True

    def test_confirmation_override_with_propose_still_blocks(self) -> None:
        """Propose mode blocks even without confirmation override."""
        result = should_dispatch(
            "deprecate_concept",
            "propose",
            {},
            confirmation_overrides={"concept": True},
        )
        assert result is False

    def test_confirmation_override_with_auto_low_still_blocks_high(self) -> None:
        """auto_low blocks high-risk actions regardless of confirmation overrides."""
        result = should_dispatch(
            "deprecate_concept",
            "auto_low",
            {},
            confirmation_overrides={"concept": True},
        )
        assert result is False

    def test_non_deprecation_action_unaffected_by_confirmation(self) -> None:
        """Actions not in _ACTION_KEY_TO_ARTIFACT_KIND are unaffected."""
        result = should_dispatch(
            "regenerate_stale_design",
            "full",
            {},
            confirmation_overrides={"concept": True},
        )
        assert result is True

    def test_action_key_to_artifact_kind_mapping(self) -> None:
        """The mapping covers exactly the expected deprecation actions."""
        assert _ACTION_KEY_TO_ARTIFACT_KIND == {
            "deprecate_concept": "concept",
            "deprecate_convention": "convention",
        }
