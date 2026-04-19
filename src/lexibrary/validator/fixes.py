"""Auto-fix functions for validation issues.

Provides a registry of fixers keyed by check name. Only auto-fixable
checks have entries: ``hash_freshness``, ``orphan_artifacts``,
``aindex_coverage``, ``orphaned_aindex``, ``orphaned_iwh``,
``orphaned_iwh_signals``, ``orphaned_designs``, ``deprecated_ttl``,
``bidirectional_deps``, ``wikilink_resolution``,
``lookup_token_budget_exceeded``, ``duplicate_slugs``, and
``duplicate_aliases``. The last two are propose-only — they emit a
"requires manual resolution" result rather than mutating disk.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, TypeVar

from lexibrary.config.schema import LexibraryConfig
from lexibrary.utils.paths import DESIGNS_DIR
from lexibrary.validator.report import ValidationIssue

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Checks routed through the escalate_* fixer family (curator-4 Group 15).
# These fixers mutate no artifact — they write an IWH signal describing the
# pending decision when running autonomously, and the bridge in
# ``curator.validation_fixers`` maps the result to ``outcome="escalation_required"``
# so the coordinator can surface a ``PendingDecision`` entry in its report.
ESCALATION_CHECKS: frozenset[str] = frozenset(
    {
        "orphan_concepts",
        "stale_concept",
        "convention_stale",
        "playbook_staleness",
    }
)


def _run_sync(coro: Coroutine[Any, Any, T]) -> T:
    """Drive *coro* to completion whether or not a loop is already running.

    Sync fixers are invoked synchronously from within the curator's async
    dispatch loop (``Coordinator._dispatch``).  When that outer loop is
    already running, ``asyncio.run`` raises "cannot be called from a
    running event loop".  The fallback path spawns a short-lived worker
    thread that owns its own loop so the coroutine completes without
    interfering with the caller's loop.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No loop in this thread — safe to drive directly.
        return asyncio.run(coro)

    result: list[T] = []
    error: list[BaseException] = []

    def _worker() -> None:
        try:
            result.append(asyncio.run(coro))
        except BaseException as exc:  # noqa: BLE001 - re-raised on join
            error.append(exc)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join()
    if error:
        raise error[0]
    return result[0]


@dataclass
class FixResult:
    """Result from attempting to auto-fix a validation issue.

    The optional ``outcome_hint`` field lets the bridge in
    ``curator.validation_fixers.fix_validation_issue`` distinguish between
    a plain "did not fix" outcome and a deliberate escalation (used by the
    curator-4 ``escalate_*`` fixer family — see :data:`ESCALATION_CHECKS`).
    When ``outcome_hint == "escalation_required"``, the bridge sets
    ``SubAgentResult.outcome = "escalation_required"`` and the coordinator
    captures a ``PendingDecision`` entry referencing ``iwh_path`` (when
    present) in ``CuratorReport.pending_decisions``.
    """

    check: str
    path: Path
    fixed: bool
    message: str
    llm_calls: int = 0
    outcome_hint: Literal["escalation_required"] | None = None
    iwh_path: Path | None = None


def fix_hash_freshness(
    issue: ValidationIssue,
    project_root: Path,
    config: LexibraryConfig,
) -> FixResult:
    """Re-generate the design file for a stale source file.

    Calls the update pipeline for the single source file referenced
    in the validation issue.
    """
    from lexibrary.archivist.pipeline import update_file  # noqa: PLC0415
    from lexibrary.archivist.service import ArchivistService  # noqa: PLC0415
    from lexibrary.llm.client_registry import build_client_registry  # noqa: PLC0415
    from lexibrary.llm.rate_limiter import RateLimiter  # noqa: PLC0415

    source_path = project_root / issue.artifact
    if not source_path.exists():
        return FixResult(
            check=issue.check,
            path=source_path,
            fixed=False,
            message=f"source file not found: {issue.artifact}",
        )

    try:
        rate_limiter = RateLimiter()
        registry = build_client_registry(config)
        archivist = ArchivistService(rate_limiter=rate_limiter, client_registry=registry)
        result = asyncio.run(update_file(source_path, project_root, config, archivist))
        if result.failed:
            return FixResult(
                check=issue.check,
                path=source_path,
                fixed=False,
                message=f"failed to re-generate design file for {issue.artifact}",
            )
        return FixResult(
            check=issue.check,
            path=source_path,
            fixed=True,
            message=f"re-generated design file for {issue.artifact}",
        )
    except Exception as exc:
        logger.exception("Failed to fix hash_freshness for %s", issue.artifact)
        return FixResult(
            check=issue.check,
            path=source_path,
            fixed=False,
            message=f"error: {exc}",
        )


def fix_orphan_artifacts(
    issue: ValidationIssue,
    project_root: Path,
    config: LexibraryConfig,
) -> FixResult:
    """Delete design files whose corresponding source file does not exist."""
    from lexibrary.utils.paths import LEXIBRARY_DIR  # noqa: PLC0415

    # The issue artifact is the relative path of the design file
    design_path = project_root / LEXIBRARY_DIR / issue.artifact
    if not design_path.exists():
        return FixResult(
            check=issue.check,
            path=design_path,
            fixed=False,
            message=f"design file already removed: {issue.artifact}",
        )

    # Determine corresponding source path from the design file
    # Design files are at .lexibrary/designs/<source-rel>.md
    source_rel = issue.artifact
    if source_rel.endswith(".md"):
        source_rel = source_rel[:-3]  # Strip trailing .md
    # Strip the designs/ prefix to recover the source-relative path
    designs_prefix = DESIGNS_DIR + "/"
    if source_rel.startswith(designs_prefix):
        source_rel = source_rel[len(designs_prefix) :]

    source_path = project_root / source_rel
    if source_path.exists():
        return FixResult(
            check=issue.check,
            path=design_path,
            fixed=False,
            message=f"source file exists: {source_rel} (not an orphan)",
        )

    # Safe to delete the orphan design file
    try:
        design_path.unlink()
        return FixResult(
            check=issue.check,
            path=design_path,
            fixed=True,
            message=f"deleted orphan design file: {issue.artifact}",
        )
    except OSError as exc:
        return FixResult(
            check=issue.check,
            path=design_path,
            fixed=False,
            message=f"failed to delete: {exc}",
        )


