"""Unit tests for body and structure validation checks.

Tests check_design_structure, check_stack_body_sections, and
check_concept_body from the validator.checks module.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from lexibrary.validator.checks import (
    check_concept_body,
    check_design_structure,
    check_stack_body_sections,
)

# ---------------------------------------------------------------------------
# Helpers — create test files on disk
# ---------------------------------------------------------------------------


def _write_design_file(
    lexibrary_dir: Path,
    source_path: str,
    *,
    include_h1: bool = True,
    include_interface_contract: bool = True,
    include_dependencies: bool = True,
    include_dependents: bool = True,
    include_footer: bool = True,
    raw_content: str | None = None,
) -> Path:
    """Write a design file with configurable sections.

    Returns the path to the design file.
    """
    design_path = lexibrary_dir / "designs" / f"{source_path}.md"
    design_path.parent.mkdir(parents=True, exist_ok=True)

    if raw_content is not None:
        design_path.write_text(raw_content, encoding="utf-8")
        return design_path

    now = datetime.now().isoformat()
    parts: list[str] = [
        "---",
        "description: Test design file",
        "updated_by: archivist",
        "---",
        "",
    ]

    if include_h1:
        parts.append(f"# {source_path}")
        parts.append("")

    if include_interface_contract:
        parts.extend(
            [
                "## Interface Contract",
                "",
                "```python",
                "def example(): ...",
                "```",
                "",
            ]
        )

    if include_dependencies:
        parts.extend(
            [
                "## Dependencies",
                "",
                "(none)",
                "",
            ]
        )

    if include_dependents:
        parts.extend(
            [
                "## Dependents",
                "",
                "(none)",
                "",
            ]
        )

    if include_footer:
        parts.extend(
            [
                "<!-- lexibrary:meta",
                f"source: {source_path}",
                "source_hash: abc123",
                "design_hash: def456",
                f"generated: {now}",
                "generator: test",
                "-->",
            ]
        )

    design_path.write_text("\n".join(parts) + "\n", encoding="utf-8")
    return design_path


def _write_stack_post(
    lexibrary_dir: Path,
    post_id: str,
    *,
    include_problem: bool = True,
    problem_content: str = "This is a test problem.",
    raw_content: str | None = None,
) -> Path:
    """Write a Stack post file with configurable sections.

    Returns the path to the post file.
    """
    posts_dir = lexibrary_dir / "stack" / "posts"
    posts_dir.mkdir(parents=True, exist_ok=True)
    path = posts_dir / f"{post_id}-test.md"

    if raw_content is not None:
        path.write_text(raw_content, encoding="utf-8")
        return path

    parts: list[str] = [
        "---",
        f"id: {post_id}",
        "title: Test Stack Post",
        "tags: [test]",
        "status: open",
        "created: 2026-01-01",
        "author: tester",
        "refs: {}",
        "---",
        "",
    ]

    if include_problem:
        parts.extend(
            [
                "## Problem",
                "",
                problem_content,
                "",
            ]
        )

    parts.extend(
        [
            "## Findings",
            "",
            "No findings yet.",
            "",
        ]
    )

    path.write_text("\n".join(parts), encoding="utf-8")
    return path


def _write_concept_file(
    lexibrary_dir: Path,
    name: str,
    *,
    body: str = "This concept describes something important.",
    raw_content: str | None = None,
) -> Path:
    """Write a concept file with configurable body content.

    Returns the path to the concept file.
    """
    concepts_dir = lexibrary_dir / "concepts"
    concepts_dir.mkdir(parents=True, exist_ok=True)
    path = concepts_dir / f"{name}.md"

    if raw_content is not None:
        path.write_text(raw_content, encoding="utf-8")
        return path

    content = f"""---
title: {name}
aliases: [{name.lower()}]
tags: [general]
status: active
---

