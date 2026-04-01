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
            "search",
            "stack",
            "concept",
            "convention",
            "describe",
            "validate",
            "status",
            "impact",
            "view",
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
        for cmd in ("init", "update", "setup", "index"):
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
    """Create a design file in .lexibrary/designs/ mirror tree with correct metadata footer."""
    content_hash = hashlib.sha256(source_content.encode()).hexdigest()
    design_path = tmp_path / ".lexibrary" / "designs" / f"{source_rel}.md"
    design_path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now().isoformat()
    design_content = f"""---
description: Design file for {source_rel}
id: DS-001
updated_by: archivist
status: active
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
    aindex_path = tmp_path / ".lexibrary" / "designs" / directory_rel / ".aindex"
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
        "id": "CN-001",
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
    resolution_type: str | None = None,
    stale_at: str | None = None,
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
    if resolution_type is not None:
        fm_data["resolution_type"] = resolution_type
    if stale_at is not None:
        fm_data["stale_at"] = stale_at
    fm_str = yaml.dump(fm_data, default_flow_style=False, sort_keys=False).rstrip("\n")

    parts = [f"---\n{fm_str}\n---\n\n## Problem\n\n{problem}\n\n### Evidence\n\n"]
    for item in resolved_evidence:
        parts.append(f"- {item}\n")
    parts.append("\n")

    post_path.write_text("".join(parts), encoding="utf-8")
    return post_path


def _create_stack_post_with_finding(
    tmp_path: Path,
    post_id: str = "ST-001",
    title: str = "Bug in auth module",
    finding_body: str = "Try restarting the service.",
) -> Path:
    """Create a stack post with one finding for testing."""
    post_path = _create_stack_post(tmp_path, post_id=post_id, title=title)
    # Append a finding section
    content = post_path.read_text(encoding="utf-8")
    finding_section = (
        "## Findings\n\n"
        "### F1\n\n"
        "**Date:** 2026-01-16 | **Author:** helper | **Votes:** 0\n\n"
        f"{finding_body}\n\n"
        "#### Comments\n\n"
    )
    content += finding_section
    post_path.write_text(content, encoding="utf-8")
    return post_path


def _create_aindex_with_conventions(
    tmp_path: Path,
    directory_rel: str,
    billboard: str,
    conventions: list[str] | None = None,
) -> Path:
    """Create a .aindex file with optional local conventions."""
    aindex_file = tmp_path / ".lexibrary" / "designs" / directory_rel / ".aindex"
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
    design_path = tmp_path / ".lexibrary" / "designs" / f"{source_rel}.md"
    design_path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now().isoformat()
    tags_section = "\n".join(f"- {t}" for t in tags) if tags else "- (none)"
    design_content = f"""---
description: {description}
id: DS-002
updated_by: archivist
status: active
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

    def test_lookup_exists_brief(self, tmp_path: Path) -> None:
        """Lookup (default brief) shows description and --full hint."""
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
        assert "Design file for src/main.py" in result.output
        assert "--full" in result.output
        # Brief mode does NOT show the full design file body
        assert "Interface Contract" not in result.output

    def test_lookup_exists_full(self, tmp_path: Path) -> None:
        """Lookup with --full shows full design file content."""
        project = _setup_archivist_project(tmp_path)
        source_content = "def hello():\n    pass\n"
        _create_design_file(project, "src/main.py", source_content)

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            result = runner.invoke(lexi_app, ["lookup", "src/main.py", "--full"])
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


def _create_convention_file(
    project: Path,
    title: str,
    *,
    scope: str = "project",
    rule: str = "",
    body: str = "",
    status: str = "active",
    source: str = "user",
    priority: int = 0,
    tags: list[str] | None = None,
) -> Path:
    """Create a convention file in .lexibrary/conventions/."""
    conventions_dir = project / ".lexibrary" / "conventions"
    conventions_dir.mkdir(parents=True, exist_ok=True)

    # Build slug from title
    slug = title.lower().replace(" ", "-")
    path = conventions_dir / f"{slug}.md"

    fm_data = {
        "title": title,
        "id": "CV-001",
        "scope": scope,
        "tags": tags or [],
        "status": status,
        "source": source,
        "priority": priority,
    }
    fm_str = yaml.dump(fm_data, default_flow_style=False, sort_keys=False).rstrip("\n")

    # If no explicit body, use the rule as the first paragraph
    if not body and rule:
        body = f"\n{rule}\n"
    elif not body:
        body = f"\n{title}\n"

    content = f"---\n{fm_str}\n---\n{body}"
    if not content.endswith("\n"):
        content += "\n"
    path.write_text(content, encoding="utf-8")
    return path