def fix_aindex_coverage(
    issue: ValidationIssue,
    project_root: Path,
    config: LexibraryConfig,
) -> FixResult:
    """Generate missing .aindex files for uncovered directories."""
    from lexibrary.indexer.orchestrator import index_directory  # noqa: PLC0415

    # The issue artifact is the relative directory path
    target_dir = project_root / issue.artifact
    if not target_dir.is_dir():
        return FixResult(
            check=issue.check,
            path=target_dir,
            fixed=False,
            message=f"directory not found: {issue.artifact}",
        )

    try:
        index_directory(target_dir, project_root, config)
        return FixResult(
            check=issue.check,
            path=target_dir,
            fixed=True,
            message=f"generated .aindex for {issue.artifact}",
        )
    except Exception as exc:
        logger.exception("Failed to generate .aindex for %s", issue.artifact)
        return FixResult(
            check=issue.check,
            path=target_dir,
            fixed=False,
            message=f"error: {exc}",
        )


def fix_orphaned_aindex(
    issue: ValidationIssue,
    project_root: Path,
    config: LexibraryConfig,
) -> FixResult:
    """Delete an orphaned ``.aindex`` file and clean up empty parent directories.

    Removes the orphaned ``.aindex`` file identified by the validation issue,
    then walks upward through empty parent directories under
    ``.lexibrary/designs/``, removing them until a non-empty directory or the
    designs root is reached.

    Args:
        issue: The validation issue describing the orphaned ``.aindex`` file.
        project_root: Root directory of the project.
        config: Project configuration (unused but required by fixer signature).

    Returns:
        A FixResult indicating whether the fix succeeded.
    """
    from lexibrary.utils.paths import LEXIBRARY_DIR  # noqa: PLC0415

    lexibrary_dir = project_root / LEXIBRARY_DIR
    designs_dir = lexibrary_dir / DESIGNS_DIR

    # issue.artifact is relative to lexibrary_dir, e.g. "designs/src/old/.aindex"
    aindex_path = lexibrary_dir / issue.artifact
    if not aindex_path.exists():
        return FixResult(
            check=issue.check,
            path=aindex_path,
            fixed=False,
            message=f".aindex file already removed: {issue.artifact}",
        )

    # Delete the orphaned .aindex file
    try:
        aindex_path.unlink()
    except OSError as exc:
        return FixResult(
            check=issue.check,
            path=aindex_path,
            fixed=False,
            message=f"failed to delete .aindex file: {exc}",
        )

    # Clean up empty parent directories up to (but not including) designs root
    parent = aindex_path.parent
    while parent != designs_dir and parent.is_dir():
        try:
            # Only remove if truly empty
            if any(parent.iterdir()):
                break
            parent.rmdir()
            parent = parent.parent
        except OSError:
            break

    return FixResult(
        check=issue.check,
        path=aindex_path,
        fixed=True,
        message=f"deleted orphaned .aindex file: {issue.artifact}",
    )


def fix_orphaned_iwh(
    issue: ValidationIssue,
    project_root: Path,
    config: LexibraryConfig,
) -> FixResult:
    """Delete an orphaned ``.iwh`` file whose source directory no longer exists.

    Removes the orphaned ``.iwh`` file identified by the validation issue,
    then walks upward through empty parent directories under
    ``.lexibrary/designs/``, removing them until a non-empty directory or the
    designs root is reached.

    Args:
        issue: The validation issue describing the orphaned ``.iwh`` file.
        project_root: Root directory of the project.
        config: Project configuration (unused but required by fixer signature).

    Returns:
        A FixResult indicating whether the fix succeeded.
    """
    from lexibrary.utils.paths import LEXIBRARY_DIR  # noqa: PLC0415

    lexibrary_dir = project_root / LEXIBRARY_DIR
    designs_dir = lexibrary_dir / DESIGNS_DIR

    # issue.artifact is relative to lexibrary_dir, e.g. "designs/src/deleted/.iwh"
    iwh_path = lexibrary_dir / issue.artifact
    if not iwh_path.exists():
        return FixResult(
            check=issue.check,
            path=iwh_path,
            fixed=False,
            message=f".iwh file already removed: {issue.artifact}",
        )

    # Delete the orphaned .iwh file
    try:
        iwh_path.unlink()
    except OSError as exc:
        return FixResult(
            check=issue.check,
            path=iwh_path,
            fixed=False,
            message=f"failed to delete .iwh file: {exc}",
        )

    # Clean up empty parent directories up to (but not including) designs root
    parent = iwh_path.parent
    while parent != designs_dir and parent.is_dir():
        try:
            # Only remove if truly empty
            if any(parent.iterdir()):
                break
            parent.rmdir()
            parent = parent.parent
        except OSError:
            break

    return FixResult(
        check=issue.check,
        path=iwh_path,
        fixed=True,
        message=f"deleted orphaned .iwh file: {issue.artifact}",
    )


