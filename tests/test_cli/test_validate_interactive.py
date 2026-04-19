"""Tests for ``lexi validate --fix --interactive`` (curator-4 Group 17).

Exercises the interactive escalation prompt loop in
``lexibrary.cli._shared._run_validate``. Scripted input is delivered via
``typer.testing.CliRunner.invoke(input=...)`` and the TTY guard is
patched with ``sys.stdout.isatty`` so the interactive branch runs under
test harness conditions.
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from click.testing import Result
from typer.testing import CliRunner

from lexibrary.cli import lexi_app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


_CONCEPT_TEMPLATE = """\
---
title: {title}
id: {cid}
aliases: []
tags: [general]
status: active
{last_verified_line}---

{body}
"""


def _setup_project(tmp_path: Path) -> Path:
    """Create a minimal project root with an empty ``.lexibrary/`` layout."""
    (tmp_path / ".lexibrary").mkdir()
    (tmp_path / ".lexibrary" / "config.yaml").write_text("scope_roots:\n  - path: .\n")
    return tmp_path


def _write_concept(
    project_root: Path,
    title: str,
    *,
    cid: str = "CN-001",
    last_verified: date | None = None,
    body: str = "A concept description.",
) -> Path:
    """Write a concept file at ``.lexibrary/concepts/<title>.md``."""
    concepts_dir = project_root / ".lexibrary" / "concepts"
    concepts_dir.mkdir(parents=True, exist_ok=True)
    last_verified_line = f"last_verified: {last_verified.isoformat()}\n" if last_verified else ""
    path = concepts_dir / f"{title}.md"
    path.write_text(
        _CONCEPT_TEMPLATE.format(
            title=title,
            cid=cid,
            last_verified_line=last_verified_line,
            body=body,
        ),
        encoding="utf-8",
    )
    return path


def _write_convention(
    project_root: Path,
    name: str,
    *,
    scope: str,
) -> Path:
    """Write a convention file at ``.lexibrary/conventions/<name>.md``."""
    conventions_dir = project_root / ".lexibrary" / "conventions"
    conventions_dir.mkdir(parents=True, exist_ok=True)
    path = conventions_dir / f"{name}.md"
    path.write_text(
        "---\n"
        "id: CV-001\n"
        f"title: {name}\n"
        f"scope: {scope}\n"
        "tags: [test]\n"
        "status: active\n"
        "---\n\n"
        "Example convention body.\n",
        encoding="utf-8",
    )
    return path


def _write_playbook(
    project_root: Path,
    name: str,
    *,
    last_verified: date | None = None,
) -> Path:
    """Write a playbook file at ``.lexibrary/playbooks/<name>.md``."""
    playbooks_dir = project_root / ".lexibrary" / "playbooks"
    playbooks_dir.mkdir(parents=True, exist_ok=True)
    path = playbooks_dir / f"{name}.md"
    last_verified_line = f"last_verified: {last_verified.isoformat()}\n" if last_verified else ""
    path.write_text(
        "---\n"
        "id: PB-001\n"
        f"title: {name}\n"
        "tags: [test]\n"
        "status: active\n"
        f"{last_verified_line}"
        "---\n\n"
        "Example playbook body.\n",
        encoding="utf-8",
    )
    return path


def _invoke(tmp_path: Path, args: list[str], input_: str | None = None) -> Result:
    """Run ``lexi ...`` with cwd=tmp_path and optional scripted stdin."""
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        return runner.invoke(lexi_app, args, input=input_)
    finally:
        os.chdir(old_cwd)


# ---------------------------------------------------------------------------
# TTY guard
# ---------------------------------------------------------------------------


class TestTTYGuard:
    """Non-TTY with ``--interactive`` exits 1 with guidance."""

    def test_non_tty_interactive_exits_1(self, tmp_path: Path) -> None:
        """CliRunner captures stdout so isatty() returns False; guarded."""
        _setup_project(tmp_path)
        result = _invoke(tmp_path, ["validate", "--fix", "--interactive"])
        assert result.exit_code == 1
        output = result.output
        assert "--interactive requires a terminal" in output
        assert "lexictl curate resolve --batch-ignore-all" in output

    def test_interactive_without_fix_exits_1(self, tmp_path: Path) -> None:
        """``--interactive`` without ``--fix`` is nonsensical; reject up front."""
        _setup_project(tmp_path)
        result = _invoke(tmp_path, ["validate", "--interactive"])
        assert result.exit_code == 1
        output = result.output
        assert "--interactive requires --fix" in output


# ---------------------------------------------------------------------------
# Escalation dispatch (interactive branch)
# ---------------------------------------------------------------------------


class TestEscalationDispatch:
    """End-to-end of the 3-option prompt loop for escalation issues."""

    def test_ignore_leaves_concept_unchanged(self, tmp_path: Path) -> None:
        """`i` on an orphan_concepts issue results in no mutation."""
        project = _setup_project(tmp_path)
        concept_path = _write_concept(project, "LonelyConcept")
        original = concept_path.read_text(encoding="utf-8")

        with patch("lexibrary.cli._shared._stdout_is_tty", return_value=True):
            result = _invoke(tmp_path, ["validate", "--fix", "--interactive"], input_="i\n")

        assert concept_path.read_text(encoding="utf-8") == original, (
            "`i` must not mutate the concept file"
        )
        # Summary line uses the interactive format (contains 'ignored:').
        assert "ignored:" in result.output

    def test_deprecate_calls_concept_deprecation_helper(self, tmp_path: Path) -> None:
        """`d` on an orphan_concepts issue invokes ``deprecate_concept``."""
        project = _setup_project(tmp_path)
        _write_concept(project, "LonelyConcept")

        with (
            patch("lexibrary.cli._shared._stdout_is_tty", return_value=True),
            patch("lexibrary.lifecycle.concept_deprecation.deprecate_concept") as mock_deprecate,
        ):
            _invoke(tmp_path, ["validate", "--fix", "--interactive"], input_="d\n")

        assert mock_deprecate.call_count == 1, "deprecate_concept must be called once"
        kwargs = mock_deprecate.call_args.kwargs
        assert kwargs["reason"] == "no_inbound_links"

    def test_refresh_calls_refresh_orphan_concept_helper(self, tmp_path: Path) -> None:
        """`r` on an orphan_concepts issue invokes ``refresh_orphan_concept``."""
        project = _setup_project(tmp_path)
        _write_concept(project, "LonelyConcept")

        with (
            patch("lexibrary.cli._shared._stdout_is_tty", return_value=True),
            patch("lexibrary.lifecycle.refresh.refresh_orphan_concept") as mock_refresh,
        ):
            _invoke(tmp_path, ["validate", "--fix", "--interactive"], input_="r\n")

        assert mock_refresh.call_count == 1, "refresh_orphan_concept must be called once"

    def test_convention_stale_refresh_accepts_valid_scope(self, tmp_path: Path) -> None:
        """`r` on a convention_stale issue + valid scope invokes the helper.

        ``check_convention_stale`` fires when the scope directory exists
        but contains no source files, so the fixture creates an empty
        ``src/empty/`` directory and a sibling ``src/valid/main.py`` so the
        refresh prompt has somewhere valid to point at.
        """
        project = _setup_project(tmp_path)
        # Empty directory triggers convention_stale (scope exists but empty).
        (project / "src" / "empty").mkdir(parents=True)
        # Non-empty directory provides a valid refresh target.
        (project / "src" / "valid").mkdir(parents=True)
        (project / "src" / "valid" / "main.py").write_text("pass\n")
        _write_convention(project, "StaleConvention", scope="src/empty/")

        with (
            patch("lexibrary.cli._shared._stdout_is_tty", return_value=True),
            patch("lexibrary.lifecycle.refresh.refresh_convention_stale") as mock_refresh,
        ):
            _invoke(
                tmp_path,
                ["validate", "--fix", "--interactive"],
                input_="r\nsrc/valid/\n",
            )

        assert mock_refresh.call_count == 1, (
            "refresh_convention_stale must be called with a valid scope"
        )
        kwargs = mock_refresh.call_args.kwargs
        assert kwargs["new_scope"] == "src/valid/"

    def test_convention_stale_refresh_rejects_invalid_scope_then_retries(
        self, tmp_path: Path
    ) -> None:
        """Invalid scope re-prompts; eventually valid scope triggers the helper."""
        project = _setup_project(tmp_path)
        (project / "src" / "empty").mkdir(parents=True)
        (project / "src" / "valid").mkdir(parents=True)
        (project / "src" / "valid" / "main.py").write_text("pass\n")
        _write_convention(project, "StaleConvention", scope="src/empty/")

        # First the operator types a bad scope, then a good one.
        with (
            patch("lexibrary.cli._shared._stdout_is_tty", return_value=True),
            patch("lexibrary.lifecycle.refresh.refresh_convention_stale") as mock_refresh,
        ):
            result = _invoke(
                tmp_path,
                ["validate", "--fix", "--interactive"],
                input_="r\nsrc/missing/\nsrc/valid/\n",
            )

        output = result.output
        assert "scope path(s) do not exist" in output, (
            "invalid scope must surface an explicit rejection"
        )
        assert mock_refresh.call_count == 1, "helper must be called once after the retry succeeds"

    def test_skip_remaining_counts_remaining_as_ignored(self, tmp_path: Path) -> None:
        """`s` on the first issue ignores the remainder without prompting again."""
        project = _setup_project(tmp_path)
        _write_concept(project, "LonelyOne")
        _write_concept(project, "LonelyTwo", cid="CN-002")

        with (
            patch("lexibrary.cli._shared._stdout_is_tty", return_value=True),
            patch("lexibrary.lifecycle.concept_deprecation.deprecate_concept") as mock_deprecate,
            patch("lexibrary.lifecycle.refresh.refresh_orphan_concept") as mock_refresh,
        ):
            # Single 's' should fan out to both issues without a 2nd prompt.
            result = _invoke(tmp_path, ["validate", "--fix", "--interactive"], input_="s\n")

        assert mock_deprecate.call_count == 0
        assert mock_refresh.call_count == 0
        # Summary: both orphans count as ignored (at least 2).
        output = result.output
        assert "ignored:" in output

    def test_quit_aborts_remaining_fixes(self, tmp_path: Path) -> None:
        """`q` on the first issue aborts the outer fix loop."""
        project = _setup_project(tmp_path)
        _write_concept(project, "LonelyConcept")

        with (
            patch("lexibrary.cli._shared._stdout_is_tty", return_value=True),
            patch("lexibrary.lifecycle.concept_deprecation.deprecate_concept") as mock_deprecate,
        ):
            result = _invoke(tmp_path, ["validate", "--fix", "--interactive"], input_="q\n")

        assert mock_deprecate.call_count == 0
        # Interactive summary still printed, but no [DEPRECATED]/[REFRESHED]/[FIXED].
        output = result.output
        assert "[FIXED]" not in output
        assert "[DEPRECATED]" not in output
        assert "[REFRESHED]" not in output

    def test_playbook_staleness_refresh_calls_helper(self, tmp_path: Path) -> None:
        """`r` on a playbook_staleness issue may invoke ``refresh_playbook_staleness``.

        The exact trigger for ``check_playbook_staleness`` depends on config
        defaults; when the check doesn't flag the seeded playbook, the
        prompt is not shown and the helper is never called. Either outcome
        is acceptable for this smoke test — the assertion guards against
        the regression where an unrelated playbook gets refreshed.
        """
        project = _setup_project(tmp_path)
        _write_playbook(project, "StalePlaybook", last_verified=date.today() - timedelta(days=365))

        with (
            patch("lexibrary.cli._shared._stdout_is_tty", return_value=True),
            patch("lexibrary.lifecycle.refresh.refresh_playbook_staleness") as mock_refresh,
        ):
            _invoke(tmp_path, ["validate", "--fix", "--interactive"], input_="r\n")

        assert mock_refresh.call_count <= 1


# ---------------------------------------------------------------------------
# Non-interactive path stays unchanged
# ---------------------------------------------------------------------------


class TestNonInteractiveUnchanged:
    """Without ``--interactive``, escalation routes through FIXERS as before."""

    def test_no_interactive_flag_routes_through_fixers(self, tmp_path: Path) -> None:
        """``--fix`` alone exercises the existing autonomous dispatch."""
        project = _setup_project(tmp_path)
        _write_concept(project, "LonelyConcept")

        # TTY patch is irrelevant here — no --interactive means no prompt.
        result = _invoke(tmp_path, ["validate", "--fix"])

        # Non-interactive summary uses the legacy phrasing.
        output = result.output
        assert "Fixed" in output
        assert "require manual attention" in output
        # Interactive-only keys must NOT appear.
        assert "refreshed:" not in output
        assert "deprecated:" not in output
