"""Tests for the search upgrade feature set (Groups 1-9).

Covers:
- 10.1: _normalize_query() — splitting, CamelCase, compound detection, edge cases
- 10.2: _escape_fts_token() — quoting, embedded quotes, FTS5 operators
- 10.3: --limit flag — forwarding to full_text_search(), default preserved
- 10.6: Suggestions field — populated when suggest=True and zero results
- 10.7: Tag normalization — underscore/hyphen equivalence
- 10.8: Integration — unified_search() with compound queries, with/without link graph
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import yaml

from lexibrary.linkgraph.query import LinkGraph
from lexibrary.linkgraph.schema import ensure_schema
from lexibrary.search import (
    NormalizedQuery,
    SearchResults,
    _escape_fts_token,
    _normalize_query,
    _normalize_tag,
    unified_search,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_project(tmp_path: Path) -> Path:
    """Create a minimal initialized project with required directories."""
    (tmp_path / ".lexibrary").mkdir()
    (tmp_path / ".lexibrary" / "config.yaml").write_text("")
    return tmp_path


def _create_concept_file(
    project: Path,
    title: str,
    *,
    concept_id: str = "CN-001",
    tags: list[str] | None = None,
    aliases: list[str] | None = None,
    status: str = "active",
    summary: str = "",
) -> Path:
    """Create a concept file in .lexibrary/concepts/."""
    concepts_dir = project / ".lexibrary" / "concepts"
    concepts_dir.mkdir(parents=True, exist_ok=True)

    slug = title.replace(" ", "")
    path = concepts_dir / f"{slug}.md"

    fm_data: dict[str, object] = {
        "title": title,
        "id": concept_id,
        "aliases": aliases or [],
        "tags": tags or [],
        "status": status,
    }
    fm_str = yaml.dump(fm_data, default_flow_style=False, sort_keys=False).rstrip("\n")

    body = summary if summary else f"Summary of {title}."
    content = f"---\n{fm_str}\n---\n{body}\n"
    path.write_text(content, encoding="utf-8")
    return path


def _create_convention_file(
    project: Path,
    title: str,
    *,
    conv_id: str = "CV-001",
    scope: str = "project",
    tags: list[str] | None = None,
    status: str = "active",
    rule: str = "",
    body: str = "",
) -> Path:
    """Create a convention file in .lexibrary/conventions/."""
    conventions_dir = project / ".lexibrary" / "conventions"
    conventions_dir.mkdir(parents=True, exist_ok=True)

    slug = title.lower().replace(" ", "-")
    path = conventions_dir / f"{slug}.md"

    fm_data: dict[str, object] = {
        "title": title,
        "id": conv_id,
        "scope": scope,
        "tags": tags or [],
        "status": status,
        "source": "user",
        "priority": 0,
    }
    fm_str = yaml.dump(fm_data, default_flow_style=False, sort_keys=False).rstrip("\n")

    if not body and rule:
        body = f"\n{rule}\n"
    elif not body:
        body = f"\n{title}\n"

    content = f"---\n{fm_str}\n---\n{body}"
    if not content.endswith("\n"):
        content += "\n"
    path.write_text(content, encoding="utf-8")
    return path


def _create_stack_post(
    project: Path,
    title: str,
    *,
    post_id: str = "ST-001",
    tags: list[str] | None = None,
    status: str = "open",
    problem: str = "A problem occurred.",
) -> Path:
    """Create a stack post file in .lexibrary/stack/.

    Includes required ``created`` and ``author`` frontmatter fields
    expected by :class:`StackPostFrontmatter`.
    """
    stack_dir = project / ".lexibrary" / "stack"
    stack_dir.mkdir(parents=True, exist_ok=True)

    slug = title.lower().replace(" ", "-")
    path = stack_dir / f"{post_id}-{slug}.md"

    fm_data: dict[str, object] = {
        "title": title,
        "id": post_id,
        "tags": tags or ["general"],
        "status": status,
        "votes": 0,
        "created": "2026-01-01",
        "author": "test-agent",
    }
    fm_str = yaml.dump(fm_data, default_flow_style=False, sort_keys=False).rstrip("\n")

    content = f"---\n{fm_str}\n---\n\n## Problem\n\n{problem}\n"
    path.write_text(content, encoding="utf-8")
    return path


def _create_design_file(
    project: Path,
    source_rel: str,
    *,
    description: str = "A design file",
    design_id: str = "DS-001",
    tags: list[str] | None = None,
    status: str = "active",
) -> Path:
    """Create a valid design file in .lexibrary/designs/ with full structure.

    Design files require an H1 heading, Interface Contract section, and a
    metadata footer to parse correctly.
    """
    design_path = project / ".lexibrary" / "designs" / f"{source_rel}.md"
    design_path.parent.mkdir(parents=True, exist_ok=True)

    content_hash = hashlib.sha256(b"test").hexdigest()
    now = datetime.now().isoformat()
    tags_section = "\n".join(f"- {t}" for t in (tags or [])) if tags else "- (none)"

    content = f"""---
