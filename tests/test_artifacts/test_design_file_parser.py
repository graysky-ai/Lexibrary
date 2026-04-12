"""Tests for design file parser."""

from __future__ import annotations

from pathlib import Path

from lexibrary.artifacts.design_file_parser import (
    parse_design_file,
    parse_design_file_frontmatter,
    parse_design_file_metadata,
)

_FULL_DESIGN_FILE = """\
---
description: CLI entry point for the lexi command.
id: DS-011
updated_by: archivist
---

# src/lexibrary/cli.py

## Interface Contract

```python
def main() -> None: ...
```

## Dependencies

- src/lexibrary/config/schema.py

## Dependents

(none)

<!-- lexibrary:meta
source: src/lexibrary/cli.py
source_hash: abc123
design_hash: def456
generated: 2026-01-01T12:00:00
generator: lexibrary-v2
-->
"""

_FULL_WITH_OPTIONAL = """\
---
description: Full design file with all sections.
id: DS-010
updated_by: agent
---

# src/foo.py

## Interface Contract

```python
class Foo: ...
```

## Dependencies

(none)

## Dependents

- src/bar.py

## Tests

See tests/test_foo.py

## Complexity Warning

High cyclomatic complexity.

## Wikilinks

- [[Config]]

## Tags

- core

## Guardrails

- G-01

<!-- lexibrary:meta
source: src/foo.py
source_hash: src123
interface_hash: iface456
design_hash: dsgn789
generated: 2026-06-15T08:30:00
generator: lexibrary-v2
-->
"""

_NO_FOOTER = """\
---
description: A file without footer.
id: DS-009
updated_by: archivist
---

# src/bar.py

## Interface Contract

```python
pass
```

## Dependencies

(none)

## Dependents

(none)
"""

_CORRUPT_FOOTER = """\
---
description: Corrupt footer file.
id: DS-008
updated_by: archivist
---

# src/baz.py

## Interface Contract

```python
pass
```

## Dependencies

(none)

## Dependents

(none)

<!-- lexibrary:meta
not_a_valid_key_value_pair
-->
"""


class TestParseDesignFileMetadata:
    def test_extracts_metadata_from_valid_footer(self, tmp_path: Path) -> None:
        f = tmp_path / "design.md"
        f.write_text(_FULL_DESIGN_FILE)
        meta = parse_design_file_metadata(f)
        assert meta is not None
        assert meta.source == "src/lexibrary/cli.py"
        assert meta.source_hash == "abc123"
        assert meta.design_hash == "def456"
        assert meta.generator == "lexibrary-v2"

    def test_returns_none_for_nonexistent_file(self, tmp_path: Path) -> None:
        result = parse_design_file_metadata(tmp_path / "missing.md")
        assert result is None

    def test_returns_none_when_no_footer(self, tmp_path: Path) -> None:
        f = tmp_path / "no_footer.md"
        f.write_text(_NO_FOOTER)
        assert parse_design_file_metadata(f) is None

    def test_returns_none_for_corrupt_footer(self, tmp_path: Path) -> None:
        f = tmp_path / "corrupt.md"
        f.write_text(_CORRUPT_FOOTER)
        assert parse_design_file_metadata(f) is None

    def test_interface_hash_optional(self, tmp_path: Path) -> None:
        f = tmp_path / "design.md"
        f.write_text(_FULL_DESIGN_FILE)
        meta = parse_design_file_metadata(f)
        assert meta is not None
        assert meta.interface_hash is None

    def test_interface_hash_parsed_when_present(self, tmp_path: Path) -> None:
        f = tmp_path / "full.md"
        f.write_text(_FULL_WITH_OPTIONAL)
        meta = parse_design_file_metadata(f)
        assert meta is not None
        assert meta.interface_hash == "iface456"


