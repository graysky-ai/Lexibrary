"""Auto-fix functions for validation issues.

Provides a registry of fixers keyed by check name. Only auto-fixable
checks have entries: ``hash_freshness``, ``orphan_artifacts``, and
``aindex_coverage``.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from lexibrary.config.schema import LexibraryConfig
from lexibrary.utils.paths import DESIGNS_DIR
from lexibrary.validator.report import ValidationIssue

logger = logging.getLogger(__name__)


@dataclass
class FixResult:
    """Result from attempting to auto-fix a validation issue."""

    check: str
    path: Path
    fixed: bool
    message: str


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
        archivist = ArchivistService(rate_limiter=rate_limiter, config=config.llm)
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
        source_rel = source_rel[len(designs_prefix):]

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


# Registry of auto-fixable checks.
# Maps check name -> fixer function.
FIXERS: dict[str, Callable[[ValidationIssue, Path, LexibraryConfig], FixResult]] = {
    "hash_freshness": fix_hash_freshness,
    "orphan_artifacts": fix_orphan_artifacts,
    "aindex_coverage": fix_aindex_coverage,
}
