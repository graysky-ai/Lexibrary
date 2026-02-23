"""Tests for linkgraph-powered CLI features in Phase 10e.

Covers:
- 6.1 -- lexi lookup reverse link display (dependents, cross-refs, both, none)
- 6.2 -- lexi lookup graceful degradation (index missing, corrupt, schema mismatch)
- 6.3 -- unified_search() with link_graph parameter (tag search with/without index)
- 6.4 -- unified_search() FTS path (FTS with index, free-text fallback without index)
- 6.5 -- lexi search CLI command dispatching open_index() to unified_search()
- 6.6 -- Tag + scope combined filter with index-accelerated path
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import yaml
from typer.testing import CliRunner

from lexibrarian.cli import lexi_app
from lexibrarian.linkgraph.query import LinkGraph
from lexibrarian.linkgraph.schema import SCHEMA_VERSION, ensure_schema
from lexibrarian.search import unified_search

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_project(tmp_path: Path) -> Path:
    """Create a minimal initialized project."""
    (tmp_path / ".lexibrary").mkdir()
    (tmp_path / ".lexibrary" / "config.yaml").write_text("")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def hello():\n    pass\n")
    (tmp_path / "src" / "utils.py").write_text("x = 1\n")
    return tmp_path


def _create_design_file(tmp_path: Path, source_rel: str, source_content: str) -> Path:
    """Create a design file in .lexibrary mirror tree with correct metadata footer."""
    content_hash = hashlib.sha256(source_content.encode()).hexdigest()
    design_path = tmp_path / ".lexibrary" / f"{source_rel}.md"
    design_path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now().isoformat()
    design_content = f"""---
description: Design file for {source_rel}
updated_by: archivist
---

# {source_rel}

Test design file content.

## Interface Contract

```python
def hello(): ...
```

## Dependencies

- (none)

## Dependents

- (none)

