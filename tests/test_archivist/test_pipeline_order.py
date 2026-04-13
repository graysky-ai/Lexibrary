"""Pipeline order verification tests for the symbol-graph-5 reorder.

This file is the deliverable of symbol-graph-5 task group 1. The group is a
read-only audit of ``update_project()`` that confirms the symbol graph build
can safely move from its current position (Step 10, the last step of the
function) to a new position before the design-file generation loop. The
tests below encode the expected post-audit order; they are ``xfail`` until
group 5 implements the reorder.

Audit note
==========

Goal
----

Phase 5 needs the symbol graph to be up-to-date **before** the design-file
generation loop so ``render_symbol_graph_context`` can pull enum and call-
path blocks for each file's prompt. Today ``build_symbol_graph`` runs as
Step 10 of ``update_project()`` — the last step, after design files are
already written. Moving it is only safe if none of the intervening steps
depend on the symbol graph being stale (i.e., matching the not-yet-updated
design files), and none of them depend on design files from the current run
to build the symbol graph. The audit checked every step between the current
symbol-graph position and the design-file loop and found no such
dependency: the reorder is safe.

Current order (pre-reorder), as written in ``update_project``
-------------------------------------------------------------

1.   Load available artifact names (concepts/conventions/playbooks).
2.   ``discover_source_files(project_root, config)``.
3.   (implicit) Initialise ``changed_file_paths: list[Path]``.
4.   **Design-file generation loop** — ``for source_path in source_files``
     calling ``await update_file(...)`` sequentially. Each ``update_file``
     writes a design file and calls
     ``symbolgraph.builder.refresh_file(project_root, config, source_path)``
     at its own Step 11. ``refresh_file`` is a no-op when ``symbols.db``
     does not yet exist (guard at :func:`refresh_file`), so on a clean
     project the per-file refresh today effectively does nothing.
5.   ``reindex_directories(affected_dirs, project_root, config)`` — writes
     ``.aindex`` files for changed directories and their ancestors. Reads
     source files and existing design files; does not read or write
     ``symbols.db``.
6.   ``generate_raw_topology(project_root)`` — reads ``.aindex`` files and
     writes ``.lexibrary/tmp/raw-topology.md``. Does not read or write
     ``symbols.db``.
7.   ``_run_deprecation_pass(project_root, config, stats)`` — detects
     renames, orphans, deprecation/unlinked status, TTL expiry. Reads
     design files and lifecycle state; does not read or write
     ``symbols.db``. (Verified with a project-wide grep for
     ``symbol_graph``/``symbols.db``/``symbols_db`` in
     ``src/lexibrary/lifecycle/`` — zero hits.)
8.   ``await _process_enrichment_queue(project_root, config, archivist,
     stats)`` — reads the skeleton enrichment queue and recursively calls
     ``update_file`` for each entry. Like the main loop, each
     ``update_file`` invokes ``refresh_file``. Does not otherwise touch
     ``symbols.db``.
9.   ``build_index(project_root)`` — full rebuild of the link graph. Reads
     design files, concepts, conventions, playbooks, and writes
     ``.lexibrary/index.db``. Does not read or write ``symbols.db``.
10.  ``build_symbol_graph(project_root, config)`` — full rebuild of the
     symbol graph. Reads source files (via ``discover_source_files``) and
     writes ``.lexibrary/symbols.db``. **Does not read design files.**

Key correction vs. the group 5 task instructions
-------------------------------------------------

The symbol-graph-5 task document says the link graph build (``build_index``,
Step 9) runs **before** the design-file loop, and instructs group 5 to
place the symbol graph build "immediately after the link graph build" while
also placing it "BEFORE the design-file generation loop". Those two
constraints are only consistent if the link graph build is already
positioned before the loop — but in the real code, ``build_index`` runs at
Step 9, **after** the design-file loop (and after re-indexing, topology,
deprecation, and the enrichment queue). The same late positioning holds in
``update_files()`` and ``update_directory()``.

Group 5 must choose between two interpretations:

**Interpretation A — minimal move (recommended).** Only ``build_symbol_graph``
moves; it slots in before the design-file loop at the point where
``discover_source_files`` is called and before the ``for source_path in
source_files`` loop. ``build_index`` stays at its current late position.
This is the literal reading of "DO NOT change the link graph build
position" and is sufficient to make ``symbols.db`` fresh for the enrichment
helper — the enrichment helper only needs the symbol graph, not the link
graph. **The ``xfail`` tests in this file encode this interpretation.**

**Interpretation B — move both.** Move ``build_index`` up to Step 3.5 (before
the loop) and then ``build_symbol_graph`` at Step 3.6. This contradicts
"DO NOT change the link graph build position" and would also change when
the link graph incorporates newly-written design files: today it runs
after design files are regenerated, so it sees the new artefacts and their
outbound wikilinks. Moving it before the loop would mean the link graph
reflects the *pre-update* design files for one run, which is a behaviour
regression for any downstream consumer that relies on link-graph freshness
inside the same ``update_project`` call. The audit therefore recommends
against Interpretation B.

The group 5 agent should pick Interpretation A and, if the task document
needs clarification, rewrite the "immediately after the link graph build"
sentence to simply say "before the ``for source_path in source_files``
loop (around Step 3.5)".

Step-by-step dependency audit (Steps 5-9)
-----------------------------------------

For each step between the design-file loop (Step 4) and the symbol graph
build (Step 10) we document:
  (a) what state it reads,
  (b) what state it writes,
  (c) whether any read depends on the symbol graph being up-to-date,
  (d) whether any read depends on design files from the *current* run.

Step 5 — ``reindex_directories``
    (a) Reads source files, existing design files, and the filesystem tree
        rooted at ``config.scope_root``.
    (b) Writes ``.aindex`` files for each affected directory and each
        ancestor up to ``scope_root``.
    (c) No dependency on ``symbols.db``. ``index_directory`` never opens
        it.
    (d) Reads design files written by the **current** run so their
        frontmatter descriptions are reflected in the ``.aindex`` billboard
        summaries. This is a dependency on design files, **not** on the
        symbol graph — moving the symbol graph build does not disturb it
        because the design-file loop still runs before ``reindex``.

Step 6 — ``generate_raw_topology``
    (a) Reads the ``.aindex`` files written in Step 5.
    (b) Writes ``.lexibrary/tmp/raw-topology.md``.
    (c) No dependency on ``symbols.db``.
    (d) Transitively reads current-run design file data via the ``.aindex``
        files refreshed in Step 5. Again a design-file dependency, not a
        symbol-graph dependency.

Step 7 — ``_run_deprecation_pass``
    (a) Reads git metadata for rename detection, design files in
        ``.lexibrary/designs/``, concept/convention/playbook indexes for
        TTL sweeps, and lifecycle state.
    (b) Moves/renames design files, flips deprecation / unlinked
        frontmatter, deletes TTL-expired artefacts.
    (c) No dependency on ``symbols.db``. A grep for
        ``symbol_graph``/``symbols.db``/``symbols_db`` under
        ``src/lexibrary/lifecycle/`` returns zero hits.
    (d) Reads design files from the current run (to decide orphan/rename
        status). No symbol-graph dependency.

Step 8 — ``_process_enrichment_queue``
    (a) Reads ``.lexibrary/tmp/enrichment_queue.jsonl`` and, for each
        entry, re-runs ``update_file``. Each ``update_file`` invokes
        ``refresh_file`` on the symbol graph — a no-op when the DB is
        absent, an incremental patch when present.
    (b) Writes regenerated design files and (if ``symbols.db`` exists)
        patches the file's rows inside it.
    (c) ``refresh_file`` **reads** ``symbols.db`` but only to mutate its
        own file's rows. It does not require the DB to be "fresh" in any
        global sense — it is tolerant of stale edges because it reruns the
        Python resolver for every call in the refreshed file. The reorder
        therefore simply means ``refresh_file`` now runs against a
        freshly-built DB instead of (today) an absent or stale DB.
    (d) Reads current-run design files for change detection inside
        ``update_file``. No current-run symbol-graph dependency.

Step 9 — ``build_index`` (link graph)
    (a) Reads design files, concepts, conventions, playbooks.
    (b) Writes ``.lexibrary/index.db``.
    (c) No dependency on ``symbols.db``. The link graph and symbol graph
        are independent indices; ``IndexBuilder`` in
        ``src/lexibrary/linkgraph/builder.py`` never opens ``symbols.db``.
    (d) Reads design files from the current run to build artefact↔link
        rows. No symbol-graph dependency. **This is the main reason the
        audit recommends Interpretation A:** ``build_index`` must keep
        running after the design-file loop so it sees freshly-written
        design-file wikilinks; moving it earlier would make the link
        graph reflect one-run-stale data.

Design-file-loop concurrency
----------------------------

``update_project`` processes source files with a plain ``for`` loop
(``for source_path in source_files: await update_file(...)``), not an
``asyncio.gather`` or ``TaskGroup``. Every iteration awaits sequentially,
so the ``SymbolQueryService`` that group 5 opens around the loop will
only ever be touched by one coroutine at a time. Group 5 can therefore
call ``render_symbol_graph_context`` synchronously (no ``asyncio.to_thread``
wrapper needed) while keeping the existing single-connection
``SymbolQueryService`` shape. If the loop later adopts concurrent tasks
via ``asyncio.gather`` or ``TaskGroup`` the render calls must be wrapped
in ``asyncio.to_thread`` — but that is not a group 5 concern.

Conclusion
----------

None of Steps 5-9 read or write ``symbols.db`` in a way that requires it to
match the design-file state of the current run. Several steps do depend on
current-run **design files**, but design files themselves are generated in
Step 4, which already runs before Steps 5-9 both pre- and post-reorder.

The reorder therefore has a single observable effect on downstream steps:
``refresh_file`` (called inside every ``update_file``) transitions from a
no-op (DB absent on first run) or stale-snapshot patch (DB present but
older than the current loop) into an incremental patch against the
just-built DB. That is strictly an improvement — ``lexi trace`` /
``lexi lookup`` calls made during a long-running ``update_project`` session
now see fresh symbol rows for every file as soon as its design file is
regenerated.

Expected post-reorder order (enforced by the tests in this file)
----------------------------------------------------------------

Under Interpretation A:

1.  Load available artifact names.
2.  Discover source files.
3.  **Build symbol graph** (``build_symbol_graph``) — MOVED here from
    Step 10.
4.  Design-file generation loop (``update_file`` × N) — now runs with a
    fresh ``symbols.db`` available for enrichment.
5.  Re-index directories (``reindex_directories``).
6.  Generate raw topology (``generate_raw_topology``).
7.  Deprecation lifecycle pass (``_run_deprecation_pass``).
8.  Enrichment queue pass (``_process_enrichment_queue``).
9.  Build link graph (``build_index``) — **unchanged position**, still
    runs at the end so it sees fresh design-file wikilinks.

The tests below monkeypatch the pipeline's step seams and record invocation
order into a shared list. ``test_pipeline_builds_symbol_graph_before_design_files``
is the simple two-way order check. ``test_pipeline_order_preserves_existing_steps``
asserts the full nine-step sequence above. Both are marked ``xfail`` until
symbol-graph-5 task group 5 implements the reorder.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lexibrary.archivist.change_checker import ChangeLevel
from lexibrary.archivist.pipeline import FileResult, update_project
from lexibrary.archivist.service import ArchivistService, DesignFileResult
from lexibrary.baml_client.types import DesignFileOutput
from lexibrary.config.schema import LexibraryConfig, ScopeRoot, TokenBudgetConfig
from lexibrary.symbolgraph.builder import SymbolBuildResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_source_file(tmp_path: Path, rel: str, content: str = "def foo(): pass") -> Path:
    """Create a source file at *rel* relative to *tmp_path*."""
    source = tmp_path / rel
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(content, encoding="utf-8")
    return source


def _make_config(scope_root: str = ".") -> LexibraryConfig:
    """Create a LexibraryConfig with a single scope root and small token budget."""
    return LexibraryConfig(
        scope_roots=[ScopeRoot(path=scope_root)],
        token_budgets=TokenBudgetConfig(design_file_tokens=400),
    )


def _mock_archivist() -> ArchivistService:
    """Create a mock ArchivistService with a canned design-file output."""
    output = DesignFileOutput(
        summary="Handles testing.",
        interface_contract="def foo(): ...",
        dependencies=[],
        tests=None,
        complexity_warning=None,
        wikilinks=[],
        tags=[],
    )
    result = DesignFileResult(
        source_path="mock",
        design_file_output=output,
        error=False,
        error_message=None,
    )
    service = MagicMock(spec=ArchivistService)
    service.generate_design_file = AsyncMock(return_value=result)
    return service


# ---------------------------------------------------------------------------
# 1. Symbol graph must run before design-file generation
# ---------------------------------------------------------------------------


class TestSymbolGraphRunsBeforeDesignFiles:
    """Symbol graph build must precede the design-file loop post-reorder."""

    @pytest.mark.asyncio()
    async def test_pipeline_builds_symbol_graph_before_design_files(
        self,
        tmp_path: Path,
    ) -> None:
        """``build_symbol_graph`` must be called before the first ``update_file``.

        Record the invocation order of the two seams via a shared list and
        assert that ``build_symbol_graph`` comes first. This is the minimal
        enforcement of the group 5 reorder — if it passes, the symbol graph
        build has been moved out of the post-loop tail position.
        """
        _make_source_file(tmp_path, "src/a.py", "def a(): pass")
        _make_source_file(tmp_path, "src/b.py", "def b(): pass")
        (tmp_path / ".lexibrary").mkdir(parents=True, exist_ok=True)

        config = _make_config(scope_root="src")
        archivist = _mock_archivist()

        call_order: list[str] = []

        def fake_build_symbol_graph(*args: object, **kwargs: object) -> SymbolBuildResult:
            call_order.append("build_symbol_graph")
            return SymbolBuildResult(build_type="full")

        async def fake_update_file(
            source_path: Path,
            project_root: Path,
            cfg: LexibraryConfig,
            svc: ArchivistService,
            **kwargs: object,
        ) -> FileResult:
            call_order.append("update_file")
            return FileResult(change=ChangeLevel.UNCHANGED)

        with (
            patch(
                "lexibrary.symbolgraph.build_symbol_graph",
                side_effect=fake_build_symbol_graph,
            ),
            patch(
                "lexibrary.archivist.pipeline.update_file",
                side_effect=fake_update_file,
            ),
        ):
            await update_project(tmp_path, config, archivist)

        # At least one update_file and exactly one build_symbol_graph must
        # have run. The symbol graph must be the first recorded call.
        assert "build_symbol_graph" in call_order
        assert "update_file" in call_order
        first_symbol_idx = call_order.index("build_symbol_graph")
        first_update_idx = call_order.index("update_file")
        assert first_symbol_idx < first_update_idx, (
            f"Expected build_symbol_graph to precede update_file, got order: {call_order}"
        )


# ---------------------------------------------------------------------------
# 2. Full expected sequence of pipeline steps
# ---------------------------------------------------------------------------


class TestPipelineOrderPreservesExistingSteps:
    """Full nine-step sequence check for ``update_project`` post-reorder."""

    @pytest.mark.asyncio()
    async def test_pipeline_order_preserves_existing_steps(
        self,
        tmp_path: Path,
    ) -> None:
        """Every named step fires in the expected post-audit order.

        Monkeypatches every seam in ``update_project`` and records each
        invocation into a shared list. Asserts the full sequence matches
        the expected post-reorder ordering documented in the module
        docstring above (Interpretation A — only the symbol graph build
        moves; everything else stays in place):

        1. symbol graph build
        2. design-file loop (one ``update_file`` per source)
        3. reindex directories
        4. raw topology generation
        5. deprecation pass
        6. enrichment queue pass
        7. link graph build — unchanged late position

        Notes
        -----
        * ``reindex_directories`` only runs when there are meaningful
          changes, so the fake ``update_file`` reports ``NEW_FILE`` to
          force the branch. Without meaningful changes the step is
          legitimately skipped and the test would see a shorter sequence.
        * The enrichment queue runs unconditionally but short-circuits
          when the queue is empty. We still monkeypatch
          ``_process_enrichment_queue`` so the seam records an invocation.
        * Two source files are created so the design-file loop contributes
          two ``update_file`` entries, confirming the whole loop happens
          before the post-loop steps.
        """
        _make_source_file(tmp_path, "src/a.py", "def a(): pass")
        _make_source_file(tmp_path, "src/b.py", "def b(): pass")
        (tmp_path / ".lexibrary").mkdir(parents=True, exist_ok=True)

        config = _make_config(scope_root="src")
        archivist = _mock_archivist()

        call_order: list[str] = []

        def fake_build_index(*args: object, **kwargs: object) -> MagicMock:
            call_order.append("build_index")
            result = MagicMock()
            result.artifact_count = 0
            result.link_count = 0
            return result

        def fake_build_symbol_graph(*args: object, **kwargs: object) -> SymbolBuildResult:
            call_order.append("build_symbol_graph")
            return SymbolBuildResult(build_type="full")

        async def fake_update_file(
            source_path: Path,
            project_root: Path,
            cfg: LexibraryConfig,
            svc: ArchivistService,
            **kwargs: object,
        ) -> FileResult:
            call_order.append("update_file")
            # Report NEW_FILE so ``_has_meaningful_changes`` is True (it
            # increments ``files_created``) and the reindex branch fires.
            return FileResult(change=ChangeLevel.NEW_FILE)

        def fake_reindex_directories(*args: object, **kwargs: object) -> int:
            call_order.append("reindex_directories")
            return 0

        def fake_generate_raw_topology(*args: object, **kwargs: object) -> Path:
            call_order.append("generate_raw_topology")
            return tmp_path / ".lexibrary" / "tmp" / "raw-topology.md"

        def fake_run_deprecation_pass(*args: object, **kwargs: object) -> None:
            call_order.append("_run_deprecation_pass")

        async def fake_process_enrichment_queue(*args: object, **kwargs: object) -> None:
            call_order.append("_process_enrichment_queue")

        with (
            patch(
                "lexibrary.archivist.pipeline.build_index",
                side_effect=fake_build_index,
            ),
            patch(
                "lexibrary.symbolgraph.build_symbol_graph",
                side_effect=fake_build_symbol_graph,
            ),
            patch(
                "lexibrary.archivist.pipeline.update_file",
                side_effect=fake_update_file,
            ),
            patch(
                "lexibrary.archivist.pipeline.reindex_directories",
                side_effect=fake_reindex_directories,
            ),
            patch(
                "lexibrary.archivist.pipeline.generate_raw_topology",
                side_effect=fake_generate_raw_topology,
            ),
            patch(
                "lexibrary.archivist.pipeline._run_deprecation_pass",
                side_effect=fake_run_deprecation_pass,
            ),
            patch(
                "lexibrary.archivist.pipeline._process_enrichment_queue",
                side_effect=fake_process_enrichment_queue,
            ),
        ):
            await update_project(tmp_path, config, archivist)

        # Collapse consecutive ``update_file`` entries into a single
        # marker so the sequence check is independent of how many source
        # files the fixture created.
        collapsed: list[str] = []
        for step in call_order:
            if step == "update_file" and collapsed and collapsed[-1] == "update_file_loop":
                continue
            collapsed.append("update_file_loop" if step == "update_file" else step)

        expected = [
            "build_symbol_graph",
            "update_file_loop",
            "reindex_directories",
            "generate_raw_topology",
            "_run_deprecation_pass",
            "_process_enrichment_queue",
            "build_index",
        ]

        assert collapsed == expected, (
            f"Unexpected pipeline step order.\nExpected: {expected}\nGot:      {collapsed}"
        )
