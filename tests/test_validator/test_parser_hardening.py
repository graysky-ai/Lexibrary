"""Tests for parser hardening — Task Group 5 of lexi-validate.

Covers:
- Stack resilience: one malformed post does not crash validation checks
- Datetime coercion for convention and Stack frontmatter models
- Serializer round-trip with datetime fields
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from lexibrary.artifacts.convention import ConventionFile, ConventionFileFrontmatter
from lexibrary.conventions.parser import parse_convention_file
from lexibrary.conventions.serializer import serialize_convention_file
from lexibrary.stack.models import StackPostFrontmatter
from lexibrary.stack.parser import parse_stack_post
from lexibrary.stack.serializer import serialize_stack_post
from lexibrary.validator.checks import (
    check_file_existence,
    check_resolved_post_staleness,
    check_stack_staleness,
    check_wikilink_resolution,
)

# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

_VALID_STACK_POST = """\
---
id: ST-001
title: Valid post
tags:
  - test
status: open
created: 2026-01-01
author: tester
refs:
  files: []
  designs: []
  concepts: []
---

## Problem

This is a valid post.
"""

_MALFORMED_STACK_POST = """\
---
id: ST-002
title: 123
tags: not-a-list
status: open
created: not-a-date
author: tester
---

## Problem

This frontmatter has invalid fields.
"""

_MALFORMED_YAML_STACK_POST = """\
---
id: ST-003
title: Bad YAML
  tags: [indentation error
status: open
---

## Problem

Totally broken YAML.
"""


def _setup_minimal_project(tmp_path: Path) -> tuple[Path, Path]:
    """Create a minimal project with .lexibrary directory.

    Returns (project_root, lexibrary_dir).
    """
    project_root = tmp_path
    lexibrary_dir = project_root / ".lexibrary"
    lexibrary_dir.mkdir(parents=True)
    # Write a minimal config
    (lexibrary_dir / "config.yaml").write_text("scope_root: .\n", encoding="utf-8")
    # Create concepts dir (needed for wikilink resolution)
    (lexibrary_dir / "concepts").mkdir()
    return project_root, lexibrary_dir


def _write_stack_post(lexibrary_dir: Path, filename: str, content: str) -> Path:
    """Write a Stack post to the stack directory."""
    stack_dir = lexibrary_dir / "stack"
    stack_dir.mkdir(parents=True, exist_ok=True)
    post_path = stack_dir / filename
    post_path.write_text(content, encoding="utf-8")
    return post_path


# ---------------------------------------------------------------------------
# Stack resilience: one bad post does not crash checks
# ---------------------------------------------------------------------------


class TestStackResilience:
    """One malformed Stack post should not prevent validation of other posts."""

    def test_check_wikilink_resolution_skips_malformed_post(
        self, tmp_path: Path
    ) -> None:
        """check_wikilink_resolution skips a malformed post and continues."""
        project_root, lexibrary_dir = _setup_minimal_project(tmp_path)
        _write_stack_post(lexibrary_dir, "ST-001-valid.md", _VALID_STACK_POST)
        _write_stack_post(lexibrary_dir, "ST-002-bad.md", _MALFORMED_STACK_POST)

        # Should not raise -- malformed post is skipped
        issues = check_wikilink_resolution(project_root, lexibrary_dir)
        # No assertion on issue count -- just verifying no crash
        assert isinstance(issues, list)

    def test_check_file_existence_skips_malformed_post(
        self, tmp_path: Path
    ) -> None:
        """check_file_existence skips a malformed post and continues."""
        project_root, lexibrary_dir = _setup_minimal_project(tmp_path)
        _write_stack_post(lexibrary_dir, "ST-001-valid.md", _VALID_STACK_POST)
        _write_stack_post(lexibrary_dir, "ST-002-bad.md", _MALFORMED_STACK_POST)

        issues = check_file_existence(project_root, lexibrary_dir)
        assert isinstance(issues, list)

    def test_check_stack_staleness_skips_malformed_post(
        self, tmp_path: Path
    ) -> None:
        """check_stack_staleness skips a malformed post and continues."""
        project_root, lexibrary_dir = _setup_minimal_project(tmp_path)
        _write_stack_post(lexibrary_dir, "ST-001-valid.md", _VALID_STACK_POST)
        _write_stack_post(lexibrary_dir, "ST-002-bad.md", _MALFORMED_STACK_POST)

        issues = check_stack_staleness(project_root, lexibrary_dir)
        assert isinstance(issues, list)

    def test_check_resolved_post_staleness_skips_malformed_post(
        self, tmp_path: Path
    ) -> None:
        """check_resolved_post_staleness skips a malformed post and continues."""
        project_root, lexibrary_dir = _setup_minimal_project(tmp_path)
        _write_stack_post(lexibrary_dir, "ST-001-valid.md", _VALID_STACK_POST)
        _write_stack_post(lexibrary_dir, "ST-002-bad.md", _MALFORMED_STACK_POST)

        issues = check_resolved_post_staleness(project_root, lexibrary_dir)
        assert isinstance(issues, list)

    def test_check_wikilink_resolution_skips_broken_yaml(
        self, tmp_path: Path
    ) -> None:
        """A post with completely broken YAML is skipped without crashing."""
        project_root, lexibrary_dir = _setup_minimal_project(tmp_path)
        _write_stack_post(lexibrary_dir, "ST-001-valid.md", _VALID_STACK_POST)
        _write_stack_post(
            lexibrary_dir, "ST-003-broken.md", _MALFORMED_YAML_STACK_POST
        )

        issues = check_wikilink_resolution(project_root, lexibrary_dir)
        assert isinstance(issues, list)

    def test_all_malformed_posts_returns_empty(self, tmp_path: Path) -> None:
        """When all posts are malformed, checks return empty lists, not crash."""
        project_root, lexibrary_dir = _setup_minimal_project(tmp_path)
        _write_stack_post(lexibrary_dir, "ST-001-bad1.md", _MALFORMED_STACK_POST)
        _write_stack_post(
            lexibrary_dir, "ST-002-bad2.md", _MALFORMED_YAML_STACK_POST
        )

        assert check_stack_staleness(project_root, lexibrary_dir) == []
        assert check_resolved_post_staleness(project_root, lexibrary_dir) == []


# ---------------------------------------------------------------------------
# Datetime coercion for convention model
# ---------------------------------------------------------------------------


class TestConventionDatetimeCoercion:
    """ConventionFileFrontmatter.deprecated_at accepts both strings and datetimes."""

    def test_deprecated_at_accepts_iso_string(self) -> None:
        """An ISO 8601 string is coerced to a datetime object."""
        fm = ConventionFileFrontmatter(
            title="Old rule",
            status="deprecated",
            deprecated_at="2026-03-04T10:00:00",
        )
        assert isinstance(fm.deprecated_at, datetime)
        assert fm.deprecated_at == datetime(2026, 3, 4, 10, 0, 0)

    def test_deprecated_at_accepts_datetime_object(self) -> None:
        """A native datetime is stored directly."""
        dt = datetime(2026, 6, 15, 12, 30, 0)
        fm = ConventionFileFrontmatter(
            title="Old rule",
            status="deprecated",
            deprecated_at=dt,
        )
        assert fm.deprecated_at == dt

    def test_deprecated_at_none_by_default(self) -> None:
        """When not set, deprecated_at is None."""
        fm = ConventionFileFrontmatter(title="Active rule")
        assert fm.deprecated_at is None


# ---------------------------------------------------------------------------
# Datetime coercion for Stack model
# ---------------------------------------------------------------------------


class TestStackDatetimeCoercion:
    """StackPostFrontmatter.stale_at and .last_vote_at accept strings and datetimes."""

    def _make(self, **overrides: object) -> StackPostFrontmatter:
        defaults: dict[str, object] = {
            "id": "ST-001",
            "title": "Test",
            "tags": ["test"],
            "created": "2026-01-01",
            "author": "tester",
        }
        defaults.update(overrides)
        return StackPostFrontmatter(**defaults)  # type: ignore[arg-type]

    def test_stale_at_accepts_iso_string(self) -> None:
        """An ISO 8601 string for stale_at is coerced to datetime."""
        fm = self._make(stale_at="2026-06-15T10:00:00")
        assert isinstance(fm.stale_at, datetime)
        assert fm.stale_at == datetime(2026, 6, 15, 10, 0, 0)

    def test_stale_at_accepts_datetime_object(self) -> None:
        """A native datetime for stale_at is stored directly."""
        dt = datetime(2026, 6, 15, 10, 0, 0)
        fm = self._make(stale_at=dt)
        assert fm.stale_at == dt

    def test_last_vote_at_accepts_iso_string(self) -> None:
        """An ISO 8601 string for last_vote_at is coerced to datetime."""
        fm = self._make(last_vote_at="2026-03-10T14:30:00")
        assert isinstance(fm.last_vote_at, datetime)
        assert fm.last_vote_at == datetime(2026, 3, 10, 14, 30, 0)

    def test_last_vote_at_accepts_datetime_object(self) -> None:
        """A native datetime for last_vote_at is stored directly."""
        dt = datetime(2026, 3, 10, 14, 30, 0)
        fm = self._make(last_vote_at=dt)
        assert fm.last_vote_at == dt

    def test_both_default_to_none(self) -> None:
        """stale_at and last_vote_at default to None."""
        fm = self._make()
        assert fm.stale_at is None
        assert fm.last_vote_at is None


# ---------------------------------------------------------------------------
# Serializer round-trip with datetime fields
# ---------------------------------------------------------------------------


class TestConventionSerializerDatetimeRoundTrip:
    """Convention serialize -> parse round-trip preserves datetime fields."""

    def test_deprecated_at_round_trips(self, tmp_path: Path) -> None:
        """deprecated_at survives serialization and parsing back."""
        dt = datetime(2026, 3, 4, 10, 0, 0)
        original = ConventionFile(
            frontmatter=ConventionFileFrontmatter(
                title="Deprecated convention",
                status="deprecated",
                deprecated_at=dt,
            ),
            body="\nThis is deprecated.\n",
        )

        serialized = serialize_convention_file(original)
        path = tmp_path / "deprecated.md"
        path.write_text(serialized, encoding="utf-8")
        parsed = parse_convention_file(path)

        assert parsed is not None
        assert parsed.frontmatter.deprecated_at == dt
        assert isinstance(parsed.frontmatter.deprecated_at, datetime)

    def test_deprecated_at_none_not_in_yaml(self, tmp_path: Path) -> None:
        """When deprecated_at is None, the key does not appear in YAML."""
        original = ConventionFile(
            frontmatter=ConventionFileFrontmatter(title="Active", status="active"),
            body="\nActive convention.\n",
        )

        serialized = serialize_convention_file(original)
        assert "deprecated_at" not in serialized

        path = tmp_path / "active.md"
        path.write_text(serialized, encoding="utf-8")
        parsed = parse_convention_file(path)

        assert parsed is not None
        assert parsed.frontmatter.deprecated_at is None


class TestStackSerializerDatetimeRoundTrip:
    """Stack serialize -> parse round-trip preserves datetime fields."""

    def _make_post(
        self,
        *,
        stale_at: datetime | None = None,
        last_vote_at: datetime | None = None,
    ) -> tuple[StackPostFrontmatter, str]:
        """Build a minimal StackPost and serialize it."""
        from datetime import date

        from lexibrary.stack.models import StackPost

        fm = StackPostFrontmatter(
            id="ST-001",
            title="Test post",
            tags=["test"],
            created=date(2026, 1, 1),
            author="tester",
            stale_at=stale_at,
            last_vote_at=last_vote_at,
        )
        post = StackPost(frontmatter=fm, problem="A test problem.")
        return fm, serialize_stack_post(post)

    def test_stale_at_round_trips(self, tmp_path: Path) -> None:
        """stale_at survives serialization and parsing back."""
        dt = datetime(2026, 6, 15, 10, 0, 0)
        _, serialized = self._make_post(stale_at=dt)

        path = tmp_path / "ST-001-test.md"
        path.write_text(serialized, encoding="utf-8")
        parsed = parse_stack_post(path)

        assert parsed is not None
        assert parsed.frontmatter.stale_at == dt
        assert isinstance(parsed.frontmatter.stale_at, datetime)

    def test_last_vote_at_round_trips(self, tmp_path: Path) -> None:
        """last_vote_at survives serialization and parsing back."""
        dt = datetime(2026, 3, 10, 14, 30, 0)
        _, serialized = self._make_post(last_vote_at=dt)

        path = tmp_path / "ST-001-test.md"
        path.write_text(serialized, encoding="utf-8")
        parsed = parse_stack_post(path)

        assert parsed is not None
        assert parsed.frontmatter.last_vote_at == dt
        assert isinstance(parsed.frontmatter.last_vote_at, datetime)

    def test_both_datetime_fields_none_omitted(self, tmp_path: Path) -> None:
        """When stale_at and last_vote_at are None, keys are absent from YAML."""
        _, serialized = self._make_post()

        assert "stale_at" not in serialized
        assert "last_vote_at" not in serialized

        path = tmp_path / "ST-001-test.md"
        path.write_text(serialized, encoding="utf-8")
        parsed = parse_stack_post(path)

        assert parsed is not None
        assert parsed.frontmatter.stale_at is None
        assert parsed.frontmatter.last_vote_at is None
