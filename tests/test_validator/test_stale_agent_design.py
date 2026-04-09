"""Unit tests for the stale_agent_design validation check.

Tests that agent- and maintainer-edited design files with stale source_hash
values are detected, while archivist-edited files and fresh files are not
flagged.
"""

from __future__ import annotations

from pathlib import Path

from lexibrary.utils.hashing import hash_file
from lexibrary.validator import AVAILABLE_CHECKS, validate_library
from lexibrary.validator.checks import check_stale_agent_design

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DESIGN_FILE_TEMPLATE = """\
---
description: {description}
id: DS-001
updated_by: {updated_by}
---

# {source_path}

## Interface Contract

```python
def example() -> None: ...
```

## Dependencies

(none)

## Dependents

(none)

## Wikilinks

(none)

<!-- lexibrary:meta
source: {source_path}
source_hash: {source_hash}
design_hash: deadbeef
generated: 2026-01-01T12:00:00
generator: lexibrary-v2
-->
"""


def _write_design_file(
    lexibrary_dir: Path,
    source_path: str,
    *,
    source_hash: str = "abc123",
    updated_by: str = "archivist",
    description: str = "Test design file",
) -> Path:
    """Write a design file to the expected mirror path."""
    design_path = lexibrary_dir / "designs" / f"{source_path}.md"
    design_path.parent.mkdir(parents=True, exist_ok=True)
    design_path.write_text(
        _DESIGN_FILE_TEMPLATE.format(
            description=description,
            source_path=source_path,
            source_hash=source_hash,
            updated_by=updated_by,
        ),
        encoding="utf-8",
    )
    return design_path


