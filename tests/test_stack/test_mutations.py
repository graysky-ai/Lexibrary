"""Unit tests for Stack post mutations."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from lexibrary.stack.mutations import (
    accept_finding,
    add_finding,
    mark_duplicate,
    mark_outdated,
    mark_stale,
    mark_unstale,
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

_POST_WITH_FINDING = """\
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

## Findings

### F1

**Date:** 2026-02-21 | **Author:** agent-789 | **Votes:** 2

Check the YAML indentation.

#### Comments

"""

_RESOLVED_POST = """\
---
id: ST-003
title: Import error with optional dep
tags:
  - bug
status: resolved
created: '2026-02-21'
author: agent-100
bead: null
votes: 1
duplicate_of: null
refs:
  concepts: []
  files: []
  designs: []
resolution_type: fix
---

## Problem

Optional dependency not found on import.

### Evidence

- ImportError traceback

## Findings

### F1

**Date:** 2026-02-22 | **Author:** agent-200 | **Votes:** 1 | **Accepted**

Wrap the import in a try/except block.

#### Comments

"""

_STALE_POST = """\
---
id: ST-004
title: Old config key no longer works
tags:
  - config
status: stale
created: '2026-01-10'
author: agent-300
bead: null
votes: 0
duplicate_of: null
refs:
  concepts: []
  files: []
  designs: []
resolution_type: workaround
stale_at: '2026-03-01T12:00:00+00:00'
---

## Problem

Legacy config key is silently ignored.

### Evidence

- Observed config mismatch

## Findings

### F1

**Date:** 2026-01-11 | **Author:** agent-400 | **Votes:** 0 | **Accepted**

Use the new config key name.

#### Comments

"""

_DUPLICATE_POST = """\
---
id: ST-005
title: Same as ST-003
tags:
  - bug
status: duplicate
created: '2026-02-25'
author: agent-500
bead: null
votes: 0
duplicate_of: ST-003
refs:
  concepts: []
  files: []
  designs: []
---

## Problem

Duplicate of import error issue.

### Evidence

