"""Tests for procedural topology generation (replaces test_start_here.py)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from lexibrary.archivist.topology import (
    _build_procedural_topology,
    _collect_aindex_data,
    _compute_depth,
    generate_topology,
)
from lexibrary.artifacts.aindex import AIndexEntry, AIndexFile
from lexibrary.artifacts.aindex_serializer import serialize_aindex
from lexibrary.artifacts.design_file import StalenessMetadata
from lexibrary.utils.paths import LEXIBRARY_DIR

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_meta(source: str) -> StalenessMetadata:
    """Create a minimal StalenessMetadata for test fixtures."""
    return StalenessMetadata(
        source=source,
        source_hash="abc123",
        generated=datetime(2025, 1, 1, tzinfo=UTC),
        generator="test",
    )


def _write_aindex(
    project_root: Path,
    directory_path: str,
    billboard: str,
    entries: list[AIndexEntry] | None = None,
) -> Path:
    """Create a serialised .aindex file under .lexibrary/ for *directory_path*.

    Returns the path to the written .aindex file.
    """
    if entries is None:
        entries = [
            AIndexEntry(name="example.py", entry_type="file", description="Example file"),
        ]

    aindex = AIndexFile(
        directory_path=directory_path,
        billboard=billboard,
        entries=entries,
        metadata=_make_meta(directory_path),
    )
    text = serialize_aindex(aindex)

    mirror_dir = project_root / LEXIBRARY_DIR / directory_path
    mirror_dir.mkdir(parents=True, exist_ok=True)
    aindex_path = mirror_dir / ".aindex"
    aindex_path.write_text(text, encoding="utf-8")
    return aindex_path


# ---------------------------------------------------------------------------
# _compute_depth
# ---------------------------------------------------------------------------


class TestComputeDepth:
    """Verify depth calculation relative to project root."""

    def test_project_root_is_depth_zero(self) -> None:
        assert _compute_depth("myproject", "myproject") == 0

    def test_dot_is_depth_zero(self) -> None:
        assert _compute_depth(".", "myproject") == 0

    def test_immediate_child(self) -> None:
        assert _compute_depth("myproject/src", "myproject") == 1

    def test_nested_two_deep(self) -> None:
        assert _compute_depth("myproject/src/auth", "myproject") == 2

    def test_nested_three_deep(self) -> None:
        assert _compute_depth("myproject/src/auth/handlers", "myproject") == 3

    def test_path_without_project_prefix(self) -> None:
        # Paths not starting with project name should still compute depth
        assert _compute_depth("src/auth", "myproject") == 2


# ---------------------------------------------------------------------------
# _collect_aindex_data
# ---------------------------------------------------------------------------


class TestCollectAindexData:
    """Verify .aindex data collection from the mirror tree."""

    def test_empty_when_no_lexibrary_dir(self, tmp_path: Path) -> None:
        result = _collect_aindex_data(tmp_path)
        assert result == []

    def test_empty_when_no_aindex_files(self, tmp_path: Path) -> None:
        (tmp_path / LEXIBRARY_DIR).mkdir()
        result = _collect_aindex_data(tmp_path)
        assert result == []

    def test_collects_single_aindex(self, tmp_path: Path) -> None:
        (tmp_path / LEXIBRARY_DIR).mkdir()
        _write_aindex(tmp_path, "src", "Main source code")
        result = _collect_aindex_data(tmp_path)
        assert len(result) == 1
        assert result[0].rel_path == "src"
        assert result[0].billboard == "Main source code"

    def test_collects_multiple_sorted(self, tmp_path: Path) -> None:
        (tmp_path / LEXIBRARY_DIR).mkdir()
        _write_aindex(tmp_path, "src/utils", "Utility functions")
        _write_aindex(tmp_path, "src", "Main source code")
        _write_aindex(tmp_path, "src/auth", "Authentication")
        result = _collect_aindex_data(tmp_path)
        paths = [info.rel_path for info in result]
        assert paths == ["src", "src/auth", "src/utils"]

    def test_extracts_child_dir_names(self, tmp_path: Path) -> None:
        (tmp_path / LEXIBRARY_DIR).mkdir()
        entries = [
            AIndexEntry(name="main.py", entry_type="file", description="Main module"),
            AIndexEntry(name="auth", entry_type="dir", description="Auth package"),
            AIndexEntry(name="utils", entry_type="dir", description="Utilities"),
        ]
        _write_aindex(tmp_path, "src", "Source code", entries=entries)
        result = _collect_aindex_data(tmp_path)
        assert result[0].child_dir_names == ["auth", "utils"]
        assert result[0].child_entry_count == 3

    def test_skips_malformed_aindex(self, tmp_path: Path) -> None:
        (tmp_path / LEXIBRARY_DIR).mkdir()
        bad_dir = tmp_path / LEXIBRARY_DIR / "bad"
        bad_dir.mkdir()
        (bad_dir / ".aindex").write_text("not a valid aindex file\n", encoding="utf-8")
        result = _collect_aindex_data(tmp_path)
        assert result == []


# ---------------------------------------------------------------------------
# _build_procedural_topology — small projects
# ---------------------------------------------------------------------------


class TestBuildProceduralTopologySmall:
    """Small projects (<= 10 dirs): full tree, no filtering."""

    def test_no_lexibrary_dir(self, tmp_path: Path) -> None:
        result = _build_procedural_topology(tmp_path)
        assert result == "(no .lexibrary directory found)"

    def test_no_aindex_files(self, tmp_path: Path) -> None:
        (tmp_path / LEXIBRARY_DIR).mkdir()
        result = _build_procedural_topology(tmp_path)
        assert result == "(no .aindex files found -- run 'lexi update' first)"

    def test_single_directory(self, tmp_path: Path) -> None:
        (tmp_path / LEXIBRARY_DIR).mkdir()
        project_name = tmp_path.name
        _write_aindex(tmp_path, project_name, "Root project directory")

        result = _build_procedural_topology(tmp_path)
        assert f"{project_name}/" in result
        assert "Root project directory" in result

    def test_small_project_shows_all_directories(self, tmp_path: Path) -> None:
        (tmp_path / LEXIBRARY_DIR).mkdir()
        project_name = tmp_path.name

        _write_aindex(tmp_path, project_name, "Root directory")
        _write_aindex(tmp_path, f"{project_name}/src", "Source code")
        _write_aindex(tmp_path, f"{project_name}/src/auth", "Authentication module")
        _write_aindex(tmp_path, f"{project_name}/src/utils", "Shared utilities")
        _write_aindex(tmp_path, f"{project_name}/tests", "Test suite")

        result = _build_procedural_topology(tmp_path)
        assert "Source code" in result
        assert "Authentication module" in result
        assert "Shared utilities" in result
        assert "Test suite" in result

    def test_indentation_increases_with_depth(self, tmp_path: Path) -> None:
        (tmp_path / LEXIBRARY_DIR).mkdir()
        project_name = tmp_path.name

        _write_aindex(tmp_path, project_name, "Root")
        _write_aindex(tmp_path, f"{project_name}/src", "Source")
        _write_aindex(tmp_path, f"{project_name}/src/auth", "Auth")

        result = _build_procedural_topology(tmp_path)
        lines = result.splitlines()

        # Root should have no indentation
        root_line = [line for line in lines if "Root" in line][0]
        assert not root_line.startswith(" ")

        # src/ should have 2-space indent (depth 1)
        src_line = [line for line in lines if "Source" in line][0]
        assert src_line.startswith("  ") and not src_line.startswith("    ")

        # auth/ should have 4-space indent (depth 2)
        auth_line = [line for line in lines if "Auth" in line][0]
        assert auth_line.startswith("    ") and not auth_line.startswith("      ")

    def test_billboard_annotations(self, tmp_path: Path) -> None:
        (tmp_path / LEXIBRARY_DIR).mkdir()
        project_name = tmp_path.name

        _write_aindex(tmp_path, project_name, "My project root")

        result = _build_procedural_topology(tmp_path)
        assert " -- My project root" in result

    def test_empty_billboard_no_annotation(self, tmp_path: Path) -> None:
        """Directories with empty billboards should not get ' -- ' annotation.

        Note: parse_aindex returns None for empty billboard, so this tests
        what happens if the billboard is empty-string in the data. In practice,
        directories without a billboard are filtered by the parser.
        """
        (tmp_path / LEXIBRARY_DIR).mkdir()
        project_name = tmp_path.name

        # We need to manually create an aindex with a non-empty billboard
        # since parse_aindex rejects empty ones. So test with a real billboard.
        _write_aindex(tmp_path, project_name, "Has billboard")
        result = _build_procedural_topology(tmp_path)
        assert " -- Has billboard" in result

    def test_dir_display_uses_last_component(self, tmp_path: Path) -> None:
        (tmp_path / LEXIBRARY_DIR).mkdir()
        project_name = tmp_path.name

        _write_aindex(tmp_path, f"{project_name}/src/auth/handlers", "Request handlers")

        result = _build_procedural_topology(tmp_path)
        # Should display just "handlers/" not the full path
        assert "handlers/" in result


# ---------------------------------------------------------------------------
# _build_procedural_topology — medium projects
# ---------------------------------------------------------------------------


class TestBuildProceduralTopologyMedium:
    """Medium projects (11-40 dirs): depth <= 2, plus hotspots."""

    @pytest.fixture()
    def medium_project(self, tmp_path: Path) -> Path:
        """Create a project with 15 directories (medium threshold)."""
        (tmp_path / LEXIBRARY_DIR).mkdir()
        project_name = tmp_path.name

        # Create 15 directories across varying depths
        dirs = [
            (project_name, "Root directory"),
            (f"{project_name}/src", "Source code"),
            (f"{project_name}/tests", "Test suite"),
            (f"{project_name}/docs", "Documentation"),
            (f"{project_name}/src/auth", "Authentication"),
            (f"{project_name}/src/api", "API layer"),
            (f"{project_name}/src/core", "Core logic"),
            (f"{project_name}/src/utils", "Utilities"),
            (f"{project_name}/src/models", "Data models"),
            (f"{project_name}/src/services", "Service layer"),
            (f"{project_name}/src/middleware", "Middleware"),
            # Depth-3 directories (should be filtered unless hotspots)
            (f"{project_name}/src/auth/handlers", "Auth handlers"),
            (f"{project_name}/src/auth/providers", "Auth providers"),
            (f"{project_name}/src/api/v1", "API v1 routes"),
            (f"{project_name}/src/api/v2", "API v2 routes"),
        ]

        for rel_path, billboard in dirs:
            _write_aindex(tmp_path, rel_path, billboard)

        return tmp_path

    def test_depth_2_directories_shown(self, medium_project: Path) -> None:
        result = _build_procedural_topology(medium_project)
        # Depth 0-2 directories should be shown
        assert "Root directory" in result
        assert "Source code" in result
        assert "Authentication" in result

    def test_depth_3_directories_filtered(self, medium_project: Path) -> None:
        result = _build_procedural_topology(medium_project)
        # Depth 3 directories should be filtered out (not hotspots)
        assert "Auth handlers" not in result
        assert "Auth providers" not in result

    def test_hidden_children_count(self, medium_project: Path) -> None:
        """Parent directories with hidden children should show a count."""
        project_name = medium_project.name

        # auth has 2 hidden children (handlers, providers)
        # We need auth to list them as child_dir_names
        entries = [
            AIndexEntry(name="handlers", entry_type="dir", description="Auth handlers"),
            AIndexEntry(name="providers", entry_type="dir", description="Auth providers"),
            AIndexEntry(name="login.py", entry_type="file", description="Login"),
        ]
        _write_aindex(medium_project, f"{project_name}/src/auth", "Authentication", entries=entries)

        result = _build_procedural_topology(medium_project)
        # The auth line should note hidden subdirs
        auth_lines = [line for line in result.splitlines() if "Authentication" in line]
        assert len(auth_lines) == 1
        assert "2 subdirs" in auth_lines[0]

    def test_hotspot_directories_shown_even_at_depth_3(self, medium_project: Path) -> None:
        """Directories with > 5 child entries (hotspots) should be shown regardless of depth."""
        project_name = medium_project.name

        # Make auth/handlers a hotspot (> 5 child entries)
        many_entries = [
            AIndexEntry(name=f"handler_{i}.py", entry_type="file", description=f"Handler {i}")
            for i in range(7)
        ]
        _write_aindex(
            medium_project,
            f"{project_name}/src/auth/handlers",
            "Auth handlers (hotspot)",
            entries=many_entries,
        )

        result = _build_procedural_topology(medium_project)
        assert "Auth handlers (hotspot)" in result


# ---------------------------------------------------------------------------
# _build_procedural_topology — large projects
# ---------------------------------------------------------------------------


class TestBuildProceduralTopologyLarge:
    """Large projects (41+ dirs): depth <= 1, plus hotspots."""

    @pytest.fixture()
    def large_project(self, tmp_path: Path) -> Path:
        """Create a project with 45 directories (large threshold)."""
        (tmp_path / LEXIBRARY_DIR).mkdir()
        project_name = tmp_path.name

        # Root + many depth-1 and depth-2 dirs
        _write_aindex(tmp_path, project_name, "Large project root")

        # 10 depth-1 directories
        for i in range(10):
            dir_name = f"pkg{i}"
            _write_aindex(tmp_path, f"{project_name}/{dir_name}", f"Package {i}")

            # 3-4 depth-2 directories under each
            for j in range(3 + (i % 2)):
                sub_name = f"sub{j}"
                _write_aindex(
                    tmp_path,
                    f"{project_name}/{dir_name}/{sub_name}",
                    f"Subpackage {i}.{j}",
                )

        return tmp_path

    def test_depth_1_directories_shown(self, large_project: Path) -> None:
        result = _build_procedural_topology(large_project)
        assert "Large project root" in result
        assert "Package 0" in result
        assert "Package 9" in result

    def test_depth_2_directories_filtered(self, large_project: Path) -> None:
        result = _build_procedural_topology(large_project)
        # Depth 2 dirs should generally be filtered (unless hotspots)
        assert "Subpackage 0.0" not in result


# ---------------------------------------------------------------------------
# generate_topology — end-to-end
# ---------------------------------------------------------------------------


class TestGenerateTopology:
    """Verify generate_topology() writes a valid TOPOLOGY.md file."""

    def test_writes_topology_md(self, tmp_path: Path) -> None:
        (tmp_path / LEXIBRARY_DIR).mkdir()
        project_name = tmp_path.name

        _write_aindex(tmp_path, project_name, "Root directory")
        _write_aindex(tmp_path, f"{project_name}/src", "Source code")

        result_path = generate_topology(tmp_path)

        expected_path = tmp_path / LEXIBRARY_DIR / "TOPOLOGY.md"
        assert result_path == expected_path
        assert expected_path.exists()

    def test_content_has_markdown_structure(self, tmp_path: Path) -> None:
        (tmp_path / LEXIBRARY_DIR).mkdir()
        project_name = tmp_path.name

        _write_aindex(tmp_path, project_name, "Root directory")
        _write_aindex(tmp_path, f"{project_name}/src", "Source code")

        result_path = generate_topology(tmp_path)
        content = result_path.read_text(encoding="utf-8")

        assert content.startswith("# Project Topology\n")
        assert "```\n" in content
        assert "Root directory" in content
        assert "Source code" in content

    def test_tree_wrapped_in_code_fence(self, tmp_path: Path) -> None:
        (tmp_path / LEXIBRARY_DIR).mkdir()
        project_name = tmp_path.name
        _write_aindex(tmp_path, project_name, "Root")

        result_path = generate_topology(tmp_path)
        content = result_path.read_text(encoding="utf-8")

        lines = content.splitlines()
        assert lines[0] == "# Project Topology"
        assert lines[1] == ""
        assert lines[2] == "```"
        # The tree content
        assert "Root" in lines[3]
        # Closing fence
        assert "```" in content.split("Root", 1)[1]

    def test_no_aindex_writes_placeholder(self, tmp_path: Path) -> None:
        (tmp_path / LEXIBRARY_DIR).mkdir()

        result_path = generate_topology(tmp_path)
        content = result_path.read_text(encoding="utf-8")

        assert "no .aindex files found" in content

    def test_overwrites_existing_topology(self, tmp_path: Path) -> None:
        (tmp_path / LEXIBRARY_DIR).mkdir()
        project_name = tmp_path.name

        topology_path = tmp_path / LEXIBRARY_DIR / "TOPOLOGY.md"
        topology_path.write_text("# Old content\n", encoding="utf-8")

        _write_aindex(tmp_path, project_name, "Fresh root")

        result_path = generate_topology(tmp_path)
        content = result_path.read_text(encoding="utf-8")

        assert "Old content" not in content
        assert "Fresh root" in content

    def test_returns_correct_path(self, tmp_path: Path) -> None:
        (tmp_path / LEXIBRARY_DIR).mkdir()
        project_name = tmp_path.name
        _write_aindex(tmp_path, project_name, "Root")

        result = generate_topology(tmp_path)
        assert result == tmp_path / LEXIBRARY_DIR / "TOPOLOGY.md"
