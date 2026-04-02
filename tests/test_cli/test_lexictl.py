"""Tests for the maintenance CLI (lexictl) application."""

from __future__ import annotations

import hashlib
import os
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import yaml
from typer.testing import CliRunner

from lexibrary.archivist.change_checker import ChangeLevel
from lexibrary.archivist.pipeline import FileResult, UpdateStats
from lexibrary.cli import lexictl_app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------


class TestHelp:
    def test_help_lists_all_commands(self) -> None:
        result = runner.invoke(lexictl_app, ["--help"])
        assert result.exit_code == 0
        for cmd in (
            "init",
            "update",
            "validate",
            "status",
            "setup",
            "sweep",
            "index",
            "bootstrap",
            "help",
        ):
            assert cmd in result.output

    def test_help_does_not_include_agent_commands(self) -> None:
        result = runner.invoke(lexictl_app, ["--help"])
        assert result.exit_code == 0
        # Extract the listed command names from Typer help output.
        # Typer formats commands as "│ command_name  Description... │"
        import re

        command_names = re.findall(r"│\s+(\w+)\s{2,}", result.output)
        # Agent commands should NOT be registered as top-level commands in lexictl
        # Note: "index" is intentionally in lexictl (moved from lexi to lexictl)
        for cmd in ("lookup", "concepts", "search", "stack", "concept", "describe"):
            assert cmd not in command_names, f"Agent command '{cmd}' should not be in lexictl"


class TestMaintainerHelpCommand:
    """Tests for `lexictl help` command."""

    def test_help_succeeds(self) -> None:
        result = runner.invoke(lexictl_app, ["help"])
        assert result.exit_code == 0
        assert len(result.output) > 0

    def test_help_shows_all_panels(self) -> None:
        result = runner.invoke(lexictl_app, ["help"])
        assert result.exit_code == 0
        assert "About lexictl" in result.output
        assert "Maintenance Commands" in result.output
        assert "Agent Guidance" in result.output

    def test_help_lists_all_commands(self) -> None:
        result = runner.invoke(lexictl_app, ["help"])
        assert result.exit_code == 0
        for cmd in (
            "init",
            "update",
            "bootstrap",
            "index",
            "validate",
            "status",
            "setup",
            "sweep",
            "iwh clean",
        ):
            assert cmd in result.output, f"Command '{cmd}' missing from help output"

    def test_help_directs_agents_to_lexi(self) -> None:
        result = runner.invoke(lexictl_app, ["help"])
        assert result.exit_code == 0
        assert "lexi --help" in result.output


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


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------


