"""Tests for convention support in unified search (Group 3).

Covers:
- _ConventionResult dataclass and SearchResults.conventions field
- has_results() returns True when only conventions are present
- Convention rendering in SearchResults.render()
- Convention handling in _tag_search_from_index() (index-accelerated tag search)
- Convention handling in _fts_search() (FTS-accelerated search)
- _search_conventions() fallback (file-scanning with query, tag, and scope)
- End-to-end CLI test: `lexi search` returns conventions
"""

from __future__ import annotations

import os
import sqlite3
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import yaml

from lexibrary.linkgraph.query import LinkGraph
from lexibrary.linkgraph.schema import ensure_schema
from lexibrary.search import SearchResults, unified_search

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_project(tmp_path: Path) -> Path:
    """Create a minimal initialized project."""
    (tmp_path / ".lexibrary").mkdir()
    (tmp_path / ".lexibrary" / "config.yaml").write_text("")
    return tmp_path


def _create_convention_file(
    project: Path,
    title: str,
    *,
    scope: str = "project",
    rule: str = "",
    body: str = "",
    status: str = "active",
    tags: list[str] | None = None,
    aliases: list[str] | None = None,
) -> Path:
    """Create a convention file in .lexibrary/conventions/."""
    conventions_dir = project / ".lexibrary" / "conventions"
    conventions_dir.mkdir(parents=True, exist_ok=True)

    slug = title.lower().replace(" ", "-")
    path = conventions_dir / f"{slug}.md"

    fm_data: dict[str, object] = {
        "title": title,
        "id": "CV-001",
        "scope": scope,
        "tags": tags or [],
        "status": status,
        "source": "user",
        "priority": 0,
    }
    if aliases:
        fm_data["aliases"] = aliases
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


def _create_linkgraph_db(project: Path) -> Path:
    """Create an empty link graph database with schema."""
    db_path = project / ".lexibrary" / "index.db"
    conn = sqlite3.connect(str(db_path))
    ensure_schema(conn)
    conn.commit()
    conn.close()
    return db_path


def _create_populated_index(
    db_path: Path,
    *,
    artifacts: list[tuple[int, str, str, str, str | None]] | None = None,
    tags: list[tuple[int, str]] | None = None,
    fts: list[tuple[int, str, str]] | None = None,
    conventions: list[tuple[int, str, int, str, str, str, int]] | None = None,
) -> None:
    """Populate a link graph database with artifacts, tags, FTS, and convention data.

    ``conventions`` rows are
    ``(artifact_id, directory_path, ordinal, body, source, status, priority)``.
    """
    conn = sqlite3.connect(str(db_path))
    if artifacts:
        for row in artifacts:
            conn.execute(
                "INSERT INTO artifacts (id, path, kind, title, status) VALUES (?, ?, ?, ?, ?)",
                row,
            )
    if tags:
        for row in tags:
            conn.execute("INSERT INTO tags (artifact_id, tag) VALUES (?, ?)", row)
    if fts:
        for row in fts:
            conn.execute("INSERT INTO artifacts_fts (rowid, title, body) VALUES (?, ?, ?)", row)
    if conventions:
        for row in conventions:
            conn.execute(
                "INSERT INTO conventions "
                "(artifact_id, directory_path, ordinal, body, source, status, priority) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                row,
            )
    conn.commit()
    conn.close()


def _render_to_string(results: SearchResults) -> str:
    """Render SearchResults to a string for assertion."""
    buf = StringIO()
    with patch("lexibrary.cli._output.sys.stdout", buf):
        results.render()
    return buf.getvalue()


# ---------------------------------------------------------------------------
# SearchResults dataclass and rendering
# ---------------------------------------------------------------------------