class TestParseDesignFileFrontmatter:
    def test_extracts_description(self, tmp_path: Path) -> None:
        f = tmp_path / "design.md"
        f.write_text(_FULL_DESIGN_FILE)
        fm = parse_design_file_frontmatter(f)
        assert fm is not None
        assert fm.description == "CLI entry point for the lexi command."

    def test_extracts_updated_by(self, tmp_path: Path) -> None:
        f = tmp_path / "design.md"
        f.write_text(_FULL_WITH_OPTIONAL)
        fm = parse_design_file_frontmatter(f)
        assert fm is not None
        assert fm.updated_by == "agent"

    def test_updated_by_defaults_to_archivist(self, tmp_path: Path) -> None:
        content = "---\ndescription: No updated_by field.\nid: DS-099\n---\n\n# src/x.py\n"
        f = tmp_path / "design.md"
        f.write_text(content)
        fm = parse_design_file_frontmatter(f)
        assert fm is not None
        assert fm.updated_by == "archivist"

    def test_returns_none_for_nonexistent_file(self, tmp_path: Path) -> None:
        assert parse_design_file_frontmatter(tmp_path / "missing.md") is None

    def test_returns_none_when_no_frontmatter(self, tmp_path: Path) -> None:
        f = tmp_path / "no_fm.md"
        f.write_text("# Just a heading\n\nNo frontmatter.\n")
        assert parse_design_file_frontmatter(f) is None


class TestParseDesignFileFull:
    def test_parse_full_design_file(self, tmp_path: Path) -> None:
        f = tmp_path / "design.md"
        f.write_text(_FULL_DESIGN_FILE)
        df = parse_design_file(f)
        assert df is not None
        assert df.source_path == "src/lexibrary/cli.py"
        assert df.frontmatter.description == "CLI entry point for the lexi command."
        assert df.frontmatter.updated_by == "archivist"
        assert df.interface_contract == "def main() -> None: ..."
        assert df.dependencies == ["src/lexibrary/config/schema.py"]
        assert df.dependents == []
        assert df.metadata.source_hash == "abc123"

    def test_parse_file_with_all_optional_sections(self, tmp_path: Path) -> None:
        f = tmp_path / "full.md"
        f.write_text(_FULL_WITH_OPTIONAL)
        df = parse_design_file(f)
        assert df is not None
        assert df.tests == "See tests/test_foo.py"
        assert df.complexity_warning == "High cyclomatic complexity."
        assert df.wikilinks == ["Config"]
        assert df.tags == ["core"]
        assert df.stack_refs == ["G-01"]
        assert df.dependents == ["src/bar.py"]

    def test_returns_none_for_nonexistent_file(self, tmp_path: Path) -> None:
        assert parse_design_file(tmp_path / "missing.md") is None

    def test_returns_none_when_no_footer(self, tmp_path: Path) -> None:
        f = tmp_path / "no_footer.md"
        f.write_text(_NO_FOOTER)
        assert parse_design_file(f) is None

    def test_returns_none_for_corrupt_footer(self, tmp_path: Path) -> None:
        f = tmp_path / "corrupt.md"
        f.write_text(_CORRUPT_FOOTER)
        assert parse_design_file(f) is None

    def test_returns_none_when_no_frontmatter(self, tmp_path: Path) -> None:
        content = "# src/x.py\n\n## Interface Contract\n\n```python\npass\n```\n"
        f = tmp_path / "no_fm.md"
        f.write_text(content)
        assert parse_design_file(f) is None


