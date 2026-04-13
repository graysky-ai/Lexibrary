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


# ---------------------------------------------------------------------------
# Group 6 — Mixed-mode search + suggestions integration (symbol-search)
# ---------------------------------------------------------------------------


def _seed_symbols_for_mixed_search(
    project: Path,
    symbols: list[tuple[str, str]],
) -> None:
    """Seed ``symbols.db`` with ``(name, file_path)`` entries.

    Creates one ``files`` row per unique *file_path* and one ``symbols``
    row per ``(name, file_path)`` entry. Uses a distinct ``parent_class``
    value (``Stub0``, ``Stub1``, ...) to sidestep the UNIQUE constraint
    on ``(file_id, name, symbol_type, parent_class)`` when the same name
    appears multiple times in one file. Mirrors ``_seed_symbol_names``
    from ``tests/test_services/test_symbols.py`` but adds per-symbol
    ``file_path`` control so scope-filtering tests can exercise both
    matching and non-matching paths.
    """
    from lexibrary.symbolgraph.query import open_symbol_graph  # noqa: PLC0415

    # Create source files for every distinct file_path — build_symbol_graph
    # reads these via hash_file, but here we only need the `files` row so
    # the symbol rows have a valid foreign key. Contents are irrelevant
    # for the search tests.
    unique_paths = []
    for _name, rel_path in symbols:
        if rel_path not in unique_paths:
            unique_paths.append(rel_path)
    for rel_path in unique_paths:
        abs_path = project / rel_path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_text(f"# {rel_path}\n")

    graph = open_symbol_graph(project)
    conn = graph._conn
    try:
        file_ids: dict[str, int] = {}
        for rel_path in unique_paths:
            cur = conn.execute(
                "INSERT INTO files (path, language, last_hash) VALUES (?, ?, ?)",
                (rel_path, "python", "stub-hash"),
            )
            file_ids[rel_path] = int(cur.lastrowid or 0)

        for index, (name, rel_path) in enumerate(symbols):
            conn.execute(
                "INSERT INTO symbols "
                "(file_id, name, qualified_name, symbol_type, line_start, "
                "line_end, visibility, parent_class) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    file_ids[rel_path],
                    name,
                    f"stub.{name}_{index}",
                    "function",
                    index * 10 + 1,
                    index * 10 + 3,
                    "public",
                    f"Stub{index}",
                ),
            )
        conn.commit()
    finally:
        graph.close()


