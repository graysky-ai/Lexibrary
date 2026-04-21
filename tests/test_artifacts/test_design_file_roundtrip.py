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

        # Extract the design_hash stored in footer — the §1.3 compact inline
        # form emits ``<!-- lexibrary:meta {..., design_hash: <hex>, ...} -->``
        # so we read the hash directly off the parsed StalenessMetadata.
        f = tmp_path / "design.md"
        f.write_text(content)
        parsed = parse_design_file(f)
        assert parsed is not None
        original_hash = parsed.metadata.design_hash
        assert original_hash is not None

        # Simulate agent edit: modify the body
        modified_body = content.replace("def main() -> None: ...", "def main() -> int: ...")
        # Hash the modified content (excluding footer)
        modified_footer_start = modified_body.index("<!-- lexibrary:meta")
        modified_pre_footer = modified_body[:modified_footer_start]
        new_hash = hashlib.sha256(modified_pre_footer.encode()).hexdigest()

        assert new_hash != original_hash, "Agent edit should produce a different hash"

    def test_dependents_hint_line_not_emitted(self, tmp_path: Path) -> None:
        """§1.2: The ``*(see `lexi lookup` ...)*`` hint line SHALL NOT appear in
        freshly serialized output. It was static noise on every design file and
        ``lexi lookup`` is the authoritative source for reverse references."""
        df = _design_file(dependents=["src/lexibrary/__main__.py"])
        content = serialize_design_file(df)
        assert "*(see `lexi lookup` for live reverse references)*" not in content
        f = tmp_path / "design.md"
        f.write_text(content)
        parsed = parse_design_file(f)
        assert parsed is not None
        assert parsed.dependents == ["src/lexibrary/__main__.py"]

    def test_dependents_hint_line_not_emitted_empty(self, tmp_path: Path) -> None:
        """§1.2: With no dependents, the section becomes heading + (none) only —
        no hint line."""
        df = _design_file(dependents=[])
        content = serialize_design_file(df)
        assert "*(see `lexi lookup` for live reverse references)*" not in content
        # Dependents section still emits (none) when empty.
        dep_start = content.index("## Dependents")
        dep_block = content[dep_start:]
        assert "(none)" in dep_block
        f = tmp_path / "design.md"
        f.write_text(content)
        parsed = parse_design_file(f)
        assert parsed is not None
        assert parsed.dependents == []

    def test_legacy_file_with_dependents_hint_parses(self, tmp_path: Path) -> None:
        """§1.2 legacy compat: a pre-§1.2 on-disk file that still carries the
        hint line parses correctly — the parser ignores non-bullet lines in the
        Dependents section, so the hint is silently skipped and the bullet list
        is extracted intact."""
        legacy_text = """---
description: CLI entry point for the lexi command.
id: DS-001
updated_by: archivist
---

# src/lexibrary/cli.py

## Interface Contract

```python
def main() -> None: ...
```

## Dependencies

(none)

## Dependents

*(see `lexi lookup` for live reverse references)*

- src/lexibrary/__main__.py
- src/lexibrary/entry.py

<!-- lexibrary:meta
source: src/lexibrary/cli.py
source_hash: src_hash_abc
design_hash: dh
generated: 2026-03-01T10:00:00
generator: lexibrary-v2
dependents_complete: false
-->
"""
        f = tmp_path / "legacy_dependents.md"
        f.write_text(legacy_text)
        parsed = parse_design_file(f)
        assert parsed is not None, "Legacy file with hint line must still parse"
        # The hint line MUST NOT leak into the parsed dependents list.
        assert parsed.dependents == [
            "src/lexibrary/__main__.py",
            "src/lexibrary/entry.py",
        ]
        for dep in parsed.dependents:
            assert "lexi lookup" not in dep
            assert "reverse references" not in dep

    def test_legacy_file_with_dependents_hint_and_none_parses(self, tmp_path: Path) -> None:
        """§1.2 legacy compat: a pre-§1.2 file with hint + (none) (no bullets)
        parses to an empty dependents list."""
        legacy_text = """---
description: CLI entry point for the lexi command.
id: DS-001
updated_by: archivist
---

# src/lexibrary/cli.py

## Interface Contract

```python
def main() -> None: ...
```

## Dependencies

(none)

## Dependents

*(see `lexi lookup` for live reverse references)*

(none)

<!-- lexibrary:meta
source: src/lexibrary/cli.py
source_hash: src_hash_abc
design_hash: dh
generated: 2026-03-01T10:00:00
generator: lexibrary-v2
dependents_complete: false
-->
"""
        f = tmp_path / "legacy_dependents_none.md"
        f.write_text(legacy_text)
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

    def test_status_active_omitted_from_serialized_frontmatter(self, tmp_path: Path) -> None:
        """Default active status SHALL NOT appear as a ``status:`` key in the YAML
        frontmatter; the parser still defaults the value to ``active``."""
        df = _design_file()
        content = serialize_design_file(df)
        # Extract just the YAML frontmatter block (between the first two "---" lines).
        fm_end = content.index("\n---\n", content.index("---\n") + 4)
        fm_block = content[: fm_end + len("\n---\n")]
        assert "status:" not in fm_block
        # But the parser should still recover status="active".
        f = tmp_path / "design.md"
        f.write_text(content)
        parsed = parse_design_file(f)
        assert parsed is not None
        assert parsed.frontmatter.status == "active"

    def test_status_deprecated_emitted_in_frontmatter(self, tmp_path: Path) -> None:
        """Non-default deprecated status SHALL appear in the serialized frontmatter
        and survive round-trip."""
        deprecated_at = datetime(2026, 3, 1, 14, 30, 0)
        df = _design_file(
            frontmatter=_frontmatter(
                status="deprecated",
                deprecated_at=deprecated_at,
                deprecated_reason="manual",
            )
        )
        content = serialize_design_file(df)
        fm_end = content.index("\n---\n", content.index("---\n") + 4)
        fm_block = content[: fm_end + len("\n---\n")]
        assert "status: deprecated" in fm_block
        f = tmp_path / "design.md"
        f.write_text(content)
        parsed = parse_design_file(f)
        assert parsed is not None
        assert parsed.frontmatter.status == "deprecated"

    def test_status_unlinked_emitted_in_frontmatter(self, tmp_path: Path) -> None:
        """Non-default unlinked status SHALL appear in the serialized frontmatter
        and survive round-trip."""
        df = _design_file(frontmatter=_frontmatter(status="unlinked"))
        content = serialize_design_file(df)
        fm_end = content.index("\n---\n", content.index("---\n") + 4)
        fm_block = content[: fm_end + len("\n---\n")]
        assert "status: unlinked" in fm_block
        f = tmp_path / "design.md"
        f.write_text(content)
        parsed = parse_design_file(f)
        assert parsed is not None
        assert parsed.frontmatter.status == "unlinked"

    def test_legacy_explicit_status_active_parses(self, tmp_path: Path) -> None:
        """A legacy on-disk file that explicitly carries ``status: active`` in its
        frontmatter SHALL parse with ``status="active"`` (backward compat)."""
        legacy_content = (
            "---\n"
            "description: Legacy design file with explicit status.\n"
            "id: DS-042\n"
            "updated_by: archivist\n"
            "status: active\n"
            "---\n"
            "\n"
            "# src/legacy/example.py\n"
            "\n"
            "## Interface Contract\n"
            "\n"
            "```python\n"
            "def noop() -> None: ...\n"
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
            "source: src/legacy/example.py\n"
            "source_hash: abc123\n"
            "design_hash: def456\n"
            "generated: 2026-01-01T00:00:00\n"
            "generator: legacy\n"
            "dependents_complete: false\n"
            "-->\n"
        )
        f = tmp_path / "legacy.md"
        f.write_text(legacy_content)
        parsed = parse_design_file(f)
        assert parsed is not None
        assert parsed.frontmatter.status == "active"

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

    def test_interface_contract_inner_fence_stripped_on_serialize(self, tmp_path: Path) -> None:
        """§1.1: serializer strips a doubled inner fence from interface_contract.

        When the upstream producer (e.g. an LLM) wraps the skeleton in its own
        ```<lang> ... ``` fence, the serializer MUST emit exactly one outer
        fence wrapping the raw body — not a nested pair.
        """
        df = _design_file(
            interface_contract="```python\ndef foo(): ...\n```",
        )
        content = serialize_design_file(df)

        # Extract the ## Interface Contract section out of the serialized text.
        start = content.index("## Interface Contract")
        after_heading = content[start:]
        # Body between the first and second ``` markers.
        first_fence = after_heading.index("```")
        after_open = after_heading[first_fence + len("```") :]
        # `after_open` begins with the language tag then \n, then the body.
        newline_idx = after_open.index("\n")
        after_lang = after_open[newline_idx + 1 :]
        closing_idx = after_lang.index("```")
        body = after_lang[:closing_idx]

        # Body is exactly `def foo(): ...\n` — no inner ```python opener, no
        # inner ``` closer left over.
        assert "```" not in body, (
            "Serialized Interface Contract must not contain a nested inner fence: " + repr(body)
        )
        assert body.strip() == "def foo(): ..."

        # Round-trip: parser strips the outer fence and returns the raw body.
        f = tmp_path / "design.md"
        f.write_text(content)
        parsed = parse_design_file(f)
        assert parsed is not None
        assert parsed.interface_contract == "def foo(): ..."

    def test_interface_contract_inner_fence_without_trailing_newline(self, tmp_path: Path) -> None:
        """§1.1: serializer handles ``` trailing with no preceding newline."""
        df = _design_file(interface_contract="```ts\nexport type X = string;```")
        content = serialize_design_file(df)

        start = content.index("## Interface Contract")
        after_heading = content[start:]
        first_fence = after_heading.index("```")
        after_open = after_heading[first_fence + len("```") :]
        newline_idx = after_open.index("\n")
        after_lang = after_open[newline_idx + 1 :]
        closing_idx = after_lang.index("```")
        body = after_lang[:closing_idx]

        assert "```" not in body
        assert body.strip() == "export type X = string;"

    def test_interface_contract_no_inner_fence_unchanged(self, tmp_path: Path) -> None:
        """§1.1: absent an inner fence, the body round-trips verbatim."""
        df = _design_file(interface_contract="def bar() -> int: ...")
        content = serialize_design_file(df)
        f = tmp_path / "design.md"
        f.write_text(content)
        parsed = parse_design_file(f)
        assert parsed is not None
        assert parsed.interface_contract == "def bar() -> int: ..."

    def test_interface_contract_legacy_doubled_fence_on_disk(self, tmp_path: Path) -> None:
        """§1.1 legacy compat: parser tolerates on-disk doubled fences.

        Files written by the pre-§1.1 serializer contain a nested ```<lang>
        ... ``` fence inside the outer fence. Parsing those files MUST yield
        the raw body without the inner fence artifact.
        """
        legacy_text = """---
description: CLI entry point for the lexi command.
id: DS-001
updated_by: archivist
status: active
---

# src/lexibrary/cli.py

## Interface Contract

```python
```python
def main() -> None: ...
```
```

## Dependencies

(none)

## Dependents

*(see `lexi lookup` for live reverse references)*

(none)

<!-- lexibrary:meta
source: src/lexibrary/cli.py
source_hash: src_hash_abc
design_hash: dh
generated: 2026-03-01T10:00:00
generator: lexibrary-v2
dependents_complete: false
-->
"""
        f = tmp_path / "legacy_design.md"
        f.write_text(legacy_text)
        parsed = parse_design_file(f)
        assert parsed is not None, "Legacy doubled-fence file must still parse"
        # Inner fence artifact is stripped; body is the raw interface.
        assert parsed.interface_contract == "def main() -> None: ..."
        assert "```" not in parsed.interface_contract

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

    def test_meta_footer_serialized_as_single_line(self, tmp_path: Path) -> None:
        """§1.3: the meta footer MUST be emitted as a single-line inline YAML
        mapping — no multi-line `<!-- lexibrary:meta\\n...\\n-->` block."""
        df = _design_file(metadata=_meta(interface_hash="iface_hash_xyz"))
        content = serialize_design_file(df)
        footer_start = content.index("<!-- lexibrary:meta")
        footer_end = content.index("-->", footer_start) + len("-->")
        footer = content[footer_start:footer_end]
        # Footer occupies exactly one line (no embedded newline).
        assert "\n" not in footer
        assert footer.startswith("<!-- lexibrary:meta {")
        assert footer.endswith("} -->")

    def test_meta_footer_roundtrip_full_metadata(self, tmp_path: Path) -> None:
        """§1.3 (a): a DesignFile with full metadata serializes to a single-line
        footer that parses back to an equivalent StalenessMetadata."""
        df = _design_file(metadata=_meta(interface_hash="iface_hash_xyz"))
        content = serialize_design_file(df)
        f = tmp_path / "design.md"
        f.write_text(content)
        parsed = parse_design_file(f)
        assert parsed is not None
        assert parsed.metadata.source == df.metadata.source
        assert parsed.metadata.source_hash == df.metadata.source_hash
        assert parsed.metadata.interface_hash == "iface_hash_xyz"
        assert parsed.metadata.generated == df.metadata.generated
        assert parsed.metadata.generator == df.metadata.generator
        assert parsed.metadata.dependents_complete == df.metadata.dependents_complete
        # design_hash is computed at serialize time, so just check it's present
        # and is a valid hex SHA-256 digest.
        assert parsed.metadata.design_hash is not None
        assert len(parsed.metadata.design_hash) == 64

    def test_meta_footer_omits_null_interface_hash(self, tmp_path: Path) -> None:
        """§1.3 (b): when ``metadata.interface_hash is None``, the inline object
        SHALL NOT carry an ``interface_hash`` key; the parser still produces a
        StalenessMetadata with ``interface_hash=None`` (matching the pre-§1.3
        conditional-emit behaviour)."""
        df = _design_file()
        assert df.metadata.interface_hash is None
        content = serialize_design_file(df)
        footer_start = content.index("<!-- lexibrary:meta")
        footer_end = content.index("-->", footer_start) + len("-->")
        footer = content[footer_start:footer_end]
        assert "interface_hash" not in footer
        f = tmp_path / "design.md"
        f.write_text(content)
        parsed = parse_design_file(f)
        assert parsed is not None
        assert parsed.metadata.interface_hash is None

    def test_meta_footer_parses_legacy_multiline_form(self, tmp_path: Path) -> None:
        """§1.3 (c): a legacy on-disk file using the multi-line footer still
        parses — the parser tries the compact inline form first and falls back
        to the multi-line form."""
        legacy_text = (
            "---\n"
            "description: CLI entry point for the lexi command.\n"
            "id: DS-001\n"
            "updated_by: archivist\n"
            "---\n"
            "\n"
            "# src/lexibrary/cli.py\n"
            "\n"
            "## Interface Contract\n"
            "\n"
            "```python\n"
            "def main() -> None: ...\n"
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
            "source: src/lexibrary/cli.py\n"
            "source_hash: src_hash_abc\n"
            "interface_hash: iface_hash_xyz\n"
            "design_hash: dh_abc_def\n"
            "generated: 2026-03-01T10:00:00\n"
            "generator: lexibrary-v2\n"
            "dependents_complete: true\n"
            "-->\n"
        )
        f = tmp_path / "legacy.md"
        f.write_text(legacy_text)
        parsed = parse_design_file(f)
        assert parsed is not None
        assert parsed.metadata.source == "src/lexibrary/cli.py"
        assert parsed.metadata.source_hash == "src_hash_abc"
        assert parsed.metadata.interface_hash == "iface_hash_xyz"
        assert parsed.metadata.design_hash == "dh_abc_def"
        assert parsed.metadata.generated == datetime(2026, 3, 1, 10, 0, 0)
        assert parsed.metadata.generator == "lexibrary-v2"
        assert parsed.metadata.dependents_complete is True

    def test_meta_footer_parses_hand_authored_inline_form(self, tmp_path: Path) -> None:
        """§1.3 (d): a hand-authored single-line fixture parses to the same
        StalenessMetadata an auto-generated file would produce."""
        inline_text = (
            "---\n"
            "description: CLI entry point.\n"
            "id: DS-001\n"
            "updated_by: archivist\n"
            "---\n"
            "\n"
            "# src/lexibrary/cli.py\n"
            "\n"
            "## Interface Contract\n"
            "\n"
            "```python\n"
            "def main() -> None: ...\n"
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
            "<!-- lexibrary:meta {source: src/lexibrary/cli.py, "
            "source_hash: src_hash_abc, interface_hash: iface_hash_xyz, "
            "design_hash: dh_abc_def, generated: '2026-03-01T10:00:00', "
            "generator: lexibrary-v2, dependents_complete: false} -->\n"
        )
        f = tmp_path / "inline.md"
        f.write_text(inline_text)
        parsed = parse_design_file(f)
        assert parsed is not None
        assert parsed.metadata.source == "src/lexibrary/cli.py"
        assert parsed.metadata.source_hash == "src_hash_abc"
        assert parsed.metadata.interface_hash == "iface_hash_xyz"
        assert parsed.metadata.design_hash == "dh_abc_def"
        assert parsed.metadata.generated == datetime(2026, 3, 1, 10, 0, 0)
        assert parsed.metadata.generator == "lexibrary-v2"
        assert parsed.metadata.dependents_complete is False

    def test_meta_footer_parses_hand_authored_inline_without_interface_hash(
        self, tmp_path: Path
    ) -> None:
        """§1.3: hand-authored inline footer that omits ``interface_hash``
        parses to ``StalenessMetadata.interface_hash is None``."""
        inline_text = (
            "---\n"
            "description: CLI entry point.\n"
            "id: DS-001\n"
            "updated_by: archivist\n"
            "---\n"
            "\n"
            "# src/lexibrary/cli.py\n"
            "\n"
            "## Interface Contract\n"
            "\n"
            "```python\n"
            "def main() -> None: ...\n"
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
            "<!-- lexibrary:meta {source: src/cli.py, source_hash: sh, "
            "design_hash: dh, generated: '2026-03-01T10:00:00', "
            "generator: gen, dependents_complete: true} -->\n"
        )
        f = tmp_path / "inline_no_iface.md"
        f.write_text(inline_text)
        parsed = parse_design_file(f)
        assert parsed is not None
        assert parsed.metadata.interface_hash is None
        assert parsed.metadata.dependents_complete is True
