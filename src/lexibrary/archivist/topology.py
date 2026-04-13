"""Procedural topology generation from .aindex billboard summaries.

Builds a deterministic ``TOPOLOGY.md`` directly from ``.aindex`` data.
The adaptive-depth algorithm shows full trees for small projects and
filters large projects to keep the output concise.
"""

from __future__ import annotations

import fnmatch
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from lexibrary.artifacts.aindex import AIndexEntry, AIndexFile
from lexibrary.artifacts.aindex_parser import parse_aindex
from lexibrary.indexer.generator import is_structural_description
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
_CONFIG_FILENAMES = frozenset(
    {
        "pyproject.toml",
        "package.json",
        "Cargo.toml",
        "go.mod",
        "setup.cfg",
    }
)
_TEST_DIR_NAMES = frozenset({"tests", "test", "__tests__", "spec"})

# Entry-point landmark selection (C1)
_PREFERRED_EP_DIRS: frozenset[str] = frozenset({"cli", "app", "cmd", "main", "bin"})
_MINIMAL_EP_DISQUALIFIER: re.Pattern[str] = re.compile(
    r"\bminimal\b.*\bentry.?points?\b", re.IGNORECASE
)

# Source directory candidates for dominant-source-dir detection
_SOURCE_DIR_CANDIDATES: tuple[str, ...] = ("src", "lib", "app", "pkg", "cmd")

# Canonical section names for raw topology output (spec: topology-section-markers)
SECTION_NAMES: tuple[str, ...] = (
    "header",
    "entry-point-candidates",
    "tree",
    "source-modules",
    "test-layout",
    "config",
    "stats",
)

# Per-root section names (subset of SECTION_NAMES that are scoped to a single
# scope root). The ``config`` and ``stats`` sections are project-wide and are
# emitted once at the document level, outside any per-root wrapper.
PER_ROOT_SECTION_NAMES: tuple[str, ...] = (
    "header",
    "entry-point-candidates",
    "tree",
    "source-modules",
    "test-layout",
)


def _section_wrap(name: str, content: str) -> str:
    """Wrap *content* in ``<!-- section: NAME -->`` / ``<!-- end: NAME -->`` markers."""
    return f"<!-- section: {name} -->\n{content}\n<!-- end: {name} -->"


def _root_wrap(name: str, content: str) -> str:
    """Wrap *content* in ``<!-- root: NAME -->`` / ``<!-- end-root: NAME -->`` markers.

    Used to demarcate per-root sections in the multi-root raw topology output.
    *name* is the declared root path (as it appears in the config), preserved
    verbatim so the topology-builder skill can map sections back to their
    declared scope roots.
    """
    return f"<!-- root: {name} -->\n{content}\n<!-- end-root: {name} -->"


def _is_test_directory(rel_path: str) -> bool:
    """Return True if *rel_path* is or is nested under a test directory."""
    parts = rel_path.split("/")
    return any(part in _TEST_DIR_NAMES for part in parts)


@dataclass
class _DirInfo:
    """Parsed directory information from a single .aindex file."""

    rel_path: str
    billboard: str
    child_entry_count: int
    child_dir_names: list[str] = field(default_factory=list)
    key_entries: list[AIndexEntry] = field(default_factory=list)
    all_file_entries: list[AIndexEntry] = field(default_factory=list)


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
        key_entries = [entry for entry in parsed.entries if _is_landmark_entry(entry)]

        # Collect all file entries for Directory Details section
        all_file_entries = [entry for entry in parsed.entries if entry.entry_type == "file"]

        infos.append(
            _DirInfo(
                rel_path=parsed.directory_path,
                billboard=parsed.billboard,
                child_entry_count=len(parsed.entries),
                child_dir_names=child_dir_names,
                key_entries=key_entries,
                all_file_entries=all_file_entries,
            )
        )

    return sorted(infos, key=lambda d: d.rel_path)


