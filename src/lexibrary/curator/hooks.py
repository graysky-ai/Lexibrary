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

from lexibrary.config.loader import load_config
from lexibrary.config.schema import LexibraryConfig
from lexibrary.curator.config import ReactiveConfig
from lexibrary.curator.coordinator import CuratorLockError
from lexibrary.validator.report import ValidationIssue

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
) -> None:
    """Instantiate and run the coordinator, handling lock contention."""
    from lexibrary.curator.coordinator import Coordinator  # noqa: PLC0415

    coordinator = Coordinator(project_root, config)
    try:
        await coordinator.run(scope=scope, trigger=trigger)
    except CuratorLockError:
        logger.info(
            "Curator already running (lock held); skipping reactive %s",
            trigger,
        )


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

    await _run_coordinator(
        project_root,
        config,
        scope=file_path,
        trigger="reactive_post_edit",
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