description: {description}
id: {design_id}
updated_by: archivist
status: {status}
---

# {source_rel}

{description}

## Interface Contract

```python
def placeholder(): ...
```

## Dependencies

- (none)

## Dependents

- (none)

## Tags

{tags_section}

<!-- lexibrary:meta
source: {source_rel}
source_hash: {content_hash}
design_hash: placeholder
generated: {now}
generator: lexibrary-v2
-->
"""
    design_path.write_text(content, encoding="utf-8")
    return design_path


def _create_linkgraph_db(project: Path) -> Path:
    """Create an empty link graph database with schema."""
    db_path = project / ".lexibrary" / "index.db"
    conn = sqlite3.connect(str(db_path))
    ensure_schema(conn)
    conn.commit()
    conn.close()
    return db_path


def _populate_index(
    db_path: Path,
    *,
    artifacts: list[tuple[int, str, str, str, str | None]] | None = None,
    tags: list[tuple[int, str]] | None = None,
    fts: list[tuple[int, str, str]] | None = None,
) -> None:
    """Populate a link graph database with artifacts, tags, and FTS data."""
    conn = sqlite3.connect(str(db_path))
    if artifacts:
        for art_row in artifacts:
            conn.execute(
                "INSERT INTO artifacts (id, path, kind, title, status) VALUES (?, ?, ?, ?, ?)",
                art_row,
            )
    if tags:
        for tag_row in tags:
            conn.execute("INSERT INTO tags (artifact_id, tag) VALUES (?, ?)", tag_row)
    if fts:
        for fts_row in fts:
            conn.execute("INSERT INTO artifacts_fts (rowid, title, body) VALUES (?, ?, ?)", fts_row)
    conn.commit()
    conn.close()


# ===========================================================================
# 10.1 — _normalize_query() unit tests
# ===========================================================================


class TestNormalizeQuery:
    """Unit tests for _normalize_query() — splitting, CamelCase, compound detection."""

    def test_underscore_splitting(self) -> None:
        """Underscores are split into separate tokens."""
        nq = _normalize_query("lookup_render")
        assert nq.tokens == ["lookup", "render"]
        assert nq.is_compound is True
        assert nq.original == "lookup_render"

    def test_hyphen_splitting(self) -> None:
        """Hyphens are split into separate tokens."""
        nq = _normalize_query("error-handling")
        assert nq.tokens == ["error", "handling"]
        assert nq.is_compound is True

    def test_dot_splitting(self) -> None:
        """Dots are split into separate tokens."""
        nq = _normalize_query("config.yaml")
        assert nq.tokens == ["config", "yaml"]
        assert nq.is_compound is True

    def test_slash_splitting(self) -> None:
        """Slashes are split into separate tokens."""
        nq = _normalize_query("src/auth")
        assert nq.tokens == ["src", "auth"]
        assert nq.is_compound is True

    def test_camelcase_splitting(self) -> None:
        """CamelCase words are split into separate tokens."""
        nq = _normalize_query("CamelCase")
        assert nq.tokens == ["camel", "case"]
        assert nq.is_compound is True

    def test_combined_splitting(self) -> None:
        """Underscore + CamelCase splitting works together."""
        nq = _normalize_query("myModule_doSomething")
        assert nq.tokens == ["my", "module", "do", "something"]
        assert nq.is_compound is True

    def test_plain_word_not_compound(self) -> None:
        """A plain single word produces is_compound=False."""
        nq = _normalize_query("search")
        assert nq.tokens == ["search"]
        assert nq.is_compound is False

    def test_plain_word_case_insensitive(self) -> None:
        """A plain word with uppercase is still not compound (just lowercased)."""
        nq = _normalize_query("Search")
        # "Search" -> _split_camel -> ["Search"] -> lowercase -> ["search"]
        # tokens == ["search"] vs [query.lower()] == ["search"] -> not compound
        assert nq.tokens == ["search"]
        assert nq.is_compound is False

    def test_empty_token_discarding(self) -> None:
        """Empty tokens from consecutive separators are discarded."""
        nq = _normalize_query("foo__bar")
        assert nq.tokens == ["foo", "bar"]
        assert nq.is_compound is True

    def test_all_tokens_lowercased(self) -> None:
        """All tokens are lowercased."""
        nq = _normalize_query("MyModule")
        assert all(t == t.lower() for t in nq.tokens)

    def test_html_parser_edge_case(self) -> None:
        """HTMLParser splits correctly on uppercase runs."""
        nq = _normalize_query("HTMLParser")
        assert nq.tokens == ["html", "parser"]
        assert nq.is_compound is True

    def test_fts_query_edge_case(self) -> None:
        """FTSQuery splits correctly."""
        nq = _normalize_query("FTSQuery")
        assert nq.tokens == ["fts", "query"]
        assert nq.is_compound is True

    def test_get_http_response_edge_case(self) -> None:
        """getHTTPResponse splits on uppercase-to-uppercase-then-lower boundary."""
        nq = _normalize_query("getHTTPResponse")
        assert nq.tokens == ["get", "http", "response"]
        assert nq.is_compound is True

    def test_simple_url_edge_case(self) -> None:
        """simpleURL splits on mixed case boundary."""
        nq = _normalize_query("simpleURL")
        assert nq.tokens == ["simple", "url"]
        assert nq.is_compound is True

    def test_original_preserved(self) -> None:
        """The original query string is preserved in NormalizedQuery."""
        nq = _normalize_query("lookup_render")
        assert nq.original == "lookup_render"


# ===========================================================================
# 10.2 — _escape_fts_token() unit tests
# ===========================================================================


class TestEscapeFtsToken:
    """Unit tests for _escape_fts_token() — quoting for FTS5 MATCH expressions."""

    def test_plain_token(self) -> None:
        """A plain token is wrapped in double quotes."""
        assert _escape_fts_token("search") == '"search"'

    def test_embedded_double_quotes(self) -> None:
        """Embedded double quotes are doubled for escaping."""
        assert _escape_fts_token('say "hello"') == '"say ""hello"""'

    def test_fts_operator_not(self) -> None:
        """FTS5 operator NOT is safely quoted."""
        assert _escape_fts_token("NOT") == '"NOT"'

    def test_fts_operator_or(self) -> None:
        """FTS5 operator OR is safely quoted."""
        assert _escape_fts_token("OR") == '"OR"'

    def test_fts_operator_and(self) -> None:
        """FTS5 operator AND is safely quoted."""
        assert _escape_fts_token("AND") == '"AND"'

    def test_empty_string(self) -> None:
        """An empty string is wrapped in double quotes."""
        assert _escape_fts_token("") == '""'