<!-- lexibrarian:meta
source: {source_rel}
source_hash: {content_hash}
design_hash: placeholder
generated: {now}
generator: lexibrarian-v2
-->
"""
    design_path.write_text(design_content, encoding="utf-8")
    return design_path


def _create_linkgraph_db(tmp_path: Path) -> Path:
    """Create a valid link graph database at the standard project location."""
    db_path = tmp_path / ".lexibrary" / "index.db"
    conn = sqlite3.connect(str(db_path))
    ensure_schema(conn)
    conn.commit()
    conn.close()
    return db_path


def _populate_db_with_imports(db_path: Path, target_path: str) -> None:
    """Populate the database with ast_import links pointing to target_path.

    Sets up:
    - target artifact at target_path
    - two source artifacts that import the target via ast_import
    """
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO artifacts (id, path, kind, title, status) "
        "VALUES (1, ?, 'source', 'Target module', 'active')",
        (target_path,),
    )
    conn.execute(
        "INSERT INTO artifacts (id, path, kind, title, status) "
        "VALUES (2, 'src/api/controller.py', 'source', 'API controller', 'active')"
    )
    conn.execute(
        "INSERT INTO artifacts (id, path, kind, title, status) "
        "VALUES (3, 'src/cli/handler.py', 'source', 'CLI handler', 'active')"
    )
    # ast_import: controller -> target
    conn.execute(
        "INSERT INTO links (source_id, target_id, link_type, link_context) "
        "VALUES (2, 1, 'ast_import', 'from src.main import hello')"
    )
    # ast_import: handler -> target
    conn.execute(
        "INSERT INTO links (source_id, target_id, link_type, link_context) "
        "VALUES (3, 1, 'ast_import', 'from src.main import hello')"
    )
    conn.commit()
    conn.close()


def _populate_db_with_crossrefs(db_path: Path, target_path: str) -> None:
    """Populate the database with non-ast_import links pointing to target_path.

    Sets up:
    - target artifact at target_path
    - a concept that wikilinks to the target
    - a stack post that references the target
    """
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO artifacts (id, path, kind, title, status) "
        "VALUES (1, ?, 'source', 'Target module', 'active')",
        (target_path,),
    )
    conn.execute(
        "INSERT INTO artifacts (id, path, kind, title, status) "
        "VALUES (4, '.lexibrary/concepts/Authentication.md', 'concept', 'Authentication', 'active')"
    )
    conn.execute(
        "INSERT INTO artifacts (id, path, kind, title, status) "
        "VALUES (5, '.lexibrary/stack/ST-001.md', 'stack', 'Auth token bug', 'open')"
    )
    # wikilink: concept -> target
    conn.execute(
        "INSERT INTO links (source_id, target_id, link_type, link_context) "
        "VALUES (4, 1, 'wikilink', 'Authentication')"
    )
    # stack_file_ref: stack -> target
    conn.execute(
        "INSERT INTO links (source_id, target_id, link_type, link_context) "
        "VALUES (5, 1, 'stack_file_ref', NULL)"
    )
    conn.commit()
    conn.close()


def _populate_db_with_both(db_path: Path, target_path: str) -> None:
    """Populate the database with both ast_import and other link types."""
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO artifacts (id, path, kind, title, status) "
        "VALUES (1, ?, 'source', 'Target module', 'active')",
        (target_path,),
    )
    conn.execute(
        "INSERT INTO artifacts (id, path, kind, title, status) "
        "VALUES (2, 'src/api/controller.py', 'source', 'API controller', 'active')"
    )
    conn.execute(
        "INSERT INTO artifacts (id, path, kind, title, status) "
        "VALUES (3, '.lexibrary/concepts/Authentication.md', 'concept', 'Authentication', 'active')"
    )
    # ast_import: controller -> target
    conn.execute(
        "INSERT INTO links (source_id, target_id, link_type, link_context) "
        "VALUES (2, 1, 'ast_import', 'from src.main import hello')"
    )
    # wikilink: concept -> target
    conn.execute(
        "INSERT INTO links (source_id, target_id, link_type, link_context) "
        "VALUES (3, 1, 'wikilink', 'Authentication')"
    )
    conn.commit()
    conn.close()


def _invoke(project: Path, args: list[str]) -> object:
    """Run a CLI command in the given project directory."""
    old_cwd = os.getcwd()
    os.chdir(project)
    try:
        return runner.invoke(lexi_app, args)
    finally:
        os.chdir(old_cwd)


def _create_concept_file(
    tmp_path: Path,
    name: str,
    *,
    tags: list[str] | None = None,
    status: str = "active",
    summary: str = "",
) -> Path:
    """Create a concept markdown file in .lexibrary/concepts/."""
    import re as _re

    concepts_dir = tmp_path / ".lexibrary" / "concepts"
    concepts_dir.mkdir(parents=True, exist_ok=True)

    resolved_tags = tags or []
    fm_data: dict[str, object] = {
        "title": name,
        "aliases": [],
        "tags": resolved_tags,
        "status": status,
    }
    fm_str = yaml.dump(fm_data, default_flow_style=False, sort_keys=False).rstrip("\n")

    words = _re.split(r"[^a-zA-Z0-9]+", name)
    pascal = "".join(w.capitalize() for w in words if w)
    file_path = concepts_dir / f"{pascal}.md"

    body = f"---\n{fm_str}\n---\n\n{summary}\n\n## Details\n\n## Decision Log\n\n## Related\n"
    file_path.write_text(body, encoding="utf-8")
    return file_path


def _create_design_file_with_tags(
    tmp_path: Path, source_rel: str, description: str, tags: list[str]
) -> Path:
    """Create a design file with tags for search testing."""
    content_hash = hashlib.sha256(b"test").hexdigest()
    design_path = tmp_path / ".lexibrary" / f"{source_rel}.md"
    design_path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now().isoformat()
    tags_section = "\n".join(f"- {t}" for t in tags) if tags else "- (none)"
    design_content = f"""---
