"""Archivist pipeline: per-file and project-wide design file generation."""

from __future__ import annotations

import contextlib
import hashlib
import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lexibrary.archivist.symbol_graph_context import SymbolGraphPromptContext
    from lexibrary.services.symbols import SymbolQueryService
    from lexibrary.tokenizer.tiktoken_counter import TiktokenCounter

from lexibrary.archivist.change_checker import (
    ChangeLevel,
    _compute_design_content_hash,
    check_change,
)
from lexibrary.archivist.dependency_extractor import extract_dependencies
from lexibrary.archivist.service import ArchivistService, DesignFileRequest
from lexibrary.archivist.skeleton import generate_skeleton_design
from lexibrary.archivist.topology import generate_raw_topology
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
from lexibrary.artifacts.ids import next_design_id
from lexibrary.ast_parser import compute_hashes, parse_interface, render_skeleton
from lexibrary.config.schema import LexibraryConfig
from lexibrary.conventions.index import ConventionIndex
from lexibrary.errors import ErrorSummary
from lexibrary.exceptions import ArchivistTruncationError
from lexibrary.ignore import create_ignore_matcher
from lexibrary.indexer.orchestrator import index_directory
from lexibrary.lifecycle.deprecation import (
    deprecate_design,
    detect_orphaned_designs,
    detect_renames,
    hard_delete_expired,
    mark_unlinked,
    migrate_design_on_rename,
)
from lexibrary.lifecycle.queue import clear_queue, read_queue
from lexibrary.linkgraph.builder import build_index
from lexibrary.playbooks.index import PlaybookIndex
from lexibrary.utils.atomic import atomic_write
from lexibrary.utils.conflict import has_conflict_markers
from lexibrary.utils.languages import detect_language
from lexibrary.utils.paths import DESIGNS_DIR, LEXIBRARY_DIR, aindex_path, mirror_path
from lexibrary.wiki.index import ConceptIndex

logger = logging.getLogger(__name__)

_GENERATOR_ID = "lexibrary-v2"

# Type for an optional progress callback: receives (file_path, change_level)
ProgressCallback = Callable[[Path, ChangeLevel, str | None], None]


@dataclass
class UpdateStats:
    """Accumulated statistics for a pipeline run."""

    files_scanned: int = 0
    files_unchanged: int = 0
    files_agent_updated: int = 0
    files_updated: int = 0
    files_created: int = 0
    files_skeletons: int = 0
    files_failed: int = 0
    failed_files: list[tuple[str, str]] = field(default_factory=list)
    aindex_refreshed: int = 0
    token_budget_warnings: int = 0
    topology_failed: bool = False
    linkgraph_built: bool = False
    linkgraph_error: str | None = None
    symbolgraph_built: bool = False
    symbolgraph_error: str | None = None
    symbolgraph_symbol_count: int = 0
    symbolgraph_call_count: int = 0
    # Deprecation lifecycle stats
    designs_deprecated: int = 0
    designs_unlinked: int = 0
    designs_deleted_ttl: int = 0
    # Concept deprecation lifecycle stats
    concepts_deleted_ttl: int = 0
    concepts_skipped_referenced: int = 0
    concept_comments_deleted: int = 0
    # Convention deprecation lifecycle stats
    conventions_deleted_ttl: int = 0
    convention_comments_deleted: int = 0
    # Rename migration stats
    renames_detected: int = 0
    renames_migrated: int = 0
    # Enrichment queue stats
    queue_processed: int = 0
    queue_failed: int = 0
    queue_remaining: int = 0
    error_summary: ErrorSummary = field(default_factory=ErrorSummary)


@dataclass
class FileResult:
    """Result from update_file with change level and tracking flags."""

    change: ChangeLevel
    aindex_refreshed: bool = False
    token_budget_exceeded: bool = False
    skeleton: bool = False
    failed: bool = False
    failure_reason: str | None = None
    skip_reason: str | None = None


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


_VALID_UPDATED_BY: frozenset[str] = frozenset(
    {
        "archivist",
        "agent",
        "bootstrap-quick",
        "maintainer",
        "curator",
        "skeleton-fallback",
    }
)


def _check_invalid_updated_by(
    design_path: Path,
    valid_values: set[str] | frozenset[str],
) -> str | None:
    """Check whether a design file's ``updated_by`` frontmatter field is valid.

    Returns the offending value string if the field exists and is NOT in
    *valid_values*, or ``None`` in all other cases (missing file, no
    frontmatter, no field, or a valid value).

    This guard prevents the archivist from clobbering design files that were
    last touched by an unrecognised tool.  The Curator is the canonical
    authority for resolving such conflicts.

    Reads raw YAML directly rather than delegating to parse_design_file_frontmatter
    because that function silently returns None (or falls back to defaults) when
    the Pydantic model rejects an invalid updated_by value — exactly the case we
    need to detect.
    """
    if not design_path.exists():
        return None

    try:
        raw = design_path.read_text(encoding="utf-8")
    except OSError:
        return None

    # Extract YAML frontmatter block between the first two "---" delimiters.
    import re  # noqa: PLC0415

    fm_match = re.match(r"^---\n(.*?)\n---", raw, re.DOTALL)
    if not fm_match:
        return None

    import yaml  # noqa: PLC0415

    try:
        fm_data = yaml.safe_load(fm_match.group(1))
    except yaml.YAMLError:
        return None

    if not isinstance(fm_data, dict):
        return None

    if "updated_by" not in fm_data:
        return None

    value = fm_data["updated_by"]
    if value in valid_values:
        return None

    return str(value)


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


