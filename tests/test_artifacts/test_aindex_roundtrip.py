"""Round-trip tests: serialize -> write -> parse produces identical AIndexFile."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from lexibrary.artifacts.aindex import AIndexEntry, AIndexFile
from lexibrary.artifacts.aindex_parser import parse_aindex
from lexibrary.artifacts.aindex_serializer import serialize_aindex
from lexibrary.artifacts.design_file import StalenessMetadata
from lexibrary.artifacts.writer import write_artifact


def _meta(**overrides: object) -> StalenessMetadata:
    base: dict = {
        "source": "src/",
        "source_hash": "abc123def456",
        "generated": datetime(2026, 1, 15, 10, 30, 0),
        "generator": "lexibrary-v2",
    }
    base.update(overrides)
    return StalenessMetadata(**base)


def _aindex(**overrides: object) -> AIndexFile:
    base: dict = {
        "directory_path": "src",
        "billboard": "Source code directory.",
        "entries": [],
        "local_conventions": [],
        "metadata": _meta(),
    }
    base.update(overrides)
    return AIndexFile(**base)


def _round_trip(original: AIndexFile, tmp_path: Path) -> AIndexFile | None:
    """Serialize, write to disk, then parse back."""
    serialized = serialize_aindex(original)
    target = tmp_path / ".aindex"
    write_artifact(target, serialized)
    return parse_aindex(target)


class TestRoundTripBasic:
    """Task 4.1: serialize -> write -> parse produces identical AIndexFile."""

    def test_basic_round_trip_with_files_and_dirs(self, tmp_path: Path) -> None:
        entries = [
            AIndexEntry(name="app.py", entry_type="file", description="Main app"),
            AIndexEntry(name="utils.py", entry_type="file", description="Utilities"),
            AIndexEntry(name="config", entry_type="dir", description="Config dir"),
            AIndexEntry(name="tests", entry_type="dir", description="Test suite"),
        ]
        original = _aindex(
            directory_path="myproject/src",
            billboard="Application source code.",
            entries=entries,
        )

        result = _round_trip(original, tmp_path)

        assert result is not None
        assert result.directory_path == original.directory_path
        assert result.billboard == original.billboard
        assert len(result.entries) == len(original.entries)
        for orig_entry, parsed_entry in zip(original.entries, result.entries, strict=True):
            assert parsed_entry.name == orig_entry.name
            assert parsed_entry.entry_type == orig_entry.entry_type
            assert parsed_entry.description == orig_entry.description
        assert result.local_conventions == original.local_conventions
        assert result.metadata == original.metadata

    def test_round_trip_preserves_metadata(self, tmp_path: Path) -> None:
        meta = _meta(
            source="lib/",
            source_hash="deadbeef",
            generated=datetime(2026, 6, 15, 8, 0, 0),
            generator="lexibrary-v3",
        )
        original = _aindex(
            directory_path="lib",
            billboard="Library code.",
            metadata=meta,
        )

        result = _round_trip(original, tmp_path)

        assert result is not None
        assert result.metadata.source == "lib/"
        assert result.metadata.source_hash == "deadbeef"
        assert result.metadata.generated == datetime(2026, 6, 15, 8, 0, 0)
        assert result.metadata.generator == "lexibrary-v3"

    def test_round_trip_preserves_interface_hash(self, tmp_path: Path) -> None:
        meta = _meta(interface_hash="iface999")
        original = _aindex(metadata=meta)

        result = _round_trip(original, tmp_path)

        assert result is not None
        assert result.metadata.interface_hash == "iface999"

    def test_round_trip_files_only(self, tmp_path: Path) -> None:
        entries = [
            AIndexEntry(name="a.py", entry_type="file", description="Alpha"),
            AIndexEntry(name="b.py", entry_type="file", description="Beta"),
        ]
        original = _aindex(entries=entries)

        result = _round_trip(original, tmp_path)

        assert result is not None
        assert len(result.entries) == 2
        assert all(e.entry_type == "file" for e in result.entries)

    def test_round_trip_dirs_only(self, tmp_path: Path) -> None:
        entries = [
            AIndexEntry(name="docs", entry_type="dir", description="Documentation"),
            AIndexEntry(name="src", entry_type="dir", description="Source"),
        ]
        original = _aindex(entries=entries)

        result = _round_trip(original, tmp_path)

        assert result is not None
        assert len(result.entries) == 2
        assert all(e.entry_type == "dir" for e in result.entries)

    def test_round_trip_written_file_exists(self, tmp_path: Path) -> None:
        original = _aindex()
        serialized = serialize_aindex(original)
        target = tmp_path / ".aindex"
        write_artifact(target, serialized)

        assert target.exists()
        assert target.read_text(encoding="utf-8") == serialized


class TestRoundTripEmptyDirectory:
    """Task 4.2: round-trip test for empty directory (no entries)."""

    def test_empty_entries_round_trip(self, tmp_path: Path) -> None:
        original = _aindex(
            directory_path="empty_dir",
            billboard="An empty directory.",
            entries=[],
            local_conventions=[],
        )

        result = _round_trip(original, tmp_path)

        assert result is not None
        assert result.directory_path == "empty_dir"
        assert result.billboard == "An empty directory."
        assert result.entries == []
        assert result.local_conventions == []
        assert result.metadata == original.metadata


class TestRoundTripLocalConventions:
    """Task 4.2: round-trip test for local conventions."""

    def test_single_convention_round_trip(self, tmp_path: Path) -> None:
        original = _aindex(
            local_conventions=["All modules use from __future__ import annotations"],
        )

        result = _round_trip(original, tmp_path)

        assert result is not None
        assert result.local_conventions == ["All modules use from __future__ import annotations"]

    def test_multiple_conventions_round_trip(self, tmp_path: Path) -> None:
        conventions = [
            "Use UTC everywhere",
            "No bare prints",
            "Type hints required on all public functions",
        ]
        original = _aindex(local_conventions=conventions)

        result = _round_trip(original, tmp_path)

        assert result is not None
        assert result.local_conventions == conventions

    def test_empty_conventions_round_trip(self, tmp_path: Path) -> None:
        original = _aindex(local_conventions=[])

        result = _round_trip(original, tmp_path)

        assert result is not None
        assert result.local_conventions == []


class TestRoundTripUnicode:
    """Task 4.2: round-trip test for Unicode names and descriptions."""

    def test_unicode_file_name(self, tmp_path: Path) -> None:
        entries = [
            AIndexEntry(
                name="\u00e9l\u00e8ve.py",
                entry_type="file",
                description="Student module",
            ),
        ]
        original = _aindex(entries=entries)

        result = _round_trip(original, tmp_path)

        assert result is not None
        assert len(result.entries) == 1
        assert result.entries[0].name == "\u00e9l\u00e8ve.py"
        assert result.entries[0].description == "Student module"

    def test_unicode_description(self, tmp_path: Path) -> None:
        entries = [
            AIndexEntry(
                name="greeting.py",
                entry_type="file",
                description=(
                    "Handles \u2018hello\u2019 and \u2018goodbye\u2019 in multiple languages"
                ),
            ),
        ]
        original = _aindex(entries=entries)

        result = _round_trip(original, tmp_path)

        assert result is not None
        expected_desc = "Handles \u2018hello\u2019 and \u2018goodbye\u2019 in multiple languages"
        assert result.entries[0].description == expected_desc

    def test_unicode_directory_name(self, tmp_path: Path) -> None:
        entries = [
            AIndexEntry(
                name="\u00fcbersetzung",
                entry_type="dir",
                description="Translation files",
            ),
        ]
        original = _aindex(entries=entries)

        result = _round_trip(original, tmp_path)

        assert result is not None
        assert result.entries[0].name == "\u00fcbersetzung"
        assert result.entries[0].entry_type == "dir"

    def test_unicode_billboard(self, tmp_path: Path) -> None:
        original = _aindex(
            billboard="Biblioth\u00e8que de donn\u00e9es \u2014 data library.",
        )

        result = _round_trip(original, tmp_path)

        assert result is not None
        assert result.billboard == "Biblioth\u00e8que de donn\u00e9es \u2014 data library."

    def test_unicode_local_convention(self, tmp_path: Path) -> None:
        original = _aindex(
            local_conventions=["Use \u00abguillemets\u00bb for French strings"],
        )

        result = _round_trip(original, tmp_path)

        assert result is not None
        assert result.local_conventions == ["Use \u00abguillemets\u00bb for French strings"]

    def test_mixed_unicode_round_trip(self, tmp_path: Path) -> None:
        """Full round-trip with Unicode in every field."""
        entries = [
            AIndexEntry(
                name="caf\u00e9.py",
                entry_type="file",
                description="Module caf\u00e9 \u2615",
            ),
            AIndexEntry(
                name="\u6587\u66f8",
                entry_type="dir",
                description="\u65e5\u672c\u8a9e\u306e\u30c9\u30ad\u30e5\u30e1\u30f3\u30c8",
            ),
        ]
        original = _aindex(
            directory_path="projet/\u00e9l\u00e8ves",
            billboard="R\u00e9pertoire des \u00e9l\u00e8ves.",
            entries=entries,
            local_conventions=["\u00c9crire en fran\u00e7ais"],
        )

        result = _round_trip(original, tmp_path)

        assert result is not None
        assert result.directory_path == "projet/\u00e9l\u00e8ves"
        assert result.billboard == "R\u00e9pertoire des \u00e9l\u00e8ves."
        assert len(result.entries) == 2
        assert result.entries[0].name == "caf\u00e9.py"
        assert result.entries[0].description == "Module caf\u00e9 \u2615"
        assert result.entries[1].name == "\u6587\u66f8"
        assert (
            result.entries[1].description
            == "\u65e5\u672c\u8a9e\u306e\u30c9\u30ad\u30e5\u30e1\u30f3\u30c8"
        )
        assert result.local_conventions == ["\u00c9crire en fran\u00e7ais"]
        assert result.metadata == original.metadata