class TestParseDesignFileFrontmatterStatus:
    """Tests for parsing status and deprecation fields from frontmatter (Task 2.2)."""

    _DEPRECATED_FRONTMATTER = """\
---
description: A deprecated file.
id: DS-007
updated_by: archivist
status: deprecated
deprecated_at: '2026-03-01T14:30:00'
deprecated_reason: source_deleted
---

# src/old_module.py

## Interface Contract

```python
pass
```

## Dependencies

(none)

## Dependents

(none)

<!-- lexibrary:meta
source: src/old_module.py
source_hash: abc123
design_hash: def456
generated: 2026-01-01T12:00:00
generator: lexibrary-v2
-->
"""

    _UNLINKED_FRONTMATTER = """\
---
description: An unlinked file.
id: DS-006
updated_by: archivist
status: unlinked
---

# src/maybe_deleted.py

## Interface Contract

```python
pass
```

## Dependencies

(none)

## Dependents

(none)

<!-- lexibrary:meta
source: src/maybe_deleted.py
source_hash: abc123
design_hash: def456
generated: 2026-01-01T12:00:00
generator: lexibrary-v2
-->
"""

    def test_parse_deprecated_status(self, tmp_path: Path) -> None:
        f = tmp_path / "deprecated.md"
        f.write_text(self._DEPRECATED_FRONTMATTER)
        df = parse_design_file(f)
        assert df is not None
        assert df.frontmatter.status == "deprecated"

    def test_parse_deprecated_at(self, tmp_path: Path) -> None:
        f = tmp_path / "deprecated.md"
        f.write_text(self._DEPRECATED_FRONTMATTER)
        df = parse_design_file(f)
        assert df is not None
        assert df.frontmatter.deprecated_at is not None
        assert df.frontmatter.deprecated_at.year == 2026
        assert df.frontmatter.deprecated_at.month == 3
        assert df.frontmatter.deprecated_at.day == 1

    def test_parse_deprecated_reason(self, tmp_path: Path) -> None:
        f = tmp_path / "deprecated.md"
        f.write_text(self._DEPRECATED_FRONTMATTER)
        df = parse_design_file(f)
        assert df is not None
        assert df.frontmatter.deprecated_reason == "source_deleted"

    def test_parse_unlinked_status(self, tmp_path: Path) -> None:
        f = tmp_path / "unlinked.md"
        f.write_text(self._UNLINKED_FRONTMATTER)
        df = parse_design_file(f)
        assert df is not None
        assert df.frontmatter.status == "unlinked"
        assert df.frontmatter.deprecated_at is None
        assert df.frontmatter.deprecated_reason is None

    def test_frontmatter_only_deprecated(self, tmp_path: Path) -> None:
        """parse_design_file_frontmatter also extracts deprecation fields."""
        f = tmp_path / "deprecated.md"
        f.write_text(self._DEPRECATED_FRONTMATTER)
        fm = parse_design_file_frontmatter(f)
        assert fm is not None
        assert fm.status == "deprecated"
        assert fm.deprecated_at is not None
        assert fm.deprecated_reason == "source_deleted"

    def test_frontmatter_only_unlinked(self, tmp_path: Path) -> None:
        f = tmp_path / "unlinked.md"
        f.write_text(self._UNLINKED_FRONTMATTER)
        fm = parse_design_file_frontmatter(f)
        assert fm is not None
        assert fm.status == "unlinked"
        assert fm.deprecated_at is None
        assert fm.deprecated_reason is None


class TestParseDesignFileLegacyBackwardCompat:
    """Tests for backward compat: parsing legacy files without status (Task 2.4)."""

    def test_legacy_file_defaults_status_to_active(self, tmp_path: Path) -> None:
        """Legacy design files without status field default to 'active'."""
        f = tmp_path / "design.md"
        f.write_text(_FULL_DESIGN_FILE)
        df = parse_design_file(f)
        assert df is not None
        assert df.frontmatter.status == "active"

    def test_legacy_file_defaults_deprecated_at_to_none(self, tmp_path: Path) -> None:
        f = tmp_path / "design.md"
        f.write_text(_FULL_DESIGN_FILE)
        df = parse_design_file(f)
        assert df is not None
        assert df.frontmatter.deprecated_at is None

    def test_legacy_file_defaults_deprecated_reason_to_none(self, tmp_path: Path) -> None:
        f = tmp_path / "design.md"
        f.write_text(_FULL_DESIGN_FILE)
        df = parse_design_file(f)
        assert df is not None
        assert df.frontmatter.deprecated_reason is None

    def test_legacy_frontmatter_only_defaults_status(self, tmp_path: Path) -> None:
        """parse_design_file_frontmatter also defaults status for legacy files."""
        f = tmp_path / "design.md"
        f.write_text(_FULL_DESIGN_FILE)
        fm = parse_design_file_frontmatter(f)
        assert fm is not None
        assert fm.status == "active"
        assert fm.deprecated_at is None
        assert fm.deprecated_reason is None

    _MINIMAL_LEGACY = """\
---
description: Minimal legacy.
id: DS-099
---

# src/x.py

## Interface Contract

```python
pass
```

## Dependencies

(none)

## Dependents

(none)

<!-- lexibrary:meta
source: src/x.py
source_hash: abc
design_hash: def
generated: 2026-01-01T12:00:00
generator: lexibrary-v2
-->
"""

    def test_legacy_file_no_updated_by_defaults_both(self, tmp_path: Path) -> None:
        """Legacy file without updated_by or status defaults both."""
        f = tmp_path / "minimal.md"
        f.write_text(self._MINIMAL_LEGACY)
        df = parse_design_file(f)
        assert df is not None
        assert df.frontmatter.updated_by == "archivist"
        assert df.frontmatter.status == "active"
        assert df.frontmatter.deprecated_at is None
        assert df.frontmatter.deprecated_reason is None


