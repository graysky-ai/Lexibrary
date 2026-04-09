"""Tests for preserved_sections and updated_by expansion (curator-1 group 3)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from lexibrary.artifacts.design_file import DesignFile, DesignFileFrontmatter, StalenessMetadata
from lexibrary.artifacts.design_file_parser import parse_design_file
from lexibrary.artifacts.design_file_serializer import serialize_design_file

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _meta(**overrides: object) -> StalenessMetadata:
    base: dict = {
        "source": "src/lexibrary/example.py",
        "source_hash": "src_hash_abc",
        "design_hash": "placeholder",
        "generated": datetime(2026, 3, 1, 10, 0, 0),
        "generator": "lexibrary-v2",
    }
    base.update(overrides)
    return StalenessMetadata(**base)


def _frontmatter(**overrides: object) -> DesignFileFrontmatter:
    base: dict = {"description": "Example module.", "id": "DS-100"}
    base.update(overrides)
    return DesignFileFrontmatter(**base)


def _design_file(**overrides: object) -> DesignFile:
    base: dict = {
        "source_path": "src/lexibrary/example.py",
        "frontmatter": _frontmatter(),
        "summary": "Example module.",
        "interface_contract": "def example() -> None: ...",
        "metadata": _meta(),
    }
    base.update(overrides)
    return DesignFile(**base)


# ---------------------------------------------------------------------------
# updated_by expansion: model acceptance
# ---------------------------------------------------------------------------


class TestUpdatedByExpansion:
    """Task 3.1 / 3.6: updated_by accepts all 6 canonical values."""

    def test_curator_accepted_by_model(self) -> None:
        """updated_by='curator' is accepted by DesignFileFrontmatter."""
        fm = _frontmatter(updated_by="curator")
        assert fm.updated_by == "curator"

    def test_skeleton_fallback_accepted_by_model(self) -> None:
        """updated_by='skeleton-fallback' is accepted by DesignFileFrontmatter."""
        fm = _frontmatter(updated_by="skeleton-fallback")
        assert fm.updated_by == "skeleton-fallback"

    def test_archivist_accepted(self) -> None:
        fm = _frontmatter(updated_by="archivist")
        assert fm.updated_by == "archivist"

    def test_agent_accepted(self) -> None:
        fm = _frontmatter(updated_by="agent")
        assert fm.updated_by == "agent"

    def test_bootstrap_quick_accepted(self) -> None:
        fm = _frontmatter(updated_by="bootstrap-quick")
        assert fm.updated_by == "bootstrap-quick"

    def test_maintainer_accepted(self) -> None:
        fm = _frontmatter(updated_by="maintainer")
        assert fm.updated_by == "maintainer"

    def test_invalid_value_still_rejected(self) -> None:
        """Values not in the 6-value Literal are still rejected."""
        with pytest.raises(ValidationError):
            _frontmatter(updated_by="unknown")

    def test_curator_roundtrip(self, tmp_path: Path) -> None:
        """updated_by='curator' survives serialize -> write -> parse."""
        df = _design_file(frontmatter=_frontmatter(updated_by="curator"))
        content = serialize_design_file(df)
        f = tmp_path / "design.md"
        f.write_text(content)
        parsed = parse_design_file(f)
        assert parsed is not None
        assert parsed.frontmatter.updated_by == "curator"

    def test_skeleton_fallback_roundtrip(self, tmp_path: Path) -> None:
        """updated_by='skeleton-fallback' survives serialize -> write -> parse."""
        df = _design_file(frontmatter=_frontmatter(updated_by="skeleton-fallback"))
        content = serialize_design_file(df)
        f = tmp_path / "design.md"
        f.write_text(content)
        parsed = parse_design_file(f)
        assert parsed is not None
        assert parsed.frontmatter.updated_by == "skeleton-fallback"


# ---------------------------------------------------------------------------
# preserved_sections: model
# ---------------------------------------------------------------------------


class TestPreservedSectionsModel:
    """Task 3.3: preserved_sections field on DesignFile model."""

    def test_default_is_empty_dict(self) -> None:
        df = _design_file()
        assert df.preserved_sections == {}

    def test_accepts_dict(self) -> None:
        df = _design_file(preserved_sections={"Insights": "Some curator insight."})
        assert df.preserved_sections == {"Insights": "Some curator insight."}

    def test_multiple_preserved_sections(self) -> None:
        sections = {
            "Insights": "Insight content here.",
            "Notes": "Additional notes.",
        }
        df = _design_file(preserved_sections=sections)
        assert df.preserved_sections == sections


# ---------------------------------------------------------------------------
# preserved_sections: parser
# ---------------------------------------------------------------------------


class TestPreservedSectionsParser:
    """Task 3.4: parse_design_file() collects unknown headings into preserved_sections."""

    _WITH_INSIGHTS = """\
