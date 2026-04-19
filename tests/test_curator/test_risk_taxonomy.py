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
    "reconcile_agent_interface_stable",
    "integrate_sidecar_comments",
    "delete_orphaned_comments",
    # ``flag_stale_convention`` / ``flag_stale_playbook`` retired in curator-4
    # Group 22 (replaced by ``escalate_convention_stale`` /
    # ``escalate_playbook_staleness`` listed below).
    "autofix_validation_issue",
    # ``remove_orphan_zero_deps`` retired in curator-4 Group 19 (replaced by
    # the ``escalate_orphan_concepts`` escalation fixer listed below).
    "add_missing_reverse_dep",
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
    # Budget trimming (Phase 3)
    "shorten_description",
    # Validation bridge per-check keys (curator-fix Phase 2)
    "fix_hash_freshness",
    "fix_orphan_artifacts",
    "fix_aindex_coverage",
    "fix_orphaned_aindex",
    "fix_orphaned_iwh",
    "fix_deprecated_ttl",
    # Bidirectional-deps fixer registered by curator-freshness group 4
    # (replaces the retired ``add_missing_bidirectional_dep`` /
    # ``remove_orphaned_reverse_dep`` consistency-side handlers with a
    # single archivist-pipeline-backed validator fix).
    "fix_bidirectional_deps",
    # Duplicate-slug / duplicate-alias fixers registered by
    # curator-freshness group 7 (Phase 4 Family B).  Both are propose-only
    # — they replace the retired curator-side ``resolve_slug_collision`` /
    # ``resolve_alias_collision`` handlers.
    "fix_duplicate_slugs",
    "fix_duplicate_aliases",
    # Wikilink resolution fixer registered by curator-freshness group 9
    # (Phase 4 Family D).  Replaces the retired curator-side
    # ``strip_unresolved_wikilink`` / ``fix_broken_wikilink_fuzzy``
    # handlers with an archivist-pipeline-backed validator fix.
    "fix_wikilink_resolution",
    # curator-4 Group 19: four escalate_* fixers route to operator
    # resolution (no artifact mutation; IWH breadcrumb only) plus the TTL
    # variant of the IWH-cleanup fixer.
    "escalate_orphan_concepts",
    "escalate_stale_concept",
    "escalate_convention_stale",
    "escalate_playbook_staleness",
    "fix_orphaned_iwh_signals",
}

EXPECTED_MEDIUM_KEYS = {
    "deprecate_design_file",
    "reconcile_agent_interface_changed",
    "suggest_new_concept",
    "promote_blocked_iwh",
    # Deprecation lifecycle (Phase 2)
    "deprecate_convention",
    "deprecate_playbook",
    "apply_migration_edits",
    # Budget trimming (Phase 3)
    "propose_condensation",
    # Comment auditing (Phase 3)
    "flag_stale_comment",
    "audit_description",
    "audit_summary",
    # Validation bridge — medium because deprecation workflow
    # deletes / mutates files (curator-fix Phase 2)
    "fix_orphaned_designs",
    # curator-4 Group 19: token-budget condensation uses a lossy BAML
    # transformation and consumes (counted) LLM budget.
    "fix_lookup_token_budget_exceeded",
}

