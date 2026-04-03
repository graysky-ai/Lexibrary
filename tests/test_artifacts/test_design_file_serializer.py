"""Tests for design file serializer."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from lexibrary.artifacts.design_file import DesignFile, DesignFileFrontmatter, StalenessMetadata
from lexibrary.artifacts.design_file_parser import parse_design_file
from lexibrary.artifacts.design_file_serializer import serialize_design_file


def _meta(**overrides: object) -> StalenessMetadata:
    base: dict = {
        "source": "src/lexibrary/cli.py",
        "source_hash": "abc123",
        "design_hash": "def456",
        "generated": datetime(2026, 1, 1, 12, 0, 0),
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


class TestSerializeDesignFileFrontmatter:
    def test_yaml_frontmatter_delimiters(self) -> None:
        result = serialize_design_file(_design_file())
        assert result.startswith("---\n")
        lines = result.split("\n")
        closing_idx = lines.index("---", 1)
        assert closing_idx > 1

    def test_frontmatter_description(self) -> None:
        result = serialize_design_file(_design_file())
        assert "description: CLI entry point for the lexi command." in result

    def test_frontmatter_updated_by_default(self) -> None:
        result = serialize_design_file(_design_file())
        assert "updated_by: archivist" in result

    def test_frontmatter_updated_by_agent(self) -> None:
        df = _design_file(frontmatter=_frontmatter(updated_by="agent"))
        result = serialize_design_file(df)
        assert "updated_by: agent" in result


class TestSerializeDesignFileFrontmatterStatus:
    """Tests for status and deprecation fields in serialized frontmatter (Task 2.1)."""

    def test_frontmatter_includes_status_active(self) -> None:
        result = serialize_design_file(_design_file())
        assert "status: active" in result

    def test_frontmatter_includes_status_deprecated(self) -> None:
        df = _design_file(frontmatter=_frontmatter(status="deprecated"))
        result = serialize_design_file(df)
        assert "status: deprecated" in result

    def test_frontmatter_includes_status_unlinked(self) -> None:
        df = _design_file(frontmatter=_frontmatter(status="unlinked"))
        result = serialize_design_file(df)
        assert "status: unlinked" in result

    def test_deprecated_at_omitted_when_none(self) -> None:
        result = serialize_design_file(_design_file())
        assert "deprecated_at" not in result

    def test_deprecated_reason_omitted_when_none(self) -> None:
        result = serialize_design_file(_design_file())
        assert "deprecated_reason" not in result

    def test_deprecated_at_included_when_set(self) -> None:
        df = _design_file(
            frontmatter=_frontmatter(
                status="deprecated",
                deprecated_at=datetime(2026, 3, 1, 14, 30, 0),
                deprecated_reason="source_deleted",
            )
        )
        result = serialize_design_file(df)
        assert "deprecated_at:" in result
        assert "2026-03-01T14:30:00" in result

    def test_deprecated_reason_included_when_set(self) -> None:
        df = _design_file(
            frontmatter=_frontmatter(
                status="deprecated",
                deprecated_at=datetime(2026, 3, 1, 14, 30, 0),
                deprecated_reason="source_deleted",
            )
        )
        result = serialize_design_file(df)
        assert "deprecated_reason: source_deleted" in result

    def test_deprecated_reason_source_renamed(self) -> None:
        df = _design_file(
            frontmatter=_frontmatter(
                status="deprecated",
                deprecated_at=datetime(2026, 3, 1, 14, 30, 0),
                deprecated_reason="source_renamed",
            )
        )
        result = serialize_design_file(df)
        assert "deprecated_reason: source_renamed" in result

    def test_deprecated_reason_manual(self) -> None:
        df = _design_file(
            frontmatter=_frontmatter(
                status="deprecated",
                deprecated_at=datetime(2026, 3, 1, 14, 30, 0),
                deprecated_reason="manual",
            )
        )
        result = serialize_design_file(df)
        assert "deprecated_reason: manual" in result


class TestSerializeDesignFileStructure:
    def test_h1_heading_with_source_path(self) -> None:
        result = serialize_design_file(_design_file())
        assert "# src/lexibrary/cli.py\n" in result

    def test_interface_contract_section(self) -> None:
        result = serialize_design_file(_design_file())
        assert "## Interface Contract" in result
        assert "```python" in result
        assert "def main() -> None: ..." in result

    def test_interface_contract_fenced_block_closed(self) -> None:
        result = serialize_design_file(_design_file())
        # Should have both opening and closing fences
        assert result.count("```python") == 1
        # closing ``` after opening
        ic_idx = result.index("```python")
        rest = result[ic_idx + 9 :]
        assert "```" in rest

    def test_dependencies_section_empty(self) -> None:
        result = serialize_design_file(_design_file())
        assert "## Dependencies" in result
        deps_body = result.split("## Dependencies")[1].split("##")[0]
        assert "(none)" in deps_body

    def test_dependencies_section_populated(self) -> None:
        df = _design_file(dependencies=["src/lexibrary/config/schema.py"])
        result = serialize_design_file(df)
        assert "- src/lexibrary/config/schema.py" in result

    def test_dependents_section_empty(self) -> None:
        result = serialize_design_file(_design_file())
        assert "## Dependents" in result
        dep_body = result.split("## Dependents")[1].split("##")[0]
        assert "(none)" in dep_body

    def test_dependents_section_populated(self) -> None:
        df = _design_file(dependents=["src/lexibrary/__main__.py"])
        result = serialize_design_file(df)
        assert "- src/lexibrary/__main__.py" in result

    def test_output_ends_with_trailing_newline(self) -> None:
        result = serialize_design_file(_design_file())
        assert result.endswith("\n")


class TestSerializeDesignFileDependentsAnnotation:
    """Tests for D-070 annotation in the Dependents section."""

    def test_annotation_present_with_empty_dependents(self) -> None:
        """Annotation appears after Dependents heading even with no dependents (task 1.2)."""
        result = serialize_design_file(_design_file())
        dep_body = result.split("## Dependents")[1].split("##")[0]
        assert "*(see `lexi lookup` for live reverse references)*" in dep_body
        assert "(none)" in dep_body

    def test_annotation_before_none_marker(self) -> None:
        """Annotation appears before the (none) marker in empty dependents."""
        result = serialize_design_file(_design_file())
        dep_body = result.split("## Dependents")[1].split("##")[0]
        annotation_idx = dep_body.index("*(see `lexi lookup` for live reverse references)*")
        none_idx = dep_body.index("(none)")
        assert annotation_idx < none_idx

    def test_annotation_present_with_non_empty_dependents(self) -> None:
        """Annotation appears alongside populated dependents list (task 1.3)."""
        df = _design_file(dependents=["src/lexibrary/__main__.py", "src/lexibrary/cli.py"])
        result = serialize_design_file(df)
        dep_body = result.split("## Dependents")[1].split("##")[0]
        assert "*(see `lexi lookup` for live reverse references)*" in dep_body
        assert "- src/lexibrary/__main__.py" in dep_body
        assert "- src/lexibrary/cli.py" in dep_body

    def test_annotation_before_bullet_items(self) -> None:
        """Annotation appears before the bullet items when dependents exist."""
        df = _design_file(dependents=["src/lexibrary/__main__.py"])
        result = serialize_design_file(df)
        dep_body = result.split("## Dependents")[1].split("##")[0]
        annotation_idx = dep_body.index("*(see `lexi lookup` for live reverse references)*")
        bullet_idx = dep_body.index("- src/lexibrary/__main__.py")
        assert annotation_idx < bullet_idx


class TestSerializeDesignFileOptionalSections:
    def test_optional_sections_omitted_when_empty(self) -> None:
        result = serialize_design_file(_design_file())
        assert "## Tests" not in result
        assert "## Complexity Warning" not in result
        assert "## Wikilinks" not in result
        assert "## Tags" not in result
        assert "## Stack" not in result

    def test_tests_section_included_when_set(self) -> None:
        df = _design_file(tests="See tests/test_cli.py")
        result = serialize_design_file(df)
        assert "## Tests" in result
        assert "See tests/test_cli.py" in result

    def test_complexity_warning_included(self) -> None:
        df = _design_file(complexity_warning="High cyclomatic complexity.")
        result = serialize_design_file(df)
        assert "## Complexity Warning" in result
        assert "High cyclomatic complexity." in result

    def test_wikilinks_included(self) -> None:
        df = _design_file(wikilinks=["[[Config]]", "[[LLMService]]"])
        result = serialize_design_file(df)
        assert "## Wikilinks" in result
        assert "- [[Config]]" in result
        assert "- [[LLMService]]" in result

    def test_tags_included(self) -> None:
        df = _design_file(tags=["cli", "entry-point"])
        result = serialize_design_file(df)
        assert "## Tags" in result
        assert "- cli" in result
        assert "- entry-point" in result

    def test_stack_refs_included(self) -> None:
        df = _design_file(stack_refs=["ST-01", "ST-02"])
        result = serialize_design_file(df)
        assert "## Stack" in result
        assert "- ST-01" in result
        assert "- ST-02" in result


class TestSerializeDesignFileFooter:
    def test_footer_present(self) -> None:
        result = serialize_design_file(_design_file())
        assert "<!-- lexibrary:meta" in result
        assert "-->" in result

    def test_footer_contains_required_fields(self) -> None:
        result = serialize_design_file(_design_file())
        assert "source: src/lexibrary/cli.py" in result
        assert "source_hash: abc123" in result
        assert "design_hash:" in result
        assert "generated:" in result
        assert "generator: lexibrary-v2" in result

    def test_footer_interface_hash_omitted_when_none(self) -> None:
        result = serialize_design_file(_design_file())
        assert "interface_hash" not in result

    def test_footer_interface_hash_included_when_set(self) -> None:
        df = _design_file(metadata=_meta(interface_hash="ifhash999"))
        result = serialize_design_file(df)
        assert "interface_hash: ifhash999" in result

    def test_design_hash_is_sha256_hex(self) -> None:
        result = serialize_design_file(_design_file())
        # Extract design_hash value
        for line in result.splitlines():
            if line.startswith("design_hash:"):
                value = line.split(": ", 1)[1].strip()
                assert len(value) == 64
                assert all(c in "0123456789abcdef" for c in value)
                break
        else:
            raise AssertionError("design_hash not found in footer")

    def test_footer_multiline_format(self) -> None:
        result = serialize_design_file(_design_file())
        # Footer should span multiple lines (key: value pairs)
        footer_start = result.index("<!-- lexibrary:meta")
        footer_end = result.index("-->", footer_start)
        footer_content = result[footer_start:footer_end]
        assert "\n" in footer_content

    def test_language_tag_python(self) -> None:
        df = _design_file(source_path="src/foo.py")
        result = serialize_design_file(df)
        assert "```python" in result

    def test_language_tag_typescript(self) -> None:
        df = _design_file(source_path="src/foo.ts")
        result = serialize_design_file(df)
        assert "```typescript" in result

    def test_language_tag_unknown_defaults_to_text(self) -> None:
        df = _design_file(source_path="src/foo.xyz")
        result = serialize_design_file(df)
        assert "```text" in result


class TestSerializeDesignFileWikilinkBrackets:
    """Tests for wikilink [[bracket]] wrapping in serializer (Task 5.3)."""

    def test_unbracketed_wikilinks_get_brackets(self) -> None:
        """Wikilinks stored without brackets are wrapped in [[]] on output."""
        df = _design_file(wikilinks=["Config", "LLMService"])
        result = serialize_design_file(df)
        assert "- [[Config]]" in result
        assert "- [[LLMService]]" in result

    def test_already_bracketed_wikilinks_not_double_wrapped(self) -> None:
        """Wikilinks already in [[brackets]] are not double-wrapped."""
        df = _design_file(wikilinks=["[[Config]]", "[[LLMService]]"])
        result = serialize_design_file(df)
        assert "- [[Config]]" in result
        assert "- [[LLMService]]" in result
        # Ensure no double-wrapping
        assert "[[[[" not in result
        assert "]]]]" not in result

    def test_mixed_bracketed_and_unbracketed(self) -> None:
        """Mix of bracketed and unbracketed wikilinks both serialize correctly."""
        df = _design_file(wikilinks=["Config", "[[LLMService]]"])
        result = serialize_design_file(df)
        assert "- [[Config]]" in result
        assert "- [[LLMService]]" in result
        assert "[[[[" not in result

    def test_single_unbracketed_wikilink(self) -> None:
        """A single unbracketed wikilink is correctly wrapped."""
        df = _design_file(wikilinks=["ErrorHandling"])
        result = serialize_design_file(df)
        assert "- [[ErrorHandling]]" in result

    def test_empty_wikilinks_no_section(self) -> None:
        """Empty wikilinks list produces no Wikilinks section."""
        df = _design_file(wikilinks=[])
        result = serialize_design_file(df)
        assert "## Wikilinks" not in result


class TestSerializeDesignFileNewlineCollapse:
    """Regression tests for newline collapse in description and sort_keys=False."""

    def test_description_newlines_collapsed(self, tmp_path: Path) -> None:
        """A description containing literal newlines is collapsed to a single line
        during serialization, and round-trips correctly."""
        # (a) Create a DesignFile with a ~200 char description containing literal \n
        long_desc = (
            "Provides the main entry point for the lexi command-line interface,\n"
            "including argument parsing, subcommand dispatch, and error handling\n"
            "for all agent-facing operations. Also initializes logging and\n"
            "validates the project root before delegating to service modules."
        )
        assert len(long_desc) > 200
        assert "\n" in long_desc

        df = _design_file(frontmatter=_frontmatter(description=long_desc))

        # (b) Serialize
        content = serialize_design_file(df)

        # (c) Write to disk and parse the YAML frontmatter
        f = tmp_path / "design.md"
        f.write_text(content)
        parsed = parse_design_file(f)
        assert parsed is not None

        # (d) Assert id matches ^DS-\d{3,}$
        assert re.match(r"^DS-\d{3,}$", parsed.frontmatter.id)

        # (e) Assert description contains no newline characters
        assert "\n" not in parsed.frontmatter.description

        # (f) Round-trip integrity: re-serialize and re-parse produce equivalent data
        content2 = serialize_design_file(parsed)
        f2 = tmp_path / "design2.md"
        f2.write_text(content2)
        parsed2 = parse_design_file(f2)
        assert parsed2 is not None
        assert parsed2.frontmatter.description == parsed.frontmatter.description
        assert parsed2.frontmatter.id == parsed.frontmatter.id
        assert parsed2.frontmatter.updated_by == parsed.frontmatter.updated_by
        assert parsed2.frontmatter.status == parsed.frontmatter.status
        assert parsed2.source_path == parsed.source_path
        assert parsed2.interface_contract == parsed.interface_contract

    def test_description_without_newlines_unchanged(self) -> None:
        """A description without newlines passes through serialization unchanged."""
        desc = "CLI entry point for the lexi command."
        df = _design_file(frontmatter=_frontmatter(description=desc))
        content = serialize_design_file(df)
        assert f"description: {desc}" in content

    def test_sort_keys_false_preserves_field_order(self) -> None:
        """Frontmatter fields appear in insertion order (description first, not sorted)."""
        df = _design_file()
        content = serialize_design_file(df)
        lines = content.split("\n")
        # Find frontmatter lines between --- delimiters
        fm_start = lines.index("---") + 1
        fm_end = lines.index("---", fm_start)
        fm_lines = lines[fm_start:fm_end]
        # First field should be description (insertion order), not id (alphabetical)
        first_key = fm_lines[0].split(":")[0]
        assert first_key == "description"