def fix_orphaned_iwh_signals(
    issue: ValidationIssue,
    project_root: Path,
    config: LexibraryConfig,
) -> FixResult:
    """Delete an IWH signal whose age exceeds ``config.iwh.ttl_hours``.

    Distinct from :func:`fix_orphaned_iwh`, which targets signals whose
    source directory has disappeared. This fixer targets *expired* signals
    — structurally valid ``.iwh`` files whose ``created`` timestamp has
    aged past the configured TTL. IWH signals are intentionally ephemeral,
    so deletion is the intended remedy.

    Behaviour:
        - If the file no longer exists, returns ``fixed=False`` with
          message "already consumed".
        - If the file is unparseable, returns ``fixed=False`` with message
          "parse error" and leaves the file untouched (orphaned-iwh fixer
          handles structural orphans).
        - If the signal is now within TTL (because TTL was raised since
          detection), returns ``fixed=False`` with message "signal within
          TTL".
        - If ``config.validator.fix_orphaned_iwh_signals_delete`` is
          ``False``, returns ``fixed=False`` with message
          "auto-delete disabled by config".
        - Otherwise deletes the file and walks up empty parent directories
          under ``.lexibrary/designs/`` (stopping at ``designs_dir``).

    Args:
        issue: The validation issue describing the expired IWH signal.
        project_root: Root directory of the project.
        config: Project configuration (reads ``iwh.ttl_hours`` and
            ``validator.fix_orphaned_iwh_signals_delete``).

    Returns:
        A FixResult indicating whether the fix succeeded.
    """
    from datetime import UTC, datetime  # noqa: PLC0415

    from lexibrary.iwh.parser import parse_iwh  # noqa: PLC0415
    from lexibrary.utils.paths import LEXIBRARY_DIR  # noqa: PLC0415

    lexibrary_dir = project_root / LEXIBRARY_DIR
    designs_dir = lexibrary_dir / DESIGNS_DIR

    # issue.artifact is relative to lexibrary_dir, e.g. "designs/src/stale/.iwh"
    iwh_path = lexibrary_dir / issue.artifact
    if not iwh_path.exists():
        return FixResult(
            check=issue.check,
            path=iwh_path,
            fixed=False,
            message="already consumed",
        )

    parsed = parse_iwh(iwh_path)
    if parsed is None:
        # Unparseable — do NOT delete. Leave for the orphaned_iwh pathway.
        return FixResult(
            check=issue.check,
            path=iwh_path,
            fixed=False,
            message="parse error",
        )

    # Re-check TTL at fix time: configuration may have changed since the
    # issue was detected, or the signal may be within the current window.
    ttl_hours = config.iwh.ttl_hours
    created = parsed.created
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    age_hours = (datetime.now(tz=UTC) - created).total_seconds() / 3600
    if ttl_hours <= 0 or age_hours <= ttl_hours:
        return FixResult(
            check=issue.check,
            path=iwh_path,
            fixed=False,
            message="signal within TTL",
        )

    if not config.validator.fix_orphaned_iwh_signals_delete:
        return FixResult(
            check=issue.check,
            path=iwh_path,
            fixed=False,
            message="auto-delete disabled by config",
        )

    try:
        iwh_path.unlink()
    except OSError as exc:
        return FixResult(
            check=issue.check,
            path=iwh_path,
            fixed=False,
            message=f"failed to delete .iwh file: {exc}",
        )

    # Clean up empty parent directories up to (but not including) designs root
    parent = iwh_path.parent
    while parent != designs_dir and parent.is_dir():
        try:
            if any(parent.iterdir()):
                break
            parent.rmdir()
            parent = parent.parent
        except OSError:
            break

    return FixResult(
        check=issue.check,
        path=iwh_path,
        fixed=True,
        message=f"deleted expired IWH ({int(age_hours)}h old)",
    )


def fix_orphaned_designs(
    issue: ValidationIssue,
    project_root: Path,
    config: LexibraryConfig,
) -> FixResult:
    """Apply the deprecation workflow to an orphaned design file.

    Instead of directly deleting orphaned design files, this fixer applies
    the proper deprecation workflow:

    - For uncommitted deletions (source still tracked in git index): marks
      the design file as ``status: unlinked``.
    - For committed deletions (source no longer tracked): marks the design
      file as ``status: deprecated`` with ``deprecated_at`` and
      ``deprecated_reason: "source_deleted"``.

    Args:
        issue: The validation issue describing the orphaned design file.
        project_root: Root directory of the project.
        config: Project configuration (unused but required by fixer signature).

    Returns:
        A FixResult indicating whether the fix succeeded.
    """
    from lexibrary.lifecycle.deprecation import (  # noqa: PLC0415
        _is_committed_deletion,
        deprecate_design,
        mark_unlinked,
    )
    from lexibrary.utils.paths import LEXIBRARY_DIR  # noqa: PLC0415

    lexibrary_dir = project_root / LEXIBRARY_DIR

    # issue.artifact is relative to lexibrary_dir, e.g. "designs/src/foo.py.md"
    design_path = lexibrary_dir / issue.artifact
    if not design_path.exists():
        return FixResult(
            check=issue.check,
            path=design_path,
            fixed=False,
            message=f"design file already removed: {issue.artifact}",
        )

    # Parse the design file to get the source path
    from lexibrary.artifacts.design_file_parser import (  # noqa: PLC0415
        parse_design_file,
    )

    parsed = parse_design_file(design_path)
    if parsed is None:
        return FixResult(
            check=issue.check,
            path=design_path,
            fixed=False,
            message=f"cannot parse design file: {issue.artifact}",
        )

    source_rel = Path(parsed.source_path)

    # Check if the deletion has been committed
    committed = _is_committed_deletion(project_root, source_rel)

    try:
        if committed:
            deprecate_design(design_path, reason="source_deleted")
            return FixResult(
                check=issue.check,
                path=design_path,
                fixed=True,
                message=f"marked as deprecated (source committed deletion): {issue.artifact}",
            )
        else:
            mark_unlinked(design_path)
            return FixResult(
                check=issue.check,
                path=design_path,
                fixed=True,
                message=f"marked as unlinked (uncommitted deletion): {issue.artifact}",
            )
    except Exception as exc:
        logger.exception("Failed to apply deprecation for %s", issue.artifact)
        return FixResult(
            check=issue.check,
            path=design_path,
            fixed=False,
            message=f"error applying deprecation: {exc}",
        )


