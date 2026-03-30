"""Tests for the index generator."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path

import pathspec
import pytest

from lexibrary.artifacts.aindex import AIndexEntry, AIndexFile
from lexibrary.artifacts.aindex_serializer import serialize_aindex
from lexibrary.artifacts.design_file import StalenessMetadata
from lexibrary.ignore.matcher import IgnoreMatcher
from lexibrary.indexer.generator import (
    _TRAILING_STRIP,
    _candidate_fragments,
    _extension_based_summary,
    _extract_role_fragment,
    _generate_billboard,
    _get_dir_description,
    _synthesize_summary,
    generate_aindex,
    is_structural_description,
)

_BINARY_EXTS: set[str] = {".png", ".jpg", ".gif", ".pdf", ".exe", ".zip"}


def _matcher(root: Path, patterns: list[str] | None = None) -> IgnoreMatcher:
    """Build an IgnoreMatcher with optional config patterns and no gitignore specs."""
    spec = pathspec.PathSpec.from_lines("gitignore", patterns or [])
    return IgnoreMatcher(root=root, config_spec=spec, gitignore_specs=[])


class TestGenerateAIndexEmptyDir:
    def test_empty_dir_returns_empty_entries(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        result = generate_aindex(src, tmp_path, _matcher(tmp_path), _BINARY_EXTS)
        assert result.entries == []

    def test_empty_dir_billboard(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        result = generate_aindex(src, tmp_path, _matcher(tmp_path), _BINARY_EXTS)
        assert result.billboard == "Empty directory."

    def test_empty_dir_has_no_local_conventions_field(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        result = generate_aindex(src, tmp_path, _matcher(tmp_path), _BINARY_EXTS)
        assert not hasattr(result, "local_conventions")


class TestGenerateAIndexFiles:
    def test_python_file_description(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "main.py").write_text("line1\nline2\nline3\n", encoding="utf-8")
        result = generate_aindex(src, tmp_path, _matcher(tmp_path), _BINARY_EXTS)
        entry = next(e for e in result.entries if e.name == "main.py")
        assert entry.description == "Python source (3 lines)"
        assert entry.entry_type == "file"

    def test_binary_file_description(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "logo.png").write_bytes(b"\x89PNG")
        result = generate_aindex(src, tmp_path, _matcher(tmp_path), _BINARY_EXTS)
        entry = next(e for e in result.entries if e.name == "logo.png")
        assert entry.description == "Binary file (.png)"

    def test_unknown_extension_description(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "data.xyz").write_text("content", encoding="utf-8")
        result = generate_aindex(src, tmp_path, _matcher(tmp_path), _BINARY_EXTS)
        entry = next(e for e in result.entries if e.name == "data.xyz")
        assert entry.description == "Unknown file type"

    def test_single_language_billboard(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "foo.py").write_text("x\n", encoding="utf-8")
        (src / "bar.py").write_text("y\n", encoding="utf-8")
        result = generate_aindex(src, tmp_path, _matcher(tmp_path), _BINARY_EXTS)
        # Tier 2: extension-based summary (no rich descriptions)
        assert result.billboard == "2 Python files"

    def test_mixed_language_billboard(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "app.py").write_text("x\n", encoding="utf-8")
        (src / "index.js").write_text("y\n", encoding="utf-8")
        result = generate_aindex(src, tmp_path, _matcher(tmp_path), _BINARY_EXTS)
        # Tier 2: mixed extension-based summary
        assert result.billboard.startswith("Mixed:")
        assert "Python" in result.billboard
        assert "JavaScript" in result.billboard

    def test_binary_only_billboard(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "logo.png").write_bytes(b"\x89PNG")
        result = generate_aindex(src, tmp_path, _matcher(tmp_path), _BINARY_EXTS)
        # Tier 3: count fallback (no recognized language extensions)
        assert result.billboard == "1 files"


class TestGenerateAIndexDirectories:
    def test_subdir_without_child_aindex_uses_direct_count(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        utils = src / "utils"
        utils.mkdir()
        (utils / "a.py").write_text("", encoding="utf-8")
        (utils / "b.py").write_text("", encoding="utf-8")
        result = generate_aindex(src, tmp_path, _matcher(tmp_path), _BINARY_EXTS)
        entry = next(e for e in result.entries if e.name == "utils")
        assert entry.entry_type == "dir"
        assert entry.description == "Contains 2 items"

    def test_subdir_with_child_aindex_uses_entry_counts(self, tmp_path: Path) -> None:
        from datetime import datetime

        from lexibrary.artifacts.aindex import AIndexEntry, AIndexFile
        from lexibrary.artifacts.design_file import StalenessMetadata

        src = tmp_path / "src"
        src.mkdir()
        utils = src / "utils"
        utils.mkdir()

        # Build a child .aindex for utils in the .lexibrary mirror
        meta = StalenessMetadata(
            source="src/utils",
            source_hash="abc",
            generated=datetime(2026, 1, 1),
            generator="lexibrary-v2",
        )
        child_model = AIndexFile(
            directory_path="src/utils",
            billboard="Utils.",
            entries=[
                AIndexEntry(name="a.py", entry_type="file", description="Python source (1 lines)"),
                AIndexEntry(name="b.py", entry_type="file", description="Python source (2 lines)"),
                AIndexEntry(name="sub", entry_type="dir", description="Contains 1 items"),
            ],
            metadata=meta,
        )
        mirror_dir = tmp_path / ".lexibrary" / "designs" / "src" / "utils"
        mirror_dir.mkdir(parents=True)
        (mirror_dir / ".aindex").write_text(serialize_aindex(child_model), encoding="utf-8")

        result = generate_aindex(src, tmp_path, _matcher(tmp_path), _BINARY_EXTS)
        entry = next(e for e in result.entries if e.name == "utils")
        # Non-structural billboard "Utils." is used as directory description
        assert entry.description == "Utils."

    def test_subdir_with_files_only_aindex_omits_subdir_count(self, tmp_path: Path) -> None:
        from datetime import datetime

        from lexibrary.artifacts.aindex import AIndexEntry, AIndexFile
        from lexibrary.artifacts.design_file import StalenessMetadata

        src = tmp_path / "src"
        src.mkdir()
        utils = src / "utils"
        utils.mkdir()

        meta = StalenessMetadata(
            source="src/utils",
            source_hash="abc",
            generated=datetime(2026, 1, 1),
            generator="lexibrary-v2",
        )
        child_model = AIndexFile(
            directory_path="src/utils",
            billboard="Utils.",
            entries=[
                AIndexEntry(name="a.py", entry_type="file", description="Python source (1 lines)"),
            ],
            metadata=meta,
        )
        mirror_dir = tmp_path / ".lexibrary" / "designs" / "src" / "utils"
        mirror_dir.mkdir(parents=True)
        (mirror_dir / ".aindex").write_text(serialize_aindex(child_model), encoding="utf-8")

        result = generate_aindex(src, tmp_path, _matcher(tmp_path), _BINARY_EXTS)
        entry = next(e for e in result.entries if e.name == "utils")
        # Non-structural billboard "Utils." is used as directory description
        assert entry.description == "Utils."


class TestGenerateAIndexIgnored:
    def test_ignored_entries_excluded(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "keep.py").write_text("x\n", encoding="utf-8")
        (src / "skip.log").write_text("log\n", encoding="utf-8")
        matcher = _matcher(tmp_path, ["*.log"])
        result = generate_aindex(src, tmp_path, matcher, _BINARY_EXTS)
        names = [e.name for e in result.entries]
        assert "keep.py" in names
        assert "skip.log" not in names

    def test_ignored_dir_excluded(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "main.py").write_text("x\n", encoding="utf-8")
        pycache = src / "__pycache__"
        pycache.mkdir()
        matcher = _matcher(tmp_path, ["__pycache__/"])
        result = generate_aindex(src, tmp_path, matcher, _BINARY_EXTS)
        names = [e.name for e in result.entries]
        assert "__pycache__" not in names


class TestGenerateAIndexMetadata:
    def test_metadata_source_is_relative_path(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        result = generate_aindex(src, tmp_path, _matcher(tmp_path), _BINARY_EXTS)
        assert result.metadata.source == "src"
        assert result.directory_path == "src"

    def test_metadata_source_hash_is_hex(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "foo.py").write_text("x\n", encoding="utf-8")
        result = generate_aindex(src, tmp_path, _matcher(tmp_path), _BINARY_EXTS)
        assert len(result.metadata.source_hash) == 64
        assert all(c in "0123456789abcdef" for c in result.metadata.source_hash)

    def test_metadata_generator(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        result = generate_aindex(src, tmp_path, _matcher(tmp_path), _BINARY_EXTS)
        assert result.metadata.generator == "lexibrary-v2"

    def test_metadata_generated_is_datetime(self, tmp_path: Path) -> None:
        from datetime import datetime

        src = tmp_path / "src"
        src.mkdir()
        result = generate_aindex(src, tmp_path, _matcher(tmp_path), _BINARY_EXTS)
        assert isinstance(result.metadata.generated, datetime)

    def test_source_hash_changes_with_directory_contents(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        r1 = generate_aindex(src, tmp_path, _matcher(tmp_path), _BINARY_EXTS)
        (src / "new.py").write_text("x\n", encoding="utf-8")
        r2 = generate_aindex(src, tmp_path, _matcher(tmp_path), _BINARY_EXTS)
        assert r1.metadata.source_hash != r2.metadata.source_hash


def _create_design_file(tmp_path: Path, rel_source: str, description: str) -> None:
    """Helper: create a minimal design file at the .lexibrary mirror path."""
    design_path = tmp_path / ".lexibrary" / "designs" / (rel_source + ".md")
    design_path.parent.mkdir(parents=True, exist_ok=True)
    frontmatter = (
        "---\n"
        f"description: {description}\n"
        "id: DS-001\n"
        "updated_by: archivist\n"
        "---\n"
        "\n"
        f"# {rel_source}\n"
        "\n"
        "## Interface Contract\n"
        "\n"
        "```python\n"
        "def example() -> None: ...\n"
        "```\n"
        "\n"
        "## Dependencies\n"
        "\n"
        "(none)\n"
        "\n"
        "## Dependents\n"
        "\n"
        "(none)\n"
        "\n"
        "<!-- lexibrary:meta\n"
        f"source: {rel_source}\n"
        "source_hash: abc123\n"
        "design_hash: def456\n"
        "generated: 2026-01-01T00:00:00\n"
        "generator: lexibrary-v2\n"
        "-->\n"
    )
    design_path.write_text(frontmatter, encoding="utf-8")


class TestGenerateAIndexFrontmatterDescription:
    """Tests for design file frontmatter description integration."""

    def test_frontmatter_description_used(self, tmp_path: Path) -> None:
        """File with a design file gets the frontmatter description."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "main.py").write_text("line1\nline2\nline3\n", encoding="utf-8")

        # Create design file with a description
        _create_design_file(tmp_path, "src/main.py", "Entry point for the application")

        result = generate_aindex(src, tmp_path, _matcher(tmp_path), _BINARY_EXTS)
        entry = next(e for e in result.entries if e.name == "main.py")
        assert entry.description == "Entry point for the application"

    def test_structural_fallback_when_no_design_file(self, tmp_path: Path) -> None:
        """File without a design file gets the structural description."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "utils.py").write_text("x\ny\n", encoding="utf-8")

        # No design file created — should fall back to structural
        result = generate_aindex(src, tmp_path, _matcher(tmp_path), _BINARY_EXTS)
        entry = next(e for e in result.entries if e.name == "utils.py")
        assert entry.description == "Python source (2 lines)"

    def test_empty_description_falls_back_to_structural(self, tmp_path: Path) -> None:
        """File whose design file has an empty description gets structural fallback."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "empty.py").write_text("a\nb\nc\nd\n", encoding="utf-8")

        # Create design file with empty description
        _create_design_file(tmp_path, "src/empty.py", "")

        result = generate_aindex(src, tmp_path, _matcher(tmp_path), _BINARY_EXTS)
        entry = next(e for e in result.entries if e.name == "empty.py")
        assert entry.description == "Python source (4 lines)"

    def test_whitespace_only_description_falls_back_to_structural(self, tmp_path: Path) -> None:
        """File whose design file has whitespace-only description gets structural fallback."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "blank.py").write_text("x\n", encoding="utf-8")

        # Create design file with whitespace-only description
        _create_design_file(tmp_path, "src/blank.py", "   ")

        result = generate_aindex(src, tmp_path, _matcher(tmp_path), _BINARY_EXTS)
        entry = next(e for e in result.entries if e.name == "blank.py")
        assert entry.description == "Python source (1 lines)"

    def test_frontmatter_description_strips_whitespace(self, tmp_path: Path) -> None:
        """Frontmatter description is stripped of leading/trailing whitespace."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "padded.py").write_text("x\n", encoding="utf-8")

        _create_design_file(tmp_path, "src/padded.py", "  Padded description  ")

        result = generate_aindex(src, tmp_path, _matcher(tmp_path), _BINARY_EXTS)
        entry = next(e for e in result.entries if e.name == "padded.py")
        assert entry.description == "Padded description"

    def test_mixed_files_with_and_without_design_files(self, tmp_path: Path) -> None:
        """Directory with some files having design files and some not."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "documented.py").write_text("x\n", encoding="utf-8")
        (src / "undocumented.py").write_text("y\nz\n", encoding="utf-8")

        _create_design_file(tmp_path, "src/documented.py", "Well-documented module")

        result = generate_aindex(src, tmp_path, _matcher(tmp_path), _BINARY_EXTS)
        documented = next(e for e in result.entries if e.name == "documented.py")
        undocumented = next(e for e in result.entries if e.name == "undocumented.py")
        assert documented.description == "Well-documented module"
        assert undocumented.description == "Python source (2 lines)"


# ---------------------------------------------------------------------------
# Task 3.1 — TestIsStructuralDescription
# ---------------------------------------------------------------------------


class TestIsStructuralDescription:
    """Tests for _is_structural_description."""

    @pytest.mark.parametrize(
        "desc",
        [
            "Python source (42 lines)",
            "Binary file (.png)",
            "Unknown file type",
            "Contains 5 files",
            "Contains 3 files, 2 subdirectories",
            "Contains 7 items",
            "Empty directory.",
            "Directory containing Python files.",
            "Mixed-language directory (Python, JavaScript).",
            "10 Python files",
            "Mixed: 5 Python, 3 JavaScript",
            "4 files",
            "3 subdirectories",
            "2 files, 1 subdirectories",
            "8 entries",
        ],
    )
    def test_known_structural_patterns_match(self, desc: str) -> None:
        assert is_structural_description(desc) is True

    @pytest.mark.parametrize(
        "desc",
        [
            "Provides CLI entry point for the application",
            "Coordinates authentication and session management",
            "Data model for user accounts",
            "Utils.",
            "Helper functions for string manipulation",
        ],
    )
    def test_rich_descriptions_do_not_match(self, desc: str) -> None:
        assert is_structural_description(desc) is False

    def test_empty_string_does_not_match(self) -> None:
        assert is_structural_description("") is False

    def test_prefix_text_with_structural_suffix_still_matches(self) -> None:
        # Pattern "^.+ source (\d+ lines)$" uses .+ so any prefix is valid
        assert is_structural_description("Not Python source (42 lines)") is True

    def test_completely_unrelated_text_does_not_match(self) -> None:
        assert is_structural_description("Handles user authentication") is False

    def test_whitespace_only_does_not_match(self) -> None:
        assert is_structural_description("   ") is False


# ---------------------------------------------------------------------------
# Task 3.2 — TestExtractRoleFragment
# ---------------------------------------------------------------------------


class TestExtractRoleFragment:
    """Tests for _extract_role_fragment."""

    @pytest.mark.parametrize(
        ("input_desc", "expected_prefix_stripped"),
        [
            ("Provides the main entry point", True),
            ("Provide a caching layer", True),
            ("Acts as a router for HTTP requests", True),
            ("Act as the central coordinator", True),
            ("Defines the data schema for users", True),
            ("Define a mapping between types", True),
            ("Generates reports from raw data", True),
            ("Generate the output artifacts", True),
            ("Coordinates the build pipeline", True),
            ("Coordinate all background tasks", True),
        ],
    )
    def test_prefix_stripping_for_each_verb_form(
        self, input_desc: str, expected_prefix_stripped: bool
    ) -> None:
        result = _extract_role_fragment(input_desc)
        # After stripping, the result should not start with the verb
        first_word = input_desc.split()[0]
        if expected_prefix_stripped:
            assert not result.lower().startswith(first_word.lower())

    def test_truncation_at_clause_marker(self) -> None:
        desc = "main entry point that handles all incoming requests"
        result = _extract_role_fragment(desc)
        assert "that handles" not in result
        assert "main entry point" in result

    def test_no_word_cap(self) -> None:
        """Verify descriptions longer than 8 words are preserved in full."""
        desc = "one two three four five six seven eight nine ten eleven"
        result = _extract_role_fragment(desc)
        assert result == desc

    def test_short_description_passes_through_unchanged(self) -> None:
        desc = "CLI entry point"
        result = _extract_role_fragment(desc)
        assert result == "CLI entry point"

    def test_clause_marker_ignored_when_before_10_chars(self) -> None:
        # "that" appears before 10 chars into the fragment
        desc = "A tool that builds"
        result = _extract_role_fragment(desc)
        # Should NOT truncate because "that" is at position 7 (< 10)
        assert result == "A tool that builds"


# ---------------------------------------------------------------------------
# Task 3.3 — TestSynthesizeSummary
# ---------------------------------------------------------------------------


class TestSynthesizeSummary:
    """Tests for _synthesize_summary."""

    def test_single_description_returned_as_is(self) -> None:
        result = _synthesize_summary(["CLI entry point"])
        assert result == "CLI entry point"

    def test_two_descriptions_joined_with_semicolon(self) -> None:
        result = _synthesize_summary(["CLI entry point", "configuration loader"])
        assert result == "CLI entry point; configuration loader"

    def test_three_descriptions_joined_directly(self) -> None:
        descs = ["CLI entry point", "configuration loader", "logging setup"]
        result = _synthesize_summary(descs)
        assert result == "CLI entry point; configuration loader; logging setup"

    def test_more_than_three_uses_scoring(self) -> None:
        descs = [
            "Provides the main CLI entry point",
            "Defines configuration schema validation",
            "Generates log output formatting",
            "Coordinates plugin loading mechanisms",
            "Defines authentication token validation",
        ]
        result = _synthesize_summary(descs)
        # Result should contain at most 3 semicolon-joined fragments
        assert result.count(";") <= 2

    def test_overlap_dedup_works(self) -> None:
        # Descriptions with highly overlapping keywords should be deduped.
        # Keywords must have >50% overlap to trigger dedup.
        descs = [
            "schema validation config processing handler",
            "schema validation config processing checker",
            "schema validation config processing verifier",
            "logging output formatter pipeline",
        ]
        result = _synthesize_summary(descs)
        # With >50% keyword overlap, only one of the schema variants selected
        assert result.count("schema validation") <= 1

    def test_empty_list_returns_empty(self) -> None:
        result = _synthesize_summary([])
        assert result == ""


# ---------------------------------------------------------------------------
# Task 3.4 — TestGenerateBillboard (updated)
# ---------------------------------------------------------------------------


class TestGenerateBillboard:
    """Tests for _generate_billboard with three-tier fallback."""

    def test_tier1_rich_descriptions(self) -> None:
        entries = [
            AIndexEntry(name="main.py", entry_type="file", description="CLI entry point"),
            AIndexEntry(name="config.py", entry_type="file", description="Configuration loader"),
        ]
        result = _generate_billboard(entries)
        assert "CLI entry point" in result
        assert "Configuration loader" in result

    def test_tier2_structural_only_uses_extension_summary(self) -> None:
        entries = [
            AIndexEntry(name="foo.py", entry_type="file", description="Python source (10 lines)"),
            AIndexEntry(name="bar.py", entry_type="file", description="Python source (20 lines)"),
        ]
        result = _generate_billboard(entries)
        assert result == "2 Python files"

    def test_tier3_count_fallback(self) -> None:
        entries = [
            AIndexEntry(name="data.xyz", entry_type="file", description="Unknown file type"),
            AIndexEntry(name="data2.xyz", entry_type="file", description="Unknown file type"),
        ]
        result = _generate_billboard(entries)
        assert result == "2 files"

    def test_mixed_only_rich_used(self) -> None:
        entries = [
            AIndexEntry(name="main.py", entry_type="file", description="CLI entry point"),
            AIndexEntry(name="utils.py", entry_type="file", description="Python source (5 lines)"),
        ]
        result = _generate_billboard(entries)
        # Only the rich description should be used for Tier 1
        assert "CLI entry point" in result
        assert "Python source" not in result

    def test_empty_entries_returns_empty_directory(self) -> None:
        result = _generate_billboard([])
        assert result == "Empty directory."

    def test_dirs_only_count_fallback(self) -> None:
        entries = [
            AIndexEntry(name="sub1", entry_type="dir", description="Contains 3 items"),
            AIndexEntry(name="sub2", entry_type="dir", description="Contains 5 items"),
        ]
        result = _generate_billboard(entries)
        assert result == "2 subdirectories"

    def test_files_and_dirs_count_fallback(self) -> None:
        entries = [
            AIndexEntry(name="data.xyz", entry_type="file", description="Unknown file type"),
            AIndexEntry(name="sub", entry_type="dir", description="Contains 1 items"),
        ]
        result = _generate_billboard(entries)
        assert result == "1 files, 1 subdirectories"


# ---------------------------------------------------------------------------
# Task 3.5 — TestExtensionBasedSummary
# ---------------------------------------------------------------------------


class TestExtensionBasedSummary:
    """Tests for _extension_based_summary."""

    def test_single_language(self) -> None:
        extensions = Counter({".py": 5})
        result = _extension_based_summary(extensions, 5)
        assert result == "5 Python files"

    def test_multiple_languages(self) -> None:
        extensions = Counter({".py": 3, ".js": 2, ".ts": 1})
        result = _extension_based_summary(extensions, 6)
        assert result.startswith("Mixed:")
        assert "Python" in result
        assert "JavaScript" in result

    def test_no_recognized_extensions(self) -> None:
        extensions = Counter({".xyz": 3, ".abc": 2})
        result = _extension_based_summary(extensions, 5)
        assert result == "5 entries"


# ---------------------------------------------------------------------------
# Task 3.6 — TestGetDirDescription
# ---------------------------------------------------------------------------


class TestGetDirDescription:
    """Tests for _get_dir_description."""

    def _make_child_aindex(
        self, tmp_path: Path, rel_dir: str, billboard: str, entries: list[AIndexEntry]
    ) -> None:
        """Helper to create a child .aindex file in the mirror tree."""
        meta = StalenessMetadata(
            source=rel_dir,
            source_hash="abc",
            generated=datetime(2026, 1, 1),
            generator="lexibrary-v2",
        )
        model = AIndexFile(
            directory_path=rel_dir,
            billboard=billboard,
            entries=entries,
            metadata=meta,
        )
        mirror_dir = tmp_path / ".lexibrary" / "designs" / rel_dir
        mirror_dir.mkdir(parents=True, exist_ok=True)
        (mirror_dir / ".aindex").write_text(serialize_aindex(model), encoding="utf-8")

    def test_uses_child_billboard_when_non_structural(self, tmp_path: Path) -> None:
        subdir = tmp_path / "src" / "utils"
        subdir.mkdir(parents=True)
        self._make_child_aindex(
            tmp_path,
            "src/utils",
            "Helper functions for path manipulation",
            [AIndexEntry(name="paths.py", entry_type="file", description="Path utilities")],
        )
        result = _get_dir_description(subdir, tmp_path)
        assert result == "Helper functions for path manipulation"

    def test_falls_back_to_counts_when_structural(self, tmp_path: Path) -> None:
        subdir = tmp_path / "src" / "core"
        subdir.mkdir(parents=True)
        self._make_child_aindex(
            tmp_path,
            "src/core",
            "3 Python files",  # structural billboard
            [
                AIndexEntry(name="a.py", entry_type="file", description="Python source (10 lines)"),
                AIndexEntry(name="b.py", entry_type="file", description="Python source (20 lines)"),
                AIndexEntry(name="c.py", entry_type="file", description="Python source (30 lines)"),
            ],
        )
        result = _get_dir_description(subdir, tmp_path)
        assert result == "Contains 3 files"

    def test_falls_back_to_counts_with_subdirs(self, tmp_path: Path) -> None:
        subdir = tmp_path / "src" / "mixed"
        subdir.mkdir(parents=True)
        self._make_child_aindex(
            tmp_path,
            "src/mixed",
            "2 Python files",  # structural
            [
                AIndexEntry(name="a.py", entry_type="file", description="Python source (10 lines)"),
                AIndexEntry(name="sub", entry_type="dir", description="Contains 1 items"),
            ],
        )
        result = _get_dir_description(subdir, tmp_path)
        assert result == "Contains 1 files, 1 subdirectories"

    def test_falls_back_to_filesystem_count_when_no_child_aindex(self, tmp_path: Path) -> None:
        subdir = tmp_path / "src" / "noindex"
        subdir.mkdir(parents=True)
        (subdir / "file1.py").write_text("x\n", encoding="utf-8")
        (subdir / "file2.py").write_text("y\n", encoding="utf-8")
        (subdir / "file3.py").write_text("z\n", encoding="utf-8")
        result = _get_dir_description(subdir, tmp_path)
        assert result == "Contains 3 items"


# ---------------------------------------------------------------------------
# A1 — TestCandidateFragments / TestSynthesizeSummaryPreSplit
# ---------------------------------------------------------------------------


class TestCandidateFragments:
    """Tests for _candidate_fragments pre-split helper."""

    def test_semicolon_description_split_into_parts(self) -> None:
        result = _candidate_fragments(["configuration schema; two-tier loader; public namespace"])
        assert result == ["configuration schema", "two-tier loader", "public namespace"]

    def test_non_semicolon_description_passed_through(self) -> None:
        result = _candidate_fragments(["CLI entry point for the application"])
        assert result == ["CLI entry point for the application"]

    def test_multiple_descriptions_expanded(self) -> None:
        result = _candidate_fragments(["schema; loader", "single clause"])
        assert result == ["schema", "loader", "single clause"]

    def test_empty_parts_after_split_are_dropped(self) -> None:
        # Leading/trailing semicolons should not produce empty strings
        result = _candidate_fragments(["; schema; "])
        assert result == ["schema"]


class TestSynthesizeSummaryPreSplit:
    """Tests for A1 pre-split behaviour in _synthesize_summary."""

    def test_semicolon_embedded_description_produces_clean_fragments(self) -> None:
        result = _synthesize_summary(["configuration schema; two-tier loader; public namespace"])
        assert "configuration schema" in result
        assert not result.endswith(";")
        assert not result.startswith(";")

    def test_no_trailing_semicolon_when_fragments_truncate(self) -> None:
        # Regression for the exact bug: "...configuration system; discovery and"
        result = _synthesize_summary(
            [
                "stable public namespace for the project's configuration system;"
                " discovery and two-tier loading",
            ]
        )
        assert not result.endswith(";")

    def test_pre_split_does_not_duplicate_non_semicolon_descriptions(self) -> None:
        result = _synthesize_summary(["authentication pipeline"])
        assert result == "authentication pipeline"


# ---------------------------------------------------------------------------
# A2 — singular/plural in _extension_based_summary
# ---------------------------------------------------------------------------


class TestExtensionBasedSummarySingular:
    """Tests for A2 singular/plural fix."""

    def test_single_language_one_file_uses_singular(self) -> None:
        result = _extension_based_summary(Counter({".py": 1}), 1)
        assert result == "1 Python file"

    def test_single_language_two_files_uses_plural(self) -> None:
        result = _extension_based_summary(Counter({".py": 2}), 2)
        assert result == "2 Python files"


# ---------------------------------------------------------------------------
# A3 — extended _LEADING_VERB_RE new verb forms
# ---------------------------------------------------------------------------


class TestExtractRoleFragmentNewVerbs:
    """Tests for A3 extended verb stripping."""

    @pytest.mark.parametrize(
        "input_desc",
        [
            "Initializes the lexibrary package",
            "Ensures the project mirrors are fresh",
            "Manages lifecycle transitions",
            "Handles watchdog file events",
            "Implements the rate-limiting protocol",
            "Exposes the public search API",
            "Writes the .aindex artifact",
            "Registers all plugin hooks",
            "Maintains an in-memory search index",
            "Builds the dependency graph",
            "Reads the design-file frontmatter",
            "Wraps the BAML client calls",
        ],
    )
    def test_new_verb_stripped(self, input_desc: str) -> None:
        result = _extract_role_fragment(input_desc)
        first_word = input_desc.split()[0]
        assert not result.lower().startswith(first_word.lower())

    def test_noun_at_line_start_not_stripped(self) -> None:
        # "Configuration" is not a verb pattern — should pass through unchanged
        result = _extract_role_fragment("Configuration schema for two-tier loading")
        assert result.startswith("Configuration")

    def test_extended_filler_stripped_after_verb(self) -> None:
        # "Manages and coordinates" → strip "Manages and " → "coordinates..."
        result = _extract_role_fragment("Manages and coordinates background tasks")
        assert not result.lower().startswith("manages")


# ---------------------------------------------------------------------------
# A4 — trailing functional word strip in _extract_role_fragment
# ---------------------------------------------------------------------------


class TestExtractRoleFragmentTrailingStrip:
    """Tests for A4 trailing preposition/article stripping."""

    def test_trailing_article_stripped(self) -> None:
        # Trailing functional word "a" is stripped from the end of the fragment
        result = _extract_role_fragment("logic to determine how a")
        assert result.split()[-1].lower() not in _TRAILING_STRIP

    def test_trailing_preposition_stripped(self) -> None:
        # Trailing preposition "of" is stripped from the end of the fragment
        desc = "one two three four five six seven of"
        result = _extract_role_fragment(desc)
        assert result.split()[-1].lower() not in _TRAILING_STRIP

    def test_trailing_conjunction_stripped(self) -> None:
        desc = "one two three four five six seven and conjunctions"
        result = _extract_role_fragment(desc)
        assert result.split()[-1].lower() not in _TRAILING_STRIP

    def test_meaningful_last_word_preserved(self) -> None:
        # "validation" is not a functional word; full string should be kept
        result = _extract_role_fragment("authentication pipeline and token validation")
        assert result.endswith("validation")

    def test_trailing_strip_on_empty_after_strip_returns_empty(self) -> None:
        # All words are filler — result should be empty, not crash
        result = _extract_role_fragment("the a an to by for of")
        assert result == ""

    def test_no_word_cap_preserves_full_description(self) -> None:
        """Verify long descriptions are preserved without truncation."""
        desc = "one two three four five six seven eight nine ten"
        result = _extract_role_fragment(desc)
        assert result == desc
        assert result.split()[-1].lower() not in _TRAILING_STRIP

    def test_uncapped_billboard_fragment_realistic(self) -> None:
        """Realistic billboard-length fragment is preserved in full (no word cap)."""
        desc = (
            "lightweight, structured way to capture, aggregate, "
            "and print errors encountered during pipeline runs"
        )
        result = _extract_role_fragment(desc)
        # All words preserved (well above the old 8-word cap)
        assert len(result.split()) > 8
        assert "pipeline runs" in result