class TestLookupConventionDelivery:
    """Tests for convention delivery in `lexi lookup` via ConventionIndex."""

    def _invoke(self, project: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            return runner.invoke(lexi_app, args)
        finally:
            os.chdir(old_cwd)

    def test_no_conventions_section_when_none_exist(self, tmp_path: Path) -> None:
        """Lookup with no convention files should not show conventions section."""
        project = _setup_archivist_project(tmp_path)
        source_content = "def hello(): pass\n"
        (project / "src" / "main.py").write_text(source_content)
        _create_design_file(project, "src/main.py", source_content)

        result = self._invoke(project, ["lookup", "src/main.py"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Applicable Conventions" not in result.output  # type: ignore[union-attr]

    def test_conventions_section_with_matching_scope(self, tmp_path: Path) -> None:
        """Lookup shows conventions matching the file's directory scope."""
        project = _setup_archivist_project(tmp_path)
        source_content = "def charge(): pass\n"
        (project / "src").mkdir(exist_ok=True)
        (project / "src" / "main.py").write_text(source_content)
        _create_design_file(project, "src/main.py", source_content)

        _create_convention_file(
            project,
            "Use UTC Everywhere",
            scope="src",
            rule="All timestamps must use UTC.",
        )

        result = self._invoke(project, ["lookup", "src/main.py"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Applicable Conventions" in output
        assert "All timestamps must use UTC." in output

    def test_conventions_grouped_by_scope(self, tmp_path: Path) -> None:
        """Conventions from multiple scopes are grouped and ordered root-to-leaf."""
        project = _setup_archivist_project(tmp_path)
        # Create nested directory structure
        (project / "src" / "payments").mkdir(parents=True, exist_ok=True)
        source_content = "def charge(): pass\n"
        (project / "src" / "payments" / "processor.py").write_text(source_content)
        _create_design_file(project, "src/payments/processor.py", source_content)

        _create_convention_file(
            project,
            "UTC Convention",
            scope="project",
            rule="Use UTC everywhere.",
        )
        _create_convention_file(
            project,
            "Decimal Convention",
            scope="src/payments",
            rule="Use Decimal for money.",
        )

        result = self._invoke(project, ["lookup", "src/payments/processor.py"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Applicable Conventions" in output
        assert "Use UTC everywhere." in output
        assert "Use Decimal for money." in output
        # Project scope header should appear before directory scope header
        # within the conventions section
        conv_start = output.index("Applicable Conventions")
        conv_output = output[conv_start:]
        project_pos = conv_output.index("project")
        payments_pos = conv_output.index("src/payments")
        assert project_pos < payments_pos

    def test_draft_conventions_marked(self, tmp_path: Path) -> None:
        """Draft conventions display with [draft] marker."""
        project = _setup_archivist_project(tmp_path)
        source_content = "def login(): pass\n"
        (project / "src" / "main.py").write_text(source_content)
        _create_design_file(project, "src/main.py", source_content)

        _create_convention_file(
            project,
            "Auth Draft Convention",
            scope="project",
            rule="Always validate tokens.",
            status="draft",
        )

        result = self._invoke(project, ["lookup", "src/main.py"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Applicable Conventions" in output
        assert "Always validate tokens." in output
        assert "[draft]" in output

    def test_active_conventions_no_draft_marker(self, tmp_path: Path) -> None:
        """Active conventions do not display a [draft] marker."""
        project = _setup_archivist_project(tmp_path)
        source_content = "def hello(): pass\n"
        (project / "src" / "main.py").write_text(source_content)
        _create_design_file(project, "src/main.py", source_content)

        _create_convention_file(
            project,
            "Active Convention",
            scope="project",
            rule="Always use type hints.",
            status="active",
        )

        result = self._invoke(project, ["lookup", "src/main.py"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Always use type hints." in output
        assert "[draft]" not in output

    def test_display_limit_truncation(self, tmp_path: Path) -> None:
        """When conventions exceed display limit, a truncation notice is shown."""
        project = _setup_archivist_project(tmp_path)
        source_content = "def main(): pass\n"
        (project / "src" / "main.py").write_text(source_content)
        _create_design_file(project, "src/main.py", source_content)

        # Set display limit to 3
        (project / ".lexibrary" / "config.yaml").write_text(
            "conventions:\n  lookup_display_limit: 3\n"
        )

        # Create 6 project-scoped conventions
        for i in range(6):
            _create_convention_file(
                project,
                f"Convention {i}",
                scope="project",
                rule=f"Rule number {i}.",
            )

        result = self._invoke(project, ["lookup", "src/main.py"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Applicable Conventions" in output
        # Should show truncation notice with correct count
        assert "3 more" in output
        assert "lexi conventions" in output

    def test_no_conventions_for_unmatched_scope(self, tmp_path: Path) -> None:
        """File outside convention scope should not see that convention."""
        project = _setup_archivist_project(tmp_path)
        source_content = "x = 1\n"
        (project / "src" / "utils.py").write_text(source_content)
        _create_design_file(project, "src/utils.py", source_content)

        # Convention scoped to src/payments only
        _create_convention_file(
            project,
            "Payments Only",
            scope="src/payments",
            rule="Use Decimal for money.",
        )

        result = self._invoke(project, ["lookup", "src/utils.py"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        # No conventions should apply to src/utils.py
        assert "Applicable Conventions" not in output

    def test_conventions_appear_before_reverse_links(self, tmp_path: Path) -> None:
        """Conventions section appears before link graph reverse-link sections.

        The design file itself may contain a ``## Dependents`` section in its
        content.  We verify ordering by checking that the ``## Applicable
        Conventions`` header in the output comes before any link-graph-generated
        ``## Dependents (imports this file)`` or ``## Also Referenced By``.
        """
        project = _setup_archivist_project(tmp_path)
        source_content = "def hello(): pass\n"
        (project / "src" / "main.py").write_text(source_content)
        _create_design_file(project, "src/main.py", source_content)

        _create_convention_file(
            project,
            "Project Convention",
            scope="project",
            rule="Convention rule text.",
        )

        result = self._invoke(project, ["lookup", "src/main.py"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Applicable Conventions" in output
        conv_pos = output.index("Applicable Conventions")
        # Link graph sections use specific header text distinct from the
        # design file's own "## Dependents" section.
        linkgraph_header = "Dependents (imports this file)"
        if linkgraph_header in output:
            assert conv_pos < output.index(linkgraph_header)
        if "Also Referenced By" in output:
            assert conv_pos < output.index("Also Referenced By")


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
        aindex_path = project / ".lexibrary" / "designs" / "src" / ".aindex"
        aindex_content = aindex_path.read_text(encoding="utf-8")
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


class TestSearchTypeConcept:
    """Tests for `lexi search --type concept` (replaces `lexi concepts`)."""

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
        result = self._invoke(tmp_path, ["search", "--type", "concept"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "No results found" in result.output  # type: ignore[union-attr]

    def test_concepts_list_all(self, tmp_path: Path) -> None:
        """List all concepts when no query is given."""
        _setup_project(tmp_path)
        _create_concept_file(tmp_path, "Authentication", tags=["security"])
        _create_concept_file(tmp_path, "Rate Limiting", tags=["performance"])

        result = self._invoke(tmp_path, ["search", "--type", "concept"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Authentication" in result.output  # type: ignore[union-attr]
        assert "Rate Limiting" in result.output  # type: ignore[union-attr]

    def test_concepts_search(self, tmp_path: Path) -> None:
        """Search concepts by topic."""
        _setup_project(tmp_path)
        _create_concept_file(tmp_path, "Authentication", tags=["security"])
        _create_concept_file(tmp_path, "Rate Limiting", tags=["performance"])

        result = self._invoke(tmp_path, ["search", "auth", "--type", "concept"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Authentication" in result.output  # type: ignore[union-attr]
        assert "Rate Limiting" not in result.output  # type: ignore[union-attr]

    def test_concepts_search_no_match(self, tmp_path: Path) -> None:
        """Search with no matches shows message."""
        _setup_project(tmp_path)
        _create_concept_file(tmp_path, "Authentication", tags=["security"])

        result = self._invoke(tmp_path, ["search", "zzzzz", "--type", "concept"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "No results found" in result.output  # type: ignore[union-attr]

    def test_concepts_no_project(self, tmp_path: Path) -> None:
        """Search without .lexibrary should fail."""
        result = self._invoke(tmp_path, ["search", "--type", "concept"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "No .lexibrary/" in result.output  # type: ignore[union-attr]

    def test_tag_filter_returns_correct_subset(self, tmp_path: Path) -> None:
        """--tag returns only concepts with that tag."""
        _setup_project(tmp_path)
        _create_concept_file(tmp_path, "Authentication", tags=["security", "core"])
        _create_concept_file(tmp_path, "Rate Limiting", tags=["performance"])
        _create_concept_file(tmp_path, "Encryption", tags=["security"])

        result = self._invoke(tmp_path, ["search", "--type", "concept", "--tag", "security"])
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
            tmp_path, ["search", "--type", "concept", "--tag", "security", "--tag", "core"]
        )
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Authentication" in output
        assert "Encryption" not in output
        assert "Config" not in output

    def test_tag_filter_no_match(self, tmp_path: Path) -> None:
        """--tag with no matching concepts shows message."""
        _setup_project(tmp_path)
        _create_concept_file(tmp_path, "Authentication", tags=["security"])

        result = self._invoke(tmp_path, ["search", "--type", "concept", "--tag", "nonexistent"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "No results found" in result.output  # type: ignore[union-attr]

    def test_status_active_filter(self, tmp_path: Path) -> None:
        """--status active returns only active concepts."""
        _setup_project(tmp_path)
        _create_concept_file(tmp_path, "Active Concept", status="active")
        _create_concept_file(tmp_path, "Draft Concept", status="draft")
        _create_concept_file(tmp_path, "Old Concept", status="deprecated")

        result = self._invoke(tmp_path, ["search", "--type", "concept", "--status", "active"])
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

        result = self._invoke(tmp_path, ["search", "--type", "concept", "--status", "draft"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Draft Concept" in output
        assert "Active Concept" not in output

    def test_status_deprecated_overrides_default_exclusion(self, tmp_path: Path) -> None:
        """--status deprecated returns deprecated concepts despite default exclusion."""
        _setup_project(tmp_path)
        _create_concept_file(tmp_path, "Active Concept", status="active")
        _create_concept_file(tmp_path, "Old Concept", status="deprecated")

        result = self._invoke(tmp_path, ["search", "--type", "concept", "--status", "deprecated"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Old Concept" in output
        assert "Active Concept" not in output

    def test_all_flag_includes_deprecated(self, tmp_path: Path) -> None:
        """--all includes deprecated concepts in results."""
        _setup_project(tmp_path)
        _create_concept_file(tmp_path, "Active Concept", status="active")
        _create_concept_file(tmp_path, "Old Concept", status="deprecated")
        _create_concept_file(tmp_path, "Draft Concept", status="draft")

        result = self._invoke(tmp_path, ["search", "--type", "concept", "--all"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Active Concept" in output
        assert "Old Concept" in output
        assert "Draft Concept" in output

    def test_bare_search_hides_deprecated(self, tmp_path: Path) -> None:
        """Bare `lexi search --type concept` hides deprecated concepts by default."""
        _setup_project(tmp_path)
        _create_concept_file(tmp_path, "Active Concept", status="active")
        _create_concept_file(tmp_path, "Draft Concept", status="draft")
        _create_concept_file(tmp_path, "Old Concept", status="deprecated")

        result = self._invoke(tmp_path, ["search", "--type", "concept"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Active Concept" in output
        assert "Draft Concept" in output
        assert "Old Concept" not in output

    def test_topic_search_hides_deprecated(self, tmp_path: Path) -> None:
        """Topic search also hides deprecated concepts by default."""
        _setup_project(tmp_path)
        _create_concept_file(tmp_path, "Auth Active", tags=["auth"], status="active")
        _create_concept_file(tmp_path, "Auth Old", tags=["auth"], status="deprecated")

        result = self._invoke(tmp_path, ["search", "auth", "--type", "concept"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Auth Active" in output
        assert "Auth Old" not in output

    def test_topic_plus_tag(self, tmp_path: Path) -> None:
        """topic + --tag narrows with AND logic."""
        _setup_project(tmp_path)
        _create_concept_file(
            tmp_path, "Auth Core", tags=["security", "core"], summary="authentication"
        )
        _create_concept_file(
            tmp_path, "Auth Perf", tags=["performance"], summary="authentication perf"
        )
        _create_concept_file(tmp_path, "Encryption", tags=["security"], summary="crypto")

        result = self._invoke(
            tmp_path, ["search", "auth", "--type", "concept", "--tag", "security"]
        )
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
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
            tmp_path, ["search", "auth", "--type", "concept", "--status", "draft"]
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
            ["search", "auth", "--type", "concept", "--tag", "security", "--status", "active"],
        )
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Auth Core Active" in output
        assert "Auth Core Draft" not in output
        assert "Auth Perf Active" not in output

    def test_all_filters_no_match(self, tmp_path: Path) -> None:
        """Combined filters that match nothing show appropriate message."""
        _setup_project(tmp_path)
        _create_concept_file(tmp_path, "Authentication", tags=["security"], status="active")

        result = self._invoke(
            tmp_path,
            ["search", "auth", "--type", "concept", "--tag", "nonexistent", "--status", "draft"],
        )
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "No results found" in result.output  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Agent help command tests (task 3.6)
# ---------------------------------------------------------------------------


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
        assert "slug: CN-001-rate-limiting" in result.output  # type: ignore[union-attr]
        assert (tmp_path / ".lexibrary" / "concepts" / "CN-001-rate-limiting.md").exists()

    def test_create_concept_with_tags(self, tmp_path: Path) -> None:
        """Create a concept with tags."""
        _setup_project(tmp_path)
        (tmp_path / ".lexibrary" / "concepts").mkdir(parents=True, exist_ok=True)

        result = self._invoke(
            tmp_path, ["concept", "new", "Auth", "--tag", "security", "--tag", "core"]
        )
        assert result.exit_code == 0  # type: ignore[union-attr]

        content = (tmp_path / ".lexibrary" / "concepts" / "CN-001-auth.md").read_text()
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
        """Concept name with spaces gets ID-prefixed slug filename."""
        _setup_project(tmp_path)
        (tmp_path / ".lexibrary" / "concepts").mkdir(parents=True, exist_ok=True)

        result = self._invoke(tmp_path, ["concept", "new", "my cool concept"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert (tmp_path / ".lexibrary" / "concepts" / "CN-001-my-cool-concept.md").exists()


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
        design_path = project / ".lexibrary" / "designs" / "src" / "main.py.md"
        design_content = design_path.read_text(encoding="utf-8")
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
# Concept comment command tests
# ---------------------------------------------------------------------------


class TestConceptCommentCommand:
    """Tests for the `lexi concept comment` command."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexi_app, args)
        finally:
            os.chdir(old_cwd)

    def test_comment_on_existing_concept(self, tmp_path: Path) -> None:
        """Successfully append a comment to an existing concept."""
        _setup_project(tmp_path)
        _create_concept_file(tmp_path, "Scope Root")

        result = self._invoke(
            tmp_path,
            ["concept", "comment", "ScopeRoot", "--body", "Add workspace root as alias"],
        )
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Comment added" in result.output  # type: ignore[union-attr]
        assert "ScopeRoot" in result.output  # type: ignore[union-attr]

        # Verify comment file was created
        comment_path = tmp_path / ".lexibrary" / "concepts" / "ScopeRoot.comments.yaml"
        assert comment_path.exists()
        content = comment_path.read_text(encoding="utf-8")
        assert "Add workspace root as alias" in content

    def test_first_comment_creates_file(self, tmp_path: Path) -> None:
        """First comment on a concept should create the .comments.yaml file."""
        _setup_project(tmp_path)
        _create_concept_file(tmp_path, "ScopeRoot")

        comment_path = tmp_path / ".lexibrary" / "concepts" / "ScopeRoot.comments.yaml"
        assert not comment_path.exists()

        result = self._invoke(
            tmp_path,
            ["concept", "comment", "ScopeRoot", "--body", "first note"],
        )
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert comment_path.exists()

        # Verify the comment file has exactly one comment
        data = yaml.safe_load(comment_path.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        assert "comments" in data
        assert len(data["comments"]) == 1
        assert data["comments"][0]["body"] == "first note"

    def test_comment_missing_concept(self, tmp_path: Path) -> None:
        """Commenting on a nonexistent concept should fail with exit code 1."""
        _setup_project(tmp_path)

        result = self._invoke(
            tmp_path,
            ["concept", "comment", "nonexistent", "--body", "text"],
        )
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "not found" in result.output.lower()  # type: ignore[union-attr]

    def test_comment_no_project(self, tmp_path: Path) -> None:
        """Concept comment without .lexibrary should fail."""
        result = self._invoke(
            tmp_path,
            ["concept", "comment", "anything", "--body", "text"],
        )
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "No .lexibrary/" in result.output  # type: ignore[union-attr]

    def test_comment_short_flag(self, tmp_path: Path) -> None:
        """The -b short flag works for --body."""
        _setup_project(tmp_path)
        _create_concept_file(tmp_path, "Auth")

        result = self._invoke(
            tmp_path,
            ["concept", "comment", "Auth", "-b", "short flag comment"],
        )
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Comment added" in result.output  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Concept deprecate CLI command tests
# ---------------------------------------------------------------------------


class TestConceptDeprecateCommand:
    """Tests for the `lexi concept deprecate` command."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexi_app, args)
        finally:
            os.chdir(old_cwd)

    def test_deprecate_active_concept(self, tmp_path: Path) -> None:
        """Deprecating an active concept sets status to deprecated."""
        _setup_project(tmp_path)
        _create_concept_file(tmp_path, "Scope Root", status="active")

        result = self._invoke(
            tmp_path,
            ["concept", "deprecate", "ScopeRoot"],
        )
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Deprecated" in result.output  # type: ignore[union-attr]
        assert "Scope Root" in result.output  # type: ignore[union-attr]

        # Verify the file was updated
        concept_path = tmp_path / ".lexibrary" / "concepts" / "ScopeRoot.md"
        content = concept_path.read_text(encoding="utf-8")
        assert "status: deprecated" in content

    def test_deprecate_with_supersession(self, tmp_path: Path) -> None:
        """Deprecating with --superseded-by sets the superseded_by field."""
        _setup_project(tmp_path)
        _create_concept_file(tmp_path, "Project Scope", status="active")

        result = self._invoke(
            tmp_path,
            ["concept", "deprecate", "ProjectScope", "--superseded-by", "Scope Root"],
        )
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Deprecated" in result.output  # type: ignore[union-attr]
        assert "Scope Root" in result.output  # type: ignore[union-attr]

        # Verify the file was updated with both fields
        concept_path = tmp_path / ".lexibrary" / "concepts" / "ProjectScope.md"
        content = concept_path.read_text(encoding="utf-8")
        assert "status: deprecated" in content
        assert "superseded_by: Scope Root" in content

    def test_deprecate_concept_not_found(self, tmp_path: Path) -> None:
        """Deprecating a nonexistent concept should fail with exit code 1."""
        _setup_project(tmp_path)

        result = self._invoke(
            tmp_path,
            ["concept", "deprecate", "nonexistent"],
        )
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "not found" in result.output.lower()  # type: ignore[union-attr]

    def test_deprecate_already_deprecated(self, tmp_path: Path) -> None:
        """Deprecating an already-deprecated concept should exit 0 with message."""
        _setup_project(tmp_path)
        _create_concept_file(tmp_path, "Old Concept", status="deprecated")

        result = self._invoke(
            tmp_path,
            ["concept", "deprecate", "OldConcept"],
        )
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Already deprecated" in result.output  # type: ignore[union-attr]

    def test_deprecate_no_project(self, tmp_path: Path) -> None:
        """Concept deprecate without .lexibrary should fail."""
        result = self._invoke(
            tmp_path,
            ["concept", "deprecate", "anything"],
        )
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "No .lexibrary/" in result.output  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Convention CLI command tests
# ---------------------------------------------------------------------------


class TestConventionNewCommand:
    """Tests for the `lexi convention new` command."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexi_app, args)
        finally:
            os.chdir(old_cwd)

    def test_create_convention_with_all_flags(self, tmp_path: Path) -> None:
        """Create a convention with --scope, --body, --tag, --title flags."""
        project = _setup_project(tmp_path)
        result = self._invoke(
            project,
            [
                "convention",
                "new",
                "--scope",
                "src/auth",
                "--body",
                "All endpoints require auth",
                "--tag",
                "auth",
                "--title",
                "Auth required",
            ],
        )
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Created" in result.output  # type: ignore[union-attr]
        assert "auth-required.md" in result.output  # type: ignore[union-attr]

        # Verify file was created (new format: CV-NNN-slug.md)
        conventions_dir = project / ".lexibrary" / "conventions"
        conv_files = list(conventions_dir.glob("CV-*-auth-required.md"))
        assert len(conv_files) == 1, (
            f"Expected 1 convention file, found: {list(conventions_dir.glob('*.md'))}"
        )
        content = conv_files[0].read_text(encoding="utf-8")
        assert "Auth required" in content
        assert "src/auth" in content
        assert "auth" in content

    def test_create_convention_auto_title(self, tmp_path: Path) -> None:
        """Create a convention with auto-generated title from body."""
        project = _setup_project(tmp_path)
        result = self._invoke(
            project,
            [
                "convention",
                "new",
                "--scope",
                "project",
                "--body",
                "Use from __future__ import annotations in every module",
            ],
        )
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Created" in result.output  # type: ignore[union-attr]

    def test_agent_source_defaults(self, tmp_path: Path) -> None:
        """Agent-created convention should default to draft status and priority -1."""
        project = _setup_project(tmp_path)
        result = self._invoke(
            project,
            [
                "convention",
                "new",
                "--scope",
                "project",
                "--body",
                "Use rich console",
                "--source",
                "agent",
            ],
        )
        assert result.exit_code == 0  # type: ignore[union-attr]

        # Read the file and check status and priority
        conventions_dir = project / ".lexibrary" / "conventions"
        files = list(conventions_dir.glob("*.md"))
        assert len(files) == 1
        content = files[0].read_text(encoding="utf-8")
        assert "status: draft" in content
        assert "priority: -1" in content
        assert "source: agent" in content

    def test_user_source_defaults(self, tmp_path: Path) -> None:
        """User-created convention should default to active status and priority 0."""
        project = _setup_project(tmp_path)
        result = self._invoke(
            project,
            [
                "convention",
                "new",
                "--scope",
                "project",
                "--body",
                "Use rich console",
                "--title",
                "Rich console",
            ],
        )
        assert result.exit_code == 0  # type: ignore[union-attr]

        conventions_dir = project / ".lexibrary" / "conventions"
        files = list(conventions_dir.glob("*.md"))
        assert len(files) == 1
        content = files[0].read_text(encoding="utf-8")
        assert "status: active" in content
        assert "priority: 0" in content
        assert "source: user" in content

    def test_creates_conventions_directory(self, tmp_path: Path) -> None:
        """Convention new should create .lexibrary/conventions/ if it does not exist."""
        project = _setup_project(tmp_path)
        conventions_dir = project / ".lexibrary" / "conventions"
        assert not conventions_dir.exists()

        result = self._invoke(
            project,
            [
                "convention",
                "new",
                "--scope",
                "project",
                "--body",
                "Test convention",
                "--title",
                "Test",
            ],
        )
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert conventions_dir.is_dir()

    def test_refuse_duplicate_slug(self, tmp_path: Path) -> None:
        """Creating a convention with an existing slug should fail."""
        project = _setup_project(tmp_path)
        _create_convention_file(project, "Auth required")

        result = self._invoke(
            project,
            [
                "convention",
                "new",
                "--scope",
                "project",
                "--body",
                "...",
                "--title",
                "Auth required",
            ],
        )
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "already exists" in result.output  # type: ignore[union-attr]

    def test_no_project(self, tmp_path: Path) -> None:
        """Convention new without .lexibrary should fail."""
        result = self._invoke(
            tmp_path,
            [
                "convention",
                "new",
                "--scope",
                "project",
                "--body",
                "test",
            ],
        )
        assert result.exit_code == 1  # type: ignore[union-attr]


class TestConventionApproveCommand:
    """Tests for the `lexi convention approve` command."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexi_app, args)
        finally:
            os.chdir(old_cwd)

    def test_approve_draft(self, tmp_path: Path) -> None:
        """Approve a draft convention sets status to active."""
        project = _setup_project(tmp_path)
        _create_convention_file(project, "Auth required", status="draft")

        result = self._invoke(project, ["convention", "approve", "auth-required"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Approved" in result.output  # type: ignore[union-attr]

        # Verify file was updated
        conv_path = project / ".lexibrary" / "conventions" / "auth-required.md"
        content = conv_path.read_text(encoding="utf-8")
        assert "status: active" in content

    def test_approve_already_active(self, tmp_path: Path) -> None:
        """Approving an already active convention should show message and exit 0."""
        project = _setup_project(tmp_path)
        _create_convention_file(project, "Auth required", status="active")

        result = self._invoke(project, ["convention", "approve", "auth-required"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Already active" in result.output  # type: ignore[union-attr]

    def test_approve_deprecated(self, tmp_path: Path) -> None:
        """Approving a deprecated convention should fail."""
        project = _setup_project(tmp_path)
        _create_convention_file(project, "Auth required", status="deprecated")

        result = self._invoke(project, ["convention", "approve", "auth-required"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "Cannot approve" in result.output  # type: ignore[union-attr]

    def test_approve_title_not_accepted(self, tmp_path: Path) -> None:
        """Approving by title (not slug) should fail -- slug-only lookups."""
        project = _setup_project(tmp_path)
        _create_convention_file(project, "Auth required", status="draft")

        result = self._invoke(project, ["convention", "approve", "Auth required"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "Convention not found" in result.output  # type: ignore[union-attr]

    def test_approve_not_found(self, tmp_path: Path) -> None:
        """Approving a nonexistent convention should fail."""
        project = _setup_project(tmp_path)
        (project / ".lexibrary" / "conventions").mkdir(parents=True, exist_ok=True)

        result = self._invoke(project, ["convention", "approve", "nonexistent"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "Convention not found" in result.output  # type: ignore[union-attr]


class TestConventionDeprecateCommand:
    """Tests for the `lexi convention deprecate` command."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexi_app, args)
        finally:
            os.chdir(old_cwd)

    def test_deprecate_active(self, tmp_path: Path) -> None:
        """Deprecating an active convention sets status to deprecated."""
        project = _setup_project(tmp_path)
        _create_convention_file(project, "Auth required", status="active")

        result = self._invoke(project, ["convention", "deprecate", "auth-required"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Deprecated" in result.output  # type: ignore[union-attr]

        conv_path = project / ".lexibrary" / "conventions" / "auth-required.md"
        content = conv_path.read_text(encoding="utf-8")
        assert "status: deprecated" in content

    def test_deprecate_draft(self, tmp_path: Path) -> None:
        """Deprecating a draft convention works."""
        project = _setup_project(tmp_path)
        _create_convention_file(project, "Auth required", status="draft")

        result = self._invoke(project, ["convention", "deprecate", "auth-required"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Deprecated" in result.output  # type: ignore[union-attr]

    def test_deprecate_not_found(self, tmp_path: Path) -> None:
        """Deprecating a nonexistent convention should fail."""
        project = _setup_project(tmp_path)
        (project / ".lexibrary" / "conventions").mkdir(parents=True, exist_ok=True)

        result = self._invoke(project, ["convention", "deprecate", "nonexistent"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "Convention not found" in result.output  # type: ignore[union-attr]

    def test_deprecate_title_not_accepted(self, tmp_path: Path) -> None:
        """Deprecating by title (not slug) should fail -- slug-only lookups."""
        project = _setup_project(tmp_path)
        _create_convention_file(project, "Auth required", status="active")

        result = self._invoke(project, ["convention", "deprecate", "Auth required"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "Convention not found" in result.output  # type: ignore[union-attr]


class TestSearchTypeConvention:
    """Tests for `lexi search --type convention` (replaces `lexi conventions`)."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexi_app, args)
        finally:
            os.chdir(old_cwd)

    def test_list_all_non_deprecated(self, tmp_path: Path) -> None:
        """List conventions should exclude deprecated by default."""
        project = _setup_project(tmp_path)
        _create_convention_file(project, "Conv Active", status="active")
        _create_convention_file(project, "Conv Draft", status="draft")
        _create_convention_file(project, "Conv Deprecated", status="deprecated")

        result = self._invoke(project, ["search", "--type", "convention"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Conv Active" in result.output  # type: ignore[union-attr]
        assert "Conv Draft" in result.output  # type: ignore[union-attr]
        assert "Conv Deprecated" not in result.output  # type: ignore[union-attr]

    def test_list_with_all_flag(self, tmp_path: Path) -> None:
        """--all flag includes deprecated conventions."""
        project = _setup_project(tmp_path)
        _create_convention_file(project, "Conv Active", status="active")
        _create_convention_file(project, "Conv Deprecated", status="deprecated")

        result = self._invoke(project, ["search", "--type", "convention", "--all"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Conv Active" in result.output  # type: ignore[union-attr]
        assert "Conv Deprecated" in result.output  # type: ignore[union-attr]

    def test_filter_by_tag(self, tmp_path: Path) -> None:
        """Filter conventions by tag."""
        project = _setup_project(tmp_path)
        _create_convention_file(project, "Python Style", tags=["python"])
        _create_convention_file(project, "Auth Rules", tags=["auth"])

        result = self._invoke(project, ["search", "--type", "convention", "--tag", "python"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Python Style" in result.output  # type: ignore[union-attr]
        assert "Auth Rules" not in result.output  # type: ignore[union-attr]

    def test_filter_by_status(self, tmp_path: Path) -> None:
        """Filter conventions by status."""
        project = _setup_project(tmp_path)
        _create_convention_file(project, "Active Conv", status="active")
        _create_convention_file(project, "Draft Conv", status="draft")

        result = self._invoke(project, ["search", "--type", "convention", "--status", "draft"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Draft Conv" in result.output  # type: ignore[union-attr]
        assert "Active Conv" not in result.output  # type: ignore[union-attr]

    def test_filter_by_scope(self, tmp_path: Path) -> None:
        """Filter conventions by scope (scope inheritance)."""
        project = _setup_project(tmp_path)
        _create_convention_file(project, "Project Wide", scope="project")
        _create_convention_file(project, "Auth Scope", scope="src/auth")

        result = self._invoke(
            project, ["search", "--type", "convention", "--scope", "src/auth/login.py"]
        )
        assert result.exit_code == 0  # type: ignore[union-attr]
        # Both project-wide and auth-scoped conventions should match via inheritance
        assert "Project Wide" in result.output  # type: ignore[union-attr]
        assert "Auth Scope" in result.output  # type: ignore[union-attr]

    def test_no_conventions_empty_result(self, tmp_path: Path) -> None:
        """When no conventions exist, show no results message."""
        project = _setup_project(tmp_path)

        result = self._invoke(project, ["search", "--type", "convention"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "No results found" in result.output  # type: ignore[union-attr]

    def test_no_matching_conventions(self, tmp_path: Path) -> None:
        """When no conventions match filters, show message."""
        project = _setup_project(tmp_path)
        _create_convention_file(project, "Active Conv", tags=["python"])

        result = self._invoke(project, ["search", "--type", "convention", "--tag", "nonexistent"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "No results found" in result.output  # type: ignore[union-attr]

    def test_table_shows_rule_column(self, tmp_path: Path) -> None:
        """Table output includes the Rule column with truncated rule text."""
        project = _setup_project(tmp_path)
        _create_convention_file(
            project, "Long Rule Conv", body="This is the rule text for the convention."
        )

        result = self._invoke(project, ["search", "--type", "convention"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "This is the rule text" in result.output  # type: ignore[union-attr]

    def test_tag_filter_and_logic(self, tmp_path: Path) -> None:
        """Multiple --tag options use AND logic."""
        project = _setup_project(tmp_path)
        _create_convention_file(project, "Both Tags", tags=["python", "auth"])
        _create_convention_file(project, "Python Only", tags=["python"])

        result = self._invoke(
            project, ["search", "--type", "convention", "--tag", "python", "--tag", "auth"]
        )
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Both Tags" in result.output  # type: ignore[union-attr]
        assert "Python Only" not in result.output  # type: ignore[union-attr]

    def test_search_by_query(self, tmp_path: Path) -> None:
        """Free-text search via positional query argument."""
        project = _setup_project(tmp_path)
        _create_convention_file(project, "All endpoints require auth decorator", tags=["auth"])
        _create_convention_file(project, "Use dataclasses for models", tags=["python"])

        result = self._invoke(project, ["search", "auth", "--type", "convention"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "auth decorator" in result.output  # type: ignore[union-attr]
        assert "dataclasses" not in result.output  # type: ignore[union-attr]

    def test_search_no_matches(self, tmp_path: Path) -> None:
        """Query with no matches shows message."""
        project = _setup_project(tmp_path)
        _create_convention_file(project, "Active Conv")

        result = self._invoke(project, ["search", "xyznonexistent", "--type", "convention"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "No results found" in result.output  # type: ignore[union-attr]

    def test_search_combinable_with_tag(self, tmp_path: Path) -> None:
        """Query combined with --tag narrows results."""
        project = _setup_project(tmp_path)
        _create_convention_file(project, "Auth endpoints required", tags=["auth"])
        _create_convention_file(project, "Auth logging required", tags=["logging"])

        result = self._invoke(
            project, ["search", "auth", "--type", "convention", "--tag", "logging"]
        )
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Auth logging" in result.output  # type: ignore[union-attr]
        assert "Auth endpoints" not in result.output  # type: ignore[union-attr]

    def test_no_query_lists_all(self, tmp_path: Path) -> None:
        """Without query, all non-deprecated conventions are listed."""
        project = _setup_project(tmp_path)
        _create_convention_file(project, "Conv A")
        _create_convention_file(project, "Conv B")

        result = self._invoke(project, ["search", "--type", "convention"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Conv A" in result.output  # type: ignore[union-attr]
        assert "Conv B" in result.output  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Convention new --alias tests
# ---------------------------------------------------------------------------


class TestConventionNewAliasFlag:
    """Tests for the --alias flag on `lexi convention new`."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexi_app, args)
        finally:
            os.chdir(old_cwd)

    def test_create_with_aliases(self, tmp_path: Path) -> None:
        """Create a convention with --alias flags populates aliases in frontmatter."""
        project = _setup_project(tmp_path)
        result = self._invoke(
            project,
            [
                "convention",
                "new",
                "--scope",
                "src/api",
                "--body",
                "Auth decorator required",
                "--title",
                "Auth decorator required",
                "--alias",
                "auth-decorator",
                "--alias",
                "auth-conv",
            ],
        )
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Created" in result.output  # type: ignore[union-attr]

        # New format: CV-NNN-slug.md
        conventions_dir = project / ".lexibrary" / "conventions"
        conv_files = list(conventions_dir.glob("CV-*-auth-decorator-required.md"))
        assert len(conv_files) == 1, (
            f"Expected 1 convention file, found: {list(conventions_dir.glob('*.md'))}"
        )
        content = conv_files[0].read_text(encoding="utf-8")
        assert "auth-decorator" in content
        assert "auth-conv" in content
        assert "aliases" in content

    def test_create_without_aliases(self, tmp_path: Path) -> None:
        """Create a convention without --alias omits aliases from frontmatter."""
        project = _setup_project(tmp_path)
        result = self._invoke(
            project,
            [
                "convention",
                "new",
                "--scope",
                "project",
                "--body",
                "Use UTC everywhere",
                "--title",
                "Use UTC everywhere",
            ],
        )
        assert result.exit_code == 0  # type: ignore[union-attr]

        conventions_dir = project / ".lexibrary" / "conventions"
        files = list(conventions_dir.glob("*.md"))
        assert len(files) == 1
        content = files[0].read_text(encoding="utf-8")
        # Empty aliases list should be omitted from serialization
        assert "aliases" not in content


# ---------------------------------------------------------------------------
# Convention deprecate with deprecated_at tests
# ---------------------------------------------------------------------------


class TestConventionDeprecateTimestamp:
    """Tests for deprecated_at timestamp in `lexi convention deprecate`."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexi_app, args)
        finally:
            os.chdir(old_cwd)

    def test_deprecate_sets_deprecated_at(self, tmp_path: Path) -> None:
        """Deprecating a convention sets deprecated_at to an ISO timestamp."""
        project = _setup_project(tmp_path)
        _create_convention_file(project, "Auth required", status="active")

        result = self._invoke(project, ["convention", "deprecate", "auth-required"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Deprecated" in result.output  # type: ignore[union-attr]

        conv_path = project / ".lexibrary" / "conventions" / "auth-required.md"
        content = conv_path.read_text(encoding="utf-8")
        assert "status: deprecated" in content
        assert "deprecated_at:" in content

    def test_deprecate_already_deprecated(self, tmp_path: Path) -> None:
        """Deprecating an already deprecated convention prints message and exits 0."""
        project = _setup_project(tmp_path)
        _create_convention_file(project, "Auth required", status="deprecated")

        result = self._invoke(project, ["convention", "deprecate", "auth-required"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Already deprecated" in result.output  # type: ignore[union-attr]

    def test_deprecate_draft_sets_timestamp(self, tmp_path: Path) -> None:
        """Deprecating a draft convention also sets deprecated_at."""
        project = _setup_project(tmp_path)
        _create_convention_file(project, "Draft rule", status="draft")

        result = self._invoke(project, ["convention", "deprecate", "draft-rule"])
        assert result.exit_code == 0  # type: ignore[union-attr]

        conv_path = project / ".lexibrary" / "conventions" / "draft-rule.md"
        content = conv_path.read_text(encoding="utf-8")
        assert "status: deprecated" in content
        assert "deprecated_at:" in content


# ---------------------------------------------------------------------------
# Convention comment command tests
# ---------------------------------------------------------------------------


class TestConventionCommentCommand:
    """Tests for the `lexi convention comment` command."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexi_app, args)
        finally:
            os.chdir(old_cwd)

    def test_add_comment(self, tmp_path: Path) -> None:
        """Add a comment to a convention creates .comments.yaml."""
        project = _setup_project(tmp_path)
        _create_convention_file(project, "Use dataclasses")

        result = self._invoke(
            project,
            ["convention", "comment", "use-dataclasses", "--body", "Consider narrowing scope"],
        )
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Comment added" in result.output  # type: ignore[union-attr]

        comment_file = project / ".lexibrary" / "conventions" / "use-dataclasses.comments.yaml"
        assert comment_file.exists()
        content = comment_file.read_text(encoding="utf-8")
        assert "Consider narrowing scope" in content

    def test_comment_creates_file(self, tmp_path: Path) -> None:
        """First comment creates the .comments.yaml file."""
        project = _setup_project(tmp_path)
        _create_convention_file(project, "Auth required")

        comment_file = project / ".lexibrary" / "conventions" / "auth-required.comments.yaml"
        assert not comment_file.exists()

        result = self._invoke(
            project,
            ["convention", "comment", "auth-required", "--body", "First feedback"],
        )
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert comment_file.exists()

    def test_comment_title_not_accepted(self, tmp_path: Path) -> None:
        """Commenting by title (not slug) should fail -- slug-only lookups."""
        project = _setup_project(tmp_path)
        _create_convention_file(project, "Auth required")

        result = self._invoke(
            project,
            ["convention", "comment", "Auth required", "--body", "Test comment"],
        )
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "Convention not found" in result.output  # type: ignore[union-attr]

    def test_comment_not_found(self, tmp_path: Path) -> None:
        """Comment on nonexistent convention fails with exit code 1."""
        project = _setup_project(tmp_path)
        (project / ".lexibrary" / "conventions").mkdir(parents=True, exist_ok=True)

        result = self._invoke(
            project,
            ["convention", "comment", "nonexistent", "--body", "feedback"],
        )
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "Convention not found" in result.output  # type: ignore[union-attr]

    def test_multiple_comments_append(self, tmp_path: Path) -> None:
        """Multiple comments are appended to the same file."""
        project = _setup_project(tmp_path)
        _create_convention_file(project, "Auth required")

        self._invoke(
            project,
            ["convention", "comment", "auth-required", "--body", "First comment"],
        )
        self._invoke(
            project,
            ["convention", "comment", "auth-required", "--body", "Second comment"],
        )

        comment_file = project / ".lexibrary" / "conventions" / "auth-required.comments.yaml"
        content = comment_file.read_text(encoding="utf-8")
        assert "First comment" in content
        assert "Second comment" in content


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

    def test_create_post_prints_blank_warnings(self, tmp_path: Path) -> None:
        """Post command prints blank-section warnings for omitted fields."""
        _setup_stack_project(tmp_path)
        result = self._invoke(tmp_path, ["stack", "post", "--title", "Bug", "--tag", "auth"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Note: The following sections are blank:" in result.output  # type: ignore[union-attr]
        assert "problem" in result.output  # type: ignore[union-attr]

    def test_one_shot_post_with_problem_and_attempts(self, tmp_path: Path) -> None:
        """One-shot post creation with --problem and --attempts populates sections."""
        _setup_stack_project(tmp_path)
        result = self._invoke(
            tmp_path,
            [
                "stack",
                "post",
                "--title",
                "Config fails",
                "--tag",
                "config",
                "--problem",
                "Config parsing fails on startup",
                "--attempts",
                "Tried strict mode",
                "--attempts",
                "Tried permissive mode",
            ],
        )
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Created" in result.output  # type: ignore[union-attr]
        stack_dir = tmp_path / ".lexibrary" / "stack"
        files = list(stack_dir.glob("ST-001-*.md"))
        assert len(files) == 1
        content = files[0].read_text(encoding="utf-8")
        assert "Config parsing fails on startup" in content
        assert "Tried strict mode" in content
        assert "Tried permissive mode" in content

    def test_finding_creates_post_with_f1(self, tmp_path: Path) -> None:
        """--finding creates post with F1 appended via mutation."""
        _setup_stack_project(tmp_path)
        result = self._invoke(
            tmp_path,
            [
                "stack",
                "post",
                "--title",
                "Bug",
                "--tag",
                "bug",
                "--problem",
                "Something broke",
                "--finding",
                "Set extra=forbid in the model",
            ],
        )
        assert result.exit_code == 0  # type: ignore[union-attr]
        stack_dir = tmp_path / ".lexibrary" / "stack"
        files = list(stack_dir.glob("ST-001-*.md"))
        assert len(files) == 1
        content = files[0].read_text(encoding="utf-8")
        assert "F1" in content
        assert "Set extra=forbid in the model" in content

    def test_finding_with_resolve_creates_resolved_post(self, tmp_path: Path) -> None:
        """--finding + --resolve creates a resolved post."""
        _setup_stack_project(tmp_path)
        result = self._invoke(
            tmp_path,
            [
                "stack",
                "post",
                "--title",
                "Bug",
                "--tag",
                "bug",
                "--finding",
                "Fixed it",
                "--resolve",
            ],
        )
        assert result.exit_code == 0  # type: ignore[union-attr]
        stack_dir = tmp_path / ".lexibrary" / "stack"
        files = list(stack_dir.glob("ST-001-*.md"))
        assert len(files) == 1
        content = files[0].read_text(encoding="utf-8")
        assert "status: resolved" in content
        assert "**Accepted:** true" in content

    def test_resolve_without_finding_fails(self, tmp_path: Path) -> None:
        """--resolve without --finding produces error."""
        _setup_stack_project(tmp_path)
        result = self._invoke(
            tmp_path,
            ["stack", "post", "--title", "Bug", "--tag", "bug", "--resolve"],
        )
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "--resolve requires --finding" in result.output  # type: ignore[union-attr]

    def test_resolution_type_without_resolve_fails(self, tmp_path: Path) -> None:
        """--resolution-type without --resolve produces error."""
        _setup_stack_project(tmp_path)
        result = self._invoke(
            tmp_path,
            [
                "stack",
                "post",
                "--title",
                "Bug",
                "--tag",
                "bug",
                "--resolution-type",
                "fix",
            ],
        )
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "--resolution-type requires --resolve" in result.output  # type: ignore[union-attr]

    def test_fix_shortcut_creates_resolved_post(self, tmp_path: Path) -> None:
        """--fix creates a resolved post with resolution_type=fix."""
        _setup_stack_project(tmp_path)
        result = self._invoke(
            tmp_path,
            [
                "stack",
                "post",
                "--title",
                "Auth crash",
                "--tag",
                "auth",
                "--problem",
                "Login crashes",
                "--fix",
                "Added null check before access",
            ],
        )
        assert result.exit_code == 0  # type: ignore[union-attr]
        stack_dir = tmp_path / ".lexibrary" / "stack"
        files = list(stack_dir.glob("ST-001-*.md"))
        assert len(files) == 1
        content = files[0].read_text(encoding="utf-8")
        assert "status: resolved" in content
        assert "resolution_type: fix" in content
        assert "Added null check before access" in content
        assert "**Accepted:** true" in content

    def test_workaround_shortcut_creates_resolved_post(self, tmp_path: Path) -> None:
        """--workaround creates a resolved post with resolution_type=workaround."""
        _setup_stack_project(tmp_path)
        result = self._invoke(
            tmp_path,
            [
                "stack",
                "post",
                "--title",
                "Timeout issue",
                "--tag",
                "perf",
                "--problem",
                "API times out",
                "--workaround",
                "Increased timeout to 30s",
            ],
        )
        assert result.exit_code == 0  # type: ignore[union-attr]
        stack_dir = tmp_path / ".lexibrary" / "stack"
        files = list(stack_dir.glob("ST-001-*.md"))
        assert len(files) == 1
        content = files[0].read_text(encoding="utf-8")
        assert "status: resolved" in content
        assert "resolution_type: workaround" in content
        assert "Increased timeout to 30s" in content
        assert "**Accepted:** true" in content

    def test_fix_and_workaround_mutual_exclusion(self, tmp_path: Path) -> None:
        """--fix and --workaround together produces error."""
        _setup_stack_project(tmp_path)
        result = self._invoke(
            tmp_path,
            [
                "stack",
                "post",
                "--title",
                "Bug",
                "--tag",
                "bug",
                "--fix",
                "Fixed it",
                "--workaround",
                "Worked around it",
            ],
        )
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "--fix and --workaround are mutually exclusive" in result.output  # type: ignore[union-attr]

    def test_fix_conflicts_with_finding(self, tmp_path: Path) -> None:
        """--fix conflicts with --finding."""
        _setup_stack_project(tmp_path)
        result = self._invoke(
            tmp_path,
            [
                "stack",
                "post",
                "--title",
                "Bug",
                "--tag",
                "bug",
                "--fix",
                "Fixed it",
                "--finding",
                "Also a finding",
            ],
        )
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "--fix conflicts with --finding" in result.output  # type: ignore[union-attr]

    def test_fix_conflicts_with_resolve(self, tmp_path: Path) -> None:
        """--fix conflicts with --resolve."""
        _setup_stack_project(tmp_path)
        result = self._invoke(
            tmp_path,
            [
                "stack",
                "post",
                "--title",
                "Bug",
                "--tag",
                "bug",
                "--fix",
                "Fixed it",
                "--resolve",
            ],
        )
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "--fix conflicts with --resolve" in result.output  # type: ignore[union-attr]

    def test_fix_conflicts_with_resolution_type(self, tmp_path: Path) -> None:
        """--fix conflicts with --resolution-type."""
        _setup_stack_project(tmp_path)
        result = self._invoke(
            tmp_path,
            [
                "stack",
                "post",
                "--title",
                "Bug",
                "--tag",
                "bug",
                "--fix",
                "Fixed it",
                "--resolution-type",
                "workaround",
            ],
        )
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "--fix conflicts with --resolution-type" in result.output  # type: ignore[union-attr]

    def test_workaround_conflicts_with_finding(self, tmp_path: Path) -> None:
        """--workaround conflicts with --finding."""
        _setup_stack_project(tmp_path)
        result = self._invoke(
            tmp_path,
            [
                "stack",
                "post",
                "--title",
                "Bug",
                "--tag",
                "bug",
                "--workaround",
                "Worked around",
                "--finding",
                "Also a finding",
            ],
        )
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "--workaround conflicts with --finding" in result.output  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Stack search command tests
# ---------------------------------------------------------------------------


class TestSearchTypeStack:
    """Tests for `lexi search --type stack` (replaces `lexi stack search`)."""

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
        result = self._invoke(tmp_path, ["search", "timezone", "--type", "stack"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Timezone bug" in result.output  # type: ignore[union-attr]
        assert "Auth issue" not in result.output  # type: ignore[union-attr]

    def test_search_with_tag_filter(self, tmp_path: Path) -> None:
        """Search with tag filter."""
        _setup_stack_project(tmp_path)
        _create_stack_post(tmp_path, post_id="ST-001", title="Bug one", tags=["auth"])
        _create_stack_post(tmp_path, post_id="ST-002", title="Bug two", tags=["performance"])
        result = self._invoke(tmp_path, ["search", "Bug", "--type", "stack", "--tag", "auth"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Bug one" in result.output  # type: ignore[union-attr]
        assert "Bug two" not in result.output  # type: ignore[union-attr]

    def test_search_no_results(self, tmp_path: Path) -> None:
        """Search with no matching posts shows no results message."""
        _setup_stack_project(tmp_path)
        result = self._invoke(tmp_path, ["search", "nonexistent", "--type", "stack"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "No results found" in result.output  # type: ignore[union-attr]

    def test_search_with_status_filter(self, tmp_path: Path) -> None:
        """Search filtered by status."""
        _setup_stack_project(tmp_path)
        _create_stack_post(tmp_path, post_id="ST-001", title="Open bug", status="open")
        _create_stack_post(tmp_path, post_id="ST-002", title="Resolved bug", status="resolved")
        result = self._invoke(tmp_path, ["search", "--type", "stack", "--status", "open"])
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
        result = self._invoke(tmp_path, ["search", "--type", "stack", "--scope", "src/models/"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Model bug" in result.output  # type: ignore[union-attr]
        assert "View bug" not in result.output  # type: ignore[union-attr]

    def test_search_no_project(self, tmp_path: Path) -> None:
        """Search without .lexibrary should fail."""
        result = self._invoke(tmp_path, ["search", "test", "--type", "stack"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "No .lexibrary/" in result.output  # type: ignore[union-attr]

    def test_search_with_resolution_type_filter(self, tmp_path: Path) -> None:
        """Search filtered by resolution-type returns only matching posts."""
        _setup_stack_project(tmp_path)
        _create_stack_post(
            tmp_path,
            post_id="ST-001",
            title="Workaround issue",
            status="resolved",
            resolution_type="workaround",
        )
        _create_stack_post(
            tmp_path,
            post_id="ST-002",
            title="Fixed issue",
            status="resolved",
            resolution_type="fix",
        )
        _create_stack_post(
            tmp_path,
            post_id="ST-003",
            title="Open issue",
            status="open",
        )
        result = self._invoke(
            tmp_path,
            ["search", "--type", "stack", "--resolution-type", "workaround"],
        )
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Workaround issue" in result.output  # type: ignore[union-attr]
        assert "Fixed issue" not in result.output  # type: ignore[union-attr]
        assert "Open issue" not in result.output  # type: ignore[union-attr]

    def test_list_all(self, tmp_path: Path) -> None:
        """List all stack posts (replaces `lexi stack list`)."""
        _setup_stack_project(tmp_path)
        _create_stack_post(tmp_path, post_id="ST-001", title="Bug one")
        _create_stack_post(tmp_path, post_id="ST-002", title="Bug two")
        result = self._invoke(tmp_path, ["search", "--type", "stack"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Bug one" in result.output  # type: ignore[union-attr]
        assert "Bug two" in result.output  # type: ignore[union-attr]

    def test_list_filtered_by_status(self, tmp_path: Path) -> None:
        """List posts filtered by status."""
        _setup_stack_project(tmp_path)
        _create_stack_post(tmp_path, post_id="ST-001", title="Open bug", status="open")
        _create_stack_post(tmp_path, post_id="ST-002", title="Resolved bug", status="resolved")
        result = self._invoke(tmp_path, ["search", "--type", "stack", "--status", "open"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Open bug" in result.output  # type: ignore[union-attr]
        assert "Resolved bug" not in result.output  # type: ignore[union-attr]

    def test_list_filtered_by_tag(self, tmp_path: Path) -> None:
        """List posts filtered by tag."""
        _setup_stack_project(tmp_path)
        _create_stack_post(tmp_path, post_id="ST-001", title="Auth issue", tags=["auth"])
        _create_stack_post(tmp_path, post_id="ST-002", title="Perf issue", tags=["performance"])
        result = self._invoke(tmp_path, ["search", "--type", "stack", "--tag", "auth"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Auth issue" in result.output  # type: ignore[union-attr]
        assert "Perf issue" not in result.output  # type: ignore[union-attr]

    def test_list_empty(self, tmp_path: Path) -> None:
        """List when no posts exist."""
        _setup_stack_project(tmp_path)
        result = self._invoke(tmp_path, ["search", "--type", "stack"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "No results found" in result.output  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Stack finding command tests
# ---------------------------------------------------------------------------


class TestStackFindingCommand:
    """Tests for the `lexi stack finding` command."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexi_app, args)
        finally:
            os.chdir(old_cwd)

    def test_add_finding(self, tmp_path: Path) -> None:
        """Add a finding to an existing post."""
        _setup_stack_project(tmp_path)
        _create_stack_post(tmp_path, post_id="ST-001", title="Bug")
        result = self._invoke(tmp_path, ["stack", "finding", "ST-001", "--body", "Try restarting."])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Added finding F1" in result.output  # type: ignore[union-attr]

    def test_add_finding_nonexistent_post(self, tmp_path: Path) -> None:
        """Finding on nonexistent post should fail."""
        _setup_stack_project(tmp_path)
        result = self._invoke(tmp_path, ["stack", "finding", "ST-999", "--body", "Solution"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "Post not found" in result.output  # type: ignore[union-attr]

    def test_add_finding_no_project(self, tmp_path: Path) -> None:
        """Finding without .lexibrary should fail."""
        result = self._invoke(tmp_path, ["stack", "finding", "ST-001", "--body", "Solution"])
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
        """Downvote a finding with required comment."""
        _setup_stack_project(tmp_path)
        _create_stack_post_with_finding(tmp_path, post_id="ST-001")
        result = self._invoke(
            tmp_path,
            ["stack", "vote", "ST-001", "down", "--finding", "1", "--comment", "Bad approach"],
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

    def test_accept_finding(self, tmp_path: Path) -> None:
        """Accept a finding and set status to resolved."""
        _setup_stack_project(tmp_path)
        _create_stack_post_with_finding(tmp_path, post_id="ST-001")
        result = self._invoke(tmp_path, ["stack", "accept", "ST-001", "--finding", "1"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Accepted F1" in result.output  # type: ignore[union-attr]
        assert "resolved" in result.output  # type: ignore[union-attr]

    def test_accept_nonexistent_post(self, tmp_path: Path) -> None:
        """Accept on nonexistent post should fail."""
        _setup_stack_project(tmp_path)
        result = self._invoke(tmp_path, ["stack", "accept", "ST-999", "--finding", "1"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "Post not found" in result.output  # type: ignore[union-attr]

    def test_accept_nonexistent_finding(self, tmp_path: Path) -> None:
        """Accept nonexistent finding should fail."""
        _setup_stack_project(tmp_path)
        _create_stack_post_with_finding(tmp_path, post_id="ST-001")
        result = self._invoke(tmp_path, ["stack", "accept", "ST-001", "--finding", "99"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "Error" in result.output  # type: ignore[union-attr]

    def test_accept_with_resolution_type(self, tmp_path: Path) -> None:
        """Accept a finding with --resolution-type sets the resolution type."""
        _setup_stack_project(tmp_path)
        _create_stack_post_with_finding(tmp_path, post_id="ST-001")
        result = self._invoke(
            tmp_path,
            ["stack", "accept", "ST-001", "--finding", "1", "--resolution-type", "fix"],
        )
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Accepted F1" in result.output  # type: ignore[union-attr]
        # Verify the resolution type was set in the file
        from lexibrary.stack.parser import parse_stack_post  # noqa: PLC0415

        stack_dir = tmp_path / ".lexibrary" / "stack"
        files = list(stack_dir.glob("ST-001-*.md"))
        assert len(files) == 1
        post = parse_stack_post(files[0])
        assert post is not None
        assert post.frontmatter.resolution_type == "fix"


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

    def test_view_post_with_finding(self, tmp_path: Path) -> None:
        """View a post with findings shows finding details."""
        _setup_stack_project(tmp_path)
        _create_stack_post_with_finding(
            tmp_path, post_id="ST-001", title="Bug", finding_body="Fix it!"
        )
        result = self._invoke(tmp_path, ["stack", "view", "ST-001"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "F1" in result.output  # type: ignore[union-attr]
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

    def test_search_no_args_lists_all(self, tmp_path: Path) -> None:
        """Search with no args lists all non-deprecated, non-stale artifacts."""
        project = _setup_unified_search_project(tmp_path)
        result = self._invoke(project, ["search"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Authentication" in output
        assert "Rate Limiting" in output
        assert "src/auth.py" in output
        assert "Login timeout bug" in output

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
# Type-specific flag validation tests (task 4.4)
# ---------------------------------------------------------------------------


class TestSearchFlagValidation:
    """Tests for type-specific flag validation on `lexi search`."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexi_app, args)
        finally:
            os.chdir(old_cwd)

    def test_concept_flag_infers_stack_type(self, tmp_path: Path) -> None:
        """--concept without --type auto-infers --type stack."""
        _setup_stack_project(tmp_path)
        _create_stack_post(
            tmp_path,
            post_id="ST-001",
            title="Auth bug",
            refs_concepts=["auth"],
        )
        result = self._invoke(tmp_path, ["search", "--concept", "auth"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Auth bug" in result.output  # type: ignore[union-attr]

    def test_concept_flag_conflicts_with_non_stack_type(self, tmp_path: Path) -> None:
        """--concept with --type concept should error."""
        _setup_project(tmp_path)
        result = self._invoke(tmp_path, ["search", "--type", "concept", "--concept", "auth"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "--concept" in result.output  # type: ignore[union-attr]
        assert "stack" in result.output  # type: ignore[union-attr]

    def test_resolution_type_flag_infers_stack(self, tmp_path: Path) -> None:
        """--resolution-type without --type auto-infers --type stack."""
        _setup_stack_project(tmp_path)
        _create_stack_post(
            tmp_path,
            post_id="ST-001",
            title="Fixed bug",
            status="resolved",
            resolution_type="fix",
        )
        result = self._invoke(tmp_path, ["search", "--resolution-type", "fix"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Fixed bug" in result.output  # type: ignore[union-attr]

    def test_include_stale_infers_stack(self, tmp_path: Path) -> None:
        """--include-stale without --type auto-infers --type stack."""
        _setup_stack_project(tmp_path)
        _create_stack_post(
            tmp_path,
            post_id="ST-001",
            title="Stale bug",
            status="stale",
            stale_at="2026-01-20T00:00:00+00:00",
        )
        result = self._invoke(tmp_path, ["search", "--include-stale"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Stale bug" in result.output  # type: ignore[union-attr]

    def test_invalid_type_value(self, tmp_path: Path) -> None:
        """Invalid --type value shows clear error listing all five valid types."""
        _setup_project(tmp_path)
        result = self._invoke(tmp_path, ["search", "--type", "foobar"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "Invalid --type" in result.output  # type: ignore[union-attr]
        assert "concept" in result.output  # type: ignore[union-attr]
        assert "playbook" in result.output  # type: ignore[union-attr]

    def test_type_playbook_accepted(self, tmp_path: Path) -> None:
        """--type playbook is accepted without error."""
        lib = tmp_path / ".lexibrary"
        lib.mkdir()
        (lib / "config.yaml").write_text("")
        (lib / "playbooks").mkdir()
        result = self._invoke(tmp_path, ["search", "--type", "playbook"])
        # Should not fail with "Invalid --type" — exit 0 with no results is fine
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Invalid --type" not in result.output  # type: ignore[union-attr]


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
    design_dir = tmp_path / ".lexibrary" / "designs" / "src"
    design_dir.mkdir(parents=True, exist_ok=True)
    design_content = f"""---
description: Main module
id: DS-001
updated_by: archivist
status: active
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
        "---\ntitle: Broken\nid: CN-001\n---\n\nMissing aliases, tags, status.\n",
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

    design_dir = tmp_path / ".lexibrary" / "designs" / "src"
    design_dir.mkdir(parents=True, exist_ok=True)
    design_content = """---
description: Main module
id: DS-001
updated_by: archivist
status: active
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
        designs_src = project / ".lexibrary" / "designs" / "src"
        designs_src.mkdir(parents=True, exist_ok=True)
        (designs_src / ".aindex").write_text(src_aindex, encoding="utf-8")
        root_aindex = (
            f"# ./\n\nRoot\n\n## Child Map\n\n"
            f"| Name | Type | Description |\n| --- | --- | --- |\n"
            f"| `src/` | dir | Source |\n\n## Local Conventions\n\n(none)\n\n"
            f'<!-- lexibrary:meta source="." source_hash="abc"'
            f' generated="{now}" -->\n'
        )
        (project / ".lexibrary" / "designs" / ".aindex").write_text(root_aindex, encoding="utf-8")
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
        assert "lexi orient" in rules

    def test_core_rules_includes_before_editing(self) -> None:
        """get_core_rules() includes 'Before Reading or Editing Files' instructions."""
        from lexibrary.init.rules.base import get_core_rules

        rules = get_core_rules()
        assert "Before Reading or Editing Files" in rules
        assert "lexi lookup" in rules

    def test_core_rules_includes_after_editing(self) -> None:
        """get_core_rules() includes 'After Editing Files' with lexi validate."""
        from lexibrary.init.rules.base import get_core_rules

        rules = get_core_rules()
        assert "After Editing" in rules
        assert "lexi validate" in rules

    def test_orient_skill_references_lexi_orient(self) -> None:
        """get_orient_skill_content() references 'lexi orient' as a single command."""
        from lexibrary.init.rules.base import get_orient_skill_content

        content = get_orient_skill_content()
        assert "lexi orient" in content
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
        # Verify the file exists in the mirror tree (designs/ prefix)
        iwh_file = tmp_path / ".lexibrary" / "designs" / "src" / ".iwh"
        assert iwh_file.exists()
        content = iwh_file.read_text(encoding="utf-8")
        assert "test signal" in content
        assert "incomplete" in content

    def test_iwh_write_default_scope_incomplete(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_iwh_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(lexi_app, ["iwh", "write", "src", "--body", "wip"])
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
        assert result.exit_code == 2
        assert "disabled" in result.output

    def test_iwh_write_project_root_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_iwh_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(lexi_app, ["iwh", "write", "--body", "root signal"])
        assert result.exit_code == 0
        # Project root IWH → .lexibrary/designs/.iwh
        iwh_file = tmp_path / ".lexibrary" / "designs" / ".iwh"
        assert iwh_file.exists()

    def test_iwh_read_consumes_signal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from lexibrary.iwh import write_iwh  # noqa: PLC0415

        _setup_iwh_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        # Write a signal at the mirror path for src/ (designs/ prefix)
        (tmp_path / ".lexibrary" / "designs" / "src").mkdir(parents=True, exist_ok=True)
        iwh_dir = tmp_path / ".lexibrary" / "designs" / "src"
        write_iwh(iwh_dir, author="agent", scope="incomplete", body="wip")
        result = runner.invoke(lexi_app, ["iwh", "read", "src"])
        assert result.exit_code == 0
        assert "INCOMPLETE" in result.output
        assert "consumed" in result.output.lower()
        # File should be deleted
        assert not (tmp_path / ".lexibrary" / "designs" / "src" / ".iwh").exists()

    def test_iwh_read_peek_preserves_signal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from lexibrary.iwh import write_iwh  # noqa: PLC0415

        _setup_iwh_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".lexibrary" / "designs" / "src").mkdir(parents=True, exist_ok=True)
        iwh_dir = tmp_path / ".lexibrary" / "designs" / "src"
        write_iwh(iwh_dir, author="agent", scope="warning", body="note")
        result = runner.invoke(lexi_app, ["iwh", "read", "src", "--peek"])
        assert result.exit_code == 0
        assert "WARNING" in result.output
        assert "consumed" not in result.output.lower()
        # File should still exist
        assert (tmp_path / ".lexibrary" / "designs" / "src" / ".iwh").exists()

    def test_iwh_read_missing_shows_message(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_iwh_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(lexi_app, ["iwh", "read", "src"])
        assert result.exit_code == 0
        assert "No IWH signal found" in result.output

    def test_iwh_list_shows_table(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from lexibrary.iwh import write_iwh  # noqa: PLC0415

        _setup_iwh_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".lexibrary" / "src").mkdir(parents=True, exist_ok=True)
        write_iwh(tmp_path / ".lexibrary" / "src", author="agent", scope="blocked", body="stuck")
        write_iwh(tmp_path / ".lexibrary", author="agent", scope="incomplete", body="root wip")
        result = runner.invoke(lexi_app, ["iwh", "list"])
        assert result.exit_code == 0
        assert "2 signal(s)" in result.output

    def test_iwh_list_empty_project(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
        assert result.exit_code == 2
        assert "disabled" in result.output


# ---------------------------------------------------------------------------
# Design update command tests
# ---------------------------------------------------------------------------


class TestDesignUpdateCommand:
    """Tests for the `lexi design update` command (pipeline-based)."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexi_app, args)
        finally:
            os.chdir(old_cwd)

    def test_skip_decision_renders_warning(self, tmp_path: Path) -> None:
        """When check_design_update returns skip, a warning is printed."""
        from unittest.mock import patch  # noqa: PLC0415

        from lexibrary.services.design import DesignUpdateDecision  # noqa: PLC0415

        _setup_project(tmp_path)
        source = tmp_path / "src" / "main.py"
        skip_decision = DesignUpdateDecision(
            action="skip",
            reason="Design file is up to date",
            skip_code="up_to_date",
        )
        with patch(
            "lexibrary.services.design.check_design_update", return_value=skip_decision
        ):
            result = self._invoke(tmp_path, ["design", "update", str(source)])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Skipped" in result.output  # type: ignore[union-attr]

    def test_generate_success(self, tmp_path: Path) -> None:
        """When pipeline succeeds, a success message is printed."""
        from unittest.mock import AsyncMock, MagicMock, patch  # noqa: PLC0415

        from lexibrary.archivist.change_checker import ChangeLevel  # noqa: PLC0415
        from lexibrary.archivist.pipeline import FileResult  # noqa: PLC0415
        from lexibrary.services.design import DesignUpdateDecision  # noqa: PLC0415

        _setup_project(tmp_path)
        source = tmp_path / "src" / "main.py"
        gen_decision = DesignUpdateDecision(action="generate", reason="No design file exists")
        file_result = FileResult(change=ChangeLevel.NEW_FILE)

        with (
            patch(
                "lexibrary.services.design.check_design_update",
                return_value=gen_decision,
            ),
            patch(
                "lexibrary.llm.client_registry.build_client_registry",
                return_value=MagicMock(),
            ),
            patch(
                "lexibrary.archivist.pipeline.update_file",
                new_callable=AsyncMock,
                return_value=file_result,
            ),
            patch(
                "lexibrary.archivist.service.ArchivistService",
                return_value=MagicMock(),
            ),
        ):
            result = self._invoke(tmp_path, ["design", "update", str(source)])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Updated design file" in result.output  # type: ignore[union-attr]
        assert "new_file" in result.output  # type: ignore[union-attr]

    def test_generate_failure(self, tmp_path: Path) -> None:
        """When pipeline returns failure, error is shown and exit code is 1."""
        from unittest.mock import AsyncMock, MagicMock, patch  # noqa: PLC0415

        from lexibrary.archivist.change_checker import ChangeLevel  # noqa: PLC0415
        from lexibrary.archivist.pipeline import FileResult  # noqa: PLC0415
        from lexibrary.services.design import DesignUpdateDecision  # noqa: PLC0415

        _setup_project(tmp_path)
        source = tmp_path / "src" / "main.py"
        gen_decision = DesignUpdateDecision(action="generate", reason="Stale")
        file_result = FileResult(
            change=ChangeLevel.UNCHANGED,
            failed=True,
            failure_reason="LLM timeout",
        )

        with (
            patch(
                "lexibrary.services.design.check_design_update",
                return_value=gen_decision,
            ),
            patch(
                "lexibrary.llm.client_registry.build_client_registry",
                return_value=MagicMock(),
            ),
            patch(
                "lexibrary.archivist.pipeline.update_file",
                new_callable=AsyncMock,
                return_value=file_result,
            ),
            patch(
                "lexibrary.archivist.service.ArchivistService",
                return_value=MagicMock(),
            ),
        ):
            result = self._invoke(tmp_path, ["design", "update", str(source)])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "Failed" in result.output  # type: ignore[union-attr]
        assert "LLM timeout" in result.output  # type: ignore[union-attr]

    def test_skeleton_fallback_warning(self, tmp_path: Path) -> None:
        """When pipeline falls back to skeleton, a warning with --unlimited suggestion is shown."""
        from unittest.mock import AsyncMock, MagicMock, patch  # noqa: PLC0415

        from lexibrary.archivist.change_checker import ChangeLevel  # noqa: PLC0415
        from lexibrary.archivist.pipeline import FileResult  # noqa: PLC0415
        from lexibrary.services.design import DesignUpdateDecision  # noqa: PLC0415

        _setup_project(tmp_path)
        source = tmp_path / "src" / "main.py"
        gen_decision = DesignUpdateDecision(action="generate", reason="New file")
        file_result = FileResult(
            change=ChangeLevel.SKELETON_ONLY,
            skeleton=True,
        )

        with (
            patch(
                "lexibrary.services.design.check_design_update",
                return_value=gen_decision,
            ),
            patch(
                "lexibrary.llm.client_registry.build_client_registry",
                return_value=MagicMock(),
            ),
            patch(
                "lexibrary.archivist.pipeline.update_file",
                new_callable=AsyncMock,
                return_value=file_result,
            ),
            patch(
                "lexibrary.archivist.service.ArchivistService",
                return_value=MagicMock(),
            ),
        ):
            result = self._invoke(tmp_path, ["design", "update", str(source)])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "skeleton" in result.output  # type: ignore[union-attr]
        assert "--unlimited" in result.output  # type: ignore[union-attr]

    def test_asyncio_exception_handled(self, tmp_path: Path) -> None:
        """When asyncio.run raises an exception, error message is shown and exit code is 1."""
        from unittest.mock import MagicMock, patch  # noqa: PLC0415

        from lexibrary.services.design import DesignUpdateDecision  # noqa: PLC0415

        _setup_project(tmp_path)
        source = tmp_path / "src" / "main.py"
        gen_decision = DesignUpdateDecision(action="generate", reason="New file")

        with (
            patch(
                "lexibrary.services.design.check_design_update",
                return_value=gen_decision,
            ),
            patch(
                "lexibrary.llm.client_registry.build_client_registry",
                return_value=MagicMock(),
            ),
            patch(
                "lexibrary.archivist.pipeline.update_file",
                side_effect=RuntimeError("Network error"),
            ),
            patch(
                "lexibrary.archivist.service.ArchivistService",
                return_value=MagicMock(),
            ),
        ):
            result = self._invoke(tmp_path, ["design", "update", str(source)])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "Design update failed" in result.output  # type: ignore[union-attr]
        assert "Network error" in result.output  # type: ignore[union-attr]

    def test_force_flag_passed_to_service(self, tmp_path: Path) -> None:
        """The --force flag is passed through to check_design_update and update_file."""
        from unittest.mock import AsyncMock, MagicMock, patch  # noqa: PLC0415

        from lexibrary.archivist.change_checker import ChangeLevel  # noqa: PLC0415
        from lexibrary.archivist.pipeline import FileResult  # noqa: PLC0415
        from lexibrary.services.design import DesignUpdateDecision  # noqa: PLC0415

        _setup_project(tmp_path)
        source = tmp_path / "src" / "main.py"
        gen_decision = DesignUpdateDecision(action="generate", reason="Force requested")
        file_result = FileResult(change=ChangeLevel.NEW_FILE)

        mock_check = MagicMock(return_value=gen_decision)
        mock_update = AsyncMock(return_value=file_result)

        with (
            patch("lexibrary.services.design.check_design_update", mock_check),
            patch(
                "lexibrary.llm.client_registry.build_client_registry",
                return_value=MagicMock(),
            ),
            patch("lexibrary.archivist.pipeline.update_file", mock_update),
            patch(
                "lexibrary.archivist.service.ArchivistService",
                return_value=MagicMock(),
            ),
        ):
            result = self._invoke(
                tmp_path, ["design", "update", str(source), "--force"]
            )
        assert result.exit_code == 0  # type: ignore[union-attr]
        # Verify force=True was passed to check_design_update
        assert mock_check.call_args[1]["force"] is True
        # Verify force=True was passed to update_file
        assert mock_update.call_args[1]["force"] is True

    def test_unlimited_flag_passed_through(self, tmp_path: Path) -> None:
        """The --unlimited flag is passed to build_client_registry and update_file."""
        from unittest.mock import AsyncMock, MagicMock, patch  # noqa: PLC0415

        from lexibrary.archivist.change_checker import ChangeLevel  # noqa: PLC0415
        from lexibrary.archivist.pipeline import FileResult  # noqa: PLC0415
        from lexibrary.services.design import DesignUpdateDecision  # noqa: PLC0415

        _setup_project(tmp_path)
        source = tmp_path / "src" / "main.py"
        gen_decision = DesignUpdateDecision(action="generate", reason="New file")
        file_result = FileResult(change=ChangeLevel.NEW_FILE)

        mock_registry = MagicMock(return_value=MagicMock())
        mock_update = AsyncMock(return_value=file_result)

        with (
            patch(
                "lexibrary.services.design.check_design_update",
                return_value=gen_decision,
            ),
            patch("lexibrary.llm.client_registry.build_client_registry", mock_registry),
            patch("lexibrary.archivist.pipeline.update_file", mock_update),
            patch(
                "lexibrary.archivist.service.ArchivistService",
                return_value=MagicMock(),
            ),
        ):
            result = self._invoke(
                tmp_path, ["design", "update", str(source), "--unlimited"]
            )
        assert result.exit_code == 0  # type: ignore[union-attr]
        # Verify unlimited=True was passed to build_client_registry
        assert mock_registry.call_args[1]["unlimited"] is True
        # Verify unlimited=True was passed to update_file
        assert mock_update.call_args[1]["unlimited"] is True

    def test_file_outside_scope(self, tmp_path: Path) -> None:
        """File outside scope_root should fail."""
        # Set up project with scope_root restricted to src/
        (tmp_path / ".lexibrary").mkdir()
        (tmp_path / ".lexibrary" / "config.yaml").write_text("scope_root: src\n")
        (tmp_path / "src").mkdir()
        # Create a file in project root but outside scope_root
        outside = tmp_path / "outside.py"
        outside.write_text("pass\n")
        result = self._invoke(tmp_path, ["design", "update", str(outside)])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "outside" in result.output.lower()  # type: ignore[union-attr]

    def test_no_project(self, tmp_path: Path) -> None:
        """Running without .lexibrary should fail."""
        source = tmp_path / "main.py"
        source.write_text("pass\n")
        result = self._invoke(tmp_path, ["design", "update", str(source)])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "No .lexibrary/" in result.output  # type: ignore[union-attr]

    def test_force_short_flag(self, tmp_path: Path) -> None:
        """The -f short flag works for --force."""
        from unittest.mock import MagicMock, patch  # noqa: PLC0415

        from lexibrary.services.design import DesignUpdateDecision  # noqa: PLC0415

        _setup_project(tmp_path)
        source = tmp_path / "src" / "main.py"
        skip_decision = DesignUpdateDecision(
            action="skip",
            reason="Design file is up to date",
            skip_code="up_to_date",
        )
        mock_check = MagicMock(return_value=skip_decision)
        with patch("lexibrary.services.design.check_design_update", mock_check):
            result = self._invoke(tmp_path, ["design", "update", str(source), "-f"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        # Verify force=True was passed
        assert mock_check.call_args[1]["force"] is True

    def test_concepts_loaded_and_passed(self, tmp_path: Path) -> None:
        """Available concepts are loaded from ConceptIndex and passed to update_file."""
        from unittest.mock import AsyncMock, MagicMock, patch  # noqa: PLC0415

        from lexibrary.archivist.change_checker import ChangeLevel  # noqa: PLC0415
        from lexibrary.archivist.pipeline import FileResult  # noqa: PLC0415
        from lexibrary.services.design import DesignUpdateDecision  # noqa: PLC0415

        _setup_project(tmp_path)
        source = tmp_path / "src" / "main.py"
        gen_decision = DesignUpdateDecision(action="generate", reason="New file")
        file_result = FileResult(change=ChangeLevel.NEW_FILE)

        mock_update = AsyncMock(return_value=file_result)
        # Create a mock ConceptIndex that returns concept names
        mock_concept_index = MagicMock()
        mock_concept_index.names.return_value = ["Error Handling", "Pipeline"]
        mock_concept_cls = MagicMock()
        mock_concept_cls.load.return_value = mock_concept_index

        with (
            patch(
                "lexibrary.services.design.check_design_update",
                return_value=gen_decision,
            ),
            patch(
                "lexibrary.llm.client_registry.build_client_registry",
                return_value=MagicMock(),
            ),
            patch("lexibrary.archivist.pipeline.update_file", mock_update),
            patch(
                "lexibrary.archivist.service.ArchivistService",
                return_value=MagicMock(),
            ),
            patch("lexibrary.wiki.index.ConceptIndex", mock_concept_cls),
        ):
            result = self._invoke(tmp_path, ["design", "update", str(source)])
        assert result.exit_code == 0  # type: ignore[union-attr]
        # Verify concepts were passed to update_file
        passed_concepts = mock_update.call_args[0][4]
        assert passed_concepts == ["Error Handling", "Pipeline"]

    def test_no_concepts_passes_none(self, tmp_path: Path) -> None:
        """When ConceptIndex returns empty names, None is passed to update_file."""
        from unittest.mock import AsyncMock, MagicMock, patch  # noqa: PLC0415

        from lexibrary.archivist.change_checker import ChangeLevel  # noqa: PLC0415
        from lexibrary.archivist.pipeline import FileResult  # noqa: PLC0415
        from lexibrary.services.design import DesignUpdateDecision  # noqa: PLC0415

        _setup_project(tmp_path)
        source = tmp_path / "src" / "main.py"
        gen_decision = DesignUpdateDecision(action="generate", reason="New file")
        file_result = FileResult(change=ChangeLevel.NEW_FILE)

        mock_update = AsyncMock(return_value=file_result)
        # Create a mock ConceptIndex with no concepts
        mock_concept_index = MagicMock()
        mock_concept_index.names.return_value = []
        mock_concept_cls = MagicMock()
        mock_concept_cls.load.return_value = mock_concept_index

        with (
            patch(
                "lexibrary.services.design.check_design_update",
                return_value=gen_decision,
            ),
            patch(
                "lexibrary.llm.client_registry.build_client_registry",
                return_value=MagicMock(),
            ),
            patch("lexibrary.archivist.pipeline.update_file", mock_update),
            patch(
                "lexibrary.archivist.service.ArchivistService",
                return_value=MagicMock(),
            ),
            patch("lexibrary.wiki.index.ConceptIndex", mock_concept_cls),
        ):
            result = self._invoke(tmp_path, ["design", "update", str(source)])
        assert result.exit_code == 0  # type: ignore[union-attr]
        # Verify None was passed (empty list -> None via `or None`)
        passed_concepts = mock_update.call_args[0][4]
        assert passed_concepts is None


# ---------------------------------------------------------------------------
# Design comment command tests
# ---------------------------------------------------------------------------


class TestDesignCommentCommand:
    """Tests for the `lexi design comment` command."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexi_app, args)
        finally:
            os.chdir(old_cwd)

    def test_success_case(self, tmp_path: Path) -> None:
        """Successfully adds a comment for a source file with an existing design file."""
        _setup_project(tmp_path)
        source = tmp_path / "src" / "main.py"
        source_content = "print('hello')\n"
        _create_design_file(tmp_path, "src/main.py", source_content)

        result = self._invoke(
            tmp_path,
            ["design", "comment", str(source), "--body", "test comment"],
        )
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Comment added" in result.output  # type: ignore[union-attr]
        assert "src/main.py" in result.output  # type: ignore[union-attr]

        # Verify comment was actually written
        comment_path = tmp_path / ".lexibrary" / "designs" / "src" / "main.py.comments.yaml"
        assert comment_path.exists()

    def test_missing_design_file_error(self, tmp_path: Path) -> None:
        """Error when design file does not exist for the source file."""
        _setup_project(tmp_path)
        source = tmp_path / "src" / "main.py"
        # Do NOT create a design file

        result = self._invoke(
            tmp_path,
            ["design", "comment", str(source), "--body", "test comment"],
        )
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "No design file" in result.output  # type: ignore[union-attr]

    def test_no_project_error(self, tmp_path: Path) -> None:
        """Error when no .lexibrary directory exists."""
        source = tmp_path / "main.py"
        source.write_text("pass\n")

        result = self._invoke(
            tmp_path,
            ["design", "comment", str(source), "--body", "test comment"],
        )
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "No .lexibrary/" in result.output  # type: ignore[union-attr]

    def test_short_flag(self, tmp_path: Path) -> None:
        """The -b short flag works for --body."""
        _setup_project(tmp_path)
        source = tmp_path / "src" / "main.py"
        source_content = "print('hello')\n"
        _create_design_file(tmp_path, "src/main.py", source_content)

        result = self._invoke(
            tmp_path,
            ["design", "comment", str(source), "-b", "short flag comment"],
        )
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Comment added" in result.output  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Stack mark-outdated command tests
# ---------------------------------------------------------------------------


class TestStackMarkOutdatedCommand:
    """Tests for the `lexi stack mark-outdated` command."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexi_app, args)
        finally:
            os.chdir(old_cwd)

    def test_mark_post_outdated(self, tmp_path: Path) -> None:
        """Mark an existing post as outdated."""
        _setup_stack_project(tmp_path)
        _create_stack_post(tmp_path, post_id="ST-001", title="Old bug")
        result = self._invoke(tmp_path, ["stack", "mark-outdated", "ST-001"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "outdated" in result.output  # type: ignore[union-attr]
        # Verify the post file was updated
        post_path = list((tmp_path / ".lexibrary" / "stack").glob("ST-001-*.md"))[0]
        content = post_path.read_text(encoding="utf-8")
        assert "status: outdated" in content

    def test_mark_nonexistent_post_outdated(self, tmp_path: Path) -> None:
        """Marking a nonexistent post should fail."""
        _setup_stack_project(tmp_path)
        result = self._invoke(tmp_path, ["stack", "mark-outdated", "ST-999"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "not found" in result.output.lower()  # type: ignore[union-attr]

    def test_mark_outdated_no_project(self, tmp_path: Path) -> None:
        """Running without .lexibrary should fail."""
        result = self._invoke(tmp_path, ["stack", "mark-outdated", "ST-001"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "No .lexibrary/" in result.output  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Stack duplicate command tests
# ---------------------------------------------------------------------------


class TestStackDuplicateCommand:
    """Tests for the `lexi stack duplicate` command."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexi_app, args)
        finally:
            os.chdir(old_cwd)

    def test_mark_post_as_duplicate(self, tmp_path: Path) -> None:
        """Mark a post as duplicate of another."""
        _setup_stack_project(tmp_path)
        _create_stack_post(tmp_path, post_id="ST-001", title="Original bug")
        _create_stack_post(tmp_path, post_id="ST-003", title="Duplicate bug")
        result = self._invoke(tmp_path, ["stack", "duplicate", "ST-003", "--of", "ST-001"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "duplicate" in result.output.lower()  # type: ignore[union-attr]
        assert "ST-001" in result.output  # type: ignore[union-attr]
        # Verify the post file was updated
        post_path = list((tmp_path / ".lexibrary" / "stack").glob("ST-003-*.md"))[0]
        content = post_path.read_text(encoding="utf-8")
        assert "status: duplicate" in content
        assert "duplicate_of: ST-001" in content

    def test_duplicate_nonexistent_post(self, tmp_path: Path) -> None:
        """Duplicating a nonexistent post should fail."""
        _setup_stack_project(tmp_path)
        result = self._invoke(tmp_path, ["stack", "duplicate", "ST-999", "--of", "ST-001"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "not found" in result.output.lower()  # type: ignore[union-attr]

    def test_duplicate_without_of_flag(self, tmp_path: Path) -> None:
        """Duplicate without --of flag should fail."""
        _setup_stack_project(tmp_path)
        _create_stack_post(tmp_path, post_id="ST-003", title="Some bug")
        result = self._invoke(tmp_path, ["stack", "duplicate", "ST-003"])
        assert result.exit_code != 0  # type: ignore[union-attr]

    def test_duplicate_no_project(self, tmp_path: Path) -> None:
        """Running without .lexibrary should fail."""
        result = self._invoke(tmp_path, ["stack", "duplicate", "ST-001", "--of", "ST-002"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "No .lexibrary/" in result.output  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Stack comment command tests
# ---------------------------------------------------------------------------


class TestStackCommentCommand:
    """Tests for the `lexi stack comment` command."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexi_app, args)
        finally:
            os.chdir(old_cwd)

    def test_add_comment_to_existing_post(self, tmp_path: Path) -> None:
        """Add comment to existing post prints confirmation with count."""
        _setup_stack_project(tmp_path)
        _create_stack_post(tmp_path, post_id="ST-001", title="Config bug")
        result = self._invoke(
            tmp_path,
            ["stack", "comment", "ST-001", "--body", "This still happens after v2 migration"],
        )
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Comment added" in result.output  # type: ignore[union-attr]
        assert "ST-001" in result.output  # type: ignore[union-attr]
        assert "1 comment total" in result.output  # type: ignore[union-attr]

    def test_add_second_comment(self, tmp_path: Path) -> None:
        """Adding a second comment shows correct count."""
        _setup_stack_project(tmp_path)
        _create_stack_post(tmp_path, post_id="ST-001", title="Config bug")
        self._invoke(
            tmp_path,
            ["stack", "comment", "ST-001", "--body", "First comment"],
        )
        result = self._invoke(
            tmp_path,
            ["stack", "comment", "ST-001", "--body", "Second comment"],
        )
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "2 comments total" in result.output  # type: ignore[union-attr]

    def test_comment_nonexistent_post(self, tmp_path: Path) -> None:
        """Commenting on a nonexistent post fails."""
        _setup_stack_project(tmp_path)
        result = self._invoke(
            tmp_path,
            ["stack", "comment", "ST-999", "--body", "test comment"],
        )
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "not found" in result.output.lower()  # type: ignore[union-attr]

    def test_comment_without_body_fails(self, tmp_path: Path) -> None:
        """Comment without --body flag fails."""
        _setup_stack_project(tmp_path)
        _create_stack_post(tmp_path, post_id="ST-001", title="Config bug")
        result = self._invoke(tmp_path, ["stack", "comment", "ST-001"])
        assert result.exit_code != 0  # type: ignore[union-attr]

    def test_comment_no_project(self, tmp_path: Path) -> None:
        """Commenting without .lexibrary should fail."""
        result = self._invoke(
            tmp_path,
            ["stack", "comment", "ST-001", "--body", "test"],
        )
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "No .lexibrary/" in result.output  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Stack stale command tests
# ---------------------------------------------------------------------------


class TestStackStaleCommand:
    """Tests for the `lexi stack stale` command."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexi_app, args)
        finally:
            os.chdir(old_cwd)

    def test_mark_resolved_post_as_stale(self, tmp_path: Path) -> None:
        """Mark a resolved post as stale shows confirmation with timestamp."""
        _setup_stack_project(tmp_path)
        _create_stack_post(tmp_path, post_id="ST-001", title="Old bug", status="resolved")
        result = self._invoke(tmp_path, ["stack", "stale", "ST-001"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "stale" in result.output.lower()  # type: ignore[union-attr]
        assert "stale_at" in result.output  # type: ignore[union-attr]
        # Verify the post file was updated
        post_path = list((tmp_path / ".lexibrary" / "stack").glob("ST-001-*.md"))[0]
        content = post_path.read_text(encoding="utf-8")
        assert "status: stale" in content

    def test_mark_non_resolved_post_fails(self, tmp_path: Path) -> None:
        """Marking an open post as stale fails with error."""
        _setup_stack_project(tmp_path)
        _create_stack_post(tmp_path, post_id="ST-001", title="Open bug", status="open")
        result = self._invoke(tmp_path, ["stack", "stale", "ST-001"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "resolved" in result.output.lower()  # type: ignore[union-attr]

    def test_mark_nonexistent_post_stale_fails(self, tmp_path: Path) -> None:
        """Marking a nonexistent post as stale fails."""
        _setup_stack_project(tmp_path)
        result = self._invoke(tmp_path, ["stack", "stale", "ST-999"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "not found" in result.output.lower()  # type: ignore[union-attr]

    def test_stale_no_project(self, tmp_path: Path) -> None:
        """Running without .lexibrary should fail."""
        result = self._invoke(tmp_path, ["stack", "stale", "ST-001"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "No .lexibrary/" in result.output  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Stack unstale command tests
# ---------------------------------------------------------------------------


class TestStackUnstaleCommand:
    """Tests for the `lexi stack unstale` command."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexi_app, args)
        finally:
            os.chdir(old_cwd)

    def test_unstale_stale_post(self, tmp_path: Path) -> None:
        """Reversing stale post back to resolved shows confirmation."""
        _setup_stack_project(tmp_path)
        _create_stack_post(
            tmp_path,
            post_id="ST-001",
            title="Old bug",
            status="stale",
            stale_at="2026-01-20T00:00:00+00:00",
        )
        result = self._invoke(tmp_path, ["stack", "unstale", "ST-001"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "resolved" in result.output.lower()  # type: ignore[union-attr]
        # Verify the post file was updated
        post_path = list((tmp_path / ".lexibrary" / "stack").glob("ST-001-*.md"))[0]
        content = post_path.read_text(encoding="utf-8")
        assert "status: resolved" in content

    def test_unstale_non_stale_post_fails(self, tmp_path: Path) -> None:
        """Un-staling a resolved post fails with error."""
        _setup_stack_project(tmp_path)
        _create_stack_post(tmp_path, post_id="ST-001", title="Resolved bug", status="resolved")
        result = self._invoke(tmp_path, ["stack", "unstale", "ST-001"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "stale" in result.output.lower()  # type: ignore[union-attr]

    def test_unstale_nonexistent_post_fails(self, tmp_path: Path) -> None:
        """Un-staling a nonexistent post fails."""
        _setup_stack_project(tmp_path)
        result = self._invoke(tmp_path, ["stack", "unstale", "ST-999"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "not found" in result.output.lower()  # type: ignore[union-attr]

    def test_unstale_no_project(self, tmp_path: Path) -> None:
        """Running without .lexibrary should fail."""
        result = self._invoke(tmp_path, ["stack", "unstale", "ST-001"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "No .lexibrary/" in result.output  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Stack search --include-stale tests
# ---------------------------------------------------------------------------


class TestSearchStackIncludeStale:
    """Tests for --include-stale flag on `lexi search --type stack`."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexi_app, args)
        finally:
            os.chdir(old_cwd)

    def test_search_excludes_stale_by_default(self, tmp_path: Path) -> None:
        """Stale posts are excluded from search results by default."""
        _setup_stack_project(tmp_path)
        _create_stack_post(tmp_path, post_id="ST-001", title="Open bug", status="open")
        _create_stack_post(
            tmp_path,
            post_id="ST-002",
            title="Stale bug",
            status="stale",
            stale_at="2026-01-20T00:00:00+00:00",
        )
        result = self._invoke(tmp_path, ["search", "bug", "--type", "stack"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Open bug" in result.output  # type: ignore[union-attr]
        assert "Stale bug" not in result.output  # type: ignore[union-attr]

    def test_search_include_stale_shows_stale(self, tmp_path: Path) -> None:
        """With --include-stale, stale posts appear in results."""
        _setup_stack_project(tmp_path)
        _create_stack_post(tmp_path, post_id="ST-001", title="Open bug", status="open")
        _create_stack_post(
            tmp_path,
            post_id="ST-002",
            title="Stale bug",
            status="stale",
            stale_at="2026-01-20T00:00:00+00:00",
        )
        result = self._invoke(tmp_path, ["search", "bug", "--include-stale"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Open bug" in result.output  # type: ignore[union-attr]
        assert "Stale bug" in result.output  # type: ignore[union-attr]

    def test_search_status_stale_shows_stale(self, tmp_path: Path) -> None:
        """Explicit --status stale shows stale posts without --include-stale."""
        _setup_stack_project(tmp_path)
        _create_stack_post(
            tmp_path,
            post_id="ST-001",
            title="Stale bug",
            status="stale",
            stale_at="2026-01-20T00:00:00+00:00",
        )
        result = self._invoke(tmp_path, ["search", "--type", "stack", "--status", "stale"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Stale bug" in result.output  # type: ignore[union-attr]

    def test_list_excludes_stale_by_default(self, tmp_path: Path) -> None:
        """Stale posts are excluded from listing by default."""
        _setup_stack_project(tmp_path)
        _create_stack_post(tmp_path, post_id="ST-001", title="Open bug", status="open")
        _create_stack_post(
            tmp_path,
            post_id="ST-002",
            title="Stale bug",
            status="stale",
            stale_at="2026-01-20T00:00:00+00:00",
        )
        result = self._invoke(tmp_path, ["search", "--type", "stack"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Open bug" in result.output  # type: ignore[union-attr]
        assert "Stale bug" not in result.output  # type: ignore[union-attr]

    def test_list_include_stale_shows_stale(self, tmp_path: Path) -> None:
        """With --include-stale, stale posts appear in listing."""
        _setup_stack_project(tmp_path)
        _create_stack_post(tmp_path, post_id="ST-001", title="Open bug", status="open")
        _create_stack_post(
            tmp_path,
            post_id="ST-002",
            title="Stale bug",
            status="stale",
            stale_at="2026-01-20T00:00:00+00:00",
        )
        result = self._invoke(tmp_path, ["search", "--type", "stack", "--include-stale"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Open bug" in result.output  # type: ignore[union-attr]
        assert "Stale bug" in result.output  # type: ignore[union-attr]

    def test_list_status_stale_shows_stale(self, tmp_path: Path) -> None:
        """Explicit --status stale shows stale posts without --include-stale."""
        _setup_stack_project(tmp_path)
        _create_stack_post(
            tmp_path,
            post_id="ST-001",
            title="Stale bug",
            status="stale",
            stale_at="2026-01-20T00:00:00+00:00",
        )
        result = self._invoke(tmp_path, ["search", "--type", "stack", "--status", "stale"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Stale bug" in result.output  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# orient (and context-dump backward compatibility)
# ---------------------------------------------------------------------------


def _write_test_aindex(
    project_root: Path,
    directory_path: str,
    billboard: str,
    entries: list[dict[str, str]] | None = None,
) -> Path:
    """Create a serialised .aindex file under .lexibrary/ for testing.

    ``entries`` should be a list of dicts with keys: name, entry_type, description.
    Returns the path to the written .aindex file.
    """
    from datetime import UTC  # noqa: PLC0415

    from lexibrary.artifacts.aindex import AIndexEntry, AIndexFile  # noqa: PLC0415
    from lexibrary.artifacts.aindex_serializer import serialize_aindex  # noqa: PLC0415
    from lexibrary.artifacts.design_file import StalenessMetadata  # noqa: PLC0415

    if entries is None:
        entry_objects = [
            AIndexEntry(name="example.py", entry_type="file", description="Example file"),
        ]
    else:
        entry_objects = [
            AIndexEntry(
                name=e["name"],
                entry_type=e["entry_type"],  # type: ignore[arg-type]
                description=e["description"],
            )
            for e in entries
        ]

    aindex = AIndexFile(
        directory_path=directory_path,
        billboard=billboard,
        entries=entry_objects,
        metadata=StalenessMetadata(
            source=directory_path,
            source_hash="abc123",
            generated=datetime(2025, 1, 1, tzinfo=UTC),
            generator="test",
        ),
    )
    text = serialize_aindex(aindex)

    mirror_dir = project_root / ".lexibrary" / directory_path
    mirror_dir.mkdir(parents=True, exist_ok=True)
    aindex_path = mirror_dir / ".aindex"
    aindex_path.write_text(text, encoding="utf-8")
    return aindex_path


def _write_test_iwh(
    project_root: Path,
    directory_path: str,
    scope: str = "incomplete",
    body: str = "Some work remains",
    author: str = "test-agent",
) -> Path:
    """Create a serialised .iwh file under .lexibrary/designs/ for testing."""
    from datetime import UTC  # noqa: PLC0415

    from lexibrary.iwh.model import IWHFile  # noqa: PLC0415
    from lexibrary.iwh.serializer import serialize_iwh  # noqa: PLC0415

    iwh = IWHFile(
        author=author,
        created=datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
        scope=scope,  # type: ignore[arg-type]
        body=body,
    )
    text = serialize_iwh(iwh)

    mirror_dir = project_root / ".lexibrary" / "designs" / directory_path
    mirror_dir.mkdir(parents=True, exist_ok=True)
    iwh_path = mirror_dir / ".iwh"
    iwh_path.write_text(text, encoding="utf-8")
    return iwh_path


class TestOrient:
    """Tests for the orient command."""

    @staticmethod
    def _invoke(cwd: Path, args: list[str]) -> object:
        return runner.invoke(lexi_app, args, catch_exceptions=False, env={"PWD": str(cwd)})

    # -- Visibility: orient is visible, context-dump is hidden --

    def test_orient_visible_in_help(self) -> None:
        """orient should appear in --help output."""
        result = runner.invoke(lexi_app, ["--help"])
        assert result.exit_code == 0
        assert "orient" in result.output

    def test_context_dump_hidden_from_help(self) -> None:
        """context-dump should NOT appear in --help output (hidden alias)."""
        result = runner.invoke(lexi_app, ["--help"])
        assert result.exit_code == 0
        assert "context-dump" not in result.output

    def test_orient_command_exists(self, tmp_path: Path) -> None:
        """orient should be callable (even if project has no .lexibrary)."""
        result = runner.invoke(
            lexi_app, ["orient"], catch_exceptions=False, env={"PWD": str(tmp_path)}
        )
        assert result.exit_code == 0

    def test_context_dump_removed(self, tmp_path: Path) -> None:
        """context-dump alias was removed; should return usage error."""
        result = runner.invoke(lexi_app, ["context-dump"], env={"PWD": str(tmp_path)})
        assert result.exit_code == 2

    # -- Topology and file descriptions --

    def test_indexed_project_includes_topology(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """orient should include TOPOLOGY.md content when present."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".lexibrary").mkdir()
        topology_content = (
            "# Project Topology\n\n```\nroot/ -- Main project\n  src/ -- Source code\n```\n"
        )
        (tmp_path / ".lexibrary" / "TOPOLOGY.md").write_text(topology_content, encoding="utf-8")

        result = runner.invoke(lexi_app, ["orient"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Project Topology" in result.output
        assert "Main project" in result.output

    def test_indexed_project_includes_file_descriptions(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """orient should include file-level descriptions from .aindex entries."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".lexibrary").mkdir()

        _write_test_aindex(
            tmp_path,
            "src",
            "Main source code",
            entries=[
                {"name": "main.py", "entry_type": "file", "description": "Application entry point"},
                {
                    "name": "utils.py",
                    "entry_type": "file",
                    "description": "Shared utility functions",
                },
                {"name": "auth", "entry_type": "dir", "description": "Authentication module"},
            ],
        )

        result = runner.invoke(lexi_app, ["orient"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "src/main.py: Application entry point" in result.output
        assert "src/utils.py: Shared utility functions" in result.output
        # dir entries should NOT appear in file descriptions
        assert "src/auth:" not in result.output

    def test_indexed_project_includes_topology_and_descriptions(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """orient should include both TOPOLOGY.md and file descriptions."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".lexibrary").mkdir()
        topology_content = "# Project Topology\n\n```\nroot/ -- My project\n```\n"
        (tmp_path / ".lexibrary" / "TOPOLOGY.md").write_text(topology_content, encoding="utf-8")

        _write_test_aindex(
            tmp_path,
            "src",
            "Source code",
            entries=[
                {"name": "app.py", "entry_type": "file", "description": "Main application"},
            ],
        )

        result = runner.invoke(lexi_app, ["orient"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Project Topology" in result.output
        assert "src/app.py: Main application" in result.output

    # -- No .lexibrary directory --

    def test_no_lexibrary_directory(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """orient should exit 0 with informational message when no .lexibrary/ exists."""
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(lexi_app, ["orient"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "No .lexibrary/" in result.output

    # -- Empty .lexibrary --

    def test_empty_lexibrary_no_topology(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Empty .lexibrary with no TOPOLOGY.md should produce informational message."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".lexibrary").mkdir()
        result = runner.invoke(lexi_app, ["orient"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "no orientation data" in result.output

    def test_empty_lexibrary_with_topology(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Empty .lexibrary with TOPOLOGY.md should still output topology content."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".lexibrary").mkdir()
        topology_content = "# Project Topology\n\n```\nroot/ -- Bare project\n```\n"
        (tmp_path / ".lexibrary" / "TOPOLOGY.md").write_text(topology_content, encoding="utf-8")

        result = runner.invoke(lexi_app, ["orient"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Bare project" in result.output

    # -- Truncation behavior --

    def test_truncation_omits_deepest_entries(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When output exceeds budget, deepest-path entries should be omitted first."""
        import lexibrary.services.orient_render as orient_render_mod  # noqa: PLC0415

        monkeypatch.chdir(tmp_path)
        (tmp_path / ".lexibrary").mkdir()

        # Use a tiny budget to force truncation easily
        monkeypatch.setattr(orient_render_mod, "ORIENT_CHAR_BUDGET", 400)

        # Create a small TOPOLOGY.md
        topology_content = "# Project Topology\n\nroot/ -- My project\n"
        (tmp_path / ".lexibrary" / "TOPOLOGY.md").write_text(topology_content, encoding="utf-8")

        # Add many file descriptions at various depths
        _write_test_aindex(
            tmp_path,
            "src",
            "Source code",
            entries=[
                {
                    "name": f"file_{i}.py",
                    "entry_type": "file",
                    "description": f"Shallow file {i} desc",
                }
                for i in range(10)
            ],
        )
        _write_test_aindex(
            tmp_path,
            "src/deep/nested/dir",
            "Deeply nested",
            entries=[
                {
                    "name": f"deep_{i}.py",
                    "entry_type": "file",
                    "description": f"Deep file {i} desc",
                }
                for i in range(10)
            ],
        )

        result = runner.invoke(lexi_app, ["orient"], catch_exceptions=False)
        assert result.exit_code == 0
        # Should include the omission notice (truncation footer)
        assert "omitted" in result.output

    def test_truncation_preserves_shallow_entries(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Truncation should prioritise shallow (fewer /) entries over deep ones."""
        import lexibrary.services.orient_render as orient_render_mod  # noqa: PLC0415

        monkeypatch.chdir(tmp_path)
        (tmp_path / ".lexibrary").mkdir()

        # Minimal topology
        (tmp_path / ".lexibrary" / "TOPOLOGY.md").write_text("# Topology\nSmall.", encoding="utf-8")

        # Use a very small budget to force truncation
        monkeypatch.setattr(orient_render_mod, "ORIENT_CHAR_BUDGET", 200)

        _write_test_aindex(
            tmp_path,
            "src",
            "Source code",
            entries=[
                {"name": "top.py", "entry_type": "file", "description": "Top level"},
            ],
        )
        _write_test_aindex(
            tmp_path,
            "src/a/b/c/d",
            "Very deep",
            entries=[
                {"name": "deep.py", "entry_type": "file", "description": "Very deep file"},
            ],
        )

        result = runner.invoke(lexi_app, ["orient"], catch_exceptions=False)
        assert result.exit_code == 0
        output = result.output

        # With a 200-char budget, not everything fits.
        # Shallow entry (src/top.py, 1 slash) should be prioritised over
        # deep entry (src/a/b/c/d/deep.py, 4 slashes).
        if "omitted" in output:
            # Truncation happened — shallow should be preferred
            assert "src/top.py" in output

    # -- Output format --

    def test_output_is_plain_text(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Output should be plain text without Rich formatting markers."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".lexibrary").mkdir()
        (tmp_path / ".lexibrary" / "TOPOLOGY.md").write_text(
            "# Project Topology\n\nPlain text.\n", encoding="utf-8"
        )

        result = runner.invoke(lexi_app, ["orient"], catch_exceptions=False)
        assert result.exit_code == 0
        # No Rich markup in output
        assert "[red]" not in result.output
        assert "[green]" not in result.output
        assert "[dim]" not in result.output

    # -- IWH signals peek --

    def test_iwh_signals_displayed(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """orient should show IWH signals without consuming them."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".lexibrary").mkdir()
        (tmp_path / ".lexibrary" / "TOPOLOGY.md").write_text("# Topology\nOK.\n", encoding="utf-8")

        _write_test_iwh(tmp_path, "src/auth", scope="blocked", body="Waiting for API key rotation")

        result = runner.invoke(lexi_app, ["orient"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "IWH Signals" in result.output
        assert "[blocked]" in result.output
        assert "Waiting for API key rotation" in result.output

    def test_iwh_signals_not_consumed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """orient should peek at IWH signals without deleting them."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".lexibrary").mkdir()
        (tmp_path / ".lexibrary" / "TOPOLOGY.md").write_text("# Topology\nOK.\n", encoding="utf-8")

        iwh_path = _write_test_iwh(tmp_path, "src/auth", body="Do not consume me")

        runner.invoke(lexi_app, ["orient"], catch_exceptions=False)
        # IWH file should still exist after orient
        assert iwh_path.exists()

    def test_no_iwh_section_when_no_signals(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """orient should not show IWH section when no signals exist."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".lexibrary").mkdir()
        (tmp_path / ".lexibrary" / "TOPOLOGY.md").write_text("# Topology\nOK.\n", encoding="utf-8")

        result = runner.invoke(lexi_app, ["orient"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "IWH Signals" not in result.output

    # -- Library stats --

    def test_library_stats_with_concepts(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """orient should show concept count in library stats."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".lexibrary").mkdir()
        (tmp_path / ".lexibrary" / "TOPOLOGY.md").write_text("# Topology\nOK.\n", encoding="utf-8")

        concepts_dir = tmp_path / ".lexibrary" / "concepts"
        concepts_dir.mkdir(parents=True)
        (concepts_dir / "AuthFlow.md").write_text(
            "---\ntitle: AuthFlow\nid: CN-002\n---\n", encoding="utf-8"
        )
        (concepts_dir / "DataModel.md").write_text(
            "---\ntitle: DataModel\nid: CN-003\n---\n", encoding="utf-8"
        )

        result = runner.invoke(lexi_app, ["orient"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Library Stats" in result.output
        assert "Concepts: 2" in result.output

    def test_library_stats_with_conventions(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """orient should show convention count in library stats."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".lexibrary").mkdir()
        (tmp_path / ".lexibrary" / "TOPOLOGY.md").write_text("# Topology\nOK.\n", encoding="utf-8")

        conventions_dir = tmp_path / ".lexibrary" / "conventions"
        conventions_dir.mkdir(parents=True)
        (conventions_dir / "naming.md").write_text(
            "---\ntitle: naming\nid: CN-004\n---\n", encoding="utf-8"
        )

        result = runner.invoke(lexi_app, ["orient"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Library Stats" in result.output
        assert "Conventions: 1" in result.output

    def test_library_stats_with_open_stack_posts(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """orient should show open stack post count in library stats."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".lexibrary").mkdir()
        (tmp_path / ".lexibrary" / "TOPOLOGY.md").write_text("# Topology\nOK.\n", encoding="utf-8")

        _create_stack_post(tmp_path, post_id="ST-001", title="Open bug", status="open")
        _create_stack_post(tmp_path, post_id="ST-002", title="Resolved bug", status="resolved")
        _create_stack_post(tmp_path, post_id="ST-003", title="Another open", status="open")

        result = runner.invoke(lexi_app, ["orient"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Library Stats" in result.output
        assert "Open stack posts: 2" in result.output

    def test_no_library_stats_when_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """orient should not show library stats section when all counts are zero."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".lexibrary").mkdir()
        (tmp_path / ".lexibrary" / "TOPOLOGY.md").write_text("# Topology\nOK.\n", encoding="utf-8")

        result = runner.invoke(lexi_app, ["orient"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Library Stats" not in result.output

    # -- IWH consumption guidance footer --

    def test_iwh_guidance_footer_present(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """orient should show consumption guidance when IWH signals are present."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".lexibrary").mkdir()
        (tmp_path / ".lexibrary" / "TOPOLOGY.md").write_text("# Topology\nOK.\n", encoding="utf-8")

        _write_test_iwh(tmp_path, "src/auth", body="Needs attention")

        result = runner.invoke(lexi_app, ["orient"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "lexi iwh read" in result.output
        assert "consume the signal" in result.output

    def test_iwh_guidance_footer_absent_when_no_signals(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """orient should not show consumption guidance when no IWH signals exist."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".lexibrary").mkdir()
        (tmp_path / ".lexibrary" / "TOPOLOGY.md").write_text("# Topology\nOK.\n", encoding="utf-8")

        result = runner.invoke(lexi_app, ["orient"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "lexi iwh read" not in result.output


# ---------------------------------------------------------------------------
# Impact command
# ---------------------------------------------------------------------------


def _create_impact_linkgraph(tmp_path: Path) -> Path:
    """Create a valid link graph database at the standard project location."""
    import sqlite3

    from lexibrary.linkgraph.schema import ensure_schema

    db_path = tmp_path / ".lexibrary" / "index.db"
    conn = sqlite3.connect(str(db_path))
    ensure_schema(conn)
    conn.commit()
    conn.close()
    return db_path


def _populate_impact_db(
    db_path: Path,
    *,
    add_depth2: bool = False,
    add_stack_post: bool = False,
) -> None:
    """Populate the database with import relationships for impact testing.

    Sets up:
    - src/core/utils.py (target)
    - src/api/controller.py imports utils.py (depth 1)
    - src/cli/handler.py imports utils.py (depth 1)

    If add_depth2:
    - src/app/main.py imports controller.py (depth 2 from utils.py)

    If add_stack_post:
    - An open stack post referencing controller.py
    """
    import sqlite3

    conn = sqlite3.connect(str(db_path))

    # Target artifact
    conn.execute(
        "INSERT INTO artifacts (id, path, kind, title, status) "
        "VALUES (1, 'src/core/utils.py', 'source', 'Core utilities', 'active')"
    )
    # Depth 1 dependents
    conn.execute(
        "INSERT INTO artifacts (id, path, kind, title, status) "
        "VALUES (2, 'src/api/controller.py', 'source', 'API controller', 'active')"
    )
    conn.execute(
        "INSERT INTO artifacts (id, path, kind, title, status) "
        "VALUES (3, 'src/cli/handler.py', 'source', 'CLI handler', 'active')"
    )
    # ast_import links: controller -> utils, handler -> utils
    conn.execute(
        "INSERT INTO links (source_id, target_id, link_type, link_context) "
        "VALUES (2, 1, 'ast_import', 'from src.core.utils import helper')"
    )
    conn.execute(
        "INSERT INTO links (source_id, target_id, link_type, link_context) "
        "VALUES (3, 1, 'ast_import', 'from src.core.utils import format_output')"
    )

    if add_depth2:
        conn.execute(
            "INSERT INTO artifacts (id, path, kind, title, status) "
            "VALUES (4, 'src/app/main.py', 'source', 'App entry point', 'active')"
        )
        # main.py imports controller.py (depth 2 from utils.py)
        conn.execute(
            "INSERT INTO links (source_id, target_id, link_type, link_context) "
            "VALUES (4, 2, 'ast_import', 'from src.api.controller import Controller')"
        )

    if add_stack_post:
        conn.execute(
            "INSERT INTO artifacts (id, path, kind, title, status) "
            "VALUES (10, '.lexibrary/stack/ST-001-auth-bug.md', 'stack', "
            "'Auth token bug in controller', 'open')"
        )
        # stack_file_ref: stack post -> controller
        conn.execute(
            "INSERT INTO links (source_id, target_id, link_type, link_context) "
            "VALUES (10, 2, 'stack_file_ref', NULL)"
        )

    conn.commit()
    conn.close()


def _setup_impact_project(tmp_path: Path) -> Path:
    """Create a project structure for impact testing."""
    (tmp_path / ".lexibrary").mkdir()
    (tmp_path / ".lexibrary" / "config.yaml").write_text("")
    (tmp_path / "src" / "core").mkdir(parents=True)
    (tmp_path / "src" / "api").mkdir(parents=True)
    (tmp_path / "src" / "cli").mkdir(parents=True)
    (tmp_path / "src" / "app").mkdir(parents=True)
    (tmp_path / "src" / "core" / "utils.py").write_text("def helper(): pass\n")
    (tmp_path / "src" / "api" / "controller.py").write_text("from src.core.utils import helper\n")
    (tmp_path / "src" / "cli" / "handler.py").write_text(
        "from src.core.utils import format_output\n"
    )
    (tmp_path / "src" / "app" / "main.py").write_text("from src.api.controller import Controller\n")
    return tmp_path


class TestImpact:
    """Tests for the ``lexi impact`` command."""

    def test_dependents_found(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Impact shows dependents that import the given file."""
        project = _setup_impact_project(tmp_path)
        monkeypatch.chdir(project)
        db_path = _create_impact_linkgraph(project)
        _populate_impact_db(db_path)

        result = runner.invoke(
            lexi_app,
            ["impact", str(project / "src" / "core" / "utils.py")],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "src/api/controller.py" in result.output
        assert "src/cli/handler.py" in result.output

    def test_depth_2(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Impact at depth 2 follows transitive dependents."""
        project = _setup_impact_project(tmp_path)
        monkeypatch.chdir(project)
        db_path = _create_impact_linkgraph(project)
        _populate_impact_db(db_path, add_depth2=True)

        result = runner.invoke(
            lexi_app,
            ["impact", str(project / "src" / "core" / "utils.py"), "--depth", "2"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "src/api/controller.py" in result.output
        assert "src/cli/handler.py" in result.output
        assert "src/app/main.py" in result.output

    def test_no_dependents(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Impact reports no dependents when file has none."""
        project = _setup_impact_project(tmp_path)
        monkeypatch.chdir(project)
        db_path = _create_impact_linkgraph(project)
        _populate_impact_db(db_path)

        # handler.py has no inbound ast_imports
        result = runner.invoke(
            lexi_app,
            ["impact", str(project / "src" / "cli" / "handler.py")],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "No dependents found" in result.output

    def test_outside_scope(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Impact rejects files outside the configured scope_root."""
        project = _setup_impact_project(tmp_path)
        monkeypatch.chdir(project)
        # Create a file outside scope
        (tmp_path / "external").mkdir()
        (tmp_path / "external" / "file.py").write_text("x = 1\n")

        # Set scope_root to src/ so external/ is outside scope
        (project / ".lexibrary" / "config.yaml").write_text("scope_root: src\n")

        result = runner.invoke(
            lexi_app,
            ["impact", str(project / "external" / "file.py")],
            catch_exceptions=False,
        )
        assert result.exit_code == 1
        assert "outside" in result.output

    def test_quiet_mode(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Quiet mode outputs paths only, one per line."""
        project = _setup_impact_project(tmp_path)
        monkeypatch.chdir(project)
        db_path = _create_impact_linkgraph(project)
        _populate_impact_db(db_path)

        result = runner.invoke(
            lexi_app,
            ["impact", str(project / "src" / "core" / "utils.py"), "--quiet"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        lines = [ln for ln in result.output.strip().splitlines() if ln.strip()]
        assert len(lines) == 2
        paths = {ln.strip() for ln in lines}
        assert "src/api/controller.py" in paths
        assert "src/cli/handler.py" in paths
        # No decorative output in quiet mode
        assert "Dependents" not in result.output

    def test_depth_clamping(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Depth values above 3 are clamped to 3, below 1 are clamped to 1."""
        project = _setup_impact_project(tmp_path)
        monkeypatch.chdir(project)
        db_path = _create_impact_linkgraph(project)
        _populate_impact_db(db_path, add_depth2=True)

        # depth=10 should be clamped to 3 — still finds depth 2 results
        result = runner.invoke(
            lexi_app,
            ["impact", str(project / "src" / "core" / "utils.py"), "--depth", "10"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "src/app/main.py" in result.output

        # depth=0 should be clamped to 1
        result_d0 = runner.invoke(
            lexi_app,
            ["impact", str(project / "src" / "core" / "utils.py"), "--depth", "0"],
            catch_exceptions=False,
        )
        assert result_d0.exit_code == 0
        # Should find depth 1 deps but not depth 2
        assert "src/api/controller.py" in result_d0.output
        assert "src/app/main.py" not in result_d0.output

    def test_no_link_graph(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Impact exits gracefully when no link graph exists."""
        project = _setup_impact_project(tmp_path)
        monkeypatch.chdir(project)
        # No index.db created

        result = runner.invoke(
            lexi_app,
            ["impact", str(project / "src" / "core" / "utils.py")],
            catch_exceptions=False,
        )
        assert result.exit_code == 1
        assert "No link graph" in result.output

    def test_no_link_graph_quiet(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Quiet mode returns empty output when no link graph exists."""
        project = _setup_impact_project(tmp_path)
        monkeypatch.chdir(project)
        # No index.db created

        result = runner.invoke(
            lexi_app,
            ["impact", str(project / "src" / "core" / "utils.py"), "--quiet"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert result.output.strip() == ""

    def test_open_stack_post_warning(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Impact shows a warning when a dependent has an open stack post."""
        project = _setup_impact_project(tmp_path)
        monkeypatch.chdir(project)
        db_path = _create_impact_linkgraph(project)
        _populate_impact_db(db_path, add_stack_post=True)

        result = runner.invoke(
            lexi_app,
            ["impact", str(project / "src" / "core" / "utils.py")],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "src/api/controller.py" in result.output
        assert "warning" in result.output.lower()
        assert "Auth token bug" in result.output

    def test_design_file_description_in_output(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Impact includes design file descriptions when available."""
        project = _setup_impact_project(tmp_path)
        monkeypatch.chdir(project)
        db_path = _create_impact_linkgraph(project)
        _populate_impact_db(db_path)

        # Create a design file for controller.py
        design_path = project / ".lexibrary" / "designs" / "src" / "api" / "controller.py.md"
        design_path.parent.mkdir(parents=True, exist_ok=True)
        design_path.write_text(
            "---\ndescription: HTTP API request handler\nid: DS-001\nupdated_by: archivist\n"
            "---\n\n# controller\n",
            encoding="utf-8",
        )

        result = runner.invoke(
            lexi_app,
            ["impact", str(project / "src" / "core" / "utils.py")],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "HTTP API request handler" in result.output


# ---------------------------------------------------------------------------
# Lookup Enhancements tests (task group 6)
# ---------------------------------------------------------------------------


def _create_stack_post_with_attempts(
    tmp_path: Path,
    post_id: str = "ST-010",
    title: str = "Known bug",
    status: str = "open",
    votes: int = 0,
    attempts: list[str] | None = None,
    refs_files: list[str] | None = None,
) -> Path:
    """Create a stack post with attempts section for testing."""
    resolved_attempts = attempts or []
    post_path = _create_stack_post(
        tmp_path,
        post_id=post_id,
        title=title,
        status=status,
        votes=votes,
        refs_files=refs_files or [],
    )
    # Append attempts section
    content = post_path.read_text(encoding="utf-8")
    if resolved_attempts:
        attempts_section = "\n### Attempts\n\n"
        for attempt in resolved_attempts:
            attempts_section += f"- {attempt}\n"
        content += attempts_section
    post_path.write_text(content, encoding="utf-8")
    return post_path


def _create_iwh_signal(
    tmp_path: Path,
    rel_dir: str,
    scope: str = "incomplete",
    author: str = "test-agent",
    body: str = "Work not finished",
) -> Path:
    """Create an IWH signal file in the mirror tree."""
    iwh_dir = tmp_path / ".lexibrary" / "designs" / rel_dir
    iwh_dir.mkdir(parents=True, exist_ok=True)
    iwh_path = iwh_dir / ".iwh"

    from datetime import UTC  # noqa: PLC0415

    created = datetime.now(tz=UTC).isoformat()
    fm_data = {
        "author": author,
        "created": created,
        "scope": scope,
    }
    fm_str = yaml.dump(fm_data, default_flow_style=False, sort_keys=False).rstrip("\n")
    content = f"---\n{fm_str}\n---\n{body}\n"
    iwh_path.write_text(content, encoding="utf-8")
    return iwh_path


class TestLookupKnownIssues:
    """Tests for Known Issues section in lookup output (task 6.1)."""

    def test_lookup_known_issues_no_link_graph(self, tmp_path: Path) -> None:
        """Lookup without link graph gracefully omits Known Issues."""
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
        assert "Known Issues" not in result.output

    def test_render_known_issues_rendering(self) -> None:
        """_render_known_issues returns formatted text with status/title/attempts/votes."""
        from lexibrary.linkgraph.query import LinkGraph, LinkResult
        from lexibrary.services.lookup_render import render_known_issues as _render_known_issues

        class FakeLinkGraph(LinkGraph):
            """Fake link graph for testing."""

            def __init__(self, links: list[LinkResult]) -> None:
                self._links = links

            def reverse_deps(self, path: str, link_type: str | None = None) -> list[LinkResult]:
                if link_type == "stack_file_ref":
                    return self._links
                return []

        # Create a temp directory with a stack post
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            post_path = _create_stack_post_with_attempts(
                project,
                post_id="ST-100",
                title="Auth failure on login",
                status="open",
                votes=3,
                attempts=["Tried restart", "Tried clearing cache"],
            )
            rel_post = str(post_path.relative_to(project))

            fake_link = LinkResult(
                source_id=1,
                source_path=rel_post,
                link_type="stack_file_ref",
                link_context=None,
            )
            fake_graph = FakeLinkGraph([fake_link])

            result = _render_known_issues(fake_graph, "src/main.py", project, display_limit=3)

        assert "Known Issues" in result
        assert "[open]" in result
        assert "Auth failure on login" in result
        assert "2 attempts" in result
        assert "3 votes" in result

    def test_render_known_issues_stale_excluded(self) -> None:
        """_render_known_issues excludes stale posts."""
        from lexibrary.linkgraph.query import LinkGraph, LinkResult
        from lexibrary.services.lookup_render import render_known_issues as _render_known_issues

        class FakeLinkGraph(LinkGraph):
            def __init__(self, links: list[LinkResult]) -> None:
                self._links = links

            def reverse_deps(self, path: str, link_type: str | None = None) -> list[LinkResult]:
                if link_type == "stack_file_ref":
                    return self._links
                return []

        import tempfile

        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            # Create a stale post
            post_path = _create_stack_post(
                project,
                post_id="ST-200",
                title="Stale issue",
                status="stale",
            )
            rel_post = str(post_path.relative_to(project))

            fake_link = LinkResult(
                source_id=1,
                source_path=rel_post,
                link_type="stack_file_ref",
                link_context=None,
            )
            fake_graph = FakeLinkGraph([fake_link])

            result = _render_known_issues(fake_graph, "src/main.py", project, display_limit=3)

        # Should be empty because the only post is stale
        assert result == ""

    def test_render_known_issues_display_limit(self) -> None:
        """_render_known_issues respects display_limit."""
        from lexibrary.linkgraph.query import LinkGraph, LinkResult
        from lexibrary.services.lookup_render import render_known_issues as _render_known_issues

        class FakeLinkGraph(LinkGraph):
            def __init__(self, links: list[LinkResult]) -> None:
                self._links = links

            def reverse_deps(self, path: str, link_type: str | None = None) -> list[LinkResult]:
                if link_type == "stack_file_ref":
                    return self._links
                return []

        import tempfile

        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            links = []
            for i in range(5):
                post_path = _create_stack_post(
                    project,
                    post_id=f"ST-30{i}",
                    title=f"Issue number {i}",
                    status="open",
                )
                rel_post = str(post_path.relative_to(project))
                links.append(
                    LinkResult(
                        source_id=i,
                        source_path=rel_post,
                        link_type="stack_file_ref",
                        link_context=None,
                    )
                )

            fake_graph = FakeLinkGraph(links)

            result = _render_known_issues(fake_graph, "src/main.py", project, display_limit=2)

        assert "Issue number" in result
        assert "3 more issues" in result


class TestLookupIWHPeek:
    """Tests for IWH signal peek in lookup output (task 6.3)."""

    def test_iwh_peek_file_lookup(self, tmp_path: Path) -> None:
        """IWH signal in parent dir mirror shows in full file lookup."""
        project = _setup_archivist_project(tmp_path)
        source_content = "def hello():\n    pass\n"
        _create_design_file(project, "src/main.py", source_content)

        # Create an IWH signal in the src/ mirror directory
        _create_iwh_signal(project, "src", body="Auth refactor incomplete")

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            result = runner.invoke(lexi_app, ["lookup", "src/main.py", "--full"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 0
        assert "IWH Signal" in result.output
        assert "incomplete" in result.output
        assert "Auth refactor incomplete" in result.output

    def test_iwh_peek_not_consumed(self, tmp_path: Path) -> None:
        """IWH peek does not consume (delete) the signal file."""
        project = _setup_archivist_project(tmp_path)
        source_content = "def hello():\n    pass\n"
        _create_design_file(project, "src/main.py", source_content)

        iwh_path = _create_iwh_signal(project, "src", body="Do not consume")

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            runner.invoke(lexi_app, ["lookup", "src/main.py", "--full"])
        finally:
            os.chdir(old_cwd)

        # The IWH file should still exist after peek
        assert iwh_path.exists()

    def test_iwh_peek_no_signal(self, tmp_path: Path) -> None:
        """Lookup without IWH signal omits the section."""
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
        assert "IWH Signal" not in result.output


class TestLookupDirectory:
    """Tests for directory lookup support (task 6.4)."""

    def test_directory_lookup_with_aindex(self, tmp_path: Path) -> None:
        """Directory lookup displays aindex content."""
        project = _setup_archivist_project(tmp_path)
        _create_aindex(project, "src", "Source code root directory")

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            result = runner.invoke(lexi_app, ["lookup", "src"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 0
        assert "Source code root directory" in result.output
        assert "Child Map" in result.output
        assert "main.py" in result.output

    def test_directory_lookup_without_aindex(self, tmp_path: Path) -> None:
        """Directory lookup without aindex shows fallback message."""
        project = _setup_archivist_project(tmp_path)

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            result = runner.invoke(lexi_app, ["lookup", "src"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 0
        assert "No .aindex file found" in result.output

    def test_directory_lookup_with_iwh(self, tmp_path: Path) -> None:
        """Directory lookup shows IWH signal in the directory."""
        project = _setup_archivist_project(tmp_path)
        _create_aindex(project, "src", "Source code root")
        _create_iwh_signal(project, "src", body="Module refactor incomplete")

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            result = runner.invoke(lexi_app, ["lookup", "src"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 0
        assert "IWH Signal" in result.output
        assert "Module refactor incomplete" in result.output

    def test_directory_lookup_outside_scope(self, tmp_path: Path) -> None:
        """Directory lookup outside scope_root should exit with error."""
        project = _setup_archivist_project(tmp_path)
        (project / ".lexibrary" / "config.yaml").write_text("scope_root: src\n")
        (project / "scripts").mkdir()

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            result = runner.invoke(lexi_app, ["lookup", "scripts"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 1
        assert "outside" in result.output


class TestLookupTokenBudget:
    """Tests for token budget truncation in lookup (task 6.5)."""

    def test_truncation_respects_priority(self) -> None:
        """Higher-priority sections are kept when budget is tight."""
        from lexibrary.services.lookup import truncate_lookup_sections as _truncate_lookup_sections

        sections = [
            ("design", "x" * 400, 0),  # ~100 tokens
            ("conventions", "y" * 400, 1),  # ~100 tokens
            ("issues", "z" * 400, 2),  # ~100 tokens
            ("iwh", "w" * 400, 3),  # ~100 tokens
            ("links", "v" * 400, 4),  # ~100 tokens
        ]

        # Budget of 200 tokens should fit design + conventions only
        result = _truncate_lookup_sections(sections, total_budget=200)
        names = [name for name, _ in result]

        assert "design" in names
        assert "conventions" in names
        # Lower priority sections should be omitted or truncated
        assert len(result) <= 3  # at most design + conventions + partial

    def test_empty_sections_skipped(self) -> None:
        """Empty sections are not included in output."""
        from lexibrary.services.lookup import truncate_lookup_sections as _truncate_lookup_sections

        sections = [
            ("design", "content here", 0),
            ("conventions", "", 1),
            ("issues", "", 2),
        ]

        result = _truncate_lookup_sections(sections, total_budget=5000)
        names = [name for name, _ in result]

        assert "design" in names
        assert "conventions" not in names
        assert "issues" not in names

    def test_estimate_tokens(self) -> None:
        """Token estimator returns reasonable estimates."""
        from lexibrary.services.lookup import estimate_tokens as _estimate_tokens

        assert _estimate_tokens("") == 0
        assert _estimate_tokens("hello world") > 0
        # ~4 chars per token
        assert _estimate_tokens("a" * 400) == 100


class TestLookupBriefMode:
    """Tests for brief vs full lookup mode (task 8.1)."""

    def test_brief_shows_description_not_body(self, tmp_path: Path) -> None:
        project = _setup_archivist_project(tmp_path)
        _create_design_file(project, "src/main.py", "def hello():\n    pass\n")
        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            result = runner.invoke(lexi_app, ["lookup", "src/main.py"])
        finally:
            os.chdir(old_cwd)
        assert result.exit_code == 0
        assert "Design file for src/main.py" in result.output
        assert "Interface Contract" not in result.output
        assert "--full" in result.output

    def test_full_shows_design_body(self, tmp_path: Path) -> None:
        project = _setup_archivist_project(tmp_path)
        _create_design_file(project, "src/main.py", "def hello():\n    pass\n")
        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            result = runner.invoke(lexi_app, ["lookup", "src/main.py", "--full"])
        finally:
            os.chdir(old_cwd)
        assert result.exit_code == 0
        assert "Interface Contract" in result.output


class TestLookupTruncationFooter:
    """Tests for lookup truncation footer (task 8.2)."""

    def test_truncation_omits_sections(self) -> None:
        from lexibrary.services.lookup import truncate_lookup_sections as _truncate_lookup_sections

        sections = [("issues", "x" * 200, 2), ("iwh", "y" * 200, 3), ("links", "z" * 200, 4)]
        result = _truncate_lookup_sections(sections, total_budget=60)
        included = {name for name, _ in result}
        assert len({"issues", "iwh", "links"} - included) > 0


# ---------------------------------------------------------------------------
# Orient topology staleness tests (task 7.6)
# ---------------------------------------------------------------------------


class TestOrientTopologyStaleness:
    """Test _check_topology_staleness warnings in orient."""

    def test_warn_when_raw_newer_than_topology(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Orient warns when raw topology is newer than TOPOLOGY.md."""
        import time  # noqa: PLC0415

        monkeypatch.chdir(tmp_path)
        (tmp_path / ".lexibrary").mkdir()

        # Create TOPOLOGY.md first (older)
        topology = tmp_path / ".lexibrary" / "TOPOLOGY.md"
        topology.write_text("# Project Topology\n\nOld content.\n", encoding="utf-8")

        # Small delay to ensure different mtime
        time.sleep(0.05)

        # Create raw topology (newer)
        tmp_dir = tmp_path / ".lexibrary" / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        raw = tmp_dir / "raw-topology.md"
        raw.write_text("# Project Topology\n\nNew content.\n", encoding="utf-8")

        result = runner.invoke(lexi_app, ["orient"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Raw topology is newer than TOPOLOGY.md" in result.output
        assert "/topology-builder" in result.output

    def test_warn_when_topology_md_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Orient warns when raw topology exists but TOPOLOGY.md is missing."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".lexibrary").mkdir()

        # Create raw topology but no TOPOLOGY.md
        tmp_dir = tmp_path / ".lexibrary" / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        raw = tmp_dir / "raw-topology.md"
        raw.write_text("# Project Topology\n\nContent.\n", encoding="utf-8")

        result = runner.invoke(lexi_app, ["orient"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Raw topology exists but TOPOLOGY.md is missing" in result.output
        assert "/topology-builder" in result.output

    def test_no_warn_when_topology_current(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No staleness warning when TOPOLOGY.md is newer than raw."""
        import time  # noqa: PLC0415

        monkeypatch.chdir(tmp_path)
        (tmp_path / ".lexibrary").mkdir()

        # Create raw topology first (older)
        tmp_dir = tmp_path / ".lexibrary" / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        raw = tmp_dir / "raw-topology.md"
        raw.write_text("# Raw\n", encoding="utf-8")

        # Small delay
        time.sleep(0.05)

        # Create TOPOLOGY.md (newer)
        topology = tmp_path / ".lexibrary" / "TOPOLOGY.md"
        topology.write_text("# Project Topology\n\nUp to date.\n", encoding="utf-8")

        result = runner.invoke(lexi_app, ["orient"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Raw topology is newer" not in result.output
        assert "TOPOLOGY.md is missing" not in result.output

    def test_no_warn_when_raw_absent(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """No staleness warning when raw topology does not exist."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".lexibrary").mkdir()

        # Only TOPOLOGY.md, no raw
        topology = tmp_path / ".lexibrary" / "TOPOLOGY.md"
        topology.write_text("# Project Topology\n\nContent.\n", encoding="utf-8")

        result = runner.invoke(lexi_app, ["orient"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Raw topology is newer" not in result.output
        assert "TOPOLOGY.md is missing" not in result.output


class TestOrientTruncationFooter:
    """Tests for orient truncation footer (task 8.3)."""

    def test_orient_truncation_starred_format(self, tmp_path: Path) -> None:
        from lexibrary.services.orient import build_orient
        from lexibrary.services.orient_render import render_orient

        project = _setup_archivist_project(tmp_path)
        (project / ".lexibrary" / "TOPOLOGY.md").write_text("x" * 20000, encoding="utf-8")
        now = datetime.now().isoformat()
        ap = project / ".lexibrary" / "designs" / "src" / ".aindex"
        ap.parent.mkdir(parents=True, exist_ok=True)
        ap.write_text(
            f"# src/\n\nSrc\n\n## Child Map\n\n| Name | Type | Description |\n"
            f"| --- | --- | --- |\n| `main.py` | file | Main |\n\n"
            f"## Local Conventions\n\n(none)\n\n"
            f'<!-- lexibrary:meta source="src" source_hash="a" '
            f'generated="{now}" generator="lexibrary-v2" -->\n',
            encoding="utf-8",
        )
        output = render_orient(build_orient(project))
        if "*Truncated:" in output:
            assert "file descriptions omitted" in output


class TestBlankSectionWarnings:
    """Tests for blank-section warnings (task 8.4)."""

    def test_stack_post_warns_blank_problem(self, tmp_path: Path) -> None:
        project = _setup_stack_project(tmp_path)
        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            result = runner.invoke(lexi_app, ["stack", "post", "--title", "Bug", "--tag", "test"])
        finally:
            os.chdir(old_cwd)
        assert result.exit_code == 0
        assert "Note: The following sections are blank:" in result.output
        assert "problem" in result.output

    def test_stack_post_no_warning_all_fields(self, tmp_path: Path) -> None:
        project = _setup_stack_project(tmp_path)
        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            result = runner.invoke(
                lexi_app,
                [
                    "stack",
                    "post",
                    "--title",
                    "Bug",
                    "--tag",
                    "test",
                    "--problem",
                    "Broke",
                    "--context",
                    "Testing",
                    "--evidence",
                    "Log",
                    "--attempts",
                    "Restarted",
                ],
            )
        finally:
            os.chdir(old_cwd)
        assert result.exit_code == 0
        assert "Note: The following sections are blank:" not in result.output

    def test_concept_new_warns_blank_tags(self, tmp_path: Path) -> None:
        project = _setup_archivist_project(tmp_path)
        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            result = runner.invoke(lexi_app, ["concept", "new", "Test Concept"])
        finally:
            os.chdir(old_cwd)
        assert result.exit_code == 0
        assert "Note: The following sections are blank:" in result.output
        assert "tags" in result.output

    def test_concept_new_no_warning_with_tags(self, tmp_path: Path) -> None:
        project = _setup_archivist_project(tmp_path)
        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            result = runner.invoke(lexi_app, ["concept", "new", "Tagged Concept", "--tag", "arch"])
        finally:
            os.chdir(old_cwd)
        assert result.exit_code == 0
        assert "Note: The following sections are blank:" not in result.output


# ---------------------------------------------------------------------------
# view
# ---------------------------------------------------------------------------

# Fixture content for view CLI tests
_VIEW_CONCEPT = """\
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

_VIEW_CONVENTION = """\
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

_VIEW_PLAYBOOK = """\
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

_VIEW_STACK = """\
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

_VIEW_DESIGN = """\
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


def _setup_view_project(tmp_path: Path) -> Path:
    """Create a minimal project with .lexibrary/ and artifact directories."""
    lib = tmp_path / ".lexibrary"
    for subdir in ("concepts", "conventions", "playbooks", "designs", "stack"):
        (lib / subdir).mkdir(parents=True)
    (lib / "config.yaml").write_text("")
    return tmp_path


class TestViewHappyPath:
    """lexi view displays parsed artifact content for valid IDs."""

    def test_view_concept(self, tmp_path: Path) -> None:
        project = _setup_view_project(tmp_path)
        (project / ".lexibrary" / "concepts" / "CN-001-example-concept.md").write_text(
            _VIEW_CONCEPT
        )
        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            result = runner.invoke(lexi_app, ["view", "CN-001"])
        finally:
            os.chdir(old_cwd)
        assert result.exit_code == 0
        assert "CN-001" in result.output
        assert "Example Concept" in result.output

    def test_view_convention(self, tmp_path: Path) -> None:
        project = _setup_view_project(tmp_path)
        (project / ".lexibrary" / "conventions" / "CV-001-example-convention.md").write_text(
            _VIEW_CONVENTION
        )
        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            result = runner.invoke(lexi_app, ["view", "CV-001"])
        finally:
            os.chdir(old_cwd)
        assert result.exit_code == 0
        assert "CV-001" in result.output
        assert "Example Convention" in result.output

    def test_view_playbook(self, tmp_path: Path) -> None:
        project = _setup_view_project(tmp_path)
        (project / ".lexibrary" / "playbooks" / "PB-001-example-playbook.md").write_text(
            _VIEW_PLAYBOOK
        )
        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            result = runner.invoke(lexi_app, ["view", "PB-001"])
        finally:
            os.chdir(old_cwd)
        assert result.exit_code == 0
        assert "PB-001" in result.output
        assert "Example Playbook" in result.output

    def test_view_stack(self, tmp_path: Path) -> None:
        project = _setup_view_project(tmp_path)
        (project / ".lexibrary" / "stack" / "ST-001-example-stack-post.md").write_text(_VIEW_STACK)
        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            result = runner.invoke(lexi_app, ["view", "ST-001"])
        finally:
            os.chdir(old_cwd)
        assert result.exit_code == 0
        assert "ST-001" in result.output
        assert "Example Stack Post" in result.output

    def test_view_design(self, tmp_path: Path) -> None:
        project = _setup_view_project(tmp_path)
        design_dir = project / ".lexibrary" / "designs" / "src"
        design_dir.mkdir(parents=True)
        (design_dir / "main.py.md").write_text(_VIEW_DESIGN)
        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            result = runner.invoke(lexi_app, ["view", "DS-001"])
        finally:
            os.chdir(old_cwd)
        assert result.exit_code == 0
        assert "DS-001" in result.output
        assert "Main entry point module" in result.output


class TestViewErrors:
    """lexi view reports errors with helpful messages."""

    def test_invalid_id_format(self, tmp_path: Path) -> None:
        project = _setup_view_project(tmp_path)
        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            result = runner.invoke(lexi_app, ["view", "NOPE"])
        finally:
            os.chdir(old_cwd)
        assert result.exit_code == 1
        assert "Invalid" in result.output or "XX-NNN" in result.output

    def test_unknown_prefix(self, tmp_path: Path) -> None:
        project = _setup_view_project(tmp_path)
        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            result = runner.invoke(lexi_app, ["view", "ZZ-001"])
        finally:
            os.chdir(old_cwd)
        assert result.exit_code == 1
        assert "Unknown" in result.output or "prefix" in result.output

    def test_artifact_not_found(self, tmp_path: Path) -> None:
        project = _setup_view_project(tmp_path)
        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            result = runner.invoke(lexi_app, ["view", "CN-999"])
        finally:
            os.chdir(old_cwd)
        assert result.exit_code == 1
        assert "not found" in result.output.lower() or "CN-999" in result.output

    def test_no_lexibrary_dir(self, tmp_path: Path) -> None:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = runner.invoke(lexi_app, ["view", "CN-001"])
        finally:
            os.chdir(old_cwd)
        assert result.exit_code == 1
        assert "No .lexibrary/ directory found" in result.output

    def test_json_error_format(self, tmp_path: Path) -> None:
        import json

        project = _setup_view_project(tmp_path)
        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            result = runner.invoke(lexi_app, ["--format", "json", "view", "CN-999"])
        finally:
            os.chdir(old_cwd)
        assert result.exit_code == 1
        # Output should be valid JSON with error info
        output = result.output.strip()
        parsed = json.loads(output)
        assert "error" in parsed
        assert parsed["artifact_id"] == "CN-999"

    def test_json_error_for_invalid_id(self, tmp_path: Path) -> None:
        import json

        project = _setup_view_project(tmp_path)
        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            result = runner.invoke(lexi_app, ["--format", "json", "view", "NOPE"])
        finally:
            os.chdir(old_cwd)
        assert result.exit_code == 1
        output = result.output.strip()
        parsed = json.loads(output)
        assert parsed["error"] == "invalid_id"

    def test_view_help(self) -> None:
        result = runner.invoke(lexi_app, ["view", "--help"])
        assert result.exit_code == 0
        assert "ARTIFACT_ID" in result.output
        assert "CN" in result.output or "artifact" in result.output.lower()
