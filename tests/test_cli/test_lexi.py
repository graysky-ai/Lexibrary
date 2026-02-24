"""Tests for the agent-facing CLI (lexi) application."""

from __future__ import annotations

import hashlib
import os
from datetime import datetime
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from lexibrary.cli import lexi_app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------


class TestHelp:
    def test_help_lists_all_commands(self) -> None:
        result = runner.invoke(lexi_app, ["--help"])
        assert result.exit_code == 0
        for cmd in (
            "lookup",
            "concepts",
            "search",
            "stack",
            "concept",
            "describe",
            "validate",
            "status",
        ):
            assert cmd in result.output

    def test_help_does_not_include_maintenance_commands(self) -> None:
        result = runner.invoke(lexi_app, ["--help"])
        assert result.exit_code == 0
        # Extract the listed command names from Typer help output.
        # Typer formats commands as "│ command_name  Description... │"
        import re

        command_names = re.findall(r"│\s+(\w+)\s{2,}", result.output)
        # Maintenance commands should NOT be registered as top-level commands in lexi
        for cmd in ("init", "update", "setup", "daemon", "index"):
            assert cmd not in command_names, f"Maintenance command '{cmd}' should not be in lexi"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_project(tmp_path: Path) -> Path:
    """Create a minimal initialized project at tmp_path with some source files."""
    (tmp_path / ".lexibrary").mkdir()
    (tmp_path / ".lexibrary" / "config.yaml").write_text("")
    # Create source directory with a Python file
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hello')\n")
    (tmp_path / "src" / "utils.py").write_text("x = 1\ny = 2\n")
    return tmp_path


def _setup_archivist_project(tmp_path: Path) -> Path:
    """Create a minimal project with .lexibrary and source files."""
    (tmp_path / ".lexibrary").mkdir()
    (tmp_path / ".lexibrary" / "config.yaml").write_text("")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def hello():\n    pass\n")
    (tmp_path / "src" / "utils.py").write_text("x = 1\n")
    return tmp_path


def _create_design_file(tmp_path: Path, source_rel: str, source_content: str) -> Path:
    """Create a design file in .lexibrary mirror tree with correct metadata footer."""
    content_hash = hashlib.sha256(source_content.encode()).hexdigest()
    design_path = tmp_path / ".lexibrary" / f"{source_rel}.md"
    design_path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now().isoformat()
    design_content = f"""---
description: Design file for {source_rel}
updated_by: archivist
---

# {source_rel}

Test design file content.

## Interface Contract

```python
def hello(): ...
```

## Dependencies

- (none)

## Dependents

- (none)

<!-- lexibrary:meta
source: {source_rel}
source_hash: {content_hash}
design_hash: placeholder
generated: {now}
generator: lexibrary-v2
-->
"""
    design_path.write_text(design_content, encoding="utf-8")
    return design_path


def _create_aindex(tmp_path: Path, directory_rel: str, billboard: str) -> Path:
    """Create a .aindex file in the .lexibrary mirror tree."""
    aindex_path = tmp_path / ".lexibrary" / directory_rel / ".aindex"
    aindex_path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now().isoformat()
    content = f"""# {directory_rel}/

{billboard}

## Child Map

| Name | Type | Description |
| --- | --- | --- |
| `main.py` | file | Main module |
| `utils.py` | file | Utility functions |

## Local Conventions

(none)

<!-- lexibrary:meta source="{directory_rel}" source_hash="abc123" """
    content += f"""generated="{now}" generator="lexibrary-v2" -->
"""
    aindex_path.write_text(content, encoding="utf-8")
    return aindex_path


def _create_concept_file(
    tmp_path: Path,
    name: str,
    *,
    tags: list[str] | None = None,
    status: str = "active",
    aliases: list[str] | None = None,
    summary: str = "",
) -> Path:
    """Create a concept markdown file in .lexibrary/concepts/."""
    import re  # noqa: PLC0415

    concepts_dir = tmp_path / ".lexibrary" / "concepts"
    concepts_dir.mkdir(parents=True, exist_ok=True)

    resolved_tags = tags or []
    resolved_aliases = aliases or []

    fm_data: dict[str, object] = {
        "title": name,
        "aliases": resolved_aliases,
        "tags": resolved_tags,
        "status": status,
    }
    fm_str = yaml.dump(fm_data, default_flow_style=False, sort_keys=False).rstrip("\n")

    # PascalCase filename
    words = re.split(r"[^a-zA-Z0-9]+", name)
    pascal = "".join(w.capitalize() for w in words if w)
    file_path = concepts_dir / f"{pascal}.md"

    body = f"---\n{fm_str}\n---\n\n{summary}\n\n## Details\n\n## Decision Log\n\n## Related\n"
    file_path.write_text(body, encoding="utf-8")
    return file_path


def _setup_stack_project(tmp_path: Path) -> Path:
    """Create a minimal initialized project with stack dir at tmp_path."""
    (tmp_path / ".lexibrary").mkdir()
    (tmp_path / ".lexibrary" / "config.yaml").write_text("")
    (tmp_path / ".lexibrary" / "stack").mkdir()
    return tmp_path


def _create_stack_post(
    tmp_path: Path,
    post_id: str = "ST-001",
    title: str = "Bug in auth module",
    tags: list[str] | None = None,
    status: str = "open",
    author: str = "tester",
    votes: int = 0,
    problem: str = "Something is broken",
    evidence: list[str] | None = None,
    bead: str | None = None,
    refs_files: list[str] | None = None,
    refs_concepts: list[str] | None = None,
) -> Path:
    """Create a stack post file for testing."""
    resolved_tags = tags or ["auth"]
    resolved_evidence = evidence or []
    import re as _re

    title_slug = _re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:50]
    filename = f"{post_id}-{title_slug}.md"
    stack_dir = tmp_path / ".lexibrary" / "stack"
    stack_dir.mkdir(parents=True, exist_ok=True)
    post_path = stack_dir / filename

    fm_data: dict[str, object] = {
        "id": post_id,
        "title": title,
        "tags": resolved_tags,
        "status": status,
        "created": "2026-01-15",
        "author": author,
        "bead": bead,
        "votes": votes,
        "duplicate_of": None,
        "refs": {
            "concepts": refs_concepts or [],
            "files": refs_files or [],
            "designs": [],
        },
    }
    fm_str = yaml.dump(fm_data, default_flow_style=False, sort_keys=False).rstrip("\n")

    parts = [f"---\n{fm_str}\n---\n\n## Problem\n\n{problem}\n\n### Evidence\n\n"]
    for item in resolved_evidence:
        parts.append(f"- {item}\n")
    parts.append("\n")

    post_path.write_text("".join(parts), encoding="utf-8")
    return post_path


def _create_stack_post_with_answer(
    tmp_path: Path,
    post_id: str = "ST-001",
    title: str = "Bug in auth module",
    answer_body: str = "Try restarting the service.",
) -> Path:
    """Create a stack post with one answer for testing."""
    post_path = _create_stack_post(tmp_path, post_id=post_id, title=title)
    # Append an answer section
    content = post_path.read_text(encoding="utf-8")
    answer_section = (
        "## Answers\n\n"
        "### A1\n\n"
        "**Date:** 2026-01-16 | **Author:** helper | **Votes:** 0\n\n"
        f"{answer_body}\n\n"
        "#### Comments\n\n"
    )
    content += answer_section
    post_path.write_text(content, encoding="utf-8")
    return post_path


def _create_aindex_with_conventions(
    tmp_path: Path,
    directory_rel: str,
    billboard: str,
    conventions: list[str] | None = None,
) -> Path:
    """Create a .aindex file with optional local conventions."""
    aindex_file = tmp_path / ".lexibrary" / directory_rel / ".aindex"
    aindex_file.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now().isoformat()

    conv_section = "\n".join(f"- {c}" for c in conventions) if conventions else "(none)"

    meta = (
        f'<!-- lexibrary:meta source="{directory_rel}" '
        f'source_hash="abc123" generated="{now}" '
        f'generator="lexibrary-v2" -->'
    )
    content = f"""# {directory_rel}/

{billboard}

## Child Map

| Name | Type | Description |
| --- | --- | --- |
| `main.py` | file | Main module |

## Local Conventions

{conv_section}

{meta}
"""
    aindex_file.write_text(content, encoding="utf-8")
    return aindex_file


def _create_design_file_with_tags(
    tmp_path: Path, source_rel: str, description: str, tags: list[str]
) -> Path:
    """Create a design file with tags for unified search testing."""
    content_hash = hashlib.sha256(b"test").hexdigest()
    design_path = tmp_path / ".lexibrary" / f"{source_rel}.md"
    design_path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now().isoformat()
    tags_section = "\n".join(f"- {t}" for t in tags) if tags else "- (none)"
    design_content = f"""---
description: {description}
updated_by: archivist
---

# {source_rel}

{description}

## Interface Contract

```python
def placeholder(): ...
```

## Dependencies

- (none)

## Dependents

- (none)

## Tags

{tags_section}

<!-- lexibrary:meta
source: {source_rel}
source_hash: {content_hash}
design_hash: placeholder
generated: {now}
generator: lexibrary-v2
-->
"""
    design_path.write_text(design_content, encoding="utf-8")
    return design_path