def fix_deprecated_ttl(
    issue: ValidationIssue,
    project_root: Path,
    config: LexibraryConfig,
) -> FixResult:
    """Hard-delete a deprecated design file whose TTL has expired.

    Checks that the design file is still deprecated and past its TTL
    before deleting. Cleans up empty parent directories under the
    designs root.

    Args:
        issue: The validation issue describing the expired deprecated file.
        project_root: Root directory of the project.
        config: Project configuration (used for TTL setting).

    Returns:
        A FixResult indicating whether the fix succeeded.
    """
    from lexibrary.lifecycle.deprecation import check_ttl_expiry  # noqa: PLC0415
    from lexibrary.utils.paths import LEXIBRARY_DIR  # noqa: PLC0415

    lexibrary_dir = project_root / LEXIBRARY_DIR
    designs_dir = lexibrary_dir / DESIGNS_DIR

    # issue.artifact is relative to lexibrary_dir, e.g. "designs/src/foo.py.md"
    design_path = lexibrary_dir / issue.artifact
    if not design_path.exists():
        return FixResult(
            check=issue.check,
            path=design_path,
            fixed=False,
            message=f"design file already removed: {issue.artifact}",
        )

    # Verify TTL is actually expired before deleting
    ttl_commits = config.deprecation.ttl_commits
    if not check_ttl_expiry(design_path, project_root, ttl_commits):
        return FixResult(
            check=issue.check,
            path=design_path,
            fixed=False,
            message=f"TTL not yet expired for: {issue.artifact}",
        )

    # Delete the expired design file
    try:
        design_path.unlink()
    except OSError as exc:
        return FixResult(
            check=issue.check,
            path=design_path,
            fixed=False,
            message=f"failed to delete design file: {exc}",
        )

    # Clean up empty parent directories up to (but not including) designs root
    parent = design_path.parent
    while parent != designs_dir and parent.is_dir():
        try:
            if any(parent.iterdir()):
                break
            parent.rmdir()
            parent = parent.parent
        except OSError:
            break

    return FixResult(
        check=issue.check,
        path=design_path,
        fixed=True,
        message=f"hard-deleted expired deprecated design file: {issue.artifact}",
    )


def fix_bidirectional_deps(
    issue: ValidationIssue,
    project_root: Path,
    config: LexibraryConfig,
) -> FixResult:
    """Reconcile a design file's Dependencies / Dependents against the link graph.

    Phase 1b fixer for ``bidirectional_deps`` issues. The validator emits this
    check when the design file's ``Dependencies`` and/or ``Dependents`` sections
    drift from the AST-derived forward edges and link-graph-derived reverse
    edges. The fix is a non-LLM rewrite via
    :func:`lexibrary.archivist.pipeline.reconcile_deps_only` — it avoids
    :func:`lexibrary.archivist.pipeline.update_file` on purpose because the
    source-hash short-circuit in ``update_file`` would silently skip the fix
    when the source hasn't changed (which is the exact case this fixer
    targets: source stable, graph moved).

    Args:
        issue: The validation issue describing the drifting design file. Its
            ``artifact`` field is the lexibrary-relative design path (e.g.
            ``designs/src/foo.py.md``).
        project_root: Root directory of the project.
        config: Project configuration (unused but required by the fixer
            signature exposed through :data:`FIXERS`).

    Returns:
        A :class:`FixResult` whose ``fixed`` flag reflects reconciler outcome.
        When the link graph is missing, returns ``fixed=False`` with the
        documented "link graph not built" message so the CLI / curator can
        surface a graceful-degradation hint.
    """
    from lexibrary.archivist.pipeline import reconcile_deps_only  # noqa: PLC0415
    from lexibrary.artifacts.design_file_parser import parse_design_file  # noqa: PLC0415
    from lexibrary.linkgraph import LinkGraphUnavailable  # noqa: PLC0415
    from lexibrary.utils.paths import LEXIBRARY_DIR  # noqa: PLC0415

    lexibrary_dir = project_root / LEXIBRARY_DIR

    # issue.artifact is relative to lexibrary_dir, e.g. "designs/src/foo.py.md"
    design_path = lexibrary_dir / issue.artifact
    if not design_path.exists():
        return FixResult(
            check=issue.check,
            path=design_path,
            fixed=False,
            message=f"design file not found: {issue.artifact}",
        )

    # Parse the design file so we can surface parse failures with a clear
    # message (reconcile_deps_only also parses internally, but it silently
    # no-ops on parse failure which would show up as a misleading "fixed" state).
    try:
        parsed = parse_design_file(design_path)
    except Exception as exc:
        return FixResult(
            check=issue.check,
            path=design_path,
            fixed=False,
            message=f"could not parse design file: {exc}",
        )
    if parsed is None:
        return FixResult(
            check=issue.check,
            path=design_path,
            fixed=False,
            message=f"could not parse design file: {issue.artifact}",
        )

    # DesignFile.source_path is a top-level field (relative to project_root);
    # reconcile_deps_only re-reads it internally but we touch it here to make
    # the contract explicit and to fail fast if it's empty for some reason.
    if not parsed.source_path:
        return FixResult(
            check=issue.check,
            path=design_path,
            fixed=False,
            message=f"design file has empty source_path: {issue.artifact}",
        )

    try:
        _run_sync(reconcile_deps_only(design_path, project_root))
    except LinkGraphUnavailable:
        return FixResult(
            check=issue.check,
            path=design_path,
            fixed=False,
            message="link graph not built — run `lexictl update` first",
        )
    except Exception as exc:
        logger.exception("Failed to reconcile bidirectional_deps for %s", issue.artifact)
        return FixResult(
            check=issue.check,
            path=design_path,
            fixed=False,
            message=f"error: {exc}",
        )

    return FixResult(
        check="bidirectional_deps",
        path=design_path,
        fixed=True,
        message="reconciled dependencies + dependents from link graph",
    )


