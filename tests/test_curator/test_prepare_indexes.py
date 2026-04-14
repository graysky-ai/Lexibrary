"""Unit tests for ``Coordinator._prepare_indexes`` (curator-freshness 1.7).

Covers the five scenarios enumerated in the ``curator-index-preparation``
delta spec:

(i)   Both DBs present and clean --- ``_prepare_indexes`` is a no-op:
      neither ``refresh_file`` nor ``build_index`` is invoked, and no
      write occurs against ``.lexibrary/index.db`` or
      ``.lexibrary/symbols.db``.  The drift-hash cache is populated for
      every walked design so ``_collect_staleness`` can reuse it.

(ii)  Both DBs absent --- the method log-and-skips with a ``logger.info``
      telemetry line and returns early; no refresh/build calls are made.

(iii) Drifted source with both DBs present --- the symbol-graph refresh
      AND the link-graph rebuild both fire, and the rebuild is scoped to
      the drifted source.

(iv)  Drifted source with ``symbols.db`` absent --- ``refresh_file`` is
      skipped (with a telemetry note) but ``build_index`` still runs for
      the drifted slice.  ``build_symbol_graph`` is NEVER invoked --- this
      is an explicit spec invariant ("SHALL NOT call
      ``symbolgraph.builder.build_symbol_graph``").

(v)   ``scope=file_path`` --- only the design that mirrors that single
      source is walked.  A sibling design whose source has also drifted
      is ignored and contributes no drift-hash entry and no refresh call.

Every test monkey-patches ``lexibrary.symbolgraph.builder.refresh_file``
and ``lexibrary.linkgraph.builder.build_index`` at the module where
``_prepare_indexes`` re-imports them (local imports inside the method).
This avoids invoking the real symbol-graph and link-graph builders,
which would require a fully-populated ``symbols.db`` / ``index.db``
schema that is far out of scope for a unit test.

The fixture design-file writer reuses the minimal-footer helper pattern
introduced for ``test_prepare_indexes_perf.py`` --- only the ``source``
and ``source_hash`` footer fields are needed for ``_prepare_indexes``.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from lexibrary.ast_parser import compute_hashes
from lexibrary.config.schema import LexibraryConfig
from lexibrary.curator.coordinator import Coordinator

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _write_minimal_design(
    design_path: Path,
    source_rel: str,
    source_hash: str,
) -> None:
    """Write a design file with only the footer ``_prepare_indexes`` reads.

    Mirrors the footer-only helper used by
    ``tests/test_curator/test_prepare_indexes_perf.py``: ``_prepare_indexes``
    only consults ``metadata.source`` and ``metadata.source_hash``, so
    frontmatter, enrichment sections, and dependency blocks are all
    unnecessary and slow down fixture setup.
    """
    design_path.parent.mkdir(parents=True, exist_ok=True)
    generated_iso = datetime.now(UTC).isoformat()
    footer = (
        "<!-- lexibrary:meta\n"
        f"source: {source_rel}\n"
        f"source_hash: {source_hash}\n"
        "design_hash: prepare-indexes-test-fixture\n"
        f"generated: {generated_iso}\n"
        "generator: test-fixture\n"
        "-->\n"
    )
    design_path.write_text(f"# {source_rel}\n\n{footer}", encoding="utf-8")


def _seed_source_and_design(
    project_root: Path,
    rel: str,
    *,
    drifted: bool,
) -> tuple[Path, Path]:
    """Seed a single (source, design) pair under ``project_root``.

    When ``drifted`` is ``True`` the design footer is written with a
    deliberately wrong ``source_hash`` so ``_prepare_indexes`` records
    the source as drifted.  When ``False`` the footer hash matches the
    on-disk source so the source is clean.

    Returns the ``(source_path, design_path)`` tuple for the caller to
    assert against.
    """
    source_abs = project_root / rel
    source_abs.parent.mkdir(parents=True, exist_ok=True)
    source_abs.write_text(f"stub source for {rel}\n", encoding="utf-8")

    real_source_hash, _ = compute_hashes(source_abs)
    footer_hash = real_source_hash if not drifted else "deadbeef" * 8

    designs_dir = project_root / ".lexibrary" / "designs"
    designs_dir.mkdir(parents=True, exist_ok=True)
    design_path = designs_dir / f"{rel}.md"
    _write_minimal_design(design_path, rel, footer_hash)
    return source_abs, design_path


def _touch_db(project_root: Path, name: str) -> Path:
    """Create an empty sentinel DB file.

    ``_prepare_indexes`` gates on ``.exists()`` for both ``symbols.db``
    and ``index.db``; an empty file is enough to flip the guard.
    """
    db_path = project_root / ".lexibrary" / name
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_bytes(b"")
    return db_path


# ---------------------------------------------------------------------------
# Call-tracking doubles for the external index builders
# ---------------------------------------------------------------------------


class _CallRecorder:
    """Tiny callable spy used to stand in for ``refresh_file`` / ``build_index``.

    Records every invocation as a ``(args, kwargs)`` tuple so tests can
    assert specific call counts, paths, and keyword arguments without
    pulling in ``unittest.mock``.  Raising behaviour is opt-in for the
    parse-error scenario.
    """

    def __init__(self, *, raise_exc: Exception | None = None) -> None:
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
        self._raise_exc = raise_exc

    def __call__(self, *args: object, **kwargs: object) -> None:
        self.calls.append((args, kwargs))
        if self._raise_exc is not None:
            raise self._raise_exc


@pytest.fixture()
def patch_builders(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, _CallRecorder]]:
    """Patch ``refresh_file`` and ``build_index`` with ``_CallRecorder`` spies.

    Both spies are attached to the modules where ``_prepare_indexes``
    imports them (``lexibrary.symbolgraph.builder`` and
    ``lexibrary.linkgraph.builder``).  ``_prepare_indexes`` imports these
    locally inside the method body, so patching the module attribute is
    sufficient --- the coordinator module itself never holds a reference.

    Yields a dict with ``"refresh_file"`` and ``"build_index"`` keys so
    tests can inspect ``.calls`` after invoking ``_prepare_indexes``.
    """
    refresh_spy = _CallRecorder()
    build_spy = _CallRecorder()
    monkeypatch.setattr(
        "lexibrary.symbolgraph.builder.refresh_file",
        refresh_spy,
    )
    monkeypatch.setattr(
        "lexibrary.linkgraph.builder.build_index",
        build_spy,
    )

    # Also guard the spec invariant "SHALL NOT call build_symbol_graph"
    # by swapping in a spy that fails loudly if ever invoked.
    def _forbidden_full_build(*args: object, **kwargs: object) -> None:  # noqa: ARG001
        msg = "build_symbol_graph must not be invoked by _prepare_indexes"
        raise AssertionError(msg)

    monkeypatch.setattr(
        "lexibrary.symbolgraph.builder.build_symbol_graph",
        _forbidden_full_build,
    )
    yield {"refresh_file": refresh_spy, "build_index": build_spy}


# ---------------------------------------------------------------------------
# Scenario (i): both DBs present and clean -> no-op
# ---------------------------------------------------------------------------


class TestScenarioCleanNoOp:
    """Both DBs exist, every source hash matches frontmatter --- no-op."""

    def test_no_refresh_calls_and_drift_cache_populated(
        self,
        tmp_path: Path,
        patch_builders: dict[str, _CallRecorder],
    ) -> None:
        """No refresh/build calls; drift-hash cache still populated.

        Populating the cache even on a clean run is the explicit
        "Drift-hash cache shared with staleness collect" requirement ---
        ``_collect_staleness`` must be able to reuse the hashes on every
        pipeline invocation, not just when drift happens.
        """
        project_root = tmp_path / "project"
        project_root.mkdir()

        _touch_db(project_root, "symbols.db")
        _touch_db(project_root, "index.db")

        source_a, _ = _seed_source_and_design(project_root, "src/a.txt", drifted=False)
        source_b, _ = _seed_source_and_design(project_root, "src/b.txt", drifted=False)

        coordinator = Coordinator(project_root, LexibraryConfig())
        coordinator._prepare_indexes()

        assert patch_builders["refresh_file"].calls == []
        assert patch_builders["build_index"].calls == []

        # The cache carries one entry per clean source so the staleness
        # collector can skip ``compute_hashes`` later in the pipeline.
        assert set(coordinator._drift_hashes.keys()) == {source_a, source_b}

    def test_no_writes_to_either_db(
        self,
        tmp_path: Path,
        patch_builders: dict[str, _CallRecorder],  # noqa: ARG002
    ) -> None:
        """No bytes written to ``symbols.db`` or ``index.db`` on clean run.

        Captures the file sizes before and after to prove the guard-rail.
        Any accidental ``refresh_file`` / ``build_index`` invocation would
        also fail the previous assertion --- this test is the stronger
        side-effect-free guarantee.
        """
        project_root = tmp_path / "project"
        project_root.mkdir()

        symbols_db = _touch_db(project_root, "symbols.db")
        index_db = _touch_db(project_root, "index.db")
        symbols_mtime_before = symbols_db.stat().st_mtime_ns
        index_mtime_before = index_db.stat().st_mtime_ns

        _seed_source_and_design(project_root, "src/a.txt", drifted=False)

        coordinator = Coordinator(project_root, LexibraryConfig())
        coordinator._prepare_indexes()

        assert symbols_db.stat().st_mtime_ns == symbols_mtime_before
        assert index_db.stat().st_mtime_ns == index_mtime_before


# ---------------------------------------------------------------------------
# Scenario (ii): both DBs absent -> log-and-skip
# ---------------------------------------------------------------------------


class TestScenarioBothDBsAbsent:
    """Neither ``symbols.db`` nor ``index.db`` exists --- log-and-skip."""

    def test_logs_and_skips_without_raising(
        self,
        tmp_path: Path,
        patch_builders: dict[str, _CallRecorder],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Method returns cleanly, logs a telemetry note, no builder calls.

        The spec text requires "log-and-skip without raising" ---
        ``_prepare_indexes`` must still populate no drift-hash entries
        (we never walked the designs) and must not invoke either builder
        because there are no indexes to refresh.
        """
        project_root = tmp_path / "project"
        project_root.mkdir()

        # Seed at least one (source, design) pair so the designs_dir
        # existence branch doesn't cause an earlier return --- we want to
        # prove the DB-absent branch short-circuits specifically.
        _seed_source_and_design(project_root, "src/a.txt", drifted=True)

        coordinator = Coordinator(project_root, LexibraryConfig())

        with caplog.at_level(logging.INFO, logger="lexibrary.curator.coordinator"):
            coordinator._prepare_indexes()

        assert patch_builders["refresh_file"].calls == []
        assert patch_builders["build_index"].calls == []

        # Log message must reference the bootstrap hint so operators
        # know how to recover.  Guards against future refactors that
        # silently drop the telemetry line.
        assert any(
            "symbols.db and index.db both absent" in record.message for record in caplog.records
        )
        assert any("lexictl update" in record.message for record in caplog.records)

        # The designs walk short-circuits before any hash compute, so the
        # drift-hash cache stays empty --- ``_collect_staleness`` will
        # fall back to direct ``compute_hashes`` per task 1.5's
        # "fallback path" requirement.
        assert coordinator._drift_hashes == {}


