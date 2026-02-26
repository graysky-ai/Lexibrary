"""Tests for AIndexFile serializer."""

from __future__ import annotations

from datetime import datetime

from lexibrary.artifacts.aindex import AIndexEntry, AIndexFile
from lexibrary.artifacts.aindex_serializer import serialize_aindex
from lexibrary.artifacts.design_file import StalenessMetadata


def _meta(**overrides: object) -> StalenessMetadata:
    base: dict = {
        "source": "src/",
        "source_hash": "abc123",
        "generated": datetime(2026, 1, 1, 12, 0, 0),
        "generator": "lexibrary-v2",
    }
    base.update(overrides)
    return StalenessMetadata(**base)


def _aindex(**overrides: object) -> AIndexFile:
    base: dict = {
        "directory_path": "src/",
        "billboard": "Source code directory.",
        "entries": [],
        "metadata": _meta(),
    }
    base.update(overrides)
    return AIndexFile(**base)


class TestSerializeAIndex:
    def test_h1_heading_with_trailing_slash(self) -> None:
        result = serialize_aindex(_aindex())
        assert result.startswith("# src/\n")

    def test_h1_heading_adds_trailing_slash(self) -> None:
        result = serialize_aindex(_aindex(directory_path="src"))
        assert result.startswith("# src/\n")

    def test_billboard_in_output(self) -> None:
        result = serialize_aindex(_aindex(billboard="My billboard."))
        assert "My billboard." in result

    def test_empty_child_map_shows_none(self) -> None:
        result = serialize_aindex(_aindex(entries=[]))
        child_map_section = result.split("## Child Map")[1].split("<!--")[0]
        assert "(none)" in child_map_section

    def test_basic_file_and_dir_entry(self) -> None:
        entries = [
            AIndexEntry(name="foo.py", entry_type="file", description="A foo file"),
            AIndexEntry(name="bar", entry_type="dir", description="A bar dir"),
        ]
        result = serialize_aindex(_aindex(entries=entries))
        assert "| `foo.py` | file | A foo file |" in result
        assert "| `bar/` | dir | A bar dir |" in result

    def test_dir_name_already_has_trailing_slash(self) -> None:
        entries = [
            AIndexEntry(name="bar/", entry_type="dir", description="Bar dir"),
        ]
        result = serialize_aindex(_aindex(entries=entries))
        assert "| `bar/` | dir | Bar dir |" in result
        assert "bar//" not in result

    def test_files_before_dirs(self) -> None:
        entries = [
            AIndexEntry(name="zoo", entry_type="dir", description="Dir"),
            AIndexEntry(name="alpha.py", entry_type="file", description="File"),
        ]
        result = serialize_aindex(_aindex(entries=entries))
        file_pos = result.index("alpha.py")
        dir_pos = result.index("zoo")
        assert file_pos < dir_pos

    def test_files_sorted_case_insensitive(self) -> None:
        entries = [
            AIndexEntry(name="Baz.py", entry_type="file", description="B"),
            AIndexEntry(name="alpha.py", entry_type="file", description="A"),
        ]
        result = serialize_aindex(_aindex(entries=entries))
        alpha_pos = result.index("alpha.py")
        baz_pos = result.index("Baz.py")
        assert alpha_pos < baz_pos

    def test_dirs_sorted_case_insensitive(self) -> None:
        entries = [
            AIndexEntry(name="Zoo", entry_type="dir", description="Z"),
            AIndexEntry(name="alpha", entry_type="dir", description="A"),
        ]
        result = serialize_aindex(_aindex(entries=entries))
        alpha_pos = result.index("alpha")
        zoo_pos = result.index("Zoo")
        assert alpha_pos < zoo_pos

    def test_files_only_no_dir_rows(self) -> None:
        entries = [
            AIndexEntry(name="foo.py", entry_type="file", description="Foo"),
        ]
        result = serialize_aindex(_aindex(entries=entries))
        assert "| `foo.py` | file | Foo |" in result
        child_map_body = result.split("## Child Map")[1].split("<!--")[0]
        assert "| dir |" not in child_map_body

    def test_dirs_only_no_file_rows(self) -> None:
        entries = [
            AIndexEntry(name="utils", entry_type="dir", description="Utils"),
        ]
        result = serialize_aindex(_aindex(entries=entries))
        assert "| `utils/` | dir | Utils |" in result
        child_map_body = result.split("## Child Map")[1].split("<!--")[0]
        assert "| file |" not in child_map_body

    def test_no_local_conventions_section(self) -> None:
        result = serialize_aindex(_aindex())
        assert "## Local Conventions" not in result

    def test_metadata_footer_required_fields(self) -> None:
        result = serialize_aindex(_aindex())
        assert "<!-- lexibrary:meta" in result
        assert 'source="src/"' in result
        assert 'source_hash="abc123"' in result
        assert 'generated="2026-01-01T12:00:00"' in result
        assert 'generator="lexibrary-v2"' in result
        assert "-->" in result

    def test_metadata_footer_interface_hash_omitted_when_none(self) -> None:
        result = serialize_aindex(_aindex())
        assert "interface_hash" not in result

    def test_metadata_footer_interface_hash_included_when_set(self) -> None:
        result = serialize_aindex(_aindex(metadata=_meta(interface_hash="xyz789")))
        assert 'interface_hash="xyz789"' in result

    def test_output_ends_with_single_trailing_newline(self) -> None:
        result = serialize_aindex(_aindex())
        assert result.endswith("\n")
        assert not result.endswith("\n\n")

    def test_table_header_present_when_entries_exist(self) -> None:
        entries = [AIndexEntry(name="f.py", entry_type="file", description="F")]
        result = serialize_aindex(_aindex(entries=entries))
        assert "| Name | Type | Description |" in result
        assert "| --- | --- | --- |" in result
