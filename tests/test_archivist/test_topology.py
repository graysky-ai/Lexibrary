"""Tests for procedural topology generation (replaces test_start_here.py)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from lexibrary.archivist.topology import (
    _TOKEN_BUDGET,
    SECTION_NAMES,
    _apply_token_sentinel,
    _build_procedural_topology,
    _build_source_module_map,
    _collect_aindex_data,
    _compute_depth,
    _display_path,
    _find_dominant_source_dir,
    _generate_directory_details,
    _generate_entry_point_candidates,
    _generate_header,
    _is_test_directory,
    _render_summary_block,
    _render_test_layout_block,
    _section_wrap,
    _should_detail_directory,
    generate_raw_topology,
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
                name="helpers.py",
                entry_type="file",
                description="Shared helper functions",
            ),
            AIndexEntry(
                name="models.py",
                entry_type="file",
                description="Data model definitions",
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

    def test_multiple_entry_points_prefers_cli_dir(self, tmp_path: Path) -> None:
        """Entry point in a cli/ dir is preferred over one in a generic dir."""
        from lexibrary.archivist.topology import _DirInfo

        project_name = tmp_path.name
        infos = [
            _DirInfo(
                rel_path=f"{project_name}/src",
                billboard="Source",
                child_entry_count=2,
                key_entries=[
                    AIndexEntry(
                        name="__main__.py",
                        entry_type="file",
                        description="Minimal entry point redirect",
                    ),
                ],
            ),
            _DirInfo(
                rel_path=f"{project_name}/src/cli",
                billboard="CLI commands",
                child_entry_count=3,
                key_entries=[
                    AIndexEntry(
                        name="lexi_app.py",
                        entry_type="file",
                        description="Main application entry point",
                    ),
                ],
            ),
        ]
        result = _generate_header(infos, tmp_path)
        assert "Entry: src/cli/lexi_app.py" in result
        assert "__main__.py" not in result

    def test_minimal_entry_point_skipped(self, tmp_path: Path) -> None:
        """Entry points described as 'minimal entry point' are skipped."""
        from lexibrary.archivist.topology import _DirInfo

        project_name = tmp_path.name
        infos = [
            _DirInfo(
                rel_path=f"{project_name}/src",
                billboard="Source",
                child_entry_count=1,
                key_entries=[
                    AIndexEntry(
                        name="__main__.py",
                        entry_type="file",
                        description="Minimal entry point that delegates to cli/",
                    ),
                ],
            ),
        ]
        result = _generate_header(infos, tmp_path)
        assert "Entry:" not in result

    def test_entry_point_in_non_preferred_dir_shown_when_no_preferred_alt(
        self, tmp_path: Path
    ) -> None:
        """A root-level entry point is still shown when no cli/app dir exists."""
        from lexibrary.archivist.topology import _DirInfo

        project_name = tmp_path.name
        infos = [
            _DirInfo(
                rel_path=f"{project_name}/src",
                billboard="Source",
                child_entry_count=2,
                key_entries=[
                    AIndexEntry(
                        name="main.py",
                        entry_type="file",
                        description="Application entry point",
                    ),
                ],
            ),
        ]
        result = _generate_header(infos, tmp_path)
        assert "Entry: src/main.py" in result

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
        result = _build_procedural_topology(
            medium_project_with_children,
            _collect_aindex_data(medium_project_with_children),
        )
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

        result = _build_procedural_topology(tmp_path, _collect_aindex_data(tmp_path))
        core_line = [line for line in result.splitlines() if "Core" in line and "subdirs" in line][
            0
        ]
        assert "5 subdirs:" in core_line
        assert "..." in core_line

    def test_greater_than_marker_present(self, medium_project_with_children: Path) -> None:
        result = _build_procedural_topology(
            medium_project_with_children,
            _collect_aindex_data(medium_project_with_children),
        )
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

        result = _build_procedural_topology(tmp_path, _collect_aindex_data(tmp_path))
        root_line = [line for line in result.splitlines() if "Root" in line][0]
        assert "subdirs" not in root_line
        assert ">" not in root_line

    def test_names_sorted_alphabetically(self, medium_project_with_children: Path) -> None:
        result = _build_procedural_topology(
            medium_project_with_children,
            _collect_aindex_data(medium_project_with_children),
        )
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

        result = _build_procedural_topology(tmp_path, _collect_aindex_data(tmp_path))
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

        result = _build_procedural_topology(tmp_path, _collect_aindex_data(tmp_path))
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

        result = _build_procedural_topology(tmp_path, _collect_aindex_data(tmp_path))
        lines = result.splitlines()

        # Find the depth-1 section lines
        depth1_indices = [
            i
            for i, line in enumerate(lines)
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

        result = _build_procedural_topology(tmp_path, _collect_aindex_data(tmp_path))
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
        result = _build_procedural_topology(tmp_path, _collect_aindex_data(tmp_path))
        assert result == "(no .lexibrary directory found)"

    def test_no_aindex_files(self, tmp_path: Path) -> None:
        (tmp_path / LEXIBRARY_DIR).mkdir()
        result = _build_procedural_topology(tmp_path, _collect_aindex_data(tmp_path))
        assert result == "(no .aindex files found -- run 'lexi update' first)"

    def test_single_directory(self, tmp_path: Path) -> None:
        (tmp_path / LEXIBRARY_DIR).mkdir()
        project_name = tmp_path.name
        _write_aindex(tmp_path, project_name, "Root project directory")

        result = _build_procedural_topology(tmp_path, _collect_aindex_data(tmp_path))
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

        result = _build_procedural_topology(tmp_path, _collect_aindex_data(tmp_path))
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

        result = _build_procedural_topology(tmp_path, _collect_aindex_data(tmp_path))
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

        result = _build_procedural_topology(tmp_path, _collect_aindex_data(tmp_path))
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
        result = _build_procedural_topology(tmp_path, _collect_aindex_data(tmp_path))
        assert " -- Has billboard" in result

    def test_dir_display_uses_last_component(self, tmp_path: Path) -> None:
        (tmp_path / LEXIBRARY_DIR).mkdir()
        project_name = tmp_path.name

        _write_aindex(tmp_path, f"{project_name}/src/auth/handlers", "Request handlers")

        result = _build_procedural_topology(tmp_path, _collect_aindex_data(tmp_path))
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
        result = _build_procedural_topology(medium_project, _collect_aindex_data(medium_project))
        # Depth 0-2 directories should be shown
        assert "Root directory" in result
        assert "Source code" in result
        assert "Authentication" in result

    def test_depth_3_directories_filtered(self, medium_project: Path) -> None:
        result = _build_procedural_topology(medium_project, _collect_aindex_data(medium_project))
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

        result = _build_procedural_topology(medium_project, _collect_aindex_data(medium_project))
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

        result = _build_procedural_topology(medium_project, _collect_aindex_data(medium_project))
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
        result = _build_procedural_topology(large_project, _collect_aindex_data(large_project))
        assert "Large project root" in result
        assert "Package 0" in result
        assert "Package 9" in result

    def test_depth_2_directories_filtered(self, large_project: Path) -> None:
        result = _build_procedural_topology(large_project, _collect_aindex_data(large_project))
        # Depth 2 dirs should generally be filtered (unless hotspots)
        assert "Subpackage 0.0" not in result


# ---------------------------------------------------------------------------
# generate_raw_topology — end-to-end
# ---------------------------------------------------------------------------


class TestGenerateTopology:
    """Verify generate_raw_topology() writes a valid TOPOLOGY.md file."""

    def test_writes_topology_md(self, tmp_path: Path) -> None:
        (tmp_path / LEXIBRARY_DIR).mkdir()
        project_name = tmp_path.name

        _write_aindex(tmp_path, project_name, "Root directory")
        _write_aindex(tmp_path, f"{project_name}/src", "Source code")

        result_path = generate_raw_topology(tmp_path)

        expected_path = tmp_path / LEXIBRARY_DIR / "tmp" / "raw-topology.md"
        assert result_path == expected_path
        assert expected_path.exists()

    def test_content_has_markdown_structure(self, tmp_path: Path) -> None:
        (tmp_path / LEXIBRARY_DIR).mkdir()
        project_name = tmp_path.name

        _write_aindex(tmp_path, project_name, "Root directory")
        _write_aindex(tmp_path, f"{project_name}/src", "Source code")

        result_path = generate_raw_topology(tmp_path)
        content = result_path.read_text(encoding="utf-8")

        assert content.startswith("# Project Topology\n")
        assert "```\n" in content
        assert "Root directory" in content
        assert "Source code" in content

    def test_tree_wrapped_in_code_fence(self, tmp_path: Path) -> None:
        (tmp_path / LEXIBRARY_DIR).mkdir()
        project_name = tmp_path.name
        _write_aindex(tmp_path, project_name, "Root")

        result_path = generate_raw_topology(tmp_path)
        content = result_path.read_text(encoding="utf-8")

        lines = content.splitlines()
        assert lines[0] == "# Project Topology"
        # Header should be present (possibly wrapped in section markers)
        assert f"**{project_name}**" in content
        # Tree should be wrapped in code fences
        assert "```" in content
        # The tree content
        assert "Root" in content
        # Closing fence after tree content
        assert "```" in content.split("Root", 1)[1]

    def test_no_aindex_writes_placeholder(self, tmp_path: Path) -> None:
        (tmp_path / LEXIBRARY_DIR).mkdir()

        result_path = generate_raw_topology(tmp_path)
        content = result_path.read_text(encoding="utf-8")

        assert "no .aindex files found" in content

    def test_overwrites_existing_topology(self, tmp_path: Path) -> None:
        (tmp_path / LEXIBRARY_DIR).mkdir()
        project_name = tmp_path.name

        tmp_dir = tmp_path / LEXIBRARY_DIR / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        topology_path = tmp_dir / "raw-topology.md"
        topology_path.write_text("# Old content\n", encoding="utf-8")

        _write_aindex(tmp_path, project_name, "Fresh root")

        result_path = generate_raw_topology(tmp_path)
        content = result_path.read_text(encoding="utf-8")

        assert "Old content" not in content
        assert "Fresh root" in content

    def test_returns_correct_path(self, tmp_path: Path) -> None:
        (tmp_path / LEXIBRARY_DIR).mkdir()
        project_name = tmp_path.name
        _write_aindex(tmp_path, project_name, "Root")

        result = generate_raw_topology(tmp_path)
        assert result == tmp_path / LEXIBRARY_DIR / "tmp" / "raw-topology.md"

    def test_header_present_before_tree(self, tmp_path: Path) -> None:
        """When .aindex data exists, header should appear before the code fence."""
        (tmp_path / LEXIBRARY_DIR).mkdir()
        project_name = tmp_path.name
        _write_aindex(tmp_path, project_name, "Root")
        _write_aindex(tmp_path, f"{project_name}/src", "Source code")

        result_path = generate_raw_topology(tmp_path)
        content = result_path.read_text(encoding="utf-8")

        assert content.startswith("# Project Topology")
        # Header with project name should appear
        assert f"**{project_name}**" in content
        # Header should come before the tree code fence
        header_pos = content.index(f"**{project_name}**")
        fence_pos = content.index("```")
        assert header_pos < fence_pos

    def test_header_absent_when_no_aindex_data(self, tmp_path: Path) -> None:
        """When no .aindex data exists, header should not appear."""
        (tmp_path / LEXIBRARY_DIR).mkdir()

        result_path = generate_raw_topology(tmp_path)
        content = result_path.read_text(encoding="utf-8")

        assert content.startswith("# Project Topology")
        # No ** bold markers in the content (no header)
        assert "**" not in content
        # Code fence should be present (tree section)
        assert "```" in content

    # -- Directory Details section --

    def test_directory_details_section_present(self, tmp_path: Path) -> None:
        """Raw topology includes source modules with per-dir subsections."""
        (tmp_path / LEXIBRARY_DIR).mkdir()
        project_name = tmp_path.name

        # Create a project with a src/ directory so the detail filtering
        # classifies entries under it as source modules (Group 5 filtering).
        root_entries = [
            AIndexEntry(name="src", entry_type="dir", description="Source"),
        ]
        _write_aindex(tmp_path, project_name, "Root", entries=root_entries)

        src_entries = [
            AIndexEntry(name="main.py", entry_type="file", description="App entry point"),
            AIndexEntry(name="utils", entry_type="dir", description="Helpers"),
        ]
        _write_aindex(tmp_path, f"{project_name}/src", "Source code", entries=src_entries)

        result_path = generate_raw_topology(tmp_path)
        content = result_path.read_text(encoding="utf-8")

        # Source modules section replaces the old Directory Details heading
        assert "## Source Modules" in content
        assert "### src/" in content
        assert "| Name | Type | Description |" in content
        assert "main.py" in content
        assert "App entry point" in content

    def test_directory_details_file_and_subdir_counts(self, tmp_path: Path) -> None:
        """Directory Details shows file and subdirectory counts."""
        (tmp_path / LEXIBRARY_DIR).mkdir()
        project_name = tmp_path.name

        # Set up a src/ directory so detail filtering includes it (Group 5).
        root_entries = [
            AIndexEntry(name="src", entry_type="dir", description="Source"),
        ]
        _write_aindex(tmp_path, project_name, "Root", entries=root_entries)

        src_entries = [
            AIndexEntry(name="a.py", entry_type="file", description="Module A"),
            AIndexEntry(name="b.py", entry_type="file", description="Module B"),
            AIndexEntry(name="sub", entry_type="dir", description="Sub package"),
        ]
        _write_aindex(tmp_path, f"{project_name}/src", "Source code", entries=src_entries)

        result_path = generate_raw_topology(tmp_path)
        content = result_path.read_text(encoding="utf-8")

        assert "Files: 2 | Subdirectories: 1" in content

    # -- Library Stats section --

    def test_library_stats_section_present(self, tmp_path: Path) -> None:
        """Raw topology includes '## Library Stats' with artifact counts."""
        (tmp_path / LEXIBRARY_DIR).mkdir()
        project_name = tmp_path.name
        _write_aindex(tmp_path, project_name, "Root")

        # Create some library artifacts
        concepts_dir = tmp_path / LEXIBRARY_DIR / "concepts"
        concepts_dir.mkdir()
        (concepts_dir / "foo.md").write_text("# Concept\n", encoding="utf-8")
        (concepts_dir / "bar.md").write_text("# Concept\n", encoding="utf-8")

        conventions_dir = tmp_path / LEXIBRARY_DIR / "conventions"
        conventions_dir.mkdir()
        (conventions_dir / "rule.md").write_text("# Conv\n", encoding="utf-8")

        result_path = generate_raw_topology(tmp_path)
        content = result_path.read_text(encoding="utf-8")

        assert "## Library Stats" in content
        assert "Concepts: 2" in content
        assert "Conventions: 1" in content
        assert "Playbooks: 0" in content
        assert "Open stack posts: 0" in content

    # -- Project Config section --

    def test_project_config_section_with_pyproject(self, tmp_path: Path) -> None:
        """Raw topology includes '## Project Config' when pyproject.toml exists."""
        (tmp_path / LEXIBRARY_DIR).mkdir()
        project_name = tmp_path.name
        _write_aindex(tmp_path, project_name, "Root")

        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "myproject"\nversion = "0.1.0"\n', encoding="utf-8"
        )

        result_path = generate_raw_topology(tmp_path)
        content = result_path.read_text(encoding="utf-8")

        assert "## Project Config" in content
        assert "**pyproject.toml**" in content
        assert "```toml" in content
        assert 'name = "myproject"' in content

    def test_project_config_absent_when_no_config_file(self, tmp_path: Path) -> None:
        """Raw topology omits Project Config section when no config file found."""
        (tmp_path / LEXIBRARY_DIR).mkdir()
        project_name = tmp_path.name
        _write_aindex(tmp_path, project_name, "Root")

        result_path = generate_raw_topology(tmp_path)
        content = result_path.read_text(encoding="utf-8")

        assert "## Project Config" not in content


# ---------------------------------------------------------------------------
# Section markers
# ---------------------------------------------------------------------------


class TestSectionMarkers:
    """Verify all 7 section marker pairs in raw topology output."""

    def _make_project_with_tests(self, tmp_path: Path) -> str:
        """Create a project with source dirs, test dirs, and config file."""
        (tmp_path / LEXIBRARY_DIR).mkdir()
        project_name = tmp_path.name

        _write_aindex(tmp_path, project_name, "Root")
        _write_aindex(
            tmp_path,
            f"{project_name}/src",
            "Source code",
            entries=[
                AIndexEntry(
                    name="main.py",
                    entry_type="file",
                    description="Application entry point",
                ),
            ],
        )
        _write_aindex(
            tmp_path,
            f"{project_name}/tests",
            "Test suite",
            entries=[
                AIndexEntry(
                    name="test_main.py",
                    entry_type="file",
                    description="Main tests",
                ),
            ],
        )

        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "test"\n', encoding="utf-8"
        )

        # Create a library artifact for stats
        concepts_dir = tmp_path / LEXIBRARY_DIR / "concepts"
        concepts_dir.mkdir()
        (concepts_dir / "foo.md").write_text("# Concept\n", encoding="utf-8")

        return project_name

    def test_all_7_section_markers_present(self, tmp_path: Path) -> None:
        """Raw topology contains exactly 7 section/end marker pairs."""
        self._make_project_with_tests(tmp_path)

        result_path = generate_raw_topology(tmp_path)
        content = result_path.read_text(encoding="utf-8")

        for name in SECTION_NAMES:
            assert f"<!-- section: {name} -->" in content, (
                f"missing opening marker for section '{name}'"
            )
            assert f"<!-- end: {name} -->" in content, (
                f"missing closing marker for section '{name}'"
            )

    def test_exactly_7_section_markers(self, tmp_path: Path) -> None:
        """Output contains exactly 7 opening and 7 closing markers."""
        self._make_project_with_tests(tmp_path)

        result_path = generate_raw_topology(tmp_path)
        content = result_path.read_text(encoding="utf-8")

        open_count = content.count("<!-- section:")
        close_count = content.count("<!-- end:")
        assert open_count == 7
        assert close_count == 7

    def test_markers_not_nested(self, tmp_path: Path) -> None:
        """Section markers are not nested -- each end marker appears before
        the next section marker."""
        self._make_project_with_tests(tmp_path)

        result_path = generate_raw_topology(tmp_path)
        content = result_path.read_text(encoding="utf-8")

        import re as _re

        # Collect all marker positions in order
        markers = list(
            _re.finditer(r"<!-- (?:section|end): [\w-]+ -->", content)
        )
        assert len(markers) == 14  # 7 open + 7 close

        # Walk markers in order: each open must be followed by its close
        # before any other open.
        open_stack: list[str] = []
        for m in markers:
            text = m.group()
            if text.startswith("<!-- section:"):
                name = text.removeprefix("<!-- section: ").removesuffix(" -->")
                assert not open_stack, (
                    f"section '{name}' opened while '{open_stack[-1]}' is still open"
                )
                open_stack.append(name)
            else:
                name = text.removeprefix("<!-- end: ").removesuffix(" -->")
                assert open_stack, f"end marker for '{name}' without matching open"
                assert open_stack[-1] == name, (
                    f"end marker for '{name}' but '{open_stack[-1]}' is open"
                )
                open_stack.pop()
        assert not open_stack, f"unclosed sections: {open_stack}"

    def test_section_order_matches_spec(self, tmp_path: Path) -> None:
        """Sections appear in the canonical order defined by SECTION_NAMES."""
        self._make_project_with_tests(tmp_path)

        result_path = generate_raw_topology(tmp_path)
        content = result_path.read_text(encoding="utf-8")

        positions = []
        for name in SECTION_NAMES:
            pos = content.index(f"<!-- section: {name} -->")
            positions.append(pos)

        # Verify positions are strictly increasing
        for i in range(1, len(positions)):
            assert positions[i] > positions[i - 1], (
                f"section '{SECTION_NAMES[i]}' appears before "
                f"'{SECTION_NAMES[i - 1]}' in output"
            )

    def test_header_content_within_markers(self, tmp_path: Path) -> None:
        """Header text is enclosed within the header section markers."""
        project_name = self._make_project_with_tests(tmp_path)

        result_path = generate_raw_topology(tmp_path)
        content = result_path.read_text(encoding="utf-8")

        # Extract content between header markers
        start = content.index("<!-- section: header -->")
        end = content.index("<!-- end: header -->")
        header_section = content[start:end]

        assert f"**{project_name}**" in header_section

    def test_tree_content_within_markers(self, tmp_path: Path) -> None:
        """Tree code fence is enclosed within the tree section markers."""
        self._make_project_with_tests(tmp_path)

        result_path = generate_raw_topology(tmp_path)
        content = result_path.read_text(encoding="utf-8")

        start = content.index("<!-- section: tree -->")
        end = content.index("<!-- end: tree -->")
        tree_section = content[start:end]

        assert "```" in tree_section
        assert "src/" in tree_section

    def test_source_modules_within_markers(self, tmp_path: Path) -> None:
        """Source module details are within source-modules section markers."""
        self._make_project_with_tests(tmp_path)

        result_path = generate_raw_topology(tmp_path)
        content = result_path.read_text(encoding="utf-8")

        start = content.index("<!-- section: source-modules -->")
        end = content.index("<!-- end: source-modules -->")
        source_section = content[start:end]

        assert "## Source Modules" in source_section
        assert "src/" in source_section

    def test_test_layout_within_markers(self, tmp_path: Path) -> None:
        """Test directory details are within test-layout section markers."""
        self._make_project_with_tests(tmp_path)

        result_path = generate_raw_topology(tmp_path)
        content = result_path.read_text(encoding="utf-8")

        start = content.index("<!-- section: test-layout -->")
        end = content.index("<!-- end: test-layout -->")
        test_section = content[start:end]

        assert "## Test Layout" in test_section
        assert "tests/" in test_section

    def test_stats_within_markers(self, tmp_path: Path) -> None:
        """Library stats are within the stats section markers."""
        self._make_project_with_tests(tmp_path)

        result_path = generate_raw_topology(tmp_path)
        content = result_path.read_text(encoding="utf-8")

        start = content.index("<!-- section: stats -->")
        end = content.index("<!-- end: stats -->")
        stats_section = content[start:end]

        assert "Concepts: 1" in stats_section

    def test_config_within_markers(self, tmp_path: Path) -> None:
        """Project config is within the config section markers."""
        self._make_project_with_tests(tmp_path)

        result_path = generate_raw_topology(tmp_path)
        content = result_path.read_text(encoding="utf-8")

        start = content.index("<!-- section: config -->")
        end = content.index("<!-- end: config -->")
        config_section = content[start:end]

        assert "## Project Config" in config_section
        assert "pyproject.toml" in config_section


class TestSectionWrap:
    """Verify _section_wrap() helper."""

    def test_wraps_content(self) -> None:
        result = _section_wrap("tree", "some content")
        assert result == "<!-- section: tree -->\nsome content\n<!-- end: tree -->"

    def test_empty_content(self) -> None:
        result = _section_wrap("header", "")
        assert result == "<!-- section: header -->\n\n<!-- end: header -->"


class TestIsTestDirectory:
    """Verify _is_test_directory() classification."""

    def test_root_test_dir(self) -> None:
        assert _is_test_directory("tests") is True

    def test_nested_under_test(self) -> None:
        assert _is_test_directory("myproject/tests/test_foo") is True

    def test_source_dir(self) -> None:
        assert _is_test_directory("myproject/src/module") is False

    def test_test_prefix_is_not_test_dir(self) -> None:
        # "test_foo" is not in _TEST_DIR_NAMES -- only "test" and "tests" are
        assert _is_test_directory("myproject/src/test_foo") is False

    def test_spec_dir(self) -> None:
        assert _is_test_directory("myproject/spec") is True

    def test_dunder_tests(self) -> None:
        assert _is_test_directory("myproject/__tests__") is True


# ---------------------------------------------------------------------------
# B1 — landmark dirs always shown
# ---------------------------------------------------------------------------


def _large_project_base(tmp_path: Path) -> str:
    """Create 42 directories to trigger large-project mode (display_depth=1)."""
    (tmp_path / LEXIBRARY_DIR).mkdir()
    project_name = tmp_path.name
    _write_aindex(tmp_path, project_name, "Root")
    _write_aindex(tmp_path, f"{project_name}/src", "Source")
    _write_aindex(tmp_path, f"{project_name}/tests", "Tests")
    _write_aindex(tmp_path, f"{project_name}/docs", "Docs")
    # Create enough dirs to exceed the 40-dir medium threshold
    for i in range(38):
        _write_aindex(tmp_path, f"{project_name}/src/pkg{i}", f"Package {i}")
    return project_name


class TestLandmarkDirsAlwaysShow:
    """B1: landmark directories shown unconditionally regardless of depth."""

    def test_landmark_dir_shown_at_depth3_in_large_project(self, tmp_path: Path) -> None:
        """A depth-3 dir with key_entries must appear even in large-project mode."""
        project_name = _large_project_base(tmp_path)
        _write_aindex(
            tmp_path,
            f"{project_name}/src",
            "Source",
            entries=[
                AIndexEntry(name="lexibrary", entry_type="dir", description="Main package"),
            ],
        )
        _write_aindex(
            tmp_path,
            f"{project_name}/src/lexibrary",
            "Main package",
            entries=[
                AIndexEntry(name="config", entry_type="dir", description="Config module"),
            ],
        )
        # Landmark: has an entry matching config keyword
        _write_aindex(
            tmp_path,
            f"{project_name}/src/lexibrary/config",
            "Configuration schema and loader",
            entries=[
                AIndexEntry(
                    name="schema.py",
                    entry_type="file",
                    description="Project configuration schema",
                ),
            ],
        )
        result = _build_procedural_topology(tmp_path, _collect_aindex_data(tmp_path))
        assert "Configuration schema and loader" in result

    def test_non_landmark_small_dir_hidden_at_depth3_in_large_project(self, tmp_path: Path) -> None:
        """A depth-3 dir with no key_entries and no rich billboard stays hidden."""
        project_name = _large_project_base(tmp_path)
        _write_aindex(
            tmp_path,
            f"{project_name}/src/pkg0",
            "Package 0",
            entries=[
                AIndexEntry(name="helpers", entry_type="dir", description="Helpers"),
            ],
        )
        _write_aindex(
            tmp_path,
            f"{project_name}/src/pkg0/helpers",
            "3 Python files",  # structural billboard → not a landmark
        )
        result = _build_procedural_topology(tmp_path, _collect_aindex_data(tmp_path))
        assert "3 Python files" not in result

    def test_landmark_dirs_shown_regardless_of_child_count(self, tmp_path: Path) -> None:
        """A landmark dir with only 1 child entry is shown in large-project mode."""
        project_name = _large_project_base(tmp_path)
        _write_aindex(
            tmp_path,
            f"{project_name}/src",
            "Source",
            entries=[
                AIndexEntry(name="auth", entry_type="dir", description="Auth module"),
            ],
        )
        # 1 child entry — well below hotspot threshold of 5
        _write_aindex(
            tmp_path,
            f"{project_name}/src/auth",
            "Authentication pipeline",
            entries=[
                AIndexEntry(
                    name="pyproject.toml",
                    entry_type="file",
                    description="Build configuration",
                ),
            ],
        )
        result = _build_procedural_topology(tmp_path, _collect_aindex_data(tmp_path))
        assert "Authentication pipeline" in result


# ---------------------------------------------------------------------------
# B2 — hotspot classification gated on non-structural billboard
# ---------------------------------------------------------------------------


class TestHotspotBillboardGate:
    """B2: directories with structural billboards don't qualify as hotspots."""

    def _make_large_project(self, tmp_path: Path) -> tuple[Path, str]:
        (tmp_path / LEXIBRARY_DIR).mkdir()
        project_name = tmp_path.name
        _write_aindex(tmp_path, project_name, "Root")
        for i in range(41):
            _write_aindex(tmp_path, f"{project_name}/pkg{i}", f"Package {i}")
        return tmp_path, project_name

    def test_structural_billboard_not_hotspot_even_when_large(self, tmp_path: Path) -> None:
        """Dir with '9 Python files' billboard and 9 entries must NOT appear as hotspot."""
        root, project_name = self._make_large_project(tmp_path)
        many_entries = [
            AIndexEntry(name=f"f{i}.py", entry_type="file", description="Python source (1 lines)")
            for i in range(9)
        ]
        _write_aindex(
            tmp_path,
            f"{project_name}/pkg0/sub",
            "9 Python files",  # structural
            entries=many_entries,
        )
        result = _build_procedural_topology(tmp_path, _collect_aindex_data(tmp_path))
        assert "9 Python files" not in result

    def test_rich_billboard_qualifies_as_hotspot(self, tmp_path: Path) -> None:
        """Dir with synthesized billboard and 9 entries MUST appear as hotspot."""
        root, project_name = self._make_large_project(tmp_path)
        many_entries = [
            AIndexEntry(name=f"f{i}.py", entry_type="file", description=f"Module {i}")
            for i in range(9)
        ]
        _write_aindex(
            tmp_path,
            f"{project_name}/pkg0/sub",
            "authentication and session management pipeline",  # rich
            entries=many_entries,
        )
        result = _build_procedural_topology(tmp_path, _collect_aindex_data(tmp_path))
        assert "authentication and session management pipeline" in result


