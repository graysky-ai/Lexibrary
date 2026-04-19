"""CLI parity tests for ``lexi playbook verify``.

These tests assert that the CLI command delegates the ``last_verified``
frontmatter stamp to the
:func:`lexibrary.lifecycle.refresh.refresh_playbook_staleness` helper with
the expected arguments. The end-to-end behavioural tests for the same
command live at ``tests/test_playbook_cli.py::TestPlaybookVerify`` and serve
as the byte-identical-output ground truth.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from lexibrary.cli.lexi_app import lexi_app

runner = CliRunner()


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


def _setup_project(tmp_path: Path) -> Path:
    """Create a minimal initialized project."""
    (tmp_path / ".lexibrary").mkdir()
    (tmp_path / ".lexibrary" / "config.yaml").write_text("")
    return tmp_path


def _write_playbook(tmp_path: Path, slug: str, content: str) -> Path:
    playbooks_dir = tmp_path / ".lexibrary" / "playbooks"
    playbooks_dir.mkdir(parents=True, exist_ok=True)
    pb_path = playbooks_dir / f"{slug}.md"
    pb_path.write_text(content, encoding="utf-8")
    return pb_path


class TestPlaybookVerifyCLIParity:
    """Verify the CLI command delegates to the lifecycle helper."""

    def test_cli_calls_refresh_playbook_staleness(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The CLI forwards the resolved path to the refresh helper."""
        _setup_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        pb_path = _write_playbook(tmp_path, "version-bump", DRAFT_PLAYBOOK)

        with patch("lexibrary.lifecycle.refresh.refresh_playbook_staleness") as mock_helper:
            result = runner.invoke(lexi_app, ["playbook", "verify", "version-bump"])

        assert result.exit_code == 0
        mock_helper.assert_called_once()
        call_args = mock_helper.call_args.args
        # First positional arg: the playbook path
        assert call_args[0] == pb_path

    def test_cli_does_not_call_helper_when_playbook_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Missing playbook file short-circuits before the helper runs."""
        _setup_project(tmp_path)
        monkeypatch.chdir(tmp_path)

        with patch("lexibrary.lifecycle.refresh.refresh_playbook_staleness") as mock_helper:
            result = runner.invoke(lexi_app, ["playbook", "verify", "nonexistent"])

        assert result.exit_code == 1
        assert "not found" in result.output.lower()
        mock_helper.assert_not_called()
