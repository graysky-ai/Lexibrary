"""Curator configuration model."""

from __future__ import annotations

import logging
import warnings
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

logger = logging.getLogger(__name__)

# Action keys recognised by the deprecation workflow.  Used by the
# ``risk_overrides`` validator to distinguish known keys from unknown ones.
DEPRECATION_ACTION_KEYS: frozenset[str] = frozenset(
    {
        "deprecate_concept",
        "deprecate_convention",
        "deprecate_playbook",
        "deprecate_design_file",
        "hard_delete_concept_past_ttl",
        "hard_delete_convention_past_ttl",
        "hard_delete_playbook_past_ttl",
        "delete_comments_sidecar",
        "apply_migration_edits",
        "concept_draft_to_active",
        "convention_draft_to_active",
        "playbook_draft_to_active",
        "stack_post_transition",
    }
)

# Narrow family action keys introduced by the ``curator-freshness`` change.
# Each key is the validator-side fixer that replaces one or more retired
# curator-side consistency action keys (see SHARED_BLOCK_A in
# ``openspec/changes/curator-freshness/tasks.md``).
#
# Pre-seeded here so that configs referencing these keys do not trigger the
# unknown-key warning before the matching ``ActionRisk`` entries land in
# ``RISK_TAXONOMY`` (they arrive incrementally across groups 4, 6, 7, 8, 9).
# As curator-side action keys retire (e.g. group 3.8 retired
# ``add_missing_bidirectional_dep`` and ``remove_orphaned_reverse_dep`` when
# their taxonomy entries were deleted), they drop out of the known set
# automatically because the known set is derived from ``RISK_TAXONOMY``.
NEW_FAMILY_ACTION_KEYS: frozenset[str] = frozenset(
    {
        "fix_bidirectional_deps",
        "fix_orphaned_aindex",
        "fix_duplicate_slugs",
        "fix_duplicate_aliases",
        "fix_orphan_concepts",
        "fix_wikilink_resolution",
    }
)

# All action keys recognised by the risk taxonomy (Phase 1 + Phase 2).
# Populated lazily by _known_action_keys() to avoid circular imports.
_KNOWN_KEYS_CACHE: frozenset[str] | None = None


def _known_action_keys() -> frozenset[str]:
    """Return the union of taxonomy keys, deprecation keys, and new family keys.

    Imports ``RISK_TAXONOMY`` lazily to avoid circular-import issues
    (risk_taxonomy imports nothing from config, but they sit in the same
    package).
    """
    global _KNOWN_KEYS_CACHE  # noqa: PLW0603
    if _KNOWN_KEYS_CACHE is None:
        try:
            from lexibrary.curator.risk_taxonomy import RISK_TAXONOMY

            _KNOWN_KEYS_CACHE = (
                frozenset(RISK_TAXONOMY)
                | DEPRECATION_ACTION_KEYS
                | NEW_FAMILY_ACTION_KEYS
            )
        except ImportError:
            # Taxonomy module not yet available — fall back to deprecation +
            # new family keys only.
            _KNOWN_KEYS_CACHE = DEPRECATION_ACTION_KEYS | NEW_FAMILY_ACTION_KEYS
    return _KNOWN_KEYS_CACHE


class BudgetTokenLimits(BaseModel):
    """Per-file-type token budgets for the Budget Trimmer sub-agent."""

    model_config = ConfigDict(extra="ignore")

    design_file: int = Field(default=4000, ge=100)
    start_here: int = Field(default=3000, ge=100)
    handoff: int = Field(default=2000, ge=100)


class BudgetConfig(BaseModel):
    """Configuration for the Budget Trimmer sub-agent."""

    model_config = ConfigDict(extra="ignore")

    token_limits: BudgetTokenLimits = Field(default_factory=BudgetTokenLimits)


class AuditingConfig(BaseModel):
    """Configuration for the Comment Auditing sub-agent."""

    model_config = ConfigDict(extra="ignore")

    quality_threshold: float = Field(default=0.7, ge=0.0, le=1.0)


class ReactiveConfig(BaseModel):
    """Configuration for reactive hooks (post-edit, post-bead-close, validation-failure)."""

    model_config = ConfigDict(extra="ignore")

    enabled: bool = False
    post_edit: bool = True
    post_bead_close: bool = True
    validation_failure: bool = True
    severity_threshold: Literal["error", "warning", "critical"] = "error"


class CuratorDeprecationConfig(BaseModel):
    """Deprecation-specific settings nested under ``curator.deprecation``."""

    model_config = ConfigDict(extra="ignore")

    ttl_commits: int = Field(default=50, ge=1)


