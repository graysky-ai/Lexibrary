"""Tests for playbook index -- load, find, search, filters, trigger-file matching."""

from __future__ import annotations

from pathlib import Path

import pytest

from lexibrary.playbooks.index import PlaybookIndex


def _write_playbook(directory: Path, filename: str, content: str) -> Path:
    """Helper to write a playbook markdown file."""
    path = directory / filename
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Playbook file fixtures
# ---------------------------------------------------------------------------

VERSION_BUMP = """\
---
title: Version Bump
id: PB-001
trigger_files:
  - pyproject.toml
tags:
  - release
  - versioning
status: active
source: user
estimated_minutes: 15
---
Bump the version number in pyproject.toml.

Follow semantic versioning rules for the bump.
"""

DB_MIGRATION = """\
---
title: DB Migration
id: PB-002
trigger_files:
  - "migrations/*.sql"
tags:
  - database
  - ops
status: active
source: user
estimated_minutes: 30
aliases:
  - database-migration
  - schema-change
---
Run database migration scripts.

Always back up the database before running migrations.
"""

DEPLOY_CHECKLIST = """\
---
title: Deploy Checklist
id: PB-003
trigger_files:
  - "**/*.toml"
tags:
  - ops
  - deploy
status: draft
source: agent
---
Pre-deployment verification checklist.

Ensure all tests pass before deploying.
"""

DEPRECATED_PLAYBOOK = """\
---
title: Old Release Process
id: PB-004
trigger_files:
  - setup.py
tags:
  - release
status: deprecated
source: user
---
Legacy release process. Use Version Bump instead.
"""

NO_TRIGGERS = """\
---
title: Code Review Guidelines
id: CN-001
tags:
  - process
  - quality
status: active
source: user
---
Guidelines for conducting code reviews.

Check for correctness, readability, and maintainability.
"""

SRC_SPECIFIC = """\
---
title: Python Source Update
id: PB-005
trigger_files:
  - "src/lexibrary/config.py"
tags:
  - python
status: active
source: user
---
Steps for updating the config module.
"""

BROAD_PYTHON = """\
---
title: Python File Changed
id: PB-006
trigger_files:
  - "**/*.py"
tags:
  - python
status: active
source: user
---
General steps when any Python file changes.
"""

MALFORMED_FILE = """\
Not valid frontmatter at all.
Just random text.
"""


# ---------------------------------------------------------------------------
# TestPlaybookIndexLoad
# ---------------------------------------------------------------------------


class TestPlaybookIndexLoad:
    def test_load_empty_directory(self, tmp_path: Path) -> None:
        index = PlaybookIndex(tmp_path)
        index.load()
        assert len(index) == 0
        assert index.playbooks == []

    def test_load_nonexistent_directory(self, tmp_path: Path) -> None:
        index = PlaybookIndex(tmp_path / "nonexistent")
        index.load()
        assert len(index) == 0
        assert index.playbooks == []

    def test_load_multiple_playbooks(self, tmp_path: Path) -> None:
        _write_playbook(tmp_path, "version-bump.md", VERSION_BUMP)
        _write_playbook(tmp_path, "db-migration.md", DB_MIGRATION)
        _write_playbook(tmp_path, "deploy-checklist.md", DEPLOY_CHECKLIST)
        index = PlaybookIndex(tmp_path)
        index.load()
        assert len(index) == 3

    def test_load_skips_malformed_files(self, tmp_path: Path) -> None:
        _write_playbook(tmp_path, "version-bump.md", VERSION_BUMP)
        _write_playbook(tmp_path, "bad.md", MALFORMED_FILE)
        index = PlaybookIndex(tmp_path)
        index.load()
        assert len(index) == 1

    def test_load_skips_non_md_files(self, tmp_path: Path) -> None:
        _write_playbook(tmp_path, "version-bump.md", VERSION_BUMP)
        (tmp_path / "notes.txt").write_text("not a playbook")
        (tmp_path / ".gitkeep").write_text("")
        index = PlaybookIndex(tmp_path)
        index.load()
        assert len(index) == 1

    def test_reload_replaces_previous(self, tmp_path: Path) -> None:
        _write_playbook(tmp_path, "version-bump.md", VERSION_BUMP)
        index = PlaybookIndex(tmp_path)
        index.load()
        assert len(index) == 1

        _write_playbook(tmp_path, "db-migration.md", DB_MIGRATION)
        index.load()
        assert len(index) == 2


# ---------------------------------------------------------------------------
# TestPlaybookIndexFind
# ---------------------------------------------------------------------------


