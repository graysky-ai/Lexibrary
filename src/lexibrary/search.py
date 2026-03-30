"""Unified cross-artifact search for concepts, conventions, design files, and Stack posts."""

from __future__ import annotations

import json as _json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from lexibrary.artifacts.ids import is_artifact_id, parse_artifact_id
from lexibrary.cli._format import OutputFormat, get_format
from lexibrary.cli._output import info, markdown_table
from lexibrary.conventions.parser import extract_rule

if TYPE_CHECKING:
    from lexibrary.linkgraph.query import ArtifactResult, LinkGraph


@dataclass
class SearchResults:
    """Container for grouped search results across artifact types."""

    concepts: list[_ConceptResult] = field(default_factory=list)
    conventions: list[_ConventionResult] = field(default_factory=list)
    design_files: list[_DesignFileResult] = field(default_factory=list)
    stack_posts: list[_StackResult] = field(default_factory=list)
    playbooks: list[_PlaybookResult] = field(default_factory=list)

    def has_results(self) -> bool:
        """Return True if any group has results."""
        return bool(
            self.concepts
            or self.conventions
            or self.design_files
            or self.stack_posts
            or self.playbooks
        )

    def render(self) -> None:
        """Render grouped results, respecting the global ``--format`` flag."""
        fmt = get_format()
        if fmt == OutputFormat.json:
            self._render_json()
        elif fmt == OutputFormat.plain:
            self._render_plain()
        else:
            self._render_markdown()

    # -- JSON rendering -----------------------------------------------------

    def _render_json(self) -> None:
        """Emit a single JSON array of result dicts."""
        records: list[dict[str, object]] = []
        for c in self.concepts:
            records.append({"name": c.name, "tags": c.tags, "status": c.status})
        for cv in self.conventions:
            records.append(
                {
                    "title": cv.title,
                    "scope": cv.scope,
                    "tags": cv.tags,
                    "status": cv.status,
                }
            )
        for s in self.stack_posts:
            records.append(
                {
                    "id": s.post_id,
                    "title": s.title,
                    "votes": s.votes,
                    "tags": s.tags,
                    "status": s.status,
                }
            )
        for d in self.design_files:
            records.append({"source": d.source_path, "description": d.description, "tags": d.tags})
        for pb in self.playbooks:
            records.append(
                {
                    "title": pb.title,
                    "status": pb.status,
                    "tags": pb.tags,
                    "overview": pb.overview,
                }
            )
        info(_json.dumps(records))

    # -- Plain (tab-separated) rendering ------------------------------------

    def _render_plain(self) -> None:
        """Emit tab-separated lines with no markdown formatting."""
        for c in self.concepts:
            info(f"{c.name}\t{', '.join(c.tags)}\t{c.status}")
        for cv in self.conventions:
            info(f"{cv.title}\t{cv.scope}\t{', '.join(cv.tags)}\t{cv.status}")
        for s in self.stack_posts:
            info(f"{s.post_id}\t{s.title}\t{s.votes}\t{', '.join(s.tags)}\t{s.status}")
        for d in self.design_files:
            info(f"{d.source_path}\t{d.description}\t{', '.join(d.tags)}")
        for pb in self.playbooks:
            info(f"{pb.title}\t{pb.status}\t{', '.join(pb.tags)}\t{pb.overview}")

    # -- Markdown rendering (original behaviour) ----------------------------

    def _render_markdown(self) -> None:
        """Render grouped results as plain Markdown tables."""
        if self.concepts:
            info("")
            info("## Concepts\n")
            rows = [
                [c.name, c.status, ", ".join(c.tags), c.summary[:50] if c.summary else ""]
                for c in self.concepts
            ]
            info(markdown_table(["Name", "Status", "Tags", "Summary"], rows))

        if self.conventions:
            info("")
            info("## Conventions\n")
            rows = [
                [
                    cv.title,
                    cv.scope,
                    cv.status,
                    cv.rule[:50] if cv.rule else "",
                    ", ".join(cv.tags),
                ]
                for cv in self.conventions
            ]
            info(markdown_table(["Title", "Scope", "Status", "Rule", "Tags"], rows))

        if self.design_files:
            info("")
            info("## Design Files\n")
            rows = [
                [d.source_path, d.description[:60] if d.description else "", ", ".join(d.tags)]
                for d in self.design_files
            ]
            info(markdown_table(["Source", "Description", "Tags"], rows))

        if self.stack_posts:
            info("")
            info("## Stack\n")
            rows = [
                [s.post_id, s.status, str(s.votes), s.title, ", ".join(s.tags)]
                for s in self.stack_posts
            ]
            info(markdown_table(["ID", "Status", "Votes", "Title", "Tags"], rows))

        if self.playbooks:
            info("")
            info("## Playbooks\n")
            rows = [
                [
                    pb.title,
                    pb.status,
                    pb.overview[:50] if pb.overview else "",
                    ", ".join(pb.tags),
                ]
                for pb in self.playbooks
            ]
            info(markdown_table(["Title", "Status", "Overview", "Tags"], rows))


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
class _ConventionResult:
    title: str
    scope: str
    status: str
    tags: list[str]
    rule: str


