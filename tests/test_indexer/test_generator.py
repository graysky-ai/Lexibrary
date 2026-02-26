"""Tests for the index generator."""

from __future__ import annotations

from pathlib import Path

import pathspec

from lexibrary.artifacts.aindex_serializer import serialize_aindex
from lexibrary.ignore.matcher import IgnoreMatcher
from lexibrary.indexer.generator import generate_aindex

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
        assert result.billboard == "Directory containing Python source files."

    def test_mixed_language_billboard(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "app.py").write_text("x\n", encoding="utf-8")
        (src / "index.js").write_text("y\n", encoding="utf-8")
        result = generate_aindex(src, tmp_path, _matcher(tmp_path), _BINARY_EXTS)
        assert result.billboard.startswith("Mixed-language directory (")
        assert "Python" in result.billboard
        assert "JavaScript" in result.billboard

    def test_binary_only_billboard(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "logo.png").write_bytes(b"\x89PNG")
        result = generate_aindex(src, tmp_path, _matcher(tmp_path), _BINARY_EXTS)
        assert result.billboard == "Directory containing binary and data files."


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
        mirror_dir = tmp_path / ".lexibrary" / "src" / "utils"
        mirror_dir.mkdir(parents=True)
        (mirror_dir / ".aindex").write_text(serialize_aindex(child_model), encoding="utf-8")

        result = generate_aindex(src, tmp_path, _matcher(tmp_path), _BINARY_EXTS)
        entry = next(e for e in result.entries if e.name == "utils")
        assert entry.description == "Contains 2 files, 1 subdirectories"

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
        mirror_dir = tmp_path / ".lexibrary" / "src" / "utils"
        mirror_dir.mkdir(parents=True)
        (mirror_dir / ".aindex").write_text(serialize_aindex(child_model), encoding="utf-8")

        result = generate_aindex(src, tmp_path, _matcher(tmp_path), _BINARY_EXTS)
        entry = next(e for e in result.entries if e.name == "utils")
        assert entry.description == "Contains 1 files"


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
    design_path = tmp_path / ".lexibrary" / (rel_source + ".md")
    design_path.parent.mkdir(parents=True, exist_ok=True)
    frontmatter = (
        "---\n"
        f"description: {description}\n"
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
