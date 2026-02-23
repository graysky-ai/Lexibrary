"""Tests for wiki concept index."""

from __future__ import annotations

from pathlib import Path

from lexibrary.wiki.index import ConceptIndex


def _write_concept(directory: Path, filename: str, content: str) -> Path:
    """Helper to write a concept markdown file."""
    path = directory / filename
    path.write_text(content, encoding="utf-8")
    return path


JWT_CONCEPT = """\
---
title: JWT Auth
aliases:
  - JSON Web Token
tags:
  - auth
  - security
status: active
---
This concept covers authentication patterns using JWT tokens.

## Details

JWT tokens are used for stateless authentication.
"""

RATE_LIMITING_CONCEPT = """\
---
title: Rate Limiting
aliases:
  - Throttling
tags:
  - api
  - security
status: draft
---
Controls the rate of requests to protect services.

## Details

Token bucket algorithm is common.
"""

OAUTH_CONCEPT = """\
---
title: OAuth2 Flow
aliases: []
tags:
  - auth
status: active
---
OAuth2 authorization code flow for third-party integrations.
"""

DEPRECATED_CONCEPT = """\
---
title: Session Cookies
aliases:
  - Cookie Auth
tags:
  - auth
status: deprecated
superseded_by: JWT Auth
---
Legacy session-based authentication using cookies.
"""


class TestConceptIndexLoad:
    def test_load_empty_directory(self, tmp_path: Path) -> None:
        index = ConceptIndex.load(tmp_path)
        assert len(index) == 0

    def test_load_nonexistent_directory(self, tmp_path: Path) -> None:
        index = ConceptIndex.load(tmp_path / "nonexistent")
        assert len(index) == 0

    def test_load_multiple_concepts(self, tmp_path: Path) -> None:
        _write_concept(tmp_path, "JWTAuth.md", JWT_CONCEPT)
        _write_concept(tmp_path, "RateLimiting.md", RATE_LIMITING_CONCEPT)
        _write_concept(tmp_path, "OAuth2Flow.md", OAUTH_CONCEPT)
        index = ConceptIndex.load(tmp_path)
        assert len(index) == 3

    def test_load_skips_invalid_files(self, tmp_path: Path) -> None:
        _write_concept(tmp_path, "JWTAuth.md", JWT_CONCEPT)
        _write_concept(tmp_path, "Bad.md", "# No frontmatter\nJust text.\n")
        index = ConceptIndex.load(tmp_path)
        assert len(index) == 1

    def test_load_skips_non_md_files(self, tmp_path: Path) -> None:
        _write_concept(tmp_path, "JWTAuth.md", JWT_CONCEPT)
        (tmp_path / "notes.txt").write_text("not a concept")
        index = ConceptIndex.load(tmp_path)
        assert len(index) == 1


class TestConceptIndexNames:
    def test_names_returns_sorted_titles(self, tmp_path: Path) -> None:
        _write_concept(tmp_path, "RateLimiting.md", RATE_LIMITING_CONCEPT)
        _write_concept(tmp_path, "JWTAuth.md", JWT_CONCEPT)
        _write_concept(tmp_path, "OAuth2Flow.md", OAUTH_CONCEPT)
        index = ConceptIndex.load(tmp_path)
        assert index.names() == ["JWT Auth", "OAuth2 Flow", "Rate Limiting"]

    def test_names_empty_index(self, tmp_path: Path) -> None:
        index = ConceptIndex.load(tmp_path)
        assert index.names() == []


