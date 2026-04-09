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
    deprecation: CuratorDeprecationConfig = Field(default_factory=CuratorDeprecationConfig)

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