class TestSearchResultsConventions:
    """Tests for the conventions field on SearchResults."""

    def test_has_results_true_with_conventions_only(self) -> None:
        """has_results() returns True when only conventions are non-empty."""
        from lexibrary.search import _ConventionResult

        results = SearchResults(
            conventions=[
                _ConventionResult(
                    id="CV-001",
                    title="Auth decorator",
                    scope="project",
                    status="active",
                    tags=["auth"],
                    rule="All endpoints require auth decorator",
                )
            ]
        )
        assert results.has_results() is True

    def test_has_results_false_when_empty(self) -> None:
        """has_results() returns False when all groups are empty."""
        results = SearchResults()
        assert results.has_results() is False

    def test_convention_table_renders(self) -> None:
        """Convention group renders a Rich Table with correct columns."""
        from lexibrary.search import _ConventionResult

        results = SearchResults(
            conventions=[
                _ConventionResult(
                    id="CV-001",
                    title="Auth decorator required",
                    scope="src/auth",
                    status="active",
                    tags=["auth", "security"],
                    rule="All endpoints require auth decorator",
                )
            ]
        )
        output = _render_to_string(results)
        assert "Conventions" in output
        assert "Auth decorator required" in output
        assert "src/auth" in output
        assert "active" in output
        assert "All endpoints require auth decorator" in output

    def test_convention_table_status_draft_renders(self) -> None:
        """Draft convention renders with yellow status."""
        from lexibrary.search import _ConventionResult

        results = SearchResults(
            conventions=[
                _ConventionResult(
                    id="CV-002",
                    title="Draft convention",
                    scope="project",
                    status="draft",
                    tags=[],
                    rule="This is a draft",
                )
            ]
        )
        output = _render_to_string(results)
        assert "draft" in output

    def test_convention_table_status_deprecated_renders(self) -> None:
        """Deprecated convention renders with red status."""
        from lexibrary.search import _ConventionResult

        results = SearchResults(
            conventions=[
                _ConventionResult(
                    id="CV-003",
                    title="Old convention",
                    scope="project",
                    status="deprecated",
                    tags=[],
                    rule="This is deprecated",
                )
            ]
        )
        output = _render_to_string(results)
        assert "deprecated" in output

    def test_empty_conventions_omitted_from_render(self) -> None:
        """When conventions list is empty, the Conventions table is not rendered."""
        from lexibrary.search import _ConceptResult

        results = SearchResults(
            concepts=[
                _ConceptResult(
                    id="CN-001",
                    name="Auth",
                    status="active",
                    tags=["auth"],
                    summary="Auth concept",
                )
            ]
        )
        output = _render_to_string(results)
        assert "Conventions" not in output
        assert "Concepts" in output

    def test_convention_rule_truncated_at_50_chars(self) -> None:
        """Convention rule is truncated to 50 characters in render."""
        from lexibrary.search import _ConventionResult

        long_rule = "A" * 80
        results = SearchResults(
            conventions=[
                _ConventionResult(
                    id="CV-004",
                    title="Long rule conv",
                    scope="project",
                    status="active",
                    tags=[],
                    rule=long_rule,
                )
            ]
        )
        output = _render_to_string(results)
        # The full 80-char rule should not appear (truncated at 50)
        assert long_rule not in output
        assert long_rule[:50] in output


# ---------------------------------------------------------------------------
# Tag search from index (conventions in link graph)
# ---------------------------------------------------------------------------


class TestTagSearchConventions:
    """Convention handling in _tag_search_from_index()."""

    def test_tag_search_returns_convention(self, tmp_path: Path) -> None:
        """Convention artifacts in the index are returned by tag search with scope and rule."""
        project = _setup_project(tmp_path)
        db_path = _create_linkgraph_db(project)

        _create_populated_index(
            db_path,
            artifacts=[
                (
                    1,
                    ".lexibrary/conventions/auth-required.md",
                    "convention",
                    "Auth required",
                    "active",
                ),
            ],
            tags=[
                (1, "security"),
            ],
            conventions=[
                (
                    1,
                    "src/auth",
                    0,
                    "All endpoints must use the auth decorator.\n\nExtra detail.",
                    "user",
                    "active",
                    0,
                ),
            ],
        )

        graph = LinkGraph.open(db_path)
        assert graph is not None
        try:
            results = unified_search(project, tag="security", link_graph=graph)
            assert results.has_results()
            assert len(results.conventions) == 1
            assert results.conventions[0].title == "Auth required"
            assert results.conventions[0].status == "active"
            assert results.conventions[0].tags == ["security"]
            assert results.conventions[0].scope == "src/auth"
            assert results.conventions[0].rule == "All endpoints must use the auth decorator."
        finally:
            graph.close()

    def test_tag_search_convention_mixed_with_concept(self, tmp_path: Path) -> None:
        """Tag search returns both concepts and conventions."""
        project = _setup_project(tmp_path)
        db_path = _create_linkgraph_db(project)

        _create_populated_index(
            db_path,
            artifacts=[
                (1, ".lexibrary/concepts/auth.md", "concept", "Authentication", "active"),
                (
                    2,
                    ".lexibrary/conventions/auth-required.md",
                    "convention",
                    "Auth required",
                    "active",
                ),
            ],
            tags=[
                (1, "security"),
                (2, "security"),
            ],
        )

        graph = LinkGraph.open(db_path)
        assert graph is not None
        try:
            results = unified_search(project, tag="security", link_graph=graph)
            assert results.has_results()
            assert len(results.concepts) == 1
            assert len(results.conventions) == 1
            assert results.concepts[0].name == "Authentication"
            assert results.conventions[0].title == "Auth required"
        finally:
            graph.close()


# ---------------------------------------------------------------------------
# FTS search (conventions in link graph)
# ---------------------------------------------------------------------------


