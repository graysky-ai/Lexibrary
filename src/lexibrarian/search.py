"""Unified cross-artifact search for concepts, design files, and Stack posts."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console
from rich.table import Table

if TYPE_CHECKING:
    from lexibrarian.linkgraph.query import LinkGraph


@dataclass
class SearchResults:
    """Container for grouped search results across artifact types."""

    concepts: list[_ConceptResult] = field(default_factory=list)
    design_files: list[_DesignFileResult] = field(default_factory=list)
    stack_posts: list[_StackResult] = field(default_factory=list)

    def has_results(self) -> bool:
        """Return True if any group has results."""
        return bool(self.concepts or self.design_files or self.stack_posts)

    def render(self, console: Console) -> None:
        """Render grouped results with Rich formatting."""
        if self.concepts:
            console.print()
            table = Table(title="Concepts")
            table.add_column("Name", style="cyan")
            table.add_column("Status")
            table.add_column("Tags")
            table.add_column("Summary", max_width=50)
            for c in self.concepts:
                status_style = {
                    "active": "green",
                    "draft": "yellow",
                    "deprecated": "red",
                }.get(c.status, "dim")
                table.add_row(
                    c.name,
                    f"[{status_style}]{c.status}[/{status_style}]",
                    ", ".join(c.tags),
                    c.summary[:50] if c.summary else "",
                )
            console.print(table)

        if self.design_files:
            console.print()
            table = Table(title="Design Files")
            table.add_column("Source", style="cyan")
            table.add_column("Description", max_width=60)
            table.add_column("Tags")
            for d in self.design_files:
                table.add_row(
                    d.source_path,
                    d.description[:60] if d.description else "",
                    ", ".join(d.tags),
                )
            console.print(table)

        if self.stack_posts:
            console.print()
            table = Table(title="Stack")
            table.add_column("ID", style="cyan")
            table.add_column("Status")
            table.add_column("Votes", justify="right")
            table.add_column("Title")
            table.add_column("Tags")
            for s in self.stack_posts:
                status_style = {
                    "open": "green",
                    "resolved": "blue",
                    "outdated": "yellow",
                    "duplicate": "red",
                }.get(s.status, "dim")
                table.add_row(
                    s.post_id,
                    f"[{status_style}]{s.status}[/{status_style}]",
                    str(s.votes),
                    s.title,
                    ", ".join(s.tags),
                )
            console.print(table)


@dataclass
class _ConceptResult:
    name: str
    status: str
    tags: list[str]
    summary: str


@dataclass
class _DesignFileResult:
    source_path: str
    description: str
    tags: list[str]


@dataclass
class _StackResult:
    post_id: str
    title: str
    status: str
    votes: int
    tags: list[str]


def unified_search(
    project_root: Path,
    *,
    query: str | None = None,
    tag: str | None = None,
    scope: str | None = None,
    link_graph: LinkGraph | None = None,
) -> SearchResults:
    """Search across concepts, design files, and Stack posts.

    When *link_graph* is provided and *tag* is specified, the function uses
    the index-accelerated code path (O(1) tag lookup via the ``tags`` table)
    instead of scanning artifact files.  When *link_graph* is provided and
    a free-text *query* is given (without *tag*), the function uses FTS5
    full-text search for relevance-ranked results.  When *link_graph* is
    ``None``, the existing file-scanning code paths are used as a fallback
    for both tag and free-text queries.

    Args:
        project_root: Absolute path to the project root.
        query: Free-text search query (matches titles, summaries, bodies).
        tag: Filter by tag across all artifact types.
        scope: Filter by file scope path.
        link_graph: Optional :class:`LinkGraph` instance for index-accelerated
            queries.  When ``None``, file-scanning fallback is used.

    Returns:
        Grouped :class:`SearchResults`.
    """
    # --- Index-accelerated tag search ---
    if link_graph is not None and tag is not None:
        return _tag_search_from_index(link_graph, tag=tag, scope=scope)

    # --- FTS-accelerated free-text search (index available, query without tag) ---
    if link_graph is not None and query is not None and tag is None:
        return _fts_search(link_graph, query=query, scope=scope)

    # --- Fallback: file-scanning search ---
    results = SearchResults()

    # --- Concepts ---
    results.concepts = _search_concepts(project_root, query=query, tag=tag, scope=scope)

    # --- Design Files ---
    results.design_files = _search_design_files(project_root, query=query, tag=tag, scope=scope)

    # --- Stack Posts ---
    results.stack_posts = _search_stack_posts(project_root, query=query, tag=tag, scope=scope)

    return results


# ---------------------------------------------------------------------------
# Index-accelerated tag search
# ---------------------------------------------------------------------------

# Mapping from LinkGraph artifact ``kind`` to SearchResults group name.
_KIND_CONCEPT = "concept"
_KIND_DESIGN = "design"
_KIND_STACK = "stack"


def _tag_search_from_index(
    link_graph: LinkGraph,
    *,
    tag: str,
    scope: str | None,
) -> SearchResults:
    """Perform tag search using the link graph index.

    Queries ``link_graph.search_by_tag()`` and groups results into
    :class:`SearchResults` by artifact kind.  When *scope* is also
    provided, results are filtered to only include artifacts whose
    path starts with the scope prefix.

    Concepts are never file-scoped, so when a scope filter is active
    concept results are omitted (consistent with the file-scanning
    fallback).
    """
    tag_lower = tag.strip().lower()
    hits = link_graph.search_by_tag(tag_lower)

    results = SearchResults()

    for hit in hits:
        # Apply scope filter: skip artifacts whose path does not match
        if scope is not None:
            # Concepts are not file-scoped; omit them when scope is active
            if hit.kind == _KIND_CONCEPT:
                continue
            if not hit.path.startswith(scope):
                continue

        if hit.kind == _KIND_CONCEPT:
            results.concepts.append(
                _ConceptResult(
                    name=hit.title or hit.path,
                    status=hit.status or "active",
                    tags=[tag],
                    summary="",
                )
            )
        elif hit.kind == _KIND_DESIGN:
            results.design_files.append(
                _DesignFileResult(
                    source_path=hit.path,
                    description=hit.title or "",
                    tags=[tag],
                )
            )
        elif hit.kind == _KIND_STACK:
            results.stack_posts.append(
                _StackResult(
                    post_id=hit.path,
                    title=hit.title or "",
                    status=hit.status or "open",
                    votes=0,
                    tags=[tag],
                )
            )

    return results


# ---------------------------------------------------------------------------
# FTS-accelerated free-text search
# ---------------------------------------------------------------------------


def _fts_search(
    link_graph: LinkGraph,
    *,
    query: str,
    scope: str | None,
) -> SearchResults:
    """Perform full-text search using the link graph FTS5 index.

    Queries ``link_graph.full_text_search()`` and groups results into
    :class:`SearchResults` by artifact kind.  Title metadata is included
    directly from the ``artifacts`` table (via :class:`ArtifactResult`),
    so no additional file I/O is required.

    When *scope* is provided, results are filtered to only include
    artifacts whose path starts with the scope prefix.  Concepts are
    never file-scoped, so when a scope filter is active concept results
    are omitted (consistent with the file-scanning fallback).
    """
    hits = link_graph.full_text_search(query)

    results = SearchResults()

    for hit in hits:
        # Apply scope filter: skip artifacts whose path does not match
        if scope is not None:
            # Concepts are not file-scoped; omit them when scope is active
            if hit.kind == _KIND_CONCEPT:
                continue
            if not hit.path.startswith(scope):
                continue

        if hit.kind == _KIND_CONCEPT:
            results.concepts.append(
                _ConceptResult(
                    name=hit.title or hit.path,
                    status=hit.status or "active",
                    tags=[],
                    summary="",
                )
            )
        elif hit.kind == _KIND_DESIGN:
            results.design_files.append(
                _DesignFileResult(
                    source_path=hit.path,
                    description=hit.title or "",
                    tags=[],
                )
            )
        elif hit.kind == _KIND_STACK:
            results.stack_posts.append(
                _StackResult(
                    post_id=hit.path,
                    title=hit.title or "",
                    status=hit.status or "open",
                    votes=0,
                    tags=[],
                )
            )

    return results


def _search_concepts(
    project_root: Path,
    *,
    query: str | None,
    tag: str | None,
    scope: str | None,
) -> list[_ConceptResult]:
    """Search concepts via ConceptIndex."""
    from lexibrarian.wiki.index import ConceptIndex

    concepts_dir = project_root / ".lexibrary" / "concepts"
    index = ConceptIndex.load(concepts_dir)

    if len(index) == 0:
        return []

    # Scope filter does not apply to concepts (they are not file-scoped)
    if scope is not None:
        return []

    if tag is not None:
        matches = index.by_tag(tag)
    elif query is not None:
        matches = index.search(query)
    else:
        return []

    return [
        _ConceptResult(
            name=c.frontmatter.title,
            status=c.frontmatter.status,
            tags=list(c.frontmatter.tags),
            summary=c.summary,
        )
        for c in matches
    ]


def _search_design_files(
    project_root: Path,
    *,
    query: str | None,
    tag: str | None,
    scope: str | None,
) -> list[_DesignFileResult]:
    """Search design files by scanning YAML frontmatter and tags."""
    from lexibrarian.artifacts.design_file_parser import parse_design_file

    lexibrary_dir = project_root / ".lexibrary"
    if not lexibrary_dir.is_dir():
        return []

    results: list[_DesignFileResult] = []

    # Scan all .md files in .lexibrary/ (excluding concepts/ and stack/)
    for md_path in sorted(lexibrary_dir.rglob("*.md")):
        # Skip non-design-file directories
        rel = md_path.relative_to(lexibrary_dir)
        parts = rel.parts
        if parts and parts[0] in ("concepts", "stack"):
            continue
        # Skip known non-design files
        if md_path.name in ("START_HERE.md", "HANDOFF.md"):
            continue

        design = parse_design_file(md_path)
        if design is None:
            continue

        # Apply scope filter
        if scope is not None and not design.source_path.startswith(scope):
            continue

        # Apply tag filter
        if tag is not None:
            tag_lower = tag.strip().lower()
            if not any(t.lower() == tag_lower for t in design.tags):
                continue

        # Apply free-text query filter
        if query is not None:
            needle = query.strip().lower()
            searchable = (
                design.frontmatter.description.lower()
                + " "
                + design.source_path.lower()
                + " "
                + " ".join(t.lower() for t in design.tags)
            )
            if needle not in searchable:
                continue

        results.append(
            _DesignFileResult(
                source_path=design.source_path,
                description=design.frontmatter.description,
                tags=list(design.tags),
            )
        )

    return results


def _search_stack_posts(
    project_root: Path,
    *,
    query: str | None,
    tag: str | None,
    scope: str | None,
) -> list[_StackResult]:
    """Search Stack posts via StackIndex."""
    from lexibrarian.stack.index import StackIndex

    idx = StackIndex.build(project_root)
    if len(idx) == 0:
        return []

    # Start with all posts or query results
    matches = idx.search(query) if query is not None else list(idx)

    # Apply tag filter
    if tag is not None:
        tag_set = {p.frontmatter.id for p in idx.by_tag(tag)}
        matches = [p for p in matches if p.frontmatter.id in tag_set]

    # Apply scope filter
    if scope is not None:
        scope_set = {p.frontmatter.id for p in idx.by_scope(scope)}
        matches = [p for p in matches if p.frontmatter.id in scope_set]

    return [
        _StackResult(
            post_id=p.frontmatter.id,
            title=p.frontmatter.title,
            status=p.frontmatter.status,
            votes=p.frontmatter.votes,
            tags=list(p.frontmatter.tags),
        )
        for p in matches
    ]