description: {description}
updated_by: archivist
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

<!-- lexibrarian:meta
source: {source_rel}
source_hash: {content_hash}
design_hash: placeholder
generated: {now}
generator: lexibrarian-v2
-->
"""
    design_path.write_text(design_content, encoding="utf-8")
    return design_path


def _create_stack_post(
    tmp_path: Path,
    post_id: str = "ST-001",
    title: str = "Bug in auth module",
    tags: list[str] | None = None,
    status: str = "open",
    problem: str = "Something is broken",
    refs_files: list[str] | None = None,
    refs_concepts: list[str] | None = None,
) -> Path:
    """Create a stack post file for testing."""
    import re as _re

    resolved_tags = tags or ["auth"]
    title_slug = _re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:50]
    filename = f"{post_id}-{title_slug}.md"
    stack_dir = tmp_path / ".lexibrary" / "stack"
    stack_dir.mkdir(parents=True, exist_ok=True)
    post_path = stack_dir / filename

    fm_data: dict[str, object] = {
        "id": post_id,
        "title": title,
        "tags": resolved_tags,
        "status": status,
        "created": "2026-01-15",
        "author": "tester",
        "bead": None,
        "votes": 0,
        "duplicate_of": None,
        "refs": {
            "concepts": refs_concepts or [],
            "files": refs_files or [],
            "designs": [],
        },
    }
    fm_str = yaml.dump(fm_data, default_flow_style=False, sort_keys=False).rstrip("\n")
    content = f"---\n{fm_str}\n---\n\n## Problem\n\n{problem}\n\n### Evidence\n\n\n"
    post_path.write_text(content, encoding="utf-8")
    return post_path


def _create_populated_index(
    db_path: Path,
    *,
    artifacts: list[tuple[int, str, str, str, str | None]] | None = None,
    tags: list[tuple[int, str]] | None = None,
    fts: list[tuple[int, str, str]] | None = None,
) -> None:
    """Populate an existing link graph database with artifacts, tags, and FTS data.

    Parameters
    ----------
    db_path:
        Path to an existing database file (already has schema).
    artifacts:
        List of (id, path, kind, title, status) tuples.
    tags:
        List of (artifact_id, tag) tuples.
    fts:
        List of (rowid, title, body) tuples for full-text search.
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
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# 6.1 -- lexi lookup reverse link display
# ---------------------------------------------------------------------------


