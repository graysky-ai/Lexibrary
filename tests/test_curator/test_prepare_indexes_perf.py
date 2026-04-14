"""Benchmark test for ``Coordinator._prepare_indexes`` warm-cache runtime.

Task 1.6 of the ``curator-freshness`` change: confirm the prepare-indexes
pass stays within its performance envelope on a library with ~1000 design
files when the file-mtime cache is warm.

The benchmark seeds a ``tmp_path`` library with 1000 synthetic design files
(minimal footer only — no real source code, no frontmatter body beyond
what :func:`parse_design_file_metadata` needs) and 1000 matching source
stubs whose on-disk ``source_hash`` matches the footer.  A single
untimed warmup call populates ``Coordinator._mtime_cache`` and
``Coordinator._drift_hashes``; subsequent timed calls exercise the
warm-cache branch exclusively (``compute_hashes`` is never invoked
because the source mtime is unchanged AND the cached source hash matches
the frontmatter).

P95 runtime across the timed runs must be ≤ 200 ms.  Exceeding the
budget fails the test with the full latency distribution inline so CI
has actionable context without re-running the benchmark locally.

The test is marked ``pytest.mark.benchmark`` so CI (and developers
iterating on unrelated curator code) can opt out via ``-m 'not
benchmark'``.  Run with ``-m benchmark`` to exercise it in isolation.
"""

from __future__ import annotations

import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from lexibrary.ast_parser import compute_hashes
from lexibrary.config.schema import LexibraryConfig
from lexibrary.curator.coordinator import Coordinator

# Benchmark tuning constants.  Kept at module scope so CI operators can
# trace the exact envelope without reading the test body.
_DESIGN_COUNT = 1000
_WARMUP_RUNS = 1
_TIMED_RUNS = 10
_P95_BUDGET_MS = 200.0


def _write_minimal_design(design_path: Path, source_rel: str, source_hash: str) -> None:
    """Write a design file with only the footer ``parse_design_file_metadata`` needs.

    The full :mod:`lexibrary.artifacts.design_file_serializer` pipeline
    writes frontmatter, enrichment sections, dependency blocks, and more —
    none of which ``_prepare_indexes`` reads.  Skipping it shrinks fixture
    setup from seconds to tens of milliseconds while still producing a
    file the parser accepts.
    """
    design_path.parent.mkdir(parents=True, exist_ok=True)
    generated_iso = datetime.now(UTC).isoformat()
    # ``_FOOTER_RE`` is ``<!-- lexibrary:meta\n{body}\n-->``.  Body is
    # YAML-ish ``key: value`` lines; ``_parse_footer`` accepts trailing
    # whitespace and ignores unknown keys.  ``design_hash`` and
    # ``generator`` are required to pass ``StalenessMetadata`` construction
    # but ``_prepare_indexes`` only reads ``source`` and ``source_hash``.
    footer = (
        "<!-- lexibrary:meta\n"
        f"source: {source_rel}\n"
        f"source_hash: {source_hash}\n"
        "design_hash: benchmark-fixture\n"
        f"generated: {generated_iso}\n"
        "generator: test-fixture\n"
        "-->\n"
    )
    design_path.write_text(f"# {source_rel}\n\n{footer}", encoding="utf-8")