def _filter_infos_for_root(
    infos: list[_DirInfo], root_rel: str, project_name: str
) -> list[_DirInfo]:
    """Return the subset of *infos* whose ``rel_path`` belongs to ``root_rel``.

    ``root_rel`` is the resolved scope-root path, expressed relative to the
    project root in POSIX form (e.g. ``"src"``, ``"baml_src"``, or ``"."``).

    ``project_name`` is the project root directory's basename. Test fixtures
    historically write ``.aindex`` files with ``directory_path`` prefixed by
    the project name (``f"{project_name}/src"``), while production-emitted
    indexes use a project-relative path (``"src"``). This helper accepts both.

    A ``.aindex`` belongs to a root when:

    - ``root_rel == "."`` (the project-root scope) — every entry qualifies.
      Mixing ``.`` with non-``.`` roots is rejected at config load by the
      nested-roots guard, so this branch is only reached for default
      single-root projects (``scope_roots: [{path: .}]``).
    - Otherwise the entry's ``rel_path`` equals ``root_rel`` or starts with
      ``root_rel + "/"`` (production layout), or — for tests — the same after
      stripping the leading ``project_name + "/"`` prefix.

    The returned list preserves the ``rel_path`` ordering of *infos*.
    """
    if root_rel == ".":
        # The project-root scope captures everything; callers who want a single
        # combined output use this. When mixed with other declared roots, this
        # branch is unreachable because the nested-roots guard rejects
        # ``[., src/]`` and similar overlaps at config load.
        return list(infos)

    prefix_eq = root_rel
    prefix_with_sep = root_rel + "/"
    project_prefix = project_name + "/"

    def _belongs(rel_path: str) -> bool:
        # Production layout: rel_path is project-relative ("src", "src/foo").
        if rel_path == prefix_eq or rel_path.startswith(prefix_with_sep):
            return True
        # Test-fixture layout: rel_path is "<project>/<root>/...".
        if rel_path.startswith(project_prefix):
            stripped = rel_path[len(project_prefix) :]
            if stripped == prefix_eq or stripped.startswith(prefix_with_sep):
                return True
        return False

    return [info for info in infos if _belongs(info.rel_path)]


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


def _find_dominant_source_dir(infos: list[_DirInfo], project_name: str) -> str:
    """Return the dominant source directory name (e.g. 'src'), or empty string."""
    for info in infos:
        depth = _compute_depth(info.rel_path, project_name)
        if depth == 1:
            dir_name = info.rel_path.rsplit("/", 1)[-1]
            if dir_name in _SOURCE_DIR_CANDIDATES:
                return dir_name
    return ""


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
    dominant_source_dir = _find_dominant_source_dir(infos, project_name)

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

    # Entry points: prefer those in CLI/app dirs; skip minimal redirects (C1)
    entry_candidates: list[tuple[int, str]] = []  # (score, path_string)
    for info in infos:
        for entry in info.key_entries:
            desc_lower = entry.description.lower()
            if not any(kw in desc_lower for kw in _ENTRY_POINT_KEYWORDS):
                continue
            if _MINIMAL_EP_DISQUALIFIER.search(entry.description):
                continue
            if info.rel_path == project_name or info.rel_path == ".":
                entry_path = entry.name
            else:
                rel = info.rel_path
                if rel.startswith(project_name + "/"):
                    rel = rel[len(project_name) + 1 :]
                entry_path = f"{rel}/{entry.name}"
            dir_name = info.rel_path.rsplit("/", 1)[-1]
            score = 1 if dir_name in _PREFERRED_EP_DIRS else 0
            entry_candidates.append((score, entry_path))
    if entry_candidates:
        entry_candidates.sort(key=lambda t: (-t[0], t[1]))
        landmarks.append(f"Entry: {entry_candidates[0][1]}")

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


def _generate_entry_point_candidates(infos: list[_DirInfo], project_name: str) -> str:
    """Emit ALL entry-point keyword matches as a markdown table.

    Returns a section containing a table with columns File, Directory,
    Signal, Confidence.  Candidates in preferred directories (cli, app,
    cmd, main, bin) get ``preferred_dir + keyword`` / ``high``; all
    others get ``keyword`` / ``medium``.

    Minimal entry-point redirects (matching ``_MINIMAL_EP_DISQUALIFIER``)
    are excluded.

    Returns an empty string when no candidates are found.
    """
    rows: list[tuple[str, str, str, str]] = []

    for info in infos:
        for entry in info.key_entries:
            desc_lower = entry.description.lower()
            if not any(kw in desc_lower for kw in _ENTRY_POINT_KEYWORDS):
                continue
            if _MINIMAL_EP_DISQUALIFIER.search(entry.description):
                continue

            # Compute display directory
            if info.rel_path == project_name or info.rel_path == ".":
                display_dir = "."
            else:
                rel = info.rel_path
                if rel.startswith(project_name + "/"):
                    rel = rel[len(project_name) + 1 :]
                display_dir = rel

            # Determine confidence
            dir_name = info.rel_path.rsplit("/", 1)[-1]
            if dir_name in _PREFERRED_EP_DIRS:
                signal = "preferred_dir + keyword"
                confidence = "high"
            else:
                signal = "keyword"
                confidence = "medium"

            rows.append((entry.name, display_dir, signal, confidence))

    if not rows:
        return ""

    # Sort by confidence (high first), then by file name for determinism
    confidence_order = {"high": 0, "medium": 1}
    rows.sort(key=lambda r: (confidence_order.get(r[3], 2), r[0]))

    lines: list[str] = [
        "## Entry-Point Candidates",
        "",
        "| File | Directory | Signal | Confidence |",
        "|------|-----------|--------|------------|",
    ]
    for file_name, directory, signal, confidence in rows:
        lines.append(f"| {file_name} | {directory} | {signal} | {confidence} |")

    lines.append("")
    lines.append(
        "*These are heuristic matches based on description keywords. "
        "Verify against `pyproject.toml` before inclusion in TOPOLOGY.md.*"
    )
    lines.append("")

    return "\n".join(lines)