def discover_source_files(
    project_root: Path,
    config: LexibraryConfig,
    scope_dir: Path | None = None,
) -> list[Path]:
    """Discover source files eligible for design file generation.

    Walks *scope_dir* (defaulting to ``config.scope_root``) recursively,
    excluding files inside ``.lexibrary/``, binary files, ignored files,
    and files exceeding ``max_file_size_kb``.
    """
    ignore_matcher = create_ignore_matcher(config, project_root)
    binary_exts = set(config.crawl.binary_extensions)

    if scope_dir is not None:
        scope_abs = scope_dir.resolve()
    else:
        scope_abs = (project_root / config.scope_root).resolve()

    source_files: list[Path] = []
    for path in sorted(scope_abs.rglob("*")):
        if not path.is_file():
            continue

        try:
            path.relative_to(project_root / LEXIBRARY_DIR)
            continue
        except ValueError:
            pass

        if _is_binary(path, binary_exts):
            continue

        if ignore_matcher.is_ignored(path):
            continue

        try:
            file_size_kb = path.stat().st_size / 1024
            if file_size_kb > config.crawl.max_file_size_kb:
                logger.debug("Skipping oversized file: %s (%.1f KB)", path, file_size_kb)
                continue
        except OSError:
            continue

        source_files.append(path)

    return source_files


async def dry_run_project(
    project_root: Path,
    config: LexibraryConfig,
    scope_dir: Path | None = None,
) -> list[tuple[Path, ChangeLevel]]:
    """Preview which files would be processed, without LLM calls or writes.

    Discovers source files within *scope_dir* (defaulting to
    ``config.scope_root``), runs change detection on each, and returns a
    list of files that would change with their change levels.  Files
    classified as UNCHANGED are excluded from the result.

    Args:
        project_root: Absolute path to the project root.
        config: Project configuration.
        scope_dir: Optional directory to scope the discovery to.  When
            ``None``, uses ``config.scope_root``.

    Returns:
        List of (source_path, change_level) tuples for files that would change.
    """
    source_files = discover_source_files(project_root, config, scope_dir=scope_dir)

    results: list[tuple[Path, ChangeLevel]] = []
    for path in source_files:
        content_hash, interface_hash = compute_hashes(path)
        change = check_change(path, project_root, content_hash, interface_hash)

        if change != ChangeLevel.UNCHANGED:
            results.append((path, change))

    return results


async def dry_run_files(
    file_paths: list[Path],
    project_root: Path,
    config: LexibraryConfig,
) -> list[tuple[Path, ChangeLevel]]:
    """Preview which of the given files would be processed, without LLM calls or writes.

    Runs change detection on each file and returns results for those that
    would change. No LLM calls are made and no files are written.

    Args:
        file_paths: List of source file paths to check.
        project_root: Absolute path to the project root.
        config: Project configuration.

    Returns:
        List of (source_path, change_level) tuples for files that would change.
    """
    ignore_matcher = create_ignore_matcher(config, project_root)
    binary_exts = set(config.crawl.binary_extensions)

    results: list[tuple[Path, ChangeLevel]] = []

    for source_path in file_paths:
        if not source_path.exists():
            continue

        # Skip .lexibrary contents
        try:
            source_path.resolve().relative_to((project_root / LEXIBRARY_DIR).resolve())
            continue
        except ValueError:
            pass

        # Skip binary files
        if _is_binary(source_path, binary_exts):
            continue

        # Skip ignored files
        if ignore_matcher.is_ignored(source_path):
            continue

        # Run change detection only
        content_hash, interface_hash = compute_hashes(source_path)
        change = check_change(source_path, project_root, content_hash, interface_hash)

        if change != ChangeLevel.UNCHANGED:
            results.append((source_path, change))

    return results


def _extract_llm_failure_reason(error_message: str | None, rel_path: str) -> str:
    """Extract a concise failure reason from an LLM error message.

    The raw error_message from ArchivistService is typically formatted as
    ``LLM error generating design file for <path>: <exception>``.  Strip the
    boilerplate prefix so the UI shows only the actionable exception text.
    Truncate to 200 characters to keep output readable.
    """
    if not error_message:
        return "LLM generation failed"

    prefix = f"LLM error generating design file for {rel_path}: "
    reason = error_message.removeprefix(prefix)

    max_len = 200
    if len(reason) > max_len:
        reason = reason[:max_len] + "…"
    return reason


# ---------------------------------------------------------------------------
# Size gate — prevents wasted LLM calls on oversized source files
# ---------------------------------------------------------------------------

# Files under this byte threshold skip tiktoken entirely (fast path).
SIZE_GATE_BYTES = 12_288  # 12 KB

# Source-token-to-max_tokens multiplier.  At the default
# archivist_max_tokens=5000 the gate triggers at ~25 000 source tokens
# (~100 KB of Python).
GATE_MULTIPLIER = 5

# Lazily initialised module-level TiktokenCounter.  The import and encoding
# download only happen when a file actually exceeds SIZE_GATE_BYTES.
_tiktoken: TiktokenCounter | None = None


def _get_tiktoken() -> TiktokenCounter:
    """Return (and cache) a module-level TiktokenCounter instance."""
    global _tiktoken  # noqa: PLW0603
    if _tiktoken is None:
        from lexibrary.tokenizer.tiktoken_counter import TiktokenCounter as _Cls

        _tiktoken = _Cls()
    return _tiktoken


def should_skip_llm(
    source_content: str,
    file_size_bytes: int,
    archivist_max_tokens: int,
) -> bool:
    """Return *True* when the source file is too large for the LLM.

    Two-tier gate:
    1. Files smaller than ``SIZE_GATE_BYTES`` pass immediately (no tokeniser
       cost).
    2. Larger files are tokenised with tiktoken; the call is skipped when
       ``source_tokens > archivist_max_tokens * GATE_MULTIPLIER``.
    """
    if file_size_bytes < SIZE_GATE_BYTES:
        return False
    source_tokens = _get_tiktoken().count(source_content)
    return source_tokens > archivist_max_tokens * GATE_MULTIPLIER