def _seed_fixture(project_root: Path, count: int) -> None:
    """Seed ``count`` synthetic (source, design) pairs under ``project_root``.

    Sources are ``.txt`` stubs (no grammar → :func:`compute_hashes` takes
    only the content-hash path, keeping fixture setup fast).  Each design's
    footer ``source_hash`` is the real on-disk hash so the first
    ``_prepare_indexes`` call reports zero drift and the timed runs hit
    the warm-cache branch end-to-end.
    """
    (project_root / ".lexibrary").mkdir()
    designs_dir = project_root / ".lexibrary" / "designs"
    designs_dir.mkdir()
    # Writing a placeholder ``index.db`` avoids the scenario-(ii) early
    # return where both DBs are absent — that branch skips the workload
    # we want to measure.  An empty file is enough; ``_prepare_indexes``
    # only checks ``.exists()``.
    (project_root / ".lexibrary" / "index.db").write_bytes(b"")

    src_root = project_root / "src"
    src_root.mkdir()

    for idx in range(count):
        # Spread sources across a handful of sub-packages so ``rglob``
        # walks a realistic directory tree rather than a single flat
        # folder of 1000 entries.
        pkg = f"pkg_{idx // 100:02d}"
        rel = f"src/{pkg}/mod_{idx:04d}.txt"
        source_abs = project_root / rel
        source_abs.parent.mkdir(parents=True, exist_ok=True)
        # Content varies per-file so ``source_hash`` is unique and the
        # cache really is keyed by path rather than accidentally sharing
        # hash entries.
        source_abs.write_text(f"stub module {idx}\n", encoding="utf-8")

        source_hash, _ = compute_hashes(source_abs)
        design_path = designs_dir / f"{rel}.md"
        _write_minimal_design(design_path, rel, source_hash)


@pytest.mark.benchmark
def test_prepare_indexes_warm_cache_p95_under_200ms(tmp_path: Path) -> None:
    """P95 warm-cache ``_prepare_indexes`` runtime ≤ 200 ms for 1000 designs.

    Fails with the full timing distribution so a regression is
    diagnosable from CI logs alone.
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    _seed_fixture(project_root, _DESIGN_COUNT)

    config = LexibraryConfig()
    coordinator = Coordinator(project_root, config)

    # Warmup populates ``_mtime_cache`` + ``_drift_hashes`` so every
    # subsequent run exercises the warm branch.  Without this, the first
    # timed run would skew the distribution by paying the cold-path
    # ``compute_hashes`` cost for every file.
    for _ in range(_WARMUP_RUNS):
        coordinator._prepare_indexes()

    # Sanity-check that the warmup actually populated the cache; without
    # this the benchmark could silently pass by running the cold path if
    # the cache invariant ever regresses.
    assert len(coordinator._drift_hashes) == _DESIGN_COUNT, (
        f"warmup produced {len(coordinator._drift_hashes)} drift-hash "
        f"entries, expected {_DESIGN_COUNT}"
    )
    assert len(coordinator._mtime_cache) == _DESIGN_COUNT, (
        f"warmup produced {len(coordinator._mtime_cache)} mtime-cache "
        f"entries, expected {_DESIGN_COUNT}"
    )

    durations_ms: list[float] = []
    for _ in range(_TIMED_RUNS):
        start = time.perf_counter()
        coordinator._prepare_indexes()
        durations_ms.append((time.perf_counter() - start) * 1000.0)

    # ``statistics.quantiles`` with ``n=20`` yields a P95 at index 18
    # (0-based), matching the standard "95th percentile" definition used
    # in perf dashboards.  Fall back to ``max`` when we have fewer runs
    # than ``quantiles`` can handle.
    if len(durations_ms) >= 20:
        p95_ms = statistics.quantiles(durations_ms, n=20)[18]
    else:
        sorted_ms = sorted(durations_ms)
        # Standard nearest-rank P95: ceil(0.95 * N) - 1.
        idx = max(0, int(0.95 * len(sorted_ms)) - 1)
        p95_ms = sorted_ms[idx] if sorted_ms else 0.0

    assert p95_ms <= _P95_BUDGET_MS, (
        f"_prepare_indexes warm-cache P95 = {p95_ms:.1f} ms exceeds "
        f"budget {_P95_BUDGET_MS:.1f} ms over {_TIMED_RUNS} runs on "
        f"{_DESIGN_COUNT} designs.\n"
        f"distribution (ms, sorted): "
        f"{sorted(round(d, 1) for d in durations_ms)}"
    )
