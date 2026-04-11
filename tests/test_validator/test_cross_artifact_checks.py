"""Unit tests for cross-artifact validation checks (Group 3).

Tests check_duplicate_aliases, check_duplicate_slugs, check_stack_refs_validity,
check_design_deps_existence, and check_aindex_entries.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from lexibrary.validator.checks import (
    check_aindex_entries,
    check_design_deps_existence,
    check_duplicate_aliases,
    check_duplicate_slugs,
    check_stack_refs_validity,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_concept_file(
    concepts_dir: Path,
    name: str,
    *,
    title: str | None = None,
    aliases: list[str] | None = None,
    tags: list[str] | None = None,
    status: str = "active",
) -> Path:
    """Write a concept file with YAML frontmatter."""
    concepts_dir.mkdir(parents=True, exist_ok=True)
    path = concepts_dir / f"{name}.md"
    title = title or name
    aliases = aliases if aliases is not None else []
    tags = tags if tags is not None else ["general"]

    aliases_yaml = "[" + ", ".join(aliases) + "]"
    tags_yaml = "[" + ", ".join(tags) + "]"

    content = f"""---
title: {title}
id: CN-001
aliases: {aliases_yaml}
tags: {tags_yaml}
status: {status}
---

{title} is a concept used in the system.
"""
    path.write_text(content, encoding="utf-8")
    return path


def _write_convention_file(
    conventions_dir: Path,
    slug: str,
    *,
    title: str | None = None,
) -> Path:
    """Write a minimal convention file."""
    conventions_dir.mkdir(parents=True, exist_ok=True)
    path = conventions_dir / f"{slug}.md"
    title = title or slug.replace("-", " ").title()

    content = f"""---
title: {title}
id: CV-001
scope: project
tags: [general]
status: active
---

{title} is a convention.
"""
    path.write_text(content, encoding="utf-8")
    return path


def _write_stack_post(
    stack_dir: Path,
    post_id: str,
    slug: str,
    *,
    file_refs: list[str] | None = None,
    design_refs: list[str] | None = None,
) -> Path:
    """Write a minimal Stack post file."""
    stack_dir.mkdir(parents=True, exist_ok=True)
    path = stack_dir / f"{post_id}-{slug}.md"

    refs_lines: list[str] = []
    if file_refs or design_refs:
        refs_lines.append("refs:")
        if file_refs:
            refs_lines.append("  files: [" + ", ".join(file_refs) + "]")
        if design_refs:
            refs_lines.append("  designs: [" + ", ".join(design_refs) + "]")

    refs_block = "\n".join(refs_lines) if refs_lines else "refs: {}"

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
"""
    path.write_text(content, encoding="utf-8")
    return path


def _write_design_file(
    lexibrary_dir: Path,
    source_path: str,
    *,
    dependencies: list[str] | None = None,
    dependents: list[str] | None = None,
) -> Path:
    """Write a minimal valid design file into the lexibrary mirror tree."""
    design_path = lexibrary_dir / "designs" / f"{source_path}.md"
    design_path.parent.mkdir(parents=True, exist_ok=True)

    deps_section = "(none)"
    if dependencies:
        deps_section = "\n".join(f"- {d}" for d in dependencies)

    dependents_section = "(none)"
    if dependents:
        dependents_section = "\n".join(f"- {d}" for d in dependents)

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

{deps_section}

## Dependents

{dependents_section}

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