# ===========================================================================
# 10.3 — --limit flag unit tests
# ===========================================================================


class TestLimitFlag:
    """Unit tests for the --limit flag: forwarded to full_text_search(), default preserved."""

    def test_limit_forwarded_to_full_text_search(self, tmp_path: Path) -> None:
        """The limit parameter is forwarded from unified_search to full_text_search."""
        project = _setup_project(tmp_path)
        db_path = _create_linkgraph_db(project)

        _populate_index(
            db_path,
            artifacts=[
                (1, ".lexibrary/concepts/Auth.md", "concept", "Authentication", "active"),
            ],
            fts=[
                (1, "Authentication", "auth patterns and security"),
            ],
        )

        graph = LinkGraph.open(db_path)
        assert graph is not None
        try:
            with patch.object(graph, "full_text_search", wraps=graph.full_text_search) as mock_fts:
                unified_search(project, query="authentication", link_graph=graph, limit=5)
                mock_fts.assert_called_once()
                call_kwargs = mock_fts.call_args.kwargs
                assert call_kwargs.get("limit") == 5
        finally:
            graph.close()

    def test_default_limit_is_20(self, tmp_path: Path) -> None:
        """When --limit is omitted, the default value of 20 is forwarded."""
        project = _setup_project(tmp_path)
        db_path = _create_linkgraph_db(project)

        _populate_index(
            db_path,
            artifacts=[
                (1, ".lexibrary/concepts/Auth.md", "concept", "Authentication", "active"),
            ],
            fts=[
                (1, "Authentication", "auth patterns and security"),
            ],
        )

        graph = LinkGraph.open(db_path)
        assert graph is not None
        try:
            with patch.object(graph, "full_text_search", wraps=graph.full_text_search) as mock_fts:
                # Do NOT pass limit — should use default
                unified_search(project, query="authentication", link_graph=graph)
                mock_fts.assert_called_once()
                call_kwargs = mock_fts.call_args.kwargs
                # limit should be 20 (passed as kwarg)
                assert call_kwargs.get("limit") == 20
        finally:
            graph.close()

    def test_limit_caps_results(self, tmp_path: Path) -> None:
        """Setting limit=1 returns at most 1 result from FTS."""
        project = _setup_project(tmp_path)
        db_path = _create_linkgraph_db(project)

        # Create multiple artifacts that match
        _populate_index(
            db_path,
            artifacts=[
                (1, ".lexibrary/concepts/Auth.md", "concept", "Auth service", "active"),
                (2, ".lexibrary/concepts/Auth2.md", "concept", "Auth token", "active"),
                (3, ".lexibrary/concepts/Auth3.md", "concept", "Auth flow", "active"),
            ],
            fts=[
                (1, "Auth service", "authentication patterns"),
                (2, "Auth token", "authentication tokens"),
                (3, "Auth flow", "authentication flow"),
            ],
        )

        graph = LinkGraph.open(db_path)
        assert graph is not None
        try:
            results = unified_search(project, query="auth", link_graph=graph, limit=1)
            # Should return at most 1 result
            total = (
                len(results.concepts)
                + len(results.conventions)
                + len(results.design_files)
                + len(results.stack_posts)
                + len(results.playbooks)
            )
            assert total <= 1
        finally:
            graph.close()


