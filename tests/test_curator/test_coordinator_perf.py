"""Benchmark test for ``Coordinator`` PID-lock hold duration.

Task 5.10 of the ``curator-freshness`` change: confirm the new two-pass
flow (``CuratorConfig.two_pass_collect=True``) does not hold the PID lock
more than 2x as long as the legacy single-pass flow on the same fixture.

Measurement strategy — **lock-wrap** (not full-pipeline proxy).  The
module-level ``_acquire_lock`` and ``_release_lock`` helpers in
:mod:`lexibrary.curator.coordinator` bookend the entire pipeline body
inside :meth:`Coordinator.run` (`_acquire_lock(...)` at the top, a
``try/finally: _release_lock(...)`` around the body).  We monkey-patch
both helpers to capture ``time.perf_counter()`` stamps at entry and exit,
then compute the interval.  This is strictly more honest than timing
``await coord.run(...)`` because it excludes the asyncio scheduling
overhead on either side of the lock acquisition.

Baseline strategy — **option (b) inline legacy**.  We run both flows
on the same fixture in the same test process back-to-back.  The
coordinator is **re-instantiated** between flows because
``self.pre_charged_llm_calls`` (set by the two-pass flow to
``hash_dispatch.llm_calls_used``) would otherwise leak between runs and
skew the legacy baseline.

Fixture — ~75 synthetic design files carrying stale ``source_hash``
footers (triggers hash-layer staleness items).  Roughly one quarter of
the designs also embed unresolved wikilinks (triggers graph-layer
consistency items under ``consistency_collect="scope"``).  The fixture
stays small on purpose: pytest's full curator suite takes ~1 min on
this project and this benchmark should remain a small fraction of that.

Signals and side effects
------------------------
* ``dry_run=True`` keeps the benchmark hermetic — no real sub-agent
  LLM calls fire.  A consequence is that ``DispatchResult.written_paths``
  is empty for both flows, which means the two ``build_index`` calls
  inside the two-pass flow are skipped via the ``if hash_written and
  index_db_path.exists():`` guard.  Those skips match the legacy flow
  (which never called ``build_index`` at all), so the comparison
  still measures what we care about: the *structural* overhead of
  running collect → triage → dispatch **twice** versus once.  The
  benchmark therefore intentionally underestimates a future
  regression that lives *inside* ``build_index``; separate coverage
  belongs in a link-graph-specific benchmark.
* An empty ``index.db`` is still touched during setup so the guard
  path is correctly exercised (task-brief requirement).
* ``consistency_collect="scope"`` is kept on so the graph-layer
  pass in the two-pass flow does actual work (wikilink hygiene).
  Without this the graph pass would short-circuit and the ratio
  would flatter two-pass artificially.
"""

from __future__ import annotations

import asyncio
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from lexibrary.config.schema import LexibraryConfig
from lexibrary.curator import coordinator as coordinator_module
from lexibrary.curator.coordinator import Coordinator
from lexibrary.linkgraph.builder import build_index

# Benchmark tuning constants.  Kept at module scope so CI operators can
# trace the exact envelope without reading the test body.
_DESIGN_COUNT = 75
_RUNS_PER_FLOW = 5
# A ``>= 2x`` regression in two-pass lock-hold relative to legacy
# blocks merge (task 5.10).  We pick ``< 2.0`` as the strict limit.
_REGRESSION_RATIO_LIMIT = 2.0


def _write_design_with_stale_hash(
    design_path: Path,
    source_rel: str,
    *,
    wikilink_target: str | None = None,
) -> None:
    """Write a design file whose footer ``source_hash`` is intentionally stale.

    The frontmatter carries an ``abc-stale`` hash while the source file's
    actual on-disk hash will differ, producing a staleness signal during
    ``_collect_staleness``.  Optionally embeds a wikilink body line that
    resolves to a missing target — the validator's ``wikilink_resolution``
    check picks this up during graph-layer collect.
    """
    design_path.parent.mkdir(parents=True, exist_ok=True)
    generated_iso = datetime.now(UTC).isoformat()
    body_extra = ""
    if wikilink_target is not None:
        body_extra = f"\nSee [[{wikilink_target}]] for context.\n"
    footer = (
        "<!-- lexibrary:meta\n"
        f"source: {source_rel}\n"
        "source_hash: abc-stale\n"
        "design_hash: benchmark-fixture\n"
        f"generated: {generated_iso}\n"
        "generator: test-fixture\n"
        "-->\n"
    )
    design_path.write_text(
        f"# {source_rel}\n\nRole: benchmark stub.{body_extra}\n{footer}",
        encoding="utf-8",
    )


