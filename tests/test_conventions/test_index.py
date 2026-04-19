"""Tests for convention index -- load, scope resolution, display limit, search, filters."""

from __future__ import annotations

from pathlib import Path

from lexibrary.config.schema import ScopeRoot
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
id: CV-001
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
id: CV-002
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
id: CV-003
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
id: CV-004
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
id: CV-005
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
id: CV-006
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
id: CV-007
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
id: CV-008
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

CONVENTION_WITH_ALIASES = """\
---
title: All endpoints require auth decorator
id: CV-009
scope: src/api
tags:
  - auth
  - security
status: active
source: user
priority: 0
aliases:
  - auth-decorator
  - require-auth
---
Every API endpoint must use the @require_auth decorator.
"""

MULTI_PATH_SCOPE = """\
---
title: CLI service extraction pattern
id: CV-010
scope: src/cli, src/services
tags:
  - cli
  - services
status: active
source: agent
priority: 0
---
New CLI commands must separate domain logic into a service module.
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

    def test_multi_path_scope_matches_first_directory(self, tmp_path: Path) -> None:
        _write_convention(tmp_path, "multi-scope.md", MULTI_PATH_SCOPE)
        index = ConventionIndex(tmp_path)
        index.load()
        result = index.find_by_scope("src/cli/app.py")
        assert len(result) == 1
        assert result[0].frontmatter.title == "CLI service extraction pattern"

    def test_multi_path_scope_matches_second_directory(self, tmp_path: Path) -> None:
        _write_convention(tmp_path, "multi-scope.md", MULTI_PATH_SCOPE)
        index = ConventionIndex(tmp_path)
        index.load()
        result = index.find_by_scope("src/services/lookup.py")
        assert len(result) == 1
        assert result[0].frontmatter.title == "CLI service extraction pattern"

    def test_multi_path_scope_does_not_match_unrelated(self, tmp_path: Path) -> None:
        _write_convention(tmp_path, "multi-scope.md", MULTI_PATH_SCOPE)
        index = ConventionIndex(tmp_path)
        index.load()
        result = index.find_by_scope("src/utils/helpers.py")
        assert result == []

    def test_multi_path_scope_ordering_with_project(self, tmp_path: Path) -> None:
        _write_convention(tmp_path, "future-annotations.md", FUTURE_ANNOTATIONS)  # project
        _write_convention(tmp_path, "multi-scope.md", MULTI_PATH_SCOPE)  # src/cli, src/services
        index = ConventionIndex(tmp_path)
        index.load()
        result = index.find_by_scope("src/cli/app.py")
        assert len(result) == 2
        # project scope first, then directory scope
        assert result[0].frontmatter.title == "Future annotations import"
        assert result[1].frontmatter.title == "CLI service extraction pattern"


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
# Multi-root convention fixtures (group 4)
# ---------------------------------------------------------------------------

BAML_SRC_FOO_CONVENTION = """\
---
title: BAML foo formatting
id: CV-100
scope: baml_src/foo
tags:
  - baml
status: active
source: user
priority: 0
---
BAML files under baml_src/foo must use camelCase enum values.
"""

BAML_SRC_ROOT_CONVENTION = """\
---
title: BAML conventions
id: CV-101
scope: baml_src
tags:
  - baml
status: active
source: user
priority: 0
---
All BAML modules must declare the version header.
"""

SRC_FOO_CONVENTION = """\
---
title: Src foo helpers
id: CV-102
scope: src/foo
tags:
  - python
status: active
source: user
priority: 0
---
Helpers under src/foo must export via __all__.
"""

MULTI_BAML_PATH_SCOPE = """\
---
title: BAML cross-directory pattern
id: CV-103
scope: baml_src/foo, baml_src/bar
tags:
  - baml
  - patterns
