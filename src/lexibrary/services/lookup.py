"""Lookup service — data-gathering logic for file and directory lookups.

Extracts the business logic from the ``lexi lookup`` CLI handler into
pure-data service functions that return result dataclasses.  No terminal
output or CLI dependencies.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lexibrary.artifacts.convention import ConventionFile
    from lexibrary.artifacts.design_file import CallPathNote, DataFlowNote, EnumNote
    from lexibrary.artifacts.playbook import PlaybookFile

_logger = logging.getLogger(__name__)


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
class ClassHierarchyEntry:
    """A class symbol declared in a file, with hierarchy counts.

    Populated by :func:`build_file_lookup` from the symbol graph for the
    "Class hierarchy" section of ``lexi lookup``. ``bases`` and
    ``unresolved_bases`` come from the outbound ``class_edges`` filtered
    to ``edge_type='inherits'`` plus ``class_edges_unresolved`` rows for
    the same source; ``subclass_count`` counts inbound inherits edges.
    ``method_count`` reflects every ``method`` symbol in the same file
    whose qualified name starts with this class's qualified-name
    prefix — the renderer uses this to size the hierarchy table without
    hitting the symbol graph a second time.
    """

    class_name: str  # bare class identifier (e.g., "LexibraryConfig")
    bases: list[str]  # resolved base class names, ordered by class_edges sort
    unresolved_bases: list[str]  # out-of-scope bases (e.g., ``BaseModel``)
    subclass_count: int  # number of inbound ``inherits`` edges
    method_count: int  # number of ``method`` symbols owned by this class
    line_start: int  # 1-based source line of the class header


@dataclass
class KeySymbolSummary:
    """A public symbol declared in a file, with caller/callee counts.

    Populated by :func:`build_file_lookup` from the symbol graph for the
    "Key symbols" section of ``lexi lookup``. Methods are rendered under
    their parent class by the render layer; the ``qualified_name`` is used
    to derive the ``Class.method`` display form.

    ``caller_count`` / ``callee_count`` come from a single
    :meth:`~lexibrary.symbolgraph.query.SymbolGraph.symbol_call_counts`
    query per file, so the renderer never has to issue a second query per
    symbol.
    """

    name: str  # bare identifier (e.g., "update_project")
    qualified_name: str | None  # dotted path (e.g., "pkg.mod.Class.method")
    symbol_type: str  # 'function' | 'class' | 'method'
    line_start: int  # 1-based source line
    caller_count: int  # inbound call edges (how many callers point at this symbol)
    callee_count: int  # outbound call edges (how many callees this symbol invokes)


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

    key_symbols: list[KeySymbolSummary] = field(default_factory=list)
    """Public top-level symbols declared in this file, capped at 10 entries.

    Populated from the symbol graph when ``config.symbols.enabled`` is True
    and ``symbols.db`` exists. Empty when symbols are disabled, the graph is
    missing, or the file has no public symbols.
    """

    key_symbols_total: int = 0
    """Pre-cap count of public symbols in this file.

    When ``key_symbols_total > len(key_symbols)``, the render layer emits a
    ``… and N more`` overflow marker. Stays at ``0`` when ``key_symbols``
    itself is empty.
    """

    classes: list[ClassHierarchyEntry] = field(default_factory=list)
    """Class symbols declared in this file with hierarchy counts.

    Populated from the symbol graph's ``class_edges`` and
    ``class_edges_unresolved`` tables when ``config.symbols.enabled`` is
    True and ``symbols.db`` exists. Empty when symbols are disabled, the
    graph is missing, or the file declares no classes.
    """

    enum_notes: list[EnumNote] = field(default_factory=list)
    """Enum/constant notes parsed from the design file's ``## Enums & constants``
    section.

    Populated from :class:`lexibrary.artifacts.design_file.DesignFile.enum_notes`
    when the design file exists and contains the enrichment section.  Empty
    when the design file is missing, the section is absent, or parsing fails.
    Surfaced by :func:`lexibrary.services.lookup_render.render_enum_notes` in
    full-mode lookup output.
    """

    call_path_notes: list[CallPathNote] = field(default_factory=list)
    """Narrative call-path notes parsed from the design file's ``## Call paths``
    section.

    Populated from
    :class:`lexibrary.artifacts.design_file.DesignFile.call_path_notes` when
    the design file exists and contains the enrichment section.  Empty when
    the design file is missing, the section is absent, or parsing fails.
    Surfaced by
    :func:`lexibrary.services.lookup_render.render_call_path_notes` in
    full-mode lookup output.
    """

    data_flow_notes: list[DataFlowNote] = field(default_factory=list)
    """Data-flow notes parsed from the design file's ``## Data flows`` section.

    Populated from
    :class:`lexibrary.artifacts.design_file.DesignFile.data_flow_notes` when
    the design file exists and contains the enrichment section.  Empty when
    the design file is missing, the section is absent, or parsing fails.
    Surfaced by
    :func:`lexibrary.services.lookup_render.render_data_flow_notes` in
    full-mode lookup output.
    """


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
        conventions_list, total_count = convention_index.find_by_any_scope_limited(
            rel_target,
            config.scope_roots,
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

    from lexibrary.artifacts.design_file import DesignFile  # noqa: PLC0415

    rel_target = str(target.relative_to(project_root))

    # Compute mirror path and check design file
    design_path = mirror_path(project_root, target)

    description: str | None = None
    is_stale = False
    design_content: str | None = None
    # Parsed design file is cached so the concept-population branch and the
    # enrichment-section population both reuse a single parse.  Stays ``None``
    # when the design file is missing or unparseable.
    parsed_design_file: DesignFile | None = None
    enum_notes_list: list[EnumNote] = []
    call_path_notes_list: list[CallPathNote] = []
    data_flow_notes_list: list[DataFlowNote] = []

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

        # Parse the full design file once so the symbol-graph enrichment
        # sections (``## Enums & constants`` and ``## Call paths``) can be
        # surfaced by the renderer.  The concept-population branch reuses
        # this parse for wikilink fallback.
        parsed_design_file = parse_design_file(design_path)
        if parsed_design_file is not None:
            enum_notes_list = list(parsed_design_file.enum_notes)
            call_path_notes_list = list(parsed_design_file.call_path_notes)
            data_flow_notes_list = list(parsed_design_file.data_flow_notes)

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
        conventions_list, total_count = convention_index.find_by_any_scope_limited(
            rel_target,
            config.scope_roots,
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

    # Open a single SymbolQueryService for the remainder of build_file_lookup.
    # This service owns both ``symbols.db`` (_symbol_graph) and ``index.db``
    # (_link_graph), so we reuse its _link_graph for the link-graph queries
    # below instead of making a separate open_index() call.  When the service
    # is ineligible (disabled, DB missing) we fall back to a standalone
    # open_index() call so link-graph data is still available.
    _symbols_eligible = _symbols_section_eligible(project_root, config)

    from lexibrary.services.symbols import SymbolQueryService  # noqa: PLC0415

    _service: SymbolQueryService | None = None
    if _symbols_eligible:
        _service = SymbolQueryService(project_root)
        _service.open()

    try:
        # Resolve the link graph: prefer the service's already-open handle.
        link_graph = (
            _service._link_graph  # noqa: SLF001
            if _service is not None
            else open_index(project_root)
        )

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

            # Only close the link graph when we opened it standalone (i.e., no
            # service).  When _service owns it, closing is handled in the
            # finally block below.
            if _service is None:
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
            if parsed_design_file is not None:
                wikilink_names = parsed_design_file.wikilinks

            for name in wikilink_names:
                concept_file = concept_index.find(name)
                status = concept_file.frontmatter.status if concept_file is not None else None
                summary = (
                    (concept_file.summary or None) if concept_file is not None and full else None
                )
                concepts_list.append(ConceptSummary(name=name, status=status, summary=summary))

        # Apply display limit
        concepts_list = concepts_list[:concept_limit]

        # Key symbols and class hierarchy reuse the already-open service.
        key_symbols: list[KeySymbolSummary] = []
        key_symbols_total = 0
        classes_list: list[ClassHierarchyEntry] = []

        if _service is not None:
            key_symbols, key_symbols_total = _build_key_symbols_with_service(rel_target, _service)
            classes_list = _build_class_hierarchy_with_service(rel_target, _service)

    finally:
        if _service is not None:
            _service.close()

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
        key_symbols=key_symbols,
        key_symbols_total=key_symbols_total,
        classes=classes_list,
        enum_notes=enum_notes_list,
        call_path_notes=call_path_notes_list,
        data_flow_notes=data_flow_notes_list,
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


_KEY_SYMBOLS_DISPLAY_CAP = 10


def _symbols_section_eligible(project_root: Path, config: object) -> bool:
    """Return ``True`` when the symbol-graph sections should be populated.

    Both :func:`_build_key_symbols_with_service` and
    :func:`_build_class_hierarchy_with_service` share the same eligibility
    gate: the config must be a :class:`~lexibrary.config.schema.LexibraryConfig`
    with ``symbols.enabled`` set and ``symbols.db`` present on disk.

    Centralising the check here lets :func:`build_file_lookup` decide once
    whether to open a :class:`~lexibrary.services.symbols.SymbolQueryService`
    rather than rediscovering the answer inside each helper.
    """
    from lexibrary.config.schema import LexibraryConfig  # noqa: PLC0415
    from lexibrary.utils.paths import symbols_db_path  # noqa: PLC0415

    if not isinstance(config, LexibraryConfig):
        _logger.debug("Symbol sections skipped: config is not a LexibraryConfig.")
        return False

    if not config.symbols.enabled:
        _logger.debug("Symbol sections skipped: config.symbols.enabled is False.")
        return False

    if not symbols_db_path(project_root).exists():
        _logger.debug("Symbol sections skipped: symbols.db is missing.")
        return False

    return True


def _build_key_symbols_with_service(
    rel_target: str,
    service: object,
) -> tuple[list[KeySymbolSummary], int]:
    """Gather public symbols using an already-open *service*.

    Returns ``(summaries, total_count)`` where *summaries* is capped at
    :data:`_KEY_SYMBOLS_DISPLAY_CAP` and *total_count* reflects the
    pre-cap number of matching symbols so the renderer can emit a
    ``… and N more`` overflow marker.

    *service* must be a :class:`~lexibrary.services.symbols.SymbolQueryService`
    that has already been opened by the caller (via ``.open()`` or as a context
    manager). The caller is responsible for closing it.

    The helper calls :meth:`SymbolGraph.symbol_call_counts` exactly **once** to
    get the ``(caller_count, callee_count)`` mapping — never per-symbol. The
    filter keeps public top-level functions and classes (``visibility ==
    "public"``) plus every ``method`` (regardless of visibility) so the
    render layer can group methods under their parent class.

    Returns ``([], 0)`` when ``service._symbol_graph`` is ``None`` (race
    condition or corrupt schema after the eligibility check).
    """
    from lexibrary.services.symbols import SymbolQueryService  # noqa: PLC0415

    assert isinstance(service, SymbolQueryService)

    if service._symbol_graph is None:  # noqa: SLF001
        # open() could not attach even though the DB existed when we checked.
        _logger.debug("Key symbols skipped: symbol graph unavailable after open().")
        return [], 0

    response = service.symbols_in_file(rel_target)
    # ``symbol_call_counts`` is the single-query aggregation helper —
    # never issue ``callers_of`` / ``callees_of`` per symbol here.
    counts = service._symbol_graph.symbol_call_counts(rel_target)  # noqa: SLF001

    matches: list[KeySymbolSummary] = []
    for row in response.symbols:
        if row.symbol_type in ("function", "class"):
            if row.visibility != "public":
                continue
        elif row.symbol_type == "method":
            pass
        else:
            # enums, constants, etc. are surfaced by different phases
            continue

        caller_count, callee_count = counts.get(row.id, (0, 0))
        matches.append(
            KeySymbolSummary(
                name=row.name,
                qualified_name=row.qualified_name,
                symbol_type=row.symbol_type,
                line_start=row.line_start if row.line_start is not None else 0,
                caller_count=caller_count,
                callee_count=callee_count,
            )
        )

    total = len(matches)
    return matches[:_KEY_SYMBOLS_DISPLAY_CAP], total


def _build_class_hierarchy_with_service(
    rel_target: str,
    service: object,
) -> list[ClassHierarchyEntry]:
    """Gather class-hierarchy entries using an already-open *service*.

    Returns one :class:`ClassHierarchyEntry` per class symbol declared in
    *rel_target*, in source order.

    *service* must be a :class:`~lexibrary.services.symbols.SymbolQueryService`
    that has already been opened by the caller. The caller is responsible for
    closing it.

    Returns ``[]`` when ``service._symbol_graph`` is ``None`` or the file
    contains no class symbols.

    For each class the helper:

    - Queries :meth:`SymbolGraph.class_edges_from` filtered to
      ``edge_type == "inherits"`` for the resolved base-class names.
    - Queries :meth:`SymbolGraph.class_edges_unresolved_from` filtered to
      ``edge_type == "inherits"`` for out-of-scope bases (``BaseModel``,
      ``Enum``, ...).
    - Queries :meth:`SymbolGraph.class_edges_to` and counts rows whose
      ``edge_type == "inherits"`` to derive ``subclass_count``.
    - Counts methods owned by this class via ``symbols_in_file`` — every
      symbol whose ``symbol_type == "method"`` and whose ``qualified_name``
      equals ``"{class.qualified_name}.{method.name}"``.
    """
    from lexibrary.services.symbols import SymbolQueryService  # noqa: PLC0415

    assert isinstance(service, SymbolQueryService)

    if service._symbol_graph is None:  # noqa: SLF001
        _logger.debug("Class hierarchy skipped: symbol graph unavailable after open().")
        return []

    response = service.symbols_in_file(rel_target)
    symbol_rows = response.symbols
    class_rows = [row for row in symbol_rows if row.symbol_type == "class"]
    if not class_rows:
        return []

    graph = service._symbol_graph  # noqa: SLF001

    entries: list[ClassHierarchyEntry] = []
    for class_row in class_rows:
        outbound = graph.class_edges_from(class_row.id)
        bases = [edge.target.name for edge in outbound if edge.edge_type == "inherits"]

        unresolved = graph.class_edges_unresolved_from(class_row.id)
        unresolved_bases = [row.target_name for row in unresolved if row.edge_type == "inherits"]

        inbound = graph.class_edges_to(class_row.id)
        subclass_count = sum(1 for edge in inbound if edge.edge_type == "inherits")

        # Method count: every method in the same file whose qualified
        # name is ``<class.qualified_name>.<method.name>``. Fall back
        # to the ``parent_class_name``-matching heuristic on
        # ``line_start`` when the class lacks a qualified name (e.g.
        # anonymous class definitions the parser only captured by
        # bare name).
        method_count = 0
        if class_row.qualified_name is not None:
            prefix = f"{class_row.qualified_name}."
            for row in symbol_rows:
                if row.symbol_type != "method":
                    continue
                if row.qualified_name is None:
                    continue
                if row.qualified_name == f"{prefix}{row.name}":
                    method_count += 1
        else:
            # Without a qualified name the best we can do is bound
            # methods by the class's source range. ``line_end`` is
            # optional on :class:`SymbolRow`, so fall back to the
            # class start line when it is missing.
            start = class_row.line_start or 0
            end = class_row.line_end or start
            for row in symbol_rows:
                if row.symbol_type != "method":
                    continue
                row_line = row.line_start or 0
                if start <= row_line <= end:
                    method_count += 1

        entries.append(
            ClassHierarchyEntry(
                class_name=class_row.name,
                bases=bases,
                unresolved_bases=unresolved_bases,
                subclass_count=subclass_count,
                method_count=method_count,
                line_start=class_row.line_start if class_row.line_start is not None else 0,
            )
        )

    return entries