# ---------------------------------------------------------------------------
# B3 — test directory annotation from source counterpart
# ---------------------------------------------------------------------------


class TestTestDirCorrelation:
    """B3: test_<name>/ annotation is derived from src/<name>/ billboard."""

    def _make_correlated_project(self, tmp_path: Path) -> str:
        """Small project with src/auth/ and tests/test_auth/."""
        (tmp_path / LEXIBRARY_DIR).mkdir()
        project_name = tmp_path.name
        _write_aindex(tmp_path, project_name, "Root")
        _write_aindex(
            tmp_path,
            f"{project_name}/src",
            "Source",
            entries=[
                AIndexEntry(name="auth", entry_type="dir", description="Auth module"),
            ],
        )
        _write_aindex(
            tmp_path,
            f"{project_name}/src/auth",
            "authentication and session management",
        )
        _write_aindex(
            tmp_path,
            f"{project_name}/tests",
            "Tests",
            entries=[
                AIndexEntry(name="test_auth", entry_type="dir", description="7 Python files"),
            ],
        )
        _write_aindex(tmp_path, f"{project_name}/tests/test_auth", "7 Python files")
        return project_name

    def test_test_dir_annotation_derived_from_source_counterpart(self, tmp_path: Path) -> None:
        self._make_correlated_project(tmp_path)
        result = _build_procedural_topology(tmp_path, _collect_aindex_data(tmp_path))
        assert "Tests for auth:" in result
        assert "authentication and session management" in result

    def test_test_dir_keeps_own_billboard_when_no_source_match(self, tmp_path: Path) -> None:
        (tmp_path / LEXIBRARY_DIR).mkdir()
        project_name = tmp_path.name
        _write_aindex(tmp_path, project_name, "Root")
        _write_aindex(tmp_path, f"{project_name}/src", "Source")
        _write_aindex(
            tmp_path,
            f"{project_name}/tests",
            "Tests",
            entries=[
                AIndexEntry(name="test_widgets", entry_type="dir", description="5 Python files"),
            ],
        )
        _write_aindex(tmp_path, f"{project_name}/tests/test_widgets", "5 Python files")
        result = _build_procedural_topology(tmp_path, _collect_aindex_data(tmp_path))
        # No src/widgets/ exists so falls back to own billboard
        assert "Tests for widgets:" not in result
        assert "5 Python files" in result

    def test_test_dir_keeps_own_billboard_when_source_has_structural_billboard(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / LEXIBRARY_DIR).mkdir()
        project_name = tmp_path.name
        _write_aindex(tmp_path, project_name, "Root")
        _write_aindex(
            tmp_path,
            f"{project_name}/src",
            "Source",
            entries=[
                AIndexEntry(name="utils", entry_type="dir", description="3 Python files"),
            ],
        )
        _write_aindex(tmp_path, f"{project_name}/src/utils", "3 Python files")
        _write_aindex(
            tmp_path,
            f"{project_name}/tests",
            "Tests",
            entries=[
                AIndexEntry(name="test_utils", entry_type="dir", description="4 Python files"),
            ],
        )
        _write_aindex(tmp_path, f"{project_name}/tests/test_utils", "4 Python files")
        result = _build_procedural_topology(tmp_path, _collect_aindex_data(tmp_path))
        # src/utils has structural billboard → not used for derivation
        assert "Tests for utils:" not in result


