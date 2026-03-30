"""Tests for playbook CLI commands — new, approve, verify, deprecate, comment."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from lexibrary.cli.lexi_app import lexi_app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_project(tmp_path: Path) -> Path:
    """Create a minimal initialized project."""
    (tmp_path / ".lexibrary").mkdir()
    (tmp_path / ".lexibrary" / "config.yaml").write_text("")
    return tmp_path


def _write_playbook(tmp_path: Path, slug: str, content: str) -> Path:
    """Write a playbook file to the playbooks directory."""
    playbooks_dir = tmp_path / ".lexibrary" / "playbooks"
    playbooks_dir.mkdir(parents=True, exist_ok=True)
    pb_path = playbooks_dir / f"{slug}.md"
    pb_path.write_text(content, encoding="utf-8")
    return pb_path


DRAFT_PLAYBOOK = """\
---
title: Version Bump
id: PB-001
trigger_files: [pyproject.toml]
tags: [release]
status: draft
source: user
estimated_minutes: 15
---

## Overview

Bump the version number.

## Steps

1. [ ] Update pyproject.toml
"""

ACTIVE_PLAYBOOK = """\
---
title: Deploy Service
id: PB-002
trigger_files: [Dockerfile]
tags: [deploy]
status: active
source: user
---

## Overview

Deploy the service.
"""

DEPRECATED_PLAYBOOK = """\
---
title: Old Process
id: PB-003
trigger_files: []
tags: []
status: deprecated
source: user
deprecated_at: '2025-01-01T00:00:00+00:00'
---

