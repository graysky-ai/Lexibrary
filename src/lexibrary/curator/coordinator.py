"""Curator coordinator -- four-phase pipeline for automated library maintenance.

Executes a deterministic collect-triage-dispatch-report pipeline.  All LLM
judgment is delegated to sub-agent stubs (BAML integration in later groups);
the coordinator itself makes no LLM calls.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import subprocess
import time
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from lexibrary.config.schema import LexibraryConfig
from lexibrary.curator.collect_filters import _should_skip_path
from lexibrary.curator.config import CuratorConfig
from lexibrary.curator.dispatch_context import DispatchContext
from lexibrary.curator.models import (
    BudgetCollectItem,
    CollectItem,
    CollectResult,
    CommentAuditCollectItem,
    CommentCollectItem,
    CuratorReport,
    DeprecationCollectItem,
    DispatchResult,
    SubAgentResult,
    TriageItem,
    TriageResult,
)
from lexibrary.curator.risk_taxonomy import get_risk_level, should_dispatch
from lexibrary.errors import ErrorSummary
from lexibrary.utils.paths import LEXIBRARY_DIR

if TYPE_CHECKING:
    from lexibrary.wiki.resolver import WikilinkResolver

logger = logging.getLogger(__name__)

# Stale lock threshold in seconds (30 minutes).
_STALE_LOCK_SECONDS = 30 * 60

# ---------------------------------------------------------------------------
# Validation action-key routing
# ---------------------------------------------------------------------------

# Mapping from validator check names to narrow per-check curator action keys.
# Classifying validation issues this way lets honest counters and risk
# taxonomy report each fixer individually instead of rolling every validator
# auto-fix under the umbrella ``autofix_validation_issue`` key.  The mapping
# MUST stay in lock-step with the keys in
# :data:`lexibrary.validator.fixes.FIXERS`.
CHECK_TO_ACTION_KEY: dict[str, str] = {
    "hash_freshness": "fix_hash_freshness",
    "orphan_artifacts": "fix_orphan_artifacts",
    "aindex_coverage": "fix_aindex_coverage",
    "orphaned_aindex": "fix_orphaned_aindex",
    "orphaned_iwh": "fix_orphaned_iwh",
    "orphaned_designs": "fix_orphaned_designs",
    "deprecated_ttl": "fix_deprecated_ttl",
    "bidirectional_deps": "fix_bidirectional_deps",
    "duplicate_slugs": "fix_duplicate_slugs",
    "duplicate_aliases": "fix_duplicate_aliases",
    "wikilink_resolution": "fix_wikilink_resolution",
}

# Set of action keys recognised by the validation bridge router.  Includes the
# narrow per-check keys and the legacy umbrella key so triage items classified
# before the CHECK_TO_ACTION_KEY mapping was applied still reach the bridge.
VALIDATION_ACTION_KEYS: frozenset[str] = frozenset(
    set(CHECK_TO_ACTION_KEY.values()) | {"autofix_validation_issue"}
)


# ---------------------------------------------------------------------------
# Two-pass collect: hash-layer vs graph-layer validator partition
# ---------------------------------------------------------------------------

# Hash-layer checks: structural/frontmatter/token-budget checks that do NOT
# read the link graph (``index.db``) or symbol graph (``symbols.db``).  These
# are safe to run in the first collect pass — before any mid-run
# ``build_index`` rebuild — because their inputs are purely on-disk file
# contents and their frontmatter.  Per ``specs/curator-two-pass-collect``:
# frontmatter validators, ``hash_freshness``, ``token_budgets``,
# ``stale_agent_design`` form the spec-named hash-layer subset.
_HASH_LAYER_CHECKS: frozenset[str] = frozenset(
    {
        # Spec-named hash-layer subset
        "hash_freshness",
        "stale_agent_design",
        "token_budgets",
        # Frontmatter validators (the spec says "frontmatter validators" as a
        # family; enumerate them explicitly so the partition is total.)
        "concept_frontmatter",
        "convention_frontmatter",
        "design_frontmatter",
        "stack_frontmatter",
        "iwh_frontmatter",
        "playbook_frontmatter",
    }
)

# Graph-layer checks: everything else from ``AVAILABLE_CHECKS`` — the
# spec-named graph-layer subset plus all remaining checks not explicitly
# assigned to hash.  Per the spec's partitioning guidance, checks omitted
# from the spec default to graph-layer (graph-layer is the "safer" pass
# because it runs after the mid-run ``build_index`` rebuild).
_GRAPH_LAYER_CHECKS: frozenset[str] = frozenset(
    {
        # Spec-named graph-layer subset
        "bidirectional_deps",
        "orphan_artifacts",
        "orphan_concepts",
        "dangling_links",
        "wikilink_resolution",
        "aindex_coverage",
        "forward_dependencies",
        "convention_stale",
        "playbook_staleness",
        "stack_staleness",
        "design_deps_existence",
        "stack_refs_validity",
        "deprecated_concept_usage",
        "convention_orphaned_scope",
        # Remaining checks default to graph-layer per the spec's
        # "when in doubt, route to graph-layer" rule.
        "file_existence",
        "orphaned_designs",
        "resolved_post_staleness",
        "orphaned_aindex",
        "orphaned_iwh",
        "comment_accumulation",
        "deprecated_ttl",
        "stale_concept",
        "supersession_candidate",
        "convention_gap",
        "convention_consistent_violation",
        "lookup_token_budget_exceeded",
        "orphaned_iwh_signals",
        "config_valid",
        "lexignore_syntax",
        "linkgraph_version",
        "duplicate_aliases",
        "duplicate_slugs",
        "artifact_id_uniqueness",
        "aindex_entries",
        "design_structure",
        "stack_body_sections",
        "concept_body",
        "playbook_wikilinks",
        "playbook_deprecated_ttl",
    }
)


def _assert_check_partition_total_and_disjoint() -> None:
    """Assert the hash/graph partition covers every registered check once.

    Guards against drift: adding a new check to
    :data:`lexibrary.validator.AVAILABLE_CHECKS` without also adding it to
    one (and only one) of the two frozensets would silently cause the new
    check to never run in either pass of the two-pass collect.
    """
    from lexibrary.validator import AVAILABLE_CHECKS  # noqa: PLC0415

    registered = frozenset(AVAILABLE_CHECKS)
    partition = _HASH_LAYER_CHECKS | _GRAPH_LAYER_CHECKS
    overlap = _HASH_LAYER_CHECKS & _GRAPH_LAYER_CHECKS
    missing = registered - partition
    extra = partition - registered
    if overlap or missing or extra:
        msg = (
            "Two-pass collect check partition is not total/disjoint: "
            f"overlap={sorted(overlap)}, missing={sorted(missing)}, "
            f"extra={sorted(extra)}"
        )
        raise AssertionError(msg)


_assert_check_partition_total_and_disjoint()


# ---------------------------------------------------------------------------
# Concurrency lock helpers
# ---------------------------------------------------------------------------


class CuratorLockError(Exception):
    """Raised when the curator lock cannot be acquired."""


def _lock_path(project_root: Path) -> Path:
    return project_root / LEXIBRARY_DIR / "curator" / ".curator.lock"


def _read_lock(path: Path) -> tuple[int, float] | None:
    """Read PID and timestamp from lock file, or return None."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return int(data["pid"]), float(data["timestamp"])
    except (json.JSONDecodeError, KeyError, ValueError, OSError):
        return None


def _pid_alive(pid: int) -> bool:
    """Check whether a process with the given PID is still running."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we cannot signal it.
        return True
    return True


def _acquire_lock(project_root: Path) -> Path:
    """Acquire the curator PID-file lock or raise CuratorLockError."""
    lock = _lock_path(project_root)
    lock.parent.mkdir(parents=True, exist_ok=True)

    existing = _read_lock(lock)
    if existing is not None:
        pid, ts = existing
        age = time.time() - ts
        if _pid_alive(pid) and age < _STALE_LOCK_SECONDS:
            msg = (
                f"Another curator process is running (PID {pid}, started {int(age)}s ago). Exiting."
            )
            raise CuratorLockError(msg)
        # Stale or dead -- reclaim.
        logger.info("Reclaiming stale curator lock (PID %d, age %.0fs)", pid, age)

    lock.write_text(
        json.dumps({"pid": os.getpid(), "timestamp": time.time()}),
        encoding="utf-8",
    )
    return lock


def _release_lock(project_root: Path) -> None:
    """Remove the curator lock file if present."""
    lock = _lock_path(project_root)
    with contextlib.suppress(OSError):
        lock.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Design body length helper
# ---------------------------------------------------------------------------


def _design_body_length(design_path: Path) -> int:
    """Return the approximate character count of a design file's body.

    Strips YAML frontmatter and the HTML comment metadata footer so that
    only the author-visible body (headings, prose, code blocks) is counted.
    Returns 0 on any read error.
    """
    import re as _re  # noqa: PLC0415

    try:
        content = design_path.read_text(encoding="utf-8")
    except OSError:
        return 0

    body = content
    # Strip YAML frontmatter
    if body.startswith("---"):
        end = body.find("---", 3)
        if end != -1:
            body = body[end + 3 :]
    # Strip metadata footer
    body = _re.sub(r"<!--\s*lexibrary:meta.*?-->", "", body, flags=_re.DOTALL)
    return len(body.strip())


# ---------------------------------------------------------------------------
# Scope isolation helpers
# ---------------------------------------------------------------------------


def _uncommitted_files(project_root: Path) -> set[Path]:
    """Return the set of source files with uncommitted git changes."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=project_root,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return set()
    if result.returncode != 0:
        return set()

    paths: set[Path] = set()
    for line in result.stdout.splitlines():
        # git status --porcelain: first 2 chars are status, then space, then path
        if len(line) > 3:
            rel = line[3:].strip()
            # Handle renames: "R  old -> new"
            if " -> " in rel:
                rel = rel.split(" -> ", 1)[1]
            paths.add(project_root / rel)
    return paths


def _active_iwh_dirs(
    project_root: Path,
    ttl_hours: int,
) -> set[Path]:
    """Return source directories with active (non-stale) IWH signals."""
    from lexibrary.iwh.reader import find_all_iwh  # noqa: PLC0415

    now = datetime.now(UTC)
    active: set[Path] = set()
    for rel_dir, iwh in find_all_iwh(project_root):
        age = now - iwh.created
        if age < timedelta(hours=ttl_hours):
            active.add(project_root / rel_dir)
    return active


# ---------------------------------------------------------------------------
# Two-pass merge helpers
# ---------------------------------------------------------------------------


def _dispatch_written_paths(result: DispatchResult) -> list[Path]:
    """Return the set of paths that this dispatch pass actually wrote.

    Used by :meth:`Coordinator._run_pipeline_two_pass` to hand
    ``changed_paths`` to ``linkgraph.builder.build_index`` between and
    after the two dispatch passes.  Only ``outcome="fixed"`` successful
    dispatches are counted — ``dry_run`` results, stubs, deferred items,
    and fixer failures never wrote to disk, so including them in the
    incremental rebuild would be wasted work.

    The list is deduplicated and returned in a stable deterministic
    order so that downstream ``build_index`` calls are idempotent.
    """
    seen: set[Path] = set()
    ordered: list[Path] = []
    for dispatched in result.dispatched:
        if (
            dispatched.path is not None
            and dispatched.success
            and dispatched.outcome == "fixed"
            and dispatched.path not in seen
        ):
            seen.add(dispatched.path)
            ordered.append(dispatched.path)
    return ordered


def _merge_collect_results(
    hash_collect: CollectResult,
    graph_collect: CollectResult,
) -> CollectResult:
    """Merge two ``CollectResult`` objects produced by the hash/graph passes.

    Concatenates each per-item-kind list in pass order (hash first,
    graph second) and ORs the two ``link_graph_available`` flags so a
    graph-pass-detected failure is not silently overwritten by the
    hash pass's default ``False``.  ``validation_error`` is carried
    forward from whichever pass first reported one.
    """
    merged = CollectResult()
    merged.items = [*hash_collect.items, *graph_collect.items]
    merged.comment_items = [
        *hash_collect.comment_items,
        *graph_collect.comment_items,
    ]
    merged.deprecation_items = [
        *hash_collect.deprecation_items,
        *graph_collect.deprecation_items,
    ]
    merged.budget_items = [
        *hash_collect.budget_items,
        *graph_collect.budget_items,
    ]
    merged.comment_audit_items = [
        *hash_collect.comment_audit_items,
        *graph_collect.comment_audit_items,
    ]
    merged.link_graph_available = (
        hash_collect.link_graph_available or graph_collect.link_graph_available
    )
    merged.validation_error = hash_collect.validation_error or graph_collect.validation_error
    return merged


# ---------------------------------------------------------------------------
# Coordinator
# ---------------------------------------------------------------------------