def _build_procedural_topology(project_root: Path, infos: list[_DirInfo]) -> str:
    """Build an adaptive-depth annotated directory tree from pre-collected data.

    Renders an indented tree from the supplied ``_DirInfo`` list.  The
    display depth adapts based on project scale:

    - Small (<=10 dirs): full tree, no filtering
    - Medium (11-40 dirs): depth <=2, plus hotspots (>5 child entries)
    - Large (41+ dirs): depth <=1, plus hotspots

    Args:
        project_root: Absolute path to the project root.
        infos: Pre-collected directory info from ``_collect_aindex_data()``.

    Returns:
        String containing the rendered tree, or a placeholder message
        if no data is available.
    """
    lexibrary_root = project_root / LEXIBRARY_DIR
    if not lexibrary_root.is_dir():
        return "(no .lexibrary directory found)"

    if not infos:
        return "(no .aindex files found -- run 'lexi update' first)"

    project_name = project_root.name
    dir_count = len(infos)

    # Build lookup maps
    info_by_path: dict[str, _DirInfo] = {info.rel_path: info for info in infos}

    # B3: Build source-module name map for test-dir annotation correlation.
    # Finds the depth at which source modules live under the dominant source dir
    # (e.g. depth 3 for src/lexibrary/archivist/, depth 2 for src/auth/).
    # Only the first match per basename is kept (shallowest wins if collision).
    dominant_source_dir = _find_dominant_source_dir(infos, project_name)
    src_by_name: dict[str, _DirInfo] = {}
    if dominant_source_dir:
        src_prefix = f"{project_name}/{dominant_source_dir}/"
        src_depth = 1  # dominant_source_dir is at depth 1
        # Determine module depth: if a depth-2 dir under src/ has child dirs,
        # source modules live one level deeper (e.g. src/lexibrary/archivist).
        module_depth = src_depth + 1
        for _path, _dinfo in info_by_path.items():
            if (
                _path.startswith(src_prefix)
                and _compute_depth(_path, project_name) == src_depth + 1
                and _dinfo.child_dir_names
            ):
                module_depth = src_depth + 2
                break
        for _path, _dinfo in info_by_path.items():
            if not _path.startswith(src_prefix):
                continue
            if _compute_depth(_path, project_name) != module_depth:
                continue
            if is_structural_description(_dinfo.billboard):
                continue
            _basename = _path.rsplit("/", 1)[-1]
            if _basename not in src_by_name:
                src_by_name[_basename] = _dinfo

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

    # Identify hotspot paths (B2: gate on non-structural billboard so test dirs
    # with "N Python files" billboards don't qualify as hotspots).
    hotspot_paths: set[str] = set()
    if hotspot_threshold is not None:
        for info in infos:
            if info.child_entry_count > hotspot_threshold and not is_structural_description(
                info.billboard
            ):
                hotspot_paths.add(info.rel_path)

    # Compute important_paths (ancestor +1 bonus) and landmark_dirs (always shown).
    # A directory is a landmark if it has key_entries or its name matches a test
    # directory pattern.  landmark_dirs are shown unconditionally regardless of
    # depth; their ancestors get a +1 effective-depth bonus via important_paths.
    # NOTE: for landmarks at depth 4+ with display_depth=1, the depth-3 ancestor
    # may still be hidden (effective_depth reaches 2, not 3); only the landmark
    # itself is guaranteed visible.
    important_paths: set[str] = set()
    landmark_dirs: set[str] = set()
    for info in infos:
        is_landmark = bool(info.key_entries)
        if not is_landmark:
            _dir_name = info.rel_path.rsplit("/", 1)[-1]
            is_landmark = _dir_name in _TEST_DIR_NAMES
        if is_landmark:
            landmark_dirs.add(info.rel_path)
            # Walk up the path adding all ancestors (including landmark itself)
            # so each ancestor gets +1 effective depth in _should_show().
            parts = info.rel_path.split("/")
            for i in range(1, len(parts) + 1):
                important_paths.add("/".join(parts[:i]))

    def _should_show(rel_path: str) -> bool:
        """Determine whether a directory should be included in the tree."""
        if display_depth is None:
            return True
        if rel_path in landmark_dirs:
            return True
        depth = _compute_depth(rel_path, project_name)
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
            dir_name = project_name
            dir_display = f"{project_name}/"
        else:
            dir_name = info.rel_path.rsplit("/", 1)[-1]
            dir_display = f"{dir_name}/"

        annotation = f" -- {info.billboard}" if info.billboard else ""

        # B3: derive annotation for test_* directories from their source counterpart
        if dir_name.startswith("test_"):
            src_name = dir_name[5:]  # strip "test_" prefix
            src_info = src_by_name.get(src_name)
            if src_info:
                annotation = f" -- Tests for {src_name}: {src_info.billboard}"

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


