"""Archivist pipeline: per-file and project-wide design file generation."""

from __future__ import annotations

import contextlib
import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from lexibrary.archivist.change_checker import (
    ChangeLevel,
    _compute_design_content_hash,
    check_change,
)
from lexibrary.archivist.dependency_extractor import extract_dependencies
from lexibrary.archivist.service import ArchivistService, DesignFileRequest
from lexibrary.archivist.start_here import generate_start_here
from lexibrary.artifacts.aindex import AIndexEntry
from lexibrary.artifacts.aindex_parser import parse_aindex
from lexibrary.artifacts.aindex_serializer import serialize_aindex
from lexibrary.artifacts.design_file import (
    DesignFile,
    DesignFileFrontmatter,
    StalenessMetadata,
)
from lexibrary.artifacts.design_file_parser import (
    _FOOTER_RE,
    parse_design_file,
    parse_design_file_frontmatter,
    parse_design_file_metadata,
)
from lexibrary.artifacts.design_file_serializer import serialize_design_file
from lexibrary.ast_parser import compute_hashes, parse_interface, render_skeleton
from lexibrary.config.schema import LexibraryConfig
from lexibrary.ignore import create_ignore_matcher
from lexibrary.indexer.orchestrator import index_directory
from lexibrary.linkgraph.builder import build_index
from lexibrary.utils.atomic import atomic_write
from lexibrary.utils.conflict import has_conflict_markers
from lexibrary.utils.languages import detect_language
from lexibrary.utils.paths import LEXIBRARY_DIR, aindex_path, mirror_path
from lexibrary.wiki.index import ConceptIndex

logger = logging.getLogger(__name__)

_GENERATOR_ID = "lexibrary-v2"

# Type for an optional progress callback: receives (file_path, change_level)
ProgressCallback = Callable[[Path, ChangeLevel], None]


@dataclass
class UpdateStats:
    """Accumulated statistics for a pipeline run."""

    files_scanned: int = 0
    files_unchanged: int = 0
    files_agent_updated: int = 0
    files_updated: int = 0
    files_created: int = 0
    files_failed: int = 0
    aindex_refreshed: int = 0
    token_budget_warnings: int = 0
    start_here_failed: bool = False
    linkgraph_built: bool = False
    linkgraph_error: str | None = None


@dataclass
class FileResult:
    """Result from update_file with change level and tracking flags."""

    change: ChangeLevel
    aindex_refreshed: bool = False
    token_budget_exceeded: bool = False
    failed: bool = False


def _is_within_scope(
    source_path: Path,
    project_root: Path,
    scope_root: str,
) -> bool:
    """Check whether *source_path* is under the configured scope_root."""
    scope_abs = (project_root / scope_root).resolve()
    try:
        source_path.resolve().relative_to(scope_abs)
        return True
    except ValueError:
        return False


