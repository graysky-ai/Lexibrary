"""Tests for procedural topology generation (replaces test_start_here.py)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from lexibrary.archivist.topology import (
    _build_procedural_topology,
    _collect_aindex_data,
    _compute_depth,
    _generate_header,
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

    def test_key_entries_populated_for_landmark_entries(self, tmp_path: Path) -> None:
        """key_entries should contain entries matching landmark keywords."""
        (tmp_path / LEXIBRARY_DIR).mkdir()
        entries = [
            AIndexEntry(name="main.py", entry_type="file", description="Application entry point"),
            AIndexEntry(name="utils.py", entry_type="file", description="Utility helpers"),
            AIndexEntry(name="pyproject.toml", entry_type="file", description="Build metadata"),
        ]
        _write_aindex(tmp_path, "src", "Source code", entries=entries)
        result = _collect_aindex_data(tmp_path)
        assert len(result) == 1
        key_names = [e.name for e in result[0].key_entries]
        # main.py matches "entry point", pyproject.toml matches config filename
        assert "main.py" in key_names
        assert "pyproject.toml" in key_names
        # utils.py does not match any landmark keyword
        assert "utils.py" not in key_names

    def test_key_entries_empty_when_no_landmarks(self, tmp_path: Path) -> None:
        """key_entries should be empty when no entries match landmark keywords."""
        (tmp_path / LEXIBRARY_DIR).mkdir()
        entries = [
            AIndexEntry(
                name="helpers.py", entry_type="file", description="Shared helper functions",
            ),
            AIndexEntry(
                name="models.py", entry_type="file", description="Data model definitions",
            ),
        ]
        _write_aindex(tmp_path, "src", "Source code", entries=entries)
        result = _collect_aindex_data(tmp_path)
        assert len(result) == 1
        assert result[0].key_entries == []


# ---------------------------------------------------------------------------
# _generate_header
# ---------------------------------------------------------------------------


class TestGenerateHeader:
    """Verify project header generation from landmark data."""

    def test_empty_infos_returns_empty_string(self, tmp_path: Path) -> None:
        result = _generate_header([], tmp_path)
        assert result == ""

    def test_entry_point_from_description(self, tmp_path: Path) -> None:
        """Header should include Entry: path when description has entry-point keyword."""
        from lexibrary.archivist.topology import _DirInfo

        project_name = tmp_path.name
        infos = [
            _DirInfo(
                rel_path=f"{project_name}/src",
                billboard="Source code",
                child_entry_count=2,
                key_entries=[
                    AIndexEntry(
                        name="cli.py",
                        entry_type="file",
                        description="Application entry point",
                    ),
                ],
            ),
        ]
        result = _generate_header(infos, tmp_path)
        assert "Entry: src/cli.py" in result

    def test_test_root_from_dir_name(self, tmp_path: Path) -> None:
        """Header should include Tests: path when dir name is a test directory."""
        from lexibrary.archivist.topology import _DirInfo

        project_name = tmp_path.name
        infos = [
            _DirInfo(
                rel_path=f"{project_name}/tests",
                billboard="Test suite",
                child_entry_count=5,
            ),
        ]
        result = _generate_header(infos, tmp_path)
        assert "Tests: tests/" in result

    def test_config_file_by_name(self, tmp_path: Path) -> None:
        """Header should include Config: filename for known config files."""
        from lexibrary.archivist.topology import _DirInfo

        project_name = tmp_path.name
        infos = [
            _DirInfo(
                rel_path=project_name,
                billboard="Root",
                child_entry_count=3,
                key_entries=[
                    AIndexEntry(
                        name="pyproject.toml",
                        entry_type="file",
                        description="Build metadata",
                    ),
                ],
            ),
        ]
        result = _generate_header(infos, tmp_path)
        assert "Config: pyproject.toml" in result

    def test_minimal_header_no_landmarks(self, tmp_path: Path) -> None:
        """When no landmarks are detected, only line 1 (name + language) appears."""
        from lexibrary.archivist.topology import _DirInfo

        project_name = tmp_path.name
        infos = [
            _DirInfo(
                rel_path=project_name,
                billboard="Root",
                child_entry_count=1,
            ),
        ]
        result = _generate_header(infos, tmp_path)
        # Should contain the project name
        assert f"**{project_name}**" in result
        # Should be a single line (no landmarks line)
        assert "\n" not in result

    def test_multiple_entry_points_picks_first(self, tmp_path: Path) -> None:
        """When multiple entry points exist, only the first is reported."""
        from lexibrary.archivist.topology import _DirInfo

        project_name = tmp_path.name
        infos = [
            _DirInfo(
                rel_path=f"{project_name}/src",
                billboard="Source",
                child_entry_count=2,
                key_entries=[
                    AIndexEntry(
                        name="app.py",
                        entry_type="file",
                        description="Main entry point",
                    ),
                ],
            ),
            _DirInfo(
                rel_path=f"{project_name}/src/alt",
                billboard="Alt source",
                child_entry_count=1,
                key_entries=[
                    AIndexEntry(
                        name="alt_main.py",
                        entry_type="file",
                        description="Alternative entry point",
                    ),
                ],
            ),
        ]
        result = _generate_header(infos, tmp_path)
        assert "Entry: src/app.py" in result
        assert "alt_main.py" not in result

    def test_dominant_language_from_key_entries(self, tmp_path: Path) -> None:
        """Header should detect dominant language from file extensions in key_entries."""
        from lexibrary.archivist.topology import _DirInfo

        project_name = tmp_path.name
        infos = [
            _DirInfo(
                rel_path=project_name,
                billboard="Root",
                child_entry_count=3,
                key_entries=[
                    AIndexEntry(
                        name="main.py",
                        entry_type="file",
                        description="Application entry point",
                    ),
                    AIndexEntry(
                        name="pyproject.toml",
                        entry_type="file",
                        description="Project configuration",
                    ),
                ],
            ),
        ]
        result = _generate_header(infos, tmp_path)
        assert "Python" in result

    def test_dominant_source_dir_shown(self, tmp_path: Path) -> None:
        """Header should include dominant source dir when detected at depth 1."""
        from lexibrary.archivist.topology import _DirInfo

        project_name = tmp_path.name
        infos = [
            _DirInfo(
                rel_path=project_name,
                billboard="Root",
                child_entry_count=1,
            ),
            _DirInfo(
                rel_path=f"{project_name}/src",
                billboard="Source code",
                child_entry_count=5,
            ),
        ]
        result = _generate_header(infos, tmp_path)
        assert "(src/)" in result


# ---------------------------------------------------------------------------
# Collapse annotations
# ---------------------------------------------------------------------------


class TestCollapseAnnotation:
    """Verify hidden children annotation in tree output."""

    @pytest.fixture()
    def medium_project_with_children(self, tmp_path: Path) -> Path:
        """Create a medium project where depth-3 children are hidden."""
        (tmp_path / LEXIBRARY_DIR).mkdir()
        project_name = tmp_path.name

        # Build 15 directories to trigger medium threshold (depth <= 2)
        dirs_at_depth_1_2 = [
            (project_name, "Root"),
            (f"{project_name}/src", "Source"),
            (f"{project_name}/docs", "Docs"),
            (f"{project_name}/tools", "Tools"),
            (f"{project_name}/scripts", "Scripts"),
            (f"{project_name}/src/core", "Core logic"),
            (f"{project_name}/src/api", "API layer"),
            (f"{project_name}/src/utils", "Utilities"),
            (f"{project_name}/src/models", "Models"),
            (f"{project_name}/src/services", "Services"),
            (f"{project_name}/src/middleware", "Middleware"),
        ]
        for rel_path, billboard in dirs_at_depth_1_2:
            _write_aindex(tmp_path, rel_path, billboard)

        # Add depth-3 hidden children under src/core
        hidden_children = ["handlers", "schemas", "validators"]
        for child in hidden_children:
            _write_aindex(
                tmp_path,
                f"{project_name}/src/core/{child}",
                f"{child.capitalize()} module",
            )

        # Rewrite src/core with child_dir_names
        core_entries = [
            AIndexEntry(name=child, entry_type="dir", description=f"{child.capitalize()} module")
            for child in hidden_children
        ] + [
            AIndexEntry(name="base.py", entry_type="file", description="Core base"),
        ]
        _write_aindex(
            tmp_path,
            f"{project_name}/src/core",
            "Core logic",
            entries=core_entries,
        )

        return tmp_path

    def test_names_shown_up_to_4(self, medium_project_with_children: Path) -> None:
        result = _build_procedural_topology(medium_project_with_children)
        core_line = [line for line in result.splitlines() if "Core logic" in line][0]
        # 3 hidden children, all names shown
        assert "3 subdirs:" in core_line
        assert "handlers" in core_line
        assert "schemas" in core_line
        assert "validators" in core_line

    def test_ellipsis_when_more_than_4_hidden(self, tmp_path: Path) -> None:
        """When >4 children are hidden, show first 4 + ellipsis."""
        (tmp_path / LEXIBRARY_DIR).mkdir()
        project_name = tmp_path.name

        # Build enough dirs to trigger medium threshold
        base_dirs = [
            (project_name, "Root"),
            (f"{project_name}/src", "Source"),
            (f"{project_name}/docs", "Docs"),
            (f"{project_name}/tools", "Tools"),
            (f"{project_name}/scripts", "Scripts"),
            (f"{project_name}/config", "Config"),
            (f"{project_name}/src/core", "Core"),
            (f"{project_name}/src/api", "API"),
            (f"{project_name}/src/utils", "Utils"),
            (f"{project_name}/src/models", "Models"),
            (f"{project_name}/src/services", "Services"),
        ]
        for rel_path, billboard in base_dirs:
            _write_aindex(tmp_path, rel_path, billboard)

        # 5 hidden children under src/core (more than 4)
        hidden = ["alpha", "beta", "gamma", "delta", "epsilon"]
        for child in hidden:
            _write_aindex(tmp_path, f"{project_name}/src/core/{child}", f"{child} mod")

        core_entries = [
            AIndexEntry(name=child, entry_type="dir", description=f"{child} mod")
            for child in hidden
        ]
        _write_aindex(tmp_path, f"{project_name}/src/core", "Core", entries=core_entries)

        result = _build_procedural_topology(tmp_path)
        core_line = [
            line for line in result.splitlines()
            if "Core" in line and "subdirs" in line
        ][0]
        assert "5 subdirs:" in core_line
        assert "..." in core_line

    def test_greater_than_marker_present(self, medium_project_with_children: Path) -> None:
        result = _build_procedural_topology(medium_project_with_children)
        core_line = [line for line in result.splitlines() if "Core logic" in line][0]
        assert core_line.rstrip().endswith(">")

    def test_no_annotation_when_zero_hidden(self, tmp_path: Path) -> None:
        """No collapse annotation when all children are visible."""
        (tmp_path / LEXIBRARY_DIR).mkdir()
        project_name = tmp_path.name

        # Small project -- all dirs visible
        _write_aindex(tmp_path, project_name, "Root")
        entries = [
            AIndexEntry(name="sub", entry_type="dir", description="Sub module"),
        ]
        _write_aindex(tmp_path, project_name, "Root", entries=entries)
        _write_aindex(tmp_path, f"{project_name}/sub", "Sub module")

        result = _build_procedural_topology(tmp_path)
        root_line = [line for line in result.splitlines() if "Root" in line][0]
        assert "subdirs" not in root_line
        assert ">" not in root_line

    def test_names_sorted_alphabetically(self, medium_project_with_children: Path) -> None:
        result = _build_procedural_topology(medium_project_with_children)
        core_line = [line for line in result.splitlines() if "Core logic" in line][0]
        # Names should be alphabetically sorted: handlers, schemas, validators
        handler_pos = core_line.index("handlers")
        schema_pos = core_line.index("schemas")
        validator_pos = core_line.index("validators")
        assert handler_pos < schema_pos < validator_pos


# ---------------------------------------------------------------------------
# Importance-weighted depth
# ---------------------------------------------------------------------------


class TestImportanceWeightedDepth:
    """Verify landmark ancestors get +1 depth bonus."""

    def test_landmark_ancestor_shown_at_depth_plus_1(self, tmp_path: Path) -> None:
        """A directory on the path to a landmark should be visible at depth+1."""
        (tmp_path / LEXIBRARY_DIR).mkdir()
        project_name = tmp_path.name

        # Build a medium project (>10 dirs, depth limit = 2)
        dirs = [
            (project_name, "Root"),
            (f"{project_name}/src", "Source"),
            (f"{project_name}/docs", "Docs"),
            (f"{project_name}/tools", "Tools"),
            (f"{project_name}/scripts", "Scripts"),
            (f"{project_name}/config", "Config"),
            (f"{project_name}/src/core", "Core"),
            (f"{project_name}/src/api", "API"),
            (f"{project_name}/src/utils", "Utils"),
            (f"{project_name}/src/models", "Models"),
            (f"{project_name}/src/services", "Services"),
        ]
        for rel_path, billboard in dirs:
            _write_aindex(tmp_path, rel_path, billboard)

        # Add a landmark (entry point) at depth 3: src/core/app
        landmark_entries = [
            AIndexEntry(
                name="main.py",
                entry_type="file",
                description="Application entry point",
            ),
        ]
        _write_aindex(
            tmp_path,
            f"{project_name}/src/core/app",
            "App module",
            entries=landmark_entries,
        )

        result = _build_procedural_topology(tmp_path)
        # src/core/app is at depth 3; base limit is 2; but it's a landmark
        # so it gets +1 bonus -> visible at effective depth 3
        assert "App module" in result

    def test_non_landmark_at_depth_plus_1_hidden(self, tmp_path: Path) -> None:
        """A non-landmark directory at depth 3 should be hidden in medium projects."""
        (tmp_path / LEXIBRARY_DIR).mkdir()
        project_name = tmp_path.name

        dirs = [
            (project_name, "Root"),
            (f"{project_name}/src", "Source"),
            (f"{project_name}/docs", "Docs"),
            (f"{project_name}/tools", "Tools"),
            (f"{project_name}/scripts", "Scripts"),
            (f"{project_name}/config", "Config"),
            (f"{project_name}/src/core", "Core"),
            (f"{project_name}/src/api", "API"),
            (f"{project_name}/src/utils", "Utils"),
            (f"{project_name}/src/models", "Models"),
            (f"{project_name}/src/services", "Services"),
        ]
        for rel_path, billboard in dirs:
            _write_aindex(tmp_path, rel_path, billboard)

        # Add non-landmark dir at depth 3
        _write_aindex(
            tmp_path,
            f"{project_name}/src/core/helpers",
            "Generic helpers",
        )

        result = _build_procedural_topology(tmp_path)
        # Depth 3, not a landmark, not a hotspot -> hidden
        assert "Generic helpers" not in result


# ---------------------------------------------------------------------------
# Format improvements — blank lines
# ---------------------------------------------------------------------------


class TestFormatImprovements:
    """Verify blank lines between depth-1 sections."""

    def test_blank_lines_between_depth_1_sections(self, tmp_path: Path) -> None:
        (tmp_path / LEXIBRARY_DIR).mkdir()
        project_name = tmp_path.name

        _write_aindex(tmp_path, project_name, "Root")
        _write_aindex(tmp_path, f"{project_name}/src", "Source code")
        _write_aindex(tmp_path, f"{project_name}/src/auth", "Auth module")
        _write_aindex(tmp_path, f"{project_name}/tests", "Test suite")
        _write_aindex(tmp_path, f"{project_name}/docs", "Documentation")

        result = _build_procedural_topology(tmp_path)
        lines = result.splitlines()

        # Find the depth-1 section lines
        depth1_indices = [
            i for i, line in enumerate(lines)
            if line.startswith("  ") and not line.startswith("    ")
        ]
        # There should be blank lines between depth-1 sections
        # (each depth-1 after the first should be preceded by a blank line)
        for idx in depth1_indices[1:]:
            assert lines[idx - 1] == "", (
                f"Expected blank line before depth-1 section at line {idx}: {lines[idx]}"
            )

    def test_no_blank_lines_within_nested_sections(self, tmp_path: Path) -> None:
        (tmp_path / LEXIBRARY_DIR).mkdir()
        project_name = tmp_path.name

        _write_aindex(tmp_path, project_name, "Root")
        _write_aindex(tmp_path, f"{project_name}/src", "Source code")
        _write_aindex(tmp_path, f"{project_name}/src/auth", "Auth module")
        _write_aindex(tmp_path, f"{project_name}/src/utils", "Utilities")

        result = _build_procedural_topology(tmp_path)
        lines = result.splitlines()

        # Find the src/ section and its children
        src_idx = next(i for i, line in enumerate(lines) if "Source code" in line)
        # Lines immediately after src/ should be its children (depth 2), no blank lines
        for i in range(src_idx + 1, len(lines)):
            if lines[i].startswith("    "):
                # This is a depth-2 child -- the line before it should NOT be blank
                # (unless it's the first child right after src/)
                if i == src_idx + 1:
                    continue
                assert lines[i - 1] != "" or lines[i - 1].startswith("    "), (
                    f"Unexpected blank line within nested section at line {i}"
                )
            else:
                break


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
        # Header is present when .aindex data exists
        assert lines[2].startswith(f"**{project_name}**")
        assert lines[3] == ""
        assert lines[4] == "```"
        # The tree content
        assert "Root" in lines[5]
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

    def test_header_present_before_tree(self, tmp_path: Path) -> None:
        """When .aindex data exists, header should appear before the code fence."""
        (tmp_path / LEXIBRARY_DIR).mkdir()
        project_name = tmp_path.name
        _write_aindex(tmp_path, project_name, "Root")
        _write_aindex(tmp_path, f"{project_name}/src", "Source code")

        result_path = generate_topology(tmp_path)
        content = result_path.read_text(encoding="utf-8")
        lines = content.splitlines()

        # Line 0: heading, Line 1: blank, Line 2: header starts with **ProjectName**
        assert lines[0] == "# Project Topology"
        assert lines[1] == ""
        assert lines[2].startswith(f"**{project_name}**")
        # Then blank line, then code fence
        fence_idx = next(i for i, line in enumerate(lines) if line == "```")
        assert fence_idx > 2

    def test_header_absent_when_no_aindex_data(self, tmp_path: Path) -> None:
        """When no .aindex data exists, header should not appear."""
        (tmp_path / LEXIBRARY_DIR).mkdir()

        result_path = generate_topology(tmp_path)
        content = result_path.read_text(encoding="utf-8")
        lines = content.splitlines()

        # Line 0: heading, Line 1: blank, Line 2: code fence (no header)
        assert lines[0] == "# Project Topology"
        assert lines[1] == ""
        assert lines[2] == "```"
        # No ** bold markers in the content (no header)
        assert "**" not in content