def fix_wikilink_resolution(
    issue: ValidationIssue,
    project_root: Path,
    config: LexibraryConfig,
) -> FixResult:
    """Repair a broken wikilink by re-generating the containing design file.

    Phase 4 Family D fixer for ``wikilink_resolution`` issues. Follows the
    same archivist-delegation pattern as :func:`fix_hash_freshness`: it
    resolves the design file identified by ``issue.artifact``, reads the
    underlying source path, and hands off to
    :func:`lexibrary.archivist.pipeline.update_file` so the LLM pipeline
    rewrites the design's wikilinks from scratch.

    Stack-post wikilinks (``.lexibrary/stack/ST-*.md``) are out of scope —
    Stack posts are human-authored and have no source to regenerate from,
    so the fixer returns a propose-only ``FixResult`` for those artifacts.

    Args:
        issue: The validation issue describing the artifact with a broken
            wikilink. ``issue.artifact`` is project-root-relative (e.g.
            ``.lexibrary/designs/src/foo.py.md`` or
            ``.lexibrary/stack/ST-001-xxx.md``).
        project_root: Root directory of the project.
        config: Project configuration.

    Returns:
        A :class:`FixResult` whose ``fixed`` flag reflects whether
        ``update_file`` succeeded. Stack posts always return ``fixed=False``.
    """
    from lexibrary.archivist.pipeline import update_file  # noqa: PLC0415
    from lexibrary.archivist.service import build_archivist_service  # noqa: PLC0415
    from lexibrary.artifacts.design_file_parser import parse_design_file  # noqa: PLC0415
    from lexibrary.utils.paths import LEXIBRARY_DIR  # noqa: PLC0415

    artifact_path = project_root / issue.artifact
    designs_root = project_root / LEXIBRARY_DIR / DESIGNS_DIR

    # Stack posts have no regeneration source — propose-only.
    try:
        artifact_path.resolve().relative_to(designs_root.resolve())
    except ValueError:
        return FixResult(
            check=issue.check,
            path=artifact_path,
            fixed=False,
            message=(
                f"wikilink in non-design artifact requires manual resolution: {issue.artifact}"
            ),
        )

    if not artifact_path.exists():
        return FixResult(
            check=issue.check,
            path=artifact_path,
            fixed=False,
            message=f"design file not found: {issue.artifact}",
        )

    try:
        parsed = parse_design_file(artifact_path)
    except Exception as exc:
        return FixResult(
            check=issue.check,
            path=artifact_path,
            fixed=False,
            message=f"could not parse design file: {exc}",
        )
    if parsed is None or not parsed.source_path:
        return FixResult(
            check=issue.check,
            path=artifact_path,
            fixed=False,
            message=f"could not resolve source for design file: {issue.artifact}",
        )

    source_path = project_root / parsed.source_path
    if not source_path.exists():
        return FixResult(
            check=issue.check,
            path=artifact_path,
            fixed=False,
            message=f"source file not found: {parsed.source_path}",
        )

    try:
        archivist = build_archivist_service(config)
        result = _run_sync(update_file(source_path, project_root, config, archivist))
    except Exception as exc:
        logger.exception("Failed to fix wikilink_resolution for %s", issue.artifact)
        return FixResult(
            check=issue.check,
            path=artifact_path,
            fixed=False,
            message=f"error: {exc}",
        )

    if result.failed:
        return FixResult(
            check=issue.check,
            path=artifact_path,
            fixed=False,
            message=f"failed to re-generate design file for {issue.artifact}",
        )

    return FixResult(
        check=issue.check,
        path=artifact_path,
        fixed=True,
        message=f"re-generated design file to resolve wikilinks: {issue.artifact}",
        llm_calls=1,
    )


