"""Unit tests for StackIndex — build, search, and filter methods."""

from __future__ import annotations

from pathlib import Path

import pytest

from lexibrary.stack.index import StackIndex

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_POST_TEMPLATE = """\
---
id: {id}
title: {title}
tags:
{tags}
status: {status}
created: 2026-02-21
author: agent-123
votes: {votes}
refs:
  concepts:
{concepts}
  files:
{files}
---

## Problem

{problem}

### F1

**Date:** 2026-02-21 | **Author:** agent-123 | **Votes:** 0

{finding_body}
"""


def _make_post(
    stack_dir: Path,
    *,
    post_id: str = "ST-001",
    title: str = "Default title",
    tags: list[str] | None = None,
    status: str = "open",
    votes: int = 0,
    concepts: list[str] | None = None,
    files: list[str] | None = None,
    problem: str = "Default problem description.",
    finding_body: str = "Default finding body.",
    filename: str | None = None,
) -> Path:
    """Write a Stack post file and return its path."""
    tags = tags or ["bug"]
    concepts = concepts or []
    files = files or []

    tags_yaml = "\n".join(f"    - {t}" for t in tags)
    concepts_yaml = "\n".join(f"    - {c}" for c in concepts) if concepts else "    []"
    files_yaml = "\n".join(f"    - {f}" for f in files) if files else "    []"

    content = _POST_TEMPLATE.format(
        id=post_id,
        title=title,
        tags=tags_yaml,
        status=status,
        votes=votes,
        concepts=concepts_yaml,
        files=files_yaml,
        problem=problem,
        finding_body=finding_body,
    )

    fname = filename or f"{post_id}-slug.md"
    path = stack_dir / fname
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture()
def stack_dir(tmp_path: Path) -> Path:
    """Create and return the .lexibrary/stack/ directory."""
    d = tmp_path / ".lexibrary" / "stack"
    d.mkdir(parents=True)
    return d


# ---------------------------------------------------------------------------
# Build tests
# ---------------------------------------------------------------------------


class TestBuild:
    """Tests for StackIndex.build()."""

    def test_build_from_stack_directory(self, tmp_path: Path, stack_dir: Path) -> None:
        _make_post(stack_dir, post_id="ST-001", title="Post one")
        _make_post(stack_dir, post_id="ST-002", title="Post two")
        _make_post(stack_dir, post_id="ST-003", title="Post three")

        idx = StackIndex.build(tmp_path)
        assert len(idx) == 3

    def test_build_empty_directory(self, tmp_path: Path, stack_dir: Path) -> None:
        idx = StackIndex.build(tmp_path)
        assert len(idx) == 0

    def test_build_skips_malformed_files(self, tmp_path: Path, stack_dir: Path) -> None:
        _make_post(stack_dir, post_id="ST-001", title="Valid post")
        # Write a malformed file
        (stack_dir / "ST-002-bad.md").write_text("not valid yaml", encoding="utf-8")

        idx = StackIndex.build(tmp_path)
        assert len(idx) == 1

    def test_build_no_stack_directory(self, tmp_path: Path) -> None:
        # No .lexibrary/stack/ at all
        idx = StackIndex.build(tmp_path)
        assert len(idx) == 0


# ---------------------------------------------------------------------------
# Search tests
# ---------------------------------------------------------------------------


