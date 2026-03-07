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

import yaml
from rich.console import Console

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
) -> None:
    """Populate a link graph database with artifacts, tags, and FTS data."""
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
    conn.commit()
    conn.close()


def _render_to_string(results: SearchResults) -> str:
    """Render SearchResults to a string for assertion."""
    buf = StringIO()
    console = Console(file=buf, width=120, force_terminal=True)
    results.render(console)
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
        """Convention artifacts in the index are returned by tag search."""
        project = _setup_project(tmp_path)
        db_path = _create_linkgraph_db(project)

        _create_populated_index(
            db_path,
            artifacts=[
                (1, ".lexibrary/conventions/auth-required.md", "convention", "Auth required", "active"),
            ],
            tags=[
                (1, "security"),
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
                (2, ".lexibrary/conventions/auth-required.md", "convention", "Auth required", "active"),
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
        """FTS search returns convention artifacts from the index."""
        project = _setup_project(tmp_path)
        db_path = _create_linkgraph_db(project)

        _create_populated_index(
            db_path,
            artifacts=[
                (1, ".lexibrary/conventions/auth-required.md", "convention", "Auth decorator required", "active"),
            ],
            fts=[
                (1, "Auth decorator required", "All endpoints must use the auth decorator"),
            ],
        )

        graph = LinkGraph.open(db_path)
        assert graph is not None
        try:
            results = unified_search(project, query="decorator", link_graph=graph)
            assert results.has_results()
            assert len(results.conventions) == 1
            assert results.conventions[0].title == "Auth decorator required"
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
                (2, ".lexibrary/conventions/auth-required.md", "convention", "Auth Required", "active"),
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
        _create_convention_file(
            project, "Models convention", tags=["models"], scope="src/models"
        )
        _create_convention_file(
            project, "Project wide convention", tags=["auth"], scope="project"
        )

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
                (1, ".lexibrary/conventions/auth-required.md", "convention", "Auth decorator", "active"),
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
                (1, ".lexibrary/conventions/auth-required.md", "convention", "Auth required", "active"),
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