class TestLookupReverseLinkDisplay:
    """6.1 -- lexi lookup displays dependents and cross-references from the link graph."""

    def test_file_with_dependents_only(self, tmp_path: Path) -> None:
        """Lookup shows Dependents section when file has ast_import inbound links."""
        project = _setup_project(tmp_path)
        source_content = "def hello():\n    pass\n"
        _create_design_file(project, "src/main.py", source_content)

        db_path = _create_linkgraph_db(project)
        _populate_db_with_imports(db_path, "src/main.py")

        result = _invoke(project, ["lookup", "src/main.py"])
        assert result.exit_code == 0
        output = result.output
        assert "Dependents (imports this file)" in output
        assert "src/api/controller.py" in output
        assert "src/cli/handler.py" in output
        # No cross-references section
        assert "Also Referenced By" not in output

    def test_file_with_cross_references_only(self, tmp_path: Path) -> None:
        """Lookup shows Also Referenced By section for non-import inbound links."""
        project = _setup_project(tmp_path)
        source_content = "def hello():\n    pass\n"
        _create_design_file(project, "src/main.py", source_content)

        db_path = _create_linkgraph_db(project)
        _populate_db_with_crossrefs(db_path, "src/main.py")

        result = _invoke(project, ["lookup", "src/main.py"])
        assert result.exit_code == 0
        output = result.output
        # No dependents section (no ast_import links)
        assert "Dependents (imports this file)" not in output
        # Cross-references section present
        assert "Also Referenced By" in output
        assert "Authentication" in output
        assert "concept wikilink" in output

    def test_file_with_both_dependents_and_crossrefs(self, tmp_path: Path) -> None:
        """Lookup shows both Dependents and Also Referenced By sections."""
        project = _setup_project(tmp_path)
        source_content = "def hello():\n    pass\n"
        _create_design_file(project, "src/main.py", source_content)

        db_path = _create_linkgraph_db(project)
        _populate_db_with_both(db_path, "src/main.py")

        result = _invoke(project, ["lookup", "src/main.py"])
        assert result.exit_code == 0
        output = result.output
        assert "Dependents (imports this file)" in output
        assert "src/api/controller.py" in output
        assert "Also Referenced By" in output
        assert "Authentication" in output

    def test_file_with_no_inbound_links(self, tmp_path: Path) -> None:
        """Lookup omits both sections when file has no inbound links."""
        project = _setup_project(tmp_path)
        source_content = "def hello():\n    pass\n"
        _create_design_file(project, "src/main.py", source_content)

        # Create database with the target artifact but no links
        db_path = _create_linkgraph_db(project)
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "INSERT INTO artifacts (id, path, kind, title, status) "
            "VALUES (1, 'src/main.py', 'source', 'Main module', 'active')"
        )
        conn.commit()
        conn.close()

        result = _invoke(project, ["lookup", "src/main.py"])
        assert result.exit_code == 0
        output = result.output
        assert "Dependents (imports this file)" not in output
        assert "Also Referenced By" not in output


# ---------------------------------------------------------------------------
# 6.2 -- lexi lookup graceful degradation
# ---------------------------------------------------------------------------


class TestLookupGracefulDegradation:
    """6.2 -- lexi lookup works correctly when index is missing, corrupt, or mismatched."""

    def test_index_missing(self, tmp_path: Path) -> None:
        """Lookup works normally when no index.db exists (graceful degradation)."""
        project = _setup_project(tmp_path)
        source_content = "def hello():\n    pass\n"
        _create_design_file(project, "src/main.py", source_content)

        # No index.db created -- open_index should return None
        result = _invoke(project, ["lookup", "src/main.py"])
        assert result.exit_code == 0
        output = result.output
        # Design file content should still be displayed
        assert "Interface Contract" in output
        # No reverse link sections
        assert "Dependents (imports this file)" not in output
        assert "Also Referenced By" not in output

    def test_index_corrupt(self, tmp_path: Path) -> None:
        """Lookup works normally when index.db is corrupt."""
        project = _setup_project(tmp_path)
        source_content = "def hello():\n    pass\n"
        _create_design_file(project, "src/main.py", source_content)

        # Write corrupt data to index.db
        corrupt_db = project / ".lexibrary" / "index.db"
        corrupt_db.write_text("this is not a sqlite database!")

        result = _invoke(project, ["lookup", "src/main.py"])
        assert result.exit_code == 0
        output = result.output
        assert "Interface Contract" in output
        assert "Dependents (imports this file)" not in output
        assert "Also Referenced By" not in output

    def test_schema_version_mismatch(self, tmp_path: Path) -> None:
        """Lookup works normally when index.db has wrong schema version."""
        project = _setup_project(tmp_path)
        source_content = "def hello():\n    pass\n"
        _create_design_file(project, "src/main.py", source_content)

        # Create database with wrong schema version
        db_path = _create_linkgraph_db(project)
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "UPDATE meta SET value = ? WHERE key = 'schema_version'",
            (str(SCHEMA_VERSION + 99),),
        )
        conn.commit()
        conn.close()

        result = _invoke(project, ["lookup", "src/main.py"])
        assert result.exit_code == 0
        output = result.output
        assert "Interface Contract" in output
        assert "Dependents (imports this file)" not in output
        assert "Also Referenced By" not in output


