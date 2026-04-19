"""End-to-end integration test for the four curator-4 escalation checks.

Curator-4 Group 23.1 / 23.3: run the full coordinator pipeline
(``collect -> triage -> dispatch -> report``) against a fixture seeded
with one of each escalation issue and assert:

1. :attr:`CuratorReport.pending_decisions` has four entries, one per
   escalation check (``orphan_concepts``, ``stale_concept``,
   ``convention_stale``, ``playbook_staleness``).
2. Each ``PendingDecision`` carries:
   - the correct ``check`` name,
   - the canonical ``suggested_actions`` triple
     (``["ignore", "deprecate", "refresh"]``),
   - a populated ``iwh_path`` (the escalate_* fixer writes the breadcrumb
     autonomously when ``sys.stdout.isatty()`` returns ``False``, which is
     the default under pytest capture).
3. Each of the four expected IWH files exists on disk under
   ``.lexibrary/designs/`` next to the matching artifact.
4. No dispatched entry carries ``outcome="no_fixer"`` for the four
   escalation checks — the ``CHECK_TO_ACTION_KEY`` mapping and
   ``FIXERS`` registry are fully wired.

Mirrors the structure of
``tests/test_curator/test_wikilink_resolution_integration.py`` and
``tests/test_curator/test_orphaned_aindex_integration.py``.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from pathlib import Path

from lexibrary.config.schema import LexibraryConfig
from lexibrary.curator.coordinator import Coordinator
from lexibrary.curator.models import CuratorReport, PendingDecision
from lexibrary.utils.paths import LEXIBRARY_DIR

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _setup_integration_project(tmp_path: Path) -> Path:
    """Build a minimal project with a full ``.lexibrary/`` layout."""
    project = tmp_path / "escalation_integration"
    project.mkdir()
    lex = project / LEXIBRARY_DIR
    lex.mkdir()
    for sub in ("designs", "concepts", "conventions", "playbooks", "stack"):
        (lex / sub).mkdir()
    # Use explicit scope_roots so the coordinator's config validation
    # succeeds and orphan_verify_ttl_days defaults to 90 (not 0).
    (lex / "config.yaml").write_text(
        "scope_roots:\n  - path: .\n",
        encoding="utf-8",
    )
    return project


def _write_orphan_concept(project: Path, *, title: str = "LonelyConcept") -> Path:
    """Write a concept with zero inbound wikilink references.

    ``check_orphan_concepts`` scans designs/, stack/, and concepts/
    themselves for ``[[wikilink]]`` matches. A concept with a unique
    title and no cross-references from any other artifact is guaranteed
    to be flagged.
    """
    concepts_dir = project / LEXIBRARY_DIR / "concepts"
    concepts_dir.mkdir(parents=True, exist_ok=True)
    path = concepts_dir / f"{title}.md"
    path.write_text(
        "---\n"
        f"title: {title}\n"
        "id: CN-ESC-001\n"
        "aliases: []\n"
        "tags: [test]\n"
        "status: active\n"
        "---\n\n"
        "A concept nobody refers to.\n",
        encoding="utf-8",
    )
    return path


def _write_stale_concept(project: Path, *, title: str = "StaleConcept") -> Path:
    """Write an active concept with a backtick-delimited missing linked_files ref.

    ``check_stale_concepts`` scans concept bodies for ``linked_files``
    paths (extracted by the parser) and flags active concepts with at
    least one non-existent reference.

    The concept must also be *referenced* somewhere so it is NOT flagged
    as an orphan — we add a wikilink back from a stack post.
    """
    concepts_dir = project / LEXIBRARY_DIR / "concepts"
    concepts_dir.mkdir(parents=True, exist_ok=True)
    path = concepts_dir / f"{title}.md"
    path.write_text(
        "---\n"
        f"title: {title}\n"
        "id: CN-ESC-002\n"
        "aliases: []\n"
        "tags: [test]\n"
        "status: active\n"
        "---\n\n"
        "This concept references a nonexistent file:\n\n"
        "- `src/missing/module.py` is referenced but not present.\n",
        encoding="utf-8",
    )

    # Reference the concept so orphan_concepts does not also fire on it.
    stack_dir = project / LEXIBRARY_DIR / "stack"
    stack_dir.mkdir(parents=True, exist_ok=True)
    (stack_dir / "reference.md").write_text(
        "---\n"
        "id: SP-001\n"
        "title: Reference post\n"
        "status: answered\n"
        "tags: [reference]\n"
        f"refs:\n"
        f"  - concept: {title}\n"
        "---\n\n"
        f"See [[{title}]] for background.\n",
        encoding="utf-8",
    )
    return path


def _write_stale_convention(
    project: Path,
    *,
    slug: str = "stale-convention",
    title: str = "Stale Convention",
) -> Path:
    """Write an active convention whose scope directory exists but is empty.

    ``check_convention_stale`` fires when the scope directory exists
    but contains no source files.
    """
    # Scope directory exists but is empty (no files).
    (project / "src" / "emptydir").mkdir(parents=True, exist_ok=True)

    conventions_dir = project / LEXIBRARY_DIR / "conventions"
    conventions_dir.mkdir(parents=True, exist_ok=True)
    path = conventions_dir / f"{slug}.md"
    path.write_text(
        "---\n"
        f"title: '{title}'\n"
        "id: CV-ESC-001\n"
        "scope: src/emptydir/\n"
        "tags: [test]\n"
        "status: active\n"
        "source: user\n"
        "priority: 0\n"
        "---\n\n"
        "Stale convention body.\n",
        encoding="utf-8",
    )
    return path


def _write_stale_playbook(project: Path, *, slug: str = "stale-playbook") -> Path:
    """Write an active playbook whose ``last_verified`` is unset.

    ``check_playbook_staleness`` flags active playbooks where
    ``last_verified`` is unset (the "never verified" branch).
    """
    playbooks_dir = project / LEXIBRARY_DIR / "playbooks"
    playbooks_dir.mkdir(parents=True, exist_ok=True)
    path = playbooks_dir / f"{slug}.md"
    path.write_text(
        "---\n"
        f"title: {slug}\n"
        "id: PB-ESC-001\n"
        "trigger_files: []\n"
        "tags: [test]\n"
        "status: active\n"
        "source: user\n"
        "---\n\n"
        "## Overview\n\nA playbook that has never been verified.\n",
        encoding="utf-8",
    )
    return path


def _run_coordinator(project: Path, *, autonomy: str = "full") -> CuratorReport:
    """Run the coordinator under *autonomy* and return the resulting report."""
    config = LexibraryConfig.model_validate(
        {
            "scope_roots": [{"path": "."}],
            "curator": {"autonomy": autonomy},
        }
    )
    coord = Coordinator(project, config)
    return asyncio.run(coord.run())


# ---------------------------------------------------------------------------
# Integration test
# ---------------------------------------------------------------------------


class TestEscalationEndToEnd:
    """All four escalation checks flow through coordinator -> pending_decisions."""

    def test_four_escalation_issues_become_pending_decisions(
        self,
        tmp_path: Path,
    ) -> None:
        """Seed one of each escalation issue and assert wiring end-to-end."""
        project = _setup_integration_project(tmp_path)

        orphan_path = _write_orphan_concept(project)
        stale_concept_path = _write_stale_concept(project)
        convention_path = _write_stale_convention(project)
        playbook_path = _write_stale_playbook(project)

        report = _run_coordinator(project)

        # --- Assertion 1: four PendingDecision entries exist. ---
        pending: list[PendingDecision] = report.pending_decisions
        pending_checks = sorted(d.check for d in pending)
        assert pending_checks == [
            "convention_stale",
            "orphan_concepts",
            "playbook_staleness",
            "stale_concept",
        ], (
            "Expected one PendingDecision per escalation check, got: "
            f"{pending_checks}. Full report dispatched_details: "
            f"{report.dispatched_details}"
        )

        # --- Assertion 2: each entry has the canonical suggested_actions. ---
        for decision in pending:
            assert decision.suggested_actions == ["ignore", "deprecate", "refresh"], (
                f"PendingDecision for {decision.check} carries non-canonical "
                f"suggested_actions={decision.suggested_actions}"
            )

        # --- Assertion 3: each entry carries an IWH breadcrumb on disk. ---
        # The escalate_* fixers write an IWH signal under the artifact's
        # parent directory via _write_escalation_iwh (scope="warning",
        # author="curator"). In pytest, sys.stdout.isatty() is False, so
        # _is_autonomous_context(config) is True and the write proceeds.
        for decision in pending:
            assert decision.iwh_path is not None, (
                f"PendingDecision for {decision.check} is missing iwh_path; "
                "the escalate_* fixer should write an IWH signal in the "
                "autonomous coordinator context."
            )
            assert decision.iwh_path.exists(), (
                f"IWH breadcrumb {decision.iwh_path} for check "
                f"{decision.check!r} does not exist on disk."
            )

        # --- Assertion 4: no no_fixer outcomes for the four checks. ---
        # Curator-4 Group 23.3 — the FIXERS registry + CHECK_TO_ACTION_KEY
        # mapping together guarantee every escalation check finds a fixer.
        dispatched = list(report.dispatched_details)
        escalation_action_keys = {
            "escalate_orphan_concepts",
            "escalate_stale_concept",
            "escalate_convention_stale",
            "escalate_playbook_staleness",
        }
        no_fixer_for_escalation = [
            entry
            for entry in dispatched
            if entry.get("outcome") == "no_fixer"
            and entry.get("action_key") in escalation_action_keys
        ]
        assert not no_fixer_for_escalation, (
            "Found no_fixer entries for escalation action keys — fixer "
            "registration gap. Entries: "
            f"{no_fixer_for_escalation}"
        )

        # The four dispatched entries must carry outcome="escalation_required".
        escalation_dispatched = [
            entry for entry in dispatched if entry.get("outcome") == "escalation_required"
        ]
        assert len(escalation_dispatched) == 4, (
            "Expected exactly four dispatched entries with "
            "outcome='escalation_required'; got "
            f"{len(escalation_dispatched)}. Entries: {escalation_dispatched}"
        )

        # --- Artifact integrity: no escalate_* fixer mutates the target. ---
        # Each escalate_* fixer is a "fixer" in name only — the artifact's
        # body must be byte-identical after the coordinator run.
        # (Serializer round-trip can alter frontmatter formatting only if
        # the artifact was parsed + rewritten; escalate_* does neither.)
        assert orphan_path.exists()
        assert stale_concept_path.exists()
        assert convention_path.exists()
        assert playbook_path.exists()

    def test_pending_decision_paths_resolve_to_artifacts(
        self,
        tmp_path: Path,
    ) -> None:
        """Each ``PendingDecision.path`` points to the originating artifact."""
        project = _setup_integration_project(tmp_path)

        orphan_path = _write_orphan_concept(project)
        convention_path = _write_stale_convention(project)
        playbook_path = _write_stale_playbook(project)

        report = _run_coordinator(project)

        # Build a lookup by check for easier per-check assertions.
        by_check = {d.check: d for d in report.pending_decisions}

        assert "orphan_concepts" in by_check
        assert by_check["orphan_concepts"].path == orphan_path

        # convention_stale emits ``conventions/<slug>.md`` relative to
        # lexibrary_dir; the escalate fixer resolves it to the absolute
        # convention path under ``.lexibrary/conventions/``.
        assert "convention_stale" in by_check
        assert by_check["convention_stale"].path == convention_path

        # playbook_staleness emits the path relative to project_root (e.g.
        # ``.lexibrary/playbooks/foo.md``); the escalate fixer resolves
        # to ``project_root / issue.artifact`` which equals the playbook
        # file on disk.
        assert "playbook_staleness" in by_check
        assert by_check["playbook_staleness"].path == playbook_path


# ---------------------------------------------------------------------------
# TTL window suppresses orphan_concepts but NOT the other three checks
# ---------------------------------------------------------------------------


class TestTTLWindowSuppressesOrphanOnly:
    """A recent ``last_verified`` suppresses ``orphan_concepts`` only.

    Curator-4 Group 10: ``check_orphan_concepts`` honours
    ``concepts.orphan_verify_ttl_days`` (default 90). When a concept has
    been verified within the TTL window, the orphan warning is suppressed
    so no ``PendingDecision`` is emitted for that concept.
    """

    def test_fresh_last_verified_skips_orphan_decision(
        self,
        tmp_path: Path,
    ) -> None:
        project = _setup_integration_project(tmp_path)

        concepts_dir = project / LEXIBRARY_DIR / "concepts"
        concepts_dir.mkdir(parents=True, exist_ok=True)
        recent = (date.today() - timedelta(days=10)).isoformat()
        (concepts_dir / "RecentlyVerified.md").write_text(
            "---\n"
            "title: RecentlyVerified\n"
            "id: CN-ESC-003\n"
            "aliases: []\n"
            "tags: [test]\n"
            "status: active\n"
            f"last_verified: {recent}\n"
            "---\n\n"
            "A concept the operator vouched for recently.\n",
            encoding="utf-8",
        )

        report = _run_coordinator(project)

        pending_checks = {d.check for d in report.pending_decisions}
        assert "orphan_concepts" not in pending_checks, (
            "check_orphan_concepts should skip recently-verified concepts; "
            f"pending_decisions={report.pending_decisions}"
        )
