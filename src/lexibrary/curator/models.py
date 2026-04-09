"""Data models for the curator coordinator pipeline.

Defines the typed results exchanged between the four coordinator phases
(collect, triage, dispatch, report) and the sub-agent stubs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

# ---------------------------------------------------------------------------
# Collect phase
# ---------------------------------------------------------------------------


@dataclass
class CollectItem:
    """A single signal discovered during the collect phase."""

    source: Literal["validation", "staleness", "iwh", "agent_edit", "deprecation"]
    path: Path | None
    severity: Literal["error", "warning", "info"]
    message: str
    check: str = ""
    # Staleness-specific metadata
    source_hash_stale: bool = False
    interface_hash_stale: bool = False
    updated_by: str = ""
    # Agent-edit detection metadata
    agent_edit_reason: str = ""
    design_body_length: int = 0


@dataclass
class CommentCollectItem:
    """A design file with unprocessed sidecar comments."""

    design_path: Path
    source_path: Path
    comment_count: int
    comments_path: Path


@dataclass
class DeprecationCollectItem:
    """A deprecation candidate discovered during the collect phase."""

    artifact_path: Path
    artifact_kind: Literal["concept", "convention", "design_file", "playbook", "stack_post"]
    current_status: str
    reason: str
    commits_since_deprecation: int = 0
    reverse_dep_count: int = 0


@dataclass
class BudgetCollectItem:
    """A knowledge-layer file that exceeds its token budget.

    Wraps a ``BudgetIssue`` from the budget sub-agent for coordinator use.
    """

    path: Path
    current_tokens: int
    budget_target: int
    file_type: str  # "design_file", "start_here", or "handoff"


@dataclass
class CommentAuditCollectItem:
    """A TODO/FIXME/HACK marker found in a source file.

    Wraps a ``CommentAuditIssue`` from the auditing sub-agent for coordinator use.
    """

    path: Path
    line_number: int
    comment_text: str
    code_context: str
    marker_type: str  # "TODO", "FIXME", or "HACK"


@dataclass
class CollectResult:
    """Aggregated output of the collect phase."""

    items: list[CollectItem] = field(default_factory=list)
    comment_items: list[CommentCollectItem] = field(default_factory=list)
    deprecation_items: list[DeprecationCollectItem] = field(default_factory=list)
    budget_items: list[BudgetCollectItem] = field(default_factory=list)
    comment_audit_items: list[CommentAuditCollectItem] = field(default_factory=list)
    link_graph_available: bool = False
    validation_error: str | None = None


# ---------------------------------------------------------------------------
# Triage phase
# ---------------------------------------------------------------------------


@dataclass
class TriageItem:
    """A collected item enriched with classification and priority."""

    source_item: CollectItem
    issue_type: Literal[
        "staleness",
        "consistency",
        "comment",
        "orphan",
        "reconciliation",
        "deprecation",
        "budget",
        "comment_audit",
        "description_audit",
        "summary_audit",
    ]
    action_key: str
    priority: float = 0.0
    agent_edited: bool = False
    reverse_dep_count: int = 0
    comment_item: CommentCollectItem | None = None
    deprecation_item: DeprecationCollectItem | None = None
    budget_item: BudgetCollectItem | None = None
    comment_audit_item: CommentAuditCollectItem | None = None
    risk_level: Literal["low", "medium", "high"] | None = None


@dataclass
class TriageResult:
    """Sorted list of triaged items ready for dispatch."""

    items: list[TriageItem] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Dispatch phase
# ---------------------------------------------------------------------------


@dataclass
class SubAgentResult:
    """Result returned by a sub-agent stub (or real BAML call later)."""

    success: bool
    action_key: str
    path: Path | None = None
    message: str = ""
    llm_calls: int = 0


@dataclass
class DispatchResult:
    """Aggregated output of the dispatch phase."""

    dispatched: list[SubAgentResult] = field(default_factory=list)
    deferred: list[TriageItem] = field(default_factory=list)
    llm_calls_used: int = 0
    llm_cap_reached: bool = False


# ---------------------------------------------------------------------------
# Report phase
# ---------------------------------------------------------------------------


@dataclass
class CuratorReport:
    """Final report summarising a curator run."""

    checked: int = 0
    fixed: int = 0
    deferred: int = 0
    errored: int = 0
    errors: list[dict[str, str]] = field(default_factory=list)
    sub_agent_calls: dict[str, int] = field(default_factory=dict)
    report_path: Path | None = None
    # Deprecation / migration counters (Phase 2)
    deprecated: int = 0
    hard_deleted: int = 0
    migrations_applied: int = 0
    migrations_proposed: int = 0
    # Phase 3: Budget trimming and comment auditing counters
    budget_condensed: int = 0
    budget_proposed: int = 0
    comments_flagged: int = 0
    descriptions_audited: int = 0
    summaries_audited: int = 0
    trigger: Literal[
        "on_demand",
        "reactive_post_edit",
        "reactive_post_bead_close",
        "reactive_validation_failure",
        "scheduled",
    ] = "on_demand"
