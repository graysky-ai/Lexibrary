"""Procedural topology generation from .aindex billboard summaries.

Replaces the LLM-generated START_HERE.md with a deterministic
``TOPOLOGY.md`` built directly from ``.aindex`` data.  The adaptive-depth
algorithm shows full trees for small projects and filters large projects
to keep the output concise.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from lexibrary.artifacts.aindex import AIndexFile
from lexibrary.artifacts.aindex_parser import parse_aindex
from lexibrary.utils.atomic import atomic_write
from lexibrary.utils.paths import LEXIBRARY_DIR

logger = logging.getLogger(__name__)

# Adaptive depth thresholds (spec: procedural-topology/spec.md)
_SMALL_THRESHOLD = 10  # <= 10 directories: show full tree
_MEDIUM_THRESHOLD = 40  # 11-40 directories: depth <= 2 + hotspots
_HOTSPOT_CHILD_THRESHOLD = 5  # directories with > 5 child entries are hotspots


@dataclass
class _DirInfo:
    """Parsed directory information from a single .aindex file."""

    rel_path: str
    billboard: str
    child_entry_count: int
    child_dir_names: list[str] = field(default_factory=list)


def _collect_aindex_data(project_root: Path) -> list[_DirInfo]:
    """Parse all .aindex files under .lexibrary/ and return directory info.

    Returns a sorted list of ``_DirInfo`` instances, one per ``.aindex``
    file found.  The list is sorted by ``rel_path`` for deterministic
    output.
    """
    lexibrary_root = project_root / LEXIBRARY_DIR
    if not lexibrary_root.is_dir():
        return []

    infos: list[_DirInfo] = []
    for aindex_path in sorted(lexibrary_root.rglob(".aindex")):
        parsed: AIndexFile | None = parse_aindex(aindex_path)
        if parsed is None:
            continue

        child_dir_names = [entry.name for entry in parsed.entries if entry.entry_type == "dir"]
        infos.append(
            _DirInfo(
                rel_path=parsed.directory_path,
                billboard=parsed.billboard,
                child_entry_count=len(parsed.entries),
                child_dir_names=child_dir_names,
            )
        )

    return sorted(infos, key=lambda d: d.rel_path)


def _compute_depth(rel_path: str, project_name: str) -> int:
    """Compute the nesting depth of a directory relative to the project root.

    The project root itself (matching ``project_name``) is depth 0.
    ``src`` under it is depth 1, ``src/auth`` is depth 2, etc.
    """
    if rel_path == project_name or rel_path == ".":
        return 0
    # Strip the project name prefix if present
    if rel_path.startswith(project_name + "/"):
        remainder = rel_path[len(project_name) + 1 :]
    else:
        remainder = rel_path
    if not remainder:
        return 0
    return remainder.count("/") + 1


def _build_procedural_topology(project_root: Path) -> str:
    """Build an adaptive-depth annotated directory tree from .aindex data.

    Reads all ``.aindex`` files under ``.lexibrary/``, extracts directory
    paths and billboard summaries, and renders an indented tree.  The
    display depth adapts based on project scale:

    - Small (<=10 dirs): full tree, no filtering
    - Medium (11-40 dirs): depth <=2, plus hotspots (>5 child entries)
    - Large (41+ dirs): depth <=1, plus hotspots

    Args:
        project_root: Absolute path to the project root.

    Returns:
        String containing the rendered tree, or a placeholder message
        if no data is available.
    """
    lexibrary_root = project_root / LEXIBRARY_DIR
    if not lexibrary_root.is_dir():
        return "(no .lexibrary directory found)"

    infos = _collect_aindex_data(project_root)
    if not infos:
        return "(no .aindex files found -- run 'lexi update' first)"

    project_name = project_root.name
    dir_count = len(infos)

    # Build lookup maps
    info_by_path: dict[str, _DirInfo] = {info.rel_path: info for info in infos}

    # Determine adaptive depth parameters
    if dir_count <= _SMALL_THRESHOLD:
        display_depth: int | None = None  # no limit
        hotspot_threshold: int | None = None
    elif dir_count <= _MEDIUM_THRESHOLD:
        display_depth = 2
        hotspot_threshold = _HOTSPOT_CHILD_THRESHOLD
    else:
        display_depth = 1
        hotspot_threshold = _HOTSPOT_CHILD_THRESHOLD

    # Identify hotspot paths (directories exceeding the hotspot threshold)
    hotspot_paths: set[str] = set()
    if hotspot_threshold is not None:
        for info in infos:
            if info.child_entry_count > hotspot_threshold:
                hotspot_paths.add(info.rel_path)

    def _should_show(rel_path: str) -> bool:
        """Determine whether a directory should be included in the tree."""
        depth = _compute_depth(rel_path, project_name)
        if display_depth is None:
            return True
        if depth <= display_depth:
            return True
        return rel_path in hotspot_paths

    def _count_hidden_children(info: _DirInfo) -> int:
        """Count child directories that exist in .aindex data but are filtered out."""
        hidden = 0
        for child_name in info.child_dir_names:
            if info.rel_path == project_name or info.rel_path == ".":
                child_path = f"{project_name}/{child_name}"
            else:
                child_path = f"{info.rel_path}/{child_name}"
            if child_path in info_by_path and not _should_show(child_path):
                hidden += 1
        return hidden

    # Render the tree
    lines: list[str] = []
    for info in infos:
        if not _should_show(info.rel_path):
            continue

        depth = _compute_depth(info.rel_path, project_name)
        indent = "  " * depth

        # Format: dir_name/ -- billboard text
        if info.rel_path == project_name or info.rel_path == ".":
            dir_display = f"{project_name}/"
        else:
            # Use just the last component for display
            dir_display = f"{info.rel_path.rsplit('/', 1)[-1]}/"

        annotation = f" -- {info.billboard}" if info.billboard else ""

        hidden = _count_hidden_children(info)
        suffix = f"  ({hidden} subdirs)" if hidden > 0 else ""

        lines.append(f"{indent}{dir_display}{annotation}{suffix}")

    return "\n".join(lines)


def generate_topology(project_root: Path) -> Path:
    """Generate ``.lexibrary/TOPOLOGY.md`` from .aindex billboard summaries.

    Builds an adaptive-depth annotated directory tree and wraps it in a
    markdown document.  Uses ``atomic_write()`` for safe file replacement.

    Args:
        project_root: Absolute path to the project root.

    Returns:
        Path to the written ``TOPOLOGY.md`` file.
    """
    tree = _build_procedural_topology(project_root)

    content_lines = [
        "# Project Topology",
        "",
        "```",
        tree,
        "```",
        "",
    ]
    content = "\n".join(content_lines)

    output_path = project_root / LEXIBRARY_DIR / "TOPOLOGY.md"
    atomic_write(output_path, content)
    logger.info("Wrote TOPOLOGY.md (%d chars)", len(content))

    return output_path