@dataclass
class _StackResult:
    post_id: str
    title: str
    status: str
    votes: int
    tags: list[str]


@dataclass
class _PlaybookResult:
    title: str
    status: str
    tags: list[str]
    overview: str


# Valid artifact type values for ``artifact_type`` parameter.
VALID_ARTIFACT_TYPES = ("concept", "convention", "design", "stack", "playbook")

# Map from 2-letter ID prefix to artifact kind (used for ID-based search).
_PREFIX_TO_KIND: dict[str, str] = {
    "CN": "concept",
    "CV": "convention",
    "PB": "playbook",
    "DS": "design",
    "ST": "stack",
}

# Map from artifact kind to the subdirectory under ``.lexibrary/``.
_KIND_TO_DIR: dict[str, str] = {
    "concept": "concepts",
    "convention": "conventions",
    "playbook": "playbooks",
    "design": "designs",
    "stack": "stack",
}


def _resolve_artifact_by_id(project_root: Path, artifact_id: str) -> SearchResults | None:
    """Attempt to resolve a single artifact by its ID (e.g. ``CN-001``, ``ST-042``).

    Scans the appropriate ``.lexibrary/<subdir>/`` directory for a file whose
    name starts with the artifact ID (for concepts, conventions, playbooks, and
    stack posts) or whose frontmatter ``id:`` field matches (for design files).

    Returns a :class:`SearchResults` containing the single matching artifact,
    or ``None`` if no match is found.
    """
    parsed = parse_artifact_id(artifact_id)
    if parsed is None:
        return None

    prefix, _number = parsed
    kind = _PREFIX_TO_KIND.get(prefix)
    if kind is None:
        return None

    subdir = _KIND_TO_DIR[kind]
    artifact_dir = project_root / ".lexibrary" / subdir

    if not artifact_dir.is_dir():
        return None

    results = SearchResults()

    if kind == "design":
        # Design files use source-mirror paths -- ID is in frontmatter only.
        return _resolve_design_by_id(artifact_dir, artifact_id)

    # For other artifact types, filenames are prefixed with the ID.
    matching_files = list(artifact_dir.glob(f"{artifact_id}-*"))
    if not matching_files:
        # Also try exact match (unlikely but defensive)
        matching_files = list(artifact_dir.glob(f"{artifact_id}.*"))
    if not matching_files:
        return None

    path = matching_files[0]

    if kind == "concept":
        concept_hit = _resolve_concept_file(path)
        if concept_hit is not None:
            results.concepts.append(concept_hit)
    elif kind == "convention":
        convention_hit = _resolve_convention_file(path)
        if convention_hit is not None:
            results.conventions.append(convention_hit)
    elif kind == "playbook":
        playbook_hit = _resolve_playbook_file(path)
        if playbook_hit is not None:
            results.playbooks.append(playbook_hit)
    elif kind == "stack":
        stack_hit = _resolve_stack_file(path)
        if stack_hit is not None:
            results.stack_posts.append(stack_hit)

    return results if results.has_results() else None


def _resolve_concept_file(path: Path) -> _ConceptResult | None:
    """Parse a concept file and return a ``_ConceptResult``."""
    from lexibrary.wiki.parser import parse_concept_file  # noqa: PLC0415

    concept = parse_concept_file(path)
    if concept is None:
        return None
    return _ConceptResult(
        name=concept.frontmatter.title,
        status=concept.frontmatter.status,
        tags=list(concept.frontmatter.tags),
        summary=concept.summary,
    )


