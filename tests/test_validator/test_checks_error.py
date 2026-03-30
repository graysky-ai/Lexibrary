"""Unit tests for error-severity validation checks.

Tests check_wikilink_resolution, check_file_existence, and
check_concept_frontmatter from the validator.checks module.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from lexibrary.validator.checks import (
    check_concept_frontmatter,
    check_file_existence,
    check_wikilink_resolution,
)

# ---------------------------------------------------------------------------
# Helpers — create valid design files on disk
# ---------------------------------------------------------------------------


def _write_design_file(
    lexibrary_dir: Path,
    source_path: str,
    *,
    wikilinks: list[str] | None = None,
) -> Path:
    """Write a minimal valid design file into the lexibrary mirror tree.

    Returns the path to the design file.
    """
    design_path = lexibrary_dir / "designs" / f"{source_path}.md"
    design_path.parent.mkdir(parents=True, exist_ok=True)

    wiki_section = ""
    if wikilinks:
        wiki_section = "\n## Wikilinks\n\n"
        for link in wikilinks:
            wiki_section += f"- [[{link}]]\n"
        wiki_section += "\n"

    now = datetime.now().isoformat()
    content = f"""---
description: Test design file
id: DS-001
updated_by: archivist
---

# {source_path}

## Interface Contract

```python
def example(): ...
```

## Dependencies

(none)

## Dependents

(none)
{wiki_section}
<!-- lexibrary:meta
source: {source_path}
source_hash: abc123
design_hash: def456
generated: {now}
generator: test
-->
"""
    design_path.write_text(content, encoding="utf-8")
    return design_path


def _write_concept_file(
    concepts_dir: Path,
    name: str,
    *,
    title: str | None = None,
    aliases: list[str] | None = None,
    tags: list[str] | None = None,
    status: str = "active",
    raw_content: str | None = None,
) -> Path:
    """Write a concept file with YAML frontmatter.

    If raw_content is provided, it is used verbatim instead of generating
    frontmatter from the keyword arguments.
    """
    concepts_dir.mkdir(parents=True, exist_ok=True)
    path = concepts_dir / f"{name}.md"

    if raw_content is not None:
        path.write_text(raw_content, encoding="utf-8")
        return path

    title = title or name
    aliases = aliases if aliases is not None else [name.lower()]
    tags = tags if tags is not None else ["general"]

    content = f"""---
title: {title}
id: CN-004
aliases: [{", ".join(aliases)}]
tags: [{", ".join(tags)}]
status: {status}
---

{title} is a concept used in the system.
"""
    path.write_text(content, encoding="utf-8")
    return path


def _write_convention_file(
    conventions_dir: Path,
    title: str,
    *,
    scope: str = "project",
    tags: list[str] | None = None,
    aliases: list[str] | None = None,
    status: str = "active",
) -> Path:
    """Write a minimal convention file into the conventions directory.

    Returns the path to the convention file.
    """
    conventions_dir.mkdir(parents=True, exist_ok=True)
    slug = title.lower().replace(" ", "-")
    path = conventions_dir / f"{slug}.md"

    tags = tags if tags is not None else ["general"]
    aliases = aliases if aliases is not None else []

    aliases_yaml = "[" + ", ".join(aliases) + "]" if aliases else "[]"
    tags_yaml = "[" + ", ".join(tags) + "]"

    content = f"""---
title: {title}
id: CV-001
scope: {scope}
tags: {tags_yaml}
status: {status}
aliases: {aliases_yaml}
---

{title} is a convention for the project.
"""
    path.write_text(content, encoding="utf-8")
    return path


def _write_stack_post(
    stack_dir: Path,
    post_id: str,
    slug: str,
    *,
    body_wikilinks: list[str] | None = None,
    concept_refs: list[str] | None = None,
    file_refs: list[str] | None = None,
    design_refs: list[str] | None = None,
) -> Path:
    """Write a minimal Stack post file."""
    stack_dir.mkdir(parents=True, exist_ok=True)
    path = stack_dir / f"{post_id}-{slug}.md"

    refs_lines: list[str] = []
    if concept_refs or file_refs or design_refs:
        refs_lines.append("refs:")
        if concept_refs:
            refs_lines.append("  concepts: [" + ", ".join(concept_refs) + "]")
        if file_refs:
            refs_lines.append("  files: [" + ", ".join(file_refs) + "]")
        if design_refs:
            refs_lines.append("  designs: [" + ", ".join(design_refs) + "]")

    refs_block = "\n".join(refs_lines) if refs_lines else "refs: {}"

    body = ""
    if body_wikilinks:
        body = "\n".join(f"See [[{link}]] for details." for link in body_wikilinks)

    content = f"""---