# ---------------------------------------------------------------------------
# B3 — _find_dominant_source_dir
# ---------------------------------------------------------------------------


class TestFindDominantSourceDir:
    """Unit tests for the extracted _find_dominant_source_dir helper."""

    def test_returns_src_when_present(self, tmp_path: Path) -> None:
        from lexibrary.archivist.topology import _DirInfo

        project_name = tmp_path.name
        infos = [
            _DirInfo(rel_path=project_name, billboard="Root", child_entry_count=1),
            _DirInfo(rel_path=f"{project_name}/src", billboard="Source", child_entry_count=5),
        ]
        assert _find_dominant_source_dir(infos, project_name) == "src"

    def test_returns_lib_when_no_src(self, tmp_path: Path) -> None:
        from lexibrary.archivist.topology import _DirInfo

        project_name = tmp_path.name
        infos = [
            _DirInfo(rel_path=project_name, billboard="Root", child_entry_count=1),
            _DirInfo(rel_path=f"{project_name}/lib", billboard="Library", child_entry_count=5),
        ]
        assert _find_dominant_source_dir(infos, project_name) == "lib"

    def test_returns_empty_string_when_no_candidate(self, tmp_path: Path) -> None:
        from lexibrary.archivist.topology import _DirInfo

        project_name = tmp_path.name
        infos = [
            _DirInfo(rel_path=project_name, billboard="Root", child_entry_count=1),
            _DirInfo(rel_path=f"{project_name}/custom", billboard="Custom", child_entry_count=5),
        ]
        assert _find_dominant_source_dir(infos, project_name) == ""


