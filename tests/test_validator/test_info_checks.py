"""Unit tests for info-severity validation checks.

Tests check_forward_dependencies, check_stack_staleness, check_aindex_coverage,
check_bidirectional_deps, check_dangling_links, and check_orphan_artifacts.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from lexibrary.linkgraph.schema import SCHEMA_VERSION, ensure_schema
from lexibrary.utils.hashing import hash_file
from lexibrary.utils.paths import LEXIBRARY_DIR
from lexibrary.validator.checks import (
    check_aindex_coverage,
    check_bidirectional_deps,
    check_dangling_links,
    check_forward_dependencies,
    check_orphan_artifacts,
    check_stack_staleness,
)

# ---------------------------------------------------------------------------
# Helpers for writing test fixtures
# ---------------------------------------------------------------------------

_DESIGN_FILE_TEMPLATE = """\
---
description: {description}
id: DS-001
updated_by: archivist
---

# {source_path}

## Interface Contract

```python
def example() -> None: ...
```

## Dependencies

{dependencies}

## Dependents

(none)

<!-- lexibrary:meta
source: {source_path}
source_hash: {source_hash}
design_hash: deadbeef
generated: 2026-01-01T12:00:00
generator: lexibrary-v2
-->
"""

_STACK_POST_TEMPLATE = """\
---
id: {post_id}
title: {title}
tags:
  - test
status: open
created: 2026-01-01
author: tester
refs:
  files:
{refs_files}
---

## Problem

Something was broken.

### A1

**Date:** 2026-01-01 | **Author:** tester | **Votes:** 0

The fix is to do X.
"""

_AINDEX_META = (
    '<!-- lexibrary:meta source="{dir}" source_hash="abc123"'
    ' generated="2026-01-01T12:00:00" generator="lexibrary-v2" -->'
)

_AINDEX_TEMPLATE = """\
# {directory_path}

{billboard}

## Child Map

| Name | Type | Description |
| --- | --- | --- |
{entries}

## Local Conventions

(none)

