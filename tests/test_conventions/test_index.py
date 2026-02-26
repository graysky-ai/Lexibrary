"""Tests for convention index -- load, scope resolution, display limit, search, filters."""

from __future__ import annotations

from pathlib import Path

from lexibrary.conventions.index import ConventionIndex


def _write_convention(directory: Path, filename: str, content: str) -> Path:
    """Helper to write a convention markdown file."""
    path = directory / filename
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Convention file fixtures
# ---------------------------------------------------------------------------

FUTURE_ANNOTATIONS = """\
---
title: Future annotations import
scope: project
tags:
  - python
  - typing
status: active
source: user
priority: 0
---
Every module must include `from __future__ import annotations`.

This ensures PEP 604 union syntax works on Python 3.9+.
"""

NO_BARE_PRINT = """\
---
title: No bare print calls
scope: project
tags:
  - output
  - python
status: active
source: config
priority: 5
---
Use `rich.console.Console` instead of bare `print()`.

Rationale: consistent formatting and testability.
"""

AUTH_ERROR_HANDLING = """\
---
title: Auth error handling
scope: src/auth
tags:
  - auth
  - errors
status: active
source: user
priority: 0
---
Auth modules must raise AuthenticationError, not generic ValueError.
"""

AUTH_LOGIN_SPECIFIC = """\
---
title: Login rate limiting
scope: src/auth/login
tags:
  - auth
  - security
status: draft
source: agent
priority: -1
---
Login endpoints must enforce rate limiting with token bucket.
"""

SRC_CONVENTIONS = """\
---
title: Type hints required
scope: src
tags:
  - typing
status: active
source: user
priority: 2
---
All public functions in src/ must have complete type hints.
"""

ROOT_SCOPE = """\
---
title: Root scope convention
scope: "."
tags:
  - style
status: active
source: user
priority: 0
---
Root-level convention for testing scope "." behaviour.
"""

DEPRECATED_CONVENTION = """\
---
title: Old naming convention
scope: project
tags:
  - naming
status: deprecated
source: user
priority: 0
---
Use camelCase for functions. Superseded by snake_case convention.
"""

DRAFT_CONVENTION = """\
---
title: Consider dataclasses
scope: src/models
tags:
  - python
  - patterns
status: draft
source: agent
priority: -1
---
Consider using dataclasses instead of plain dicts for data transfer.
"""

MALFORMED_FILE = """\
Not valid frontmatter at all.
Just random text.
"""


# ---------------------------------------------------------------------------
# TestConventionIndexLoad
# ---------------------------------------------------------------------------


class TestConventionIndexLoad:
    def test_load_empty_directory(self, tmp_path: Path) -> None:
        index = ConventionIndex(tmp_path)
        index.load()
        assert len(index) == 0
        assert index.conventions == []

    def test_load_nonexistent_directory(self, tmp_path: Path) -> None:
        index = ConventionIndex(tmp_path / "nonexistent")
        index.load()
        assert len(index) == 0
        assert index.conventions == []

    def test_load_multiple_conventions(self, tmp_path: Path) -> None:
        _write_convention(tmp_path, "future-annotations.md", FUTURE_ANNOTATIONS)
        _write_convention(tmp_path, "no-bare-print.md", NO_BARE_PRINT)
        _write_convention(tmp_path, "auth-error-handling.md", AUTH_ERROR_HANDLING)
        index = ConventionIndex(tmp_path)
        index.load()
        assert len(index) == 3

    def test_load_skips_malformed_files(self, tmp_path: Path) -> None:
        _write_convention(tmp_path, "future-annotations.md", FUTURE_ANNOTATIONS)
        _write_convention(tmp_path, "no-bare-print.md", NO_BARE_PRINT)
        _write_convention(tmp_path, "bad.md", MALFORMED_FILE)
        index = ConventionIndex(tmp_path)
        index.load()
        assert len(index) == 2

    def test_load_skips_non_md_files(self, tmp_path: Path) -> None:
        _write_convention(tmp_path, "future-annotations.md", FUTURE_ANNOTATIONS)
        (tmp_path / "notes.txt").write_text("not a convention")
        (tmp_path / ".gitkeep").write_text("")
        index = ConventionIndex(tmp_path)
        index.load()
        assert len(index) == 1

    def test_reload_replaces_previous(self, tmp_path: Path) -> None:
        _write_convention(tmp_path, "future-annotations.md", FUTURE_ANNOTATIONS)
        index = ConventionIndex(tmp_path)
        index.load()
        assert len(index) == 1

        _write_convention(tmp_path, "no-bare-print.md", NO_BARE_PRINT)
        index.load()
        assert len(index) == 2