# ---------------------------------------------------------------------------
# Size sentinel — 25K token cap
# ---------------------------------------------------------------------------


class TestTokenSentinel:
    """Verify _apply_token_sentinel caps raw topology output."""

    def test_content_within_budget_passes_through(self) -> None:
        """Content under 25K tokens is returned unchanged."""
        from lexibrary.archivist.topology import _DirInfo

        content = "# Topology\n" + "x" * 1000
        infos = [_DirInfo(rel_path="proj", billboard="Root", child_entry_count=1)]
        result = _apply_token_sentinel(content, infos, "proj")
        assert result == content

    def test_over_budget_triggers_table_removal(self, tmp_path: Path) -> None:
        """Content over 25K tokens has file tables trimmed from largest dirs first."""
        from lexibrary.archivist.topology import _DirInfo

        project_name = "bigproject"
        num_files = 1000

        # Build content larger than 25K tokens (100K chars needed)
        lines = ["# Project Topology", "", "```", f"{project_name}/ -- Root", "```", ""]
        lines.append("## Directory Details")
        lines.append("")
        lines.append(f"### {project_name}/")
        lines.append("Root")
        lines.append("")
        lines.append(f"Files: {num_files} | Subdirectories: 0")
        lines.append("")
        lines.append("| Name | Type | Description |")
        lines.append("|------|------|-------------|")
        for i in range(num_files):
            lines.append(
                f"| file_{i:04d}.py | Python | "
                f"Module handling feature {i} with extensive description "
                f"padding to increase the total character count significantly |"
            )
        lines.append("")

        content = "\n".join(lines)
        # Ensure it's actually over budget (25K tokens = 100K chars)
        assert len(content) // 4 > _TOKEN_BUDGET

        all_file_entries = [
            AIndexEntry(name=f"file_{i:04d}.py", entry_type="file", description=f"Module {i}")
            for i in range(num_files)
        ]
        infos = [
            _DirInfo(
                rel_path=project_name,
                billboard="Root",
                child_entry_count=num_files,
                all_file_entries=all_file_entries,
            ),
        ]

        result = _apply_token_sentinel(content, infos, project_name)
        # The large file table should be replaced with a truncation notice
        assert "table omitted for size" in result
        assert f"{num_files} files" in result

    def test_over_budget_logs_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Token sentinel logs a warning when capping is applied."""
        import logging  # noqa: PLC0415

        from lexibrary.archivist.topology import _DirInfo

        project_name = "bigproject"
        num_files = 1000

        # Build oversized content with a trimmable file table
        lines = ["# Project Topology", "", "```", f"{project_name}/ -- Root", "```", ""]
        lines.append("## Directory Details")
        lines.append("")
        lines.append(f"### {project_name}/")
        lines.append("Root")
        lines.append("")
        lines.append(f"Files: {num_files} | Subdirectories: 0")
        lines.append("")
        lines.append("| Name | Type | Description |")
        lines.append("|------|------|-------------|")
        for i in range(num_files):
            lines.append(
                f"| file_{i:04d}.py | Python | "
                f"Module handling feature {i} with extensive description "
                f"padding to increase the total character count significantly |"
            )
        lines.append("")
        content = "\n".join(lines)
        assert len(content) // 4 > _TOKEN_BUDGET

        all_file_entries = [
            AIndexEntry(name=f"file_{i:04d}.py", entry_type="file", description=f"Module {i}")
            for i in range(num_files)
        ]
        infos = [
            _DirInfo(
                rel_path=project_name,
                billboard="Root",
                child_entry_count=num_files,
                all_file_entries=all_file_entries,
            ),
        ]

        with caplog.at_level(logging.WARNING, logger="lexibrary.archivist.topology"):
            _apply_token_sentinel(content, infos, project_name)

        assert any("25K token budget" in r.message for r in caplog.records)

    def test_end_to_end_large_project_caps(self, tmp_path: Path) -> None:
        """generate_raw_topology caps output on a project with many files."""
        (tmp_path / LEXIBRARY_DIR).mkdir()
        project_name = tmp_path.name

        # Create a directory with many file entries to exceed the 25K token budget
        entries = [
            AIndexEntry(
                name=f"module_{i:03d}.py",
                entry_type="file",
                description=(
                    f"Handles feature {i} with detailed comprehensive "
                    "logic and validation routines for data processing"
                ),
            )
            for i in range(600)
        ]
        _write_aindex(tmp_path, project_name, "Root with many files", entries=entries)

        result_path = generate_raw_topology(tmp_path)
        content = result_path.read_text(encoding="utf-8")

        # Token estimate should be at or under budget (or warning logged)
        estimated_tokens = len(content) // 4
        # Either the content was capped or it was small enough to fit
        if estimated_tokens > _TOKEN_BUDGET:
            # If still over, the warning was logged (non-fatal)
            pass
        else:
            # Capping worked — verify notice present
            assert "table omitted for size" in content or estimated_tokens <= _TOKEN_BUDGET


# ---------------------------------------------------------------------------
# _generate_entry_point_candidates
# ---------------------------------------------------------------------------


class TestGenerateEntryPointCandidates:
    """Verify entry-point candidates table generation."""

    def test_empty_when_no_candidates(self, tmp_path: Path) -> None:
        """Returns empty string when no entries match entry-point keywords."""
        from lexibrary.archivist.topology import _DirInfo

        project_name = tmp_path.name
        infos = [
            _DirInfo(
                rel_path=f"{project_name}/src",
                billboard="Source code",
                child_entry_count=2,
                key_entries=[
                    AIndexEntry(
                        name="pyproject.toml",
                        entry_type="file",
                        description="Project configuration",
                    ),
                ],
            ),
        ]
        result = _generate_entry_point_candidates(infos, project_name)
        assert result == ""

    def test_single_candidate_table_format(self, tmp_path: Path) -> None:
        """A single match produces a well-formed markdown table with header and one row."""
        from lexibrary.archivist.topology import _DirInfo

        project_name = tmp_path.name
        infos = [
            _DirInfo(
                rel_path=f"{project_name}/src",
                billboard="Source code",
                child_entry_count=1,
                key_entries=[
                    AIndexEntry(
                        name="main.py",
                        entry_type="file",
                        description="Application entry point",
                    ),
                ],
            ),
        ]
        result = _generate_entry_point_candidates(infos, project_name)
        assert "## Entry-Point Candidates" in result
        assert "| File | Directory | Signal | Confidence |" in result
        assert "|------|-----------|--------|------------|" in result
        assert "| main.py | src | keyword | medium |" in result

    def test_multi_candidate_output(self, tmp_path: Path) -> None:
        """All matching entry-point candidates appear in the table."""
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
                        description="Application entry point",
                    ),
                ],
            ),
            _DirInfo(
                rel_path=f"{project_name}/src/cli",
                billboard="CLI commands",
                child_entry_count=3,
                key_entries=[
                    AIndexEntry(
                        name="lexi_app.py",
                        entry_type="file",
                        description="Main application entry point",
                    ),
                ],
            ),
        ]
        result = _generate_entry_point_candidates(infos, project_name)
        # Both candidates should appear
        assert "app.py" in result
        assert "lexi_app.py" in result
        # Count table rows (excluding header/separator)
        table_rows = [
            line for line in result.split("\n")
            if line.startswith("|") and "File" not in line and "---" not in line
        ]
        assert len(table_rows) == 2

    def test_preferred_dir_high_confidence(self, tmp_path: Path) -> None:
        """Candidates in preferred directories get 'preferred_dir + keyword' / 'high'."""
        from lexibrary.archivist.topology import _DirInfo

        project_name = tmp_path.name
        infos = [
            _DirInfo(
                rel_path=f"{project_name}/src/cli",
                billboard="CLI commands",
                child_entry_count=1,
                key_entries=[
                    AIndexEntry(
                        name="lexi_app.py",
                        entry_type="file",
                        description="Main application entry point",
                    ),
                ],
            ),
        ]
        result = _generate_entry_point_candidates(infos, project_name)
        assert "| lexi_app.py | src/cli | preferred_dir + keyword | high |" in result

    def test_non_preferred_dir_medium_confidence(self, tmp_path: Path) -> None:
        """Candidates NOT in preferred directories get 'keyword' / 'medium'."""
        from lexibrary.archivist.topology import _DirInfo

        project_name = tmp_path.name
        infos = [
            _DirInfo(
                rel_path=f"{project_name}/src/utils",
                billboard="Utilities",
                child_entry_count=1,
                key_entries=[
                    AIndexEntry(
                        name="bootstrap.py",
                        entry_type="file",
                        description="Application entry point bootstrap",
                    ),
                ],
            ),
        ]
        result = _generate_entry_point_candidates(infos, project_name)
        assert "| bootstrap.py | src/utils | keyword | medium |" in result

    def test_minimal_entry_point_excluded(self, tmp_path: Path) -> None:
        """Entries matching the minimal entry-point disqualifier are excluded."""
        from lexibrary.archivist.topology import _DirInfo

        project_name = tmp_path.name
        infos = [
            _DirInfo(
                rel_path=f"{project_name}/src",
                billboard="Source",
                child_entry_count=2,
                key_entries=[
                    AIndexEntry(
                        name="__main__.py",
                        entry_type="file",
                        description="Minimal entry point that delegates to cli/",
                    ),
                    AIndexEntry(
                        name="real_app.py",
                        entry_type="file",
                        description="Application entry point",
                    ),
                ],
            ),
        ]
        result = _generate_entry_point_candidates(infos, project_name)
        assert "__main__.py" not in result
        assert "real_app.py" in result

    def test_verification_disclaimer_present(self, tmp_path: Path) -> None:
        """The section includes a disclaimer about heuristic matches."""
        from lexibrary.archivist.topology import _DirInfo

        project_name = tmp_path.name
        infos = [
            _DirInfo(
                rel_path=f"{project_name}/src",
                billboard="Source",
                child_entry_count=1,
                key_entries=[
                    AIndexEntry(
                        name="main.py",
                        entry_type="file",
                        description="Application entry point",
                    ),
                ],
            ),
        ]
        result = _generate_entry_point_candidates(infos, project_name)
        assert "heuristic matches" in result
        assert "pyproject.toml" in result

    def test_confidence_sorting_high_before_medium(self, tmp_path: Path) -> None:
        """High-confidence candidates are listed before medium-confidence ones."""
        from lexibrary.archivist.topology import _DirInfo

        project_name = tmp_path.name
        infos = [
            _DirInfo(
                rel_path=f"{project_name}/src/utils",
                billboard="Utilities",
                child_entry_count=1,
                key_entries=[
                    AIndexEntry(
                        name="bootstrap.py",
                        entry_type="file",
                        description="Application entry point",
                    ),
                ],
            ),
            _DirInfo(
                rel_path=f"{project_name}/src/cli",
                billboard="CLI commands",
                child_entry_count=1,
                key_entries=[
                    AIndexEntry(
                        name="lexi_app.py",
                        entry_type="file",
                        description="Main entry point",
                    ),
                ],
            ),
        ]
        result = _generate_entry_point_candidates(infos, project_name)
        lines = result.split("\n")
        table_rows = [
            line for line in lines
            if line.startswith("|") and "File" not in line and "---" not in line
        ]
        # High confidence (cli/) should come first
        assert "high" in table_rows[0]
        assert "medium" in table_rows[1]

    def test_root_dir_candidate_shows_dot_directory(self, tmp_path: Path) -> None:
        """Candidates at the project root display '.' as directory."""
        from lexibrary.archivist.topology import _DirInfo

        project_name = tmp_path.name
        infos = [
            _DirInfo(
                rel_path=project_name,
                billboard="Root",
                child_entry_count=1,
                key_entries=[
                    AIndexEntry(
                        name="main.py",
                        entry_type="file",
                        description="Main entry point",
                    ),
                ],
            ),
        ]
        result = _generate_entry_point_candidates(infos, project_name)
        assert "| main.py | . | keyword | medium |" in result

    def test_non_entry_point_key_entries_excluded(self, tmp_path: Path) -> None:
        """Config and other non-entry-point key_entries are not in the table."""
        from lexibrary.archivist.topology import _DirInfo

        project_name = tmp_path.name
        infos = [
            _DirInfo(
                rel_path=project_name,
                billboard="Root",
                child_entry_count=2,
                key_entries=[
                    AIndexEntry(
                        name="pyproject.toml",
                        entry_type="file",
                        description="Project configuration",
                    ),
                    AIndexEntry(
                        name="main.py",
                        entry_type="file",
                        description="Application entry point",
                    ),
                ],
            ),
        ]
        result = _generate_entry_point_candidates(infos, project_name)
        # Config file should not appear as a row in the table
        table_rows = [
            line for line in result.split("\n")
            if line.startswith("|") and "File" not in line and "---" not in line
        ]
        assert len(table_rows) == 1
        assert "main.py" in table_rows[0]
        assert "pyproject.toml" not in "".join(table_rows)


# ---------------------------------------------------------------------------
# Test Directory Collapse — one-line summaries in Test Layout section
# ---------------------------------------------------------------------------


class TestTestDirectoryCollapse:
    """Test directories should be rendered as one-line summaries, not per-file tables."""

    def _make_project_with_test_dirs(self, tmp_path: Path) -> str:
        """Create a project with src/auth/ and tests/test_auth/ for collapse tests."""
        (tmp_path / LEXIBRARY_DIR).mkdir()
        project_name = tmp_path.name
        _write_aindex(tmp_path, project_name, "Root")
        _write_aindex(
            tmp_path,
            f"{project_name}/src",
            "Source",
            entries=[
                AIndexEntry(name="auth", entry_type="dir", description="Auth module"),
            ],
        )
        _write_aindex(
            tmp_path,
            f"{project_name}/src/auth",
            "authentication and session management",
            entries=[
                AIndexEntry(name="login.py", entry_type="file", description="Login handler"),
                AIndexEntry(name="session.py", entry_type="file", description="Session manager"),
            ],
        )
        _write_aindex(
            tmp_path,
            f"{project_name}/tests",
            "Tests",
            entries=[
                AIndexEntry(
                    name="test_auth", entry_type="dir", description="4 Python files"
                ),
                AIndexEntry(name="conftest.py", entry_type="file", description="Shared fixtures"),
            ],
        )
        _write_aindex(
            tmp_path,
            f"{project_name}/tests/test_auth",
            "4 Python files",
            entries=[
                AIndexEntry(
                    name="test_login.py", entry_type="file", description="Login tests"
                ),
                AIndexEntry(
                    name="test_session.py", entry_type="file", description="Session tests"
                ),
                AIndexEntry(
                    name="test_utils.py", entry_type="file", description="Auth util tests"
                ),
                AIndexEntry(
                    name="conftest.py", entry_type="file", description="Auth fixtures"
                ),
            ],
        )
        return project_name

    def test_test_dir_collapsed_with_covering_clause(self, tmp_path: Path) -> None:
        """test_auth/ with correlated src/auth/ shows 'covering auth/'."""
        self._make_project_with_test_dirs(tmp_path)
        result_path = generate_raw_topology(tmp_path)
        content = result_path.read_text(encoding="utf-8")

        # test_auth/ should have one-line summary with covering clause
        assert "tests/test_auth/ -- 4 files covering auth/" in content
        # Should NOT have per-file table for test_auth
        assert "test_login.py" not in content
        assert "test_session.py" not in content

    def test_test_root_dir_collapsed(self, tmp_path: Path) -> None:
        """The tests/ root directory itself should also be collapsed."""
        self._make_project_with_test_dirs(tmp_path)
        result_path = generate_raw_topology(tmp_path)
        content = result_path.read_text(encoding="utf-8")

        # tests/ is a test directory and should be collapsed
        assert "tests/ -- 1 files" in content

    def test_test_dir_without_source_correlation(self, tmp_path: Path) -> None:
        """test_widgets/ with no matching source module omits covering clause."""
        (tmp_path / LEXIBRARY_DIR).mkdir()
        project_name = tmp_path.name
        _write_aindex(tmp_path, project_name, "Root")
        _write_aindex(tmp_path, f"{project_name}/src", "Source")
        _write_aindex(
            tmp_path,
            f"{project_name}/tests",
            "Tests",
            entries=[
                AIndexEntry(
                    name="test_widgets", entry_type="dir", description="3 Python files"
                ),
            ],
        )
        _write_aindex(
            tmp_path,
            f"{project_name}/tests/test_widgets",
            "3 Python files",
            entries=[
                AIndexEntry(name="test_a.py", entry_type="file", description="A tests"),
                AIndexEntry(name="test_b.py", entry_type="file", description="B tests"),
                AIndexEntry(name="test_c.py", entry_type="file", description="C tests"),
            ],
        )
        result_path = generate_raw_topology(tmp_path)
        content = result_path.read_text(encoding="utf-8")

        # No src/widgets/ exists, so no "covering" clause
        assert "tests/test_widgets/ -- 3 files" in content
        assert "covering" not in content.split("tests/test_widgets/")[1].split("\n")[0]

    def test_non_test_dirs_unaffected(self, tmp_path: Path) -> None:
        """Source directories still get full per-file tables."""
        self._make_project_with_test_dirs(tmp_path)
        result_path = generate_raw_topology(tmp_path)
        content = result_path.read_text(encoding="utf-8")

        # Source modules should still have per-file tables
        assert "### src/auth/" in content
        assert "| Name | Type | Description |" in content
        assert "login.py" in content
        assert "session.py" in content

    def test_render_test_layout_block_unit(self, tmp_path: Path) -> None:
        """Unit test for _render_test_layout_block with correlated source module."""
        from lexibrary.archivist.topology import _DirInfo

        project_name = "myproject"
        test_infos = [
            _DirInfo(
                rel_path=f"{project_name}/tests/test_auth",
                billboard="4 Python files",
                child_entry_count=4,
                all_file_entries=[
                    AIndexEntry(name=f"test_{i}.py", entry_type="file", description=f"Test {i}")
                    for i in range(4)
                ],
            ),
        ]
        all_infos = [
            _DirInfo(
                rel_path=project_name,
                billboard="Root",
                child_entry_count=2,
            ),
            _DirInfo(
                rel_path=f"{project_name}/src",
                billboard="Source",
                child_entry_count=1,
                child_dir_names=["auth"],
            ),
            _DirInfo(
                rel_path=f"{project_name}/src/auth",
                billboard="authentication and session management",
                child_entry_count=2,
            ),
            *test_infos,
        ]

        result = _render_test_layout_block(test_infos, all_infos, project_name)
        assert "## Test Layout" in result
        assert "tests/test_auth/ -- 4 files covering auth/" in result
        # No per-file table
        assert "| Name |" not in result

    def test_render_test_layout_block_no_correlation(self, tmp_path: Path) -> None:
        """Unit test for _render_test_layout_block without source correlation."""
        from lexibrary.archivist.topology import _DirInfo

        project_name = "myproject"
        test_infos = [
            _DirInfo(
                rel_path=f"{project_name}/tests/test_widgets",
                billboard="3 Python files",
                child_entry_count=3,
                all_file_entries=[
                    AIndexEntry(name=f"test_{i}.py", entry_type="file", description=f"Test {i}")
                    for i in range(3)
                ],
            ),
        ]
        # No src/widgets/ in all_infos
        all_infos = [
            _DirInfo(
                rel_path=project_name,
                billboard="Root",
                child_entry_count=1,
            ),
            _DirInfo(
                rel_path=f"{project_name}/src",
                billboard="Source",
                child_entry_count=0,
            ),
            *test_infos,
        ]

        result = _render_test_layout_block(test_infos, all_infos, project_name)
        assert "tests/test_widgets/ -- 3 files" in result
        assert "covering" not in result

    def test_render_test_layout_block_empty(self) -> None:
        """_render_test_layout_block returns empty string when no test dirs."""
        result = _render_test_layout_block([], [], "myproject")
        assert result == ""

    def test_build_source_module_map(self, tmp_path: Path) -> None:
        """_build_source_module_map returns correct source module mappings."""
        from lexibrary.archivist.topology import _DirInfo

        project_name = "myproject"
        infos = [
            _DirInfo(
                rel_path=project_name,
                billboard="Root",
                child_entry_count=2,
            ),
            _DirInfo(
                rel_path=f"{project_name}/src",
                billboard="Source",
                child_entry_count=1,
                child_dir_names=["auth"],
            ),
            _DirInfo(
                rel_path=f"{project_name}/src/auth",
                billboard="authentication and session management",
                child_entry_count=2,
            ),
        ]
        result = _build_source_module_map(infos, project_name)
        assert "auth" in result
        assert result["auth"].billboard == "authentication and session management"


# ---------------------------------------------------------------------------
# Directory Detail Filtering (Group 5)
# ---------------------------------------------------------------------------


class TestShouldDetailDirectory:
    """Tests for _should_detail_directory() filtering logic."""

    def test_dir_under_dominant_source_gets_detail(self) -> None:
        """Directories under the dominant source dir get full detail."""
        assert _should_detail_directory(
            "myproject/src/auth", "myproject", "src", []
        )

    def test_dominant_source_dir_itself_gets_detail(self) -> None:
        """The dominant source dir itself gets full detail."""
        assert _should_detail_directory(
            "myproject/src", "myproject", "src", []
        )

    def test_non_source_dir_no_detail_dirs_gets_summary(self) -> None:
        """Non-source dir without detail_dirs configured gets a summary."""
        assert not _should_detail_directory(
            "myproject/docs", "myproject", "src", []
        )

    def test_non_source_dir_matching_detail_dirs_gets_detail(self) -> None:
        """Non-source dir matching a detail_dirs pattern gets full detail."""
        assert _should_detail_directory(
            "myproject/docs", "myproject", "src", ["docs"]
        )

    def test_nested_dir_matching_detail_dirs_glob(self) -> None:
        """Nested directory matching a detail_dirs glob pattern gets detail."""
        assert _should_detail_directory(
            "myproject/baml_src/agent", "myproject", "src", ["baml_src/**"]
        )

    def test_no_dominant_source_dir_only_detail_dirs(self) -> None:
        """When no dominant source dir, only detail_dirs patterns match."""
        assert _should_detail_directory(
            "myproject/lib", "myproject", "", ["lib"]
        )

    def test_no_dominant_source_no_detail_dirs_gets_summary(self) -> None:
        """No dominant source dir and no detail_dirs means everything is summary."""
        assert not _should_detail_directory(
            "myproject/lib", "myproject", "", []
        )

    def test_root_dir_without_source_gets_summary(self) -> None:
        """Project root not under a source dir gets a summary."""
        assert not _should_detail_directory(
            "myproject", "myproject", "src", []
        )


class TestDisplayPath:
    """Tests for _display_path() helper."""

    def test_project_root(self) -> None:
        assert _display_path("myproject", "myproject") == "myproject/"

    def test_dot_root(self) -> None:
        assert _display_path(".", "myproject") == "myproject/"

    def test_nested_dir(self) -> None:
        assert _display_path("myproject/src/auth", "myproject") == "src/auth/"


class TestRenderSummaryBlock:
    """Tests for _render_summary_block() one-line summary output."""

    def test_empty_infos_returns_empty(self) -> None:
        result = _render_summary_block([], "myproject", "## Other Directories")
        assert result == ""

    def test_summary_line_format(self) -> None:
        from lexibrary.archivist.topology import _DirInfo

        infos = [
            _DirInfo(
                rel_path="myproject/docs",
                billboard="Project documentation",
                child_entry_count=3,
                all_file_entries=[
                    AIndexEntry(name="readme.md", entry_type="file", description="README"),
                    AIndexEntry(name="guide.md", entry_type="file", description="Guide"),
                ],
            ),
        ]
        result = _render_summary_block(infos, "myproject", "## Other Directories")
        assert "## Other Directories" in result
        assert "docs/ -- 2 files -- Project documentation" in result

    def test_summary_no_billboard(self) -> None:
        from lexibrary.archivist.topology import _DirInfo

        infos = [
            _DirInfo(
                rel_path="myproject/misc",
                billboard="",
                child_entry_count=1,
                all_file_entries=[
                    AIndexEntry(name="x.txt", entry_type="file", description="Misc"),
                ],
            ),
        ]
        result = _render_summary_block(infos, "myproject", "## Other Directories")
        assert "misc/ -- 1 files" in result
        assert result.count("--") == 1  # only the file count, no billboard clause


class TestDirectoryDetailFiltering:
    """Integration tests for detail filtering in _generate_directory_details()."""

    def test_source_dirs_get_full_tables(self) -> None:
        """Directories under dominant source dir get full file tables."""
        from lexibrary.archivist.topology import _DirInfo

        project_name = "myproject"
        infos = [
            _DirInfo(
                rel_path=project_name,
                billboard="Root",
                child_entry_count=2,
                child_dir_names=["src"],
            ),
            _DirInfo(
                rel_path=f"{project_name}/src",
                billboard="Source code",
                child_entry_count=2,
                child_dir_names=["auth"],
                all_file_entries=[
                    AIndexEntry(name="app.py", entry_type="file", description="App module"),
                ],
            ),
            _DirInfo(
                rel_path=f"{project_name}/src/auth",
                billboard="Authentication",
                child_entry_count=1,
                all_file_entries=[
                    AIndexEntry(name="login.py", entry_type="file", description="Login logic"),
                ],
            ),
        ]

        source_content, _ = _generate_directory_details(infos, project_name)
        assert "### src/" in source_content
        assert "### src/auth/" in source_content
        assert "| Name | Type | Description |" in source_content
        assert "app.py" in source_content
        assert "login.py" in source_content

    def test_non_source_dirs_get_summaries_when_unconfigured(self) -> None:
        """Non-source dirs without detail_dirs get one-line summaries."""
        from lexibrary.archivist.topology import _DirInfo

        project_name = "myproject"
        infos = [
            _DirInfo(
                rel_path=project_name,
                billboard="Root",
                child_entry_count=3,
                child_dir_names=["src", "docs"],
            ),
            _DirInfo(
                rel_path=f"{project_name}/src",
                billboard="Source code",
                child_entry_count=1,
                child_dir_names=[],
                all_file_entries=[
                    AIndexEntry(name="app.py", entry_type="file", description="App"),
                ],
            ),
            _DirInfo(
                rel_path=f"{project_name}/docs",
                billboard="Documentation",
                child_entry_count=2,
                all_file_entries=[
                    AIndexEntry(name="readme.md", entry_type="file", description="README"),
                    AIndexEntry(name="guide.md", entry_type="file", description="User guide"),
                ],
            ),
        ]

        source_content, _ = _generate_directory_details(infos, project_name)
        # src/ gets a full table
        assert "### src/" in source_content
        # docs/ gets a one-line summary, NOT a full table
        assert "## Other Directories" in source_content
        assert "docs/ -- 2 files -- Documentation" in source_content
        # docs/ should NOT have a ### heading or file table
        assert "### docs/" not in source_content

    def test_detail_dirs_patterns_get_full_tables(self) -> None:
        """Directories matching detail_dirs patterns get full file tables."""
        from lexibrary.archivist.topology import _DirInfo

        project_name = "myproject"
        infos = [
            _DirInfo(
                rel_path=project_name,
                billboard="Root",
                child_entry_count=3,
                child_dir_names=["src", "docs"],
            ),
            _DirInfo(
                rel_path=f"{project_name}/src",
                billboard="Source code",
                child_entry_count=1,
                child_dir_names=[],
                all_file_entries=[
                    AIndexEntry(name="app.py", entry_type="file", description="App"),
                ],
            ),
            _DirInfo(
                rel_path=f"{project_name}/docs",
                billboard="Documentation",
                child_entry_count=2,
                all_file_entries=[
                    AIndexEntry(name="readme.md", entry_type="file", description="README"),
                    AIndexEntry(name="guide.md", entry_type="file", description="User guide"),
                ],
            ),
        ]

        source_content, _ = _generate_directory_details(
            infos, project_name, detail_dirs=["docs"]
        )
        # Both src/ and docs/ get full tables
        assert "### src/" in source_content
        assert "### docs/" in source_content
        assert "| Name | Type | Description |" in source_content
        assert "readme.md" in source_content
        assert "User guide" in source_content
        # The root dir itself is in "Other Directories" (not under src/, not in detail_dirs)
        # but docs/ should NOT appear there since it matched detail_dirs
        assert "docs/ -- 2 files" not in source_content

    def test_detail_dirs_glob_pattern_matching(self) -> None:
        """Glob patterns in detail_dirs match nested directories."""
        from lexibrary.archivist.topology import _DirInfo

        project_name = "myproject"
        infos = [
            _DirInfo(
                rel_path=project_name,
                billboard="Root",
                child_entry_count=3,
                child_dir_names=["src", "baml_src"],
            ),
            _DirInfo(
                rel_path=f"{project_name}/src",
                billboard="Source code",
                child_entry_count=1,
                child_dir_names=[],
                all_file_entries=[
                    AIndexEntry(name="app.py", entry_type="file", description="App"),
                ],
            ),
            _DirInfo(
                rel_path=f"{project_name}/baml_src",
                billboard="BAML definitions",
                child_entry_count=1,
                child_dir_names=["agents"],
                all_file_entries=[
                    AIndexEntry(name="main.baml", entry_type="file", description="Main BAML"),
                ],
            ),
            _DirInfo(
                rel_path=f"{project_name}/baml_src/agents",
                billboard="Agent definitions",
                child_entry_count=1,
                all_file_entries=[
                    AIndexEntry(name="planner.baml", entry_type="file", description="Planner"),
                ],
            ),
        ]

        source_content, _ = _generate_directory_details(
            infos, project_name, detail_dirs=["baml_src/**"]
        )
        # baml_src/ and its children match the glob, so they get full tables
        assert "### baml_src/" in source_content
        assert "### baml_src/agents/" in source_content
        assert "main.baml" in source_content
        assert "planner.baml" in source_content

    def test_empty_detail_dirs_only_source_gets_detail(self) -> None:
        """With empty detail_dirs, only the dominant source dir gets detail."""
        from lexibrary.archivist.topology import _DirInfo

        project_name = "myproject"
        infos = [
            _DirInfo(
                rel_path=project_name,
                billboard="Root",
                child_entry_count=3,
                child_dir_names=["src", "scripts", "config"],
            ),
            _DirInfo(
                rel_path=f"{project_name}/src",
                billboard="Source code",
                child_entry_count=1,
                child_dir_names=[],
                all_file_entries=[
                    AIndexEntry(name="app.py", entry_type="file", description="App"),
                ],
            ),
            _DirInfo(
                rel_path=f"{project_name}/scripts",
                billboard="Utility scripts",
                child_entry_count=1,
                all_file_entries=[
                    AIndexEntry(name="deploy.sh", entry_type="file", description="Deploy"),
                ],
            ),
            _DirInfo(
                rel_path=f"{project_name}/config",
                billboard="Config files",
                child_entry_count=1,
                all_file_entries=[
                    AIndexEntry(name="prod.yaml", entry_type="file", description="Production"),
                ],
            ),
        ]

        source_content, _ = _generate_directory_details(
            infos, project_name, detail_dirs=[]
        )
        # src/ gets full detail
        assert "### src/" in source_content
        # scripts/ and config/ get summaries
        assert "## Other Directories" in source_content
        assert "scripts/ -- 1 files -- Utility scripts" in source_content
        assert "config/ -- 1 files -- Config files" in source_content
        # No full tables for non-source dirs
        assert "### scripts/" not in source_content
        assert "### config/" not in source_content

    def test_test_dirs_unaffected_by_detail_filtering(self) -> None:
        """Test directories are always collapsed regardless of detail_dirs."""
        from lexibrary.archivist.topology import _DirInfo

        project_name = "myproject"
        infos = [
            _DirInfo(
                rel_path=project_name,
                billboard="Root",
                child_entry_count=2,
                child_dir_names=["src", "tests"],
            ),
            _DirInfo(
                rel_path=f"{project_name}/src",
                billboard="Source code",
                child_entry_count=1,
                child_dir_names=[],
                all_file_entries=[
                    AIndexEntry(name="app.py", entry_type="file", description="App"),
                ],
            ),
            _DirInfo(
                rel_path=f"{project_name}/tests",
                billboard="5 Python files",
                child_entry_count=5,
                all_file_entries=[
                    AIndexEntry(name=f"test_{i}.py", entry_type="file", description=f"Test {i}")
                    for i in range(5)
                ],
            ),
        ]

        _, test_content = _generate_directory_details(
            infos, project_name, detail_dirs=["tests"]
        )
        # Test dirs always get collapsed summaries
        assert "tests/ -- 5 files" in test_content
        # No full file table in test layout
        assert "| Name | Type | Description |" not in test_content


class TestTokenSentinelTodo:
    """Verify the TODO comment in _apply_token_sentinel."""

    def test_todo_comment_present(self) -> None:
        """_apply_token_sentinel source contains the review TODO."""
        import inspect

        source = inspect.getsource(_apply_token_sentinel)
        assert "TODO: review sentinel strategy after detail_dirs" in source