---
description: File with Insights section.
id: DS-100
updated_by: curator
---

# src/lexibrary/example.py

## Interface Contract

```python
def example() -> None: ...
```

## Dependencies

(none)

## Dependents

(none)

## Insights

This module has a subtle coupling to the config loader.
The `example()` function should be refactored.

<!-- lexibrary:meta
source: src/lexibrary/example.py
source_hash: abc123
design_hash: def456
generated: 2026-01-01T12:00:00
generator: lexibrary-v2
-->
"""

    _WITH_MULTIPLE_PRESERVED = """\
---
description: File with multiple preserved sections.
id: DS-101
updated_by: curator
---

# src/lexibrary/example.py

## Interface Contract

```python
def example() -> None: ...
```

## Dependencies

(none)

## Dependents

(none)

## Insights

First insight about coupling.

## Notes

Additional context about this module.

<!-- lexibrary:meta
source: src/lexibrary/example.py
source_hash: abc123
design_hash: def456
generated: 2026-01-01T12:00:00
generator: lexibrary-v2
-->
"""

    _NO_PRESERVED = """\
---
description: Standard file, no extra sections.
id: DS-102
updated_by: archivist
---

# src/lexibrary/example.py

## Interface Contract

```python
def example() -> None: ...
```

## Dependencies

(none)

## Dependents

(none)

<!-- lexibrary:meta
source: src/lexibrary/example.py
source_hash: abc123
design_hash: def456
generated: 2026-01-01T12:00:00
generator: lexibrary-v2
-->
"""

    _WITH_KNOWN_AND_UNKNOWN = """\
---
description: File with known and unknown sections.
id: DS-103
updated_by: curator
---

# src/lexibrary/example.py

## Interface Contract

```python
def example() -> None: ...
```

## Dependencies

- src/lexibrary/config.py

## Dependents

- src/lexibrary/main.py

## Tests

See tests/test_example.py

## Insights

Curator-generated insight content.

## Wikilinks

- [[Config]]

