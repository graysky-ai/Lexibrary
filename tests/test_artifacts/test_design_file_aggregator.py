"""Round-trip tests for the aggregator ``## Re-exports`` rendering path.

Covers the §2.1 aggregator-design-rendering spec: when ``DesignFile.reexports``
is populated, the serializer SHALL emit ``## Re-exports`` in place of
``## Interface Contract`` and the parser SHALL round-trip it faithfully.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from lexibrary.artifacts.design_file import DesignFile, DesignFileFrontmatter, StalenessMetadata
from lexibrary.artifacts.design_file_parser import parse_design_file
from lexibrary.artifacts.design_file_serializer import serialize_design_file


def _meta(**overrides: object) -> StalenessMetadata:
    base: dict = {
        "source": "src/lexibrary/artifacts/__init__.py",
        "source_hash": "src_hash_abc",
        "design_hash": "placeholder",
        "generated": datetime(2026, 4, 21, 10, 0, 0),
        "generator": "lexibrary-v2",
    }
    base.update(overrides)
    return StalenessMetadata(**base)


def _frontmatter(**overrides: object) -> DesignFileFrontmatter:
    base: dict = {
        "description": "Aggregator module re-exporting the public design-file API.",
        "id": "DS-042",
    }
    base.update(overrides)
    return DesignFileFrontmatter(**base)


def _aggregator_df(**overrides: object) -> DesignFile:
    base: dict = {
        "source_path": "src/lexibrary/artifacts/__init__.py",
        "frontmatter": _frontmatter(),
        "summary": "Aggregator module re-exporting the public design-file API.",
        "interface_contract": "",
        "reexports": {
            "lexibrary.artifacts.design_file": [
                "DesignFile",
                "DesignFileFrontmatter",
                "StalenessMetadata",
            ],
        },
        "metadata": _meta(),
    }
    base.update(overrides)
    return DesignFile(**base)


def _non_aggregator_df(**overrides: object) -> DesignFile:
    base: dict = {
        "source_path": "src/lexibrary/cli.py",
        "frontmatter": _frontmatter(
            description="CLI entry point for the lexi command.",
            id="DS-099",
        ),
        "summary": "CLI entry point for the lexi command.",
        "interface_contract": "def main() -> None: ...",
        "metadata": _meta(source="src/lexibrary/cli.py"),
    }
    base.update(overrides)
    return DesignFile(**base)


class TestAggregatorRoundtrip:
    """Aggregator design-file round-trip: Re-exports → serializer → parser."""

    def test_aggregator_roundtrip_preserves_reexports(self, tmp_path: Path) -> None:
        """Serialize+parse an aggregator DesignFile and assert reexports survive."""
        df = _aggregator_df()
        content = serialize_design_file(df)
        f = tmp_path / "design.md"
        f.write_text(content)
        parsed = parse_design_file(f)
        assert parsed is not None
        assert parsed.reexports == df.reexports
        assert parsed.interface_contract == ""

    def test_aggregator_serializes_reexports_section(self, tmp_path: Path) -> None:
        """``## Re-exports`` emitted; ``## Interface Contract`` suppressed."""
        df = _aggregator_df()
        content = serialize_design_file(df)
        assert "## Re-exports" in content
        assert "## Interface Contract" not in content
        # Bullet format: ``- From `<source-module>`: Name1, Name2, Name3``
        assert (
            "- From `lexibrary.artifacts.design_file`: "
            "DesignFile, DesignFileFrontmatter, StalenessMetadata"
        ) in content

    def test_aggregator_with_multiple_source_modules(self, tmp_path: Path) -> None:
        """Re-exports grouped by source module: one bullet per source."""
        df = _aggregator_df(
            reexports={
                "lexibrary.x": ["A", "B"],
                "lexibrary.y": ["C"],
            }
        )
        content = serialize_design_file(df)
        f = tmp_path / "design.md"
        f.write_text(content)
        parsed = parse_design_file(f)
        assert parsed is not None
        assert parsed.reexports == {
            "lexibrary.x": ["A", "B"],
            "lexibrary.y": ["C"],
        }
        # Two bullets, one per source module.
        assert "- From `lexibrary.x`: A, B" in content
        assert "- From `lexibrary.y`: C" in content

    def test_non_aggregator_roundtrip_preserves_interface_contract(self, tmp_path: Path) -> None:
        """Non-aggregator DesignFile round-trips via ``## Interface Contract``."""
        df = _non_aggregator_df()
        content = serialize_design_file(df)
        f = tmp_path / "design.md"
        f.write_text(content)
        parsed = parse_design_file(f)
        assert parsed is not None
        assert parsed.reexports is None
        assert parsed.interface_contract == "def main() -> None: ..."

    def test_non_aggregator_serializes_interface_contract_only(self, tmp_path: Path) -> None:
        """``## Interface Contract`` emitted; ``## Re-exports`` suppressed."""
        df = _non_aggregator_df()
        content = serialize_design_file(df)
        assert "## Interface Contract" in content
        assert "## Re-exports" not in content
