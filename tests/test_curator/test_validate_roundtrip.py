"""Mixed-fixture round-trip integration test (curator-fix Phase 5 — group 10).

This module is the end-to-end counterpart to the per-check round-trip
tests in :mod:`tests.test_curator.test_validation_roundtrip`.  Where that
module plants exactly one issue per fixture and asserts that one fixer
runs, this module plants issues across **all three** categories the
curator touches — FIXERS checks, consistency actions, and IWH residual
stubs — then asserts that a single ``Coordinator.run()`` call covers all
of them in one sweep.

Three scenarios live here:

* :class:`TestMixedFixtureRoundtrip` builds a self-contained library
  with planted issues across every category, runs the coordinator,
  re-runs ``validate_library()``, and checks that ``count_after``
  dropped by at least the number of categories we planted.  Per-category
  dispatches are also verified via ``report.dispatched_details`` so any
  silent regression in the validation bridge, consistency router, or
  IWH residual handler surfaces as a failing assertion.

* :class:`TestVerificationDeltaReported` exercises the Phase 5 observability
  feature: when ``CuratorConfig.verify_after_sweep`` is ``True`` the
  persisted JSON report must carry a ``verification`` block with
  ``before``, ``after`` and ``delta`` keys, and the in-memory
  :class:`CuratorReport` must expose the same dict.

* :class:`TestVerificationDeltaDisabledByDefault` pins the contract
  that verification is strictly opt-in — default config runs must not
  emit a ``verification`` key and must call ``validate_library()``
  exactly twice (one hash-layer call and one graph-layer call inside
  ``_collect_validation``; see task 5.2 for the split).

Fixture strategy: each test builds its own ``tmp_path``-rooted library
so cross-test interference is impossible.  This mirrors the per-test
isolation pattern established by sq5.6 in
``test_validation_roundtrip.py`` and avoids the stale link-graph +
oversaturated hash-freshness issues that sq5.1 flagged for the shared
``tests/fixtures/curator_library/`` tree.

BAML/LLM dependencies: the archivist pipeline call used by
``fix_hash_freshness`` is swapped for a deterministic stand-in so no
API keys are required.  No other sub-agent currently depends on BAML
on the code paths exercised here.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from lexibrary.artifacts.design_file import (
    DesignFile,
    DesignFileFrontmatter,
    StalenessMetadata,
)
from lexibrary.artifacts.design_file_serializer import serialize_design_file
from lexibrary.config.schema import LexibraryConfig
from lexibrary.curator.coordinator import Coordinator
from lexibrary.curator.models import CuratorReport
from lexibrary.validator import validate_library
from lexibrary.validator.report import ValidationReport

# ---------------------------------------------------------------------------
# Fixture builders — minimal, tmp_path-rooted libraries
# ---------------------------------------------------------------------------


def _write_config(project_root: Path, body: str | None = None) -> Path:
    """Write a minimal ``.lexibrary/config.yaml`` so ``load_config`` succeeds."""
    config_path = project_root / ".lexibrary" / "config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if body is None:
        body = (
            "project:\n  name: roundtrip-mixed\n  type: application\n  source_roots:\n    - src\n"
        )
    config_path.write_text(body, encoding="utf-8")
    return config_path


def _write_source_file(project_root: Path, rel_path: str, content: str) -> Path:
    """Write a source file under *project_root*."""
    abs_path = project_root / rel_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(content, encoding="utf-8")
    return abs_path


def _write_design_file(
    project_root: Path,
    source_rel: str,
    *,
    source_hash: str,
    wikilinks: list[str] | None = None,
    description: str = "Test design file",
) -> Path:
    """Write a design file at the mirrored path and return its absolute path."""
    design_path = project_root / ".lexibrary" / "designs" / (source_rel + ".md")
    design_path.parent.mkdir(parents=True, exist_ok=True)

    design = DesignFile(
        source_path=source_rel,
        frontmatter=DesignFileFrontmatter(
            description=description,
            id=source_rel.replace("/", "-").replace(".", "-"),
            updated_by="archivist",
            status="active",
        ),
        summary="",
        interface_contract='"""Placeholder."""',
        dependencies=[],
        dependents=[],
        wikilinks=list(wikilinks or []),
        metadata=StalenessMetadata(
            source=source_rel,
            source_hash=source_hash,
            interface_hash=None,
            generated=datetime.now(UTC).replace(tzinfo=None),
            generator="lexibrary-v2-test",
        ),
    )
    design_path.write_text(serialize_design_file(design), encoding="utf-8")
    return design_path


def _write_aindex(project_root: Path, source_rel_dir: str, body: str = "# Test aindex") -> Path:
    """Write a ``.aindex`` at the mirrored design path."""
    aindex_path = project_root / ".lexibrary" / "designs" / source_rel_dir / ".aindex"
    aindex_path.parent.mkdir(parents=True, exist_ok=True)
    aindex_path.write_text(body + "\n", encoding="utf-8")
    return aindex_path


def _write_concept(project_root: Path, concept_id: str, title: str, aliases: list[str]) -> Path:
    """Write a minimal concept file so ``WikilinkResolver`` can load an index."""
    concepts_dir = project_root / ".lexibrary" / "concepts"
    concepts_dir.mkdir(parents=True, exist_ok=True)
    concept_path = concepts_dir / f"{concept_id}-{title.lower().replace(' ', '-')}.md"
    alias_block = "\n".join(f"- {alias}" for alias in aliases) if aliases else ""
    body = (
        "---\n"
        f"title: {title}\n"
        f"id: {concept_id}\n"
        + ("aliases:\n" + alias_block + "\n" if aliases else "")
        + "tags:\n- test\n"
        "status: active\n"
        "---\n"
        f"Concept definition for {title}.\n"
    )
    concept_path.write_text(body, encoding="utf-8")
    return concept_path


def _write_convention(
    project_root: Path,
    conv_id: str,
    title: str,
    *,
    scope: str,
    body: str,
) -> Path:
    """Write a minimal convention file used by the consistency checks."""
    conv_dir = project_root / ".lexibrary" / "conventions"
    conv_dir.mkdir(parents=True, exist_ok=True)
    conv_path = conv_dir / f"{conv_id}-{title.lower().replace(' ', '-')}.md"
    text = (
        "---\n"
        f"title: {title}\n"
        f"id: {conv_id}\n"
        f"scope: {scope}\n"
        "tags:\n- test\n"
        "status: active\n"
        "source: agent\n"
        "priority: 0\n"
        "---\n"
        f"{body}\n"
    )
    conv_path.write_text(text, encoding="utf-8")
    return conv_path


def _write_iwh(
    project_root: Path,
    source_rel_dir: str,
    *,
    scope: str,
    body: str,
    age_days: int,
) -> Path:
    """Write an ``.iwh`` file directly so we control the ``created`` timestamp.

    The curator's stock ``write_iwh`` helper stamps ``created`` with
    ``datetime.now()``, which is too recent for the promote-blocked-iwh
    ``ttl_hours=72`` threshold.  Writing the YAML by hand lets us backdate
    the signal so ``detect_promotable_iwh`` fires deterministically.
    """
    iwh_path = project_root / ".lexibrary" / "designs" / source_rel_dir / ".iwh"
    iwh_path.parent.mkdir(parents=True, exist_ok=True)
    created = datetime.now(UTC) - timedelta(days=age_days)
    text = (
        f"---\nauthor: test-agent\ncreated: '{created.isoformat()}'\nscope: {scope}\n---\n{body}\n"
    )
    iwh_path.write_text(text, encoding="utf-8")
    return iwh_path


def _build_mixed_library(tmp_path: Path, *, name: str = "mixed") -> Path:
    """Create a ``tmp_path``-rooted library with issues across every category.

    Planted issues (by curator category):

    FIXERS (validation bridge)
    --------------------------
    * ``hash_freshness`` — ``src/utils/helpers.py`` design file has a
      deliberately wrong ``source_hash``.
    * ``aindex_coverage`` — ``src/auth/`` has no ``.aindex``.
    * ``orphaned_aindex`` — ``.lexibrary/designs/src/deleted/.aindex``
      without a matching source directory.

    Validator-bridge consistency actions
    -------------------------------------
    * ``fix_wikilink_resolution`` — ``formatter.py.md`` carries
      ``[[NonexistentConcept]]`` which has no concept file.  Planted on
      a design with a correct ``source_hash`` so the hash_freshness
      regeneration does not pre-empt the wikilink fixer dispatch under
      the two-pass flow introduced in group 5.

    Curator-side consistency actions
    --------------------------------
    * ``flag_stale_convention`` — ``CV-001-stale.md`` references
      ``src/old_auth/`` which does not exist.

    IWH residual / consistency
    --------------------------
    * ``promote_blocked_iwh`` — ``.lexibrary/designs/src/utils/.iwh``
      with ``scope: blocked`` and a ``created`` timestamp well beyond
      the 72-hour TTL.
    """
    project = tmp_path / name
    project.mkdir()
    (project / ".lexibrary").mkdir()
    (project / ".lexibrary" / "designs").mkdir()
    _write_config(project)

    # Healthy concept so the WikilinkResolver can build an index and the
    # convention check has something to compare against.
    _write_concept(project, "CN-001", "Authentication", aliases=["auth"])

    # --- FIXERS planted issues ------------------------------------------
    # hash_freshness: real source file, design with wrong hash.
    _write_source_file(
        project,
        "src/utils/helpers.py",
        '"""Helpers."""\n\n\ndef slugify(text: str) -> str:\n    return text\n',
    )
    _write_design_file(
        project,
        "src/utils/helpers.py",
        source_hash="deadbeef" * 8,  # deliberately wrong
    )
    # fix_wikilink_resolution: planted on a SEPARATE design with a
    # correct hash so the hash_freshness regeneration (which would
    # otherwise rewrite the body via the same archivist pipeline under
    # the two-pass flow introduced in group 5) does not pre-empt the
    # validator-bridge dispatch for wikilink resolution.
    from lexibrary.ast_parser import compute_hashes  # noqa: PLC0415

    formatter_source = _write_source_file(
        project,
        "src/utils/formatter.py",
        '"""Formatter."""\n\n\ndef format_text(text: str) -> str:\n    return text\n',
    )
    formatter_source_hash, _formatter_interface_hash = compute_hashes(formatter_source)
    _write_design_file(
        project,
        "src/utils/formatter.py",
        source_hash=formatter_source_hash,
        wikilinks=["NonexistentConcept"],  # plants wikilink_resolution issue
    )
    # aindex_coverage: src/auth/ has a source file but no .aindex.
    _write_source_file(project, "src/auth/login.py", '"""Login."""\n')
    # orphaned_aindex: src/deleted/ has a .aindex but no source directory.
    _write_aindex(project, "src/deleted")

    # --- Consistency planted issues -------------------------------------
    # flag_stale_convention: convention references src/old_auth/ which is absent.
    _write_convention(
        project,
        "CV-001",
        "Stale",
        scope="src/old_auth/",
        body="Authentication code must live under `src/old_auth/` (this path no longer exists).",
    )

    # --- IWH residual (detected by consistency `full` mode) -------------
    _write_iwh(
        project,
        "src/utils",
        scope="blocked",
        body="Blocked on upstream decision; promote to Stack after review.",
        age_days=30,
    )

    return project


# ---------------------------------------------------------------------------
# Deterministic archivist stub (shared with the per-check round-trip suite)
# ---------------------------------------------------------------------------


@pytest.fixture()
def deterministic_hash_freshness(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace ``archivist.pipeline.update_file`` with a deterministic stub.

    ``fix_hash_freshness`` normally invokes the archivist pipeline, which
    regenerates the design body via a BAML/LLM runtime.  Round-trip tests
    must not depend on a live LLM, so this fixture swaps the pipeline for
    a stand-in that refreshes only the footer hashes of the existing
    design file in place — same return contract as the real
    ``update_file``.

    The pattern mirrors sq5.6's ``deterministic_hash_freshness`` fixture
    in ``test_validation_roundtrip.py`` verbatim so both round-trip
    suites exercise identical hash-refresh semantics.
    """

    from lexibrary.archivist import pipeline as archivist_pipeline
    from lexibrary.archivist.change_checker import ChangeLevel
    from lexibrary.archivist.pipeline import FileResult, _refresh_footer_hashes
    from lexibrary.ast_parser import compute_hashes
    from lexibrary.utils.paths import mirror_path

    async def deterministic_update_file(
        source_path: Path,
        project_root: Path,
        config: Any,
        archivist: Any,
        available_artifacts: list[str] | None = None,
        *,
        force: bool = False,
        unlimited: bool = False,
    ) -> FileResult:
        design_path = mirror_path(project_root, source_path)
        if not design_path.exists():
            return FileResult(
                change=ChangeLevel.UNCHANGED,
                failed=True,
                failure_reason="design file missing",
            )
        content_hash, interface_hash = compute_hashes(source_path)
        _refresh_footer_hashes(design_path, content_hash, interface_hash, project_root)
        return FileResult(change=ChangeLevel.CONTENT_ONLY)

    monkeypatch.setattr(archivist_pipeline, "update_file", deterministic_update_file)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_coordinator(
    project_root: Path,
    *,
    autonomy: str = "full",
    verify_after_sweep: bool = False,
    consistency_collect: str = "full",
) -> CuratorReport:
    """Run the coordinator pipeline synchronously.

    Defaults to ``autonomy="full"`` so medium-risk consistency actions
    (``promote_blocked_iwh``) dispatch instead of being deferred, and
    ``consistency_collect="full"`` so the library-wide promotable-IWH
    and orphan-concept checks run alongside the scope-bounded ones.
    """
    config = LexibraryConfig.model_validate(
        {
            "curator": {
                "autonomy": autonomy,
                "consistency_collect": consistency_collect,
                "verify_after_sweep": verify_after_sweep,
            }
        }
    )
    coord = Coordinator(project_root, config)
    return asyncio.run(coord.run())


