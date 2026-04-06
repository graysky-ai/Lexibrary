"""Tests for linkgraph query interface -- LinkGraph and result dataclasses.

Covers all query methods (get_artifact, resolve_alias, reverse_deps,
search_by_tag, full_text_search, get_conventions, build_summary, traverse)
as well as graceful degradation on open, context manager support, and
read-only enforcement.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from lexibrary.linkgraph.query import (
    ArtifactResult,
    BuildSummaryEntry,
    ConventionResult,
    LinkGraph,
    LinkResult,
    TraversalNode,
)
from lexibrary.linkgraph.schema import SCHEMA_VERSION, ensure_schema

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def writable_db(tmp_path: Path) -> Path:
    """Create a valid link graph database on disk and return its path.

    The database has the correct schema and schema version, ready for
    ``LinkGraph.open()`` to accept.
    """
    db_path = tmp_path / "index.db"
    conn = sqlite3.connect(str(db_path))
    ensure_schema(conn)
    conn.close()
    return db_path


@pytest.fixture()
def populated_db(tmp_path: Path) -> Path:
    """Create a database populated with representative test data.

    Contains artifacts, links, tags, aliases, conventions, FTS rows,
    and build_log entries sufficient for testing all query methods.
    """
    db_path = tmp_path / "index.db"
    conn = sqlite3.connect(str(db_path))
    ensure_schema(conn)

    # -- artifacts ----------------------------------------------------------
    conn.execute(
        "INSERT INTO artifacts (id, path, kind, title, status) "
        "VALUES (1, 'src/auth/service.py', 'source', 'Auth service', 'active')"
    )
    conn.execute(
        "INSERT INTO artifacts (id, path, kind, title, status) "
        "VALUES (2, '.lexibrary/designs/src/auth/service.py.md', "
        "'design', 'Auth service design', NULL)"
    )
    conn.execute(
        "INSERT INTO artifacts (id, path, kind, title, status) "
        "VALUES (3, '.lexibrary/concepts/Authentication.md', 'concept', 'Authentication', 'active')"
    )
    conn.execute(
        "INSERT INTO artifacts (id, path, kind, title, status) "
        "VALUES (4, 'src/api/controller.py', 'source', 'API controller', 'active')"
    )
    conn.execute(
        "INSERT INTO artifacts (id, path, kind, title, status) "
        "VALUES (5, 'src/core/utils.py', 'source', 'Core utilities', 'active')"
    )
    conn.execute(
        "INSERT INTO artifacts (id, path, kind, title, status) "
        "VALUES (6, '.lexibrary/concepts/Authorization.md', 'concept', 'Authorization', 'active')"
    )
    conn.execute(
        "INSERT INTO artifacts (id, path, kind, title, status) "
        "VALUES (7, '.lexibrary/stack/ST-001.md', 'stack', 'How to handle auth tokens', 'open')"
    )
    conn.execute(
        "INSERT INTO artifacts (id, path, kind, title, status) "
        "VALUES (8, 'src/middleware/cors.py', 'source', 'CORS middleware', 'active')"
    )

    # -- links --------------------------------------------------------------
    # design_source: design -> source
    conn.execute(
        "INSERT INTO links (source_id, target_id, link_type, link_context) "
        "VALUES (2, 1, 'design_source', NULL)"
    )
    # ast_import: controller -> auth service
    conn.execute(
        "INSERT INTO links (source_id, target_id, link_type, link_context) "
        "VALUES (4, 1, 'ast_import', 'from src.auth.service import AuthService')"
    )
    # ast_import: controller -> utils
    conn.execute(
        "INSERT INTO links (source_id, target_id, link_type, link_context) "
        "VALUES (4, 5, 'ast_import', 'from src.core.utils import helper')"
    )
    # wikilink: design -> concept
    conn.execute(
        "INSERT INTO links (source_id, target_id, link_type, link_context) "
        "VALUES (2, 3, 'wikilink', NULL)"
    )
    # ast_import: auth service -> utils
    conn.execute(
        "INSERT INTO links (source_id, target_id, link_type, link_context) "
        "VALUES (1, 5, 'ast_import', 'from src.core.utils import hash_password')"
    )
    # wikilink: concept Authentication -> concept Authorization
    conn.execute(
        "INSERT INTO links (source_id, target_id, link_type, link_context) "
        "VALUES (3, 6, 'wikilink', NULL)"
    )
    # stack_concept_ref: stack -> Authentication concept
    conn.execute(
        "INSERT INTO links (source_id, target_id, link_type, link_context) "
        "VALUES (7, 3, 'stack_concept_ref', NULL)"
    )
    # ast_import: cors middleware -> utils
    conn.execute(
        "INSERT INTO links (source_id, target_id, link_type, link_context) "
        "VALUES (8, 5, 'ast_import', 'from src.core.utils import validate')"
    )

    # -- tags ---------------------------------------------------------------
    conn.execute("INSERT INTO tags (artifact_id, tag) VALUES (2, 'authentication')")
    conn.execute("INSERT INTO tags (artifact_id, tag) VALUES (2, 'security')")
    conn.execute("INSERT INTO tags (artifact_id, tag) VALUES (3, 'authentication')")
    conn.execute("INSERT INTO tags (artifact_id, tag) VALUES (6, 'security')")
    conn.execute("INSERT INTO tags (artifact_id, tag) VALUES (7, 'authentication')")

    # -- aliases ------------------------------------------------------------
    conn.execute("INSERT INTO aliases (artifact_id, alias) VALUES (3, 'auth')")
    conn.execute("INSERT INTO aliases (artifact_id, alias) VALUES (3, 'authn')")
    conn.execute("INSERT INTO aliases (artifact_id, alias) VALUES (6, 'authz')")

    # -- conventions --------------------------------------------------------
    conn.execute(
        "INSERT INTO conventions (artifact_id, directory_path, ordinal, body) "
        "VALUES (1, 'src', 0, 'All source files must include type annotations.')"
    )
    conn.execute(
        "INSERT INTO conventions (artifact_id, directory_path, ordinal, body) "
        "VALUES (1, 'src', 1, 'Use absolute imports only.')"
    )
    conn.execute(
        "INSERT INTO conventions (artifact_id, directory_path, ordinal, body) "
        "VALUES (1, 'src/auth', 0, 'Auth modules must validate tokens before processing.')"
    )
    conn.execute(
        "INSERT INTO conventions (artifact_id, directory_path, ordinal, body) "
        "VALUES (1, 'src/auth/middleware', 0, 'Middleware must set request context.')"
    )

    # -- FTS5 ---------------------------------------------------------------
    conn.execute(
        "INSERT INTO artifacts_fts (rowid, title, body) VALUES (?, ?, ?)",
        (1, "Auth service", "Authentication service handles token validation and user identity"),
    )
    conn.execute(
        "INSERT INTO artifacts_fts (rowid, title, body) VALUES (?, ?, ?)",
        (2, "Auth service design", "Design file for the authentication service module"),
    )
    conn.execute(
        "INSERT INTO artifacts_fts (rowid, title, body) VALUES (?, ?, ?)",
        (3, "Authentication", "Concept covering authentication patterns and best practices"),
    )
    conn.execute(
        "INSERT INTO artifacts_fts (rowid, title, body) VALUES (?, ?, ?)",
        (4, "API controller", "REST API controller for handling HTTP requests"),
    )
    conn.execute(
        "INSERT INTO artifacts_fts (rowid, title, body) VALUES (?, ?, ?)",
        (5, "Core utilities", "Shared utility functions including hashing and validation"),
    )

    # -- build_log ----------------------------------------------------------
    build_ts = "2026-02-22T10:00:00+00:00"
    _blog_sql = (
        "INSERT INTO build_log "
        "(build_started, build_type, artifact_path, artifact_kind, action, duration_ms) "
        "VALUES (?, ?, ?, ?, ?, ?)"
    )
    conn.execute(_blog_sql, (build_ts, "full", "src/auth/service.py", "source", "created", 100))
    conn.execute(
        _blog_sql,
        (build_ts, "full", ".lexibrary/designs/src/auth/service.py.md", "design", "created", 50),
    )
    conn.execute(_blog_sql, (build_ts, "full", "src/api/controller.py", "source", "created", 75))
    conn.execute(_blog_sql, (build_ts, "full", "src/core/utils.py", "source", "unchanged", 10))

    conn.commit()
    conn.close()
    return db_path


@pytest.fixture()
def graph(populated_db: Path) -> LinkGraph:
    """Return an open LinkGraph against the populated database.

    The caller must close it manually or use it inside a ``with`` block.
    """
    g = LinkGraph.open(populated_db)
    assert g is not None, "Failed to open populated test database"
    return g


# ---------------------------------------------------------------------------
# 7.1 -- LinkGraph.open() graceful degradation: missing file returns None
# ---------------------------------------------------------------------------


class TestOpenMissingFile:
    """7.1 -- LinkGraph.open() returns None for a non-existent database file."""

    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        """open() with a non-existent path returns None without raising."""
        result = LinkGraph.open(tmp_path / "does_not_exist.db")
        assert result is None

    def test_missing_file_no_side_effects(self, tmp_path: Path) -> None:
        """open() does not create a file when the database does not exist."""
        db_path = tmp_path / "phantom.db"
        LinkGraph.open(db_path)
        assert not db_path.exists()


# ---------------------------------------------------------------------------
# 7.2 -- LinkGraph.open() graceful degradation: corrupt file returns None
# ---------------------------------------------------------------------------


class TestOpenCorruptFile:
    """7.2 -- LinkGraph.open() returns None for a corrupt database file."""

    def test_corrupt_file_returns_none(self, tmp_path: Path) -> None:
        """A file with non-SQLite content causes open() to return None."""
        corrupt = tmp_path / "corrupt.db"
        corrupt.write_text("this is not a sqlite database at all!")
        result = LinkGraph.open(corrupt)
        assert result is None

    def test_corrupt_binary_returns_none(self, tmp_path: Path) -> None:
        """A binary file that is not a valid SQLite database returns None."""
        corrupt = tmp_path / "corrupt_bin.db"
        corrupt.write_bytes(b"\x00\x01\x02\x03" * 100)
        result = LinkGraph.open(corrupt)
        assert result is None


# ---------------------------------------------------------------------------
# 7.3 -- LinkGraph.open() graceful degradation: schema version mismatch
# ---------------------------------------------------------------------------


class TestOpenSchemaMismatch:
    """7.3 -- LinkGraph.open() returns None when schema version does not match."""

    def test_wrong_schema_version_returns_none(self, writable_db: Path) -> None:
        """A database with a different schema_version returns None from open()."""
        # Write a different schema version into the meta table
        conn = sqlite3.connect(str(writable_db))
        conn.execute(
            "UPDATE meta SET value = ? WHERE key = 'schema_version'",
            (str(SCHEMA_VERSION + 99),),
        )
        conn.commit()
        conn.close()

        result = LinkGraph.open(writable_db)
        assert result is None

    def test_missing_schema_version_returns_none(self, writable_db: Path) -> None:
        """A database with no schema_version row in meta returns None."""
        conn = sqlite3.connect(str(writable_db))
        conn.execute("DELETE FROM meta WHERE key = 'schema_version'")
        conn.commit()
        conn.close()

        result = LinkGraph.open(writable_db)
        assert result is None

    def test_empty_meta_table_returns_none(self, writable_db: Path) -> None:
        """A database with an empty meta table returns None."""
        conn = sqlite3.connect(str(writable_db))
        conn.execute("DELETE FROM meta")
        conn.commit()
        conn.close()

        result = LinkGraph.open(writable_db)
        assert result is None


# ---------------------------------------------------------------------------
# 7.4 -- LinkGraph.open() successful open and context manager close
# ---------------------------------------------------------------------------


class TestOpenSuccessAndContextManager:
    """7.4 -- Successful open() returns LinkGraph; context manager closes connection."""

    def test_successful_open(self, writable_db: Path) -> None:
        """open() returns a LinkGraph instance for a valid database."""
        g = LinkGraph.open(writable_db)
        assert g is not None
        assert isinstance(g, LinkGraph)
        g.close()

    def test_context_manager_closes_connection(self, writable_db: Path) -> None:
        """Using LinkGraph as a context manager closes the connection on exit."""
        g = LinkGraph.open(writable_db)
        assert g is not None

        with g:
            # Connection should work inside the block
            pass

        # After exiting the context manager, the connection should be closed.
        # Attempting a query on a closed connection raises ProgrammingError.
        with pytest.raises(sqlite3.ProgrammingError):
            g._conn.execute("SELECT 1")

    def test_explicit_close(self, writable_db: Path) -> None:
        """Calling close() directly closes the underlying connection."""
        g = LinkGraph.open(writable_db)
        assert g is not None
        g.close()

        with pytest.raises(sqlite3.ProgrammingError):
            g._conn.execute("SELECT 1")

    def test_open_returns_linkgraph_via_context_manager(self, writable_db: Path) -> None:
        """Context manager __enter__ returns self."""
        g = LinkGraph.open(writable_db)
        assert g is not None
        with g as entered:
            assert entered is g


# ---------------------------------------------------------------------------
# 7.5 -- get_artifact() with existing and non-existing paths
# ---------------------------------------------------------------------------


class TestGetArtifact:
    """7.5 -- get_artifact() returns ArtifactResult or None."""

    def test_existing_path(self, graph: LinkGraph) -> None:
        """get_artifact() returns ArtifactResult for an indexed path."""
        result = graph.get_artifact("src/auth/service.py")
        assert result is not None
        assert isinstance(result, ArtifactResult)
        assert result.path == "src/auth/service.py"
        assert result.kind == "source"
        assert result.title == "Auth service"
        assert result.status == "active"
        assert result.id == 1
        graph.close()

    def test_nonexistent_path(self, graph: LinkGraph) -> None:
        """get_artifact() returns None for a path not in the index."""
        result = graph.get_artifact("nonexistent/file.py")
        assert result is None
        graph.close()

    def test_design_artifact(self, graph: LinkGraph) -> None:
        """get_artifact() can return design-type artifacts."""
        result = graph.get_artifact(".lexibrary/designs/src/auth/service.py.md")
        assert result is not None
        assert result.kind == "design"
        graph.close()

    def test_concept_artifact(self, graph: LinkGraph) -> None:
        """get_artifact() can return concept-type artifacts."""
        result = graph.get_artifact(".lexibrary/concepts/Authentication.md")
        assert result is not None
        assert result.kind == "concept"
        assert result.title == "Authentication"
        graph.close()


# ---------------------------------------------------------------------------
# 7.6 -- reverse_deps() with and without link_type filter
# ---------------------------------------------------------------------------


class TestReverseDeps:
    """7.6 -- reverse_deps() returns inbound links to an artifact."""

    def test_all_inbound_links(self, graph: LinkGraph) -> None:
        """reverse_deps() without filter returns all inbound link types."""
        results = graph.reverse_deps("src/auth/service.py")
        assert len(results) >= 2
        assert all(isinstance(r, LinkResult) for r in results)
        # Should include ast_import from controller and design_source from design
        link_types = {r.link_type for r in results}
        assert "ast_import" in link_types
        assert "design_source" in link_types
        graph.close()

    def test_filtered_by_link_type(self, graph: LinkGraph) -> None:
        """reverse_deps() with link_type filter returns only matching links."""
        results = graph.reverse_deps("src/auth/service.py", link_type="ast_import")
        assert len(results) >= 1
        assert all(r.link_type == "ast_import" for r in results)
        # controller -> auth service via ast_import
        source_paths = {r.source_path for r in results}
        assert "src/api/controller.py" in source_paths
        graph.close()

    def test_nonexistent_target(self, graph: LinkGraph) -> None:
        """reverse_deps() returns empty list for a path not in the index."""
        results = graph.reverse_deps("nonexistent/path.py")
        assert results == []
        graph.close()

    def test_no_inbound_links(self, graph: LinkGraph) -> None:
        """reverse_deps() returns empty list when artifact has no inbound links."""
        # controller has no inbound links in our test data
        results = graph.reverse_deps("src/api/controller.py")
        assert results == []
        graph.close()

    def test_link_context_populated(self, graph: LinkGraph) -> None:
        """reverse_deps() includes link_context when present."""
        results = graph.reverse_deps("src/auth/service.py", link_type="ast_import")
        assert any(r.link_context is not None for r in results)
        graph.close()


# ---------------------------------------------------------------------------
# 7.7 -- search_by_tag() with matching and non-matching tags
# ---------------------------------------------------------------------------


class TestSearchByTag:
    """7.7 -- search_by_tag() returns artifacts with matching tags."""

    def test_matching_tag(self, graph: LinkGraph) -> None:
        """search_by_tag() returns all artifacts tagged with the given tag."""
        results = graph.search_by_tag("authentication")
        assert len(results) >= 2
        assert all(isinstance(r, ArtifactResult) for r in results)
        paths = {r.path for r in results}
        assert ".lexibrary/designs/src/auth/service.py.md" in paths
        assert ".lexibrary/concepts/Authentication.md" in paths
        graph.close()

    def test_non_matching_tag(self, graph: LinkGraph) -> None:
        """search_by_tag() returns empty list for a non-existent tag."""
        results = graph.search_by_tag("nonexistent-tag-xyz")
        assert results == []
        graph.close()

    def test_security_tag(self, graph: LinkGraph) -> None:
        """search_by_tag() finds multiple artifacts with the same tag."""
        results = graph.search_by_tag("security")
        assert len(results) >= 2
        paths = {r.path for r in results}
        assert ".lexibrary/designs/src/auth/service.py.md" in paths
        assert ".lexibrary/concepts/Authorization.md" in paths
        graph.close()


# ---------------------------------------------------------------------------
# 7.8 -- full_text_search() including special character handling
# ---------------------------------------------------------------------------


class TestFullTextSearch:
    """7.8 -- full_text_search() queries FTS5 with safe quoting."""

    def test_matching_query(self, graph: LinkGraph) -> None:
        """full_text_search() returns relevant artifacts for a matching term."""
        results = graph.full_text_search("authentication")
        assert len(results) >= 1
        assert all(isinstance(r, ArtifactResult) for r in results)
        graph.close()

    def test_no_matching_results(self, graph: LinkGraph) -> None:
        """full_text_search() returns empty list when nothing matches."""
        results = graph.full_text_search("xyznonexistent12345")
        assert results == []
        graph.close()

    def test_special_fts_characters_safe(self, graph: LinkGraph) -> None:
        """full_text_search() safely handles FTS5 operator characters.

        The query is double-quoted internally, so FTS5 operators like OR,
        AND, NOT are treated as literal terms.
        """
        # This should NOT raise an FTS5 syntax error
        results = graph.full_text_search("error OR warning")
        assert isinstance(results, list)
        graph.close()

    def test_double_quotes_in_query(self, graph: LinkGraph) -> None:
        """full_text_search() handles embedded double quotes without errors."""
        results = graph.full_text_search('term with "quotes" inside')
        assert isinstance(results, list)
        graph.close()

    def test_limit_parameter(self, graph: LinkGraph) -> None:
        """full_text_search() respects the limit parameter."""
        results = graph.full_text_search("authentication", limit=1)
        assert len(results) <= 1
        graph.close()

    def test_multi_word_query(self, graph: LinkGraph) -> None:
        """full_text_search() handles multi-word queries."""
        results = graph.full_text_search("token validation")
        assert isinstance(results, list)
        graph.close()


# ---------------------------------------------------------------------------
# 7.8b -- full_text_search(raw=True) bypasses double-quote wrapping
# ---------------------------------------------------------------------------


class TestFullTextSearchRaw:
    """Tests for full_text_search(raw=True) — raw FTS5 expression passthrough."""

    def test_raw_true_passes_query_as_is(self, graph: LinkGraph) -> None:
        """raw=True passes the query string directly without double-quote wrapping.

        An AND expression like '"auth" AND "service"' should work as a boolean
        FTS5 query when raw=True.
        """
        results = graph.full_text_search('"auth" AND "service"', raw=True)
        assert isinstance(results, list)
        # Should find Auth service (matches both tokens)
        assert len(results) >= 1
        graph.close()

    def test_raw_false_wraps_in_quotes(self, graph: LinkGraph) -> None:
        """raw=False (default) wraps the query in double quotes.

        FTS5 operators like AND/OR are treated as literal text, so
        'auth AND service' is searched as a literal phrase.
        """
        # This should NOT be interpreted as an AND expression
        results = graph.full_text_search("auth AND service", raw=False)
        assert isinstance(results, list)
        # "auth AND service" as a literal phrase — unlikely to match
        # (there is no document containing the literal string "auth AND service")
        graph.close()

    def test_raw_true_or_expression(self, graph: LinkGraph) -> None:
        """raw=True allows OR expressions in FTS5."""
        results = graph.full_text_search(
            '"authentication" OR "controller"', raw=True
        )
        assert isinstance(results, list)
        # Should match Authentication concept and API controller
        assert len(results) >= 2
        graph.close()

    def test_raw_default_is_false(self, graph: LinkGraph) -> None:
        """The default value of raw is False (existing behavior preserved)."""
        # A query with FTS5 operators should be safely quoted by default
        results = graph.full_text_search("NOT something OR other")
        assert isinstance(results, list)
        # Should not raise an FTS5 syntax error
        graph.close()

    def test_raw_true_with_limit(self, graph: LinkGraph) -> None:
        """raw=True works correctly with the limit parameter."""
        results = graph.full_text_search(
            '"authentication" OR "controller"', limit=1, raw=True
        )
        assert len(results) <= 1
        graph.close()


# ---------------------------------------------------------------------------
# 7.9 -- resolve_alias() with case-insensitive matching
# ---------------------------------------------------------------------------


class TestResolveAlias:
    """7.9 -- resolve_alias() returns ArtifactResult with case-insensitive matching."""

    def test_exact_match(self, graph: LinkGraph) -> None:
        """resolve_alias() matches an alias exactly."""
        result = graph.resolve_alias("auth")
        assert result is not None
        assert isinstance(result, ArtifactResult)
        assert result.path == ".lexibrary/concepts/Authentication.md"
        assert result.kind == "concept"
        graph.close()

    def test_case_insensitive_uppercase(self, graph: LinkGraph) -> None:
        """resolve_alias() matches case-insensitively (uppercase input)."""
        result = graph.resolve_alias("AUTH")
        assert result is not None
        assert result.path == ".lexibrary/concepts/Authentication.md"
        graph.close()

    def test_case_insensitive_mixed_case(self, graph: LinkGraph) -> None:
        """resolve_alias() matches case-insensitively (mixed case)."""
        result = graph.resolve_alias("Auth")
        assert result is not None
        assert result.path == ".lexibrary/concepts/Authentication.md"
        graph.close()

    def test_alternative_alias(self, graph: LinkGraph) -> None:
        """resolve_alias() resolves a different alias for the same concept."""
        result = graph.resolve_alias("authn")
        assert result is not None
        assert result.path == ".lexibrary/concepts/Authentication.md"
        graph.close()

    def test_alias_for_different_concept(self, graph: LinkGraph) -> None:
        """resolve_alias() resolves aliases pointing to different concepts."""
        result = graph.resolve_alias("authz")
        assert result is not None
        assert result.path == ".lexibrary/concepts/Authorization.md"
        graph.close()

    def test_nonexistent_alias(self, graph: LinkGraph) -> None:
        """resolve_alias() returns None for an unknown alias."""
        result = graph.resolve_alias("nonexistent-alias-xyz")
        assert result is None
        graph.close()


# ---------------------------------------------------------------------------
# 7.10 -- get_conventions() with multiple directory paths
# ---------------------------------------------------------------------------


class TestGetConventions:
    """7.10 -- get_conventions() returns conventions ordered by path hierarchy."""

    def test_multiple_directories(self, graph: LinkGraph) -> None:
        """get_conventions() returns conventions from root to leaf."""
        results = graph.get_conventions(["src", "src/auth", "src/auth/middleware"])
        assert len(results) >= 4
        assert all(isinstance(r, ConventionResult) for r in results)

        # Verify root conventions come first
        assert results[0].directory_path == "src"
        assert results[0].ordinal == 0
        assert results[1].directory_path == "src"
        assert results[1].ordinal == 1

        # Then the more specific directory
        auth_conventions = [r for r in results if r.directory_path == "src/auth"]
        assert len(auth_conventions) >= 1

        # Then the most specific directory
        middleware_conventions = [r for r in results if r.directory_path == "src/auth/middleware"]
        assert len(middleware_conventions) >= 1
        graph.close()

    def test_single_directory(self, graph: LinkGraph) -> None:
        """get_conventions() works with a single directory path."""
        results = graph.get_conventions(["src"])
        assert len(results) == 2
        assert all(r.directory_path == "src" for r in results)
        graph.close()

    def test_nonexistent_directory(self, graph: LinkGraph) -> None:
        """get_conventions() returns empty list for non-existent directories."""
        results = graph.get_conventions(["nonexistent/path"])
        assert results == []
        graph.close()

    def test_empty_list(self, graph: LinkGraph) -> None:
        """get_conventions() returns empty list for empty input."""
        results = graph.get_conventions([])
        assert results == []
        graph.close()

    def test_convention_body_content(self, graph: LinkGraph) -> None:
        """get_conventions() returns the full convention body text."""
        results = graph.get_conventions(["src"])
        assert any("type annotations" in r.body for r in results)
        graph.close()

    def test_ordering_preserves_caller_path_order(self, graph: LinkGraph) -> None:
        """get_conventions() sorts by the caller-specified directory order, not alphabetical."""
        # Reverse the order: leaf before root
        results = graph.get_conventions(["src/auth", "src"])
        # The first conventions should be from src/auth (it was listed first)
        assert results[0].directory_path == "src/auth"
        graph.close()

    def test_convention_result_extended_fields_have_defaults(self, graph: LinkGraph) -> None:
        """ConventionResult extended fields (source, status, priority) have SQL defaults."""
        results = graph.get_conventions(["src"])
        assert len(results) >= 1
        # Existing test data uses SQL defaults: source='user', status='active', priority=0
        for r in results:
            assert r.source == "user"
            assert r.status == "active"
            assert r.priority == 0
        graph.close()


class TestGetConventionsExtended:
    """Tests for get_conventions() with extended metadata (source, status, priority).

    These tests use a fresh database with conventions that exercise the new columns.
    """

    @pytest.fixture()
    def extended_graph(self, tmp_path: Path) -> LinkGraph:
        """Build a database with conventions using extended metadata columns."""
        db_path = tmp_path / "extended.db"
        conn = sqlite3.connect(str(db_path))
        ensure_schema(conn)

        # Insert convention artifacts
        conn.execute(
            "INSERT INTO artifacts (id, path, kind, title, status) "
            "VALUES (1, '.lexibrary/conventions/active-user.md', "
            "'convention', 'Active User Conv', 'active')"
        )
        conn.execute(
            "INSERT INTO artifacts (id, path, kind, title, status) "
            "VALUES (2, '.lexibrary/conventions/draft-agent.md', "
            "'convention', 'Draft Agent Conv', 'draft')"
        )
        conn.execute(
            "INSERT INTO artifacts (id, path, kind, title, status) "
            "VALUES (3, '.lexibrary/conventions/deprecated.md', "
            "'convention', 'Deprecated Conv', 'deprecated')"
        )
        conn.execute(
            "INSERT INTO artifacts (id, path, kind, title, status) "
            "VALUES (4, '.lexibrary/conventions/high-priority.md', "
            "'convention', 'High Priority', 'active')"
        )

        # Insert convention rows with extended metadata
        conv_insert = (
            "INSERT INTO conventions "
            "(artifact_id, directory_path, ordinal, body, source, status, priority) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)"
        )
        conn.execute(
            conv_insert,
            (1, ".", 0, "Active user convention body.", "user", "active", 0),
        )
        conn.execute(
            conv_insert,
            (2, ".", 1, "Draft agent convention body.", "agent", "draft", -1),
        )
        conn.execute(
            conv_insert,
            (3, ".", 2, "Deprecated convention body.", "user", "deprecated", 0),
        )
        conn.execute(conv_insert, (4, ".", 3, "High priority convention.", "config", "active", 10))

        # Seed schema version
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        conn.commit()
        conn.close()

        g = LinkGraph.open(db_path)
        assert g is not None
        return g

    def test_extended_metadata_returned(self, extended_graph: LinkGraph) -> None:
        """get_conventions() returns source, status, and priority in results."""
        results = extended_graph.get_conventions(["."], include_deprecated=True)
        assert len(results) == 4

        active_user = next(r for r in results if r.body == "Active user convention body.")
        assert active_user.source == "user"
        assert active_user.status == "active"
        assert active_user.priority == 0

        draft_agent = next(r for r in results if r.body == "Draft agent convention body.")
        assert draft_agent.source == "agent"
        assert draft_agent.status == "draft"
        assert draft_agent.priority == -1

        deprecated = next(r for r in results if r.body == "Deprecated convention body.")
        assert deprecated.source == "user"
        assert deprecated.status == "deprecated"
        assert deprecated.priority == 0
        extended_graph.close()

    def test_deprecated_excluded_by_default(self, extended_graph: LinkGraph) -> None:
        """get_conventions() excludes deprecated conventions by default."""
        results = extended_graph.get_conventions(["."])
        statuses = {r.status for r in results}
        assert "deprecated" not in statuses
        assert len(results) == 3
        extended_graph.close()

    def test_include_deprecated_flag(self, extended_graph: LinkGraph) -> None:
        """get_conventions(include_deprecated=True) includes deprecated conventions."""
        results = extended_graph.get_conventions(["."], include_deprecated=True)
        statuses = {r.status for r in results}
        assert "deprecated" in statuses
        assert len(results) == 4
        extended_graph.close()

    def test_priority_ordering(self, extended_graph: LinkGraph) -> None:
        """Higher priority conventions come before lower priority within same scope."""
        results = extended_graph.get_conventions(["."])
        # All are in "." scope; ordered by priority descending then ordinal
        # High priority (10) should come first, then active (0), then draft (-1)
        assert results[0].priority == 10
        assert results[0].body == "High priority convention."
        extended_graph.close()


# ---------------------------------------------------------------------------
# 7.10b -- get_convention_details() batch lookup
# ---------------------------------------------------------------------------


class TestGetConventionDetails:
    """get_convention_details() returns (directory_path, body) keyed by artifact_id."""

    def test_returns_correct_details(self, graph: LinkGraph) -> None:
        """Known convention artifact IDs return correct directory_path and body."""
        details = graph.get_convention_details([1])
        assert 1 in details
        dir_path, body = details[1]
        assert dir_path in ("src", "src/auth", "src/auth/middleware")
        assert body != ""
        graph.close()

    def test_empty_input_returns_empty_dict(self, graph: LinkGraph) -> None:
        """Empty artifact_ids list returns an empty dict."""
        details = graph.get_convention_details([])
        assert details == {}
        graph.close()

    def test_nonexistent_ids_returns_empty(self, graph: LinkGraph) -> None:
        """Artifact IDs with no convention row are omitted from the result."""
        details = graph.get_convention_details([9999, 8888])
        assert details == {}
        graph.close()

    def test_mixed_existing_and_missing(self, graph: LinkGraph) -> None:
        """Only IDs with convention rows appear in the result; missing ones are omitted."""
        details = graph.get_convention_details([1, 9999])
        assert 1 in details
        assert 9999 not in details
        graph.close()


# ---------------------------------------------------------------------------
# 7.11 -- build_summary() with and without log entries
# ---------------------------------------------------------------------------


class TestBuildSummary:
    """7.11 -- build_summary() returns aggregate stats for the most recent build."""

    def test_with_log_entries(self, graph: LinkGraph) -> None:
        """build_summary() aggregates by action for the most recent build."""
        results = graph.build_summary()
        assert len(results) >= 1
        assert all(isinstance(r, BuildSummaryEntry) for r in results)

        # Our test data has 'created' and 'unchanged' actions
        actions = {r.action for r in results}
        assert "created" in actions

        # Check that counts make sense
        created_entry = next(r for r in results if r.action == "created")
        assert created_entry.count >= 1
        assert created_entry.total_duration_ms is not None
        graph.close()

    def test_without_log_entries(self, tmp_path: Path) -> None:
        """build_summary() returns empty list when no build log entries exist."""
        db_path = tmp_path / "empty_log.db"
        conn = sqlite3.connect(str(db_path))
        ensure_schema(conn)
        conn.commit()
        conn.close()

        g = LinkGraph.open(db_path)
        assert g is not None
        results = g.build_summary()
        assert results == []
        g.close()


# ---------------------------------------------------------------------------
# 7.12 -- traverse() outbound and inbound directions
# ---------------------------------------------------------------------------


class TestTraverseDirections:
    """7.12 -- traverse() supports outbound and inbound traversal."""

    def test_outbound_traversal(self, graph: LinkGraph) -> None:
        """traverse() follows outbound links from start to targets."""
        results = graph.traverse("src/api/controller.py", max_depth=1, direction="outbound")
        assert len(results) >= 1
        assert all(isinstance(r, TraversalNode) for r in results)

        # controller imports auth/service.py and core/utils.py
        reachable_paths = {r.path for r in results}
        assert "src/auth/service.py" in reachable_paths
        assert "src/core/utils.py" in reachable_paths
        graph.close()

    def test_outbound_multi_hop(self, graph: LinkGraph) -> None:
        """traverse() follows multi-hop outbound links."""
        results = graph.traverse("src/api/controller.py", max_depth=2, direction="outbound")
        # At depth 1: auth/service.py, core/utils.py
        # At depth 2: core/utils.py (via auth/service.py -> utils.py)
        reachable_paths = {r.path for r in results}
        assert "src/auth/service.py" in reachable_paths
        assert "src/core/utils.py" in reachable_paths
        graph.close()

    def test_inbound_traversal(self, graph: LinkGraph) -> None:
        """traverse() follows inbound links (reverse dependency chain)."""
        results = graph.traverse("src/core/utils.py", max_depth=2, direction="inbound")
        assert len(results) >= 1

        # utils.py is imported by auth/service.py, controller.py, and cors middleware
        reachable_paths = {r.path for r in results}
        assert "src/auth/service.py" in reachable_paths
        graph.close()

    def test_start_path_not_found(self, graph: LinkGraph) -> None:
        """traverse() returns empty list when start path is not indexed."""
        results = graph.traverse("nonexistent/path.py")
        assert results == []
        graph.close()

    def test_no_outbound_links(self, graph: LinkGraph) -> None:
        """traverse() returns empty list when start artifact has no outbound links."""
        # core/utils.py has no outbound ast_import links in our test data
        results = graph.traverse(
            "src/core/utils.py",
            max_depth=3,
            link_types=["ast_import"],
            direction="outbound",
        )
        assert results == []
        graph.close()

    def test_link_types_filter(self, graph: LinkGraph) -> None:
        """traverse() restricts traversal to specified link types."""
        results = graph.traverse(
            "src/api/controller.py",
            max_depth=2,
            link_types=["ast_import"],
            direction="outbound",
        )
        # All results should be reachable via ast_import edges
        assert all(r.via_link_type == "ast_import" for r in results)
        graph.close()

    def test_traversal_node_fields(self, graph: LinkGraph) -> None:
        """traverse() returns TraversalNode with all expected fields."""
        results = graph.traverse("src/api/controller.py", max_depth=1, direction="outbound")
        assert len(results) >= 1
        node = results[0]
        assert node.artifact_id > 0
        assert node.path != ""
        assert node.kind in ("source", "design", "concept", "stack", "convention")
        assert node.depth == 1
        assert node.via_link_type is not None
        graph.close()


# ---------------------------------------------------------------------------
# 7.13 -- traverse() cycle detection (A->B->A does not loop)
# ---------------------------------------------------------------------------


class TestTraverseCycleDetection:
    """7.13 -- traverse() handles cycles without infinite recursion."""

    def test_simple_cycle(self, tmp_path: Path) -> None:
        """A -> B -> A cycle terminates without infinite recursion."""
        db_path = tmp_path / "cycle.db"
        conn = sqlite3.connect(str(db_path))
        ensure_schema(conn)

        # Create two artifacts that form a cycle
        conn.execute(
            "INSERT INTO artifacts (id, path, kind, title, status) "
            "VALUES (1, 'a.py', 'source', 'A', 'active')"
        )
        conn.execute(
            "INSERT INTO artifacts (id, path, kind, title, status) "
            "VALUES (2, 'b.py', 'source', 'B', 'active')"
        )
        # A -> B
        conn.execute(
            "INSERT INTO links (source_id, target_id, link_type) VALUES (1, 2, 'ast_import')"
        )
        # B -> A (cycle)
        conn.execute(
            "INSERT INTO links (source_id, target_id, link_type) VALUES (2, 1, 'ast_import')"
        )
        conn.commit()
        conn.close()

        g = LinkGraph.open(db_path)
        assert g is not None

        # This should terminate without infinite recursion
        results = g.traverse("a.py", max_depth=10, direction="outbound")

        # Should find B at depth 1, and A at depth 2 would be blocked by cycle detection
        # (or A might not appear since it's the start node)
        paths = {r.path for r in results}
        assert "b.py" in paths
        # Verify it terminates (the assertion itself proves no infinite loop)
        assert len(results) <= 10
        g.close()

    def test_triangle_cycle(self, tmp_path: Path) -> None:
        """A -> B -> C -> A cycle terminates correctly."""
        db_path = tmp_path / "triangle.db"
        conn = sqlite3.connect(str(db_path))
        ensure_schema(conn)

        conn.execute(
            "INSERT INTO artifacts (id, path, kind, title, status) "
            "VALUES (1, 'a.py', 'source', 'A', 'active')"
        )
        conn.execute(
            "INSERT INTO artifacts (id, path, kind, title, status) "
            "VALUES (2, 'b.py', 'source', 'B', 'active')"
        )
        conn.execute(
            "INSERT INTO artifacts (id, path, kind, title, status) "
            "VALUES (3, 'c.py', 'source', 'C', 'active')"
        )
        # A -> B -> C -> A
        conn.execute(
            "INSERT INTO links (source_id, target_id, link_type) VALUES (1, 2, 'ast_import')"
        )
        conn.execute(
            "INSERT INTO links (source_id, target_id, link_type) VALUES (2, 3, 'ast_import')"
        )
        conn.execute(
            "INSERT INTO links (source_id, target_id, link_type) VALUES (3, 1, 'ast_import')"
        )
        conn.commit()
        conn.close()

        g = LinkGraph.open(db_path)
        assert g is not None

        results = g.traverse("a.py", max_depth=10, direction="outbound")

        # Should find B (depth 1) and C (depth 2), but not revisit A
        paths = {r.path for r in results}
        assert "b.py" in paths
        assert "c.py" in paths
        # Should not have infinitely many results
        assert len(results) <= 3
        g.close()


# ---------------------------------------------------------------------------
# 7.14 -- traverse() max_depth clamping to 10
# ---------------------------------------------------------------------------


class TestTraverseMaxDepthClamping:
    """7.14 -- traverse() clamps max_depth to the hard cap of 10."""

    def test_max_depth_clamped(self, graph: LinkGraph) -> None:
        """Passing max_depth > 10 does not error and effectively caps at 10."""
        # This should not error, even though 50 > cap of 10
        results = graph.traverse("src/api/controller.py", max_depth=50, direction="outbound")
        # The traversal should still work correctly
        assert isinstance(results, list)
        graph.close()

    def test_clamping_consistent_with_cap(self, tmp_path: Path) -> None:
        """max_depth=50 produces the same results as max_depth=10."""
        # Create a long chain: 1 -> 2 -> 3 -> ... -> 15
        db_path = tmp_path / "chain.db"
        conn = sqlite3.connect(str(db_path))
        ensure_schema(conn)

        for i in range(1, 16):
            conn.execute(
                "INSERT INTO artifacts (id, path, kind, title, status) "
                f"VALUES ({i}, 'node_{i}.py', 'source', 'Node {i}', 'active')"
            )

        for i in range(1, 15):
            conn.execute(
                "INSERT INTO links (source_id, target_id, link_type) "
                f"VALUES ({i}, {i + 1}, 'ast_import')"
            )

        conn.commit()
        conn.close()

        g = LinkGraph.open(db_path)
        assert g is not None

        results_capped = g.traverse("node_1.py", max_depth=50, direction="outbound")
        g.close()

        g = LinkGraph.open(db_path)
        assert g is not None
        results_ten = g.traverse("node_1.py", max_depth=10, direction="outbound")
        g.close()

        # Both should produce the same results since 50 is clamped to 10
        assert len(results_capped) == len(results_ten)
        # With a 15-node chain starting at node_1, we can reach nodes 2-11 (depth 1-10)
        assert len(results_ten) == 10

    def test_max_depth_exactly_10(self, tmp_path: Path) -> None:
        """max_depth=10 reaches exactly 10 hops in a chain."""
        db_path = tmp_path / "chain10.db"
        conn = sqlite3.connect(str(db_path))
        ensure_schema(conn)

        for i in range(1, 13):
            conn.execute(
                "INSERT INTO artifacts (id, path, kind, title, status) "
                f"VALUES ({i}, 'n{i}.py', 'source', 'N{i}', 'active')"
            )

        for i in range(1, 12):
            conn.execute(
                "INSERT INTO links (source_id, target_id, link_type) "
                f"VALUES ({i}, {i + 1}, 'ast_import')"
            )

        conn.commit()
        conn.close()

        g = LinkGraph.open(db_path)
        assert g is not None
        results = g.traverse("n1.py", max_depth=10, direction="outbound")

        # Starting from n1, depth 1 = n2, depth 2 = n3, ..., depth 10 = n11
        # n12 exists but would be at depth 11, so should not be included
        paths = {r.path for r in results}
        assert "n11.py" in paths
        assert "n12.py" not in paths
        assert len(results) == 10
        g.close()


# ---------------------------------------------------------------------------
# 7.15 -- Read-only enforcement (write attempt raises OperationalError)
# ---------------------------------------------------------------------------


class TestReadOnlyEnforcement:
    """7.15 -- Write attempts on a LinkGraph connection raise OperationalError."""

    def test_insert_raises(self, graph: LinkGraph) -> None:
        """INSERT on the read-only connection raises OperationalError."""
        with pytest.raises(sqlite3.OperationalError):
            graph._conn.execute("INSERT INTO artifacts (path, kind) VALUES ('test.py', 'source')")
        graph.close()

    def test_update_raises(self, graph: LinkGraph) -> None:
        """UPDATE on the read-only connection raises OperationalError."""
        with pytest.raises(sqlite3.OperationalError):
            graph._conn.execute("UPDATE artifacts SET title = 'changed' WHERE id = 1")
        graph.close()

    def test_delete_raises(self, graph: LinkGraph) -> None:
        """DELETE on the read-only connection raises OperationalError."""
        with pytest.raises(sqlite3.OperationalError):
            graph._conn.execute("DELETE FROM artifacts WHERE id = 1")
        graph.close()

    def test_ddl_raises(self, graph: LinkGraph) -> None:
        """DDL operations on the read-only connection raise OperationalError."""
        with pytest.raises(sqlite3.OperationalError):
            graph._conn.execute("CREATE TABLE test_table (id INTEGER)")
        graph.close()


# ---------------------------------------------------------------------------
# Result dataclass tests
# ---------------------------------------------------------------------------


class TestResultDataclasses:
    """Verify structured result types behave correctly as dataclasses."""

    def test_artifact_result_equality(self) -> None:
        """Two ArtifactResult instances with identical fields are equal."""
        a = ArtifactResult(id=1, path="a.py", kind="source", title="A", status="active")
        b = ArtifactResult(id=1, path="a.py", kind="source", title="A", status="active")
        assert a == b

    def test_artifact_result_inequality(self) -> None:
        """Two ArtifactResult instances with different fields are not equal."""
        a = ArtifactResult(id=1, path="a.py", kind="source", title="A", status="active")
        b = ArtifactResult(id=2, path="b.py", kind="source", title="B", status="active")
        assert a != b

    def test_link_result_fields(self) -> None:
        """LinkResult fields are accessible by name."""
        r = LinkResult(source_id=1, source_path="a.py", link_type="ast_import", link_context="ctx")
        assert r.source_id == 1
        assert r.source_path == "a.py"
        assert r.link_type == "ast_import"
        assert r.link_context == "ctx"

    def test_traversal_node_fields(self) -> None:
        """TraversalNode fields are accessible by name."""
        n = TraversalNode(
            artifact_id=1, path="a.py", kind="source", depth=2, via_link_type="ast_import"
        )
        assert n.artifact_id == 1
        assert n.depth == 2

    def test_convention_result_fields(self) -> None:
        """ConventionResult fields are accessible by name."""
        c = ConventionResult(body="Use type hints.", directory_path="src", ordinal=0)
        assert c.body == "Use type hints."
        assert c.directory_path == "src"
        assert c.ordinal == 0

    def test_build_summary_entry_fields(self) -> None:
        """BuildSummaryEntry fields are accessible by name."""
        b = BuildSummaryEntry(action="created", count=5, total_duration_ms=100)
        assert b.action == "created"
        assert b.count == 5
        assert b.total_duration_ms == 100