class TestMixedModeSearchAugmentation:
    """Integration tests for ``_augment_with_symbols`` wiring.

    These tests cover tasks 6.1-6.6 + 6.8-6.10 from Group 6 of the
    ``symbol-search`` OpenSpec change: mixed-mode search seeds
    ``results.symbol_results`` alongside artefact hits when no symbol-
    incompatible filter is active and silently skips symbols otherwise.
    Each test seeds a minimal concept and (where relevant) a symbols.db
    via :func:`_seed_symbols_for_mixed_search`.
    """

    def test_mixed_search_includes_symbols(self, tmp_path: Path) -> None:
        """6.1 — mixed-mode search populates concepts AND symbol_results.

        Seeds a concept whose title matches ``render`` and a symbol whose
        name matches ``render``. Running ``unified_search`` with no type
        filter must return non-empty ``concepts`` (from the file-scanning
        concept search) and non-empty ``symbol_results`` (from the
        symbol-graph augmentation).
        """
        project = _setup_project(tmp_path)
        _create_concept_file(
            project,
            "Render Pipeline",
            concept_id="CN-001",
            tags=["rendering"],
        )
        _seed_symbols_for_mixed_search(
            project,
            [("render_output", "src/lexibrary/render.py")],
        )

        results = unified_search(project, query="render")
        assert results.concepts, "concept should match 'render'"
        assert results.symbol_results, "symbol should be augmented into mixed results"
        names = {sym.name for sym in results.symbol_results}
        assert "render_output" in names

    def test_mixed_search_respects_symbol_limit(self, tmp_path: Path) -> None:
        """6.2 — symbol_limit caps symbol_results without affecting artefacts.

        Seeds a concept that matches ``render`` plus five symbols whose
        names all match ``render``. Calling ``unified_search`` with
        ``symbol_limit=2`` must cap ``symbol_results`` at 2 while leaving
        the artefact buckets untouched.
        """
        project = _setup_project(tmp_path)
        _create_concept_file(project, "Render Pipeline", concept_id="CN-001")
        _seed_symbols_for_mixed_search(
            project,
            [
                ("render_a", "src/a.py"),
                ("render_b", "src/b.py"),
                ("render_c", "src/c.py"),
                ("render_d", "src/d.py"),
                ("render_e", "src/e.py"),
            ],
        )

        results = unified_search(project, query="render", symbol_limit=2)
        assert len(results.symbol_results) == 2
        # Artefact bucket must NOT be capped by symbol_limit.
        assert len(results.concepts) == 1

    def test_mixed_search_skips_symbols_when_tag_set(self, tmp_path: Path) -> None:
        """6.3 — ``tag`` filter causes the symbol augmentation to no-op.

        Seeds a symbol matching ``render``; calling ``unified_search``
        with ``tags=["foo"]`` (a symbol-incompatible filter) must leave
        ``symbol_results`` empty — this is the regression the Group 6
        expected-false-positive (task 6.11) guards against.
        """
        project = _setup_project(tmp_path)
        _seed_symbols_for_mixed_search(
            project,
            [("render_output", "src/lexibrary/render.py")],
        )

        results = unified_search(project, query="render", tags=["foo"])
        assert results.symbol_results == []

    def test_mixed_search_skips_symbols_when_status_set(self, tmp_path: Path) -> None:
        """6.4 — ``status`` filter causes the symbol augmentation to no-op.

        Mirrors 6.3 but uses ``status="active"`` instead of a tag filter.
        Symbols cannot carry artefact status, so passing ``status`` must
        short-circuit the augmentation path.
        """
        project = _setup_project(tmp_path)
        _seed_symbols_for_mixed_search(
            project,
            [("render_output", "src/lexibrary/render.py")],
        )

        results = unified_search(project, query="render", status="active")
        assert results.symbol_results == []

    def test_mixed_search_respects_scope_for_symbols(self, tmp_path: Path) -> None:
        """6.5 — ``scope`` filters symbols by file-path prefix.

        Seeds two symbols — one under ``src/lexibrary/curator/`` and one
        under ``src/lexibrary/other/`` — then constrains the search to
        the curator scope. Only the curator symbol must appear.
        """
        project = _setup_project(tmp_path)
        _seed_symbols_for_mixed_search(
            project,
            [
                ("render_curator", "src/lexibrary/curator/render.py"),
                ("render_other", "src/lexibrary/other/render.py"),
            ],
        )

        results = unified_search(
            project,
            query="render",
            scope="src/lexibrary/curator/",
        )
        names = {sym.name for sym in results.symbol_results}
        assert names == {"render_curator"}

    def test_mixed_search_symbols_when_symbols_db_missing(self, tmp_path: Path) -> None:
        """6.6 — missing ``symbols.db`` degrades silently.

        With only the artefact side seeded (no ``symbols.db`` on disk),
        ``unified_search`` must still populate artefact buckets and
        return an empty ``symbol_results`` list without raising.
        """
        project = _setup_project(tmp_path)
        _create_concept_file(project, "Render Pipeline", concept_id="CN-001")
        assert not (project / ".lexibrary" / "symbols.db").exists()

        results = unified_search(project, query="render")
        assert results.concepts, "artefact buckets should still populate"
        assert results.symbol_results == []

    def test_suggestions_include_symbol_names(self, tmp_path: Path) -> None:
        """6.7 — ``_gather_suggestions`` pulls symbol names when needed.

        Seeds a single symbol named ``render_results`` and an artefact
        candidate pool (one concept + tag) that does NOT fuzzy-match
        ``renderr``. Running with ``suggest=True`` and a near-miss query
        must produce a suggestion that includes the symbol name (the
        lazy ``list_symbol_names`` branch fires because the artefact-
        only pool yielded fewer than three hits). Populating the
        artefact pool with one unrelated concept is necessary because
        ``_gather_suggestions`` returns early when the concept+tag
        pool is entirely empty — matching the "search-suggestions" spec
        scenario which requires at least some artefact candidates to
        exist before the symbol augmentation step runs.
        """
        project = _setup_project(tmp_path)
        # Populate the candidate pool with a concept that will NOT fuzzy-
        # match 'renderr' (ratio well below 0.6) so the artefact-only
        # difflib pass yields < 3 hits and the symbol augmentation fires.
        _create_concept_file(
            project,
            "AuthenticationConfig",
            concept_id="CN-001",
            tags=["security"],
        )
        _seed_symbols_for_mixed_search(
            project,
            [("render_results", "src/lexibrary/render.py")],
        )

        results = unified_search(project, query="renderr", suggest=True)
        assert not results.has_results()
        assert "render_results" in results.suggestions

    def test_mixed_search_fts_path_includes_symbols(self, tmp_path: Path) -> None:
        """6.8 — FTS code path also augments with symbols.

        Constructs a valid ``LinkGraph`` with an FTS-indexed artefact
        that matches ``render`` and seeds a symbol that matches
        ``render``. Calling ``unified_search(..., link_graph=graph)``
        must surface BOTH the FTS artefact hit AND the symbol hit — this
        test exercises the wiring at search.py:770.
        """
        project = _setup_project(tmp_path)
        db_path = _create_linkgraph_db(project)
        _populate_index(
            db_path,
            artifacts=[
                (1, ".lexibrary/concepts/Render.md", "concept", "Render Pipeline", "active"),
            ],
            fts=[
                (1, "Render Pipeline", "documents the render pipeline internals"),
            ],
        )
        _seed_symbols_for_mixed_search(
            project,
            [("render_output", "src/lexibrary/render.py")],
        )

        graph = LinkGraph.open(db_path)
        assert graph is not None
        try:
            results = unified_search(project, query="render", link_graph=graph)
            assert results.has_results()
            # FTS artefact hit surfaced as a concept.
            assert results.concepts, "FTS should return a concept hit"
            # Symbol augmentation fired in the FTS branch.
            assert results.symbol_results, "symbols should be augmented in FTS path"
            names = {sym.name for sym in results.symbol_results}
            assert "render_output" in names
        finally:
            graph.close()

    def test_mixed_search_fallback_path_includes_symbols(self, tmp_path: Path) -> None:
        """6.9 — file-scanning fallback path also augments with symbols.

        No ``link_graph`` is passed, so ``unified_search`` falls through
        to the file-scanning branch (search.py:859). The symbol
        augmentation must still fire and populate ``symbol_results``.
        """
        project = _setup_project(tmp_path)
        _create_concept_file(project, "Render Pipeline", concept_id="CN-001")
        _seed_symbols_for_mixed_search(
            project,
            [("render_output", "src/lexibrary/render.py")],
        )

        results = unified_search(project, query="render", link_graph=None)
        assert results.symbol_results, "symbols should be augmented in fallback path"
        names = {sym.name for sym in results.symbol_results}
        assert "render_output" in names

    def test_mixed_search_json_shape(self, tmp_path: Path) -> None:
        """6.10 — ``_render_json`` emits both artefact and symbol records.

        Renders a mixed-mode result set as JSON via ``_render_json`` and
        asserts that the output contains a concept record AND a
        ``{"type": "symbol", ...}`` record. This locks in the JSON
        contract that CLI consumers rely on.
        """
        import json
        from io import StringIO

        project = _setup_project(tmp_path)
        _create_concept_file(project, "Render Pipeline", concept_id="CN-001")
        _seed_symbols_for_mixed_search(
            project,
            [("render_output", "src/lexibrary/render.py")],
        )

        results = unified_search(project, query="render")
        assert results.concepts and results.symbol_results

        buf = StringIO()
        with patch("lexibrary.cli._output.sys.stdout", buf):
            results._render_json()
        payload = json.loads(buf.getvalue())
        # No suggestions → payload is a flat list of record dicts.
        assert isinstance(payload, list)
        types = {record.get("type") for record in payload}
        assert "concept" in types
        assert "symbol" in types