def _seed_fixture(project_root: Path, count: int) -> None:
    """Seed ``count`` (source, design) pairs with a mix of hash + graph issues.

    Every design carries a stale ``source_hash`` to guarantee hash-layer
    work.  Every fourth design also embeds a dangling wikilink so the
    graph-layer pass has consistency signals to process.  The sources are
    ``.txt`` stubs so :func:`compute_hashes` stays on the fast content-hash
    path.
    """
    (project_root / ".lexibrary").mkdir()
    (project_root / ".lexibrary" / "designs").mkdir()
    (project_root / ".lexibrary" / "config.yaml").write_text("", encoding="utf-8")

    src_root = project_root / "src"
    src_root.mkdir()

    for idx in range(count):
        pkg = f"pkg_{idx // 25:02d}"
        rel = f"src/{pkg}/mod_{idx:03d}.txt"
        source_abs = project_root / rel
        source_abs.parent.mkdir(parents=True, exist_ok=True)
        # Unique content -> unique real hash; footer carries a stale hash
        # that will NOT match, so _collect_staleness flags every file.
        source_abs.write_text(f"stub module {idx}\n", encoding="utf-8")

        designs_dir = project_root / ".lexibrary" / "designs"
        design_path = designs_dir / f"{rel}.md"
        wikilink = f"MissingConcept{idx}" if idx % 4 == 0 else None
        _write_design_with_stale_hash(design_path, rel, wikilink_target=wikilink)

    # build_index once during setup so ``index.db`` exists and the
    # post-dispatch guard path in _run_pipeline_two_pass sees a present
    # DB (per task 5.10 brief).  With dry_run=True dispatches produce
    # no written_paths so build_index inside the pipeline is still
    # skipped — this touch exists to keep the guard honest for future
    # non-dry benchmarks on the same fixture.
    build_index(project_root)


def _measure_one_run(
    project_root: Path,
    *,
    two_pass: bool,
) -> float:
    """Run the coordinator once under the requested flow and return the
    PID-lock hold duration in seconds.

    Monkey-patches ``_acquire_lock`` / ``_release_lock`` at the
    ``lexibrary.curator.coordinator`` module level — which is the site
    :meth:`Coordinator.run` resolves them from — so the captured stamps
    bookend the actual lock tenure.  The Coordinator is instantiated
    fresh per run so ``pre_charged_llm_calls`` cannot leak from a prior
    two-pass run into the legacy baseline (the two-pass flow bumps that
    attribute to ``hash_dispatch.llm_calls_used``).
    """
    config = LexibraryConfig.model_validate(
        {
            "curator": {
                "two_pass_collect": two_pass,
                # ``consistency_collect="scope"`` is the default; pinned
                # here so a future config default change does not silently
                # flatten the two-pass side by short-circuiting its graph
                # pass.
                "consistency_collect": "scope",
                # A realistic but modest per-run budget keeps the dispatch
                # loop from becoming the dominant cost.  dry_run=True still
                # bypasses real LLM work; this just sets the cap the
                # dispatcher uses for its 70/30 split.
                "max_llm_calls_per_run": 10,
            }
        }
    )
    coord = Coordinator(project_root, config)

    stamps: dict[str, float] = {}

    original_acquire = coordinator_module._acquire_lock
    original_release = coordinator_module._release_lock

    def _timed_acquire(root: Path) -> Path:
        stamps["enter"] = time.perf_counter()
        return original_acquire(root)

    def _timed_release(root: Path) -> None:
        stamps["exit"] = time.perf_counter()
        original_release(root)

    coordinator_module._acquire_lock = _timed_acquire  # type: ignore[assignment]
    coordinator_module._release_lock = _timed_release  # type: ignore[assignment]
    try:
        asyncio.run(coord.run(dry_run=True))
    finally:
        coordinator_module._acquire_lock = original_acquire  # type: ignore[assignment]
        coordinator_module._release_lock = original_release  # type: ignore[assignment]

    assert "enter" in stamps, "lock-acquire stamp was never captured"
    assert "exit" in stamps, "lock-release stamp was never captured"
    return stamps["exit"] - stamps["enter"]


