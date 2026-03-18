"""Tests for archivist skeleton generation helper."""

from __future__ import annotations

from pathlib import Path

from lexibrary.archivist.skeleton import (
    generate_skeleton_design,
    heuristic_description,
)
from lexibrary.artifacts.design_file import DesignFile

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_source_file(
    tmp_path: Path, rel: str, content: str = "print('hello')"
) -> Path:
    """Create a source file at the given relative path."""
    source = tmp_path / rel
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(content, encoding="utf-8")
    return source


# ---------------------------------------------------------------------------
# Tests: heuristic_description
# ---------------------------------------------------------------------------


class TestHeuristicDescription:
    """Tests for the heuristic_description function."""

    def test_uses_module_docstring(self, tmp_path: Path) -> None:
        source = _make_source_file(
            tmp_path,
            "src/example.py",
            '"""Module that does something useful."""\n\nx = 1\n',
        )
        desc = heuristic_description(source)
        assert desc == "Module that does something useful."

    def test_uses_first_line_of_multiline_docstring(self, tmp_path: Path) -> None:
        source = _make_source_file(
            tmp_path,
            "src/multi.py",
            '"""First line.\n\nMore details here.\n"""\n',
        )
        desc = heuristic_description(source)
        assert desc == "First line."

    def test_init_file(self, tmp_path: Path) -> None:
        source = _make_source_file(tmp_path, "src/mypackage/__init__.py", "")
        desc = heuristic_description(source)
        assert desc == "Package initializer for mypackage"

    def test_main_file(self, tmp_path: Path) -> None:
        source = _make_source_file(tmp_path, "src/mypackage/__main__.py", "")
        desc = heuristic_description(source)
        assert desc == "Entry point for mypackage"

    def test_snake_case_filename(self, tmp_path: Path) -> None:
        source = _make_source_file(tmp_path, "src/my_module.py", "x = 1\n")
        desc = heuristic_description(source)
        assert desc == "Design file for my module"

    def test_non_python_file(self, tmp_path: Path) -> None:
        source = _make_source_file(tmp_path, "config.yaml", "key: value\n")
        desc = heuristic_description(source)
        assert desc == "Design file for config"


# ---------------------------------------------------------------------------
# Tests: generate_skeleton_design
# ---------------------------------------------------------------------------


class TestGenerateSkeletonDesign:
    """Tests for the generate_skeleton_design function."""

    def test_returns_design_file_model(self, tmp_path: Path) -> None:
        source = _make_source_file(tmp_path, "src/example.py", "x = 1\n")
        result = generate_skeleton_design(source, tmp_path)
        assert isinstance(result, DesignFile)

    def test_default_updated_by_is_skeleton_fallback(self, tmp_path: Path) -> None:
        source = _make_source_file(tmp_path, "src/example.py", "x = 1\n")
        result = generate_skeleton_design(source, tmp_path)
        assert result.frontmatter.updated_by == "skeleton-fallback"

    def test_custom_updated_by(self, tmp_path: Path) -> None:
        source = _make_source_file(tmp_path, "src/example.py", "x = 1\n")
        result = generate_skeleton_design(
            source, tmp_path, updated_by="bootstrap-quick"
        )
        assert result.frontmatter.updated_by == "bootstrap-quick"

    def test_source_path_is_relative(self, tmp_path: Path) -> None:
        source = _make_source_file(tmp_path, "src/example.py", "x = 1\n")
        result = generate_skeleton_design(source, tmp_path)
        assert result.source_path == "src/example.py"

    def test_metadata_has_hashes(self, tmp_path: Path) -> None:
        source = _make_source_file(tmp_path, "src/example.py", "x = 1\n")
        result = generate_skeleton_design(source, tmp_path)
        assert result.metadata.source_hash != ""
        assert result.metadata.source == "src/example.py"
        assert result.metadata.generator == "lexibrary-v2"

    def test_interface_extraction_for_python(self, tmp_path: Path) -> None:
        content = (
            "from __future__ import annotations\n\n"
            "class MyClass:\n"
            '    """A test class."""\n\n'
            "    def method(self, x: int) -> str:\n"
            '        return "hello"\n'
        )
        source = _make_source_file(tmp_path, "src/example.py", content)
        result = generate_skeleton_design(source, tmp_path)
        # Tree-sitter should extract the class and method
        assert "MyClass" in result.interface_contract

    def test_non_code_file_has_no_interface(self, tmp_path: Path) -> None:
        source = _make_source_file(tmp_path, "config.yaml", "key: value\n")
        result = generate_skeleton_design(source, tmp_path)
        # YAML files don't have tree-sitter parsers, so interface should be empty
        assert result.interface_contract == ""

    def test_summary_suffix_appended(self, tmp_path: Path) -> None:
        source = _make_source_file(tmp_path, "src/example.py", "x = 1\n")
        suffix = " -- source too large (~5000 tokens)"
        result = generate_skeleton_design(
            source, tmp_path, summary_suffix=suffix
        )
        assert result.summary.endswith(suffix)
        # Description in frontmatter should NOT have the suffix
        assert not result.frontmatter.description.endswith(suffix)

    def test_summary_without_suffix(self, tmp_path: Path) -> None:
        source = _make_source_file(
            tmp_path,
            "src/example.py",
            '"""My module."""\nx = 1\n',
        )
        result = generate_skeleton_design(source, tmp_path)
        # Summary should equal the description when no suffix
        assert result.summary == result.frontmatter.description

    def test_dependencies_extracted(self, tmp_path: Path) -> None:
        content = (
            "from __future__ import annotations\n\n"
            "from pathlib import Path\n\n"
            "x = 1\n"
        )
        source = _make_source_file(tmp_path, "src/example.py", content)
        result = generate_skeleton_design(source, tmp_path)
        # dependencies is a list (may be empty if no local deps found)
        assert isinstance(result.dependencies, list)

    def test_dependents_is_empty(self, tmp_path: Path) -> None:
        source = _make_source_file(tmp_path, "src/example.py", "x = 1\n")
        result = generate_skeleton_design(source, tmp_path)
        assert result.dependents == []