class Coordinator:
    """Central orchestration module for the curator subsystem.

    Executes a four-phase pipeline: collect -> triage -> dispatch -> report.
    The coordinator is pure Python with no LLM calls.  LLM judgment is
    pushed into sub-agent stubs invoked during the dispatch phase.
    """

    def __init__(self, project_root: Path, config: LexibraryConfig) -> None:
        self.project_root = project_root
        self.config = config
        self.curator_config: CuratorConfig = config.curator
        self.lexibrary_dir = project_root / LEXIBRARY_DIR
        self.summary = ErrorSummary()
        # Scope-isolation caches populated during _collect; consumed when
        # building a DispatchContext.  Reset at the start of each pipeline run.
        self._uncommitted: set[Path] = set()
        self._active_iwh: set[Path] = set()
        # Set at the top of _dispatch so _ctx() can report the correct flag.
        self._dry_run: bool = False
        # Raw ``validate_library()`` issue count captured during the collect
        # phase.  Only consumed when ``curator_config.verify_after_sweep`` is
        # True, where it supplies the ``before`` leg of the verification
        # delta.  ``None`` means validation did not run (or raised).
        self._validation_before_count: int | None = None
        # Populated by ``_prepare_indexes`` with ``(source_hash,
        # interface_hash)`` pairs keyed by absolute source path.  Consumed
        # by ``_collect_staleness`` via task 1.5 so staleness detection
        # reuses the hashes computed during prepare rather than re-running
        # ``compute_hashes``.  Reset at the top of each ``_prepare_indexes``
        # invocation.
        self._drift_hashes: dict[Path, tuple[str, str | None]] = {}
        # File-mtime cache shared across ``_prepare_indexes`` invocations
        # on the same Coordinator instance.  Keyed by absolute source path;
        # value is ``(mtime_ns, source_hash)``.  When a source file's
        # on-disk ``mtime_ns`` is unchanged AND the cached ``source_hash``
        # still matches the design file's frontmatter, ``_prepare_indexes``
        # skips ``compute_hashes`` entirely — this is the warm-cache path
        # targeted by the P95 <=200ms benchmark in task 1.6.
        self._mtime_cache: dict[Path, tuple[int, str]] = {}
        # Pre-charged LLM calls counted against ``max_llm_calls_per_run``
        # before the dispatch phase runs.  Callers outside the coordinator
        # (today: the reactive-hook bootstrap in ``hooks.post_edit_hook``
        # when ``reactive_bootstrap_regenerate`` is ``True``) may invoke
        # ``archivist.pipeline.update_file`` prior to handing control to
        # :meth:`run`; each such invocation increments this counter so the
        # coordinator's dispatch cap in ``_dispatch`` accounts for the
        # budget already consumed.  ``DispatchResult.llm_calls_used`` is
        # seeded from this value at the top of ``_dispatch``.
        self.pre_charged_llm_calls: int = 0

    def _ctx(self) -> DispatchContext:
        """Build a :class:`DispatchContext` snapshot from coordinator state.

        The returned context is a shallow snapshot — ``uncommitted`` and
        ``active_iwh`` are the sets captured during ``_collect`` and
        ``dry_run`` reflects the flag passed to ``_dispatch``.  Handlers
        must treat the sets as read-only.
        """
        return DispatchContext(
            project_root=self.project_root,
            config=self.config,
            summary=self.summary,
            lexibrary_dir=self.lexibrary_dir,
            dry_run=self._dry_run,
            uncommitted=self._uncommitted,
            active_iwh=self._active_iwh,
        )

    # -- Public API ---------------------------------------------------------

    async def run(
        self,
        *,
        scope: Path | None = None,
        check: str | None = None,
        dry_run: bool = False,
        trigger: str = "on_demand",
    ) -> CuratorReport:
        """Execute the full curator pipeline and return a report."""
        _acquire_lock(self.project_root)
        try:
            return await self._run_pipeline(
                scope=scope, check=check, dry_run=dry_run, trigger=trigger
            )
        finally:
            _release_lock(self.project_root)

    # -- Pipeline -----------------------------------------------------------

    async def _run_pipeline(
        self,
        *,
        scope: Path | None = None,
        check: str | None = None,
        dry_run: bool = False,
        trigger: str = "on_demand",
    ) -> CuratorReport:
        """Internal pipeline execution after lock acquisition.

        Two flow modes, gated by ``CuratorConfig.two_pass_collect``:

        * **Two-pass (default, task 5.4):** hash-layer collect → triage →
          dispatch (capped at 70% of ``max_llm_calls_per_run``) →
          mid-run ``build_index`` with paths written by the hash pass →
          graph-layer collect → triage → dispatch (using the full shared
          budget minus what hash consumed) → final ``build_index`` →
          ``_verify_after_sweep`` (task 5.7, on post-graph-dispatch
          link graph) → merged ``_report``.
        * **Legacy single-pass:** the pre-restructure ``_collect →
          _triage → _dispatch → _verify_after_sweep → _report`` flow,
          preserved verbatim for the ``two_pass_collect=False``
          kill-switch.  Items emitted from ``_collect`` carry
          ``layer=None`` so honest-reporting tests can distinguish.
        """
        # Reset per-run state so multiple pipeline invocations on the
        # same Coordinator instance do not accumulate counts.  The
        # two-pass flow (and the legacy flow that calls both layer
        # methods) accumulates ``_validation_before_count`` across
        # successive ``_collect_validation`` calls; without a reset
        # here a second pipeline run would double-count.
        self._validation_before_count = None
        # Phase 0: Prepare indexes (refresh symbol/link graphs for drifted sources)
        if self.curator_config.prepare_indexes:
            self._prepare_indexes(scope=scope)

        if self.curator_config.two_pass_collect:
            return await self._run_pipeline_two_pass(
                scope=scope, check=check, dry_run=dry_run, trigger=trigger
            )
        return await self._run_pipeline_legacy(
            scope=scope, check=check, dry_run=dry_run, trigger=trigger
        )

    async def _run_pipeline_legacy(
        self,
        *,
        scope: Path | None,
        check: str | None,
        dry_run: bool,
        trigger: str,
    ) -> CuratorReport:
        """Legacy single-pass flow (kill-switch ``two_pass_collect=False``).

        Preserves the pre-Phase-2 call ordering verbatim: collect →
        triage → dispatch → verify_after_sweep → report.  Items emitted
        by ``_collect`` carry ``layer=None``.  No mid-run ``build_index``
        occurs.
        """
        # Phase 1: Collect
        collect_result = self._collect(scope=scope, check=check)

        # Phase 2: Triage
        triage_result = self._triage(collect_result)

        # Phase 3: Dispatch (legacy: no per-pass cap; only the shared
        # ``max_llm_calls_per_run`` ceiling applies).
        dispatch_result = await self._dispatch(triage_result, dry_run=dry_run)

        # Phase 3b: Migration dispatch cycle (after deprecations committed)
        migrations_applied, migrations_proposed = self._dispatch_migrations(
            dispatch_result, dry_run=dry_run
        )

        # Phase 3c: Post-sweep verification (curator-fix Phase 5 — group 10).
        # Strictly observability — does NOT influence which fixes ran.
        verification = self._verify_after_sweep(check=check)

        # Phase 4: Report
        report = self._report(
            collect_result,
            triage_result,
            dispatch_result,
            migrations_applied=migrations_applied,
            migrations_proposed=migrations_proposed,
            trigger=trigger,
            verification=verification,
        )
        return report

    async def _run_pipeline_two_pass(
        self,
        *,
        scope: Path | None,
        check: str | None,
        dry_run: bool,
        trigger: str,
    ) -> CuratorReport:
        """Two-pass hash-layer → graph-layer flow (task 5.4).

        Step-by-step:

        1. ``_collect_hash_layer`` — staleness, agent-edit, IWH, comment,
           comment-audit, budget, hash-layer validator subset.  Items
           are tagged ``layer="hash"`` at the emission site.
        2. ``_triage`` + ``_dispatch`` with
           ``budget_cap=int(max_llm_calls_per_run * 0.7)`` — the
           hash-layer pass cannot consume more than 70% of the shared
           LLM budget.
        3. ``linkgraph.builder.build_index(changed_paths=...)`` for the
           paths that hash-layer dispatch actually fixed.  This rebuild
           is what makes graph-layer triage see a fresh link graph.
        4. ``_collect_graph_layer`` — validator graph-subset,
           deprecation, consistency, link-graph availability probe.
           Items tagged ``layer="graph"``.
        5. ``_triage`` + ``_dispatch`` with
           ``budget_cap=max_llm_calls_per_run`` (the shared counter —
           pre-seeded via ``self.pre_charged_llm_calls`` — handles the
           "30% remaining" accounting).
        6. ``linkgraph.builder.build_index`` again for graph-pass fixes.
        7. ``_verify_after_sweep`` on the post-graph-dispatch link
           graph (task 5.7).
        8. ``_report`` with the hash-pass and graph-pass dispatches
           merged into a single ``DispatchResult``.
        """
        from lexibrary.linkgraph.builder import build_index  # noqa: PLC0415

        # --- Pass 1: hash layer -------------------------------------------
        hash_collect = CollectResult()
        self._collect_hash_layer(hash_collect, scope=scope, check=check, layer="hash")

        hash_triage = self._triage(hash_collect)

        hash_budget_cap = int(self.curator_config.max_llm_calls_per_run * 0.7)
        hash_dispatch = await self._dispatch(
            hash_triage, dry_run=dry_run, budget_cap=hash_budget_cap
        )

        # Mid-run link graph rebuild — only the paths the hash layer
        # actually wrote need re-indexing.  ``build_index`` degrades
        # gracefully per the curator-link-graph convention; wrap in
        # try/except so an index failure never aborts the run.
        #
        # Guard: only rebuild if ``index.db`` already exists.  When
        # ``_prepare_indexes`` chose to log-and-skip because the DB was
        # absent (scenario (ii)), creating an artificially sparse index
        # here via ``incremental_update`` would mislead graph-layer
        # checks — e.g. ``_collect_orphan_artifacts`` would flag every
        # unreferenced artifact simply because the freshly-created DB
        # knows only about ``hash_written``.  Bootstrapping the full
        # index is outside the curator's remit; the user must run
        # ``lexictl update``.
        index_db_path = self.lexibrary_dir / "index.db"
        hash_written = _dispatch_written_paths(hash_dispatch)
        if hash_written and index_db_path.exists():
            try:
                build_index(self.project_root, changed_paths=hash_written)
            except Exception as exc:
                logger.warning(
                    "_run_pipeline_two_pass: mid-run build_index raised — "
                    "continuing with a potentially stale link graph",
                    exc_info=True,
                )
                self.summary.add("two_pass_build_index", exc, path="mid_run")

        # Carry the hash-pass LLM consumption forward so the graph-pass
        # dispatch's effective shared budget starts where hash left off.
        # (``_dispatch`` seeds ``DispatchResult.llm_calls_used`` from
        # ``self.pre_charged_llm_calls``; this bump is how the single
        # shared counter is enforced across passes without a second
        # counter.)  Do NOT reset the counter — the hook-seeded starting
        # value is part of the accumulated total.
        self.pre_charged_llm_calls = hash_dispatch.llm_calls_used

        # --- Pass 2: graph layer ------------------------------------------
        graph_collect = CollectResult()
        self._collect_graph_layer(graph_collect, scope=scope, check=check, layer="graph")

        graph_triage = self._triage(graph_collect)

        graph_dispatch = await self._dispatch(
            graph_triage,
            dry_run=dry_run,
            budget_cap=self.curator_config.max_llm_calls_per_run,
        )

        # Final link graph rebuild — graph-pass writes may still invalidate
        # downstream readers (e.g. ``_verify_after_sweep``).  Mirrors the
        # "index must pre-exist" guard from the mid-run rebuild.
        graph_written = _dispatch_written_paths(graph_dispatch)
        if graph_written and index_db_path.exists():
            try:
                build_index(self.project_root, changed_paths=graph_written)
            except Exception as exc:
                logger.warning(
                    "_run_pipeline_two_pass: post-graph build_index raised — "
                    "continuing with a potentially stale link graph",
                    exc_info=True,
                )
                self.summary.add("two_pass_build_index", exc, path="post_graph")

        # Merge the two passes into a single ``DispatchResult`` for
        # downstream consumers.  The ``dispatched`` / ``deferred`` lists
        # are concatenated in pass order (hash first, graph second) so
        # honest-reporting tests that iterate see a stable ordering.
        # ``llm_calls_used`` takes the graph-pass cumulative total
        # because ``pre_charged_llm_calls`` was bumped to the hash-pass
        # total before the graph pass ran.
        merged_dispatch = DispatchResult(
            dispatched=[*hash_dispatch.dispatched, *graph_dispatch.dispatched],
            deferred=[*hash_dispatch.deferred, *graph_dispatch.deferred],
            llm_calls_used=graph_dispatch.llm_calls_used,
            llm_cap_reached=hash_dispatch.llm_cap_reached or graph_dispatch.llm_cap_reached,
        )

        # Similarly merge the collect / triage results so ``_report``'s
        # ``checked`` / issue-breakdown accounting reflects both passes.
        merged_collect = _merge_collect_results(hash_collect, graph_collect)
        merged_triage = TriageResult(items=[*hash_triage.items, *graph_triage.items])

        # Phase 3b: Migration dispatch cycle (after deprecations committed).
        # Runs against the merged dispatch so migrations for deprecations
        # from either pass are picked up.
        migrations_applied, migrations_proposed = self._dispatch_migrations(
            merged_dispatch, dry_run=dry_run
        )

        # Phase 3c: Post-sweep verification (task 5.7).  Runs AFTER the
        # graph-layer build_index so the before/after delta reads a
        # link graph reflecting graph-pass output — the spec's "honest
        # delta" requirement.
        verification = self._verify_after_sweep(check=check)

        # Phase 4: Report
        report = self._report(
            merged_collect,
            merged_triage,
            merged_dispatch,
            migrations_applied=migrations_applied,
            migrations_proposed=migrations_proposed,
            trigger=trigger,
            verification=verification,
        )
        return report

    # -- Phase 0: Prepare indexes -----------------------------------------

    def _prepare_indexes(self, scope: Path | None = None) -> None:
        """Rebuild derived indexes for drifted sources before collect runs.

        Walks ``.lexibrary/designs/**.md`` (or, when ``scope`` is provided,
        only the design that mirrors the single source file at ``scope``),
        compares frontmatter hashes against the current on-disk source,
        and refreshes ``symbols.db`` + ``index.db`` for every drifted
        source before the collect phase runs.  Populates
        ``self._drift_hashes`` so ``_collect_staleness`` (task 1.5) can
        reuse the hashes without recomputing them.

        The method makes no LLM calls and performs no write outside the
        PID lock already acquired by ``_run_pipeline``.  See the
        ``curator-index-preparation`` spec for the five scenarios this
        method satisfies (clean, both-DBs-absent, drifted, symbols-db
        absent, scoped).

        Parameters
        ----------
        scope:
            Optional absolute source path (or directory).  When provided,
            only the design files whose ``source`` field lives under
            ``scope`` are walked.  When ``None``, the full design tree is
            walked.

        Returns
        -------
        None
            The method mutates ``self._drift_hashes`` and the on-disk
            indexes as a side effect.
        """
        from lexibrary.artifacts.design_file_parser import (  # noqa: PLC0415
            parse_design_file_metadata,
        )
        from lexibrary.ast_parser import compute_hashes  # noqa: PLC0415
        from lexibrary.utils.paths import symbols_db_path  # noqa: PLC0415

        # Reset the per-run drift-hash cache.  The mtime cache persists
        # across runs so the warm-cache benchmark budget holds.
        self._drift_hashes = {}

        designs_dir = self.lexibrary_dir / "designs"
        if not designs_dir.is_dir():
            # No design tree at all — nothing to prepare.  The collect
            # phase will still run; staleness detection will simply have
            # no cache to reuse.
            return

        # Scenario (ii): both databases absent — log-and-skip without
        # raising.  The collect phase continues normally; validator checks
        # degrade gracefully per the curator-link-graph convention.
        index_db_path = self.lexibrary_dir / "index.db"
        symbols_db_present = symbols_db_path(self.project_root).exists()
        index_db_present = index_db_path.exists()
        if not symbols_db_present and not index_db_present:
            logger.info(
                "_prepare_indexes: symbols.db and index.db both absent — "
                "skipping derived-index refresh. Run `lexictl update` to "
                "bootstrap the indexes."
            )
            return

        # Walk the design tree and compare hashes.  ``drifted_sources``
        # accumulates absolute source paths whose on-disk hash disagrees
        # with the design-file frontmatter.
        drifted_sources: list[Path] = []

        for design_path in sorted(designs_dir.rglob("*.md")):
            # Skip dotfiles / sidecar files.
            if design_path.name.startswith("."):
                continue

            try:
                metadata = parse_design_file_metadata(design_path)
            except Exception as exc:  # pragma: no cover - defensive
                self.summary.add("prepare_indexes", exc, path=str(design_path))
                continue

            if metadata is None:
                continue

            source_path = self.project_root / metadata.source
            if not source_path.exists():
                continue

            # Scope filtering — when ``scope`` is an absolute path (file
            # or directory), restrict the walk to designs whose source
            # lives under it.  ``Path.is_relative_to`` treats a path as
            # relative to itself, so the single-file case works without
            # special handling.
            if scope is not None and not source_path.is_relative_to(scope):
                continue

            # Check the file-mtime cache before calling ``compute_hashes``.
            # ``st_mtime_ns`` gives us nanosecond-precision comparisons
            # against the cached timestamp, which is enough to detect any
            # write to the file between runs.
            try:
                current_mtime_ns = source_path.stat().st_mtime_ns
            except OSError as exc:  # pragma: no cover - defensive
                self.summary.add("prepare_indexes", exc, path=str(source_path))
                continue

            cached = self._mtime_cache.get(source_path)
            if (
                cached is not None
                and cached[0] == current_mtime_ns
                and cached[1] == metadata.source_hash
            ):
                # Warm-cache hit: mtime hasn't moved AND the cached hash
                # still matches the frontmatter, so we know the source
                # hasn't changed since we last recorded it.  Populate
                # ``_drift_hashes`` with the cached hash so
                # ``_collect_staleness`` can still reuse it — interface
                # hash is ``None`` here because we skip ``compute_hashes``
                # in this branch; ``_collect_staleness`` compares only the
                # source hash when the interface hash is absent.
                self._drift_hashes[source_path] = (cached[1], None)
                continue

            # Cold path — must recompute the hashes.
            try:
                current_source_hash, current_interface_hash = compute_hashes(source_path)
            except Exception as exc:
                self.summary.add("prepare_indexes", exc, path=str(source_path))
                continue

            # Record every computed pair so ``_collect_staleness`` can
            # reuse them without re-invoking ``compute_hashes`` (satisfies
            # the "Drift-hash cache shared with staleness collect"
            # requirement).
            self._drift_hashes[source_path] = (current_source_hash, current_interface_hash)

            # Update the mtime cache with the freshly-computed source
            # hash so the next run hits the warm-cache branch above.
            self._mtime_cache[source_path] = (current_mtime_ns, current_source_hash)

            if metadata.source_hash != current_source_hash:
                drifted_sources.append(source_path)

        # Scenario (i): no drift — return early without touching either
        # index.  Satisfies the "both DBs present and clean -> no write"
        # scenario.
        if not drifted_sources:
            return

        # Scenario (iii) / (iv): drift detected — refresh the symbol
        # graph per-file and rebuild the affected slice of the link
        # graph.  ``refresh_file`` is wrapped in try/except because a
        # parse error or missing DB must never abort the prepare phase;
        # the spec explicitly forbids falling through to a full
        # ``build_symbol_graph`` under any condition.
        if symbols_db_present:
            from lexibrary.symbolgraph.builder import (  # noqa: PLC0415
                refresh_file as _refresh_symbols,
            )

            for source in drifted_sources:
                try:
                    _refresh_symbols(self.project_root, self.config, source)
                except Exception as exc:
                    # Per spec scenario "Parse error during refresh_file":
                    # log-and-skip this source and continue refreshing the
                    # remaining drifted sources.  The exception is also
                    # recorded in the run summary for later inspection.
                    logger.warning(
                        "_prepare_indexes: symbolgraph.refresh_file raised for %s — "
                        "skipping symbol-graph refresh for this source",
                        source,
                        exc_info=True,
                    )
                    self.summary.add("prepare_indexes", exc, path=str(source))
        else:
            # Scenario (iv): symbols.db is absent but the link graph
            # exists.  Skip ``refresh_file`` with a log note; do NOT fall
            # through to ``build_symbol_graph``.
            logger.info(
                "_prepare_indexes: symbols.db absent — skipping per-file "
                "symbol-graph refresh for %d drifted source(s). Link graph "
                "rebuild will still run.",
                len(drifted_sources),
            )

        # Rebuild the link graph for the drifted slice only.  Passing a
        # non-None ``changed_paths`` selects the incremental update path;
        # an empty list would still be accepted by ``build_index`` but we
        # already returned above when ``drifted_sources`` was empty.
        from lexibrary.linkgraph.builder import build_index  # noqa: PLC0415

        try:
            build_index(self.project_root, changed_paths=drifted_sources)
        except Exception as exc:
            # Mirror the curator-link-graph convention: log and record a
            # summary entry rather than raising — the collect phase can
            # still run with a stale index, and validator checks degrade
            # gracefully on schema/availability failures.
            logger.warning(
                "_prepare_indexes: linkgraph.build_index raised — "
                "continuing with a potentially stale link graph",
                exc_info=True,
            )
            self.summary.add("prepare_indexes", exc, path=str(index_db_path))

    # -- Phase 1: Collect ---------------------------------------------------

    def _collect_hash_layer(
        self,
        result: CollectResult,
        *,
        scope: Path | None = None,
        check: str | None = None,
        layer: Literal["hash", "graph"] | None = "hash",
    ) -> None:
        """First collect pass — hash-layer signals.

        Invokes sub-agents that do NOT depend on the link graph
        (``index.db``) or symbol graph (``symbols.db``): staleness
        detection, agent-edit scan, IWH signal scan, comment detection,
        comment audit, token budgets, and the hash-layer validator
        subset from :data:`_HASH_LAYER_CHECKS`.

        Populates the scope-isolation caches (``self._uncommitted`` and
        ``self._active_iwh``) at the top of the method so the graph
        layer (which runs after the mid-run ``build_index`` rebuild in
        the two-pass flow) can reuse them without re-querying git.

        Each emitted :class:`CollectItem` is tagged with ``layer`` at
        the emission site.  Passing ``layer=None`` (used by the legacy
        single-pass :meth:`_collect` helper) disables tagging while
        preserving the rest of the collection work — legacy consumers
        see the same items they always have.
        """
        # Determine scope isolation exclusions.  Populated during
        # hash-layer collect so the graph-layer pass (and the legacy
        # single-pass helper) can reuse them without re-querying git.
        uncommitted = _uncommitted_files(self.project_root)
        active_iwh = _active_iwh_dirs(self.project_root, self.config.iwh.ttl_hours)
        # Stash on self so _ctx() (dispatch phase) and _collect_graph_layer
        # can expose them.  Task 5.8: scope-isolation caches are populated
        # in the hash layer only; the graph layer asserts their presence.
        self._uncommitted = uncommitted
        self._active_iwh = active_iwh

        # 1. Hash-layer validation subset (frontmatter validators,
        #    hash_freshness, token_budgets, stale_agent_design, ...).
        self._collect_validation(
            result,
            check=check,
            checks=_HASH_LAYER_CHECKS,
            uncommitted=uncommitted,
            active_iwh=active_iwh,
            layer=layer,
        )

        # 2. Hash-based staleness detection (reuses self._drift_hashes
        #    from _prepare_indexes; fallback path stays).
        self._collect_staleness(
            result,
            scope=scope,
            uncommitted=uncommitted,
            active_iwh=active_iwh,
            layer=layer,
        )

        # 3. Agent-edit detection via change_checker.
        self._collect_agent_edits(
            result,
            scope=scope,
            uncommitted=uncommitted,
            active_iwh=active_iwh,
            layer=layer,
        )

        # 4. IWH signal scan.
        self._collect_iwh(result, scope=scope, layer=layer)

        # 5. Comment detection (emits CommentCollectItem — no layer
        #    field on that dataclass; tagging happens downstream in
        #    triage if at all).
        self._collect_comments(
            result,
            scope=scope,
            uncommitted=uncommitted,
            active_iwh=active_iwh,
        )

        # 6. TODO/FIXME/HACK scanning (emits CommentAuditCollectItem —
        #    no layer field on that dataclass).
        self._collect_comment_audit_issues(result, scope=scope)

        # 7. Token budget checks (emits BudgetCollectItem — no layer
        #    field on that dataclass).
        self._collect_budget_issues(result, scope=scope)

    def _collect_graph_layer(
        self,
        result: CollectResult,
        *,
        scope: Path | None = None,
        check: str | None = None,
        layer: Literal["hash", "graph"] | None = "graph",
    ) -> None:
        """Second collect pass — graph-layer signals.

        Invokes sub-agents that read from the link graph (``index.db``)
        or symbol graph (``symbols.db``): the graph-layer validator
        subset from :data:`_GRAPH_LAYER_CHECKS`, deprecation candidate
        detection, consistency checks, and the link-graph availability
        probe.

        When invoked via the two-pass flow, the link graph has already
        been rebuilt by a mid-run ``build_index`` call (task 5.4), so
        graph-dependent checks see the post-hash-dispatch state.

        Each emitted :class:`CollectItem` is tagged with ``layer`` at
        the emission site.  Passing ``layer=None`` (used by the legacy
        single-pass :meth:`_collect` helper) disables tagging.

        Asserts the scope-isolation caches populated by
        :meth:`_collect_hash_layer` are present — the two-pass flow
        relies on that invariant (task 5.8).
        """
        # Task 5.8: scope-isolation caches MUST be populated by the
        # hash layer before graph collect runs.  In the two-pass flow
        # this assertion guards against future refactors that might
        # accidentally short-circuit the hash layer; in the legacy
        # single-pass flow the helper calls both layers in sequence so
        # the caches are always populated.
        assert self._uncommitted is not None and self._active_iwh is not None, (
            "scope caches must be populated by the hash layer before graph collect"
        )
        uncommitted = self._uncommitted
        active_iwh = self._active_iwh

        # 1. Graph-layer validation subset (bidirectional_deps,
        #    orphan_artifacts, wikilink_resolution, aindex_coverage,
        #    forward_dependencies, duplicate_slugs/aliases, ...).
        self._collect_validation(
            result,
            check=check,
            checks=_GRAPH_LAYER_CHECKS,
            uncommitted=uncommitted,
            active_iwh=active_iwh,
            layer=layer,
        )

        # 2. Deprecation candidate detection — reads link-graph
        #    snapshots for orphan-artifact discovery (emits
        #    DeprecationCollectItem; no layer field on that dataclass).
        self._collect_deprecation_candidates(result)

        # 3. Consistency checks — per the curator-two-pass-collect
        #    spec, these live exclusively in the graph layer because
        #    they read wikilink / link-graph state (task 5.6).
        self._collect_consistency(
            result,
            scope=scope,
            uncommitted=uncommitted,
            active_iwh=active_iwh,
            layer=layer,
        )

        # 4. Link graph availability probe.
        result.link_graph_available = self._check_link_graph()

    def _collect(
        self,
        *,
        scope: Path | None = None,
        check: str | None = None,
    ) -> CollectResult:
        """Gather signals from validation, staleness checks, and IWH scan.

        Legacy single-pass helper used when
        :attr:`CuratorConfig.two_pass_collect` is ``False``.  Invokes
        :meth:`_collect_hash_layer` and :meth:`_collect_graph_layer`
        back-to-back with ``layer=None`` so the emitted items carry
        no layer tag — preserving pre-two-pass behaviour for callers
        that have not yet opted in to the split.

        Task 5.4 owns wiring :meth:`_collect_hash_layer` and
        :meth:`_collect_graph_layer` directly into :meth:`_run_pipeline`
        as two separate passes; this helper is the ``False`` branch
        for the kill-switch config flag.
        """
        result = CollectResult()
        self._collect_hash_layer(result, scope=scope, check=check, layer=None)
        self._collect_graph_layer(result, scope=scope, check=check, layer=None)
        return result

    def _collect_validation(
        self,
        result: CollectResult,
        *,
        check: str | None = None,
        checks: Iterable[str] | None = None,
        uncommitted: set[Path] | None = None,
        active_iwh: set[Path] | None = None,
        layer: Literal["hash", "graph"] | None = None,
    ) -> None:
        """Run validate_library() and add results to CollectResult.

        ``checks`` is forwarded verbatim to :func:`validate_library`.  When
        ``None`` (the default) every registered check runs -- matching the
        legacy behaviour.  When provided, only the named checks execute;
        this is the hook used by the two-pass collect phases to partition
        validator work between the hash and graph layers.

        ``layer`` tags every emitted :class:`CollectItem` with its
        originating two-pass collect layer.  ``None`` (the default)
        preserves the legacy single-pass behaviour.  ``_validation_before_count``
        accumulates across successive calls within a single run so the
        legacy flow (which invokes this method twice — once per layer —
        to aggregate the full registry) still produces the same total
        count as a single-call invocation would.
        """
        from lexibrary.validator import validate_library  # noqa: PLC0415

        uncommitted = uncommitted or set()
        active_iwh = active_iwh or set()

        try:
            report = validate_library(
                self.project_root,
                self.lexibrary_dir,
                check_filter=check,
                checks=checks,
            )
            # Capture the raw issue count so the Phase 5 post-sweep
            # verification can compute a ``before`` figure without having
            # to re-run the validator when ``verify_after_sweep`` is False.
            # Accumulate across layer calls so the legacy single-pass
            # flow (invoked via both layer methods with layer=None) still
            # aggregates the full-registry count.
            previous = self._validation_before_count or 0
            self._validation_before_count = previous + len(report.issues)
            for issue in report.issues:
                artifact_path = Path(issue.artifact) if issue.artifact else None
                if artifact_path is not None and _should_skip_path(
                    artifact_path, uncommitted, active_iwh
                ):
                    continue
                result.items.append(
                    CollectItem(
                        source="validation",
                        path=artifact_path,
                        severity=issue.severity,
                        message=issue.message,
                        check=issue.check,
                        layer=layer,
                    )
                )
        except Exception as exc:
            logger.error("validate_library() raised: %s", exc)
            self.summary.add("collect", exc, path="validate_library")
            result.validation_error = str(exc)

    def _collect_staleness(
        self,
        result: CollectResult,
        *,
        scope: Path | None = None,
        uncommitted: set[Path],
        active_iwh: set[Path],
        layer: Literal["hash", "graph"] | None = None,
    ) -> None:
        """Walk design files and detect stale source/interface hashes.

        ``layer`` tags every emitted :class:`CollectItem` with its
        originating two-pass collect layer.  ``None`` (the default)
        preserves the legacy single-pass behaviour.
        """
        from lexibrary.artifacts.design_file_parser import (  # noqa: PLC0415
            parse_design_file_metadata,
        )
        from lexibrary.ast_parser import compute_hashes  # noqa: PLC0415

        designs_dir = self.lexibrary_dir / "designs"
        if not designs_dir.is_dir():
            return

        for design_path in sorted(designs_dir.rglob("*.md")):
            # Skip non-design files (e.g. .comments.yaml siblings)
            if design_path.name.startswith("."):
                continue

            try:
                metadata = parse_design_file_metadata(design_path)
            except Exception as exc:
                self.summary.add("collect", exc, path=str(design_path))
                continue

            if metadata is None:
                continue

            source_path = self.project_root / metadata.source
            if not source_path.exists():
                continue

            # Scope filtering
            if scope is not None and not source_path.is_relative_to(scope):
                continue

            # Scope isolation: skip uncommitted files or active IWH dirs
            if _should_skip_path(source_path, uncommitted, active_iwh):
                if source_path in uncommitted:
                    skip_msg = "Skipped -- uncommitted changes detected"
                else:
                    skip_msg = "Skipped -- active IWH signal in directory"
                result.items.append(
                    CollectItem(
                        source="staleness",
                        path=source_path,
                        severity="info",
                        message=skip_msg,
                        check="scope_isolation",
                        layer=layer,
                    )
                )
                continue

            # Prefer the drift-hash cache populated by ``_prepare_indexes``
            # (task 1.5): it already computed these hashes during the
            # prepare pass, so re-invoking ``compute_hashes`` here would
            # duplicate work.  The cache may be empty when
            # ``curator_config.prepare_indexes`` is ``False`` (kill-switch
            # opt-out) OR when a given source was not visited during
            # prepare — fall back to ``compute_hashes`` in that case.
            cached_hashes = self._drift_hashes.get(source_path)
            if cached_hashes is not None:
                current_source_hash, current_interface_hash = cached_hashes
            else:
                try:
                    current_source_hash, current_interface_hash = compute_hashes(source_path)
                except Exception as exc:
                    self.summary.add("collect", exc, path=str(source_path))
                    continue

            source_stale = metadata.source_hash != current_source_hash
            interface_stale = (
                metadata.interface_hash is not None
                and current_interface_hash is not None
                and metadata.interface_hash != current_interface_hash
            )

            if source_stale or interface_stale:
                # Determine updated_by from frontmatter
                updated_by = self._get_updated_by(design_path)
                severity: str = "warning" if interface_stale else "info"
                src_lbl = "stale" if source_stale else "ok"
                ifc_lbl = "stale" if interface_stale else "ok"
                msg = f"Stale design file (source_hash={src_lbl}, interface_hash={ifc_lbl})"

                # Compute design body length for agent-edited files
                # (needed for extensive-content risk classification)
                design_body_length = 0
                if updated_by in ("agent", "maintainer"):
                    design_body_length = _design_body_length(design_path)

                result.items.append(
                    CollectItem(
                        source="staleness",
                        path=source_path,
                        severity=severity,  # type: ignore[arg-type]
                        message=msg,
                        check="staleness",
                        source_hash_stale=source_stale,
                        interface_hash_stale=interface_stale,
                        updated_by=updated_by,
                        design_body_length=design_body_length,
                        layer=layer,
                    )
                )

    def _get_updated_by(self, design_path: Path) -> str:
        """Extract updated_by from a design file's frontmatter."""
        from lexibrary.artifacts.design_file_parser import (  # noqa: PLC0415
            parse_design_file_frontmatter,
        )

        try:
            fm = parse_design_file_frontmatter(design_path)
            if fm is not None:
                return fm.updated_by or ""
        except Exception:
            pass
        return ""

    def _collect_iwh(
        self,
        result: CollectResult,
        *,
        scope: Path | None = None,
        layer: Literal["hash", "graph"] | None = None,
    ) -> None:
        """Scan IWH signals and add to results.

        ``layer`` tags every emitted :class:`CollectItem` with its
        originating two-pass collect layer.  ``None`` (the default)
        preserves the legacy single-pass behaviour.
        """
        from lexibrary.iwh.reader import find_all_iwh  # noqa: PLC0415
        from lexibrary.utils.paths import iwh_path as _iwh_path  # noqa: PLC0415

        try:
            signals = find_all_iwh(self.project_root)
        except Exception as exc:
            self.summary.add("collect", exc, path="iwh_scan")
            return

        for rel_dir, iwh in signals:
            source_dir = self.project_root / rel_dir
            if scope is not None and not source_dir.is_relative_to(scope):
                continue
            # ``consume_iwh`` needs the mirror directory where the ``.iwh`` file
            # actually lives; ``source_dir`` is used only for scope filtering.
            mirror_dir = _iwh_path(self.project_root, source_dir).parent
            result.items.append(
                CollectItem(
                    source="iwh",
                    path=mirror_dir,
                    severity="info",
                    message=f"IWH signal: scope={iwh.scope}, body={iwh.body[:80]}",
                    check="iwh_scan",
                    layer=layer,
                )
            )

    def _collect_comments(
        self,
        result: CollectResult,
        *,
        scope: Path | None = None,
        uncommitted: set[Path] | None = None,
        active_iwh: set[Path] | None = None,
    ) -> None:
        """Detect design files with unprocessed sidecar comments."""
        from lexibrary.lifecycle.comments import comment_count  # noqa: PLC0415
        from lexibrary.lifecycle.design_comments import design_comment_path  # noqa: PLC0415

        designs_dir = self.lexibrary_dir / "designs"
        if not designs_dir.is_dir():
            return

        uncommitted = uncommitted or set()
        active_iwh = active_iwh or set()

        for design_path in sorted(designs_dir.rglob("*.md")):
            if design_path.name.startswith("."):
                continue

            comments_path = design_comment_path(design_path)
            try:
                count = comment_count(comments_path)
            except Exception as exc:
                self.summary.add("collect", exc, path=str(comments_path))
                continue

            if count == 0:
                continue

            # Derive the source path from the design path
            # Design path: .lexibrary/designs/src/foo.py.md -> src/foo.py
            try:
                rel_design = design_path.relative_to(designs_dir)
                # Strip the .md suffix to get the source relative path
                source_rel = str(rel_design)
                if source_rel.endswith(".md"):
                    source_rel = source_rel[:-3]
                source_path = self.project_root / source_rel
            except ValueError:
                continue

            # Scope filtering
            if scope is not None and not source_path.is_relative_to(scope):
                continue

            # Scope isolation: skip uncommitted files and active IWH dirs
            if _should_skip_path(source_path, uncommitted, active_iwh):
                continue

            result.comment_items.append(
                CommentCollectItem(
                    design_path=design_path,
                    source_path=source_path,
                    comment_count=count,
                    comments_path=comments_path,
                )
            )

        # Sort by comment count descending (higher count = higher priority)
        result.comment_items.sort(key=lambda c: c.comment_count, reverse=True)

    def _collect_agent_edits(
        self,
        result: CollectResult,
        *,
        scope: Path | None = None,
        uncommitted: set[Path],
        active_iwh: set[Path],
        layer: Literal["hash", "graph"] | None = None,
    ) -> None:
        """Detect agent-edited design files via change_checker classification.

        Uses ``change_checker.check_change()`` to find files classified as
        ``AGENT_UPDATED`` (no footer = agent-authored from scratch,
        design_hash drift = agent-modified body).  These are files that may
        have ``updated_by: archivist`` in frontmatter but whose body was
        edited by an agent after generation.

        Also picks up files with invalid ``updated_by`` values from
        validation results already collected.

        Only collects files not already present in the staleness items
        (to avoid duplicates).

        ``layer`` tags every emitted :class:`CollectItem` with its
        originating two-pass collect layer.  ``None`` (the default)
        preserves the legacy single-pass behaviour.
        """
        from lexibrary.archivist.change_checker import ChangeLevel, check_change  # noqa: PLC0415
        from lexibrary.artifacts.design_file_parser import (  # noqa: PLC0415
            parse_design_file_metadata,
        )
        from lexibrary.ast_parser import compute_hashes  # noqa: PLC0415

        designs_dir = self.lexibrary_dir / "designs"
        if not designs_dir.is_dir():
            return

        # Build set of source paths already collected by staleness detection
        already_collected: set[Path] = set()
        for item in result.items:
            if item.source in ("staleness", "agent_edit") and item.path is not None:
                already_collected.add(item.path)

        for design_path in sorted(designs_dir.rglob("*.md")):
            if design_path.name.startswith("."):
                continue

            try:
                metadata = parse_design_file_metadata(design_path)
            except Exception as exc:
                self.summary.add("collect", exc, path=str(design_path))
                continue

            # Derive source path from metadata or design path
            if metadata is not None:
                source_path = self.project_root / metadata.source
            else:
                # No metadata footer -- derive from design path
                try:
                    rel_design = design_path.relative_to(designs_dir)
                    source_rel = str(rel_design)
                    if source_rel.endswith(".md"):
                        source_rel = source_rel[:-3]
                    source_path = self.project_root / source_rel
                except ValueError:
                    continue

            if not source_path.exists():
                continue

            # Skip if already collected by staleness detection
            if source_path in already_collected:
                continue

            # Scope filtering
            if scope is not None and not source_path.is_relative_to(scope):
                continue

            # Scope isolation: skip uncommitted files
            if source_path in uncommitted:
                continue

            # Scope isolation: skip files in active IWH directories
            if any(source_path.is_relative_to(d) for d in active_iwh):
                continue

            # Compute current hashes
            try:
                current_source_hash, current_interface_hash = compute_hashes(source_path)
            except Exception as exc:
                self.summary.add("collect", exc, path=str(source_path))
                continue

            # Use change_checker to classify
            try:
                change_level = check_change(
                    source_path, self.project_root, current_source_hash, current_interface_hash
                )
            except Exception as exc:
                self.summary.add("collect", exc, path=str(source_path))
                continue

            if change_level != ChangeLevel.AGENT_UPDATED:
                continue

            # Read design file body length for extensive-content detection
            design_body_length = _design_body_length(design_path)

            updated_by = self._get_updated_by(design_path)

            # Determine the agent-edit reason
            reason = "no_metadata_footer" if metadata is None else "design_hash_drift"

            result.items.append(
                CollectItem(
                    source="agent_edit",
                    path=source_path,
                    severity="warning",
                    message=(
                        f"Agent-edited design file detected "
                        f"(reason={reason}, updated_by={updated_by!r})"
                    ),
                    check="agent_edit_detection",
                    source_hash_stale=(
                        metadata is not None and metadata.source_hash != current_source_hash
                    ),
                    interface_hash_stale=(
                        metadata is not None
                        and metadata.interface_hash is not None
                        and current_interface_hash is not None
                        and metadata.interface_hash != current_interface_hash
                    ),
                    updated_by=updated_by,
                    agent_edit_reason=reason,
                    design_body_length=design_body_length,
                    layer=layer,
                )
            )

        # Also pick up invalid updated_by values from already-collected
        # validation results.
        for item in result.items:
            if (
                item.source == "validation"
                and item.check == "design_frontmatter"
                and "updated_by" in item.message.lower()
                and item.path is not None
                and item.path not in already_collected
            ):
                result.items.append(
                    CollectItem(
                        source="agent_edit",
                        path=item.path,
                        severity="warning",
                        message=f"Invalid updated_by detected via validation: {item.message}",
                        check="agent_edit_detection",
                        agent_edit_reason="invalid_updated_by",
                        layer=layer,
                    )
                )

    def _check_link_graph(self) -> bool:
        """Check whether the link graph database is available."""
        from lexibrary.linkgraph.query import LinkGraph  # noqa: PLC0415

        db_path = self.lexibrary_dir / "index.db"
        graph = LinkGraph.open(db_path)
        if graph is None:
            logger.warning(
                "Link graph unavailable -- skipping graph-dependent checks. "
                "Run `lexictl update` to rebuild."
            )
            return False
        graph.close()
        return True

    # -- Deprecation candidate collection (Phase 2) -------------------------

    def _collect_deprecation_candidates(self, result: CollectResult) -> None:
        """Detect deprecation candidates across all artifact types.

        Detects:
        (a) Orphan artifacts with zero inbound references via link graph.
        (b) Design files whose source file has been deleted.
        (c) Deprecated artifacts past TTL with zero references.
        (d) Resolved stack posts with changed referenced code.
        """
        from lexibrary.curator.cascade import snapshot_link_graph  # noqa: PLC0415

        snapshot = snapshot_link_graph(self.project_root)
        ttl = self.curator_config.deprecation.ttl_commits

        # (a) Orphan artifacts via reverse_deps
        self._collect_orphan_artifacts(result, snapshot)

        # (b) Design files with deleted source
        self._collect_deleted_source_designs(result)

        # (c) Deprecated artifacts past TTL with zero refs
        self._collect_ttl_expired_artifacts(result, snapshot, ttl)

        # (d) Resolved stack posts with changed referenced code
        self._collect_stale_resolved_stack_posts(result)

    def _collect_orphan_artifacts(
        self,
        result: CollectResult,
        snapshot: object,
    ) -> None:
        """Detect active concepts/conventions/playbooks with zero inbound refs."""
        from lexibrary.curator.cascade import LinkGraphSnapshot  # noqa: PLC0415

        if not isinstance(snapshot, LinkGraphSnapshot) or snapshot._link_graph is None:
            return

        # Scan concepts
        concepts_dir = self.lexibrary_dir / "concepts"
        if concepts_dir.is_dir():
            self._scan_orphan_dir(result, concepts_dir, "concept", snapshot, "*.md")

        # Scan conventions
        conventions_dir = self.lexibrary_dir / "conventions"
        if conventions_dir.is_dir():
            self._scan_orphan_dir(result, conventions_dir, "convention", snapshot, "*.md")

        # Scan playbooks
        playbooks_dir = self.lexibrary_dir / "playbooks"
        if playbooks_dir.is_dir():
            self._scan_orphan_dir(result, playbooks_dir, "playbook", snapshot, "*.md")

    def _scan_orphan_dir(
        self,
        result: CollectResult,
        directory: Path,
        kind: str,
        snapshot: object,
        pattern: str,
    ) -> None:
        """Scan a directory for orphan artifacts (zero inbound links)."""
        from lexibrary.curator.cascade import LinkGraphSnapshot  # noqa: PLC0415

        if not isinstance(snapshot, LinkGraphSnapshot):
            return

        for artifact_path in sorted(directory.glob(pattern)):
            if artifact_path.name.startswith("."):
                continue

            # Read current status
            status = self._read_artifact_status(kind, artifact_path)
            if status != "active":
                continue

            # Check inbound references via snapshot
            try:
                rel_path = str(artifact_path.relative_to(self.project_root))
            except ValueError:
                continue

            deps = snapshot.reverse_deps(rel_path)
            if len(deps) == 0:
                result.deprecation_items.append(
                    DeprecationCollectItem(
                        artifact_path=artifact_path,
                        artifact_kind=kind,  # type: ignore[arg-type]
                        current_status="active",
                        reason="orphan_zero_refs",
                    )
                )

    def _collect_deleted_source_designs(self, result: CollectResult) -> None:
        """Detect design files whose source file has been deleted."""
        from lexibrary.artifacts.design_file_parser import (  # noqa: PLC0415
            parse_design_file_metadata,
        )

        designs_dir = self.lexibrary_dir / "designs"
        if not designs_dir.is_dir():
            return

        for design_path in sorted(designs_dir.rglob("*.md")):
            if design_path.name.startswith("."):
                continue

            try:
                metadata = parse_design_file_metadata(design_path)
            except Exception as exc:
                self.summary.add("collect", exc, path=str(design_path))
                continue

            if metadata is None:
                continue

            source_path = self.project_root / metadata.source
            if not source_path.exists():
                # Read the design file's status
                status = self._read_artifact_status("design_file", design_path)
                if status in ("deprecated", "unlinked"):
                    continue  # Already handled

                result.deprecation_items.append(
                    DeprecationCollectItem(
                        artifact_path=design_path,
                        artifact_kind="design_file",
                        current_status=status or "active",
                        reason="source_deleted",
                    )
                )

    def _collect_ttl_expired_artifacts(
        self,
        result: CollectResult,
        snapshot: object,
        ttl_commits: int,
    ) -> None:
        """Detect deprecated artifacts past TTL with zero references."""
        # Scan concepts
        concepts_dir = self.lexibrary_dir / "concepts"
        if concepts_dir.is_dir():
            self._scan_ttl_expired(result, concepts_dir, "concept", snapshot, ttl_commits, "*.md")

        # Scan conventions
        conventions_dir = self.lexibrary_dir / "conventions"
        if conventions_dir.is_dir():
            self._scan_ttl_expired(
                result, conventions_dir, "convention", snapshot, ttl_commits, "*.md"
            )

        # Scan playbooks
        playbooks_dir = self.lexibrary_dir / "playbooks"
        if playbooks_dir.is_dir():
            self._scan_ttl_expired(result, playbooks_dir, "playbook", snapshot, ttl_commits, "*.md")

    def _scan_ttl_expired(
        self,
        result: CollectResult,
        directory: Path,
        kind: str,
        snapshot: object,
        ttl_commits: int,
        pattern: str,
    ) -> None:
        """Scan a directory for TTL-expired deprecated artifacts."""
        from lexibrary.curator.cascade import LinkGraphSnapshot  # noqa: PLC0415

        for artifact_path in sorted(directory.glob(pattern)):
            if artifact_path.name.startswith("."):
                continue

            status = self._read_artifact_status(kind, artifact_path)
            if status != "deprecated":
                continue

            # Estimate commits since deprecation via git
            commits_since = self._commits_since_deprecation(artifact_path)

            if commits_since < ttl_commits:
                continue

            # Check zero references via snapshot
            try:
                rel_path = str(artifact_path.relative_to(self.project_root))
            except ValueError:
                continue

            ref_count = 0
            if isinstance(snapshot, LinkGraphSnapshot) and snapshot._link_graph is not None:
                deps = snapshot.reverse_deps(rel_path)
                ref_count = len(deps)

            if ref_count == 0:
                result.deprecation_items.append(
                    DeprecationCollectItem(
                        artifact_path=artifact_path,
                        artifact_kind=kind,  # type: ignore[arg-type]
                        current_status="deprecated",
                        reason="ttl_expired_zero_refs",
                        commits_since_deprecation=commits_since,
                    )
                )

    def _collect_stale_resolved_stack_posts(self, result: CollectResult) -> None:
        """Detect resolved stack posts whose referenced code has changed."""
        from lexibrary.stack.parser import parse_stack_post  # noqa: PLC0415

        stack_dir = self.lexibrary_dir / "stack"
        if not stack_dir.is_dir():
            return

        for post_path in sorted(stack_dir.glob("*.md")):
            if post_path.name.startswith("."):
                continue

            try:
                post = parse_stack_post(post_path)
            except Exception:
                continue

            if post is None or post.frontmatter.status != "resolved":
                continue

            # Check if any referenced files have changed since resolution
            refs = post.frontmatter.refs
            if refs is None:
                continue

            for ref_file in refs.files:
                ref_path = self.project_root / ref_file
                if not ref_path.exists():
                    # Referenced file was deleted -- candidate for stale transition
                    result.deprecation_items.append(
                        DeprecationCollectItem(
                            artifact_path=post_path,
                            artifact_kind="stack_post",
                            current_status="resolved",
                            reason="referenced_code_changed",
                        )
                    )
                    break  # One reason is enough per post

    def _read_artifact_status(self, kind: str, artifact_path: Path) -> str:
        """Read the current status of an artifact from its frontmatter."""
        if kind == "design_file":
            from lexibrary.artifacts.design_file_parser import (  # noqa: PLC0415
                parse_design_file_frontmatter,
            )

            try:
                fm = parse_design_file_frontmatter(artifact_path)
                if fm is not None:
                    return fm.status or "active"
            except Exception:
                pass
            return "active"

        if kind == "concept":
            from lexibrary.wiki.parser import parse_concept_file  # noqa: PLC0415

            try:
                concept = parse_concept_file(artifact_path)
                if concept is not None:
                    return concept.frontmatter.status or "draft"
            except Exception:
                pass
            return "draft"

        if kind == "convention":
            from lexibrary.conventions.parser import parse_convention_file  # noqa: PLC0415

            try:
                convention = parse_convention_file(artifact_path)
                if convention is not None:
                    return convention.frontmatter.status or "draft"
            except Exception:
                pass
            return "draft"

        if kind == "playbook":
            from lexibrary.playbooks.parser import parse_playbook_file  # noqa: PLC0415

            try:
                playbook = parse_playbook_file(artifact_path)
                if playbook is not None:
                    return playbook.frontmatter.status or "draft"
            except Exception:
                pass
            return "draft"

        return ""

    def _commits_since_deprecation(self, artifact_path: Path) -> int:
        """Estimate commits since an artifact was deprecated via git log."""
        try:
            result = subprocess.run(
                ["git", "log", "--oneline", "--follow", "--", str(artifact_path)],
                capture_output=True,
                text=True,
                cwd=self.project_root,
                timeout=30,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return 0
        if result.returncode != 0:
            return 0

        return len(result.stdout.strip().splitlines())

    # -- Budget and comment-audit collection (Phase 3) ----------------------

    def _collect_budget_issues(
        self,
        result: CollectResult,
        *,
        scope: Path | None = None,
    ) -> None:
        """Scan knowledge-layer files for token budget overruns."""
        from lexibrary.curator.budget import scan_token_budgets  # noqa: PLC0415

        try:
            issues = scan_token_budgets(self.project_root, self.curator_config)
        except Exception as exc:
            logger.error("scan_token_budgets() raised: %s", exc)
            self.summary.add("collect", exc, path="budget_scan")
            return

        for issue in issues:
            # Scope filtering
            if scope is not None and not issue.path.is_relative_to(scope):
                continue

            result.budget_items.append(
                BudgetCollectItem(
                    path=issue.path,
                    current_tokens=issue.current_tokens,
                    budget_target=issue.budget_target,
                    file_type=issue.file_type,
                )
            )

    def _collect_comment_audit_issues(
        self,
        result: CollectResult,
        *,
        scope: Path | None = None,
    ) -> None:
        """Scan source files for TODO/FIXME/HACK markers."""
        from lexibrary.curator.auditing import scan_todo_comments  # noqa: PLC0415

        src_dir = self.project_root / "src"
        if not src_dir.is_dir():
            return

        for source_path in sorted(src_dir.rglob("*.py")):
            if source_path.name.startswith("."):
                continue

            # Scope filtering
            if scope is not None and not source_path.is_relative_to(scope):
                continue

            try:
                issues = scan_todo_comments(source_path)
            except Exception as exc:
                self.summary.add("collect", exc, path=str(source_path))
                continue

            for issue in issues:
                result.comment_audit_items.append(
                    CommentAuditCollectItem(
                        path=issue.path,
                        line_number=issue.line_number,
                        comment_text=issue.comment_text,
                        code_context=issue.code_context,
                        marker_type=issue.marker_type,
                    )
                )

    # -- Consistency collection (curator-fix Phase 3 — group 8) -------------

    def _collect_consistency(
        self,
        result: CollectResult,
        *,
        scope: Path | None = None,
        uncommitted: set[Path],
        active_iwh: set[Path],
        layer: Literal["hash", "graph"] | None = None,
    ) -> None:
        """Run :class:`ConsistencyChecker` checks and append ``CollectItem``s.

        Gated on ``self.curator_config.consistency_collect``:
        - ``"off"``   — skip all consistency checks.
        - ``"scope"`` — run scope-bounded checks (orphaned .comments.yaml,
          design-file bidirectional dep cross-reference, stale
          conventions / playbooks, promotable blocked IWH).
        - ``"full"``  — also run library-wide checks (domain-term
          suggestion, orphan concept detection).

        ``FixInstruction`` objects returned by the checker are translated
        into :class:`CollectItem` rows with ``source="consistency"``, the
        raw ``action`` string on ``action_hint``, and the human-readable
        ``detail`` on ``fix_instruction_detail``.  Triage then maps
        ``action_hint`` to a canonical ``action_key`` via
        :data:`lexibrary.curator.consistency_fixes.CONSISTENCY_ACTION_KEYS`.

        ``layer`` tags every emitted :class:`CollectItem` with its
        originating two-pass collect layer.  ``None`` (the default)
        preserves the legacy single-pass behaviour.  Per the
        ``curator-two-pass-collect`` spec this method SHALL only be
        invoked from the graph-layer (or from the legacy single-pass
        flow); it reads link-graph-derived state and so is not safe
        to run before the mid-run ``build_index`` rebuild.
        """
        mode = self.curator_config.consistency_collect
        if mode == "off":
            return

        from lexibrary.curator.consistency import (  # noqa: PLC0415
            ConsistencyChecker,
            FixInstruction,
        )

        resolver = self._build_wikilink_resolver()
        checker = ConsistencyChecker(self.project_root, self.lexibrary_dir, resolver=resolver)

        def _append(instruction: FixInstruction) -> None:
            path = instruction.target_path
            # Consistency paths may be absolute paths anywhere in the
            # library; ``_should_skip_path`` works on absolute paths.
            if _should_skip_path(path, uncommitted, active_iwh):
                return
            if scope is not None:
                # Convert to project-relative comparison where possible.
                try:
                    if not path.is_relative_to(scope):
                        return
                except ValueError:
                    return
            severity: Literal["error", "warning", "info"] = (
                "warning" if instruction.risk == "medium" else "info"
            )
            result.items.append(
                CollectItem(
                    source="consistency",
                    path=path,
                    severity=severity,
                    message=instruction.detail,
                    check="consistency",
                    action_hint=instruction.action,
                    fix_instruction_detail=instruction.detail,
                    layer=layer,
                )
            )

        designs_dir = self.lexibrary_dir / "designs"
        design_files: list[Path] = []
        if designs_dir.is_dir():
            for design_path in sorted(designs_dir.rglob("*.md")):
                if design_path.name.startswith("."):
                    continue
                design_files.append(design_path)

        # -- Scope-bounded checks -----------------------------------------
        # Wikilink hygiene retired in Phase 4 Family D of the
        # ``curator-freshness`` change. The validator's
        # ``check_wikilink_resolution`` paired with
        # :func:`lexibrary.validator.fixes.fix_wikilink_resolution` is now
        # the canonical detector + fixer; the validation bridge surfaces
        # the narrow ``fix_wikilink_resolution`` action key in reports.

        # Slug and alias collision detection retired in Phase 4 Family B of
        # the ``curator-freshness`` change. The validator's
        # ``check_duplicate_slugs`` / ``check_duplicate_aliases`` checks are
        # routed through ``CHECK_TO_ACTION_KEY`` to the propose-only
        # ``fix_duplicate_slugs`` / ``fix_duplicate_aliases`` fixers.

        # Orphaned .comments.yaml cleanup.
        try:
            for instruction in checker.detect_orphaned_comments():
                _append(instruction)
        except Exception as exc:
            self.summary.add("collect", exc, path="orphaned_comments")

        # Bidirectional dep cross-reference across design files.
        try:
            for instruction in checker.detect_design_dep_mismatch(design_files):
                _append(instruction)
        except Exception as exc:
            self.summary.add("collect", exc, path="design_dep_mismatch")

        # Stale convention / playbook path refs.
        try:
            for instruction in checker.detect_stale_conventions(self.lexibrary_dir / "conventions"):
                _append(instruction)
        except Exception as exc:
            self.summary.add("collect", exc, path="stale_conventions")
        try:
            for instruction in checker.detect_stale_playbooks(self.lexibrary_dir / "playbooks"):
                _append(instruction)
        except Exception as exc:
            self.summary.add("collect", exc, path="stale_playbooks")

        # Promotable blocked IWH: scope-level (runs in both "scope" and
        # "full" modes).  The check walks ``.lexibrary/designs/`` for
        # stale ``scope=blocked`` .iwh files; each hit yields a
        # ``promote_blocked_iwh`` escalation instruction.  Moved above
        # the ``full`` guard so default runs surface blocked IWH
        # promotion candidates without requiring full library sweeps.
        try:
            for instruction in checker.detect_promotable_iwh():
                _append(instruction)
        except Exception as exc:
            self.summary.add("collect", exc, path="promotable_iwh")

        if mode != "full":
            return

        # -- Library-wide checks (mode == "full") -------------------------
        try:
            for instruction in checker.detect_domain_terms(design_files):
                _append(instruction)
        except Exception as exc:
            self.summary.add("collect", exc, path="domain_terms")

        try:
            for instruction in checker.detect_orphan_concepts(
                self.lexibrary_dir / "concepts",
                link_graph_available=result.link_graph_available,
            ):
                _append(instruction)
        except Exception as exc:
            self.summary.add("collect", exc, path="orphan_concepts")

    def _build_wikilink_resolver(self) -> WikilinkResolver | None:
        """Build a :class:`WikilinkResolver` from the library layout.

        Returns ``None`` if the concepts directory is missing so
        ``ConsistencyChecker`` falls back to the resolver-less path.
        """
        concepts_dir = self.lexibrary_dir / "concepts"
        if not concepts_dir.is_dir():
            return None
        try:
            from lexibrary.wiki.index import ConceptIndex  # noqa: PLC0415
            from lexibrary.wiki.resolver import (  # noqa: PLC0415
                WikilinkResolver as _Resolver,
            )

            index = ConceptIndex.load(concepts_dir)
            return _Resolver(
                index=index,
                convention_dir=self.lexibrary_dir / "conventions",
                playbook_dir=self.lexibrary_dir / "playbooks",
                designs_dir=self.lexibrary_dir / "designs",
                stack_dir=self.lexibrary_dir / "stack",
            )
        except Exception as exc:
            logger.warning("Failed to build WikilinkResolver: %s", exc)
            return None

    # -- Phase 2: Triage ----------------------------------------------------

    def _triage(self, collect: CollectResult) -> TriageResult:
        """Classify and prioritise collected items for dispatch.

        Propagates the two-pass ``layer`` tag from each source
        :class:`CollectItem` onto the resulting :class:`TriageItem` so
        the ``dispatched_details`` regression surface in ``_report``
        can distinguish hash-pass vs graph-pass dispatches (schema v3).
        Comment / budget / comment-audit collect items do not carry a
        ``layer`` field today; their triage items inherit ``None``.
        """
        result = TriageResult()

        for item in collect.items:
            # Skip scope-isolation placeholders
            if item.check == "scope_isolation":
                continue

            triage_item = self._classify_item(item, collect.link_graph_available)
            if triage_item is not None:
                triage_item.layer = item.layer
                result.items.append(triage_item)

        # Triage comment items into the same priority queue
        for comment_item in collect.comment_items:
            triage_item = self._classify_comment(comment_item)
            result.items.append(triage_item)

        # Triage deprecation candidates -- interleaved with existing items
        for dep_item in collect.deprecation_items:
            triage_item = self._classify_deprecation(dep_item)
            result.items.append(triage_item)

        # Triage budget items (Phase 3)
        for budget_item in collect.budget_items:
            triage_item = self._classify_budget(budget_item)
            result.items.append(triage_item)

        # Triage comment audit items (Phase 3)
        for audit_item in collect.comment_audit_items:
            triage_item = self._classify_comment_audit(audit_item)
            result.items.append(triage_item)

        # Sort by priority (descending = highest first).
        # Within same risk level, more deps = higher priority.
        result.items.sort(key=lambda t: t.priority, reverse=True)
        return result

    def _classify_item(
        self,
        item: CollectItem,
        graph_available: bool,
    ) -> TriageItem | None:
        """Map a CollectItem to a TriageItem with type, action_key, priority."""
        if item.source == "staleness":
            return self._classify_staleness(item, graph_available)
        if item.source == "agent_edit":
            return self._classify_agent_edit(item, graph_available)
        if item.source == "validation":
            return self._classify_validation(item)
        if item.source == "iwh":
            return self._classify_iwh(item)
        if item.source == "consistency":
            return self._classify_consistency(item)
        return None

    def _classify_staleness(
        self,
        item: CollectItem,
        graph_available: bool,
    ) -> TriageItem:
        """Classify a staleness item."""
        agent_edited = item.updated_by in ("agent", "maintainer")

        # Determine action key and risk level based on agent-edited status
        risk_level: str | None = None
        if agent_edited:
            risk_level, action_key = self._reconciliation_risk(
                interface_hash_stale=item.interface_hash_stale,
                design_body_length=item.design_body_length,
            )
        else:
            action_key = "regenerate_stale_design"

        # Priority scoring:
        # - Interface hash change: +100
        # - Source hash change (content only): +50
        # - Agent-edited gets separate classification
        priority = 0.0
        if item.interface_hash_stale:
            priority += 100.0
        if item.source_hash_stale:
            priority += 50.0

        # Reverse dependent count boost (if graph available)
        reverse_dep_count = 0
        if graph_available and item.path is not None:
            reverse_dep_count = self._get_reverse_dep_count(item.path)
            priority += reverse_dep_count * 5.0

        issue_type = "reconciliation" if agent_edited else "staleness"
        return TriageItem(
            source_item=item,
            issue_type=issue_type,  # type: ignore[arg-type]
            action_key=action_key,
            priority=priority,
            agent_edited=agent_edited,
            reverse_dep_count=reverse_dep_count,
            risk_level=risk_level,  # type: ignore[arg-type]
        )

    def _classify_agent_edit(
        self,
        item: CollectItem,
        graph_available: bool,
    ) -> TriageItem:
        """Classify an agent-edit detection item for reconciliation.

        Three-tier risk classification:
        - Interface hash stable + small change -> Low
        - Interface hash changed -> Medium
        - Extensive agent content (body significantly longer than
          typical archivist output) -> High
        """
        risk_level, action_key = self._reconciliation_risk(
            interface_hash_stale=item.interface_hash_stale,
            design_body_length=item.design_body_length,
        )

        # Priority scoring for reconciliation items
        priority = 60.0  # Base priority for reconciliation
        if item.interface_hash_stale:
            priority += 40.0
        if item.source_hash_stale:
            priority += 20.0

        # Reverse dependent count boost
        reverse_dep_count = 0
        if graph_available and item.path is not None:
            reverse_dep_count = self._get_reverse_dep_count(item.path)
            priority += reverse_dep_count * 5.0

        return TriageItem(
            source_item=item,
            issue_type="reconciliation",
            action_key=action_key,
            priority=priority,
            agent_edited=True,
            reverse_dep_count=reverse_dep_count,
            risk_level=risk_level,  # type: ignore[arg-type]
        )

    @staticmethod
    def _reconciliation_risk(
        *,
        interface_hash_stale: bool,
        design_body_length: int,
    ) -> tuple[str, str]:
        """Return ``(risk_level, action_key)`` for an agent-edit reconciliation.

        Classification rules:
        - Extensive agent content (body > 3000 chars) -> High
        - Interface hash changed -> Medium
        - Interface hash stable (small change) -> Low
        """
        # Threshold: a typical archivist-generated design file body is
        # ~800-2000 chars.  Bodies significantly longer (>3000) indicate
        # extensive agent-authored content that is high-risk to merge.
        extensive_threshold = 3000

        if design_body_length > extensive_threshold:
            return "high", "reconcile_agent_extensive_content"
        if interface_hash_stale:
            return "medium", "reconcile_agent_interface_changed"
        return "low", "reconcile_agent_interface_stable"

    def _classify_validation(self, item: CollectItem) -> TriageItem:
        """Classify a validation issue.

        Uses :data:`CHECK_TO_ACTION_KEY` to pick the narrow per-check action
        key (e.g. ``"fix_hash_freshness"``) when the validator check has a
        registered fixer.  Checks without a registered fixer fall back to the
        umbrella ``"autofix_validation_issue"`` key — the dispatch bridge will
        still route them through :func:`fix_validation_issue`, which reports
        ``outcome="no_fixer"`` for unhandled checks.
        """
        # Map validation checks to issue types and action keys
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
        ] = "consistency"
        action_key = CHECK_TO_ACTION_KEY.get(item.check, "autofix_validation_issue")

        # Map severity to priority
        severity_priority = {"error": 80.0, "warning": 40.0, "info": 10.0}
        priority = severity_priority.get(item.severity, 10.0)

        return TriageItem(
            source_item=item,
            issue_type=issue_type,
            action_key=action_key,
            priority=priority,
        )

    def _classify_iwh(self, item: CollectItem) -> TriageItem:
        """Classify an IWH signal.

        ``consume_superseded_iwh`` is routed via ``issue_type="orphan"``
        because it simply deletes a stale signal and has no escalation
        path.  ``promote_blocked_iwh``, however, is an escalation-only
        handler that lives in ``consistency_fixes`` and must be routed
        through ``_dispatch_consistency_fix`` — so it is tagged
        ``issue_type="consistency_fix"``.
        """
        # IWH signals may be superseded or blocked
        if "scope=blocked" in item.message:
            return TriageItem(
                source_item=item,
                issue_type="consistency_fix",
                action_key="promote_blocked_iwh",
                priority=5.0,
            )
        return TriageItem(
            source_item=item,
            issue_type="orphan",
            action_key="consume_superseded_iwh",
            priority=5.0,
        )

    def _classify_consistency(self, item: CollectItem) -> TriageItem:
        """Classify a consistency-checker item (curator-fix Phase 3 — group 8).

        Maps the raw ``action_hint`` (emitted by ``ConsistencyChecker``)
        to a canonical ``action_key`` via
        :data:`lexibrary.curator.consistency_fixes.CONSISTENCY_ACTION_KEYS`.
        Unknown action hints fall back to the hint itself — the dispatch
        router will still report an unrecognised-handler stub so the
        counter logic stays honest.
        """
        from lexibrary.curator.consistency_fixes import (  # noqa: PLC0415
            CONSISTENCY_ACTION_KEYS,
        )

        action_key = CONSISTENCY_ACTION_KEYS.get(item.action_hint, item.action_hint)

        # Resolve the risk level from the taxonomy so autonomy gating
        # defers Medium/High actions correctly under ``auto_low``.
        risk_level: Literal["low", "medium", "high"] | None = None
        try:
            level = get_risk_level(action_key, self.curator_config.risk_overrides)
        except KeyError:
            level = "medium"  # Unknown -- default to Medium so it's deferred.
        if level in ("low", "medium", "high"):
            risk_level = level  # type: ignore[assignment]

        # Priority: Medium/High get a higher base so they surface above
        # routine Low consistency chores in the triage queue.
        risk_base = {"low": 15.0, "medium": 40.0, "high": 70.0}
        priority = risk_base.get(level, 15.0)

        return TriageItem(
            source_item=item,
            issue_type="consistency_fix",
            action_key=action_key,
            priority=priority,
            risk_level=risk_level,
        )

    def _classify_comment(self, item: CommentCollectItem) -> TriageItem:
        """Classify a comment collect item for dispatch."""
        # Priority: base 30 + 10 per comment (higher count = higher priority)
        priority = 30.0 + item.comment_count * 10.0

        return TriageItem(
            source_item=CollectItem(
                source="validation",  # Reuse validation source type for compatibility
                path=item.source_path,
                severity="info",
                message=f"Unprocessed comments: {item.comment_count}",
                check="comment_integration",
            ),
            issue_type="comment",
            action_key="integrate_sidecar_comments",
            priority=priority,
            comment_item=item,
        )

    def _classify_deprecation(self, item: DeprecationCollectItem) -> TriageItem:
        """Classify a deprecation candidate for dispatch.

        Assigns action key based on artifact kind and reason, and ranks
        by risk level (low first) then reverse dependent count (more deps
        = higher priority within same risk).
        """
        action_key = self._deprecation_action_key(item)
        try:
            risk_level = get_risk_level(action_key, self.curator_config.risk_overrides)
        except KeyError:
            risk_level = "medium"

        # Priority: low risk = base 20, medium = base 60, high = base 100.
        # Then add reverse_dep_count * 2 so more deps rise within same risk.
        risk_base = {"low": 20.0, "medium": 60.0, "high": 100.0}
        priority = risk_base.get(risk_level, 60.0) + item.reverse_dep_count * 2.0

        return TriageItem(
            source_item=CollectItem(
                source="deprecation",
                path=item.artifact_path,
                severity="warning",
                message=f"Deprecation candidate: {item.reason} ({item.artifact_kind})",
                check="deprecation",
            ),
            issue_type="deprecation",
            action_key=action_key,
            priority=priority,
            reverse_dep_count=item.reverse_dep_count,
            deprecation_item=item,
            risk_level=risk_level,  # type: ignore[arg-type]
        )

    @staticmethod
    def _deprecation_action_key(item: DeprecationCollectItem) -> str:
        """Map a deprecation candidate to its risk-taxonomy action key."""
        kind = item.artifact_kind
        reason = item.reason

        if reason == "ttl_expired_zero_refs":
            return f"hard_delete_{kind}_past_ttl"

        if reason == "source_deleted" and kind == "design_file":
            return "deprecate_design_file"

        if reason == "orphan_zero_refs":
            if kind == "concept":
                return "deprecate_concept"
            if kind == "convention":
                return "deprecate_convention"
            if kind == "playbook":
                return "deprecate_playbook"

        if reason == "referenced_code_changed" and kind == "stack_post":
            return "stack_post_transition"

        # Fallback
        return f"deprecate_{kind}"

    def _classify_budget(self, item: BudgetCollectItem) -> TriageItem:
        """Classify a budget issue for dispatch.

        Budget condensation is High risk (``condense_file``).  Priority
        scales with the overage ratio so larger overruns are processed first.
        """
        # Overage ratio drives priority within budget issues
        overage_ratio = item.current_tokens / max(item.budget_target, 1)
        priority = 40.0 + min(overage_ratio * 10.0, 60.0)

        return TriageItem(
            source_item=CollectItem(
                source="validation",
                path=item.path,
                severity="warning",
                message=(
                    f"Over budget: {item.current_tokens} tokens "
                    f"(limit {item.budget_target}, type={item.file_type})"
                ),
                check="budget",
            ),
            issue_type="budget",
            action_key="condense_file",
            priority=priority,
            budget_item=item,
            risk_level="high",
        )

    def _classify_comment_audit(self, item: CommentAuditCollectItem) -> TriageItem:
        """Classify a comment audit issue for dispatch.

        Comment staleness assessment is Medium risk (``flag_stale_comment``).
        """
        return TriageItem(
            source_item=CollectItem(
                source="validation",
                path=item.path,
                severity="info",
                message=(
                    f"{item.marker_type} at line {item.line_number}: {item.comment_text[:80]}"
                ),
                check="comment_audit",
            ),
            issue_type="comment_audit",
            action_key="flag_stale_comment",
            priority=25.0,
            comment_audit_item=item,
            risk_level="medium",
        )

    def _get_reverse_dep_count(self, source_path: Path) -> int:
        """Query the link graph for reverse dependent count."""
        from lexibrary.linkgraph.query import LinkGraph  # noqa: PLC0415

        db_path = self.lexibrary_dir / "index.db"
        graph = LinkGraph.open(db_path)
        if graph is None:
            return 0
        try:
            rel = source_path.relative_to(self.project_root)
            dependents = graph.reverse_deps(str(rel))
            return len(dependents)
        except Exception:
            return 0
        finally:
            graph.close()

    # -- Phase 3: Dispatch --------------------------------------------------

    async def _dispatch(
        self,
        triage: TriageResult,
        *,
        dry_run: bool = False,
        budget_cap: int | None = None,
    ) -> DispatchResult:
        """Apply autonomy gating and dispatch to sub-agent stubs.

        Parameters
        ----------
        triage:
            The triage-phase result whose items will be dispatched.
        dry_run:
            When ``True``, record dispatched items with
            ``outcome="dry_run"`` but do not actually invoke handlers.
        budget_cap:
            Optional per-pass LLM-call ceiling.  When ``None`` (default,
            legacy behaviour), only the shared
            ``curator_config.max_llm_calls_per_run`` cap applies.  When
            set, this dispatch call stops issuing new LLM calls once
            ``result.llm_calls_used >= budget_cap`` — even if the shared
            counter would allow more.  Used by the two-pass flow to
            enforce the 70/30 split: the hash-layer pass caps itself at
            ``int(max_llm_calls_per_run * 0.7)`` while the graph-layer
            pass uses the full ``max_llm_calls_per_run`` (the shared
            counter, seeded with the hash-pass total, handles the
            subtraction automatically).
        """
        # Stash on self so handlers consuming _ctx() see the correct flag.
        self._dry_run = dry_run
        # Seed ``llm_calls_used`` from ``self.pre_charged_llm_calls`` so the
        # dispatch cap accounts for LLM calls already consumed before the
        # dispatch phase (e.g., the reactive-hook archivist regeneration
        # path under ``reactive_bootstrap_regenerate=True``, or — in the
        # two-pass flow — the hash-layer dispatch that already ran).
        # When the counter is zero (default), behaviour is unchanged.
        result = DispatchResult(llm_calls_used=self.pre_charged_llm_calls)
        autonomy = self.curator_config.autonomy
        overrides = self.curator_config.risk_overrides
        max_llm = self.curator_config.max_llm_calls_per_run
        # Effective per-pass ceiling.  When ``budget_cap`` is ``None`` the
        # per-pass ceiling is the shared cap (so behaviour is identical to
        # single-pass dispatch).  When set, take the stricter of the two —
        # ``budget_cap`` must never exceed ``max_llm_calls_per_run``.
        effective_cap = max_llm if budget_cap is None else min(budget_cap, max_llm)

        for item in triage.items:
            # Check LLM call cap (per-pass budget_cap OR shared max_llm)
            if result.llm_calls_used >= effective_cap:
                result.llm_cap_reached = True
                item_copy = TriageItem(
                    source_item=item.source_item,
                    issue_type=item.issue_type,
                    action_key=item.action_key,
                    priority=item.priority,
                    agent_edited=item.agent_edited,
                    reverse_dep_count=item.reverse_dep_count,
                    layer=item.layer,
                )
                result.deferred.append(item_copy)
                continue

            # Build confirmation overrides from config
            confirmation_overrides: dict[str, bool] = {}
            if self.config.concepts.curator_deprecation_confirm:
                confirmation_overrides["concept"] = True
            if self.config.conventions.curator_deprecation_confirm:
                confirmation_overrides["convention"] = True

            # Autonomy gating (with confirmation overrides for deprecation)
            try:
                dispatch = should_dispatch(
                    item.action_key,
                    autonomy,
                    overrides,
                    confirmation_overrides=confirmation_overrides or None,
                )
            except KeyError:
                # Unknown action key -- defer
                self.summary.add(
                    "dispatch",
                    KeyError(f"Unknown action key: {item.action_key}"),
                    path=str(item.source_item.path),
                )
                result.deferred.append(item)
                continue

            if not dispatch:
                result.deferred.append(item)
                # Write IWH signal for gated deprecation actions
                if item.issue_type == "deprecation" and item.deprecation_item is not None:
                    self._write_deprecation_proposal_iwh(item)
                continue

            if dry_run:
                # In dry-run mode, record as dispatched but don't execute.
                # Propagate the two-pass ``layer`` tag from the triage item
                # (schema v3) so downstream readers of ``dispatched_details``
                # can distinguish hash-pass vs graph-pass dispatches.
                result.dispatched.append(
                    SubAgentResult(
                        success=True,
                        action_key=item.action_key,
                        path=item.source_item.path,
                        message="dry-run: would dispatch",
                        llm_calls=0,
                        outcome="dry_run",
                        layer=item.layer,
                    )
                )
                continue

            # Dispatch to sub-agent handler (or stub fallback for unrecognized keys).
            # Handlers construct ``SubAgentResult`` without knowledge of the
            # originating triage layer; overlay the tag here so the per-item
            # ``layer`` field survives end-to-end in schema v3.
            agent_result = await self._route_to_handler(item)
            agent_result.layer = item.layer
            result.dispatched.append(agent_result)
            result.llm_calls_used += agent_result.llm_calls

        return result

    async def _route_to_handler(self, item: TriageItem) -> SubAgentResult:
        """Route a triage item to the matching public dispatch function.

        Pure router — contains zero business logic.  Every branch imports
        the module-level dispatch function (defined in a sibling curator
        module) and delegates with ``self._ctx()``.  The final fallback
        returns a stub ``SubAgentResult`` (``outcome="stubbed"``) for
        action keys that do not yet have a handler wired up.
        """
        # Deprecation workflow dispatch
        if item.issue_type == "deprecation" and item.deprecation_item is not None:
            from lexibrary.curator.deprecation import (  # noqa: PLC0415
                dispatch_deprecation_router,
            )

            return dispatch_deprecation_router(item, self._ctx())

        # Validation bridge — route per-check and umbrella validation keys to
        # the validator-fixer bridge.  The bridge is a synchronous helper that
        # takes the coordinator state directly rather than a DispatchContext.
        if item.action_key in VALIDATION_ACTION_KEYS:
            from lexibrary.curator.validation_fixers import (  # noqa: PLC0415
                fix_validation_issue,
            )

            return fix_validation_issue(item, self.project_root, self.config)

        if item.action_key == "regenerate_stale_design":
            from lexibrary.curator.staleness import (  # noqa: PLC0415
                dispatch_staleness_resolver,
            )

            return dispatch_staleness_resolver(item, self._ctx())

        if item.action_key in (
            "reconcile_agent_interface_stable",
            "reconcile_agent_interface_changed",
            "reconcile_agent_extensive_content",
        ):
            from lexibrary.curator.reconciliation import (  # noqa: PLC0415
                dispatch_reconciliation,
            )

            return dispatch_reconciliation(item, self._ctx())

        if item.action_key == "integrate_sidecar_comments":
            from lexibrary.curator.comments import (  # noqa: PLC0415
                dispatch_comment_integration,
            )

            return dispatch_comment_integration(item, self._ctx())

        # Phase 3: Budget Trimmer dispatch
        if item.issue_type == "budget" and item.budget_item is not None:
            from lexibrary.curator.budget import (  # noqa: PLC0415
                dispatch_budget_condense,
            )

            return await dispatch_budget_condense(item, self._ctx())

        # Phase 3: Comment Auditor dispatch
        if item.issue_type == "comment_audit" and item.comment_audit_item is not None:
            from lexibrary.curator.auditing import (  # noqa: PLC0415
                dispatch_comment_audit,
            )

            return await dispatch_comment_audit(item, self._ctx())

        # curator-fix Phase 3 — group 8: Consistency Integration
        # Every item with ``issue_type="consistency_fix"`` routes through
        # the coordinator-level dispatcher which in turn calls a helper
        # in :mod:`lexibrary.curator.consistency_fixes`.
        if item.issue_type == "consistency_fix":
            return self._dispatch_consistency_fix(item)

        # curator-fix Phase 4 — group 9: IWH residual handlers
        # Route the three residual IWH action keys to the public helpers
        # in :mod:`lexibrary.curator.iwh_actions`.  These handlers never
        # modify design files, never call LLMs, and never raise; they
        # return ``outcome="errored"`` on failure so the honest counter
        # logic reports them correctly.
        if item.action_key == "consume_superseded_iwh":
            from lexibrary.curator.iwh_actions import (  # noqa: PLC0415
                consume_superseded_iwh,
            )

            return consume_superseded_iwh(item, self._ctx())

        if item.action_key == "write_reactive_iwh":
            from lexibrary.curator.iwh_actions import (  # noqa: PLC0415
                write_reactive_iwh,
            )

            return write_reactive_iwh(item, self._ctx())

        if item.action_key == "flag_unresolvable_agent_design":
            from lexibrary.curator.iwh_actions import (  # noqa: PLC0415
                flag_unresolvable_agent_design,
            )

            return flag_unresolvable_agent_design(item, self._ctx())

        # Stub fallback for action keys without a wired handler.
        try:
            risk = get_risk_level(item.action_key, self.curator_config.risk_overrides)
        except KeyError:
            risk = "unknown"

        llm_calls = 1 if risk in ("medium", "high") else 0
        return SubAgentResult(
            success=True,
            action_key=item.action_key,
            path=item.source_item.path,
            message=f"stub: {item.action_key} (risk={risk})",
            llm_calls=llm_calls,
            outcome="stubbed",
        )

    # -- Dispatch delegates -------------------------------------------------
    #
    # Each of the methods below is a thin one-line delegation to a public
    # ``dispatch_*`` function living in a sibling curator module.  They are
    # kept for backward compatibility with tests that patch the Coordinator
    # bound methods; new tests should target the module-level functions
    # directly.

    def _dispatch_staleness_resolver(self, item: TriageItem) -> SubAgentResult:
        from lexibrary.curator.staleness import (  # noqa: PLC0415
            dispatch_staleness_resolver,
        )

        return dispatch_staleness_resolver(item, self._ctx())

    def _dispatch_reconciliation(self, item: TriageItem) -> SubAgentResult:
        from lexibrary.curator.reconciliation import (  # noqa: PLC0415
            dispatch_reconciliation,
        )

        return dispatch_reconciliation(item, self._ctx())

    def _dispatch_comment_integration(self, item: TriageItem) -> SubAgentResult:
        from lexibrary.curator.comments import (  # noqa: PLC0415
            dispatch_comment_integration,
        )

        return dispatch_comment_integration(item, self._ctx())

    async def _dispatch_budget_condense(self, item: TriageItem) -> SubAgentResult:
        from lexibrary.curator.budget import (  # noqa: PLC0415
            dispatch_budget_condense,
        )

        return await dispatch_budget_condense(item, self._ctx())

    async def _dispatch_comment_audit(self, item: TriageItem) -> SubAgentResult:
        from lexibrary.curator.auditing import (  # noqa: PLC0415
            dispatch_comment_audit,
        )

        return await dispatch_comment_audit(item, self._ctx())

    def _dispatch_deprecation(self, item: TriageItem) -> SubAgentResult:
        from lexibrary.curator.deprecation import (  # noqa: PLC0415
            dispatch_deprecation_router,
        )

        return dispatch_deprecation_router(item, self._ctx())

    def _dispatch_hard_delete(
        self, item: TriageItem, dep: DeprecationCollectItem
    ) -> SubAgentResult:
        from lexibrary.curator.lifecycle import dispatch_hard_delete  # noqa: PLC0415

        return dispatch_hard_delete(item, self._ctx(), dep)

    def _dispatch_stack_transition(
        self, item: TriageItem, dep: DeprecationCollectItem
    ) -> SubAgentResult:
        from lexibrary.curator.lifecycle import (  # noqa: PLC0415
            dispatch_stack_transition,
        )

        return dispatch_stack_transition(item, self._ctx(), dep)

    def _dispatch_soft_deprecation(
        self, item: TriageItem, dep: DeprecationCollectItem
    ) -> SubAgentResult:
        from lexibrary.curator.deprecation import (  # noqa: PLC0415
            dispatch_soft_deprecation,
        )

        return dispatch_soft_deprecation(item, self._ctx(), dep)

    # -- Consistency dispatch (curator-fix Phase 3 — group 8) ---------------

    def _dispatch_consistency_fix(self, item: TriageItem) -> SubAgentResult:
        """Route a ``consistency_fix`` triage item to the matching fix helper.

        The mapping from canonical ``action_key`` to helper function lives
        in :mod:`lexibrary.curator.consistency_fixes`.  Unknown action keys
        fall through to a stub result so the honest counter logic still
        records them as ``outcome="stubbed"``.
        """
        from lexibrary.curator import consistency_fixes  # noqa: PLC0415

        # Canonical action_key -> helper function.  The mapping keys
        # mirror :data:`CONSISTENCY_ACTION_KEYS` values.
        handlers = {
            "delete_orphaned_comments": consistency_fixes.apply_orphaned_comments_delete,
            "remove_orphan_zero_deps": consistency_fixes.apply_orphan_concept_delete,
            "add_missing_reverse_dep": consistency_fixes.apply_add_reverse_dep,
            "flag_stale_convention": consistency_fixes.apply_flag_stale_convention,
            "flag_stale_playbook": consistency_fixes.apply_flag_stale_playbook,
            "suggest_new_concept": consistency_fixes.apply_suggest_new_concept,
            "promote_blocked_iwh": consistency_fixes.apply_promote_blocked_iwh,
        }

        handler = handlers.get(item.action_key)
        if handler is None:
            return SubAgentResult(
                success=True,
                action_key=item.action_key,
                path=item.source_item.path,
                message=f"stub: consistency {item.action_key} (no handler)",
                llm_calls=0,
                outcome="stubbed",
            )

        try:
            return handler(item, self._ctx())
        except Exception as exc:
            self.summary.add(
                "dispatch",
                exc,
                path=str(item.source_item.path) if item.source_item.path else "",
            )
            return SubAgentResult(
                success=False,
                action_key=item.action_key,
                path=item.source_item.path,
                message=f"consistency fix error: {exc}",
                llm_calls=0,
                outcome="errored",
            )

    def _write_deprecation_proposal_iwh(self, item: TriageItem) -> None:
        """Write an IWH signal for a proposed (gated) deprecation action."""
        from lexibrary.iwh.writer import write_iwh  # noqa: PLC0415

        dep = item.deprecation_item
        if dep is None:
            return

        # The artifact already lives inside .lexibrary/ (concepts, conventions,
        # designs, playbooks, stack), so its parent is the correct target.
        # Do not re-prefix with self.lexibrary_dir — that produced a nested
        # .lexibrary/.lexibrary/ path.
        target_dir = dep.artifact_path.parent

        body = (
            f"Proposed deprecation: {dep.artifact_kind} at {dep.artifact_path.name}\n"
            f"Reason: {dep.reason}\n"
            f"Action key: {item.action_key}\n"
            f"Risk level: {item.risk_level or 'unknown'}\n"
            f"Autonomy gating prevented automatic execution."
        )

        try:
            write_iwh(target_dir, author="curator", scope="warning", body=body)
        except Exception as exc:
            logger.warning("Failed to write deprecation proposal IWH: %s", exc)

    # -- Migration dispatch cycle -------------------------------------------

    def _dispatch_migrations(
        self,
        dispatch_result: DispatchResult,
        *,
        dry_run: bool = False,
    ) -> tuple[int, int]:
        """Run the migration dispatch cycle after deprecations are committed.

        Iterates migration edits from sub-agent results.  Gates each
        migration batch by autonomy (Medium risk).  Under ``auto_low``,
        proposes the migration plan.  Under ``full``, calls
        ``apply_migration_edits()`` then ``verify_migration()``.

        Returns
        -------
        tuple[int, int]
            ``(migrations_applied, migrations_proposed)`` counts.
        """
        from lexibrary.curator.migration import (  # noqa: PLC0415
            verify_migration,
        )
        from lexibrary.linkgraph.query import open_index  # noqa: PLC0415

        migrations_applied = 0
        migrations_proposed = 0

        # Collect deprecation results that may have migration edits
        # (In the current stub implementation, migration edits will be
        # populated when the BAML sub-agent is wired in.  For now,
        # this structure is ready for that integration.)
        deprecation_results = [
            d
            for d in dispatch_result.dispatched
            if d.success and d.action_key.startswith("deprecate_")
        ]

        if not deprecation_results:
            return (0, 0)

        autonomy = self.curator_config.autonomy
        overrides = self.curator_config.risk_overrides

        # Check if migration is allowed under current autonomy
        try:
            can_migrate = should_dispatch("apply_migration_edits", autonomy, overrides)
        except KeyError:
            can_migrate = False

        if dry_run or not can_migrate:
            # Propose migrations without executing
            migrations_proposed = len(deprecation_results)
            return (0, migrations_proposed)

        # Execute migrations for each deprecation that has edits
        link_graph = open_index(self.project_root)
        try:
            for dep_result in deprecation_results:
                # Verify migration after deprecation
                if dep_result.path is not None:
                    try:
                        rel_path = str(dep_result.path.relative_to(self.project_root))
                    except ValueError:
                        rel_path = str(dep_result.path)

                    remaining = verify_migration(rel_path, link_graph)
                    if remaining:
                        logger.info(
                            "Post-deprecation: %s still has %d inbound refs",
                            dep_result.path.name,
                            len(remaining),
                        )
                    migrations_applied += 1
        except Exception as exc:
            self.summary.add("dispatch", exc, path="migration_cycle")
        finally:
            if link_graph is not None:
                link_graph.close()

        return (migrations_applied, migrations_proposed)

    # -- Phase 3c: Post-sweep verification (curator-fix Phase 5) -------------

    def _verify_after_sweep(self, *, check: str | None = None) -> dict[str, int] | None:
        """Optionally re-run ``validate_library()`` to measure sweep impact.

        Returns a ``{"before": int, "after": int, "delta": int}`` dict when
        ``curator_config.verify_after_sweep`` is True and the pre-sweep
        validation call during ``_collect_validation`` succeeded.  Returns
        ``None`` when verification is disabled, when the pre-sweep count
        was never captured (validator raised), or when the post-sweep
        validator itself raises.

        The ``delta`` is expressed as ``before - after`` — a positive
        value indicates issues were resolved during the sweep.  This is
        strictly observability data; it does not affect which fixes ran.

        The ``check`` filter is passed through unchanged so the after-count
        is scoped to the same subset of checks as the before-count.  This
        keeps the delta meaningful when callers invoke the coordinator
        with ``--check <name>``.
        """
        if not self.curator_config.verify_after_sweep:
            return None
        if self._validation_before_count is None:
            return None

        from lexibrary.validator import validate_library  # noqa: PLC0415

        try:
            report = validate_library(
                self.project_root,
                self.lexibrary_dir,
                check_filter=check,
            )
        except Exception as exc:
            logger.error("validate_library() (post-sweep) raised: %s", exc)
            self.summary.add("verify", exc, path="validate_library")
            return None

        before = self._validation_before_count
        after = len(report.issues)
        return {"before": before, "after": after, "delta": before - after}

    # -- Phase 4: Report ----------------------------------------------------

    def _report(
        self,
        collect: CollectResult,
        triage: TriageResult,
        dispatch: DispatchResult,
        *,
        migrations_applied: int = 0,
        migrations_proposed: int = 0,
        trigger: str = "on_demand",
        verification: dict[str, int] | None = None,
    ) -> CuratorReport:
        """Aggregate results into a CuratorReport and write to disk."""
        # Count sub-agent calls by type
        sub_agent_calls: dict[str, int] = {}
        for d in dispatch.dispatched:
            sub_agent_calls[d.action_key] = sub_agent_calls.get(d.action_key, 0) + 1

        # Count fixed and stubbed from outcome field
        fixed = sum(1 for d in dispatch.dispatched if d.outcome == "fixed")
        stubbed = sum(1 for d in dispatch.dispatched if d.outcome == "stubbed")

        # Populate dispatched_details for verbose rendering and persisted report.
        # Schema v3 adds the per-item ``layer`` key (``"hash"``/``"graph"``/``None``)
        # so post-run introspection can attribute each dispatch to the
        # two-pass layer that produced it.
        dispatched_details: list[dict[str, object]] = [
            {
                "action_key": d.action_key,
                "path": str(d.path) if d.path is not None else None,
                "message": d.message,
                "success": d.success,
                "outcome": d.outcome,
                "llm_calls": d.llm_calls,
                "layer": d.layer,
            }
            for d in dispatch.dispatched
        ]

        # Populate deferred_details for verbose rendering and persisted report
        deferred_details: list[dict[str, object]] = [
            {
                "action_key": t.action_key,
                "issue_type": t.issue_type,
                "path": (str(t.source_item.path) if t.source_item.path is not None else None),
                "check": t.source_item.check,
                "message": t.source_item.message,
                "risk_level": t.risk_level,
            }
            for t in dispatch.deferred
        ]

        # Count deprecation-specific results
        deprecated = sum(
            1
            for d in dispatch.dispatched
            if d.success and d.action_key.startswith("deprecate_") and d.outcome != "dry_run"
        )
        hard_deleted = sum(
            1
            for d in dispatch.dispatched
            if d.success and d.action_key.startswith("hard_delete_") and d.outcome != "dry_run"
        )

        # Phase 3: Budget and auditing counters
        budget_condensed = sum(
            1
            for d in dispatch.dispatched
            if d.success and d.action_key == "condense_file" and d.outcome != "dry_run"
        )
        budget_proposed = sum(
            1
            for d in dispatch.dispatched
            if d.success and d.action_key == "propose_condensation" and d.outcome != "dry_run"
        )
        comments_flagged = sum(
            1
            for d in dispatch.dispatched
            if d.success and d.action_key == "flag_stale_comment" and d.outcome != "dry_run"
        )
        descriptions_audited = sum(
            1
            for d in dispatch.dispatched
            if d.success and d.action_key == "audit_description" and d.outcome != "dry_run"
        )
        summaries_audited = sum(
            1
            for d in dispatch.dispatched
            if d.success and d.action_key == "audit_summary" and d.outcome != "dry_run"
        )

        # Errors from ErrorSummary
        errors = [
            {
                "phase": rec.phase,
                "path": rec.path or "",
                "message": rec.message,
            }
            for rec in self.summary.records
        ]

        # Validate trigger literal
        valid_triggers = {
            "on_demand",
            "reactive_post_edit",
            "reactive_post_bead_close",
            "reactive_validation_failure",
            "scheduled",
        }
        trigger_value = trigger if trigger in valid_triggers else "on_demand"

        report = CuratorReport(
            checked=len(triage.items),
            fixed=fixed,
            deferred=len(dispatch.deferred),
            errored=self.summary.count,
            errors=errors,
            sub_agent_calls=sub_agent_calls,
            deprecated=deprecated,
            hard_deleted=hard_deleted,
            migrations_applied=migrations_applied,
            migrations_proposed=migrations_proposed,
            budget_condensed=budget_condensed,
            budget_proposed=budget_proposed,
            comments_flagged=comments_flagged,
            descriptions_audited=descriptions_audited,
            summaries_audited=summaries_audited,
            schema_version=3,
            stubbed=stubbed,
            dispatched_details=dispatched_details,
            deferred_details=deferred_details,
            trigger=trigger_value,  # type: ignore[arg-type]
            verification=verification,
        )

        # Write report to disk
        report.report_path = self._write_report(report)

        return report

    def _write_report(self, report: CuratorReport) -> Path | None:
        """Write JSON report to .lexibrary/curator/reports/."""
        reports_dir = self.lexibrary_dir / "curator" / "reports"
        try:
            reports_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.summary.add("report", exc, path=str(reports_dir))
            return None

        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        report_file = reports_dir / f"{timestamp}.json"

        data: dict[str, object] = {
            "schema_version": report.schema_version,
            "timestamp": timestamp,
            "trigger": report.trigger,
            "checked": report.checked,
            "fixed": report.fixed,
            "stubbed": report.stubbed,
            "deferred": report.deferred,
            "errored": report.errored,
            "errors": report.errors,
            "sub_agent_calls": report.sub_agent_calls,
            "dispatched": report.dispatched_details,
            "deferred_details": report.deferred_details,
            "deprecated": report.deprecated,
            "hard_deleted": report.hard_deleted,
            "migrations_applied": report.migrations_applied,
            "migrations_proposed": report.migrations_proposed,
            "budget_condensed": report.budget_condensed,
            "budget_proposed": report.budget_proposed,
            "comments_flagged": report.comments_flagged,
            "descriptions_audited": report.descriptions_audited,
            "summaries_audited": report.summaries_audited,
        }
        # Phase 5 (curator-fix): emit the post-sweep verification block only
        # when the feature is enabled and the delta was computed.  The key's
        # absence for default runs is part of the contract — see
        # ``test_verification_delta_disabled_by_default``.
        if report.verification is not None:
            data["verification"] = report.verification

        try:
            report_file.write_text(
                json.dumps(data, indent=2, default=str),
                encoding="utf-8",
            )
        except OSError as exc:
            self.summary.add("report", exc, path=str(report_file))
            return None

        return report_file
