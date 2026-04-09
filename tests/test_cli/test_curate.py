"""Tests for the ``lexictl curate`` CLI command."""

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
# Helpers
# ---------------------------------------------------------------------------


def _setup_project(tmp_path: Path) -> Path:
    """Create a minimal initialized project at tmp_path."""
    (tmp_path / ".lexibrary").mkdir()
    (tmp_path / ".lexibrary" / "config.yaml").write_text("")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hello')\n")
    return tmp_path


def _make_report(
    *,
    checked: int = 5,
    fixed: int = 2,
    deferred: int = 1,
    errored: int = 0,
    sub_agent_calls: dict[str, int] | None = None,
    report_path: Path | None = None,
) -> CuratorReport:
    """Create a CuratorReport with customizable fields."""
    return CuratorReport(
        checked=checked,
        fixed=fixed,
        deferred=deferred,
        errored=errored,
        sub_agent_calls=sub_agent_calls or {},
        report_path=report_path,
    )


def _write_json_report(
    tmp_path: Path,
    *,
    timestamp: str = "20260409T120000Z",
    checked: int = 10,
    fixed: int = 3,
    deferred: int = 2,
    errored: int = 0,
) -> Path:
    """Write a JSON report file in the curator reports directory."""
    reports_dir = tmp_path / ".lexibrary" / "curator" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_file = reports_dir / f"{timestamp}.json"
    data = {
        "timestamp": timestamp,
        "checked": checked,
        "fixed": fixed,
        "deferred": deferred,
        "errored": errored,
        "errors": [],
        "sub_agent_calls": {"regenerate_stale_design": 2, "autofix_validation_issue": 1},
    }
    report_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return report_file


# ---------------------------------------------------------------------------
# Full sweep (no flags)
# ---------------------------------------------------------------------------


