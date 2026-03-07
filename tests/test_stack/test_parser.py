"""Unit tests for Stack post parser."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from lexibrary.exceptions import ConfigError
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

### F1

**Date:** 2026-02-21 | **Author:** agent-456 | **Votes:** 2 | **Accepted:** true

Use `calendar.isleap()` to check before parsing.

#### Comments

**2026-02-22 agent-789 [upvote]:** Confirmed this works.

### F2

**Date:** 2026-02-22 | **Author:** agent-789 | **Votes:** -1

Try a different library instead.

#### Comments

**2026-02-22 agent-123 [downvote]:** This approach is unreliable.
**2026-02-23 agent-456 [upvote]:** Worth considering though.
"""

_POST_NO_FINDINGS = """\
---
id: ST-002
title: No findings yet
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

_POST_ACCEPTED_FINDING = """\
---
id: ST-003
title: Accepted finding post
tags:
  - resolved
status: resolved
created: 2026-02-21
author: agent-200
---

## Problem

Need a solution.

### F1

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

_POST_ALL_FOUR_SECTIONS = """\
---
id: ST-010
title: All four body sections
tags:
  - bug
created: 2026-03-01
author: agent-400
---

## Problem

The database connection times out under load.

### Context

Running against PostgreSQL 15 on a staging environment with 4 vCPUs.

### Evidence

- connection pool exhausted after 30s
- no idle connections available

### Attempts

- Increased pool size to 50
- Added connection timeout of 10s
"""

_POST_MISSING_CONTEXT = """\
---
id: ST-011
title: Missing context section
tags:
  - bug
created: 2026-03-01
author: agent-400
---

## Problem

Widget rendering fails on Safari.

### Evidence

- CSS grid not supported in Safari 14

### Attempts

- Tried flexbox fallback
"""

_POST_MISSING_ATTEMPTS = """\
---
id: ST-012
title: Missing attempts section
tags:
  - question
created: 2026-03-01
author: agent-400
---

## Problem

Memory leak in event handlers.

### Context

React 18 app with useEffect cleanup handlers.

### Evidence

- heap snapshot shows growing detached DOM nodes
"""

_POST_NON_CANONICAL_ORDER = """\
---
id: ST-013
title: Sections in non-canonical order
tags:
  - bug
created: 2026-03-01
author: agent-400
---

## Problem

Parser handles any order.

### Attempts

- Tried approach A
- Tried approach B

### Evidence

- log entry alpha
- log entry beta

### Context

Context comes last but should still parse.
"""

_POST_SCAFFOLD_ONLY = """\
---
id: ST-014
title: Scaffold-only post
tags:
  - question
created: 2026-03-01
author: agent-400
---

## Problem

<!-- Describe the problem -->

### Context

<!-- What were you doing when this happened? -->

### Evidence

<!-- Add supporting evidence as bullet points -->

### Attempts

<!-- List approaches tried as bullet points -->
"""

_POST_FINDINGS_TERMINATES = """\
---
id: ST-015
title: Findings header terminates body extraction
tags:
  - resolved
status: resolved
created: 2026-03-01
author: agent-400
---

## Problem

Something is broken.

## Findings

### F1

**Date:** 2026-03-01 | **Author:** agent-500 | **Votes:** 1 | **Accepted:** true

Fixed by restarting.
"""

_POST_F1_TERMINATES_DIRECTLY = """\
---
id: ST-016
title: F1 header terminates body extraction directly
tags:
  - resolved
status: resolved
created: 2026-03-01
author: agent-400
---

## Problem

Something is broken.

### F1

**Date:** 2026-03-01 | **Author:** agent-500 | **Votes:** 1 | **Accepted:** true

Fixed by restarting.
"""