class TestFTSSearchConventions:
    """Convention handling in _fts_search()."""

    def test_fts_returns_convention(self, tmp_path: Path) -> None:
        """FTS search returns convention artifacts with scope and rule."""
        project = _setup_project(tmp_path)
        db_path = _create_linkgraph_db(project)

        _create_populated_index(
            db_path,
            artifacts=[
                (
                    1,
                    ".lexibrary/conventions/auth-required.md",
                    "convention",
                    "Auth decorator required",
                    "active",
                ),
            ],
            fts=[
                (1, "Auth decorator required", "All endpoints must use the auth decorator"),
            ],
            conventions=[
                (
                    1,
                    "src/auth",
                    0,
                    "All endpoints must use the auth decorator.\n\nMore info here.",
                    "user",
                    "active",
                    0,
                ),
            ],
        )

        graph = LinkGraph.open(db_path)
        assert graph is not None
        try:
            results = unified_search(project, query="decorator", link_graph=graph)
            assert results.has_results()
            assert len(results.conventions) == 1
            assert results.conventions[0].title == "Auth decorator required"
            assert results.conventions[0].scope == "src/auth"
            assert results.conventions[0].rule == "All endpoints must use the auth decorator."
        finally:
            graph.close()

    def test_fts_convention_mixed_with_other_types(self, tmp_path: Path) -> None:
        """FTS search returns conventions alongside concepts and design files."""
        project = _setup_project(tmp_path)
        db_path = _create_linkgraph_db(project)

        _create_populated_index(
            db_path,
            artifacts=[
                (1, ".lexibrary/concepts/auth.md", "concept", "Authentication", "active"),
                (
                    2,
                    ".lexibrary/conventions/auth-required.md",
                    "convention",
                    "Auth Required",
                    "active",
                ),
                (3, "src/auth.py", "design", "Auth service module", None),
            ],
            fts=[
                (1, "Authentication", "Authentication concepts and patterns"),
                (2, "Auth Required", "All auth endpoints require decorator"),
                (3, "Auth service module", "The auth service handles tokens"),
            ],
        )

        graph = LinkGraph.open(db_path)
        assert graph is not None
        try:
            # Use "authentication" which matches the concept FTS title/body
            results = unified_search(project, query="authentication", link_graph=graph)
            assert results.has_results()
            assert len(results.concepts) >= 1

            # Use "auth" which matches convention and design file FTS rows
            results2 = unified_search(project, query="auth", link_graph=graph)
            assert results2.has_results()
            assert len(results2.conventions) >= 1
            assert len(results2.design_files) >= 1
        finally:
            graph.close()


# ---------------------------------------------------------------------------
# Edge-case tests: scope mapping, rule extraction, graceful degradation
# ---------------------------------------------------------------------------