# ---------------------------------------------------------------------------
# 6.3 -- unified_search() with link_graph parameter (tag search)
# ---------------------------------------------------------------------------


class TestUnifiedSearchTagWithIndex:
    """6.3 -- unified_search() uses index-accelerated tag search when link_graph provided."""

    def test_tag_search_with_index(self, tmp_path: Path) -> None:
        """Tag search uses the link graph index when available."""
        project = _setup_project(tmp_path)
        db_path = _create_linkgraph_db(project)

        # Populate: a concept and a design file both tagged "security"
        _create_populated_index(
            db_path,
            artifacts=[
                (1, ".lexibrary/concepts/Auth.md", "concept", "Authentication", "active"),
                (2, "src/auth.py", "design", "Auth service design", None),
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
            # Should find the concept
            assert len(results.concepts) >= 1
            assert any(c.name == "Authentication" for c in results.concepts)
            # Should find the design file
            assert len(results.design_files) >= 1
            assert any(d.source_path == "src/auth.py" for d in results.design_files)
        finally:
            graph.close()

    def test_tag_search_fallback_without_index(self, tmp_path: Path) -> None:
        """Tag search falls back to file scanning when link_graph is None."""
        project = _setup_project(tmp_path)
        (project / "src" / "auth.py").write_text("def login(): pass\n")

        # Create artifact files (concepts, design files) with tags
        _create_concept_file(project, "Authentication", tags=["security"], summary="Auth concept")
        _create_design_file_with_tags(project, "src/auth.py", "Auth service", ["security"])

        # No link_graph provided -- should use file scanning
        results = unified_search(project, tag="security", link_graph=None)
        assert results.has_results()
        assert len(results.concepts) >= 1
        assert any(c.name == "Authentication" for c in results.concepts)
        assert len(results.design_files) >= 1
        assert any(d.source_path == "src/auth.py" for d in results.design_files)

    def test_tag_search_no_matching_tag_in_index(self, tmp_path: Path) -> None:
        """Tag search returns empty results when no artifacts match the tag."""
        project = _setup_project(tmp_path)
        db_path = _create_linkgraph_db(project)

        _create_populated_index(
            db_path,
            artifacts=[
                (1, ".lexibrary/concepts/Auth.md", "concept", "Authentication", "active"),
            ],
            tags=[
                (1, "security"),
            ],
        )

        graph = LinkGraph.open(db_path)
        assert graph is not None
        try:
            results = unified_search(project, tag="nonexistent-tag", link_graph=graph)
            assert not results.has_results()
        finally:
            graph.close()


# ---------------------------------------------------------------------------
# 6.4 -- unified_search() FTS path
# ---------------------------------------------------------------------------


class TestUnifiedSearchFTS:
    """6.4 -- unified_search() uses FTS when link_graph provided and query given."""

    def test_fts_search_with_index(self, tmp_path: Path) -> None:
        """FTS search uses the link graph FTS5 index when available."""
        project = _setup_project(tmp_path)
        db_path = _create_linkgraph_db(project)

        _create_populated_index(
            db_path,
            artifacts=[
                (1, "src/auth.py", "design", "Auth service design", None),
                (2, ".lexibrary/concepts/Auth.md", "concept", "Authentication", "active"),
                (3, "src/models.py", "design", "User data models", None),
            ],
            fts=[
                (1, "Auth service design", "Authentication service handles tokens"),
                (2, "Authentication", "Concept covering authentication patterns"),
                (3, "User data models", "Models for user entities and profiles"),
            ],
        )

        graph = LinkGraph.open(db_path)
        assert graph is not None
        try:
            results = unified_search(project, query="authentication", link_graph=graph)
            assert results.has_results()
            # Should find auth-related artifacts via FTS
            all_items = results.concepts + results.design_files + results.stack_posts
            assert len(all_items) >= 1
        finally:
            graph.close()

    def test_fts_includes_title_metadata(self, tmp_path: Path) -> None:
        """FTS results include title metadata from the artifacts table."""
        project = _setup_project(tmp_path)
        db_path = _create_linkgraph_db(project)

        _create_populated_index(
            db_path,
            artifacts=[
                (1, "src/auth.py", "design", "Auth Service Module", None),
            ],
            fts=[
                (1, "Auth Service Module", "Handles authentication and authorization"),
            ],
        )

        graph = LinkGraph.open(db_path)
        assert graph is not None
        try:
            results = unified_search(project, query="authentication", link_graph=graph)
            assert results.has_results()
            assert len(results.design_files) >= 1
            # Title from artifacts table should be available
            assert results.design_files[0].description == "Auth Service Module"
        finally:
            graph.close()

    def test_fts_fallback_without_index(self, tmp_path: Path) -> None:
        """Free-text search falls back to file scanning when link_graph is None."""
        project = _setup_project(tmp_path)
        (project / "src" / "auth.py").write_text("def login(): pass\n")

        # Create searchable artifacts
        _create_concept_file(project, "Authentication", tags=["security"], summary="Auth logic")
        _create_design_file_with_tags(
            project, "src/auth.py", "Authentication flow handler", ["auth"]
        )

        # No link_graph -- uses file scanning fallback
        results = unified_search(project, query="auth", link_graph=None)
        assert results.has_results()
        # Should find items via file-scanning path
        total_items = len(results.concepts) + len(results.design_files) + len(results.stack_posts)
        assert total_items >= 1

    def test_fts_no_matching_results(self, tmp_path: Path) -> None:
        """FTS search returns empty results when nothing matches."""
        project = _setup_project(tmp_path)
        db_path = _create_linkgraph_db(project)

        _create_populated_index(
            db_path,
            artifacts=[
                (1, "src/auth.py", "design", "Auth service design", None),
            ],
            fts=[
                (1, "Auth service design", "Authentication service handles tokens"),
            ],
        )

        graph = LinkGraph.open(db_path)
        assert graph is not None
        try:
            results = unified_search(project, query="xyznonexistent12345", link_graph=graph)
            assert not results.has_results()
        finally:
            graph.close()


# ---------------------------------------------------------------------------
# 6.5 -- lexi search CLI command dispatching open_index() to unified_search()
# ---------------------------------------------------------------------------


class TestSearchCLIWithOpenIndex:
    """6.5 -- lexi search command calls open_index() and passes result to unified_search()."""

    def test_search_uses_index_when_available(self, tmp_path: Path) -> None:
        """lexi search uses the link graph index when index.db exists."""
        project = _setup_project(tmp_path)
        (project / "src" / "auth.py").write_text("def login(): pass\n")

        db_path = _create_linkgraph_db(project)
        _create_populated_index(
            db_path,
            artifacts=[
                (1, ".lexibrary/concepts/Auth.md", "concept", "Authentication", "active"),
            ],
            tags=[
                (1, "security"),
            ],
        )

        # Also create the concept file so fallback path can work too
        _create_concept_file(project, "Authentication", tags=["security"], summary="Auth concept")

        result = _invoke(project, ["search", "--tag", "security"])
        assert result.exit_code == 0
        output = result.output
        assert "Authentication" in output

    def test_search_degrades_gracefully_without_index(self, tmp_path: Path) -> None:
        """lexi search works via fallback when no index.db exists."""
        project = _setup_project(tmp_path)
        (project / "src" / "auth.py").write_text("def login(): pass\n")

        _create_concept_file(project, "Authentication", tags=["security"], summary="Auth concept")
        _create_design_file_with_tags(project, "src/auth.py", "Auth handler", ["security"])

        # No index.db -- should fall back to file scanning
        result = _invoke(project, ["search", "--tag", "security"])
        assert result.exit_code == 0
        output = result.output
        assert "Authentication" in output
        assert "src/auth.py" in output

    def test_search_fts_via_cli(self, tmp_path: Path) -> None:
        """lexi search dispatches FTS when index.db exists and query is given."""
        project = _setup_project(tmp_path)
        db_path = _create_linkgraph_db(project)

        _create_populated_index(
            db_path,
            artifacts=[
                (1, ".lexibrary/concepts/Auth.md", "concept", "Authentication", "active"),
            ],
            fts=[
                (1, "Authentication", "Concept covering authentication patterns and tokens"),
            ],
        )

        result = _invoke(project, ["search", "tokens"])
        assert result.exit_code == 0
        output = result.output
        assert "Authentication" in output

    def test_search_closes_link_graph(self, tmp_path: Path) -> None:
        """lexi search properly closes the link graph after use."""
        project = _setup_project(tmp_path)
        db_path = _create_linkgraph_db(project)

        _create_populated_index(
            db_path,
            artifacts=[
                (1, ".lexibrary/concepts/Auth.md", "concept", "Auth", "active"),
            ],
            tags=[(1, "test")],
        )

        # Patch LinkGraph.close to verify it gets called
        original_close = LinkGraph.close
        close_called = []

        def tracking_close(self: LinkGraph) -> None:
            close_called.append(True)
            original_close(self)

        with patch.object(LinkGraph, "close", tracking_close):
            result = _invoke(project, ["search", "--tag", "test"])

        assert result.exit_code == 0
        assert len(close_called) >= 1, "LinkGraph.close() was not called"

    def test_search_no_results_with_index(self, tmp_path: Path) -> None:
        """lexi search shows 'No results found' when FTS returns nothing."""
        project = _setup_project(tmp_path)
        db_path = _create_linkgraph_db(project)

        _create_populated_index(
            db_path,
            artifacts=[
                (1, "src/auth.py", "design", "Auth service", None),
            ],
            fts=[
                (1, "Auth service", "Authentication tokens"),
            ],
        )

        result = _invoke(project, ["search", "xyznonexistent12345"])
        assert result.exit_code == 0
        assert "No results found" in result.output


# ---------------------------------------------------------------------------
# 6.6 -- Tag + scope combined filter with index-accelerated path
# ---------------------------------------------------------------------------


class TestTagScopeCombinedFilter:
    """6.6 -- Tag + scope combined filter works with index-accelerated path."""

    def test_tag_and_scope_filters_design_files(self, tmp_path: Path) -> None:
        """Tag + scope filter narrows results to matching design files only."""
        project = _setup_project(tmp_path)
        db_path = _create_linkgraph_db(project)

        # Two design files with same tag, different paths
        _create_populated_index(
            db_path,
            artifacts=[
                (1, "src/auth/service.py", "design", "Auth service", None),
                (2, "src/models/user.py", "design", "User model", None),
            ],
            tags=[
                (1, "security"),
                (2, "security"),
            ],
        )

        graph = LinkGraph.open(db_path)
        assert graph is not None
        try:
            results = unified_search(project, tag="security", scope="src/auth", link_graph=graph)
            assert results.has_results()
            # Only the auth service should match (scope filters out models)
            assert len(results.design_files) == 1
            assert results.design_files[0].source_path == "src/auth/service.py"
        finally:
            graph.close()

    def test_tag_and_scope_excludes_concepts(self, tmp_path: Path) -> None:
        """Tag + scope filter excludes concepts (concepts are not file-scoped)."""
        project = _setup_project(tmp_path)
        db_path = _create_linkgraph_db(project)

        _create_populated_index(
            db_path,
            artifacts=[
                (1, ".lexibrary/concepts/Auth.md", "concept", "Authentication", "active"),
                (2, "src/auth/service.py", "design", "Auth service", None),
            ],
            tags=[
                (1, "security"),
                (2, "security"),
            ],
        )

        graph = LinkGraph.open(db_path)
        assert graph is not None
        try:
            results = unified_search(project, tag="security", scope="src/", link_graph=graph)
            # Concepts are excluded when scope is active
            assert len(results.concepts) == 0
            # Design files within scope are included
            assert len(results.design_files) >= 1
        finally:
            graph.close()

    def test_tag_and_scope_includes_stack_posts(self, tmp_path: Path) -> None:
        """Tag + scope filter includes stack posts whose path matches the scope."""
        project = _setup_project(tmp_path)
        db_path = _create_linkgraph_db(project)

        _create_populated_index(
            db_path,
            artifacts=[
                (1, "src/auth/service.py", "design", "Auth service", None),
                (2, ".lexibrary/stack/ST-001.md", "stack", "Auth token bug", "open"),
                (3, ".lexibrary/stack/ST-002.md", "stack", "Model bug", "open"),
            ],
            tags=[
                (1, "security"),
                (2, "security"),
                (3, "security"),
            ],
        )

        graph = LinkGraph.open(db_path)
        assert graph is not None
        try:
            results = unified_search(
                project, tag="security", scope=".lexibrary/stack/ST-001", link_graph=graph
            )
            # Only ST-001 should match the scope
            assert len(results.stack_posts) == 1
            assert results.stack_posts[0].post_id == ".lexibrary/stack/ST-001.md"
        finally:
            graph.close()

    def test_tag_and_scope_no_results(self, tmp_path: Path) -> None:
        """Tag + scope filter returns empty when no artifacts match both criteria."""
        project = _setup_project(tmp_path)
        db_path = _create_linkgraph_db(project)

        _create_populated_index(
            db_path,
            artifacts=[
                (1, "src/auth/service.py", "design", "Auth service", None),
            ],
            tags=[
                (1, "security"),
            ],
        )

        graph = LinkGraph.open(db_path)
        assert graph is not None
        try:
            results = unified_search(project, tag="security", scope="src/models/", link_graph=graph)
            # Auth service has "security" tag but its path doesn't start with "src/models/"
            assert not results.has_results()
        finally:
            graph.close()

    def test_tag_only_without_scope_includes_concepts(self, tmp_path: Path) -> None:
        """Tag search without scope includes concepts from the index."""
        project = _setup_project(tmp_path)
        db_path = _create_linkgraph_db(project)

        _create_populated_index(
            db_path,
            artifacts=[
                (1, ".lexibrary/concepts/Auth.md", "concept", "Authentication", "active"),
                (2, "src/auth/service.py", "design", "Auth service", None),
            ],
            tags=[
                (1, "security"),
                (2, "security"),
            ],
        )

        graph = LinkGraph.open(db_path)
        assert graph is not None
        try:
            results = unified_search(project, tag="security", scope=None, link_graph=graph)
            assert results.has_results()
            # Concepts should be included when there is no scope filter
            assert len(results.concepts) >= 1
            assert any(c.name == "Authentication" for c in results.concepts)
        finally:
            graph.close()

    def test_scope_filter_via_cli(self, tmp_path: Path) -> None:
        """Tag + scope combined filter works via the CLI."""
        project = _setup_project(tmp_path)
        (project / "src" / "auth.py").write_text("def login(): pass\n")
        (project / "src" / "models.py").write_text("class User: pass\n")

        db_path = _create_linkgraph_db(project)
        _create_populated_index(
            db_path,
            artifacts=[
                (1, "src/auth.py", "design", "Auth service", None),
                (2, "src/models.py", "design", "User model", None),
            ],
            tags=[
                (1, "core"),
                (2, "core"),
            ],
        )

        result = _invoke(project, ["search", "--tag", "core", "--scope", "src/auth"])
        assert result.exit_code == 0
        output = result.output
        # Should find auth service (matches both tag and scope)
        assert "src/auth.py" in output
        # Should NOT find models (doesn't match scope)
        assert "src/models.py" not in output
