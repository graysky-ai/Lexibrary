"""Unit tests for playbook validation checks.

Tests check_playbook_frontmatter, check_playbook_wikilinks,
check_playbook_staleness, and check_playbook_deprecated_ttl from
the validator.checks module.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch

from lexibrary.validator.checks import (
    check_playbook_deprecated_ttl,
    check_playbook_frontmatter,
    check_playbook_staleness,
    check_playbook_wikilinks,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_playbook_id_counter = 0


def _next_playbook_id() -> str:
    global _playbook_id_counter
    _playbook_id_counter += 1
    return f"PB-{_playbook_id_counter:03d}"


def _write_playbook(
    playbooks_dir: Path,
    name: str,
    *,
    raw_content: str | None = None,
    title: str = "Test Playbook",
    status: str = "draft",
    source: str = "user",
    trigger_files: str = "[]",
    tags: str = "[]",
    last_verified: str | None = None,
    deprecated_at: str | None = None,
    superseded_by: str | None = None,
    pb_id: str | None = None,
) -> Path:
    """Write a playbook file; use raw_content for custom frontmatter."""
    playbooks_dir.mkdir(parents=True, exist_ok=True)
    path = playbooks_dir / f"{name}.md"
    if raw_content is not None:
        path.write_text(raw_content, encoding="utf-8")
    else:
        artifact_id = pb_id if pb_id is not None else _next_playbook_id()
        lines = [
            "---",
            f"title: {title}",
            f"id: {artifact_id}",
            f"status: {status}",
            f"source: {source}",
            f"trigger_files: {trigger_files}",
            f"tags: {tags}",
        ]
        if last_verified is not None:
            lines.append(f"last_verified: {last_verified}")
        if deprecated_at is not None:
            lines.append(f"deprecated_at: {deprecated_at}")
        if superseded_by is not None:
            lines.append(f"superseded_by: {superseded_by}")
        lines.append("---")
        lines.append("")
        lines.append("## Overview")
        lines.append("")
        lines.append("A test playbook.")
        lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")
    return path


_concept_id_counter = 0


def _next_concept_id() -> str:
    global _concept_id_counter
    _concept_id_counter += 1
    return f"CN-{_concept_id_counter:03d}"


def _write_concept(concepts_dir: Path, name: str, title: str) -> Path:
    """Write a concept file for wikilink resolution tests."""
    concepts_dir.mkdir(parents=True, exist_ok=True)
    path = concepts_dir / f"{name}.md"
    concept_id = _next_concept_id()
    path.write_text(
        f"""---
title: {title}
id: {concept_id}
status: active
aliases: []
tags: []
linked_files: []
---

