"""Tests for reactive curator hooks.

Covers: post_edit_hook, post_bead_close_hook, validation_failure_hook
and their interactions with config toggles, concurrency locks, and
scope filtering.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from lexibrary.config.schema import LexibraryConfig
from lexibrary.curator.coordinator import CuratorLockError
from lexibrary.curator.hooks import (
    _is_source_file,
    _severity_at_or_above,
    post_bead_close_hook,
    post_edit_hook,
    validation_failure_hook,
)
from lexibrary.curator.models import CuratorReport
from lexibrary.validator.report import ValidationIssue

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_project(tmp_path: Path) -> Path:
    """Create a minimal .lexibrary project structure."""
    lex_dir = tmp_path / ".lexibrary"
    lex_dir.mkdir()
    (lex_dir / "designs").mkdir()
    (lex_dir / "curator").mkdir()
    return tmp_path


def _make_config(
    *,
    enabled: bool = True,
    post_edit: bool = True,
    post_bead_close: bool = True,
    validation_failure: bool = True,
    severity_threshold: str = "error",
) -> LexibraryConfig:
    """Build a LexibraryConfig with the given reactive settings."""
    return LexibraryConfig.model_validate(
        {
            "curator": {
                "reactive": {
                    "enabled": enabled,
                    "post_edit": post_edit,
                    "post_bead_close": post_bead_close,
                    "validation_failure": validation_failure,
                    "severity_threshold": severity_threshold,
                },
            },
        }
    )


def _make_source_file(project_root: Path, rel_path: str) -> Path:
    """Create a minimal source file and return its absolute path."""
    p = project_root / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("# placeholder\n", encoding="utf-8")
    return p


def _default_report() -> CuratorReport:
    """Return a default CuratorReport for mocking coordinator.run()."""
    return CuratorReport()


# ---------------------------------------------------------------------------
# _is_source_file helper
# ---------------------------------------------------------------------------


class TestIsSourceFile:
    """Tests for the _is_source_file scope-checking helper."""

    def test_src_file_returns_true(self, tmp_path: Path) -> None:
        project = _setup_project(tmp_path)
        fp = _make_source_file(project, "src/lexibrary/foo.py")
        assert _is_source_file(fp, project) is True

    def test_tests_file_returns_false(self, tmp_path: Path) -> None:
        project = _setup_project(tmp_path)
        fp = _make_source_file(project, "tests/test_foo.py")
        assert _is_source_file(fp, project) is False

    def test_root_file_returns_false(self, tmp_path: Path) -> None:
        project = _setup_project(tmp_path)
        fp = _make_source_file(project, "README.md")
        assert _is_source_file(fp, project) is False

    def test_outside_project_returns_false(self, tmp_path: Path) -> None:
        project = _setup_project(tmp_path)
        outside = tmp_path / "other" / "src" / "foo.py"
        outside.parent.mkdir(parents=True, exist_ok=True)
        outside.write_text("x\n")
        assert _is_source_file(outside, project) is False


# ---------------------------------------------------------------------------
# _severity_at_or_above helper
# ---------------------------------------------------------------------------


class TestSeverityAtOrAbove:
    """Tests for severity threshold comparison."""

    def test_error_at_error_threshold(self) -> None:
        assert _severity_at_or_above("error", "error") is True

    def test_warning_below_error_threshold(self) -> None:
        assert _severity_at_or_above("warning", "error") is False

    def test_error_above_warning_threshold(self) -> None:
        assert _severity_at_or_above("error", "warning") is True

    def test_critical_above_error_threshold(self) -> None:
        assert _severity_at_or_above("critical", "error") is True

    def test_info_below_warning_threshold(self) -> None:
        assert _severity_at_or_above("info", "warning") is False


# ---------------------------------------------------------------------------
# post_edit_hook
# ---------------------------------------------------------------------------


class TestPostEditHook:
    """Tests for post_edit_hook."""

    @pytest.mark.asyncio
    async def test_calls_coordinator_with_correct_scope_and_trigger(self, tmp_path: Path) -> None:
        """post_edit_hook calls coordinator with scope=file_path and trigger."""
        project = _setup_project(tmp_path)
        fp = _make_source_file(project, "src/lexibrary/foo.py")
        config = _make_config(enabled=True)

        with patch("lexibrary.curator.coordinator.Coordinator") as mock_coordinator:
            mock_instance = mock_coordinator.return_value
            mock_instance.run = AsyncMock(return_value=_default_report())

            await post_edit_hook(fp, project, config=config)

            mock_coordinator.assert_called_once_with(project, config)
            mock_instance.run.assert_awaited_once_with(scope=fp, trigger="reactive_post_edit")

    @pytest.mark.asyncio
    async def test_returns_immediately_when_disabled(self, tmp_path: Path) -> None:
        """post_edit_hook returns immediately when reactive.enabled is False."""
        project = _setup_project(tmp_path)
        fp = _make_source_file(project, "src/lexibrary/foo.py")
        config = _make_config(enabled=False)

        with patch("lexibrary.curator.coordinator.Coordinator") as mock_coordinator:
            await post_edit_hook(fp, project, config=config)
            mock_coordinator.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_immediately_when_post_edit_toggle_off(self, tmp_path: Path) -> None:
        """post_edit_hook returns when reactive.post_edit is False."""
        project = _setup_project(tmp_path)
        fp = _make_source_file(project, "src/lexibrary/foo.py")
        config = _make_config(enabled=True, post_edit=False)

        with patch("lexibrary.curator.coordinator.Coordinator") as mock_coordinator:
            await post_edit_hook(fp, project, config=config)
            mock_coordinator.assert_not_called()

    @pytest.mark.asyncio
    async def test_exits_when_coordinator_lock_held(self, tmp_path: Path) -> None:
        """post_edit_hook exits gracefully when coordinator lock is held."""
        project = _setup_project(tmp_path)
        fp = _make_source_file(project, "src/lexibrary/foo.py")
        config = _make_config(enabled=True)

        with patch("lexibrary.curator.coordinator.Coordinator") as mock_coordinator:
            mock_instance = mock_coordinator.return_value
            mock_instance.run = AsyncMock(side_effect=CuratorLockError("lock held"))

            # Should not raise
            await post_edit_hook(fp, project, config=config)

            mock_instance.run.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_non_source_file_does_not_trigger(self, tmp_path: Path) -> None:
        """Non-source files (e.g., tests/) do not trigger post_edit_hook."""
        project = _setup_project(tmp_path)
        fp = _make_source_file(project, "tests/test_foo.py")
        config = _make_config(enabled=True)

        with patch("lexibrary.curator.coordinator.Coordinator") as mock_coordinator:
            await post_edit_hook(fp, project, config=config)
            mock_coordinator.assert_not_called()


# ---------------------------------------------------------------------------
# post_bead_close_hook
# ---------------------------------------------------------------------------


class TestPostBeadCloseHook:
    """Tests for post_bead_close_hook."""

    @pytest.mark.asyncio
    async def test_calls_coordinator_with_directory_scope(self, tmp_path: Path) -> None:
        """post_bead_close_hook calls coordinator with scope=directory."""
        project = _setup_project(tmp_path)
        directory = project / "src" / "lexibrary" / "curator"
        directory.mkdir(parents=True, exist_ok=True)
        config = _make_config(enabled=True)

        with patch("lexibrary.curator.coordinator.Coordinator") as mock_coordinator:
            mock_instance = mock_coordinator.return_value
            mock_instance.run = AsyncMock(return_value=_default_report())

            await post_bead_close_hook(directory, project, config=config)

            mock_coordinator.assert_called_once_with(project, config)
            mock_instance.run.assert_awaited_once_with(
                scope=directory, trigger="reactive_post_bead_close"
            )

    @pytest.mark.asyncio
    async def test_returns_immediately_when_disabled(self, tmp_path: Path) -> None:
        """post_bead_close_hook returns when reactive.enabled is False."""
        project = _setup_project(tmp_path)
        directory = project / "src" / "lexibrary"
        config = _make_config(enabled=False)

        with patch("lexibrary.curator.coordinator.Coordinator") as mock_coordinator:
            await post_bead_close_hook(directory, project, config=config)
            mock_coordinator.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_when_toggle_off(self, tmp_path: Path) -> None:
        """post_bead_close_hook returns when reactive.post_bead_close is False."""
        project = _setup_project(tmp_path)
        directory = project / "src" / "lexibrary"
        config = _make_config(enabled=True, post_bead_close=False)

        with patch("lexibrary.curator.coordinator.Coordinator") as mock_coordinator:
            await post_bead_close_hook(directory, project, config=config)
            mock_coordinator.assert_not_called()

    @pytest.mark.asyncio
    async def test_exits_when_lock_held(self, tmp_path: Path) -> None:
        """post_bead_close_hook exits gracefully when lock is held."""
        project = _setup_project(tmp_path)
        directory = project / "src" / "lexibrary"
        directory.mkdir(parents=True, exist_ok=True)
        config = _make_config(enabled=True)

        with patch("lexibrary.curator.coordinator.Coordinator") as mock_coordinator:
            mock_instance = mock_coordinator.return_value
            mock_instance.run = AsyncMock(side_effect=CuratorLockError("lock held"))

            await post_bead_close_hook(directory, project, config=config)
            mock_instance.run.assert_awaited_once()


# ---------------------------------------------------------------------------
# validation_failure_hook
# ---------------------------------------------------------------------------


class TestValidationFailureHook:
    """Tests for validation_failure_hook."""

    @pytest.mark.asyncio
    async def test_dispatches_for_error_level_issues(self, tmp_path: Path) -> None:
        """validation_failure_hook dispatches for error-level issues."""
        project = _setup_project(tmp_path)
        config = _make_config(enabled=True, severity_threshold="error")

        errors = [
            ValidationIssue(
                severity="error",
                check="stale_agent_design",
                message="Design file is stale",
                artifact="src/lexibrary/foo.py",
            ),
        ]

        with patch("lexibrary.curator.coordinator.Coordinator") as mock_coordinator:
            mock_instance = mock_coordinator.return_value
            mock_instance.run = AsyncMock(return_value=_default_report())

            await validation_failure_hook(errors, project, config=config)

            mock_instance.run.assert_awaited_once_with(
                scope=project / "src/lexibrary/foo.py",
                trigger="reactive_validation_failure",
            )

    @pytest.mark.asyncio
    async def test_skips_warning_when_threshold_is_error(self, tmp_path: Path) -> None:
        """Warning-level issues are skipped when threshold is 'error'."""
        project = _setup_project(tmp_path)
        config = _make_config(enabled=True, severity_threshold="error")

        errors = [
            ValidationIssue(
                severity="warning",
                check="wikilink_resolution",
                message="Broken wikilink",
                artifact="src/lexibrary/bar.py",
            ),
        ]

        with patch("lexibrary.curator.coordinator.Coordinator") as mock_coordinator:
            await validation_failure_hook(errors, project, config=config)
            mock_coordinator.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatches_warning_when_threshold_is_warning(self, tmp_path: Path) -> None:
        """Warning-level issues are dispatched when threshold is 'warning'."""
        project = _setup_project(tmp_path)
        config = _make_config(enabled=True, severity_threshold="warning")

        errors = [
            ValidationIssue(
                severity="warning",
                check="wikilink_resolution",
                message="Broken wikilink",
                artifact="src/lexibrary/bar.py",
            ),
        ]

        with patch("lexibrary.curator.coordinator.Coordinator") as mock_coordinator:
            mock_instance = mock_coordinator.return_value
            mock_instance.run = AsyncMock(return_value=_default_report())

            await validation_failure_hook(errors, project, config=config)
            mock_instance.run.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_when_disabled(self, tmp_path: Path) -> None:
        """validation_failure_hook returns when reactive.enabled is False."""
        project = _setup_project(tmp_path)
        config = _make_config(enabled=False)

        errors = [
            ValidationIssue(
                severity="error",
                check="stale_agent_design",
                message="stale",
                artifact="src/foo.py",
            ),
        ]

        with patch("lexibrary.curator.coordinator.Coordinator") as mock_coordinator:
            await validation_failure_hook(errors, project, config=config)
            mock_coordinator.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_when_toggle_off(self, tmp_path: Path) -> None:
        """validation_failure_hook returns when reactive.validation_failure is False."""
        project = _setup_project(tmp_path)
        config = _make_config(enabled=True, validation_failure=False)

        errors = [
            ValidationIssue(
                severity="error",
                check="stale_agent_design",
                message="stale",
                artifact="src/foo.py",
            ),
        ]

        with patch("lexibrary.curator.coordinator.Coordinator") as mock_coordinator:
            await validation_failure_hook(errors, project, config=config)
            mock_coordinator.assert_not_called()

    @pytest.mark.asyncio
    async def test_deduplicates_scopes(self, tmp_path: Path) -> None:
        """Multiple errors for the same artifact result in a single coordinator call."""
        project = _setup_project(tmp_path)
        config = _make_config(enabled=True, severity_threshold="error")

        errors = [
            ValidationIssue(
                severity="error",
                check="stale_agent_design",
                message="stale",
                artifact="src/lexibrary/foo.py",
            ),
            ValidationIssue(
                severity="error",
                check="hash_freshness",
                message="hash mismatch",
                artifact="src/lexibrary/foo.py",
            ),
        ]

        with patch("lexibrary.curator.coordinator.Coordinator") as mock_coordinator:
            mock_instance = mock_coordinator.return_value
            mock_instance.run = AsyncMock(return_value=_default_report())

            await validation_failure_hook(errors, project, config=config)

            # Only one call despite two errors for the same artifact
            assert mock_instance.run.await_count == 1

    @pytest.mark.asyncio
    async def test_multiple_unique_scopes(self, tmp_path: Path) -> None:
        """Errors for different artifacts trigger separate coordinator calls."""
        project = _setup_project(tmp_path)
        config = _make_config(enabled=True, severity_threshold="error")

        errors = [
            ValidationIssue(
                severity="error",
                check="stale_agent_design",
                message="stale",
                artifact="src/lexibrary/foo.py",
            ),
            ValidationIssue(
                severity="error",
                check="wikilink_resolution",
                message="broken link",
                artifact="src/lexibrary/bar.py",
            ),
        ]

        with patch("lexibrary.curator.coordinator.Coordinator") as mock_coordinator:
            mock_instance = mock_coordinator.return_value
            mock_instance.run = AsyncMock(return_value=_default_report())

            await validation_failure_hook(errors, project, config=config)

            assert mock_instance.run.await_count == 2

    @pytest.mark.asyncio
    async def test_exits_gracefully_when_lock_held(self, tmp_path: Path) -> None:
        """validation_failure_hook exits gracefully when lock is held."""
        project = _setup_project(tmp_path)
        config = _make_config(enabled=True, severity_threshold="error")

        errors = [
            ValidationIssue(
                severity="error",
                check="stale_agent_design",
                message="stale",
                artifact="src/foo.py",
            ),
        ]

        with patch("lexibrary.curator.coordinator.Coordinator") as mock_coordinator:
            mock_instance = mock_coordinator.return_value
            mock_instance.run = AsyncMock(side_effect=CuratorLockError("lock held"))

            # Should not raise
            await validation_failure_hook(errors, project, config=config)
            mock_instance.run.assert_awaited_once()
