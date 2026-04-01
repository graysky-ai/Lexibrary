"""Tests for lexibrary.services.view -- view service module."""

from __future__ import annotations

from pathlib import Path

import pytest

from lexibrary.artifacts.concept import ConceptFile
from lexibrary.artifacts.convention import ConventionFile
from lexibrary.artifacts.design_file import DesignFile
from lexibrary.artifacts.playbook import PlaybookFile
from lexibrary.services.view import (
    ArtifactNotFoundError,
    ArtifactParseError,
    InvalidArtifactIdError,
    UnknownPrefixError,
    ViewError,
    ViewResult,
    resolve_and_load,
)
from lexibrary.stack.models import StackPost

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

CONCEPT_CONTENT = """\
---
id: CN-001
title: Example Concept
status: active
tags: []
aliases: []
---
A brief summary of this concept.

## Details

Some body content.
"""

CONVENTION_CONTENT = """\
---
id: CV-001
title: Example Convention
scope: project
status: active
source: user
priority: 0
tags: []
---
All files must follow this rule.

## Rationale

Because consistency matters.
"""

PLAYBOOK_CONTENT = """\
---
id: PB-001
title: Example Playbook
status: active
trigger_files: []
tags: [testing]
---
Overview of the playbook.

## Steps

1. Do step one.
2. Do step two.
"""

STACK_CONTENT = """\
---
id: ST-001
title: Example Stack Post
tags: [bug]
status: open
created: 2024-01-15
author: agent
votes: 0
---

## Problem

Something is broken.

## Context

It broke yesterday.
"""

# Design files need special structure: frontmatter, H1 heading, sections,
# and a metadata HTML comment footer (lexibrary:meta format).
DESIGN_CONTENT = """\
---
id: DS-001
description: Main entry point module
updated_by: archivist
status: active
---

# src/main.py

Main module for the application.

## Interface Contract

```python
def main() -> None: ...
```

## Dependencies

- os
- sys

<!-- lexibrary:meta
source: src/main.py
source_hash: abc123
design_hash: def456
generated: 2024-01-15T00:00:00
generator: archivist
-->
"""


def _setup_lexibrary(tmp_path: Path) -> Path:
    """Create a minimal .lexibrary/ directory structure for testing."""
    lib = tmp_path / ".lexibrary"
    for subdir in ("concepts", "conventions", "playbooks", "designs", "stack"):
        (lib / subdir).mkdir(parents=True)
    return tmp_path


# ---------------------------------------------------------------------------
# ViewResult dataclass tests
# ---------------------------------------------------------------------------


class TestViewResult:
    """ViewResult can be constructed and inspected."""

    def test_construction(self, tmp_path: Path) -> None:
        """ViewResult can be constructed with all required fields."""
        concept = ConceptFile(
            frontmatter={"title": "Test", "id": "CN-001"},  # type: ignore[arg-type]
            body="body",
        )
        result = ViewResult(
            kind="concept",
            artifact_id="CN-001",
            file_path=tmp_path / "test.md",
            content=concept,
        )
        assert result.kind == "concept"
        assert result.artifact_id == "CN-001"
        assert result.file_path == tmp_path / "test.md"
        assert isinstance(result.content, ConceptFile)


# ---------------------------------------------------------------------------
# ViewError hierarchy tests
# ---------------------------------------------------------------------------


class TestViewErrorHierarchy:
    """ViewError subtypes carry structured data for agent consumers."""

    def test_view_error_is_lexibrary_error(self) -> None:
        from lexibrary.exceptions import LexibraryError

        err = ViewError("test", artifact_id="CN-001", hint="try again")
        assert isinstance(err, LexibraryError)

    def test_view_error_fields(self) -> None:
        err = ViewError("msg", artifact_id="CN-001", hint="hint text")
        assert str(err) == "msg"
        assert err.artifact_id == "CN-001"
        assert err.hint == "hint text"

    def test_view_error_defaults(self) -> None:
        err = ViewError("msg")
        assert err.artifact_id == ""
        assert err.hint == ""

    def test_invalid_artifact_id_error_is_view_error(self) -> None:
        err = InvalidArtifactIdError("bad id", artifact_id="NOPE")
        assert isinstance(err, ViewError)

    def test_unknown_prefix_error_is_view_error(self) -> None:
        err = UnknownPrefixError("bad prefix", artifact_id="ZZ-001")
        assert isinstance(err, ViewError)

    def test_artifact_not_found_error_is_view_error(self) -> None:
        err = ArtifactNotFoundError("not found", artifact_id="CN-999")
        assert isinstance(err, ViewError)

    def test_artifact_parse_error_is_view_error(self) -> None:
        err = ArtifactParseError("parse failed", artifact_id="CN-001")
        assert isinstance(err, ViewError)