# ===========================================================================
# 10.6 — Suggestions field unit tests
# ===========================================================================


class TestSuggestionsField:
    """Unit tests for the suggestions field on SearchResults."""

    def test_suggestions_populated_when_suggest_true_and_zero_results(self, tmp_path: Path) -> None:
        """Suggestions are populated when suggest=True and no results found.

        Uses a query that produces no results (neither substring nor fuzzy
        in ConceptIndex) but is close enough to a concept name or tag for
        ``_gather_suggestions`` to suggest it.
        """
        project = _setup_project(tmp_path)
        _create_concept_file(
            project,
            "Link Graph Indexing",
            concept_id="CN-001",
            tags=["indexing", "search"],
            aliases=["linkgraph"],
        )

        # "indexng" is close to "indexing" (tag) but NOT a substring of any
        # concept field, so concept search returns nothing.  _gather_suggestions
        # collects tags as candidates and should suggest "indexing".
        results = unified_search(project, query="indexng", suggest=True)
        assert not results.has_results()
        assert len(results.suggestions) > 0

    def test_suggestions_empty_when_suggest_false(self, tmp_path: Path) -> None:
        """Suggestions are empty when suggest=False even with zero results."""
        project = _setup_project(tmp_path)
        _create_concept_file(project, "Authentication", concept_id="CN-001", tags=["security"])

        results = unified_search(project, query="authenticaton", suggest=False)
        assert results.suggestions == []

    def test_suggestions_empty_when_results_exist(self, tmp_path: Path) -> None:
        """Suggestions are empty when actual results are found (regardless of suggest flag)."""
        project = _setup_project(tmp_path)
        _create_concept_file(project, "Authentication", concept_id="CN-001", tags=["security"])

        results = unified_search(project, query="authentication", suggest=True)
        assert results.has_results()
        assert results.suggestions == []

    def test_suggestions_at_most_3(self, tmp_path: Path) -> None:
        """Suggestions list contains at most 3 entries."""
        project = _setup_project(tmp_path)
        # Create many concepts with similar names
        for i in range(10):
            _create_concept_file(
                project,
                f"SearchPattern{i}",
                concept_id=f"CN-{i:03d}",
                tags=["patterns"],
            )

        results = unified_search(project, query="SearchPatern", suggest=True)
        assert len(results.suggestions) <= 3

    def test_suggestions_with_link_graph_path(self, tmp_path: Path) -> None:
        """Suggestions work through the FTS code path with a link graph."""
        project = _setup_project(tmp_path)
        _create_concept_file(project, "Authentication", concept_id="CN-001", tags=["security"])

        db_path = _create_linkgraph_db(project)
        # No FTS data — so FTS returns nothing, triggering concept fallback,
        # then suggestions
        graph = LinkGraph.open(db_path)
        assert graph is not None
        try:
            results = unified_search(
                project,
                query="xyznonexistent",
                link_graph=graph,
                suggest=True,
            )
            # No results and no close match for "xyznonexistent"
            assert not results.has_results()
            # Suggestions might be empty (no close match) but should not error
            assert isinstance(results.suggestions, list)
        finally:
            graph.close()

    def test_suggestions_render_plain_did_you_mean(self, tmp_path: Path) -> None:
        """Plain rendering shows 'Did you mean' when suggestions are present."""
        from io import StringIO

        results = SearchResults(suggestions=["authentication", "authorization"])
        buf = StringIO()
        with patch("lexibrary.cli._output.sys.stdout", buf):
            results._render_plain()
        output = buf.getvalue()
        assert "Did you mean" in output
        assert "authentication" in output
        assert "authorization" in output

    def test_suggestions_render_json_includes_field(self) -> None:
        """JSON rendering includes suggestions field when present."""
        import json
        from io import StringIO

        results = SearchResults(suggestions=["auth", "authorize"])
        buf = StringIO()
        with patch("lexibrary.cli._output.sys.stdout", buf):
            results._render_json()
        output = buf.getvalue()
        parsed = json.loads(output)
        assert "suggestions" in parsed
        assert parsed["suggestions"] == ["auth", "authorize"]


