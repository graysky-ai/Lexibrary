"""Tests for the ``FIXERS`` registry entries wired by curator-4 group 16.

These tests pin the association between escalation-routed checks and the
``escalate_*`` fixer family. If any of the four escalation entries is
removed or rebound to a different callable, these tests fail loudly
instead of the coordinator silently falling back to ``no_fixer_registered``
for a check that should now be escalated.
"""

from __future__ import annotations

from lexibrary.validator.fixes import (
    ESCALATION_CHECKS,
    FIXERS,
    escalate_convention_stale,
    escalate_orphan_concepts,
    escalate_playbook_staleness,
    escalate_stale_concept,
)


class TestEscalationFixersRegistered:
    """The four escalation checks must be wired to their ``escalate_*`` fixers."""

    def test_orphan_concepts_registered(self) -> None:
        assert "orphan_concepts" in FIXERS
        assert FIXERS["orphan_concepts"] is escalate_orphan_concepts

    def test_stale_concept_registered(self) -> None:
        assert "stale_concept" in FIXERS
        assert FIXERS["stale_concept"] is escalate_stale_concept

    def test_convention_stale_registered(self) -> None:
        assert "convention_stale" in FIXERS
        assert FIXERS["convention_stale"] is escalate_convention_stale

    def test_playbook_staleness_registered(self) -> None:
        assert "playbook_staleness" in FIXERS
        assert FIXERS["playbook_staleness"] is escalate_playbook_staleness

    def test_each_escalation_key_maps_to_an_escalate_callable(self) -> None:
        """Every key in ``ESCALATION_CHECKS`` resolves to a callable whose
        ``__name__`` starts with ``escalate_``. Guards against future
        accidental rebinding to a mutating fixer.
        """
        for check in ESCALATION_CHECKS:
            assert check in FIXERS, f"escalation check {check!r} missing from FIXERS"
            fixer = FIXERS[check]
            assert callable(fixer)
            assert fixer.__name__.startswith("escalate_"), (
                f"FIXERS[{check!r}] is {fixer.__name__}; expected an escalate_* callable"
            )


class TestEscalationChecksFrozenset:
    """``ESCALATION_CHECKS`` must pin the exact four escalation checks."""

    def test_escalation_checks_exact_membership(self) -> None:
        expected = frozenset(
            {
                "orphan_concepts",
                "stale_concept",
                "convention_stale",
                "playbook_staleness",
            }
        )
        # Compare as sets of equal cardinality AND identical membership —
        # avoids Yoda-condition lint (SIM300) while still pinning the exact
        # contents and size of ``ESCALATION_CHECKS``.
        assert expected <= ESCALATION_CHECKS
        assert expected >= ESCALATION_CHECKS
        assert len(ESCALATION_CHECKS) == len(expected)