# ---------------------------------------------------------------------------
# TestConventionIndexFindByScope
# ---------------------------------------------------------------------------


class TestConventionIndexFindByScope:
    def test_project_scope_matches_any_file(self, tmp_path: Path) -> None:
        _write_convention(tmp_path, "future-annotations.md", FUTURE_ANNOTATIONS)
        index = ConventionIndex(tmp_path)
        index.load()
        result = index.find_by_scope("src/auth/login.py")
        assert len(result) == 1
        assert result[0].frontmatter.title == "Future annotations import"

    def test_file_inherits_project_and_directory_scoped(self, tmp_path: Path) -> None:
        _write_convention(tmp_path, "future-annotations.md", FUTURE_ANNOTATIONS)
        _write_convention(tmp_path, "auth-error-handling.md", AUTH_ERROR_HANDLING)
        index = ConventionIndex(tmp_path)
        index.load()
        result = index.find_by_scope("src/auth/login.py")
        assert len(result) == 2
        # Project-scoped first, then directory-scoped
        assert result[0].frontmatter.title == "Future annotations import"
        assert result[1].frontmatter.title == "Auth error handling"

    def test_file_with_no_matching_scopes(self, tmp_path: Path) -> None:
        _write_convention(tmp_path, "auth-error-handling.md", AUTH_ERROR_HANDLING)
        index = ConventionIndex(tmp_path)
        index.load()
        result = index.find_by_scope("src/utils/helpers.py")
        assert result == []

    def test_priority_ordering_within_same_scope(self, tmp_path: Path) -> None:
        _write_convention(tmp_path, "no-bare-print.md", NO_BARE_PRINT)  # priority 5
        _write_convention(tmp_path, "future-annotations.md", FUTURE_ANNOTATIONS)  # priority 0
        index = ConventionIndex(tmp_path)
        index.load()
        result = index.find_by_scope("src/foo.py")
        assert len(result) == 2
        # Priority 5 before priority 0, both project scope
        assert result[0].frontmatter.title == "No bare print calls"
        assert result[1].frontmatter.title == "Future annotations import"

    def test_scope_root_limits_ancestry(self, tmp_path: Path) -> None:
        _write_convention(tmp_path, "future-annotations.md", FUTURE_ANNOTATIONS)  # project
        _write_convention(tmp_path, "root-scope.md", ROOT_SCOPE)  # scope "."
        _write_convention(tmp_path, "auth-error-handling.md", AUTH_ERROR_HANDLING)  # src/auth
        index = ConventionIndex(tmp_path)
        index.load()
        # With scope_root="src", "." should NOT match
        result = index.find_by_scope("src/auth/login.py", scope_root="src")
        titles = [c.frontmatter.title for c in result]
        # "project" always matches, "src/auth" matches, "." does NOT
        assert "Future annotations import" in titles
        assert "Auth error handling" in titles
        assert "Root scope convention" not in titles

    def test_root_to_leaf_ordering(self, tmp_path: Path) -> None:
        _write_convention(tmp_path, "future-annotations.md", FUTURE_ANNOTATIONS)  # project
        _write_convention(tmp_path, "src-types.md", SRC_CONVENTIONS)  # src
        _write_convention(tmp_path, "auth-error-handling.md", AUTH_ERROR_HANDLING)  # src/auth
        _write_convention(tmp_path, "login-rate-limit.md", AUTH_LOGIN_SPECIFIC)  # src/auth/login
        index = ConventionIndex(tmp_path)
        index.load()
        result = index.find_by_scope("src/auth/login/handler.py")
        titles = [c.frontmatter.title for c in result]
        # Order: project -> src -> src/auth -> src/auth/login
        assert titles.index("Future annotations import") < titles.index("Type hints required")
        assert titles.index("Type hints required") < titles.index("Auth error handling")
        assert titles.index("Auth error handling") < titles.index("Login rate limiting")

    def test_dot_scope_matches_at_project_root(self, tmp_path: Path) -> None:
        _write_convention(tmp_path, "root-scope.md", ROOT_SCOPE)
        index = ConventionIndex(tmp_path)
        index.load()
        result = index.find_by_scope("src/foo.py")
        assert len(result) == 1
        assert result[0].frontmatter.title == "Root scope convention"

    def test_empty_index_returns_empty_list(self, tmp_path: Path) -> None:
        index = ConventionIndex(tmp_path)
        index.load()
        result = index.find_by_scope("src/foo.py")
        assert result == []