def fix_lookup_token_budget_exceeded(
    issue: ValidationIssue,
    project_root: Path,
    config: LexibraryConfig,
) -> FixResult:
    """Condense an over-budget design file via ``curator.budget.condense_file``.

    Curator-4 Phase 4 fixer for ``lookup_token_budget_exceeded`` info-severity
    issues.  The check is emitted by
    :func:`lexibrary.validator.checks.check_lookup_token_budget_exceeded`
    when a single design file consumes the entire
    ``token_budgets.lookup_total_tokens`` budget (at which point
    supplementary lookup sections — known issues, IWH signals, links —
    are always truncated).
    The fixer calls the standalone :func:`lexibrary.curator.budget.condense_file`
    helper (extracted in curator-4 Group 11) to rewrite the design-file
    body with ``updated_by="archivist"`` and refreshed hashes.
    Gated behind the ``config.validator.fix_lookup_token_budget_condense``
    kill-switch (defaults to ``False``) because condensation mutates
    content and consumes LLM budget.

    Args:
        issue: The ``lookup_token_budget_exceeded`` validation issue.
            ``issue.artifact`` is a path relative to ``.lexibrary/``
            (e.g. ``designs/src/foo.py.md``) — matching the format
            emitted by the check.
        project_root: Absolute project root.  Forwarded to ``condense_file``
            for source-hash recomputation.
        config: Project configuration.  Reads
            ``config.token_budgets.lookup_total_tokens`` for the re-count
            threshold and ``config.validator.fix_lookup_token_budget_condense``
            as the kill-switch.

    Returns:
        A :class:`FixResult` describing the outcome.  ``fixed=True``
        (with ``llm_calls=1``) when the file condensed below budget;
        ``fixed=False`` with a descriptive message for the several
        no-op/failure paths (under budget at fix time, kill-switch off,
        condensation did not reduce enough, BAML raised).
    """
    from lexibrary.curator.budget import condense_file  # noqa: PLC0415
    from lexibrary.tokenizer.approximate import ApproximateCounter  # noqa: PLC0415
    from lexibrary.utils.paths import LEXIBRARY_DIR  # noqa: PLC0415

    # ``issue.artifact`` is relative to ``.lexibrary/`` (e.g. ``designs/src/foo.py.md``).
    lexibrary_dir = project_root / LEXIBRARY_DIR
    design_path = lexibrary_dir / issue.artifact

    if not design_path.exists():
        return FixResult(
            check=issue.check,
            path=design_path,
            fixed=False,
            llm_calls=0,
            message=f"design file not found: {issue.artifact}",
        )

    budget = config.token_budgets.lookup_total_tokens
    counter = ApproximateCounter()

    # (ii) Re-count tokens — the file may have been trimmed since detection.
    try:
        current_content = design_path.read_text(encoding="utf-8")
    except OSError as exc:
        return FixResult(
            check=issue.check,
            path=design_path,
            fixed=False,
            llm_calls=0,
            message=f"could not read design file: {exc}",
        )
    current_tokens = counter.count(current_content)
    if current_tokens <= budget:
        return FixResult(
            check=issue.check,
            path=design_path,
            fixed=False,
            llm_calls=0,
            message="file fits budget now",
        )

    # (iii) Kill-switch gate — defaults to False per Group 1 config addition.
    if not config.validator.fix_lookup_token_budget_condense:
        return FixResult(
            check=issue.check,
            path=design_path,
            fixed=False,
            llm_calls=0,
            message=(
                "auto-condense disabled by config; increase "
                "token_budgets.lookup_total_tokens or trim manually"
            ),
        )

    # (iv) Invoke the async condense_file helper via the _run_sync bridge.
    try:
        result = _run_sync(condense_file(design_path, project_root, config))
    except Exception as exc:
        # BAML failure (or any other) — we cannot tell how much of the LLM
        # call completed, so conservatively charge zero (parity with the
        # "fixer raised" branch in curator.validation_fixers.fix_validation_issue).
        logger.exception("Failed to fix lookup_token_budget_exceeded for %s", issue.artifact)
        return FixResult(
            check=issue.check,
            path=design_path,
            fixed=False,
            llm_calls=0,
            message=f"error: {exc}",
        )

    # (v/vi) Re-count after write — if still over budget, return failure but
    # leave the condensed body on disk (the rewrite still improved things).
    if result.after_tokens > budget:
        return FixResult(
            check=issue.check,
            path=design_path,
            fixed=False,
            llm_calls=1,
            message="condensation did not reduce below budget",
        )

    return FixResult(
        check=issue.check,
        path=design_path,
        fixed=True,
        llm_calls=1,
        message=(f"condensed from {result.before_tokens} to {result.after_tokens} tokens"),
    )


def fix_duplicate_slugs(
    issue: ValidationIssue,
    project_root: Path,
    config: LexibraryConfig,
) -> FixResult:
    """Propose-only fixer for ``duplicate_slugs`` validation issues.

    Resolving a slug collision requires human judgement — renaming one of
    the colliding files breaks existing wikilinks, and the "right" rename
    depends on artifact history and external references that the fixer
    cannot safely infer. The fixer therefore returns ``fixed=False`` with
    a message directing the operator to resolve the collision manually.
    """
    from lexibrary.utils.paths import LEXIBRARY_DIR  # noqa: PLC0415

    artifact_path = project_root / LEXIBRARY_DIR / issue.artifact
    return FixResult(
        check=issue.check,
        path=artifact_path,
        fixed=False,
        message="requires manual resolution",
    )


def fix_duplicate_aliases(
    issue: ValidationIssue,
    project_root: Path,
    config: LexibraryConfig,
) -> FixResult:
    """Propose-only fixer for ``duplicate_aliases`` validation issues.

    Removing or renaming a duplicated alias/title changes how the
    concept is addressed by wikilinks and external documents, so the
    choice of which occurrence to keep must be made by a human. The
    fixer returns ``fixed=False`` with a message directing the operator
    to resolve the collision manually.
    """
    from lexibrary.utils.paths import LEXIBRARY_DIR  # noqa: PLC0415

    artifact_path = project_root / LEXIBRARY_DIR / issue.artifact
    return FixResult(
        check=issue.check,
        path=artifact_path,
        fixed=False,
        message="requires manual resolution",
    )


# ---------------------------------------------------------------------------
# Escalation fixer family (curator-4 Group 15)
# ---------------------------------------------------------------------------


def _is_autonomous_context(config: LexibraryConfig) -> bool:
    """Return True when the current fixer invocation is autonomous.

    The interactive CLI flow (``lexi validate --fix --interactive``)
    short-circuits ``FIXERS`` dispatch for checks in
    :data:`ESCALATION_CHECKS` BEFORE reaching this helper, so any
    invocation that gets here is autonomous by construction. The TTY
    check is kept as a belt-and-braces guard — if ``sys.stdout`` is a
    TTY AND no caller short-circuited, something is wrong; returning
    False suppresses the IWH write in that edge case. ``config`` is
    accepted for forward compatibility (future heuristics may inspect
    configured autonomy markers) but is currently unused.
    """
    import sys  # noqa: PLC0415

    del config  # currently unused — reserved for future heuristics
    return not sys.stdout.isatty()


