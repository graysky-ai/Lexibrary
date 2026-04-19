"""Tests for the escalation schema introduced by curator-4 Phase 6 (Group 14).

Covers:

* ``PendingDecision`` Pydantic model shape and round-trip semantics.
* ``CuratorReport.pending_decisions`` default is an empty list.
* ``CuratorReport.schema_version`` is bumped to ``4``.
* ``SubAgentResult.outcome`` Literal accepts ``"escalation_required"``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from lexibrary.curator.models import (
    CuratorReport,
    PendingDecision,
    SubAgentResult,
)

# ---------------------------------------------------------------------------
# PendingDecision model shape
# ---------------------------------------------------------------------------


class TestPendingDecisionModel:
    """``PendingDecision`` is a Pydantic model with the spec-mandated fields."""

    def test_minimal_construction(self) -> None:
        """Required fields are ``check``, ``path``, ``message``, ``suggested_actions``."""
        decision = PendingDecision(
            check="orphan_concepts",
            path=Path(".lexibrary/designs/foo.md"),
            message="concept has zero inbound link-graph references",
            suggested_actions=["ignore", "deprecate", "refresh"],
        )

        assert decision.check == "orphan_concepts"
        assert decision.path == Path(".lexibrary/designs/foo.md")
        assert decision.message == "concept has zero inbound link-graph references"
        assert decision.suggested_actions == ["ignore", "deprecate", "refresh"]
        # iwh_path defaults to None when the decision came from an interactive run.
        assert decision.iwh_path is None

    def test_with_iwh_path(self) -> None:
        """``iwh_path`` carries the path written in autonomous mode."""
        iwh = Path(".lexibrary/designs/foo.iwh")
        decision = PendingDecision(
            check="stale_concept",
            path=Path(".lexibrary/designs/foo.md"),
            message="3 linked_files entries missing",
            suggested_actions=["ignore", "deprecate", "refresh"],
            iwh_path=iwh,
        )

        assert decision.iwh_path == iwh

    def test_suggested_actions_rejects_unknown_literal(self) -> None:
        """Only ``ignore`` / ``deprecate`` / ``refresh`` are permitted."""
        with pytest.raises(ValidationError):
            PendingDecision(
                check="orphan_concepts",
                path=Path(".lexibrary/designs/foo.md"),
                message="m",
                suggested_actions=["bogus"],  # type: ignore[list-item]
            )

    def test_round_trip_to_from_json(self) -> None:
        """``model_dump_json`` + ``model_validate_json`` preserves data."""
        decision = PendingDecision(
            check="convention_stale",
            path=Path(".lexibrary/conventions/scope/foo.md"),
            message="scope path missing: src/removed/",
            suggested_actions=["ignore", "deprecate", "refresh"],
            iwh_path=Path(".lexibrary/conventions/scope/foo.iwh"),
        )

        payload = decision.model_dump_json()
        restored = PendingDecision.model_validate_json(payload)

        assert restored.check == decision.check
        assert restored.path == decision.path
        assert restored.message == decision.message
        assert restored.suggested_actions == decision.suggested_actions
        assert restored.iwh_path == decision.iwh_path

    def test_round_trip_without_iwh_path(self) -> None:
        """Absent ``iwh_path`` survives JSON round-trip as ``None``."""
        decision = PendingDecision(
            check="playbook_staleness",
            path=Path(".lexibrary/playbooks/foo.md"),
            message="past last_verified window",
            suggested_actions=["ignore", "deprecate", "refresh"],
        )

        payload = decision.model_dump_json()
        restored = PendingDecision.model_validate_json(payload)

        assert restored.iwh_path is None


# ---------------------------------------------------------------------------
# CuratorReport schema v4
# ---------------------------------------------------------------------------


class TestCuratorReportSchemaVersion:
    """Schema version is bumped from 3 to 4."""

    def test_default_schema_version_is_four(self) -> None:
        """Default ``schema_version`` on a bare ``CuratorReport`` is ``4``."""
        report = CuratorReport()

        assert report.schema_version == 4

    def test_pending_decisions_defaults_to_empty_list(self) -> None:
        """``pending_decisions`` default is an empty list, per the spec."""
        report = CuratorReport()

        assert report.pending_decisions == []
        # New dataclass instances do not share the same list object.
        assert report.pending_decisions is not CuratorReport().pending_decisions

    def test_pending_decisions_accepts_decisions(self) -> None:
        """The field accepts a list of ``PendingDecision`` instances."""
        decision = PendingDecision(
            check="orphan_concepts",
            path=Path(".lexibrary/designs/foo.md"),
            message="m",
            suggested_actions=["ignore", "deprecate", "refresh"],
        )

        report = CuratorReport(pending_decisions=[decision])

        assert len(report.pending_decisions) == 1
        assert report.pending_decisions[0].check == "orphan_concepts"


# ---------------------------------------------------------------------------
# SubAgentResult.outcome Literal
# ---------------------------------------------------------------------------


class TestSubAgentResultEscalationOutcome:
    """``outcome`` Literal now includes ``"escalation_required"``."""

    def test_escalation_required_accepted(self) -> None:
        """Constructing with ``outcome="escalation_required"`` is valid."""
        result = SubAgentResult(
            success=False,
            action_key="escalate_orphan_concepts",
            path=Path(".lexibrary/designs/foo.md"),
            message="escalation queued: orphan_concepts (foo.md)",
            llm_calls=0,
            outcome="escalation_required",
        )

        assert result.outcome == "escalation_required"
        assert result.success is False
        # llm_calls remains 0 for escalation fixers (no LLM call).
        assert result.llm_calls == 0

    def test_existing_outcomes_still_accepted(self) -> None:
        """Legacy outcomes (`fixed`, `fixer_failed`, `no_fixer`) still work."""
        fixed = SubAgentResult(success=True, action_key="a", outcome="fixed")
        failed = SubAgentResult(success=False, action_key="a", outcome="fixer_failed")
        nofixer = SubAgentResult(success=False, action_key="a", outcome="no_fixer")

        assert fixed.outcome == "fixed"
        assert failed.outcome == "fixer_failed"
        assert nofixer.outcome == "no_fixer"
