"""Autonomy gating tests for deprecation actions under all autonomy levels.

Tests that deprecation action keys behave correctly under ``propose``,
``auto_low``, and ``full`` autonomy modes, and that confirmation policy
overrides gate dispatch as specified.
"""

from __future__ import annotations

import pytest

from lexibrary.curator.risk_taxonomy import (
    RISK_TAXONOMY,
    should_dispatch,
)

# ---------------------------------------------------------------------------
# All 13 deprecation action keys with their canonical risk levels (from spec).
# ---------------------------------------------------------------------------

DEPRECATION_KEYS: dict[str, str] = {
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

LOW_DEPRECATION_KEYS = {k for k, v in DEPRECATION_KEYS.items() if v == "low"}
MEDIUM_DEPRECATION_KEYS = {k for k, v in DEPRECATION_KEYS.items() if v == "medium"}
HIGH_DEPRECATION_KEYS = {k for k, v in DEPRECATION_KEYS.items() if v == "high"}


# ---------------------------------------------------------------------------
# 11.1 — Propose mode: all deprecation actions return False
# ---------------------------------------------------------------------------


class TestProposeMode:
    """Under ``propose`` mode no deprecation action is dispatched."""

    @pytest.mark.parametrize("action_key", sorted(DEPRECATION_KEYS))
    def test_propose_blocks_all_deprecation_actions(self, action_key: str) -> None:
        """Every deprecation action key returns ``should_dispatch() == False``
        under ``propose`` autonomy."""
        assert should_dispatch(action_key, "propose", {}) is False

    def test_propose_blocks_all_low_deprecation_actions(self) -> None:
        """Explicit check that even low-risk deprecation actions are blocked."""
        for key in LOW_DEPRECATION_KEYS:
            assert should_dispatch(key, "propose", {}) is False, (
                f"{key} (low) should be blocked under propose"
            )

    def test_propose_blocks_all_medium_deprecation_actions(self) -> None:
        for key in MEDIUM_DEPRECATION_KEYS:
            assert should_dispatch(key, "propose", {}) is False, (
                f"{key} (medium) should be blocked under propose"
            )

    def test_propose_blocks_all_high_deprecation_actions(self) -> None:
        for key in HIGH_DEPRECATION_KEYS:
            assert should_dispatch(key, "propose", {}) is False, (
                f"{key} (high) should be blocked under propose"
            )

    def test_propose_blocks_even_with_risk_override_to_low(self) -> None:
        """Lowering a high-risk action to low still blocks under propose."""
        overrides = {"deprecate_concept": "low"}
        assert should_dispatch("deprecate_concept", "propose", overrides) is False


# ---------------------------------------------------------------------------
# 11.2 — auto_low mode: risk-level based gating
# ---------------------------------------------------------------------------


class TestAutoLowMode:
    """Under ``auto_low`` only low-risk deprecation actions dispatch."""

    def test_deprecate_concept_high_blocked(self) -> None:
        """``deprecate_concept`` is high risk -- blocked under ``auto_low``."""
        assert should_dispatch("deprecate_concept", "auto_low", {}) is False

    def test_hard_delete_concept_past_ttl_low_dispatched(self) -> None:
        """``hard_delete_concept_past_ttl`` is low risk -- dispatched under ``auto_low``."""
        assert should_dispatch("hard_delete_concept_past_ttl", "auto_low", {}) is True

    def test_apply_migration_edits_medium_blocked(self) -> None:
        """``apply_migration_edits`` is medium risk -- blocked under ``auto_low``."""
        assert should_dispatch("apply_migration_edits", "auto_low", {}) is False

    @pytest.mark.parametrize("action_key", sorted(LOW_DEPRECATION_KEYS))
    def test_auto_low_dispatches_all_low_deprecation_actions(
        self, action_key: str
    ) -> None:
        """All low-risk deprecation actions dispatch under ``auto_low``."""
        assert should_dispatch(action_key, "auto_low", {}) is True

    @pytest.mark.parametrize("action_key", sorted(MEDIUM_DEPRECATION_KEYS))
    def test_auto_low_blocks_all_medium_deprecation_actions(
        self, action_key: str
    ) -> None:
        """All medium-risk deprecation actions are blocked under ``auto_low``."""
        assert should_dispatch(action_key, "auto_low", {}) is False

    @pytest.mark.parametrize("action_key", sorted(HIGH_DEPRECATION_KEYS))
    def test_auto_low_blocks_all_high_deprecation_actions(
        self, action_key: str
    ) -> None:
        """All high-risk deprecation actions are blocked under ``auto_low``."""
        assert should_dispatch(action_key, "auto_low", {}) is False

    def test_auto_low_with_override_lowering_medium_to_low(self) -> None:
        """Override can lower medium to low, allowing dispatch under ``auto_low``."""
        overrides = {"apply_migration_edits": "low"}
        assert should_dispatch("apply_migration_edits", "auto_low", overrides) is True

    def test_auto_low_with_override_elevating_low_to_medium(self) -> None:
        """Override can elevate low to medium, blocking dispatch under ``auto_low``."""
        overrides = {"hard_delete_concept_past_ttl": "medium"}
        assert (
            should_dispatch("hard_delete_concept_past_ttl", "auto_low", overrides)
            is False
        )


# ---------------------------------------------------------------------------
# 11.3 — Full mode: all deprecation actions return True
# ---------------------------------------------------------------------------


class TestFullMode:
    """Under ``full`` autonomy all deprecation actions are dispatched."""

    @pytest.mark.parametrize("action_key", sorted(DEPRECATION_KEYS))
    def test_full_dispatches_all_deprecation_actions(self, action_key: str) -> None:
        """Every deprecation action key returns ``should_dispatch() == True``
        under ``full`` autonomy (no confirmation overrides)."""
        assert should_dispatch(action_key, "full", {}) is True

    def test_full_dispatches_high_risk_deprecation(self) -> None:
        """Explicit check that even the high-risk ``deprecate_concept`` dispatches."""
        assert should_dispatch("deprecate_concept", "full", {}) is True

    def test_full_dispatches_medium_risk_deprecation(self) -> None:
        for key in MEDIUM_DEPRECATION_KEYS:
            assert should_dispatch(key, "full", {}) is True, (
                f"{key} (medium) should dispatch under full"
            )

    def test_full_dispatches_low_risk_deprecation(self) -> None:
        for key in LOW_DEPRECATION_KEYS:
            assert should_dispatch(key, "full", {}) is True, (
                f"{key} (low) should dispatch under full"
            )

    def test_full_with_override_elevating_to_high_still_dispatches(self) -> None:
        """Even with an override elevating risk to high, full dispatches."""
        overrides = {"hard_delete_concept_past_ttl": "high"}
        assert (
            should_dispatch("hard_delete_concept_past_ttl", "full", overrides) is True
        )


# ---------------------------------------------------------------------------
# 11.4 — Confirmation policy overrides
# ---------------------------------------------------------------------------


class TestConfirmationPolicy:
    """Confirmation policy overrides block deprecation even under ``full`` autonomy."""

    def test_concept_confirmation_blocks_full(self) -> None:
        """``deprecate_concept`` under ``full`` with
        ``confirmation_overrides={"concept": True}`` returns ``False``."""
        result = should_dispatch(
            "deprecate_concept",
            "full",
            {},
            confirmation_overrides={"concept": True},
        )
        assert result is False

    def test_convention_confirmation_blocks_full(self) -> None:
        """``deprecate_convention`` under ``full`` with
        ``confirmation_overrides={"convention": True}`` returns ``False``."""
        result = should_dispatch(
            "deprecate_convention",
            "full",
            {},
            confirmation_overrides={"convention": True},
        )
        assert result is False

    def test_concept_confirmation_false_allows_full(self) -> None:
        """Setting confirmation to ``False`` does not block dispatch."""
        result = should_dispatch(
            "deprecate_concept",
            "full",
            {},
            confirmation_overrides={"concept": False},
        )
        assert result is True

    def test_no_confirmation_overrides_allows_full(self) -> None:
        """Passing ``None`` for confirmation_overrides does not block."""
        result = should_dispatch(
            "deprecate_concept",
            "full",
            {},
            confirmation_overrides=None,
        )
        assert result is True

    def test_empty_confirmation_overrides_allows_full(self) -> None:
        """Empty dict for confirmation_overrides does not block."""
        result = should_dispatch(
            "deprecate_concept",
            "full",
            {},
            confirmation_overrides={},
        )
        assert result is True

    def test_unrelated_kind_override_does_not_block(self) -> None:
        """Override for ``"convention"`` does not block ``deprecate_concept``."""
        result = should_dispatch(
            "deprecate_concept",
            "full",
            {},
            confirmation_overrides={"convention": True},
        )
        assert result is True

    def test_confirmation_override_on_non_mapped_action_no_effect(self) -> None:
        """Actions not in _ACTION_KEY_TO_ARTIFACT_KIND are unaffected by
        confirmation overrides."""
        result = should_dispatch(
            "hard_delete_concept_past_ttl",
            "full",
            {},
            confirmation_overrides={"concept": True},
        )
        assert result is True

    def test_confirmation_override_with_propose_still_blocked(self) -> None:
        """Propose mode blocks regardless of confirmation overrides."""
        result = should_dispatch(
            "deprecate_concept",
            "propose",
            {},
            confirmation_overrides={"concept": True},
        )
        assert result is False

    def test_confirmation_override_with_auto_low_high_still_blocked(self) -> None:
        """``auto_low`` blocks high-risk even without confirmation gating."""
        result = should_dispatch(
            "deprecate_concept",
            "auto_low",
            {},
            confirmation_overrides={"concept": True},
        )
        assert result is False

    def test_both_concept_and_convention_confirmed_blocks_both(self) -> None:
        """When both kinds require confirmation, both deprecation actions are blocked."""
        overrides = {"concept": True, "convention": True}
        assert (
            should_dispatch(
                "deprecate_concept", "full", {}, confirmation_overrides=overrides
            )
            is False
        )
        assert (
            should_dispatch(
                "deprecate_convention", "full", {}, confirmation_overrides=overrides
            )
            is False
        )

    def test_confirmation_combined_with_risk_override(self) -> None:
        """Confirmation override takes precedence even when risk is overridden."""
        # Lower deprecate_concept from high to low, but confirm still blocks
        risk_overrides = {"deprecate_concept": "low"}
        result = should_dispatch(
            "deprecate_concept",
            "full",
            risk_overrides,
            confirmation_overrides={"concept": True},
        )
        assert result is False


# ---------------------------------------------------------------------------
# Cross-cutting: verify test data alignment with taxonomy
# ---------------------------------------------------------------------------


class TestDataAlignment:
    """Ensure the test's key sets match what is actually in RISK_TAXONOMY."""

    def test_all_deprecation_keys_exist_in_taxonomy(self) -> None:
        for key in DEPRECATION_KEYS:
            assert key in RISK_TAXONOMY, f"{key!r} missing from RISK_TAXONOMY"

    def test_deprecation_key_levels_match_taxonomy(self) -> None:
        for key, expected_level in DEPRECATION_KEYS.items():
            assert RISK_TAXONOMY[key].level == expected_level, (
                f"{key}: expected {expected_level!r}, "
                f"got {RISK_TAXONOMY[key].level!r}"
            )
