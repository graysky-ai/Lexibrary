"""Tests for Phase 1 honest counters, enriched report, and collect filters.

Covers the changes introduced by openspec change ``curator-fix`` group 2:

* :class:`SubAgentResult` ``outcome`` drives ``fixed`` / ``stubbed`` counts.
* :class:`CuratorReport` carries ``schema_version``, ``stubbed``,
  ``dispatched_details``, ``deferred_details``.
* :meth:`Coordinator._report` populates the detail lists correctly.
* :meth:`Coordinator._write_report` persists the new JSON fields while
  preserving v1 keys.
* :mod:`lexibrary.services.curate_render` handles v1 and v2 reports.
* ``_should_skip_path`` skips uncommitted files and active-IWH directories.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lexibrary.config.schema import LexibraryConfig
from lexibrary.curator.collect_filters import _should_skip_path
from lexibrary.curator.coordinator import Coordinator
from lexibrary.curator.models import (
    CollectItem,
    CollectResult,
    DispatchResult,
    SubAgentResult,
    TriageItem,
    TriageResult,
)
from lexibrary.services.curate_render import render_last_run, render_summary

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_minimal_project(tmp_path: Path) -> Path:
    """Create a minimal project directory with ``.lexibrary`` structure."""
    project = tmp_path / "project"
    project.mkdir()
    (project / ".lexibrary").mkdir()
    (project / ".lexibrary" / "designs").mkdir()
    (project / ".lexibrary" / "config.yaml").write_text("", encoding="utf-8")
    return project


def _make_dispatch_result(*results: SubAgentResult) -> DispatchResult:
    return DispatchResult(dispatched=list(results))


def _make_triage_item(
    action_key: str,
    *,
    source_path: Path | None = None,
    issue_type: str = "staleness",
    check: str = "check_x",
    message: str = "planted issue",
    risk_level: str | None = "low",
) -> TriageItem:
    return TriageItem(
        source_item=CollectItem(
            source="validation",
            path=source_path,
            severity="warning",
            message=message,
            check=check,
        ),
        issue_type=issue_type,  # type: ignore[arg-type]
        action_key=action_key,
        priority=0.5,
        risk_level=risk_level,  # type: ignore[arg-type]
    )


def _coord(project: Path) -> Coordinator:
    return Coordinator(project, LexibraryConfig())


# ---------------------------------------------------------------------------
# 2.9 report tests
# ---------------------------------------------------------------------------


class TestOutcomeCounters:
    """``outcome`` field drives the honest ``fixed`` / ``stubbed`` split."""

    def test_report_excludes_stubs_from_fixed(self, tmp_path: Path) -> None:
        project = _setup_minimal_project(tmp_path)
        coord = _coord(project)

        dispatched = _make_dispatch_result(
            SubAgentResult(success=True, action_key="fix_a", outcome="fixed", message="ok"),
            SubAgentResult(
                success=True,
                action_key="stub_b",
                outcome="stubbed",
                message="stub: stub_b (risk=low)",
            ),
            SubAgentResult(
                success=True,
                action_key="stub_c",
                outcome="stubbed",
                message="stub: stub_c (risk=medium)",
            ),
        )
        triage = TriageResult(
            items=[
                _make_triage_item("fix_a"),
                _make_triage_item("stub_b"),
                _make_triage_item("stub_c"),
            ]
        )

        report = coord._report(
            CollectResult(),
            triage,
            dispatched,
            migrations_applied=0,
            migrations_proposed=0,
            trigger="on_demand",
        )

        assert report.fixed == 1
        assert report.stubbed == 2

    def test_sub_agent_result_outcome_drives_counters(self, tmp_path: Path) -> None:
        """Setting ``outcome`` — even with ``success=True`` — flips the
        count bucket."""
        project = _setup_minimal_project(tmp_path)
        coord = _coord(project)

        dispatched = _make_dispatch_result(
            SubAgentResult(success=True, action_key="a", outcome="fixed"),
            SubAgentResult(success=True, action_key="b", outcome="stubbed"),
            SubAgentResult(success=True, action_key="c", outcome="dry_run"),
            SubAgentResult(success=False, action_key="d", outcome="fixer_failed"),
            SubAgentResult(success=False, action_key="e", outcome="errored"),
        )
        triage = TriageResult(items=[_make_triage_item(k) for k in ("a", "b", "c", "d", "e")])

        report = coord._report(
            CollectResult(),
            triage,
            dispatched,
            migrations_applied=0,
            migrations_proposed=0,
            trigger="on_demand",
        )

        assert report.fixed == 1
        assert report.stubbed == 1

    def test_report_schema_version_bump(self, tmp_path: Path) -> None:
        project = _setup_minimal_project(tmp_path)
        coord = _coord(project)

        report = coord._report(
            CollectResult(),
            TriageResult(items=[]),
            _make_dispatch_result(),
            migrations_applied=0,
            migrations_proposed=0,
            trigger="on_demand",
        )

        assert report.schema_version == 4


class TestReportDetails:
    """``_report`` populates ``dispatched_details`` / ``deferred_details``."""

    def test_report_populates_dispatched_details(self, tmp_path: Path) -> None:
        project = _setup_minimal_project(tmp_path)
        coord = _coord(project)

        src = project / "src" / "foo.py"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text("pass\n", encoding="utf-8")

        dispatched = _make_dispatch_result(
            SubAgentResult(
                success=True,
                action_key="regenerate_stale_design",
                path=src,
                message="regenerated",
                llm_calls=2,
                outcome="fixed",
            )
        )
        triage = TriageResult(items=[_make_triage_item("regenerate_stale_design")])

        report = coord._report(
            CollectResult(),
            triage,
            dispatched,
            migrations_applied=0,
            migrations_proposed=0,
            trigger="on_demand",
        )

        assert len(report.dispatched_details) == 1
        entry = report.dispatched_details[0]
        assert entry["action_key"] == "regenerate_stale_design"
        assert entry["path"] == str(src)
        assert entry["message"] == "regenerated"
        assert entry["success"] is True
        assert entry["outcome"] == "fixed"
        assert entry["llm_calls"] == 2

    def test_report_populates_deferred_details(self, tmp_path: Path) -> None:
        project = _setup_minimal_project(tmp_path)
        coord = _coord(project)

        src = project / "src" / "bar.py"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text("pass\n", encoding="utf-8")

        deferred_item = _make_triage_item(
            "risky_fix",
            source_path=src,
            check="risky_check",
            message="needs review",
            risk_level="high",
        )
        dispatch = DispatchResult(deferred=[deferred_item])

        report = coord._report(
            CollectResult(),
            TriageResult(items=[]),
            dispatch,
            migrations_applied=0,
            migrations_proposed=0,
            trigger="on_demand",
        )

        assert len(report.deferred_details) == 1
        entry = report.deferred_details[0]
        assert entry["action_key"] == "risky_fix"
        assert entry["issue_type"] == "staleness"
        assert entry["path"] == str(src)
        assert entry["check"] == "risky_check"
        assert entry["message"] == "needs review"
        assert entry["risk_level"] == "high"


class TestWriteReportJson:
    """``_write_report`` persists the new fields in the JSON payload."""

    def test_write_report_json_includes_new_fields(self, tmp_path: Path) -> None:
        project = _setup_minimal_project(tmp_path)
        coord = _coord(project)

        dispatched = _make_dispatch_result(
            SubAgentResult(
                success=True,
                action_key="fix_a",
                outcome="fixed",
                message="ok",
            ),
            SubAgentResult(
                success=True,
                action_key="stub_b",
                outcome="stubbed",
                message="stub: stub_b",
            ),
        )
        triage = TriageResult(items=[_make_triage_item("fix_a"), _make_triage_item("stub_b")])

        report = coord._report(
            CollectResult(),
            triage,
            dispatched,
            migrations_applied=0,
            migrations_proposed=0,
            trigger="on_demand",
        )

        assert report.report_path is not None
        data = json.loads(report.report_path.read_text(encoding="utf-8"))

        assert data["schema_version"] == 4
        assert data["stubbed"] == 1
        assert data["fixed"] == 1
        assert data["trigger"] == "on_demand"
        assert data["checked"] == 2
        # v1 keys preserved
        assert data["deferred"] == 0
        assert data["errored"] == 0
        # New detail lists
        assert isinstance(data["dispatched"], list)
        assert len(data["dispatched"]) == 2
        assert data["dispatched"][0]["action_key"] == "fix_a"
        assert isinstance(data["deferred_details"], list)


# ---------------------------------------------------------------------------
# 2.10 rendering, CLI, and filter tests
# ---------------------------------------------------------------------------


class TestRenderSummary:
    def test_render_summary_warns_on_stubs(self) -> None:
        lines = render_summary(
            checked=5,
            fixed=2,
            deferred=0,
            errored=0,
            sub_agent_calls={},
            report_path=None,
            stubbed=3,
        )
        warns = [(lvl, msg) for lvl, msg in lines if lvl == "warn"]
        stub_lines = [msg for _lvl, msg in warns if "Stubbed" in msg]
        assert len(stub_lines) == 1
        assert "3" in stub_lines[0]

    def test_render_summary_no_warning_when_stubs_zero(self) -> None:
        lines = render_summary(
            checked=5,
            fixed=5,
            deferred=0,
            errored=0,
            sub_agent_calls={},
            report_path=None,
            stubbed=0,
        )
        assert all("Stubbed" not in msg for _lvl, msg in lines)

    def test_render_summary_verbose_lists_dispatches(self) -> None:
        details = [
            {
                "action_key": "fix_a",
                "path": "/tmp/a.py",
                "message": "ok",
                "success": True,
                "outcome": "fixed",
                "llm_calls": 0,
            },
            {
                "action_key": "stub_b",
                "path": "/tmp/b.py",
                "message": "stub: stub_b (risk=low)",
                "success": True,
                "outcome": "stubbed",
                "llm_calls": 0,
            },
        ]
        lines = render_summary(
            checked=2,
            fixed=1,
            deferred=0,
            errored=0,
            sub_agent_calls={},
            report_path=None,
            stubbed=1,
            verbose=True,
            dispatched_details=details,
        )
        messages = [msg for _lvl, msg in lines]
        assert any("[fix_a] /tmp/a.py -- ok" in m for m in messages)
        assert any("[stub_b] /tmp/b.py -- stub: stub_b" in m for m in messages)


class TestRenderLastRun:
    """``render_last_run`` handles both schema versions gracefully."""

    def _write_v2_report(self, tmp_path: Path, **overrides: object) -> Path:
        reports_dir = tmp_path / ".lexibrary" / "curator" / "reports"
        reports_dir.mkdir(parents=True)
        data: dict[str, object] = {
            "schema_version": 2,
            "timestamp": "20260411T000000Z",
            "trigger": "on_demand",
            "checked": 5,
            "fixed": 2,
            "stubbed": 3,
            "deferred": 0,
            "errored": 0,
            "errors": [],
            "sub_agent_calls": {"stub_b": 3},
            "dispatched": [
                {
                    "action_key": "fix_a",
                    "path": "/tmp/a.py",
                    "message": "regenerated",
                    "success": True,
                    "outcome": "fixed",
                    "llm_calls": 0,
                },
                {
                    "action_key": "stub_b",
                    "path": "/tmp/b.py",
                    "message": "stub: stub_b",
                    "success": True,
                    "outcome": "stubbed",
                    "llm_calls": 0,
                },
            ],
            "deferred_details": [],
        }
        data.update(overrides)
        report_path = reports_dir / "20260411T000000Z.json"
        report_path.write_text(json.dumps(data), encoding="utf-8")
        return report_path

    def test_v2_report_displays_stubbed(self, tmp_path: Path) -> None:
        report_path = self._write_v2_report(tmp_path)
        lines = render_last_run(report_path)
        stub_lines = [msg for lvl, msg in lines if lvl == "warn" and "Stubbed" in msg]
        assert len(stub_lines) == 1

    def test_v2_verbose_walks_dispatched_details(self, tmp_path: Path) -> None:
        report_path = self._write_v2_report(tmp_path)
        lines = render_last_run(report_path, verbose=True)
        messages = [msg for _lvl, msg in lines]
        assert any("[fix_a] /tmp/a.py -- regenerated" in m for m in messages)
        assert any("[stub_b] /tmp/b.py -- stub: stub_b" in m for m in messages)

    def test_v1_report_uses_legacy_rendering(self, tmp_path: Path) -> None:
        reports_dir = tmp_path / ".lexibrary" / "curator" / "reports"
        reports_dir.mkdir(parents=True)
        v1 = {
            "timestamp": "20260101T000000Z",
            "trigger": "on_demand",
            "checked": 3,
            "fixed": 3,
            "deferred": 0,
            "errored": 0,
            "errors": [],
            "sub_agent_calls": {},
        }
        report_path = reports_dir / "20260101T000000Z.json"
        report_path.write_text(json.dumps(v1), encoding="utf-8")

        lines = render_last_run(report_path)
        messages = [msg for _lvl, msg in lines]
        assert any("Checked:" in m for m in messages)
        # No Stubbed line when schema_version absent / 1
        assert all("Stubbed" not in m for m in messages)


class TestCliCurateVerbose:
    """CLI ``--verbose`` flag wiring."""

    def test_cli_curate_verbose_lists_dispatches(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from typer.testing import CliRunner  # noqa: PLC0415

        from lexibrary.cli.lexictl_app import lexictl_app  # noqa: PLC0415
        from lexibrary.curator import coordinator as coord_mod  # noqa: PLC0415

        project = _setup_minimal_project(tmp_path)
        monkeypatch.chdir(project)

        async def _fake_run(
            self: coord_mod.Coordinator,
            *,
            scope: Path | None = None,
            check: str | None = None,
            dry_run: bool = False,
            trigger: str = "on_demand",
        ) -> object:
            from lexibrary.curator.models import CuratorReport  # noqa: PLC0415

            return CuratorReport(
                checked=2,
                fixed=1,
                stubbed=1,
                schema_version=2,
                dispatched_details=[
                    {
                        "action_key": "fix_a",
                        "path": "/tmp/a.py",
                        "message": "regenerated",
                        "success": True,
                        "outcome": "fixed",
                        "llm_calls": 0,
                    },
                    {
                        "action_key": "stub_b",
                        "path": "/tmp/b.py",
                        "message": "stub: stub_b",
                        "success": True,
                        "outcome": "stubbed",
                        "llm_calls": 0,
                    },
                ],
                report_path=None,
            )

        monkeypatch.setattr(coord_mod.Coordinator, "run", _fake_run)

        runner = CliRunner()
        result = runner.invoke(lexictl_app, ["curate", "--verbose"])
        assert result.exit_code == 0, result.output
        assert "[fix_a]" in result.output
        assert "[stub_b]" in result.output
        assert "Stubbed" in result.output

    def test_cli_curate_last_run_verbose(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from typer.testing import CliRunner  # noqa: PLC0415

        from lexibrary.cli.lexictl_app import lexictl_app  # noqa: PLC0415

        project = _setup_minimal_project(tmp_path)
        reports_dir = project / ".lexibrary" / "curator" / "reports"
        reports_dir.mkdir(parents=True)
        payload = {
            "schema_version": 2,
            "timestamp": "20260411T000000Z",
            "trigger": "on_demand",
            "checked": 2,
            "fixed": 1,
            "stubbed": 1,
            "deferred": 0,
            "errored": 0,
            "errors": [],
            "sub_agent_calls": {},
            "dispatched": [
                {
                    "action_key": "fix_a",
                    "path": "/tmp/a.py",
                    "message": "regenerated",
                    "success": True,
                    "outcome": "fixed",
                    "llm_calls": 0,
                }
            ],
            "deferred_details": [],
        }
        (reports_dir / "20260411T000000Z.json").write_text(json.dumps(payload), encoding="utf-8")
        monkeypatch.chdir(project)

        runner = CliRunner()
        result = runner.invoke(lexictl_app, ["curate", "--last-run", "--verbose"])
        assert result.exit_code == 0, result.output
        assert "[fix_a] /tmp/a.py -- regenerated" in result.output


class TestShouldSkipPath:
    def test_should_skip_path_covers_uncommitted_and_iwh(self, tmp_path: Path) -> None:
        uncommitted = {tmp_path / "src" / "foo.py"}
        active_iwh = {tmp_path / "src" / "mod"}

        # Direct uncommitted hit
        assert _should_skip_path(tmp_path / "src" / "foo.py", uncommitted, active_iwh)

        # Path inside an active IWH directory
        assert _should_skip_path(tmp_path / "src" / "mod" / "bar.py", uncommitted, active_iwh)

        # Path outside both sets is not skipped
        assert not _should_skip_path(tmp_path / "src" / "baz.py", uncommitted, active_iwh)

        # Empty sets: nothing is skipped
        assert not _should_skip_path(tmp_path / "src" / "foo.py", set(), set())