# ---------------------------------------------------------------------------
# TestConventionIndexFindByScopeLimited
# ---------------------------------------------------------------------------


class TestConventionIndexFindByScopeLimited:
    def test_under_limit_returns_all(self, tmp_path: Path) -> None:
        _write_convention(tmp_path, "future-annotations.md", FUTURE_ANNOTATIONS)
        _write_convention(tmp_path, "no-bare-print.md", NO_BARE_PRINT)
        _write_convention(tmp_path, "auth-error-handling.md", AUTH_ERROR_HANDLING)
        index = ConventionIndex(tmp_path)
        index.load()
        result, total = index.find_by_scope_limited("src/auth/login.py", limit=5)
        assert total == 3
        assert len(result) == 3

    def test_over_limit_truncates_root_ward(self, tmp_path: Path) -> None:
        # Create 4 conventions across different scope levels
        _write_convention(tmp_path, "future-annotations.md", FUTURE_ANNOTATIONS)  # project
        _write_convention(tmp_path, "no-bare-print.md", NO_BARE_PRINT)  # project
        _write_convention(tmp_path, "src-types.md", SRC_CONVENTIONS)  # src
        _write_convention(tmp_path, "auth-error-handling.md", AUTH_ERROR_HANDLING)  # src/auth
        index = ConventionIndex(tmp_path)
        index.load()
        result, total = index.find_by_scope_limited("src/auth/login.py", limit=2)
        assert total == 4
        assert len(result) == 2
        # Should keep the most-specific (leaf-ward): src and src/auth
        titles = [c.frontmatter.title for c in result]
        assert "Auth error handling" in titles
        assert "Type hints required" in titles

    def test_limit_zero_returns_empty(self, tmp_path: Path) -> None:
        _write_convention(tmp_path, "future-annotations.md", FUTURE_ANNOTATIONS)
        index = ConventionIndex(tmp_path)
        index.load()
        result, total = index.find_by_scope_limited("src/foo.py", limit=0)
        assert result == []
        assert total == 1

    def test_exact_limit_returns_all(self, tmp_path: Path) -> None:
        _write_convention(tmp_path, "future-annotations.md", FUTURE_ANNOTATIONS)
        _write_convention(tmp_path, "no-bare-print.md", NO_BARE_PRINT)
        index = ConventionIndex(tmp_path)
        index.load()
        result, total = index.find_by_scope_limited("src/foo.py", limit=2)
        assert total == 2
        assert len(result) == 2


# ---------------------------------------------------------------------------
# TestConventionIndexSearch
# ---------------------------------------------------------------------------