# ===========================================================================
# 10.7 — Tag normalization unit tests
# ===========================================================================


class TestTagNormalization:
    """Unit tests for tag normalization: underscore/hyphen equivalence."""

    def test_normalize_tag_underscore_to_hyphen(self) -> None:
        """_normalize_tag converts underscores to hyphens."""
        assert _normalize_tag("error_handling") == "error-handling"

    def test_normalize_tag_hyphen_preserved(self) -> None:
        """_normalize_tag preserves hyphens."""
        assert _normalize_tag("error-handling") == "error-handling"

    def test_normalize_tag_case_insensitive(self) -> None:
        """_normalize_tag lowercases the tag."""
        assert _normalize_tag("Error_Handling") == "error-handling"

    def test_normalize_tag_strips_whitespace(self) -> None:
        """_normalize_tag strips leading/trailing whitespace."""
        assert _normalize_tag("  error_handling  ") == "error-handling"

    def test_tag_filter_underscore_matches_hyphen_in_design_files(self, tmp_path: Path) -> None:
        """Design file with tag 'error-handling' is found when filtering by 'error_handling'.

        Design files apply _normalize_tag inline in their tag filter, so
        underscore/hyphen equivalence works for tag-only queries.
        """
        project = _setup_project(tmp_path)
        _create_design_file(
            project,
            "src/handler.py",
            description="Error handler module",
            design_id="DS-001",
            tags=["error-handling"],
        )

        results = unified_search(project, tag="error_handling")
        assert results.has_results()
        assert len(results.design_files) == 1
        assert results.design_files[0].description == "Error handler module"

    def test_tag_filter_hyphen_matches_underscore_in_design_files(self, tmp_path: Path) -> None:
        """Design file with tag 'error_handling' is found when filtering by 'error-handling'."""
        project = _setup_project(tmp_path)
        _create_design_file(
            project,
            "src/handler.py",
            description="Error handler module",
            design_id="DS-001",
            tags=["error_handling"],
        )

        results = unified_search(project, tag="error-handling")
        assert results.has_results()
        assert len(results.design_files) == 1

    def test_tag_normalization_in_convention_extra_tags(self, tmp_path: Path) -> None:
        """Convention extra_tags AND filter normalises underscores and hyphens.

        The multi-tag AND path in _search_conventions uses _normalize_tag for
        extra tags, so passing ['error_handling'] matches a convention
        tagged with 'error-handling'.
        """
        project = _setup_project(tmp_path)
        _create_convention_file(
            project,
            "Error handling rules",
            conv_id="CV-001",
            tags=["error-handling", "patterns"],
            rule="All errors must be handled.",
        )

        # Use 'patterns' as the primary tag (exact match) and 'error_handling'
        # as an extra tag (normalised match via _normalize_tag).
        results = unified_search(project, tags=["patterns", "error_handling"])
        assert results.has_results()
        assert len(results.conventions) == 1

    def test_tag_filter_underscore_matches_hyphen_in_stack_posts(self, tmp_path: Path) -> None:
        """Stack post with tag 'error-handling' is found when filtering by 'error_handling'.

        Stack posts apply _normalize_tag in their tag filter so underscore/
        hyphen equivalence works even on tag-only queries.
        """
        project = _setup_project(tmp_path)
        _create_stack_post(
            project,
            "Error handling issue",
            post_id="ST-001",
            tags=["error-handling"],
            problem="Unhandled errors in production.",
        )

        results = unified_search(project, tag="error_handling")
        assert results.has_results()
        assert len(results.stack_posts) == 1