# ---------------------------------------------------------------------------
# Scenario (iii): drifted source + both DBs present -> both refreshed
# ---------------------------------------------------------------------------


class TestScenarioDriftedBothDBsPresent:
    """At least one source drifted --- both indexes get refreshed."""

    def test_refresh_and_build_both_invoked_with_drifted_paths(
        self,
        tmp_path: Path,
        patch_builders: dict[str, _CallRecorder],
    ) -> None:
        """``refresh_file`` called per-source; ``build_index`` called with slice.

        Drift is seeded by writing the design footer with a wrong
        ``source_hash``.  The coordinator should detect the mismatch,
        add the source to ``drifted_sources``, and dispatch both the
        symbol-graph and link-graph refresh paths.
        """
        project_root = tmp_path / "project"
        project_root.mkdir()

        _touch_db(project_root, "symbols.db")
        _touch_db(project_root, "index.db")

        source_drifted, _ = _seed_source_and_design(
            project_root,
            "src/drifted.txt",
            drifted=True,
        )
        source_clean, _ = _seed_source_and_design(
            project_root,
            "src/clean.txt",
            drifted=False,
        )

        coordinator = Coordinator(project_root, LexibraryConfig())
        coordinator._prepare_indexes()

        # Symbol refresh is called exactly once --- only for the drifted
        # source.  The clean source must not appear in the call list.
        assert len(patch_builders["refresh_file"].calls) == 1
        refresh_args, _ = patch_builders["refresh_file"].calls[0]
        # Signature: ``refresh_file(project_root, config, file_path)``.
        assert refresh_args[0] == project_root
        assert refresh_args[2] == source_drifted

        # Link-graph rebuild fires once with the drifted slice as
        # ``changed_paths``.  The ``build_index`` signature is
        # ``build_index(project_root, changed_paths=...)`` so we assert
        # on the kwarg.
        assert len(patch_builders["build_index"].calls) == 1
        build_args, build_kwargs = patch_builders["build_index"].calls[0]
        assert build_args[0] == project_root
        assert build_kwargs["changed_paths"] == [source_drifted]

        # Drift-hash cache holds entries for BOTH sources --- every
        # walked source is cached, drift status is orthogonal.
        assert source_drifted in coordinator._drift_hashes
        assert source_clean in coordinator._drift_hashes