class TestConceptIndexFind:
    def test_find_exact_title(self, tmp_path: Path) -> None:
        _write_concept(tmp_path, "JWTAuth.md", JWT_CONCEPT)
        index = ConceptIndex.load(tmp_path)
        result = index.find("JWT Auth")
        assert result is not None
        assert result.frontmatter.title == "JWT Auth"

    def test_find_case_insensitive(self, tmp_path: Path) -> None:
        _write_concept(tmp_path, "JWTAuth.md", JWT_CONCEPT)
        index = ConceptIndex.load(tmp_path)
        result = index.find("jwt auth")
        assert result is not None
        assert result.frontmatter.title == "JWT Auth"

    def test_find_by_alias(self, tmp_path: Path) -> None:
        _write_concept(tmp_path, "JWTAuth.md", JWT_CONCEPT)
        index = ConceptIndex.load(tmp_path)
        result = index.find("JSON Web Token")
        assert result is not None
        assert result.frontmatter.title == "JWT Auth"

    def test_find_alias_case_insensitive(self, tmp_path: Path) -> None:
        _write_concept(tmp_path, "RateLimiting.md", RATE_LIMITING_CONCEPT)
        index = ConceptIndex.load(tmp_path)
        result = index.find("throttling")
        assert result is not None
        assert result.frontmatter.title == "Rate Limiting"

    def test_find_not_found(self, tmp_path: Path) -> None:
        _write_concept(tmp_path, "JWTAuth.md", JWT_CONCEPT)
        index = ConceptIndex.load(tmp_path)
        assert index.find("Nonexistent") is None

    def test_find_with_whitespace(self, tmp_path: Path) -> None:
        _write_concept(tmp_path, "JWTAuth.md", JWT_CONCEPT)
        index = ConceptIndex.load(tmp_path)
        result = index.find("  JWT Auth  ")
        assert result is not None

    def test_contains_operator(self, tmp_path: Path) -> None:
        _write_concept(tmp_path, "JWTAuth.md", JWT_CONCEPT)
        index = ConceptIndex.load(tmp_path)
        assert "JWT Auth" in index
        assert "json web token" in index
        assert "Nonexistent" not in index


class TestConceptIndexSearch:
    def test_search_by_title_substring(self, tmp_path: Path) -> None:
        _write_concept(tmp_path, "JWTAuth.md", JWT_CONCEPT)
        _write_concept(tmp_path, "RateLimiting.md", RATE_LIMITING_CONCEPT)
        index = ConceptIndex.load(tmp_path)
        results = index.search("jwt")
        assert len(results) == 1
        assert results[0].frontmatter.title == "JWT Auth"

    def test_search_by_alias_substring(self, tmp_path: Path) -> None:
        _write_concept(tmp_path, "JWTAuth.md", JWT_CONCEPT)
        index = ConceptIndex.load(tmp_path)
        results = index.search("web token")
        assert len(results) == 1
        assert results[0].frontmatter.title == "JWT Auth"

    def test_search_by_tag(self, tmp_path: Path) -> None:
        _write_concept(tmp_path, "JWTAuth.md", JWT_CONCEPT)
        _write_concept(tmp_path, "RateLimiting.md", RATE_LIMITING_CONCEPT)
        _write_concept(tmp_path, "OAuth2Flow.md", OAUTH_CONCEPT)
        index = ConceptIndex.load(tmp_path)
        results = index.search("auth")
        titles = [r.frontmatter.title for r in results]
        assert "JWT Auth" in titles
        assert "OAuth2 Flow" in titles

    def test_search_by_summary(self, tmp_path: Path) -> None:
        _write_concept(tmp_path, "JWTAuth.md", JWT_CONCEPT)
        _write_concept(tmp_path, "RateLimiting.md", RATE_LIMITING_CONCEPT)
        index = ConceptIndex.load(tmp_path)
        results = index.search("authentication")
        assert len(results) == 1
        assert results[0].frontmatter.title == "JWT Auth"

    def test_search_case_insensitive(self, tmp_path: Path) -> None:
        _write_concept(tmp_path, "RateLimiting.md", RATE_LIMITING_CONCEPT)
        index = ConceptIndex.load(tmp_path)
        results = index.search("RATE")
        assert len(results) == 1

    def test_search_no_results(self, tmp_path: Path) -> None:
        _write_concept(tmp_path, "JWTAuth.md", JWT_CONCEPT)
        index = ConceptIndex.load(tmp_path)
        results = index.search("kubernetes")
        assert results == []

    def test_search_empty_query(self, tmp_path: Path) -> None:
        _write_concept(tmp_path, "JWTAuth.md", JWT_CONCEPT)
        index = ConceptIndex.load(tmp_path)
        results = index.search("")
        assert results == []

    def test_search_results_sorted_by_title(self, tmp_path: Path) -> None:
        _write_concept(tmp_path, "JWTAuth.md", JWT_CONCEPT)
        _write_concept(tmp_path, "RateLimiting.md", RATE_LIMITING_CONCEPT)
        _write_concept(tmp_path, "SessionCookies.md", DEPRECATED_CONCEPT)
        index = ConceptIndex.load(tmp_path)
        # "security" matches JWT Auth (tag) and Rate Limiting (tag)
        results = index.search("security")
        titles = [r.frontmatter.title for r in results]
        assert titles == sorted(titles)

    def test_search_no_duplicates(self, tmp_path: Path) -> None:
        _write_concept(tmp_path, "JWTAuth.md", JWT_CONCEPT)
        index = ConceptIndex.load(tmp_path)
        # "auth" matches both title ("JWT Auth") and tag ("auth")
        results = index.search("auth")
        assert len(results) == 1

    def test_search_across_multiple_fields(self, tmp_path: Path) -> None:
        _write_concept(tmp_path, "JWTAuth.md", JWT_CONCEPT)
        _write_concept(tmp_path, "RateLimiting.md", RATE_LIMITING_CONCEPT)
        _write_concept(tmp_path, "OAuth2Flow.md", OAUTH_CONCEPT)
        _write_concept(tmp_path, "SessionCookies.md", DEPRECATED_CONCEPT)
        index = ConceptIndex.load(tmp_path)
        # "cookie" matches Session Cookies by title and alias
        results = index.search("cookie")
        assert len(results) == 1
        assert results[0].frontmatter.title == "Session Cookies"