<!-- lexibrary:meta
source: src/lexibrary/example.py
source_hash: abc123
design_hash: def456
generated: 2026-01-01T12:00:00
generator: lexibrary-v2
-->
"""

    def test_parser_extracts_insights_into_preserved_sections(self, tmp_path: Path) -> None:
        """Parser collects ## Insights into preserved_sections."""
        f = tmp_path / "design.md"
        f.write_text(self._WITH_INSIGHTS)
        df = parse_design_file(f)
        assert df is not None
        assert "Insights" in df.preserved_sections
        assert "subtle coupling" in df.preserved_sections["Insights"]
        assert "should be refactored" in df.preserved_sections["Insights"]

    def test_parser_extracts_multiple_preserved_sections(self, tmp_path: Path) -> None:
        """Parser collects multiple unknown headings into preserved_sections."""
        f = tmp_path / "design.md"
        f.write_text(self._WITH_MULTIPLE_PRESERVED)
        df = parse_design_file(f)
        assert df is not None
        assert len(df.preserved_sections) == 2
        assert "Insights" in df.preserved_sections
        assert "Notes" in df.preserved_sections
        assert "coupling" in df.preserved_sections["Insights"]
        assert "Additional context" in df.preserved_sections["Notes"]

    def test_no_preserved_sections_returns_empty_dict(self, tmp_path: Path) -> None:
        """Standard design file with only known sections has empty preserved_sections."""
        f = tmp_path / "design.md"
        f.write_text(self._NO_PRESERVED)
        df = parse_design_file(f)
        assert df is not None
        assert df.preserved_sections == {}

    def test_known_sections_not_in_preserved(self, tmp_path: Path) -> None:
        """Known sections (Tests, Wikilinks, etc.) are NOT collected into preserved_sections."""
        f = tmp_path / "design.md"
        f.write_text(self._WITH_KNOWN_AND_UNKNOWN)
        df = parse_design_file(f)
        assert df is not None
        # Only Insights should be in preserved_sections, not Tests or Wikilinks
        assert "Tests" not in df.preserved_sections
        assert "Wikilinks" not in df.preserved_sections
        assert "Interface Contract" not in df.preserved_sections
        assert "Dependencies" not in df.preserved_sections
        assert "Dependents" not in df.preserved_sections
        # Insights should be preserved
        assert "Insights" in df.preserved_sections

    def test_known_sections_still_parsed_normally(self, tmp_path: Path) -> None:
        """Known sections are still parsed into their dedicated fields."""
        f = tmp_path / "design.md"
        f.write_text(self._WITH_KNOWN_AND_UNKNOWN)
        df = parse_design_file(f)
        assert df is not None
        assert df.tests == "See tests/test_example.py"
        assert df.wikilinks == ["Config"]
        assert df.dependencies == ["src/lexibrary/config.py"]
        assert df.dependents == ["src/lexibrary/main.py"]


# ---------------------------------------------------------------------------
# preserved_sections: serializer
# ---------------------------------------------------------------------------


class TestPreservedSectionsSerializer:
    """Task 3.5: serialize_design_file() emits preserved_sections in correct position."""

    def test_empty_preserved_sections_no_extra_output(self) -> None:
        """Empty preserved_sections produces no extra section headings."""
        df = _design_file(preserved_sections={})
        content = serialize_design_file(df)
        assert "## Insights" not in content

    def test_single_preserved_section_emitted(self) -> None:
        """A single preserved section is emitted as ## Heading + content."""
        df = _design_file(preserved_sections={"Insights": "Curator insight here."})
        content = serialize_design_file(df)
        assert "## Insights" in content
        assert "Curator insight here." in content

    def test_multiple_preserved_sections_emitted(self) -> None:
        """Multiple preserved sections are all emitted."""
        sections = {
            "Insights": "Insight content.",
            "Notes": "Note content.",
        }
        df = _design_file(preserved_sections=sections)
        content = serialize_design_file(df)
        assert "## Insights" in content
        assert "Insight content." in content
        assert "## Notes" in content
        assert "Note content." in content

    def test_preserved_sections_after_dependents(self) -> None:
        """Preserved sections appear after Dependents section."""
        df = _design_file(preserved_sections={"Insights": "Some insight."})
        content = serialize_design_file(df)
        dependents_idx = content.index("## Dependents")
        insights_idx = content.index("## Insights")
        assert insights_idx > dependents_idx

    def test_preserved_sections_before_footer(self) -> None:
        """Preserved sections appear before the metadata footer."""
        df = _design_file(preserved_sections={"Insights": "Some insight."})
        content = serialize_design_file(df)
        insights_idx = content.index("## Insights")
        footer_idx = content.index("<!-- lexibrary:meta")
        assert insights_idx < footer_idx

    def test_preserved_sections_before_optional_sections(self) -> None:
        """Preserved sections appear before optional sections like Tests."""
        df = _design_file(
            preserved_sections={"Insights": "Some insight."},
            tests="See test file.",
        )
        content = serialize_design_file(df)
        insights_idx = content.index("## Insights")
        tests_idx = content.index("## Tests")
        assert insights_idx < tests_idx


# ---------------------------------------------------------------------------
# preserved_sections: round-trip
# ---------------------------------------------------------------------------


