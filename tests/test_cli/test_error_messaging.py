"""Tests for the error messaging overhaul (Group 7).

Covers:
- IWH disabled exit codes (Exit(2) instead of Exit(0))
- _require_post helper with recovery hints
- Recovery hints on concept link file-not-found, describe aindex-parse-failure,
  convention-not-found
- Vote rate-limiting with 60s cooldown
- Silent-exit path audit (orient with no project)
"""

from __future__ import annotations

import re as _re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from lexibrary.cli import lexi_app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_project(tmp_path: Path) -> Path:
    """Create a minimal initialized project."""
    (tmp_path / ".lexibrary").mkdir()
    (tmp_path / ".lexibrary" / "config.yaml").write_text("")
    (tmp_path / "src").mkdir()
    return tmp_path


def _setup_iwh_project(tmp_path: Path, *, enabled: bool = True) -> Path:
    """Create a project with IWH config."""
    (tmp_path / ".lexibrary").mkdir()
    val = "true" if enabled else "false"
    (tmp_path / ".lexibrary" / "config.yaml").write_text(f"iwh:\n  enabled: {val}\n")
    (tmp_path / "src").mkdir()
    return tmp_path


def _create_stack_post(
    tmp_path: Path,
    post_id: str = "ST-001",
    title: str = "Test issue",
    tags: list[str] | None = None,
    status: str = "open",
    votes: int = 0,
    last_vote_at: str | None = None,
) -> Path:
    """Create a stack post file for testing."""
    resolved_tags = tags or ["test"]
    title_slug = _re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:50]
    filename = f"{post_id}-{title_slug}.md"
    stack_dir = tmp_path / ".lexibrary" / "stack"
    stack_dir.mkdir(parents=True, exist_ok=True)
    post_path = stack_dir / filename

    fm_data: dict[str, object] = {
        "id": post_id,
        "title": title,
        "tags": resolved_tags,
        "status": status,
        "created": "2026-01-15",
        "author": "tester",
        "votes": votes,
        "duplicate_of": None,
        "refs": {"concepts": [], "files": [], "designs": []},
    }
    if last_vote_at is not None:
        fm_data["last_vote_at"] = last_vote_at

    fm_str = yaml.dump(fm_data, default_flow_style=False, sort_keys=False).rstrip("\n")
    content = f"---\n{fm_str}\n---\n\n## Problem\n\nTest problem.\n"
    post_path.write_text(content, encoding="utf-8")
    return post_path


def _create_stack_post_with_finding(
    tmp_path: Path,
    post_id: str = "ST-001",
    title: str = "Test issue",
    finding_body: str = "A finding.",
    last_vote_at: str | None = None,
) -> Path:
    """Create a stack post with one finding for testing."""
    post_path = _create_stack_post(
        tmp_path, post_id=post_id, title=title, last_vote_at=last_vote_at
    )
    content = post_path.read_text(encoding="utf-8")
    finding_section = (
        "\n## Findings\n\n"
        "### F1\n"
        "date: 2026-01-15\n"
        "author: tester\n"
        "votes: 0\n"
        "accepted: false\n\n"
        f"{finding_body}\n"
    )
    post_path.write_text(content + finding_section, encoding="utf-8")
    return post_path


# ---------------------------------------------------------------------------
# 7.1: IWH disabled exit code tests
# ---------------------------------------------------------------------------