def _write_skeleton_fallback(
    source_path: Path,
    project_root: Path,
    *,
    summary_suffix: str = "",
) -> FileResult:
    """Write a skeleton design file as a fallback (size gate or truncation).

    Returns a ``FileResult`` with ``skeleton=True`` and the appropriate change
    level.  The caller is responsible for incrementing ``files_skeletons``.
    """
    design_path = mirror_path(project_root, source_path)
    design_path.parent.mkdir(parents=True, exist_ok=True)

    skeleton = generate_skeleton_design(
        source_path,
        project_root,
        updated_by="skeleton-fallback",
        summary_suffix=summary_suffix,
    )
    serialized = serialize_design_file(skeleton)
    atomic_write(design_path, serialized)
    logger.info("Wrote skeleton fallback: %s", design_path)

    aindex_refreshed = _refresh_parent_aindex(
        source_path, project_root, skeleton.frontmatter.description
    )
    return FileResult(
        change=ChangeLevel.NEW_FILE,
        aindex_refreshed=aindex_refreshed,
        skeleton=True,
    )


async def update_file(
    source_path: Path,
    project_root: Path,
    config: LexibraryConfig,
    archivist: ArchivistService,
    available_artifacts: list[str] | None = None,
    *,
    force: bool = False,
    unlimited: bool = False,
    symbol_context: SymbolGraphPromptContext | None = None,
) -> FileResult:
    """Generate or update the design file for a single source file.

    Args:
        source_path: Absolute path to the source file.
        project_root: Absolute path to the project root.
        config: Project configuration.
        archivist: LLM service for design file generation.
        available_artifacts: Optional list of artifact names for wikilink guidance.
        force: When True, delete the existing design file before change detection
            so the pipeline treats it as a new file.  The existing content is
            preserved and passed as ``existing_design`` context to the LLM.
        unlimited: When True, bypass the size gate and re-enrich SKELETON_ONLY
            files instead of skipping them.
        symbol_context: Optional pre-rendered symbol graph context for the
            file's enum/constant and call-path blocks. Forwarded to the LLM
            via ``DesignFileRequest``. When ``None``, no symbol enrichment
            is included in the prompt.

    Returns a ``FileResult`` containing the change level and tracking flags.
    """
    # 1. Scope check
    if not _is_within_scope(source_path, project_root, config.scope_root):
        return FileResult(change=ChangeLevel.UNCHANGED, skip_reason="out of scope")

    # 1a. Force: preserve existing design content, then delete so check_change
    #     sees a NEW_FILE.  The preserved content is later passed as
    #     existing_design context to the LLM.
    force_preserved_design: str | None = None
    if force:
        design_path_for_force = mirror_path(project_root, source_path)
        if design_path_for_force.exists():
            with contextlib.suppress(OSError):
                force_preserved_design = design_path_for_force.read_text(encoding="utf-8")
            with contextlib.suppress(OSError):
                design_path_for_force.unlink()
            logger.info("Force mode: deleted existing design file for %s", source_path.name)

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
                return FileResult(change=ChangeLevel.UNCHANGED, skip_reason="IWH blocked")
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
        return FileResult(change=change, skip_reason="unchanged")

    # 4b. SKELETON_ONLY -- skip in normal mode, proceed with unlimited
    if change == ChangeLevel.SKELETON_ONLY:
        if not unlimited:
            logger.debug(
                "Skipping skeleton-only file %s (use --unlimited to re-enrich)",
                source_path.name,
            )
            return FileResult(
                change=ChangeLevel.UNCHANGED, skip_reason="skeleton-only (use --unlimited)"
            )
        # unlimited=True: treat as needing generation (fall through to LLM path)
        logger.info(
            "Re-enriching skeleton-only file %s (unlimited mode)",
            source_path.name,
        )

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
        return FileResult(
            change=change,
            failed=True,
            failure_reason="unresolved merge conflict markers",
        )

    # 4c. Frontmatter guard — reject invalid updated_by without an LLM call.
    #     An unrecognised updated_by value means an external tool (not the
    #     archivist, agent, or Curator) last touched the design file.
    #     The Curator must review and correct the file before the archivist
    #     is allowed to regenerate it.
    if design_path.exists():
        bad_value = _check_invalid_updated_by(design_path, _VALID_UPDATED_BY)
        if bad_value is not None:
            logger.error(
                "Rejecting %s: design file has invalid updated_by=%r — review with Curator",
                source_path.name,
                bad_value,
            )
            return FileResult(
                change=change,
                failed=True,
                failure_reason=(
                    f"invalid updated_by '{bad_value}' in design file — "
                    "review and correct with the Curator before regenerating"
                ),
            )

    # 6. LLM generation: NEW_FILE, CONTENT_ONLY, CONTENT_CHANGED, INTERFACE_CHANGED,
    #    or SKELETON_ONLY (with unlimited=True)
    rel_path = str(source_path.relative_to(project_root))
    try:
        source_content = source_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        logger.error("Cannot read source file: %s", source_path)
        return FileResult(
            change=change,
            failed=True,
            failure_reason="cannot read source file",
        )

    # 6a. Size gate — skip LLM for oversized files (unless unlimited)
    if not unlimited:
        file_size_bytes = source_path.stat().st_size
        archivist_max_tokens = config.token_budgets.archivist_max_tokens
        if should_skip_llm(source_content, file_size_bytes, archivist_max_tokens):
            logger.info(
                "Size gate: %s is too large for LLM (%d bytes), writing skeleton fallback",
                source_path.name,
                file_size_bytes,
            )
            return _write_skeleton_fallback(
                source_path,
                project_root,
                summary_suffix=" (file too large for LLM — re-run with --unlimited)",
            )

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

    # Read existing design file content for update context.
    # When force was used, the file was deleted earlier — use the preserved copy.
    existing_design: str | None = force_preserved_design
    if existing_design is None and design_path.exists():
        with contextlib.suppress(OSError):
            existing_design = design_path.read_text(encoding="utf-8")

    request = DesignFileRequest(
        source_path=rel_path,
        source_content=source_content,
        interface_skeleton=skeleton_text,
        language=language,
        existing_design_file=existing_design,
        available_artifacts=available_artifacts,
        symbol_context=symbol_context,
    )

    try:
        result = await archivist.generate_design_file(request)
    except ArchivistTruncationError:
        logger.warning(
            "LLM output truncated for %s, writing skeleton fallback",
            rel_path,
        )
        return _write_skeleton_fallback(
            source_path,
            project_root,
            summary_suffix=" (LLM output truncated — re-run with --unlimited)",
        )

    if result.error or result.design_file_output is None:
        logger.error(
            "Failed to generate design file for %s: %s",
            rel_path,
            result.error_message or "unknown error",
        )
        reason = _extract_llm_failure_reason(result.error_message, rel_path)
        return FileResult(change=change, failed=True, failure_reason=reason)

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

    # Assign DS-NNN ID post-LLM-generation (LLM never produces IDs)
    designs_dir = project_root / LEXIBRARY_DIR / DESIGNS_DIR
    design_id = next_design_id(designs_dir)

    # 7b. Preserved sections passthrough — carry over non-standard sections
    #     (e.g. ## Insights, ## Notes) from the pre-regeneration design file.
    #     These sections are curator-authored and must not be lost on archivist
    #     regen.  We parse the existing on-disk file (before we overwrite it)
    #     rather than the force-preserved copy so the design_hash re-check
    #     above already guards against concurrent edits.
    preserved_sections: dict[str, str] = {}
    if design_path.exists():
        existing_parsed = parse_design_file(design_path)
        if existing_parsed is not None and existing_parsed.preserved_sections:
            preserved_sections = existing_parsed.preserved_sections
            logger.debug(
                "Carrying over %d preserved section(s) from %s: %s",
                len(preserved_sections),
                design_path.name,
                list(preserved_sections.keys()),
            )

    design_file = DesignFile(
        source_path=rel_path,
        frontmatter=DesignFileFrontmatter(
            description=description,
            id=design_id,
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
        preserved_sections=preserved_sections,
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

    # 11. Refresh the symbol-graph entry for this file so `lexi trace` and
    #     `lexi lookup` stay accurate in the same agent session. Wrapped in
    #     its own try/except so a symbol-graph failure can never fail the
    #     design-update path — the symbol graph is a secondary artifact and
    #     we prefer a stale graph over a failed update. The refresh is also
    #     a no-op when the symbol graph is disabled or the DB does not
    #     exist yet (first-run bootstrap is handled by the project
    #     maintainer running a full build).
    try:
        from lexibrary.symbolgraph.builder import refresh_file as _refresh_symbols  # noqa: PLC0415

        _refresh_symbols(project_root, config, source_path)
    except Exception:
        logger.exception(
            "Symbol graph refresh failed for %s — continuing with design update",
            source_path,
        )

    return FileResult(
        change=change,
        aindex_refreshed=aindex_refreshed,
        token_budget_exceeded=token_budget_exceeded,
    )


def _accumulate_stats(
    stats: UpdateStats,
    file_result: FileResult,
    source_path: Path | None = None,
) -> None:
    """Update *stats* in-place from a single file result."""
    change = file_result.change
    if file_result.failed:
        stats.files_failed += 1
        if source_path is not None:
            reason = file_result.failure_reason or "unknown error"
            stats.failed_files.append((str(source_path), reason))
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

    if file_result.skeleton:
        stats.files_skeletons += 1
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


def _run_deprecation_pass(
    project_root: Path,
    config: LexibraryConfig,
    stats: UpdateStats,
) -> None:
    """Detect orphaned designs, apply deprecation/unlinked status, and delete TTL-expired files.

    Also detects renames (via git and content-hash fallback) and migrates
    design files to follow their renamed source files.

    Mutates *stats* in-place with deprecation, TTL, and rename counts.
    """
    lexibrary_dir = project_root / LEXIBRARY_DIR

    # 1. Detect renames and migrate design files first (before orphan detection)
    try:
        renames = detect_renames(project_root)
        stats.renames_detected += len(renames)

        for mapping in renames:
            try:
                migrate_design_on_rename(project_root, mapping.old_path, mapping.new_path)
                stats.renames_migrated += 1
                logger.info(
                    "Migrated design file: %s -> %s",
                    mapping.old_path,
                    mapping.new_path,
                )
            except FileNotFoundError:
                logger.debug(
                    "No design file to migrate for rename: %s -> %s",
                    mapping.old_path,
                    mapping.new_path,
                )
            except Exception:
                logger.exception(
                    "Failed to migrate design file: %s -> %s",
                    mapping.old_path,
                    mapping.new_path,
                )
    except Exception as exc:
        logger.exception("Failed to detect renames")
        stats.error_summary.add("deprecation", exc)

    # 2. Detect orphaned designs and apply deprecation/unlinked status
    try:
        orphans = detect_orphaned_designs(project_root, lexibrary_dir)

        for orphan in orphans:
            try:
                if orphan.committed:
                    deprecate_design(orphan.design_path, "source_deleted")
                    stats.designs_deprecated += 1
                    logger.info("Deprecated design: %s", orphan.design_path.name)
                else:
                    mark_unlinked(orphan.design_path)
                    stats.designs_unlinked += 1
                    logger.info("Marked unlinked: %s", orphan.design_path.name)
            except Exception:
                logger.exception("Failed to update orphaned design: %s", orphan.design_path)
    except Exception as exc:
        logger.exception("Failed to detect orphaned designs")
        stats.error_summary.add("deprecation", exc)

    # 3. Hard-delete TTL-expired deprecated design files
    try:
        ttl_commits = config.deprecation.ttl_commits
        deleted = hard_delete_expired(project_root, lexibrary_dir, ttl_commits)
        stats.designs_deleted_ttl += len(deleted)
        for d in deleted:
            logger.info("TTL-expired design deleted: %s", d.name)
    except Exception as exc:
        logger.exception("Failed to delete TTL-expired designs")
        stats.error_summary.add("deprecation", exc)

    # 4. Hard-delete TTL-expired deprecated concepts
    try:
        from lexibrary.lifecycle.concept_deprecation import (  # noqa: PLC0415
            hard_delete_expired_concepts,
        )

        ttl_commits = config.deprecation.ttl_commits
        result = hard_delete_expired_concepts(project_root, lexibrary_dir, ttl_commits)
        stats.concepts_deleted_ttl += len(result.deleted)
        stats.concepts_skipped_referenced += len(result.skipped_referenced)
        stats.concept_comments_deleted += len(result.comments_deleted)
        for d in result.deleted:
            logger.info("TTL-expired concept deleted: %s", d.name)
        for concept_path, refs in result.skipped_referenced:
            logger.info(
                "Concept '%s' still referenced by %d artefact(s), skipping deletion",
                concept_path.name,
                len(refs),
            )
    except Exception as exc:
        logger.exception("Failed to delete TTL-expired concepts")
        stats.error_summary.add("deprecation", exc)

    # 5. Hard-delete TTL-expired deprecated conventions
    try:
        from lexibrary.lifecycle.convention_deprecation import (  # noqa: PLC0415
            hard_delete_expired_conventions,
        )

        ttl_commits = config.deprecation.ttl_commits
        conv_result = hard_delete_expired_conventions(project_root, lexibrary_dir, ttl_commits)
        stats.conventions_deleted_ttl += len(conv_result.deleted)
        stats.convention_comments_deleted += len(conv_result.comments_deleted)
        for d in conv_result.deleted:
            logger.info("TTL-expired convention deleted: %s", d.name)
    except Exception as exc:
        logger.exception("Failed to delete TTL-expired conventions")
        stats.error_summary.add("deprecation", exc)


async def _process_enrichment_queue(
    project_root: Path,
    config: LexibraryConfig,
    archivist: ArchivistService,
    stats: UpdateStats,
) -> None:
    """Process the enrichment queue: re-generate queued skeleton design files via LLM.

    Reads the queue, processes each entry through the normal ``update_file()``
    pipeline, and clears successfully processed entries from the queue.

    Mutates *stats* in-place with queue processing counts.
    """
    entries = read_queue(project_root)
    if not entries:
        return

    # Load available artifact names for wikilink guidance
    concepts_dir = project_root / LEXIBRARY_DIR / "concepts"
    conventions_dir = project_root / LEXIBRARY_DIR / "conventions"
    playbooks_dir = project_root / LEXIBRARY_DIR / "playbooks"

    artifact_names: list[str] = []
    if concepts_dir.exists():
        concept_index = ConceptIndex.load(concepts_dir)
        artifact_names.extend(concept_index.names())
    if conventions_dir.exists():
        conv_index = ConventionIndex(conventions_dir)
        conv_index.load()
        artifact_names.extend(conv_index.names())
    if playbooks_dir.exists():
        pb_index = PlaybookIndex(playbooks_dir)
        pb_index.load()
        artifact_names.extend(pb_index.names())

    available_artifacts = artifact_names or None

    processed_paths: list[Path] = []

    for entry in entries:
        source_path = project_root / entry.source_path
        if not source_path.exists():
            logger.debug("Queue entry source missing, skipping: %s", entry.source_path)
            # Still mark as processed to clear from queue
            processed_paths.append(entry.source_path)
            continue

        try:
            file_result = await update_file(
                source_path,
                project_root,
                config,
                archivist,
                available_artifacts=available_artifacts,
            )
            if file_result.failed:
                stats.queue_failed += 1
                logger.warning("Queue enrichment failed for %s", entry.source_path)
            else:
                stats.queue_processed += 1
                processed_paths.append(entry.source_path)
                logger.info(
                    "Queue enrichment complete for %s (change: %s)",
                    entry.source_path,
                    file_result.change.value,
                )
        except Exception as exc:
            stats.queue_failed += 1
            logger.exception("Unexpected error enriching queued file: %s", entry.source_path)
            stats.error_summary.add("queue", exc, path=str(entry.source_path))

    # Clear successfully processed entries from the queue
    if processed_paths:
        try:
            clear_queue(project_root, processed_paths)
        except Exception as exc:
            logger.exception("Failed to clear enrichment queue")
            stats.error_summary.add("queue", exc)

    # Report remaining queue size
    remaining = read_queue(project_root)
    stats.queue_remaining = len(remaining)


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
    *,
    force: bool = False,
    unlimited: bool = False,
) -> UpdateStats:
    """Process a specific list of source files through the pipeline.

    Unlike ``update_project()``, this does NOT discover files via rglob and
    does NOT generate ``TOPOLOGY.md``. It is designed for git-hook and
    ``--changed-only`` usage where the caller already knows which files changed.

    Files that are deleted, binary, ignored, or inside ``.lexibrary/`` are
    silently skipped for design file processing.  Deleted file paths are
    collected and forwarded to the link graph incremental update so that
    artifact rows and cascaded links are cleaned up.
    """
    stats = UpdateStats()
    ignore_matcher = create_ignore_matcher(config, project_root)
    binary_exts = set(config.crawl.binary_extensions)

    # Load available artifact names for wikilink guidance
    concepts_dir = project_root / LEXIBRARY_DIR / "concepts"
    conventions_dir = project_root / LEXIBRARY_DIR / "conventions"
    playbooks_dir = project_root / LEXIBRARY_DIR / "playbooks"

    artifact_names: list[str] = []
    if concepts_dir.exists():
        concept_index = ConceptIndex.load(concepts_dir)
        artifact_names.extend(concept_index.names())
    if conventions_dir.exists():
        conv_index = ConventionIndex(conventions_dir)
        conv_index.load()
        artifact_names.extend(conv_index.names())
    if playbooks_dir.exists():
        pb_index = PlaybookIndex(playbooks_dir)
        pb_index.load()
        artifact_names.extend(pb_index.names())

    available_artifacts = artifact_names or None

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
                available_artifacts=available_artifacts,
                force=force,
                unlimited=unlimited,
            )
        except Exception as exc:
            logger.exception("Unexpected error processing %s", source_path)
            stats.files_failed += 1
            stats.failed_files.append((str(source_path), str(exc)))
            stats.error_summary.add("archivist", exc, path=str(source_path))
            if progress_callback is not None:
                progress_callback(source_path, ChangeLevel.UNCHANGED, None)
            continue

        _accumulate_stats(stats, file_result, source_path=source_path)
        processed_paths.append(source_path)

        if progress_callback is not None:
            progress_callback(source_path, file_result.change, file_result.skip_reason)

    # Re-index directories containing changed files (plus ancestors up to
    # scope_root) so .aindex files stay fresh after hook-triggered updates.
    # Skipped when no files were actually created, updated, or failed (4.3).
    if _has_meaningful_changes(stats) and processed_paths:
        affected_dirs = sorted({p.parent for p in processed_paths})
        try:
            reindexed = reindex_directories(list(affected_dirs), project_root, config)
            stats.aindex_refreshed += reindexed
        except Exception as exc:
            logger.exception("Failed to re-index directories after update_files")
            stats.error_summary.add("archivist", exc)

    # Incremental link graph index update: pass both processed and deleted
    # paths so the builder can update changed artifacts and clean up deleted
    # ones via CASCADE.  Wrapped in try/except so index failures never block
    # the pipeline from returning design file stats (D3).
    all_changed = processed_paths + deleted_paths
    if all_changed:
        try:
            build_index(project_root, changed_paths=all_changed)
            stats.linkgraph_built = True
        except Exception as exc:
            logger.exception("Failed to run incremental link graph update")
            stats.linkgraph_error = "Link graph incremental update failed"
            stats.error_summary.add("linkgraph", exc)

    # Build the symbol graph incrementally — only rebuild files the caller
    # knows changed. The builder falls back to a full rebuild when the ratio
    # of changed files exceeds INCREMENTAL_THRESHOLD.
    try:
        from lexibrary.symbolgraph import build_symbol_graph  # noqa: PLC0415

        symbol_result = build_symbol_graph(project_root, config, changed_paths=file_paths)
        stats.symbolgraph_built = True
        stats.symbolgraph_symbol_count = symbol_result.symbol_count
        stats.symbolgraph_call_count = symbol_result.call_count
    except Exception as exc:
        logger.exception("Failed to build symbol graph")
        stats.symbolgraph_error = "Symbol graph build failed"
        stats.error_summary.add("symbolgraph", exc)

    return stats