class CuratorConfig(BaseModel):
    """Configuration for the automated curator subsystem.

    Controls autonomy level, LLM call budgets, and per-action risk overrides
    for the curator's collect-triage-dispatch-report pipeline.
    """

    model_config = ConfigDict(extra="ignore")

    autonomy: Literal["auto_low", "full", "propose"] = "auto_low"
    max_llm_calls_per_run: int = Field(default=50, ge=1)
    risk_overrides: dict[str, Literal["low", "medium", "high"]] = Field(default_factory=dict)
    # Consistency collection scope (Phase 3 — group 8).
    # Controls which subset of :class:`ConsistencyChecker` checks run during
    # ``_collect_consistency``.  ``"off"`` disables all consistency checks,
    # ``"scope"`` runs the scope-bounded checks (wikilink hygiene,
    # slug/alias collisions, bidirectional deps, orphaned .aindex, orphaned
    # .comments.yaml, stale conventions/playbooks, and promotable blocked
    # IWH), and ``"full"`` additionally runs the library-wide checks
    # (domain term detection, orphan concept detection).
    consistency_collect: Literal["off", "scope", "full"] = "scope"
    # Post-sweep verification (Phase 5 — group 10).  When ``True``, the
    # coordinator re-runs ``validate_library()`` after the dispatch phase
    # and records a ``verification: {before, after, delta}`` block in the
    # persisted JSON report.  This is strictly an observability toggle —
    # it does NOT affect which fixes run, only whether a second validation
    # pass is performed to measure the sweep's effect.
    verify_after_sweep: bool = False
    # Phase 0 prepare-step refresh (``curator-freshness`` change, group 1).
    # When ``True``, the coordinator's ``_prepare_indexes()`` step runs
    # before ``_collect`` to refresh the symbol graph and link graph for
    # any drifted sources (the "prepare" invariant that lets collect steps
    # assume index freshness).  When ``False``, the prepare step is skipped
    # AND — per SHARED_BLOCK_B in ``openspec/changes/curator-freshness`` —
    # the reactive-hook bootstrap also short-circuits, keeping the
    # "opt-out of prepare = opt-out of bootstrap" invariant uniform.
    # Opt-out for large libraries where the warm-cache cost is unacceptable;
    # callers are then responsible for running ``lexictl update`` on their
    # own cadence.
    prepare_indexes: bool = Field(
        default=True,
        description=(
            "When True, run _prepare_indexes() before _collect to refresh "
            "symbol/link graphs for drifted sources. Setting False is an "
            "opt-out for large libraries; it also disables the reactive-hook "
            "bootstrap so the 'opt-out of prepare = opt-out of bootstrap' "
            "invariant stays uniform."
        ),
    )
    # Phase 0b reactive-hook LLM regeneration gate
    # (``curator-freshness`` change, group 2).  Gates ONLY the LLM step of
    # the reactive-hook bootstrap — i.e. whether ``archivist.pipeline.update_file``
    # runs after the always-on index refresh.  When ``False`` (default), the
    # hook still refreshes symbol + link graphs but does NOT call the
    # archivist LLM, even if the source hash has drifted.  When ``True``,
    # ``update_file`` runs and the call counts against
    # ``max_llm_calls_per_run``.  Gated independently of ``prepare_indexes``
    # because the cost/latency profile of LLM regeneration is very different
    # from cheap graph refreshes; many users want fresh indexes on every
    # edit but only occasional LLM rewrites.
    reactive_bootstrap_regenerate: bool = Field(
        default=False,
        description=(
            "When True, the reactive-hook bootstrap invokes archivist.pipeline."
            "update_file after the index refresh, consuming from "
            "max_llm_calls_per_run. Defaults off because LLM regeneration on "
            "every edit is expensive; opt in only when you want aggressive "
            "design-file refresh on save."
        ),
    )
    # Phase 2 two-pass collect restructure (``curator-freshness`` change,
    # group 5).  When ``True`` (default), the coordinator runs the two-pass
    # ``_collect_hash_layer`` / ``_collect_graph_layer`` flow with a 70/30
    # budget split between passes.  When ``False``, the coordinator runs
    # the legacy single-pass ``_collect``.  Provided as a kill-switch for
    # the rollout; to be removed one release after two-pass collect is
    # confirmed stable.
    two_pass_collect: bool = Field(
        default=True,
        description=(
            "When True, run the two-pass hash/graph collect flow with 70/30 "
            "budget split. When False, fall back to the legacy single-pass "
            "_collect. Kill-switch for rollout; will be removed after one "
            "release."
        ),
    )
    deprecation: CuratorDeprecationConfig = Field(default_factory=CuratorDeprecationConfig)
    budget: BudgetConfig = Field(default_factory=BudgetConfig)
    auditing: AuditingConfig = Field(default_factory=AuditingConfig)
    reactive: ReactiveConfig = Field(default_factory=ReactiveConfig)

    @model_validator(mode="after")
    def _warn_unknown_risk_overrides(self) -> CuratorConfig:
        """Emit a warning for risk_overrides keys not in the known set."""
        known = _known_action_keys()
        for key in self.risk_overrides:
            if key not in known:
                warnings.warn(
                    f"Unknown risk_overrides key: {key!r}. "
                    "It will be accepted but may not match any curator action.",
                    UserWarning,
                    stacklevel=2,
                )
        return self