class TestSearch:
    """Tests for StackIndex.search()."""

    def test_search_matches_title(self, tmp_path: Path, stack_dir: Path) -> None:
        _make_post(stack_dir, post_id="ST-001", title="Timezone conversion bug")

        idx = StackIndex.build(tmp_path)
        results = idx.search("timezone")
        assert len(results) == 1
        assert results[0].frontmatter.id == "ST-001"

    def test_search_matches_problem_body(self, tmp_path: Path, stack_dir: Path) -> None:
        _make_post(
            stack_dir,
            post_id="ST-001",
            title="A bug",
            problem="Calling datetime.now() raises an error.",
        )

        idx = StackIndex.build(tmp_path)
        results = idx.search("datetime.now")
        assert len(results) == 1

    def test_search_matches_finding_body(self, tmp_path: Path, stack_dir: Path) -> None:
        _make_post(
            stack_dir,
            post_id="ST-001",
            title="File reference issue",
            finding_body="Check utils/time.py for the fix.",
        )

        idx = StackIndex.build(tmp_path)
        results = idx.search("utils/time.py")
        assert len(results) == 1

    def test_search_matches_tags(self, tmp_path: Path, stack_dir: Path) -> None:
        _make_post(
            stack_dir,
            post_id="ST-001",
            title="Data issue",
            tags=["data-integrity", "bug"],
        )

        idx = StackIndex.build(tmp_path)
        results = idx.search("data-integrity")
        assert len(results) == 1

    def test_search_is_case_insensitive(self, tmp_path: Path, stack_dir: Path) -> None:
        _make_post(stack_dir, post_id="ST-001", title="Timezone conversion bug")

        idx = StackIndex.build(tmp_path)
        lower = idx.search("timezone")
        upper = idx.search("TIMEZONE")
        assert len(lower) == len(upper) == 1
        assert lower[0].frontmatter.id == upper[0].frontmatter.id

    def test_search_no_matches(self, tmp_path: Path, stack_dir: Path) -> None:
        _make_post(stack_dir, post_id="ST-001", title="Something else")

        idx = StackIndex.build(tmp_path)
        results = idx.search("nonexistent-query-xyz")
        assert results == []

    def test_search_empty_query(self, tmp_path: Path, stack_dir: Path) -> None:
        _make_post(stack_dir, post_id="ST-001", title="Something")

        idx = StackIndex.build(tmp_path)
        assert idx.search("") == []

    def test_search_sorted_by_votes_descending(self, tmp_path: Path, stack_dir: Path) -> None:
        _make_post(stack_dir, post_id="ST-001", title="Common bug report", votes=2)
        _make_post(stack_dir, post_id="ST-002", title="Another common bug report", votes=10)
        _make_post(stack_dir, post_id="ST-003", title="Yet another common bug", votes=5)

        idx = StackIndex.build(tmp_path)
        results = idx.search("common bug")
        assert len(results) == 3
        assert [r.frontmatter.votes for r in results] == [10, 5, 2]


# ---------------------------------------------------------------------------
# Filter tests
# ---------------------------------------------------------------------------


class TestByTag:
    """Tests for StackIndex.by_tag()."""

    def test_filter_existing_tag(self, tmp_path: Path, stack_dir: Path) -> None:
        _make_post(stack_dir, post_id="ST-001", tags=["datetime", "bug"])
        _make_post(stack_dir, post_id="ST-002", tags=["datetime"])
        _make_post(stack_dir, post_id="ST-003", tags=["config"])

        idx = StackIndex.build(tmp_path)
        results = idx.by_tag("datetime")
        assert len(results) == 2

    def test_filter_nonexistent_tag(self, tmp_path: Path, stack_dir: Path) -> None:
        _make_post(stack_dir, post_id="ST-001", tags=["bug"])

        idx = StackIndex.build(tmp_path)
        assert idx.by_tag("nonexistent") == []

    def test_filter_tag_case_insensitive(self, tmp_path: Path, stack_dir: Path) -> None:
        _make_post(stack_dir, post_id="ST-001", tags=["DateTime"])

        idx = StackIndex.build(tmp_path)
        results = idx.by_tag("datetime")
        assert len(results) == 1


class TestByScope:
    """Tests for StackIndex.by_scope()."""

    def test_filter_by_directory_scope(self, tmp_path: Path, stack_dir: Path) -> None:
        _make_post(
            stack_dir,
            post_id="ST-001",
            files=["src/models/event.py"],
        )
        _make_post(
            stack_dir,
            post_id="ST-002",
            files=["src/utils/helpers.py"],
        )

        idx = StackIndex.build(tmp_path)
        results = idx.by_scope("src/models/")
        assert len(results) == 1
        assert results[0].frontmatter.id == "ST-001"

    def test_filter_by_exact_file_scope(self, tmp_path: Path, stack_dir: Path) -> None:
        _make_post(
            stack_dir,
            post_id="ST-001",
            files=["src/models/event.py"],
        )
        _make_post(
            stack_dir,
            post_id="ST-002",
            files=["src/models/user.py"],
        )

        idx = StackIndex.build(tmp_path)
        results = idx.by_scope("src/models/event.py")
        assert len(results) == 1
        assert results[0].frontmatter.id == "ST-001"


