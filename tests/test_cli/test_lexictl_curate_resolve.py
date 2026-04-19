"""Tests for ``lexictl curate resolve`` (curator-4 Group 18).

Covers the admin subcommand that replays
:attr:`CuratorReport.pending_decisions` through the shared 3-option
prompt loop (``[i]gnore [d]eprecate [r]efresh``).

Scope of this file:
* ``lexictl curate`` (no subcommand) still runs the pipeline.
* ``lexictl curate run`` runs the pipeline.
* ``lexictl curate resolve`` replays pending decisions from a fixture.
* ``--batch-ignore-all`` skips prompts and preserves IWH breadcrumbs.
* ``--report PATH`` override is respected.
* IWH signal is deleted after a successful deprecate/refresh.

The tests use ``typer.testing.CliRunner`` directly -- per the curator-4
tasks.md Note 4, agents must not invoke ``lexictl`` and therefore shelling
out to the real command is prohibited.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from lexibrary.cli import lexictl_app
from lexibrary.curator.models import CuratorReport

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _setup_project(tmp_path: Path) -> Path:
    """Create a minimal initialised project at ``tmp_path``."""
    (tmp_path / ".lexibrary").mkdir()
    (tmp_path / ".lexibrary" / "config.yaml").write_text("scope_roots:\n  - path: .\n")
    return tmp_path


_CONCEPT_TEMPLATE = """\
---
title: {title}
id: CN-001
aliases: []
tags: [general]
status: active
---

