"""Lookup service — data-gathering logic for file and directory lookups.

Extracts the business logic from the ``lexi lookup`` CLI handler into
pure-data service functions that return result dataclasses.  No terminal
output or CLI dependencies.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lexibrary.artifacts.convention import ConventionFile
    from lexibrary.artifacts.playbook import PlaybookFile


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class SiblingSummary:
    """Summary of a sibling file from .aindex."""

    name: str  # filename (e.g., "search.py")
    description: str  # one-line description from .aindex entry


@dataclass
class ConceptSummary:
    """Summary of a related concept."""

    name: str  # concept slug (e.g., "error-handling")
    status: str | None  # "active", "draft", "deprecated" -- None when only name is known
    summary: str | None  # one-line summary -- None in brief mode or when unavailable


@dataclass
class DirectoryLookupResult:
    """Data gathered for a directory lookup."""

    directory_path: str
    """Relative path of the directory from project root."""

    aindex_content: str | None
    """Rendered aindex content (billboard + child map), or None if no .aindex."""

    conventions: list[ConventionFile]
    """Applicable conventions for this directory."""

    conventions_total_count: int
    """Total number of matching conventions (before display-limit truncation)."""

    display_limit: int
    """Maximum number of conventions to display."""

    iwh_text: str
    """Rendered IWH signal text, or empty string."""

    playbooks: list[PlaybookFile]
    """Triggered playbooks for this directory."""

    playbook_display_limit: int
    """Maximum number of playbooks to display."""

    import_count: int
    """Total inbound ast_import links."""

    imported_file_count: int
    """Distinct files with inbound imports."""


@dataclass
class LookupResult:
    """Data gathered for a file lookup."""

    file_path: str
    """Relative path of the file from project root."""

    description: str | None
    """One-line description from design file frontmatter."""

    is_stale: bool
    """Whether the source file has changed since the design was generated."""

    design_content: str | None
    """Full design file content, or None if no design file exists."""

    conventions: list[ConventionFile]
    """Applicable conventions for this file."""

    conventions_total_count: int
    """Total number of matching conventions (before display-limit truncation)."""

    display_limit: int
    """Maximum number of conventions to display."""

    playbooks: list[PlaybookFile]
    """Triggered playbooks for this file."""

    playbook_display_limit: int
    """Maximum number of playbooks to display."""

    issues_text: str
    """Rendered known-issues text, or empty string."""

    iwh_text: str
    """Rendered IWH signal text, or empty string."""

    links_text: str
    """Rendered reverse-links text, or empty string."""

    dependents: list[str]
    """Paths of files that import this file (ast_import links)."""

    open_issue_count: int
    """Number of open stack issues referencing this file."""

    siblings: list[SiblingSummary]
    """Sibling files from .aindex."""

    concepts: list[ConceptSummary]
    """Related concepts."""

    concepts_linkgraph_available: bool = True
    """Whether concepts were populated from the link graph (True) or fell back to wikilinks."""


# ---------------------------------------------------------------------------
# Token budget helpers
# ---------------------------------------------------------------------------


def estimate_tokens(text: str) -> int:
    """Estimate token count using a character-based heuristic.

    Approximates ~4 characters per token, avoiding the overhead of
    importing a tokenizer for CLI output.
    """
    if not text:
        return 0
    return max(1, len(text) // 4)


def truncate_lookup_sections(
    sections: list[tuple[str, str, int]],
    total_budget: int,
) -> list[tuple[str, str]]:
    """Truncate lookup sections to fit within a token budget.

    Sections are provided as ``(name, content, priority)`` tuples where
    lower priority values mean higher importance.  Sections are included
    in priority order until the budget is exhausted.

    Priority order: design (0) > conventions (1) > issues (2) > IWH (3) > links (4)

    Returns a list of ``(name, content)`` tuples for sections that fit.
    """
    # Sort by priority (lower = more important)
    sorted_sections = sorted(sections, key=lambda s: s[2])

    result: list[tuple[str, str]] = []
    used_tokens = 0

    for name, content, _priority in sorted_sections:
        if not content:
            continue
        section_tokens = estimate_tokens(content)
        if used_tokens + section_tokens <= total_budget:
            result.append((name, content))
            used_tokens += section_tokens
        else:
            # Try to include a truncated version if there's budget left
            remaining = total_budget - used_tokens
            if remaining > 50:
                max_chars = remaining * 4
                truncated = content[:max_chars] + "\n... truncated due to token budget\n"
                result.append((name, truncated))
                used_tokens = total_budget
            break

    return result


# ---------------------------------------------------------------------------
# Service functions
# ---------------------------------------------------------------------------


def build_directory_lookup(
    target: Path,
    project_root: Path,
    config: object,
) -> DirectoryLookupResult | None:
    """Gather data for a directory lookup.

    Returns a :class:`DirectoryLookupResult` with aindex content,
    conventions, and IWH text.  Returns ``None`` if *config* is not a
    valid :class:`LexibraryConfig`.
    """
    from lexibrary.artifacts.aindex_parser import parse_aindex  # noqa: PLC0415
    from lexibrary.config.schema import LexibraryConfig  # noqa: PLC0415
    from lexibrary.conventions.index import ConventionIndex  # noqa: PLC0415
    from lexibrary.linkgraph import open_index  # noqa: PLC0415
    from lexibrary.playbooks.index import PlaybookIndex  # noqa: PLC0415
    from lexibrary.utils.paths import LEXIBRARY_DIR  # noqa: PLC0415

    if not isinstance(config, LexibraryConfig):
        return None

    rel_target = str(target.relative_to(project_root))

    # Parse aindex file
    aindex_path = project_root / LEXIBRARY_DIR / "designs" / rel_target / ".aindex"
    aindex = parse_aindex(aindex_path)

    aindex_content: str | None = None
    if aindex is not None:
        lines: list[str] = []
        lines.append(f"# {aindex.directory_path}\n")
        lines.append(f"{aindex.billboard}\n")
        if aindex.entries:
            lines.append("## Child Map\n")
            lines.append("| Name | Type | Description |")
            lines.append("| --- | --- | --- |")
            for entry in aindex.entries:
                suffix = "/" if entry.entry_type == "dir" else ""
                lines.append(
                    f"| `{entry.name}{suffix}` | {entry.entry_type} | {entry.description} |"
                )
            lines.append("")
        aindex_content = "\n".join(lines)

    # Convention delivery
    conventions_dir = project_root / ".lexibrary" / "conventions"
    convention_index = ConventionIndex(conventions_dir)
    convention_index.load()

    conventions_list: list[ConventionFile] = []
    total_count = 0
    display_limit = config.conventions.lookup_display_limit

    if len(convention_index) > 0:
        conventions_list, total_count = convention_index.find_by_scope_limited(
            rel_target,
            scope_root=config.scope_root,
            limit=display_limit,
        )

    # Triggered playbooks for directory
    playbooks_dir = project_root / ".lexibrary" / "playbooks"
    playbook_index = PlaybookIndex(playbooks_dir)
    playbook_index.load()
    triggered_playbooks = playbook_index.by_trigger_dir(rel_target)
    pb_display_limit = config.playbooks.lookup_display_limit

    # Inbound import counts from link graph
    import_count = 0
    imported_file_count = 0
    link_graph = open_index(project_root)
    if link_graph is not None and aindex is not None:
        importing_files: set[str] = set()
        file_entries = [e for e in aindex.entries if e.entry_type == "file"]
        for entry in file_entries:
            entry_path = f"{rel_target}/{entry.name}"
            import_links = link_graph.reverse_deps(entry_path, link_type="ast_import")
            import_count += len(import_links)
            for lnk in import_links:
                importing_files.add(lnk.source_path)
        imported_file_count = len(importing_files)
        link_graph.close()
    elif link_graph is not None:
        link_graph.close()

    # IWH signal peek
    iwh_text = _build_iwh_peek(project_root, target)

    return DirectoryLookupResult(
        directory_path=rel_target,
        aindex_content=aindex_content,
        conventions=conventions_list,
        conventions_total_count=total_count,
        display_limit=display_limit,
        iwh_text=iwh_text,
        playbooks=triggered_playbooks,
        playbook_display_limit=pb_display_limit,
        import_count=import_count,
        imported_file_count=imported_file_count,
    )


def build_file_lookup(
    target: Path,
    project_root: Path,
    config: object,
    *,
    full: bool = False,
) -> LookupResult | None:
    """Gather data for a file lookup.

    Returns a :class:`LookupResult` with all data needed to render the
    lookup response.  Returns ``None`` if *config* is not a valid
    :class:`LexibraryConfig`.

    When *full* is ``False`` (brief mode), only basic fields are populated;
    design_content, links_text, and issues_text remain empty.
    """
    from lexibrary.artifacts.aindex_parser import parse_aindex  # noqa: PLC0415
    from lexibrary.artifacts.design_file_parser import (  # noqa: PLC0415
        parse_design_file,
        parse_design_file_frontmatter,
        parse_design_file_metadata,
    )
    from lexibrary.config.schema import LexibraryConfig  # noqa: PLC0415
    from lexibrary.conventions.index import ConventionIndex  # noqa: PLC0415
    from lexibrary.linkgraph import open_index  # noqa: PLC0415
    from lexibrary.playbooks.index import PlaybookIndex  # noqa: PLC0415
    from lexibrary.stack.parser import parse_stack_post  # noqa: PLC0415
    from lexibrary.utils.paths import LEXIBRARY_DIR, mirror_path  # noqa: PLC0415
    from lexibrary.wiki.index import ConceptIndex as _ConceptIndex  # noqa: PLC0415

    if not isinstance(config, LexibraryConfig):
        return None

    rel_target = str(target.relative_to(project_root))

    # Compute mirror path and check design file
    design_path = mirror_path(project_root, target)

    description: str | None = None
    is_stale = False
    design_content: str | None = None

    if design_path.exists():
        # Check staleness
        metadata = parse_design_file_metadata(design_path)
        if metadata is not None:
            try:
                current_hash = hashlib.sha256(target.read_bytes()).hexdigest()
                if current_hash != metadata.source_hash:
                    is_stale = True
            except OSError:
                pass

        # Parse frontmatter for description
        fm = parse_design_file_frontmatter(design_path)
        if fm is not None:
            description = fm.description

        if full:
            design_content = design_path.read_text(encoding="utf-8")
    else:
        design_content = None

    # Sibling population from parent .aindex
    aindex_path = project_root / LEXIBRARY_DIR / "designs" / Path(rel_target).parent / ".aindex"
    aindex = parse_aindex(aindex_path)
    siblings_list: list[SiblingSummary] = []
    if aindex is not None:
        siblings_list = [
            SiblingSummary(name=entry.name, description=entry.description)
            for entry in aindex.entries
            if entry.entry_type == "file"
        ]

    # Convention delivery
    conventions_dir = project_root / ".lexibrary" / "conventions"
    convention_index = ConventionIndex(conventions_dir)
    convention_index.load()

    conventions_list: list[ConventionFile] = []
    total_count = 0

    if full:
        display_limit = config.conventions.lookup_display_limit
    else:
        display_limit = min(config.conventions.lookup_display_limit, 5)

    if len(convention_index) > 0:
        conventions_list, total_count = convention_index.find_by_scope_limited(
            rel_target,
            scope_root=config.scope_root,
            limit=display_limit,
        )

    # Triggered playbooks
    playbooks_dir = project_root / ".lexibrary" / "playbooks"
    playbook_index = PlaybookIndex(playbooks_dir)
    playbook_index.load()
    triggered_playbooks = playbook_index.by_trigger_file(rel_target)

    if full:
        pb_display_limit = config.playbooks.lookup_display_limit
    else:
        pb_display_limit = min(config.playbooks.lookup_display_limit, 5)

    # Link graph queries
    link_graph = open_index(project_root)
    issues_text = ""
    links_text = ""
    dependents: list[str] = []
    open_issue_count = 0
    # Concept link data gathered from link graph (used in full mode)
    concept_link_names: list[str] = []

    if link_graph is not None:
        if full:
            # Full mode: gather known issues text
            stack_display_limit = config.stack.lookup_display_limit
            issues_text = _build_known_issues(
                link_graph, rel_target, project_root, stack_display_limit
            )

            # Dependents: inbound ast_import links
            import_links = link_graph.reverse_deps(rel_target, link_type="ast_import")
            links_text_parts: list[str] = []
            if import_links:
                links_text_parts.append("\n## Dependents (imports this file)\n")
                for link in import_links:
                    links_text_parts.append(f"- {link.source_path}")
                    dependents.append(link.source_path)
                links_text_parts.append("")

            # Also Referenced By: all other inbound link types
            link_type_labels: dict[str, str] = {
                "wikilink": "concept wikilink",
                "stack_file_ref": "stack post",
                "stack_concept_ref": "stack concept ref",
                "design_stack_ref": "design stack ref",
                "design_source": "design file",
                "concept_file_ref": "concept file ref",
                "convention_concept_ref": "convention concept ref",
            }
            all_links = link_graph.reverse_deps(rel_target)
            # Exclude ast_import (shown in Dependents) and the file's own design file
            rel_design = str(design_path.relative_to(project_root))
            other_links = [
                lnk
                for lnk in all_links
                if lnk.link_type != "ast_import"
                and not (lnk.link_type == "design_source" and lnk.source_path == rel_design)
            ]
            if other_links:
                links_text_parts.append("\n## Also Referenced By\n")
                for link in other_links:
                    label = link_type_labels.get(link.link_type, link.link_type)
                    display_name = link.link_context or link.source_path
                    links_text_parts.append(f"- [[{display_name}]] ({label})")
                links_text_parts.append("")

            links_text = "\n".join(links_text_parts)

            # Gather concept names from link graph (wikilink + concept_file_ref)
            concept_links = [
                lnk for lnk in all_links if lnk.link_type in ("wikilink", "concept_file_ref")
            ]
            seen_concept_names: set[str] = set()
            for lnk in concept_links:
                name = lnk.link_context or lnk.source_path
                if name not in seen_concept_names:
                    seen_concept_names.add(name)
                    concept_link_names.append(name)
        else:
            # Brief mode: just count open issues
            stack_links = link_graph.reverse_deps(rel_target, link_type="stack_file_ref")
            for slink in stack_links:
                post_path = project_root / slink.source_path
                post = parse_stack_post(post_path)
                if post is not None and post.frontmatter.status == "open":
                    open_issue_count += 1

        link_graph.close()

    # Concept population
    concepts_list: list[ConceptSummary] = []
    linkgraph_available = True
    concept_limit = config.concepts.lookup_display_limit

    # Load concept index for enriching status/summary
    concepts_dir = project_root / ".lexibrary" / "concepts"
    concept_index = _ConceptIndex.load(concepts_dir)

    if full and concept_link_names:
        # Full mode with link graph: use link graph concept names
        for name in concept_link_names:
            concept_file = concept_index.find(name)
            if concept_file is not None:
                concepts_list.append(
                    ConceptSummary(
                        name=name,
                        status=concept_file.frontmatter.status,
                        summary=concept_file.summary or None,
                    )
                )
            else:
                concepts_list.append(ConceptSummary(name=name, status=None, summary=None))
    else:
        # Brief mode, or full mode without link graph: use design file wikilinks
        if full and link_graph is None:
            linkgraph_available = False

        wikilink_names: list[str] = []
        if design_path.exists():
            design_file = parse_design_file(design_path)
            if design_file is not None:
                wikilink_names = design_file.wikilinks

        for name in wikilink_names:
            concept_file = concept_index.find(name)
            status = concept_file.frontmatter.status if concept_file is not None else None
            summary = (concept_file.summary or None) if concept_file is not None and full else None
            concepts_list.append(ConceptSummary(name=name, status=status, summary=summary))

    # Apply display limit
    concepts_list = concepts_list[:concept_limit]

    # IWH signal peek
    iwh_text = _build_iwh_peek(project_root, target)

    return LookupResult(
        file_path=rel_target,
        description=description,
        is_stale=is_stale,
        design_content=design_content,
        conventions=conventions_list,
        conventions_total_count=total_count,
        display_limit=display_limit,
        playbooks=triggered_playbooks,
        playbook_display_limit=pb_display_limit,
        issues_text=issues_text,
        iwh_text=iwh_text,
        links_text=links_text,
        dependents=dependents,
        open_issue_count=open_issue_count,
        siblings=siblings_list,
        concepts=concepts_list,
        concepts_linkgraph_available=linkgraph_available,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_iwh_peek(
    project_root: Path,
    target: Path,
) -> str:
    """Build IWH signal peek text without consuming the signal.

    Checks for an IWH file in the mirror directory corresponding to *target*
    (which may be a file or directory).  Returns rendered text or empty string.
    """
    from lexibrary.iwh.reader import read_iwh  # noqa: PLC0415
    from lexibrary.utils.paths import LEXIBRARY_DIR  # noqa: PLC0415

    # For a file, the IWH lives in the parent's mirror directory
    # For a directory, it lives in the directory's own mirror
    if target.is_file():
        rel = target.parent.relative_to(project_root)
    else:
        rel = target.relative_to(project_root)

    # Check the designs mirror tree for IWH signals
    iwh_dir = project_root / LEXIBRARY_DIR / "designs" / rel
    iwh = None
    if iwh_dir.is_dir():
        iwh = read_iwh(iwh_dir)

    if iwh is None:
        # Also check legacy mirror path (without designs/)
        iwh_dir = project_root / LEXIBRARY_DIR / rel
        if iwh_dir.is_dir():
            iwh = read_iwh(iwh_dir)

    if iwh is None:
        return ""

    lines: list[str] = ["\n## IWH Signal\n"]
    lines.append(f"- Scope: {iwh.scope}")
    lines.append(f"- Author: {iwh.author}")
    lines.append(f"- Created: {iwh.created.isoformat()}")
    if iwh.body:
        # Truncate body preview to first 200 chars
        body_preview = iwh.body[:200]
        if len(iwh.body) > 200:
            body_preview += "..."
        lines.append(f"- Body: {body_preview}")
    lines.append("")
    lines.append("Run `lexi iwh read <directory>` to consume this signal.")
    lines.append("")

    return "\n".join(lines)


def _build_known_issues(
    link_graph: object,
    rel_path: str,
    project_root: Path,
    display_limit: int,
) -> str:
    """Build known-issues text from stack_file_ref links.

    Queries the link graph for ``stack_file_ref`` links pointing to *rel_path*,
    parses each matching Stack post, and builds a summary with status, title,
    attempts count, and votes.

    Posts with ``stale`` status are excluded.  Open posts are shown first,
    then resolved posts, up to *display_limit*.

    Returns the rendered text (empty string if no issues found).
    """
    from lexibrary.linkgraph.query import LinkGraph  # noqa: PLC0415
    from lexibrary.stack.parser import parse_stack_post  # noqa: PLC0415

    if not isinstance(link_graph, LinkGraph):
        return ""

    stack_links = link_graph.reverse_deps(rel_path, link_type="stack_file_ref")
    if not stack_links:
        return ""

    # Parse each referenced stack post
    posts = []
    for link in stack_links:
        post_path = project_root / link.source_path
        post = parse_stack_post(post_path)
        if post is None:
            continue
        # Exclude stale posts
        if post.frontmatter.status == "stale":
            continue
        posts.append(post)

    if not posts:
        return ""

    # Sort: open first, then resolved; within each group sort by votes descending
    status_order = {"open": 0, "resolved": 1, "outdated": 2, "duplicate": 3}
    posts.sort(key=lambda p: (status_order.get(p.frontmatter.status, 9), -p.frontmatter.votes))

    # Apply display limit
    shown = posts[:display_limit]
    omitted = len(posts) - len(shown)

    lines: list[str] = ["\n## Known Issues\n"]
    for post in shown:
        status_label = post.frontmatter.status
        attempts_count = len(post.attempts)
        attempts_str = f", {attempts_count} attempts" if attempts_count > 0 else ""
        votes_str = f", {post.frontmatter.votes} votes" if post.frontmatter.votes > 0 else ""
        lines.append(f"- [{status_label}] {post.frontmatter.title}{attempts_str}{votes_str}")
    if omitted > 0:
        lines.append(f"\n... and {omitted} more issues")
    lines.append("")

    return "\n".join(lines)