async def update_directory(
    directory: Path,
    project_root: Path,
    config: LexibraryConfig,
    archivist: ArchivistService,
    progress_callback: ProgressCallback | None = None,
    *,
    force: bool = False,
    unlimited: bool = False,
) -> UpdateStats:
    """Update design files for source files within a directory subtree.

    Discovers files within *directory*, processes each sequentially, then
    regenerates ``TOPOLOGY.md``, re-indexes affected directories, and
    rebuilds the link graph.  Skips project-wide passes (deprecation
    lifecycle, enrichment queue) that only apply to full-project updates.

    When *force* is True, every file is treated as if it is new regardless
    of its current hash, so stale link-graph entries for deleted artifacts
    get pruned on the next full rebuild.
    """
    stats = UpdateStats()

    # Load available artifact names for wikilink guidance
    concepts_dir = project_root / LEXIBRARY_DIR / "concepts"
    conventions_dir = project_root / LEXIBRARY_DIR / "conventions"
    playbooks_dir = project_root / LEXIBRARY_DIR / "playbooks"

    artifact_names: list[str] = []
    if concepts_dir.exists():
        concept_index = ConceptIndex.load(concepts_dir)
        artifact_names.extend(concept_index.names())
    if conventions_dir.exists():
        conv_index = ConventionIndex(conventions_dir)
        conv_index.load()
        artifact_names.extend(conv_index.names())
    if playbooks_dir.exists():
        pb_index = PlaybookIndex(playbooks_dir)
        pb_index.load()
        artifact_names.extend(pb_index.names())

    available_artifacts = artifact_names or None

    source_files = discover_source_files(project_root, config, scope_dir=directory)

    logger.info(
        "Discovered %d source files in %s for processing",
        len(source_files),
        directory,
    )

    changed_file_paths: list[Path] = []

    for source_path in source_files:
        stats.files_scanned += 1

        try:
            file_result = await update_file(
                source_path,
                project_root,
                config,
                archivist,
                available_artifacts=available_artifacts,
                force=force,
                unlimited=unlimited,
            )
        except Exception as exc:
            logger.exception("Unexpected error processing %s", source_path)
            stats.files_failed += 1
            stats.failed_files.append((str(source_path), str(exc)))
            stats.error_summary.add("archivist", exc, path=str(source_path))
            changed_file_paths.append(source_path)
            if progress_callback is not None:
                progress_callback(source_path, ChangeLevel.UNCHANGED, None)
            continue

        _accumulate_stats(stats, file_result, source_path=source_path)

        if file_result.change not in (ChangeLevel.UNCHANGED, ChangeLevel.AGENT_UPDATED):
            changed_file_paths.append(source_path)

        if progress_callback is not None:
            progress_callback(source_path, file_result.change, file_result.skip_reason)

    if _has_meaningful_changes(stats) and changed_file_paths:
        affected_dirs = sorted({p.parent for p in changed_file_paths})
        try:
            reindexed = reindex_directories(list(affected_dirs), project_root, config)
            stats.aindex_refreshed += reindexed
        except Exception as exc:
            logger.exception("Failed to re-index directories after update_directory")
            stats.error_summary.add("archivist", exc)

    try:
        generate_raw_topology(project_root)
        logger.info("Raw topology written to .lexibrary/tmp/raw-topology.md")
        logger.info("Run /topology-builder to generate TOPOLOGY.md")
    except Exception as exc:
        logger.exception("Failed to generate raw topology")
        stats.topology_failed = True
        stats.error_summary.add("archivist", exc, path="tmp/raw-topology.md")

    try:
        build_index(project_root)
        stats.linkgraph_built = True
    except Exception as exc:
        logger.exception("Failed to build link graph index")
        stats.linkgraph_error = "Link graph full build failed"
        stats.error_summary.add("linkgraph", exc)

    # Build the symbol graph incrementally — only rebuild files that
    # changed during this directory update. Falls back to full rebuild
    # when the changed ratio exceeds INCREMENTAL_THRESHOLD.
    try:
        from lexibrary.symbolgraph import build_symbol_graph  # noqa: PLC0415

        symbol_result = build_symbol_graph(project_root, config, changed_paths=changed_file_paths)
        stats.symbolgraph_built = True
        stats.symbolgraph_symbol_count = symbol_result.symbol_count
        stats.symbolgraph_call_count = symbol_result.call_count
    except Exception as exc:
        logger.exception("Failed to build symbol graph")
        stats.symbolgraph_error = "Symbol graph build failed"
        stats.error_summary.add("symbolgraph", exc)

    return stats


