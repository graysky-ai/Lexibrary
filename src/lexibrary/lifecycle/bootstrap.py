"""Bootstrap design file generation for existing projects.

Provides quick-mode (heuristic skeleton) and full-mode (LLM-enriched)
batch generation of design files across all source files in scope.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from lexibrary.archivist.change_checker import ChangeLevel, check_change
from lexibrary.archivist.dependency_extractor import extract_dependencies
from lexibrary.archivist.pipeline import (
    FileResult,
    _is_binary,
    _is_within_scope,
    _refresh_parent_aindex,
    update_file,
)
from lexibrary.artifacts.design_file import (
    DesignFile,
    DesignFileFrontmatter,
    StalenessMetadata,
)
from lexibrary.artifacts.design_file_serializer import serialize_design_file
from lexibrary.ast_parser import compute_hashes, parse_interface, render_skeleton
from lexibrary.config.schema import LexibraryConfig
from lexibrary.ignore import create_ignore_matcher
from lexibrary.utils.atomic import atomic_write
from lexibrary.utils.paths import LEXIBRARY_DIR, mirror_path

logger = logging.getLogger(__name__)

_GENERATOR_ID = "lexibrary-v2"

# Progress callback receives (source_path, status_label)
BootstrapProgressCallback = Callable[[Path, str], None]


@dataclass
class BootstrapStats:
    """Statistics accumulated during a bootstrap run."""

    files_scanned: int = 0
    files_created: int = 0
    files_updated: int = 0
    files_skipped: int = 0
    files_failed: int = 0
    errors: list[str] = field(default_factory=list)


def _extract_module_docstring(source_path: Path) -> str | None:
    """Extract the module-level docstring from a Python file.

    Returns the docstring text or None if no module docstring is found.
    """
    if source_path.suffix not in (".py", ".pyi"):
        return None

    try:
        source = source_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    import ast  # noqa: PLC0415

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    return ast.get_docstring(tree)


def _heuristic_description(source_path: Path) -> str:
    """Generate a heuristic description from filename and docstrings.

    Checks for a module-level docstring first. Falls back to a
    description derived from the filename.
    """
    docstring = _extract_module_docstring(source_path)
    if docstring:
        # Use first line of docstring as description
        first_line = docstring.strip().split("\n")[0].strip()
        if first_line:
            return first_line

    # Fallback: generate from filename
    stem = source_path.stem
    if stem == "__init__":
        return f"Package initializer for {source_path.parent.name}"
    if stem == "__main__":
        return f"Entry point for {source_path.parent.name}"

    # Convert snake_case to readable
    readable = stem.replace("_", " ").strip()
    return f"Design file for {readable}"


def _discover_source_files(
    scope_dir: Path,
    project_root: Path,
    config: LexibraryConfig,
) -> list[Path]:
    """Discover all source files within the scope directory.

    Filters out binary files, ignored files, .lexibrary contents,
    and files exceeding the max file size.
    """
    ignore_matcher = create_ignore_matcher(config, project_root)
    binary_exts = set(config.crawl.binary_extensions)

    source_files: list[Path] = []
    for path in sorted(scope_dir.rglob("*")):
        if not path.is_file():
            continue

        # Skip .lexibrary contents
        try:
            path.relative_to(project_root / LEXIBRARY_DIR)
            continue
        except ValueError:
            pass

        # Skip binary files
        if _is_binary(path, binary_exts):
            continue

        # Skip ignored files
        if ignore_matcher.is_ignored(path):
            continue

        # Skip files above max_file_size_kb
        try:
            file_size_kb = path.stat().st_size / 1024
            if file_size_kb > config.crawl.max_file_size_kb:
                continue
        except OSError:
            continue

        source_files.append(path)

    return source_files


def _generate_quick_design(
    source_path: Path,
    project_root: Path,
) -> FileResult:
    """Generate a skeleton design file for a single source file without LLM.

    Uses tree-sitter for interface extraction, AST for dependency extraction,
    and heuristics for the description. Marks the file with
    ``updated_by: bootstrap-quick``.

    Returns a FileResult indicating what happened.
    """
    # Compute hashes
    content_hash, interface_hash = compute_hashes(source_path)

    # Change detection
    change = check_change(source_path, project_root, content_hash, interface_hash)

    # Skip unchanged files
    if change == ChangeLevel.UNCHANGED:
        return FileResult(change=change)

    # Skip agent-updated files (preserve agent work)
    if change == ChangeLevel.AGENT_UPDATED:
        return FileResult(change=change)

    design_path = mirror_path(project_root, source_path)
    design_path.parent.mkdir(parents=True, exist_ok=True)

    rel_path = str(source_path.relative_to(project_root))

    # Extract interface skeleton
    skeleton = parse_interface(source_path)
    skeleton_text = ""
    if skeleton is not None:
        skeleton_text = render_skeleton(skeleton)

    # Extract dependencies
    deps = extract_dependencies(source_path, project_root)

    # Heuristic description
    description = _heuristic_description(source_path)

    # Build DesignFile model
    design_file = DesignFile(
        source_path=rel_path,
        frontmatter=DesignFileFrontmatter(
            description=description,
            updated_by="bootstrap-quick",
        ),
        summary=description,
        interface_contract=skeleton_text,
        dependencies=deps,
        dependents=[],
        metadata=StalenessMetadata(
            source=rel_path,
            source_hash=content_hash,
            interface_hash=interface_hash,
            generated=datetime.now(UTC).replace(tzinfo=None),
            generator=_GENERATOR_ID,
        ),
    )

    # Serialize and write
    serialized = serialize_design_file(design_file)
    atomic_write(design_path, serialized)
    logger.info("Bootstrap (quick): wrote %s", design_path)

    # Refresh parent .aindex
    aindex_refreshed = _refresh_parent_aindex(source_path, project_root, description)

    return FileResult(
        change=change,
        aindex_refreshed=aindex_refreshed,
    )


def bootstrap_quick(
    project_root: Path,
    config: LexibraryConfig,
    scope_override: str | None = None,
    progress_callback: BootstrapProgressCallback | None = None,
) -> BootstrapStats:
    """Run quick-mode bootstrap: generate skeleton design files for all source files.

    Discovers source files within the scope root, generates design files
    using tree-sitter extraction and heuristic descriptions (no LLM calls),
    and reports progress.

    Args:
        project_root: Absolute path to the project root.
        config: Project configuration.
        scope_override: Optional scope root override (relative to project root).
        progress_callback: Optional callback receiving (source_path, status_label).

    Returns:
        BootstrapStats with counts of scanned, created, updated, skipped files.
    """
    stats = BootstrapStats()

    # Resolve scope root
    scope_root_str = scope_override if scope_override is not None else config.scope_root
    scope_dir = (project_root / scope_root_str).resolve()

    # Discover source files
    source_files = _discover_source_files(scope_dir, project_root, config)
    logger.info("Bootstrap: discovered %d source files", len(source_files))

    for source_path in source_files:
        stats.files_scanned += 1

        try:
            result = _generate_quick_design(source_path, project_root)
        except Exception as exc:
            logger.exception("Bootstrap failed for %s", source_path)
            stats.files_failed += 1
            stats.errors.append(f"{source_path.name}: {exc}")
            if progress_callback is not None:
                progress_callback(source_path, "failed")
            continue

        # Accumulate stats
        if result.change in (ChangeLevel.UNCHANGED, ChangeLevel.AGENT_UPDATED):
            stats.files_skipped += 1
            status = "skipped"
        elif result.change == ChangeLevel.NEW_FILE:
            stats.files_created += 1
            status = "created"
        else:
            stats.files_updated += 1
            status = "updated"

        if progress_callback is not None:
            progress_callback(source_path, status)

    return stats


async def bootstrap_full(
    project_root: Path,
    config: LexibraryConfig,
    scope_override: str | None = None,
    progress_callback: BootstrapProgressCallback | None = None,
) -> BootstrapStats:
    """Run full-mode bootstrap: generate LLM-enriched design files for all source files.

    Discovers source files within the scope root and processes each through
    the standard archivist pipeline (which includes LLM enrichment via
    ``ArchivistService``). Files are generated with ``updated_by: archivist``.

    Args:
        project_root: Absolute path to the project root.
        config: Project configuration.
        scope_override: Optional scope root override (relative to project root).
        progress_callback: Optional callback receiving (source_path, status_label).

    Returns:
        BootstrapStats with counts of scanned, created, updated, skipped files.
    """
    from lexibrary.archivist.service import ArchivistService  # noqa: PLC0415
    from lexibrary.llm.rate_limiter import RateLimiter  # noqa: PLC0415

    stats = BootstrapStats()

    # Resolve scope root
    scope_root_str = scope_override if scope_override is not None else config.scope_root
    scope_dir = (project_root / scope_root_str).resolve()

    # Create archivist service for LLM enrichment
    rate_limiter = RateLimiter()
    archivist = ArchivistService(rate_limiter=rate_limiter, config=config.llm)

    # Discover source files
    source_files = _discover_source_files(scope_dir, project_root, config)
    logger.info("Bootstrap (full): discovered %d source files", len(source_files))

    for source_path in source_files:
        stats.files_scanned += 1

        # Scope check (update_file does this internally, but we skip
        # files out of scope before the call for efficiency)
        if not _is_within_scope(source_path, project_root, scope_root_str):
            stats.files_skipped += 1
            if progress_callback is not None:
                progress_callback(source_path, "skipped")
            continue

        try:
            result = await update_file(
                source_path,
                project_root,
                config,
                archivist,
            )
        except Exception as exc:
            logger.exception("Bootstrap (full) failed for %s", source_path)
            stats.files_failed += 1
            stats.errors.append(f"{source_path.name}: {exc}")
            if progress_callback is not None:
                progress_callback(source_path, "failed")
            continue

        # Accumulate stats
        if result.failed:
            stats.files_failed += 1
            status = "failed"
        elif result.change in (ChangeLevel.UNCHANGED, ChangeLevel.AGENT_UPDATED):
            stats.files_skipped += 1
            status = "skipped"
        elif result.change == ChangeLevel.NEW_FILE:
            stats.files_created += 1
            status = "created"
        else:
            stats.files_updated += 1
            status = "updated"

        if progress_callback is not None:
            progress_callback(source_path, status)

    return stats
