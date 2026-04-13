"""Integration tests for validate_library() orchestrator.

Tests the full validation pipeline including healthy projects, mixed issues,
empty libraries, severity filtering, and check filtering.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from lexibrary.utils.hashing import hash_file
from lexibrary.validator import AVAILABLE_CHECKS, ValidationReport, validate_library

# ---------------------------------------------------------------------------
# Helpers -- create valid artifacts on disk
# ---------------------------------------------------------------------------


def _write_config(
    project_root: Path,
    *,
    scope_roots: list[str] | None = None,
    **overrides: object,
) -> None:
    """Write a minimal config.yaml.

    ``scope_roots`` defaults to ``["."]`` (single project-root scope) — the
    multi-root migration's default shape. Pass an explicit list to exercise
    multi-root behaviour, e.g. ``scope_roots=["src/", "baml_src/"]``.
    """
    config_dir = project_root / ".lexibrary"
    config_dir.mkdir(parents=True, exist_ok=True)
    declared = scope_roots if scope_roots is not None else ["."]
    lines = ["scope_roots:"]
    for path in declared:
        lines.append(f"  - path: {path}")
    if "token_budgets" in overrides:
        budgets = overrides["token_budgets"]
        lines.append("token_budgets:")
        for key, val in budgets.items():  # type: ignore[union-attr]
            lines.append(f"  {key}: {val}")
    config_path = config_dir / "config.yaml"
    config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_design_file(
    lexibrary_dir: Path,
    source_path: str,
    source_hash: str = "abc123",
    *,
    wikilinks: list[str] | None = None,
) -> Path:
    """Write a design file to the expected mirror path."""
    design_path = lexibrary_dir / "designs" / f"{source_path}.md"
    design_path.parent.mkdir(parents=True, exist_ok=True)

    wiki_section = "(none)"
    if wikilinks:
        wiki_section = "\n".join(f"- [[{link}]]" for link in wikilinks)

    now = datetime.now().isoformat()
    content = f"""\
---
description: Test design file
id: DS-001
updated_by: archivist
status: active
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

{wiki_section}

<!-- lexibrary:meta
source: {source_path}
source_hash: {source_hash}
design_hash: deadbeef
generated: {now}
generator: test
-->
"""
    design_path.write_text(content, encoding="utf-8")
    return design_path


def _write_concept_file(
    lexibrary_dir: Path,
    title: str,
    *,
    aliases: list[str] | None = None,
    tags: list[str] | None = None,
    status: str = "active",
    superseded_by: str | None = None,
) -> Path:
    """Write a concept file under .lexibrary/concepts/."""
    concepts_dir = lexibrary_dir / "concepts"
    concepts_dir.mkdir(parents=True, exist_ok=True)

    aliases_yaml = "[" + ", ".join(aliases or [title.lower()]) + "]"
    tags_yaml = "[" + ", ".join(tags or ["general"]) + "]"
    superseded_line = f"superseded_by: {superseded_by}" if superseded_by else ""

    filename = title.lower().replace(" ", "-") + ".md"
    concept_path = concepts_dir / filename
    concept_path.write_text(
        f"""\
---
title: {title}
id: CN-001
aliases: {aliases_yaml}
tags: {tags_yaml}
status: {status}
{superseded_line}
---