class TestParseDesignFileWikilinkBrackets:
    """Tests for wikilink [[bracket]] stripping and backward compatibility (Task 5.4)."""

    _BRACKETED_WIKILINKS = """\
---
description: File with bracketed wikilinks.
id: DS-005
updated_by: archivist
---

# src/example.py

## Interface Contract

```python
pass
```

## Dependencies

(none)

## Dependents

(none)

## Wikilinks

- [[Config]]
- [[LLMService]]

<!-- lexibrary:meta
source: src/example.py
source_hash: abc123
design_hash: def456
generated: 2026-01-01T12:00:00
generator: lexibrary-v2
-->
"""

    _UNBRACKETED_WIKILINKS = """\
---
description: File with unbracketed wikilinks (legacy format).
id: DS-004
updated_by: archivist
---

# src/legacy.py

## Interface Contract

```python
pass
```

## Dependencies

(none)

## Dependents

(none)

## Wikilinks

- Config
- LLMService

<!-- lexibrary:meta
source: src/legacy.py
source_hash: abc123
design_hash: def456
generated: 2026-01-01T12:00:00
generator: lexibrary-v2
-->
"""

    _MIXED_WIKILINKS = """\
---
description: File with mixed bracketed and unbracketed wikilinks.
id: DS-003
updated_by: archivist
---

# src/mixed.py

## Interface Contract

```python
pass
```

## Dependencies

(none)

## Dependents

(none)

## Wikilinks

- [[Config]]
- LLMService
- [[ErrorHandling]]

<!-- lexibrary:meta
source: src/mixed.py
source_hash: abc123
design_hash: def456
generated: 2026-01-01T12:00:00
generator: lexibrary-v2
-->
"""

    def test_bracketed_wikilinks_stripped(self, tmp_path: Path) -> None:
        """Parser strips [[]] brackets from wikilinks."""
        f = tmp_path / "bracketed.md"
        f.write_text(self._BRACKETED_WIKILINKS)
        df = parse_design_file(f)
        assert df is not None
        assert df.wikilinks == ["Config", "LLMService"]

    def test_unbracketed_wikilinks_backward_compatible(self, tmp_path: Path) -> None:
        """Parser handles legacy unbracketed wikilinks (no brackets to strip)."""
        f = tmp_path / "unbracketed.md"
        f.write_text(self._UNBRACKETED_WIKILINKS)
        df = parse_design_file(f)
        assert df is not None
        assert df.wikilinks == ["Config", "LLMService"]

    def test_mixed_wikilinks_handled(self, tmp_path: Path) -> None:
        """Parser handles mix of bracketed and unbracketed wikilinks."""
        f = tmp_path / "mixed.md"
        f.write_text(self._MIXED_WIKILINKS)
        df = parse_design_file(f)
        assert df is not None
        assert df.wikilinks == ["Config", "LLMService", "ErrorHandling"]

    def test_no_wikilinks_section_returns_empty_list(self, tmp_path: Path) -> None:
        """Files without a Wikilinks section return an empty list."""
        f = tmp_path / "design.md"
        f.write_text(_FULL_DESIGN_FILE)
        df = parse_design_file(f)
        assert df is not None
        assert df.wikilinks == []