def _write_config(project_root: Path) -> None:
    """Write a minimal config.yaml so validate_library can load config."""
    config_dir = project_root / ".lexibrary"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.yaml"
    config_path.write_text("scope_root: .\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCheckStaleAgentDesign:
    """Tests for check_stale_agent_design."""

    def test_agent_edited_current_hash_passes(self, tmp_path: Path) -> None:
        """Agent-edited file with matching source_hash produces no issues."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()

        # Create source file
        src_dir = project_root / "src"
        src_dir.mkdir()
        source_file = src_dir / "fresh.py"
        source_file.write_text("def hello(): pass\n", encoding="utf-8")

        # Compute current hash and write matching design file
        current_hash = hash_file(source_file)
        _write_design_file(
            lexibrary_dir,
            "src/fresh.py",
            source_hash=current_hash,
            updated_by="agent",
        )

        issues = check_stale_agent_design(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_agent_edited_stale_hash_produces_warning(self, tmp_path: Path) -> None:
        """Agent-edited file with mismatched source_hash produces a warning."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()

        # Create source file
        src_dir = project_root / "src"
        src_dir.mkdir()
        source_file = src_dir / "stale.py"
        source_file.write_text("def updated(): pass\n", encoding="utf-8")

        # Write design file with wrong hash
        _write_design_file(
            lexibrary_dir,
            "src/stale.py",
            source_hash="old_stale_hash_value",
            updated_by="agent",
        )

        issues = check_stale_agent_design(project_root, lexibrary_dir)
        assert len(issues) == 1
        issue = issues[0]
        assert issue.severity == "warning"
        assert issue.check == "stale_agent_design"
        assert "agent" in issue.message.lower()
        assert "stale" in issue.message.lower()
        assert "lexictl curate" in issue.suggestion

    def test_maintainer_edited_stale_hash_produces_warning(self, tmp_path: Path) -> None:
        """Maintainer-edited file with mismatched source_hash produces a warning."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()

        # Create source file
        src_dir = project_root / "src"
        src_dir.mkdir()
        source_file = src_dir / "maintained.py"
        source_file.write_text("class Config: pass\n", encoding="utf-8")

        # Write design file with wrong hash
        _write_design_file(
            lexibrary_dir,
            "src/maintained.py",
            source_hash="old_maintainer_hash",
            updated_by="maintainer",
        )

        issues = check_stale_agent_design(project_root, lexibrary_dir)
        assert len(issues) == 1
        issue = issues[0]
        assert issue.severity == "warning"
        assert issue.check == "stale_agent_design"
        assert "maintainer" in issue.message
        assert "lexictl curate" in issue.suggestion

    def test_non_agent_file_not_checked(self, tmp_path: Path) -> None:
        """Files with updated_by='archivist' are not flagged by this check."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()

        # Create source file
        src_dir = project_root / "src"
        src_dir.mkdir()
        source_file = src_dir / "auto.py"
        source_file.write_text("x = 1\n", encoding="utf-8")

        # Write stale archivist-edited design file
        _write_design_file(
            lexibrary_dir,
            "src/auto.py",
            source_hash="wrong_hash",
            updated_by="archivist",
        )

        issues = check_stale_agent_design(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_bootstrap_quick_not_checked(self, tmp_path: Path) -> None:
        """Files with updated_by='bootstrap-quick' are not flagged."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()

        src_dir = project_root / "src"
        src_dir.mkdir()
        source_file = src_dir / "boot.py"
        source_file.write_text("y = 2\n", encoding="utf-8")

        _write_design_file(
            lexibrary_dir,
            "src/boot.py",
            source_hash="wrong_hash",
            updated_by="bootstrap-quick",
        )

        issues = check_stale_agent_design(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_missing_source_file_skipped(self, tmp_path: Path) -> None:
        """When source file doesn't exist, the check skips it."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()

        # Design file exists but source does not
        _write_design_file(
            lexibrary_dir,
            "src/gone.py",
            source_hash="whatever",
            updated_by="agent",
        )

        issues = check_stale_agent_design(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_no_design_files(self, tmp_path: Path) -> None:
        """No design files means no issues."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()

        issues = check_stale_agent_design(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_no_designs_directory(self, tmp_path: Path) -> None:
        """Missing designs directory returns empty list."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()
        # Do NOT create the designs/ subdirectory

        issues = check_stale_agent_design(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_mixed_files(self, tmp_path: Path) -> None:
        """Multiple design files: only agent/maintainer stale files flagged."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()

        src_dir = project_root / "src"
        src_dir.mkdir()

        # 1. Fresh agent-edited file (should pass)
        fresh_agent = src_dir / "fresh_agent.py"
        fresh_agent.write_text("pass\n", encoding="utf-8")
        _write_design_file(
            lexibrary_dir,
            "src/fresh_agent.py",
            source_hash=hash_file(fresh_agent),
            updated_by="agent",
        )

        # 2. Stale agent-edited file (should warn)
        stale_agent = src_dir / "stale_agent.py"
        stale_agent.write_text("changed\n", encoding="utf-8")
        _write_design_file(
            lexibrary_dir,
            "src/stale_agent.py",
            source_hash="old_hash",
            updated_by="agent",
        )

        # 3. Stale archivist-edited file (should NOT be flagged)
        stale_archivist = src_dir / "stale_archivist.py"
        stale_archivist.write_text("also changed\n", encoding="utf-8")
        _write_design_file(
            lexibrary_dir,
            "src/stale_archivist.py",
            source_hash="old_hash",
            updated_by="archivist",
        )

        # 4. Stale maintainer-edited file (should warn)
        stale_maint = src_dir / "stale_maint.py"
        stale_maint.write_text("new code\n", encoding="utf-8")
        _write_design_file(
            lexibrary_dir,
            "src/stale_maint.py",
            source_hash="old_hash",
            updated_by="maintainer",
        )

        issues = check_stale_agent_design(project_root, lexibrary_dir)
        assert len(issues) == 2
        checks = {i.check for i in issues}
        assert checks == {"stale_agent_design"}
        # Verify both are warnings
        assert all(i.severity == "warning" for i in issues)


class TestStaleAgentDesignRegistered:
    """Verify the check is registered and runs in full validation."""

    def test_registered_in_available_checks(self) -> None:
        """stale_agent_design is registered in AVAILABLE_CHECKS."""
        assert "stale_agent_design" in AVAILABLE_CHECKS
        fn, severity = AVAILABLE_CHECKS["stale_agent_design"]
        assert fn is check_stale_agent_design
        assert severity == "warning"

    def test_runs_in_full_validation(self, tmp_path: Path) -> None:
        """stale_agent_design runs when validate_library is called."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()
        _write_config(project_root)

        # Create a stale agent-edited design file
        src_dir = project_root / "src"
        src_dir.mkdir()
        source_file = src_dir / "target.py"
        source_file.write_text("x = 42\n", encoding="utf-8")
        _write_design_file(
            lexibrary_dir,
            "src/target.py",
            source_hash="wrong_hash",
            updated_by="agent",
        )

        report = validate_library(
            project_root,
            lexibrary_dir,
            check_filter="stale_agent_design",
        )
        stale_issues = [i for i in report.issues if i.check == "stale_agent_design"]
        assert len(stale_issues) == 1
        assert stale_issues[0].severity == "warning"