"""


def _write_post(tmp_path: Path, content: str, name: str = "ST-001.md") -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# add_finding
# ---------------------------------------------------------------------------


class TestAddFinding:
    """Tests for add_finding()."""

    def test_add_first_finding(self, tmp_path: Path) -> None:
        post_path = _write_post(tmp_path, _BASE_POST)
        result = add_finding(post_path, "agent-new", "Try reformatting the date.")

        assert len(result.findings) == 1
        f = result.findings[0]
        assert f.number == 1
        assert f.author == "agent-new"
        assert f.body == "Try reformatting the date."
        assert f.date == date.today()
        assert f.votes == 0
        assert f.accepted is False

    def test_add_second_finding(self, tmp_path: Path) -> None:
        post_path = _write_post(tmp_path, _POST_WITH_FINDING, "ST-002.md")
        result = add_finding(post_path, "agent-new", "Also check encoding.")

        assert len(result.findings) == 2
        assert result.findings[0].number == 1
        assert result.findings[1].number == 2
        assert result.findings[1].author == "agent-new"
        assert result.findings[1].body == "Also check encoding."

    def test_existing_findings_preserved(self, tmp_path: Path) -> None:
        post_path = _write_post(tmp_path, _POST_WITH_FINDING, "ST-002.md")
        original = parse_stack_post(post_path)
        assert original is not None

        result = add_finding(post_path, "agent-new", "New finding body.")

        # Original finding preserved
        assert result.findings[0].number == 1
        assert result.findings[0].author == "agent-789"
        assert result.findings[0].votes == 2
        assert "Check the YAML indentation." in result.findings[0].body

    def test_add_finding_invalid_file(self, tmp_path: Path) -> None:
        post_path = tmp_path / "nonexistent.md"
        with pytest.raises(ValueError, match="Cannot parse"):
            add_finding(post_path, "agent", "body")


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

    def test_upvote_finding(self, tmp_path: Path) -> None:
        post_path = _write_post(tmp_path, _POST_WITH_FINDING, "ST-002.md")
        result = record_vote(post_path, "F1", "up", "agent-voter")
        assert result.findings[0].votes == 3

    def test_downvote_finding_appends_comment(self, tmp_path: Path) -> None:
        post_path = _write_post(tmp_path, _POST_WITH_FINDING, "ST-002.md")
        result = record_vote(post_path, "F1", "down", "agent-voter", comment="Doesn't work")
        assert result.findings[0].votes == 1
        assert any("[downvote]" in c for c in result.findings[0].comments)
        assert any("agent-voter" in c for c in result.findings[0].comments)
        assert any("Doesn't work" in c for c in result.findings[0].comments)

    def test_upvote_with_optional_comment(self, tmp_path: Path) -> None:
        post_path = _write_post(tmp_path, _POST_WITH_FINDING, "ST-002.md")
        result = record_vote(post_path, "F1", "up", "agent-voter", comment="Confirmed working")
        assert result.findings[0].votes == 3
        assert any("[upvote]" in c for c in result.findings[0].comments)
        assert any("Confirmed working" in c for c in result.findings[0].comments)

    def test_vote_nonexistent_finding_raises(self, tmp_path: Path) -> None:
        post_path = _write_post(tmp_path, _POST_WITH_FINDING, "ST-002.md")
        with pytest.raises(ValueError, match="F99 not found"):
            record_vote(post_path, "F99", "up", "agent-voter")


# ---------------------------------------------------------------------------
# accept_finding
# ---------------------------------------------------------------------------


class TestAcceptFinding:
    """Tests for accept_finding()."""

    def test_accept_marks_resolved(self, tmp_path: Path) -> None:
        post_path = _write_post(tmp_path, _POST_WITH_FINDING, "ST-002.md")
        result = accept_finding(post_path, 1)

        assert result.findings[0].accepted is True
        assert result.frontmatter.status == "resolved"

    def test_accept_with_resolution_type_sets_field(self, tmp_path: Path) -> None:
        post_path = _write_post(tmp_path, _POST_WITH_FINDING, "ST-002.md")
        result = accept_finding(post_path, 1, resolution_type="fix")

        assert result.findings[0].accepted is True
        assert result.frontmatter.status == "resolved"
        assert result.frontmatter.resolution_type == "fix"

    def test_accept_without_resolution_type_leaves_none(self, tmp_path: Path) -> None:
        post_path = _write_post(tmp_path, _POST_WITH_FINDING, "ST-002.md")
        result = accept_finding(post_path, 1)

        assert result.findings[0].accepted is True
        assert result.frontmatter.status == "resolved"
        assert result.frontmatter.resolution_type is None

    def test_accept_nonexistent_finding_raises(self, tmp_path: Path) -> None:
        post_path = _write_post(tmp_path, _POST_WITH_FINDING, "ST-002.md")
        with pytest.raises(ValueError, match="F99 not found"):
            accept_finding(post_path, 99)


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
# mark_stale
# ---------------------------------------------------------------------------


class TestMarkStale:
    """Tests for mark_stale()."""

    def test_mark_resolved_post_as_stale(self, tmp_path: Path) -> None:
        """Resolved post transitions to stale with a stale_at timestamp."""
        post_path = _write_post(tmp_path, _RESOLVED_POST, "ST-003.md")
        result = mark_stale(post_path)

        assert result.frontmatter.status == "stale"
        assert result.frontmatter.stale_at is not None
        # stale_at should be a datetime object
        from datetime import datetime as _datetime

        assert isinstance(result.frontmatter.stale_at, _datetime)

    def test_mark_open_post_as_stale_raises(self, tmp_path: Path) -> None:
        """Open posts cannot be marked stale."""
        post_path = _write_post(tmp_path, _BASE_POST)
        with pytest.raises(ValueError, match="[Oo]nly resolved"):
            mark_stale(post_path)

    def test_mark_duplicate_post_as_stale_raises(self, tmp_path: Path) -> None:
        """Duplicate posts cannot be marked stale."""
        post_path = _write_post(tmp_path, _DUPLICATE_POST, "ST-005.md")
        with pytest.raises(ValueError, match="[Oo]nly resolved"):
            mark_stale(post_path)

    def test_mark_stale_post_as_stale_raises(self, tmp_path: Path) -> None:
        """Already-stale posts cannot be marked stale again."""
        post_path = _write_post(tmp_path, _STALE_POST, "ST-004.md")
        with pytest.raises(ValueError, match="[Oo]nly resolved"):
            mark_stale(post_path)

    def test_mark_outdated_post_as_stale_raises(self, tmp_path: Path) -> None:
        """Outdated posts cannot be marked stale."""
        post_path = _write_post(tmp_path, _BASE_POST)
        # First mark as outdated
        mark_outdated(post_path)
        with pytest.raises(ValueError, match="[Oo]nly resolved"):
            mark_stale(post_path)

    def test_mark_stale_preserves_body(self, tmp_path: Path) -> None:
        """Marking stale must not alter the problem/evidence body."""
        post_path = _write_post(tmp_path, _RESOLVED_POST, "ST-003.md")
        original = parse_stack_post(post_path)
        assert original is not None

        result = mark_stale(post_path)

        assert result.problem == original.problem
        assert result.evidence == original.evidence

    def test_mark_stale_preserves_resolution_type(self, tmp_path: Path) -> None:
        """Marking stale must not clear the resolution_type."""
        post_path = _write_post(tmp_path, _RESOLVED_POST, "ST-003.md")
        result = mark_stale(post_path)

        assert result.frontmatter.resolution_type == "fix"


# ---------------------------------------------------------------------------
# mark_unstale
# ---------------------------------------------------------------------------


class TestMarkUnstale:
    """Tests for mark_unstale()."""

    def test_mark_stale_post_as_unstale(self, tmp_path: Path) -> None:
        """Stale post transitions back to resolved with stale_at cleared."""
        post_path = _write_post(tmp_path, _STALE_POST, "ST-004.md")
        result = mark_unstale(post_path)

        assert result.frontmatter.status == "resolved"
        assert result.frontmatter.stale_at is None

    def test_mark_open_post_as_unstale_raises(self, tmp_path: Path) -> None:
        """Open posts cannot be un-staled."""
        post_path = _write_post(tmp_path, _BASE_POST)
        with pytest.raises(ValueError, match="[Oo]nly stale"):
            mark_unstale(post_path)

    def test_mark_resolved_post_as_unstale_raises(self, tmp_path: Path) -> None:
        """Resolved posts (that are not stale) cannot be un-staled."""
        post_path = _write_post(tmp_path, _RESOLVED_POST, "ST-003.md")
        with pytest.raises(ValueError, match="[Oo]nly stale"):
            mark_unstale(post_path)

    def test_mark_duplicate_post_as_unstale_raises(self, tmp_path: Path) -> None:
        """Duplicate posts cannot be un-staled."""
        post_path = _write_post(tmp_path, _DUPLICATE_POST, "ST-005.md")
        with pytest.raises(ValueError, match="[Oo]nly stale"):
            mark_unstale(post_path)

    def test_unstale_preserves_body(self, tmp_path: Path) -> None:
        """Un-staling must not alter the problem/evidence body."""
        post_path = _write_post(tmp_path, _STALE_POST, "ST-004.md")
        original = parse_stack_post(post_path)
        assert original is not None

        result = mark_unstale(post_path)

        assert result.problem == original.problem
        assert result.evidence == original.evidence

    def test_unstale_preserves_resolution_type(self, tmp_path: Path) -> None:
        """Un-staling must preserve the resolution_type."""
        post_path = _write_post(tmp_path, _STALE_POST, "ST-004.md")
        result = mark_unstale(post_path)

        assert result.frontmatter.resolution_type == "workaround"

    def test_round_trip_stale_unstale(self, tmp_path: Path) -> None:
        """A resolved post can be marked stale and then un-staled."""
        post_path = _write_post(tmp_path, _RESOLVED_POST, "ST-003.md")

        staled = mark_stale(post_path)
        assert staled.frontmatter.status == "stale"
        assert staled.frontmatter.stale_at is not None

        unstaled = mark_unstale(post_path)
        assert unstaled.frontmatter.status == "resolved"
        assert unstaled.frontmatter.stale_at is None


# ---------------------------------------------------------------------------
# Append-only body invariant
# ---------------------------------------------------------------------------


class TestAppendOnlyInvariant:
    """Mutations must not alter the problem/evidence body content."""

    def test_add_finding_preserves_body(self, tmp_path: Path) -> None:
        post_path = _write_post(tmp_path, _BASE_POST)
        original = parse_stack_post(post_path)
        assert original is not None

        result = add_finding(post_path, "agent", "New finding")

        assert result.problem == original.problem
        assert result.evidence == original.evidence

    def test_vote_preserves_body(self, tmp_path: Path) -> None:
        post_path = _write_post(tmp_path, _POST_WITH_FINDING, "ST-002.md")
        original = parse_stack_post(post_path)
        assert original is not None

        result = record_vote(post_path, "post", "up", "agent")

        assert result.problem == original.problem
        assert result.evidence == original.evidence

    def test_accept_preserves_body(self, tmp_path: Path) -> None:
        post_path = _write_post(tmp_path, _POST_WITH_FINDING, "ST-002.md")
        original = parse_stack_post(post_path)
        assert original is not None

        result = accept_finding(post_path, 1)

        assert result.problem == original.problem
        assert result.evidence == original.evidence