{body}
"""
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# check_design_structure
# ---------------------------------------------------------------------------


class TestCheckDesignStructure:
    """Tests for check_design_structure."""

    def test_well_formed_design_passes(self, tmp_path: Path) -> None:
        """When a design file has all expected sections, no issues returned."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_design_file(lexibrary_dir, "src/example.py")

        issues = check_design_structure(project_root, lexibrary_dir)
        assert issues == []

    def test_missing_h1_reports_warning(self, tmp_path: Path) -> None:
        """When a design file lacks an H1 heading, a warning is returned."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_design_file(lexibrary_dir, "src/example.py", include_h1=False)

        issues = check_design_structure(project_root, lexibrary_dir)
        h1_issues = [i for i in issues if "H1" in i.message]
        assert len(h1_issues) == 1
        assert h1_issues[0].severity == "warning"
        assert h1_issues[0].check == "design_structure"

    def test_missing_interface_contract_reports_warning(self, tmp_path: Path) -> None:
        """When a design file lacks Interface Contract section, a warning is returned."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_design_file(lexibrary_dir, "src/example.py", include_interface_contract=False)

        issues = check_design_structure(project_root, lexibrary_dir)
        ic_issues = [i for i in issues if "Interface Contract" in i.message]
        assert len(ic_issues) == 1
        assert ic_issues[0].severity == "warning"

    def test_missing_metadata_footer_reports_warning(self, tmp_path: Path) -> None:
        """When a design file has no metadata footer, a warning is returned."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_design_file(lexibrary_dir, "src/example.py", include_footer=False)

        issues = check_design_structure(project_root, lexibrary_dir)
        footer_issues = [i for i in issues if "metadata footer" in i.message]
        assert len(footer_issues) == 1
        assert footer_issues[0].severity == "warning"
        assert footer_issues[0].check == "design_structure"

    def test_multiple_missing_sections_produce_multiple_issues(self, tmp_path: Path) -> None:
        """When multiple sections are missing, each produces a separate issue."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_design_file(
            lexibrary_dir,
            "src/example.py",
            include_dependencies=False,
            include_dependents=False,
        )

        issues = check_design_structure(project_root, lexibrary_dir)
        section_issues = [
            i for i in issues if "Dependencies" in i.message or "Dependents" in i.message
        ]
        assert len(section_issues) == 2

    def test_no_frontmatter_skipped(self, tmp_path: Path) -> None:
        """When a design file has no frontmatter, it is skipped."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_design_file(
            lexibrary_dir,
            "src/example.py",
            raw_content="# No frontmatter here\n\nJust a plain file.\n",
        )

        issues = check_design_structure(project_root, lexibrary_dir)
        assert issues == []

    def test_invalid_yaml_frontmatter_skipped(self, tmp_path: Path) -> None:
        """When a design file has invalid YAML in frontmatter, it is skipped."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_design_file(
            lexibrary_dir,
            "src/example.py",
            raw_content="---\n: bad: yaml: [unclosed\n---\n\n# src/example.py\n",
        )

        issues = check_design_structure(project_root, lexibrary_dir)
        assert issues == []

    def test_non_dict_frontmatter_skipped(self, tmp_path: Path) -> None:
        """When frontmatter is not a mapping, the file is skipped."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_design_file(
            lexibrary_dir,
            "src/example.py",
            raw_content="---\n- just a list\n---\n\n# src/example.py\n",
        )

        issues = check_design_structure(project_root, lexibrary_dir)
        assert issues == []

    def test_missing_designs_directory_returns_empty(self, tmp_path: Path) -> None:
        """When .lexibrary/designs/ does not exist, return empty list."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        issues = check_design_structure(project_root, lexibrary_dir)
        assert issues == []


# ---------------------------------------------------------------------------
# check_stack_body_sections
# ---------------------------------------------------------------------------