def _is_binary(source_path: Path, binary_extensions: set[str]) -> bool:
    """Check whether a file has a binary extension."""
    return source_path.suffix.lower() in binary_extensions


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: split on whitespace."""
    return len(text.split())


def _refresh_footer_hashes(
    design_path: Path,
    content_hash: str,
    interface_hash: str | None,
    project_root: Path,
) -> None:
    """Re-write only the metadata footer with current source hashes.

    Used for AGENT_UPDATED files: the agent wrote the body, we just keep
    the footer in sync so subsequent runs see the file as UNCHANGED.
    """
    design_file = parse_design_file(design_path)
    if design_file is not None:
        # Full parse succeeded -- update metadata fields and re-serialize
        design_file.metadata.source_hash = content_hash
        design_file.metadata.interface_hash = interface_hash
        design_file.metadata.generated = datetime.now(UTC).replace(tzinfo=None)
        serialized = serialize_design_file(design_file)
        atomic_write(design_path, serialized)
        return

    # Full parse failed -- try metadata-level update
    try:
        raw = design_path.read_text(encoding="utf-8")
    except OSError:
        return

    metadata = parse_design_file_metadata(design_path)

    # Strip existing footer
    body = _FOOTER_RE.sub("", raw).rstrip("\n")
    design_hash = hashlib.sha256(body.encode()).hexdigest()

    now = datetime.now(UTC).replace(tzinfo=None)
    source_field = metadata.source if metadata is not None else str(design_path.stem)
    generator = metadata.generator if metadata is not None else _GENERATOR_ID

    footer_lines = [
        "<!-- lexibrary:meta",
        f"source: {source_field}",
        f"source_hash: {content_hash}",
    ]
    if interface_hash is not None:
        footer_lines.append(f"interface_hash: {interface_hash}")
    footer_lines.append(f"design_hash: {design_hash}")
    footer_lines.append(f"generated: {now.isoformat()}")
    footer_lines.append(f"generator: {generator}")
    footer_lines.append("-->")

    new_text = body + "\n\n" + "\n".join(footer_lines) + "\n"
    atomic_write(design_path, new_text)


def _refresh_parent_aindex(
    source_path: Path,
    project_root: Path,
    description: str,
) -> bool:
    """Update the parent directory's .aindex Child Map entry with *description*.

    Returns True if the .aindex was refreshed, False otherwise.
    """
    parent_dir = source_path.parent
    aindex_file_path = aindex_path(project_root, parent_dir)

    if not aindex_file_path.exists():
        return False

    aindex = parse_aindex(aindex_file_path)
    if aindex is None:
        return False

    file_name = source_path.name
    updated = False
    for entry in aindex.entries:
        if entry.name == file_name and entry.entry_type == "file":
            if entry.description != description:
                entry.description = description
                updated = True
            break
    else:
        # Entry not found -- add it
        aindex.entries.append(
            AIndexEntry(name=file_name, entry_type="file", description=description)
        )
        updated = True

    if updated:
        serialized = serialize_aindex(aindex)
        atomic_write(aindex_file_path, serialized)

    return updated


async def update_file(
    source_path: Path,
    project_root: Path,
    config: LexibraryConfig,
    archivist: ArchivistService,
    available_concepts: list[str] | None = None,
) -> FileResult:
    """Generate or update the design file for a single source file.

    Returns a ``FileResult`` containing the change level and tracking flags.
    """
    # 1. Scope check
    if not _is_within_scope(source_path, project_root, config.scope_root):
        return FileResult(change=ChangeLevel.UNCHANGED)

    # 1b. IWH check: skip if blocked signal exists for the source directory
    if config.iwh.enabled:
        from lexibrary.iwh.reader import read_iwh  # noqa: PLC0415
        from lexibrary.utils.paths import iwh_path as _iwh_path  # noqa: PLC0415

        iwh_dir = _iwh_path(project_root, source_path.parent).parent
        iwh_signal = read_iwh(iwh_dir)
        if iwh_signal is not None:
            if iwh_signal.scope == "blocked":
                logger.warning(
                    "Skipping %s: IWH blocked signal in %s — %s",
                    source_path.name,
                    source_path.parent,
                    iwh_signal.body[:100] if iwh_signal.body else "(no body)",
                )
                return FileResult(change=ChangeLevel.UNCHANGED)
            if iwh_signal.scope == "incomplete":
                logger.info(
                    "IWH incomplete signal in %s — proceeding with caution: %s",
                    source_path.parent,
                    iwh_signal.body[:100] if iwh_signal.body else "(no body)",
                )

    # 2. Compute hashes
    content_hash, interface_hash = compute_hashes(source_path)

    # 3. Change detection
    change = check_change(source_path, project_root, content_hash, interface_hash)
    logger.info("Change detection for %s: %s", source_path.name, change.value)

    # 4. UNCHANGED -- early return
    if change == ChangeLevel.UNCHANGED:
        return FileResult(change=change)

    design_path = mirror_path(project_root, source_path)
    design_path.parent.mkdir(parents=True, exist_ok=True)

    # 5. AGENT_UPDATED -- refresh footer only, no LLM call
    if change == ChangeLevel.AGENT_UPDATED:
        _refresh_footer_hashes(design_path, content_hash, interface_hash, project_root)
        # Still refresh parent .aindex if the design file has frontmatter
        aindex_refreshed = False
        frontmatter = parse_design_file_frontmatter(design_path)
        if frontmatter is not None and frontmatter.description.strip():
            aindex_refreshed = _refresh_parent_aindex(
                source_path,
                project_root,
                frontmatter.description.strip(),
            )
        return FileResult(change=change, aindex_refreshed=aindex_refreshed)

    # 5b. Conflict marker check — skip files with unresolved merge conflicts
    if has_conflict_markers(source_path):
        logger.warning(
            "Skipping %s: unresolved merge conflict markers detected",
            source_path.name,
        )
        return FileResult(change=change, failed=True)

    # 6. LLM generation: NEW_FILE, CONTENT_ONLY, CONTENT_CHANGED, INTERFACE_CHANGED
    rel_path = str(source_path.relative_to(project_root))
    try:
        source_content = source_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        logger.error("Cannot read source file: %s", source_path)
        return FileResult(change=change, failed=True)

    # Parse interface skeleton for the LLM prompt
    skeleton = parse_interface(source_path)
    skeleton_text: str | None = None
    if skeleton is not None:
        skeleton_text = render_skeleton(skeleton)

    language = detect_language(rel_path) if skeleton is not None else None

    # Capture pre-LLM design hash for TOCTOU re-check (D-061 / D3)
    pre_llm_design_hash: str | None = None
    pre_llm_metadata = parse_design_file_metadata(design_path)
    if pre_llm_metadata is not None and pre_llm_metadata.design_hash is not None:
        pre_llm_design_hash = pre_llm_metadata.design_hash

    # Read existing design file content for update context
    existing_design: str | None = None
    if design_path.exists():
        with contextlib.suppress(OSError):
            existing_design = design_path.read_text(encoding="utf-8")

    request = DesignFileRequest(
        source_path=rel_path,
        source_content=source_content,
        interface_skeleton=skeleton_text,
        language=language,
        existing_design_file=existing_design,
        available_concepts=available_concepts,
    )

    result = await archivist.generate_design_file(request)

    if result.error or result.design_file_output is None:
        logger.error(
            "Failed to generate design file for %s: %s",
            rel_path,
            result.error_message or "unknown error",
        )
        return FileResult(change=change, failed=True)

    output = result.design_file_output

    # 6b. Design hash re-check (TOCTOU protection, D-061 / D3)
    if pre_llm_design_hash is not None:
        post_llm_design_hash = _compute_design_content_hash(design_path)
        if post_llm_design_hash is not None and post_llm_design_hash != pre_llm_design_hash:
            logger.info(
                "Discarding LLM output for %s: design file was edited during generation",
                rel_path,
            )
            return FileResult(change=ChangeLevel.AGENT_UPDATED, aindex_refreshed=False)

    # 7. Build DesignFile model
    deps = extract_dependencies(source_path, project_root)
    description = output.summary or f"Design file for {source_path.name}"

    design_file = DesignFile(
        source_path=rel_path,
        frontmatter=DesignFileFrontmatter(
            description=description,
            updated_by="archivist",
        ),
        summary=description,
        interface_contract=output.interface_contract or "",
        dependencies=deps,
        dependents=[],
        tests=output.tests,
        complexity_warning=output.complexity_warning,
        wikilinks=list(output.wikilinks) if output.wikilinks else [],
        tags=list(output.tags) if output.tags else [],
        stack_refs=[],
        metadata=StalenessMetadata(
            source=rel_path,
            source_hash=content_hash,
            interface_hash=interface_hash,
            generated=datetime.now(UTC).replace(tzinfo=None),
            generator=_GENERATOR_ID,
        ),
    )

    # 8. Serialize and validate token budget
    serialized = serialize_design_file(design_file)

    token_budget_exceeded = False
    token_count = _estimate_tokens(serialized)
    budget = config.token_budgets.design_file_tokens
    if token_count > budget:
        logger.warning(
            "Design file for %s exceeds token budget: ~%d tokens > %d limit",
            rel_path,
            token_count,
            budget,
        )
        token_budget_exceeded = True

    # 9. Write design file (even if over budget)
    atomic_write(design_path, serialized)
    logger.info("Wrote design file: %s", design_path)

    # 10. Refresh parent .aindex
    aindex_refreshed = _refresh_parent_aindex(source_path, project_root, description)

    return FileResult(
        change=change,
        aindex_refreshed=aindex_refreshed,
        token_budget_exceeded=token_budget_exceeded,
    )


def _accumulate_stats(stats: UpdateStats, file_result: FileResult) -> None:
    """Update *stats* in-place from a single file result."""
    change = file_result.change
    if file_result.failed:
        stats.files_failed += 1
    elif change == ChangeLevel.UNCHANGED:
        stats.files_unchanged += 1
    elif change == ChangeLevel.AGENT_UPDATED:
        stats.files_agent_updated += 1
    elif change == ChangeLevel.NEW_FILE:
        stats.files_created += 1
    elif change in (
        ChangeLevel.CONTENT_ONLY,
        ChangeLevel.CONTENT_CHANGED,
        ChangeLevel.INTERFACE_CHANGED,
    ):
        stats.files_updated += 1

    if file_result.aindex_refreshed:
        stats.aindex_refreshed += 1
    if file_result.token_budget_exceeded:
        stats.token_budget_warnings += 1


def _has_meaningful_changes(stats: UpdateStats) -> bool:
    """Return True if any files were created, updated, or failed.

    Used to decide whether to run post-pipeline re-indexing.  When zero
    files actually changed, re-indexing is skipped because the existing
    ``.aindex`` files are already up-to-date.
    """
    return (stats.files_created + stats.files_updated + stats.files_failed) > 0


def reindex_directories(
    directories: list[Path],
    project_root: Path,
    config: LexibraryConfig,
) -> int:
    """Regenerate ``.aindex`` files for *directories* and their ancestors.

    For each directory in *directories*, walks up to ``scope_root`` and
    collects ancestor directories.  Then re-indexes each unique directory
    (deepest first so child ``.aindex`` data is available when parents
    are processed).

    Uses the existing ``index_directory()`` from the indexer orchestrator
    to ensure output is identical to ``lexictl index``.

    Args:
        directories: Source directories containing changed files.
        project_root: The project root (contains ``.lexibrary/``).
        config: Project configuration (provides ``scope_root``).

    Returns:
        Number of directories re-indexed.
    """
    if not directories:
        return 0

    scope_abs = (project_root / config.scope_root).resolve()

    # Collect all directories plus their ancestors up to scope_root
    all_dirs: set[Path] = set()
    for dir_path in directories:
        resolved = dir_path.resolve()
        # Walk up from the directory to scope_root (inclusive)
        current = resolved
        while True:
            all_dirs.add(current)
            if current == scope_abs:
                break
            parent = current.parent
            if parent == current:
                # Hit filesystem root without reaching scope_root
                break
            # Don't walk above scope_root
            try:
                parent.relative_to(scope_abs)
            except ValueError:
                break
            current = parent

    # Sort deepest-first so child .aindex files exist before parents
    sorted_dirs = sorted(all_dirs, key=lambda p: len(p.parts), reverse=True)

    count = 0
    for dir_path in sorted_dirs:
        if not dir_path.is_dir():
            continue
        try:
            index_directory(dir_path, project_root, config)
            count += 1
        except Exception:
            logger.exception("Failed to re-index directory: %s", dir_path)

    if count:
        logger.info("Re-indexed %d directories", count)

    return count


async def update_files(
    file_paths: list[Path],
    project_root: Path,
    config: LexibraryConfig,
    archivist: ArchivistService,
    progress_callback: ProgressCallback | None = None,
) -> UpdateStats:
    """Process a specific list of source files through the pipeline.

    Unlike ``update_project()``, this does NOT discover files via rglob and
    does NOT regenerate ``START_HERE.md``. It is designed for git-hook and
    ``--changed-only`` usage where the caller already knows which files changed.

    Files that are deleted, binary, ignored, or inside ``.lexibrary/`` are
    silently skipped for design file processing.  Deleted file paths are
    collected and forwarded to the link graph incremental update so that
    artifact rows and cascaded links are cleaned up.
    """
    stats = UpdateStats()
    ignore_matcher = create_ignore_matcher(config, project_root)
    binary_exts = set(config.crawl.binary_extensions)

    # Load available concept names for wikilink guidance
    concepts_dir = project_root / LEXIBRARY_DIR / "concepts"
    concept_index = ConceptIndex.load(concepts_dir)
    available_concepts = concept_index.names() or None

    # Collect deleted file paths before the processing loop so they can be
    # forwarded to the link graph incremental update for CASCADE cleanup.
    deleted_paths: list[Path] = [p for p in file_paths if not p.exists()]
    processed_paths: list[Path] = []

    for source_path in file_paths:
        # Skip deleted files (already collected above)
        if not source_path.exists():
            logger.debug("Skipping deleted file: %s", source_path)
            continue

        # Skip .lexibrary contents
        try:
            source_path.resolve().relative_to((project_root / LEXIBRARY_DIR).resolve())
            logger.debug("Skipping .lexibrary file: %s", source_path)
            continue
        except ValueError:
            pass

        # Skip binary files
        if _is_binary(source_path, binary_exts):
            logger.debug("Skipping binary file: %s", source_path)
            continue

        # Skip ignored files
        if ignore_matcher.is_ignored(source_path):
            logger.debug("Skipping ignored file: %s", source_path)
            continue

        stats.files_scanned += 1

        try:
            file_result = await update_file(
                source_path,
                project_root,
                config,
                archivist,
                available_concepts=available_concepts,
            )
        except Exception:
            logger.exception("Unexpected error processing %s", source_path)
            stats.files_failed += 1
            if progress_callback is not None:
                progress_callback(source_path, ChangeLevel.UNCHANGED)
            continue

        _accumulate_stats(stats, file_result)
        processed_paths.append(source_path)

        if progress_callback is not None:
            progress_callback(source_path, file_result.change)

    # Re-index directories containing changed files (plus ancestors up to
    # scope_root) so .aindex files stay fresh after hook-triggered updates.
    # Skipped when no files were actually created, updated, or failed (4.3).
    if _has_meaningful_changes(stats) and processed_paths:
        affected_dirs = sorted({p.parent for p in processed_paths})
        try:
            reindexed = reindex_directories(list(affected_dirs), project_root, config)
            stats.aindex_refreshed += reindexed
        except Exception:
            logger.exception("Failed to re-index directories after update_files")

    # Incremental link graph index update: pass both processed and deleted
    # paths so the builder can update changed artifacts and clean up deleted
    # ones via CASCADE.  Wrapped in try/except so index failures never block
    # the pipeline from returning design file stats (D3).
    all_changed = processed_paths + deleted_paths
    if all_changed:
        try:
            build_index(project_root, changed_paths=all_changed)
            stats.linkgraph_built = True
        except Exception:
            logger.exception("Failed to run incremental link graph update")
            stats.linkgraph_error = "Link graph incremental update failed"

    return stats


async def update_project(
    project_root: Path,
    config: LexibraryConfig,
    archivist: ArchivistService,
    progress_callback: ProgressCallback | None = None,
) -> UpdateStats:
    """Update all design files for the project.

    Discovers source files within scope_root, filters ignored and binary
    files, processes each sequentially, then returns accumulated stats.
    """
    stats = UpdateStats()
    ignore_matcher = create_ignore_matcher(config, project_root)
    binary_exts = set(config.crawl.binary_extensions)
    scope_abs = (project_root / config.scope_root).resolve()

    # Load available concept names for wikilink guidance
    concepts_dir = project_root / LEXIBRARY_DIR / "concepts"
    concept_index = ConceptIndex.load(concepts_dir)
    available_concepts = concept_index.names() or None

    # Discover all source files within scope
    source_files: list[Path] = []
    for path in sorted(scope_abs.rglob("*")):
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
                logger.debug("Skipping oversized file: %s (%.1f KB)", path, file_size_kb)
                continue
        except OSError:
            continue

        source_files.append(path)

    logger.info("Discovered %d source files for processing", len(source_files))

    # Track which files were actually changed (for targeted re-indexing)
    changed_file_paths: list[Path] = []

    # Process each file sequentially
    for source_path in source_files:
        stats.files_scanned += 1

        try:
            file_result = await update_file(
                source_path,
                project_root,
                config,
                archivist,
                available_concepts=available_concepts,
            )
        except Exception:
            logger.exception("Unexpected error processing %s", source_path)
            stats.files_failed += 1
            changed_file_paths.append(source_path)
            if progress_callback is not None:
                progress_callback(source_path, ChangeLevel.UNCHANGED)
            continue

        _accumulate_stats(stats, file_result)

        # Track files that were actually created, updated, or failed
        if file_result.change not in (ChangeLevel.UNCHANGED, ChangeLevel.AGENT_UPDATED):
            changed_file_paths.append(source_path)

        if progress_callback is not None:
            progress_callback(source_path, file_result.change)

    # Step 5: Regenerate START_HERE.md after processing all files (pipeline spec SS5)
    try:
        await generate_start_here(project_root, config, archivist)
    except Exception:
        logger.exception("Failed to regenerate START_HERE.md")
        stats.start_here_failed = True

    # Step 6: Re-index directories containing changed files (D-2, D-3).
    # Skipped when no files were actually created, updated, or failed (4.3).
    if _has_meaningful_changes(stats) and changed_file_paths:
        affected_dirs = sorted({p.parent for p in changed_file_paths})
        try:
            reindexed = reindex_directories(list(affected_dirs), project_root, config)
            stats.aindex_refreshed += reindexed
        except Exception:
            logger.exception("Failed to re-index directories after update_project")

    # Step 7: Build the link graph index (full rebuild after all artifacts are up to date)
    try:
        build_index(project_root)
        stats.linkgraph_built = True
    except Exception:
        logger.exception("Failed to build link graph index")
        stats.linkgraph_error = "Link graph full build failed"

    return stats