def _resolve_concept_path(
    issue: ValidationIssue,
    project_root: Path,
) -> Path | None:
    """Resolve the concept .md path from an ``orphan_concepts``/``stale_concept`` issue.

    The checks emit ``issue.artifact`` as ``"concepts/<title>"`` (no ``.md``
    suffix — see ``check_orphan_concepts`` and ``check_stale_concepts``).
    The on-disk filename is ``<id>-<slug>.md``, so we look up the concept
    by title via :class:`ConceptIndex` and return its ``file_path``.
    """
    from lexibrary.utils.paths import LEXIBRARY_DIR  # noqa: PLC0415
    from lexibrary.wiki.index import ConceptIndex  # noqa: PLC0415

    concepts_dir = project_root / LEXIBRARY_DIR / "concepts"
    if not concepts_dir.is_dir():
        return None

    artifact = issue.artifact
    # Strip the "concepts/" prefix if present; the remainder is the title.
    title = artifact
    prefix = "concepts/"
    if title.startswith(prefix):
        title = title[len(prefix) :]

    index = ConceptIndex.load(concepts_dir)
    concept = index.find(title)
    if concept is None or concept.file_path is None:
        return None
    return concept.file_path


def _write_escalation_iwh(
    *,
    artifact_path: Path,
    body: str,
) -> Path | None:
    """Write an IWH signal describing an escalation to the artifact's parent dir.

    Mirrors the pattern used by ``curator.iwh_actions.write_reactive_iwh``:
    scope is ``"warning"`` (the closest value in the existing ``IWHScope``
    Literal — there is no ``"escalation"`` value in the schema), author
    is ``"curator"``. Returns the IWH path on success, or ``None`` if the
    write fails.
    """
    from lexibrary.iwh.writer import write_iwh  # noqa: PLC0415

    directory = artifact_path.parent
    try:
        return write_iwh(directory, author="curator", scope="warning", body=body)
    except OSError as exc:
        logger.warning("Failed to write escalation IWH at %s: %s", directory, exc)
        return None


def escalate_orphan_concepts(
    issue: ValidationIssue,
    project_root: Path,
    config: LexibraryConfig,
) -> FixResult:
    """Queue an ``orphan_concepts`` issue for operator resolution.

    Writes no mutation to the concept artifact. When running autonomously
    (coordinator path), writes an IWH signal at the concept's parent
    directory describing the pending decision. Always returns a
    ``FixResult`` with ``outcome_hint="escalation_required"`` so the
    bridge surfaces a ``PendingDecision`` entry in the curator report.

    Args:
        issue: The ``orphan_concepts`` validation issue.
            ``issue.artifact`` is ``"concepts/<title>"`` (no ``.md``).
        project_root: Absolute project root.
        config: Project configuration.

    Returns:
        A :class:`FixResult` with ``fixed=False``, ``llm_calls=0``, and
        ``outcome_hint="escalation_required"``. ``iwh_path`` is populated
        only when an IWH signal was successfully written (autonomous runs).
    """
    concept_path = _resolve_concept_path(issue, project_root)
    target = concept_path if concept_path is not None else project_root / issue.artifact

    iwh_path: Path | None = None
    if _is_autonomous_context(config) and concept_path is not None:
        body = (
            "escalation: orphan_concepts — concept has zero inbound "
            "link-graph references\n"
            f"Artifact: {issue.artifact}\n"
            f"Message: {issue.message}\n"
            "Suggested actions: ignore / deprecate / refresh"
        )
        iwh_path = _write_escalation_iwh(artifact_path=concept_path, body=body)

    return FixResult(
        check=issue.check,
        path=target,
        fixed=False,
        llm_calls=0,
        outcome_hint="escalation_required",
        iwh_path=iwh_path,
        message=f"escalation queued: orphan_concepts ({target.name})",
    )


def escalate_stale_concept(
    issue: ValidationIssue,
    project_root: Path,
    config: LexibraryConfig,
) -> FixResult:
    """Queue a ``stale_concept`` issue for operator resolution.

    Re-scans ``linked_files`` at fix time to count missing entries for
    an informational message (actual resolution — refresh or deprecate —
    happens later via the interactive CLI or ``lexictl curate resolve``).
    """
    from lexibrary.wiki.parser import parse_concept_file  # noqa: PLC0415

    concept_path = _resolve_concept_path(issue, project_root)
    target = concept_path if concept_path is not None else project_root / issue.artifact

    # Re-count missing linked_files at fix time for the message body.
    missing_count = 0
    if concept_path is not None:
        parsed = parse_concept_file(concept_path)
        if parsed is not None:
            for file_ref in parsed.linked_files:
                if not (project_root / file_ref).exists():
                    missing_count += 1

    iwh_path: Path | None = None
    if _is_autonomous_context(config) and concept_path is not None:
        body = (
            "escalation: stale_concept — "
            f"{missing_count} linked_files entries missing\n"
            f"Artifact: {issue.artifact}\n"
            f"Message: {issue.message}\n"
            "Suggested actions: ignore / deprecate / refresh"
        )
        iwh_path = _write_escalation_iwh(artifact_path=concept_path, body=body)

    return FixResult(
        check=issue.check,
        path=target,
        fixed=False,
        llm_calls=0,
        outcome_hint="escalation_required",
        iwh_path=iwh_path,
        message=(
            f"escalation queued: stale_concept ({target.name}) — "
            f"{missing_count} missing linked_files"
        ),
    )