status: active
source: user
priority: 0
---
BAML modules under baml_src/foo and baml_src/bar must share generator config.
"""


# ---------------------------------------------------------------------------
# TestConventionIndexFindByAnyScope
# ---------------------------------------------------------------------------


class TestConventionIndexFindByAnyScope:
    """Tests for the multi-root ``find_by_any_scope`` entry point."""

    def test_file_under_second_declared_root_matches(self, tmp_path: Path) -> None:
        """A convention scoped under the second declared root matches files there."""
        _write_convention(tmp_path, "baml-foo.md", BAML_SRC_FOO_CONVENTION)
        index = ConventionIndex(tmp_path)
        index.load()
        roots = [ScopeRoot(path="src/"), ScopeRoot(path="baml_src/")]
        result = index.find_by_any_scope("baml_src/foo/example.baml", roots)
        assert len(result) == 1
        assert result[0].frontmatter.title == "BAML foo formatting"

    def test_dot_scope_always_matches_under_any_root(self, tmp_path: Path) -> None:
        """Convention with ``scope: "."`` matches a file owned by ``src/``."""
        _write_convention(tmp_path, "root-scope.md", ROOT_SCOPE)
        index = ConventionIndex(tmp_path)
        index.load()
        roots = [ScopeRoot(path="src/"), ScopeRoot(path="baml_src/")]
        result = index.find_by_any_scope("src/foo.py", roots)
        assert len(result) == 1
        assert result[0].frontmatter.title == "Root scope convention"

    def test_dot_scope_matches_file_under_second_root(self, tmp_path: Path) -> None:
        """Convention with ``scope: "."`` also matches files under the second root."""
        _write_convention(tmp_path, "root-scope.md", ROOT_SCOPE)
        index = ConventionIndex(tmp_path)
        index.load()
        roots = [ScopeRoot(path="src/"), ScopeRoot(path="baml_src/")]
        result = index.find_by_any_scope("baml_src/foo.baml", roots)
        assert len(result) == 1
        assert result[0].frontmatter.title == "Root scope convention"

    def test_scope_path_in_other_root_does_not_match(self, tmp_path: Path) -> None:
        """``scope: src/foo`` MUST NOT match a file owned by ``baml_src/``."""
        _write_convention(tmp_path, "src-foo.md", SRC_FOO_CONVENTION)
        index = ConventionIndex(tmp_path)
        index.load()
        roots = [ScopeRoot(path="src/"), ScopeRoot(path="baml_src/")]
        result = index.find_by_any_scope("baml_src/foo/x.baml", roots)
        assert result == []

    def test_file_outside_all_roots_returns_empty(self, tmp_path: Path) -> None:
        """A file under no declared root resolves to no owning root → no matches."""
        _write_convention(tmp_path, "future-annotations.md", FUTURE_ANNOTATIONS)
        _write_convention(tmp_path, "root-scope.md", ROOT_SCOPE)
        index = ConventionIndex(tmp_path)
        index.load()
        roots = [ScopeRoot(path="src/"), ScopeRoot(path="baml_src/")]
        result = index.find_by_any_scope("docs/README.md", roots)
        assert result == []

    def test_project_scope_matches_under_any_root(self, tmp_path: Path) -> None:
        """``scope: "project"`` always matches, mirroring single-root semantics."""
        _write_convention(tmp_path, "future-annotations.md", FUTURE_ANNOTATIONS)
        index = ConventionIndex(tmp_path)
        index.load()
        roots = [ScopeRoot(path="src/"), ScopeRoot(path="baml_src/")]
        for path in ("src/foo.py", "baml_src/foo.baml"):
            result = index.find_by_any_scope(path, roots)
            assert len(result) == 1
            assert result[0].frontmatter.title == "Future annotations import"

    def test_first_match_wins_for_owning_root(self, tmp_path: Path) -> None:
        """Owning-root selection follows declared-order first-match-wins.

        With ``scope_roots: [".", "src/"]``, every path is owned by ".".
        A convention scoped under ``src/foo`` then matches files inside it,
        because ancestry from ``src/foo/x.py`` up to the project root
        passes through ``src/foo``.
        """
        _write_convention(tmp_path, "src-foo.md", SRC_FOO_CONVENTION)
        index = ConventionIndex(tmp_path)
        index.load()
        roots = [ScopeRoot(path="."), ScopeRoot(path="src/")]
        result = index.find_by_any_scope("src/foo/helper.py", roots)
        assert len(result) == 1
        assert result[0].frontmatter.title == "Src foo helpers"

    def test_root_to_leaf_ordering_with_dot_and_owning_root(self, tmp_path: Path) -> None:
        """Ordering: ``project`` first, then ``.``, then owning root, then deeper."""
        _write_convention(tmp_path, "project.md", FUTURE_ANNOTATIONS)  # project
        _write_convention(tmp_path, "dot.md", ROOT_SCOPE)  # scope "."
        _write_convention(tmp_path, "baml-root.md", BAML_SRC_ROOT_CONVENTION)  # baml_src
        _write_convention(tmp_path, "baml-foo.md", BAML_SRC_FOO_CONVENTION)  # baml_src/foo
        index = ConventionIndex(tmp_path)
        index.load()
        roots = [ScopeRoot(path="src/"), ScopeRoot(path="baml_src/")]
        result = index.find_by_any_scope("baml_src/foo/example.baml", roots)
        titles = [c.frontmatter.title for c in result]
        # project → "." → baml_src → baml_src/foo
        assert titles == [
            "Future annotations import",
            "Root scope convention",
            "BAML conventions",
            "BAML foo formatting",
        ]

    def test_st006_comma_split_under_multi_root(self, tmp_path: Path) -> None:
        """Regression: comma-split scopes still work under multi-root.

        A convention with ``scope: baml_src/foo, baml_src/bar`` must match
        files in EITHER directory when the project declares
        ``scope_roots: [src, baml_src]``.
        """
        _write_convention(tmp_path, "multi-baml.md", MULTI_BAML_PATH_SCOPE)
        index = ConventionIndex(tmp_path)
        index.load()
        roots = [ScopeRoot(path="src/"), ScopeRoot(path="baml_src/")]

        result_foo = index.find_by_any_scope("baml_src/foo/example.baml", roots)
        assert len(result_foo) == 1
        assert result_foo[0].frontmatter.title == "BAML cross-directory pattern"

        result_bar = index.find_by_any_scope("baml_src/bar/example.baml", roots)
        assert len(result_bar) == 1
        assert result_bar[0].frontmatter.title == "BAML cross-directory pattern"

        # Sibling directory not in the comma list must NOT match.
        result_baz = index.find_by_any_scope("baml_src/baz/example.baml", roots)
        assert result_baz == []

    def test_empty_index_returns_empty(self, tmp_path: Path) -> None:
        """No conventions loaded → no matches even when the file is in scope."""
        index = ConventionIndex(tmp_path)
        index.load()
        roots = [ScopeRoot(path="src/"), ScopeRoot(path="baml_src/")]
        result = index.find_by_any_scope("src/foo.py", roots)
        assert result == []

    def test_single_root_dot_behaves_like_single_root_helper(self, tmp_path: Path) -> None:
        """``scope_roots: [{path: "."}]`` should match the legacy single-root behaviour."""
        _write_convention(tmp_path, "future-annotations.md", FUTURE_ANNOTATIONS)
        _write_convention(tmp_path, "root-scope.md", ROOT_SCOPE)
        _write_convention(tmp_path, "auth-error-handling.md", AUTH_ERROR_HANDLING)
        index = ConventionIndex(tmp_path)
        index.load()

        single = [ScopeRoot(path=".")]
        multi = index.find_by_any_scope("src/auth/login.py", single)
        legacy = index.find_by_scope("src/auth/login.py")
        assert [c.frontmatter.title for c in multi] == [c.frontmatter.title for c in legacy]


# ---------------------------------------------------------------------------
# TestConventionIndexFindByAnyScopeLimited
# ---------------------------------------------------------------------------


class TestConventionIndexFindByAnyScopeLimited:
    """Tests for the multi-root ``find_by_any_scope_limited`` entry point."""

    def test_under_limit_returns_all(self, tmp_path: Path) -> None:
        _write_convention(tmp_path, "project.md", FUTURE_ANNOTATIONS)
        _write_convention(tmp_path, "baml-foo.md", BAML_SRC_FOO_CONVENTION)
        index = ConventionIndex(tmp_path)
        index.load()
        roots = [ScopeRoot(path="src/"), ScopeRoot(path="baml_src/")]
        result, total = index.find_by_any_scope_limited("baml_src/foo/example.baml", roots, limit=5)
        assert total == 2
        assert len(result) == 2

    def test_over_limit_truncates_root_ward(self, tmp_path: Path) -> None:
        """Over the limit, root-ward conventions are dropped first."""
        _write_convention(tmp_path, "project.md", FUTURE_ANNOTATIONS)  # project
        _write_convention(tmp_path, "dot.md", ROOT_SCOPE)  # scope "."
        _write_convention(tmp_path, "baml-root.md", BAML_SRC_ROOT_CONVENTION)  # baml_src
        _write_convention(tmp_path, "baml-foo.md", BAML_SRC_FOO_CONVENTION)  # baml_src/foo
        index = ConventionIndex(tmp_path)
        index.load()
        roots = [ScopeRoot(path="src/"), ScopeRoot(path="baml_src/")]
        result, total = index.find_by_any_scope_limited("baml_src/foo/example.baml", roots, limit=2)
        assert total == 4
        # Most leaf-ward kept: baml_src + baml_src/foo
        titles = [c.frontmatter.title for c in result]
        assert titles == ["BAML conventions", "BAML foo formatting"]

    def test_limit_zero_returns_empty_with_total(self, tmp_path: Path) -> None:
        _write_convention(tmp_path, "baml-foo.md", BAML_SRC_FOO_CONVENTION)
        index = ConventionIndex(tmp_path)
        index.load()
        roots = [ScopeRoot(path="src/"), ScopeRoot(path="baml_src/")]
        result, total = index.find_by_any_scope_limited("baml_src/foo/example.baml", roots, limit=0)
        assert result == []
        assert total == 1

    def test_no_owning_root_returns_empty_zero_total(self, tmp_path: Path) -> None:
        """No matches for an out-of-scope file → ``([], 0)``."""
        _write_convention(tmp_path, "baml-foo.md", BAML_SRC_FOO_CONVENTION)
        index = ConventionIndex(tmp_path)
        index.load()
        roots = [ScopeRoot(path="src/"), ScopeRoot(path="baml_src/")]
        result, total = index.find_by_any_scope_limited("docs/README.md", roots, limit=5)
        assert result == []
        assert total == 0


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

    def test_search_by_alias_substring(self, tmp_path: Path) -> None:
        _write_convention(tmp_path, "auth-decorator.md", CONVENTION_WITH_ALIASES)
        _write_convention(tmp_path, "future-annotations.md", FUTURE_ANNOTATIONS)
        index = ConventionIndex(tmp_path)
        index.load()
        results = index.search("auth-dec")
        assert len(results) == 1
        assert results[0].frontmatter.title == "All endpoints require auth decorator"

    def test_search_by_alias_case_insensitive(self, tmp_path: Path) -> None:
        _write_convention(tmp_path, "auth-decorator.md", CONVENTION_WITH_ALIASES)
        index = ConventionIndex(tmp_path)
        index.load()
        results = index.search("AUTH-DECORATOR")
        assert len(results) == 1
        assert results[0].frontmatter.title == "All endpoints require auth decorator"

    def test_search_by_alias_second_alias(self, tmp_path: Path) -> None:
        _write_convention(tmp_path, "auth-decorator.md", CONVENTION_WITH_ALIASES)
        index = ConventionIndex(tmp_path)
        index.load()
        results = index.search("require-auth")
        assert len(results) == 1
        assert results[0].frontmatter.title == "All endpoints require auth decorator"

    def test_search_alias_no_duplicate_with_title(self, tmp_path: Path) -> None:
        _write_convention(tmp_path, "auth-decorator.md", CONVENTION_WITH_ALIASES)
        index = ConventionIndex(tmp_path)
        index.load()
        # "auth" matches both the title and the alias; should return only one result
        results = index.search("auth")
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
