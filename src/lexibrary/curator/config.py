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

# All action keys recognised by the risk taxonomy (Phase 1 + Phase 2).
# Populated lazily by _known_action_keys() to avoid circular imports.
_KNOWN_KEYS_CACHE: frozenset[str] | None = None


def _known_action_keys() -> frozenset[str]:
    """Return the union of taxonomy keys and deprecation action keys.

    Imports ``RISK_TAXONOMY`` lazily to avoid circular-import issues
    (risk_taxonomy imports nothing from config, but they sit in the same
    package).
    """
    global _KNOWN_KEYS_CACHE  # noqa: PLW0603
    if _KNOWN_KEYS_CACHE is None:
        try:
            from lexibrary.curator.risk_taxonomy import RISK_TAXONOMY

            _KNOWN_KEYS_CACHE = frozenset(RISK_TAXONOMY) | DEPRECATION_ACTION_KEYS
        except ImportError:
            # Taxonomy module not yet available — fall back to deprecation keys only.
            _KNOWN_KEYS_CACHE = DEPRECATION_ACTION_KEYS
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