{meta}
"""


def _write_design_file(
    lexibrary_dir: Path,
    source_path: str,
    source_hash: str = "abc123",
    dependencies: str = "(none)",
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
            dependencies=dependencies,
        ),
        encoding="utf-8",
    )
    return design_path


def _write_stack_post(
    lexibrary_dir: Path,
    post_id: str,
    title: str,
    refs_files: list[str],
) -> Path:
    """Write a Stack post file."""
    stack_dir = lexibrary_dir / "stack"
    stack_dir.mkdir(parents=True, exist_ok=True)
    post_path = stack_dir / f"{post_id}.md"
    # Format refs.files as YAML list
    refs_lines = "\n".join(f"    - {f}" for f in refs_files) if refs_files else "    []"
    post_path.write_text(
        _STACK_POST_TEMPLATE.format(
            post_id=post_id,
            title=title,
            refs_files=refs_lines,
        ),
        encoding="utf-8",
    )
    return post_path


def _write_aindex(
    lexibrary_dir: Path,
    directory_path: str,
    billboard: str = "Test directory.",
) -> Path:
    """Write a .aindex file to the expected mirror path."""
    aindex = lexibrary_dir / "designs" / directory_path / ".aindex"
    aindex.parent.mkdir(parents=True, exist_ok=True)
    meta = _AINDEX_META.format(dir=directory_path)
    aindex.write_text(
        _AINDEX_TEMPLATE.format(
            directory_path=directory_path,
            billboard=billboard,
            entries="(none)",
            meta=meta,
        ),
        encoding="utf-8",
    )
    return aindex


def _write_config(project_root: Path, scope_root: str = ".") -> None:
    """Write a minimal config.yaml using the multi-root scope_roots format."""
    config_dir = project_root / ".lexibrary"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.yaml"
    config_path.write_text(
        f"scope_roots:\n  - path: {scope_root}\n", encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# check_forward_dependencies
# ---------------------------------------------------------------------------


class TestCheckForwardDependencies:
    """Tests for check_forward_dependencies."""

    def test_all_dependencies_exist(self, tmp_path: Path) -> None:
        """When all dependency targets exist on disk, no issues are returned."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()

        # Create a source file
        src_dir = project_root / "src"
        src_dir.mkdir()
        source_file = src_dir / "main.py"
        source_file.write_text("print('hello')", encoding="utf-8")

        # Create a dependency target that exists
        dep_file = src_dir / "utils.py"
        dep_file.write_text("def helper(): pass", encoding="utf-8")

        # Create a design file that lists the dependency
        _write_design_file(
            lexibrary_dir,
            "src/main.py",
            dependencies="- src/utils.py",
        )

        issues = check_forward_dependencies(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_missing_dependency_produces_info(self, tmp_path: Path) -> None:
        """When a dependency target does not exist, an info issue is returned."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()

        # Create a design file referencing a non-existent dependency
        _write_design_file(
            lexibrary_dir,
            "src/main.py",
            dependencies="- src/missing_module.py",
        )

        issues = check_forward_dependencies(project_root, lexibrary_dir)
        assert len(issues) == 1
        issue = issues[0]
        assert issue.severity == "info"
        assert issue.check == "forward_dependencies"
        assert "src/missing_module.py" in issue.message
        assert "missing_module.py" in issue.suggestion

    def test_none_dependency_ignored(self, tmp_path: Path) -> None:
        """Dependencies listed as '(none)' are skipped."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_design_file(
            lexibrary_dir,
            "src/main.py",
            dependencies="(none)",
        )

        issues = check_forward_dependencies(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_multiple_deps_mixed(self, tmp_path: Path) -> None:
        """Mix of existing and missing dependencies produces issues only for missing."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()

        # Create one existing dependency
        src_dir = project_root / "src"
        src_dir.mkdir()
        (src_dir / "exists.py").write_text("pass", encoding="utf-8")

        _write_design_file(
            lexibrary_dir,
            "src/main.py",
            dependencies="- src/exists.py\n- src/gone.py",
        )

        issues = check_forward_dependencies(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert "src/gone.py" in issues[0].message

    def test_empty_lexibrary(self, tmp_path: Path) -> None:
        """No design files means no issues."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()

        issues = check_forward_dependencies(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_nonexistent_lexibrary_dir(self, tmp_path: Path) -> None:
        """If .lexibrary doesn't exist, no issues (graceful)."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"

        issues = check_forward_dependencies(project_root, lexibrary_dir)
        assert len(issues) == 0


# ---------------------------------------------------------------------------
# check_stack_staleness
# ---------------------------------------------------------------------------


class TestCheckStackStaleness:
    """Tests for check_stack_staleness."""

    def test_unchanged_refs_pass(self, tmp_path: Path) -> None:
        """When all referenced files have fresh design files, no issues returned."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()

        # Create source file
        src_dir = project_root / "src"
        src_dir.mkdir()
        source_file = src_dir / "api.py"
        source_file.write_text("def handle(): pass", encoding="utf-8")

        # Compute current hash
        current_hash = hash_file(source_file)

        # Create design file with matching hash
        _write_design_file(
            lexibrary_dir,
            "src/api.py",
            source_hash=current_hash,
        )

        # Create stack post referencing the file
        _write_stack_post(
            lexibrary_dir,
            post_id="Q-001",
            title="How to handle requests",
            refs_files=["src/api.py"],
        )

        issues = check_stack_staleness(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_stale_ref_produces_info(self, tmp_path: Path) -> None:
        """When a referenced file's design file has a stale hash, info issue returned."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()

        # Create source file
        src_dir = project_root / "src"
        src_dir.mkdir()
        source_file = src_dir / "events.py"
        source_file.write_text("def emit(): pass", encoding="utf-8")

        # Create design file with a STALE hash (doesn't match current content)
        _write_design_file(
            lexibrary_dir,
            "src/events.py",
            source_hash="stale_hash_value",
        )

        # Create stack post referencing the file
        _write_stack_post(
            lexibrary_dir,
            post_id="Q-002",
            title="Event handling patterns",
            refs_files=["src/events.py"],
        )

        issues = check_stack_staleness(project_root, lexibrary_dir)
        assert len(issues) == 1
        issue = issues[0]
        assert issue.severity == "info"
        assert issue.check == "stack_staleness"
        assert "Event handling patterns" in issue.message
        assert "src/events.py" in issue.message
        assert "lexi stack" in issue.suggestion

    def test_no_stack_posts(self, tmp_path: Path) -> None:
        """If no stack directory exists, no issues."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()

        issues = check_stack_staleness(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_stack_post_without_refs(self, tmp_path: Path) -> None:
        """Stack posts with no refs.files are skipped."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()

        _write_stack_post(
            lexibrary_dir,
            post_id="Q-003",
            title="General question",
            refs_files=[],
        )

        issues = check_stack_staleness(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_missing_design_file_not_flagged(self, tmp_path: Path) -> None:
        """If a referenced file has no design file, staleness can't be determined."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()

        # Create source file but NO design file
        src_dir = project_root / "src"
        src_dir.mkdir()
        (src_dir / "orphan.py").write_text("pass", encoding="utf-8")

        _write_stack_post(
            lexibrary_dir,
            post_id="Q-004",
            title="About orphan",
            refs_files=["src/orphan.py"],
        )

        issues = check_stack_staleness(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_missing_source_file_not_flagged(self, tmp_path: Path) -> None:
        """If the source file itself is missing, file_existence handles it."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()

        # Design file exists but source does not
        _write_design_file(
            lexibrary_dir,
            "src/gone.py",
            source_hash="whatever",
        )

        _write_stack_post(
            lexibrary_dir,
            post_id="Q-005",
            title="About gone module",
            refs_files=["src/gone.py"],
        )

        issues = check_stack_staleness(project_root, lexibrary_dir)
        assert len(issues) == 0


# ---------------------------------------------------------------------------
# check_aindex_coverage
# ---------------------------------------------------------------------------


class TestCheckAindexCoverage:
    """Tests for check_aindex_coverage."""

    def test_all_dirs_indexed(self, tmp_path: Path) -> None:
        """When every directory has an .aindex file, no issues returned."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()
        _write_config(project_root)

        # Create directory structure
        src_dir = project_root / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("pass", encoding="utf-8")

        # Create .aindex files for project_root (.) and src
        _write_aindex(lexibrary_dir, ".", billboard="Project root.")
        _write_aindex(lexibrary_dir, "src", billboard="Source code.")

        issues = check_aindex_coverage(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_unindexed_dir_produces_info(self, tmp_path: Path) -> None:
        """When a directory lacks an .aindex file, an info issue is returned."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()
        _write_config(project_root)

        # Create directory structure
        src_dir = project_root / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("pass", encoding="utf-8")

        # Only create .aindex for root, not src
        _write_aindex(lexibrary_dir, ".", billboard="Project root.")

        issues = check_aindex_coverage(project_root, lexibrary_dir)
        # Should flag the unindexed "src" directory
        src_issues = [i for i in issues if "src" in i.message]
        assert len(src_issues) == 1
        issue = src_issues[0]
        assert issue.severity == "info"
        assert issue.check == "aindex_coverage"
        assert "not indexed" in issue.message
        assert "lexictl update" in issue.suggestion

    def test_hidden_dirs_skipped(self, tmp_path: Path) -> None:
        """Hidden directories (starting with .) are not checked."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()
        _write_config(project_root)

        # Create a hidden directory
        hidden_dir = project_root / ".hidden"
        hidden_dir.mkdir()

        # Create .aindex for root only
        _write_aindex(lexibrary_dir, ".", billboard="Project root.")

        issues = check_aindex_coverage(project_root, lexibrary_dir)
        # Should not flag .hidden
        hidden_issues = [i for i in issues if ".hidden" in i.message]
        assert len(hidden_issues) == 0

    def test_nested_unindexed_dirs(self, tmp_path: Path) -> None:
        """Nested directories without .aindex files produce individual issues."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()
        _write_config(project_root)

        # Create nested dirs
        deep = project_root / "src" / "core"
        deep.mkdir(parents=True)

        # Only index root
        _write_aindex(lexibrary_dir, ".", billboard="Project root.")

        issues = check_aindex_coverage(project_root, lexibrary_dir)
        messages = [i.message for i in issues]
        assert any("src" in m for m in messages)
        assert any("core" in m for m in messages)

    def test_empty_project(self, tmp_path: Path) -> None:
        """Project with no subdirectories only checks root."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()
        _write_config(project_root)

        # Index root
        _write_aindex(lexibrary_dir, ".", billboard="Empty project.")

        issues = check_aindex_coverage(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_scope_root_respected(self, tmp_path: Path) -> None:
        """Only directories under scope_root are checked."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"
        lexibrary_dir.mkdir()
        _write_config(project_root, scope_root="src")

        # Create dirs inside and outside scope_root
        src_dir = project_root / "src"
        src_dir.mkdir()
        docs_dir = project_root / "docs"
        docs_dir.mkdir()

        # Index src
        _write_aindex(lexibrary_dir, "src", billboard="Source code.")

        issues = check_aindex_coverage(project_root, lexibrary_dir)
        # docs is outside scope_root, should not be flagged
        docs_issues = [i for i in issues if "docs" in i.message]
        assert len(docs_issues) == 0

    def test_nonexistent_lexibrary_dir(self, tmp_path: Path) -> None:
        """If .lexibrary doesn't exist, graceful handling."""
        project_root = tmp_path
        lexibrary_dir = project_root / ".lexibrary"

        issues = check_aindex_coverage(project_root, lexibrary_dir)
        # The config load will fail but should be handled gracefully
        # The scope_root walk should still work
        assert isinstance(issues, list)


# ---------------------------------------------------------------------------
# Helpers for check_dangling_links and check_orphan_artifacts tests
# ---------------------------------------------------------------------------


def _create_index_with_artifacts(
    lexibrary_dir: Path,
    artifacts: list[tuple[str, str]],
) -> None:
    """Create an index.db with the given artifacts.

    Args:
        lexibrary_dir: Path to .lexibrary directory.
        artifacts: List of (path, kind) tuples to insert.
    """
    db_path = lexibrary_dir / "index.db"
    conn = sqlite3.connect(str(db_path))
    ensure_schema(conn)
    for i, (art_path, kind) in enumerate(artifacts, start=1):
        conn.execute(
            "INSERT INTO artifacts (id, path, kind, title, status) VALUES (?, ?, ?, ?, ?)",
            (i, art_path, kind, f"Artifact {i}", "active" if kind != "design" else None),
        )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# check_dangling_links
# ---------------------------------------------------------------------------


class TestCheckDanglingLinks:
    """Tests for check_dangling_links."""

    def test_all_files_exist(self, tmp_path: Path) -> None:
        """When every artifact in the graph has a corresponding file on disk, no issues."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        # Create actual files on disk
        src_dir = project_root / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("pass", encoding="utf-8")

        design_dir = lexibrary_dir / "designs" / "src"
        design_dir.mkdir(parents=True)
        (design_dir / "main.py.md").write_text("# design", encoding="utf-8")

        # Create index with matching artifacts
        _create_index_with_artifacts(
            lexibrary_dir,
            [
                ("src/main.py", "source"),
                (".lexibrary/designs/src/main.py.md", "design"),
            ],
        )

        issues = check_dangling_links(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_source_file_deleted_but_in_index(self, tmp_path: Path) -> None:
        """When a source file is deleted but still in the graph, an info issue is returned."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        # Do NOT create the source file on disk -- it has been deleted
        _create_index_with_artifacts(
            lexibrary_dir,
            [("src/old_module.py", "source")],
        )

        issues = check_dangling_links(project_root, lexibrary_dir)
        assert len(issues) == 1
        issue = issues[0]
        assert issue.severity == "info"
        assert issue.check == "dangling_links"
        assert "src/old_module.py" in issue.message
        assert "no longer exists" in issue.message
        assert issue.artifact == "src/old_module.py"
        assert "lexictl update" in issue.suggestion

    def test_convention_artifacts_skipped(self, tmp_path: Path) -> None:
        """Convention artifacts are not checked for file existence."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        # Create index with only a convention artifact (synthetic path, no backing file)
        db_path = lexibrary_dir / "index.db"
        conn = sqlite3.connect(str(db_path))
        ensure_schema(conn)
        conn.execute(
            "INSERT INTO artifacts (id, path, kind, title) "
            "VALUES (1, 'src/api::convention::0', 'convention', 'Convention 1')"
        )
        conn.commit()
        conn.close()

        issues = check_dangling_links(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_index_missing_returns_empty(self, tmp_path: Path) -> None:
        """When index.db does not exist, returns empty list without error."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        # No index.db created
        issues = check_dangling_links(project_root, lexibrary_dir)
        assert issues == []

    def test_index_corrupt_returns_empty(self, tmp_path: Path) -> None:
        """When index.db is corrupt, returns empty list without error."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        db_path = lexibrary_dir / "index.db"
        db_path.write_bytes(b"this is not a valid sqlite database")

        issues = check_dangling_links(project_root, lexibrary_dir)
        assert issues == []

    def test_schema_version_mismatch_returns_empty(self, tmp_path: Path) -> None:
        """When schema version does not match, returns empty list."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        db_path = lexibrary_dir / "index.db"
        conn = sqlite3.connect(str(db_path))
        ensure_schema(conn)
        conn.execute(
            "UPDATE meta SET value = ? WHERE key = 'schema_version'",
            (str(SCHEMA_VERSION + 999),),
        )
        conn.commit()
        conn.close()

        issues = check_dangling_links(project_root, lexibrary_dir)
        assert issues == []

    def test_mixed_existing_and_deleted(self, tmp_path: Path) -> None:
        """Only artifacts with deleted files produce issues; existing ones are fine."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        # Create one existing source file
        src_dir = project_root / "src"
        src_dir.mkdir()
        (src_dir / "alive.py").write_text("pass", encoding="utf-8")

        # Index has both existing and deleted
        _create_index_with_artifacts(
            lexibrary_dir,
            [
                ("src/alive.py", "source"),
                ("src/deleted.py", "source"),
            ],
        )

        issues = check_dangling_links(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert "src/deleted.py" in issues[0].message

    def test_lexibrary_dir_does_not_exist(self, tmp_path: Path) -> None:
        """When .lexibrary directory itself is missing, returns empty list."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        # Do not create .lexibrary

        issues = check_dangling_links(project_root, lexibrary_dir)
        assert issues == []

    def test_multiple_artifact_kinds_checked(self, tmp_path: Path) -> None:
        """All non-convention kinds (source, design, concept, stack) are checked."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        # None of the backing files exist on disk
        _create_index_with_artifacts(
            lexibrary_dir,
            [
                ("src/module.py", "source"),
                (".lexibrary/designs/src/module.py.md", "design"),
                (".lexibrary/concepts/auth.md", "concept"),
                (".lexibrary/stack/ST-Q-001.md", "stack"),
            ],
        )

        issues = check_dangling_links(project_root, lexibrary_dir)
        assert len(issues) == 4
        checks = {i.check for i in issues}
        assert checks == {"dangling_links"}
        severities = {i.severity for i in issues}
        assert severities == {"info"}


# ---------------------------------------------------------------------------
# check_orphan_artifacts
# ---------------------------------------------------------------------------


class TestCheckOrphanArtifacts:
    """Tests for check_orphan_artifacts."""

    def test_no_orphans(self, tmp_path: Path) -> None:
        """When all artifacts have existing backing files, no issues returned."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        # Create actual files on disk
        src_dir = project_root / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("pass", encoding="utf-8")

        design_dir = lexibrary_dir / "designs" / "src"
        design_dir.mkdir(parents=True)
        (design_dir / "main.py.md").write_text("# design", encoding="utf-8")

        # Create index with matching artifacts
        _create_index_with_artifacts(
            lexibrary_dir,
            [
                ("src/main.py", "source"),
                (".lexibrary/designs/src/main.py.md", "design"),
            ],
        )

        issues = check_orphan_artifacts(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_source_file_deleted(self, tmp_path: Path) -> None:
        """When a source file is deleted but still in index, an info issue is returned."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        # Do NOT create the source file on disk -- it is "deleted"
        _create_index_with_artifacts(
            lexibrary_dir,
            [("src/services/deprecated.py", "source")],
        )

        issues = check_orphan_artifacts(project_root, lexibrary_dir)
        assert len(issues) == 1
        issue = issues[0]
        assert issue.severity == "info"
        assert issue.check == "orphan_artifacts"
        assert "src/services/deprecated.py" in issue.message
        assert issue.artifact == "src/services/deprecated.py"
        assert "lexictl update" in issue.suggestion

    def test_design_file_deleted(self, tmp_path: Path) -> None:
        """When a design file is deleted but still in index, an info issue is returned."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        # Do NOT create the design file on disk -- it is "deleted"
        _create_index_with_artifacts(
            lexibrary_dir,
            [(".lexibrary/designs/src/old_module.py.md", "design")],
        )

        issues = check_orphan_artifacts(project_root, lexibrary_dir)
        assert len(issues) == 1
        issue = issues[0]
        assert issue.severity == "info"
        assert issue.check == "orphan_artifacts"
        assert ".lexibrary/designs/src/old_module.py.md" in issue.message
        assert "design" in issue.message
        assert "lexictl update" in issue.suggestion

    def test_index_missing_returns_empty(self, tmp_path: Path) -> None:
        """When index.db does not exist, returns empty list without error."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        # No index.db created
        issues = check_orphan_artifacts(project_root, lexibrary_dir)
        assert issues == []

    def test_index_corrupt_returns_empty(self, tmp_path: Path) -> None:
        """When index.db is corrupt, returns empty list without error."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        db_path = lexibrary_dir / "index.db"
        db_path.write_bytes(b"this is not a valid sqlite database")

        issues = check_orphan_artifacts(project_root, lexibrary_dir)
        assert issues == []

    def test_schema_version_mismatch_returns_empty(self, tmp_path: Path) -> None:
        """When schema version does not match, returns empty list."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        db_path = lexibrary_dir / "index.db"
        conn = sqlite3.connect(str(db_path))
        ensure_schema(conn)
        conn.execute(
            "UPDATE meta SET value = ? WHERE key = 'schema_version'",
            (str(SCHEMA_VERSION + 999),),
        )
        conn.commit()
        conn.close()

        issues = check_orphan_artifacts(project_root, lexibrary_dir)
        assert issues == []

    def test_convention_artifacts_skipped(self, tmp_path: Path) -> None:
        """Convention artifacts are not checked for backing files."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        # Create index with a convention artifact (no backing file)
        db_path = lexibrary_dir / "index.db"
        conn = sqlite3.connect(str(db_path))
        ensure_schema(conn)
        conn.execute(
            "INSERT INTO artifacts (id, path, kind, title) "
            "VALUES (1, 'src/api::convention::0', 'convention', 'Convention 1')"
        )
        conn.commit()
        conn.close()

        issues = check_orphan_artifacts(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_mixed_existing_and_deleted(self, tmp_path: Path) -> None:
        """Only deleted artifacts produce issues; existing ones are fine."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        # Create one existing source file
        src_dir = project_root / "src"
        src_dir.mkdir()
        (src_dir / "alive.py").write_text("pass", encoding="utf-8")

        # Index has both existing and deleted
        _create_index_with_artifacts(
            lexibrary_dir,
            [
                ("src/alive.py", "source"),
                ("src/deleted.py", "source"),
            ],
        )

        issues = check_orphan_artifacts(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert "src/deleted.py" in issues[0].message

    def test_lexibrary_dir_does_not_exist(self, tmp_path: Path) -> None:
        """When .lexibrary directory itself is missing, returns empty list."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        # Do not create .lexibrary

        issues = check_orphan_artifacts(project_root, lexibrary_dir)
        assert issues == []


# ---------------------------------------------------------------------------
# Helpers for check_bidirectional_deps tests
# ---------------------------------------------------------------------------


def _create_index_with_links(
    lexibrary_dir: Path,
    artifacts: list[tuple[int, str, str]],
    links: list[tuple[int, int, str]],
) -> None:
    """Create an index.db with given artifacts and links.

    Args:
        lexibrary_dir: Path to .lexibrary directory.
        artifacts: List of (id, path, kind) tuples to insert.
        links: List of (source_id, target_id, link_type) tuples to insert.
    """
    db_path = lexibrary_dir / "index.db"
    conn = sqlite3.connect(str(db_path))
    ensure_schema(conn)
    for art_id, art_path, kind in artifacts:
        conn.execute(
            "INSERT INTO artifacts (id, path, kind, title, status) VALUES (?, ?, ?, ?, ?)",
            (art_id, art_path, kind, f"Artifact {art_id}", None),
        )
    for src_id, tgt_id, link_type in links:
        conn.execute(
            "INSERT INTO links (source_id, target_id, link_type) VALUES (?, ?, ?)",
            (src_id, tgt_id, link_type),
        )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# check_bidirectional_deps
# ---------------------------------------------------------------------------


class TestCheckBidirectionalDeps:
    """Tests for check_bidirectional_deps.

    Scenarios per task 2.2:
    1. All consistent (no issues)
    2. Design file lists dep not in graph
    3. Graph has link not in design file
    4. Index missing (returns empty)
    5. Index corrupt (returns empty)
    """

    def test_all_consistent_no_issues(self, tmp_path: Path) -> None:
        """When design deps and graph ast_import links match, no issues returned."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        # Create source files on disk
        src_dir = project_root / "src" / "api"
        src_dir.mkdir(parents=True)
        (src_dir / "auth.py").write_text("import crypto", encoding="utf-8")

        utils_dir = project_root / "src" / "utils"
        utils_dir.mkdir(parents=True)
        (utils_dir / "crypto.py").write_text("def encrypt(): pass", encoding="utf-8")

        source_hash = hash_file(src_dir / "auth.py")

        # Create design file listing src/utils/crypto.py as a dependency
        _write_design_file(
            lexibrary_dir,
            "src/api/auth.py",
            source_hash=source_hash,
            dependencies="- src/utils/crypto.py",
        )

        # Create index with matching ast_import link
        _create_index_with_links(
            lexibrary_dir,
            artifacts=[
                (1, "src/api/auth.py", "source"),
                (2, "src/utils/crypto.py", "source"),
            ],
            links=[
                (1, 2, "ast_import"),
            ],
        )

        issues = check_bidirectional_deps(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_design_dep_not_in_graph(self, tmp_path: Path) -> None:
        """When design file lists a dep not in the graph, an info issue is returned."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        # Create source file
        src_dir = project_root / "src" / "api"
        src_dir.mkdir(parents=True)
        (src_dir / "auth.py").write_text("import crypto", encoding="utf-8")

        source_hash = hash_file(src_dir / "auth.py")

        # Design file lists src/utils/crypto.py as dep
        _write_design_file(
            lexibrary_dir,
            "src/api/auth.py",
            source_hash=source_hash,
            dependencies="- src/utils/crypto.py",
        )

        # Index has the source artifact but NO ast_import link
        _create_index_with_links(
            lexibrary_dir,
            artifacts=[
                (1, "src/api/auth.py", "source"),
                (2, "src/utils/crypto.py", "source"),
            ],
            links=[],
        )

        issues = check_bidirectional_deps(project_root, lexibrary_dir)
        assert len(issues) == 1
        issue = issues[0]
        assert issue.severity == "info"
        assert issue.check == "bidirectional_deps"
        assert "src/utils/crypto.py" in issue.message
        assert "listed in the design file" in issue.message
        assert "not found" in issue.message
        assert "stale" in issue.suggestion

    def test_graph_link_not_in_design(self, tmp_path: Path) -> None:
        """When graph has ast_import not listed in design file, an info issue is returned."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        # Create source file
        src_dir = project_root / "src" / "api"
        src_dir.mkdir(parents=True)
        (src_dir / "auth.py").write_text("from models import user", encoding="utf-8")

        source_hash = hash_file(src_dir / "auth.py")

        # Design file has NO dependencies listed
        _write_design_file(
            lexibrary_dir,
            "src/api/auth.py",
            source_hash=source_hash,
            dependencies="(none)",
        )

        # Graph has an ast_import link from auth.py to models/user.py
        _create_index_with_links(
            lexibrary_dir,
            artifacts=[
                (1, "src/api/auth.py", "source"),
                (2, "src/models/user.py", "source"),
            ],
            links=[
                (1, 2, "ast_import"),
            ],
        )

        issues = check_bidirectional_deps(project_root, lexibrary_dir)
        assert len(issues) == 1
        issue = issues[0]
        assert issue.severity == "info"
        assert issue.check == "bidirectional_deps"
        assert "src/models/user.py" in issue.message
        assert "exists in the link graph" in issue.message
        assert "not listed in the design file" in issue.message

    def test_index_missing_returns_empty(self, tmp_path: Path) -> None:
        """When index.db does not exist, returns empty list without error."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        # Create a design file with dependencies but no index
        _write_design_file(
            lexibrary_dir,
            "src/main.py",
            dependencies="- src/utils.py",
        )

        issues = check_bidirectional_deps(project_root, lexibrary_dir)
        assert issues == []

    def test_index_corrupt_returns_empty(self, tmp_path: Path) -> None:
        """When index.db is corrupt, returns empty list without error."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        db_path = lexibrary_dir / "index.db"
        db_path.write_bytes(b"this is not a valid sqlite database")

        issues = check_bidirectional_deps(project_root, lexibrary_dir)
        assert issues == []