class TestInit:
    """Tests for the wizard-based ``lexictl init`` command."""

    def test_reinit_guard_blocks_existing_project(self, tmp_path: Path) -> None:
        """Init should fail with exit 1 when .lexibrary/ already exists."""
        (tmp_path / ".lexibrary").mkdir()

        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = runner.invoke(lexictl_app, ["init"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 1
        assert "already initialised" in result.output
        assert "setup --update" in result.output

    def test_defaults_creates_skeleton(self, tmp_path: Path) -> None:
        """``--defaults`` should run the wizard in non-interactive mode and create .lexibrary/."""
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = runner.invoke(lexictl_app, ["init", "--defaults"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 0
        assert "Created" in result.output
        assert (tmp_path / ".lexibrary" / "config.yaml").exists()
        assert not (tmp_path / ".lexibrary" / "START_HERE.md").exists()
        # Wizard path does NOT create HANDOFF.md
        assert not (tmp_path / ".lexibrary" / "HANDOFF.md").exists()
        assert (tmp_path / ".lexibrary" / "concepts" / ".gitkeep").exists()
        assert (tmp_path / ".lexibrary" / "stack" / ".gitkeep").exists()
        assert "lexictl update" in result.output

    def test_defaults_reinit_guard_still_works(self, tmp_path: Path) -> None:
        """Re-init guard should also trigger with ``--defaults``."""
        (tmp_path / ".lexibrary").mkdir()

        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = runner.invoke(lexictl_app, ["init", "--defaults"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 1
        assert "already initialised" in result.output


# ---------------------------------------------------------------------------
# Update command tests
# ---------------------------------------------------------------------------


class TestUpdateCommand:
    """Tests for the `lexictl update` command."""

    def test_update_single_file(self, tmp_path: Path) -> None:
        """Update single file calls update_file and reports result."""
        project = _setup_archivist_project(tmp_path)

        mock_result = FileResult(change=ChangeLevel.NEW_FILE)
        mock_update_file = AsyncMock(return_value=mock_result)

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            with patch(
                "lexibrary.archivist.pipeline.update_file",
                mock_update_file,
            ):
                result = runner.invoke(lexictl_app, ["update", "src/main.py"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 0
        assert "Done" in result.output
        assert "new_file" in result.output

    def test_update_directory(self, tmp_path: Path) -> None:
        """Update directory calls update_directory with progress bar."""
        project = _setup_archivist_project(tmp_path)

        mock_stats = UpdateStats(
            files_scanned=5,
            files_unchanged=2,
            files_updated=2,
            files_created=1,
        )
        mock_update_directory = AsyncMock(return_value=mock_stats)

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            with patch(
                "lexibrary.archivist.pipeline.update_directory",
                mock_update_directory,
            ):
                result = runner.invoke(lexictl_app, ["update", "src"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 0
        assert "Updating directory" in result.output
        assert "Files scanned" in result.output
        assert "5" in result.output

    def test_update_project(self, tmp_path: Path) -> None:
        """Update with no args calls update_project and generates TOPOLOGY.md."""
        project = _setup_archivist_project(tmp_path)

        mock_stats = UpdateStats(files_scanned=3, files_unchanged=3)
        mock_update_project = AsyncMock(return_value=mock_stats)

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            with patch(
                "lexibrary.archivist.pipeline.update_project",
                mock_update_project,
            ):
                result = runner.invoke(lexictl_app, ["update"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 0
        assert "Raw topology generated" in result.output
        assert "Files scanned" in result.output

    def test_update_no_project_error(self, tmp_path: Path) -> None:
        """Update outside a project should exit with error."""
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = runner.invoke(lexictl_app, ["update"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 1
        assert "No .lexibrary/" in result.output

    def test_update_single_file_failure(self, tmp_path: Path) -> None:
        """Update single file that fails should exit 1."""
        project = _setup_archivist_project(tmp_path)

        mock_result = FileResult(change=ChangeLevel.INTERFACE_CHANGED, failed=True)
        mock_update_file = AsyncMock(return_value=mock_result)

        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            with patch(
                "lexibrary.archivist.pipeline.update_file",
                mock_update_file,
            ):
                result = runner.invoke(lexictl_app, ["update", "src/main.py"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 1
        assert "Failed" in result.output


# ---------------------------------------------------------------------------
# Validate command tests
# ---------------------------------------------------------------------------


def _setup_validate_project(tmp_path: Path) -> Path:
    """Create a project with known validation issues for testing.

    Sets up:
    - A minimal .lexibrary with config
    - A source file with a matching design file (fresh hash)
    - A concept file with valid frontmatter
    - No deliberate errors (clean baseline)
    """
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
    """Create a project that will produce validation errors.

    Includes a concept file missing mandatory frontmatter fields.
    """
    project = _setup_validate_project(tmp_path)
    # Create a broken concept file (missing required frontmatter fields)
    concepts_dir = project / ".lexibrary" / "concepts"
    concepts_dir.mkdir(parents=True, exist_ok=True)
    (concepts_dir / "BrokenConcept.md").write_text(
        "---\ntitle: Broken\nid: CN-001\n---\n\nMissing aliases, tags, status.\n",
        encoding="utf-8",
    )
    return project


def _setup_validate_project_with_warnings(tmp_path: Path) -> Path:
    """Create a project with stale hash (warning) but no errors.

    Writes a design file whose source_hash does not match the actual source.
    """
    (tmp_path / ".lexibrary").mkdir()
    (tmp_path / ".lexibrary" / "config.yaml").write_text("")
    (tmp_path / ".lexibrary" / "concepts").mkdir(parents=True)
    (tmp_path / "src").mkdir()
    source_content = "def hello():\n    return 42\n"
    (tmp_path / "src" / "main.py").write_text(source_content)

    # Design file with WRONG hash (stale)
    design_dir = tmp_path / ".lexibrary" / "designs" / "src"
    design_dir.mkdir(parents=True, exist_ok=True)
    design_content = """---
description: Main module
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


class TestValidateCommand:
    """Tests for the `lexictl validate` command."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexictl_app, args)
        finally:
            os.chdir(old_cwd)

    def test_validate_clean_exit_0(self, tmp_path: Path) -> None:
        """A clean library with no issues exits with code 0."""
        project = _setup_validate_project(tmp_path)
        # Make an .aindex so aindex_coverage does not fire info
        aindex_dir = project / ".lexibrary" / "designs" / "src"
        aindex_dir.mkdir(parents=True, exist_ok=True)
        from datetime import datetime as _dt

        now = _dt.now().isoformat()
        (aindex_dir / ".aindex").write_text(
            f"""# src/

Source directory

## Child Map

| Name | Type | Description |
| --- | --- | --- |
| `main.py` | file | Main module |

## Local Conventions

(none)

<!-- lexibrary:meta source="src" source_hash="abc" generated="{now}" -->
""",
            encoding="utf-8",
        )
        # Also create root .aindex
        root_aindex_dir = project / ".lexibrary" / "designs"
        root_aindex_dir.mkdir(parents=True, exist_ok=True)
        (root_aindex_dir / ".aindex").write_text(
            f"""# ./

Project root

## Child Map

| Name | Type | Description |
| --- | --- | --- |
| `src/` | dir | Source code |

## Local Conventions

(none)

<!-- lexibrary:meta source="." source_hash="abc" generated="{now}" generator="lexibrary-v2" -->
""",
            encoding="utf-8",
        )
        result = self._invoke(project, ["validate"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "No validation issues found" in result.output  # type: ignore[union-attr]

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
        # Run only hash_freshness check (warning-level) to isolate warnings
        result = self._invoke(project, ["validate", "--check", "hash_freshness"])
        assert result.exit_code == 2  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "warning" in output.lower()

    def test_validate_json_produces_valid_json(self, tmp_path: Path) -> None:
        """The --json flag outputs valid JSON with issues and summary."""
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
        assert "total" in parsed["summary"]

    def test_validate_severity_filter(self, tmp_path: Path) -> None:
        """The --severity flag filters checks by severity level."""
        import json as _json

        project = _setup_validate_project_with_warnings(tmp_path)
        # With --severity error, only error-level checks run (no warnings expected)
        result = self._invoke(project, ["validate", "--severity", "error", "--json"])
        output = result.output  # type: ignore[union-attr]
        parsed = _json.loads(output)
        # No warning or info issues should be present because only error-level checks ran
        assert parsed["summary"]["warning_count"] == 0
        assert parsed["summary"]["info_count"] == 0

    def test_validate_check_runs_single_check(self, tmp_path: Path) -> None:
        """The --check flag runs only the specified check."""
        import json as _json

        project = _setup_validate_project(tmp_path)
        result = self._invoke(project, ["validate", "--check", "concept_frontmatter", "--json"])
        output = result.output  # type: ignore[union-attr]
        parsed = _json.loads(output)
        # All issues (if any) should be from the concept_frontmatter check
        for issue in parsed["issues"]:
            assert issue["check"] == "concept_frontmatter"

    def test_validate_invalid_check_name_shows_available(self, tmp_path: Path) -> None:
        """An invalid --check name shows available checks and exits 1."""
        project = _setup_validate_project(tmp_path)
        result = self._invoke(project, ["validate", "--check", "nonexistent_check"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Available checks" in output or "Unknown check" in output
        # Should list some real check names
        assert "concept_frontmatter" in output
        assert "hash_freshness" in output

    def test_validate_no_project_root(self, tmp_path: Path) -> None:
        """Validate without .lexibrary should exit 1."""
        result = self._invoke(tmp_path, ["validate"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "No .lexibrary/" in result.output  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Status command tests
# ---------------------------------------------------------------------------


def _setup_status_project(tmp_path: Path) -> Path:
    """Create a project with design files, concepts, and stack posts for status tests."""
    (tmp_path / ".lexibrary").mkdir()
    (tmp_path / ".lexibrary" / "config.yaml").write_text("")
    (tmp_path / "src").mkdir()
    return tmp_path


class TestStatusCommand:
    """Tests for the `lexictl status` command."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexictl_app, args)
        finally:
            os.chdir(old_cwd)

    def test_status_output_format(self, tmp_path: Path) -> None:
        """Status shows dashboard with artifact counts and issues."""
        project = _setup_status_project(tmp_path)

        # Create source files and design files
        src_content = "def hello(): pass\n"
        (project / "src" / "main.py").write_text(src_content)
        _create_design_file(project, "src/main.py", src_content)

        # Create concepts
        _create_concept_file(project, "Auth", tags=["security"], status="active")
        _create_concept_file(project, "Cache", tags=["perf"], status="draft")

        # Create stack posts
        _create_stack_post(project, post_id="ST-001", title="Test bug", status="open")
        _create_stack_post(project, post_id="ST-002", title="Fixed issue", status="resolved")

        result = self._invoke(project, ["status"])
        output = result.output  # type: ignore[union-attr]

        # Dashboard header
        assert "Lexibrary Status" in output
        # File counts
        assert "Files:" in output
        assert "1 tracked" in output
        # Concept counts
        assert "Concepts:" in output
        assert "1 active" in output
        assert "1 draft" in output
        # Stack counts
        assert "Stack:" in output
        assert "2 post" in output
        assert "1 resolved" in output
        assert "1 open" in output
        # Issues line
        assert "Issues:" in output
        # Updated line
        assert "Updated:" in output

    def test_status_clean_library_exits_0(self, tmp_path: Path) -> None:
        """Clean library with no validation issues exits with code 0."""
        project = _setup_status_project(tmp_path)
        src_content = "x = 1\n"
        (project / "src" / "main.py").write_text(src_content)
        _create_design_file(project, "src/main.py", src_content)

        result = self._invoke(project, ["status"])
        assert result.exit_code == 0  # type: ignore[union-attr]

    def test_status_empty_library(self, tmp_path: Path) -> None:
        """Empty library shows zero counts and 'Updated: never'."""
        project = _setup_status_project(tmp_path)
        result = self._invoke(project, ["status"])
        output = result.output  # type: ignore[union-attr]
        assert "Files: 0 tracked" in output
        assert "Concepts: 0" in output
        assert "Stack: 0 posts" in output
        assert "Updated: never" in output
        assert result.exit_code == 0  # type: ignore[union-attr]

    def test_status_quiet_healthy(self, tmp_path: Path) -> None:
        """Quiet mode with no issues outputs 'lexictl: library healthy'."""
        project = _setup_status_project(tmp_path)
        result = self._invoke(project, ["status", "--quiet"])
        output = result.output.strip()  # type: ignore[union-attr]
        assert output == "lexictl: library healthy"
        assert result.exit_code == 0  # type: ignore[union-attr]

    def test_status_quiet_with_warnings(self, tmp_path: Path) -> None:
        """Quiet mode with warnings shows count and suggests lexictl validate."""
        project = _setup_status_project(tmp_path)

        # Create a stale design file (source hash mismatch -> warning from hash_freshness)
        original_content = "def hello(): pass\n"
        (project / "src" / "stale.py").write_text("def hello(): return 1\n")
        _create_design_file(project, "src/stale.py", original_content)

        result = self._invoke(project, ["status", "--quiet"])
        output = result.output.strip()  # type: ignore[union-attr]
        # Should mention warnings and suggest lexictl validate
        assert "warning" in output
        assert "lexictl validate" in output
        assert result.exit_code == 2  # type: ignore[union-attr]

    def test_status_stale_files_counted(self, tmp_path: Path) -> None:
        """Status reports stale file count when hashes mismatch."""
        project = _setup_status_project(tmp_path)

        # Create a fresh file
        fresh_content = "x = 1\n"
        (project / "src" / "fresh.py").write_text(fresh_content)
        _create_design_file(project, "src/fresh.py", fresh_content)

        # Create a stale file (content differs from hash in design file)
        original_content = "y = 2\n"
        (project / "src" / "stale.py").write_text("y = 3\n")
        _create_design_file(project, "src/stale.py", original_content)

        result = self._invoke(project, ["status"])
        output = result.output  # type: ignore[union-attr]
        assert "2 tracked" in output
        assert "1 stale" in output

    def test_status_concept_status_breakdown(self, tmp_path: Path) -> None:
        """Status shows concept counts broken down by status."""
        project = _setup_status_project(tmp_path)

        _create_concept_file(project, "Alpha", tags=["a"], status="active")
        _create_concept_file(project, "Beta", tags=["b"], status="active")
        _create_concept_file(project, "Gamma", tags=["c"], status="deprecated")
        _create_concept_file(project, "Delta", tags=["d"], status="draft")

        result = self._invoke(project, ["status"])
        output = result.output  # type: ignore[union-attr]
        assert "2 active" in output
        assert "1 deprecated" in output
        assert "1 draft" in output

    def test_status_no_validate_suggestion_when_clean(self, tmp_path: Path) -> None:
        """When no issues, the 'Run lexictl validate' suggestion is not shown."""
        project = _setup_status_project(tmp_path)
        result = self._invoke(project, ["status"])
        output = result.output  # type: ignore[union-attr]
        assert "lexictl validate" not in output

    def test_status_validate_suggestion_when_issues(self, tmp_path: Path) -> None:
        """When issues exist, suggests running lexictl validate."""
        project = _setup_status_project(tmp_path)

        # Create stale file to generate a warning
        original = "x = 1\n"
        (project / "src" / "s.py").write_text("x = 2\n")
        _create_design_file(project, "src/s.py", original)

        result = self._invoke(project, ["status"])
        output = result.output  # type: ignore[union-attr]
        assert "Run `lexictl validate` for details." in output

    def test_status_exit_code_with_warnings(self, tmp_path: Path) -> None:
        """Status exits with code 2 when warnings exist but no errors."""
        project = _setup_status_project(tmp_path)

        # Stale file -> hash_freshness warning
        original = "a = 1\n"
        (project / "src" / "w.py").write_text("a = 2\n")
        _create_design_file(project, "src/w.py", original)

        result = self._invoke(project, ["status"])
        assert result.exit_code == 2  # type: ignore[union-attr]

    def test_status_no_project_exits_1(self, tmp_path: Path) -> None:
        """Status without .lexibrary should exit 1."""
        result = self._invoke(tmp_path, ["status"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "No .lexibrary/" in result.output  # type: ignore[union-attr]

    def test_status_link_graph_exists_shows_health(self, tmp_path: Path) -> None:
        """When index.db exists with data, status shows link graph health line."""
        import sqlite3

        from lexibrary.linkgraph.schema import ensure_schema

        project = _setup_status_project(tmp_path)
        db_path = project / ".lexibrary" / "index.db"
        conn = sqlite3.connect(str(db_path))
        ensure_schema(conn)

        # Insert artifacts
        conn.execute(
            "INSERT INTO artifacts (id, path, kind, title, status) "
            "VALUES (1, 'src/main.py', 'source', 'Main', 'active')"
        )
        conn.execute(
            "INSERT INTO artifacts (id, path, kind, title, status) "
            "VALUES (2, '.lexibrary/designs/src/main.py.md', 'design', 'Main design', NULL)"
        )
        # Insert a link
        conn.execute(
            "INSERT INTO links (source_id, target_id, link_type) VALUES (2, 1, 'design_source')"
        )
        # Set built_at
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) "
            "VALUES ('built_at', '2026-02-20T10:30:00+00:00')"
        )
        conn.commit()
        conn.close()

        result = self._invoke(project, ["status"])
        output = result.output  # type: ignore[union-attr]
        assert "Link graph:" in output
        assert "2 artifacts" in output
        assert "1 link" in output
        assert "built 2026-02-20T10:30:00+00:00" in output

    def test_status_link_graph_missing_shows_not_built(self, tmp_path: Path) -> None:
        """When index.db does not exist, status shows 'not built' message."""
        project = _setup_status_project(tmp_path)

        result = self._invoke(project, ["status"])
        output = result.output  # type: ignore[union-attr]
        assert "Link graph: not built" in output
        assert "run lexictl update to create" in output

    def test_status_quiet_omits_link_graph(self, tmp_path: Path) -> None:
        """Quiet mode does not include the link graph health line."""
        import sqlite3

        from lexibrary.linkgraph.schema import ensure_schema

        project = _setup_status_project(tmp_path)
        db_path = project / ".lexibrary" / "index.db"
        conn = sqlite3.connect(str(db_path))
        ensure_schema(conn)
        conn.execute(
            "INSERT INTO artifacts (id, path, kind, title, status) "
            "VALUES (1, 'src/main.py', 'source', 'Main', 'active')"
        )
        conn.commit()
        conn.close()

        result = self._invoke(project, ["status", "--quiet"])
        output = result.output  # type: ignore[union-attr]
        assert "Link graph" not in output


# ---------------------------------------------------------------------------
# Setup command tests
# ---------------------------------------------------------------------------


class TestSetupCommand:
    """Tests for the ``lexictl setup`` command."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexictl_app, args)
        finally:
            os.chdir(old_cwd)

    def test_setup_without_update_shows_usage(self, tmp_path: Path) -> None:
        """Running ``setup`` without ``--update`` shows usage instructions and exits 0."""
        result = self._invoke(tmp_path, ["setup"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "setup --update" in output
        assert "lexictl init" in output

    def test_setup_update_no_project_exits_1(self, tmp_path: Path) -> None:
        """``setup --update`` outside a project should exit 1."""
        result = self._invoke(tmp_path, ["setup", "--update"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "No .lexibrary/" in result.output  # type: ignore[union-attr]

    def test_setup_update_empty_env_shows_message(self, tmp_path: Path) -> None:
        """``setup --update`` with no agent environments shows a message and exits 1."""
        (tmp_path / ".lexibrary").mkdir()
        (tmp_path / ".lexibrary" / "config.yaml").write_text(
            "scope_root: .\nagent_environment: []\n"
        )

        result = self._invoke(tmp_path, ["setup", "--update"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "No agent environments configured" in output
        assert "lexictl init" in output

    def test_setup_update_config_persisted_envs(self, tmp_path: Path) -> None:
        """``setup --update`` reads environments from config and generates rules."""
        (tmp_path / ".lexibrary").mkdir()
        (tmp_path / ".lexibrary" / "config.yaml").write_text(
            "scope_root: .\nagent_environment:\n  - claude\n  - cursor\n"
        )

        result = self._invoke(tmp_path, ["setup", "--update"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "claude" in output
        assert "cursor" in output
        assert "Setup complete" in output
        # Verify files were actually created
        assert (tmp_path / "CLAUDE.md").exists()
        assert (tmp_path / ".cursor" / "rules" / "lexibrary.mdc").exists()

    def test_setup_update_explicit_env_arg(self, tmp_path: Path) -> None:
        """``--env`` overrides config-persisted environments."""
        (tmp_path / ".lexibrary").mkdir()
        # Config has claude, but we explicitly request codex
        (tmp_path / ".lexibrary" / "config.yaml").write_text(
            "scope_root: .\nagent_environment:\n  - claude\n"
        )

        result = self._invoke(tmp_path, ["setup", "--update", "--env", "codex"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "codex" in output
        assert "Setup complete" in output
        # Codex file created, Claude file NOT created
        assert (tmp_path / "AGENTS.md").exists()
        assert not (tmp_path / "CLAUDE.md").exists()

    def test_setup_update_explicit_env_overrides_empty_config(self, tmp_path: Path) -> None:
        """``--env`` works even when config has no environments."""
        (tmp_path / ".lexibrary").mkdir()
        (tmp_path / ".lexibrary" / "config.yaml").write_text(
            "scope_root: .\nagent_environment: []\n"
        )

        result = self._invoke(tmp_path, ["setup", "--update", "--env", "claude"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "claude" in output
        assert "Setup complete" in output
        assert (tmp_path / "CLAUDE.md").exists()

    def test_setup_update_no_env_error(self, tmp_path: Path) -> None:
        """``setup --update`` with no config envs and no ``--env`` exits 1."""
        (tmp_path / ".lexibrary").mkdir()
        (tmp_path / ".lexibrary" / "config.yaml").write_text("scope_root: .\n")

        result = self._invoke(tmp_path, ["setup", "--update"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "No agent environments configured" in output

    def test_setup_update_unsupported_env_error(self, tmp_path: Path) -> None:
        """``setup --update --env fake`` exits 1 with unsupported environment error."""
        (tmp_path / ".lexibrary").mkdir()
        (tmp_path / ".lexibrary" / "config.yaml").write_text("scope_root: .\n")

        result = self._invoke(tmp_path, ["setup", "--update", "--env", "nonexistent"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Unsupported" in output
        assert "nonexistent" in output
        # Should show supported environments
        assert "claude" in output

    def test_setup_update_unsupported_env_from_config(self, tmp_path: Path) -> None:
        """Config with unsupported environment exits 1 with clear error."""
        (tmp_path / ".lexibrary").mkdir()
        (tmp_path / ".lexibrary" / "config.yaml").write_text(
            "scope_root: .\nagent_environment:\n  - vscode\n"
        )

        result = self._invoke(tmp_path, ["setup", "--update"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Unsupported" in output
        assert "vscode" in output

    def test_setup_update_flag_generates_rules_and_gitignore(self, tmp_path: Path) -> None:
        """``--update`` generates rules AND adds IWH pattern to gitignore."""
        (tmp_path / ".lexibrary").mkdir()
        (tmp_path / ".lexibrary" / "config.yaml").write_text(
            "scope_root: .\nagent_environment:\n  - claude\n"
        )

        result = self._invoke(tmp_path, ["setup", "--update"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        # Rules generated
        assert "claude" in output
        assert "file(s) written" in output
        # Gitignore updated
        assert ".gitignore" in output
        assert "IWH" in output
        # .gitignore file should exist with IWH pattern
        gitignore = (tmp_path / ".gitignore").read_text()
        assert "**/.iwh" in gitignore

    def test_setup_update_idempotent_gitignore(self, tmp_path: Path) -> None:
        """Running ``setup --update`` twice does not duplicate .gitignore pattern."""
        (tmp_path / ".lexibrary").mkdir()
        (tmp_path / ".lexibrary" / "config.yaml").write_text(
            "scope_root: .\nagent_environment:\n  - claude\n"
        )
        # Pre-existing gitignore with pattern
        (tmp_path / ".gitignore").write_text("**/.iwh\n")

        result = self._invoke(tmp_path, ["setup", "--update"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        # Should NOT report gitignore modification
        assert ".gitignore" not in output
        # Pattern should appear only once
        gitignore = (tmp_path / ".gitignore").read_text()
        assert gitignore.count("**/.iwh") == 1

    def test_setup_update_multiple_envs(self, tmp_path: Path) -> None:
        """``setup --update`` with multiple --env flags generates for all."""
        (tmp_path / ".lexibrary").mkdir()
        (tmp_path / ".lexibrary" / "config.yaml").write_text("scope_root: .\n")

        result = self._invoke(tmp_path, ["setup", "--update", "--env", "claude", "--env", "codex"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "claude" in output
        assert "codex" in output
        assert (tmp_path / "CLAUDE.md").exists()
        assert (tmp_path / "AGENTS.md").exists()


# ---------------------------------------------------------------------------
# Update --changed-only tests
# ---------------------------------------------------------------------------


class TestUpdateChangedOnly:
    """Tests for the ``--changed-only`` flag on ``lexictl update``."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexictl_app, args)
        finally:
            os.chdir(old_cwd)

    def test_changed_only_calls_update_files(self, tmp_path: Path) -> None:
        """--changed-only passes resolved paths to update_files()."""
        project = _setup_archivist_project(tmp_path)
        mock_stats = UpdateStats(files_scanned=1, files_updated=1)
        mock_update_files = AsyncMock(return_value=mock_stats)

        with patch(
            "lexibrary.archivist.pipeline.update_files",
            mock_update_files,
        ):
            result = self._invoke(project, ["update", "--changed-only", "src/main.py"])

        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "1" in output
        assert "Update summary" in output
        mock_update_files.assert_called_once()

    def test_changed_only_multiple_files(self, tmp_path: Path) -> None:
        """--changed-only accepts multiple file paths."""
        project = _setup_archivist_project(tmp_path)
        mock_stats = UpdateStats(files_scanned=2, files_updated=2)
        mock_update_files = AsyncMock(return_value=mock_stats)

        with patch(
            "lexibrary.archivist.pipeline.update_files",
            mock_update_files,
        ):
            result = self._invoke(
                project,
                ["update", "--changed-only", "src/main.py", "--changed-only", "src/utils.py"],
            )

        assert result.exit_code == 0  # type: ignore[union-attr]
        mock_update_files.assert_called_once()
        # Verify two paths were passed
        call_args = mock_update_files.call_args
        assert len(call_args[0][0]) == 2  # first positional arg is the list of paths

    def test_changed_only_mutual_exclusivity(self, tmp_path: Path) -> None:
        """path and --changed-only cannot be used together."""
        project = _setup_archivist_project(tmp_path)
        result = self._invoke(project, ["update", "src/main.py", "--changed-only", "src/utils.py"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "mutually exclusive" in output

    def test_changed_only_with_failures_exits_1(self, tmp_path: Path) -> None:
        """--changed-only exits 1 when files_failed > 0."""
        project = _setup_archivist_project(tmp_path)
        mock_stats = UpdateStats(files_scanned=1, files_failed=1)
        mock_update_files = AsyncMock(return_value=mock_stats)

        with patch(
            "lexibrary.archivist.pipeline.update_files",
            mock_update_files,
        ):
            result = self._invoke(project, ["update", "--changed-only", "src/main.py"])

        assert result.exit_code == 1  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "failed" in output.lower()


# ---------------------------------------------------------------------------
# Sweep command tests
# ---------------------------------------------------------------------------


class TestSweepCommand:
    """Tests for the ``lexictl sweep`` command (inline implementation)."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexictl_app, args)
        finally:
            os.chdir(old_cwd)

    def test_sweep_one_shot_calls_update_project(self, tmp_path: Path) -> None:
        """``lexictl sweep`` calls update_project() directly."""
        (tmp_path / ".lexibrary").mkdir()
        (tmp_path / ".lexibrary" / "config.yaml").write_text("")

        mock_stats = MagicMock(
            files_scanned=5,
            files_updated=1,
            files_created=0,
            files_unchanged=4,
            files_failed=0,
        )
        with patch(
            "lexibrary.archivist.pipeline.update_project",
            new_callable=AsyncMock,
            return_value=mock_stats,
        ):
            result = self._invoke(tmp_path, ["sweep"])

        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Sweep complete" in result.output  # type: ignore[union-attr]

    def test_sweep_one_shot_skip_unchanged(self, tmp_path: Path) -> None:
        """``lexictl sweep`` skips when no changes detected and skip_if_unchanged is True."""
        (tmp_path / ".lexibrary").mkdir()
        (tmp_path / ".lexibrary" / "config.yaml").write_text("")

        with (
            patch("lexibrary.cli.lexictl_app._has_changes", return_value=False),
            patch(
                "lexibrary.config.loader.load_config",
                return_value=MagicMock(
                    sweep=MagicMock(sweep_skip_if_unchanged=True, sweep_interval_seconds=60),
                    llm=MagicMock(),
                ),
            ),
        ):
            result = self._invoke(tmp_path, ["sweep"])

        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "No changes detected" in result.output  # type: ignore[union-attr]

    def test_sweep_watch_runs_loop(self, tmp_path: Path) -> None:
        """``lexictl sweep --watch`` runs the inline watch loop."""
        (tmp_path / ".lexibrary").mkdir()
        (tmp_path / ".lexibrary" / "config.yaml").write_text("")

        mock_stats = MagicMock(
            files_scanned=5,
            files_updated=1,
            files_created=0,
            files_unchanged=4,
            files_failed=0,
        )

        call_count = 0

        def _side_effect(*args: object, **kwargs: object) -> object:
            nonlocal call_count
            call_count += 1
            # After first sweep, simulate shutdown via signal
            import signal as _sig

            _sig.raise_signal(_sig.SIGINT)
            return mock_stats

        with patch(
            "lexibrary.archivist.pipeline.update_project",
            new_callable=AsyncMock,
            side_effect=_side_effect,
        ):
            result = self._invoke(tmp_path, ["sweep", "--watch"])

        assert result.exit_code == 0  # type: ignore[union-attr]
        assert call_count >= 1

    def test_sweep_no_project_exits_1(self, tmp_path: Path) -> None:
        """sweep without .lexibrary/ exits 1."""
        result = self._invoke(tmp_path, ["sweep"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "No .lexibrary/" in result.output  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Setup --hooks tests
# ---------------------------------------------------------------------------


class TestSetupHooks:
    """Tests for the ``--hooks`` flag on ``lexictl setup``."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexictl_app, args)
        finally:
            os.chdir(old_cwd)

    def test_setup_hooks_installs_hook(self, tmp_path: Path) -> None:
        """``setup --hooks`` installs the post-commit hook."""
        (tmp_path / ".lexibrary").mkdir()
        (tmp_path / ".lexibrary" / "config.yaml").write_text("")
        (tmp_path / ".git" / "hooks").mkdir(parents=True)

        result = self._invoke(tmp_path, ["setup", "--hooks"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "installed" in output.lower()
        # Hook file should exist
        assert (tmp_path / ".git" / "hooks" / "post-commit").exists()

    def test_setup_hooks_idempotent(self, tmp_path: Path) -> None:
        """``setup --hooks`` twice reports already installed."""
        (tmp_path / ".lexibrary").mkdir()
        (tmp_path / ".lexibrary" / "config.yaml").write_text("")
        (tmp_path / ".git" / "hooks").mkdir(parents=True)

        # Install once
        self._invoke(tmp_path, ["setup", "--hooks"])
        # Install again
        result = self._invoke(tmp_path, ["setup", "--hooks"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "already installed" in output.lower()

    def test_setup_hooks_no_git_dir(self, tmp_path: Path) -> None:
        """``setup --hooks`` without .git exits 1."""
        (tmp_path / ".lexibrary").mkdir()
        (tmp_path / ".lexibrary" / "config.yaml").write_text("")

        result = self._invoke(tmp_path, ["setup", "--hooks"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "No .git" in output or "no git" in output.lower()


# ---------------------------------------------------------------------------
# Commands without .lexibrary/ should exit 1 with friendly error (lexictl)
# ---------------------------------------------------------------------------


class TestNoProjectRoot:
    def _invoke_without_project(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexictl_app, args)
        finally:
            os.chdir(old_cwd)

    def test_status_no_project_root(self, tmp_path: Path) -> None:
        result = self._invoke_without_project(tmp_path, ["status"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "No .lexibrary/" in result.output  # type: ignore[union-attr]

    def test_validate_no_project_root(self, tmp_path: Path) -> None:
        result = self._invoke_without_project(tmp_path, ["validate"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "lexictl init" in result.output  # type: ignore[union-attr]

    def test_update_no_project_root(self, tmp_path: Path) -> None:
        result = self._invoke_without_project(tmp_path, ["update"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "No .lexibrary/" in result.output  # type: ignore[union-attr]

    def test_sweep_no_project_root(self, tmp_path: Path) -> None:
        result = self._invoke_without_project(tmp_path, ["sweep"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "No .lexibrary/" in result.output  # type: ignore[union-attr]

    def test_index_no_project_root(self, tmp_path: Path) -> None:
        result = self._invoke_without_project(tmp_path, ["index", str(tmp_path)])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "No .lexibrary/" in result.output  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Lexictl index command tests (task 7.3)
# ---------------------------------------------------------------------------


class TestLexictlIndexCommand:
    """Tests for the `lexictl index` command (task 7.3)."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexictl_app, args)
        finally:
            os.chdir(old_cwd)

    def test_index_single_directory(self, tmp_path: Path) -> None:
        """Index a single directory writes a .aindex file."""
        project = _setup_project(tmp_path)
        result = self._invoke(project, ["index", "src"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Wrote" in output
        # Verify .aindex file was created
        aindex_path = project / ".lexibrary" / "designs" / "src" / ".aindex"
        assert aindex_path.exists()

    def test_index_recursive(self, tmp_path: Path) -> None:
        """Index with -r flag recursively indexes directories."""
        project = _setup_project(tmp_path)
        # Create a subdirectory with a file
        (project / "src" / "sub").mkdir()
        (project / "src" / "sub" / "helper.py").write_text("h = 1\n")

        result = self._invoke(project, ["index", "src", "-r"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Indexing complete" in output
        # Should report at least 2 directories indexed
        assert "directories indexed" in output

    def test_index_recursive_long_flag(self, tmp_path: Path) -> None:
        """Index with --recursive flag works."""
        project = _setup_project(tmp_path)
        result = self._invoke(project, ["index", "src", "--recursive"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Indexing complete" in output

    def test_index_requires_project_root(self, tmp_path: Path) -> None:
        """Index without .lexibrary should fail with exit code 1."""
        (tmp_path / "src").mkdir()
        result = self._invoke(tmp_path, ["index", "src"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "No .lexibrary/" in result.output  # type: ignore[union-attr]

    def test_index_summary_output(self, tmp_path: Path) -> None:
        """Index single directory reports the output path."""
        project = _setup_project(tmp_path)
        result = self._invoke(project, ["index", "src"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        # Should mention the .aindex path
        assert ".aindex" in output

    def test_index_nonexistent_directory(self, tmp_path: Path) -> None:
        """Index a nonexistent directory should fail."""
        project = _setup_project(tmp_path)
        result = self._invoke(project, ["index", "nonexistent"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "Directory not found" in result.output  # type: ignore[union-attr]

    def test_index_file_instead_of_directory(self, tmp_path: Path) -> None:
        """Index a file (not a directory) should fail."""
        project = _setup_project(tmp_path)
        result = self._invoke(project, ["index", "src/main.py"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "Not a directory" in result.output  # type: ignore[union-attr]

    def test_index_outside_project_root(self, tmp_path: Path) -> None:
        """Index a directory outside the project root should fail."""
        # Create project in a subdirectory, external dir is sibling
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        _setup_project(project_dir)
        external = tmp_path / "external"
        external.mkdir()
        result = self._invoke(project_dir, ["index", str(external)])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "outside the project root" in result.output  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Lexictl bootstrap command tests (aindex-update TG3)
# ---------------------------------------------------------------------------


class TestLexictlBootstrapCommand:
    """Tests for the `lexictl bootstrap` command."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexictl_app, args)
        finally:
            os.chdir(old_cwd)

    def test_bootstrap_default_scope(self, tmp_path: Path) -> None:
        """Bootstrap with default scope indexes the entire project."""
        project = _setup_project(tmp_path)
        result = self._invoke(project, ["bootstrap"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Bootstrap complete" in output
        assert "Directories indexed" in output
        # Verify .aindex files were created under .lexibrary/designs/
        aindex = project / ".lexibrary" / "designs" / "src" / ".aindex"
        assert aindex.exists()

    def test_bootstrap_scope_override(self, tmp_path: Path) -> None:
        """Bootstrap with --scope indexes only the specified subtree."""
        project = _setup_project(tmp_path)
        # Create another top-level directory
        (project / "lib").mkdir()
        (project / "lib" / "helper.py").write_text("h = 1\n")

        result = self._invoke(project, ["bootstrap", "--scope", "src"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Bootstrap complete" in output
        # src should be indexed
        assert (project / ".lexibrary" / "designs" / "src" / ".aindex").exists()
        # lib should NOT be indexed (outside scope)
        assert not (project / ".lexibrary" / "designs" / "lib" / ".aindex").exists()

    def test_bootstrap_empty_scope(self, tmp_path: Path) -> None:
        """Bootstrap on an empty scope directory still succeeds."""
        project = _setup_project(tmp_path)
        (project / "empty_dir").mkdir()

        result = self._invoke(project, ["bootstrap", "--scope", "empty_dir"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Bootstrap complete" in output
        # Should index the directory (with 0 files)
        assert "Directories indexed: 1" in output

    def test_bootstrap_idempotent(self, tmp_path: Path) -> None:
        """Running bootstrap twice produces the same result."""
        project = _setup_project(tmp_path)

        result1 = self._invoke(project, ["bootstrap"])
        assert result1.exit_code == 0  # type: ignore[union-attr]

        result2 = self._invoke(project, ["bootstrap"])
        assert result2.exit_code == 0  # type: ignore[union-attr]
        output2 = result2.output  # type: ignore[union-attr]
        assert "Bootstrap complete" in output2
        # .aindex file should still exist
        assert (project / ".lexibrary" / "designs" / "src" / ".aindex").exists()

    def test_bootstrap_requires_project_root(self, tmp_path: Path) -> None:
        """Bootstrap without .lexibrary should fail."""
        (tmp_path / "src").mkdir()
        result = self._invoke(tmp_path, ["bootstrap"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "No .lexibrary/" in result.output  # type: ignore[union-attr]

    def test_bootstrap_nonexistent_scope(self, tmp_path: Path) -> None:
        """Bootstrap with a nonexistent --scope should fail."""
        project = _setup_project(tmp_path)
        result = self._invoke(project, ["bootstrap", "--scope", "nonexistent"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "Scope directory not found" in result.output  # type: ignore[union-attr]

    def test_bootstrap_full_and_quick_mutually_exclusive(self, tmp_path: Path) -> None:
        """Passing both --full and --quick should fail."""
        project = _setup_project(tmp_path)
        result = self._invoke(project, ["bootstrap", "--full", "--quick"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "mutually exclusive" in result.output  # type: ignore[union-attr]

    def test_bootstrap_quick_flag(self, tmp_path: Path) -> None:
        """--quick flag is accepted and behaves like default."""
        project = _setup_project(tmp_path)
        result = self._invoke(project, ["bootstrap", "--quick"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Bootstrap complete" in result.output  # type: ignore[union-attr]

    def test_bootstrap_full_flag_runs_llm_enrichment(self, tmp_path: Path) -> None:
        """--full flag triggers LLM-enriched design file generation."""
        from unittest.mock import AsyncMock, patch  # noqa: PLC0415

        project = _setup_project(tmp_path)

        with patch(
            "lexibrary.lifecycle.bootstrap.bootstrap_full",
            new_callable=AsyncMock,
        ) as mock_full:
            from lexibrary.lifecycle.bootstrap import BootstrapStats  # noqa: PLC0415

            mock_full.return_value = BootstrapStats(
                files_scanned=2,
                files_created=2,
            )
            result = self._invoke(project, ["bootstrap", "--full"])

        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "full" in output
        assert "Bootstrap complete" in output
        mock_full.assert_called_once()

    def test_bootstrap_reports_stats(self, tmp_path: Path) -> None:
        """Bootstrap reports directories indexed and files found."""
        project = _setup_project(tmp_path)
        # Create subdirectories for more interesting stats
        (project / "src" / "sub").mkdir()
        (project / "src" / "sub" / "mod.py").write_text("m = 1\n")

        result = self._invoke(project, ["bootstrap"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Directories indexed:" in output
        assert "Files found:" in output

    def test_bootstrap_scope_from_config(self, tmp_path: Path) -> None:
        """Bootstrap uses scope_root from config when --scope is not provided."""
        project = _setup_project(tmp_path)
        # Write config with scope_root set to "src"
        (project / ".lexibrary" / "config.yaml").write_text("scope_root: src\n")
        # Create another directory outside scope
        (project / "lib").mkdir()
        (project / "lib" / "x.py").write_text("x = 1\n")

        result = self._invoke(project, ["bootstrap"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        # src should be indexed
        assert (project / ".lexibrary" / "designs" / "src" / ".aindex").exists()
        # lib should NOT be indexed (outside scope_root from config)
        assert not (project / ".lexibrary" / "designs" / "lib" / ".aindex").exists()

    def test_bootstrap_generates_raw_topology(self, tmp_path: Path) -> None:
        """Bootstrap generates raw topology as Phase 3."""
        project = _setup_project(tmp_path)
        result = self._invoke(project, ["bootstrap"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Phase 3: Generating raw topology" in output
        assert "Raw topology written to .lexibrary/tmp/raw-topology.md" in output
        assert "Run /topology-builder to generate TOPOLOGY.md" in output
        # The raw topology file should exist
        assert (project / ".lexibrary" / "tmp" / "raw-topology.md").exists()

    def test_bootstrap_topology_failure_is_non_fatal(self, tmp_path: Path) -> None:
        """Bootstrap continues even if raw topology generation fails."""
        from unittest.mock import patch  # noqa: PLC0415

        project = _setup_project(tmp_path)

        with patch(
            "lexibrary.archivist.topology.generate_raw_topology",
            side_effect=OSError("disk full"),
        ):
            result = self._invoke(project, ["bootstrap"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Raw topology generation failed (non-fatal)" in output
        assert "Bootstrap complete" in output


# ---------------------------------------------------------------------------
# IWH clean
# ---------------------------------------------------------------------------


class TestIWHClean:
    """Tests for the `lexictl iwh clean` command."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexictl_app, args)
        finally:
            os.chdir(old_cwd)

    def test_help_lists_iwh_subgroup(self) -> None:
        result = runner.invoke(lexictl_app, ["--help"])
        assert result.exit_code == 0
        assert "iwh" in result.output

    def test_clean_removes_all_signals(self, tmp_path: Path) -> None:
        from lexibrary.iwh import write_iwh

        project = _setup_project(tmp_path)
        (project / ".lexibrary" / "src").mkdir(parents=True, exist_ok=True)
        write_iwh(project / ".lexibrary" / "src", author="agent", scope="incomplete", body="wip")
        write_iwh(project / ".lexibrary", author="agent", scope="warning", body="note")

        result = self._invoke(project, ["iwh", "clean", "--all"])
        assert result.exit_code == 0
        assert "2 signal(s)" in result.output
        assert not (project / ".lexibrary" / "src" / ".iwh").exists()
        assert not (project / ".lexibrary" / ".iwh").exists()

    def test_clean_empty_project(self, tmp_path: Path) -> None:
        project = _setup_project(tmp_path)
        result = self._invoke(project, ["iwh", "clean"])
        assert result.exit_code == 0
        assert "No IWH signals to clean" in result.output

    def test_clean_older_than_filter(self, tmp_path: Path) -> None:
        from datetime import UTC, datetime

        from lexibrary.iwh import IWHFile, serialize_iwh

        project = _setup_project(tmp_path)
        (project / ".lexibrary" / "src").mkdir(parents=True, exist_ok=True)

        # Write an old signal (48 hours ago)
        old_iwh = IWHFile(
            author="agent",
            created=datetime(2020, 1, 1, 0, 0, 0, tzinfo=UTC),
            scope="incomplete",
            body="old signal",
        )
        (project / ".lexibrary" / "src" / ".iwh").write_text(
            serialize_iwh(old_iwh), encoding="utf-8"
        )

        # Write a recent signal
        from lexibrary.iwh import write_iwh

        write_iwh(project / ".lexibrary", author="agent", scope="warning", body="new")

        result = self._invoke(project, ["iwh", "clean", "--older-than", "1"])
        assert result.exit_code == 0
        assert "1 signal(s)" in result.output
        # Old signal should be removed, new one preserved
        assert not (project / ".lexibrary" / "src" / ".iwh").exists()
        assert (project / ".lexibrary" / ".iwh").exists()

    def test_clean_shows_removed_count(self, tmp_path: Path) -> None:
        from lexibrary.iwh import write_iwh

        project = _setup_project(tmp_path)
        write_iwh(project / ".lexibrary", author="agent", scope="blocked", body="stuck")

        result = self._invoke(project, ["iwh", "clean", "--all"])
        assert result.exit_code == 0
        assert "Cleaned" in result.output
        assert "1 signal(s)" in result.output
        assert "Removed" in result.output


# ---------------------------------------------------------------------------
# Update --dry-run tests (task 2.11)
# ---------------------------------------------------------------------------


class TestUpdateDryRun:
    """Tests for the ``--dry-run`` flag on ``lexictl update``."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexictl_app, args)
        finally:
            os.chdir(old_cwd)

    def test_dry_run_shows_header(self, tmp_path: Path) -> None:
        """--dry-run shows DRY-RUN MODE header."""
        project = _setup_archivist_project(tmp_path)

        mock_results = [
            (tmp_path / "src" / "main.py", ChangeLevel.NEW_FILE),
        ]
        mock_dry_run = AsyncMock(return_value=mock_results)

        with patch(
            "lexibrary.archivist.pipeline.dry_run_project",
            mock_dry_run,
        ):
            result = self._invoke(project, ["update", "--dry-run"])

        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "DRY-RUN MODE" in output

    def test_dry_run_shows_change_levels(self, tmp_path: Path) -> None:
        """--dry-run displays ChangeLevel per file."""
        project = _setup_archivist_project(tmp_path)

        mock_results = [
            (tmp_path / "src" / "main.py", ChangeLevel.NEW_FILE),
            (tmp_path / "src" / "utils.py", ChangeLevel.CONTENT_CHANGED),
        ]
        mock_dry_run = AsyncMock(return_value=mock_results)

        with patch(
            "lexibrary.archivist.pipeline.dry_run_project",
            mock_dry_run,
        ):
            result = self._invoke(project, ["update", "--dry-run"])

        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "NEW_FILE" in output
        assert "CONTENT_CHANGED" in output
        assert "Summary" in output
        assert "2 files" in output

    def test_dry_run_empty_project(self, tmp_path: Path) -> None:
        """--dry-run with no changes shows appropriate message."""
        project = _setup_archivist_project(tmp_path)

        mock_dry_run = AsyncMock(return_value=[])

        with patch(
            "lexibrary.archivist.pipeline.dry_run_project",
            mock_dry_run,
        ):
            result = self._invoke(project, ["update", "--dry-run"])

        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "No files would change" in output

    def test_dry_run_with_changed_only(self, tmp_path: Path) -> None:
        """--dry-run combined with --changed-only uses dry_run_files()."""
        project = _setup_archivist_project(tmp_path)

        mock_results = [
            (tmp_path / "src" / "main.py", ChangeLevel.CONTENT_CHANGED),
        ]
        mock_dry_run_files = AsyncMock(return_value=mock_results)

        with patch(
            "lexibrary.archivist.pipeline.dry_run_files",
            mock_dry_run_files,
        ):
            result = self._invoke(project, ["update", "--dry-run", "--changed-only", "src/main.py"])

        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "CONTENT_CHANGED" in output
        mock_dry_run_files.assert_called_once()


# ---------------------------------------------------------------------------
# Update --topology tests (task 2.11)
# ---------------------------------------------------------------------------


class TestUpdateTopology:
    """Tests for the ``--topology`` flag on ``lexictl update``."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexictl_app, args)
        finally:
            os.chdir(old_cwd)

    def test_topology_regenerates(self, tmp_path: Path) -> None:
        """--topology calls generate_raw_topology and shows success."""
        project = _setup_archivist_project(tmp_path)

        mock_generate = MagicMock(return_value=project / ".lexibrary" / "tmp" / "raw-topology.md")

        with patch(
            "lexibrary.archivist.topology.generate_raw_topology",
            mock_generate,
        ):
            result = self._invoke(project, ["update", "--topology"])

        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Raw topology written to .lexibrary/tmp/raw-topology.md" in output
        assert "Run /topology-builder to generate TOPOLOGY.md" in output
        mock_generate.assert_called_once()

    def test_topology_mutual_exclusivity_with_changed_only(self, tmp_path: Path) -> None:
        """--topology and --changed-only cannot be used together."""
        project = _setup_archivist_project(tmp_path)
        result = self._invoke(project, ["update", "--topology", "--changed-only", "src/main.py"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "cannot be combined" in output

    def test_topology_mutual_exclusivity_with_path(self, tmp_path: Path) -> None:
        """--topology and path cannot be used together."""
        project = _setup_archivist_project(tmp_path)
        result = self._invoke(project, ["update", "--topology", "src/main.py"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "cannot be combined" in output


# ---------------------------------------------------------------------------
# Update --skeleton tests (task 7.1-7.3)
# ---------------------------------------------------------------------------


class TestUpdateSkeleton:
    """Tests for the ``--skeleton`` flag on ``lexictl update``."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexictl_app, args)
        finally:
            os.chdir(old_cwd)

    def test_skeleton_requires_path(self, tmp_path: Path) -> None:
        """--skeleton without a file path exits with error."""
        project = _setup_archivist_project(tmp_path)
        result = self._invoke(project, ["update", "--skeleton"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "requires a file path" in output

    def test_skeleton_generates_design_file(self, tmp_path: Path) -> None:
        """--skeleton generates a skeleton design file and queues for enrichment."""
        project = _setup_archivist_project(tmp_path)

        mock_result = FileResult(change=ChangeLevel.NEW_FILE)
        mock_generate = MagicMock(return_value=mock_result)
        mock_queue = MagicMock()

        with (
            patch(
                "lexibrary.lifecycle.bootstrap._generate_quick_design",
                mock_generate,
            ),
            patch(
                "lexibrary.lifecycle.queue.queue_for_enrichment",
                mock_queue,
            ),
        ):
            result = self._invoke(project, ["update", "--skeleton", "src/main.py"])

        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Skeleton generated" in output
        mock_generate.assert_called_once()
        mock_queue.assert_called_once()

    def test_skeleton_queues_for_enrichment(self, tmp_path: Path) -> None:
        """--skeleton queues the source file for LLM enrichment."""
        project = _setup_archivist_project(tmp_path)

        mock_result = FileResult(change=ChangeLevel.NEW_FILE)
        mock_generate = MagicMock(return_value=mock_result)
        mock_queue = MagicMock()

        with (
            patch(
                "lexibrary.lifecycle.bootstrap._generate_quick_design",
                mock_generate,
            ),
            patch(
                "lexibrary.lifecycle.queue.queue_for_enrichment",
                mock_queue,
            ),
        ):
            result = self._invoke(project, ["update", "--skeleton", "src/main.py"])

        assert result.exit_code == 0  # type: ignore[union-attr]
        # Verify queue_for_enrichment was called with the project root and source path
        call_args = mock_queue.call_args
        assert call_args is not None
        assert call_args[0][0] == project  # project_root
        assert call_args[0][1].name == "main.py"  # source file

    def test_skeleton_mutual_exclusivity_with_changed_only(self, tmp_path: Path) -> None:
        """--skeleton and --changed-only cannot be used together."""
        project = _setup_archivist_project(tmp_path)
        result = self._invoke(
            project, ["update", "--skeleton", "--changed-only", "src/main.py", "src/main.py"]
        )
        assert result.exit_code == 1  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "cannot be combined" in output

    def test_skeleton_mutual_exclusivity_with_dry_run(self, tmp_path: Path) -> None:
        """--skeleton and --dry-run cannot be used together."""
        project = _setup_archivist_project(tmp_path)
        result = self._invoke(project, ["update", "--skeleton", "--dry-run", "src/main.py"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "cannot be combined" in output

    def test_skeleton_mutual_exclusivity_with_topology(self, tmp_path: Path) -> None:
        """--skeleton and --topology cannot be used together."""
        project = _setup_archivist_project(tmp_path)
        result = self._invoke(project, ["update", "--skeleton", "--topology", "src/main.py"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "cannot be combined" in output

    def test_skeleton_nonexistent_file_error(self, tmp_path: Path) -> None:
        """--skeleton with nonexistent file exits with error."""
        project = _setup_archivist_project(tmp_path)
        result = self._invoke(project, ["update", "--skeleton", "src/nonexistent.py"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "not found" in output.lower()

    def test_skeleton_directory_error(self, tmp_path: Path) -> None:
        """--skeleton with a directory (not a file) exits with error."""
        project = _setup_archivist_project(tmp_path)
        result = self._invoke(project, ["update", "--skeleton", "src"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Not a file" in output

    def test_skeleton_generation_failure(self, tmp_path: Path) -> None:
        """--skeleton reports error when generation fails."""
        project = _setup_archivist_project(tmp_path)

        mock_generate = MagicMock(side_effect=RuntimeError("parse error"))

        with patch(
            "lexibrary.lifecycle.bootstrap._generate_quick_design",
            mock_generate,
        ):
            result = self._invoke(project, ["update", "--skeleton", "src/main.py"])

        assert result.exit_code == 1  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Failed to generate skeleton" in output


# ---------------------------------------------------------------------------
# Validate --ci tests (task 2.11)
# ---------------------------------------------------------------------------


class TestValidateCi:
    """Tests for the ``--ci`` flag on ``lexictl validate``."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexictl_app, args)
        finally:
            os.chdir(old_cwd)

    def test_ci_mode_compact_output(self, tmp_path: Path) -> None:
        """--ci produces compact single-line output."""
        project = _setup_validate_project(tmp_path)
        result = self._invoke(project, ["validate", "--ci"])
        output = result.output.strip()  # type: ignore[union-attr]
        assert output.startswith("lexibrary-validate:")
        assert "errors=" in output
        assert "warnings=" in output
        assert "info=" in output

    def test_ci_mode_clean_exit_0(self, tmp_path: Path) -> None:
        """--ci with clean library exits 0."""
        project = _setup_validate_project(tmp_path)
        result = self._invoke(project, ["validate", "--ci", "--check", "hash_freshness"])
        assert result.exit_code == 0  # type: ignore[union-attr]

    def test_ci_mode_errors_exit_1(self, tmp_path: Path) -> None:
        """--ci with errors exits 1."""
        project = _setup_validate_project_with_errors(tmp_path)
        result = self._invoke(project, ["validate", "--ci"])
        assert result.exit_code == 1  # type: ignore[union-attr]
        output = result.output.strip()  # type: ignore[union-attr]
        assert "errors=" in output


# ---------------------------------------------------------------------------
# Validate --fix tests (task 2.11)
# ---------------------------------------------------------------------------


class TestValidateFix:
    """Tests for the ``--fix`` flag on ``lexictl validate``."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexictl_app, args)
        finally:
            os.chdir(old_cwd)

    def test_fix_reports_non_fixable_as_skip(self, tmp_path: Path) -> None:
        """--fix reports non-fixable issues as [SKIP]."""
        project = _setup_validate_project_with_errors(tmp_path)
        result = self._invoke(project, ["validate", "--fix"])
        output = result.output  # type: ignore[union-attr]
        assert "SKIP" in output
        assert "Fixed" in output

    def test_fix_shows_summary(self, tmp_path: Path) -> None:
        """--fix shows summary line."""
        project = _setup_validate_project(tmp_path)
        result = self._invoke(project, ["validate", "--fix"])
        output = result.output  # type: ignore[union-attr]
        # Even with no issues, check that it still behaves correctly
        assert "Fixed" in output or "No validation issues" not in output

    def test_fix_not_on_lexi_validate(self) -> None:
        """--fix is NOT available on lexi validate (agent CLI)."""
        from lexibrary.cli import lexi_app

        result = runner.invoke(lexi_app, ["validate", "--fix"])
        # Typer should report --fix as unrecognized or show an error
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Update IWH cleanup integration tests (task 3.3)
# ---------------------------------------------------------------------------


class TestUpdateIWHCleanup:
    """Tests for IWH cleanup integration in ``lexictl update``."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexictl_app, args)
        finally:
            os.chdir(old_cwd)

    def test_full_update_runs_iwh_cleanup(self, tmp_path: Path) -> None:
        """Full project update (no path) calls iwh_cleanup and prints summary."""
        project = _setup_archivist_project(tmp_path)

        mock_stats = UpdateStats(files_scanned=2, files_unchanged=2)
        mock_update_project = AsyncMock(return_value=mock_stats)

        # Create a fake cleanup result with expired and orphaned signals
        from lexibrary.iwh.cleanup import CleanedSignal, CleanupResult

        mock_cleanup_result = CleanupResult(
            expired=[
                CleanedSignal(source_dir=Path("src/old"), scope="incomplete", reason="expired"),
            ],
            orphaned=[
                CleanedSignal(source_dir=Path("src/gone"), scope="blocked", reason="orphaned"),
            ],
            kept=1,
        )
        mock_iwh_cleanup = MagicMock(return_value=mock_cleanup_result)

        with (
            patch(
                "lexibrary.archivist.pipeline.update_project",
                mock_update_project,
            ),
            patch(
                "lexibrary.iwh.cleanup.iwh_cleanup",
                mock_iwh_cleanup,
            ),
        ):
            result = self._invoke(project, ["update"])

        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "IWH cleanup" in output
        assert "Expired" in output
        assert "1 signal(s) removed" in output
        assert "Orphaned" in output
        assert "Kept" in output
        mock_iwh_cleanup.assert_called_once()

    def test_full_update_no_cleanup_needed(self, tmp_path: Path) -> None:
        """Full project update with no expired/orphaned signals shows nothing."""
        project = _setup_archivist_project(tmp_path)

        mock_stats = UpdateStats(files_scanned=2, files_unchanged=2)
        mock_update_project = AsyncMock(return_value=mock_stats)

        from lexibrary.iwh.cleanup import CleanupResult

        mock_cleanup_result = CleanupResult(kept=3)
        mock_iwh_cleanup = MagicMock(return_value=mock_cleanup_result)

        with (
            patch(
                "lexibrary.archivist.pipeline.update_project",
                mock_update_project,
            ),
            patch(
                "lexibrary.iwh.cleanup.iwh_cleanup",
                mock_iwh_cleanup,
            ),
        ):
            result = self._invoke(project, ["update"])

        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        # No cleanup section printed when nothing was cleaned
        assert "IWH cleanup" not in output
        mock_iwh_cleanup.assert_called_once()

    def test_single_file_update_skips_iwh_cleanup(self, tmp_path: Path) -> None:
        """Single-file update does NOT run IWH cleanup."""
        project = _setup_archivist_project(tmp_path)

        mock_result = FileResult(change=ChangeLevel.NEW_FILE)
        mock_update_file = AsyncMock(return_value=mock_result)
        mock_iwh_cleanup = MagicMock()

        with (
            patch(
                "lexibrary.archivist.pipeline.update_file",
                mock_update_file,
            ),
            patch(
                "lexibrary.iwh.cleanup.iwh_cleanup",
                mock_iwh_cleanup,
            ),
        ):
            result = self._invoke(project, ["update", "src/main.py"])

        assert result.exit_code == 0  # type: ignore[union-attr]
        mock_iwh_cleanup.assert_not_called()

    def test_directory_update_skips_iwh_cleanup(self, tmp_path: Path) -> None:
        """Directory-scoped update does NOT run IWH cleanup."""
        project = _setup_archivist_project(tmp_path)

        mock_stats = UpdateStats(files_scanned=2, files_unchanged=2)
        mock_update_directory = AsyncMock(return_value=mock_stats)
        mock_iwh_cleanup = MagicMock()

        with (
            patch(
                "lexibrary.archivist.pipeline.update_directory",
                mock_update_directory,
            ),
            patch(
                "lexibrary.iwh.cleanup.iwh_cleanup",
                mock_iwh_cleanup,
            ),
        ):
            result = self._invoke(project, ["update", "src"])

        assert result.exit_code == 0  # type: ignore[union-attr]
        mock_iwh_cleanup.assert_not_called()

    def test_changed_only_update_skips_iwh_cleanup(self, tmp_path: Path) -> None:
        """--changed-only update does NOT run IWH cleanup."""
        project = _setup_archivist_project(tmp_path)

        mock_stats = UpdateStats(files_scanned=1, files_unchanged=1)
        mock_update_files = AsyncMock(return_value=mock_stats)
        mock_iwh_cleanup = MagicMock()

        with (
            patch(
                "lexibrary.archivist.pipeline.update_files",
                mock_update_files,
            ),
            patch(
                "lexibrary.iwh.cleanup.iwh_cleanup",
                mock_iwh_cleanup,
            ),
        ):
            result = self._invoke(project, ["update", "--changed-only", "src/main.py"])

        assert result.exit_code == 0  # type: ignore[union-attr]
        mock_iwh_cleanup.assert_not_called()


# ---------------------------------------------------------------------------
# IWH clean config-aware TTL and --all tests (task 3.4)
# ---------------------------------------------------------------------------


class TestIWHCleanConfigAware:
    """Tests for config-aware TTL default and ``--all`` flag on ``lexictl iwh clean``."""

    def _invoke(self, tmp_path: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return runner.invoke(lexictl_app, args)
        finally:
            os.chdir(old_cwd)

    def test_clean_uses_config_ttl_by_default(self, tmp_path: Path) -> None:
        """Without --older-than or --all, clean uses config.iwh.ttl_hours."""
        from datetime import UTC, datetime, timedelta

        from lexibrary.iwh import IWHFile, serialize_iwh, write_iwh

        project = _setup_project(tmp_path)

        # Set config with a short TTL (1 hour)
        (project / ".lexibrary" / "config.yaml").write_text(
            "iwh:\n  ttl_hours: 1\n", encoding="utf-8"
        )

        # Write an old signal (2 hours ago) — should be removed
        (project / ".lexibrary" / "src").mkdir(parents=True, exist_ok=True)
        old_iwh = IWHFile(
            author="agent",
            created=datetime.now(tz=UTC) - timedelta(hours=2),
            scope="incomplete",
            body="old signal",
        )
        (project / ".lexibrary" / "src" / ".iwh").write_text(
            serialize_iwh(old_iwh), encoding="utf-8"
        )

        # Write a recent signal (just now) — should be kept
        write_iwh(project / ".lexibrary", author="agent", scope="warning", body="new")

        result = self._invoke(project, ["iwh", "clean"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "1 signal(s)" in output
        # Old signal removed, new one preserved
        assert not (project / ".lexibrary" / "src" / ".iwh").exists()
        assert (project / ".lexibrary" / ".iwh").exists()

    def test_clean_default_ttl_keeps_young_signals(self, tmp_path: Path) -> None:
        """With default config TTL (72h), recently created signals are kept."""
        from lexibrary.iwh import write_iwh

        project = _setup_project(tmp_path)
        # Default config.yaml (empty) => ttl_hours defaults to 72
        (project / ".lexibrary" / "config.yaml").write_text("", encoding="utf-8")

        # Write a fresh signal
        write_iwh(project / ".lexibrary", author="agent", scope="warning", body="fresh")

        result = self._invoke(project, ["iwh", "clean"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "0 signal(s)" in output
        # Signal should still exist
        assert (project / ".lexibrary" / ".iwh").exists()

    def test_clean_all_bypasses_ttl(self, tmp_path: Path) -> None:
        """--all removes all signals regardless of age."""
        from lexibrary.iwh import write_iwh

        project = _setup_project(tmp_path)
        (project / ".lexibrary" / "config.yaml").write_text(
            "iwh:\n  ttl_hours: 9999\n", encoding="utf-8"
        )

        # Write a fresh signal (well within TTL)
        (project / ".lexibrary" / "src").mkdir(parents=True, exist_ok=True)
        write_iwh(project / ".lexibrary" / "src", author="agent", scope="incomplete", body="wip")
        write_iwh(project / ".lexibrary", author="agent", scope="warning", body="note")

        result = self._invoke(project, ["iwh", "clean", "--all"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "2 signal(s)" in output
        assert not (project / ".lexibrary" / "src" / ".iwh").exists()
        assert not (project / ".lexibrary" / ".iwh").exists()

    def test_clean_older_than_overrides_config_ttl(self, tmp_path: Path) -> None:
        """--older-than takes precedence over config TTL."""
        from datetime import UTC, datetime, timedelta

        from lexibrary.iwh import IWHFile, serialize_iwh, write_iwh

        project = _setup_project(tmp_path)
        # Config TTL is very high — signals would normally be kept
        (project / ".lexibrary" / "config.yaml").write_text(
            "iwh:\n  ttl_hours: 9999\n", encoding="utf-8"
        )

        # Write a 5-hour-old signal
        (project / ".lexibrary" / "src").mkdir(parents=True, exist_ok=True)
        old_iwh = IWHFile(
            author="agent",
            created=datetime.now(tz=UTC) - timedelta(hours=5),
            scope="incomplete",
            body="old signal",
        )
        (project / ".lexibrary" / "src" / ".iwh").write_text(
            serialize_iwh(old_iwh), encoding="utf-8"
        )

        # Write a fresh signal
        write_iwh(project / ".lexibrary", author="agent", scope="warning", body="new")

        # --older-than 1 should override the 9999h config TTL
        result = self._invoke(project, ["iwh", "clean", "--older-than", "1"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "1 signal(s)" in output
        assert not (project / ".lexibrary" / "src" / ".iwh").exists()
        assert (project / ".lexibrary" / ".iwh").exists()

    def test_clean_all_on_empty_project(self, tmp_path: Path) -> None:
        """--all on a project with no signals shows 'no signals'."""
        project = _setup_project(tmp_path)
        result = self._invoke(project, ["iwh", "clean", "--all"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "No IWH signals to clean" in result.output  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Update --unlimited tests (task 7.1-7.3)
# ---------------------------------------------------------------------------


class TestUpdateUnlimited:
    """Tests for the ``--unlimited`` flag on ``lexictl update``."""

    @staticmethod
    def _invoke(project: Path, args: list[str]) -> object:
        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            return runner.invoke(lexictl_app, args)
        finally:
            os.chdir(old_cwd)

    def test_unlimited_default_false(self, tmp_path: Path) -> None:
        """--unlimited defaults to False; update_project receives unlimited=False."""
        project = _setup_archivist_project(tmp_path)

        mock_stats = UpdateStats(files_scanned=1, files_unchanged=1)
        mock_update_project = AsyncMock(return_value=mock_stats)

        with patch(
            "lexibrary.archivist.pipeline.update_project",
            mock_update_project,
        ):
            result = self._invoke(project, ["update"])

        assert result.exit_code == 0  # type: ignore[union-attr]
        # Verify unlimited=False was passed
        _, kwargs = mock_update_project.call_args
        assert kwargs.get("unlimited") is False

    def test_unlimited_flag_accepted(self, tmp_path: Path) -> None:
        """--unlimited flag is accepted and passed through to update_project."""
        project = _setup_archivist_project(tmp_path)

        mock_stats = UpdateStats(files_scanned=1, files_unchanged=1)
        mock_update_project = AsyncMock(return_value=mock_stats)

        with patch(
            "lexibrary.archivist.pipeline.update_project",
            mock_update_project,
        ):
            result = self._invoke(project, ["update", "--unlimited"])

        assert result.exit_code == 0  # type: ignore[union-attr]
        _, kwargs = mock_update_project.call_args
        assert kwargs.get("unlimited") is True

    def test_unlimited_single_file(self, tmp_path: Path) -> None:
        """--unlimited is threaded through to update_file for single file update."""
        project = _setup_archivist_project(tmp_path)

        mock_result = FileResult(change=ChangeLevel.NEW_FILE)
        mock_update_file = AsyncMock(return_value=mock_result)

        with patch(
            "lexibrary.archivist.pipeline.update_file",
            mock_update_file,
        ):
            result = self._invoke(project, ["update", "--unlimited", "src/main.py"])

        assert result.exit_code == 0  # type: ignore[union-attr]
        _, kwargs = mock_update_file.call_args
        assert kwargs.get("unlimited") is True

    def test_unlimited_changed_only(self, tmp_path: Path) -> None:
        """--unlimited is threaded through to update_files for --changed-only."""
        project = _setup_archivist_project(tmp_path)

        mock_stats = UpdateStats(files_scanned=1, files_unchanged=1)
        mock_update_files = AsyncMock(return_value=mock_stats)

        with patch(
            "lexibrary.archivist.pipeline.update_files",
            mock_update_files,
        ):
            result = self._invoke(
                project, ["update", "--unlimited", "--changed-only", "src/main.py"]
            )

        assert result.exit_code == 0  # type: ignore[union-attr]
        _, kwargs = mock_update_files.call_args
        assert kwargs.get("unlimited") is True

    def test_unlimited_directory(self, tmp_path: Path) -> None:
        """--unlimited is threaded through to update_directory."""
        project = _setup_archivist_project(tmp_path)

        mock_stats = UpdateStats(files_scanned=1, files_unchanged=1)
        mock_update_directory = AsyncMock(return_value=mock_stats)

        with patch(
            "lexibrary.archivist.pipeline.update_directory",
            mock_update_directory,
        ):
            result = self._invoke(project, ["update", "--unlimited", "src"])

        assert result.exit_code == 0  # type: ignore[union-attr]
        _, kwargs = mock_update_directory.call_args
        assert kwargs.get("unlimited") is True

    def test_unlimited_skeleton_mutual_exclusion(self, tmp_path: Path) -> None:
        """--unlimited and --skeleton cannot be used together."""
        project = _setup_archivist_project(tmp_path)

        result = self._invoke(project, ["update", "--unlimited", "--skeleton", "src/main.py"])

        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "--skeleton cannot be combined" in result.output  # type: ignore[union-attr]

    def test_unlimited_passes_to_build_client_registry(self, tmp_path: Path) -> None:
        """--unlimited is passed to build_client_registry."""
        project = _setup_archivist_project(tmp_path)

        mock_stats = UpdateStats(files_scanned=1, files_unchanged=1)
        mock_update_project = AsyncMock(return_value=mock_stats)
        mock_build_registry = MagicMock(return_value=MagicMock())

        with (
            patch(
                "lexibrary.archivist.pipeline.update_project",
                mock_update_project,
            ),
            patch(
                "lexibrary.llm.client_registry.build_client_registry",
                mock_build_registry,
            ),
        ):
            result = self._invoke(project, ["update", "--unlimited"])

        assert result.exit_code == 0  # type: ignore[union-attr]
        _, kwargs = mock_build_registry.call_args
        assert kwargs.get("unlimited") is True