# ---------------------------------------------------------------------------
# resolve_and_load -- happy path for each artifact type
# ---------------------------------------------------------------------------


class TestResolveAndLoadConcept:
    """resolve_and_load successfully loads concept artifacts."""

    def test_load_concept(self, tmp_path: Path) -> None:
        root = _setup_lexibrary(tmp_path)
        concept_file = root / ".lexibrary" / "concepts" / "CN-001-example-concept.md"
        concept_file.write_text(CONCEPT_CONTENT)

        result = resolve_and_load(root, "CN-001")

        assert result.kind == "concept"
        assert result.artifact_id == "CN-001"
        assert result.file_path == concept_file
        assert isinstance(result.content, ConceptFile)
        assert result.content.frontmatter.title == "Example Concept"
        assert result.content.frontmatter.id == "CN-001"


class TestResolveAndLoadConvention:
    """resolve_and_load successfully loads convention artifacts."""

    def test_load_convention(self, tmp_path: Path) -> None:
        root = _setup_lexibrary(tmp_path)
        conv_file = root / ".lexibrary" / "conventions" / "CV-001-example-convention.md"
        conv_file.write_text(CONVENTION_CONTENT)

        result = resolve_and_load(root, "CV-001")

        assert result.kind == "convention"
        assert result.artifact_id == "CV-001"
        assert result.file_path == conv_file
        assert isinstance(result.content, ConventionFile)
        assert result.content.frontmatter.title == "Example Convention"
        assert result.content.frontmatter.scope == "project"


class TestResolveAndLoadPlaybook:
    """resolve_and_load successfully loads playbook artifacts."""

    def test_load_playbook(self, tmp_path: Path) -> None:
        root = _setup_lexibrary(tmp_path)
        pb_file = root / ".lexibrary" / "playbooks" / "PB-001-example-playbook.md"
        pb_file.write_text(PLAYBOOK_CONTENT)

        result = resolve_and_load(root, "PB-001")

        assert result.kind == "playbook"
        assert result.artifact_id == "PB-001"
        assert result.file_path == pb_file
        assert isinstance(result.content, PlaybookFile)
        assert result.content.frontmatter.title == "Example Playbook"
        assert "testing" in result.content.frontmatter.tags


class TestResolveAndLoadDesign:
    """resolve_and_load successfully loads design file artifacts."""

    def test_load_design(self, tmp_path: Path) -> None:
        root = _setup_lexibrary(tmp_path)
        # Design files live in source-mirror paths under designs/
        design_dir = root / ".lexibrary" / "designs" / "src"
        design_dir.mkdir(parents=True)
        design_file = design_dir / "main.py.md"
        design_file.write_text(DESIGN_CONTENT)

        result = resolve_and_load(root, "DS-001")

        assert result.kind == "design"
        assert result.artifact_id == "DS-001"
        assert result.file_path == design_file
        assert isinstance(result.content, DesignFile)
        assert result.content.frontmatter.description == "Main entry point module"
        assert result.content.source_path == "src/main.py"


class TestResolveAndLoadStack:
    """resolve_and_load successfully loads stack post artifacts."""

    def test_load_stack(self, tmp_path: Path) -> None:
        root = _setup_lexibrary(tmp_path)
        st_file = root / ".lexibrary" / "stack" / "ST-001-example-stack-post.md"
        st_file.write_text(STACK_CONTENT)

        result = resolve_and_load(root, "ST-001")

        assert result.kind == "stack"
        assert result.artifact_id == "ST-001"
        assert result.file_path == st_file
        assert isinstance(result.content, StackPost)
        assert result.content.frontmatter.title == "Example Stack Post"
        assert result.content.frontmatter.status == "open"


# ---------------------------------------------------------------------------
# resolve_and_load -- error cases
# ---------------------------------------------------------------------------


class TestResolveAndLoadInvalidId:
    """resolve_and_load raises InvalidArtifactIdError for malformed IDs."""

    def test_no_dash(self, tmp_path: Path) -> None:
        root = _setup_lexibrary(tmp_path)
        with pytest.raises(InvalidArtifactIdError) as exc_info:
            resolve_and_load(root, "NOPE")
        assert exc_info.value.artifact_id == "NOPE"
        assert "XX-NNN" in exc_info.value.hint

    def test_too_few_digits(self, tmp_path: Path) -> None:
        root = _setup_lexibrary(tmp_path)
        with pytest.raises(InvalidArtifactIdError):
            resolve_and_load(root, "CN-01")

    def test_empty_string(self, tmp_path: Path) -> None:
        root = _setup_lexibrary(tmp_path)
        with pytest.raises(InvalidArtifactIdError):
            resolve_and_load(root, "")

    def test_lowercase_prefix(self, tmp_path: Path) -> None:
        root = _setup_lexibrary(tmp_path)
        with pytest.raises(InvalidArtifactIdError):
            resolve_and_load(root, "cn-001")

    def test_slug_suffix(self, tmp_path: Path) -> None:
        root = _setup_lexibrary(tmp_path)
        with pytest.raises(InvalidArtifactIdError):
            resolve_and_load(root, "CN-001-slug")