_TOKEN_BUDGET = 25_000  # Maximum estimated tokens (chars // 4) for raw topology


# Config file candidates in priority order for Project Config section
_PROJECT_CONFIG_FILES: tuple[tuple[str, str], ...] = (
    ("pyproject.toml", "toml"),
    ("package.json", "json"),
    ("Cargo.toml", "toml"),
    ("go.mod", ""),
)


def _build_source_module_map(infos: list[_DirInfo], project_name: str) -> dict[str, _DirInfo]:
    """Build a mapping from source module basename to its ``_DirInfo``.

    Used by test-directory collapse to correlate ``test_<name>/`` directories
    to their source counterpart ``<name>/``.  Only non-structural-billboard
    source modules under the dominant source directory are included.
    """
    info_by_path: dict[str, _DirInfo] = {info.rel_path: info for info in infos}
    dominant_source_dir = _find_dominant_source_dir(infos, project_name)
    src_by_name: dict[str, _DirInfo] = {}
    if dominant_source_dir:
        src_prefix = f"{project_name}/{dominant_source_dir}/"
        src_depth = 1  # dominant_source_dir is at depth 1
        # Determine module depth: if a depth-2 dir under src/ has child dirs,
        # source modules live one level deeper (e.g. src/lexibrary/archivist).
        module_depth = src_depth + 1
        for _path, _dinfo in info_by_path.items():
            if (
                _path.startswith(src_prefix)
                and _compute_depth(_path, project_name) == src_depth + 1
                and _dinfo.child_dir_names
            ):
                module_depth = src_depth + 2
                break
        for _path, _dinfo in info_by_path.items():
            if not _path.startswith(src_prefix):
                continue
            if _compute_depth(_path, project_name) != module_depth:
                continue
            if is_structural_description(_dinfo.billboard):
                continue
            _basename = _path.rsplit("/", 1)[-1]
            if _basename not in src_by_name:
                src_by_name[_basename] = _dinfo
    return src_by_name


def _render_directory_detail_block(infos: list[_DirInfo], project_name: str, heading: str) -> str:
    """Render per-directory subsections with billboard, counts, and file table.

    Each directory in *infos* gets a subsection containing:

    - The billboard text
    - File and subdirectory counts
    - A markdown table of all file entries (Name, Type, Description)

    Args:
        infos: Directory info entries to render.
        project_name: Project root directory name for path display.
        heading: Section heading (e.g. ``"## Source Modules"``).
    """
    from lexibrary.utils.languages import detect_language  # noqa: PLC0415

    if not infos:
        return ""

    sections: list[str] = [heading, ""]
    for info in infos:
        # Compute display path (strip project name prefix)
        if info.rel_path == project_name or info.rel_path == ".":
            display_path = f"{project_name}/"
        else:
            rel = info.rel_path
            if rel.startswith(project_name + "/"):
                rel = rel[len(project_name) + 1 :]
            display_path = f"{rel}/"

        sections.append(f"### {display_path}")
        if info.billboard:
            sections.append(f"{info.billboard}")
        sections.append("")

        file_count = len(info.all_file_entries)
        dir_count = len(info.child_dir_names)
        sections.append(f"Files: {file_count} | Subdirectories: {dir_count}")
        sections.append("")

        if info.all_file_entries:
            sections.append("| Name | Type | Description |")
            sections.append("|------|------|-------------|")
            for entry in info.all_file_entries:
                file_type = detect_language(entry.name)
                # Escape pipe characters in description for markdown table
                desc = entry.description.replace("|", "\\|")
                sections.append(f"| {entry.name} | {file_type} | {desc} |")
            sections.append("")

    return "\n".join(sections)


