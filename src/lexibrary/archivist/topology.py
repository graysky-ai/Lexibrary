"""Procedural topology generation from .aindex billboard summaries.

Builds a deterministic ``TOPOLOGY.md`` directly from ``.aindex`` data.
The adaptive-depth algorithm shows full trees for small projects and
filters large projects to keep the output concise.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from lexibrary.artifacts.aindex import AIndexEntry, AIndexFile
from lexibrary.artifacts.aindex_parser import parse_aindex
from lexibrary.utils.atomic import atomic_write
from lexibrary.utils.paths import LEXIBRARY_DIR

logger = logging.getLogger(__name__)

# Adaptive depth thresholds (spec: procedural-topology/spec.md)
_SMALL_THRESHOLD = 10  # <= 10 directories: show full tree
_MEDIUM_THRESHOLD = 40  # 11-40 directories: depth <= 2 + hotspots
_HOTSPOT_CHILD_THRESHOLD = 5  # directories with > 5 child entries are hotspots

# Landmark detection keywords (spec: procedural-topology/spec.md)
_ENTRY_POINT_KEYWORDS = ("entry point", "entry-point", "main", "application entry")
_CONFIG_KEYWORDS = ("configuration", "config", "settings")
_CONFIG_FILENAMES = frozenset({
    "pyproject.toml",
    "package.json",
    "Cargo.toml",
    "go.mod",
    "setup.cfg",
})
_TEST_DIR_NAMES = frozenset({"tests", "test", "__tests__", "spec"})


@dataclass
class _DirInfo:
    """Parsed directory information from a single .aindex file."""

    rel_path: str
    billboard: str
    child_entry_count: int
    child_dir_names: list[str] = field(default_factory=list)
    key_entries: list[AIndexEntry] = field(default_factory=list)


def _is_landmark_entry(entry: AIndexEntry) -> bool:
    """Return True if *entry* matches any landmark keyword pattern.

    Landmark types:
    - **Entry point**: description contains an entry-point keyword.
    - **Config**: description contains a config keyword, OR filename is a
      known config file.
    """
    desc_lower = entry.description.lower()

    # Entry-point keywords
    if any(kw in desc_lower for kw in _ENTRY_POINT_KEYWORDS):
        return True

    # Config keywords
    if any(kw in desc_lower for kw in _CONFIG_KEYWORDS):
        return True

    # Config filenames
    return entry.name in _CONFIG_FILENAMES


def _collect_aindex_data(project_root: Path) -> list[_DirInfo]:
    """Parse all .aindex files under .lexibrary/ and return directory info.

    Returns a sorted list of ``_DirInfo`` instances, one per ``.aindex``
    file found.  The list is sorted by ``rel_path`` for deterministic
    output.

    Entries whose descriptions match landmark keywords are collected into
    ``_DirInfo.key_entries`` for downstream use by ``_generate_header()``
    and importance-weighted depth.
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

        # Collect landmark entries from file entries
        key_entries = [
            entry for entry in parsed.entries if _is_landmark_entry(entry)
        ]

        infos.append(
            _DirInfo(
                rel_path=parsed.directory_path,
                billboard=parsed.billboard,
                child_entry_count=len(parsed.entries),
                child_dir_names=child_dir_names,
                key_entries=key_entries,
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


# Extension-to-language mapping for dominant language detection
_EXT_LANGUAGE: dict[str, str] = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".jsx": "JavaScript",
    ".rs": "Rust",
    ".go": "Go",
    ".java": "Java",
    ".rb": "Ruby",
    ".c": "C",
    ".cpp": "C++",
    ".cs": "C#",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".php": "PHP",
    ".scala": "Scala",
    ".hs": "Haskell",
    ".ex": "Elixir",
    ".exs": "Elixir",
    ".lua": "Lua",
    ".r": "R",
    ".R": "R",
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
}


def _generate_header(infos: list[_DirInfo], project_root: Path) -> str:
    """Emit a 1-2 line project header from landmark data and dominant language.

    The header summarises the project for agent navigation:

    - **Line 1**: ``**ProjectName** -- Language (dominant_source_dir/)``
    - **Line 2** (optional): landmark labels such as
      ``Entry: path | Tests: path | Config: filename``

    Returns an empty string when *infos* is empty (no ``.aindex`` data).
    """
    if not infos:
        return ""

    project_name = project_root.name

    # Find the dominant source directory (first depth-1 dir with a source-like name)
    dominant_source_dir = ""
    source_dir_candidates = ("src", "lib", "app", "pkg", "cmd")
    for info in infos:
        depth = _compute_depth(info.rel_path, project_name)
        if depth == 1:
            dir_name = info.rel_path.rsplit("/", 1)[-1]
            if dir_name in source_dir_candidates:
                dominant_source_dir = dir_name
                break

    # Count file extensions from key_entries to determine dominant language
    ext_counts: Counter[str] = Counter()
    for info in infos:
        for entry in info.key_entries:
            if entry.entry_type == "file":
                suffix = Path(entry.name).suffix
                if suffix in _EXT_LANGUAGE:
                    ext_counts[suffix] += 1

    if ext_counts:
        dominant_ext = ext_counts.most_common(1)[0][0]
        language = _EXT_LANGUAGE[dominant_ext]
    else:
        language = "Mixed"

    # Build line 1
    if dominant_source_dir:
        line1 = f"**{project_name}** \u2014 {language} ({dominant_source_dir}/)"
    else:
        line1 = f"**{project_name}** \u2014 {language}"

    # Detect landmarks for line 2
    landmarks: list[str] = []

    # Entry points: first entry whose description matches entry-point keywords
    for info in infos:
        for entry in info.key_entries:
            desc_lower = entry.description.lower()
            if any(kw in desc_lower for kw in _ENTRY_POINT_KEYWORDS):
                if info.rel_path == project_name or info.rel_path == ".":
                    entry_path = entry.name
                else:
                    rel = info.rel_path
                    if rel.startswith(project_name + "/"):
                        rel = rel[len(project_name) + 1 :]
                    entry_path = f"{rel}/{entry.name}"
                landmarks.append(f"Entry: {entry_path}")
                break
        if any(lm.startswith("Entry:") for lm in landmarks):
            break

    # Test roots: directories whose name matches test dir patterns
    for info in infos:
        dir_name = info.rel_path.rsplit("/", 1)[-1]
        if dir_name in _TEST_DIR_NAMES:
            rel = info.rel_path
            if rel.startswith(project_name + "/"):
                rel = rel[len(project_name) + 1 :]
            landmarks.append(f"Tests: {rel}/")
            break

    # Config files: entries matching config filenames or config-related descriptions
    for info in infos:
        for entry in info.key_entries:
            if entry.name in _CONFIG_FILENAMES:
                landmarks.append(f"Config: {entry.name}")
                break
            desc_lower = entry.description.lower()
            if any(kw in desc_lower for kw in _CONFIG_KEYWORDS):
                landmarks.append(f"Config: {entry.name}")
                break
        if any(lm.startswith("Config:") for lm in landmarks):
            break

    # Assemble header
    if landmarks:
        line2 = " | ".join(landmarks)
        return f"{line1}\n{line2}"
    return line1


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

    # Compute important_paths: ancestor paths leading to detected landmarks.
    # A directory is a landmark if it has key_entries or its name matches
    # a test directory pattern.  All ancestors of landmark directories get
    # a +1 depth bonus in _should_show().
    important_paths: set[str] = set()
    for info in infos:
        is_landmark = bool(info.key_entries)
        if not is_landmark:
            dir_name = info.rel_path.rsplit("/", 1)[-1]
            is_landmark = dir_name in _TEST_DIR_NAMES
        if is_landmark:
            # Walk up the path, adding each ancestor
            parts = info.rel_path.split("/")
            for i in range(1, len(parts)):
                ancestor = "/".join(parts[:i])
                important_paths.add(ancestor)
            # Also add the landmark directory itself
            important_paths.add(info.rel_path)

    def _should_show(rel_path: str) -> bool:
        """Determine whether a directory should be included in the tree."""
        depth = _compute_depth(rel_path, project_name)
        if display_depth is None:
            return True
        effective_depth = display_depth
        if rel_path in important_paths:
            effective_depth += 1
        if depth <= effective_depth:
            return True
        return rel_path in hotspot_paths

    def _get_hidden_children_info(
        info: _DirInfo,
    ) -> tuple[int, list[str]]:
        """Return count and sorted names of hidden child directories.

        A child directory is "hidden" if it exists in ``.aindex`` data
        but is filtered out by the adaptive depth algorithm.

        Returns:
            Tuple of (hidden_count, sorted_names) where *sorted_names*
            is an alphabetically-sorted list of the hidden directory names.
        """
        hidden_names: list[str] = []
        for child_name in info.child_dir_names:
            if info.rel_path == project_name or info.rel_path == ".":
                child_path = f"{project_name}/{child_name}"
            else:
                child_path = f"{info.rel_path}/{child_name}"
            if child_path in info_by_path and not _should_show(child_path):
                hidden_names.append(child_name)
        hidden_names.sort()
        return len(hidden_names), hidden_names

    # Render the tree
    lines: list[str] = []
    seen_depth1 = False
    for info in infos:
        if not _should_show(info.rel_path):
            continue

        depth = _compute_depth(info.rel_path, project_name)

        # Insert blank line between depth-1 sections
        if depth == 1:
            if seen_depth1:
                lines.append("")
            seen_depth1 = True

        indent = "  " * depth

        # Format: dir_name/ -- billboard text
        if info.rel_path == project_name or info.rel_path == ".":
            dir_display = f"{project_name}/"
        else:
            # Use just the last component for display
            dir_display = f"{info.rel_path.rsplit('/', 1)[-1]}/"

        annotation = f" -- {info.billboard}" if info.billboard else ""

        hidden_count, hidden_names = _get_hidden_children_info(info)
        if hidden_count > 0:
            if len(hidden_names) > 4:
                names_str = ", ".join(hidden_names[:4]) + ", ..."
            else:
                names_str = ", ".join(hidden_names)
            suffix = f"  ({hidden_count} subdirs: {names_str}) >"
        else:
            suffix = ""

        lines.append(f"{indent}{dir_display}{annotation}{suffix}")

    return "\n".join(lines)


def generate_topology(project_root: Path) -> Path:
    """Generate ``.lexibrary/TOPOLOGY.md`` from .aindex billboard summaries.

    Builds an adaptive-depth annotated directory tree and wraps it in a
    markdown document.  Uses ``atomic_write()`` for safe file replacement.

    When ``.aindex`` data is available, a project header (name, language,
    landmarks) is prepended before the code-fenced tree.  The header is
    omitted when no ``.aindex`` data exists.

    Args:
        project_root: Absolute path to the project root.

    Returns:
        Path to the written ``TOPOLOGY.md`` file.
    """
    tree = _build_procedural_topology(project_root)

    # Generate header from .aindex data (empty string when no data)
    infos = _collect_aindex_data(project_root)
    header = _generate_header(infos, project_root)

    content_lines = ["# Project Topology", ""]
    if header:
        content_lines.append(header)
        content_lines.append("")
    content_lines.extend(["```", tree, "```", ""])
    content = "\n".join(content_lines)

    output_path = project_root / LEXIBRARY_DIR / "TOPOLOGY.md"
    atomic_write(output_path, content)
    logger.info("Wrote TOPOLOGY.md (%d chars)", len(content))

    return output_path