class TestConceptIndexByTag:
    def test_by_tag_single_match(self, tmp_path: Path) -> None:
        _write_concept(tmp_path, "RateLimiting.md", RATE_LIMITING_CONCEPT)
        _write_concept(tmp_path, "JWTAuth.md", JWT_CONCEPT)
        index = ConceptIndex.load(tmp_path)
        results = index.by_tag("api")
        assert len(results) == 1
        assert results[0].frontmatter.title == "Rate Limiting"

    def test_by_tag_multiple_matches(self, tmp_path: Path) -> None:
        _write_concept(tmp_path, "JWTAuth.md", JWT_CONCEPT)
        _write_concept(tmp_path, "RateLimiting.md", RATE_LIMITING_CONCEPT)
        index = ConceptIndex.load(tmp_path)
        results = index.by_tag("security")
        titles = [r.frontmatter.title for r in results]
        assert "JWT Auth" in titles
        assert "Rate Limiting" in titles

    def test_by_tag_case_insensitive(self, tmp_path: Path) -> None:
        _write_concept(tmp_path, "JWTAuth.md", JWT_CONCEPT)
        index = ConceptIndex.load(tmp_path)
        results = index.by_tag("AUTH")
        assert len(results) == 1

    def test_by_tag_no_match(self, tmp_path: Path) -> None:
        _write_concept(tmp_path, "JWTAuth.md", JWT_CONCEPT)
        index = ConceptIndex.load(tmp_path)
        results = index.by_tag("database")
        assert results == []

    def test_by_tag_results_sorted(self, tmp_path: Path) -> None:
        _write_concept(tmp_path, "JWTAuth.md", JWT_CONCEPT)
        _write_concept(tmp_path, "OAuth2Flow.md", OAUTH_CONCEPT)
        _write_concept(tmp_path, "SessionCookies.md", DEPRECATED_CONCEPT)
        index = ConceptIndex.load(tmp_path)
        results = index.by_tag("auth")
        titles = [r.frontmatter.title for r in results]
        assert titles == sorted(titles)