class TestCheckStackBodySections:
    """Tests for check_stack_body_sections."""

    def test_post_with_problem_section_passes(self, tmp_path: Path) -> None:
        """When a Stack post has a non-empty ## Problem section, no issues returned."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_stack_post(lexibrary_dir, "ST-001")

        issues = check_stack_body_sections(project_root, lexibrary_dir)
        assert issues == []

    def test_missing_problem_section_reports_warning(self, tmp_path: Path) -> None:
        """When a Stack post has no ## Problem heading, a warning is returned."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_stack_post(lexibrary_dir, "ST-001", include_problem=False)

        issues = check_stack_body_sections(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert issues[0].severity == "warning"
        assert issues[0].check == "stack_body_sections"
        assert "Missing" in issues[0].message

    def test_empty_problem_section_reports_warning(self, tmp_path: Path) -> None:
        """When ## Problem exists but has only whitespace, a warning is returned."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_stack_post(lexibrary_dir, "ST-001", problem_content="")

        issues = check_stack_body_sections(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert issues[0].severity == "warning"
        assert "Empty" in issues[0].message

    def test_whitespace_only_problem_reports_warning(self, tmp_path: Path) -> None:
        """When ## Problem has only whitespace content, a warning is returned."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_stack_post(lexibrary_dir, "ST-001", problem_content="   \n  \n   ")

        issues = check_stack_body_sections(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert "Empty" in issues[0].message

    def test_parse_failure_skips_post(self, tmp_path: Path) -> None:
        """When a Stack post has malformed YAML, it is skipped gracefully."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_stack_post(
            lexibrary_dir,
            "ST-001",
            raw_content="---\n: bad: yaml: [unclosed\n---\n\n## Problem\n\nContent.\n",
        )

        issues = check_stack_body_sections(project_root, lexibrary_dir)
        assert issues == []

    def test_no_frontmatter_skipped(self, tmp_path: Path) -> None:
        """When a post file has no frontmatter block, it is skipped."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_stack_post(
            lexibrary_dir,
            "ST-001",
            raw_content="Just plain text, no frontmatter.\n\n## Problem\n\nContent.\n",
        )

        issues = check_stack_body_sections(project_root, lexibrary_dir)
        assert issues == []

    def test_missing_posts_directory_returns_empty(self, tmp_path: Path) -> None:
        """When .lexibrary/stack/posts/ does not exist, return empty list."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        issues = check_stack_body_sections(project_root, lexibrary_dir)
        assert issues == []

    def test_non_dict_frontmatter_skipped(self, tmp_path: Path) -> None:
        """When frontmatter is not a mapping, the post is skipped."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_stack_post(
            lexibrary_dir,
            "ST-001",
            raw_content="---\n- just a list\n---\n\n## Problem\n\nContent.\n",
        )

        issues = check_stack_body_sections(project_root, lexibrary_dir)
        assert issues == []


# ---------------------------------------------------------------------------
# check_concept_body
# ---------------------------------------------------------------------------


class TestCheckConceptBody:
    """Tests for check_concept_body."""

    def test_concept_with_body_passes(self, tmp_path: Path) -> None:
        """When a concept has text content after frontmatter, no issues returned."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_concept_file(lexibrary_dir, "example-concept")

        issues = check_concept_body(project_root, lexibrary_dir)
        assert issues == []

    def test_empty_body_reports_info(self, tmp_path: Path) -> None:
        """When a concept has no body content, an info issue is returned."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_concept_file(lexibrary_dir, "empty-concept", body="")

        issues = check_concept_body(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert issues[0].severity == "info"
        assert issues[0].check == "concept_body"
        assert "empty body" in issues[0].message

    def test_whitespace_only_body_reports_info(self, tmp_path: Path) -> None:
        """When concept body is only whitespace, an info issue is returned."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_concept_file(lexibrary_dir, "ws-concept", body="   \n  \n   ")

        issues = check_concept_body(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert issues[0].severity == "info"

    def test_concept_with_wikilinks_passes(self, tmp_path: Path) -> None:
        """When a concept has wikilinks in body, no issues returned."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_concept_file(
            lexibrary_dir,
            "linked-concept",
            body="See [[related concept]] for more details.",
        )

        issues = check_concept_body(project_root, lexibrary_dir)
        assert issues == []

    def test_no_concepts_directory_returns_empty(self, tmp_path: Path) -> None:
        """When .lexibrary/concepts/ does not exist, return empty list."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        issues = check_concept_body(project_root, lexibrary_dir)
        assert issues == []

    def test_no_frontmatter_skipped(self, tmp_path: Path) -> None:
        """When a concept file has no frontmatter, it is skipped."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_concept_file(
            lexibrary_dir,
            "no-fm",
            raw_content="Just plain text, no frontmatter.\n",
        )

        issues = check_concept_body(project_root, lexibrary_dir)
        assert issues == []

    def test_invalid_yaml_skipped(self, tmp_path: Path) -> None:
        """When a concept file has invalid YAML, it is skipped."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_concept_file(
            lexibrary_dir,
            "bad-yaml",
            raw_content="---\n: bad: yaml: [unclosed\n---\n\nBody content.\n",
        )

        issues = check_concept_body(project_root, lexibrary_dir)
        assert issues == []

    def test_non_dict_frontmatter_skipped(self, tmp_path: Path) -> None:
        """When frontmatter is not a mapping, the file is skipped."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_concept_file(
            lexibrary_dir,
            "list-fm",
            raw_content="---\n- just a list\n---\n\nBody content.\n",
        )

        issues = check_concept_body(project_root, lexibrary_dir)
        assert issues == []