class TestConventionEnrichmentEdgeCases:
    """Edge-case tests for convention enrichment in index-backed search paths."""

    def test_directory_path_dot_yields_scope_project(self, tmp_path: Path) -> None:
        """Convention with directory_path='.' maps to scope='project'."""
        project = _setup_project(tmp_path)
        db_path = _create_linkgraph_db(project)

        _create_populated_index(
            db_path,
            artifacts=[
                (1, ".lexibrary/conventions/proj-wide.md", "convention", "Project wide", "active"),
            ],
            tags=[(1, "testing")],
            conventions=[
                (1, ".", 0, "Project-wide rule body.", "user", "active", 0),
            ],
        )

        graph = LinkGraph.open(db_path)
        assert graph is not None
        try:
            results = unified_search(project, tag="testing", link_graph=graph)
            assert len(results.conventions) == 1
            assert results.conventions[0].scope == "project"
        finally:
            graph.close()

    def test_directory_path_subdir_yields_scope_as_is(self, tmp_path: Path) -> None:
        """Convention with directory_path='src/auth' maps to scope='src/auth'."""
        project = _setup_project(tmp_path)
        db_path = _create_linkgraph_db(project)

        _create_populated_index(
            db_path,
            artifacts=[
                (1, ".lexibrary/conventions/auth-conv.md", "convention", "Auth conv", "active"),
            ],
            tags=[(1, "auth")],
            conventions=[
                (1, "src/auth", 0, "Auth-specific rule.", "user", "active", 0),
            ],
        )

        graph = LinkGraph.open(db_path)
        assert graph is not None
        try:
            results = unified_search(project, tag="auth", link_graph=graph)
            assert len(results.conventions) == 1
            assert results.conventions[0].scope == "src/auth"
        finally:
            graph.close()

    def test_rule_extracted_from_body_first_paragraph(self, tmp_path: Path) -> None:
        """Rule is extracted as first paragraph before blank line."""
        project = _setup_project(tmp_path)
        db_path = _create_linkgraph_db(project)

        body = "Use type hints everywhere.\n\nThis is additional context.\nMore details."
        _create_populated_index(
            db_path,
            artifacts=[
                (1, ".lexibrary/conventions/type-hints.md", "convention", "Type hints", "active"),
            ],
            tags=[(1, "typing")],
            conventions=[
                (1, "src", 0, body, "user", "active", 0),
            ],
        )

        graph = LinkGraph.open(db_path)
        assert graph is not None
        try:
            results = unified_search(project, tag="typing", link_graph=graph)
            assert len(results.conventions) == 1
            assert results.conventions[0].rule == "Use type hints everywhere."
        finally:
            graph.close()

    def test_empty_body_yields_empty_rule(self, tmp_path: Path) -> None:
        """Convention with empty body yields rule=''."""
        project = _setup_project(tmp_path)
        db_path = _create_linkgraph_db(project)

        _create_populated_index(
            db_path,
            artifacts=[
                (1, ".lexibrary/conventions/empty-body.md", "convention", "Empty body", "active"),
            ],
            tags=[(1, "misc")],
            conventions=[
                (1, ".", 0, "", "user", "active", 0),
            ],
        )

        graph = LinkGraph.open(db_path)
        assert graph is not None
        try:
            results = unified_search(project, tag="misc", link_graph=graph)
            assert len(results.conventions) == 1
            assert results.conventions[0].rule == ""
        finally:
            graph.close()

    def test_orphaned_artifact_degrades_gracefully(self, tmp_path: Path) -> None:
        """Convention artifact with no conventions table row degrades to scope='', rule=''."""
        project = _setup_project(tmp_path)
        db_path = _create_linkgraph_db(project)

        _create_populated_index(
            db_path,
            artifacts=[
                (1, ".lexibrary/conventions/orphan.md", "convention", "Orphan conv", "active"),
            ],
            tags=[(1, "orphan")],
        )

        graph = LinkGraph.open(db_path)
        assert graph is not None
        try:
            results = unified_search(project, tag="orphan", link_graph=graph)
            assert len(results.conventions) == 1
            assert results.conventions[0].scope == ""
            assert results.conventions[0].rule == ""
        finally:
            graph.close()

    def test_fts_directory_path_dot_yields_scope_project(self, tmp_path: Path) -> None:
        """FTS path: convention with directory_path='.' maps to scope='project'."""
        project = _setup_project(tmp_path)
        db_path = _create_linkgraph_db(project)

        _create_populated_index(
            db_path,
            artifacts=[
                (
                    1,
                    ".lexibrary/conventions/proj-conv.md",
                    "convention",
                    "Project convention",
                    "active",
                ),
            ],
            fts=[
                (1, "Project convention", "Project-wide rule body"),
            ],
            conventions=[
                (1, ".", 0, "Project-wide rule body.", "user", "active", 0),
            ],
        )

        graph = LinkGraph.open(db_path)
        assert graph is not None
        try:
            results = unified_search(project, query="project", link_graph=graph)
            assert len(results.conventions) == 1
            assert results.conventions[0].scope == "project"
        finally:
            graph.close()

    def test_fts_orphaned_artifact_degrades_gracefully(self, tmp_path: Path) -> None:
        """FTS path: orphaned convention artifact degrades to scope='', rule=''."""
        project = _setup_project(tmp_path)
        db_path = _create_linkgraph_db(project)

        _create_populated_index(
            db_path,
            artifacts=[
                (1, ".lexibrary/conventions/orphan.md", "convention", "Orphan FTS", "active"),
            ],
            fts=[
                (1, "Orphan FTS", "Some searchable text"),
            ],
        )

        graph = LinkGraph.open(db_path)
        assert graph is not None
        try:
            results = unified_search(project, query="orphan", link_graph=graph)
            assert len(results.conventions) == 1
            assert results.conventions[0].scope == ""
            assert results.conventions[0].rule == ""
        finally:
            graph.close()


# ---------------------------------------------------------------------------
# Fallback file-scanning search for conventions
# ---------------------------------------------------------------------------