def _write_aindex_file(
    lexibrary_dir: Path,
    directory_path: str,
    entries: list[tuple[str, str, str]],
) -> Path:
    """Write a minimal .aindex file.

    entries is a list of (name, entry_type, description) tuples.
    """
    designs_dir = lexibrary_dir / "designs"
    aindex_dir = designs_dir / directory_path
    aindex_dir.mkdir(parents=True, exist_ok=True)
    aindex_path = aindex_dir / ".aindex"

    # Build table rows
    rows = ""
    if entries:
        rows = "| Name | Type | Description |\n| --- | --- | --- |\n"
        for name, entry_type, desc in entries:
            display_name = f"{name}/" if entry_type == "dir" else name
            rows += f"| `{display_name}` | {entry_type} | {desc} |\n"
    else:
        rows = "(none)"

    now = datetime.now().isoformat()
    meta = (
        f'<!-- lexibrary:meta source="{directory_path}"'
        f' source_hash="abc123" generated="{now}"'
        f' generator="test" -->'
    )
    content = f"""# {directory_path}

This is the billboard for {directory_path}.

## Child Map

{rows}

{meta}
"""
    aindex_path.write_text(content, encoding="utf-8")
    return aindex_path


# ---------------------------------------------------------------------------
# check_duplicate_aliases
# ---------------------------------------------------------------------------