# ---------------------------------------------------------------------------
# Scenario (iv): drifted source + symbols.db absent -> link graph only
# ---------------------------------------------------------------------------


class TestScenarioSymbolsDBAbsent:
    """Drift with ``symbols.db`` absent --- link graph only, telemetry logged."""

    def test_link_graph_refreshes_symbol_refresh_skipped_with_log(
        self,
        tmp_path: Path,
        patch_builders: dict[str, _CallRecorder],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """``refresh_file`` skipped; ``build_index`` still runs; log note emitted.

        This is a strictly stronger assertion than "no ``refresh_file``
        calls": the spec forbids falling through to
        ``build_symbol_graph`` under any condition, so our
        ``patch_builders`` fixture also installs a tripwire on that
        symbol.  If the coordinator ever regresses into calling the
        full rebuild, this test fails via ``AssertionError`` inside the
        tripwire rather than a silent pass.
        """
        project_root = tmp_path / "project"
        project_root.mkdir()

        # Only index.db exists --- symbols.db is deliberately absent.
        _touch_db(project_root, "index.db")
        (project_root / ".lexibrary" / "symbols.db").unlink(missing_ok=True)

        source_drifted, _ = _seed_source_and_design(
            project_root,
            "src/drifted.txt",
            drifted=True,
        )

        coordinator = Coordinator(project_root, LexibraryConfig())

        with caplog.at_level(logging.INFO, logger="lexibrary.curator.coordinator"):
            coordinator._prepare_indexes()

        # Per-file symbol refresh is skipped (no symbols.db to patch).
        assert patch_builders["refresh_file"].calls == []

        # Link-graph rebuild still runs for the drifted slice.
        assert len(patch_builders["build_index"].calls) == 1
        _, build_kwargs = patch_builders["build_index"].calls[0]
        assert build_kwargs["changed_paths"] == [source_drifted]

        # Telemetry: the "symbols.db absent" log must reference both the
        # skip action and the continued link-graph rebuild so operators
        # understand the partial-refresh semantics.
        assert any(
            "symbols.db absent" in record.message
            and "Link graph rebuild will still run" in record.message
            for record in caplog.records
        )


# ---------------------------------------------------------------------------
# Scenario (v): scope=file_path -> walks only that file's design
# ---------------------------------------------------------------------------


class TestScenarioScopedSingleFile:
    """``scope=file_path`` restricts the walk to a single source's design."""

    def test_only_scoped_design_walked(
        self,
        tmp_path: Path,
        patch_builders: dict[str, _CallRecorder],
    ) -> None:
        """Out-of-scope drifted design is ignored; drift-hash cache scoped.

        Seeds TWO drifted sources --- the scoped one and an out-of-scope
        sibling.  After the scoped call, only the scoped source should
        appear in ``refresh_file`` calls, ``build_index.changed_paths``,
        and ``_drift_hashes``.  The sibling must be completely
        invisible to the preparation phase.
        """
        project_root = tmp_path / "project"
        project_root.mkdir()

        _touch_db(project_root, "symbols.db")
        _touch_db(project_root, "index.db")

        source_in_scope, _ = _seed_source_and_design(
            project_root,
            "src/in_scope.txt",
            drifted=True,
        )
        source_out_of_scope, _ = _seed_source_and_design(
            project_root,
            "src/out_of_scope.txt",
            drifted=True,
        )

        coordinator = Coordinator(project_root, LexibraryConfig())
        coordinator._prepare_indexes(scope=source_in_scope)

        # Exactly one refresh call, and it must target the scoped source.
        assert len(patch_builders["refresh_file"].calls) == 1
        refresh_args, _ = patch_builders["refresh_file"].calls[0]
        assert refresh_args[2] == source_in_scope

        # ``build_index`` receives only the scoped source in its
        # ``changed_paths`` --- the out-of-scope source's drift is
        # invisible to this preparation pass.
        assert len(patch_builders["build_index"].calls) == 1
        _, build_kwargs = patch_builders["build_index"].calls[0]
        assert build_kwargs["changed_paths"] == [source_in_scope]

        # Drift-hash cache mirrors the scope: the sibling's hash is
        # NOT computed because its design is filtered out before the
        # ``compute_hashes`` branch runs.
        assert source_in_scope in coordinator._drift_hashes
        assert source_out_of_scope not in coordinator._drift_hashes
