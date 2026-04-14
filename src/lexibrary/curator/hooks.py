"""Reactive hook entry points for the curator subsystem.

Provides three hook functions that trigger scoped coordinator runs:
- post_edit_hook: fires after a source file under ``src/`` is modified
- post_bead_close_hook: fires after a bead-agent closes a bead
- validation_failure_hook: fires when validation surfaces errors above a
  configurable severity threshold

All hooks respect the ``ReactiveConfig`` toggles, the PID-file concurrency
lock, and the shared LLM call cap.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from lexibrary.config.loader import load_config
from lexibrary.config.schema import LexibraryConfig
from lexibrary.curator.config import ReactiveConfig
from lexibrary.curator.coordinator import (
    CuratorLockError,
    _acquire_lock,
    _release_lock,
)
from lexibrary.validator.report import ValidationIssue

if TYPE_CHECKING:
    from lexibrary.curator.coordinator import Coordinator

logger = logging.getLogger(__name__)

# Check types that map to known sub-agents for validation-failure dispatch.
# Staleness-related checks -> Staleness Resolver
_STALENESS_CHECKS: frozenset[str] = frozenset(
    {
        "stale_agent_design",
        "hash_freshness",
        "stale_concept",
    }
)
# Consistency/wikilink checks -> Consistency Checker
_CONSISTENCY_CHECKS: frozenset[str] = frozenset(
    {
        "wikilink_resolution",
    }
)

# Severity ordering for threshold comparison.
_SEVERITY_ORDER: dict[str, int] = {
    "info": 0,
    "warning": 1,
    "error": 2,
    "critical": 3,
}


def _severity_at_or_above(severity: str, threshold: str) -> bool:
    """Return True if *severity* meets or exceeds *threshold*."""
    return _SEVERITY_ORDER.get(severity, 0) >= _SEVERITY_ORDER.get(threshold, 2)


def _is_source_file(file_path: Path, project_root: Path) -> bool:
    """Return True if *file_path* is under the ``src/`` tree of the project."""
    try:
        rel = file_path.resolve().relative_to(project_root.resolve())
    except ValueError:
        return False
    parts = rel.parts
    return len(parts) > 0 and parts[0] == "src"


async def _run_coordinator(
    project_root: Path,
    config: LexibraryConfig,
    *,
    scope: Path | None = None,
    trigger: str = "on_demand",
    coordinator: Coordinator | None = None,
) -> None:
    """Instantiate (or reuse) and run the coordinator, handling lock contention.

    ``coordinator`` allows callers such as :func:`post_edit_hook` to thread an
    already-built instance in so that any state seeded on it prior to
    ``.run(...)`` (for example ``pre_charged_llm_calls`` after an archivist
    regeneration) is honoured by the dispatch phase.  When ``None`` (the
    default and legacy behaviour), a fresh coordinator is constructed here.
    """
    from lexibrary.curator.coordinator import Coordinator  # noqa: PLC0415

    if coordinator is None:
        coordinator = Coordinator(project_root, config)
    try:
        await coordinator.run(scope=scope, trigger=trigger)
    except CuratorLockError:
        logger.info(
            "Curator already running (lock held); skipping reactive %s",
            trigger,
        )


def _bootstrap_refresh_indexes(
    file_path: Path,
    project_root: Path,
    config: LexibraryConfig,
) -> None:
    """Refresh symbol and link graphs for *file_path* under the curator PID lock.

    Per the ``curator-reactive-hooks`` spec, the reactive post-edit hook
    SHALL refresh both indexes for the edited source file before handing
    off to the coordinator.  The refresh runs inside the same PID-file
    lock used by :class:`Coordinator` so a concurrent coordinator run is
    never racing against this bootstrap for ``.lexibrary/index.db``.

    Lock behaviour:
        * If the lock is contended (another curator or bootstrap is
          running), we log-skip and return — the concurrent writer will
          produce a consistent index when it finishes.
        * On any other exception during refresh, we log and continue —
          the coordinator must still run even when a bootstrap step
          fails.

    Refresh order:
        1. ``symbolgraph.builder.refresh_file`` — skipped silently when
           ``symbols.db`` is absent (the helper guards this itself); any
           parse/IO error is logged and swallowed so link-graph refresh
           still runs.
        2. ``linkgraph.builder.build_index`` with ``changed_paths=[file_path]``
           — incremental update for the single edited file.

    Parameters
    ----------
    file_path:
        Absolute path to the edited source file.
    project_root:
        Absolute path to the project root.
    config:
        Loaded :class:`LexibraryConfig` used by
        :func:`symbolgraph.builder.refresh_file`.
    """
    from lexibrary.linkgraph.builder import build_index  # noqa: PLC0415
    from lexibrary.symbolgraph.builder import (  # noqa: PLC0415
        refresh_file as _refresh_symbols,
    )

    try:
        _acquire_lock(project_root)
    except CuratorLockError:
        logger.info(
            "Curator lock held; skipping reactive post_edit bootstrap for %s",
            file_path,
        )
        return

    try:
        # Symbol-graph refresh: tolerate a missing symbols.db and any
        # per-file extraction failure.  The helper already silently
        # no-ops when the DB is absent, but we still wrap the call so a
        # surprise exception never blocks the link-graph rebuild below.
        try:
            _refresh_symbols(project_root, config, file_path)
        except Exception:
            logger.warning(
                "post_edit bootstrap: symbolgraph.refresh_file raised for %s — "
                "continuing with link-graph rebuild",
                file_path,
                exc_info=True,
            )

        # Link-graph incremental rebuild for the single edited file.
        try:
            build_index(project_root, changed_paths=[file_path])
        except Exception:
            logger.warning(
                "post_edit bootstrap: linkgraph.build_index raised for %s — "
                "continuing without a refreshed link graph",
                file_path,
                exc_info=True,
            )
    finally:
        _release_lock(project_root)


async def _bootstrap_archivist_regenerate(
    file_path: Path,
    project_root: Path,
    config: LexibraryConfig,
    coordinator: Coordinator,
) -> None:
    """Invoke ``archivist.pipeline.update_file`` for the edited source file.

    Called by :func:`post_edit_hook` only when
    ``curator.reactive_bootstrap_regenerate`` is ``True``.  Builds a fresh
    archivist service via :func:`build_archivist_service` and awaits
    :func:`archivist.pipeline.update_file`.  The invocation is accounted
    against ``curator.max_llm_calls_per_run`` by incrementing
    ``coordinator.pre_charged_llm_calls`` when ``update_file`` actually
    issues an LLM call (i.e. returned without an early no-op or failure).

    An ``update_file`` run that returns UNCHANGED, AGENT_UPDATED, a size-gate
    skeleton fallback, or any failure path does NOT make an LLM call and
    therefore SHALL NOT be charged against the budget.

    Exceptions are logged and swallowed so the coordinator run still
    proceeds; a failure to regenerate is not a reason to drop the reactive
    post-edit pass.
    """
    from lexibrary.archivist.change_checker import ChangeLevel  # noqa: PLC0415
    from lexibrary.archivist.pipeline import update_file  # noqa: PLC0415
    from lexibrary.archivist.service import build_archivist_service  # noqa: PLC0415

    archivist = build_archivist_service(config)
    try:
        result = await update_file(file_path, project_root, config, archivist)
    except Exception:
        logger.warning(
            "post_edit bootstrap: archivist.update_file raised for %s — "
            "continuing with coordinator run",
            file_path,
            exc_info=True,
        )
        return

    # Charge the coordinator's budget counter only when update_file actually
    # issued an LLM call.  ``update_file`` returns early (no LLM) for
    # UNCHANGED / AGENT_UPDATED change levels and for ``skip_reason`` /
    # ``failed`` paths (out-of-scope, IWH-blocked, size-gate skeleton,
    # unreadable source, merge-conflict markers, invalid ``updated_by``).
    # All other outcomes — including a successful regeneration, a
    # post-LLM TOCTOU discard, or an LLM-reported error — have consumed a
    # provider call and MUST count against ``max_llm_calls_per_run``.
    llm_was_called = not (
        result.change == ChangeLevel.UNCHANGED
        or result.change == ChangeLevel.AGENT_UPDATED
        or result.skip_reason is not None
        or (result.failed and result.failure_reason in {
            "cannot read source file",
            "unresolved merge conflict markers",
        })
        or (
            result.failed
            and result.failure_reason is not None
            and result.failure_reason.startswith("invalid updated_by")
        )
    )
    if llm_was_called:
        coordinator.pre_charged_llm_calls += 1


# ---------------------------------------------------------------------------
# Public hook entry points
# ---------------------------------------------------------------------------


async def post_edit_hook(
    file_path: Path,
    project_root: Path,
    *,
    config: LexibraryConfig | None = None,
) -> None:
    """Reactive hook fired when a source file under ``src/`` is modified.

    Validates the file is within the configured scope, then invokes the
    coordinator with ``scope=file_path`` and
    ``trigger="reactive_post_edit"``.

    Args:
        file_path: Absolute path to the modified file.
        project_root: Absolute path to the project root.
        config: Optional pre-loaded config; loaded from disk if not provided.
    """
    if config is None:
        config = load_config(project_root)

    reactive: ReactiveConfig = config.curator.reactive

    if not reactive.enabled:
        logger.debug("Reactive hooks disabled; skipping post_edit_hook")
        return

    if not reactive.post_edit:
        logger.debug("post_edit toggle disabled; skipping")
        return

    if not _is_source_file(file_path, project_root):
        logger.debug("Not a source file (%s); skipping post_edit_hook", file_path)
        return

    # Opt-out short-circuit (curator-freshness, task 2.4): when
    # ``curator.prepare_indexes`` is ``False``, skip the entire reactive
    # bootstrap (index refresh + optional archivist regeneration) and hand
    # straight off to the coordinator.  The coordinator itself independently
    # honours ``prepare_indexes`` inside ``_run_pipeline``, so passing through
    # is safe.  This enforces the "opt-out of prepare = opt-out of bootstrap"
    # invariant from SHARED_BLOCK_B.
    if not config.curator.prepare_indexes:
        return await _run_coordinator(
            project_root,
            config,
            scope=file_path,
            trigger="reactive_post_edit",
        )

    # Always-on index-refresh bootstrap (curator-freshness, task 2.1).
    # The bootstrap acquires and releases the curator PID lock around its
    # writes so a concurrent coordinator run never races with it.  Any
    # failure is logged; we still hand off to the coordinator below.
    _bootstrap_refresh_indexes(file_path, project_root, config)

    # Build the coordinator up-front so the optional archivist regeneration
    # below can pre-charge its LLM-budget counter before ``.run(...)``.
    from lexibrary.curator.coordinator import Coordinator  # noqa: PLC0415

    coordinator = Coordinator(project_root, config)

    # Optional LLM regeneration step (curator-freshness, task 2.3).
    # Gated by ``curator.reactive_bootstrap_regenerate`` (default: False).
    # When enabled, invoke the archivist pipeline for the edited file and
    # charge the call against ``max_llm_calls_per_run`` via the coordinator's
    # ``pre_charged_llm_calls`` counter, so the dispatch phase that follows
    # picks up the consumed budget.
    if config.curator.reactive_bootstrap_regenerate:
        await _bootstrap_archivist_regenerate(
            file_path, project_root, config, coordinator
        )

    await _run_coordinator(
        project_root,
        config,
        scope=file_path,
        trigger="reactive_post_edit",
        coordinator=coordinator,
    )


async def post_bead_close_hook(
    directory: Path,
    project_root: Path,
    *,
    config: LexibraryConfig | None = None,
) -> None:
    """Reactive hook fired after a bead-agent closes a bead.

    Invokes the coordinator with ``scope=directory`` and
    ``trigger="reactive_post_bead_close"``.

    Args:
        directory: Absolute path to the directory affected by the bead.
        project_root: Absolute path to the project root.
        config: Optional pre-loaded config; loaded from disk if not provided.
    """
    if config is None:
        config = load_config(project_root)

    reactive: ReactiveConfig = config.curator.reactive

    if not reactive.enabled:
        logger.debug("Reactive hooks disabled; skipping post_bead_close_hook")
        return

    if not reactive.post_bead_close:
        logger.debug("post_bead_close toggle disabled; skipping")
        return

    await _run_coordinator(
        project_root,
        config,
        scope=directory,
        trigger="reactive_post_bead_close",
    )


async def validation_failure_hook(
    errors: list[ValidationIssue],
    project_root: Path,
    *,
    config: LexibraryConfig | None = None,
) -> None:
    """Reactive hook fired when validation surfaces errors above threshold.

    Filters *errors* against ``config.reactive.severity_threshold``, then
    dispatches the coordinator with scope set to each affected artifact.

    Args:
        errors: List of :class:`ValidationIssue` instances from a validation run.
        project_root: Absolute path to the project root.
        config: Optional pre-loaded config; loaded from disk if not provided.
    """
    if config is None:
        config = load_config(project_root)

    reactive: ReactiveConfig = config.curator.reactive

    if not reactive.enabled:
        logger.debug("Reactive hooks disabled; skipping validation_failure_hook")
        return

    if not reactive.validation_failure:
        logger.debug("validation_failure toggle disabled; skipping")
        return

    # Filter to issues at or above the severity threshold.
    threshold = reactive.severity_threshold
    actionable = [e for e in errors if _severity_at_or_above(e.severity, threshold)]

    if not actionable:
        logger.debug("No validation issues at or above threshold %r", threshold)
        return

    # Determine unique scopes from actionable errors.  Each error's artifact
    # field gives the affected path.  We run one coordinator invocation per
    # unique scope to avoid redundant work.
    scopes_seen: set[Path] = set()
    for issue in actionable:
        if not issue.artifact:
            continue
        scope_path = project_root / issue.artifact
        if scope_path in scopes_seen:
            continue
        scopes_seen.add(scope_path)

        await _run_coordinator(
            project_root,
            config,
            scope=scope_path,
            trigger="reactive_validation_failure",
        )


# ---------------------------------------------------------------------------
# Synchronous convenience wrappers (for hook runners)
# ---------------------------------------------------------------------------


def post_edit_hook_sync(
    file_path: Path,
    project_root: Path,
    *,
    config: LexibraryConfig | None = None,
) -> None:
    """Synchronous wrapper around :func:`post_edit_hook`."""
    asyncio.run(post_edit_hook(file_path, project_root, config=config))


def post_bead_close_hook_sync(
    directory: Path,
    project_root: Path,
    *,
    config: LexibraryConfig | None = None,
) -> None:
    """Synchronous wrapper around :func:`post_bead_close_hook`."""
    asyncio.run(post_bead_close_hook(directory, project_root, config=config))


def validation_failure_hook_sync(
    errors: list[ValidationIssue],
    project_root: Path,
    *,
    config: LexibraryConfig | None = None,
) -> None:
    """Synchronous wrapper around :func:`validation_failure_hook`."""
    asyncio.run(validation_failure_hook(errors, project_root, config=config))