_POST_PARTIAL_SCAFFOLD = """\
---
id: ST-017
title: Partial scaffold
tags:
  - bug
created: 2026-03-01
author: agent-400
---

## Problem

The real problem description lives here.

### Context

<!-- What were you doing when this happened? -->

### Evidence

- actual evidence item

### Attempts

<!-- List approaches tried as bullet points -->
"""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestParseValidPost:
    """Tests for parsing a well-formed post with findings."""

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

    def test_finding_count(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-001.md"
        p.write_text(_VALID_POST)
        post = parse_stack_post(p)
        assert post is not None
        assert len(post.findings) == 2

    def test_finding_one_metadata(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-001.md"
        p.write_text(_VALID_POST)
        post = parse_stack_post(p)
        assert post is not None
        f1 = post.findings[0]
        assert f1.number == 1
        assert f1.date == date(2026, 2, 21)
        assert f1.author == "agent-456"
        assert f1.votes == 2
        assert f1.accepted is True

    def test_finding_one_body(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-001.md"
        p.write_text(_VALID_POST)
        post = parse_stack_post(p)
        assert post is not None
        assert "calendar.isleap()" in post.findings[0].body

    def test_finding_one_comments(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-001.md"
        p.write_text(_VALID_POST)
        post = parse_stack_post(p)
        assert post is not None
        assert len(post.findings[0].comments) == 1
        assert "[upvote]" in post.findings[0].comments[0]

    def test_finding_two_metadata(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-001.md"
        p.write_text(_VALID_POST)
        post = parse_stack_post(p)
        assert post is not None
        f2 = post.findings[1]
        assert f2.number == 2
        assert f2.date == date(2026, 2, 22)
        assert f2.author == "agent-789"
        assert f2.votes == -1
        assert f2.accepted is False

    def test_finding_two_comments(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-001.md"
        p.write_text(_VALID_POST)
        post = parse_stack_post(p)
        assert post is not None
        assert len(post.findings[1].comments) == 2
        assert "[downvote]" in post.findings[1].comments[0]
        assert "[upvote]" in post.findings[1].comments[1]

    def test_raw_body_stored(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-001.md"
        p.write_text(_VALID_POST)
        post = parse_stack_post(p)
        assert post is not None
        assert post.raw_body != ""
        assert "## Problem" in post.raw_body


class TestParsePostNoFindings:
    """Tests for parsing a post with no findings."""

    def test_returns_empty_findings(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-002.md"
        p.write_text(_POST_NO_FINDINGS)
        post = parse_stack_post(p)
        assert post is not None
        assert post.findings == []

    def test_problem_extracted(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-002.md"
        p.write_text(_POST_NO_FINDINGS)
        post = parse_stack_post(p)
        assert post is not None
        assert "Something is broken" in post.problem

    def test_evidence_extracted(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-002.md"
        p.write_text(_POST_NO_FINDINGS)
        post = parse_stack_post(p)
        assert post is not None
        assert post.evidence == ["error log entry"]


class TestParseAcceptedFinding:
    """Tests for parsing a post with an accepted finding."""

    def test_accepted_flag(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-003.md"
        p.write_text(_POST_ACCEPTED_FINDING)
        post = parse_stack_post(p)
        assert post is not None
        assert len(post.findings) == 1
        assert post.findings[0].accepted is True
        assert post.findings[0].votes == 5

    def test_status_resolved(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-003.md"
        p.write_text(_POST_ACCEPTED_FINDING)
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

    def test_invalid_frontmatter_raises_config_error(self, tmp_path: Path) -> None:
        p = tmp_path / "malformed.md"
        p.write_text(_MALFORMED_FRONTMATTER)
        with pytest.raises(ConfigError):
            parse_stack_post(p)

    def test_no_frontmatter_returns_none(self, tmp_path: Path) -> None:
        p = tmp_path / "no-fm.md"
        p.write_text(_NO_FRONTMATTER)
        result = parse_stack_post(p)
        assert result is None


# ---------------------------------------------------------------------------
# TG3: Parser Changes (Phase 2) — new body section tests
# ---------------------------------------------------------------------------


class TestParseAllFourSections:
    """Task 3.5: parse post with all four body sections."""

    def test_problem_populated(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-010.md"
        p.write_text(_POST_ALL_FOUR_SECTIONS)
        post = parse_stack_post(p)
        assert post is not None
        assert "database connection times out" in post.problem

    def test_context_populated(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-010.md"
        p.write_text(_POST_ALL_FOUR_SECTIONS)
        post = parse_stack_post(p)
        assert post is not None
        assert "PostgreSQL 15" in post.context

    def test_evidence_populated(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-010.md"
        p.write_text(_POST_ALL_FOUR_SECTIONS)
        post = parse_stack_post(p)
        assert post is not None
        assert post.evidence == [
            "connection pool exhausted after 30s",
            "no idle connections available",
        ]

    def test_attempts_populated(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-010.md"
        p.write_text(_POST_ALL_FOUR_SECTIONS)
        post = parse_stack_post(p)
        assert post is not None
        assert post.attempts == [
            "Increased pool size to 50",
            "Added connection timeout of 10s",
        ]


class TestParseMissingContext:
    """Task 3.6: parse post with missing Context -> empty string."""

    def test_context_is_empty(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-011.md"
        p.write_text(_POST_MISSING_CONTEXT)
        post = parse_stack_post(p)
        assert post is not None
        assert post.context == ""

    def test_other_sections_present(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-011.md"
        p.write_text(_POST_MISSING_CONTEXT)
        post = parse_stack_post(p)
        assert post is not None
        assert "Widget rendering fails" in post.problem
        assert post.evidence == ["CSS grid not supported in Safari 14"]
        assert post.attempts == ["Tried flexbox fallback"]


class TestParseMissingAttempts:
    """Task 3.7: parse post with missing Attempts -> empty list."""

    def test_attempts_is_empty(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-012.md"
        p.write_text(_POST_MISSING_ATTEMPTS)
        post = parse_stack_post(p)
        assert post is not None
        assert post.attempts == []

    def test_other_sections_present(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-012.md"
        p.write_text(_POST_MISSING_ATTEMPTS)
        post = parse_stack_post(p)
        assert post is not None
        assert "Memory leak" in post.problem
        assert "React 18" in post.context
        assert post.evidence == ["heap snapshot shows growing detached DOM nodes"]


class TestParseNonCanonicalOrder:
    """Task 3.8: sections in non-canonical order parse correctly."""

    def test_problem_parsed(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-013.md"
        p.write_text(_POST_NON_CANONICAL_ORDER)
        post = parse_stack_post(p)
        assert post is not None
        assert "Parser handles any order" in post.problem

    def test_context_parsed(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-013.md"
        p.write_text(_POST_NON_CANONICAL_ORDER)
        post = parse_stack_post(p)
        assert post is not None
        assert "Context comes last" in post.context

    def test_evidence_parsed(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-013.md"
        p.write_text(_POST_NON_CANONICAL_ORDER)
        post = parse_stack_post(p)
        assert post is not None
        assert post.evidence == ["log entry alpha", "log entry beta"]

    def test_attempts_parsed(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-013.md"
        p.write_text(_POST_NON_CANONICAL_ORDER)
        post = parse_stack_post(p)
        assert post is not None
        assert post.attempts == ["Tried approach A", "Tried approach B"]


class TestParseScaffoldOnlyPost:
    """Task 3.9: HTML comment placeholders are stripped -- scaffold-only post parses to empty fields."""

    def test_problem_empty(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-014.md"
        p.write_text(_POST_SCAFFOLD_ONLY)
        post = parse_stack_post(p)
        assert post is not None
        assert post.problem == ""

    def test_context_empty(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-014.md"
        p.write_text(_POST_SCAFFOLD_ONLY)
        post = parse_stack_post(p)
        assert post is not None
        assert post.context == ""

    def test_evidence_empty(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-014.md"
        p.write_text(_POST_SCAFFOLD_ONLY)
        post = parse_stack_post(p)
        assert post is not None
        assert post.evidence == []

    def test_attempts_empty(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-014.md"
        p.write_text(_POST_SCAFFOLD_ONLY)
        post = parse_stack_post(p)
        assert post is not None
        assert post.attempts == []


class TestParseFindingsTerminatesBody:
    """Task 3.10: ## Findings / ### F{n} header terminates body section extraction."""

    def test_findings_header_terminates(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-015.md"
        p.write_text(_POST_FINDINGS_TERMINATES)
        post = parse_stack_post(p)
        assert post is not None
        assert "Something is broken" in post.problem
        # Context/evidence/attempts should be empty -- nothing after Problem
        assert post.context == ""
        assert post.evidence == []
        assert post.attempts == []

    def test_findings_still_parsed(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-015.md"
        p.write_text(_POST_FINDINGS_TERMINATES)
        post = parse_stack_post(p)
        assert post is not None
        assert len(post.findings) == 1
        assert post.findings[0].accepted is True

    def test_f1_directly_terminates(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-016.md"
        p.write_text(_POST_F1_TERMINATES_DIRECTLY)
        post = parse_stack_post(p)
        assert post is not None
        assert "Something is broken" in post.problem
        assert post.context == ""
        assert post.evidence == []
        assert post.attempts == []
        assert len(post.findings) == 1
        assert post.findings[0].accepted is True


class TestParsePartialScaffold:
    """Task 3.11: partial scaffold -- Problem filled, Context is comment placeholder."""

    def test_problem_has_content(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-017.md"
        p.write_text(_POST_PARTIAL_SCAFFOLD)
        post = parse_stack_post(p)
        assert post is not None
        assert "real problem description" in post.problem

    def test_context_is_empty(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-017.md"
        p.write_text(_POST_PARTIAL_SCAFFOLD)
        post = parse_stack_post(p)
        assert post is not None
        assert post.context == ""

    def test_evidence_has_content(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-017.md"
        p.write_text(_POST_PARTIAL_SCAFFOLD)
        post = parse_stack_post(p)
        assert post is not None
        assert post.evidence == ["actual evidence item"]

    def test_attempts_is_empty(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-017.md"
        p.write_text(_POST_PARTIAL_SCAFFOLD)
        post = parse_stack_post(p)
        assert post is not None
        assert post.attempts == []


class TestLegacyPostBackwardCompatibility:
    """Backward compatibility: legacy posts with only Problem + Evidence still parse."""

    def test_context_defaults_empty(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-002.md"
        p.write_text(_POST_NO_FINDINGS)
        post = parse_stack_post(p)
        assert post is not None
        assert post.context == ""

    def test_attempts_defaults_empty(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-002.md"
        p.write_text(_POST_NO_FINDINGS)
        post = parse_stack_post(p)
        assert post is not None
        assert post.attempts == []

    def test_valid_post_context_defaults_empty(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-001.md"
        p.write_text(_VALID_POST)
        post = parse_stack_post(p)
        assert post is not None
        assert post.context == ""

    def test_valid_post_attempts_defaults_empty(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-001.md"
        p.write_text(_VALID_POST)
        post = parse_stack_post(p)
        assert post is not None
        assert post.attempts == []


# ---------------------------------------------------------------------------
# TG6: Serializer & Parser Updates — stale_at parser tests (task 6.1/6.2)
# ---------------------------------------------------------------------------

_POST_WITH_STALE_AT = """\
---
id: ST-020
title: Stale post with stale_at
tags:
  - bug
status: stale
created: 2026-03-01
author: agent-400
resolution_type: fix
stale_at: '2026-06-15T10:00:00'
---

## Problem

Old fix no longer applies after library upgrade.
"""

_POST_WITHOUT_STALE_AT = """\
---
id: ST-021
title: Resolved post without stale_at
tags:
  - bug
status: resolved
created: 2026-03-01
author: agent-400
resolution_type: fix
---

## Problem

This was fixed normally.
"""


class TestParseStaleAtField:
    """Task 6.1/6.2: parse stale_at field from frontmatter."""

    def test_stale_at_parsed(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-020.md"
        p.write_text(_POST_WITH_STALE_AT)
        post = parse_stack_post(p)
        assert post is not None
        assert post.frontmatter.stale_at == "2026-06-15T10:00:00"

    def test_stale_status_parsed(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-020.md"
        p.write_text(_POST_WITH_STALE_AT)
        post = parse_stack_post(p)
        assert post is not None
        assert post.frontmatter.status == "stale"

    def test_stale_at_defaults_none(self, tmp_path: Path) -> None:
        p = tmp_path / "ST-021.md"
        p.write_text(_POST_WITHOUT_STALE_AT)
        post = parse_stack_post(p)
        assert post is not None
        assert post.frontmatter.stale_at is None

    def test_legacy_post_stale_at_defaults_none(self, tmp_path: Path) -> None:
        """Legacy posts without stale_at field default to None."""
        p = tmp_path / "ST-001.md"
        p.write_text(_VALID_POST)
        post = parse_stack_post(p)
        assert post is not None
        assert post.frontmatter.stale_at is None