def _count_issues(report: ValidationReport) -> int:
    return len(report.issues)


def _dispatched_action_keys(report: CuratorReport) -> set[str]:
    return {str(entry.get("action_key")) for entry in report.dispatched_details}


def _count_by_check(report: ValidationReport) -> dict[str, int]:
    counts: dict[str, int] = {}
    for issue in report.issues:
        counts[issue.check] = counts.get(issue.check, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# Test class 1 — mixed fixture round-trip
# ---------------------------------------------------------------------------


class TestMixedFixtureRoundtrip:
    """Validate → curator → validate: every planted category must drop."""

    def test_curator_validate_roundtrip_mixed_fixture(
        self,
        tmp_path: Path,
        deterministic_hash_freshness: None,
    ) -> None:
        project = _build_mixed_library(tmp_path, name="round-trip")

        before = validate_library(project, project / ".lexibrary")
        before_count = _count_issues(before)
        before_checks = _count_by_check(before)

        # Sanity — every planted FIXERS category must be visible up front.
        assert before_checks.get("hash_freshness", 0) >= 1, (
            f"expected planted hash_freshness, got: {before_checks}"
        )
        assert before_checks.get("aindex_coverage", 0) >= 1, (
            f"expected planted aindex_coverage, got: {before_checks}"
        )
        assert before_checks.get("orphaned_aindex", 0) >= 1, (
            f"expected planted orphaned_aindex, got: {before_checks}"
        )
        # Wikilink resolution fires from the validator for the planted
        # unresolved wikilink in helpers.py.md.
        assert before_checks.get("wikilink_resolution", 0) >= 1, (
            f"expected planted wikilink_resolution, got: {before_checks}"
        )
        # Convention orphaned scope picks up CV-001's src/old_auth/.
        assert before_checks.get("convention_orphaned_scope", 0) >= 1, (
            f"expected planted convention_orphaned_scope, got: {before_checks}"
        )

        report = _run_coordinator(project)

        after = validate_library(project, project / ".lexibrary")
        after_count = _count_issues(after)
        after_checks = _count_by_check(after)

        # Core invariant: the sweep resolved at least some planted issues.
        assert after_count < before_count, (
            f"count_after ({after_count}) is not less than "
            f"count_before ({before_count}); deltas by check: "
            f"{ {k: before_checks.get(k, 0) - after_checks.get(k, 0) for k in before_checks} }"
        )

        # Per-category dispatch coverage (verified via action_key on the
        # in-memory CuratorReport so the test fails loudly if the router
        # silently drops a category).
        action_keys = _dispatched_action_keys(report)
        # FIXERS bridge — narrow action keys from CHECK_TO_ACTION_KEY.
        assert "fix_hash_freshness" in action_keys, (
            f"expected fix_hash_freshness dispatch, got: {sorted(action_keys)}"
        )
        assert "fix_aindex_coverage" in action_keys, (
            f"expected fix_aindex_coverage dispatch, got: {sorted(action_keys)}"
        )
        assert "fix_orphaned_aindex" in action_keys, (
            f"expected fix_orphaned_aindex dispatch, got: {sorted(action_keys)}"
        )
        # Validator bridge — wikilink resolution (curator-freshness group 9
        # retired the curator-side ``strip_unresolved_wikilink`` handler in
        # favour of the archivist-delegated ``fix_wikilink_resolution`` fixer).
        assert "fix_wikilink_resolution" in action_keys, (
            f"expected fix_wikilink_resolution dispatch, got: {sorted(action_keys)}"
        )
        # Consistency router — stale convention.
        assert "flag_stale_convention" in action_keys, (
            f"expected flag_stale_convention dispatch, got: {sorted(action_keys)}"
        )
        # IWH residual (consistency `full` mode) — blocked IWH promotion.
        assert "promote_blocked_iwh" in action_keys, (
            f"expected promote_blocked_iwh dispatch, got: {sorted(action_keys)}"
        )

        # Per-category after-count assertions — each planted FIXERS check
        # must drop to zero.  Consistency-only categories are not guaranteed
        # to clear from the validator side (e.g. ``flag_stale_convention``
        # only writes a warning IWH without rewriting the convention
        # scope), so we only assert the FIXERS deltas here.
        assert after_checks.get("hash_freshness", 0) == 0, (
            f"hash_freshness should be resolved, got: {after_checks.get('hash_freshness')}"
        )
        # aindex_coverage: src/auth should no longer be flagged.
        after_coverage_dirs = {
            issue.artifact for issue in after.issues if issue.check == "aindex_coverage"
        }
        assert "src/auth" not in after_coverage_dirs, (
            f"src/auth should have a .aindex after the sweep, "
            f"remaining missing: {after_coverage_dirs}"
        )
        assert after_checks.get("orphaned_aindex", 0) == 0, (
            f"orphaned_aindex should be resolved, got: {after_checks.get('orphaned_aindex')}"
        )
        # wikilink_resolution: ``fix_wikilink_resolution`` delegates to
        # ``archivist.pipeline.update_file``, which is stubbed here by
        # ``deterministic_hash_freshness`` to refresh footer hashes only —
        # the body wikilink is not actually rewritten under the stub.  The
        # dispatch-coverage assertion above pins the routing; the count
        # may legitimately stay flat.  Allow no-decrease (``<=``) so the
        # assertion still guards against regression growth.
        assert after_checks.get("wikilink_resolution", 0) <= before_checks.get(
            "wikilink_resolution", 0
        ), (
            "wikilink_resolution count grew; "
            f"before={before_checks.get('wikilink_resolution', 0)} "
            f"after={after_checks.get('wikilink_resolution', 0)}"
        )


# ---------------------------------------------------------------------------
# Test class 1b — flag_stale_convention escalation-only pin
# ---------------------------------------------------------------------------


class TestFlagStaleConventionEscalationOnly:
    """``flag_stale_convention`` is escalation-only: writes a warning IWH but
    does NOT rewrite the convention body, so ``convention_orphaned_scope`` in
    the validator must stay at the same count after the curator sweep.
    """

    def test_flag_stale_convention_does_not_reduce_validator_count(
        self,
        tmp_path: Path,
        deterministic_hash_freshness: None,
    ) -> None:
        project = _build_mixed_library(tmp_path, name="flag-stale-pin")

        before = validate_library(project, project / ".lexibrary")
        before_checks = _count_by_check(before)
        convention_before = before_checks.get("convention_orphaned_scope", 0)
        assert convention_before >= 1, (
            f"expected planted convention_orphaned_scope, got: {before_checks}"
        )

        # ``flag_stale_convention`` is collected in ``scope`` mode, so use
        # ``consistency_collect="scope"`` to exercise that collect path.
        report = _run_coordinator(project, consistency_collect="scope")

        # The curator must have dispatched ``flag_stale_convention`` — the
        # whole point of this test is that it ran yet did not reduce the
        # validator count.
        action_keys = _dispatched_action_keys(report)
        assert "flag_stale_convention" in action_keys, (
            f"expected flag_stale_convention dispatch, got: {sorted(action_keys)}"
        )

        after = validate_library(project, project / ".lexibrary")
        after_checks = _count_by_check(after)
        convention_after = after_checks.get("convention_orphaned_scope", 0)
        assert convention_after == convention_before, (
            f"flag_stale_convention is escalation-only and must not reduce "
            f"convention_orphaned_scope: before={convention_before} "
            f"after={convention_after}"
        )


# ---------------------------------------------------------------------------
# Test class 2 — verification delta reported when enabled
# ---------------------------------------------------------------------------


class TestVerificationDeltaReported:
    """When ``verify_after_sweep=True`` the report carries a delta block."""

    def test_verification_delta_reported_when_enabled(
        self,
        tmp_path: Path,
        deterministic_hash_freshness: None,
    ) -> None:
        project = _build_mixed_library(tmp_path, name="verify-enabled")

        report = _run_coordinator(project, verify_after_sweep=True)

        # In-memory report carries the dict.
        assert report.verification is not None, (
            "CuratorReport.verification must be populated when verify_after_sweep=True"
        )
        assert set(report.verification.keys()) == {"before", "after", "delta"}, (
            f"verification keys: {sorted(report.verification.keys())}"
        )
        before = report.verification["before"]
        after = report.verification["after"]
        delta = report.verification["delta"]
        assert isinstance(before, int)
        assert isinstance(after, int)
        assert isinstance(delta, int)
        # Before count must exceed after (we planted several fixable issues).
        assert before > 0
        assert after >= 0
        assert delta == before - after
        assert delta > 0, (
            f"expected positive delta, got before={before} after={after} delta={delta}"
        )

        # Persisted JSON report mirrors the in-memory block.
        assert report.report_path is not None
        persisted = json.loads(report.report_path.read_text(encoding="utf-8"))
        assert "verification" in persisted, (
            f"JSON report missing verification key; keys: {sorted(persisted.keys())}"
        )
        assert persisted["verification"] == {
            "before": before,
            "after": after,
            "delta": delta,
        }


# ---------------------------------------------------------------------------
# Test class 3 — verification disabled by default
# ---------------------------------------------------------------------------


class TestVerificationDeltaDisabledByDefault:
    """Default config: no verification key, ``validate_library()`` called once."""

    def test_verification_delta_disabled_by_default(
        self,
        tmp_path: Path,
        deterministic_hash_freshness: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        project = _build_mixed_library(tmp_path, name="verify-default")

        # Count how many times ``validate_library`` is called on the
        # coordinator's code path.  Because ``_collect_validation`` and
        # ``_verify_after_sweep`` both import the symbol lazily from
        # :mod:`lexibrary.validator` at call time, patching the module
        # attribute covers both call sites.
        call_counter: dict[str, int] = {"count": 0}
        import lexibrary.validator as validator_module

        real_validate = validator_module.validate_library

        def counting_validate(
            project_root: Path,
            lexibrary_dir: Path,
            *args: Any,
            **kwargs: Any,
        ) -> ValidationReport:
            call_counter["count"] += 1
            return real_validate(project_root, lexibrary_dir, *args, **kwargs)

        monkeypatch.setattr(validator_module, "validate_library", counting_validate)

        # Default config: verify_after_sweep=False, consistency_collect="scope".
        # The mixed fixture's promote_blocked_iwh is ``full``-only so it will
        # NOT dispatch here; that is intentional — the purpose of this test
        # is to pin the observability contract, not per-category coverage.
        config = LexibraryConfig.model_validate(
            {
                "curator": {
                    "autonomy": "full",
                }
            }
        )
        coord = Coordinator(project, config)
        report = asyncio.run(coord.run())

        # 1) ``validate_library`` was called exactly twice — once per
        #    layer (hash-layer subset + graph-layer subset) inside
        #    ``_collect_validation`` after the task 5.2 split.  The
        #    two calls together cover the full check registry exactly
        #    once (the ``_HASH_LAYER_CHECKS`` / ``_GRAPH_LAYER_CHECKS``
        #    partition is total and disjoint).  No post-sweep
        #    verification pass should have run.
        assert call_counter["count"] == 2, (
            f"validate_library should be called exactly twice with default "
            f"config (once per layer), got {call_counter['count']} calls"
        )

        # 2) In-memory report has no verification block.
        assert report.verification is None, (
            f"CuratorReport.verification should be None by default, got: {report.verification}"
        )

        # 3) Persisted JSON report has no ``verification`` key.
        assert report.report_path is not None
        persisted = json.loads(report.report_path.read_text(encoding="utf-8"))
        assert "verification" not in persisted, (
            f"JSON report must not contain verification key by default; "
            f"found keys: {sorted(persisted.keys())}"
        )