id: {post_id}
title: Test Stack Post
tags: [test]
status: open
created: 2026-01-01
author: tester
{refs_block}
---

## Problem

This is a test problem.

{body}
"""
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# check_wikilink_resolution
# ---------------------------------------------------------------------------


class TestCheckWikilinkResolution:
    """Tests for check_wikilink_resolution."""

    def test_all_wikilinks_resolve_returns_empty(self, tmp_path: Path) -> None:
        """When all wikilinks resolve, no issues are returned."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        # Create a concept that will be referenced
        _write_concept_file(
            lexibrary_dir / "concepts",
            "Authentication",
            title="Authentication",
            aliases=["auth"],
            tags=["security"],
        )

        # Create a source file and its design file with a resolvable wikilink
        (tmp_path / "src").mkdir(parents=True)
        (tmp_path / "src" / "auth.py").write_text("# auth", encoding="utf-8")
        _write_design_file(
            lexibrary_dir,
            "src/auth.py",
            wikilinks=["Authentication"],
        )

        issues = check_wikilink_resolution(project_root, lexibrary_dir)
        assert issues == []

    def test_broken_wikilink_produces_error(self, tmp_path: Path) -> None:
        """Unresolved wikilink produces an error with check=wikilink_resolution."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        # Create concepts directory (empty or with unrelated concept)
        (lexibrary_dir / "concepts").mkdir(parents=True)

        # Create a source file
        (tmp_path / "src").mkdir(parents=True)
        (tmp_path / "src" / "auth.py").write_text("# auth", encoding="utf-8")

        # Create design file with a wikilink to a non-existent concept
        _write_design_file(
            lexibrary_dir,
            "src/auth.py",
            wikilinks=["NonExistentConcept"],
        )

        issues = check_wikilink_resolution(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert issues[0].check == "wikilink_resolution"
        assert "[[NonExistentConcept]]" in issues[0].message
        assert "does not resolve" in issues[0].message

    def test_broken_wikilink_no_suggestions(self, tmp_path: Path) -> None:
        """Unresolvable wikilink with no similar concepts has empty suggestion."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        # Create a concept with a completely unrelated name
        _write_concept_file(
            lexibrary_dir / "concepts",
            "DatabaseConfig",
            title="DatabaseConfig",
            aliases=["db-config"],
            tags=["config"],
        )

        # Reference something completely unrelated
        (tmp_path / "src").mkdir(parents=True)
        (tmp_path / "src" / "api.py").write_text("# api", encoding="utf-8")
        _write_design_file(
            lexibrary_dir,
            "src/api.py",
            wikilinks=["ZzzzTotallyUnrelatedXxxx"],
        )

        issues = check_wikilink_resolution(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert issues[0].suggestion == ""

    def test_stack_post_wikilinks_checked(self, tmp_path: Path) -> None:
        """Wikilinks in Stack post bodies are also validated."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()
        (lexibrary_dir / "concepts").mkdir(parents=True)

        _write_stack_post(
            lexibrary_dir / "stack",
            "ST-001",
            "test-post",
            body_wikilinks=["MissingConcept"],
        )

        issues = check_wikilink_resolution(project_root, lexibrary_dir)
        assert len(issues) >= 1
        assert any(
            i.check == "wikilink_resolution" and "MissingConcept" in i.message for i in issues
        )

    def test_no_design_files_returns_empty(self, tmp_path: Path) -> None:
        """When no design files exist, no issues are returned."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        issues = check_wikilink_resolution(project_root, lexibrary_dir)
        assert issues == []

    def test_design_file_without_wikilinks_returns_empty(self, tmp_path: Path) -> None:
        """Design files with no wikilinks produce no issues."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()
        (lexibrary_dir / "concepts").mkdir(parents=True)

        (tmp_path / "src").mkdir(parents=True)
        (tmp_path / "src" / "main.py").write_text("# main", encoding="utf-8")
        _write_design_file(lexibrary_dir, "src/main.py")

        issues = check_wikilink_resolution(project_root, lexibrary_dir)
        assert issues == []

    def test_convention_title_wikilink_resolves(self, tmp_path: Path) -> None:
        """Wikilink matching a convention title resolves without false positive."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()
        (lexibrary_dir / "concepts").mkdir(parents=True)

        # Create a convention
        _write_convention_file(
            lexibrary_dir / "conventions",
            "All endpoints require auth decorator",
            tags=["security"],
        )

        # Create a design file that references the convention by title
        (tmp_path / "src").mkdir(parents=True)
        (tmp_path / "src" / "api.py").write_text("# api", encoding="utf-8")
        _write_design_file(
            lexibrary_dir,
            "src/api.py",
            wikilinks=["All endpoints require auth decorator"],
        )

        issues = check_wikilink_resolution(project_root, lexibrary_dir)
        assert issues == []

    def test_convention_alias_wikilink_resolves(self, tmp_path: Path) -> None:
        """Wikilink matching a convention alias resolves without false positive."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()
        (lexibrary_dir / "concepts").mkdir(parents=True)

        # Create a convention with an alias
        _write_convention_file(
            lexibrary_dir / "conventions",
            "All endpoints require auth decorator",
            aliases=["auth-decorator"],
            tags=["security"],
        )

        # Create a design file that references the convention by alias
        (tmp_path / "src").mkdir(parents=True)
        (tmp_path / "src" / "views.py").write_text("# views", encoding="utf-8")
        _write_design_file(
            lexibrary_dir,
            "src/views.py",
            wikilinks=["auth-decorator"],
        )

        issues = check_wikilink_resolution(project_root, lexibrary_dir)
        assert issues == []

    def test_convention_wikilink_in_stack_post_resolves(self, tmp_path: Path) -> None:
        """Convention wikilinks in Stack post bodies also resolve."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()
        (lexibrary_dir / "concepts").mkdir(parents=True)

        _write_convention_file(
            lexibrary_dir / "conventions",
            "Error Handling Pattern",
            aliases=["error-handling"],
            tags=["patterns"],
        )

        _write_stack_post(
            lexibrary_dir / "stack",
            "ST-001",
            "error-fix",
            body_wikilinks=["Error Handling Pattern"],
        )

        issues = check_wikilink_resolution(project_root, lexibrary_dir)
        assert issues == []

    def test_without_conventions_dir_still_works(self, tmp_path: Path) -> None:
        """Validator works when no conventions directory exists."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        # Create a concept
        _write_concept_file(
            lexibrary_dir / "concepts",
            "Authentication",
            title="Authentication",
            aliases=["auth"],
        )

        # Reference a concept (should still resolve without conventions dir)
        (tmp_path / "src").mkdir(parents=True)
        (tmp_path / "src" / "auth.py").write_text("# auth", encoding="utf-8")
        _write_design_file(
            lexibrary_dir,
            "src/auth.py",
            wikilinks=["Authentication"],
        )

        issues = check_wikilink_resolution(project_root, lexibrary_dir)
        assert issues == []


# ---------------------------------------------------------------------------
# check_file_existence
# ---------------------------------------------------------------------------


class TestCheckFileExistence:
    """Tests for check_file_existence."""

    def test_all_files_exist_returns_empty(self, tmp_path: Path) -> None:
        """When all referenced files exist, no issues are returned."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        # Create source file and its design file
        (tmp_path / "src").mkdir(parents=True)
        (tmp_path / "src" / "app.py").write_text("# app", encoding="utf-8")
        _write_design_file(lexibrary_dir, "src/app.py")

        issues = check_file_existence(project_root, lexibrary_dir)
        assert issues == []

    def test_missing_source_file_produces_error(self, tmp_path: Path) -> None:
        """Design file referencing a missing source file produces an error."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        # Create design file for a source that does NOT exist
        _write_design_file(lexibrary_dir, "src/old_module.py")

        issues = check_file_existence(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert issues[0].check == "file_existence"
        assert "src/old_module.py" in issues[0].message
        assert "does not exist" in issues[0].message

    def test_missing_stack_ref_file_produces_error(self, tmp_path: Path) -> None:
        """Stack post refs.files pointing to missing file produces an error."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_stack_post(
            lexibrary_dir / "stack",
            "ST-001",
            "test-post",
            file_refs=["src/nonexistent.py"],
        )

        issues = check_file_existence(project_root, lexibrary_dir)
        assert len(issues) >= 1
        file_issues = [i for i in issues if "src/nonexistent.py" in i.message]
        assert len(file_issues) == 1
        assert file_issues[0].severity == "error"
        assert file_issues[0].check == "file_existence"

    def test_missing_stack_ref_design_produces_error(self, tmp_path: Path) -> None:
        """Stack post refs.designs pointing to missing file produces an error."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_stack_post(
            lexibrary_dir / "stack",
            "ST-002",
            "design-ref",
            design_refs=[".lexibrary/designs/src/missing.py.md"],
        )

        issues = check_file_existence(project_root, lexibrary_dir)
        assert len(issues) >= 1
        design_issues = [i for i in issues if "missing.py.md" in i.message]
        assert len(design_issues) == 1
        assert design_issues[0].severity == "error"

    def test_existing_stack_refs_return_empty(self, tmp_path: Path) -> None:
        """When all Stack refs point to existing files, no issues returned."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        # Create the referenced file
        (tmp_path / "src").mkdir(parents=True)
        (tmp_path / "src" / "handler.py").write_text("# h", encoding="utf-8")

        _write_stack_post(
            lexibrary_dir / "stack",
            "ST-001",
            "test-post",
            file_refs=["src/handler.py"],
        )

        issues = check_file_existence(project_root, lexibrary_dir)
        assert issues == []

    def test_no_design_files_returns_empty(self, tmp_path: Path) -> None:
        """When no artifacts exist, no issues are returned."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        issues = check_file_existence(project_root, lexibrary_dir)
        assert issues == []


# ---------------------------------------------------------------------------
# check_concept_frontmatter
# ---------------------------------------------------------------------------


class TestCheckConceptFrontmatter:
    """Tests for check_concept_frontmatter."""

    def test_valid_frontmatter_returns_empty(self, tmp_path: Path) -> None:
        """Valid concept file with all fields produces no issues."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        concepts_dir = lexibrary_dir / "concepts"

        _write_concept_file(
            concepts_dir,
            "TestConcept",
            title="TestConcept",
            aliases=["tc"],
            tags=["general"],
            status="active",
        )

        issues = check_concept_frontmatter(project_root, lexibrary_dir)
        assert issues == []

    def test_missing_frontmatter_produces_error(self, tmp_path: Path) -> None:
        """Concept file without YAML frontmatter produces an error."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        concepts_dir = lexibrary_dir / "concepts"
        concepts_dir.mkdir(parents=True)

        path = concepts_dir / "BadConcept.md"
        path.write_text("# No frontmatter here\n\nJust content.\n", encoding="utf-8")

        issues = check_concept_frontmatter(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert issues[0].check == "concept_frontmatter"
        assert "Missing YAML frontmatter" in issues[0].message

    def test_missing_title_produces_error(self, tmp_path: Path) -> None:
        """Concept file missing the title field produces an error."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        concepts_dir = lexibrary_dir / "concepts"

        _write_concept_file(
            concepts_dir,
            "NoTitle",
            raw_content="""---
aliases: [nt]
tags: [test]
status: draft
---

Missing title field.
""",
        )

        issues = check_concept_frontmatter(project_root, lexibrary_dir)
        assert len(issues) >= 1
        title_issues = [i for i in issues if "title" in i.message]
        assert len(title_issues) == 1
        assert title_issues[0].severity == "error"

    def test_missing_multiple_fields_produces_multiple_errors(self, tmp_path: Path) -> None:
        """Concept file missing multiple fields produces one error per field."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        concepts_dir = lexibrary_dir / "concepts"

        _write_concept_file(
            concepts_dir,
            "Minimal",
            raw_content="""---