def _render_test_layout_block(
    test_infos: list[_DirInfo],
    all_infos: list[_DirInfo],
    project_name: str,
) -> str:
    """Render test directories as collapsed one-line summaries.

    Each test directory is rendered as a single line instead of a per-file
    table.  Format:

    - With source correlation: ``test_foo/ -- N files covering foo/``
    - Without correlation: ``test_foo/ -- N files``

    Args:
        test_infos: Directory info entries for test directories only.
        all_infos: All directory info entries (needed for source module map).
        project_name: Project root directory name for path display.
    """
    if not test_infos:
        return ""

    src_by_name = _build_source_module_map(all_infos, project_name)

    sections: list[str] = ["## Test Layout", ""]
    for info in test_infos:
        # Compute display path (strip project name prefix)
        if info.rel_path == project_name or info.rel_path == ".":
            display_path = f"{project_name}/"
        else:
            rel = info.rel_path
            if rel.startswith(project_name + "/"):
                rel = rel[len(project_name) + 1 :]
            display_path = f"{rel}/"

        dir_name = info.rel_path.rsplit("/", 1)[-1]
        file_count = len(info.all_file_entries)

        # Try to correlate test_<name>/ to source module <name>/
        covering_clause = ""
        if dir_name.startswith("test_"):
            src_name = dir_name[5:]  # strip "test_" prefix
            if src_name in src_by_name:
                covering_clause = f" covering {src_name}/"

        sections.append(f"{display_path} -- {file_count} files{covering_clause}")

    sections.append("")
    return "\n".join(sections)


def _display_path(rel_path: str, project_name: str) -> str:
    """Compute the display path for a directory (strip project name prefix)."""
    if rel_path == project_name or rel_path == ".":
        return f"{project_name}/"
    rel = rel_path
    if rel.startswith(project_name + "/"):
        rel = rel[len(project_name) + 1 :]
    return f"{rel}/"


def _should_detail_directory(
    rel_path: str,
    project_name: str,
    dominant_source_dir: str,
    detail_dirs: list[str],
) -> bool:
    """Return True if *rel_path* should get a full file table.

    Full detail is emitted for:
    - Directories under the dominant source directory (e.g. ``src/``)
    - Directories matching any pattern in *detail_dirs*

    Everything else receives a one-line summary.
    """
    # Directories under the dominant source dir always get full detail
    if dominant_source_dir:
        src_prefix = f"{project_name}/{dominant_source_dir}/"
        if rel_path.startswith(src_prefix) or rel_path == f"{project_name}/{dominant_source_dir}":
            return True

    # Check display path against detail_dirs patterns
    display = _display_path(rel_path, project_name)
    # Strip trailing slash for matching (patterns like "docs/**" should match "docs/agent/")
    display_no_slash = display.rstrip("/")
    for pattern in detail_dirs:
        if fnmatch.fnmatch(display_no_slash, pattern):
            return True
        # Also match with trailing slash for patterns like "docs/**"
        if fnmatch.fnmatch(display, pattern):
            return True
    return False


def _render_summary_block(infos: list[_DirInfo], project_name: str, heading: str) -> str:
    """Render non-detailed directories as one-line summaries under *heading*.

    Each directory is rendered as: ``display_path -- N files``
    (with billboard appended if non-empty).
    """
    if not infos:
        return ""

    sections: list[str] = [heading, ""]
    for info in infos:
        display = _display_path(info.rel_path, project_name)
        file_count = len(info.all_file_entries)
        billboard_clause = f" -- {info.billboard}" if info.billboard else ""
        sections.append(f"{display} -- {file_count} files{billboard_clause}")

    sections.append("")
    return "\n".join(sections)