def _resolve_convention_file(path: Path) -> _ConventionResult | None:
    """Parse a convention file and return a ``_ConventionResult``."""
    from lexibrary.conventions.parser import parse_convention_file  # noqa: PLC0415

    conv = parse_convention_file(path)
    if conv is None:
        return None
    return _ConventionResult(
        title=conv.frontmatter.title,
        scope=conv.frontmatter.scope,
        status=conv.frontmatter.status,
        tags=list(conv.frontmatter.tags),
        rule=conv.rule,
    )


def _resolve_playbook_file(path: Path) -> _PlaybookResult | None:
    """Parse a playbook file and return a ``_PlaybookResult``."""
    from lexibrary.playbooks.parser import parse_playbook_file  # noqa: PLC0415

    pb = parse_playbook_file(path)
    if pb is None:
        return None
    return _PlaybookResult(
        title=pb.frontmatter.title,
        status=pb.frontmatter.status,
        tags=list(pb.frontmatter.tags),
        overview=pb.overview,
    )


def _resolve_stack_file(path: Path) -> _StackResult | None:
    """Parse a stack post file and return a ``_StackResult``."""
    from lexibrary.stack.parser import parse_stack_post  # noqa: PLC0415

    post = parse_stack_post(path)
    if post is None:
        return None
    return _StackResult(
        post_id=post.frontmatter.id,
        title=post.frontmatter.title,
        status=post.frontmatter.status,
        votes=post.frontmatter.votes,
        tags=list(post.frontmatter.tags),
    )


def _resolve_design_by_id(designs_dir: Path, artifact_id: str) -> SearchResults | None:
    """Scan design file frontmatter for a matching ``id:`` field.

    Design files use source-mirror paths (no ID in filename), so we must
    scan the ``id`` field in each file's YAML frontmatter.
    """
    from lexibrary.artifacts.design_file_parser import parse_design_file  # noqa: PLC0415

    for md_path in designs_dir.rglob("*.md"):
        design = parse_design_file(md_path)
        if design is None:
            continue
        if design.frontmatter.id == artifact_id:
            results = SearchResults()
            results.design_files.append(
                _DesignFileResult(
                    source_path=design.source_path,
                    description=design.frontmatter.description,
                    tags=list(design.tags),
                )
            )
            return results
    return None


