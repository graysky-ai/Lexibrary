"""End-to-end integration test for the two curator-4 operational fixers.

Curator-4 Group 23.2 / 23.3: run the full coordinator pipeline
(``collect -> triage -> dispatch -> report``) against a fixture seeded
with ``lookup_token_budget_exceeded`` and ``orphaned_iwh_signals``
issues and assert:

1. The ``lookup_token_budget_exceeded`` issue dispatches with
   ``action_key="fix_lookup_token_budget_exceeded"`` and
   ``outcome="fixed"``.
2. The BAML ``CuratorCondenseFile`` call is counted exactly once
   (``llm_calls=1`` on the matching dispatched entry), satisfying the
   "``llm_calls_used`` increments correctly for the token-budget fixer"
   requirement.
3. The expired ``.iwh`` signal is removed from disk by the pipeline.
   The curator's own ``_collect_iwh`` hash-layer collector routes
   non-blocked IWH files through ``consume_superseded_iwh`` before the
   graph-layer validator check emits an ``orphaned_iwh_signals`` issue,
   so the on-disk contract holds either way — the test asserts the
   observable side-effect (file deleted) rather than the specific
   action key, while still enforcing the Group 23.3 ``no_fixer`` guard.
4. **Group 23.3** — zero dispatched entries carry ``outcome="no_fixer"``
   for any of the six curator-4 action keys.

The fixture deliberately uses ``body_size=200`` so the design file
lands between the default ``BudgetTrimmer`` 4000-token design budget
and the test-scoped 200-token lookup budget.  That keeps the
curator-side ``condense_file`` sub-agent idle (it would otherwise
dispatch via ``action_key="condense_file"`` from the token-budget
scanner, shadowing the validator route).

The BAML ``CuratorCondenseFile`` call is mocked to keep the test
deterministic and LLM-free.

Mirrors the structure of
``tests/test_curator/test_wikilink_resolution_integration.py``.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from lexibrary.artifacts.design_file import (
    DesignFile,
    DesignFileFrontmatter,
    StalenessMetadata,
)
from lexibrary.artifacts.design_file_serializer import serialize_design_file
from lexibrary.config.schema import LexibraryConfig
from lexibrary.curator.coordinator import Coordinator
from lexibrary.curator.models import CuratorReport
from lexibrary.utils.paths import DESIGNS_DIR, LEXIBRARY_DIR

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _setup_integration_project(tmp_path: Path) -> Path:
    """Build a minimal project with a full ``.lexibrary/`` layout."""
    project = tmp_path / "operational_fixer_integration"
    project.mkdir()
    lex = project / LEXIBRARY_DIR
    lex.mkdir()
    for sub in ("designs", "concepts", "conventions", "playbooks", "stack"):
        (lex / sub).mkdir()
    (lex / "config.yaml").write_text(
        "scope_roots:\n  - path: .\n",
        encoding="utf-8",
    )
    return project


def _write_oversized_design(
    project: Path,
    source_rel: str,
    *,
    body_size: int = 200,
) -> Path:
    """Write a design file over *lookup_total_tokens* but under *design_file*.

    With ``body_size=200`` the serialised design is ~2220 approximate
    tokens — well below the default ``BudgetTrimmer`` 4000-token design
    budget (so ``scan_token_budgets`` emits no ``BudgetIssue``), but well
    above the 200-token lookup budget configured in the test
    (so ``check_lookup_token_budget_exceeded`` emits an info issue).
    """
    source_path = project / source_rel
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(
        "def noop() -> None:\n    return None\n",
        encoding="utf-8",
    )

    bulky = "Padding paragraph to inflate token count. " * body_size
    df = DesignFile(
        source_path=source_rel,
        frontmatter=DesignFileFrontmatter(
            description="Oversized fixture for token-budget fixer.",
            id="DS-OVER-001",
            updated_by="agent",
        ),
        summary="Sentinel (not serialised).",
        interface_contract="def noop() -> None: ...",
        dependencies=[],
        dependents=[],
        preserved_sections={"Summary": bulky},
        metadata=StalenessMetadata(
            source=source_rel,
            source_hash="stub-source-hash",
            interface_hash="stub-interface-hash",
            design_hash="stub-design-hash",
            generated=datetime.now(UTC).replace(tzinfo=None),
            generator="test",
        ),
    )

    design_path = project / LEXIBRARY_DIR / DESIGNS_DIR / f"{source_rel}.md"
    design_path.parent.mkdir(parents=True, exist_ok=True)
    design_path.write_text(serialize_design_file(df), encoding="utf-8")
    return design_path


def _build_condensed_body(source_rel: str) -> str:
    """Return a minimal design-file body (~130 approximate tokens)."""
    df = DesignFile(
        source_path=source_rel,
        frontmatter=DesignFileFrontmatter(
            description="Oversized fixture for token-budget fixer.",
            id="DS-OVER-001",
            updated_by="curator",
        ),
        summary="Sentinel (not serialised).",
        interface_contract="def noop() -> None: ...",
        dependencies=[],
        dependents=[],
        preserved_sections={},
        metadata=StalenessMetadata(
            source=source_rel,
            source_hash="baml-source-hash",
            interface_hash="baml-interface-hash",
            design_hash="baml-design-hash",
            generated=datetime.now(UTC).replace(tzinfo=None),
            generator="test",
        ),
    )
    return serialize_design_file(df)


def _write_expired_iwh(project: Path, directory_path: str) -> Path:
    """Write a valid .iwh whose ``created`` is > 72h old.

    The source directory is also created so ``find_orphaned_iwh``
    (which targets signals whose source dir has vanished) does NOT
    also fire — we want only the TTL-expired variant.
    """
    created = datetime.now(tz=UTC) - timedelta(hours=200)
    iso = created.strftime("%Y-%m-%dT%H:%M:%SZ")
    source_dir = project / directory_path
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "module.py").write_text("pass\n", encoding="utf-8")

    iwh_dir = project / LEXIBRARY_DIR / DESIGNS_DIR / directory_path
    iwh_dir.mkdir(parents=True, exist_ok=True)
    iwh_path = iwh_dir / ".iwh"
    iwh_path.write_text(
        "---\n"
        "author: test-agent\n"
        f"created: {iso}\n"
        "scope: incomplete\n"
        "---\n\n"
        "Expired signal body.\n",
        encoding="utf-8",
    )
    return iwh_path


def _run_coordinator(
    project: Path,
    *,
    autonomy: str = "full",
    lookup_total_tokens: int = 200,
    fix_condense: bool = True,
) -> CuratorReport:
    """Run the coordinator under ``full`` autonomy with opt-in fixers."""
    config = LexibraryConfig.model_validate(
        {
            "scope_roots": [{"path": "."}],
            "curator": {"autonomy": autonomy},
            "token_budgets": {"lookup_total_tokens": lookup_total_tokens},
            "validator": {
                "fix_lookup_token_budget_condense": fix_condense,
                "fix_orphaned_iwh_signals_delete": True,
            },
        }
    )
    coord = Coordinator(project, config)
    return asyncio.run(coord.run())


# ---------------------------------------------------------------------------
# fix_lookup_token_budget_exceeded end-to-end
# ---------------------------------------------------------------------------


class TestTokenBudgetFixerEndToEnd:
    """``fix_lookup_token_budget_exceeded`` dispatches under ``full`` autonomy.

    Uses ``body_size=200`` (~2220 tokens) so the file exceeds the
    lookup budget (200 tokens) but NOT the default ``BudgetTrimmer``
    design budget (4000 tokens) — only the validator-fixer path
    dispatches; the curator-side ``condense_file`` sub-agent stays
    idle.
    """

    def test_token_budget_fixer_dispatches_with_llm_call(
        self,
        tmp_path: Path,
    ) -> None:
        project = _setup_integration_project(tmp_path)

        source_rel = "src/oversized/module.py"
        design_path = _write_oversized_design(project, source_rel, body_size=200)

        # Mock the BAML client so the condense path runs deterministically.
        short_body = _build_condensed_body(source_rel)
        mock_baml = MagicMock()
        mock_baml.condensed_content = short_body
        mock_baml.trimmed_sections = ["Removed verbose Summary"]

        mock_client = AsyncMock()
        mock_client.CuratorCondenseFile.return_value = mock_baml

        with patch("lexibrary.curator.budget.b", mock_client):
            report = _run_coordinator(project, lookup_total_tokens=200)

        dispatched = list(report.dispatched_details)

        # Validator-fixer dispatched with outcome="fixed".
        token_budget_fixed = [
            entry
            for entry in dispatched
            if entry.get("action_key") == "fix_lookup_token_budget_exceeded"
            and entry.get("outcome") == "fixed"
        ]
        assert token_budget_fixed, (
            "Expected a dispatched entry with "
            "action_key='fix_lookup_token_budget_exceeded' and "
            f"outcome='fixed'; got {dispatched}"
        )

        # llm_calls=1 on the fixer — CuratorCondenseFile was invoked.
        assert token_budget_fixed[0]["llm_calls"] == 1, (
            "fix_lookup_token_budget_exceeded must charge exactly one "
            f"LLM call; got {token_budget_fixed[0]['llm_calls']}"
        )

        # The coordinator's ``condense_file`` budget-trimmer sub-agent
        # must NOT dispatch — the file sits below its 4000-token budget.
        # This is what the body_size=200 fixture is guarding: we want
        # only one path to fire, and it must be the validator-fixer.
        curator_condense = [
            entry for entry in dispatched if entry.get("action_key") == "condense_file"
        ]
        assert not curator_condense, (
            "Curator-side condense_file sub-agent should not dispatch "
            "under body_size=200 / 4000-token default design budget; "
            f"got {curator_condense}"
        )

        # Side effect lands: the design body is condensed on disk.
        assert design_path.exists()
        condensed_text = design_path.read_text(encoding="utf-8")
        assert len(condensed_text) < 8_000, (
            "Condensed body should be much smaller than the ~11k-char "
            f"original; got {len(condensed_text)} chars"
        )


# ---------------------------------------------------------------------------
# orphaned_iwh_signals route — observable outcome
# ---------------------------------------------------------------------------


class TestOrphanedIwhSignalsEndToEnd:
    """Expired IWH signal is removed by the pipeline.

    The curator's ``_collect_iwh`` hash-layer collector dispatches
    ``consume_superseded_iwh`` for every non-blocked IWH it finds —
    this runs BEFORE the graph-layer ``check_orphaned_iwh_signals``
    validator check has a chance to emit its issue.  The end-to-end
    contract we test is therefore:

    1. The expired ``.iwh`` file is deleted after the pipeline runs
       (either path satisfies the operator's intent).
    2. Any dispatched entry that touches this file carries
       ``outcome="fixed"`` — not ``no_fixer``.
    3. The Group 23.3 invariant (no ``no_fixer`` entries for any of the
       six curator-4 action keys) holds regardless of which path
       actually fires.
    """

    def test_expired_iwh_deleted_and_no_fixer_gap(self, tmp_path: Path) -> None:
        project = _setup_integration_project(tmp_path)
        expired_iwh = _write_expired_iwh(project, "src/stale_iwh_dir")
        assert expired_iwh.exists()

        report = _run_coordinator(project)

        # Observable side-effect: the IWH is gone.
        assert not expired_iwh.exists(), (
            f"Expected expired IWH {expired_iwh} to be removed; "
            "still present after coordinator run."
        )

        dispatched = list(report.dispatched_details)

        # Whichever fixer acted on the IWH must have outcome="fixed".
        iwh_touching_entries = [
            entry
            for entry in dispatched
            if (
                entry.get("action_key") in {"fix_orphaned_iwh_signals", "consume_superseded_iwh"}
                and entry.get("path")
                and "stale_iwh_dir" in str(entry.get("path"))
            )
        ]
        assert iwh_touching_entries, (
            "No dispatched entry for the expired IWH; pipeline did not "
            f"touch it. Dispatched: {dispatched}"
        )
        for entry in iwh_touching_entries:
            assert entry.get("outcome") == "fixed", (
                f"IWH-touching entry {entry} must carry outcome='fixed'"
            )

        # Group 23.3 guard — no_fixer for any of the six action keys.
        six_action_keys = {
            "escalate_orphan_concepts",
            "escalate_stale_concept",
            "escalate_convention_stale",
            "escalate_playbook_staleness",
            "fix_lookup_token_budget_exceeded",
            "fix_orphaned_iwh_signals",
        }
        no_fixer_offenders = [
            entry
            for entry in dispatched
            if entry.get("outcome") == "no_fixer" and entry.get("action_key") in six_action_keys
        ]
        assert not no_fixer_offenders, (
            "Group 23.3 regression: found no_fixer entries for "
            f"curator-4 action keys: {no_fixer_offenders}"
        )


# ---------------------------------------------------------------------------
# Group 23.3 — combined "no_fixer_registered" assertion
# ---------------------------------------------------------------------------


class TestNoFixerRegisteredForSixChecks:
    """After a mixed run, zero ``no_fixer`` entries for any of the six checks.

    Group 23.3 — the merged ``dispatched_details`` across escalation +
    operational issues SHALL contain zero ``no_fixer`` entries for any
    of the six curator-4 action keys.  This guards against a regression
    where the bridge or the FIXERS registry loses one of the routes.
    """

    def test_mixed_escalation_and_operational_dispatch_no_fixer_gap(
        self,
        tmp_path: Path,
    ) -> None:
        project = _setup_integration_project(tmp_path)

        # Escalation seeds — orphan_concepts + playbook_staleness.
        (project / LEXIBRARY_DIR / "concepts").mkdir(parents=True, exist_ok=True)
        (project / LEXIBRARY_DIR / "concepts" / "OrphanCombined.md").write_text(
            "---\n"
            "title: OrphanCombined\n"
            "id: CN-COMB-001\n"
            "aliases: []\n"
            "tags: [test]\n"
            "status: active\n"
            "---\n\n"
            "A concept.\n",
            encoding="utf-8",
        )
        (project / LEXIBRARY_DIR / "playbooks").mkdir(parents=True, exist_ok=True)
        (project / LEXIBRARY_DIR / "playbooks" / "never-verified.md").write_text(
            "---\n"
            "title: never-verified\n"
            "id: PB-COMB-001\n"
            "trigger_files: []\n"
            "tags: [test]\n"
            "status: active\n"
            "source: user\n"
            "---\n\n"
            "## Overview\n\nA playbook.\n",
            encoding="utf-8",
        )

        # Operational seeds — oversized design + expired IWH.
        source_rel = "src/big/module.py"
        _write_oversized_design(project, source_rel, body_size=200)
        _write_expired_iwh(project, "src/expired_iwh")

        short_body = _build_condensed_body(source_rel)
        mock_baml = MagicMock()
        mock_baml.condensed_content = short_body
        mock_baml.trimmed_sections = []
        mock_client = AsyncMock()
        mock_client.CuratorCondenseFile.return_value = mock_baml

        with patch("lexibrary.curator.budget.b", mock_client):
            report = _run_coordinator(project)

        dispatched = list(report.dispatched_details)
        six_action_keys = {
            "escalate_orphan_concepts",
            "escalate_stale_concept",
            "escalate_convention_stale",
            "escalate_playbook_staleness",
            "fix_lookup_token_budget_exceeded",
            "fix_orphaned_iwh_signals",
        }
        no_fixer_offenders = [
            entry
            for entry in dispatched
            if entry.get("outcome") == "no_fixer" and entry.get("action_key") in six_action_keys
        ]
        assert not no_fixer_offenders, (
            "Group 23.3 regression: coordinator produced no_fixer entries "
            "for one or more of the six curator-4 action keys. Entries: "
            f"{no_fixer_offenders}"
        )