class TestCheckDuplicateAliases:
    """Tests for check_duplicate_aliases."""

    def test_unique_aliases_returns_empty(self, tmp_path: Path) -> None:
        """When all aliases are unique, no issues are returned."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_concept_file(
            lexibrary_dir / "concepts",
            "alpha",
            title="Alpha",
            aliases=["a"],
        )
        _write_concept_file(
            lexibrary_dir / "concepts",
            "beta",
            title="Beta",
            aliases=["b"],
        )

        issues = check_duplicate_aliases(project_root, lexibrary_dir)
        assert issues == []

    def test_duplicate_alias_across_files(self, tmp_path: Path) -> None:
        """Duplicate alias across two concept files produces issues."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_concept_file(
            lexibrary_dir / "concepts",
            "alpha",
            title="Alpha",
            aliases=["shared-name"],
        )
        _write_concept_file(
            lexibrary_dir / "concepts",
            "beta",
            title="Beta",
            aliases=["shared-name"],
        )

        issues = check_duplicate_aliases(project_root, lexibrary_dir)
        assert len(issues) >= 2
        assert all(i.check == "duplicate_aliases" for i in issues)
        assert all(i.severity == "error" for i in issues)
        # Both files should be mentioned
        artifacts = {i.artifact for i in issues}
        assert "concepts/alpha.md" in artifacts
        assert "concepts/beta.md" in artifacts

    def test_title_duplicates_alias(self, tmp_path: Path) -> None:
        """A concept title duplicating another concept's alias is flagged."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_concept_file(
            lexibrary_dir / "concepts",
            "alpha",
            title="Alpha",
            aliases=["beta-alias"],
        )
        _write_concept_file(
            lexibrary_dir / "concepts",
            "beta",
            title="beta-alias",
            aliases=[],
        )

        issues = check_duplicate_aliases(project_root, lexibrary_dir)
        assert len(issues) >= 2
        assert all(i.check == "duplicate_aliases" for i in issues)

    def test_missing_directory_returns_empty(self, tmp_path: Path) -> None:
        """When concepts directory doesn't exist, returns empty."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        issues = check_duplicate_aliases(project_root, lexibrary_dir)
        assert issues == []

    def test_case_insensitive_duplicate(self, tmp_path: Path) -> None:
        """Aliases that differ only in case are treated as duplicates."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_concept_file(
            lexibrary_dir / "concepts",
            "alpha",
            title="Alpha",
            aliases=["MyAlias"],
        )
        _write_concept_file(
            lexibrary_dir / "concepts",
            "beta",
            title="Beta",
            aliases=["myalias"],
        )

        issues = check_duplicate_aliases(project_root, lexibrary_dir)
        assert len(issues) >= 2


# ---------------------------------------------------------------------------
# check_duplicate_slugs
# ---------------------------------------------------------------------------


class TestCheckDuplicateSlugs:
    """Tests for check_duplicate_slugs."""

    def test_unique_slugs_returns_empty(self, tmp_path: Path) -> None:
        """When all slugs are unique, no issues are returned."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_concept_file(
            lexibrary_dir / "concepts",
            "alpha",
            title="Alpha",
        )
        _write_convention_file(
            lexibrary_dir / "conventions",
            "beta",
        )

        issues = check_duplicate_slugs(project_root, lexibrary_dir)
        assert issues == []

    def test_duplicate_slug_across_types_allowed(self, tmp_path: Path) -> None:
        """Same slug in concepts/ and conventions/ is allowed — slugs need only
        be unique within a type, not globally across types."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_concept_file(
            lexibrary_dir / "concepts",
            "my-thing",
            title="My Thing",
        )
        _write_convention_file(
            lexibrary_dir / "conventions",
            "my-thing",
            title="My Thing Convention",
        )

        issues = check_duplicate_slugs(project_root, lexibrary_dir)
        assert issues == [], (
            "Cross-type slug collisions should not be reported; "
            "each artifact type is its own namespace"
        )

    def test_duplicate_slugs_within_concepts(self, tmp_path: Path) -> None:
        """Two concept files with different ID prefixes but the same slug produce issues."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        # Two concept files that share the slug "error-handling" after prefix stripping.
        # ID-prefixed filenames allow both to exist on the filesystem simultaneously.
        concepts_dir = lexibrary_dir / "concepts"
        concepts_dir.mkdir(parents=True, exist_ok=True)
        (concepts_dir / "CN-001-error-handling.md").write_text(
            "---\ntitle: Error Handling\nid: CN-001\n"
            "aliases: []\ntags: [general]\nstatus: active\n---\n"
        )
        (concepts_dir / "CN-002-error-handling.md").write_text(
            "---\ntitle: Error Handling v2\nid: CN-002\n"
            "aliases: []\ntags: [general]\nstatus: active\n---\n"
        )

        issues = check_duplicate_slugs(project_root, lexibrary_dir)
        assert len(issues) == 2
        assert all(i.check == "duplicate_slugs" for i in issues)
        assert all(i.severity == "warning" for i in issues)
        artifacts = {i.artifact for i in issues}
        assert "concepts/CN-001-error-handling.md" in artifacts
        assert "concepts/CN-002-error-handling.md" in artifacts
        # Message should name the artifact type, not just say "multiple files"
        assert all("concept" in i.message for i in issues)

    def test_missing_directories_returns_empty(self, tmp_path: Path) -> None:
        """When neither concepts nor conventions exist, returns empty."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        issues = check_duplicate_slugs(project_root, lexibrary_dir)
        assert issues == []


# ---------------------------------------------------------------------------
# check_stack_refs_validity
# ---------------------------------------------------------------------------


class TestCheckStackRefsValidity:
    """Tests for check_stack_refs_validity."""

    def test_valid_refs_returns_empty(self, tmp_path: Path) -> None:
        """When all refs exist on disk, no issues are returned."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        # Create the referenced files
        src_file = project_root / "src" / "main.py"
        src_file.parent.mkdir(parents=True, exist_ok=True)
        src_file.write_text("# main", encoding="utf-8")

        design_file = lexibrary_dir / "designs" / "src" / "main.py.md"
        design_file.parent.mkdir(parents=True, exist_ok=True)
        design_file.write_text("# design", encoding="utf-8")

        _write_stack_post(
            lexibrary_dir / "stack",
            "ST-001",
            "test",
            file_refs=["src/main.py"],
            design_refs=[".lexibrary/designs/src/main.py.md"],
        )

        issues = check_stack_refs_validity(project_root, lexibrary_dir)
        assert issues == []

    def test_broken_file_ref(self, tmp_path: Path) -> None:
        """A refs.files entry that doesn't exist produces a warning."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_stack_post(
            lexibrary_dir / "stack",
            "ST-001",
            "test",
            file_refs=["src/nonexistent.py"],
        )

        issues = check_stack_refs_validity(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert issues[0].check == "stack_refs_validity"
        assert issues[0].severity == "warning"
        assert "src/nonexistent.py" in issues[0].message

    def test_broken_design_ref(self, tmp_path: Path) -> None:
        """A refs.designs entry that doesn't exist produces a warning."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_stack_post(
            lexibrary_dir / "stack",
            "ST-001",
            "test",
            design_refs=[".lexibrary/designs/missing.py.md"],
        )

        issues = check_stack_refs_validity(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert issues[0].check == "stack_refs_validity"
        assert "missing.py.md" in issues[0].message

    def test_missing_stack_dir_returns_empty(self, tmp_path: Path) -> None:
        """When stack directory doesn't exist, returns empty."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        issues = check_stack_refs_validity(project_root, lexibrary_dir)
        assert issues == []

    def test_multiple_broken_refs(self, tmp_path: Path) -> None:
        """Multiple broken refs in one post produce multiple issues."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_stack_post(
            lexibrary_dir / "stack",
            "ST-001",
            "test",
            file_refs=["src/a.py", "src/b.py"],
            design_refs=[".lexibrary/designs/c.py.md"],
        )

        issues = check_stack_refs_validity(project_root, lexibrary_dir)
        assert len(issues) == 3