class TestFallbackSearchConventions:
    """Convention fallback search via _search_conventions()."""

    def test_fallback_search_by_query(self, tmp_path: Path) -> None:
        """Fallback search finds conventions by query substring in title."""
        project = _setup_project(tmp_path)
        _create_convention_file(project, "Auth decorator required", tags=["auth"])
        _create_convention_file(project, "Use dataclasses for models", tags=["python"])

        # No link_graph -- uses fallback file scanning
        results = unified_search(project, query="auth", link_graph=None)
        assert results.has_results()
        assert len(results.conventions) >= 1
        assert any(c.title == "Auth decorator required" for c in results.conventions)
        assert not any(c.title == "Use dataclasses for models" for c in results.conventions)

    def test_fallback_search_by_tag(self, tmp_path: Path) -> None:
        """Fallback search finds conventions by tag."""
        project = _setup_project(tmp_path)
        _create_convention_file(project, "Auth decorator required", tags=["security"])
        _create_convention_file(project, "Use dataclasses", tags=["python"])

        results = unified_search(project, tag="security", link_graph=None)
        assert results.has_results()
        assert len(results.conventions) >= 1
        assert any(c.title == "Auth decorator required" for c in results.conventions)
        assert not any(c.title == "Use dataclasses" for c in results.conventions)

    def test_fallback_search_with_scope_filter(self, tmp_path: Path) -> None:
        """Fallback search filters conventions by scope prefix."""
        project = _setup_project(tmp_path)
        _create_convention_file(
            project, "Auth handlers convention", tags=["auth"], scope="src/auth"
        )
        _create_convention_file(project, "Models convention", tags=["models"], scope="src/models")
        _create_convention_file(project, "Project wide convention", tags=["auth"], scope="project")

        # Scope "src/auth/handlers" should match "src/auth" (prefix) and "project"
        results = unified_search(
            project, query="convention", scope="src/auth/handlers", link_graph=None
        )
        assert results.has_results()
        matching_titles = {c.title for c in results.conventions}
        assert "Auth handlers convention" in matching_titles
        assert "Project wide convention" in matching_titles
        assert "Models convention" not in matching_titles

    def test_fallback_search_no_conventions_dir(self, tmp_path: Path) -> None:
        """Fallback search returns empty when conventions directory does not exist."""
        project = _setup_project(tmp_path)
        # No .lexibrary/conventions/ directory created

        results = unified_search(project, query="auth", link_graph=None)
        assert len(results.conventions) == 0

    def test_fallback_search_returns_convention_fields(self, tmp_path: Path) -> None:
        """Convention results contain correct title, scope, status, tags, and rule."""
        project = _setup_project(tmp_path)
        _create_convention_file(
            project,
            "Auth endpoints required",
            tags=["auth", "security"],
            scope="src/auth",
            status="active",
            rule="All endpoints must use the auth decorator",
        )

        results = unified_search(project, query="auth", link_graph=None)
        assert len(results.conventions) >= 1
        conv = next(c for c in results.conventions if c.title == "Auth endpoints required")
        assert conv.scope == "src/auth"
        assert conv.status == "active"
        assert "auth" in conv.tags
        assert "security" in conv.tags
        assert conv.rule == "All endpoints must use the auth decorator"

    def test_fallback_search_no_match(self, tmp_path: Path) -> None:
        """Fallback search returns empty conventions when nothing matches."""
        project = _setup_project(tmp_path)
        _create_convention_file(project, "Auth decorator required", tags=["auth"])

        results = unified_search(project, query="xyznonexistent", link_graph=None)
        assert len(results.conventions) == 0


# ---------------------------------------------------------------------------
# End-to-end CLI tests
# ---------------------------------------------------------------------------