@contextlib.contextmanager
def _open_symbol_service_for_enrichment(
    project_root: Path,
    config: LexibraryConfig,
    *,
    enabled: bool,
) -> Iterator[SymbolQueryService | None]:
    """Yield an open :class:`SymbolQueryService` or ``None`` as a context manager.

    Wraps :class:`SymbolQueryService` so ``update_project`` can always
    open the enrichment service with ``with`` syntax even when the
    underlying symbol graph is disabled, unbuilt, or fails to open.
    When enrichment is possible the helper enters the service via its
    own ``__enter__`` / ``__exit__`` protocol and forwards the entered
    value to the caller; when enrichment is not possible it yields
    ``None`` without touching the class.

    Using the service's native context-manager protocol (rather than
    calling :meth:`~SymbolQueryService.open` / :meth:`~SymbolQueryService.close`
    directly) means tests can spy on ``SymbolQueryService.__enter__`` to
    assert the pipeline opens the service exactly once per
    ``update_project`` invocation regardless of how many files are in
    scope.

    Parameters
    ----------
    project_root:
        Absolute path to the project root.
    config:
        Project config. ``config.symbols.enabled`` must be true for the
        helper to attempt an open.
    enabled:
        Caller-supplied gate used by ``update_project`` to skip the
        open when the symbol graph build itself failed earlier in the
        run. Orthogonal to ``config.symbols.enabled``: both must be
        true to get a live service.
    """
    if not config.symbols.enabled or not enabled:
        yield None
        return

    from lexibrary.services.symbols import SymbolQueryService  # noqa: PLC0415

    svc_instance = SymbolQueryService(project_root)
    try:
        entered = svc_instance.__enter__()
    except Exception:
        logger.exception(
            "Failed to open SymbolQueryService for prompt enrichment — "
            "continuing without symbol-graph context"
        )
        yield None
        return

    try:
        yield entered
    finally:
        svc_instance.__exit__(None, None, None)


