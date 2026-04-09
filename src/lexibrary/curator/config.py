"""Curator configuration model."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CuratorConfig(BaseModel):
    """Configuration for the automated curator subsystem.

    Controls autonomy level, LLM call budgets, and per-action risk overrides
    for the curator's collect-triage-dispatch-report pipeline.
    """

    model_config = ConfigDict(extra="ignore")

    autonomy: Literal["auto_low", "full", "propose"] = "auto_low"
    max_llm_calls_per_run: int = Field(default=50, ge=1)
    risk_overrides: dict[str, Literal["low", "medium", "high"]] = Field(default_factory=dict)