{title} is a concept used in the system.
""",
        encoding="utf-8",
    )
    return concept_path


def _write_source_file(project_root: Path, rel_path: str, content: str = "# source\n") -> Path:
    """Write a source file at the given relative path."""
    path = project_root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _write_aindex(project_root: Path, lexibrary_dir: Path, rel_dir: str) -> Path:
    """Write a minimal .aindex file for a directory."""
    from lexibrary.utils.paths import aindex_path

    aindex = aindex_path(project_root, project_root / rel_dir)
    aindex.parent.mkdir(parents=True, exist_ok=True)
    aindex.write_text(
        f"# .aindex for {rel_dir}\n\nNo entries yet.\n",
        encoding="utf-8",
    )
    return aindex


def _setup_healthy_project(tmp_path: Path) -> tuple[Path, Path]:
    """Create a healthy project with no validation issues.

    Returns (project_root, lexibrary_dir).
    """
    project_root = tmp_path
    lexibrary_dir = project_root / ".lexibrary"
    lexibrary_dir.mkdir()

    # Write config
    _write_config(project_root)

    # Create a source file and matching design file with correct hash
    source = _write_source_file(project_root, "src/app.py", "def main(): pass\n")
    current_hash = hash_file(source)
    _write_design_file(
        lexibrary_dir,
        "src/app.py",
        source_hash=current_hash,
        wikilinks=["Application"],
    )

    # Create a valid concept that is referenced in the design file
    _write_concept_file(lexibrary_dir, "Application", aliases=["app"])

    # Create .aindex files so aindex_coverage check passes
    _write_aindex(project_root, lexibrary_dir, ".")
    _write_aindex(project_root, lexibrary_dir, "src")

    return project_root, lexibrary_dir


# ---------------------------------------------------------------------------
# Healthy project -- no issues
# ---------------------------------------------------------------------------


class TestHealthyProject:
    """Validate that a well-formed project produces no issues."""

    def test_healthy_project_returns_empty_report(self, tmp_path: Path) -> None:
        """A properly set up project should have zero validation issues."""
        project_root, lexibrary_dir = _setup_healthy_project(tmp_path)

        report = validate_library(project_root, lexibrary_dir)

        assert isinstance(report, ValidationReport)
        assert len(report.issues) == 0
        assert report.exit_code() == 0
        assert not report.has_errors()
        assert not report.has_warnings()


# ---------------------------------------------------------------------------
# Mixed issues -- errors + warnings + info
# ---------------------------------------------------------------------------


class TestMixedIssues:
    """Validate that a project with mixed issues returns all severities."""

    def test_mixed_issues_produces_errors_warnings_info(self, tmp_path: Path) -> None:
        """A project with broken wikilinks, stale hashes, and missing
        aindex should produce issues at all severity levels."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()
        _write_config(project_root)

        # ERROR: Design file with broken wikilink
        source = _write_source_file(project_root, "src/broken.py", "# broken\n")
        current_hash = hash_file(source)
        _write_design_file(
            lexibrary_dir,
            "src/broken.py",
            source_hash=current_hash,
            wikilinks=["NonExistentConcept"],
        )
        # Create concepts dir so resolver can load
        (lexibrary_dir / "concepts").mkdir(parents=True, exist_ok=True)

        # WARNING: Stale design file (hash mismatch)
        _write_source_file(project_root, "src/stale.py", "# stale\n")
        _write_design_file(
            lexibrary_dir,
            "src/stale.py",
            source_hash="wrong_hash_value",
        )

        # INFO: Directory without aindex coverage
        _write_source_file(project_root, "src/subdir/module.py", "# module\n")

        report = validate_library(project_root, lexibrary_dir)

        assert report.has_errors()
        assert report.has_warnings()
        assert report.exit_code() == 1  # errors present -> exit 1

        # Check that we have all three severity levels
        severities = {issue.severity for issue in report.issues}
        assert "error" in severities
        assert "warning" in severities
        assert "info" in severities

    def test_warnings_only_exit_code_2(self, tmp_path: Path) -> None:
        """When only warnings exist (no errors), exit code should be 2."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()
        _write_config(project_root)
        (lexibrary_dir / "concepts").mkdir(parents=True, exist_ok=True)

        # WARNING: Stale design file (hash mismatch) but source exists
        _write_source_file(project_root, "src/stale.py", "# stale\n")
        _write_design_file(
            lexibrary_dir,
            "src/stale.py",
            source_hash="definitely_wrong_hash",
        )

        # Run with severity_filter=warning to skip info checks
        report = validate_library(project_root, lexibrary_dir, severity_filter="warning")

        assert not report.has_errors()
        assert report.has_warnings()
        assert report.exit_code() == 2


# ---------------------------------------------------------------------------
# Empty library -- graceful handling
# ---------------------------------------------------------------------------


class TestEmptyLibrary:
    """Validate that an empty .lexibrary directory is handled gracefully."""

    def test_empty_library_returns_empty_report(self, tmp_path: Path) -> None:
        """An empty .lexibrary with no artifacts should produce no issues
        (except possibly aindex_coverage info)."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()
        _write_config(project_root)

        # Run only error + warning checks to avoid aindex_coverage noise
        report = validate_library(project_root, lexibrary_dir, severity_filter="warning")

        assert isinstance(report, ValidationReport)
        assert len(report.issues) == 0
        assert report.exit_code() == 0

    def test_empty_library_full_run_succeeds(self, tmp_path: Path) -> None:
        """Full validation on empty library should not crash."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()
        _write_config(project_root)

        report = validate_library(project_root, lexibrary_dir)

        assert isinstance(report, ValidationReport)
        # Should not crash -- may have info-level issues like aindex_coverage
        assert report.exit_code() in (0, 2)


# ---------------------------------------------------------------------------
# Severity filter
# ---------------------------------------------------------------------------


class TestSeverityFilter:
    """Validate that severity_filter correctly limits which checks run."""

    def test_severity_filter_error_only(self, tmp_path: Path) -> None:
        """severity_filter='error' should only run error-severity checks."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()
        _write_config(project_root)
        (lexibrary_dir / "concepts").mkdir(parents=True, exist_ok=True)

        # Create a stale design file (would produce warning) and a missing
        # source file (would produce error)
        _write_design_file(lexibrary_dir, "src/missing.py", source_hash="abc")
        _write_source_file(project_root, "src/stale.py", "# stale\n")
        _write_design_file(lexibrary_dir, "src/stale.py", source_hash="wrong_hash")

        # Only error-severity checks
        report = validate_library(project_root, lexibrary_dir, severity_filter="error")

        # Should find the missing source file error
        assert report.has_errors()
        # Should NOT find warnings -- those checks were not run
        assert all(i.severity == "error" for i in report.issues)

    def test_severity_filter_warning_includes_errors_and_warnings(self, tmp_path: Path) -> None:
        """severity_filter='warning' should run error and warning checks."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()
        _write_config(project_root)
        (lexibrary_dir / "concepts").mkdir(parents=True, exist_ok=True)

        # Error: missing source file
        _write_design_file(lexibrary_dir, "src/gone.py", source_hash="abc")

        # Warning: stale hash
        _write_source_file(project_root, "src/stale.py", "# stale\n")
        _write_design_file(lexibrary_dir, "src/stale.py", source_hash="wrong_hash")

        report = validate_library(project_root, lexibrary_dir, severity_filter="warning")

        severities = {i.severity for i in report.issues}
        assert "error" in severities
        assert "warning" in severities
        # Info checks should not have run
        assert "info" not in severities

    def test_severity_filter_info_runs_all(self, tmp_path: Path) -> None:
        """severity_filter='info' should run all checks (same as no filter)."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()
        _write_config(project_root)
        (lexibrary_dir / "concepts").mkdir(parents=True, exist_ok=True)

        # Set up issues at all levels
        _write_design_file(lexibrary_dir, "src/gone.py", source_hash="abc")
        _write_source_file(project_root, "src/stale.py", "# stale\n")
        _write_design_file(lexibrary_dir, "src/stale.py", source_hash="wrong_hash")

        report_filtered = validate_library(project_root, lexibrary_dir, severity_filter="info")
        report_unfiltered = validate_library(project_root, lexibrary_dir)

        # Both should produce the same issues
        assert len(report_filtered.issues) == len(report_unfiltered.issues)

    def test_invalid_severity_filter_raises(self, tmp_path: Path) -> None:
        """Invalid severity_filter should raise ValueError."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()

        with pytest.raises(ValueError, match="Invalid severity_filter"):
            validate_library(project_root, lexibrary_dir, severity_filter="critical")


# ---------------------------------------------------------------------------
# Check filter
# ---------------------------------------------------------------------------


class TestCheckFilter:
    """Validate that check_filter correctly limits which single check runs."""

    def test_check_filter_runs_single_check(self, tmp_path: Path) -> None:
        """check_filter should run only the named check."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()
        _write_config(project_root)
        (lexibrary_dir / "concepts").mkdir(parents=True, exist_ok=True)

        # Create missing source (error) and stale hash (warning)
        _write_design_file(lexibrary_dir, "src/missing.py", source_hash="abc")
        _write_source_file(project_root, "src/stale.py", "# stale\n")
        _write_design_file(lexibrary_dir, "src/stale.py", source_hash="wrong")

        # Only run hash_freshness check
        report = validate_library(project_root, lexibrary_dir, check_filter="hash_freshness")

        # Should only contain hash_freshness issues
        assert all(i.check == "hash_freshness" for i in report.issues)
        # Should find the stale hash
        assert len(report.issues) >= 1

    def test_check_filter_file_existence(self, tmp_path: Path) -> None:
        """check_filter='file_existence' should only return file_existence issues."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()
        _write_config(project_root)

        # Create design file for non-existent source
        _write_design_file(lexibrary_dir, "src/phantom.py", source_hash="abc")

        report = validate_library(project_root, lexibrary_dir, check_filter="file_existence")

        assert len(report.issues) >= 1
        assert all(i.check == "file_existence" for i in report.issues)
        assert all(i.severity == "error" for i in report.issues)

    def test_unknown_check_filter_raises(self, tmp_path: Path) -> None:
        """Unknown check_filter should raise ValueError."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()

        with pytest.raises(ValueError, match="Unknown check"):
            validate_library(project_root, lexibrary_dir, check_filter="nonexistent_check")

    def test_all_registered_checks_are_valid(self) -> None:
        """Every key in AVAILABLE_CHECKS should be a valid check name."""
        expected = {
            # --- Original checks ---
            "wikilink_resolution",
            "file_existence",
            "concept_frontmatter",
            "hash_freshness",
            "token_budgets",
            "orphan_concepts",
            "deprecated_concept_usage",
            "orphaned_designs",
            "forward_dependencies",
            "stack_staleness",
            "resolved_post_staleness",
            "aindex_coverage",
            "bidirectional_deps",
            "dangling_links",
            "orphan_artifacts",
            "orphaned_aindex",
            "orphaned_iwh",
            "comment_accumulation",
            "deprecated_ttl",
            "stale_concept",
            "supersession_candidate",
            "convention_orphaned_scope",
            "convention_stale",
            "convention_gap",
            "convention_consistent_violation",
            "lookup_token_budget_exceeded",
            "orphaned_iwh_signals",
            # --- Schema frontmatter checks (Group 1) ---
            "convention_frontmatter",
            "design_frontmatter",
            "stack_frontmatter",
            "iwh_frontmatter",
            # --- Infrastructure checks (Group 2) ---
            "config_valid",
            "lexignore_syntax",
            "linkgraph_version",
            # --- Cross-artifact checks (Group 3) ---
            "duplicate_aliases",
            "duplicate_slugs",
            "stack_refs_validity",
            "design_deps_existence",
            "aindex_entries",
            # --- Body and structure checks (Group 4) ---
            "design_structure",
            "stack_body_sections",
            "concept_body",
            # --- Playbook checks ---
            "playbook_frontmatter",
            "playbook_wikilinks",
            "playbook_staleness",
            "playbook_deprecated_ttl",
            "artifact_id_uniqueness",
            "stale_agent_design",
        }
        assert set(AVAILABLE_CHECKS.keys()) == expected

    def test_check_filter_with_severity_filter(self, tmp_path: Path) -> None:
        """Both filters can be combined -- check_filter + severity_filter."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()
        _write_config(project_root)
        (lexibrary_dir / "concepts").mkdir(parents=True, exist_ok=True)

        # Create stale hash (warning-severity check)
        _write_source_file(project_root, "src/stale.py", "# stale\n")
        _write_design_file(lexibrary_dir, "src/stale.py", source_hash="wrong")

        # Filter to error severity only + hash_freshness check
        # hash_freshness is a warning-severity check, so it should be excluded
        report = validate_library(
            project_root,
            lexibrary_dir,
            check_filter="hash_freshness",
            severity_filter="error",
        )

        # hash_freshness is warning-level, so with error-only filter it should not run
        assert len(report.issues) == 0


# ---------------------------------------------------------------------------
# All 20 checks registered (including link-graph and lifecycle checks)
# ---------------------------------------------------------------------------


class TestAllChecksRegistered:
    """Verify that validate_library() includes all 27 checks and that
    link-graph checks degrade gracefully when index.db is absent."""

    def test_available_checks_count_is_47(self) -> None:
        """AVAILABLE_CHECKS should contain exactly 48 entries."""
        assert len(AVAILABLE_CHECKS) == 48

    def test_validate_library_runs_all_13_checks_without_filters(self, tmp_path: Path) -> None:
        """With no severity or check filters, all 15 checks should be invoked.

        We verify this indirectly: an unfiltered run on a minimal project
        should not crash and should exercise every registered check.
        """
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()
        _write_config(project_root)
        (lexibrary_dir / "concepts").mkdir(parents=True, exist_ok=True)

        # Provide a source + matching design so some checks have work to do
        source = _write_source_file(project_root, "src/app.py", "def main(): pass\n")
        current_hash = hash_file(source)
        _write_design_file(
            lexibrary_dir,
            "src/app.py",
            source_hash=current_hash,
        )

        # No index.db -- link-graph checks must degrade gracefully
        report = validate_library(project_root, lexibrary_dir)

        assert isinstance(report, ValidationReport)
        # The run must not crash; any issues present are from non-graph checks
        # (e.g., aindex_coverage info). Graph checks should return empty.
        for issue in report.issues:
            assert issue.check not in {
                "bidirectional_deps",
                "dangling_links",
                "orphan_artifacts",
            }, (
                f"Link-graph check '{issue.check}' should return empty "
                f"when index.db is absent, but produced: {issue.message}"
            )

    def test_link_graph_checks_return_empty_when_index_absent(self, tmp_path: Path) -> None:
        """Each link-graph check individually returns an empty list when no index.db exists."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()
        _write_config(project_root)

        link_graph_check_names = [
            "bidirectional_deps",
            "dangling_links",
            "orphan_artifacts",
        ]

        for check_name in link_graph_check_names:
            report = validate_library(
                project_root,
                lexibrary_dir,
                check_filter=check_name,
            )
            assert isinstance(report, ValidationReport)
            assert len(report.issues) == 0, (
                f"Check '{check_name}' should return no issues when index.db "
                f"is absent, but got {len(report.issues)} issues"
            )

    def test_link_graph_checks_have_info_severity_in_registry(self) -> None:
        """All three link-graph checks should be registered with 'info' severity."""
        link_graph_checks = ["bidirectional_deps", "dangling_links", "orphan_artifacts"]
        for name in link_graph_checks:
            assert name in AVAILABLE_CHECKS, f"Check '{name}' not found in AVAILABLE_CHECKS"
            _fn, severity = AVAILABLE_CHECKS[name]
            assert severity == "info", (
                f"Check '{name}' should have 'info' severity, got '{severity}'"
            )