{body}
"""


def _write_concept(project_root: Path, title: str, *, body: str = "Body.") -> Path:
    """Write a concept file at ``.lexibrary/concepts/<title>.md``."""
    concepts_dir = project_root / ".lexibrary" / "concepts"
    concepts_dir.mkdir(parents=True, exist_ok=True)
    path = concepts_dir / f"{title}.md"
    path.write_text(_CONCEPT_TEMPLATE.format(title=title, body=body), encoding="utf-8")
    return path


def _write_report_with_pending(
    project_root: Path,
    *,
    pending: list[dict[str, object]],
    timestamp: str = "20260409T120000Z",
) -> Path:
    """Write a curator report JSON with ``pending_decisions`` populated."""
    reports_dir = project_root / ".lexibrary" / "curator" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_file = reports_dir / f"{timestamp}.json"
    data = {
        "schema_version": 4,
        "timestamp": timestamp,
        "trigger": "on_demand",
        "checked": 0,
        "fixed": 0,
        "stubbed": 0,
        "deferred": 0,
        "errored": 0,
        "errors": [],
        "sub_agent_calls": {},
        "dispatched": [],
        "deferred_details": [],
        "deprecated": 0,
        "hard_deleted": 0,
        "migrations_applied": 0,
        "migrations_proposed": 0,
        "budget_condensed": 0,
        "budget_proposed": 0,
        "comments_flagged": 0,
        "descriptions_audited": 0,
        "summaries_audited": 0,
        "pending_decisions": pending,
    }
    report_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return report_file


def _invoke(tmp_path: Path, args: list[str], *, input_: str | None = None) -> object:
    """Invoke the ``lexictl`` app with ``cwd`` set to the project root."""
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        return runner.invoke(lexictl_app, args, input=input_)
    finally:
        os.chdir(old_cwd)


def _make_report(
    *,
    checked: int = 5,
    fixed: int = 2,
    deferred: int = 1,
    errored: int = 0,
    sub_agent_calls: dict[str, int] | None = None,
    report_path: Path | None = None,
) -> CuratorReport:
    """Build a minimal ``CuratorReport`` for coordinator mocking."""
    return CuratorReport(
        checked=checked,
        fixed=fixed,
        deferred=deferred,
        errored=errored,
        sub_agent_calls=sub_agent_calls or {},
        report_path=report_path,
    )


# ---------------------------------------------------------------------------
# Subcommand wiring: ``lexictl curate`` and ``lexictl curate run``
# ---------------------------------------------------------------------------


class TestCurateSubAppWiring:
    """Verify the Typer sub-app preserves backward compatibility."""

    def test_lexictl_curate_no_subcommand_runs_pipeline(self, tmp_path: Path) -> None:
        """``lexictl curate`` (no subcommand) still runs the coordinator pipeline."""
        _setup_project(tmp_path)
        report = _make_report(
            report_path=tmp_path / ".lexibrary" / "curator" / "reports" / "test.json",
        )

        mock_run = AsyncMock(return_value=report)
        mock_coordinator = MagicMock()
        mock_coordinator.run = mock_run

        with patch(
            "lexibrary.curator.coordinator.Coordinator",
            return_value=mock_coordinator,
        ):
            result = _invoke(tmp_path, ["curate"])

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "Curator Run Summary" in result.output
        mock_run.assert_awaited_once()

    def test_lexictl_curate_run_also_runs_pipeline(self, tmp_path: Path) -> None:
        """``lexictl curate run`` runs the coordinator pipeline."""
        _setup_project(tmp_path)
        report = _make_report(
            report_path=tmp_path / ".lexibrary" / "curator" / "reports" / "test.json",
        )

        mock_run = AsyncMock(return_value=report)
        mock_coordinator = MagicMock()
        mock_coordinator.run = mock_run

        with patch(
            "lexibrary.curator.coordinator.Coordinator",
            return_value=mock_coordinator,
        ):
            result = _invoke(tmp_path, ["curate", "run"])

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "Curator Run Summary" in result.output
        mock_run.assert_awaited_once()

    def test_lexictl_curate_run_scope_flag_forwarded(self, tmp_path: Path) -> None:
        """``lexictl curate run --scope <dir>`` forwards ``scope`` to coordinator."""
        _setup_project(tmp_path)
        (tmp_path / "src").mkdir()
        report = _make_report()

        mock_run = AsyncMock(return_value=report)
        mock_coordinator = MagicMock()
        mock_coordinator.run = mock_run

        with patch(
            "lexibrary.curator.coordinator.Coordinator",
            return_value=mock_coordinator,
        ):
            result = _invoke(tmp_path, ["curate", "run", "--scope", "src"])

        assert result.exit_code == 0, f"Output: {result.output}"
        mock_run.assert_awaited_once()
        kwargs = mock_run.call_args.kwargs
        assert kwargs["scope"] == (tmp_path / "src").resolve()


# ---------------------------------------------------------------------------
# ``lexictl curate resolve`` -- no report / empty report
# ---------------------------------------------------------------------------


class TestResolveDegenerateCases:
    """Behaviour when there is nothing to replay."""

    def test_no_reports_dir(self, tmp_path: Path) -> None:
        """Missing reports directory exits cleanly with a hint."""
        _setup_project(tmp_path)
        result = _invoke(tmp_path, ["curate", "resolve"])
        assert result.exit_code == 0, f"Output: {result.output}"
        assert "No curator reports" in result.output

    def test_empty_reports_dir(self, tmp_path: Path) -> None:
        """Empty reports directory exits cleanly with a hint."""
        _setup_project(tmp_path)
        (tmp_path / ".lexibrary" / "curator" / "reports").mkdir(parents=True)
        result = _invoke(tmp_path, ["curate", "resolve"])
        assert result.exit_code == 0, f"Output: {result.output}"
        assert "No curator reports" in result.output

    def test_empty_pending_decisions(self, tmp_path: Path) -> None:
        """A report with no pending decisions emits the no-op message."""
        _setup_project(tmp_path)
        _write_report_with_pending(tmp_path, pending=[])
        result = _invoke(tmp_path, ["curate", "resolve"])
        assert result.exit_code == 0, f"Output: {result.output}"
        assert "No pending decisions" in result.output


# ---------------------------------------------------------------------------
# ``lexictl curate resolve`` -- replay a fixture
# ---------------------------------------------------------------------------


class TestResolveReplay:
    """End-to-end prompts against a seeded report."""

    def _seed(self, tmp_path: Path) -> tuple[Path, Path]:
        """Seed a project with one concept + a report referencing it."""
        project = _setup_project(tmp_path)
        concept_path = _write_concept(project, "LonelyConcept")
        iwh_path = project / ".lexibrary" / "designs" / "LonelyConcept.iwh"
        iwh_path.parent.mkdir(parents=True, exist_ok=True)
        iwh_path.write_text("scope: escalation\n---\npending decision", encoding="utf-8")

        _write_report_with_pending(
            project,
            pending=[
                {
                    "check": "orphan_concepts",
                    "path": str(concept_path),
                    "message": "concept has zero inbound link-graph references",
                    "suggested_actions": ["ignore", "deprecate", "refresh"],
                    "iwh_path": str(iwh_path),
                }
            ],
        )
        return concept_path, iwh_path

    def test_resolve_ignore_leaves_artifact_untouched(self, tmp_path: Path) -> None:
        """Typing ``i`` on a replayed decision does not mutate the concept."""
        concept_path, _iwh_path = self._seed(tmp_path)
        original = concept_path.read_text(encoding="utf-8")

        result = _invoke(tmp_path, ["curate", "resolve"], input_="i\n")

        assert result.exit_code == 0, f"Output: {result.output}"
        assert concept_path.read_text(encoding="utf-8") == original
        assert "resolved: 1/1" in result.output
        assert "ignored: 1" in result.output

    def test_resolve_deprecate_invokes_helper(self, tmp_path: Path) -> None:
        """Typing ``d`` invokes ``deprecate_concept`` with the canonical reason."""
        concept_path, _iwh_path = self._seed(tmp_path)

        with patch("lexibrary.lifecycle.concept_deprecation.deprecate_concept") as mock_deprecate:
            result = _invoke(tmp_path, ["curate", "resolve"], input_="d\n")

        assert result.exit_code == 0, f"Output: {result.output}"
        mock_deprecate.assert_called_once()
        kwargs = mock_deprecate.call_args.kwargs
        assert kwargs["reason"] == "no_inbound_links"
        # Positional args carry the resolved concept path.
        assert mock_deprecate.call_args.args[0] == concept_path

    def test_resolve_refresh_invokes_helper(self, tmp_path: Path) -> None:
        """Typing ``r`` invokes ``refresh_orphan_concept``."""
        self._seed(tmp_path)

        with patch("lexibrary.lifecycle.refresh.refresh_orphan_concept") as mock_refresh:
            result = _invoke(tmp_path, ["curate", "resolve"], input_="r\n")

        assert result.exit_code == 0, f"Output: {result.output}"
        mock_refresh.assert_called_once()


# ---------------------------------------------------------------------------
# ``--batch-ignore-all``
# ---------------------------------------------------------------------------


class TestBatchIgnoreAll:
    """CI path that skips prompts and preserves IWH breadcrumbs."""

    def test_batch_ignore_all_skips_prompts(self, tmp_path: Path) -> None:
        """``--batch-ignore-all`` resolves without consuming stdin."""
        project = _setup_project(tmp_path)
        concept_path = _write_concept(project, "LonelyConcept")

        _write_report_with_pending(
            project,
            pending=[
                {
                    "check": "orphan_concepts",
                    "path": str(concept_path),
                    "message": "msg",
                    "suggested_actions": ["ignore", "deprecate", "refresh"],
                    "iwh_path": None,
                }
            ],
        )

        # No stdin supplied intentionally -- ``--batch-ignore-all`` must not
        # prompt. If the code tries to read stdin, typer.prompt raises.
        result = _invoke(tmp_path, ["curate", "resolve", "--batch-ignore-all"])

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "batch-ignore-all" in result.output
        assert "resolved: 1/1" in result.output
        assert "ignored: 1" in result.output

    def test_batch_ignore_all_preserves_iwh(self, tmp_path: Path) -> None:
        """``--batch-ignore-all`` does NOT delete the IWH breadcrumb."""
        project = _setup_project(tmp_path)
        concept_path = _write_concept(project, "LonelyConcept")
        iwh_path = project / ".lexibrary" / "designs" / "LonelyConcept.iwh"
        iwh_path.parent.mkdir(parents=True, exist_ok=True)
        iwh_path.write_text("scope: escalation\n---\npending", encoding="utf-8")

        _write_report_with_pending(
            project,
            pending=[
                {
                    "check": "orphan_concepts",
                    "path": str(concept_path),
                    "message": "msg",
                    "suggested_actions": ["ignore", "deprecate", "refresh"],
                    "iwh_path": str(iwh_path),
                }
            ],
        )

        result = _invoke(tmp_path, ["curate", "resolve", "--batch-ignore-all"])
        assert result.exit_code == 0, f"Output: {result.output}"
        assert iwh_path.exists(), "IWH breadcrumb MUST survive batch-ignore-all"


# ---------------------------------------------------------------------------
# ``--report <path>``
# ---------------------------------------------------------------------------


class TestReportOverride:
    """``--report`` selects an explicit file instead of the latest."""

    def test_report_override_respected(self, tmp_path: Path) -> None:
        """``--report OLDER`` picks the older file even when a newer exists."""
        project = _setup_project(tmp_path)
        concept_path = _write_concept(project, "LonelyOlder")

        older = _write_report_with_pending(
            project,
            pending=[
                {
                    "check": "orphan_concepts",
                    "path": str(concept_path),
                    "message": "from older report",
                    "suggested_actions": ["ignore", "deprecate", "refresh"],
                    "iwh_path": None,
                }
            ],
            timestamp="20260101T000000Z",
        )
        # Newer report has a different pending decision with an
        # identifiable message; the override should bypass it.
        _write_report_with_pending(
            project,
            pending=[
                {
                    "check": "orphan_concepts",
                    "path": str(concept_path),
                    "message": "from newer report",
                    "suggested_actions": ["ignore", "deprecate", "refresh"],
                    "iwh_path": None,
                }
            ],
            timestamp="20260410T000000Z",
        )

        result = _invoke(
            tmp_path,
            ["curate", "resolve", "--report", str(older), "--batch-ignore-all"],
        )
        assert result.exit_code == 0, f"Output: {result.output}"
        assert "from older report" in result.output
        assert "from newer report" not in result.output

    def test_report_override_missing_file_errors(self, tmp_path: Path) -> None:
        """``--report NONEXISTENT`` exits 1 with an actionable error."""
        _setup_project(tmp_path)
        result = _invoke(
            tmp_path,
            ["curate", "resolve", "--report", str(tmp_path / "does-not-exist.json")],
        )
        assert result.exit_code == 1, f"Output: {result.output}"
        assert "not found" in result.output.lower()


# ---------------------------------------------------------------------------
# IWH breadcrumb cleanup
# ---------------------------------------------------------------------------


class TestIwhCleanup:
    """Breadcrumb should be removed after a successful resolve."""

    def test_iwh_deleted_after_refresh(self, tmp_path: Path) -> None:
        """Interactive refresh deletes the matching IWH file."""
        project = _setup_project(tmp_path)
        concept_path = _write_concept(project, "LonelyConcept")
        iwh_path = project / ".lexibrary" / "designs" / "LonelyConcept.iwh"
        iwh_path.parent.mkdir(parents=True, exist_ok=True)
        iwh_path.write_text("scope: escalation\n---\npending", encoding="utf-8")

        _write_report_with_pending(
            project,
            pending=[
                {
                    "check": "orphan_concepts",
                    "path": str(concept_path),
                    "message": "msg",
                    "suggested_actions": ["ignore", "deprecate", "refresh"],
                    "iwh_path": str(iwh_path),
                }
            ],
        )

        with patch("lexibrary.lifecycle.refresh.refresh_orphan_concept"):
            result = _invoke(tmp_path, ["curate", "resolve"], input_="r\n")

        assert result.exit_code == 0, f"Output: {result.output}"
        assert not iwh_path.exists(), (
            "IWH breadcrumb MUST be deleted after a successful interactive refresh"
        )

    def test_iwh_deleted_after_deprecate(self, tmp_path: Path) -> None:
        """Interactive deprecate deletes the matching IWH file."""
        project = _setup_project(tmp_path)
        concept_path = _write_concept(project, "LonelyConcept")
        iwh_path = project / ".lexibrary" / "designs" / "LonelyConcept.iwh"
        iwh_path.parent.mkdir(parents=True, exist_ok=True)
        iwh_path.write_text("scope: escalation\n---\npending", encoding="utf-8")

        _write_report_with_pending(
            project,
            pending=[
                {
                    "check": "orphan_concepts",
                    "path": str(concept_path),
                    "message": "msg",
                    "suggested_actions": ["ignore", "deprecate", "refresh"],
                    "iwh_path": str(iwh_path),
                }
            ],
        )

        with patch("lexibrary.lifecycle.concept_deprecation.deprecate_concept"):
            result = _invoke(tmp_path, ["curate", "resolve"], input_="d\n")

        assert result.exit_code == 0, f"Output: {result.output}"
        assert not iwh_path.exists(), (
            "IWH breadcrumb MUST be deleted after a successful interactive deprecate"
        )

    def test_iwh_survives_ignore(self, tmp_path: Path) -> None:
        """Ignoring an interactive decision preserves the IWH breadcrumb.

        The IWH file is a durable marker that the operator owes a
        decision; a mere ``i`` keypress doesn't dispose of it. Operators
        can later re-run ``lexictl curate resolve`` and see the same
        pending entry.
        """
        project = _setup_project(tmp_path)
        concept_path = _write_concept(project, "LonelyConcept")
        iwh_path = project / ".lexibrary" / "designs" / "LonelyConcept.iwh"
        iwh_path.parent.mkdir(parents=True, exist_ok=True)
        iwh_path.write_text("scope: escalation\n---\npending", encoding="utf-8")

        _write_report_with_pending(
            project,
            pending=[
                {
                    "check": "orphan_concepts",
                    "path": str(concept_path),
                    "message": "msg",
                    "suggested_actions": ["ignore", "deprecate", "refresh"],
                    "iwh_path": str(iwh_path),
                }
            ],
        )

        result = _invoke(tmp_path, ["curate", "resolve"], input_="i\n")

        assert result.exit_code == 0, f"Output: {result.output}"
        assert iwh_path.exists(), (
            "Ignored decisions MUST leave the breadcrumb on disk for later review"
        )
