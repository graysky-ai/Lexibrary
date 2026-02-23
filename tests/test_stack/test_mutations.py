"""Unit tests for Stack post mutations."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from lexibrary.stack.mutations import (
    accept_answer,
    add_answer,
    mark_duplicate,
    mark_outdated,
    record_vote,
)
from lexibrary.stack.parser import parse_stack_post

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_BASE_POST = """\
---
id: ST-001
title: Date parsing fails on leap years
tags:
  - bug
  - dates
status: open
created: '2026-02-21'
author: agent-123
bead: null
votes: 3
duplicate_of: null
refs:
  concepts: []
  files: []
  designs: []
---

## Problem

The date parser raises ValueError when given Feb 29 on leap years.

### Evidence

- traceback line 1

"""

_POST_WITH_ANSWER = """\
---
id: ST-002
title: Config file not loaded
tags:
  - bug
status: open
created: '2026-02-21'
author: agent-456
bead: null
votes: 0
duplicate_of: null
refs:
  concepts: []
  files: []
  designs: []
---

## Problem

Config file is ignored on startup.

### Evidence

## Answers

### A1

**Date:** 2026-02-21 | **Author:** agent-789 | **Votes:** 2

Check the YAML indentation.

#### Comments

"""


def _write_post(tmp_path: Path, content: str, name: str = "ST-001.md") -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# add_answer
# ---------------------------------------------------------------------------


class TestAddAnswer:
    """Tests for add_answer()."""

    def test_add_first_answer(self, tmp_path: Path) -> None:
        post_path = _write_post(tmp_path, _BASE_POST)
        result = add_answer(post_path, "agent-new", "Try reformatting the date.")

        assert len(result.answers) == 1
        a = result.answers[0]
        assert a.number == 1
        assert a.author == "agent-new"
        assert a.body == "Try reformatting the date."
        assert a.date == date.today()
        assert a.votes == 0
        assert a.accepted is False

    def test_add_second_answer(self, tmp_path: Path) -> None:
        post_path = _write_post(tmp_path, _POST_WITH_ANSWER, "ST-002.md")
        result = add_answer(post_path, "agent-new", "Also check encoding.")

        assert len(result.answers) == 2
        assert result.answers[0].number == 1
        assert result.answers[1].number == 2
        assert result.answers[1].author == "agent-new"
        assert result.answers[1].body == "Also check encoding."

    def test_existing_answers_preserved(self, tmp_path: Path) -> None:
        post_path = _write_post(tmp_path, _POST_WITH_ANSWER, "ST-002.md")
        original = parse_stack_post(post_path)
        assert original is not None

        result = add_answer(post_path, "agent-new", "New answer body.")

        # Original answer preserved
        assert result.answers[0].number == 1
        assert result.answers[0].author == "agent-789"
        assert result.answers[0].votes == 2
        assert "Check the YAML indentation." in result.answers[0].body

    def test_add_answer_invalid_file(self, tmp_path: Path) -> None:
        post_path = tmp_path / "nonexistent.md"
        with pytest.raises(ValueError, match="Cannot parse"):
            add_answer(post_path, "agent", "body")


# ---------------------------------------------------------------------------
# record_vote
# ---------------------------------------------------------------------------


class TestRecordVote:
    """Tests for record_vote()."""

    def test_upvote_post(self, tmp_path: Path) -> None:
        post_path = _write_post(tmp_path, _BASE_POST)
        result = record_vote(post_path, "post", "up", "agent-voter")
        assert result.frontmatter.votes == 4

    def test_downvote_post_with_comment(self, tmp_path: Path) -> None:
        post_path = _write_post(tmp_path, _BASE_POST)
        result = record_vote(post_path, "post", "down", "agent-voter", comment="Incorrect")
        assert result.frontmatter.votes == 2

    def test_downvote_without_comment_raises(self, tmp_path: Path) -> None:
        post_path = _write_post(tmp_path, _BASE_POST)
        with pytest.raises(ValueError, match="[Dd]ownvote"):
            record_vote(post_path, "post", "down", "agent-voter")

    def test_downvote_with_none_comment_raises(self, tmp_path: Path) -> None:
        post_path = _write_post(tmp_path, _BASE_POST)
        with pytest.raises(ValueError, match="[Dd]ownvote"):
            record_vote(post_path, "post", "down", "agent-voter", comment=None)

    def test_upvote_answer(self, tmp_path: Path) -> None:
        post_path = _write_post(tmp_path, _POST_WITH_ANSWER, "ST-002.md")
        result = record_vote(post_path, "A1", "up", "agent-voter")
        assert result.answers[0].votes == 3

    def test_downvote_answer_appends_comment(self, tmp_path: Path) -> None:
        post_path = _write_post(tmp_path, _POST_WITH_ANSWER, "ST-002.md")
        result = record_vote(post_path, "A1", "down", "agent-voter", comment="Doesn't work")
        assert result.answers[0].votes == 1
        assert any("[downvote]" in c for c in result.answers[0].comments)
        assert any("agent-voter" in c for c in result.answers[0].comments)
        assert any("Doesn't work" in c for c in result.answers[0].comments)

    def test_upvote_with_optional_comment(self, tmp_path: Path) -> None:
        post_path = _write_post(tmp_path, _POST_WITH_ANSWER, "ST-002.md")
        result = record_vote(post_path, "A1", "up", "agent-voter", comment="Confirmed working")
        assert result.answers[0].votes == 3
        assert any("[upvote]" in c for c in result.answers[0].comments)
        assert any("Confirmed working" in c for c in result.answers[0].comments)

    def test_vote_nonexistent_answer_raises(self, tmp_path: Path) -> None:
        post_path = _write_post(tmp_path, _POST_WITH_ANSWER, "ST-002.md")
        with pytest.raises(ValueError, match="A99 not found"):
            record_vote(post_path, "A99", "up", "agent-voter")


# ---------------------------------------------------------------------------
# accept_answer
# ---------------------------------------------------------------------------


class TestAcceptAnswer:
    """Tests for accept_answer()."""

    def test_accept_marks_resolved(self, tmp_path: Path) -> None:
        post_path = _write_post(tmp_path, _POST_WITH_ANSWER, "ST-002.md")
        result = accept_answer(post_path, 1)

        assert result.answers[0].accepted is True
        assert result.frontmatter.status == "resolved"

    def test_accept_nonexistent_answer_raises(self, tmp_path: Path) -> None:
        post_path = _write_post(tmp_path, _POST_WITH_ANSWER, "ST-002.md")
        with pytest.raises(ValueError, match="A99 not found"):
            accept_answer(post_path, 99)


# ---------------------------------------------------------------------------
# mark_duplicate
# ---------------------------------------------------------------------------


class TestMarkDuplicate:
    """Tests for mark_duplicate()."""

    def test_mark_duplicate(self, tmp_path: Path) -> None:
        post_path = _write_post(tmp_path, _BASE_POST)
        result = mark_duplicate(post_path, "ST-005")

        assert result.frontmatter.status == "duplicate"
        assert result.frontmatter.duplicate_of == "ST-005"


# ---------------------------------------------------------------------------
# mark_outdated
# ---------------------------------------------------------------------------


class TestMarkOutdated:
    """Tests for mark_outdated()."""

    def test_mark_outdated(self, tmp_path: Path) -> None:
        post_path = _write_post(tmp_path, _BASE_POST)
        result = mark_outdated(post_path)

        assert result.frontmatter.status == "outdated"


# ---------------------------------------------------------------------------
# Append-only body invariant
# ---------------------------------------------------------------------------


class TestAppendOnlyInvariant:
    """Mutations must not alter the problem/evidence body content."""

    def test_add_answer_preserves_body(self, tmp_path: Path) -> None:
        post_path = _write_post(tmp_path, _BASE_POST)
        original = parse_stack_post(post_path)
        assert original is not None

        result = add_answer(post_path, "agent", "New answer")

        assert result.problem == original.problem
        assert result.evidence == original.evidence

    def test_vote_preserves_body(self, tmp_path: Path) -> None:
        post_path = _write_post(tmp_path, _POST_WITH_ANSWER, "ST-002.md")
        original = parse_stack_post(post_path)
        assert original is not None

        result = record_vote(post_path, "post", "up", "agent")

        assert result.problem == original.problem
        assert result.evidence == original.evidence

    def test_accept_preserves_body(self, tmp_path: Path) -> None:
        post_path = _write_post(tmp_path, _POST_WITH_ANSWER, "ST-002.md")
        original = parse_stack_post(post_path)
        assert original is not None

        result = accept_answer(post_path, 1)

        assert result.problem == original.problem
        assert result.evidence == original.evidence