def unified_search(
    project_root: Path,
    *,
    query: str | None = None,
    tag: str | None = None,
    tags: list[str] | None = None,
    scope: str | None = None,
    link_graph: LinkGraph | None = None,
    artifact_type: str | None = None,
    status: str | None = None,
    include_deprecated: bool = False,
    concept: str | None = None,
    resolution_type: str | None = None,
    include_stale: bool = False,
) -> SearchResults:
    """Search across concepts, conventions, design files, and Stack posts.

    When *link_graph* is provided and *tag*/*tags* is specified, the function
    uses the index-accelerated code path (O(1) tag lookup via the ``tags``
    table) instead of scanning artifact files.  When *link_graph* is provided
    and a free-text *query* is given (without *tag*/*tags*), the function uses
    FTS5 full-text search for relevance-ranked results.  When *link_graph* is
    ``None``, the existing file-scanning code paths are used as a fallback
    for both tag and free-text queries.

    Args:
        project_root: Absolute path to the project root.
        query: Free-text search query (matches titles, summaries, bodies).
        tag: Filter by a single tag across all artifact types.  Convenience
            alias -- wraps into a single-element ``tags`` list.
        tags: Filter by multiple tags with AND logic (all tags must match).
        scope: Filter by file scope path.
        link_graph: Optional :class:`LinkGraph` instance for index-accelerated
            queries.  When ``None``, file-scanning fallback is used.
        artifact_type: Restrict search to a single artifact type.  Valid
            values: ``"concept"``, ``"convention"``, ``"design"``, ``"stack"``.
        status: Filter results by artifact status value.
        include_deprecated: When ``True``, include deprecated concepts and
            conventions (hidden by default).
        concept: Stack-only filter: match posts referencing this concept.
        resolution_type: Stack-only filter: match posts with this resolution
            type.
        include_stale: Stack-only: when ``True``, include stale posts
            (hidden by default).

    Returns:
        Grouped :class:`SearchResults`.
    """
    # --- ID-pattern short-circuit ---
    # When the query matches an artifact ID pattern (e.g. CN-001, ST-042) and
    # no other filters are active, attempt a direct lookup by ID.  If the ID
    # does not resolve to an existing artifact, fall back to the normal search
    # flow (treating the ID string as a free-text query).
    if (
        query is not None
        and is_artifact_id(query.strip())
        and tag is None
        and tags is None
        and scope is None
    ):
        id_result = _resolve_artifact_by_id(project_root, query.strip())
        if id_result is not None:
            return id_result
        # ID did not resolve -- fall through to normal search.

    # Normalise tag/tags: merge ``tag`` convenience alias into ``tags`` list.
    resolved_tags = _resolve_tags(tag=tag, tags=tags)

    # Pick the first tag for index-accelerated paths (they accept a single tag;
    # additional tags are applied as post-filters).
    first_tag = resolved_tags[0] if resolved_tags else None

    # --- Index-accelerated tag search ---
    if link_graph is not None and first_tag is not None:
        return _tag_search_from_index(
            link_graph,
            tag=first_tag,
            extra_tags=resolved_tags[1:],
            scope=scope,
            artifact_type=artifact_type,
            status=status,
            include_deprecated=include_deprecated,
            include_stale=include_stale,
        )

    # --- FTS-accelerated free-text search (index available, query without tag) ---
    if link_graph is not None and query is not None and first_tag is None:
        return _fts_search(
            link_graph,
            query=query,
            scope=scope,
            artifact_type=artifact_type,
            status=status,
            include_deprecated=include_deprecated,
            include_stale=include_stale,
        )

    # --- Fallback: file-scanning search ---
    results = SearchResults()

    # Determine which artifact types to search.
    search_concepts = artifact_type is None or artifact_type == "concept"
    search_conventions = artifact_type is None or artifact_type == "convention"
    search_designs = artifact_type is None or artifact_type == "design"
    search_stack = artifact_type is None or artifact_type == "stack"
    search_playbooks = artifact_type is None or artifact_type == "playbook"

    if search_concepts:
        results.concepts = _search_concepts(
            project_root,
            query=query,
            tag=first_tag,
            extra_tags=resolved_tags[1:] if resolved_tags else [],
            scope=scope,
            status=status,
            include_deprecated=include_deprecated,
        )

    if search_designs:
        results.design_files = _search_design_files(
            project_root,
            query=query,
            tag=first_tag,
            extra_tags=resolved_tags[1:] if resolved_tags else [],
            scope=scope,
            status=status,
        )

    if search_stack:
        results.stack_posts = _search_stack_posts(
            project_root,
            query=query,
            tag=first_tag,
            extra_tags=resolved_tags[1:] if resolved_tags else [],
            scope=scope,
            status=status,
            concept=concept,
            resolution_type=resolution_type,
            include_stale=include_stale,
        )

    if search_conventions:
        results.conventions = _search_conventions(
            project_root,
            query=query,
            tag=first_tag,
            extra_tags=resolved_tags[1:] if resolved_tags else [],
            scope=scope,
            status=status,
            include_deprecated=include_deprecated,
        )

    if search_playbooks:
        results.playbooks = _search_playbooks(
            project_root,
            query=query,
            tag=first_tag,
            extra_tags=resolved_tags[1:] if resolved_tags else [],
            status=status,
            include_deprecated=include_deprecated,
        )

    return results


# ---------------------------------------------------------------------------
# Tag / tags normalisation helper
# ---------------------------------------------------------------------------


def _resolve_tags(*, tag: str | None, tags: list[str] | None) -> list[str]:
    """Merge ``tag`` (single convenience alias) and ``tags`` (multi-tag list).

    Returns a deduplicated list of lowercase tag strings, preserving order.
    """
    combined: list[str] = []
    if tag is not None:
        combined.append(tag.strip().lower())
    if tags is not None:
        for t in tags:
            norm = t.strip().lower()
            if norm and norm not in combined:
                combined.append(norm)
    return combined


# ---------------------------------------------------------------------------
# Index-accelerated tag search
# ---------------------------------------------------------------------------

# Mapping from LinkGraph artifact ``kind`` to SearchResults group name.
_KIND_CONCEPT = "concept"
_KIND_CONVENTION = "convention"
_KIND_DESIGN = "design"
_KIND_STACK = "stack"