def _generate_directory_details(
    infos: list[_DirInfo],
    project_name: str,
    detail_dirs: list[str] | None = None,
) -> tuple[str, str]:
    """Split directory infos into source-modules and test-layout sections.

    Non-test directories under the dominant source dir or matching
    *detail_dirs* patterns get full per-file tables.  All other non-test
    directories get one-line summaries appended to the source-modules
    section.  Test directories are collapsed to one-line summaries with
    optional source-module correlation.

    Args:
        infos: All directory info entries.
        project_name: Project root directory name.
        detail_dirs: Glob patterns for extra directories that should
            receive full file tables.  ``None`` or empty list means
            only the dominant source directory gets detail.

    Returns:
        Tuple of ``(source_modules_content, test_layout_content)``.
        Either may be an empty string if no directories of that type exist.
    """
    if detail_dirs is None:
        detail_dirs = []

    test_infos = [i for i in infos if _is_test_directory(i.rel_path)]
    non_test_infos = [i for i in infos if not _is_test_directory(i.rel_path)]

    dominant_source_dir = _find_dominant_source_dir(infos, project_name)

    detail_infos = [
        i
        for i in non_test_infos
        if _should_detail_directory(i.rel_path, project_name, dominant_source_dir, detail_dirs)
    ]
    summary_infos = [
        i
        for i in non_test_infos
        if not _should_detail_directory(i.rel_path, project_name, dominant_source_dir, detail_dirs)
    ]

    # Build the source-modules section: full tables for detail dirs,
    # then one-line summaries for the rest
    source_content = _render_directory_detail_block(detail_infos, project_name, "## Source Modules")

    if summary_infos:
        summary_text = _render_summary_block(summary_infos, project_name, "## Other Directories")
        source_content = source_content + "\n" + summary_text if source_content else summary_text

    test_content = _render_test_layout_block(test_infos, infos, project_name)

    return source_content, test_content


def _generate_library_stats(project_root: Path) -> str:
    """Render library statistics: concept, convention, playbook, open stack post counts."""
    lexibrary_root = project_root / LEXIBRARY_DIR

    # Count concepts
    concepts_dir = lexibrary_root / "concepts"
    concept_count = 0
    if concepts_dir.is_dir():
        concept_count = len(list(concepts_dir.glob("*.md")))

    # Count conventions
    conventions_dir = lexibrary_root / "conventions"
    convention_count = 0
    if conventions_dir.is_dir():
        convention_count = len(list(conventions_dir.glob("*.md")))

    # Count playbooks
    playbooks_dir = lexibrary_root / "playbooks"
    playbook_count = 0
    if playbooks_dir.is_dir():
        playbook_count = len(list(playbooks_dir.glob("*.md")))

    # Count open stack posts
    stack_dir = lexibrary_root / "stack"
    open_stack_count = 0
    if stack_dir.is_dir():
        from lexibrary.stack.parser import parse_stack_post  # noqa: PLC0415

        for md_path in stack_dir.glob("ST-*-*.md"):
            post = parse_stack_post(md_path)
            if post is not None and post.frontmatter.status == "open":
                open_stack_count += 1

    lines: list[str] = ["## Library Stats", ""]
    lines.append(f"Concepts: {concept_count}")
    lines.append(f"Conventions: {convention_count}")
    lines.append(f"Playbooks: {playbook_count}")
    lines.append(f"Open stack posts: {open_stack_count}")
    lines.append("")
    return "\n".join(lines)


def _generate_project_config(project_root: Path) -> str:
    """Inline the first found project config file in a fenced code block."""
    for filename, lang in _PROJECT_CONFIG_FILES:
        config_path = project_root / filename
        if config_path.is_file():
            try:
                config_content = config_path.read_text(encoding="utf-8")
            except OSError:
                continue
            fence = f"```{lang}" if lang else "```"
            lines: list[str] = [
                "## Project Config",
                "",
                f"**{filename}**",
                "",
                fence,
                config_content.rstrip(),
                "```",
                "",
            ]
            return "\n".join(lines)
    return ""