class TestSearchCLIConventions:
    """End-to-end CLI tests for convention support in `lexi search`."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        from typer.testing import CliRunner

        from lexibrary.cli import lexi_app

        runner = CliRunner()
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexi_app, args)
        finally:
            os.chdir(old_cwd)

    def test_search_returns_conventions_via_fallback(self, tmp_path: Path) -> None:
        """lexi search returns convention matches via file-scanning fallback."""
        project = _setup_project(tmp_path)
        _create_convention_file(project, "Auth required", tags=["auth", "security"])

        result = self._invoke(project, ["search", "auth"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Conventions" in output
        assert "Auth required" in output

    def test_search_by_tag_returns_conventions(self, tmp_path: Path) -> None:
        """lexi search --tag returns convention matches via fallback."""
        project = _setup_project(tmp_path)
        _create_convention_file(project, "Auth required", tags=["security"])

        result = self._invoke(project, ["search", "--tag", "security"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Conventions" in output
        assert "Auth required" in output

    def test_search_omits_empty_conventions_group(self, tmp_path: Path) -> None:
        """When no conventions match, the Conventions group is omitted."""
        project = _setup_project(tmp_path)
        # Create a convention that will NOT match the search
        _create_convention_file(project, "Python style guide", tags=["style"])

        result = self._invoke(project, ["search", "xyznonexistent"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Conventions" not in output

    def test_search_convention_via_fts_index(self, tmp_path: Path) -> None:
        """lexi search returns conventions via FTS when index.db exists."""
        project = _setup_project(tmp_path)
        db_path = _create_linkgraph_db(project)

        _create_populated_index(
            db_path,
            artifacts=[
                (
                    1,
                    ".lexibrary/conventions/auth-required.md",
                    "convention",
                    "Auth decorator",
                    "active",
                ),
            ],
            fts=[
                (1, "Auth decorator", "All endpoints require the auth decorator"),
            ],
        )

        result = self._invoke(project, ["search", "decorator"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Conventions" in output
        assert "Auth decorator" in output

    def test_search_convention_via_tag_index(self, tmp_path: Path) -> None:
        """lexi search --tag returns conventions via index when index.db exists."""
        project = _setup_project(tmp_path)
        db_path = _create_linkgraph_db(project)

        _create_populated_index(
            db_path,
            artifacts=[
                (
                    1,
                    ".lexibrary/conventions/auth-required.md",
                    "convention",
                    "Auth required",
                    "active",
                ),
            ],
            tags=[
                (1, "security"),
            ],
        )

        result = self._invoke(project, ["search", "--tag", "security"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Conventions" in output
        assert "Auth required" in output


# ---------------------------------------------------------------------------
# ID column rendering tests (Group 8 -- search-first-workflow)
# ---------------------------------------------------------------------------


class TestMarkdownIDColumn:
    """8.1 -- Search output includes ID column in markdown format."""

    def test_concept_table_has_id_column(self) -> None:
        """Concept markdown table includes an ID column header and shows the ID value."""
        from lexibrary.search import _ConceptResult

        results = SearchResults(
            concepts=[
                _ConceptResult(
                    id="CN-001",
                    name="Authentication",
                    status="active",
                    tags=["security"],
                    summary="Auth logic",
                )
            ]
        )
        output = _render_to_string(results)
        assert "| ID" in output
        assert "CN-001" in output

    def test_convention_table_has_id_column(self) -> None:
        """Convention markdown table includes an ID column header and shows the ID value."""
        from lexibrary.search import _ConventionResult

        results = SearchResults(
            conventions=[
                _ConventionResult(
                    id="CV-010",
                    title="Require type hints",
                    scope="project",
                    status="active",
                    tags=["typing"],
                    rule="All functions must have type annotations",
                )
            ]
        )
        output = _render_to_string(results)
        assert "| ID" in output
        assert "CV-010" in output

    def test_design_file_table_has_id_column(self) -> None:
        """Design file markdown table includes an ID column header and shows the ID value."""
        from lexibrary.search import _DesignFileResult

        results = SearchResults(
            design_files=[
                _DesignFileResult(
                    id="DS-005",
                    source_path="src/auth.py",
                    description="Authentication handler",
                    tags=["security"],
                )
            ]
        )
        output = _render_to_string(results)
        assert "| ID" in output
        assert "DS-005" in output

    def test_stack_table_has_id_column(self) -> None:
        """Stack markdown table includes an ID column header and shows the post_id value."""
        from lexibrary.search import _StackResult

        results = SearchResults(
            stack_posts=[
                _StackResult(
                    post_id="ST-007",
                    title="Login timeout bug",
                    status="open",
                    votes=3,
                    tags=["auth"],
                )
            ]
        )
        output = _render_to_string(results)
        assert "| ID" in output
        assert "ST-007" in output

    def test_playbook_table_has_id_column(self) -> None:
        """Playbook markdown table includes an ID column header and shows the ID value."""
        from lexibrary.search import _PlaybookResult

        results = SearchResults(
            playbooks=[
                _PlaybookResult(
                    id="PB-003",
                    title="Deploy procedure",
                    status="active",
                    tags=["ops"],
                    overview="How to deploy",
                )
            ]
        )
        output = _render_to_string(results)
        assert "| ID" in output
        assert "PB-003" in output


class TestStackIDShowsArtifactCode:
    """8.2 -- Stack search results show ST-NNN IDs, not file paths."""

    def test_tag_search_stack_uses_artifact_code_not_path(self, tmp_path: Path) -> None:
        """Tag search returns stack results with ST-NNN post_id from artifact_code."""
        project = _setup_project(tmp_path)
        db_path = _create_linkgraph_db(project)

        _create_populated_index(
            db_path,
            artifacts=[(1, ".lexibrary/stack/ST-042.md", "stack", "Fix timeout", "open")],
            tags=[(1, "auth")],
        )
        # Set artifact_code so the search path picks it up
        conn = sqlite3.connect(str(db_path))
        conn.execute("UPDATE artifacts SET artifact_code = 'ST-042' WHERE id = 1")
        conn.commit()
        conn.close()

        graph = LinkGraph.open(db_path)
        assert graph is not None
        try:
            results = unified_search(project, tag="auth", link_graph=graph)
            assert results.has_results()
            assert len(results.stack_posts) == 1
            assert results.stack_posts[0].post_id == "ST-042"
            # Must NOT be the raw file path
            assert ".lexibrary/stack/" not in results.stack_posts[0].post_id
        finally:
            graph.close()

    def test_fts_search_stack_uses_artifact_code_not_path(self, tmp_path: Path) -> None:
        """FTS search returns stack results with ST-NNN post_id from artifact_code."""
        project = _setup_project(tmp_path)
        db_path = _create_linkgraph_db(project)

        _create_populated_index(
            db_path,
            artifacts=[(1, ".lexibrary/stack/ST-099.md", "stack", "Memory leak fix", "open")],
            fts=[(1, "Memory leak fix", "Fixed a memory leak in the connection pool")],
        )
        conn = sqlite3.connect(str(db_path))
        conn.execute("UPDATE artifacts SET artifact_code = 'ST-099' WHERE id = 1")
        conn.commit()
        conn.close()

        graph = LinkGraph.open(db_path)
        assert graph is not None
        try:
            results = unified_search(project, query="memory", link_graph=graph)
            assert results.has_results()
            assert len(results.stack_posts) == 1
            assert results.stack_posts[0].post_id == "ST-099"
            assert ".lexibrary/stack/" not in results.stack_posts[0].post_id
        finally:
            graph.close()

    def test_stack_renders_st_id_in_markdown(self) -> None:
        """Stack results render ST-NNN in the ID column, not a file path."""
        from lexibrary.search import _StackResult

        results = SearchResults(
            stack_posts=[
                _StackResult(
                    post_id="ST-042",
                    title="Fix timeout",
                    status="open",
                    votes=1,
                    tags=["auth"],
                )
            ]
        )
        output = _render_to_string(results)
        assert "ST-042" in output
        assert ".lexibrary/stack/" not in output


class TestJSONOutputTypeAndId:
    """8.3 -- JSON output includes 'type' and 'id' fields for all artifact types."""

    def _render_json(self, results: SearchResults) -> list[dict[str, object]]:
        """Render SearchResults as JSON and parse back into a list of dicts."""
        import json

        from lexibrary.cli._format import OutputFormat, set_format

        buf = StringIO()
        old_format = OutputFormat.markdown
        set_format(OutputFormat.json)
        try:
            with patch("lexibrary.cli._output.sys.stdout", buf):
                results.render()
        finally:
            set_format(old_format)
        return json.loads(buf.getvalue())

    def test_concept_json_has_type_and_id(self) -> None:
        """Concept JSON record includes 'type': 'concept' and 'id' field."""
        from lexibrary.search import _ConceptResult

        results = SearchResults(
            concepts=[
                _ConceptResult(
                    id="CN-001",
                    name="Authentication",
                    status="active",
                    tags=["security"],
                    summary="Auth logic",
                )
            ]
        )
        records = self._render_json(results)
        assert len(records) == 1
        assert records[0]["type"] == "concept"
        assert records[0]["id"] == "CN-001"

    def test_convention_json_has_type_and_id(self) -> None:
        """Convention JSON record includes 'type': 'convention' and 'id' field."""
        from lexibrary.search import _ConventionResult

        results = SearchResults(
            conventions=[
                _ConventionResult(
                    id="CV-010",
                    title="Type hints required",
                    scope="project",
                    status="active",
                    tags=["typing"],
                    rule="All functions need type annotations",
                )
            ]
        )
        records = self._render_json(results)
        assert len(records) == 1
        assert records[0]["type"] == "convention"
        assert records[0]["id"] == "CV-010"

    def test_stack_json_has_type_and_id(self) -> None:
        """Stack JSON record includes 'type': 'stack' and 'id' field."""
        from lexibrary.search import _StackResult

        results = SearchResults(
            stack_posts=[
                _StackResult(
                    post_id="ST-042",
                    title="Timeout bug",
                    status="open",
                    votes=1,
                    tags=["auth"],
                )
            ]
        )
        records = self._render_json(results)
        assert len(records) == 1
        assert records[0]["type"] == "stack"
        assert records[0]["id"] == "ST-042"

    def test_design_json_has_type_and_id(self) -> None:
        """Design file JSON record includes 'type': 'design' and 'id' field."""
        from lexibrary.search import _DesignFileResult

        results = SearchResults(
            design_files=[
                _DesignFileResult(
                    id="DS-005",
                    source_path="src/auth.py",
                    description="Auth handler",
                    tags=["security"],
                )
            ]
        )
        records = self._render_json(results)
        assert len(records) == 1
        assert records[0]["type"] == "design"
        assert records[0]["id"] == "DS-005"

    def test_playbook_json_has_type_and_id(self) -> None:
        """Playbook JSON record includes 'type': 'playbook' and 'id' field."""
        from lexibrary.search import _PlaybookResult

        results = SearchResults(
            playbooks=[
                _PlaybookResult(
                    id="PB-003",
                    title="Deploy procedure",
                    status="active",
                    tags=["ops"],
                    overview="How to deploy",
                )
            ]
        )
        records = self._render_json(results)
        assert len(records) == 1
        assert records[0]["type"] == "playbook"
        assert records[0]["id"] == "PB-003"

    def test_mixed_json_all_have_type_and_id(self) -> None:
        """All artifact types in a mixed result set include 'type' and 'id'."""
        from lexibrary.search import (
            _ConceptResult,
            _ConventionResult,
            _DesignFileResult,
            _PlaybookResult,
            _StackResult,
        )

        results = SearchResults(
            concepts=[
                _ConceptResult(id="CN-001", name="Auth", status="active", tags=[], summary="")
            ],
            conventions=[
                _ConventionResult(
                    id="CV-001",
                    title="Hints",
                    scope="project",
                    status="active",
                    tags=[],
                    rule="",
                )
            ],
            stack_posts=[
                _StackResult(post_id="ST-001", title="Bug", status="open", votes=0, tags=[])
            ],
            design_files=[
                _DesignFileResult(id="DS-001", source_path="src/a.py", description="", tags=[])
            ],
            playbooks=[
                _PlaybookResult(id="PB-001", title="Deploy", status="active", tags=[], overview="")
            ],
        )
        records = self._render_json(results)
        assert len(records) == 5
        for record in records:
            assert "type" in record, f"Missing 'type' in {record}"
            assert "id" in record, f"Missing 'id' in {record}"
        types = {r["type"] for r in records}
        assert types == {"concept", "convention", "stack", "design", "playbook"}


# ---------------------------------------------------------------------------
# 13 -- Symbol search via unified_search (symbol-graph-2 group 13)
# ---------------------------------------------------------------------------


class TestUnifiedSearchSymbolType:
    """End-to-end unit tests for ``unified_search(..., artifact_type='symbol')``.

    Seeds a minimal ``symbols.db`` via the shared Phase 2 fixture and then
    drives ``unified_search`` directly (no CLI runner) so the routing path,
    flag rejection, and ``SearchResults.symbol_results`` wiring are all
    exercised at the Python API level.
    """

    def test_symbol_type_returns_symbol_results(self, tmp_path: Path) -> None:
        """``artifact_type='symbol'`` populates ``symbol_results`` from
        ``SymbolQueryService.search_symbols``."""
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
            query="bar",
            artifact_type="symbol",
        )

        assert results.has_results()
        assert len(results.symbol_results) >= 1
        # The seeded corpus maps ``bar`` to ``a.bar`` at ``src/a.py``.
        qualified = {sym.qualified_name for sym in results.symbol_results}
        assert "a.bar" in qualified
        # Other artifact buckets remain empty on the symbol-search path.
        assert results.concepts == []
        assert results.conventions == []
        assert results.stack_posts == []
        assert results.design_files == []
        assert results.playbooks == []

    def test_symbol_type_empty_query_returns_empty_results(self, tmp_path: Path) -> None:
        """``query=None`` on the symbol branch returns empty results rather
        than dispatching a wildcard LIKE scan."""
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
            query=None,
            artifact_type="symbol",
        )
        assert results.symbol_results == []
        assert not results.has_results()

    def test_symbol_type_missing_db_returns_empty(self, tmp_path: Path) -> None:
        """No ``symbols.db`` means ``SymbolQueryService`` degrades gracefully
        and ``unified_search`` returns an empty ``SearchResults``."""
        project = _setup_project(tmp_path)

        results = unified_search(
            project,
            query="anything",
            artifact_type="symbol",
        )
        assert results.symbol_results == []
        assert not results.has_results()

    def test_symbol_type_rejects_tag_flag(self, tmp_path: Path) -> None:
        """Combining ``--tag`` with ``--type symbol`` raises ``ValueError``
        so the CLI handler can turn it into exit 1."""
        import pytest  # noqa: PLC0415

        project = _setup_project(tmp_path)

        with pytest.raises(ValueError, match="--tag is not supported"):
            unified_search(
                project,
                query="bar",
                artifact_type="symbol",
                tag="security",
            )

    def test_symbol_type_rejects_tags_list(self, tmp_path: Path) -> None:
        """Passing ``tags=[...]`` (the multi-tag form) also raises."""
        import pytest  # noqa: PLC0415

        project = _setup_project(tmp_path)

        with pytest.raises(ValueError, match="--tag is not supported"):
            unified_search(
                project,
                query="bar",
                artifact_type="symbol",
                tags=["security"],
            )

    def test_symbol_type_rejects_concept_filter(self, tmp_path: Path) -> None:
        """``concept=<name>`` is rejected on the symbol-search path."""
        import pytest  # noqa: PLC0415

        project = _setup_project(tmp_path)

        with pytest.raises(ValueError, match="--concept is not supported"):
            unified_search(
                project,
                query="bar",
                artifact_type="symbol",
                concept="auth",
            )

    def test_symbol_type_rejects_resolution_type_filter(self, tmp_path: Path) -> None:
        """``resolution_type`` is rejected on the symbol-search path."""
        import pytest  # noqa: PLC0415

        project = _setup_project(tmp_path)

        with pytest.raises(ValueError, match="--resolution-type is not supported"):
            unified_search(
                project,
                query="bar",
                artifact_type="symbol",
                resolution_type="answered",
            )

    def test_symbol_type_rejects_include_stale(self, tmp_path: Path) -> None:
        """``include_stale=True`` is rejected on the symbol-search path."""
        import pytest  # noqa: PLC0415

        project = _setup_project(tmp_path)

        with pytest.raises(ValueError, match="--include-stale is not supported"):
            unified_search(
                project,
                query="bar",
                artifact_type="symbol",
                include_stale=True,
            )

    def test_symbol_type_rejects_include_deprecated(self, tmp_path: Path) -> None:
        """``include_deprecated=True`` is rejected on the symbol-search path."""
        import pytest  # noqa: PLC0415

        project = _setup_project(tmp_path)

        with pytest.raises(ValueError, match="--all is not supported"):
            unified_search(
                project,
                query="bar",
                artifact_type="symbol",
                include_deprecated=True,
            )

    def test_symbol_type_rejects_status_filter(self, tmp_path: Path) -> None:
        """``status=<value>`` is rejected on the symbol-search path."""
        import pytest  # noqa: PLC0415

        project = _setup_project(tmp_path)

        with pytest.raises(ValueError, match="--status is not supported"):
            unified_search(
                project,
                query="bar",
                artifact_type="symbol",
                status="active",
            )