class TestByStatus:
    """Tests for StackIndex.by_status()."""

    def test_filter_open_posts(self, tmp_path: Path, stack_dir: Path) -> None:
        _make_post(stack_dir, post_id="ST-001", status="open")
        _make_post(stack_dir, post_id="ST-002", status="resolved")
        _make_post(stack_dir, post_id="ST-003", status="open")

        idx = StackIndex.build(tmp_path)
        results = idx.by_status("open")
        assert len(results) == 2
        assert all(r.frontmatter.status == "open" for r in results)

    def test_filter_resolved_posts(self, tmp_path: Path, stack_dir: Path) -> None:
        _make_post(stack_dir, post_id="ST-001", status="open")
        _make_post(stack_dir, post_id="ST-002", status="resolved")

        idx = StackIndex.build(tmp_path)
        results = idx.by_status("resolved")
        assert len(results) == 1
        assert results[0].frontmatter.id == "ST-002"


class TestByConcept:
    """Tests for StackIndex.by_concept()."""

    def test_filter_by_concept_name(self, tmp_path: Path, stack_dir: Path) -> None:
        _make_post(
            stack_dir,
            post_id="ST-001",
            concepts=["DateHandling"],
        )
        _make_post(
            stack_dir,
            post_id="ST-002",
            concepts=["Authentication"],
        )

        idx = StackIndex.build(tmp_path)
        results = idx.by_concept("DateHandling")
        assert len(results) == 1
        assert results[0].frontmatter.id == "ST-001"

    def test_filter_concept_case_insensitive(self, tmp_path: Path, stack_dir: Path) -> None:
        _make_post(
            stack_dir,
            post_id="ST-001",
            concepts=["DateHandling"],
        )

        idx = StackIndex.build(tmp_path)
        results = idx.by_concept("datehandling")
        assert len(results) == 1

    def test_filter_concept_no_match(self, tmp_path: Path, stack_dir: Path) -> None:
        _make_post(stack_dir, post_id="ST-001", concepts=["DateHandling"])

        idx = StackIndex.build(tmp_path)
        assert idx.by_concept("NonExistent") == []


# ---------------------------------------------------------------------------
# Extended post template with context, attempts, and resolution_type
# ---------------------------------------------------------------------------

_EXTENDED_POST_TEMPLATE = """\
---
id: {id}
title: {title}
tags:
{tags}
status: {status}
created: 2026-02-21
author: agent-123
votes: {votes}
refs:
  concepts:
{concepts}
  files:
{files}
{resolution_type_yaml}---

## Problem

{problem}

### Context

{context}

### Attempts

{attempts}

### F1

**Date:** 2026-02-21 | **Author:** agent-123 | **Votes:** 0

{finding_body}
"""


def _make_extended_post(
    stack_dir: Path,
    *,
    post_id: str = "ST-001",
    title: str = "Default title",
    tags: list[str] | None = None,
    status: str = "open",
    votes: int = 0,
    concepts: list[str] | None = None,
    files: list[str] | None = None,
    problem: str = "Default problem description.",
    context: str = "Default context.",
    attempts: list[str] | None = None,
    finding_body: str = "Default finding body.",
    resolution_type: str | None = None,
    filename: str | None = None,
) -> Path:
    """Write a Stack post file with context, attempts, and optional resolution_type."""
    tags = tags or ["bug"]
    concepts = concepts or []
    files = files or []
    attempts = attempts or []

    tags_yaml = "\n".join(f"    - {t}" for t in tags)
    concepts_yaml = "\n".join(f"    - {c}" for c in concepts) if concepts else "    []"
    files_yaml = "\n".join(f"    - {f}" for f in files) if files else "    []"
    attempts_yaml = "\n".join(f"- {a}" for a in attempts) if attempts else ""
    resolution_type_yaml = (
        f"resolution_type: {resolution_type}\n" if resolution_type else ""
    )

    content = _EXTENDED_POST_TEMPLATE.format(
        id=post_id,
        title=title,
        tags=tags_yaml,
        status=status,
        votes=votes,
        concepts=concepts_yaml,
        files=files_yaml,
        problem=problem,
        context=context,
        attempts=attempts_yaml,
        finding_body=finding_body,
        resolution_type_yaml=resolution_type_yaml,
    )

    fname = filename or f"{post_id}-slug.md"
    path = stack_dir / fname
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Search tests for context and attempts fields
# ---------------------------------------------------------------------------