# ===========================================================================
# 10.8 — Integration: unified_search() with compound queries
# ===========================================================================


class TestUnifiedSearchCompoundQuery:
    """Integration tests: compound query via unified_search() with and without link graph."""

    def test_compound_query_fts_path_with_link_graph(self, tmp_path: Path) -> None:
        """A compound query like 'lookup_render' uses FTS OR expression with link graph."""
        project = _setup_project(tmp_path)
        db_path = _create_linkgraph_db(project)

        # Create an artifact whose body contains both "lookup" and "render"
        # but NOT the exact string "lookup_render"
        _populate_index(
            db_path,
            artifacts=[
                (
                    1,
                    ".lexibrary/designs/src/lookup.py.md",
                    "design",
                    "Lookup and render utilities",
                    "active",
                ),
            ],
            fts=[
                (1, "Lookup and render utilities", "This module handles lookup and render logic"),
            ],
        )

        graph = LinkGraph.open(db_path)
        assert graph is not None
        try:
            results = unified_search(project, query="lookup_render", link_graph=graph)
            # The compound query should match because the FTS expression is
            # "lookup render" OR ("lookup" AND "render") and the document
            # contains both tokens
            assert results.has_results()
        finally:
            graph.close()

    def test_compound_query_fallback_path_without_link_graph(self, tmp_path: Path) -> None:
        """A compound query uses AND fallback in file-scanning path (no link graph)."""
        project = _setup_project(tmp_path)

        # Create a convention whose body contains both "lookup" and "render"
        # but not the exact substring "lookup_render"
        _create_convention_file(
            project,
            "Lookup and render pattern",
            conv_id="CV-001",
            tags=["patterns"],
            body="\nThis convention covers lookup and render techniques.\n",
        )

        results = unified_search(project, query="lookup_render")
        # The AND fallback should find this because all tokens are present
        assert results.has_results()
        assert len(results.conventions) == 1

    def test_compound_query_no_match_when_tokens_missing(self, tmp_path: Path) -> None:
        """A compound query does NOT match when some tokens are missing from content."""
        project = _setup_project(tmp_path)

        _create_convention_file(
            project,
            "Only lookup here",
            conv_id="CV-001",
            tags=["patterns"],
            body="\nThis convention covers lookup techniques.\n",
        )

        results = unified_search(project, query="lookup_render")
        # "render" is not in the body, so AND fallback should not match
        assert not results.conventions

    def test_simple_query_exact_match_preferred(self, tmp_path: Path) -> None:
        """A plain (non-compound) query uses exact substring matching."""
        project = _setup_project(tmp_path)

        _create_convention_file(
            project,
            "Search patterns convention",
            conv_id="CV-001",
            tags=["search"],
            body="\nDefines search patterns for the codebase.\n",
        )

        results = unified_search(project, query="search")
        assert results.has_results()
        assert len(results.conventions) == 1

    def test_compound_query_works_with_stack_posts(self, tmp_path: Path) -> None:
        """Compound query AND fallback works for stack posts."""
        project = _setup_project(tmp_path)

        _create_stack_post(
            project,
            "Error handling fix",
            post_id="ST-001",
            tags=["debugging"],
            problem="The lookup module failed to render correctly.",
        )

        results = unified_search(project, query="lookup_render", artifact_type="stack")
        assert results.has_results()
        assert len(results.stack_posts) == 1

    def test_normalized_query_passed_through_unified_search(self, tmp_path: Path) -> None:
        """unified_search() creates and passes NormalizedQuery to internal functions."""
        project = _setup_project(tmp_path)
        db_path = _create_linkgraph_db(project)

        graph = LinkGraph.open(db_path)
        assert graph is not None
        try:
            with patch("lexibrary.search._fts_search", wraps=None) as mock_fts:
                mock_fts.return_value = SearchResults()
                unified_search(project, query="lookup_render", link_graph=graph)
                mock_fts.assert_called_once()
                call_kwargs = mock_fts.call_args.kwargs
                nq = call_kwargs.get("normalized_query")
                assert nq is not None
                assert isinstance(nq, NormalizedQuery)
                assert nq.tokens == ["lookup", "render"]
                assert nq.is_compound is True
        finally:
            graph.close()


