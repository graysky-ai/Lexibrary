"""Tests for .aindex file parser."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from lexibrary.artifacts.aindex import AIndexEntry, AIndexFile
from lexibrary.artifacts.aindex_parser import parse_aindex, parse_aindex_metadata
from lexibrary.artifacts.aindex_serializer import serialize_aindex
from lexibrary.artifacts.design_file import StalenessMetadata


def _meta(**overrides: object) -> StalenessMetadata:
    base: dict = {
        "source": "src",
        "source_hash": "abc123",
        "generated": datetime(2026, 1, 1, 12, 0, 0),
        "generator": "lexibrary-v2",
    }
    base.update(overrides)
    return StalenessMetadata(**base)


def _aindex(**overrides: object) -> AIndexFile:
    base: dict = {
        "directory_path": "src",
        "billboard": "Source code directory.",
        "entries": [],
        "metadata": _meta(),
    }
    base.update(overrides)
    return AIndexFile(**base)


def _write_aindex(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


class TestParseAIndex:
    def test_returns_none_for_nonexistent_file(self, tmp_path: Path) -> None:
        result = parse_aindex(tmp_path / "missing.aindex")
        assert result is None

    def test_returns_none_for_malformed_content(self, tmp_path: Path) -> None:
        p = _write_aindex(tmp_path, "bad.aindex", "garbage content with no structure\n")
        result = parse_aindex(p)
        assert result is None

    def test_returns_none_for_missing_metadata_footer(self, tmp_path: Path) -> None:
        content = (
            "# src\n\nBillboard.\n\n## Child Map\n\n(none)\n\n## Local Conventions\n\n(none)\n"
        )
        p = _write_aindex(tmp_path, "nometa.aindex", content)
        result = parse_aindex(p)
        assert result is None

    def test_parse_well_formed_empty_directory(self, tmp_path: Path) -> None:
        model = _aindex()
        p = _write_aindex(tmp_path, ".aindex", serialize_aindex(model))
        result = parse_aindex(p)
        assert result is not None
        assert result.directory_path == "src"
        assert result.billboard == "Source code directory."
        assert result.entries == []
        assert result.local_conventions == []

    def test_parse_directory_path_strips_trailing_slash(self, tmp_path: Path) -> None:
        # The serializer adds trailing slash in the H1 heading; parser must strip it
        content = (
            "# src/\n\nBillboard.\n\n## Child Map\n\n(none)\n\n"
            "## Local Conventions\n\n(none)\n\n"
            '<!-- lexibrary:meta source="src" source_hash="abc"'
            ' generated="2026-01-01T00:00:00" generator="g" -->\n'
        )
        p = _write_aindex(tmp_path, ".aindex", content)
        result = parse_aindex(p)
        assert result is not None
        assert result.directory_path == "src"

    def test_parse_file_and_dir_entries(self, tmp_path: Path) -> None:
        entries = [
            AIndexEntry(name="foo.py", entry_type="file", description="A Python file"),
            AIndexEntry(name="bar", entry_type="dir", description="A subdir"),
        ]
        model = _aindex(entries=entries)
        p = _write_aindex(tmp_path, ".aindex", serialize_aindex(model))
        result = parse_aindex(p)
        assert result is not None
        assert len(result.entries) == 2
        file_entry = next(e for e in result.entries if e.entry_type == "file")
        dir_entry = next(e for e in result.entries if e.entry_type == "dir")
        assert file_entry.name == "foo.py"
        assert file_entry.description == "A Python file"
        assert dir_entry.name == "bar"
        assert dir_entry.description == "A subdir"

    def test_parse_dir_entry_strips_trailing_slash(self, tmp_path: Path) -> None:
        # The serializer outputs "`bar/`" in the table; parser should store "bar"
        entries = [AIndexEntry(name="bar", entry_type="dir", description="Dir")]
        model = _aindex(entries=entries)
        p = _write_aindex(tmp_path, ".aindex", serialize_aindex(model))
        result = parse_aindex(p)
        assert result is not None
        dir_entry = result.entries[0]
        assert dir_entry.name == "bar"
        assert not dir_entry.name.endswith("/")

    def test_parse_empty_child_map_returns_empty_entries(self, tmp_path: Path) -> None:
        model = _aindex(entries=[])
        p = _write_aindex(tmp_path, ".aindex", serialize_aindex(model))
        result = parse_aindex(p)
        assert result is not None
        assert result.entries == []

    def test_parse_local_conventions(self, tmp_path: Path) -> None:
        model = _aindex(local_conventions=["Use UTC everywhere", "No bare prints"])
        p = _write_aindex(tmp_path, ".aindex", serialize_aindex(model))
        result = parse_aindex(p)
        assert result is not None
        assert result.local_conventions == ["Use UTC everywhere", "No bare prints"]

    def test_parse_empty_local_conventions(self, tmp_path: Path) -> None:
        model = _aindex(local_conventions=[])
        p = _write_aindex(tmp_path, ".aindex", serialize_aindex(model))
        result = parse_aindex(p)
        assert result is not None
        assert result.local_conventions == []

    def test_parse_metadata_fields(self, tmp_path: Path) -> None:
        model = _aindex()
        p = _write_aindex(tmp_path, ".aindex", serialize_aindex(model))
        result = parse_aindex(p)
        assert result is not None
        assert result.metadata.source == "src"
        assert result.metadata.source_hash == "abc123"
        assert result.metadata.generated == datetime(2026, 1, 1, 12, 0, 0)
        assert result.metadata.generator == "lexibrary-v2"
        assert result.metadata.interface_hash is None

    def test_parse_metadata_with_interface_hash(self, tmp_path: Path) -> None:
        model = _aindex(metadata=_meta(interface_hash="xyz789"))
        p = _write_aindex(tmp_path, ".aindex", serialize_aindex(model))
        result = parse_aindex(p)
        assert result is not None
        assert result.metadata.interface_hash == "xyz789"

    def test_tolerant_of_extra_blank_lines(self, tmp_path: Path) -> None:
        # Extra blank lines should not prevent parsing
        content = (
            "# src\n\n\n"
            "Billboard text.\n\n\n"
            "## Child Map\n\n\n"
            "(none)\n\n\n"
            "## Local Conventions\n\n\n"
            "(none)\n\n\n"
            '<!-- lexibrary:meta source="src" source_hash="h" '
            'generated="2026-01-01T00:00:00" generator="g" -->\n'
        )
        p = _write_aindex(tmp_path, ".aindex", content)
        result = parse_aindex(p)
        assert result is not None
        assert result.billboard == "Billboard text."


class TestParseAIndexMetadata:
    def test_returns_none_for_nonexistent_file(self, tmp_path: Path) -> None:
        result = parse_aindex_metadata(tmp_path / "missing.aindex")
        assert result is None

    def test_returns_none_when_footer_absent(self, tmp_path: Path) -> None:
        p = _write_aindex(tmp_path, "nofooter.aindex", "# src\n\nBillboard.\n")
        result = parse_aindex_metadata(p)
        assert result is None

    def test_parse_metadata_from_valid_file(self, tmp_path: Path) -> None:
        model = _aindex()
        p = _write_aindex(tmp_path, ".aindex", serialize_aindex(model))
        result = parse_aindex_metadata(p)
        assert result is not None
        assert result.source == "src"
        assert result.source_hash == "abc123"
        assert result.generated == datetime(2026, 1, 1, 12, 0, 0)
        assert result.generator == "lexibrary-v2"

    def test_parse_metadata_matches_full_parse(self, tmp_path: Path) -> None:
        model = _aindex()
        p = _write_aindex(tmp_path, ".aindex", serialize_aindex(model))
        full = parse_aindex(p)
        meta_only = parse_aindex_metadata(p)
        assert full is not None
        assert meta_only is not None
        assert meta_only == full.metadata

    def test_parse_metadata_standalone(self, tmp_path: Path) -> None:
        # Should work without calling parse_aindex first
        content = (
            "# src\n\nBillboard.\n\n## Child Map\n\n(none)\n\n"
            "## Local Conventions\n\n(none)\n\n"
            '<!-- lexibrary:meta source="s" source_hash="h" '
            'generated="2026-06-01T10:00:00" generator="gen" -->\n'
        )
        p = _write_aindex(tmp_path, ".aindex", content)
        result = parse_aindex_metadata(p)
        assert result is not None
        assert result.source == "s"
        assert result.generator == "gen"