class TestSearchContext:
    """Tests for search matching content in the context field."""

    def test_search_matches_context_field(self, tmp_path: Path, stack_dir: Path) -> None:
        _make_extended_post(
            stack_dir,
            post_id="ST-001",
            title="A database issue",
            context="Running PostgreSQL 14 on Ubuntu with pgbouncer connection pooling.",
        )

        idx = StackIndex.build(tmp_path)
        results = idx.search("pgbouncer")
        assert len(results) == 1
        assert results[0].frontmatter.id == "ST-001"

    def test_search_context_no_false_positive(self, tmp_path: Path, stack_dir: Path) -> None:
        _make_extended_post(
            stack_dir,
            post_id="ST-001",
            title="A database issue",
            context="Running PostgreSQL 14 on Ubuntu.",
        )

        idx = StackIndex.build(tmp_path)
        results = idx.search("nonexistent-context-query")
        assert results == []


class TestSearchAttempts:
    """Tests for search matching content in the attempts field."""

    def test_search_matches_attempts_field(self, tmp_path: Path, stack_dir: Path) -> None:
        _make_extended_post(
            stack_dir,
            post_id="ST-001",
            title="A config issue",
            attempts=["Tried restarting the celery workers", "Cleared the Redis cache"],
        )

        idx = StackIndex.build(tmp_path)
        results = idx.search("celery workers")
        assert len(results) == 1
        assert results[0].frontmatter.id == "ST-001"

    def test_search_attempts_second_item(self, tmp_path: Path, stack_dir: Path) -> None:
        _make_extended_post(
            stack_dir,
            post_id="ST-001",
            title="A config issue",
            attempts=["Tried restarting the service", "Cleared the Redis cache"],
        )

        idx = StackIndex.build(tmp_path)
        results = idx.search("redis cache")
        assert len(results) == 1
        assert results[0].frontmatter.id == "ST-001"

    def test_search_attempts_no_false_positive(self, tmp_path: Path, stack_dir: Path) -> None:
        _make_extended_post(
            stack_dir,
            post_id="ST-001",
            title="A config issue",
            attempts=["Tried restarting the service"],
        )

        idx = StackIndex.build(tmp_path)
        results = idx.search("nonexistent-attempts-query")
        assert results == []


# ---------------------------------------------------------------------------
# by_resolution_type tests
# ---------------------------------------------------------------------------


class TestByResolutionType:
    """Tests for StackIndex.by_resolution_type()."""

    def test_filter_fix_returns_matching(self, tmp_path: Path, stack_dir: Path) -> None:
        _make_extended_post(
            stack_dir,
            post_id="ST-001",
            title="Fixed config issue",
            status="resolved",
            resolution_type="fix",
        )
        _make_extended_post(
            stack_dir,
            post_id="ST-002",
            title="Workaround for auth bug",
            status="resolved",
            resolution_type="workaround",
        )
        _make_extended_post(
            stack_dir,
            post_id="ST-003",
            title="Open issue",
            status="open",
        )

        idx = StackIndex.build(tmp_path)
        results = idx.by_resolution_type("fix")
        assert len(results) == 1
        assert results[0].frontmatter.id == "ST-001"

    def test_filter_workaround_excludes_non_matching(
        self, tmp_path: Path, stack_dir: Path
    ) -> None:
        _make_extended_post(
            stack_dir,
            post_id="ST-001",
            title="Fixed config issue",
            status="resolved",
            resolution_type="fix",
        )
        _make_extended_post(
            stack_dir,
            post_id="ST-002",
            title="Workaround for auth bug",
            status="resolved",
            resolution_type="workaround",
        )
        _make_extended_post(
            stack_dir,
            post_id="ST-003",
            title="Open issue",
            status="open",
        )

        idx = StackIndex.build(tmp_path)
        results = idx.by_resolution_type("workaround")
        assert len(results) == 1
        assert results[0].frontmatter.id == "ST-002"
        # Ensure "fix" posts are excluded
        assert all(r.frontmatter.resolution_type == "workaround" for r in results)

    def test_filter_no_matching_resolution_type(
        self, tmp_path: Path, stack_dir: Path
    ) -> None:
        _make_extended_post(
            stack_dir,
            post_id="ST-001",
            title="Open issue",
            status="open",
        )

        idx = StackIndex.build(tmp_path)
        results = idx.by_resolution_type("fix")
        assert results == []
