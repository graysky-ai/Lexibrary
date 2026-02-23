"""Unit tests for Stack post parser."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from lexibrary.stack.parser import parse_stack_post

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_POST = """\
---
id: ST-001
title: Date parsing fails on leap years
tags:
  - bug
  - dates
status: open
created: 2026-02-21
author: agent-123
refs:
  concepts:
    - DateHandling
  files:
    - src/models/event.py
---

## Problem

The date parser raises ValueError when given Feb 29 on leap years.

### Evidence

- traceback line 1
- traceback line 2

### A1

**Date:** 2026-02-21 | **Author:** agent-456 | **Votes:** 2 | **Accepted:** true

Use `calendar.isleap()` to check before parsing.

#### Comments

**2026-02-22 agent-789 [upvote]:** Confirmed this works.

### A2

**Date:** 2026-02-22 | **Author:** agent-789 | **Votes:** -1

Try a different library instead.

#### Comments

**2026-02-22 agent-123 [downvote]:** This approach is unreliable.
**2026-02-23 agent-456 [upvote]:** Worth considering though.
"""

_POST_NO_ANSWERS = """\
---
id: ST-002
title: No answers yet
tags:
  - question
created: 2026-02-21
author: agent-100
---

## Problem

Something is broken.

### Evidence

- error log entry
"""

_POST_ACCEPTED_ANSWER = """\
---
id: ST-003
title: Accepted answer post
tags:
  - resolved
status: resolved
created: 2026-02-21
author: agent-200
---

## Problem

Need a solution.

### A1

**Date:** 2026-02-21 | **Author:** agent-300 | **Votes:** 5 | **Accepted:** true

This is the accepted solution.
"""

_MALFORMED_FRONTMATTER = """\
---
id: ST-004
title: [invalid yaml
tags: not-a-list
---

## Problem

This should fail.
"""

_NO_FRONTMATTER = """\
# Just a regular markdown file

No frontmatter here.
"""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestParseValidPost:
    """Tests for parsing a well-formed post with answers."""

    def test_frontmatter_fields(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-001-date-parsing.md"
        p.write_text(_VALID_POST)
        post = parse_stack_post(p)
        assert post is not None
        assert post.frontmatter.id == "ST-001"
        assert post.frontmatter.title == "Date parsing fails on leap years"
        assert post.frontmatter.tags == ["bug", "dates"]
        assert post.frontmatter.status == "open"
        assert post.frontmatter.created == date(2026, 2, 21)
        assert post.frontmatter.author == "agent-123"

    def test_frontmatter_refs(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-001-date-parsing.md"
        p.write_text(_VALID_POST)
        post = parse_stack_post(p)
        assert post is not None
        assert post.frontmatter.refs.concepts == ["DateHandling"]
        assert post.frontmatter.refs.files == ["src/models/event.py"]
        assert post.frontmatter.refs.designs == []

    def test_problem_extraction(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-001.md"
        p.write_text(_VALID_POST)
        post = parse_stack_post(p)
        assert post is not None
        assert "date parser raises ValueError" in post.problem

    def test_evidence_extraction(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-001.md"
        p.write_text(_VALID_POST)
        post = parse_stack_post(p)
        assert post is not None
        assert post.evidence == ["traceback line 1", "traceback line 2"]

    def test_answer_count(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-001.md"
        p.write_text(_VALID_POST)
        post = parse_stack_post(p)
        assert post is not None
        assert len(post.answers) == 2

    def test_answer_one_metadata(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-001.md"
        p.write_text(_VALID_POST)
        post = parse_stack_post(p)
        assert post is not None
        a1 = post.answers[0]
        assert a1.number == 1
        assert a1.date == date(2026, 2, 21)
        assert a1.author == "agent-456"
        assert a1.votes == 2
        assert a1.accepted is True

    def test_answer_one_body(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-001.md"
        p.write_text(_VALID_POST)
        post = parse_stack_post(p)
        assert post is not None
        assert "calendar.isleap()" in post.answers[0].body

    def test_answer_one_comments(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-001.md"
        p.write_text(_VALID_POST)
        post = parse_stack_post(p)
        assert post is not None
        assert len(post.answers[0].comments) == 1
        assert "[upvote]" in post.answers[0].comments[0]

    def test_answer_two_metadata(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-001.md"
        p.write_text(_VALID_POST)
        post = parse_stack_post(p)
        assert post is not None
        a2 = post.answers[1]
        assert a2.number == 2
        assert a2.date == date(2026, 2, 22)
        assert a2.author == "agent-789"
        assert a2.votes == -1
        assert a2.accepted is False

    def test_answer_two_comments(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-001.md"
        p.write_text(_VALID_POST)
        post = parse_stack_post(p)
        assert post is not None
        assert len(post.answers[1].comments) == 2
        assert "[downvote]" in post.answers[1].comments[0]
        assert "[upvote]" in post.answers[1].comments[1]

    def test_raw_body_stored(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-001.md"
        p.write_text(_VALID_POST)
        post = parse_stack_post(p)
        assert post is not None
        assert post.raw_body != ""
        assert "## Problem" in post.raw_body


class TestParsePostNoAnswers:
    """Tests for parsing a post with no answers."""

    def test_returns_empty_answers(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-002.md"
        p.write_text(_POST_NO_ANSWERS)
        post = parse_stack_post(p)
        assert post is not None
        assert post.answers == []

    def test_problem_extracted(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-002.md"
        p.write_text(_POST_NO_ANSWERS)
        post = parse_stack_post(p)
        assert post is not None
        assert "Something is broken" in post.problem

    def test_evidence_extracted(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-002.md"
        p.write_text(_POST_NO_ANSWERS)
        post = parse_stack_post(p)
        assert post is not None
        assert post.evidence == ["error log entry"]


class TestParseAcceptedAnswer:
    """Tests for parsing a post with an accepted answer."""

    def test_accepted_flag(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-003.md"
        p.write_text(_POST_ACCEPTED_ANSWER)
        post = parse_stack_post(p)
        assert post is not None
        assert len(post.answers) == 1
        assert post.answers[0].accepted is True
        assert post.answers[0].votes == 5

    def test_status_resolved(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-003.md"
        p.write_text(_POST_ACCEPTED_ANSWER)
        post = parse_stack_post(p)
        assert post is not None
        assert post.frontmatter.status == "resolved"


class TestParseNonexistentFile:
    """Tests for parsing a nonexistent file."""

    def test_returns_none(self, tmp_path: Path) -> None:
        p = tmp_path / "does-not-exist.md"
        result = parse_stack_post(p)
        assert result is None


class TestParseMalformedFile:
    """Tests for parsing malformed files."""

    def test_invalid_frontmatter_returns_none(self, tmp_path: Path) -> None:
        p = tmp_path / "malformed.md"
        p.write_text(_MALFORMED_FRONTMATTER)
        result = parse_stack_post(p)
        assert result is None

    def test_no_frontmatter_returns_none(self, tmp_path: Path) -> None:
        p = tmp_path / "no-fm.md"
        p.write_text(_NO_FRONTMATTER)
        result = parse_stack_post(p)
        assert result is None