def _setup_unified_search_project(tmp_path: Path) -> Path:
    """Create a project with concepts, design files, and stack posts for search tests."""
    project = tmp_path
    (project / ".lexibrary").mkdir()
    (project / ".lexibrary" / "config.yaml").write_text("")
    (project / "src").mkdir()
    (project / "src" / "auth.py").write_text("def login(): pass\n")
    (project / "src" / "models.py").write_text("class User: pass\n")

    # Create concept files
    _create_concept_file(project, "Authentication", tags=["security", "auth"], summary="Auth logic")
    _create_concept_file(project, "Rate Limiting", tags=["performance"], summary="Throttling")

    # Create design files with tags
    _create_design_file_with_tags(
        project,
        "src/auth.py",
        "Authentication flow handler",
        ["security", "auth"],
    )
    _create_design_file_with_tags(project, "src/models.py", "Data models for users", ["models"])

    # Create stack posts
    _create_stack_post(
        project,
        post_id="ST-001",
        title="Login timeout bug",
        tags=["auth", "bug"],
        problem="Login times out after 30s",
        refs_files=["src/auth.py"],
    )
    _create_stack_post(
        project,
        post_id="ST-002",
        title="Rate limiter memory leak",
        tags=["performance"],
        problem="Memory grows over time",
        refs_files=["src/models.py"],
    )

    return project


# ---------------------------------------------------------------------------
# Verify lexi index is no longer registered
# ---------------------------------------------------------------------------


class TestIndexCommandRemoved:
    """Verify that `lexi index` is no longer registered."""

    def test_index_not_in_help(self) -> None:
        """lexi --help should not list 'index' as a command."""
        import re

        result = runner.invoke(lexi_app, ["--help"])
        assert result.exit_code == 0
        command_names = re.findall(r"│\s+(\w+)\s{2,}", result.output)
        assert "index" not in command_names, "'index' should not be in lexi --help"


# ---------------------------------------------------------------------------
# Lookup command tests
# ---------------------------------------------------------------------------


