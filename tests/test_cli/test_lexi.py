"""Tests for the agent-facing CLI (lexi) application."""

from __future__ import annotations

import hashlib
import os
from datetime import datetime
from pathlib import Path

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
            "index",
            "concepts",
            "search",
            "stack",
            "concept",
            "describe",
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
        for cmd in ("init", "update", "validate", "status", "setup", "daemon"):
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
# Index command
# ---------------------------------------------------------------------------


class TestIndexCommand:
    """Tests for the `lexi index` command."""

    def test_index_single_directory(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = runner.invoke(lexi_app, ["index", "src"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 0
        assert "Wrote" in result.output
        assert (tmp_path / ".lexibrary" / "src" / ".aindex").exists()

    def test_index_recursive(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        # Add a subdirectory
        (tmp_path / "src" / "sub").mkdir()
        (tmp_path / "src" / "sub" / "mod.py").write_text("a = 1\n")

        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = runner.invoke(lexi_app, ["index", "-r", "."])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 0
        assert "Indexing complete" in result.output
        assert "directories indexed" in result.output
        # Root and src and src/sub should all have .aindex files
        assert (tmp_path / ".lexibrary" / "src" / ".aindex").exists()
        assert (tmp_path / ".lexibrary" / "src" / "sub" / ".aindex").exists()
        assert (tmp_path / ".lexibrary" / ".aindex").exists()

    def test_index_missing_project(self, tmp_path: Path) -> None:
        """Index should fail if no .lexibrary/ exists."""
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = runner.invoke(lexi_app, ["index", "."])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 1
        assert "No .lexibrary/" in result.output

    def test_index_missing_directory(self, tmp_path: Path) -> None:
        """Index should fail if target directory does not exist."""
        _setup_project(tmp_path)
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = runner.invoke(lexi_app, ["index", "nonexistent"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 1
        assert "Directory not found" in result.output

    def test_index_outside_project_root(self, tmp_path: Path) -> None:
        """Index should fail if target directory is outside the project root."""
        project = tmp_path / "project"
        project.mkdir()
        _setup_project(project)
        outside = tmp_path / "outside"
        outside.mkdir()

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            result = runner.invoke(lexi_app, ["index", str(outside)])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 1
        assert "outside the project root" in result.output


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
        assert "lexi index" in result.output

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