# ---------------------------------------------------------------------------
# Symbol-graph search integration (symbol-graph-2 group 13)
# ---------------------------------------------------------------------------


class TestUnifiedSearchSymbolIntegration:
    """End-to-end integration tests for ``--type symbol`` routing.

    These tests seed a real ``symbols.db`` via the shared Phase 2 fixture
    and drive ``unified_search`` through the full symbol-query service so
    the routing path is exercised against actual SQL.
    """

    def test_unified_search_symbol_returns_non_empty_results(self, tmp_path: Path) -> None:
        """A seeded symbols.db plus ``artifact_type='symbol'`` yields at
        least one ``SymbolSearchHit`` wrapped in a ``_SymbolResult``."""
        from tests.test_symbolgraph.conftest import (  # noqa: PLC0415
            make_linkgraph,
            make_project,
            seed_phase2_fixture,
        )

        project = make_project(tmp_path)
        make_linkgraph(project)
        seed_phase2_fixture(project)

        results = unified_search(
            project,
            query="foo",
            artifact_type="symbol",
        )

        assert results.has_results()
        assert len(results.symbol_results) >= 1
        names = {sym.name for sym in results.symbol_results}
        assert "foo" in names
        # Qualified name matches the Phase 2 fixture layout.
        qualified = {sym.qualified_name for sym in results.symbol_results}
        assert "a.foo" in qualified
        # Field types line up with the ``_SymbolResult`` dataclass.
        first = results.symbol_results[0]
        assert isinstance(first.id, int)
        assert first.file_path == "src/a.py"
        assert isinstance(first.line_start, int)

    def test_unified_search_symbol_limit_honoured(self, tmp_path: Path) -> None:
        """The ``limit`` kwarg is propagated to ``search_symbols`` and caps
        the returned list accordingly."""
        from tests.test_symbolgraph.conftest import (  # noqa: PLC0415
            make_linkgraph,
            make_project,
            seed_phase2_fixture,
        )

        project = make_project(tmp_path)
        make_linkgraph(project)
        seed_phase2_fixture(project)

        results = unified_search(
            project,
            query="ba",  # matches both ``bar`` and ``baz``
            artifact_type="symbol",
            limit=1,
        )
        assert len(results.symbol_results) == 1

    def test_unified_search_symbol_no_match(self, tmp_path: Path) -> None:
        """A query that doesn't match any seeded symbol yields an empty
        ``symbol_results`` list without raising."""
        from tests.test_symbolgraph.conftest import (  # noqa: PLC0415
            make_linkgraph,
            make_project,
            seed_phase2_fixture,
        )

        project = make_project(tmp_path)
        make_linkgraph(project)
        seed_phase2_fixture(project)

        results = unified_search(
            project,
            query="nothing_matches_this",
            artifact_type="symbol",
        )
        assert results.symbol_results == []
        assert not results.has_results()