# ---------------------------------------------------------------------------
# check_design_deps_existence
# ---------------------------------------------------------------------------


class TestCheckDesignDepsExistence:
    """Tests for check_design_deps_existence."""

    def test_valid_deps_returns_empty(self, tmp_path: Path) -> None:
        """When all design deps exist, no issues are returned."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        # Create both design files so they can reference each other
        _write_design_file(
            lexibrary_dir,
            "src/alpha.py",
            dependencies=["src/beta.py"],
        )
        _write_design_file(
            lexibrary_dir,
            "src/beta.py",
            dependents=["src/alpha.py"],
        )

        issues = check_design_deps_existence(project_root, lexibrary_dir)
        assert issues == []

    def test_missing_dependency(self, tmp_path: Path) -> None:
        """A dependency pointing to a nonexistent design file is flagged."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_design_file(
            lexibrary_dir,
            "src/alpha.py",
            dependencies=["src/nonexistent.py"],
        )

        issues = check_design_deps_existence(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert issues[0].check == "design_deps_existence"
        assert issues[0].severity == "warning"
        assert "nonexistent.py" in issues[0].message

    def test_missing_dependent(self, tmp_path: Path) -> None:
        """A dependent pointing to a nonexistent design file is flagged."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_design_file(
            lexibrary_dir,
            "src/alpha.py",
            dependents=["src/missing.py"],
        )

        issues = check_design_deps_existence(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert issues[0].check == "design_deps_existence"
        assert "missing.py" in issues[0].message

    def test_none_deps_skipped(self, tmp_path: Path) -> None:
        """Design files with (none) dependencies produce no issues."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_design_file(
            lexibrary_dir,
            "src/alpha.py",
        )

        issues = check_design_deps_existence(project_root, lexibrary_dir)
        assert issues == []

    def test_missing_designs_dir_returns_empty(self, tmp_path: Path) -> None:
        """When designs directory doesn't exist, returns empty."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        issues = check_design_deps_existence(project_root, lexibrary_dir)
        assert issues == []

    def test_gitignored_missing_dependency_is_skipped(self, tmp_path: Path) -> None:
        """A dependency pointing to a gitignored path produces no issue.

        This guards against false positives for generated code (e.g.
        baml_client/) that is legitimately absent from the design library
        because the archivist skips gitignored sources.
        """
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        # Write a .gitignore that ignores the generated directory
        (project_root / ".gitignore").write_text("generated/\n", encoding="utf-8")

        # Design file that lists a dep inside the gitignored directory
        _write_design_file(
            lexibrary_dir,
            "src/alpha.py",
            dependencies=["src/generated/client.py"],
        )

        issues = check_design_deps_existence(project_root, lexibrary_dir)
        assert issues == [], (
            f"Expected no issues for a dependency under a gitignored path, got: {issues}"
        )

    def test_gitignored_missing_dependent_is_skipped(self, tmp_path: Path) -> None:
        """A dependent pointing to a gitignored path produces no issue."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        (project_root / ".gitignore").write_text("generated/\n", encoding="utf-8")

        _write_design_file(
            lexibrary_dir,
            "src/alpha.py",
            dependents=["src/generated/consumer.py"],
        )

        issues = check_design_deps_existence(project_root, lexibrary_dir)
        assert issues == []

    def test_non_ignored_missing_dep_still_produces_warning(self, tmp_path: Path) -> None:
        """A missing dep that is NOT gitignored still produces a warning.

        Regression guard: the ignore-filter must not suppress genuine issues.
        """
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        # .gitignore ignores only 'generated/', not 'src/'
        (project_root / ".gitignore").write_text("generated/\n", encoding="utf-8")

        _write_design_file(
            lexibrary_dir,
            "src/alpha.py",
            dependencies=["src/nonexistent.py"],
        )

        issues = check_design_deps_existence(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert issues[0].check == "design_deps_existence"
        assert issues[0].severity == "warning"
        assert "nonexistent.py" in issues[0].message


# ---------------------------------------------------------------------------
# check_aindex_entries
# ---------------------------------------------------------------------------


class TestCheckAindexEntries:
    """Tests for check_aindex_entries."""

    def test_valid_entries_returns_empty(self, tmp_path: Path) -> None:
        """When all child map entries exist on disk, no issues are returned."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        # Create the actual source directory and files
        src_dir = project_root / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        (src_dir / "main.py").write_text("# main", encoding="utf-8")
        (src_dir / "utils").mkdir(exist_ok=True)

        _write_aindex_file(
            lexibrary_dir,
            "src",
            [
                ("main.py", "file", "Main module"),
                ("utils", "dir", "Utility functions"),
            ],
        )

        issues = check_aindex_entries(project_root, lexibrary_dir)
        assert issues == []

    def test_stale_file_entry(self, tmp_path: Path) -> None:
        """A file entry that doesn't exist on disk is flagged."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        # Create directory but not the referenced file
        src_dir = project_root / "src"
        src_dir.mkdir(parents=True, exist_ok=True)

        _write_aindex_file(
            lexibrary_dir,
            "src",
            [("deleted.py", "file", "A deleted file")],
        )

        issues = check_aindex_entries(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert issues[0].check == "aindex_entries"
        assert issues[0].severity == "warning"
        assert "deleted.py" in issues[0].message

    def test_stale_dir_entry(self, tmp_path: Path) -> None:
        """A directory entry that doesn't exist on disk is flagged."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        src_dir = project_root / "src"
        src_dir.mkdir(parents=True, exist_ok=True)

        _write_aindex_file(
            lexibrary_dir,
            "src",
            [("removed_pkg", "dir", "A removed package")],
        )

        issues = check_aindex_entries(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert issues[0].check == "aindex_entries"
        assert "removed_pkg" in issues[0].message

    def test_mixed_valid_and_stale(self, tmp_path: Path) -> None:
        """Mix of valid and stale entries: only stale ones flagged."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        src_dir = project_root / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        (src_dir / "exists.py").write_text("# exists", encoding="utf-8")

        _write_aindex_file(
            lexibrary_dir,
            "src",
            [
                ("exists.py", "file", "An existing file"),
                ("gone.py", "file", "A deleted file"),
            ],
        )

        issues = check_aindex_entries(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert "gone.py" in issues[0].message

    def test_missing_designs_dir_returns_empty(self, tmp_path: Path) -> None:
        """When designs directory doesn't exist, returns empty."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        issues = check_aindex_entries(project_root, lexibrary_dir)
        assert issues == []