class TestCurateFullSweep:
    """Tests for ``lexictl curate`` without flags."""

    def test_full_sweep_produces_output(self, tmp_path: Path) -> None:
        """Full sweep with mocked coordinator produces summary output."""
        _setup_project(tmp_path)
        report = _make_report(
            checked=5,
            fixed=2,
            deferred=1,
            sub_agent_calls={"regenerate_stale_design": 2},
            report_path=tmp_path / ".lexibrary" / "curator" / "reports" / "test.json",
        )

        mock_run = AsyncMock(return_value=report)
        mock_coordinator = MagicMock()
        mock_coordinator.run = mock_run

        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            with patch(
                "lexibrary.curator.coordinator.Coordinator",
                return_value=mock_coordinator,
            ):
                result = runner.invoke(lexictl_app, ["curate"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "Curator Run Summary" in result.output
        assert "Checked:  5" in result.output
        assert "Fixed:    2" in result.output

    def test_full_sweep_exit_1_on_errors(self, tmp_path: Path) -> None:
        """Exit code 1 when report has errors."""
        _setup_project(tmp_path)
        report = _make_report(errored=3)

        mock_run = AsyncMock(return_value=report)
        mock_coordinator = MagicMock()
        mock_coordinator.run = mock_run

        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            with patch(
                "lexibrary.curator.coordinator.Coordinator",
                return_value=mock_coordinator,
            ):
                result = runner.invoke(lexictl_app, ["curate"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 1

    def test_full_sweep_no_project_root(self, tmp_path: Path) -> None:
        """Exit 1 when no .lexibrary/ directory exists."""
        # Don't create .lexibrary
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = runner.invoke(lexictl_app, ["curate"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 1
        assert "No .lexibrary/" in result.output

    def test_full_sweep_lock_error(self, tmp_path: Path) -> None:
        """Exit 1 when curator lock cannot be acquired."""
        from lexibrary.curator.coordinator import CuratorLockError  # noqa: PLC0415

        _setup_project(tmp_path)

        mock_coordinator = MagicMock()
        mock_coordinator.run = AsyncMock(
            side_effect=CuratorLockError("Another curator is running (PID 12345)")
        )

        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            with patch(
                "lexibrary.curator.coordinator.Coordinator",
                return_value=mock_coordinator,
            ):
                result = runner.invoke(lexictl_app, ["curate"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 1
        assert "Another curator" in result.output


# ---------------------------------------------------------------------------
# --scope
# ---------------------------------------------------------------------------


class TestCurateScope:
    """Tests for ``lexictl curate --scope``."""

    def test_scope_limits_to_directory(self, tmp_path: Path) -> None:
        """--scope passes the resolved path to coordinator.run()."""
        _setup_project(tmp_path)
        report = _make_report()

        mock_run = AsyncMock(return_value=report)
        mock_coordinator = MagicMock()
        mock_coordinator.run = mock_run

        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            with patch(
                "lexibrary.curator.coordinator.Coordinator",
                return_value=mock_coordinator,
            ):
                result = runner.invoke(lexictl_app, ["curate", "--scope", "src"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 0, f"Output: {result.output}"
        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["scope"] == (tmp_path / "src").resolve()

    def test_scope_invalid_path_errors(self, tmp_path: Path) -> None:
        """--scope with non-existent path exits with error."""
        _setup_project(tmp_path)

        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = runner.invoke(lexictl_app, ["curate", "--scope", "nonexistent"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 1
        assert "not found" in result.output.lower()


# ---------------------------------------------------------------------------
# --check
# ---------------------------------------------------------------------------


class TestCurateCheck:
    """Tests for ``lexictl curate --check``."""

    def test_check_runs_single_check(self, tmp_path: Path) -> None:
        """--check passes the check name to coordinator.run()."""
        _setup_project(tmp_path)
        report = _make_report()

        mock_run = AsyncMock(return_value=report)
        mock_coordinator = MagicMock()
        mock_coordinator.run = mock_run

        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            with patch(
                "lexibrary.curator.coordinator.Coordinator",
                return_value=mock_coordinator,
            ):
                result = runner.invoke(lexictl_app, ["curate", "--check", "hash_freshness"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 0, f"Output: {result.output}"
        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["check"] == "hash_freshness"

    def test_check_invalid_name_errors_and_lists_available(self, tmp_path: Path) -> None:
        """--check with invalid name exits with error and lists available checks."""
        _setup_project(tmp_path)

        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = runner.invoke(lexictl_app, ["curate", "--check", "nonexistent_check"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 1
        assert "Unknown check" in result.output
        # Should hint at available checks
        assert "Available checks" in result.output


# ---------------------------------------------------------------------------
# --dry-run
# ---------------------------------------------------------------------------


class TestCurateDryRun:
    """Tests for ``lexictl curate --dry-run``."""

    def test_dry_run_shows_counts_without_modifying(self, tmp_path: Path) -> None:
        """--dry-run displays counts and does not modify files."""
        _setup_project(tmp_path)
        report = _make_report(
            checked=8,
            fixed=3,  # In dry-run these are "would dispatch" stubs
            deferred=2,
            sub_agent_calls={"regenerate_stale_design": 2, "autofix_validation_issue": 1},
        )

        mock_run = AsyncMock(return_value=report)
        mock_coordinator = MagicMock()
        mock_coordinator.run = mock_run

        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            with patch(
                "lexibrary.curator.coordinator.Coordinator",
                return_value=mock_coordinator,
            ):
                result = runner.invoke(lexictl_app, ["curate", "--dry-run"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "DRY-RUN" in result.output
        assert "Checked:" in result.output

        # Verify dry_run=True was passed to coordinator
        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["dry_run"] is True


# ---------------------------------------------------------------------------
# --last-run
# ---------------------------------------------------------------------------


class TestCurateLastRun:
    """Tests for ``lexictl curate --last-run``."""

    def test_last_run_displays_info(self, tmp_path: Path) -> None:
        """--last-run reads and displays the most recent report."""
        _setup_project(tmp_path)
        _write_json_report(tmp_path, timestamp="20260409T120000Z", checked=10, fixed=3)

        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = runner.invoke(lexictl_app, ["curate", "--last-run"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "Last Curator Run" in result.output
        assert "20260409T120000Z" in result.output
        assert "Checked:" in result.output

    def test_last_run_no_prior_runs(self, tmp_path: Path) -> None:
        """--last-run with no prior runs shows message."""
        _setup_project(tmp_path)

        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = runner.invoke(lexictl_app, ["curate", "--last-run"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 0
        assert "No previous curator runs found" in result.output

    def test_last_run_picks_most_recent(self, tmp_path: Path) -> None:
        """--last-run picks the most recent file when multiple exist."""
        _setup_project(tmp_path)
        _write_json_report(tmp_path, timestamp="20260408T100000Z", checked=5, fixed=1)
        _write_json_report(tmp_path, timestamp="20260409T150000Z", checked=15, fixed=7)

        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = runner.invoke(lexictl_app, ["curate", "--last-run"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 0
        assert "20260409T150000Z" in result.output
        assert "Checked:   15" in result.output

    def test_last_run_empty_reports_dir(self, tmp_path: Path) -> None:
        """--last-run with empty reports directory shows message."""
        _setup_project(tmp_path)
        (tmp_path / ".lexibrary" / "curator" / "reports").mkdir(parents=True)

        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = runner.invoke(lexictl_app, ["curate", "--last-run"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 0
        assert "No previous curator runs found" in result.output


# ---------------------------------------------------------------------------
# Output goes through _output.py helpers
# ---------------------------------------------------------------------------


class TestCurateOutput:
    """Verify all output goes through _output.py helpers."""

    def test_deferred_shows_warning(self, tmp_path: Path) -> None:
        """Deferred items produce warnings via warn()."""
        _setup_project(tmp_path)
        report = _make_report(deferred=5)

        mock_run = AsyncMock(return_value=report)
        mock_coordinator = MagicMock()
        mock_coordinator.run = mock_run

        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            with patch(
                "lexibrary.curator.coordinator.Coordinator",
                return_value=mock_coordinator,
            ):
                result = runner.invoke(lexictl_app, ["curate"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 0
        # warn() prepends "Warning: " -- but since CliRunner captures both
        # stdout and stderr together, we check the content
        assert "Deferred: 5" in result.output

    def test_errors_show_error_output(self, tmp_path: Path) -> None:
        """Error count produces error-level output via error()."""
        _setup_project(tmp_path)
        report = _make_report(errored=2)

        mock_run = AsyncMock(return_value=report)
        mock_coordinator = MagicMock()
        mock_coordinator.run = mock_run

        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            with patch(
                "lexibrary.curator.coordinator.Coordinator",
                return_value=mock_coordinator,
            ):
                result = runner.invoke(lexictl_app, ["curate"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 1
        assert "Errors:" in result.output

    def test_sub_agent_calls_displayed(self, tmp_path: Path) -> None:
        """Sub-agent call counts appear in output."""
        _setup_project(tmp_path)
        report = _make_report(
            sub_agent_calls={"regenerate_stale_design": 3, "integrate_sidecar_comments": 1},
        )

        mock_run = AsyncMock(return_value=report)
        mock_coordinator = MagicMock()
        mock_coordinator.run = mock_run

        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            with patch(
                "lexibrary.curator.coordinator.Coordinator",
                return_value=mock_coordinator,
            ):
                result = runner.invoke(lexictl_app, ["curate"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 0
        assert "regenerate_stale_design: 3" in result.output
        assert "integrate_sidecar_comments: 1" in result.output


# ---------------------------------------------------------------------------
# Command registration
# ---------------------------------------------------------------------------


class TestCurateRegistration:
    """Verify the curate command is correctly registered."""

    def test_curate_appears_in_help(self) -> None:
        """The curate command appears in lexictl --help."""
        result = runner.invoke(lexictl_app, ["--help"])
        assert result.exit_code == 0
        assert "curate" in result.output

    def test_curate_help_shows_options(self) -> None:
        """``lexictl curate --help`` lists all four options."""
        result = runner.invoke(lexictl_app, ["curate", "--help"])
        assert result.exit_code == 0
        for option in ("--scope", "--check", "--dry-run", "--last-run"):
            assert option in result.output, f"Option {option} missing from help"