class TestParseDesignFileStackRefs:
    """Tests for ## Stack section parsing and backward compat with ## Guardrails."""

    _WITH_STACK_SECTION = """\
---
description: File with Stack section.
id: DS-002
updated_by: archivist
---

# src/example.py

## Interface Contract

```python
pass
```

## Dependencies

(none)

## Dependents

(none)

## Stack

- ST-001
- ST-002

<!-- lexibrary:meta
source: src/example.py
source_hash: abc123
design_hash: def456
generated: 2026-01-01T12:00:00
generator: lexibrary-v2
-->
"""

    _WITH_GUARDRAILS_SECTION = """\
---
description: Legacy file with Guardrails section.
id: DS-001
updated_by: archivist
---

# src/legacy.py

## Interface Contract

```python
pass
```

## Dependencies

(none)

## Dependents

(none)

## Guardrails

- G-01
- G-02

<!-- lexibrary:meta
source: src/legacy.py
source_hash: abc123
design_hash: def456
generated: 2026-01-01T12:00:00
generator: lexibrary-v2
-->
"""

    def test_stack_section_parsed_into_stack_refs(self, tmp_path: Path) -> None:
        """New ## Stack section is parsed into stack_refs."""
        f = tmp_path / "stack.md"
        f.write_text(self._WITH_STACK_SECTION)
        df = parse_design_file(f)
        assert df is not None
        assert df.stack_refs == ["ST-001", "ST-002"]

    def test_guardrails_section_backward_compat(self, tmp_path: Path) -> None:
        """Legacy ## Guardrails section is parsed into stack_refs for backward compatibility."""
        f = tmp_path / "legacy.md"
        f.write_text(self._WITH_GUARDRAILS_SECTION)
        df = parse_design_file(f)
        assert df is not None
        assert df.stack_refs == ["G-01", "G-02"]

    def test_no_stack_section_returns_empty_list(self, tmp_path: Path) -> None:
        """Files without Stack or Guardrails section return empty stack_refs."""
        f = tmp_path / "design.md"
        f.write_text(_FULL_DESIGN_FILE)
        df = parse_design_file(f)
        assert df is not None
        assert df.stack_refs == []


class TestParseDesignFileEnrichment:
    """Tests for parsing Enums & constants and Call paths enrichment sections."""

    _WITH_ENUM_NOTES = """\
---
description: File with enum notes.
id: DS-100
updated_by: archivist
---

# src/lexibrary/status.py

## Interface Contract

```python
pass
```

## Dependencies

(none)

## Dependents

(none)

## Enums & constants

- **BuildStatus** — Tracks pipeline execution state.
  Values: PENDING, RUNNING, FAILED, SUCCESS.
- **MAX_RETRIES** — Upper bound on retry attempts before failing a job.
  Values: 3.

<!-- lexibrary:meta
source: src/lexibrary/status.py
source_hash: abc123
design_hash: def456
generated: 2026-01-01T12:00:00
generator: lexibrary-v2
-->
"""

    _WITH_CALL_PATHS = """\
---
description: File with call path notes.
id: DS-101
updated_by: archivist
---

# src/lexibrary/archivist/pipeline.py

## Interface Contract

```python
pass
```

## Dependencies

(none)

## Dependents

(none)

## Call paths

- **update_project()** — Orchestrates a full project build, rebuilding design files and graphs.
  Key hops: discover_source_files, update_file, build_index, build_symbol_graph.

<!-- lexibrary:meta
source: src/lexibrary/archivist/pipeline.py
source_hash: abc123
design_hash: def456
generated: 2026-01-01T12:00:00
generator: lexibrary-v2
-->
"""

    def test_parser_reads_enum_notes_section(self, tmp_path: Path) -> None:
        """Parser extracts multiple enum notes with names, roles, and values."""
        f = tmp_path / "enums.md"
        f.write_text(self._WITH_ENUM_NOTES)
        df = parse_design_file(f)
        assert df is not None
        assert len(df.enum_notes) == 2

        first = df.enum_notes[0]
        assert first.name == "BuildStatus"
        assert first.role == "Tracks pipeline execution state."
        assert first.values == ["PENDING", "RUNNING", "FAILED", "SUCCESS"]

        second = df.enum_notes[1]
        assert second.name == "MAX_RETRIES"
        assert second.role == "Upper bound on retry attempts before failing a job."
        assert second.values == ["3"]

    def test_parser_reads_call_paths_section(self, tmp_path: Path) -> None:
        """Parser extracts call path notes with entry, narrative, and key hops."""
        f = tmp_path / "call_paths.md"
        f.write_text(self._WITH_CALL_PATHS)
        df = parse_design_file(f)
        assert df is not None
        assert len(df.call_path_notes) == 1

        note = df.call_path_notes[0]
        assert note.entry == "update_project()"
        assert "Orchestrates a full project build" in note.narrative
        assert note.key_hops == [
            "discover_source_files",
            "update_file",
            "build_index",
            "build_symbol_graph",
        ]

    def test_parser_handles_missing_enrichment_sections(self, tmp_path: Path) -> None:
        """Parser returns empty lists when enrichment sections are absent."""
        f = tmp_path / "no_enrichment.md"
        f.write_text(_FULL_DESIGN_FILE)
        df = parse_design_file(f)
        assert df is not None
        assert df.enum_notes == []
        assert df.call_path_notes == []

    def test_parser_does_not_treat_enrichment_as_preserved_section(self, tmp_path: Path) -> None:
        """Enums & constants and Call paths should not end up in preserved_sections."""
        f = tmp_path / "enums.md"
        f.write_text(self._WITH_ENUM_NOTES)
        df = parse_design_file(f)
        assert df is not None
        assert "Enums & constants" not in df.preserved_sections
        assert "Call paths" not in df.preserved_sections

    def test_parser_handles_entry_without_continuation(self, tmp_path: Path) -> None:
        """Entries with no `Values:` / `Key hops:` line get empty value lists."""
        content = """\
---
description: Minimal enum entry.
id: DS-102
updated_by: archivist
---

# src/lexibrary/marker.py

## Interface Contract

```python
pass
```

## Dependencies

(none)

## Dependents

(none)

## Enums & constants

- **Marker** — A sentinel used to signal completion.

<!-- lexibrary:meta
source: src/lexibrary/marker.py
source_hash: abc123
design_hash: def456
generated: 2026-01-01T12:00:00
generator: lexibrary-v2
-->
"""
        f = tmp_path / "marker.md"
        f.write_text(content)
        df = parse_design_file(f)
        assert df is not None
        assert len(df.enum_notes) == 1
        assert df.enum_notes[0].name == "Marker"
        assert df.enum_notes[0].role == "A sentinel used to signal completion."
        assert df.enum_notes[0].values == []