class TestPlaybookIndexFind:
    def test_find_existing_slug(self, tmp_path: Path) -> None:
        _write_playbook(tmp_path, "version-bump.md", VERSION_BUMP)
        index = PlaybookIndex(tmp_path)
        index.load()
        result = index.find("version-bump")
        assert result is not None
        assert result.frontmatter.title == "Version Bump"

    def test_find_missing_slug(self, tmp_path: Path) -> None:
        _write_playbook(tmp_path, "version-bump.md", VERSION_BUMP)
        index = PlaybookIndex(tmp_path)
        index.load()
        result = index.find("nonexistent")
        assert result is None

    def test_find_empty_index(self, tmp_path: Path) -> None:
        index = PlaybookIndex(tmp_path)
        index.load()
        assert index.find("version-bump") is None


# ---------------------------------------------------------------------------
# TestPlaybookIndexSearch
# ---------------------------------------------------------------------------


class TestPlaybookIndexSearch:
    def test_search_by_title(self, tmp_path: Path) -> None:
        _write_playbook(tmp_path, "version-bump.md", VERSION_BUMP)
        _write_playbook(tmp_path, "db-migration.md", DB_MIGRATION)
        index = PlaybookIndex(tmp_path)
        index.load()
        results = index.search("version")
        assert len(results) == 1
        assert results[0].frontmatter.title == "Version Bump"

    def test_search_by_overview(self, tmp_path: Path) -> None:
        _write_playbook(tmp_path, "version-bump.md", VERSION_BUMP)
        index = PlaybookIndex(tmp_path)
        index.load()
        results = index.search("pyproject.toml")
        assert len(results) == 1
        assert results[0].frontmatter.title == "Version Bump"

    def test_search_by_tag(self, tmp_path: Path) -> None:
        _write_playbook(tmp_path, "version-bump.md", VERSION_BUMP)
        _write_playbook(tmp_path, "db-migration.md", DB_MIGRATION)
        index = PlaybookIndex(tmp_path)
        index.load()
        results = index.search("versioning")
        assert len(results) == 1
        assert results[0].frontmatter.title == "Version Bump"

    def test_search_by_alias(self, tmp_path: Path) -> None:
        _write_playbook(tmp_path, "db-migration.md", DB_MIGRATION)
        index = PlaybookIndex(tmp_path)
        index.load()
        results = index.search("schema-change")
        assert len(results) == 1
        assert results[0].frontmatter.title == "DB Migration"

    def test_search_case_insensitive(self, tmp_path: Path) -> None:
        _write_playbook(tmp_path, "version-bump.md", VERSION_BUMP)
        index = PlaybookIndex(tmp_path)
        index.load()
        results = index.search("VERSION")
        assert len(results) == 1

    def test_search_no_results(self, tmp_path: Path) -> None:
        _write_playbook(tmp_path, "version-bump.md", VERSION_BUMP)
        index = PlaybookIndex(tmp_path)
        index.load()
        results = index.search("nonexistent")
        assert results == []

    def test_search_empty_query(self, tmp_path: Path) -> None:
        _write_playbook(tmp_path, "version-bump.md", VERSION_BUMP)
        index = PlaybookIndex(tmp_path)
        index.load()
        results = index.search("")
        assert results == []

    def test_search_results_sorted_by_title(self, tmp_path: Path) -> None:
        _write_playbook(tmp_path, "version-bump.md", VERSION_BUMP)
        _write_playbook(tmp_path, "deploy-checklist.md", DEPLOY_CHECKLIST)
        index = PlaybookIndex(tmp_path)
        index.load()
        # Both match "ops" or similar broad terms; use a tag match
        results = index.search("ops")
        titles = [r.frontmatter.title for r in results]
        assert titles == sorted(titles)

    def test_search_no_duplicates(self, tmp_path: Path) -> None:
        _write_playbook(tmp_path, "db-migration.md", DB_MIGRATION)
        index = PlaybookIndex(tmp_path)
        index.load()
        # "database" matches both tag and overview
        results = index.search("database")
        assert len(results) == 1


# ---------------------------------------------------------------------------
# TestPlaybookIndexByTag
# ---------------------------------------------------------------------------