class TestConventionIndexSearch:
    def test_search_by_title(self, tmp_path: Path) -> None:
        _write_convention(tmp_path, "future-annotations.md", FUTURE_ANNOTATIONS)
        _write_convention(tmp_path, "no-bare-print.md", NO_BARE_PRINT)
        index = ConventionIndex(tmp_path)
        index.load()
        results = index.search("annotations")
        assert len(results) == 1
        assert results[0].frontmatter.title == "Future annotations import"

    def test_search_by_body_content(self, tmp_path: Path) -> None:
        _write_convention(tmp_path, "future-annotations.md", FUTURE_ANNOTATIONS)
        index = ConventionIndex(tmp_path)
        index.load()
        results = index.search("PEP 604")
        assert len(results) == 1
        assert results[0].frontmatter.title == "Future annotations import"

    def test_search_by_tag(self, tmp_path: Path) -> None:
        _write_convention(tmp_path, "future-annotations.md", FUTURE_ANNOTATIONS)
        _write_convention(tmp_path, "no-bare-print.md", NO_BARE_PRINT)
        index = ConventionIndex(tmp_path)
        index.load()
        results = index.search("typing")
        assert len(results) == 1
        assert results[0].frontmatter.title == "Future annotations import"

    def test_search_case_insensitive(self, tmp_path: Path) -> None:
        _write_convention(tmp_path, "future-annotations.md", FUTURE_ANNOTATIONS)
        index = ConventionIndex(tmp_path)
        index.load()
        results = index.search("FUTURE")
        assert len(results) == 1

    def test_search_no_results(self, tmp_path: Path) -> None:
        _write_convention(tmp_path, "future-annotations.md", FUTURE_ANNOTATIONS)
        index = ConventionIndex(tmp_path)
        index.load()
        results = index.search("nonexistent")
        assert results == []

    def test_search_empty_query(self, tmp_path: Path) -> None:
        _write_convention(tmp_path, "future-annotations.md", FUTURE_ANNOTATIONS)
        index = ConventionIndex(tmp_path)
        index.load()
        results = index.search("")
        assert results == []

    def test_search_results_sorted_by_title(self, tmp_path: Path) -> None:
        _write_convention(tmp_path, "future-annotations.md", FUTURE_ANNOTATIONS)
        _write_convention(tmp_path, "no-bare-print.md", NO_BARE_PRINT)
        index = ConventionIndex(tmp_path)
        index.load()
        # Both match "python" tag
        results = index.search("python")
        titles = [r.frontmatter.title for r in results]
        assert titles == sorted(titles)

    def test_search_no_duplicates(self, tmp_path: Path) -> None:
        _write_convention(tmp_path, "future-annotations.md", FUTURE_ANNOTATIONS)
        index = ConventionIndex(tmp_path)
        index.load()
        # "python" matches both tag and body
        results = index.search("python")
        assert len(results) == 1


# ---------------------------------------------------------------------------
# TestConventionIndexByTag
# ---------------------------------------------------------------------------


class TestConventionIndexByTag:
    def test_filter_by_tag_single_match(self, tmp_path: Path) -> None:
        _write_convention(tmp_path, "future-annotations.md", FUTURE_ANNOTATIONS)
        _write_convention(tmp_path, "auth-error-handling.md", AUTH_ERROR_HANDLING)
        index = ConventionIndex(tmp_path)
        index.load()
        results = index.by_tag("typing")
        assert len(results) == 1
        assert results[0].frontmatter.title == "Future annotations import"

    def test_filter_by_tag_multiple_matches(self, tmp_path: Path) -> None:
        _write_convention(tmp_path, "future-annotations.md", FUTURE_ANNOTATIONS)
        _write_convention(tmp_path, "no-bare-print.md", NO_BARE_PRINT)
        index = ConventionIndex(tmp_path)
        index.load()
        results = index.by_tag("python")
        assert len(results) == 2

    def test_filter_by_tag_case_insensitive(self, tmp_path: Path) -> None:
        _write_convention(tmp_path, "future-annotations.md", FUTURE_ANNOTATIONS)
        index = ConventionIndex(tmp_path)
        index.load()
        results = index.by_tag("PYTHON")
        assert len(results) == 1

    def test_filter_by_tag_no_match(self, tmp_path: Path) -> None:
        _write_convention(tmp_path, "future-annotations.md", FUTURE_ANNOTATIONS)
        index = ConventionIndex(tmp_path)
        index.load()
        results = index.by_tag("database")
        assert results == []

    def test_filter_by_tag_results_sorted(self, tmp_path: Path) -> None:
        _write_convention(tmp_path, "future-annotations.md", FUTURE_ANNOTATIONS)
        _write_convention(tmp_path, "no-bare-print.md", NO_BARE_PRINT)
        index = ConventionIndex(tmp_path)
        index.load()
        results = index.by_tag("python")
        titles = [r.frontmatter.title for r in results]
        assert titles == sorted(titles)