def escalate_convention_stale(
    issue: ValidationIssue,
    project_root: Path,
    config: LexibraryConfig,
) -> FixResult:
    """Queue a ``convention_stale`` issue for operator resolution.

    Lists the missing scope paths from the current convention in the
    IWH body so the operator can decide between refreshing the scope
    and deprecating the convention.
    """
    from lexibrary.artifacts.convention import split_scope  # noqa: PLC0415
    from lexibrary.conventions.parser import parse_convention_file  # noqa: PLC0415
    from lexibrary.utils.paths import LEXIBRARY_DIR  # noqa: PLC0415

    # convention_stale emits artifact relative to .lexibrary/ (e.g.
    # "conventions/foo.md"). See check_convention_stale in checks.py.
    convention_path = project_root / LEXIBRARY_DIR / issue.artifact

    missing_paths: list[str] = []
    if convention_path.exists():
        parsed = parse_convention_file(convention_path)
        if parsed is not None:
            for sp in split_scope(parsed.frontmatter.scope):
                scope_dir = project_root / sp
                if not scope_dir.is_dir():
                    missing_paths.append(sp)

    missing_detail = ", ".join(missing_paths) if missing_paths else "(none)"

    iwh_path: Path | None = None
    if _is_autonomous_context(config) and convention_path.exists():
        body = (
            "escalation: convention_stale — missing scope path(s): "
            f"{missing_detail}\n"
            f"Artifact: {issue.artifact}\n"
            f"Message: {issue.message}\n"
            "Suggested actions: ignore / deprecate / refresh"
        )
        iwh_path = _write_escalation_iwh(artifact_path=convention_path, body=body)

    return FixResult(
        check=issue.check,
        path=convention_path,
        fixed=False,
        llm_calls=0,
        outcome_hint="escalation_required",
        iwh_path=iwh_path,
        message=(
            f"escalation queued: convention_stale ({convention_path.name}) — "
            f"missing scope: {missing_detail}"
        ),
    )


def escalate_playbook_staleness(
    issue: ValidationIssue,
    project_root: Path,
    config: LexibraryConfig,
) -> FixResult:
    """Queue a ``playbook_staleness`` issue for operator resolution.

    Includes a delta from ``last_verified`` (when set) in the IWH body so
    the operator can see how stale the playbook is at a glance.
    """
    from datetime import date  # noqa: PLC0415

    from lexibrary.playbooks.parser import parse_playbook_file  # noqa: PLC0415

    # playbook_staleness emits artifact relative to project_root
    # (e.g. ".lexibrary/playbooks/foo.md"). See check_playbook_staleness.
    playbook_path = project_root / issue.artifact

    staleness_detail = "never verified"
    if playbook_path.exists():
        parsed = parse_playbook_file(playbook_path)
        if parsed is not None and parsed.frontmatter.last_verified is not None:
            delta_days = (date.today() - parsed.frontmatter.last_verified).days
            staleness_detail = f"{delta_days} days since last_verified"

    iwh_path: Path | None = None
    if _is_autonomous_context(config) and playbook_path.exists():
        body = (
            f"escalation: playbook_staleness — {staleness_detail}\n"
            f"Artifact: {issue.artifact}\n"
            f"Message: {issue.message}\n"
            "Suggested actions: ignore / deprecate / refresh"
        )
        iwh_path = _write_escalation_iwh(artifact_path=playbook_path, body=body)

    return FixResult(
        check=issue.check,
        path=playbook_path,
        fixed=False,
        llm_calls=0,
        outcome_hint="escalation_required",
        iwh_path=iwh_path,
        message=(
            f"escalation queued: playbook_staleness ({playbook_path.name}) — {staleness_detail}"
        ),
    )


# Checks whose fixers delete files from disk and therefore require user confirmation
# before running in interactive mode.  This set is consumed by the CLI fix flow in
# ``lexibrary.cli._shared._run_validate`` to gate a single y/n prompt before any
# destructive work begins.
DESTRUCTIVE_CHECKS: frozenset[str] = frozenset(
    {
        "orphan_artifacts",  # deletes orphaned design files
        "orphaned_aindex",  # deletes orphaned .aindex files + empty parent dirs
        "orphaned_iwh",  # deletes orphaned .iwh files + empty parent dirs
        "deprecated_ttl",  # hard-deletes expired deprecated design files + empty parent dirs
    }
)

# Registry of auto-fixable checks.
# Maps check name -> fixer function.
FIXERS: dict[str, Callable[[ValidationIssue, Path, LexibraryConfig], FixResult]] = {
    "hash_freshness": fix_hash_freshness,
    "orphan_artifacts": fix_orphan_artifacts,
    "aindex_coverage": fix_aindex_coverage,
    "orphaned_aindex": fix_orphaned_aindex,
    "orphaned_iwh": fix_orphaned_iwh,
    "orphaned_iwh_signals": fix_orphaned_iwh_signals,
    "orphaned_designs": fix_orphaned_designs,
    "deprecated_ttl": fix_deprecated_ttl,
    "bidirectional_deps": fix_bidirectional_deps,
    "wikilink_resolution": fix_wikilink_resolution,
    "lookup_token_budget_exceeded": fix_lookup_token_budget_exceeded,
    "duplicate_slugs": fix_duplicate_slugs,
    "duplicate_aliases": fix_duplicate_aliases,
    # curator-4: escalation fixers — members of ESCALATION_CHECKS.
    # These fixers mutate no artifact; they write an IWH signal in autonomous
    # runs and the bridge maps the outcome_hint to "escalation_required".
    "orphan_concepts": escalate_orphan_concepts,
    "stale_concept": escalate_stale_concept,
    "convention_stale": escalate_convention_stale,
    "playbook_staleness": escalate_playbook_staleness,
}