def _should_include_hit(
    hit: ArtifactResult,
    *,
    artifact_type: str | None,
    status: str | None,
    include_deprecated: bool,
    include_stale: bool,
) -> bool:
    """Decide whether an index hit should be included in results.

    Shared filter logic for both ``_tag_search_from_index`` and
    ``_fts_search``.
    """
    # Artifact type filter
    if artifact_type is not None and hit.kind != artifact_type:
        return False

    hit_status = hit.status or ("active" if hit.kind != _KIND_STACK else "open")

    # Explicit status filter
    if status is not None and hit_status != status:
        return False

    # Hide deprecated concepts/conventions by default
    if (
        not include_deprecated
        and hit_status == "deprecated"
        and hit.kind in (_KIND_CONCEPT, _KIND_CONVENTION)
    ):
        return False

    # Hide stale stack posts by default (unless caller explicitly asked for status="stale")
    return not (
        not include_stale
        and hit_status == "stale"
        and hit.kind == _KIND_STACK
        and status != "stale"
    )


def _extra_tag_ids(
    extra_tags: list[str],
    link_graph: LinkGraph,
) -> set[int] | None:
    """Return the set of artifact IDs that match ALL *extra_tags* (AND logic).

    Returns ``None`` when *extra_tags* is empty (meaning no filtering needed).
    Each extra tag is looked up via ``search_by_tag`` and the resulting ID sets
    are intersected.
    """
    if not extra_tags:
        return None
    id_sets: list[set[int]] = []
    for et in extra_tags:
        hits = link_graph.search_by_tag(et)
        id_sets.append({h.id for h in hits})
    return id_sets[0].intersection(*id_sets[1:]) if id_sets else set()


