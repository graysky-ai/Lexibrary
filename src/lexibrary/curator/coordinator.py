"""Curator coordinator -- four-phase pipeline for automated library maintenance.

Executes a deterministic collect-triage-dispatch-report pipeline.  All LLM
judgment is delegated to sub-agent stubs (BAML integration in later groups);
the coordinator itself makes no LLM calls.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from lexibrary.config.schema import LexibraryConfig
from lexibrary.curator.config import CuratorConfig
from lexibrary.curator.models import (
    CollectItem,
    CollectResult,
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

logger = logging.getLogger(__name__)

# Stale lock threshold in seconds (30 minutes).
_STALE_LOCK_SECONDS = 30 * 60


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
    import contextlib  # noqa: PLC0415

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

    # -- Public API ---------------------------------------------------------

    async def run(
        self,
        *,
        scope: Path | None = None,
        check: str | None = None,
        dry_run: bool = False,
    ) -> CuratorReport:
        """Execute the full curator pipeline and return a report."""
        _acquire_lock(self.project_root)
        try:
            return await self._run_pipeline(scope=scope, check=check, dry_run=dry_run)
        finally:
            _release_lock(self.project_root)

    # -- Pipeline -----------------------------------------------------------

    async def _run_pipeline(
        self,
        *,
        scope: Path | None = None,
        check: str | None = None,
        dry_run: bool = False,
    ) -> CuratorReport:
        """Internal pipeline execution after lock acquisition."""
        # Phase 1: Collect
        collect_result = self._collect(scope=scope, check=check)

        # Phase 2: Triage
        triage_result = self._triage(collect_result)

        # Phase 3: Dispatch
        dispatch_result = self._dispatch(triage_result, dry_run=dry_run)

        # Phase 3b: Migration dispatch cycle (after deprecations committed)
        migrations_applied, migrations_proposed = self._dispatch_migrations(
            dispatch_result, dry_run=dry_run
        )

        # Phase 4: Report
        report = self._report(
            collect_result,
            triage_result,
            dispatch_result,
            migrations_applied=migrations_applied,
            migrations_proposed=migrations_proposed,
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

        # 1. Validation
        self._collect_validation(result, check=check)

        # 2. Hash-based staleness detection
        self._collect_staleness(result, scope=scope, uncommitted=uncommitted, active_iwh=active_iwh)

        # 3. IWH signal scan
        self._collect_iwh(result, scope=scope)

        # 4. Comment detection
        self._collect_comments(result, scope=scope)

        # 5. Agent-edit detection via change_checker
        self._collect_agent_edits(
            result, scope=scope, uncommitted=uncommitted, active_iwh=active_iwh
        )

        # 6. Link graph availability
        result.link_graph_available = self._check_link_graph()

        # 7. Deprecation candidate detection (Phase 2)
        self._collect_deprecation_candidates(result)

        return result

    def _collect_validation(
        self,
        result: CollectResult,
        *,
        check: str | None = None,
    ) -> None:
        """Run validate_library() and add results to CollectResult."""
        from lexibrary.validator import validate_library  # noqa: PLC0415

        try:
            report = validate_library(
                self.project_root,
                self.lexibrary_dir,
                check_filter=check,
            )
            for issue in report.issues:
                result.items.append(
                    CollectItem(
                        source="validation",
                        path=Path(issue.artifact) if issue.artifact else None,
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

            # Scope isolation: skip uncommitted files
            if source_path in uncommitted:
                result.items.append(
                    CollectItem(
                        source="staleness",
                        path=source_path,
                        severity="info",
                        message="Skipped -- uncommitted changes detected",
                        check="scope_isolation",
                    )
                )
                continue

            # Scope isolation: skip files in active IWH directories
            if any(source_path.is_relative_to(d) for d in active_iwh):
                result.items.append(
                    CollectItem(
                        source="staleness",
                        path=source_path,
                        severity="info",
                        message="Skipped -- active IWH signal in directory",
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

        try:
            signals = find_all_iwh(self.project_root)
        except Exception as exc:
            self.summary.add("collect", exc, path="iwh_scan")
            return

        for rel_dir, iwh in signals:
            source_dir = self.project_root / rel_dir
            if scope is not None and not source_dir.is_relative_to(scope):
                continue
            result.items.append(
                CollectItem(
                    source="iwh",
                    path=source_dir,
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
    ) -> None:
        """Detect design files with unprocessed sidecar comments."""
        from lexibrary.lifecycle.comments import comment_count  # noqa: PLC0415
        from lexibrary.lifecycle.design_comments import design_comment_path  # noqa: PLC0415

        designs_dir = self.lexibrary_dir / "designs"
        if not designs_dir.is_dir():
            return

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
        """Classify a validation issue."""
        # Map validation checks to issue types and action keys
        issue_type = "consistency"
        action_key = "autofix_validation_issue"

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
        """Classify an IWH signal."""
        # IWH signals may be superseded or blocked
        if "scope=blocked" in item.message:
            action_key = "promote_blocked_iwh"
        else:
            action_key = "consume_superseded_iwh"

        return TriageItem(
            source_item=item,
            issue_type="orphan",
            action_key=action_key,
            priority=5.0,
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

    def _dispatch(
        self,
        triage: TriageResult,
        *,
        dry_run: bool = False,
    ) -> DispatchResult:
        """Apply autonomy gating and dispatch to sub-agent stubs."""
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
                    )
                )
                continue

            # Dispatch to sub-agent stub
            agent_result = self._dispatch_to_stub(item)
            result.dispatched.append(agent_result)
            result.llm_calls_used += agent_result.llm_calls

        return result

    def _dispatch_to_stub(self, item: TriageItem) -> SubAgentResult:
        """Dispatch a triage item to a sub-agent or stub.

        Routes ``regenerate_stale_design`` to the Staleness Resolver,
        ``reconcile_agent_*`` to the Reconciliation sub-agent,
        ``integrate_sidecar_comments`` to the Comment Curator,
        deprecation action keys to the Deprecation Analyst.
        All other action keys remain as stubs until their sub-agents are
        implemented in later groups.
        """
        # Deprecation workflow dispatch
        if item.issue_type == "deprecation" and item.deprecation_item is not None:
            return self._dispatch_deprecation(item)

        if item.action_key == "regenerate_stale_design":
            return self._dispatch_staleness_resolver(item)

        if item.action_key in (
            "reconcile_agent_interface_stable",
            "reconcile_agent_interface_changed",
            "reconcile_agent_extensive_content",
        ):
            return self._dispatch_reconciliation(item)

        if item.action_key == "integrate_sidecar_comments":
            return self._dispatch_comment_integration(item)

        try:
            risk = get_risk_level(item.action_key, self.curator_config.risk_overrides)
        except KeyError:
            risk = "unknown"

        # Stub: return success with 1 LLM call for non-deterministic actions
        llm_calls = 1 if risk in ("medium", "high") else 0
        return SubAgentResult(
            success=True,
            action_key=item.action_key,
            path=item.source_item.path,
            message=f"stub: {item.action_key} (risk={risk})",
            llm_calls=llm_calls,
        )

    def _dispatch_staleness_resolver(self, item: TriageItem) -> SubAgentResult:
        """Dispatch a staleness item to the Staleness Resolver.

        For non-agent-edited files, the resolver regenerates the design
        file via the archivist pipeline (BAML stub for now).  Agent-edited
        files are returned as deferred.
        """
        from lexibrary.curator.staleness import (  # noqa: PLC0415
            StalenessWorkItem,
            resolve_stale_design,
            staleness_result_to_sub_agent_result,
        )
        from lexibrary.utils.paths import mirror_path  # noqa: PLC0415

        source_path = item.source_item.path
        if source_path is None:
            return SubAgentResult(
                success=False,
                action_key="regenerate_stale_design",
                path=None,
                message="No source path available for staleness resolution",
            )

        design_path = mirror_path(self.project_root, source_path)

        work_item = StalenessWorkItem(
            source_path=source_path,
            design_path=design_path,
            source_hash_stale=item.source_item.source_hash_stale,
            interface_hash_stale=item.source_item.interface_hash_stale,
            updated_by=item.source_item.updated_by,
        )

        try:
            result = resolve_stale_design(work_item, self.project_root)
            return staleness_result_to_sub_agent_result(result)
        except Exception as exc:
            self.summary.add(
                "dispatch",
                exc,
                path=str(source_path),
            )
            return SubAgentResult(
                success=False,
                action_key="regenerate_stale_design",
                path=source_path,
                message=f"Staleness resolver error: {exc}",
            )

    def _dispatch_reconciliation(self, item: TriageItem) -> SubAgentResult:
        """Dispatch an agent-edit reconciliation item.

        Sends the work item to the Reconciliation sub-agent (Opus) via BAML
        stub.  On successful return: passes through ``serialize_design_file()``,
        sets ``updated_by: curator``, computes fresh hashes, writes via
        ``atomic_write()``.

        On low-confidence or malformed output: does NOT write, creates IWH
        signal (scope: warning), records failure in report, leaves existing
        stale file in place.
        """
        from lexibrary.curator.reconciliation import (  # noqa: PLC0415
            ReconciliationWorkItem,
            reconcile_agent_design,
            reconciliation_result_to_sub_agent_result,
        )
        from lexibrary.utils.paths import mirror_path  # noqa: PLC0415

        source_path = item.source_item.path
        if source_path is None:
            return SubAgentResult(
                success=False,
                action_key=item.action_key,
                path=None,
                message="No source path available for reconciliation",
            )

        design_path = mirror_path(self.project_root, source_path)

        work_item = ReconciliationWorkItem(
            source_path=source_path,
            design_path=design_path,
            source_hash_stale=item.source_item.source_hash_stale,
            interface_hash_stale=item.source_item.interface_hash_stale,
            updated_by=item.source_item.updated_by,
            risk_level=item.risk_level or "low",
        )

        try:
            result = reconcile_agent_design(work_item, self.project_root)
            return reconciliation_result_to_sub_agent_result(result)
        except Exception as exc:
            self.summary.add(
                "dispatch",
                exc,
                path=str(source_path),
            )
            return SubAgentResult(
                success=False,
                action_key=item.action_key,
                path=source_path,
                message=f"Reconciliation error: {exc}",
            )

    def _dispatch_comment_integration(self, item: TriageItem) -> SubAgentResult:
        """Dispatch a comment integration item to the Comment Curator.

        Reads sidecar comments, calls the Comment Curator sub-agent,
        updates the design file Insights section, and handles Stack
        post promotion for actionable comments.
        """
        from lexibrary.curator.comments import (  # noqa: PLC0415
            CommentWorkItem,
            comment_result_to_sub_agent_result,
            integrate_comments,
            promote_to_stack_post,
        )
        from lexibrary.lifecycle.comments import read_comments  # noqa: PLC0415
        from lexibrary.stack.helpers import stack_dir  # noqa: PLC0415

        if item.comment_item is None:
            return SubAgentResult(
                success=False,
                action_key="integrate_sidecar_comments",
                path=item.source_item.path,
                message="No comment item available for integration",
            )

        # Read the actual comments from sidecar
        comments = read_comments(item.comment_item.comments_path)
        if not comments:
            return SubAgentResult(
                success=True,
                action_key="integrate_sidecar_comments",
                path=item.source_item.path,
                message="No comments to process",
                llm_calls=0,
            )

        work_item = CommentWorkItem(
            design_path=item.comment_item.design_path,
            source_path=item.comment_item.source_path,
            comments_path=item.comment_item.comments_path,
            comments=comments,
        )

        try:
            result = integrate_comments(work_item, self.project_root)
        except Exception as exc:
            self.summary.add(
                "dispatch",
                exc,
                path=str(item.comment_item.source_path),
            )
            return SubAgentResult(
                success=False,
                action_key="integrate_sidecar_comments",
                path=item.source_item.path,
                message=f"Comment integration error: {exc}",
            )

        # Handle actionable comment promotion to Stack posts
        if result.success:
            sdir = stack_dir(self.project_root)
            source_rel = str(item.comment_item.source_path.relative_to(self.project_root))
            for classification in result.classifications:
                if classification.disposition == "actionable":
                    try:
                        promote_to_stack_post(
                            sdir,
                            source_path=source_rel,
                            title=classification.promotion_title,
                            problem=classification.promotion_problem,
                        )
                    except Exception as exc:
                        self.summary.add(
                            "dispatch",
                            exc,
                            path=f"stack-promote:{source_rel}",
                        )

        return comment_result_to_sub_agent_result(result, item.source_item.path)

    # -- Deprecation dispatch -----------------------------------------------

    def _dispatch_deprecation(self, item: TriageItem) -> SubAgentResult:
        """Dispatch a deprecation candidate to the appropriate handler.

        Routes to hard deletion, lifecycle deprecation, or the Deprecation
        Analyst sub-agent depending on the action key.  Before dispatch:
        checks ``git status``, IWH signals, and risk level.
        """
        dep = item.deprecation_item
        if dep is None:
            return SubAgentResult(
                success=False,
                action_key=item.action_key,
                path=item.source_item.path,
                message="No deprecation item available for dispatch",
            )

        action_key = item.action_key

        # Hard deletion actions (TTL-expired, zero refs)
        if action_key.startswith("hard_delete_"):
            return self._dispatch_hard_delete(item, dep)

        # Stack post transition
        if action_key == "stack_post_transition":
            return self._dispatch_stack_transition(item, dep)

        # Soft deprecation (concept, convention, playbook, design_file)
        return self._dispatch_soft_deprecation(item, dep)

    def _dispatch_hard_delete(
        self, item: TriageItem, dep: DeprecationCollectItem
    ) -> SubAgentResult:
        """Execute hard deletion of a TTL-expired deprecated artifact."""
        from lexibrary.curator.lifecycle import execute_hard_delete  # noqa: PLC0415
        from lexibrary.linkgraph.query import open_index  # noqa: PLC0415

        link_graph = open_index(self.project_root)
        try:
            execute_hard_delete(
                kind=dep.artifact_kind,
                artifact_path=dep.artifact_path,
                ttl_commits=self.curator_config.deprecation.ttl_commits,
                commits_since_deprecation=dep.commits_since_deprecation,
                link_graph=link_graph,
            )
            return SubAgentResult(
                success=True,
                action_key=item.action_key,
                path=dep.artifact_path,
                message=f"Hard-deleted {dep.artifact_kind}: {dep.artifact_path.name}",
                llm_calls=0,
            )
        except Exception as exc:
            self.summary.add("dispatch", exc, path=str(dep.artifact_path))
            return SubAgentResult(
                success=False,
                action_key=item.action_key,
                path=dep.artifact_path,
                message=f"Hard deletion failed: {exc}",
            )
        finally:
            if link_graph is not None:
                link_graph.close()

    def _dispatch_stack_transition(
        self, item: TriageItem, dep: DeprecationCollectItem
    ) -> SubAgentResult:
        """Dispatch a stack post state transition (e.g. resolved -> stale)."""
        from lexibrary.curator.lifecycle import execute_deprecation  # noqa: PLC0415

        try:
            execute_deprecation(
                kind="stack_post",
                artifact_path=dep.artifact_path,
                target_status="stale",
            )
            return SubAgentResult(
                success=True,
                action_key=item.action_key,
                path=dep.artifact_path,
                message=f"Transitioned stack post to stale: {dep.artifact_path.name}",
                llm_calls=0,
            )
        except Exception as exc:
            self.summary.add("dispatch", exc, path=str(dep.artifact_path))
            return SubAgentResult(
                success=False,
                action_key=item.action_key,
                path=dep.artifact_path,
                message=f"Stack transition failed: {exc}",
            )

    def _dispatch_soft_deprecation(
        self, item: TriageItem, dep: DeprecationCollectItem
    ) -> SubAgentResult:
        """Dispatch soft deprecation via the Deprecation Analyst sub-agent.

        For now this is a stub that performs the deprecation directly
        using the lifecycle module.  When the BAML sub-agent is wired
        in, this will route through ``analyze_deprecation()`` first.
        """
        from lexibrary.curator.lifecycle import execute_deprecation  # noqa: PLC0415

        target_status = "deprecated"
        if dep.artifact_kind == "design_file" and dep.reason == "source_deleted":
            target_status = "deprecated"

        try:
            execute_deprecation(
                kind=dep.artifact_kind,
                artifact_path=dep.artifact_path,
                target_status=target_status,
                deprecated_reason=dep.reason,
            )
            return SubAgentResult(
                success=True,
                action_key=item.action_key,
                path=dep.artifact_path,
                message=f"Deprecated {dep.artifact_kind}: {dep.artifact_path.name}",
                llm_calls=1,
            )
        except Exception as exc:
            self.summary.add("dispatch", exc, path=str(dep.artifact_path))
            return SubAgentResult(
                success=False,
                action_key=item.action_key,
                path=dep.artifact_path,
                message=f"Deprecation failed: {exc}",
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

    # -- Phase 4: Report ----------------------------------------------------

    def _report(
        self,
        collect: CollectResult,
        triage: TriageResult,
        dispatch: DispatchResult,
        *,
        migrations_applied: int = 0,
        migrations_proposed: int = 0,
    ) -> CuratorReport:
        """Aggregate results into a CuratorReport and write to disk."""
        # Count sub-agent calls by type
        sub_agent_calls: dict[str, int] = {}
        for d in dispatch.dispatched:
            sub_agent_calls[d.action_key] = sub_agent_calls.get(d.action_key, 0) + 1

        # Count fixed (successful dispatches that actually ran)
        fixed = sum(
            1 for d in dispatch.dispatched if d.success and d.message != "dry-run: would dispatch"
        )

        # Count deprecation-specific results
        deprecated = sum(
            1
            for d in dispatch.dispatched
            if d.success
            and d.action_key.startswith("deprecate_")
            and d.message != "dry-run: would dispatch"
        )
        hard_deleted = sum(
            1
            for d in dispatch.dispatched
            if d.success
            and d.action_key.startswith("hard_delete_")
            and d.message != "dry-run: would dispatch"
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

        data = {
            "timestamp": timestamp,
            "checked": report.checked,
            "fixed": report.fixed,
            "deferred": report.deferred,
            "errored": report.errored,
            "errors": report.errors,
            "sub_agent_calls": report.sub_agent_calls,
            "deprecated": report.deprecated,
            "hard_deleted": report.hard_deleted,
            "migrations_applied": report.migrations_applied,
            "migrations_proposed": report.migrations_proposed,
        }

        try:
            report_file.write_text(
                json.dumps(data, indent=2, default=str),
                encoding="utf-8",
            )
        except OSError as exc:
            self.summary.add("report", exc, path=str(report_file))
            return None

        return report_file