class TestLookupCommand:
    """Tests for the `lexi lookup` command."""

    def test_lookup_exists(self, tmp_path: Path) -> None:
        """Lookup with existing design file prints its content."""
        project = _setup_archivist_project(tmp_path)
        source_content = "def hello():\n    pass\n"
        _create_design_file(project, "src/main.py", source_content)

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            result = runner.invoke(lexi_app, ["lookup", "src/main.py"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 0
        assert "Interface Contract" in result.output

    def test_lookup_missing(self, tmp_path: Path) -> None:
        """Lookup without design file suggests running lexictl update."""
        project = _setup_archivist_project(tmp_path)

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            result = runner.invoke(lexi_app, ["lookup", "src/main.py"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 1
        assert "No design file found" in result.output
        assert "lexictl update" in result.output

    def test_lookup_stale(self, tmp_path: Path) -> None:
        """Lookup with changed source file shows staleness warning."""
        project = _setup_archivist_project(tmp_path)
        # Create design file with the original content hash
        original_content = "def hello():\n    pass\n"
        _create_design_file(project, "src/main.py", original_content)

        # Now change the source file
        (project / "src" / "main.py").write_text("def hello():\n    return 42\n")

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            result = runner.invoke(lexi_app, ["lookup", "src/main.py"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 0
        assert "Warning" in result.output
        assert "changed" in result.output

    def test_lookup_outside_scope(self, tmp_path: Path) -> None:
        """Lookup outside scope_root should print message and exit."""
        project = _setup_archivist_project(tmp_path)
        # Set scope_root to src/ only
        (project / ".lexibrary" / "config.yaml").write_text("scope_root: src\n")
        # Create a file outside scope
        (project / "scripts").mkdir()
        (project / "scripts" / "deploy.sh").write_text("#!/bin/bash\n")

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            result = runner.invoke(lexi_app, ["lookup", "scripts/deploy.sh"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 1
        assert "outside" in result.output


# ---------------------------------------------------------------------------
# Lookup convention inheritance tests
# ---------------------------------------------------------------------------


class TestLookupConventionInheritance:
    """Tests for convention inheritance in `lexi lookup`."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexi_app, args)
        finally:
            os.chdir(old_cwd)

    def test_conventions_from_multiple_parents(self, tmp_path: Path) -> None:
        """Conventions from multiple parent directories shown in bottom-up order."""
        project = _setup_archivist_project(tmp_path)
        # Create nested structure: src/payments/stripe/charge.py
        (project / "src" / "payments").mkdir(parents=True)
        (project / "src" / "payments" / "stripe").mkdir()
        source_content = "def charge(): pass\n"
        (project / "src" / "payments" / "stripe" / "charge.py").write_text(source_content)

        # Create design file for the source
        _create_design_file(project, "src/payments/stripe/charge.py", source_content)

        # Create .aindex files with conventions at different levels
        _create_aindex_with_conventions(
            project,
            "src/payments",
            "Payment processing",
            ["All monetary values use Decimal"],
        )
        _create_aindex_with_conventions(
            project,
            "src",
            "Source code root",
            ["Use UTC everywhere"],
        )

        result = self._invoke(project, ["lookup", "src/payments/stripe/charge.py"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]

        # Should have conventions section
        assert "Applicable Conventions" in output
        # Closest directory first
        assert "src/payments/" in output
        assert "All monetary values use Decimal" in output
        assert "Use UTC everywhere" in output
        # payments/ should appear before src/ (closest first)
        payments_idx = output.index("src/payments/")
        src_idx = output.index("From `src/`")
        assert payments_idx < src_idx

    def test_no_conventions_means_no_section(self, tmp_path: Path) -> None:
        """No conventions in any parent means no extra section appended."""
        project = _setup_archivist_project(tmp_path)
        source_content = "def hello():\n    pass\n"
        _create_design_file(project, "src/main.py", source_content)

        # Create .aindex with no conventions
        _create_aindex_with_conventions(project, "src", "Source root", conventions=None)

        result = self._invoke(project, ["lookup", "src/main.py"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]

        # Should NOT have conventions section
        assert "Applicable Conventions" not in output

    def test_missing_aindex_silently_skipped(self, tmp_path: Path) -> None:
        """Missing .aindex files are silently skipped without errors."""
        project = _setup_archivist_project(tmp_path)
        # Create nested dir without .aindex at intermediate level
        (project / "src" / "api").mkdir(parents=True)
        source_content = "def endpoint(): pass\n"
        (project / "src" / "api" / "auth.py").write_text(source_content)
        _create_design_file(project, "src/api/auth.py", source_content)

        # Only create .aindex at src/ level (not src/api/)
        _create_aindex_with_conventions(
            project,
            "src",
            "Source root",
            ["Use type hints everywhere"],
        )

        result = self._invoke(project, ["lookup", "src/api/auth.py"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]

        # Should still pick up conventions from src/
        assert "Applicable Conventions" in output
        assert "Use type hints everywhere" in output
        # No errors about missing .aindex
        assert "Error" not in output

    def test_walk_stops_at_scope_root(self, tmp_path: Path) -> None:
        """Convention walk does not traverse above scope_root."""
        project = _setup_archivist_project(tmp_path)
        # Set scope_root to src/
        (project / ".lexibrary" / "config.yaml").write_text("scope_root: src\n")

        source_content = "def handler(): pass\n"
        (project / "src" / "main.py").write_text(source_content)
        _create_design_file(project, "src/main.py", source_content)

        # Create .aindex at project root (above scope_root) with conventions
        _create_aindex_with_conventions(
            project,
            ".",
            "Project root",
            ["Root convention that should NOT appear"],
        )
        # Create .aindex at src/ (within scope_root) with conventions
        _create_aindex_with_conventions(
            project,
            "src",
            "Source root",
            ["Src convention that SHOULD appear"],
        )

        result = self._invoke(project, ["lookup", "src/main.py"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]

        # Conventions from src/ should appear (within scope_root)
        assert "Src convention that SHOULD appear" in output
        # Conventions from project root should NOT appear (above scope_root)
        assert "Root convention that should NOT appear" not in output


# ---------------------------------------------------------------------------
# Describe command tests
# ---------------------------------------------------------------------------


class TestDescribeCommand:
    """Tests for the `lexi describe` command."""

    def test_describe_directory(self, tmp_path: Path) -> None:
        """Describe updates the .aindex billboard for a directory."""
        project = _setup_archivist_project(tmp_path)
        _create_aindex(project, "src", "Old description of src")

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            result = runner.invoke(
                lexi_app, ["describe", "src", "Authentication and authorization services"]
            )
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 0
        assert "Updated" in result.output

        # Verify the .aindex was actually updated
        aindex_content = (project / ".lexibrary" / "src" / ".aindex").read_text(encoding="utf-8")
        assert "Authentication and authorization services" in aindex_content

    def test_describe_missing_aindex(self, tmp_path: Path) -> None:
        """Describe with no .aindex suggests running index first."""
        project = _setup_archivist_project(tmp_path)

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            result = runner.invoke(lexi_app, ["describe", "src", "New description"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 1
        assert "No .aindex" in result.output
        assert "lexictl index" in result.output

    def test_describe_missing_directory(self, tmp_path: Path) -> None:
        """Describe with nonexistent directory should fail."""
        project = _setup_archivist_project(tmp_path)

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            result = runner.invoke(lexi_app, ["describe", "nonexistent", "Description"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 1
        assert "Directory not found" in result.output

    def test_describe_no_project(self, tmp_path: Path) -> None:
        """Describe without .lexibrary should fail."""
        (tmp_path / "src").mkdir()

        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = runner.invoke(lexi_app, ["describe", "src", "Description"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 1
        assert "No .lexibrary/" in result.output


# ---------------------------------------------------------------------------
# Concepts command tests
# ---------------------------------------------------------------------------


class TestConceptsCommand:
    """Tests for the `lexi concepts` command."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexi_app, args)
        finally:
            os.chdir(old_cwd)

    def test_concepts_empty(self, tmp_path: Path) -> None:
        """Show message when no concepts exist."""
        _setup_project(tmp_path)
        result = self._invoke(tmp_path, ["concepts"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "No concepts found" in result.output  # type: ignore[union-attr]

    def test_concepts_list_all(self, tmp_path: Path) -> None:
        """List all concepts in a Rich table."""
        _setup_project(tmp_path)
        _create_concept_file(tmp_path, "Authentication", tags=["security"])
        _create_concept_file(tmp_path, "Rate Limiting", tags=["performance"])

        result = self._invoke(tmp_path, ["concepts"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Authentication" in result.output  # type: ignore[union-attr]
        assert "Rate Limiting" in result.output  # type: ignore[union-attr]

    def test_concepts_search(self, tmp_path: Path) -> None:
        """Search concepts by topic."""
        _setup_project(tmp_path)
        _create_concept_file(tmp_path, "Authentication", tags=["security"])
        _create_concept_file(tmp_path, "Rate Limiting", tags=["performance"])

        result = self._invoke(tmp_path, ["concepts", "auth"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Authentication" in result.output  # type: ignore[union-attr]
        assert "Rate Limiting" not in result.output  # type: ignore[union-attr]

    def test_concepts_search_no_match(self, tmp_path: Path) -> None:
        """Search with no matches shows message."""
        _setup_project(tmp_path)
        _create_concept_file(tmp_path, "Authentication", tags=["security"])

        result = self._invoke(tmp_path, ["concepts", "zzzzz"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "No concepts matching" in result.output  # type: ignore[union-attr]

    def test_concepts_no_project(self, tmp_path: Path) -> None:
        """Concepts without .lexibrary should fail."""
        result = self._invoke(tmp_path, ["concepts"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "No .lexibrary/" in result.output  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Concepts --tag filtering tests (task 3.1)
# ---------------------------------------------------------------------------


class TestConceptsTagFilter:
    """Tests for `lexi concepts --tag` filtering."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexi_app, args)
        finally:
            os.chdir(old_cwd)

    def test_tag_filter_returns_correct_subset(self, tmp_path: Path) -> None:
        """--tag returns only concepts with that tag."""
        _setup_project(tmp_path)
        _create_concept_file(tmp_path, "Authentication", tags=["security", "core"])
        _create_concept_file(tmp_path, "Rate Limiting", tags=["performance"])
        _create_concept_file(tmp_path, "Encryption", tags=["security"])

        result = self._invoke(tmp_path, ["concepts", "--tag", "security"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Authentication" in output
        assert "Encryption" in output
        assert "Rate Limiting" not in output

    def test_multiple_tags_use_and_logic(self, tmp_path: Path) -> None:
        """Multiple --tag flags narrow results with AND logic."""
        _setup_project(tmp_path)
        _create_concept_file(tmp_path, "Authentication", tags=["security", "core"])
        _create_concept_file(tmp_path, "Encryption", tags=["security"])
        _create_concept_file(tmp_path, "Config", tags=["core"])

        result = self._invoke(
            tmp_path, ["concepts", "--tag", "security", "--tag", "core"]
        )
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        # Only Authentication has both tags
        assert "Authentication" in output
        assert "Encryption" not in output
        assert "Config" not in output

    def test_tag_filter_no_match(self, tmp_path: Path) -> None:
        """--tag with no matching concepts shows filter message."""
        _setup_project(tmp_path)
        _create_concept_file(tmp_path, "Authentication", tags=["security"])

        result = self._invoke(tmp_path, ["concepts", "--tag", "nonexistent"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "No concepts found matching" in result.output  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Concepts --status filtering tests (task 3.2)
# ---------------------------------------------------------------------------


class TestConceptsStatusFilter:
    """Tests for `lexi concepts --status` filtering."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexi_app, args)
        finally:
            os.chdir(old_cwd)

    def test_status_active_filter(self, tmp_path: Path) -> None:
        """--status active returns only active concepts."""
        _setup_project(tmp_path)
        _create_concept_file(tmp_path, "Active Concept", status="active")
        _create_concept_file(tmp_path, "Draft Concept", status="draft")
        _create_concept_file(tmp_path, "Old Concept", status="deprecated")

        result = self._invoke(tmp_path, ["concepts", "--status", "active"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Active Concept" in output
        assert "Draft Concept" not in output
        assert "Old Concept" not in output

    def test_status_draft_filter(self, tmp_path: Path) -> None:
        """--status draft returns only draft concepts."""
        _setup_project(tmp_path)
        _create_concept_file(tmp_path, "Active Concept", status="active")
        _create_concept_file(tmp_path, "Draft Concept", status="draft")

        result = self._invoke(tmp_path, ["concepts", "--status", "draft"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Draft Concept" in output
        assert "Active Concept" not in output

    def test_status_deprecated_overrides_default_exclusion(self, tmp_path: Path) -> None:
        """--status deprecated returns deprecated concepts despite default exclusion."""
        _setup_project(tmp_path)
        _create_concept_file(tmp_path, "Active Concept", status="active")
        _create_concept_file(tmp_path, "Old Concept", status="deprecated")

        result = self._invoke(tmp_path, ["concepts", "--status", "deprecated"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Old Concept" in output
        assert "Active Concept" not in output

    def test_invalid_status_value(self, tmp_path: Path) -> None:
        """--status with invalid value shows error."""
        _setup_project(tmp_path)
        _create_concept_file(tmp_path, "Something", status="active")

        result = self._invoke(tmp_path, ["concepts", "--status", "invalid"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "Invalid status" in result.output  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Concepts --all flag tests (task 3.3)
# ---------------------------------------------------------------------------


class TestConceptsAllFlag:
    """Tests for `lexi concepts --all` flag."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexi_app, args)
        finally:
            os.chdir(old_cwd)

    def test_all_flag_includes_deprecated(self, tmp_path: Path) -> None:
        """--all includes deprecated concepts in results."""
        _setup_project(tmp_path)
        _create_concept_file(tmp_path, "Active Concept", status="active")
        _create_concept_file(tmp_path, "Old Concept", status="deprecated")
        _create_concept_file(tmp_path, "Draft Concept", status="draft")

        result = self._invoke(tmp_path, ["concepts", "--all"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Active Concept" in output
        assert "Old Concept" in output
        assert "Draft Concept" in output


# ---------------------------------------------------------------------------
# Concepts default deprecated exclusion tests (task 3.4)
# ---------------------------------------------------------------------------


class TestConceptsDefaultDeprecatedExclusion:
    """Tests for default deprecated concept exclusion."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexi_app, args)
        finally:
            os.chdir(old_cwd)

    def test_bare_concepts_hides_deprecated(self, tmp_path: Path) -> None:
        """Bare `lexi concepts` hides deprecated concepts by default."""
        _setup_project(tmp_path)
        _create_concept_file(tmp_path, "Active Concept", status="active")
        _create_concept_file(tmp_path, "Draft Concept", status="draft")
        _create_concept_file(tmp_path, "Old Concept", status="deprecated")

        result = self._invoke(tmp_path, ["concepts"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Active Concept" in output
        assert "Draft Concept" in output
        assert "Old Concept" not in output

    def test_topic_search_hides_deprecated(self, tmp_path: Path) -> None:
        """Topic search also hides deprecated concepts by default."""
        _setup_project(tmp_path)
        _create_concept_file(
            tmp_path, "Auth Active", tags=["auth"], status="active"
        )
        _create_concept_file(
            tmp_path, "Auth Old", tags=["auth"], status="deprecated"
        )

        result = self._invoke(tmp_path, ["concepts", "auth"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Auth Active" in output
        assert "Auth Old" not in output


# ---------------------------------------------------------------------------
# Concepts combined filter tests (task 3.5)
# ---------------------------------------------------------------------------


class TestConceptsCombinedFilters:
    """Tests for combining topic + --tag + --status filters with AND logic."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexi_app, args)
        finally:
            os.chdir(old_cwd)

    def test_topic_plus_tag(self, tmp_path: Path) -> None:
        """topic + --tag narrows with AND logic."""
        _setup_project(tmp_path)
        _create_concept_file(
            tmp_path, "Auth Core", tags=["security", "core"], summary="authentication"
        )
        _create_concept_file(
            tmp_path, "Auth Perf", tags=["performance"], summary="authentication perf"
        )
        _create_concept_file(
            tmp_path, "Encryption", tags=["security"], summary="crypto"
        )

        result = self._invoke(tmp_path, ["concepts", "auth", "--tag", "security"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        # Only "Auth Core" matches both topic "auth" and tag "security"
        assert "Auth Core" in output
        assert "Auth Perf" not in output
        assert "Encryption" not in output

    def test_topic_plus_status(self, tmp_path: Path) -> None:
        """topic + --status narrows with AND logic."""
        _setup_project(tmp_path)
        _create_concept_file(
            tmp_path, "Auth Active", tags=["auth"], status="active", summary="authentication"
        )
        _create_concept_file(
            tmp_path, "Auth Draft", tags=["auth"], status="draft", summary="authentication draft"
        )

        result = self._invoke(
            tmp_path, ["concepts", "auth", "--status", "draft"]
        )
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Auth Draft" in output
        assert "Auth Active" not in output

    def test_topic_plus_tag_plus_status(self, tmp_path: Path) -> None:
        """topic + --tag + --status all narrow with AND logic."""
        _setup_project(tmp_path)
        _create_concept_file(
            tmp_path,
            "Auth Core Active",
            tags=["security", "core"],
            status="active",
            summary="authentication",
        )
        _create_concept_file(
            tmp_path,
            "Auth Core Draft",
            tags=["security", "core"],
            status="draft",
            summary="authentication",
        )
        _create_concept_file(
            tmp_path,
            "Auth Perf Active",
            tags=["performance"],
            status="active",
            summary="authentication",
        )

        result = self._invoke(
            tmp_path,
            ["concepts", "auth", "--tag", "security", "--status", "active"],
        )
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        # Only "Auth Core Active" matches all three filters
        assert "Auth Core Active" in output
        assert "Auth Core Draft" not in output
        assert "Auth Perf Active" not in output

    def test_all_filters_no_match(self, tmp_path: Path) -> None:
        """Combined filters that match nothing show appropriate message."""
        _setup_project(tmp_path)
        _create_concept_file(
            tmp_path, "Authentication", tags=["security"], status="active"
        )

        result = self._invoke(
            tmp_path,
            ["concepts", "auth", "--tag", "nonexistent", "--status", "draft"],
        )
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "No concepts found matching" in result.output  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Agent help command tests (task 3.6)
# ---------------------------------------------------------------------------


class TestAgentHelpCommand:
    """Tests for `lexi help` command."""

    def test_help_succeeds_without_project_root(self, tmp_path: Path) -> None:
        """lexi help works anywhere -- no .lexibrary/ directory required."""
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = runner.invoke(lexi_app, ["help"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 0
        assert len(result.output) > 0

    def test_help_shows_command_groups(self) -> None:
        """lexi help displays all command group sections including Inspection & Annotation."""
        result = runner.invoke(lexi_app, ["help"])
        assert result.exit_code == 0
        output = result.output
        assert "Available Commands" in output
        assert "Lookup" in output or "lookup" in output
        assert "Concepts" in output or "concepts" in output
        assert "Stack" in output or "stack" in output
        # The old "Indexing & Maintenance" section was replaced with "Inspection & Annotation"
        assert "Inspection" in output or "Annotation" in output

    def test_help_does_not_reference_lexi_index(self) -> None:
        """lexi help should not reference the removed 'lexi index' command."""
        result = runner.invoke(lexi_app, ["help"])
        assert result.exit_code == 0
        output = result.output
        # "lexi index" should NOT appear as a command reference
        assert "lexi index" not in output

    def test_help_shows_inspection_section(self) -> None:
        """lexi help includes 'Inspection & Annotation' with status, validate, describe."""
        result = runner.invoke(lexi_app, ["help"])
        assert result.exit_code == 0
        output = result.output
        assert "Inspection" in output
        assert "lexi status" in output
        assert "lexi validate" in output
        assert "lexi describe" in output

    def test_help_shows_workflows(self) -> None:
        """lexi help displays common workflows section."""
        result = runner.invoke(lexi_app, ["help"])
        assert result.exit_code == 0
        output = result.output
        assert "Common Workflows" in output
        # At least 4 workflows
        assert "Understand a source file" in output
        assert "Explore a topic" in output
        assert "Ask a question" in output
        # New workflow: "Check library health" replacing "Index a new directory"
        assert "Check library health" in output

    def test_help_check_library_health_workflow(self) -> None:
        """lexi help contains the 'Check library health' workflow with status and validate."""
        result = runner.invoke(lexi_app, ["help"])
        assert result.exit_code == 0
        output = result.output
        assert "Check library health" in output
        assert "lexi status" in output
        assert "lexi validate" in output

    def test_help_shows_navigation_tips(self) -> None:
        """lexi help displays navigation tips section."""
        result = runner.invoke(lexi_app, ["help"])
        assert result.exit_code == 0
        output = result.output
        assert "Navigation Tips" in output
        assert "Wikilinks" in output or "wikilink" in output

    def test_help_references_all_agent_commands(self) -> None:
        """lexi help references all current agent-facing commands (no lexi index)."""
        result = runner.invoke(lexi_app, ["help"])
        assert result.exit_code == 0
        output = result.output
        for cmd in (
            "lookup",
            "describe",
            "concepts",
            "concept new",
            "concept link",
            "stack post",
            "stack search",
            "stack view",
            "stack answer",
            "stack vote",
            "stack accept",
            "stack list",
            "search",
            "help",
            "status",
            "validate",
        ):
            assert cmd in output, f"Expected command '{cmd}' to be referenced in help output"


# ---------------------------------------------------------------------------
# Concept new command tests
# ---------------------------------------------------------------------------


class TestConceptNewCommand:
    """Tests for the `lexi concept new` command."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexi_app, args)
        finally:
            os.chdir(old_cwd)

    def test_create_concept(self, tmp_path: Path) -> None:
        """Create a new concept file."""
        _setup_project(tmp_path)
        (tmp_path / ".lexibrary" / "concepts").mkdir(parents=True, exist_ok=True)

        result = self._invoke(tmp_path, ["concept", "new", "Rate Limiting"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Created" in result.output  # type: ignore[union-attr]
        assert (tmp_path / ".lexibrary" / "concepts" / "RateLimiting.md").exists()

    def test_create_concept_with_tags(self, tmp_path: Path) -> None:
        """Create a concept with tags."""
        _setup_project(tmp_path)
        (tmp_path / ".lexibrary" / "concepts").mkdir(parents=True, exist_ok=True)

        result = self._invoke(
            tmp_path, ["concept", "new", "Auth", "--tag", "security", "--tag", "core"]
        )
        assert result.exit_code == 0  # type: ignore[union-attr]

        content = (tmp_path / ".lexibrary" / "concepts" / "Auth.md").read_text()
        assert "security" in content
        assert "core" in content

    def test_create_concept_already_exists(self, tmp_path: Path) -> None:
        """Refuse to overwrite existing concept file."""
        _setup_project(tmp_path)
        _create_concept_file(tmp_path, "Authentication")

        result = self._invoke(tmp_path, ["concept", "new", "Authentication"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "already exists" in result.output  # type: ignore[union-attr]

    def test_create_concept_no_project(self, tmp_path: Path) -> None:
        """Concept new without .lexibrary should fail."""
        result = self._invoke(tmp_path, ["concept", "new", "Test"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "No .lexibrary/" in result.output  # type: ignore[union-attr]

    def test_create_concept_pascalcase(self, tmp_path: Path) -> None:
        """Concept name with spaces gets PascalCase filename."""
        _setup_project(tmp_path)
        (tmp_path / ".lexibrary" / "concepts").mkdir(parents=True, exist_ok=True)

        result = self._invoke(tmp_path, ["concept", "new", "my cool concept"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert (tmp_path / ".lexibrary" / "concepts" / "MyCoolConcept.md").exists()


# ---------------------------------------------------------------------------
# Concept link command tests
# ---------------------------------------------------------------------------


class TestConceptLinkCommand:
    """Tests for the `lexi concept link` command."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexi_app, args)
        finally:
            os.chdir(old_cwd)

    def test_link_concept(self, tmp_path: Path) -> None:
        """Link a concept to a source file's design file."""
        project = _setup_archivist_project(tmp_path)
        _create_concept_file(project, "Authentication")
        source_content = "def hello():\n    pass\n"
        _create_design_file(project, "src/main.py", source_content)

        result = self._invoke(project, ["concept", "link", "Authentication", "src/main.py"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Linked" in result.output  # type: ignore[union-attr]

        # Verify wikilink was added to design file
        design_content = (project / ".lexibrary" / "src" / "main.py.md").read_text(encoding="utf-8")
        assert "[[Authentication]]" in design_content

    def test_link_concept_already_linked(self, tmp_path: Path) -> None:
        """Linking an already-linked concept shows message."""
        project = _setup_archivist_project(tmp_path)
        _create_concept_file(project, "Authentication")
        source_content = "def hello():\n    pass\n"
        _create_design_file(project, "src/main.py", source_content)

        # Link once
        self._invoke(project, ["concept", "link", "Authentication", "src/main.py"])
        # Link again
        result = self._invoke(project, ["concept", "link", "Authentication", "src/main.py"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Already linked" in result.output  # type: ignore[union-attr]

    def test_link_concept_not_found(self, tmp_path: Path) -> None:
        """Linking a nonexistent concept should fail."""
        project = _setup_archivist_project(tmp_path)
        source_content = "def hello():\n    pass\n"
        _create_design_file(project, "src/main.py", source_content)

        result = self._invoke(project, ["concept", "link", "Nonexistent", "src/main.py"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "Concept not found" in result.output  # type: ignore[union-attr]

    def test_link_source_not_found(self, tmp_path: Path) -> None:
        """Linking to a nonexistent source file should fail."""
        project = _setup_archivist_project(tmp_path)
        _create_concept_file(project, "Authentication")

        result = self._invoke(project, ["concept", "link", "Authentication", "src/missing.py"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "Source file not found" in result.output  # type: ignore[union-attr]

    def test_link_no_design_file(self, tmp_path: Path) -> None:
        """Linking when no design file exists should suggest running lexictl update."""
        project = _setup_archivist_project(tmp_path)
        _create_concept_file(project, "Authentication")

        result = self._invoke(project, ["concept", "link", "Authentication", "src/main.py"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "No design file found" in result.output  # type: ignore[union-attr]
        assert "lexictl update" in result.output  # type: ignore[union-attr]

    def test_link_no_project(self, tmp_path: Path) -> None:
        """Concept link without .lexibrary should fail."""
        result = self._invoke(tmp_path, ["concept", "link", "Test", "file.py"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "No .lexibrary/" in result.output  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Stack post command tests
# ---------------------------------------------------------------------------


class TestStackPostCommand:
    """Tests for the `lexi stack post` command."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexi_app, args)
        finally:
            os.chdir(old_cwd)

    def test_create_post(self, tmp_path: Path) -> None:
        """Create a new stack post with required flags."""
        _setup_stack_project(tmp_path)
        result = self._invoke(
            tmp_path,
            ["stack", "post", "--title", "Bug in auth", "--tag", "auth"],
        )
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Created" in result.output  # type: ignore[union-attr]
        # File should exist
        stack_dir = tmp_path / ".lexibrary" / "stack"
        files = list(stack_dir.glob("ST-001-*.md"))
        assert len(files) == 1
        content = files[0].read_text(encoding="utf-8")
        assert "Bug in auth" in content
        assert "auth" in content

    def test_create_post_with_all_flags(self, tmp_path: Path) -> None:
        """Create a post with bead, file, and concept refs."""
        _setup_stack_project(tmp_path)
        result = self._invoke(
            tmp_path,
            [
                "stack",
                "post",
                "--title",
                "Auth bug",
                "--tag",
                "auth",
                "--tag",
                "security",
                "--bead",
                "BEAD-1",
                "--file",
                "src/auth.py",
                "--concept",
                "Authentication",
            ],
        )
        assert result.exit_code == 0  # type: ignore[union-attr]
        stack_dir = tmp_path / ".lexibrary" / "stack"
        files = list(stack_dir.glob("ST-001-*.md"))
        assert len(files) == 1
        content = files[0].read_text(encoding="utf-8")
        assert "BEAD-1" in content
        assert "src/auth.py" in content
        assert "Authentication" in content

    def test_create_post_auto_increments_id(self, tmp_path: Path) -> None:
        """Second post gets ST-002."""
        _setup_stack_project(tmp_path)
        _create_stack_post(tmp_path, post_id="ST-001", title="First post")
        result = self._invoke(
            tmp_path,
            ["stack", "post", "--title", "Second post", "--tag", "test"],
        )
        assert result.exit_code == 0  # type: ignore[union-attr]
        stack_dir = tmp_path / ".lexibrary" / "stack"
        files = list(stack_dir.glob("ST-002-*.md"))
        assert len(files) == 1

    def test_create_post_no_project(self, tmp_path: Path) -> None:
        """Post without .lexibrary should fail."""
        result = self._invoke(tmp_path, ["stack", "post", "--title", "Bug", "--tag", "auth"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "No .lexibrary/" in result.output  # type: ignore[union-attr]

    def test_create_post_prints_guidance(self, tmp_path: Path) -> None:
        """Post command prints guidance about filling in sections."""
        _setup_stack_project(tmp_path)
        result = self._invoke(tmp_path, ["stack", "post", "--title", "Bug", "--tag", "auth"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Problem" in result.output  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Stack search command tests
# ---------------------------------------------------------------------------


class TestStackSearchCommand:
    """Tests for the `lexi stack search` command."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexi_app, args)
        finally:
            os.chdir(old_cwd)

    def test_search_by_query(self, tmp_path: Path) -> None:
        """Search posts by query string."""
        _setup_stack_project(tmp_path)
        _create_stack_post(tmp_path, post_id="ST-001", title="Timezone bug", tags=["datetime"])
        _create_stack_post(tmp_path, post_id="ST-002", title="Auth issue", tags=["auth"])
        result = self._invoke(tmp_path, ["stack", "search", "timezone"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Timezone bug" in result.output  # type: ignore[union-attr]
        assert "Auth issue" not in result.output  # type: ignore[union-attr]

    def test_search_with_tag_filter(self, tmp_path: Path) -> None:
        """Search with tag filter."""
        _setup_stack_project(tmp_path)
        _create_stack_post(tmp_path, post_id="ST-001", title="Bug one", tags=["auth"])
        _create_stack_post(tmp_path, post_id="ST-002", title="Bug two", tags=["performance"])
        result = self._invoke(tmp_path, ["stack", "search", "Bug", "--tag", "auth"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Bug one" in result.output  # type: ignore[union-attr]
        assert "Bug two" not in result.output  # type: ignore[union-attr]

    def test_search_no_results(self, tmp_path: Path) -> None:
        """Search with no matching posts."""
        _setup_stack_project(tmp_path)
        result = self._invoke(tmp_path, ["stack", "search", "nonexistent"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "No posts found" in result.output  # type: ignore[union-attr]

    def test_search_with_status_filter(self, tmp_path: Path) -> None:
        """Search filtered by status."""
        _setup_stack_project(tmp_path)
        _create_stack_post(tmp_path, post_id="ST-001", title="Open bug", status="open")
        _create_stack_post(tmp_path, post_id="ST-002", title="Resolved bug", status="resolved")
        result = self._invoke(tmp_path, ["stack", "search", "--status", "open"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Open bug" in result.output  # type: ignore[union-attr]
        assert "Resolved bug" not in result.output  # type: ignore[union-attr]

    def test_search_with_scope_filter(self, tmp_path: Path) -> None:
        """Search filtered by scope path."""
        _setup_stack_project(tmp_path)
        _create_stack_post(
            tmp_path,
            post_id="ST-001",
            title="Model bug",
            refs_files=["src/models/user.py"],
        )
        _create_stack_post(
            tmp_path,
            post_id="ST-002",
            title="View bug",
            refs_files=["src/views/home.py"],
        )
        result = self._invoke(tmp_path, ["stack", "search", "--scope", "src/models/"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Model bug" in result.output  # type: ignore[union-attr]
        assert "View bug" not in result.output  # type: ignore[union-attr]

    def test_search_no_project(self, tmp_path: Path) -> None:
        """Search without .lexibrary should fail."""
        result = self._invoke(tmp_path, ["stack", "search", "test"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "No .lexibrary/" in result.output  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Stack answer command tests
# ---------------------------------------------------------------------------


class TestStackAnswerCommand:
    """Tests for the `lexi stack answer` command."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexi_app, args)
        finally:
            os.chdir(old_cwd)

    def test_add_answer(self, tmp_path: Path) -> None:
        """Add an answer to an existing post."""
        _setup_stack_project(tmp_path)
        _create_stack_post(tmp_path, post_id="ST-001", title="Bug")
        result = self._invoke(tmp_path, ["stack", "answer", "ST-001", "--body", "Try restarting."])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Added answer A1" in result.output  # type: ignore[union-attr]

    def test_add_answer_nonexistent_post(self, tmp_path: Path) -> None:
        """Answer to nonexistent post should fail."""
        _setup_stack_project(tmp_path)
        result = self._invoke(tmp_path, ["stack", "answer", "ST-999", "--body", "Solution"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "Post not found" in result.output  # type: ignore[union-attr]

    def test_add_answer_no_project(self, tmp_path: Path) -> None:
        """Answer without .lexibrary should fail."""
        result = self._invoke(tmp_path, ["stack", "answer", "ST-001", "--body", "Solution"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "No .lexibrary/" in result.output  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Stack vote command tests
# ---------------------------------------------------------------------------


class TestStackVoteCommand:
    """Tests for the `lexi stack vote` command."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexi_app, args)
        finally:
            os.chdir(old_cwd)

    def test_upvote_post(self, tmp_path: Path) -> None:
        """Upvote a post."""
        _setup_stack_project(tmp_path)
        _create_stack_post(tmp_path, post_id="ST-001", title="Bug")
        result = self._invoke(tmp_path, ["stack", "vote", "ST-001", "up"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "upvote" in result.output  # type: ignore[union-attr]
        assert "votes: 1" in result.output  # type: ignore[union-attr]

    def test_downvote_with_comment(self, tmp_path: Path) -> None:
        """Downvote an answer with required comment."""
        _setup_stack_project(tmp_path)
        _create_stack_post_with_answer(tmp_path, post_id="ST-001")
        result = self._invoke(
            tmp_path,
            ["stack", "vote", "ST-001", "down", "--answer", "1", "--comment", "Bad approach"],
        )
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "downvote" in result.output  # type: ignore[union-attr]

    def test_downvote_without_comment_fails(self, tmp_path: Path) -> None:
        """Downvote without comment should fail."""
        _setup_stack_project(tmp_path)
        _create_stack_post(tmp_path, post_id="ST-001", title="Bug")
        result = self._invoke(tmp_path, ["stack", "vote", "ST-001", "down"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "comment" in result.output.lower()  # type: ignore[union-attr]

    def test_vote_nonexistent_post(self, tmp_path: Path) -> None:
        """Vote on nonexistent post should fail."""
        _setup_stack_project(tmp_path)
        result = self._invoke(tmp_path, ["stack", "vote", "ST-999", "up"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "Post not found" in result.output  # type: ignore[union-attr]

    def test_invalid_direction(self, tmp_path: Path) -> None:
        """Invalid vote direction should fail."""
        _setup_stack_project(tmp_path)
        _create_stack_post(tmp_path, post_id="ST-001", title="Bug")
        result = self._invoke(tmp_path, ["stack", "vote", "ST-001", "sideways"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "up" in result.output or "down" in result.output  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Stack accept command tests
# ---------------------------------------------------------------------------


class TestStackAcceptCommand:
    """Tests for the `lexi stack accept` command."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexi_app, args)
        finally:
            os.chdir(old_cwd)

    def test_accept_answer(self, tmp_path: Path) -> None:
        """Accept an answer and set status to resolved."""
        _setup_stack_project(tmp_path)
        _create_stack_post_with_answer(tmp_path, post_id="ST-001")
        result = self._invoke(tmp_path, ["stack", "accept", "ST-001", "--answer", "1"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Accepted A1" in result.output  # type: ignore[union-attr]
        assert "resolved" in result.output  # type: ignore[union-attr]

    def test_accept_nonexistent_post(self, tmp_path: Path) -> None:
        """Accept on nonexistent post should fail."""
        _setup_stack_project(tmp_path)
        result = self._invoke(tmp_path, ["stack", "accept", "ST-999", "--answer", "1"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "Post not found" in result.output  # type: ignore[union-attr]

    def test_accept_nonexistent_answer(self, tmp_path: Path) -> None:
        """Accept nonexistent answer should fail."""
        _setup_stack_project(tmp_path)
        _create_stack_post_with_answer(tmp_path, post_id="ST-001")
        result = self._invoke(tmp_path, ["stack", "accept", "ST-001", "--answer", "99"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "Error" in result.output  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Stack view command tests
# ---------------------------------------------------------------------------


class TestStackViewCommand:
    """Tests for the `lexi stack view` command."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexi_app, args)
        finally:
            os.chdir(old_cwd)

    def test_view_post(self, tmp_path: Path) -> None:
        """View a post displays formatted output."""
        _setup_stack_project(tmp_path)
        _create_stack_post(
            tmp_path,
            post_id="ST-001",
            title="Timezone bug",
            tags=["datetime"],
            problem="Dates are wrong in UTC",
        )
        result = self._invoke(tmp_path, ["stack", "view", "ST-001"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Timezone bug" in result.output  # type: ignore[union-attr]
        assert "Problem" in result.output  # type: ignore[union-attr]
        assert "Dates are wrong" in result.output  # type: ignore[union-attr]

    def test_view_post_with_answer(self, tmp_path: Path) -> None:
        """View a post with answers shows answer details."""
        _setup_stack_project(tmp_path)
        _create_stack_post_with_answer(
            tmp_path, post_id="ST-001", title="Bug", answer_body="Fix it!"
        )
        result = self._invoke(tmp_path, ["stack", "view", "ST-001"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "A1" in result.output  # type: ignore[union-attr]
        assert "Fix it" in result.output  # type: ignore[union-attr]

    def test_view_nonexistent_post(self, tmp_path: Path) -> None:
        """View nonexistent post should fail."""
        _setup_stack_project(tmp_path)
        result = self._invoke(tmp_path, ["stack", "view", "ST-999"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "Post not found" in result.output  # type: ignore[union-attr]

    def test_view_no_project(self, tmp_path: Path) -> None:
        """View without .lexibrary should fail."""
        result = self._invoke(tmp_path, ["stack", "view", "ST-001"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "No .lexibrary/" in result.output  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Stack list command tests
# ---------------------------------------------------------------------------


class TestStackListCommand:
    """Tests for the `lexi stack list` command."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexi_app, args)
        finally:
            os.chdir(old_cwd)

    def test_list_all(self, tmp_path: Path) -> None:
        """List all stack posts."""
        _setup_stack_project(tmp_path)
        _create_stack_post(tmp_path, post_id="ST-001", title="Bug one")
        _create_stack_post(tmp_path, post_id="ST-002", title="Bug two")
        result = self._invoke(tmp_path, ["stack", "list"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Bug one" in result.output  # type: ignore[union-attr]
        assert "Bug two" in result.output  # type: ignore[union-attr]

    def test_list_filtered_by_status(self, tmp_path: Path) -> None:
        """List posts filtered by status."""
        _setup_stack_project(tmp_path)
        _create_stack_post(tmp_path, post_id="ST-001", title="Open bug", status="open")
        _create_stack_post(tmp_path, post_id="ST-002", title="Resolved bug", status="resolved")
        result = self._invoke(tmp_path, ["stack", "list", "--status", "open"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Open bug" in result.output  # type: ignore[union-attr]
        assert "Resolved bug" not in result.output  # type: ignore[union-attr]

    def test_list_filtered_by_tag(self, tmp_path: Path) -> None:
        """List posts filtered by tag."""
        _setup_stack_project(tmp_path)
        _create_stack_post(tmp_path, post_id="ST-001", title="Auth issue", tags=["auth"])
        _create_stack_post(tmp_path, post_id="ST-002", title="Perf issue", tags=["performance"])
        result = self._invoke(tmp_path, ["stack", "list", "--tag", "auth"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Auth issue" in result.output  # type: ignore[union-attr]
        assert "Perf issue" not in result.output  # type: ignore[union-attr]

    def test_list_empty(self, tmp_path: Path) -> None:
        """List when no posts exist."""
        _setup_stack_project(tmp_path)
        result = self._invoke(tmp_path, ["stack", "list"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "No posts found" in result.output  # type: ignore[union-attr]

    def test_list_no_project(self, tmp_path: Path) -> None:
        """List without .lexibrary should fail."""
        result = self._invoke(tmp_path, ["stack", "list"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "No .lexibrary/" in result.output  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Unified search command tests
# ---------------------------------------------------------------------------


class TestUnifiedSearchCommand:
    """Tests for the `lexi search` command."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexi_app, args)
        finally:
            os.chdir(old_cwd)

    def test_search_no_args_requires_input(self, tmp_path: Path) -> None:
        """Search with no query, tag, or scope should exit 1."""
        _setup_stack_project(tmp_path)
        result = self._invoke(tmp_path, ["search"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "Provide a query" in result.output  # type: ignore[union-attr]

    def test_search_free_text_across_all_types(self, tmp_path: Path) -> None:
        """Free-text search matches across concepts, design files, and Stack posts."""
        project = _setup_unified_search_project(tmp_path)
        result = self._invoke(project, ["search", "auth"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        # Should find concept
        assert "Authentication" in output
        # Should find design file
        assert "src/auth.py" in output
        # Should find stack post
        assert "Login timeout bug" in output

    def test_search_by_tag_across_types(self, tmp_path: Path) -> None:
        """Tag search filters across all artifact types."""
        project = _setup_unified_search_project(tmp_path)
        result = self._invoke(project, ["search", "--tag", "security"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        # Concept "Authentication" has tag "security"
        assert "Authentication" in output
        # Design file "src/auth.py" has tag "security"
        assert "src/auth.py" in output
        # Stack posts do not have "security" tag -- should not appear
        assert "Login timeout" not in output
        assert "Rate limiter" not in output

    def test_search_by_tag_auth_includes_stack(self, tmp_path: Path) -> None:
        """Tag search for 'auth' includes stack post with auth tag."""
        project = _setup_unified_search_project(tmp_path)
        result = self._invoke(project, ["search", "--tag", "auth"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Authentication" in output
        assert "src/auth.py" in output
        assert "Login timeout bug" in output

    def test_search_by_scope(self, tmp_path: Path) -> None:
        """Scope search filters design files and stack posts by file path."""
        project = _setup_unified_search_project(tmp_path)
        result = self._invoke(project, ["search", "--scope", "src/auth"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        # Design file for auth.py should match
        assert "src/auth.py" in output
        # Stack post referencing src/auth.py should match
        assert "Login timeout bug" in output
        # models.py should not match
        assert "src/models.py" not in output

    def test_search_no_results(self, tmp_path: Path) -> None:
        """Search with no matching results shows appropriate message."""
        project = _setup_unified_search_project(tmp_path)
        result = self._invoke(project, ["search", "zzz-nonexistent-zzz"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "No results found" in result.output  # type: ignore[union-attr]

    def test_search_omits_empty_groups(self, tmp_path: Path) -> None:
        """Groups with no matches are omitted from output."""
        project = _setup_unified_search_project(tmp_path)
        # "performance" tag only on concept "Rate Limiting" and stack "ST-002"
        result = self._invoke(project, ["search", "--tag", "performance"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Rate Limiting" in output
        assert "Rate limiter memory leak" in output
        # No design files have "performance" tag, so "Design Files" should not appear
        assert "Design Files" not in output

    def test_search_free_text_design_file_description(self, tmp_path: Path) -> None:
        """Free-text matches against design file frontmatter description."""
        project = _setup_unified_search_project(tmp_path)
        result = self._invoke(project, ["search", "Data models for users"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "src/models.py" in result.output  # type: ignore[union-attr]

    def test_search_no_project(self, tmp_path: Path) -> None:
        """Search without .lexibrary should fail."""
        result = self._invoke(tmp_path, ["search", "test"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "No .lexibrary/" in result.output  # type: ignore[union-attr]

    def test_search_concepts_only_when_no_scope(self, tmp_path: Path) -> None:
        """Concepts are excluded from scope-filtered searches (they are not file-scoped)."""
        project = _setup_unified_search_project(tmp_path)
        result = self._invoke(project, ["search", "--scope", "src/"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        # Concepts should not appear (scope filter excludes them)
        assert "Concepts" not in output
        # Design files and stack posts should appear
        assert "src/auth.py" in output or "src/models.py" in output


# ---------------------------------------------------------------------------
# Commands without .lexibrary/ should exit 1 with friendly error (lexi)
# ---------------------------------------------------------------------------


class TestNoProjectRoot:
    def _invoke_without_project(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexi_app, args)
        finally:
            os.chdir(old_cwd)

    def test_search_no_project_root(self, tmp_path: Path) -> None:
        result = self._invoke_without_project(tmp_path, ["search", "test"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "No .lexibrary/" in result.output  # type: ignore[union-attr]

    def test_concepts_no_project_root(self, tmp_path: Path) -> None:
        result = self._invoke_without_project(tmp_path, ["concepts"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "No .lexibrary/" in result.output  # type: ignore[union-attr]

    def test_validate_no_project_root(self, tmp_path: Path) -> None:
        result = self._invoke_without_project(tmp_path, ["validate"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "No .lexibrary/" in result.output  # type: ignore[union-attr]

    def test_status_no_project_root(self, tmp_path: Path) -> None:
        result = self._invoke_without_project(tmp_path, ["status"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "No .lexibrary/" in result.output  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Lexi validate command tests (task 7.1)
# ---------------------------------------------------------------------------


def _setup_validate_project(tmp_path: Path) -> Path:
    """Create a project with known validation state for testing."""
    (tmp_path / ".lexibrary").mkdir()
    (tmp_path / ".lexibrary" / "config.yaml").write_text("")
    (tmp_path / ".lexibrary" / "concepts").mkdir(parents=True)
    (tmp_path / "src").mkdir()
    source_content = "def hello():\n    pass\n"
    (tmp_path / "src" / "main.py").write_text(source_content)

    # Create a design file with correct hash
    source_hash = hashlib.sha256(source_content.encode()).hexdigest()
    design_dir = tmp_path / ".lexibrary" / "src"
    design_dir.mkdir(parents=True, exist_ok=True)
    design_content = f"""---
description: Main module
updated_by: archivist
---

# src/main.py

Main module.

## Interface Contract

```python
def hello(): ...
```

## Dependencies

- (none)

## Dependents

- (none)

<!-- lexibrary:meta
source: src/main.py
source_hash: {source_hash}
design_hash: placeholder
generated: 2026-01-01T00:00:00
generator: lexibrary-v2
-->
"""
    (design_dir / "main.py.md").write_text(design_content, encoding="utf-8")
    return tmp_path


def _setup_validate_project_with_errors(tmp_path: Path) -> Path:
    """Create a project with validation errors (broken concept frontmatter)."""
    project = _setup_validate_project(tmp_path)
    concepts_dir = project / ".lexibrary" / "concepts"
    concepts_dir.mkdir(parents=True, exist_ok=True)
    (concepts_dir / "BrokenConcept.md").write_text(
        "---\ntitle: Broken\n---\n\nMissing aliases, tags, status.\n",
        encoding="utf-8",
    )
    return project


def _setup_validate_project_with_warnings(tmp_path: Path) -> Path:
    """Create a project with stale hash (warning) but no errors."""
    (tmp_path / ".lexibrary").mkdir()
    (tmp_path / ".lexibrary" / "config.yaml").write_text("")
    (tmp_path / ".lexibrary" / "concepts").mkdir(parents=True)
    (tmp_path / "src").mkdir()
    source_content = "def hello():\n    return 42\n"
    (tmp_path / "src" / "main.py").write_text(source_content)

    design_dir = tmp_path / ".lexibrary" / "src"
    design_dir.mkdir(parents=True, exist_ok=True)
    design_content = """---
description: Main module
updated_by: archivist
---

# src/main.py

Main module.

## Interface Contract

```python
def hello(): ...
```

## Dependencies

- (none)

## Dependents

- (none)

<!-- lexibrary:meta
source: src/main.py
source_hash: 0000000000000000000000000000000000000000000000000000000000000000
design_hash: placeholder
generated: 2026-01-01T00:00:00
generator: lexibrary-v2
-->
"""
    (design_dir / "main.py.md").write_text(design_content, encoding="utf-8")
    return tmp_path


class TestLexiValidateCommand:
    """Tests for the `lexi validate` command (task 7.1)."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexi_app, args)
        finally:
            os.chdir(old_cwd)

    def test_validate_execution_clean(self, tmp_path: Path) -> None:
        """A clean library with no issues exits with code 0."""
        project = _setup_validate_project(tmp_path)
        # Create .aindex files to avoid aindex_coverage info issues
        from datetime import datetime as _dt

        now = _dt.now().isoformat()
        src_aindex = (
            f"# src/\n\nSource\n\n## Child Map\n\n"
            f"| Name | Type | Description |\n| --- | --- | --- |\n"
            f"| `main.py` | file | Main |\n\n## Local Conventions\n\n(none)\n\n"
            f'<!-- lexibrary:meta source="src" source_hash="abc"'
            f' generated="{now}" -->\n'
        )
        (project / ".lexibrary" / "src" / ".aindex").write_text(
            src_aindex, encoding="utf-8"
        )
        root_aindex = (
            f"# ./\n\nRoot\n\n## Child Map\n\n"
            f"| Name | Type | Description |\n| --- | --- | --- |\n"
            f"| `src/` | dir | Source |\n\n## Local Conventions\n\n(none)\n\n"
            f'<!-- lexibrary:meta source="." source_hash="abc"'
            f' generated="{now}" -->\n'
        )
        (project / ".lexibrary" / ".aindex").write_text(
            root_aindex, encoding="utf-8"
        )
        result = self._invoke(project, ["validate"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "No validation issues found" in result.output  # type: ignore[union-attr]

    def test_validate_severity_filter(self, tmp_path: Path) -> None:
        """The --severity flag filters checks by severity level."""
        import json as _json

        project = _setup_validate_project_with_warnings(tmp_path)
        result = self._invoke(project, ["validate", "--severity", "error", "--json"])
        output = result.output  # type: ignore[union-attr]
        parsed = _json.loads(output)
        # Only error-level checks should run; no warnings or info
        assert parsed["summary"]["warning_count"] == 0
        assert parsed["summary"]["info_count"] == 0

    def test_validate_check_filter(self, tmp_path: Path) -> None:
        """The --check flag runs only the specified check."""
        import json as _json

        project = _setup_validate_project(tmp_path)
        result = self._invoke(project, ["validate", "--check", "concept_frontmatter", "--json"])
        output = result.output  # type: ignore[union-attr]
        parsed = _json.loads(output)
        for issue in parsed["issues"]:
            assert issue["check"] == "concept_frontmatter"

    def test_validate_json_output(self, tmp_path: Path) -> None:
        """The --json flag produces valid JSON output."""
        import json as _json

        project = _setup_validate_project(tmp_path)
        result = self._invoke(project, ["validate", "--json"])
        output = result.output  # type: ignore[union-attr]
        parsed = _json.loads(output)
        assert "issues" in parsed
        assert "summary" in parsed
        assert isinstance(parsed["issues"], list)
        assert isinstance(parsed["summary"], dict)
        assert "error_count" in parsed["summary"]
        assert "warning_count" in parsed["summary"]
        assert "info_count" in parsed["summary"]

    def test_validate_errors_exit_1(self, tmp_path: Path) -> None:
        """A library with error-severity issues exits with code 1."""
        project = _setup_validate_project_with_errors(tmp_path)
        result = self._invoke(project, ["validate"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "error" in output.lower()

    def test_validate_warnings_only_exit_2(self, tmp_path: Path) -> None:
        """A library with only warning-severity issues exits with code 2."""
        project = _setup_validate_project_with_warnings(tmp_path)
        result = self._invoke(project, ["validate", "--check", "hash_freshness"])
        assert result.exit_code == 2  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "warning" in output.lower()

    def test_validate_requires_project_root(self, tmp_path: Path) -> None:
        """Validate without .lexibrary should fail with exit code 1."""
        result = self._invoke(tmp_path, ["validate"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "No .lexibrary/" in result.output  # type: ignore[union-attr]

    def test_validate_invalid_check_name(self, tmp_path: Path) -> None:
        """An invalid --check name shows available checks and exits 1."""
        project = _setup_validate_project(tmp_path)
        result = self._invoke(project, ["validate", "--check", "nonexistent_check"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Available checks" in output or "Unknown check" in output
        assert "concept_frontmatter" in output


# ---------------------------------------------------------------------------
# Lexi status command tests (task 7.2)
# ---------------------------------------------------------------------------


def _setup_status_project(tmp_path: Path) -> Path:
    """Create a project with design files, concepts, and stack posts for status tests."""
    (tmp_path / ".lexibrary").mkdir()
    (tmp_path / ".lexibrary" / "config.yaml").write_text("")
    (tmp_path / "src").mkdir()
    return tmp_path


class TestLexiStatusCommand:
    """Tests for the `lexi status` command (task 7.2)."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexi_app, args)
        finally:
            os.chdir(old_cwd)

    def test_status_full_dashboard(self, tmp_path: Path) -> None:
        """Status shows a dashboard with artifact counts and issues."""
        project = _setup_status_project(tmp_path)

        # Create source files and design files
        src_content = "def hello(): pass\n"
        (project / "src" / "main.py").write_text(src_content)
        _create_design_file(project, "src/main.py", src_content)

        # Create concepts
        _create_concept_file(project, "Auth", tags=["security"], status="active")

        # Create stack posts
        _create_stack_post(project, post_id="ST-001", title="Test bug", status="open")

        result = self._invoke(project, ["status"])
        output = result.output  # type: ignore[union-attr]

        assert "Lexibrary Status" in output
        assert "Files:" in output
        assert "1 tracked" in output
        assert "Concepts:" in output
        assert "Stack:" in output
        assert "Issues:" in output
        assert "Updated:" in output

    def test_status_quiet_mode_with_lexi_prefix(self, tmp_path: Path) -> None:
        """Quiet mode outputs 'lexi: library healthy' with the lexi prefix."""
        project = _setup_status_project(tmp_path)
        result = self._invoke(project, ["status", "--quiet"])
        output = result.output.strip()  # type: ignore[union-attr]
        # Key: lexi status uses "lexi:" prefix, not "lexictl:"
        assert output == "lexi: library healthy"
        assert result.exit_code == 0  # type: ignore[union-attr]

    def test_status_quiet_with_warnings_uses_lexi_prefix(self, tmp_path: Path) -> None:
        """Quiet mode with warnings uses 'lexi:' prefix and suggests 'lexi validate'."""
        project = _setup_status_project(tmp_path)

        # Create a stale design file
        original_content = "def hello(): pass\n"
        (project / "src" / "stale.py").write_text("def hello(): return 1\n")
        _create_design_file(project, "src/stale.py", original_content)

        result = self._invoke(project, ["status", "--quiet"])
        output = result.output.strip()  # type: ignore[union-attr]
        assert "lexi:" in output
        assert "lexi validate" in output
        assert result.exit_code == 2  # type: ignore[union-attr]

    def test_status_exit_code_clean(self, tmp_path: Path) -> None:
        """Clean library exits with code 0."""
        project = _setup_status_project(tmp_path)
        src_content = "x = 1\n"
        (project / "src" / "main.py").write_text(src_content)
        _create_design_file(project, "src/main.py", src_content)

        result = self._invoke(project, ["status"])
        assert result.exit_code == 0  # type: ignore[union-attr]

    def test_status_exit_code_with_warnings(self, tmp_path: Path) -> None:
        """Status exits with code 2 when only warnings exist."""
        project = _setup_status_project(tmp_path)

        original = "a = 1\n"
        (project / "src" / "w.py").write_text("a = 2\n")
        _create_design_file(project, "src/w.py", original)

        result = self._invoke(project, ["status"])
        assert result.exit_code == 2  # type: ignore[union-attr]

    def test_status_requires_project_root(self, tmp_path: Path) -> None:
        """Status without .lexibrary should fail with exit code 1."""
        result = self._invoke(tmp_path, ["status"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "No .lexibrary/" in result.output  # type: ignore[union-attr]

    def test_status_empty_library(self, tmp_path: Path) -> None:
        """Empty library shows zero counts and 'Updated: never'."""
        project = _setup_status_project(tmp_path)
        result = self._invoke(project, ["status"])
        output = result.output  # type: ignore[union-attr]
        assert "Files: 0 tracked" in output
        assert "Concepts: 0" in output
        assert "Stack: 0 posts" in output
        assert "Updated: never" in output


# ---------------------------------------------------------------------------
# Agent rule content tests (task 7.8)
# ---------------------------------------------------------------------------


class TestAgentRuleContent:
    """Tests for agent rule content via get_core_rules() (task 7.8)."""

    def test_core_rules_includes_lexi_validate(self) -> None:
        """get_core_rules() includes 'lexi validate' instruction."""
        from lexibrary.init.rules.base import get_core_rules

        rules = get_core_rules()
        assert "lexi validate" in rules

    def test_core_rules_excludes_lexi_index(self) -> None:
        """get_core_rules() does NOT include 'lexi index' references."""
        from lexibrary.init.rules.base import get_core_rules

        rules = get_core_rules()
        assert "lexi index" not in rules

    def test_core_rules_excludes_lexictl_instructions(self) -> None:
        """get_core_rules() instructs agents to never run lexictl commands."""
        from lexibrary.init.rules.base import get_core_rules

        rules = get_core_rules()
        # The rules should mention lexictl only in a "never run" / prohibited context
        assert "lexictl" in rules
        assert "Never run" in rules or "never run" in rules.lower()

    def test_core_rules_includes_session_start(self) -> None:
        """get_core_rules() includes session start instructions."""
        from lexibrary.init.rules.base import get_core_rules

        rules = get_core_rules()
        assert "Session Start" in rules
        assert "START_HERE.md" in rules

    def test_core_rules_includes_before_editing(self) -> None:
        """get_core_rules() includes 'Before Editing Files' instructions."""
        from lexibrary.init.rules.base import get_core_rules

        rules = get_core_rules()
        assert "Before Editing" in rules
        assert "lexi lookup" in rules

    def test_core_rules_includes_after_editing(self) -> None:
        """get_core_rules() includes 'After Editing Files' with lexi validate."""
        from lexibrary.init.rules.base import get_core_rules

        rules = get_core_rules()
        assert "After Editing" in rules
        assert "lexi validate" in rules

    def test_orient_skill_references_lexi_status(self) -> None:
        """get_orient_skill_content() references 'lexi status' correctly."""
        from lexibrary.init.rules.base import get_orient_skill_content

        content = get_orient_skill_content()
        assert "lexi status" in content
        assert "lexi index" not in content


# ---------------------------------------------------------------------------
# IWH commands
# ---------------------------------------------------------------------------


def _setup_iwh_project(tmp_path: Path) -> Path:
    """Create a minimal project with IWH enabled."""
    (tmp_path / ".lexibrary").mkdir()
    (tmp_path / ".lexibrary" / "config.yaml").write_text("iwh:\n  enabled: true\n")
    (tmp_path / "src").mkdir()
    return tmp_path


class TestIWH:
    """Tests for lexi iwh write/read/list commands."""

    def test_help_lists_iwh_subgroup(self) -> None:
        result = runner.invoke(lexi_app, ["--help"])
        assert result.exit_code == 0
        assert "iwh" in result.output

    def test_iwh_write_creates_signal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_iwh_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(
            lexi_app,
            ["iwh", "write", "src", "--scope", "incomplete", "--body", "test signal"],
        )
        assert result.exit_code == 0
        assert "Created" in result.output
        # Verify the file exists in the mirror tree
        iwh_file = tmp_path / ".lexibrary" / "src" / ".iwh"
        assert iwh_file.exists()
        content = iwh_file.read_text(encoding="utf-8")
        assert "test signal" in content
        assert "incomplete" in content

    def test_iwh_write_default_scope_incomplete(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_iwh_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(
            lexi_app, ["iwh", "write", "src", "--body", "wip"]
        )
        assert result.exit_code == 0
        assert "incomplete" in result.output

    def test_iwh_write_invalid_scope_exits_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_iwh_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(
            lexi_app,
            ["iwh", "write", "src", "--scope", "critical", "--body", "bad"],
        )
        assert result.exit_code == 1
        assert "Invalid scope" in result.output

    def test_iwh_write_respects_disabled_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / ".lexibrary").mkdir()
        (tmp_path / ".lexibrary" / "config.yaml").write_text("iwh:\n  enabled: false\n")
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(
            lexi_app, ["iwh", "write", "--scope", "incomplete", "--body", "test"]
        )
        assert result.exit_code == 0
        assert "disabled" in result.output

    def test_iwh_write_project_root_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_iwh_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(
            lexi_app, ["iwh", "write", "--body", "root signal"]
        )
        assert result.exit_code == 0
        # Project root IWH → .lexibrary/.iwh
        iwh_file = tmp_path / ".lexibrary" / ".iwh"
        assert iwh_file.exists()

    def test_iwh_read_consumes_signal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from lexibrary.iwh import write_iwh  # noqa: PLC0415

        _setup_iwh_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        # Write a signal at the mirror path for src/
        (tmp_path / ".lexibrary" / "src").mkdir(parents=True, exist_ok=True)
        write_iwh(tmp_path / ".lexibrary" / "src", author="agent", scope="incomplete", body="wip")
        result = runner.invoke(lexi_app, ["iwh", "read", "src"])
        assert result.exit_code == 0
        assert "INCOMPLETE" in result.output
        assert "consumed" in result.output.lower()
        # File should be deleted
        assert not (tmp_path / ".lexibrary" / "src" / ".iwh").exists()

    def test_iwh_read_peek_preserves_signal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from lexibrary.iwh import write_iwh  # noqa: PLC0415

        _setup_iwh_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".lexibrary" / "src").mkdir(parents=True, exist_ok=True)
        write_iwh(tmp_path / ".lexibrary" / "src", author="agent", scope="warning", body="note")
        result = runner.invoke(lexi_app, ["iwh", "read", "src", "--peek"])
        assert result.exit_code == 0
        assert "WARNING" in result.output
        assert "consumed" not in result.output.lower()
        # File should still exist
        assert (tmp_path / ".lexibrary" / "src" / ".iwh").exists()

    def test_iwh_read_missing_shows_message(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_iwh_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(lexi_app, ["iwh", "read", "src"])
        assert result.exit_code == 0
        assert "No IWH signal found" in result.output

    def test_iwh_list_shows_table(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from lexibrary.iwh import write_iwh  # noqa: PLC0415

        _setup_iwh_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".lexibrary" / "src").mkdir(parents=True, exist_ok=True)
        write_iwh(tmp_path / ".lexibrary" / "src", author="agent", scope="blocked", body="stuck")
        write_iwh(tmp_path / ".lexibrary", author="agent", scope="incomplete", body="root wip")
        result = runner.invoke(lexi_app, ["iwh", "list"])
        assert result.exit_code == 0
        assert "2 signal(s)" in result.output

    def test_iwh_list_empty_project(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_iwh_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(lexi_app, ["iwh", "list"])
        assert result.exit_code == 0
        assert "No IWH signals found" in result.output

    def test_iwh_read_respects_disabled_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / ".lexibrary").mkdir()
        (tmp_path / ".lexibrary" / "config.yaml").write_text("iwh:\n  enabled: false\n")
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(lexi_app, ["iwh", "read"])
        assert result.exit_code == 0
        assert "disabled" in result.output