class TestResolveAndLoadUnknownPrefix:
    """resolve_and_load raises UnknownPrefixError for valid format but unknown prefix."""

    def test_unknown_prefix(self, tmp_path: Path) -> None:
        root = _setup_lexibrary(tmp_path)
        with pytest.raises(UnknownPrefixError) as exc_info:
            resolve_and_load(root, "ZZ-001")
        assert exc_info.value.artifact_id == "ZZ-001"
        assert "Valid prefixes" in exc_info.value.hint

    def test_another_unknown_prefix(self, tmp_path: Path) -> None:
        root = _setup_lexibrary(tmp_path)
        with pytest.raises(UnknownPrefixError) as exc_info:
            resolve_and_load(root, "XX-999")
        assert exc_info.value.artifact_id == "XX-999"


class TestResolveAndLoadNotFound:
    """resolve_and_load raises ArtifactNotFoundError when file doesn't exist."""

    def test_concept_not_found(self, tmp_path: Path) -> None:
        root = _setup_lexibrary(tmp_path)
        with pytest.raises(ArtifactNotFoundError) as exc_info:
            resolve_and_load(root, "CN-999")
        assert exc_info.value.artifact_id == "CN-999"
        assert "concept" in exc_info.value.hint

    def test_stack_not_found(self, tmp_path: Path) -> None:
        root = _setup_lexibrary(tmp_path)
        with pytest.raises(ArtifactNotFoundError) as exc_info:
            resolve_and_load(root, "ST-999")
        assert exc_info.value.artifact_id == "ST-999"

    def test_design_not_found(self, tmp_path: Path) -> None:
        root = _setup_lexibrary(tmp_path)
        with pytest.raises(ArtifactNotFoundError) as exc_info:
            resolve_and_load(root, "DS-999")
        assert exc_info.value.artifact_id == "DS-999"


class TestResolveAndLoadParseError:
    """resolve_and_load raises ArtifactParseError when parser returns None."""

    def test_concept_parse_failure(self, tmp_path: Path) -> None:
        root = _setup_lexibrary(tmp_path)
        # File exists but has invalid/missing frontmatter
        bad_file = root / ".lexibrary" / "concepts" / "CN-001-bad.md"
        bad_file.write_text("No frontmatter here, just plain text.")
        with pytest.raises(ArtifactParseError) as exc_info:
            resolve_and_load(root, "CN-001")
        assert exc_info.value.artifact_id == "CN-001"
        assert "parser returned None" in exc_info.value.hint

    def test_convention_parse_failure(self, tmp_path: Path) -> None:
        root = _setup_lexibrary(tmp_path)
        bad_file = root / ".lexibrary" / "conventions" / "CV-001-bad.md"
        bad_file.write_text("Not a valid convention file.")
        with pytest.raises(ArtifactParseError):
            resolve_and_load(root, "CV-001")

    def test_playbook_parse_failure(self, tmp_path: Path) -> None:
        root = _setup_lexibrary(tmp_path)
        bad_file = root / ".lexibrary" / "playbooks" / "PB-001-bad.md"
        bad_file.write_text("Invalid playbook content.")
        with pytest.raises(ArtifactParseError):
            resolve_and_load(root, "PB-001")

    def test_stack_parse_failure(self, tmp_path: Path) -> None:
        root = _setup_lexibrary(tmp_path)
        bad_file = root / ".lexibrary" / "stack" / "ST-001-bad.md"
        bad_file.write_text("Invalid stack post.")
        with pytest.raises(ArtifactParseError):
            resolve_and_load(root, "ST-001")

    def test_design_parse_failure(self, tmp_path: Path) -> None:
        root = _setup_lexibrary(tmp_path)
        # Design file found by frontmatter ID scan but body is malformed
        design_dir = root / ".lexibrary" / "designs"
        bad_file = design_dir / "bad.md"
        # Has frontmatter with id but missing required sections
        bad_file.write_text("---\nid: DS-001\ndescription: Bad\n---\nNo H1 heading.\n")
        with pytest.raises(ArtifactParseError):
            resolve_and_load(root, "DS-001")