def _apply_token_sentinel(
    content: str,
    infos: list[_DirInfo],
    project_name: str,
) -> str:
    # TODO: review sentinel strategy after detail_dirs
    # With detail filtering now collapsing many directories to one-line
    # summaries, the sentinel's table-removal approach may target fewer
    # directories and the 25K budget may rarely be hit.  Consider whether
    # the sentinel is still needed or should adapt to the new content shape.
    """Cap raw topology at ~25K tokens by trimming largest directory file tables.

    Estimates tokens via ``len(content) // 4``.  When over budget, removes
    file tables from the Directory Details section starting with the largest
    directories (by file count) until the output fits.
    """
    estimated_tokens = len(content) // 4
    if estimated_tokens <= _TOKEN_BUDGET:
        return content

    # Sort directories by file count descending for progressive capping
    dirs_by_size = sorted(infos, key=lambda d: len(d.all_file_entries), reverse=True)

    for info in dirs_by_size:
        if not info.all_file_entries:
            continue

        # Compute the display path used in the section header
        if info.rel_path == project_name or info.rel_path == ".":
            display_path = f"{project_name}/"
        else:
            rel = info.rel_path
            if rel.startswith(project_name + "/"):
                rel = rel[len(project_name) + 1 :]
            display_path = f"{rel}/"

        # Find and remove the file table for this directory
        header = f"### {display_path}"
        header_pos = content.find(header)
        if header_pos == -1:
            continue

        # Find the table start (| Name |) after this header
        table_marker = "| Name | Type | Description |"
        table_start = content.find(table_marker, header_pos)
        if table_start == -1:
            continue

        # Find table end (next blank line after table rows)
        table_end = table_start
        for line in content[table_start:].split("\n"):
            table_end += len(line) + 1
            if not line.strip():
                break

        # Replace table with truncation notice
        file_count = len(info.all_file_entries)
        notice = f"*({file_count} files -- table omitted for size)*\n\n"
        content = content[:table_start] + notice + content[table_end:]

        estimated_tokens = len(content) // 4
        if estimated_tokens <= _TOKEN_BUDGET:
            break

    if len(content) // 4 > _TOKEN_BUDGET:
        logger.warning(
            "Raw topology exceeds 25K token budget after capping (%d estimated tokens)",
            len(content) // 4,
        )
    else:
        logger.warning(
            "Raw topology capped to fit 25K token budget (%d estimated tokens after trimming)",
            len(content) // 4,
        )

    return content


def _build_per_root_section(
    project_root: Path,
    project_name: str,
    root_rel: str,
    root_infos: list[_DirInfo],
    detail_dirs: list[str],
) -> str:
    """Build the per-root section body for one declared scope root.

    Renders the five per-root section blocks (``header``,
    ``entry-point-candidates``, ``tree``, ``source-modules``, ``test-layout``)
    using only the ``.aindex`` data that belongs to this root, then wraps the
    block in ``<!-- root: NAME -->`` / ``<!-- end-root: NAME -->`` markers so
    downstream consumers (the topology-builder skill) can mechanically
    partition the document by root.

    Args:
        project_root: Absolute project root path.
        project_name: Project root directory's basename (used for path display).
        root_rel: Declared root path string (e.g. ``"src"``, ``"baml_src"``,
            ``"."``). Preserved verbatim in the wrapper marker.
        root_infos: ``_DirInfo`` entries that belong to this root, already
            filtered by :func:`_filter_infos_for_root`.
        detail_dirs: ``topology.detail_dirs`` glob patterns from config.
    """
    section_lines: list[str] = []

    # -- header section --
    header_body = _generate_header(root_infos, project_root)
    section_lines.append(_section_wrap("header", header_body))
    section_lines.append("")

    # -- entry-point-candidates section --
    entry_candidates = _generate_entry_point_candidates(root_infos, project_name)
    section_lines.append(_section_wrap("entry-point-candidates", entry_candidates))
    section_lines.append("")

    # -- tree section --
    tree_text = _build_procedural_topology(project_root, root_infos)
    tree_body = f"```\n{tree_text}\n```"
    section_lines.append(_section_wrap("tree", tree_body))
    section_lines.append("")

    # -- source-modules and test-layout sections --
    source_modules, test_layout = _generate_directory_details(
        root_infos, project_name, detail_dirs=detail_dirs
    )
    section_lines.append(_section_wrap("source-modules", source_modules))
    section_lines.append("")
    section_lines.append(_section_wrap("test-layout", test_layout))

    return _root_wrap(root_rel, "\n".join(section_lines))