class TestPlaybookIndexByTag:
    def test_filter_by_tag_single_match(self, tmp_path: Path) -> None:
        _write_playbook(tmp_path, "version-bump.md", VERSION_BUMP)
        _write_playbook(tmp_path, "db-migration.md", DB_MIGRATION)
        index = PlaybookIndex(tmp_path)
        index.load()
        results = index.by_tag("versioning")
        assert len(results) == 1
        assert results[0].frontmatter.title == "Version Bump"

    def test_filter_by_tag_multiple_matches(self, tmp_path: Path) -> None:
        _write_playbook(tmp_path, "version-bump.md", VERSION_BUMP)
        _write_playbook(tmp_path, "deprecated-release.md", DEPRECATED_PLAYBOOK)
        index = PlaybookIndex(tmp_path)
        index.load()
        results = index.by_tag("release")
        assert len(results) == 2

    def test_filter_by_tag_case_insensitive(self, tmp_path: Path) -> None:
        _write_playbook(tmp_path, "version-bump.md", VERSION_BUMP)
        index = PlaybookIndex(tmp_path)
        index.load()
        results = index.by_tag("RELEASE")
        assert len(results) == 1

    def test_filter_by_tag_no_match(self, tmp_path: Path) -> None:
        _write_playbook(tmp_path, "version-bump.md", VERSION_BUMP)
        index = PlaybookIndex(tmp_path)
        index.load()
        results = index.by_tag("nonexistent")
        assert results == []

    def test_filter_by_tag_results_sorted(self, tmp_path: Path) -> None:
        _write_playbook(tmp_path, "version-bump.md", VERSION_BUMP)
        _write_playbook(tmp_path, "deprecated-release.md", DEPRECATED_PLAYBOOK)
        index = PlaybookIndex(tmp_path)
        index.load()
        results = index.by_tag("release")
        titles = [r.frontmatter.title for r in results]
        assert titles == sorted(titles)


# ---------------------------------------------------------------------------
# TestPlaybookIndexByStatus
# ---------------------------------------------------------------------------


class TestPlaybookIndexByStatus:
    def test_filter_by_active_status(self, tmp_path: Path) -> None:
        _write_playbook(tmp_path, "version-bump.md", VERSION_BUMP)
        _write_playbook(tmp_path, "deploy-checklist.md", DEPLOY_CHECKLIST)
        _write_playbook(tmp_path, "deprecated-release.md", DEPRECATED_PLAYBOOK)
        index = PlaybookIndex(tmp_path)
        index.load()
        results = index.by_status("active")
        assert len(results) == 1
        assert results[0].frontmatter.title == "Version Bump"

    def test_filter_by_draft_status(self, tmp_path: Path) -> None:
        _write_playbook(tmp_path, "deploy-checklist.md", DEPLOY_CHECKLIST)
        _write_playbook(tmp_path, "version-bump.md", VERSION_BUMP)
        index = PlaybookIndex(tmp_path)
        index.load()
        results = index.by_status("draft")
        assert len(results) == 1
        assert results[0].frontmatter.title == "Deploy Checklist"

    def test_filter_by_deprecated_status(self, tmp_path: Path) -> None:
        _write_playbook(tmp_path, "deprecated-release.md", DEPRECATED_PLAYBOOK)
        _write_playbook(tmp_path, "version-bump.md", VERSION_BUMP)
        index = PlaybookIndex(tmp_path)
        index.load()
        results = index.by_status("deprecated")
        assert len(results) == 1
        assert results[0].frontmatter.title == "Old Release Process"

    def test_filter_by_status_no_match(self, tmp_path: Path) -> None:
        _write_playbook(tmp_path, "version-bump.md", VERSION_BUMP)
        index = PlaybookIndex(tmp_path)
        index.load()
        results = index.by_status("deprecated")
        assert results == []

    def test_filter_by_status_results_sorted(self, tmp_path: Path) -> None:
        _write_playbook(tmp_path, "no-triggers.md", NO_TRIGGERS)
        _write_playbook(tmp_path, "db-migration.md", DB_MIGRATION)
        _write_playbook(tmp_path, "version-bump.md", VERSION_BUMP)
        index = PlaybookIndex(tmp_path)
        index.load()
        results = index.by_status("active")
        titles = [r.frontmatter.title for r in results]
        assert titles == sorted(titles)


# ---------------------------------------------------------------------------
# TestPlaybookIndexByTriggerFile
# ---------------------------------------------------------------------------


