"""CLI parity tests for ``lexi playbook deprecate``.

These tests assert that the CLI command delegates the frontmatter +
body-note mutation to the :func:`lexibrary.lifecycle.playbook_deprecation
.deprecate_playbook` helper with the expected arguments. The
end-to-end behavioural tests for the same command live at
``tests/test_playbook_cli.py::TestPlaybookDeprecate`` and serve as the
byte-identical-output ground truth.
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


class TestPlaybookDeprecateCLIParity:
    """Verify the CLI command delegates to the lifecycle helper."""

    def test_cli_calls_deprecate_playbook_with_reason(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``--reason`` is forwarded verbatim to the helper."""
        _setup_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        pb_path = _write_playbook(tmp_path, "version-bump", DRAFT_PLAYBOOK)

        with patch("lexibrary.lifecycle.playbook_deprecation.deprecate_playbook") as mock_helper:
            result = runner.invoke(
                lexi_app,
                [
                    "playbook",
                    "deprecate",
                    "version-bump",
                    "--reason",
                    "Replaced by new process",
                ],
            )

        assert result.exit_code == 0
        mock_helper.assert_called_once()
        call_kwargs = mock_helper.call_args.kwargs
        call_args = mock_helper.call_args.args
        # First positional arg: the playbook path
        assert call_args[0] == pb_path
        # Keyword args: reason + superseded_by (None)
        assert call_kwargs["reason"] == "Replaced by new process"
        assert call_kwargs["superseded_by"] is None

    def test_cli_calls_deprecate_playbook_with_superseded_by(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``--superseded-by`` is forwarded to the helper."""
        _setup_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        pb_path = _write_playbook(tmp_path, "old-bump", DRAFT_PLAYBOOK)

        with patch("lexibrary.lifecycle.playbook_deprecation.deprecate_playbook") as mock_helper:
            result = runner.invoke(
                lexi_app,
                [
                    "playbook",
                    "deprecate",
                    "old-bump",
                    "--superseded-by",
                    "new-bump",
                    "--reason",
                    "Superseded",
                ],
            )

        assert result.exit_code == 0
        mock_helper.assert_called_once()
        call_kwargs = mock_helper.call_args.kwargs
        call_args = mock_helper.call_args.args
        assert call_args[0] == pb_path
        assert call_kwargs["reason"] == "Superseded"
        assert call_kwargs["superseded_by"] == "new-bump"

    def test_cli_supplies_default_reason_when_flag_omitted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With no ``--reason`` flag, the CLI still calls the helper with
        a non-None reason (the helper requires one).
        """
        _setup_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        _write_playbook(tmp_path, "solo", DRAFT_PLAYBOOK)

        with patch("lexibrary.lifecycle.playbook_deprecation.deprecate_playbook") as mock_helper:
            result = runner.invoke(lexi_app, ["playbook", "deprecate", "solo"])

        assert result.exit_code == 0
        mock_helper.assert_called_once()
        call_kwargs = mock_helper.call_args.kwargs
        # Helper signature requires ``reason`` — CLI must supply a non-None value.
        assert call_kwargs["reason"] is not None
        assert isinstance(call_kwargs["reason"], str)
        assert call_kwargs["superseded_by"] is None

    def test_cli_does_not_call_helper_when_already_deprecated(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The CLI pre-check short-circuits before invoking the helper so
        users see the familiar error exit rather than a silent no-op.
        """
        _setup_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        _write_playbook(
            tmp_path,
            "already",
            (
                "---\n"
                "title: Already\n"
                "id: PB-007\n"
                "trigger_files: []\n"
                "tags: []\n"
                "status: deprecated\n"
                "source: user\n"
                "deprecated_at: '2025-01-01T00:00:00+00:00'\n"
                "---\n\nSome body.\n"
            ),
        )

        with patch("lexibrary.lifecycle.playbook_deprecation.deprecate_playbook") as mock_helper:
            result = runner.invoke(lexi_app, ["playbook", "deprecate", "already"])

        assert result.exit_code == 1
        assert "deprecated" in result.output.lower()
        mock_helper.assert_not_called()

    def test_cli_does_not_call_helper_when_playbook_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Missing playbook file short-circuits before the helper runs."""
        _setup_project(tmp_path)
        monkeypatch.chdir(tmp_path)

        with patch("lexibrary.lifecycle.playbook_deprecation.deprecate_playbook") as mock_helper:
            result = runner.invoke(lexi_app, ["playbook", "deprecate", "nonexistent"])

        assert result.exit_code == 1
        assert "not found" in result.output.lower()
        mock_helper.assert_not_called()