{title} concept body.
""",
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# check_playbook_frontmatter
# ---------------------------------------------------------------------------


class TestCheckPlaybookFrontmatter:
    """Tests for check_playbook_frontmatter."""

    def test_valid_playbook_returns_empty(self, tmp_path: Path) -> None:
        """Valid playbook with all fields produces no issues."""
        project_root = tmp_path
        ld = tmp_path / ".lexibrary"
        _write_playbook(ld / "playbooks", "good-playbook")

        issues = check_playbook_frontmatter(project_root, ld)
        assert issues == []

    def test_missing_directory_returns_empty(self, tmp_path: Path) -> None:
        """No playbooks directory returns empty list."""
        project_root = tmp_path
        ld = tmp_path / ".lexibrary"
        ld.mkdir()

        issues = check_playbook_frontmatter(project_root, ld)
        assert issues == []

    def test_missing_frontmatter(self, tmp_path: Path) -> None:
        """Playbook file with no frontmatter produces error."""
        project_root = tmp_path
        ld = tmp_path / ".lexibrary"
        _write_playbook(
            ld / "playbooks",
            "no-frontmatter",
            raw_content="# No frontmatter here\n",
        )

        issues = check_playbook_frontmatter(project_root, ld)
        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert issues[0].check == "playbook_frontmatter"
        assert "Missing YAML frontmatter" in issues[0].message

    def test_invalid_yaml(self, tmp_path: Path) -> None:
        """Invalid YAML in frontmatter produces error."""
        project_root = tmp_path
        ld = tmp_path / ".lexibrary"
        _write_playbook(
            ld / "playbooks",
            "bad-yaml",
            raw_content="---\ntitle: [unterminated\nid: CN-001\n---\n",
        )

        issues = check_playbook_frontmatter(project_root, ld)
        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert "Invalid YAML" in issues[0].message

    def test_frontmatter_not_mapping(self, tmp_path: Path) -> None:
        """Frontmatter that is not a mapping produces error."""
        project_root = tmp_path
        ld = tmp_path / ".lexibrary"
        _write_playbook(
            ld / "playbooks",
            "not-mapping",
            raw_content="---\n- item1\n- item2\n---\n",
        )

        issues = check_playbook_frontmatter(project_root, ld)
        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert "not a YAML mapping" in issues[0].message

    def test_missing_title(self, tmp_path: Path) -> None:
        """Playbook missing title field produces error."""
        project_root = tmp_path
        ld = tmp_path / ".lexibrary"
        _write_playbook(
            ld / "playbooks",
            "no-title",
            raw_content="---\nid: PB-001\nstatus: draft\nsource: user\n---\nBody.\n",
        )

        issues = check_playbook_frontmatter(project_root, ld)
        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert "Missing mandatory field: title" in issues[0].message

    def test_empty_title(self, tmp_path: Path) -> None:
        """Playbook with empty title produces error."""
        project_root = tmp_path
        ld = tmp_path / ".lexibrary"
        _write_playbook(
            ld / "playbooks",
            "empty-title",
            raw_content='---\ntitle: ""\nid: PB-002\nstatus: draft\n---\nBody.\n',
        )

        issues = check_playbook_frontmatter(project_root, ld)
        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert "non-empty string" in issues[0].message

    def test_invalid_status(self, tmp_path: Path) -> None:
        """Playbook with invalid status produces error."""
        project_root = tmp_path
        ld = tmp_path / ".lexibrary"
        _write_playbook(
            ld / "playbooks",
            "bad-status",
            raw_content="---\ntitle: Bad Status\nid: PB-003\nstatus: archived\n---\nBody.\n",
        )

        issues = check_playbook_frontmatter(project_root, ld)
        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert "Invalid status" in issues[0].message

    def test_invalid_source(self, tmp_path: Path) -> None:
        """Playbook with invalid source produces error."""
        project_root = tmp_path
        ld = tmp_path / ".lexibrary"
        _write_playbook(
            ld / "playbooks",
            "bad-source",
            raw_content="---\ntitle: Bad Source\nid: PB-004\nsource: system\n---\nBody.\n",
        )

        issues = check_playbook_frontmatter(project_root, ld)
        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert "Invalid source" in issues[0].message

    @patch(
        "pathspec.PathSpec.from_lines",
        side_effect=ValueError("bad pattern"),
    )
    def test_invalid_trigger_glob(self, mock_pathspec: object, tmp_path: Path) -> None:
        """Playbook with unparseable trigger_files glob produces error."""
        project_root = tmp_path
        ld = tmp_path / ".lexibrary"
        _write_playbook(
            ld / "playbooks",
            "bad-trigger",
            raw_content='---\ntitle: Bad Trigger\ntrigger_files:\n  - "[invalid"\n---\nBody.\n',
        )

        issues = check_playbook_frontmatter(project_root, ld)
        # Filter to trigger-related issues only
        trigger_issues = [i for i in issues if "trigger_files" in i.message]
        assert len(trigger_issues) == 1
        assert trigger_issues[0].severity == "error"
        assert "Invalid trigger_files glob" in trigger_issues[0].message

    def test_valid_trigger_globs(self, tmp_path: Path) -> None:
        """Playbook with valid trigger_files globs produces no trigger issues."""
        project_root = tmp_path
        ld = tmp_path / ".lexibrary"
        _write_playbook(
            ld / "playbooks",
            "good-triggers",
            trigger_files='["src/**/*.py", "tests/"]',
        )

        issues = check_playbook_frontmatter(project_root, ld)
        assert issues == []

    def test_valid_playbook_all_statuses(self, tmp_path: Path) -> None:
        """All valid status values pass validation."""
        project_root = tmp_path
        ld = tmp_path / ".lexibrary"
        for i, status in enumerate(["draft", "active", "deprecated"]):
            _write_playbook(
                ld / "playbooks",
                f"playbook-{i}",
                title=f"Playbook {i}",
                status=status,
            )

        issues = check_playbook_frontmatter(project_root, ld)
        assert issues == []


# ---------------------------------------------------------------------------
# check_playbook_wikilinks
# ---------------------------------------------------------------------------


class TestCheckPlaybookWikilinks:
    """Tests for check_playbook_wikilinks."""

    def test_no_playbooks_dir(self, tmp_path: Path) -> None:
        """No playbooks directory returns empty list."""
        project_root = tmp_path
        ld = tmp_path / ".lexibrary"
        ld.mkdir()

        issues = check_playbook_wikilinks(project_root, ld)
        assert issues == []

    def test_valid_wikilinks(self, tmp_path: Path) -> None:
        """Playbook with valid concept wikilinks produces no issues."""
        project_root = tmp_path
        ld = tmp_path / ".lexibrary"

        # Create a concept for the wikilink to resolve to
        _write_concept(ld / "concepts", "my-concept", "My Concept")

        # Create a playbook that links to the concept
        _write_playbook(
            ld / "playbooks",
            "linked-playbook",
            raw_content=(
                "---\ntitle: Linked Playbook\nid: PB-005\nstatus: draft\n---\n\n"
                "Follow the [[My Concept]] guidelines.\n"
            ),
        )

        issues = check_playbook_wikilinks(project_root, ld)
        assert issues == []

    def test_broken_wikilink(self, tmp_path: Path) -> None:
        """Playbook with unresolved wikilink produces error."""
        project_root = tmp_path
        ld = tmp_path / ".lexibrary"

        # Create playbooks dir but no concepts
        _write_playbook(
            ld / "playbooks",
            "broken-link",
            raw_content=(
                "---\ntitle: Broken Link\nid: PB-006\nstatus: draft\n---\n\n"
                "Follow the [[convention: Nonexistent]] instructions.\n"
            ),
        )

        issues = check_playbook_wikilinks(project_root, ld)
        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert issues[0].check == "playbook_wikilinks"
        assert "does not resolve" in issues[0].message

    def test_playbook_with_no_wikilinks(self, tmp_path: Path) -> None:
        """Playbook with no wikilinks produces no issues."""
        project_root = tmp_path
        ld = tmp_path / ".lexibrary"

        _write_playbook(
            ld / "playbooks",
            "no-links",
            raw_content=(
                "---\ntitle: No Links\nid: PB-007\nstatus: draft\n---\n\n"
                "Just plain text, no links.\n"
            ),
        )

        issues = check_playbook_wikilinks(project_root, ld)
        assert issues == []


# ---------------------------------------------------------------------------
# check_playbook_staleness
# ---------------------------------------------------------------------------


class TestCheckPlaybookStaleness:
    """Tests for check_playbook_staleness."""

    def test_no_playbooks_dir(self, tmp_path: Path) -> None:
        """No playbooks directory returns empty list."""
        project_root = tmp_path
        ld = tmp_path / ".lexibrary"
        ld.mkdir()

        issues = check_playbook_staleness(project_root, ld)
        assert issues == []

    def test_draft_playbook_not_checked(self, tmp_path: Path) -> None:
        """Draft playbooks are not flagged for staleness."""
        project_root = tmp_path
        ld = tmp_path / ".lexibrary"
        _write_playbook(
            ld / "playbooks",
            "draft-playbook",
            status="draft",
        )

        issues = check_playbook_staleness(project_root, ld)
        assert issues == []

    def test_active_never_verified(self, tmp_path: Path) -> None:
        """Active playbook with no last_verified is flagged."""
        project_root = tmp_path
        ld = tmp_path / ".lexibrary"
        _write_playbook(
            ld / "playbooks",
            "unverified",
            status="active",
        )

        issues = check_playbook_staleness(project_root, ld)
        assert len(issues) == 1
        assert issues[0].severity == "info"
        assert issues[0].check == "playbook_staleness"
        assert "never been verified" in issues[0].message

    @patch("lexibrary.validator.checks._count_commits_since", return_value=150)
    def test_stale_by_commits(self, mock_commits: object, tmp_path: Path) -> None:
        """Active playbook stale by commit count is flagged."""
        project_root = tmp_path
        ld = tmp_path / ".lexibrary"
        _write_playbook(
            ld / "playbooks",
            "stale-commits",
            status="active",
            last_verified="2025-01-01",
        )

        issues = check_playbook_staleness(project_root, ld)
        commit_issues = [i for i in issues if "commits since" in i.message]
        assert len(commit_issues) == 1
        assert commit_issues[0].severity == "info"

    @patch("lexibrary.validator.checks._count_commits_since", return_value=5)
    def test_stale_by_days(self, mock_commits: object, tmp_path: Path) -> None:
        """Active playbook stale by calendar days is flagged."""
        project_root = tmp_path
        ld = tmp_path / ".lexibrary"
        # Use a date far in the past to exceed the 180-day default
        _write_playbook(
            ld / "playbooks",
            "stale-days",
            status="active",
            last_verified="2024-01-01",
        )

        issues = check_playbook_staleness(project_root, ld)
        day_issues = [i for i in issues if "days since" in i.message]
        assert len(day_issues) == 1
        assert day_issues[0].severity == "info"

    @patch("lexibrary.validator.checks._count_commits_since", return_value=5)
    def test_recently_verified_not_flagged(self, mock_commits: object, tmp_path: Path) -> None:
        """Recently verified active playbook produces no issues."""
        project_root = tmp_path
        ld = tmp_path / ".lexibrary"
        _write_playbook(
            ld / "playbooks",
            "recently-verified",
            status="active",
            last_verified=date.today().isoformat(),
        )

        issues = check_playbook_staleness(project_root, ld)
        assert issues == []


# ---------------------------------------------------------------------------
# check_playbook_deprecated_ttl
# ---------------------------------------------------------------------------


class TestCheckPlaybookDeprecatedTtl:
    """Tests for check_playbook_deprecated_ttl."""

    def test_no_playbooks_dir(self, tmp_path: Path) -> None:
        """No playbooks directory returns empty list."""
        project_root = tmp_path
        ld = tmp_path / ".lexibrary"
        ld.mkdir()

        issues = check_playbook_deprecated_ttl(project_root, ld)
        assert issues == []

    def test_active_playbook_not_checked(self, tmp_path: Path) -> None:
        """Active playbooks are not checked for deprecated TTL."""
        project_root = tmp_path
        ld = tmp_path / ".lexibrary"
        _write_playbook(
            ld / "playbooks",
            "active-playbook",
            status="active",
        )

        issues = check_playbook_deprecated_ttl(project_root, ld)
        assert issues == []

    @patch("lexibrary.validator.checks._count_commits_since", return_value=100)
    def test_expired_deprecated_playbook(self, mock_commits: object, tmp_path: Path) -> None:
        """Deprecated playbook past TTL is flagged."""
        project_root = tmp_path
        ld = tmp_path / ".lexibrary"
        _write_playbook(
            ld / "playbooks",
            "expired",
            status="deprecated",
            deprecated_at="2024-01-01T00:00:00",
        )

        issues = check_playbook_deprecated_ttl(project_root, ld)
        ttl_issues = [i for i in issues if "exceeded TTL" in i.message]
        assert len(ttl_issues) == 1
        assert ttl_issues[0].severity == "info"
        assert ttl_issues[0].check == "playbook_deprecated_ttl"

    @patch("lexibrary.validator.checks._count_commits_since", return_value=5)
    def test_deprecated_within_ttl(self, mock_commits: object, tmp_path: Path) -> None:
        """Recently deprecated playbook within TTL produces no TTL issues."""
        project_root = tmp_path
        ld = tmp_path / ".lexibrary"
        _write_playbook(
            ld / "playbooks",
            "recent-deprecated",
            status="deprecated",
            deprecated_at="2026-03-19T00:00:00",
        )

        issues = check_playbook_deprecated_ttl(project_root, ld)
        ttl_issues = [i for i in issues if "exceeded TTL" in i.message]
        assert ttl_issues == []

    def test_invalid_superseded_by(self, tmp_path: Path) -> None:
        """Deprecated playbook with nonexistent superseded_by is flagged."""
        project_root = tmp_path
        ld = tmp_path / ".lexibrary"
        _write_playbook(
            ld / "playbooks",
            "bad-superseded",
            status="deprecated",
            superseded_by="nonexistent-slug",
        )

        issues = check_playbook_deprecated_ttl(project_root, ld)
        superseded_issues = [i for i in issues if "superseded_by" in i.message]
        assert len(superseded_issues) == 1
        assert superseded_issues[0].severity == "info"
        assert "no such playbook exists" in superseded_issues[0].message

    @patch("lexibrary.validator.checks._count_commits_since", return_value=5)
    def test_valid_superseded_by(self, mock_commits: object, tmp_path: Path) -> None:
        """Deprecated playbook with valid superseded_by produces no superseded issues."""
        project_root = tmp_path
        ld = tmp_path / ".lexibrary"
        playbooks_dir = ld / "playbooks"

        # Create the target playbook
        _write_playbook(
            playbooks_dir,
            "replacement",
            title="Replacement Playbook",
            status="active",
        )

        # Create the deprecated playbook pointing to it
        _write_playbook(
            playbooks_dir,
            "old-playbook",
            status="deprecated",
            superseded_by="replacement-playbook",
        )

        issues = check_playbook_deprecated_ttl(project_root, ld)
        superseded_issues = [i for i in issues if "superseded_by" in i.message]
        assert superseded_issues == []


# ---------------------------------------------------------------------------
# AVAILABLE_CHECKS registration
# ---------------------------------------------------------------------------


class TestPlaybookChecksRegistered:
    """Verify all four playbook checks are registered in AVAILABLE_CHECKS."""

    def test_all_checks_registered(self) -> None:
        """AVAILABLE_CHECKS contains all four playbook check keys."""
        from lexibrary.validator import AVAILABLE_CHECKS

        expected = {
            "playbook_frontmatter",
            "playbook_wikilinks",
            "playbook_staleness",
            "playbook_deprecated_ttl",
        }
        assert expected.issubset(set(AVAILABLE_CHECKS.keys()))

    def test_severity_assignments(self) -> None:
        """Playbook checks have correct default severities."""
        from lexibrary.validator import AVAILABLE_CHECKS

        assert AVAILABLE_CHECKS["playbook_frontmatter"][1] == "error"
        assert AVAILABLE_CHECKS["playbook_wikilinks"][1] == "error"
        assert AVAILABLE_CHECKS["playbook_staleness"][1] == "info"
        assert AVAILABLE_CHECKS["playbook_deprecated_ttl"][1] == "info"