title: Minimal
id: CN-003
---

Just a title, nothing else.
""",
        )

        issues = check_concept_frontmatter(project_root, lexibrary_dir)
        # Missing: aliases, tags, status
        missing_fields = [i for i in issues if "Missing mandatory field" in i.message]
        assert len(missing_fields) == 3
        field_names = {i.message.split(": ")[-1] for i in missing_fields}
        assert field_names == {"aliases", "tags", "status"}

    def test_invalid_status_produces_error(self, tmp_path: Path) -> None:
        """Concept file with invalid status value produces an error."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        concepts_dir = lexibrary_dir / "concepts"

        _write_concept_file(
            concepts_dir,
            "BadStatus",
            raw_content="""---
title: BadStatus
id: CN-002
aliases: [bs]
tags: [test]
status: invalid_status
---

Bad status value.
""",
        )

        issues = check_concept_frontmatter(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert "Invalid status" in issues[0].message
        assert "invalid_status" in issues[0].message

    def test_invalid_yaml_produces_error(self, tmp_path: Path) -> None:
        """Concept file with malformed YAML produces an error."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        concepts_dir = lexibrary_dir / "concepts"

        _write_concept_file(
            concepts_dir,
            "BadYaml",
            raw_content="""---
title: [unterminated
id: CN-001
aliases: broken
---

Bad YAML.
""",
        )

        issues = check_concept_frontmatter(project_root, lexibrary_dir)
        assert len(issues) >= 1
        assert any(i.check == "concept_frontmatter" for i in issues)

    def test_no_concepts_dir_returns_empty(self, tmp_path: Path) -> None:
        """When no concepts directory exists, no issues are returned."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        issues = check_concept_frontmatter(project_root, lexibrary_dir)
        assert issues == []

    def test_all_valid_statuses_pass(self, tmp_path: Path) -> None:
        """Valid status values (draft, active, deprecated) produce no issues."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        concepts_dir = lexibrary_dir / "concepts"

        for status in ("draft", "active", "deprecated"):
            _write_concept_file(
                concepts_dir,
                f"Concept_{status}",
                title=f"Concept {status}",
                aliases=[status],
                tags=["test"],
                status=status,
            )

        issues = check_concept_frontmatter(project_root, lexibrary_dir)
        assert issues == []
