"""Risk taxonomy for curator actions.

Defines the risk level, rationale, and handler reference for every curator
action key.  The `get_risk_level` and `should_dispatch` helpers translate
these classifications into runtime dispatch decisions based on the active
autonomy mode and any user-configured overrides.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
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
# 35 Low  ·  12 Medium  ·  3 High
# ---------------------------------------------------------------------------

RISK_TAXONOMY: dict[str, ActionRisk] = {
    # --- Low-risk actions -------------------------------------------------
    "regenerate_stale_design": ActionRisk(
        level="low",
        rationale="Mechanical re-run of archivist pipeline",
        function_ref="curator.staleness.dispatch_staleness_resolver",
    ),
    "update_footer_hashes": ActionRisk(
        level="low",
        rationale="Metadata-only refresh",
        function_ref="curator.staleness.dispatch_staleness_resolver",
    ),
    "reconcile_agent_interface_stable": ActionRisk(
        level="low",
        rationale="Interface unchanged; mechanical refresh",
        function_ref="curator.reconciliation.dispatch_reconciliation",
    ),
    "integrate_sidecar_comments": ActionRisk(
        level="low",
        rationale="Additive; no existing content modified",
        function_ref="curator.comments.dispatch_comment_integration",
    ),
    "delete_orphaned_comments": ActionRisk(
        level="low",
        rationale="Parent artifact already removed",
        function_ref="curator.consistency_fixes.apply_orphaned_comments_delete",
    ),
    # ``fix_broken_wikilink_fuzzy`` and ``strip_unresolved_wikilink`` retired
    # in Phase 4 Family D of the ``curator-freshness`` change. Wikilink
    # repair now routes through the validator-side ``fix_wikilink_resolution``
    # fixer (registered below), which delegates to the archivist pipeline
    # to regenerate the design body from the source.
    "fix_wikilink_resolution": ActionRisk(
        level="low",
        rationale="Mechanical regeneration via archivist pipeline",
        function_ref="validator.fixes.fix_wikilink_resolution",
    ),
    # ``add_alias_fuzzy_match`` removed alongside the slug/alias retirement
    # in Phase 4 Family B of ``curator-freshness``. Its sole ``function_ref``
    # target was ``apply_alias_dedup``, which retired with
    # ``resolve_alias_collision``. No detector ever emitted the action, so
    # the entry was dead code.
    # Duplicate-slug / duplicate-alias routing added by Phase 4 Family B of
    # the ``curator-freshness`` change. Both fixers are propose-only — they
    # emit ``fixed=False`` with a "requires manual resolution" message
    # because resolving a slug/alias collision requires human judgement
    # (renaming or alias removal breaks existing wikilinks and external
    # references that the fixer cannot safely infer).
    "fix_duplicate_slugs": ActionRisk(
        level="low",
        rationale="Propose-only; surfaces collision for human resolution",
        function_ref="validator.fixes.fix_duplicate_slugs",
    ),
    "fix_duplicate_aliases": ActionRisk(
        level="low",
        rationale="Propose-only; surfaces collision for human resolution",
        function_ref="validator.fixes.fix_duplicate_aliases",
    ),
    # Consistency convention/playbook staleness flagging (Phase 3 — group 8).
    # ``consistency.py`` emits ``flag_stale_convention`` and
    # ``flag_stale_playbook`` from ``detect_stale_conventions`` /
    # ``detect_stale_playbooks``.  Both are Low risk because the fix helper
    # only writes a warning IWH signal next to the target file -- no
    # artifact mutation happens without human review.
    "flag_stale_convention": ActionRisk(
        level="low",
        rationale="Writes warning IWH signal only; no artifact mutation",
        function_ref="curator.consistency_fixes.apply_flag_stale_convention",
    ),
    "flag_stale_playbook": ActionRisk(
        level="low",
        rationale="Writes warning IWH signal only; no artifact mutation",
        function_ref="curator.consistency_fixes.apply_flag_stale_playbook",
    ),
    "autofix_validation_issue": ActionRisk(
        level="low",
        rationale="Pre-vetted fixes from validator registry",
        function_ref="curator.validation_fixers.fix_validation_issue",
    ),
    # --- Per-check validation bridge action keys (Phase 2) --------------
    # Each per-check key maps 1:1 to an entry in
    # ``lexibrary.validator.fixes.FIXERS``.  All route through the same
    # bridge function ``curator.validation_fixers.fix_validation_issue``.
    # Risk tier mirrors the destructiveness of the underlying fixer:
    # ``fix_orphaned_designs`` applies the deprecation workflow and so is
    # Medium; the rest are mechanical repairs and remain Low.
    "fix_hash_freshness": ActionRisk(
        level="low",
        rationale="Mechanical re-run of archivist pipeline",
        function_ref="curator.validation_fixers.fix_validation_issue",
    ),
    "fix_orphan_artifacts": ActionRisk(
        level="low",
        rationale="Source file already absent; deterministic cleanup",
        function_ref="curator.validation_fixers.fix_validation_issue",
    ),
    "fix_aindex_coverage": ActionRisk(
        level="low",
        rationale="Generates missing .aindex for uncovered directory",
        function_ref="curator.validation_fixers.fix_validation_issue",
    ),
    "fix_orphaned_aindex": ActionRisk(
        level="low",
        rationale="Removes .aindex whose source directory is gone",
        function_ref="curator.validation_fixers.fix_validation_issue",
    ),
    "fix_orphaned_iwh": ActionRisk(
        level="low",
        rationale="Removes .iwh whose source directory is gone",
        function_ref="curator.validation_fixers.fix_validation_issue",
    ),
    "fix_orphaned_designs": ActionRisk(
        level="medium",
        rationale="Applies deprecation workflow to orphan design files",
        function_ref="curator.validation_fixers.fix_validation_issue",
    ),
    "fix_deprecated_ttl": ActionRisk(
        level="low",
        rationale="Hard-deletes deprecated design files past TTL",
        function_ref="curator.validation_fixers.fix_validation_issue",
    ),
    "fix_bidirectional_deps": ActionRisk(
        level="low",
        rationale="Mechanical regeneration via archivist pipeline",
        function_ref="validator.fixes.fix_bidirectional_deps",
    ),
    "remove_orphan_zero_deps": ActionRisk(
        level="low",
        rationale="Nothing references it",
        function_ref="curator.consistency_fixes.apply_orphan_concept_delete",
    ),
    "add_missing_reverse_dep": ActionRisk(
        level="low",
        rationale="Mechanical cross-reference repair; adds existing dep as reverse entry",
        function_ref="curator.consistency_fixes.apply_add_reverse_dep",
    ),
    "consume_superseded_iwh": ActionRisk(
        level="low",
        rationale="Subsequent commits indicate completion",
        function_ref="curator.iwh_actions.consume_superseded_iwh",
    ),
    "write_reactive_iwh": ActionRisk(
        level="low",
        rationale="Directory-scoped coordination message",
        function_ref="curator.iwh_actions.write_reactive_iwh",
    ),
    "flag_unresolvable_agent_design": ActionRisk(
        level="low",
        rationale="Escalation only; no artifact modification",
        function_ref="curator.iwh_actions.flag_unresolvable_agent_design",
    ),
    # --- Medium-risk actions ---------------------------------------------
    "deprecate_design_file": ActionRisk(
        level="medium",
        rationale="Cascade may affect dependents",
        function_ref="curator.deprecation.dispatch_soft_deprecation",
    ),
    "reconcile_agent_interface_changed": ActionRisk(
        level="medium",
        rationale="LLM judges which agent notes still apply",
        function_ref="curator.reconciliation.dispatch_reconciliation",
    ),
    "suggest_new_concept": ActionRisk(
        level="medium",
        rationale="Proposes artifact creation; needs review",
        function_ref="curator.consistency_fixes.apply_suggest_new_concept",
    ),
    "promote_blocked_iwh": ActionRisk(
        level="medium",
        rationale=(
            "Overwrites blocked IWH with warning signal for human review; "
            "does not create Stack post"
        ),
        function_ref="curator.consistency_fixes.apply_promote_blocked_iwh",
    ),
    # --- Budget trimming actions (Phase 3) ---------------------------------
    "shorten_description": ActionRisk(
        level="low",
        rationale="Summary-level compression only",
        function_ref="curator.budget.dispatch_budget_condense",
    ),
    "propose_condensation": ActionRisk(
        level="medium",
        rationale="LLM suggests; human approves",
        function_ref="curator.budget.dispatch_budget_condense",
    ),
    "condense_file": ActionRisk(
        level="high",
        rationale="Lossy transformation; may remove needed detail",
        function_ref="curator.budget.dispatch_budget_condense",
    ),
    # --- Comment auditing actions (Phase 3) --------------------------------
    "flag_stale_comment": ActionRisk(
        level="medium",
        rationale="Requires understanding of original intent",
        function_ref="curator.auditing.dispatch_comment_audit",
    ),
    "audit_description": ActionRisk(
        level="medium",
        rationale="LLM judgment on clarity and accuracy",
        function_ref="curator.auditing.audit_description",
    ),
    "audit_summary": ActionRisk(
        level="medium",
        rationale="LLM must extract intent from source",
        function_ref="curator.auditing.audit_summary",
    ),
    # --- Deprecation lifecycle: low-risk actions ---------------------------
    "hard_delete_concept_past_ttl": ActionRisk(
        level="low",
        rationale="TTL expired and zero inbound references",
        function_ref="curator.lifecycle.dispatch_hard_delete",
    ),
    "hard_delete_convention_past_ttl": ActionRisk(
        level="low",
        rationale="TTL expired and zero inbound references",
        function_ref="curator.lifecycle.dispatch_hard_delete",
    ),
    "hard_delete_playbook_past_ttl": ActionRisk(
        level="low",
        rationale="TTL expired and zero inbound references",
        function_ref="curator.lifecycle.dispatch_hard_delete",
    ),
    "delete_comments_sidecar": ActionRisk(
        level="low",
        rationale="Parent artifact already deprecated or deleted",
        function_ref="curator.deprecation.dispatch_soft_deprecation",
    ),
    "concept_draft_to_active": ActionRisk(
        level="low",
        rationale="Promotion from draft; no existing content modified",
        function_ref="curator.lifecycle.execute_deprecation",
    ),
    "convention_draft_to_active": ActionRisk(
        level="low",
        rationale="Promotion from draft; no existing content modified",
        function_ref="curator.lifecycle.execute_deprecation",
    ),
    "playbook_draft_to_active": ActionRisk(
        level="low",
        rationale="Promotion from draft; no existing content modified",
        function_ref="curator.lifecycle.execute_deprecation",
    ),
    "stack_post_transition": ActionRisk(
        level="low",
        rationale="Lifecycle state change on resolved or stale post",
        function_ref="curator.lifecycle.dispatch_stack_transition",
    ),
    # --- Deprecation lifecycle: medium-risk actions ----------------------
    "deprecate_convention": ActionRisk(
        level="medium",
        rationale="Cascade may affect convention consumers",
        function_ref="curator.deprecation.dispatch_soft_deprecation",
    ),
    "deprecate_playbook": ActionRisk(
        level="medium",
        rationale="Cascade may affect playbook consumers",
        function_ref="curator.deprecation.dispatch_soft_deprecation",
    ),
    "apply_migration_edits": ActionRisk(
        level="medium",
        rationale="Modifies dependent artifacts post-deprecation",
        function_ref="curator.migration.apply_migration_edits",
    ),
    # --- High-risk actions -----------------------------------------------
    "reconcile_agent_extensive_content": ActionRisk(
        level="high",
        rationale="Lossy merge possible; agent insights at risk",
        function_ref="curator.reconciliation.dispatch_reconciliation",
    ),
    "deprecate_concept": ActionRisk(
        level="high",
        rationale="Concepts are high-value knowledge; cascade may be extensive",
        function_ref="curator.deprecation.dispatch_soft_deprecation",
    ),
}


def get_risk_level(
    action_key: str,
    overrides: Mapping[str, str],
) -> str:
    """Return the effective risk level for *action_key*.

    Checks *overrides* first (user-configured per-key risk-level tweaks),
    then falls back to the canonical ``RISK_TAXONOMY``.

    If *action_key* is not in *overrides* and also not in
    ``RISK_TAXONOMY`` (for example, a stale user override referencing a
    removed action), logs a warning and returns ``"low"`` as a safe
    default rather than raising.
    """
    if action_key in overrides:
        return overrides[action_key]
    if action_key not in RISK_TAXONOMY:
        logging.getLogger(__name__).warning(
            "Ignoring unrecognized action key in risk_overrides: %r", action_key
        )
        return "low"  # safe default for unknown keys
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
    overrides: Mapping[str, str],
    *,
    confirmation_overrides: Mapping[str, bool] | None = None,
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
