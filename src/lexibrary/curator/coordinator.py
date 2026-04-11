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
}

# Set of action keys recognised by the validation bridge router.  Includes the
# narrow per-check keys and the legacy umbrella key so triage items classified
# before the CHECK_TO_ACTION_KEY mapping was applied still reach the bridge.
VALIDATION_ACTION_KEYS: frozenset[str] = frozenset(
    set(CHECK_TO_ACTION_KEY.values()) | {"autofix_validation_issue"}
)


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
        """Internal pipeline execution after lock acquisition."""
        # Phase 1: Collect
        collect_result = self._collect(scope=scope, check=check)

        # Phase 2: Triage
        triage_result = self._triage(collect_result)

        # Phase 3: Dispatch
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

    # -- Phase 1: Collect ---------------------------------------------------

    def _collect(
        self,
        *,
        scope: Path | None = None,
        check: str | None = None,
    ) -> CollectResult:
        """Gather signals from validation, staleness checks, and IWH scan."""
        result = CollectResult()

        # Determine scope isolation exclusions
        uncommitted = _uncommitted_files(self.project_root)
        active_iwh = _active_iwh_dirs(self.project_root, self.config.iwh.ttl_hours)
        # Stash on self so _ctx() (dispatch phase) can expose them.
        self._uncommitted = uncommitted
        self._active_iwh = active_iwh

        # 1. Validation
        self._collect_validation(
            result, check=check, uncommitted=uncommitted, active_iwh=active_iwh
        )

        # 2. Hash-based staleness detection
        self._collect_staleness(result, scope=scope, uncommitted=uncommitted, active_iwh=active_iwh)

        # 3. IWH signal scan
        self._collect_iwh(result, scope=scope)

        # 4. Comment detection
        self._collect_comments(result, scope=scope, uncommitted=uncommitted, active_iwh=active_iwh)

        # 5. Agent-edit detection via change_checker
        self._collect_agent_edits(
            result, scope=scope, uncommitted=uncommitted, active_iwh=active_iwh
        )

        # 6. Link graph availability
        result.link_graph_available = self._check_link_graph()

        # 7. Deprecation candidate detection (Phase 2)
        self._collect_deprecation_candidates(result)

        # 8. Token budget checks (Phase 3)
        self._collect_budget_issues(result, scope=scope)

        # 9. TODO/FIXME/HACK scanning (Phase 3)
        self._collect_comment_audit_issues(result, scope=scope)

        # 10. Consistency checks (curator-fix Phase 3 — group 8)
        self._collect_consistency(
            result,
            scope=scope,
            uncommitted=uncommitted,
            active_iwh=active_iwh,
        )

        return result

    def _collect_validation(
        self,
        result: CollectResult,
        *,
        check: str | None = None,
        uncommitted: set[Path] | None = None,
        active_iwh: set[Path] | None = None,
    ) -> None:
        """Run validate_library() and add results to CollectResult."""
        from lexibrary.validator import validate_library  # noqa: PLC0415

        uncommitted = uncommitted or set()
        active_iwh = active_iwh or set()

        try:
            report = validate_library(
                self.project_root,
                self.lexibrary_dir,
                check_filter=check,
            )
            # Capture the raw issue count so the Phase 5 post-sweep
            # verification can compute a ``before`` figure without having
            # to re-run the validator when ``verify_after_sweep`` is False.
            self._validation_before_count = len(report.issues)
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
    ) -> None:
        """Walk design files and detect stale source/interface hashes."""
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
                    )
                )
                continue

            # Compare hashes
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
    ) -> None:
        """Scan IWH signals and add to results."""
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
    ) -> None:
        """Run :class:`ConsistencyChecker` checks and append ``CollectItem``s.

        Gated on ``self.curator_config.consistency_collect``:
        - ``"off"``   — skip all consistency checks.
        - ``"scope"`` — run scope-bounded checks (wikilink hygiene,
          slug/alias collisions, bidirectional deps, orphaned .aindex,
          orphaned .comments.yaml, stale conventions / playbooks,
          promotable blocked IWH).
        - ``"full"``  — also run library-wide checks (domain-term
          suggestion, orphan concept detection).

        ``FixInstruction`` objects returned by the checker are translated
        into :class:`CollectItem` rows with ``source="consistency"``, the
        raw ``action`` string on ``action_hint``, and the human-readable
        ``detail`` on ``fix_instruction_detail``.  Triage then maps
        ``action_hint`` to a canonical ``action_key`` via
        :data:`lexibrary.curator.consistency_fixes.CONSISTENCY_ACTION_KEYS`.
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
        # Wikilink hygiene: per-design-file pass.
        for design_path in design_files:
            try:
                instructions = checker.check_wikilinks(design_path)
            except Exception as exc:
                self.summary.add("collect", exc, path=str(design_path))
                continue
            for instruction in instructions:
                _append(instruction)

        # Slug collision detection across design files.
        try:
            for instruction in checker.detect_slug_collisions(design_files):
                _append(instruction)
        except Exception as exc:
            self.summary.add("collect", exc, path="slug_collisions")

        # Alias collisions across concepts + conventions.
        try:
            alias_instructions = checker.detect_alias_collisions(
                self.lexibrary_dir / "concepts",
                self.lexibrary_dir / "conventions",
            )
            for instruction in alias_instructions:
                _append(instruction)
        except Exception as exc:
            self.summary.add("collect", exc, path="alias_collisions")

        # Bidirectional dependency check.
        try:
            for instruction in checker.check_bidirectional_deps(design_files):
                _append(instruction)
        except Exception as exc:
            self.summary.add("collect", exc, path="bidirectional_deps")

        # Orphaned .aindex cleanup.
        try:
            for instruction in checker.detect_orphaned_aindex():
                _append(instruction)
        except Exception as exc:
            self.summary.add("collect", exc, path="orphaned_aindex")

        # Orphaned .comments.yaml cleanup.
        try:
            for instruction in checker.detect_orphaned_comments():
                _append(instruction)
        except Exception as exc:
            self.summary.add("collect", exc, path="orphaned_comments")

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
        """Classify and prioritise collected items for dispatch."""
        result = TriageResult()

        for item in collect.items:
            # Skip scope-isolation placeholders
            if item.check == "scope_isolation":
                continue

            triage_item = self._classify_item(item, collect.link_graph_available)
            if triage_item is not None:
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
    ) -> DispatchResult:
        """Apply autonomy gating and dispatch to sub-agent stubs."""
        # Stash on self so handlers consuming _ctx() see the correct flag.
        self._dry_run = dry_run
        result = DispatchResult()
        autonomy = self.curator_config.autonomy
        overrides = self.curator_config.risk_overrides
        max_llm = self.curator_config.max_llm_calls_per_run

        for item in triage.items:
            # Check LLM call cap
            if result.llm_calls_used >= max_llm:
                result.llm_cap_reached = True
                item_copy = TriageItem(
                    source_item=item.source_item,
                    issue_type=item.issue_type,
                    action_key=item.action_key,
                    priority=item.priority,
                    agent_edited=item.agent_edited,
                    reverse_dep_count=item.reverse_dep_count,
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
                # In dry-run mode, record as dispatched but don't execute
                result.dispatched.append(
                    SubAgentResult(
                        success=True,
                        action_key=item.action_key,
                        path=item.source_item.path,
                        message="dry-run: would dispatch",
                        llm_calls=0,
                        outcome="dry_run",
                    )
                )
                continue

            # Dispatch to sub-agent handler (or stub fallback for unrecognized keys)
            agent_result = await self._route_to_handler(item)
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
            "strip_unresolved_wikilink": consistency_fixes.apply_strip_wikilink,
            "fix_broken_wikilink_fuzzy": consistency_fixes.apply_substitute_wikilink,
            "resolve_slug_collision": consistency_fixes.apply_slug_suffix,
            "resolve_alias_collision": consistency_fixes.apply_alias_dedup,
            "add_missing_bidirectional_dep": consistency_fixes.apply_bidirectional_dep,
            "remove_orphaned_aindex": consistency_fixes.apply_orphaned_aindex_delete,
            "delete_orphaned_comments": consistency_fixes.apply_orphaned_comments_delete,
            "remove_orphan_zero_deps": consistency_fixes.apply_orphan_concept_delete,
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

        # Write to the artifact's parent directory in the .lexibrary mirror
        try:
            rel = dep.artifact_path.relative_to(self.project_root)
            mirror_dir = self.lexibrary_dir / rel.parent
        except ValueError:
            mirror_dir = dep.artifact_path.parent

        body = (
            f"Proposed deprecation: {dep.artifact_kind} at {dep.artifact_path.name}\n"
            f"Reason: {dep.reason}\n"
            f"Action key: {item.action_key}\n"
            f"Risk level: {item.risk_level or 'unknown'}\n"
            f"Autonomy gating prevented automatic execution."
        )

        try:
            write_iwh(mirror_dir, author="curator", scope="warning", body=body)
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

        # Populate dispatched_details for verbose rendering and persisted report
        dispatched_details: list[dict[str, object]] = [
            {
                "action_key": d.action_key,
                "path": str(d.path) if d.path is not None else None,
                "message": d.message,
                "success": d.success,
                "outcome": d.outcome,
                "llm_calls": d.llm_calls,
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
            if d.success
            and d.action_key.startswith("deprecate_")
            and d.outcome != "dry_run"
        )
        hard_deleted = sum(
            1
            for d in dispatch.dispatched
            if d.success
            and d.action_key.startswith("hard_delete_")
            and d.outcome != "dry_run"
        )

        # Phase 3: Budget and auditing counters
        budget_condensed = sum(
            1
            for d in dispatch.dispatched
            if d.success
            and d.action_key == "condense_file"
            and d.outcome != "dry_run"
        )
        budget_proposed = sum(
            1
            for d in dispatch.dispatched
            if d.success
            and d.action_key == "propose_condensation"
            and d.outcome != "dry_run"
        )
        comments_flagged = sum(
            1
            for d in dispatch.dispatched
            if d.success
            and d.action_key == "flag_stale_comment"
            and d.outcome != "dry_run"
        )
        descriptions_audited = sum(
            1
            for d in dispatch.dispatched
            if d.success
            and d.action_key == "audit_description"
            and d.outcome != "dry_run"
        )
        summaries_audited = sum(
            1
            for d in dispatch.dispatched
            if d.success
            and d.action_key == "audit_summary"
            and d.outcome != "dry_run"
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
            schema_version=2,
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
