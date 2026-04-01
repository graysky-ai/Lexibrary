"""Tests for lexibrary.services.view_render -- view renderer module."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from lexibrary.artifacts.concept import ConceptFile, ConceptFileFrontmatter
from lexibrary.artifacts.convention import ConventionFile, ConventionFileFrontmatter
from lexibrary.artifacts.design_file import (
    DesignFile,
    DesignFileFrontmatter,
    StalenessMetadata,
)
from lexibrary.artifacts.playbook import PlaybookFile, PlaybookFileFrontmatter
from lexibrary.services.view import (
    ArtifactNotFoundError,
    ArtifactParseError,
    InvalidArtifactIdError,
    UnknownPrefixError,
    ViewError,
    ViewResult,
)
from lexibrary.services.view_render import render_view, render_view_error
from lexibrary.stack.models import (
    StackFinding,
    StackPost,
    StackPostFrontmatter,
    StackPostRefs,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(kind: str, artifact_id: str, content: object) -> ViewResult:
    """Build a ViewResult with a dummy file path."""
    return ViewResult(
        kind=kind,
        artifact_id=artifact_id,
        file_path=Path(f"/tmp/test/{artifact_id}.md"),
        content=content,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# render_view -- concept
# ---------------------------------------------------------------------------


class TestRenderConcept:
    """render_view formats ConceptFile content correctly."""

    def test_basic_concept(self) -> None:
        concept = ConceptFile(
            frontmatter=ConceptFileFrontmatter(
                title="Error Handling",
                id="CN-001",
                status="active",
                tags=["errors", "patterns"],
                aliases=["exception handling"],
            ),
            summary="How we handle errors.",
            body="Detailed explanation of error handling patterns.",
            related_concepts=["Logging", "Validation"],
            linked_files=["src/errors.py", "src/handler.py"],
            decision_log=["2024-01-15: Adopted exception hierarchy"],
        )
        result = _make_result("concept", "CN-001", concept)
        output = render_view(result)

        assert "# CN-001: Error Handling" in output
        assert "Status: active" in output
        assert "Tags: errors, patterns" in output
        assert "Aliases: exception handling" in output
        assert "## Summary" in output
        assert "How we handle errors." in output
        assert "## Body" in output
        assert "Detailed explanation" in output
        assert "## Related Concepts" in output
        assert "- Logging" in output
        assert "## Linked Files" in output
        assert "- src/errors.py" in output
        assert "## Decision Log" in output
        assert "2024-01-15: Adopted exception hierarchy" in output

    def test_minimal_concept(self) -> None:
        concept = ConceptFile(
            frontmatter=ConceptFileFrontmatter(
                title="Simple",
                id="CN-002",
                status="draft",
            ),
        )
        result = _make_result("concept", "CN-002", concept)
        output = render_view(result)

        assert "# CN-002: Simple" in output
        assert "Status: draft" in output
        # No optional sections when empty
        assert "## Summary" not in output
        assert "## Related Concepts" not in output
        assert "## Linked Files" not in output
        assert "## Decision Log" not in output

    def test_deprecated_concept_with_superseded_by(self) -> None:
        concept = ConceptFile(
            frontmatter=ConceptFileFrontmatter(
                title="Old Pattern",
                id="CN-003",
                status="deprecated",
                superseded_by="CN-010",
            ),
        )
        result = _make_result("concept", "CN-003", concept)
        output = render_view(result)

        assert "Status: deprecated" in output
        assert "Superseded by: CN-010" in output


# ---------------------------------------------------------------------------
# render_view -- convention
# ---------------------------------------------------------------------------


class TestRenderConvention:
    """render_view formats ConventionFile content correctly."""

    def test_basic_convention(self) -> None:
        convention = ConventionFile(
            frontmatter=ConventionFileFrontmatter(
                title="Use UTC Everywhere",
                id="CV-001",
                scope="project",
                status="active",
                source="user",
                priority=10,
                tags=["time", "dates"],
                aliases=["utc rule"],
            ),
            rule="Always use UTC for timestamps.",
            body="Detailed rationale for UTC usage.",
        )
        result = _make_result("convention", "CV-001", convention)
        output = render_view(result)

        assert "# CV-001: Use UTC Everywhere" in output
        assert "Status: active" in output
        assert "Scope: project" in output
        assert "Priority: 10" in output
        assert "Source: user" in output
        assert "Tags: time, dates" in output
        assert "Aliases: utc rule" in output
        assert "## Rule" in output
        assert "Always use UTC" in output
        assert "## Body" in output
        assert "Detailed rationale" in output

    def test_minimal_convention(self) -> None:
        convention = ConventionFile(
            frontmatter=ConventionFileFrontmatter(
                title="Draft Convention",
                id="CV-002",
            ),
        )
        result = _make_result("convention", "CV-002", convention)
        output = render_view(result)

        assert "# CV-002: Draft Convention" in output
        assert "Status: draft" in output
        assert "## Rule" not in output
        assert "## Body" not in output


# ---------------------------------------------------------------------------
# render_view -- playbook
# ---------------------------------------------------------------------------


class TestRenderPlaybook:
    """render_view formats PlaybookFile content correctly."""

    def test_basic_playbook(self) -> None:
        playbook = PlaybookFile(
            frontmatter=PlaybookFileFrontmatter(
                title="Version Bump",
                id="PB-001",
                status="active",
                estimated_minutes=15,
                tags=["release"],
                trigger_files=["pyproject.toml"],
                last_verified=date(2024, 6, 1),
            ),
            overview="Steps to bump the version number.",
            body="1. Update pyproject.toml\n2. Tag the release",
        )
        result = _make_result("playbook", "PB-001", playbook)
        output = render_view(result)

        assert "# PB-001: Version Bump" in output
        assert "Status: active" in output
        assert "Est: 15 min" in output
        assert "Tags: release" in output
        assert "Trigger files: pyproject.toml" in output
        assert "Last verified: 2024-06-01" in output
        assert "## Overview" in output
        assert "Steps to bump" in output
        assert "## Steps" in output
        assert "Update pyproject.toml" in output

    def test_minimal_playbook(self) -> None:
        playbook = PlaybookFile(
            frontmatter=PlaybookFileFrontmatter(
                title="Simple Playbook",
                id="PB-002",
                tags=["misc"],
            ),
        )
        result = _make_result("playbook", "PB-002", playbook)
        output = render_view(result)

        assert "# PB-002: Simple Playbook" in output
        assert "Est:" not in output  # No estimated_minutes
        assert "## Overview" not in output
        assert "## Steps" not in output

    def test_playbook_with_superseded_by(self) -> None:
        playbook = PlaybookFile(
            frontmatter=PlaybookFileFrontmatter(
                title="Old Playbook",
                id="PB-003",
                status="deprecated",
                tags=["old"],
                superseded_by="PB-010",
            ),
        )
        result = _make_result("playbook", "PB-003", playbook)
        output = render_view(result)

        assert "Superseded by: PB-010" in output


# ---------------------------------------------------------------------------
# render_view -- design
# ---------------------------------------------------------------------------


class TestRenderDesign:
    """render_view formats DesignFile content correctly."""

    def test_basic_design(self) -> None:
        design = DesignFile(
            source_path="src/main.py",
            frontmatter=DesignFileFrontmatter(
                description="Main entry point module",
                id="DS-001",
                updated_by="archivist",
                status="active",
            ),
            summary="Core application entry point.",
            interface_contract="def main() -> None: ...",
            dependencies=["os", "sys"],
            dependents=["tests/test_main.py"],
            tags=["core", "entry"],
            metadata=StalenessMetadata(
                source="src/main.py",
                source_hash="abc123",
                generated=datetime(2024, 1, 15),
                generator="archivist",
            ),
        )
        result = _make_result("design", "DS-001", design)
        output = render_view(result)

        assert "# DS-001: src/main.py" in output
        assert "Status: active" in output
        assert "Updated by: archivist" in output
        assert "Tags: core, entry" in output
        assert "## Description" in output
        assert "Main entry point module" in output
        assert "## Summary" in output
        assert "Core application entry point." in output
        assert "## Interface Contract" in output
        assert "def main() -> None" in output
        assert "## Dependencies" in output
        assert "- os" in output
        assert "- sys" in output
        assert "## Dependents" in output
        assert "- tests/test_main.py" in output

    def test_minimal_design(self) -> None:
        design = DesignFile(
            source_path="src/utils.py",
            frontmatter=DesignFileFrontmatter(
                description="Utility functions",
                id="DS-002",
            ),
            summary="",
            interface_contract="",
            metadata=StalenessMetadata(
                source="src/utils.py",
                source_hash="def456",
                generated=datetime(2024, 1, 15),
                generator="archivist",
            ),
        )
        result = _make_result("design", "DS-002", design)
        output = render_view(result)

        assert "# DS-002: src/utils.py" in output
        assert "## Description" in output
        assert "Utility functions" in output
        # Empty optional sections should not appear
        assert "## Summary" not in output
        assert "## Interface Contract" not in output
        assert "## Dependencies" not in output
        assert "## Dependents" not in output


# ---------------------------------------------------------------------------
# render_view -- stack
# ---------------------------------------------------------------------------


class TestRenderStack:
    """render_view formats StackPost content correctly."""

    def test_basic_stack_post(self) -> None:
        post = StackPost(
            frontmatter=StackPostFrontmatter(
                id="ST-001",
                title="Import loop in services",
                tags=["bug", "imports"],
                status="open",
                created=date(2024, 1, 15),
                author="agent",
                votes=3,
                refs=StackPostRefs(
                    files=["src/services/view.py"],
                    concepts=["Error Handling"],
                ),
            ),
            problem="Circular import between view and render modules.",
            context="Discovered during refactor.",
            evidence=["traceback shows ImportError"],
            attempts=["Tried lazy imports"],
        )
        result = _make_result("stack", "ST-001", post)
        output = render_view(result)

        assert "# ST-001: Import loop in services" in output
        assert "Status: open" in output
        assert "Votes: 3" in output
        assert "Tags: bug, imports" in output
        assert "Created: 2024-01-15" in output
        assert "Author: agent" in output
        assert "Files: src/services/view.py" in output
        assert "Concepts: Error Handling" in output
        assert "## Problem" in output
        assert "Circular import" in output
        assert "### Context" in output
        assert "Discovered during refactor" in output
        assert "### Evidence" in output
        assert "traceback shows ImportError" in output
        assert "### Attempts" in output
        assert "Tried lazy imports" in output

    def test_stack_post_with_findings(self) -> None:
        post = StackPost(
            frontmatter=StackPostFrontmatter(
                id="ST-002",
                title="Test failure",
                tags=["bug"],
                status="resolved",
                created=date(2024, 2, 1),
                author="user",
                resolution_type="fix",
            ),
            problem="Tests fail on CI.",
            findings=[
                StackFinding(
                    number=1,
                    date=date(2024, 2, 2),
                    author="agent",
                    votes=2,
                    accepted=True,
                    body="Fixed by updating dependency.",
                    comments=["Good catch!"],
                ),
            ],
        )
        result = _make_result("stack", "ST-002", post)
        output = render_view(result)

        assert "Status: resolved" in output
        assert "Resolution: fix" in output
        assert "## Findings (1)" in output
        assert "### F1 (accepted)" in output
        assert "Votes: 2" in output
        assert "Fixed by updating dependency." in output
        assert "Comments:" in output
        assert "Good catch!" in output

    def test_stack_post_no_findings(self) -> None:
        post = StackPost(
            frontmatter=StackPostFrontmatter(
                id="ST-003",
                title="Minimal Post",
                tags=["question"],
                status="open",
                created=date(2024, 3, 1),
                author="user",
            ),
            problem="Something is unclear.",
        )
        result = _make_result("stack", "ST-003", post)
        output = render_view(result)

        assert "No findings yet." in output

    def test_stack_post_with_bead(self) -> None:
        post = StackPost(
            frontmatter=StackPostFrontmatter(
                id="ST-004",
                title="Bead-linked Post",
                tags=["task"],
                status="open",
                created=date(2024, 4, 1),
                author="agent",
                bead="lexibrary-abc.1",
            ),
            problem="Issue found during bead work.",
        )
        result = _make_result("stack", "ST-004", post)
        output = render_view(result)

        assert "Bead: lexibrary-abc.1" in output

    def test_stack_post_duplicate(self) -> None:
        post = StackPost(
            frontmatter=StackPostFrontmatter(
                id="ST-005",
                title="Duplicate Post",
                tags=["bug"],
                status="duplicate",
                created=date(2024, 5, 1),
                author="user",
                duplicate_of="ST-001",
            ),
            problem="Same as ST-001.",
        )
        result = _make_result("stack", "ST-005", post)
        output = render_view(result)

        assert "Duplicate of: ST-001" in output


# ---------------------------------------------------------------------------
# render_view_error -- plain text
# ---------------------------------------------------------------------------


class TestRenderViewErrorPlain:
    """render_view_error formats errors as plain text."""

    def test_invalid_id_error(self) -> None:
        err = InvalidArtifactIdError(
            "Invalid artifact ID format: 'NOPE'",
            artifact_id="NOPE",
            hint="Expected format: XX-NNN",
        )
        output = render_view_error(err)
        assert "Error:" in output
        assert "NOPE" in output
        assert "Hint: Expected format: XX-NNN" in output

    def test_unknown_prefix_error(self) -> None:
        err = UnknownPrefixError(
            "Unknown artifact prefix: 'ZZ'",
            artifact_id="ZZ-001",
            hint="Valid prefixes: CN, CV, DS, PB, ST",
        )
        output = render_view_error(err)
        assert "Error:" in output
        assert "ZZ" in output
        assert "Hint:" in output

    def test_not_found_error(self) -> None:
        err = ArtifactNotFoundError(
            "Artifact not found: CN-999",
            artifact_id="CN-999",
            hint="No concept file found for CN-999.",
        )
        output = render_view_error(err)
        assert "Error:" in output
        assert "CN-999" in output
        assert "Hint:" in output

    def test_parse_error(self) -> None:
        err = ArtifactParseError(
            "Failed to parse artifact: CN-001",
            artifact_id="CN-001",
            hint="File found but parser returned None.",
        )
        output = render_view_error(err)
        assert "Error:" in output
        assert "CN-001" in output
        assert "Hint:" in output

    def test_base_view_error(self) -> None:
        err = ViewError("Something went wrong", artifact_id="CN-001")
        output = render_view_error(err)
        assert "Error: Something went wrong" in output

    def test_error_without_hint(self) -> None:
        err = ViewError("Some error")
        output = render_view_error(err)
        assert "Error:" in output
        assert "Hint:" not in output


# ---------------------------------------------------------------------------
# render_view_error -- JSON format
# ---------------------------------------------------------------------------


class TestRenderViewErrorJson:
    """render_view_error formats errors as JSON."""

    def test_invalid_id_json(self) -> None:
        err = InvalidArtifactIdError(
            "Invalid artifact ID format: 'NOPE'",
            artifact_id="NOPE",
            hint="Expected format: XX-NNN",
        )
        output = render_view_error(err, fmt="json")
        obj = json.loads(output)
        assert obj["error"] == "invalid_id"
        assert obj["artifact_id"] == "NOPE"
        assert obj["hint"] == "Expected format: XX-NNN"

    def test_unknown_prefix_json(self) -> None:
        err = UnknownPrefixError(
            "Unknown prefix",
            artifact_id="ZZ-001",
            hint="Valid prefixes: CN, CV, DS, PB, ST",
        )
        output = render_view_error(err, fmt="json")
        obj = json.loads(output)
        assert obj["error"] == "unknown_prefix"
        assert obj["artifact_id"] == "ZZ-001"

    def test_not_found_json(self) -> None:
        err = ArtifactNotFoundError(
            "Not found",
            artifact_id="CN-999",
            hint="Check if artifact exists.",
        )
        output = render_view_error(err, fmt="json")
        obj = json.loads(output)
        assert obj["error"] == "not_found"
        assert obj["artifact_id"] == "CN-999"
        assert obj["hint"] == "Check if artifact exists."

    def test_parse_error_json(self) -> None:
        err = ArtifactParseError(
            "Parse failed",
            artifact_id="CN-001",
            hint="Parser returned None.",
        )
        output = render_view_error(err, fmt="json")
        obj = json.loads(output)
        assert obj["error"] == "parse_error"
        assert obj["artifact_id"] == "CN-001"

    def test_base_view_error_json(self) -> None:
        err = ViewError("Generic error")
        output = render_view_error(err, fmt="json")
        obj = json.loads(output)
        assert obj["error"] == "view_error"
        assert "artifact_id" not in obj  # Empty artifact_id not included
        assert "hint" not in obj  # Empty hint not included

    def test_json_output_is_valid_json(self) -> None:
        err = ArtifactNotFoundError(
            "Not found",
            artifact_id="CN-999",
            hint="No file found.",
        )
        output = render_view_error(err, fmt="json")
        # Should not raise
        parsed = json.loads(output)
        assert isinstance(parsed, dict)


# ---------------------------------------------------------------------------
# render_view -- dispatch correctness
# ---------------------------------------------------------------------------


class TestRenderViewDispatch:
    """render_view dispatches to the correct per-type renderer."""

    def test_dispatches_concept(self) -> None:
        concept = ConceptFile(
            frontmatter=ConceptFileFrontmatter(title="Test", id="CN-001"),
        )
        result = _make_result("concept", "CN-001", concept)
        output = render_view(result)
        assert "Type: concept" in output

    def test_dispatches_convention(self) -> None:
        convention = ConventionFile(
            frontmatter=ConventionFileFrontmatter(title="Test", id="CV-001"),
        )
        result = _make_result("convention", "CV-001", convention)
        output = render_view(result)
        assert "Type: convention" in output

    def test_dispatches_playbook(self) -> None:
        playbook = PlaybookFile(
            frontmatter=PlaybookFileFrontmatter(title="Test", id="PB-001", tags=["test"]),
        )
        result = _make_result("playbook", "PB-001", playbook)
        output = render_view(result)
        assert "Type: playbook" in output

    def test_dispatches_design(self) -> None:
        design = DesignFile(
            source_path="src/test.py",
            frontmatter=DesignFileFrontmatter(description="Test", id="DS-001"),
            summary="Test summary",
            interface_contract="",
            metadata=StalenessMetadata(
                source="src/test.py",
                source_hash="abc",
                generated=datetime(2024, 1, 1),
                generator="test",
            ),
        )
        result = _make_result("design", "DS-001", design)
        output = render_view(result)
        assert "Type: design" in output

    def test_dispatches_stack(self) -> None:
        post = StackPost(
            frontmatter=StackPostFrontmatter(
                id="ST-001",
                title="Test",
                tags=["test"],
                status="open",
                created=date(2024, 1, 1),
                author="test",
            ),
            problem="Test problem.",
        )
        result = _make_result("stack", "ST-001", post)
        output = render_view(result)
        # Stack posts don't have "Type:" prefix -- they use Status: directly
        assert "Status: open" in output
        assert "# ST-001: Test" in output