def _p50(values: list[float]) -> float:
    """Return the median (P50) of a non-empty list."""
    return statistics.median(values)


@pytest.mark.benchmark
def test_two_pass_lock_hold_under_2x_legacy(tmp_path: Path) -> None:
    """Two-pass PID-lock hold duration must be < 2x legacy baseline.

    Both flows run on the same fixture in the same process, back-to-back,
    with fresh ``Coordinator`` instances (to avoid ``pre_charged_llm_calls``
    leakage).  Each flow's P50 duration is computed over
    ``_RUNS_PER_FLOW`` independent runs; the ratio two-pass / legacy
    is asserted ``< _REGRESSION_RATIO_LIMIT``.

    On failure the assertion message surfaces the full per-run
    distribution for both flows so a regression is diagnosable from CI
    logs alone without re-running the benchmark locally.
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    _seed_fixture(project_root, _DESIGN_COUNT)

    # Warmup: one run of each flow before the timed loop dampens first-run
    # noise (import caches, SQLite page cache, Pydantic validator warmup).
    # These results are discarded.
    _measure_one_run(project_root, two_pass=False)
    _measure_one_run(project_root, two_pass=True)

    legacy_durations: list[float] = []
    two_pass_durations: list[float] = []

    # Interleave legacy and two-pass runs so transient system noise
    # (background GC, disk flush) affects both flows symmetrically rather
    # than biasing whichever runs last.
    for _ in range(_RUNS_PER_FLOW):
        legacy_durations.append(_measure_one_run(project_root, two_pass=False))
        two_pass_durations.append(_measure_one_run(project_root, two_pass=True))

    legacy_p50 = _p50(legacy_durations)
    two_pass_p50 = _p50(two_pass_durations)
    # Guard against a zero baseline — if legacy somehow completes in
    # sub-microsecond time (the lock-path itself takes longer than that
    # on any real filesystem), the ratio calculation would divide by
    # zero.  We bail out loud rather than silently dividing.
    assert legacy_p50 > 0.0, (
        f"legacy P50 lock-hold is non-positive ({legacy_p50:.6f}s); "
        f"fixture or measurement is broken"
    )

    ratio = two_pass_p50 / legacy_p50

    # Surface the observed measurements on stdout so operators running
    # the benchmark with ``pytest -s`` can track drift run-over-run
    # without editing the test.  Silent on pass for default pytest
    # output.
    print(
        f"\n[benchmark] legacy P50={legacy_p50 * 1000:.1f}ms "
        f"two-pass P50={two_pass_p50 * 1000:.1f}ms ratio={ratio:.2f}x "
        f"(limit<{_REGRESSION_RATIO_LIMIT:.1f}x, "
        f"fixture={_DESIGN_COUNT} designs)"
    )

    assert ratio < _REGRESSION_RATIO_LIMIT, (
        f"two-pass lock-hold P50 = {two_pass_p50 * 1000:.1f} ms vs "
        f"legacy P50 = {legacy_p50 * 1000:.1f} ms "
        f"(ratio={ratio:.2f}x, limit<{_REGRESSION_RATIO_LIMIT:.1f}x).\n"
        f"legacy distribution (ms, sorted): "
        f"{sorted(round(d * 1000, 1) for d in legacy_durations)}\n"
        f"two-pass distribution (ms, sorted): "
        f"{sorted(round(d * 1000, 1) for d in two_pass_durations)}\n"
        f"fixture: {_DESIGN_COUNT} designs, {_RUNS_PER_FLOW} runs/flow"
    )
