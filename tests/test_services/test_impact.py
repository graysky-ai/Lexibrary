"""Unit tests for lexibrary.services.impact and impact_render."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from lexibrary.services.impact import (
    DependentNode,
    ImpactResult,
    LinkGraphMissingError,
    analyse_impact,
)
from lexibrary.services.impact_render import render_quiet, render_tree

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_project(tmp_path: Path) -> Path:
    """Create a minimal project with .lexibrary directory and source files."""
    (tmp_path / ".lexibrary").mkdir()
    (tmp_path / ".lexibrary" / "config.yaml").write_text("")
    (tmp_path / "src" / "core").mkdir(parents=True)
    (tmp_path / "src" / "api").mkdir(parents=True)
    (tmp_path / "src" / "cli").mkdir(parents=True)
    (tmp_path / "src" / "app").mkdir(parents=True)
    (tmp_path / "src" / "core" / "utils.py").write_text("def helper(): pass\n")
    (tmp_path / "src" / "api" / "controller.py").write_text("from src.core.utils import helper\n")
    (tmp_path / "src" / "cli" / "handler.py").write_text(
        "from src.core.utils import format_output\n"
    )
    (tmp_path / "src" / "app" / "main.py").write_text("from src.api.controller import Controller\n")
    return tmp_path


def _create_linkgraph(project: Path) -> Path:
    """Create a valid link graph database at the standard project location."""
    from lexibrary.linkgraph.schema import ensure_schema

    db_path = project / ".lexibrary" / "index.db"
    conn = sqlite3.connect(str(db_path))
    ensure_schema(conn)
    conn.commit()
    conn.close()
    return db_path


def _populate_db(
    db_path: Path,
    *,
    add_depth2: bool = False,
    add_stack_post: bool = False,
) -> None:
    """Populate the link graph with import relationships for impact testing."""
    conn = sqlite3.connect(str(db_path))

    # Target artifact
    conn.execute(
        "INSERT INTO artifacts (id, path, kind, title, status) "
        "VALUES (1, 'src/core/utils.py', 'source', 'Core utilities', 'active')"
    )
    # Depth 1 dependents
    conn.execute(
        "INSERT INTO artifacts (id, path, kind, title, status) "
        "VALUES (2, 'src/api/controller.py', 'source', 'API controller', 'active')"
    )
    conn.execute(
        "INSERT INTO artifacts (id, path, kind, title, status) "
        "VALUES (3, 'src/cli/handler.py', 'source', 'CLI handler', 'active')"
    )
    # ast_import links: controller -> utils, handler -> utils
    conn.execute(
        "INSERT INTO links (source_id, target_id, link_type, link_context) "
        "VALUES (2, 1, 'ast_import', 'from src.core.utils import helper')"
    )
    conn.execute(
        "INSERT INTO links (source_id, target_id, link_type, link_context) "
        "VALUES (3, 1, 'ast_import', 'from src.core.utils import format_output')"
    )

    if add_depth2:
        conn.execute(
            "INSERT INTO artifacts (id, path, kind, title, status) "
            "VALUES (4, 'src/app/main.py', 'source', 'App entry point', 'active')"
        )
        conn.execute(
            "INSERT INTO links (source_id, target_id, link_type, link_context) "
            "VALUES (4, 2, 'ast_import', 'from src.api.controller import Controller')"
        )

    if add_stack_post:
        conn.execute(
            "INSERT INTO artifacts (id, path, kind, title, status) "
            "VALUES (10, '.lexibrary/stack/ST-001-auth-bug.md', 'stack', "
            "'Auth token bug in controller', 'open')"
        )
        conn.execute(
            "INSERT INTO links (source_id, target_id, link_type, link_context) "
            "VALUES (10, 2, 'stack_file_ref', NULL)"
        )

    conn.commit()
    conn.close()


def _load_config(project: Path):
    """Load config for the test project."""
    from lexibrary.config.loader import load_config

    return load_config(project)


# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------


class TestDataclasses:
    """Dataclasses are importable and hold correct data."""

    def test_impact_result_defaults(self) -> None:
        """ImpactResult has empty dependents by default."""
        result = ImpactResult(target_path="src/core/utils.py")
        assert result.target_path == "src/core/utils.py"
        assert result.dependents == []

    def test_dependent_node_defaults(self) -> None:
        """DependentNode has None description and empty stack posts by default."""
        node = DependentNode(path="src/api/controller.py", depth=1)
        assert node.path == "src/api/controller.py"
        assert node.depth == 1
        assert node.description is None
        assert node.open_stack_posts == []

    def test_dependent_node_with_description(self) -> None:
        """DependentNode stores description and stack posts."""
        node = DependentNode(
            path="src/api/controller.py",
            depth=1,
            description="HTTP API request handler",
            open_stack_posts=[".lexibrary/stack/ST-001-auth-bug.md (Auth token bug)"],
        )
        assert node.description == "HTTP API request handler"
        assert len(node.open_stack_posts) == 1

    def test_importable_without_cli(self) -> None:
        """ImpactResult and DependentNode import without CLI dependencies."""
        # This test succeeds by reaching this point -- the imports at the
        # top of the file already prove it.  We verify the types are the
        # expected dataclass types.
        import dataclasses

        assert dataclasses.is_dataclass(ImpactResult)
        assert dataclasses.is_dataclass(DependentNode)


# ---------------------------------------------------------------------------
# Service function tests
# ---------------------------------------------------------------------------


class TestAnalyseImpact:
    """Tests for the analyse_impact() service function."""

    def test_returns_dependents(self, tmp_path: Path) -> None:
        """analyse_impact returns dependents that import the target file."""
        project = _setup_project(tmp_path)
        db_path = _create_linkgraph(project)
        _populate_db(db_path)
        config = _load_config(project)

        result = analyse_impact(project / "src" / "core" / "utils.py", project, config)
        assert result.target_path == "src/core/utils.py"
        paths = {dep.path for dep in result.dependents}
        assert "src/api/controller.py" in paths
        assert "src/cli/handler.py" in paths

    def test_returns_depth2(self, tmp_path: Path) -> None:
        """analyse_impact at depth 2 follows transitive dependents."""
        project = _setup_project(tmp_path)
        db_path = _create_linkgraph(project)
        _populate_db(db_path, add_depth2=True)
        config = _load_config(project)

        result = analyse_impact(project / "src" / "core" / "utils.py", project, config, depth=2)
        paths = {dep.path for dep in result.dependents}
        assert "src/api/controller.py" in paths
        assert "src/cli/handler.py" in paths
        assert "src/app/main.py" in paths

    def test_no_dependents(self, tmp_path: Path) -> None:
        """analyse_impact returns empty list when no dependents exist."""
        project = _setup_project(tmp_path)
        db_path = _create_linkgraph(project)
        _populate_db(db_path)
        config = _load_config(project)

        # handler.py has no inbound ast_imports
        result = analyse_impact(project / "src" / "cli" / "handler.py", project, config)
        assert result.target_path == "src/cli/handler.py"
        assert result.dependents == []

    def test_no_link_graph_raises(self, tmp_path: Path) -> None:
        """analyse_impact raises LinkGraphMissingError when no index.db exists."""
        project = _setup_project(tmp_path)
        config = _load_config(project)

        with pytest.raises(LinkGraphMissingError):
            analyse_impact(project / "src" / "core" / "utils.py", project, config)

    def test_depth_clamping_high(self, tmp_path: Path) -> None:
        """Depth above 3 is clamped to 3."""
        project = _setup_project(tmp_path)
        db_path = _create_linkgraph(project)
        _populate_db(db_path, add_depth2=True)
        config = _load_config(project)

        result = analyse_impact(project / "src" / "core" / "utils.py", project, config, depth=10)
        paths = {dep.path for dep in result.dependents}
        assert "src/app/main.py" in paths

    def test_depth_clamping_low(self, tmp_path: Path) -> None:
        """Depth below 1 is clamped to 1."""
        project = _setup_project(tmp_path)
        db_path = _create_linkgraph(project)
        _populate_db(db_path, add_depth2=True)
        config = _load_config(project)

        result = analyse_impact(project / "src" / "core" / "utils.py", project, config, depth=0)
        paths = {dep.path for dep in result.dependents}
        assert "src/api/controller.py" in paths
        # depth 2 should NOT appear when clamped to depth=1
        assert "src/app/main.py" not in paths

    def test_stack_posts_captured(self, tmp_path: Path) -> None:
        """analyse_impact captures open stack posts for dependents."""
        project = _setup_project(tmp_path)
        db_path = _create_linkgraph(project)
        _populate_db(db_path, add_stack_post=True)
        config = _load_config(project)

        result = analyse_impact(project / "src" / "core" / "utils.py", project, config)
        controller_deps = [d for d in result.dependents if d.path == "src/api/controller.py"]
        assert len(controller_deps) == 1
        assert len(controller_deps[0].open_stack_posts) == 1
        assert "Auth token bug" in controller_deps[0].open_stack_posts[0]

    def test_design_description_captured(self, tmp_path: Path) -> None:
        """analyse_impact includes design-file descriptions."""
        project = _setup_project(tmp_path)
        db_path = _create_linkgraph(project)
        _populate_db(db_path)
        config = _load_config(project)

        # Create a design file for controller.py
        design_path = project / ".lexibrary" / "designs" / "src" / "api" / "controller.py.md"
        design_path.parent.mkdir(parents=True, exist_ok=True)
        design_path.write_text(
            "---\ndescription: HTTP API request handler\nid: DS-001\nupdated_by: archivist\n"
            "---\n\n# controller\n",
            encoding="utf-8",
        )

        result = analyse_impact(project / "src" / "core" / "utils.py", project, config)
        controller_deps = [d for d in result.dependents if d.path == "src/api/controller.py"]
        assert len(controller_deps) == 1
        assert controller_deps[0].description == "HTTP API request handler"

    def test_missing_description_is_none(self, tmp_path: Path) -> None:
        """DependentNode has description=None when no design file exists."""
        project = _setup_project(tmp_path)
        db_path = _create_linkgraph(project)
        _populate_db(db_path)
        config = _load_config(project)

        result = analyse_impact(project / "src" / "core" / "utils.py", project, config)
        for dep in result.dependents:
            assert dep.description is None


# ---------------------------------------------------------------------------
# Render tests
# ---------------------------------------------------------------------------


class TestRenderTree:
    """Tests for the tree renderer."""

    def test_tree_output_format(self) -> None:
        """Tree renderer includes header, paths, and indent structure."""
        result = ImpactResult(
            target_path="src/core/utils.py",
            dependents=[
                DependentNode(path="src/api/controller.py", depth=1),
                DependentNode(path="src/cli/handler.py", depth=1),
            ],
        )
        output = render_tree(result)
        assert "## Dependents of src/core/utils.py" in output
        assert "|- src/api/controller.py" in output
        assert "|- src/cli/handler.py" in output

    def test_tree_with_descriptions(self) -> None:
        """Tree renderer shows descriptions inline."""
        result = ImpactResult(
            target_path="src/core/utils.py",
            dependents=[
                DependentNode(
                    path="src/api/controller.py",
                    depth=1,
                    description="HTTP API request handler",
                ),
            ],
        )
        output = render_tree(result)
        assert "-- HTTP API request handler" in output

    def test_tree_with_stack_warnings(self) -> None:
        """Tree renderer shows open stack post warnings."""
        result = ImpactResult(
            target_path="src/core/utils.py",
            dependents=[
                DependentNode(
                    path="src/api/controller.py",
                    depth=1,
                    open_stack_posts=[".lexibrary/stack/ST-001-auth-bug.md (Auth token bug)"],
                ),
            ],
        )
        output = render_tree(result)
        assert "warning: open stack post" in output
        assert "Auth token bug" in output

    def test_tree_depth2_indentation(self) -> None:
        """Depth-2 nodes use deeper indent and |-- prefix."""
        result = ImpactResult(
            target_path="src/core/utils.py",
            dependents=[
                DependentNode(path="src/api/controller.py", depth=1),
                DependentNode(path="src/app/main.py", depth=2),
            ],
        )
        output = render_tree(result)
        assert "|- src/api/controller.py" in output
        assert "  |-- src/app/main.py" in output


class TestRenderQuiet:
    """Tests for the quiet renderer."""

    def test_quiet_paths_only(self) -> None:
        """Quiet renderer returns paths only, one per line."""
        result = ImpactResult(
            target_path="src/core/utils.py",
            dependents=[
                DependentNode(path="src/api/controller.py", depth=1),
                DependentNode(path="src/cli/handler.py", depth=1),
            ],
        )
        output = render_quiet(result)
        lines = output.strip().splitlines()
        assert len(lines) == 2
        assert "src/api/controller.py" in lines
        assert "src/cli/handler.py" in lines

    def test_quiet_deduplication(self) -> None:
        """Quiet renderer deduplicates paths."""
        result = ImpactResult(
            target_path="src/core/utils.py",
            dependents=[
                DependentNode(path="src/api/controller.py", depth=1),
                DependentNode(path="src/api/controller.py", depth=2),
            ],
        )
        output = render_quiet(result)
        lines = output.strip().splitlines()
        assert len(lines) == 1
        assert lines[0] == "src/api/controller.py"

    def test_quiet_empty(self) -> None:
        """Quiet renderer returns empty string for no dependents."""
        result = ImpactResult(target_path="src/core/utils.py")
        output = render_quiet(result)
        assert output == ""

    def test_quiet_no_decorations(self) -> None:
        """Quiet output contains no tree decorations."""
        result = ImpactResult(
            target_path="src/core/utils.py",
            dependents=[
                DependentNode(path="src/api/controller.py", depth=1),
            ],
        )
        output = render_quiet(result)
        assert "|-" not in output
        assert "Dependents" not in output
        assert "--" not in output