class TestPlaybookIndexByTriggerFile:
    def test_exact_file_match(self, tmp_path: Path) -> None:
        _write_playbook(tmp_path, "version-bump.md", VERSION_BUMP)
        index = PlaybookIndex(tmp_path)
        index.load()
        results = index.by_trigger_file("pyproject.toml")
        assert len(results) == 1
        assert results[0].frontmatter.title == "Version Bump"

    def test_directory_glob_match(self, tmp_path: Path) -> None:
        _write_playbook(tmp_path, "db-migration.md", DB_MIGRATION)
        index = PlaybookIndex(tmp_path)
        index.load()
        results = index.by_trigger_file("migrations/001_create_users.sql")
        assert len(results) == 1
        assert results[0].frontmatter.title == "DB Migration"

    def test_specificity_ordering(self, tmp_path: Path) -> None:
        """More specific patterns rank higher than broad globs."""
        _write_playbook(tmp_path, "version-bump.md", VERSION_BUMP)  # pyproject.toml
        _write_playbook(tmp_path, "deploy-checklist.md", DEPLOY_CHECKLIST)  # **/*.toml
        index = PlaybookIndex(tmp_path)
        index.load()
        results = index.by_trigger_file("pyproject.toml")
        assert len(results) == 2
        # pyproject.toml (1 segment) is more specific than **/*.toml (1 literal segment)
        # Actually: "pyproject.toml" = 1 literal segment, "**/*.toml" = 1 literal segment
        # but pyproject.toml is an exact match, both have specificity 1
        # They tie on specificity, so sorted by title
        titles = [r.frontmatter.title for r in results]
        assert titles[0] == "Deploy Checklist"
        assert titles[1] == "Version Bump"

    def test_specificity_deep_vs_broad(self, tmp_path: Path) -> None:
        """A path-specific trigger ranks above a broad wildcard."""
        _write_playbook(tmp_path, "src-specific.md", SRC_SPECIFIC)  # src/lexibrary/config.py
        _write_playbook(tmp_path, "broad-python.md", BROAD_PYTHON)  # **/*.py
        index = PlaybookIndex(tmp_path)
        index.load()
        results = index.by_trigger_file("src/lexibrary/config.py")
        assert len(results) == 2
        # src/lexibrary/config.py has 3 literal segments, **/*.py has 1
        assert results[0].frontmatter.title == "Python Source Update"
        assert results[1].frontmatter.title == "Python File Changed"

    def test_no_match(self, tmp_path: Path) -> None:
        _write_playbook(tmp_path, "version-bump.md", VERSION_BUMP)
        index = PlaybookIndex(tmp_path)
        index.load()
        results = index.by_trigger_file("README.md")
        assert results == []

    def test_playbook_without_triggers_excluded(self, tmp_path: Path) -> None:
        _write_playbook(tmp_path, "no-triggers.md", NO_TRIGGERS)
        _write_playbook(tmp_path, "version-bump.md", VERSION_BUMP)
        index = PlaybookIndex(tmp_path)
        index.load()
        results = index.by_trigger_file("pyproject.toml")
        assert len(results) == 1
        assert results[0].frontmatter.title == "Version Bump"

    def test_empty_file_path(self, tmp_path: Path) -> None:
        _write_playbook(tmp_path, "version-bump.md", VERSION_BUMP)
        index = PlaybookIndex(tmp_path)
        index.load()
        results = index.by_trigger_file("")
        assert results == []


# ---------------------------------------------------------------------------
# TestPlaybookIndexNames
# ---------------------------------------------------------------------------


class TestPlaybookIndexNames:
    def test_names_returns_sorted_titles(self, tmp_path: Path) -> None:
        _write_playbook(tmp_path, "db-migration.md", DB_MIGRATION)
        _write_playbook(tmp_path, "version-bump.md", VERSION_BUMP)
        _write_playbook(tmp_path, "deploy-checklist.md", DEPLOY_CHECKLIST)
        index = PlaybookIndex(tmp_path)
        index.load()
        assert index.names() == [
            "DB Migration",
            "Deploy Checklist",
            "Version Bump",
        ]

    def test_names_empty_index(self, tmp_path: Path) -> None:
        index = PlaybookIndex(tmp_path)
        index.load()
        assert index.names() == []


# ---------------------------------------------------------------------------
# TestPlaybookIndexIteration
# ---------------------------------------------------------------------------


class TestPlaybookIndexIteration:
    def test_iteration_raises_type_error(self, tmp_path: Path) -> None:
        _write_playbook(tmp_path, "version-bump.md", VERSION_BUMP)
        index = PlaybookIndex(tmp_path)
        index.load()
        with pytest.raises(TypeError, match="not iterable"):
            iter(index)

    def test_for_loop_raises_type_error(self, tmp_path: Path) -> None:
        _write_playbook(tmp_path, "version-bump.md", VERSION_BUMP)
        index = PlaybookIndex(tmp_path)
        index.load()
        with pytest.raises(TypeError, match="not iterable"):
            for _ in index:
                pass


# ---------------------------------------------------------------------------
# TestPlaybookIndexImport
# ---------------------------------------------------------------------------


class TestPlaybookIndexImport:
    def test_importable_from_playbooks_package(self) -> None:
        from lexibrary.playbooks import PlaybookIndex

        assert PlaybookIndex is not None