EXPECTED_HIGH_KEYS = {
    "reconcile_agent_extensive_content",
    # Deprecation lifecycle (Phase 2)
    "deprecate_concept",
    # Budget trimming (Phase 3)
    "condense_file",
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
        # 39 previously (37 base + 2 Phase 3 group 8) minus 4 orphan/dead
        # stubs removed by curator-fix-2 group 1 (``mark_design_unlinked``,
        # ``prune_ephemeral_comments``, ``promote_comment``,
        # ``fix_broken_wikilink_exact``) minus 2 bidirectional-deps
        # handlers retired in Phase 1a of ``curator-freshness``
        # (``add_missing_bidirectional_dep``, ``remove_orphaned_reverse_dep``)
        # plus 1 replacement fixer added in group 4 of ``curator-freshness``
        # (``fix_bidirectional_deps``) minus 1 curator-side .aindex
        # cleanup retired in Phase 3 of ``curator-freshness``
        # (``remove_orphaned_aindex`` — replaced by the validator's
        # ``fix_orphaned_aindex`` already counted above) minus 3 slug/alias
        # handlers retired in Phase 4 Family B of ``curator-freshness``
        # (``resolve_slug_collision``, ``resolve_alias_collision``, and the
        # orphaned ``add_alias_fuzzy_match`` entry) plus 2 replacement
        # propose-only fixers added in the same group
        # (``fix_duplicate_slugs``, ``fix_duplicate_aliases``) minus 2
        # wikilink hygiene handlers retired in Phase 4 Family D
        # (``strip_unresolved_wikilink``, ``fix_broken_wikilink_fuzzy``)
        # plus 1 replacement fixer added in the same group
        # (``fix_wikilink_resolution``).  curator-4 Group 19: minus 1
        # retired (``remove_orphan_zero_deps``) plus 5 added
        # (``escalate_orphan_concepts``, ``escalate_stale_concept``,
        # ``escalate_convention_stale``, ``escalate_playbook_staleness``,
        # ``fix_orphaned_iwh_signals``).  curator-4 Group 22: minus 2
        # retired (``flag_stale_convention``, ``flag_stale_playbook``).
        assert len(low_keys) == 34

    def test_medium_risk_count(self) -> None:
        medium_keys = {k for k, v in RISK_TAXONOMY.items() if v.level == "medium"}
        # 14 previously minus 2 orphan/dead stubs removed by
        # curator-fix-2 group 1 (``rewrite_insights_section``,
        # ``flag_conflicting_conventions``).  curator-4 Group 19 adds 1
        # (``fix_lookup_token_budget_exceeded``).
        assert len(medium_keys) == 13

    def test_high_risk_count(self) -> None:
        high_keys = {k for k, v in RISK_TAXONOMY.items() if v.level == "high"}
        assert len(high_keys) == 3

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
        # 34 Low + 13 Medium + 3 High = 50 (curator-4 Group 22 delta: -2 Low
        # retired — ``flag_stale_convention`` / ``flag_stale_playbook``).
        assert len(RISK_TAXONOMY) == 50


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

    def test_unknown_key_returns_low_with_warning(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Unknown action key logs a warning and falls back to ``low``."""
        import logging

        with caplog.at_level(logging.WARNING, logger="lexibrary.curator.risk_taxonomy"):
            result = get_risk_level("nonexistent_action", {})
        assert result == "low"
        assert any("nonexistent_action" in record.getMessage() for record in caplog.records), (
            f"expected warning mentioning 'nonexistent_action', got {caplog.records!r}"
        )

    def test_unknown_key_with_override_succeeds(self) -> None:
        """Override for unknown key does NOT warn -- override takes precedence."""
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

    # --- unknown key falls back to "low" (warning logged) ---

    def test_unknown_key_falls_back_to_low(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Unknown action key resolves to ``low``; auto_low dispatches it."""
        import logging

        with caplog.at_level(logging.WARNING, logger="lexibrary.curator.risk_taxonomy"):
            # Unknown key → warning + "low" default → auto_low dispatches
            assert should_dispatch("nonexistent_action", "auto_low", {}) is True
        assert any("nonexistent_action" in record.getMessage() for record in caplog.records)

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


# ---------------------------------------------------------------------------
# Phase 3: Budget trimming and comment auditing action keys
# ---------------------------------------------------------------------------

# All 6 Phase 3 action keys with their expected risk levels.
PHASE3_ACTION_KEYS_WITH_LEVELS: dict[str, str] = {
    "condense_file": "high",
    "shorten_description": "low",
    "propose_condensation": "medium",
    "flag_stale_comment": "medium",
    "audit_description": "medium",
    "audit_summary": "medium",
}

# Expected function_ref values for Phase 3 action keys.
# After the Phase 1.5 dispatcher refactor (openspec change curator-fix,
# group 3), every budget/comment-audit action key resolves to the public
# async dispatcher in the owning module.  ``audit_description`` and
# ``audit_summary`` still point at their domain-specific BAML wrappers
# because no dedicated dispatcher has been extracted yet.
PHASE3_FUNCTION_REFS: dict[str, str] = {
    "condense_file": "curator.budget.dispatch_budget_condense",
    "shorten_description": "curator.budget.dispatch_budget_condense",
    "propose_condensation": "curator.budget.dispatch_budget_condense",
    "flag_stale_comment": "curator.auditing.dispatch_comment_audit",
    "audit_description": "curator.auditing.audit_description",
    "audit_summary": "curator.auditing.audit_summary",
}


class TestPhase3ActionKeys:
    """All 6 Phase 3 action keys are present with correct risk levels."""

    def test_all_6_phase3_keys_present(self) -> None:
        for key in PHASE3_ACTION_KEYS_WITH_LEVELS:
            assert key in RISK_TAXONOMY, f"Missing Phase 3 key: {key!r}"

    def test_phase3_key_count(self) -> None:
        assert len(PHASE3_ACTION_KEYS_WITH_LEVELS) == 6

    def test_phase3_risk_levels_match(self) -> None:
        for key, expected_level in PHASE3_ACTION_KEYS_WITH_LEVELS.items():
            actual = RISK_TAXONOMY[key].level
            assert actual == expected_level, (
                f"{key}: expected level={expected_level!r}, got {actual!r}"
            )

    def test_phase3_function_refs_match(self) -> None:
        for key, expected_ref in PHASE3_FUNCTION_REFS.items():
            actual = RISK_TAXONOMY[key].function_ref
            assert actual == expected_ref, (
                f"{key}: expected function_ref={expected_ref!r}, got {actual!r}"
            )

    def test_phase3_entries_have_rationale(self) -> None:
        for key in PHASE3_ACTION_KEYS_WITH_LEVELS:
            assert RISK_TAXONOMY[key].rationale, f"{key} has empty rationale"

    def test_phase3_function_refs_use_correct_modules(self) -> None:
        """Budget trimming refs use curator.budget, auditing uses curator.auditing."""
        budget_keys = {"condense_file", "shorten_description", "propose_condensation"}
        auditing_keys = {"flag_stale_comment", "audit_description", "audit_summary"}

        for key in budget_keys:
            ref = RISK_TAXONOMY[key].function_ref
            assert ref.startswith("curator.budget."), (
                f"{key}: function_ref {ref!r} should start with 'curator.budget.'"
            )

        for key in auditing_keys:
            ref = RISK_TAXONOMY[key].function_ref
            assert ref.startswith("curator.auditing."), (
                f"{key}: function_ref {ref!r} should start with 'curator.auditing.'"
            )


class TestPhase3ShouldDispatch:
    """should_dispatch for Phase 3 action keys under all autonomy modes."""

    # --- condense_file (high) ---

    def test_condense_file_blocked_auto_low(self) -> None:
        assert should_dispatch("condense_file", "auto_low", {}) is False

    def test_condense_file_dispatched_full(self) -> None:
        assert should_dispatch("condense_file", "full", {}) is True

    def test_condense_file_blocked_propose(self) -> None:
        assert should_dispatch("condense_file", "propose", {}) is False

    # --- shorten_description (low) ---

    def test_shorten_description_dispatched_auto_low(self) -> None:
        assert should_dispatch("shorten_description", "auto_low", {}) is True

    def test_shorten_description_dispatched_full(self) -> None:
        assert should_dispatch("shorten_description", "full", {}) is True

    def test_shorten_description_blocked_propose(self) -> None:
        assert should_dispatch("shorten_description", "propose", {}) is False

    # --- propose_condensation (medium) ---

    def test_propose_condensation_blocked_auto_low(self) -> None:
        assert should_dispatch("propose_condensation", "auto_low", {}) is False

    def test_propose_condensation_dispatched_full(self) -> None:
        assert should_dispatch("propose_condensation", "full", {}) is True

    def test_propose_condensation_blocked_propose(self) -> None:
        assert should_dispatch("propose_condensation", "propose", {}) is False

    # --- flag_stale_comment (medium) ---

    def test_flag_stale_comment_blocked_auto_low(self) -> None:
        assert should_dispatch("flag_stale_comment", "auto_low", {}) is False

    def test_flag_stale_comment_dispatched_full(self) -> None:
        assert should_dispatch("flag_stale_comment", "full", {}) is True

    def test_flag_stale_comment_blocked_propose(self) -> None:
        assert should_dispatch("flag_stale_comment", "propose", {}) is False

    # --- audit_description (medium) ---

    def test_audit_description_blocked_auto_low(self) -> None:
        assert should_dispatch("audit_description", "auto_low", {}) is False

    def test_audit_description_dispatched_full(self) -> None:
        assert should_dispatch("audit_description", "full", {}) is True

    def test_audit_description_blocked_propose(self) -> None:
        assert should_dispatch("audit_description", "propose", {}) is False

    # --- audit_summary (medium) ---

    def test_audit_summary_blocked_auto_low(self) -> None:
        assert should_dispatch("audit_summary", "auto_low", {}) is False

    def test_audit_summary_dispatched_full(self) -> None:
        assert should_dispatch("audit_summary", "full", {}) is True

    def test_audit_summary_blocked_propose(self) -> None:
        assert should_dispatch("audit_summary", "propose", {}) is False


class TestPhase3GetRiskLevel:
    """get_risk_level for Phase 3 action keys, with and without overrides."""

    def test_condense_file_default_high(self) -> None:
        assert get_risk_level("condense_file", {}) == "high"

    def test_shorten_description_default_low(self) -> None:
        assert get_risk_level("shorten_description", {}) == "low"

    def test_propose_condensation_default_medium(self) -> None:
        assert get_risk_level("propose_condensation", {}) == "medium"

    def test_flag_stale_comment_default_medium(self) -> None:
        assert get_risk_level("flag_stale_comment", {}) == "medium"

    def test_audit_description_default_medium(self) -> None:
        assert get_risk_level("audit_description", {}) == "medium"

    def test_audit_summary_default_medium(self) -> None:
        assert get_risk_level("audit_summary", {}) == "medium"

    def test_override_condense_file_to_low(self) -> None:
        overrides = {"condense_file": "low"}
        assert get_risk_level("condense_file", overrides) == "low"

    def test_override_shorten_description_to_high(self) -> None:
        overrides = {"shorten_description": "high"}
        assert get_risk_level("shorten_description", overrides) == "high"

    def test_override_changes_dispatch_for_condense_file(self) -> None:
        """Overriding condense_file from high to low enables auto_low dispatch."""
        overrides = {"condense_file": "low"}
        assert should_dispatch("condense_file", "auto_low", overrides) is True

    def test_override_elevates_shorten_description_blocks_auto_low(self) -> None:
        """Overriding shorten_description from low to medium blocks auto_low."""
        overrides = {"shorten_description": "medium"}
        assert should_dispatch("shorten_description", "auto_low", overrides) is False