# ---------------------------------------------------------------------------
# Multi-root aindex_coverage walk
# ---------------------------------------------------------------------------


class TestAindexCoverageMultiRoot:
    """Pin ``check_aindex_coverage`` semantics across multiple declared roots.

    The check should walk every declared scope root (one walk per root),
    surface info-severity issues for any directory that lacks an ``.aindex``
    under any root, and stay silent when every directory under every root is
    indexed.
    """

    def test_unindexed_under_either_root_produces_info(self, tmp_path: Path) -> None:
        """Missing ``.aindex`` under any declared root raises an info issue.

        With ``scope_roots: [src/, baml_src/]`` and a source file under each
        root (so each root resolves to a real directory), neither directory
        has an ``.aindex``. The check should flag both ``src/`` and
        ``baml_src/`` (not just one) — proving the loop runs per root.
        """
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()
        _write_config(project_root, scope_roots=["src/", "baml_src/"])

        # Each root must exist on disk to survive the resolver's existence
        # filter; populate each with a single source file.
        _write_source_file(project_root, "src/app.py", "def main(): pass\n")
        _write_source_file(project_root, "baml_src/main.baml", "// baml\n")

        report = validate_library(
            project_root,
            lexibrary_dir,
            check_filter="aindex_coverage",
        )

        coverage_artifacts = {
            issue.artifact for issue in report.issues if issue.check == "aindex_coverage"
        }
        # Both root directories should be reported as unindexed.
        assert "src" in coverage_artifacts, coverage_artifacts
        assert "baml_src" in coverage_artifacts, coverage_artifacts
        for issue in report.issues:
            if issue.check == "aindex_coverage":
                assert issue.severity == "info"

    def test_unindexed_under_only_second_root_still_reported(self, tmp_path: Path) -> None:
        """A fully-indexed first root does not mask gaps under a second root.

        Pins the per-root walk: even when ``src/`` has every directory
        covered, an unindexed ``baml_src/`` directory must still surface.
        """
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()
        _write_config(project_root, scope_roots=["src/", "baml_src/"])

        _write_source_file(project_root, "src/app.py", "def main(): pass\n")
        _write_source_file(project_root, "baml_src/main.baml", "// baml\n")

        # Only ``src/`` has its .aindex; ``baml_src/`` is left bare.
        _write_aindex(project_root, lexibrary_dir, "src")

        report = validate_library(
            project_root,
            lexibrary_dir,
            check_filter="aindex_coverage",
        )

        coverage_artifacts = {
            issue.artifact for issue in report.issues if issue.check == "aindex_coverage"
        }
        assert "baml_src" in coverage_artifacts, coverage_artifacts
        assert "src" not in coverage_artifacts, coverage_artifacts

    def test_fully_indexed_both_roots_zero_issues(self, tmp_path: Path) -> None:
        """When every directory under every declared root is indexed, no issues."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()
        _write_config(project_root, scope_roots=["src/", "baml_src/"])

        _write_source_file(project_root, "src/app.py", "def main(): pass\n")
        _write_source_file(project_root, "baml_src/main.baml", "// baml\n")

        _write_aindex(project_root, lexibrary_dir, "src")
        _write_aindex(project_root, lexibrary_dir, "baml_src")

        report = validate_library(
            project_root,
            lexibrary_dir,
            check_filter="aindex_coverage",
        )

        coverage_issues = [i for i in report.issues if i.check == "aindex_coverage"]
        assert coverage_issues == []