Old deprecated playbook.
"""


# ---------------------------------------------------------------------------
# playbook new
# ---------------------------------------------------------------------------


class TestPlaybookNew:
    """Tests for `lexi playbook new`."""

    def test_new_creates_playbook(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _setup_project(tmp_path)
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(
            lexi_app,
            ["playbook", "new", "Version Bump"],
        )
        assert result.exit_code == 0
        assert "Created" in result.output

        # ID-prefixed filename: PB-001-version-bump.md
        pb_path = tmp_path / ".lexibrary" / "playbooks" / "PB-001-version-bump.md"
        assert pb_path.exists()
        content = pb_path.read_text(encoding="utf-8")
        assert "title: Version Bump" in content
        assert "status: draft" in content

    def test_new_with_all_options(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _setup_project(tmp_path)
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(
            lexi_app,
            [
                "playbook",
                "new",
                "Version Bump",
                "--trigger-file",
                "pyproject.toml",
                "--trigger-file",
                "setup.cfg",
                "--tag",
                "release",
                "--tag",
                "versioning",
                "--estimated-minutes",
                "15",
            ],
        )
        assert result.exit_code == 0

        # ID-prefixed filename
        pb_path = tmp_path / ".lexibrary" / "playbooks" / "PB-001-version-bump.md"
        content = pb_path.read_text(encoding="utf-8")
        assert "pyproject.toml" in content
        assert "setup.cfg" in content
        assert "release" in content
        assert "versioning" in content
        assert "estimated_minutes: 15" in content

    def test_new_creates_directory(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _setup_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        # Ensure playbooks dir doesn't exist yet
        assert not (tmp_path / ".lexibrary" / "playbooks").exists()

        result = runner.invoke(lexi_app, ["playbook", "new", "First Playbook"])
        assert result.exit_code == 0
        assert (tmp_path / ".lexibrary" / "playbooks").is_dir()

    def test_new_duplicate_slug_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        _write_playbook(tmp_path, "version-bump", DRAFT_PLAYBOOK)

        result = runner.invoke(lexi_app, ["playbook", "new", "Version Bump"])
        assert result.exit_code == 1
        assert "already exists" in result.output


# ---------------------------------------------------------------------------
# playbook approve
# ---------------------------------------------------------------------------


class TestPlaybookApprove:
    """Tests for `lexi playbook approve`."""

    def test_approve_draft_to_active(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _setup_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        _write_playbook(tmp_path, "version-bump", DRAFT_PLAYBOOK)

        result = runner.invoke(lexi_app, ["playbook", "approve", "version-bump"])
        assert result.exit_code == 0
        assert "Approved" in result.output
        assert "active" in result.output

        # Verify file was updated
        pb_path = tmp_path / ".lexibrary" / "playbooks" / "version-bump.md"
        content = pb_path.read_text(encoding="utf-8")
        assert "status: active" in content

    def test_approve_non_draft_errors(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        _write_playbook(tmp_path, "deploy-service", ACTIVE_PLAYBOOK)

        result = runner.invoke(lexi_app, ["playbook", "approve", "deploy-service"])
        assert result.exit_code == 1
        assert "non-draft" in result.output.lower() or "Cannot approve" in result.output

    def test_approve_deprecated_errors(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        _write_playbook(tmp_path, "old-process", DEPRECATED_PLAYBOOK)

        result = runner.invoke(lexi_app, ["playbook", "approve", "old-process"])
        assert result.exit_code == 1

    def test_approve_not_found(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _setup_project(tmp_path)
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(lexi_app, ["playbook", "approve", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()


# ---------------------------------------------------------------------------
# playbook verify
# ---------------------------------------------------------------------------


class TestPlaybookVerify:
    """Tests for `lexi playbook verify`."""

    def test_verify_sets_last_verified(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from datetime import date

        _setup_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        _write_playbook(tmp_path, "version-bump", DRAFT_PLAYBOOK)

        result = runner.invoke(lexi_app, ["playbook", "verify", "version-bump"])
        assert result.exit_code == 0
        assert "Verified" in result.output

        pb_path = tmp_path / ".lexibrary" / "playbooks" / "version-bump.md"
        content = pb_path.read_text(encoding="utf-8")
        today = date.today().isoformat()
        assert today in content

    def test_verify_not_found(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _setup_project(tmp_path)
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(lexi_app, ["playbook", "verify", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()


# ---------------------------------------------------------------------------
# playbook deprecate
# ---------------------------------------------------------------------------


class TestPlaybookDeprecate:
    """Tests for `lexi playbook deprecate`."""

    def test_deprecate_sets_status(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _setup_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        _write_playbook(tmp_path, "version-bump", DRAFT_PLAYBOOK)

        result = runner.invoke(lexi_app, ["playbook", "deprecate", "version-bump"])
        assert result.exit_code == 0
        assert "Deprecated" in result.output

        pb_path = tmp_path / ".lexibrary" / "playbooks" / "version-bump.md"
        content = pb_path.read_text(encoding="utf-8")
        assert "status: deprecated" in content
        assert "deprecated_at" in content

    def test_deprecate_with_superseded_by_and_reason(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        _write_playbook(tmp_path, "old-bump", DRAFT_PLAYBOOK)

        result = runner.invoke(
            lexi_app,
            [
                "playbook",
                "deprecate",
                "old-bump",
                "--superseded-by",
                "version-bump",
                "--reason",
                "Replaced by new process",
            ],
        )
        assert result.exit_code == 0

        pb_path = tmp_path / ".lexibrary" / "playbooks" / "old-bump.md"
        content = pb_path.read_text(encoding="utf-8")
        assert "superseded_by: version-bump" in content
        assert "Replaced by new process" in content

    def test_deprecate_already_deprecated_errors(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        _write_playbook(tmp_path, "old-process", DEPRECATED_PLAYBOOK)

        result = runner.invoke(lexi_app, ["playbook", "deprecate", "old-process"])
        assert result.exit_code == 1
        assert "deprecated" in result.output.lower()

    def test_deprecate_not_found(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _setup_project(tmp_path)
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(lexi_app, ["playbook", "deprecate", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()


# ---------------------------------------------------------------------------
# playbook comment
# ---------------------------------------------------------------------------


class TestPlaybookComment:
    """Tests for `lexi playbook comment`.

    NOTE: The comment command depends on lifecycle.playbook_comments (group 6).
    These tests will pass once that module is implemented.
    """

    def test_comment_appends(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _setup_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        _write_playbook(tmp_path, "version-bump", DRAFT_PLAYBOOK)

        result = runner.invoke(
            lexi_app,
            ["playbook", "comment", "version-bump", "--body", "Verified with team"],
        )
        assert result.exit_code == 0
        assert "Comment added" in result.output

        # Verify comment file was created
        comment_path = tmp_path / ".lexibrary" / "playbooks" / "version-bump.comments.yaml"
        assert comment_path.exists()

    def test_comment_not_found(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _setup_project(tmp_path)
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(
            lexi_app,
            ["playbook", "comment", "nonexistent", "--body", "test"],
        )
        assert result.exit_code == 1
        assert "not found" in result.output.lower()