def _tag_search_from_index(
    link_graph: LinkGraph,
    *,
    tag: str,
    extra_tags: list[str],
    scope: str | None,
    artifact_type: str | None,
    status: str | None,
    include_deprecated: bool,
    include_stale: bool,
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

    # Pre-compute the set of IDs that match ALL extra tags (AND logic).
    allowed_ids = _extra_tag_ids(extra_tags, link_graph)

    results = SearchResults()

    conv_ids = [hit.id for hit in hits if hit.kind == _KIND_CONVENTION]
    conv_details = link_graph.get_convention_details(conv_ids) if conv_ids else {}

    for hit in hits:
        # Apply shared inclusion filters (type, status, deprecated, stale)
        if not _should_include_hit(
            hit,
            artifact_type=artifact_type,
            status=status,
            include_deprecated=include_deprecated,
            include_stale=include_stale,
        ):
            continue

        # Multi-tag AND: verify the hit also has all extra tags
        if allowed_ids is not None and hit.id not in allowed_ids:
            continue

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
        elif hit.kind == _KIND_CONVENTION:
            detail = conv_details.get(hit.id)
            if detail is not None:
                dir_path, body = detail
                conv_scope = "project" if dir_path == "." else dir_path
                conv_rule = extract_rule(body)
            else:
                conv_scope = ""
                conv_rule = ""
            results.conventions.append(
                _ConventionResult(
                    title=hit.title or hit.path,
                    scope=conv_scope,
                    status=hit.status or "active",
                    tags=[tag],
                    rule=conv_rule,
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
    artifact_type: str | None,
    status: str | None,
    include_deprecated: bool,
    include_stale: bool,
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

    conv_ids = [hit.id for hit in hits if hit.kind == _KIND_CONVENTION]
    conv_details = link_graph.get_convention_details(conv_ids) if conv_ids else {}

    for hit in hits:
        # Apply shared inclusion filters (type, status, deprecated, stale)
        if not _should_include_hit(
            hit,
            artifact_type=artifact_type,
            status=status,
            include_deprecated=include_deprecated,
            include_stale=include_stale,
        ):
            continue

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
        elif hit.kind == _KIND_CONVENTION:
            detail = conv_details.get(hit.id)
            if detail is not None:
                dir_path, body = detail
                conv_scope = "project" if dir_path == "." else dir_path
                conv_rule = extract_rule(body)
            else:
                conv_scope = ""
                conv_rule = ""
            results.conventions.append(
                _ConventionResult(
                    title=hit.title or hit.path,
                    scope=conv_scope,
                    status=hit.status or "active",
                    tags=[],
                    rule=conv_rule,
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
    extra_tags: list[str],
    scope: str | None,
    status: str | None,
    include_deprecated: bool,
) -> list[_ConceptResult]:
    """Search concepts via ConceptIndex.

    Supports list-all (no query/tag returns all concepts), multi-tag AND,
    status filtering, and deprecated hiding.
    """
    from lexibrary.wiki.index import ConceptIndex

    concepts_dir = project_root / ".lexibrary" / "concepts"
    index = ConceptIndex.load(concepts_dir)

    if len(index) == 0:
        return []

    # Scope filter does not apply to concepts (they are not file-scoped)
    if scope is not None:
        return []

    if query is not None:
        matches = index.search(query)
    elif tag is not None:
        matches = index.by_tag(tag)
    else:
        # List-all: return all concepts
        all_found = [index.find(name) for name in index.names()]
        matches = [m for m in all_found if m is not None]

    # Apply tag filter (even when query was the primary search)
    if tag is not None and query is not None:
        tag_set = {c.frontmatter.title for c in index.by_tag(tag)}
        matches = [c for c in matches if c.frontmatter.title in tag_set]

    # Multi-tag AND: filter for extra tags
    if extra_tags:
        matches = [
            c
            for c in matches
            if all(any(t.strip().lower() == et for t in c.frontmatter.tags) for et in extra_tags)
        ]

    # Status filter
    if status is not None:
        matches = [c for c in matches if c.frontmatter.status == status]

    # Hide deprecated by default (unless explicitly requested via status or flag)
    if not include_deprecated and status != "deprecated":
        matches = [c for c in matches if c.frontmatter.status != "deprecated"]

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
    extra_tags: list[str],
    scope: str | None,
    status: str | None,
) -> list[_DesignFileResult]:
    """Search design files by scanning YAML frontmatter and tags.

    Supports list-all (no query/tag returns all design files) and status
    filtering.
    """
    from lexibrary.artifacts.design_file_parser import parse_design_file
    from lexibrary.utils.paths import DESIGNS_DIR

    designs_dir = project_root / ".lexibrary" / DESIGNS_DIR
    if not designs_dir.is_dir():
        return []

    results: list[_DesignFileResult] = []

    # Scan all .md files in .lexibrary/designs/ directly
    for md_path in sorted(designs_dir.rglob("*.md")):
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

        # Multi-tag AND: all extra tags must match
        if extra_tags:
            design_tags_lower = {t.lower() for t in design.tags}
            if not all(et in design_tags_lower for et in extra_tags):
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

        # Status filter
        if status is not None and design.frontmatter.status != status:
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
    extra_tags: list[str],
    scope: str | None,
    status: str | None,
    concept: str | None,
    resolution_type: str | None,
    include_stale: bool,
) -> list[_StackResult]:
    """Search Stack posts via StackIndex.

    Supports list-all, multi-tag AND, status filter, concept filter,
    resolution_type filter, and stale hiding.
    """
    from lexibrary.stack.index import StackIndex

    idx = StackIndex.build(project_root)
    if len(idx) == 0:
        return []

    # Start with all posts or query results
    matches = idx.search(query) if query is not None else list(idx)

    # Apply tag filter
    if tag is not None:
        tag_set = {p.frontmatter.id for p in idx.by_tag(tag)}
        matches = [p for p in matches if p.frontmatter.id in tag_set]

    # Multi-tag AND: filter for extra tags
    if extra_tags:
        for et in extra_tags:
            et_set = {p.frontmatter.id for p in idx.by_tag(et)}
            matches = [p for p in matches if p.frontmatter.id in et_set]

    # Apply scope filter
    if scope is not None:
        scope_set = {p.frontmatter.id for p in idx.by_scope(scope)}
        matches = [p for p in matches if p.frontmatter.id in scope_set]

    # Apply status filter
    if status is not None:
        matches = [p for p in matches if p.frontmatter.status == status]

    # Apply concept filter (stack-specific)
    if concept is not None:
        concept_set = {p.frontmatter.id for p in idx.by_concept(concept)}
        matches = [p for p in matches if p.frontmatter.id in concept_set]

    # Apply resolution_type filter (stack-specific)
    if resolution_type is not None:
        matches = [p for p in matches if p.frontmatter.resolution_type == resolution_type]

    # Hide stale posts by default (unless include_stale or status is "stale")
    if not include_stale and status != "stale":
        matches = [p for p in matches if p.frontmatter.status != "stale"]

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


def _search_conventions(
    project_root: Path,
    *,
    query: str | None,
    tag: str | None,
    extra_tags: list[str],
    scope: str | None,
    status: str | None,
    include_deprecated: bool,
) -> list[_ConventionResult]:
    """Search conventions via ConventionIndex (file-scanning fallback).

    When *tag* is provided, uses :meth:`ConventionIndex.by_tag`.
    When *query* is provided, uses :meth:`ConventionIndex.search`.
    When neither is provided, returns all conventions (list-all).
    When *scope* is provided, results are filtered to conventions whose
    scope matches (convention scope is a prefix of the query scope, or
    convention scope is ``"project"``).
    """
    from lexibrary.conventions.index import ConventionIndex  # noqa: PLC0415

    conventions_dir = project_root / ".lexibrary" / "conventions"
    if not conventions_dir.is_dir():
        return []

    index = ConventionIndex(conventions_dir)
    index.load()

    if len(index) == 0:
        return []

    if query is not None:
        matches = index.search(query)
    elif tag is not None:
        matches = index.by_tag(tag)
    else:
        # List-all: return all conventions
        matches = list(index.conventions)

    # Apply tag filter (even when query was the primary search)
    if tag is not None and query is not None:
        tag_lower = tag.strip().lower()
        matches = [
            c for c in matches if any(t.strip().lower() == tag_lower for t in c.frontmatter.tags)
        ]

    # Multi-tag AND: filter for extra tags
    if extra_tags:
        matches = [
            c
            for c in matches
            if all(any(t.strip().lower() == et for t in c.frontmatter.tags) for et in extra_tags)
        ]

    # Apply scope filter: keep conventions whose scope is "project" or
    # whose scope is a prefix of the query scope.
    if scope is not None:
        norm_scope = scope.strip("/")
        matches = [
            c
            for c in matches
            if c.frontmatter.scope == "project"
            or norm_scope.startswith(c.frontmatter.scope.strip("/"))
        ]

    # Status filter
    if status is not None:
        matches = [c for c in matches if c.frontmatter.status == status]

    # Hide deprecated by default (unless explicitly requested via status or flag)
    if not include_deprecated and status != "deprecated":
        matches = [c for c in matches if c.frontmatter.status != "deprecated"]

    return [
        _ConventionResult(
            title=c.frontmatter.title,
            scope=c.frontmatter.scope,
            status=c.frontmatter.status,
            tags=list(c.frontmatter.tags),
            rule=c.rule,
        )
        for c in matches
    ]


def _search_playbooks(
    project_root: Path,
    *,
    query: str | None,
    tag: str | None,
    extra_tags: list[str],
    status: str | None,
    include_deprecated: bool,
) -> list[_PlaybookResult]:
    """Search playbooks via PlaybookIndex (file-scanning).

    Follows the same pattern as ``_search_conventions``.  Supports list-all
    (no query/tag returns all playbooks), multi-tag AND, status filtering,
    and deprecated hiding.
    """
    from lexibrary.playbooks.index import PlaybookIndex  # noqa: PLC0415

    playbooks_dir = project_root / ".lexibrary" / "playbooks"
    if not playbooks_dir.is_dir():
        return []

    index = PlaybookIndex(playbooks_dir)
    index.load()

    if len(index) == 0:
        return []

    if query is not None:
        matches = index.search(query)
    elif tag is not None:
        matches = index.by_tag(tag)
    else:
        # List-all: return all playbooks
        matches = list(index.playbooks)

    # Apply tag filter (even when query was the primary search)
    if tag is not None and query is not None:
        tag_lower = tag.strip().lower()
        matches = [
            pb for pb in matches if any(t.strip().lower() == tag_lower for t in pb.frontmatter.tags)
        ]

    # Multi-tag AND: filter for extra tags
    if extra_tags:
        matches = [
            pb
            for pb in matches
            if all(any(t.strip().lower() == et for t in pb.frontmatter.tags) for et in extra_tags)
        ]

    # Status filter
    if status is not None:
        matches = [pb for pb in matches if pb.frontmatter.status == status]

    # Hide deprecated by default (unless explicitly requested via status or flag)
    if not include_deprecated and status != "deprecated":
        matches = [pb for pb in matches if pb.frontmatter.status != "deprecated"]

    return [
        _PlaybookResult(
            title=pb.frontmatter.title,
            status=pb.frontmatter.status,
            tags=list(pb.frontmatter.tags),
            overview=pb.overview,
        )
        for pb in matches
    ]