async def update_project(
    project_root: Path,
    config: LexibraryConfig,
    archivist: ArchivistService,
    progress_callback: ProgressCallback | None = None,
    *,
    force: bool = False,
    unlimited: bool = False,
) -> UpdateStats:
    """Update all design files for the project.

    Discovers source files within scope_root, filters ignored and binary
    files, processes each sequentially, then returns accumulated stats.

    When *force* is True, every file is treated as if it is new regardless
    of its current hash.  This causes a full rebuild of all design files and
    ensures the link-graph index is rebuilt from scratch, pruning any stale
    entries left behind by deleted concept or convention files.
    """
    stats = UpdateStats()

    # Load available artifact names for wikilink guidance
    concepts_dir = project_root / LEXIBRARY_DIR / "concepts"
    conventions_dir = project_root / LEXIBRARY_DIR / "conventions"
    playbooks_dir = project_root / LEXIBRARY_DIR / "playbooks"

    artifact_names: list[str] = []
    if concepts_dir.exists():
        concept_index = ConceptIndex.load(concepts_dir)
        artifact_names.extend(concept_index.names())
    if conventions_dir.exists():
        conv_index = ConventionIndex(conventions_dir)
        conv_index.load()
        artifact_names.extend(conv_index.names())
    if playbooks_dir.exists():
        pb_index = PlaybookIndex(playbooks_dir)
        pb_index.load()
        artifact_names.extend(pb_index.names())

    available_artifacts = artifact_names or None

    # Discover all source files within scope
    source_files = discover_source_files(project_root, config)

    logger.info("Discovered %d source files for processing", len(source_files))

    # Step 3: Build the symbol graph BEFORE the design-file generation loop
    # so the archivist enrichment helper can read fresh enum and call-path
    # context for each file it regenerates. This is the group-5 reorder from
    # the symbol-graph-5 plan (see tests/test_archivist/test_pipeline_order.py
    # for the full audit + interpretation). Only update_project() does this
    # reorder — update_files() and update_directory() keep their late
    # symbol-graph build because they are incremental/targeted entry points
    # rather than full-project refreshes.
    #
    # changed_paths is intentionally omitted (full build) because this
    # pre-loop build must produce a complete graph for design-file enrichment.
    # update_files() and update_directory() pass changed_paths for incremental
    # rebuilds since they run after their processing loops.
    try:
        from lexibrary.symbolgraph import build_symbol_graph  # noqa: PLC0415

        symbol_result = build_symbol_graph(project_root, config)
        stats.symbolgraph_built = True
        stats.symbolgraph_symbol_count = symbol_result.symbol_count
        stats.symbolgraph_call_count = symbol_result.call_count
    except Exception as exc:
        logger.exception("Failed to build symbol graph")
        stats.symbolgraph_error = "Symbol graph build failed"
        stats.error_summary.add("symbolgraph", exc)

    # Track which files were actually changed (for targeted re-indexing)
    changed_file_paths: list[Path] = []

    # Step 4: Design-file generation loop. Open a single SymbolQueryService
    # around the loop so the enrichment helper can walk the freshly-built
    # symbol graph without re-opening the underlying sqlite3 connection per
    # file. When symbols are disabled or the graph build failed we pass
    # symbol_context=None to every update_file via the ``with
    # _open_symbol_service_for_enrichment(...) as svc`` contract, whose
    # value is either a live service (when enrichment is possible) or
    # ``None`` (when it is not).
    #
    # SQLite concurrency note: update_project processes files with a plain
    # ``for`` loop that awaits sequentially (no asyncio.gather / TaskGroup),
    # so the single connection the service holds is only touched by one
    # coroutine at a time. If this loop is ever converted to concurrent
    # execution the render_symbol_graph_context() calls must be wrapped in
    # asyncio.to_thread.
    from lexibrary.archivist.symbol_graph_context import (  # noqa: PLC0415
        render_symbol_graph_context,
    )

    with _open_symbol_service_for_enrichment(
        project_root, config, enabled=stats.symbolgraph_built
    ) as symbol_svc:
        # Process each file sequentially
        for source_path in source_files:
            stats.files_scanned += 1

            symbol_context: SymbolGraphPromptContext | None = None
            if symbol_svc is not None:
                try:
                    symbol_context = render_symbol_graph_context(
                        symbol_svc, project_root, source_path, config
                    )
                except Exception:
                    logger.exception(
                        "Failed to render symbol graph context for %s — "
                        "continuing without symbol-graph context",
                        source_path,
                    )
                    symbol_context = None

            try:
                file_result = await update_file(
                    source_path,
                    project_root,
                    config,
                    archivist,
                    available_artifacts=available_artifacts,
                    force=force,
                    unlimited=unlimited,
                    symbol_context=symbol_context,
                )
            except Exception as exc:
                logger.exception("Unexpected error processing %s", source_path)
                stats.files_failed += 1
                stats.failed_files.append((str(source_path), str(exc)))
                stats.error_summary.add("archivist", exc, path=str(source_path))
                changed_file_paths.append(source_path)
                if progress_callback is not None:
                    progress_callback(source_path, ChangeLevel.UNCHANGED, None)
                continue

            _accumulate_stats(stats, file_result, source_path=source_path)

            # Track files that were actually created, updated, or failed
            if file_result.change not in (ChangeLevel.UNCHANGED, ChangeLevel.AGENT_UPDATED):
                changed_file_paths.append(source_path)

            if progress_callback is not None:
                progress_callback(source_path, file_result.change, file_result.skip_reason)

    # Step 5: Re-index directories containing changed files (D-2, D-3).
    # Skipped when no files were actually created, updated, or failed (4.3).
    # Must run before topology generation so raw-topology.md reflects fresh .aindex data.
    if _has_meaningful_changes(stats) and changed_file_paths:
        affected_dirs = sorted({p.parent for p in changed_file_paths})
        try:
            reindexed = reindex_directories(list(affected_dirs), project_root, config)
            stats.aindex_refreshed += reindexed
        except Exception as exc:
            logger.exception("Failed to re-index directories after update_project")
            stats.error_summary.add("archivist", exc)

    # Step 6: Generate raw topology after re-indexing so it reads fresh .aindex data.
    try:
        generate_raw_topology(project_root)
        logger.info("Raw topology written to .lexibrary/tmp/raw-topology.md")
        logger.info("Run /topology-builder to generate TOPOLOGY.md")
    except Exception as exc:
        logger.exception("Failed to generate raw topology")
        stats.topology_failed = True
        stats.error_summary.add("archivist", exc, path="tmp/raw-topology.md")

    # Step 7: Deprecation lifecycle post-pass — detect orphans, apply
    # deprecation/unlinked status, handle renames, and delete TTL-expired files.
    _run_deprecation_pass(project_root, config, stats)

    # Step 8: Process enrichment queue — re-generate queued skeletons via LLM.
    await _process_enrichment_queue(project_root, config, archivist, stats)

    # Step 9: Build the link graph index (full rebuild after all artifacts are up to date).
    # Stays at this late position even after the group-5 reorder: it must see the
    # freshly-written design files from the loop above so outbound wikilinks are
    # included in the rebuilt index. Moving it earlier would cause the link graph
    # to reflect one-run-stale design-file state.
    try:
        build_index(project_root)
        stats.linkgraph_built = True
    except Exception as exc:
        logger.exception("Failed to build link graph index")
        stats.linkgraph_error = "Link graph full build failed"
        stats.error_summary.add("linkgraph", exc)

    return stats
