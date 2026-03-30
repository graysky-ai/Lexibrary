"""Orient service -- gathers project orientation data without terminal output."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Approximate token budget for orient output.
# 1 token ~= 4 characters for English text.
ORIENT_TOKEN_BUDGET = 4000
CHARS_PER_TOKEN = 4
ORIENT_CHAR_BUDGET = ORIENT_TOKEN_BUDGET * CHARS_PER_TOKEN


@dataclass
class OrientResult:
    """Pure-data result returned by :func:`build_orient`."""

    topology_text: str = ""
    file_descriptions: list[tuple[str, str]] = field(default_factory=list)
    library_stats: str = ""
    iwh_signals: str = ""
    is_stale: bool = False
    staleness_message: str | None = None


def collect_file_descriptions(project_root: Path) -> list[tuple[str, str]]:
    """Extract (relative_path, description) pairs for file-level aindex entries.

    Reuses `parse_aindex` for .aindex discovery, then parses each .aindex file
    for entries with ``entry_type == "file"`` and returns their descriptions.

    Returns a sorted list of ``(dir_path/file_name, description)`` tuples.
    """
    from lexibrary.artifacts.aindex_parser import parse_aindex  # noqa: PLC0415
    from lexibrary.utils.paths import LEXIBRARY_DIR  # noqa: PLC0415

    lexibrary_root = project_root / LEXIBRARY_DIR
    if not lexibrary_root.is_dir():
        return []

    descriptions: list[tuple[str, str]] = []
    for aindex_path in sorted(lexibrary_root.rglob(".aindex")):
        parsed = parse_aindex(aindex_path)
        if parsed is None:
            continue
        for entry in parsed.entries:
            if entry.entry_type == "file" and entry.description:
                dir_path = parsed.directory_path
                file_rel = f"{dir_path}/{entry.name}" if dir_path != "." else entry.name
                descriptions.append((file_rel, entry.description))

    return sorted(descriptions, key=lambda t: t[0])


def collect_library_stats(project_root: Path) -> str:
    """Collect library statistics: concept, convention, playbook counts, and open stack posts.

    Returns a formatted section string, or empty string if no stats available.
    """
    from lexibrary.utils.paths import LEXIBRARY_DIR  # noqa: PLC0415

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

    if concept_count or convention_count or playbook_count or open_stack_count:
        lines: list[str] = ["## Library Stats\n"]
        lines.append(f"Concepts: {concept_count}")
        lines.append(f"Conventions: {convention_count}")
        lines.append(f"Playbooks: {playbook_count}")
        lines.append(f"Open stack posts: {open_stack_count}")
        return "\n".join(lines)

    return ""


def collect_iwh_peek(project_root: Path) -> str:
    """Peek at IWH signals without consuming them.

    Returns a formatted section string, or empty string if no signals found.
    """
    from lexibrary.iwh.reader import find_all_iwh  # noqa: PLC0415

    results = find_all_iwh(project_root)
    if not results:
        return ""

    lines: list[str] = ["## IWH Signals\n"]
    for source_dir, iwh in results:
        display_dir = f"{source_dir}/" if str(source_dir) != "." else "./"
        body_preview = iwh.body.replace("\n", " ").strip()
        if len(body_preview) > 80:
            body_preview = body_preview[:77] + "..."
        lines.append(f"- [{iwh.scope}] {display_dir} -- {body_preview}")

    # Consumption guidance footer
    lines.append("")
    lines.append(
        "Run `lexi iwh read <directory>` for each signal above to get full details "
        "and consume the signal."
    )

    return "\n".join(lines)


def check_topology_staleness(project_root: Path) -> tuple[bool, str | None]:
    """Check if raw topology is newer than TOPOLOGY.md or TOPOLOGY.md is missing.

    Returns ``(is_stale, message)`` where *message* is ``None`` when not stale.
    Does **not** produce any terminal output.
    """
    from lexibrary.utils.paths import LEXIBRARY_DIR  # noqa: PLC0415

    lexibrary_root = project_root / LEXIBRARY_DIR
    raw_path = lexibrary_root / "tmp" / "raw-topology.md"
    topology_path = lexibrary_root / "TOPOLOGY.md"

    if not raw_path.is_file():
        return False, None

    if not topology_path.is_file():
        return True, (
            "Raw topology exists but TOPOLOGY.md is missing. Run /topology-builder to generate it."
        )

    if raw_path.stat().st_mtime > topology_path.stat().st_mtime:
        return True, ("Raw topology is newer than TOPOLOGY.md. Run /topology-builder to refresh.")

    return False, None


def build_orient(project_root: Path) -> OrientResult:
    """Build orientation data for agent sessions.

    Includes TOPOLOGY.md content, file-level descriptions from .aindex
    files (trimmed to approximately :data:`ORIENT_TOKEN_BUDGET` tokens),
    library stats (concept count, convention count, open stack posts),
    and IWH signal summaries (peek only, no consumption).

    Returns an :class:`OrientResult` with empty fields if no
    ``.lexibrary/`` directory exists.
    """
    from lexibrary.utils.paths import LEXIBRARY_DIR  # noqa: PLC0415

    lexibrary_root = project_root / LEXIBRARY_DIR
    if not lexibrary_root.is_dir():
        return OrientResult()

    # 1. TOPOLOGY.md content
    topology_path = lexibrary_root / "TOPOLOGY.md"
    topology_text = ""
    if topology_path.is_file():
        topology_text = topology_path.read_text(encoding="utf-8").strip()

    # 2. File descriptions from .aindex entries
    file_descs = collect_file_descriptions(project_root)

    # 3. Library stats
    stats = collect_library_stats(project_root)

    # 4. IWH signals peek
    iwh_section = collect_iwh_peek(project_root)

    # 5. Topology staleness
    is_stale, staleness_message = check_topology_staleness(project_root)

    return OrientResult(
        topology_text=topology_text,
        file_descriptions=file_descs,
        library_stats=stats,
        iwh_signals=iwh_section,
        is_stale=is_stale,
        staleness_message=staleness_message,
    )