class TestPreservedSectionsRoundtrip:
    """Task 3.6: serialize -> write -> parse produces identical preserved_sections."""

    def test_roundtrip_single_section(self, tmp_path: Path) -> None:
        """Single preserved section survives round-trip."""
        df = _design_file(
            preserved_sections={"Insights": "This module has subtle coupling."},
        )
        content = serialize_design_file(df)
        f = tmp_path / "design.md"
        f.write_text(content)
        parsed = parse_design_file(f)
        assert parsed is not None
        assert parsed.preserved_sections == {"Insights": "This module has subtle coupling."}

    def test_roundtrip_multiple_sections(self, tmp_path: Path) -> None:
        """Multiple preserved sections survive round-trip in order."""
        sections = {
            "Insights": "Insight content.",
            "Notes": "Note content.",
        }
        df = _design_file(preserved_sections=sections)
        content = serialize_design_file(df)
        f = tmp_path / "design.md"
        f.write_text(content)
        parsed = parse_design_file(f)
        assert parsed is not None
        assert parsed.preserved_sections == sections

    def test_roundtrip_empty_preserved_sections(self, tmp_path: Path) -> None:
        """Empty preserved_sections round-trips as empty dict."""
        df = _design_file(preserved_sections={})
        content = serialize_design_file(df)
        f = tmp_path / "design.md"
        f.write_text(content)
        parsed = parse_design_file(f)
        assert parsed is not None
        assert parsed.preserved_sections == {}

    def test_roundtrip_with_all_optional_sections(self, tmp_path: Path) -> None:
        """Preserved sections survive round-trip alongside all optional sections."""
        df = _design_file(
            dependencies=["src/config.py"],
            dependents=["src/main.py"],
            tests="See tests/test_example.py",
            complexity_warning="High complexity.",
            wikilinks=["Config"],
            tags=["core"],
            stack_refs=["ST-001"],
            preserved_sections={"Insights": "Important observation."},
            metadata=_meta(interface_hash="iface_xyz"),
        )
        content = serialize_design_file(df)
        f = tmp_path / "design.md"
        f.write_text(content)
        parsed = parse_design_file(f)
        assert parsed is not None
        # Preserved sections intact
        assert parsed.preserved_sections == {"Insights": "Important observation."}
        # All other fields intact
        assert parsed.dependencies == ["src/config.py"]
        assert parsed.dependents == ["src/main.py"]
        assert parsed.tests == "See tests/test_example.py"
        assert parsed.complexity_warning == "High complexity."
        assert parsed.wikilinks == ["Config"]
        assert parsed.tags == ["core"]
        assert parsed.stack_refs == ["ST-001"]

    def test_roundtrip_multiline_preserved_content(self, tmp_path: Path) -> None:
        """Preserved section with multiline content survives round-trip."""
        multiline_content = (
            "This module has a subtle coupling to the config loader.\n"
            "The `example()` function should be refactored.\n"
            "\n"
            "Consider splitting into two modules."
        )
        df = _design_file(
            preserved_sections={"Insights": multiline_content},
        )
        content = serialize_design_file(df)
        f = tmp_path / "design.md"
        f.write_text(content)
        parsed = parse_design_file(f)
        assert parsed is not None
        # Content should survive (parser strips leading/trailing whitespace)
        assert "subtle coupling" in parsed.preserved_sections["Insights"]
        assert "Consider splitting" in parsed.preserved_sections["Insights"]

    def test_double_roundtrip_stable(self, tmp_path: Path) -> None:
        """Two consecutive round-trips produce identical preserved_sections."""
        df = _design_file(
            preserved_sections={"Insights": "Stable insight content."},
        )
        # First round-trip
        content1 = serialize_design_file(df)
        f1 = tmp_path / "design1.md"
        f1.write_text(content1)
        parsed1 = parse_design_file(f1)
        assert parsed1 is not None

        # Second round-trip
        content2 = serialize_design_file(parsed1)
        f2 = tmp_path / "design2.md"
        f2.write_text(content2)
        parsed2 = parse_design_file(f2)
        assert parsed2 is not None

        assert parsed1.preserved_sections == parsed2.preserved_sections
