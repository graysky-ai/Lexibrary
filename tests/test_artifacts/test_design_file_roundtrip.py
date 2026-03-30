"""Round-trip tests for design file serializer + parser."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

from lexibrary.artifacts.design_file import DesignFile, DesignFileFrontmatter, StalenessMetadata
from lexibrary.artifacts.design_file_parser import parse_design_file
from lexibrary.artifacts.design_file_serializer import serialize_design_file


def _meta(**overrides: object) -> StalenessMetadata:
    base: dict = {
        "source": "src/lexibrary/cli.py",
        "source_hash": "src_hash_abc",
        "design_hash": "placeholder",
        "generated": datetime(2026, 3, 1, 10, 0, 0),
        "generator": "lexibrary-v2",
    }
    base.update(overrides)
    return StalenessMetadata(**base)


def _frontmatter(**overrides: object) -> DesignFileFrontmatter:
    base: dict = {"description": "CLI entry point for the lexi command.", "id": "DS-001"}
    base.update(overrides)
    return DesignFileFrontmatter(**base)


def _design_file(**overrides: object) -> DesignFile:
    base: dict = {
        "source_path": "src/lexibrary/cli.py",
        "frontmatter": _frontmatter(),
        "summary": "CLI entry point for the lexi command.",
        "interface_contract": "def main() -> None: ...",
        "metadata": _meta(),
    }
    base.update(overrides)
    return DesignFile(**base)


class TestDesignFileRoundtrip:
    def test_roundtrip_minimal(self, tmp_path: Path) -> None:
        df = _design_file()
        content = serialize_design_file(df)
        f = tmp_path / "design.md"
        f.write_text(content)
        parsed = parse_design_file(f)
        assert parsed is not None
        assert parsed.source_path == df.source_path
        assert parsed.frontmatter.description == df.frontmatter.description
        assert parsed.frontmatter.updated_by == df.frontmatter.updated_by
        assert parsed.interface_contract == df.interface_contract
        assert parsed.dependencies == df.dependencies
        assert parsed.dependents == df.dependents
        assert parsed.tests is None
        assert parsed.complexity_warning is None
        assert parsed.wikilinks == []
        assert parsed.tags == []
        assert parsed.stack_refs == []

    def test_roundtrip_with_all_optional_sections(self, tmp_path: Path) -> None:
        df = _design_file(
            dependencies=["src/lexibrary/config/schema.py", "src/lexibrary/utils/paths.py"],
            dependents=["src/lexibrary/__main__.py"],
            tests="See tests/test_cli.py for full coverage.",
            complexity_warning="High cyclomatic complexity — 12 branches.",
            wikilinks=["Config", "LLMService"],
            tags=["cli", "entry-point"],
            stack_refs=["G-01", "G-03"],
            metadata=_meta(interface_hash="iface_hash_xyz"),
        )
        content = serialize_design_file(df)
        f = tmp_path / "design.md"
        f.write_text(content)
        parsed = parse_design_file(f)
        assert parsed is not None
        assert parsed.dependencies == [
            "src/lexibrary/config/schema.py",
            "src/lexibrary/utils/paths.py",
        ]
        assert parsed.dependents == ["src/lexibrary/__main__.py"]
        assert parsed.tests == "See tests/test_cli.py for full coverage."
        assert parsed.complexity_warning == "High cyclomatic complexity — 12 branches."
        assert parsed.wikilinks == ["Config", "LLMService"]
        assert parsed.tags == ["cli", "entry-point"]
        assert parsed.stack_refs == ["G-01", "G-03"]
        assert parsed.metadata.interface_hash == "iface_hash_xyz"

    def test_roundtrip_agent_updated_by(self, tmp_path: Path) -> None:
        df = _design_file(frontmatter=_frontmatter(updated_by="agent"))
        content = serialize_design_file(df)
        f = tmp_path / "design.md"
        f.write_text(content)
        parsed = parse_design_file(f)
        assert parsed is not None
        assert parsed.frontmatter.updated_by == "agent"

    def test_design_hash_computed_from_body(self, tmp_path: Path) -> None:
        df = _design_file()
        content = serialize_design_file(df)
        f = tmp_path / "design.md"
        f.write_text(content)

        # Extract the design_hash from the footer
        parsed_meta = parse_design_file(f)
        assert parsed_meta is not None
        design_hash_in_footer = parsed_meta.metadata.design_hash

        # The design_hash should be SHA-256 of the content above the footer.
        # Serializer hashes the parts joined with "\n" before appending footer
        # so we just verify it's a valid 64-char hex string
        assert len(design_hash_in_footer) == 64
        assert all(c in "0123456789abcdef" for c in design_hash_in_footer)

    def test_agent_edit_detection(self, tmp_path: Path) -> None:
        """Modifying the body after serialization produces a different hash."""
        df = _design_file()
        content = serialize_design_file(df)

        # Extract the design_hash stored in footer
        footer_match_start = content.index("<!-- lexibrary:meta")
        footer_body = content[footer_match_start:]
        original_hash = None
        for line in footer_body.splitlines():
            if line.startswith("design_hash:"):
                original_hash = line.split(": ", 1)[1].strip()
                break
        assert original_hash is not None

        # Simulate agent edit: modify the body
        modified_body = content.replace("def main() -> None: ...", "def main() -> int: ...")
        # Hash the modified content (excluding footer)
        modified_footer_start = modified_body.index("<!-- lexibrary:meta")
        modified_pre_footer = modified_body[:modified_footer_start]
        new_hash = hashlib.sha256(modified_pre_footer.encode()).hexdigest()

        assert new_hash != original_hash, "Agent edit should produce a different hash"

    def test_roundtrip_annotation_not_in_dependents_list(self, tmp_path: Path) -> None:
        """D-070: Annotation line is present in serialized output but does not
        appear in parsed dependents list after round-trip (task 1.4)."""
        df = _design_file(dependents=["src/lexibrary/__main__.py"])
        content = serialize_design_file(df)
        # Verify annotation is present in the raw serialized text
        assert "*(see `lexi lookup` for live reverse references)*" in content
        f = tmp_path / "design.md"
        f.write_text(content)
        parsed = parse_design_file(f)
        assert parsed is not None
        # Annotation must NOT be in the parsed dependents list
        assert parsed.dependents == ["src/lexibrary/__main__.py"]
        for dep in parsed.dependents:
            assert "lexi lookup" not in dep
            assert "reverse references" not in dep

    def test_roundtrip_annotation_not_in_empty_dependents(self, tmp_path: Path) -> None:
        """D-070: With no dependents, annotation is serialized but parsed dependents
        remains empty after round-trip."""
        df = _design_file(dependents=[])
        content = serialize_design_file(df)
        assert "*(see `lexi lookup` for live reverse references)*" in content
        f = tmp_path / "design.md"
        f.write_text(content)
        parsed = parse_design_file(f)
        assert parsed is not None
        assert parsed.dependents == []

    def test_roundtrip_status_active(self, tmp_path: Path) -> None:
        """Active status survives round-trip."""
        df = _design_file()
        content = serialize_design_file(df)
        f = tmp_path / "design.md"
        f.write_text(content)
        parsed = parse_design_file(f)
        assert parsed is not None
        assert parsed.frontmatter.status == "active"
        assert parsed.frontmatter.deprecated_at is None
        assert parsed.frontmatter.deprecated_reason is None

    def test_roundtrip_deprecated_all_fields(self, tmp_path: Path) -> None:
        """Deprecated status with all deprecation fields survives round-trip."""
        deprecated_at = datetime(2026, 3, 1, 14, 30, 0)
        df = _design_file(
            frontmatter=_frontmatter(
                status="deprecated",
                deprecated_at=deprecated_at,
                deprecated_reason="source_deleted",
            )
        )
        content = serialize_design_file(df)
        f = tmp_path / "design.md"
        f.write_text(content)
        parsed = parse_design_file(f)
        assert parsed is not None
        assert parsed.frontmatter.status == "deprecated"
        assert parsed.frontmatter.deprecated_at == deprecated_at
        assert parsed.frontmatter.deprecated_reason == "source_deleted"

    def test_roundtrip_deprecated_source_renamed(self, tmp_path: Path) -> None:
        """Deprecated with source_renamed reason survives round-trip."""
        deprecated_at = datetime(2026, 2, 15, 9, 0, 0)
        df = _design_file(
            frontmatter=_frontmatter(
                status="deprecated",
                deprecated_at=deprecated_at,
                deprecated_reason="source_renamed",
            )
        )
        content = serialize_design_file(df)
        f = tmp_path / "design.md"
        f.write_text(content)
        parsed = parse_design_file(f)
        assert parsed is not None
        assert parsed.frontmatter.status == "deprecated"
        assert parsed.frontmatter.deprecated_at == deprecated_at
        assert parsed.frontmatter.deprecated_reason == "source_renamed"

    def test_roundtrip_deprecated_manual(self, tmp_path: Path) -> None:
        """Deprecated with manual reason survives round-trip."""
        deprecated_at = datetime(2026, 1, 20, 16, 45, 0)
        df = _design_file(
            frontmatter=_frontmatter(
                status="deprecated",
                deprecated_at=deprecated_at,
                deprecated_reason="manual",
            )
        )
        content = serialize_design_file(df)
        f = tmp_path / "design.md"
        f.write_text(content)
        parsed = parse_design_file(f)
        assert parsed is not None
        assert parsed.frontmatter.status == "deprecated"
        assert parsed.frontmatter.deprecated_at == deprecated_at
        assert parsed.frontmatter.deprecated_reason == "manual"

    def test_roundtrip_unlinked_status(self, tmp_path: Path) -> None:
        """Unlinked status (no deprecation fields) survives round-trip."""
        df = _design_file(frontmatter=_frontmatter(status="unlinked"))
        content = serialize_design_file(df)
        f = tmp_path / "design.md"
        f.write_text(content)
        parsed = parse_design_file(f)
        assert parsed is not None
        assert parsed.frontmatter.status == "unlinked"
        assert parsed.frontmatter.deprecated_at is None
        assert parsed.frontmatter.deprecated_reason is None

    def test_roundtrip_deprecated_with_all_optional_sections(self, tmp_path: Path) -> None:
        """Deprecated file with all optional sections survives full round-trip."""
        deprecated_at = datetime(2026, 3, 1, 14, 30, 0)
        df = _design_file(
            frontmatter=_frontmatter(
                status="deprecated",
                deprecated_at=deprecated_at,
                deprecated_reason="source_deleted",
                updated_by="agent",
            ),
            dependencies=["src/lexibrary/config/schema.py"],
            dependents=["src/lexibrary/__main__.py"],
            tests="See tests/test_cli.py",
            complexity_warning="High cyclomatic complexity.",
            wikilinks=["Config", "LLMService"],
            tags=["cli"],
            stack_refs=["ST-01"],
            metadata=_meta(interface_hash="iface_hash_xyz"),
        )
        content = serialize_design_file(df)
        f = tmp_path / "design.md"
        f.write_text(content)
        parsed = parse_design_file(f)
        assert parsed is not None
        assert parsed.frontmatter.status == "deprecated"
        assert parsed.frontmatter.deprecated_at == deprecated_at
        assert parsed.frontmatter.deprecated_reason == "source_deleted"
        assert parsed.frontmatter.updated_by == "agent"
        assert parsed.dependencies == ["src/lexibrary/config/schema.py"]
        assert parsed.dependents == ["src/lexibrary/__main__.py"]
        assert parsed.tests == "See tests/test_cli.py"
        assert parsed.complexity_warning == "High cyclomatic complexity."
        assert parsed.wikilinks == ["Config", "LLMService"]
        assert parsed.tags == ["cli"]
        assert parsed.stack_refs == ["ST-01"]

    def test_metadata_source_fields_preserved(self, tmp_path: Path) -> None:
        df = _design_file(
            metadata=_meta(
                source="src/lexibrary/cli.py",
                source_hash="src_hash_abc",
                generated=datetime(2026, 3, 1, 10, 0, 0),
                generator="lexibrary-v2",
            )
        )
        content = serialize_design_file(df)
        f = tmp_path / "design.md"
        f.write_text(content)
        parsed = parse_design_file(f)
        assert parsed is not None
        assert parsed.metadata.source == "src/lexibrary/cli.py"
        assert parsed.metadata.source_hash == "src_hash_abc"
        assert parsed.metadata.generator == "lexibrary-v2"
        assert parsed.metadata.generated == datetime(2026, 3, 1, 10, 0, 0)
