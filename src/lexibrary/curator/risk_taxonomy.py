"""Risk taxonomy for curator actions.

Defines the risk level, rationale, and handler reference for every curator
action key.  The `get_risk_level` and `should_dispatch` helpers translate
these classifications into runtime dispatch decisions based on the active
autonomy mode and any user-configured overrides.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class ActionRisk:
    """Immutable risk classification for a single curator action."""

    level: Literal["low", "medium", "high"]
    rationale: str
    function_ref: str


# ---------------------------------------------------------------------------
# Canonical risk taxonomy — every action the curator may perform.
# 30 Low  ·  9 Medium  ·  2 High
# ---------------------------------------------------------------------------

RISK_TAXONOMY: dict[str, ActionRisk] = {
    # --- Low-risk actions (22) -------------------------------------------
    "regenerate_stale_design": ActionRisk(
        level="low",
        rationale="Mechanical re-run of archivist pipeline",
        function_ref="curator.staleness.regenerate",
    ),
    "update_footer_hashes": ActionRisk(
        level="low",
        rationale="Metadata-only refresh",
        function_ref="curator.staleness.update_footer_hashes",
    ),
    "mark_design_unlinked": ActionRisk(
        level="low",
        rationale="Reversible on re-addition",
        function_ref="curator.consistency.mark_design_unlinked",
    ),
    "reconcile_agent_interface_stable": ActionRisk(
        level="low",
        rationale="Interface unchanged; mechanical refresh",
        function_ref="curator.reconciliation.reconcile_stable",
    ),
    "integrate_sidecar_comments": ActionRisk(
        level="low",
        rationale="Additive; no existing content modified",
        function_ref="curator.comments.integrate_sidecar_comments",
    ),
    "prune_ephemeral_comments": ActionRisk(
        level="low",
        rationale="Operational annotation, not knowledge",
        function_ref="curator.comments.prune_ephemeral_comments",
    ),
    "promote_comment": ActionRisk(
        level="low",
        rationale="Read-only analysis + artifact creation",
        function_ref="curator.comments.promote_comment",
    ),
    "delete_orphaned_comments": ActionRisk(
        level="low",
        rationale="Parent artifact already removed",
        function_ref="curator.comments.delete_orphaned_comments",
    ),
    "fix_broken_wikilink_exact": ActionRisk(
        level="low",
        rationale="Mechanical, verifiable via resolver",
        function_ref="curator.consistency.fix_broken_wikilink_exact",
    ),
    "fix_broken_wikilink_fuzzy": ActionRisk(
        level="low",
        rationale="Verifiable; confidence threshold applies",
        function_ref="curator.consistency.fix_broken_wikilink_fuzzy",
    ),
    "strip_unresolved_wikilink": ActionRisk(
        level="low",
        rationale="Removes dead reference",
        function_ref="curator.consistency.strip_unresolved_wikilink",
    ),
    "add_alias_fuzzy_match": ActionRisk(
        level="low",
        rationale="Non-destructive alias expansion",
        function_ref="curator.consistency.add_alias_fuzzy_match",
    ),
    "add_missing_bidirectional_dep": ActionRisk(
        level="low",
        rationale="Mechanical repair",
        function_ref="curator.consistency.add_missing_bidirectional_dep",
    ),
    "remove_orphaned_reverse_dep": ActionRisk(
        level="low",
        rationale="Dependent no longer exists",
        function_ref="curator.consistency.remove_orphaned_reverse_dep",
    ),
    "resolve_slug_collision": ActionRisk(
        level="low",
        rationale="Deterministic suffix algorithm",
        function_ref="curator.consistency.resolve_slug_collision",
    ),
    "resolve_alias_collision": ActionRisk(
        level="low",
        rationale="Deterministic deduplication",
        function_ref="curator.consistency.resolve_alias_collision",
    ),
    "autofix_validation_issue": ActionRisk(
        level="low",
        rationale="Pre-vetted fixes from validator registry",
        function_ref="curator.consistency.autofix_validation_issue",
    ),
    "remove_orphan_zero_deps": ActionRisk(
        level="low",
        rationale="Nothing references it",
        function_ref="curator.consistency.remove_orphan_zero_deps",
    ),
    "remove_orphaned_aindex": ActionRisk(
        level="low",
        rationale="Source directory deleted",
        function_ref="curator.consistency.remove_orphaned_aindex",
    ),
    "consume_superseded_iwh": ActionRisk(
        level="low",
        rationale="Subsequent commits indicate completion",
        function_ref="curator.consistency.consume_superseded_iwh",
    ),
    "write_reactive_iwh": ActionRisk(
        level="low",
        rationale="Directory-scoped coordination message",
        function_ref="curator.consistency.write_reactive_iwh",
    ),
    "flag_unresolvable_agent_design": ActionRisk(
        level="low",
        rationale="Escalation only; no artifact modification",
        function_ref="curator.reconciliation.flag_unresolvable_agent_design",
    ),
    # --- Medium-risk actions (6) -----------------------------------------
    "deprecate_design_file": ActionRisk(
        level="medium",
        rationale="Cascade may affect dependents",
        function_ref="curator.deprecation.deprecate_design_file",
    ),
    "reconcile_agent_interface_changed": ActionRisk(
        level="medium",
        rationale="LLM judges which agent notes still apply",
        function_ref="curator.reconciliation.reconcile_interface_changed",
    ),
    "rewrite_insights_section": ActionRisk(
        level="medium",
        rationale="Existing curator insights may be invalidated",
        function_ref="curator.comments.rewrite_insights_section",
    ),
    "flag_conflicting_conventions": ActionRisk(
        level="medium",
        rationale="May require scope restructuring",
        function_ref="curator.consistency.flag_conflicting_conventions",
    ),
    "suggest_new_concept": ActionRisk(
        level="medium",
        rationale="Proposes artifact creation; needs review",
        function_ref="curator.consistency.suggest_new_concept",
    ),
    "promote_blocked_iwh": ActionRisk(
        level="medium",
        rationale="Creates persistent searchable artifact",
        function_ref="curator.consistency.promote_blocked_iwh",
    ),
    # --- Deprecation lifecycle: low-risk actions ---------------------------
    "hard_delete_concept_past_ttl": ActionRisk(
        level="low",
        rationale="TTL expired and zero inbound references",
        function_ref="curator.lifecycle.hard_delete",
    ),
    "hard_delete_convention_past_ttl": ActionRisk(
        level="low",
        rationale="TTL expired and zero inbound references",
        function_ref="curator.lifecycle.hard_delete",
    ),
    "hard_delete_playbook_past_ttl": ActionRisk(
        level="low",
        rationale="TTL expired and zero inbound references",
        function_ref="curator.lifecycle.hard_delete",
    ),
    "delete_comments_sidecar": ActionRisk(
        level="low",
        rationale="Parent artifact already deprecated or deleted",
        function_ref="curator.deprecation.delete_comments_sidecar",
    ),
    "concept_draft_to_active": ActionRisk(
        level="low",
        rationale="Promotion from draft; no existing content modified",
        function_ref="curator.lifecycle.draft_to_active",
    ),
    "convention_draft_to_active": ActionRisk(
        level="low",
        rationale="Promotion from draft; no existing content modified",
        function_ref="curator.lifecycle.draft_to_active",
    ),
    "playbook_draft_to_active": ActionRisk(
        level="low",
        rationale="Promotion from draft; no existing content modified",
        function_ref="curator.lifecycle.draft_to_active",
    ),
    "stack_post_transition": ActionRisk(
        level="low",
        rationale="Lifecycle state change on resolved or stale post",
        function_ref="curator.lifecycle.stack_post_transition",
    ),
    # --- Deprecation lifecycle: medium-risk actions ----------------------
    "deprecate_convention": ActionRisk(
        level="medium",
        rationale="Cascade may affect convention consumers",
        function_ref="curator.deprecation.deprecate_convention",
    ),
    "deprecate_playbook": ActionRisk(
        level="medium",
        rationale="Cascade may affect playbook consumers",
        function_ref="curator.deprecation.deprecate_playbook",
    ),
    "apply_migration_edits": ActionRisk(
        level="medium",
        rationale="Modifies dependent artifacts post-deprecation",
        function_ref="curator.migration.apply_migration_edits",
    ),
    # --- High-risk actions (2) -------------------------------------------
    "reconcile_agent_extensive_content": ActionRisk(
        level="high",
        rationale="Lossy merge possible; agent insights at risk",
        function_ref="curator.reconciliation.reconcile_extensive_content",
    ),
    "deprecate_concept": ActionRisk(
        level="high",
        rationale="Concepts are high-value knowledge; cascade may be extensive",
        function_ref="curator.deprecation.deprecate_concept",
    ),
}


def get_risk_level(
    action_key: str,
    overrides: dict[str, str],
) -> str:
    """Return the effective risk level for *action_key*.

    Checks *overrides* first (user-configured per-key risk-level tweaks),
    then falls back to the canonical ``RISK_TAXONOMY``.

    Raises ``KeyError`` if *action_key* does not exist in the taxonomy
    **and** is not present in *overrides*.
    """
    if action_key in overrides:
        return overrides[action_key]
    if action_key not in RISK_TAXONOMY:
        raise KeyError(f"Unknown action key: {action_key!r}")
    return RISK_TAXONOMY[action_key].level


# Mapping from deprecation action keys to artifact kinds for confirmation
# override lookup.  When a confirmation override maps a kind to ``True``,
# the action is blocked even under ``full`` autonomy.
_ACTION_KEY_TO_ARTIFACT_KIND: dict[str, str] = {
    "deprecate_concept": "concept",
    "deprecate_convention": "convention",
}


def should_dispatch(
    action_key: str,
    autonomy: str,
    overrides: dict[str, str],
    *,
    confirmation_overrides: dict[str, bool] | None = None,
) -> bool:
    """Decide whether *action_key* should be dispatched under *autonomy*.

    Autonomy modes:
    - ``"auto_low"`` — dispatch **low** only
    - ``"full"``     — dispatch **all** levels
    - ``"propose"``  — dispatch **none** (proposal-only mode)

    The effective risk level is resolved via :func:`get_risk_level`, which
    respects user-configured *overrides*.

    When *confirmation_overrides* maps an artifact kind (e.g. ``"concept"``)
    to ``True``, the corresponding deprecation action is blocked even under
    ``full`` autonomy.  The mapping from action key to artifact kind is
    defined in ``_ACTION_KEY_TO_ARTIFACT_KIND``.
    """
    # Check confirmation overrides first — these block regardless of autonomy.
    if confirmation_overrides:
        kind = _ACTION_KEY_TO_ARTIFACT_KIND.get(action_key)
        if kind is not None and confirmation_overrides.get(kind, False):
            return False

    level = get_risk_level(action_key, overrides)
    if autonomy == "auto_low":
        return level == "low"
    # "propose" — never dispatch
    return autonomy == "full"