class TestIWHDisabledExitCode:
    """IWH commands should exit with code 2 when IWH is disabled."""

    def test_iwh_write_exits_2_when_disabled(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_iwh_project(tmp_path, enabled=False)
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(
            lexi_app, ["iwh", "write", "--scope", "incomplete", "--body", "test"]
        )
        assert result.exit_code == 2
        assert "disabled" in result.output

    def test_iwh_read_exits_2_when_disabled(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_iwh_project(tmp_path, enabled=False)
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(lexi_app, ["iwh", "read"])
        assert result.exit_code == 2
        assert "disabled" in result.output

    def test_iwh_list_exits_2_when_disabled(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_iwh_project(tmp_path, enabled=False)
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(lexi_app, ["iwh", "list"])
        assert result.exit_code == 2
        assert "disabled" in result.output


# ---------------------------------------------------------------------------
# 7.2: _require_post helper tests
# ---------------------------------------------------------------------------


class TestRequirePost:
    """The _require_post helper should exit 1 with hint on missing post."""

    def test_missing_post_exits_1_with_hint(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(
            lexi_app, ["stack", "view", "ST-999"]
        )
        assert result.exit_code == 1
        assert "Post not found: ST-999" in result.output
        assert "lexi search --type stack" in result.output

    def test_missing_post_finding_exits_1_with_hint(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(
            lexi_app, ["stack", "finding", "ST-999", "--body", "test"]
        )
        assert result.exit_code == 1
        assert "Post not found" in result.output
        assert "lexi search --type stack" in result.output

    def test_missing_post_vote_exits_1_with_hint(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(
            lexi_app, ["stack", "vote", "ST-999", "up"]
        )
        assert result.exit_code == 1
        assert "Post not found" in result.output
        assert "lexi search --type stack" in result.output


# ---------------------------------------------------------------------------
# 7.3: Recovery hints tests
# ---------------------------------------------------------------------------


class TestRecoveryHints:
    """Error messages should include actionable recovery hints."""

    def test_concept_link_file_not_found_has_hint(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _setup_project(tmp_path)
        # Create a concept so the slug lookup passes
        concepts_dir = project / ".lexibrary" / "concepts"
        concepts_dir.mkdir(parents=True, exist_ok=True)
        (concepts_dir / "test-concept.md").write_text(
            "---\ntitle: Test Concept\nstatus: active\ntags: []\n---\n\nA concept.\n"
        )
        monkeypatch.chdir(project)
        result = runner.invoke(
            lexi_app, ["concept", "link", "test-concept", "nonexistent.py"]
        )
        assert result.exit_code == 1
        assert "Source file not found" in result.output
        assert "Hint:" in result.output

    def test_convention_not_found_has_hint(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _setup_project(tmp_path)
        (project / ".lexibrary" / "conventions").mkdir(parents=True, exist_ok=True)
        monkeypatch.chdir(project)
        result = runner.invoke(
            lexi_app, ["convention", "approve", "nonexistent-convention"]
        )
        assert result.exit_code == 1
        assert "Convention not found" in result.output
        assert "lexi search --type convention" in result.output


# ---------------------------------------------------------------------------
# 7.4: Vote rate-limiting tests
# ---------------------------------------------------------------------------


class TestVoteRateLimiting:
    """Votes should be rate-limited with a 60-second cooldown."""

    def test_vote_succeeds_without_prior_vote(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _setup_project(tmp_path)
        _create_stack_post(project, post_id="ST-001")
        monkeypatch.chdir(project)
        result = runner.invoke(
            lexi_app, ["stack", "vote", "ST-001", "up"]
        )
        assert result.exit_code == 0
        assert "Recorded upvote" in result.output

    def test_vote_rate_limited_within_60s(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _setup_project(tmp_path)
        # Set last_vote_at to 10 seconds ago
        recent_vote = (datetime.now(tz=UTC) - timedelta(seconds=10)).isoformat()
        _create_stack_post(project, post_id="ST-001", last_vote_at=recent_vote)
        monkeypatch.chdir(project)
        result = runner.invoke(
            lexi_app, ["stack", "vote", "ST-001", "up"]
        )
        assert result.exit_code == 1
        assert "rate-limited" in result.output

    def test_vote_succeeds_after_cooldown(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _setup_project(tmp_path)
        # Set last_vote_at to 120 seconds ago (well past cooldown)
        old_vote = (datetime.now(tz=UTC) - timedelta(seconds=120)).isoformat()
        _create_stack_post(project, post_id="ST-001", last_vote_at=old_vote)
        monkeypatch.chdir(project)
        result = runner.invoke(
            lexi_app, ["stack", "vote", "ST-001", "up"]
        )
        assert result.exit_code == 0
        assert "Recorded upvote" in result.output

    def test_vote_sets_last_vote_at(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _setup_project(tmp_path)
        post_path = _create_stack_post(project, post_id="ST-001")
        monkeypatch.chdir(project)

        result = runner.invoke(
            lexi_app, ["stack", "vote", "ST-001", "up"]
        )
        assert result.exit_code == 0

        # Verify last_vote_at was written to the post
        content = post_path.read_text(encoding="utf-8")
        assert "last_vote_at" in content


# ---------------------------------------------------------------------------
# 7.5: Silent-exit path tests
# ---------------------------------------------------------------------------


class TestSilentExitPaths:
    """Previously silent exit paths should now emit informational messages."""

    def test_orient_no_project_emits_message(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(lexi_app, ["orient"])
        assert result.exit_code == 0
        assert "No .lexibrary/" in result.output