# ---------------------------------------------------------------------------
# TestConventionIndexByStatus
# ---------------------------------------------------------------------------


class TestConventionIndexByStatus:
    def test_filter_by_active_status(self, tmp_path: Path) -> None:
        _write_convention(tmp_path, "future-annotations.md", FUTURE_ANNOTATIONS)
        _write_convention(tmp_path, "deprecated-naming.md", DEPRECATED_CONVENTION)
        _write_convention(tmp_path, "draft-dataclasses.md", DRAFT_CONVENTION)
        index = ConventionIndex(tmp_path)
        index.load()
        results = index.by_status("active")
        assert len(results) == 1
        assert results[0].frontmatter.title == "Future annotations import"

    def test_filter_by_draft_status(self, tmp_path: Path) -> None:
        _write_convention(tmp_path, "future-annotations.md", FUTURE_ANNOTATIONS)
        _write_convention(tmp_path, "draft-dataclasses.md", DRAFT_CONVENTION)
        _write_convention(tmp_path, "login-rate-limit.md", AUTH_LOGIN_SPECIFIC)
        index = ConventionIndex(tmp_path)
        index.load()
        results = index.by_status("draft")
        assert len(results) == 2

    def test_filter_by_deprecated_status(self, tmp_path: Path) -> None:
        _write_convention(tmp_path, "deprecated-naming.md", DEPRECATED_CONVENTION)
        _write_convention(tmp_path, "future-annotations.md", FUTURE_ANNOTATIONS)
        index = ConventionIndex(tmp_path)
        index.load()
        results = index.by_status("deprecated")
        assert len(results) == 1
        assert results[0].frontmatter.title == "Old naming convention"

    def test_filter_by_status_no_match(self, tmp_path: Path) -> None:
        _write_convention(tmp_path, "future-annotations.md", FUTURE_ANNOTATIONS)
        index = ConventionIndex(tmp_path)
        index.load()
        results = index.by_status("deprecated")
        assert results == []

    def test_filter_by_status_results_sorted(self, tmp_path: Path) -> None:
        _write_convention(tmp_path, "draft-dataclasses.md", DRAFT_CONVENTION)
        _write_convention(tmp_path, "login-rate-limit.md", AUTH_LOGIN_SPECIFIC)
        index = ConventionIndex(tmp_path)
        index.load()
        results = index.by_status("draft")
        titles = [r.frontmatter.title for r in results]
        assert titles == sorted(titles)


# ---------------------------------------------------------------------------
# TestConventionIndexNames
# ---------------------------------------------------------------------------


class TestConventionIndexNames:
    def test_names_returns_sorted_titles(self, tmp_path: Path) -> None:
        _write_convention(tmp_path, "no-bare-print.md", NO_BARE_PRINT)
        _write_convention(tmp_path, "future-annotations.md", FUTURE_ANNOTATIONS)
        _write_convention(tmp_path, "auth-error-handling.md", AUTH_ERROR_HANDLING)
        index = ConventionIndex(tmp_path)
        index.load()
        assert index.names() == [
            "Auth error handling",
            "Future annotations import",
            "No bare print calls",
        ]

    def test_names_empty_index(self, tmp_path: Path) -> None:
        index = ConventionIndex(tmp_path)
        index.load()
        assert index.names() == []


# ---------------------------------------------------------------------------
# TestConventionIndexImport
# ---------------------------------------------------------------------------


class TestConventionIndexImport:
    def test_importable_from_conventions_package(self) -> None:
        from lexibrary.conventions import ConventionIndex

        assert ConventionIndex is not None
