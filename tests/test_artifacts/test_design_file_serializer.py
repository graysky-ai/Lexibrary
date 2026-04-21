"""Tests for design file serializer."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from lexibrary.artifacts.design_file import (
    CallPathNote,
    DataFlowNote,
    DesignFile,
    DesignFileFrontmatter,
    EnumNote,
    StalenessMetadata,
)
from lexibrary.artifacts.design_file_parser import parse_design_file
from lexibrary.artifacts.design_file_serializer import serialize_design_file


def _meta(**overrides: object) -> StalenessMetadata:
    base: dict[str, object] = {
        "source": "src/lexibrary/cli.py",
        "source_hash": "abc123",
        "design_hash": "def456",
        "generated": datetime(2026, 1, 1, 12, 0, 0),
        "generator": "lexibrary-v2",
    }
    base.update(overrides)
    return StalenessMetadata(**base)


def _frontmatter(**overrides: object) -> DesignFileFrontmatter:
    base: dict[str, object] = {
        "description": "CLI entry point for the lexi command.",
        "id": "DS-001",
    }
    base.update(overrides)
    return DesignFileFrontmatter(**base)


def _design_file(**overrides: object) -> DesignFile:
    base: dict[str, object] = {
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

    def test_frontmatter_omits_status_active(self) -> None:
        """Default ``status: active`` SHALL be omitted from the serialized
        frontmatter (§1.4 — design-cleanup). The parser defaults a missing
        ``status`` key to ``"active"`` so on-disk absence is equivalent."""
        result = serialize_design_file(_design_file())
        # Extract just the YAML frontmatter block (between the first two "---" lines).
        lines = result.split("\n")
        closing_idx = lines.index("---", 1)
        fm_block = "\n".join(lines[: closing_idx + 1])
        assert "status:" not in fm_block

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


class TestSerializeDesignFileDependentsNoHint:
    """§1.2: The `*(see `lexi lookup` ...)*` hint line SHALL NOT appear in
    the Dependents section of freshly serialized output. (Previously asserted
    as D-070 annotation presence; the hint was static noise on every design
    file and was removed in §1.2.)"""

    def test_no_hint_with_empty_dependents(self) -> None:
        """With no dependents, the section is heading + (none) only — no hint."""
        result = serialize_design_file(_design_file())
        dep_body = result.split("## Dependents")[1].split("##")[0]
        assert "*(see `lexi lookup` for live reverse references)*" not in dep_body
        assert "(none)" in dep_body

    def test_no_hint_with_non_empty_dependents(self) -> None:
        """With dependents, the bullet list is emitted directly — no hint line."""
        df = _design_file(dependents=["src/lexibrary/__main__.py", "src/lexibrary/cli.py"])
        result = serialize_design_file(df)
        dep_body = result.split("## Dependents")[1].split("##")[0]
        assert "*(see `lexi lookup` for live reverse references)*" not in dep_body
        assert "- src/lexibrary/__main__.py" in dep_body
        assert "- src/lexibrary/cli.py" in dep_body


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
        # Extract design_hash value from the compact inline footer (§1.3):
        # ``<!-- lexibrary:meta {..., design_hash: <hex>, ...} -->``.
        footer_start = result.index("<!-- lexibrary:meta")
        footer_end = result.index("-->", footer_start)
        footer = result[footer_start:footer_end]
        marker = "design_hash: "
        idx = footer.index(marker)
        value = footer[idx + len(marker) :].split(",", 1)[0].strip()
        assert len(value) == 64
        assert all(c in "0123456789abcdef" for c in value)

    def test_footer_single_line_inline_format(self) -> None:
        """§1.3: the meta footer MUST be a single-line inline YAML mapping —
        ``<!-- lexibrary:meta {k: v, ...} -->`` — with no embedded newlines."""
        result = serialize_design_file(_design_file())
        footer_start = result.index("<!-- lexibrary:meta")
        footer_end = result.index("-->", footer_start) + len("-->")
        footer_content = result[footer_start:footer_end]
        assert "\n" not in footer_content
        assert footer_content.startswith("<!-- lexibrary:meta {")
        assert footer_content.endswith("} -->")

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


class TestSerializeDesignFileEnrichment:
    """Tests for Enums & constants and Call paths enrichment sections (Task 6.5)."""

    def test_serializer_emits_enum_notes(self) -> None:
        """Serializer emits `## Enums & constants` with entries and Values lines."""
        df = _design_file(
            enum_notes=[
                EnumNote(
                    name="BuildStatus",
                    role="Tracks pipeline execution state.",
                    values=["PENDING", "RUNNING", "FAILED", "SUCCESS"],
                ),
                EnumNote(
                    name="MAX_RETRIES",
                    role="Upper bound on retry attempts before failing a job.",
                    values=["3"],
                ),
            ]
        )
        result = serialize_design_file(df)
        assert "## Enums & constants" in result
        assert "- **BuildStatus** — Tracks pipeline execution state." in result
        assert "  Values: PENDING, RUNNING, FAILED, SUCCESS." in result
        assert "- **MAX_RETRIES** — Upper bound on retry attempts before failing a job." in result
        assert "  Values: 3." in result

    def test_serializer_emits_call_paths(self) -> None:
        """Serializer emits `## Call paths` with entries and Key hops lines."""
        df = _design_file(
            call_path_notes=[
                CallPathNote(
                    entry="update_project()",
                    narrative=(
                        "Orchestrates a full project build: discovers source files, "
                        "regenerates changed design files, refreshes aindexes, rebuilds "
                        "the link graph, then the symbol graph."
                    ),
                    key_hops=[
                        "discover_source_files",
                        "update_file",
                        "build_index",
                        "build_symbol_graph",
                    ],
                )
            ]
        )
        result = serialize_design_file(df)
        assert "## Call paths" in result
        assert "- **update_project()** — Orchestrates a full project build" in result
        assert (
            "  Key hops: discover_source_files, update_file, build_index, build_symbol_graph."
        ) in result

    def test_serializer_omits_empty_enrichment_sections(self) -> None:
        """Empty enum_notes / call_path_notes lists produce no section headings."""
        df = _design_file(enum_notes=[], call_path_notes=[])
        result = serialize_design_file(df)
        assert "## Enums & constants" not in result
        assert "## Call paths" not in result

    def test_serializer_omits_values_line_when_no_values(self) -> None:
        """An enum note with an empty values list should emit only the header line."""
        df = _design_file(
            enum_notes=[
                EnumNote(
                    name="Marker",
                    role="A sentinel used to signal completion.",
                    values=[],
                )
            ]
        )
        result = serialize_design_file(df)
        assert "## Enums & constants" in result
        assert "- **Marker** — A sentinel used to signal completion." in result
        # Confirm no Values line was emitted for this entry
        enum_body = result.split("## Enums & constants")[1].split("##")[0]
        assert "Values:" not in enum_body

    def test_serializer_omits_key_hops_line_when_no_hops(self) -> None:
        """A call-path note with no key hops should emit only the header line."""
        df = _design_file(
            call_path_notes=[
                CallPathNote(
                    entry="noop()",
                    narrative="A no-op for testing.",
                    key_hops=[],
                )
            ]
        )
        result = serialize_design_file(df)
        assert "## Call paths" in result
        assert "- **noop()** — A no-op for testing." in result
        call_body = result.split("## Call paths")[1].split("##")[0]
        assert "Key hops:" not in call_body

    def test_enrichment_sections_placed_between_complexity_and_wikilinks(self) -> None:
        """Enum/Call-path sections sit after Complexity Warning and before Wikilinks."""
        df = _design_file(
            complexity_warning="High cyclomatic complexity.",
            enum_notes=[
                EnumNote(
                    name="BuildStatus",
                    role="Tracks pipeline execution state.",
                    values=["PENDING", "SUCCESS"],
                )
            ],
            call_path_notes=[
                CallPathNote(
                    entry="run()",
                    narrative="Kicks off a build.",
                    key_hops=["prepare", "execute"],
                )
            ],
            wikilinks=["Config"],
        )
        result = serialize_design_file(df)
        complexity_idx = result.index("## Complexity Warning")
        enums_idx = result.index("## Enums & constants")
        calls_idx = result.index("## Call paths")
        wikilinks_idx = result.index("## Wikilinks")
        assert complexity_idx < enums_idx < calls_idx < wikilinks_idx

    def test_roundtrip_design_file_with_enrichment(self, tmp_path: Path) -> None:
        """Serialize → write → parse preserves enrichment fields."""
        df = _design_file(
            enum_notes=[
                EnumNote(
                    name="BuildStatus",
                    role="Tracks pipeline execution state.",
                    values=["PENDING", "RUNNING", "FAILED", "SUCCESS"],
                ),
                EnumNote(
                    name="MAX_RETRIES",
                    role="Upper bound on retry attempts before failing a job.",
                    values=["3"],
                ),
            ],
            call_path_notes=[
                CallPathNote(
                    entry="update_project()",
                    narrative="Orchestrates a full project build.",
                    key_hops=[
                        "discover_source_files",
                        "update_file",
                        "build_index",
                        "build_symbol_graph",
                    ],
                )
            ],
        )
        content = serialize_design_file(df)
        f = tmp_path / "roundtrip.md"
        f.write_text(content)
        parsed = parse_design_file(f)
        assert parsed is not None
        assert len(parsed.enum_notes) == 2
        assert parsed.enum_notes[0].name == "BuildStatus"
        assert parsed.enum_notes[0].role == "Tracks pipeline execution state."
        assert parsed.enum_notes[0].values == ["PENDING", "RUNNING", "FAILED", "SUCCESS"]
        assert parsed.enum_notes[1].name == "MAX_RETRIES"
        assert parsed.enum_notes[1].values == ["3"]
        assert len(parsed.call_path_notes) == 1
        assert parsed.call_path_notes[0].entry == "update_project()"
        assert parsed.call_path_notes[0].narrative == "Orchestrates a full project build."
        assert parsed.call_path_notes[0].key_hops == [
            "discover_source_files",
            "update_file",
            "build_index",
            "build_symbol_graph",
        ]


class TestSerializeDesignFileDataFlows:
    """Tests for `## Data flows` section serialization and round-trip."""

    def test_serializer_emits_data_flows(self) -> None:
        """Serializer emits `## Data flows` with correct bullet format."""
        df = _design_file(
            data_flow_notes=[
                DataFlowNote(
                    parameter="changed_paths",
                    location="build_index()",
                    effect=(
                        "`None` triggers a full build; a non-None list triggers incremental update."
                    ),
                ),
                DataFlowNote(
                    parameter="config",
                    location="render()",
                    effect="Controls output format and verbosity level.",
                ),
            ]
        )
        result = serialize_design_file(df)
        assert "## Data flows" in result
        assert (
            "- **changed_paths** in **build_index()** \u2014 "
            "`None` triggers a full build;"
            " a non-None list triggers incremental update."
        ) in result
        assert (
            "- **config** in **render()** — Controls output format and verbosity level."
        ) in result

    def test_serializer_omits_empty_data_flows(self) -> None:
        """Empty data_flow_notes list produces no Data flows section."""
        df = _design_file(data_flow_notes=[])
        result = serialize_design_file(df)
        assert "## Data flows" not in result

    def test_data_flows_placed_after_call_paths_before_wikilinks(self) -> None:
        """Data flows section sits after Call paths and before Wikilinks."""
        df = _design_file(
            call_path_notes=[
                CallPathNote(
                    entry="run()",
                    narrative="Kicks off a build.",
                    key_hops=["prepare", "execute"],
                )
            ],
            data_flow_notes=[
                DataFlowNote(
                    parameter="config",
                    location="run()",
                    effect="Selects build mode.",
                ),
            ],
            wikilinks=["Config"],
        )
        result = serialize_design_file(df)
        calls_idx = result.index("## Call paths")
        flows_idx = result.index("## Data flows")
        wikilinks_idx = result.index("## Wikilinks")
        assert calls_idx < flows_idx < wikilinks_idx

    def test_roundtrip_with_data_flows(self, tmp_path: Path) -> None:
        """Serialize -> write -> parse preserves data flow notes."""
        df = _design_file(
            data_flow_notes=[
                DataFlowNote(
                    parameter="changed_paths",
                    location="build_index()",
                    effect=(
                        "`None` triggers a full build; a non-None list triggers incremental update."
                    ),
                ),
                DataFlowNote(
                    parameter="config",
                    location="render()",
                    effect="Controls output format and verbosity level.",
                ),
            ]
        )
        content = serialize_design_file(df)
        f = tmp_path / "roundtrip.md"
        f.write_text(content)
        parsed = parse_design_file(f)
        assert parsed is not None
        assert len(parsed.data_flow_notes) == 2
        assert parsed.data_flow_notes[0].parameter == "changed_paths"
        assert parsed.data_flow_notes[0].location == "build_index()"
        assert "`None` triggers a full build" in parsed.data_flow_notes[0].effect
        assert parsed.data_flow_notes[1].parameter == "config"
        assert parsed.data_flow_notes[1].location == "render()"
        assert "output format" in parsed.data_flow_notes[1].effect

    def test_roundtrip_with_preserved_sections_and_data_flows(self, tmp_path: Path) -> None:
        """Round-trip preserves data flows alongside preserved sections and ordering is stable."""
        df = _design_file(
            preserved_sections={"Agent Notes": "Some agent-authored content."},
            call_path_notes=[
                CallPathNote(
                    entry="run()",
                    narrative="Kicks off a build.",
                    key_hops=["prepare"],
                )
            ],
            data_flow_notes=[
                DataFlowNote(
                    parameter="mode",
                    location="run()",
                    effect="Selects between full and incremental build.",
                ),
            ],
            wikilinks=["Config"],
        )
        content = serialize_design_file(df)
        f = tmp_path / "roundtrip_preserved.md"
        f.write_text(content)
        parsed = parse_design_file(f)
        assert parsed is not None

        # Data flow notes preserved
        assert len(parsed.data_flow_notes) == 1
        assert parsed.data_flow_notes[0].parameter == "mode"
        assert parsed.data_flow_notes[0].location == "run()"

        # Preserved sections preserved
        assert "Agent Notes" in parsed.preserved_sections
        assert parsed.preserved_sections["Agent Notes"] == "Some agent-authored content."

        # Call path notes preserved
        assert len(parsed.call_path_notes) == 1

        # Wikilinks preserved
        assert parsed.wikilinks == ["Config"]

        # Re-serialize and verify ordering is stable
        content2 = serialize_design_file(parsed)
        f2 = tmp_path / "roundtrip_preserved_2.md"
        f2.write_text(content2)
        parsed2 = parse_design_file(f2)
        assert parsed2 is not None
        assert len(parsed2.data_flow_notes) == 1
        assert parsed2.data_flow_notes[0].parameter == "mode"

    def test_roundtrip_without_data_flows(self, tmp_path: Path) -> None:
        """Round-trip of a file without data flows does not introduce the section."""
        df = _design_file(data_flow_notes=[])
        content = serialize_design_file(df)
        f = tmp_path / "roundtrip_no_flows.md"
        f.write_text(content)
        parsed = parse_design_file(f)
        assert parsed is not None
        assert parsed.data_flow_notes == []
        assert "## Data flows" not in content