class TestParseDesignFileDataFlows:
    """Tests for parsing the `## Data flows` section."""

    _WITH_DATA_FLOWS = """\
---
description: File with data flow notes.
id: DS-200
updated_by: archivist
---

# src/lexibrary/archivist/pipeline.py

## Interface Contract

```python
pass
```

## Dependencies

(none)

## Dependents

(none)

## Data flows

- **changed_paths** in **build_index()** — `None` triggers full build; non-None is incremental.
- **config** in **render()** — Controls output format and verbosity level.

<!-- lexibrary:meta
source: src/lexibrary/archivist/pipeline.py
source_hash: abc123
design_hash: def456
generated: 2026-01-01T12:00:00
generator: lexibrary-v2
-->
"""

    def test_parser_reads_data_flows_section(self, tmp_path: Path) -> None:
        """Parser extracts data flow notes with parameter, location, and effect."""
        f = tmp_path / "data_flows.md"
        f.write_text(self._WITH_DATA_FLOWS)
        df = parse_design_file(f)
        assert df is not None
        assert len(df.data_flow_notes) == 2

        first = df.data_flow_notes[0]
        assert first.parameter == "changed_paths"
        assert first.location == "build_index()"
        assert "`None` triggers full build" in first.effect

        second = df.data_flow_notes[1]
        assert second.parameter == "config"
        assert second.location == "render()"
        assert "output format" in second.effect

    def test_parser_data_flows_missing_section_is_empty_list(self, tmp_path: Path) -> None:
        """Files without a Data flows section return an empty list."""
        f = tmp_path / "design.md"
        f.write_text(_FULL_DESIGN_FILE)
        df = parse_design_file(f)
        assert df is not None
        assert df.data_flow_notes == []

    def test_parser_does_not_treat_data_flows_as_preserved_section(self, tmp_path: Path) -> None:
        """Data flows should not end up in preserved_sections."""
        f = tmp_path / "data_flows.md"
        f.write_text(self._WITH_DATA_FLOWS)
        df = parse_design_file(f)
        assert df is not None
        assert "Data flows" not in df.preserved_sections