def generate_raw_topology(project_root: Path) -> Path:
    """Generate ``.lexibrary/tmp/raw-topology.md`` from .aindex billboard summaries.

    Builds an adaptive-depth annotated directory tree and wraps it in a
    markdown document.  Uses ``atomic_write()`` for safe file replacement.

    Multi-root layout
    -----------------

    The document is laid out as:

    1. Document title (``# Project Topology``).
    2. One ``<!-- root: NAME -->`` block per declared scope root in
       ``config.scope_roots`` declared order. Each per-root block contains the
       five scoped sections (``header``, ``entry-point-candidates``, ``tree``,
       ``source-modules``, ``test-layout``) wrapped in their existing
       ``<!-- section: NAME -->`` markers. Roots with zero ``.aindex`` entries
       are skipped entirely.
    3. Project-level ``config`` and ``stats`` sections, emitted once at the
       document level (outside any per-root wrapper) because they describe
       the whole project rather than any single root.

    For the default single-root config (``scope_roots: [{path: .}]``) this
    yields exactly one per-root block whose contents are the same five
    sections that were emitted before multi-root support landed, plus the
    two project-level sections — the byte-level diff is the new
    ``<!-- root: . -->`` wrapper around the per-root block.

    Determinism: the ``resolved_scope_roots`` list preserves the user's
    declared order, ``_collect_aindex_data`` sorts entries by ``rel_path``,
    and per-root rendering reads only from those sorted lists. Two consecutive
    runs against an unchanged tree produce byte-identical output.

    Empty-document fallback: when no per-root section qualifies (no roots
    have ``.aindex`` entries, or no scope roots resolved on disk), a single
    placeholder per-root section is still emitted so the topology-builder
    skill always sees a well-formed document.

    Reads ``topology.detail_dirs`` from project configuration to control
    which directories receive full file tables versus one-line summaries.

    Args:
        project_root: Absolute path to the project root.

    Returns:
        Path to the written ``tmp/raw-topology.md`` file.
    """
    from lexibrary.config.loader import load_config  # noqa: PLC0415

    config = load_config(project_root)
    detail_dirs = config.topology.detail_dirs

    # Collect .aindex data once and pass to all consumers
    infos = _collect_aindex_data(project_root)
    project_name = project_root.name

    content_lines = ["# Project Topology", ""]

    # -- per-root sections (one per declared scope root, declared order) --
    # Resolve scope roots up front. ``resolved_scope_roots`` enforces the
    # path-traversal, nested-roots, and duplicate-entry guards at load; we
    # consume only the resolved (existing-on-disk) list. Missing-on-disk
    # entries are surfaced by the lifecycle bootstrap layer, not here.
    resolved = config.resolved_scope_roots(project_root).resolved

    # Build a (declared root path string, resolved Path) zip so we can
    # preserve the user's declared spelling in the ``<!-- root: NAME -->``
    # wrapper while still using the resolved Path to filter ``_DirInfo``
    # entries. ``resolved`` follows declared order (the model preserves the
    # input list and filters only by existence), so we walk
    # ``config.scope_roots`` and keep entries whose resolved path is in
    # ``resolved``.
    project_root_abs = project_root.resolve()
    declared_existing: list[tuple[str, Path]] = []
    for sr in config.scope_roots:
        candidate = (project_root_abs / sr.path).resolve()
        if candidate in resolved:
            declared_existing.append((sr.path, candidate))

    sections_emitted = 0
    for declared_path, abs_path in declared_existing:
        # Compute the project-relative POSIX root path string used by the
        # filter helper (e.g. ``"src"`` rather than ``"src/"`` or absolute).
        try:
            rel = abs_path.relative_to(project_root_abs)
        except ValueError:
            # Defensive: ``resolved_scope_roots`` already enforces this, but
            # don't crash topology generation on an unexpected layout.
            continue
        root_rel = "." if str(rel) in (".", "") else rel.as_posix()

        root_infos = _filter_infos_for_root(infos, root_rel, project_name)

        # Skip roots with zero ``.aindex`` entries — keeps the document
        # focused on roots the archivist has actually indexed.
        if not root_infos:
            continue

        content_lines.append(
            _build_per_root_section(
                project_root,
                project_name,
                declared_path,
                root_infos,
                detail_dirs,
            )
        )
        content_lines.append("")
        sections_emitted += 1

    # When no per-root section was emitted (either ``.aindex`` data is
    # missing entirely or the on-disk root layout doesn't match any declared
    # root), emit a placeholder section so the topology-builder skill still
    # has a well-formed document to consume. We attribute the placeholder to
    # the first declared+existing root (or ``"."`` when no scope roots
    # resolved).
    if sections_emitted == 0:
        placeholder_root = declared_existing[0][0] if declared_existing else "."
        content_lines.append(
            _build_per_root_section(
                project_root,
                project_name,
                placeholder_root,
                [],
                detail_dirs,
            )
        )
        content_lines.append("")

    # -- config section (project-level, emitted once) --
    project_config = _generate_project_config(project_root)
    content_lines.append(_section_wrap("config", project_config))
    content_lines.append("")

    # -- stats section (project-level, emitted once) --
    library_stats = _generate_library_stats(project_root)
    content_lines.append(_section_wrap("stats", library_stats))
    content_lines.append("")

    content = "\n".join(content_lines)

    # Apply 25K-token size sentinel
    content = _apply_token_sentinel(content, infos, project_name)

    tmp_dir = project_root / LEXIBRARY_DIR / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    output_path = tmp_dir / "raw-topology.md"
    atomic_write(output_path, content)
    logger.info("Wrote tmp/raw-topology.md (%d chars)", len(content))

    return output_path
