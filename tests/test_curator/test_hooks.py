"""Tests for reactive curator hooks.

Covers: post_edit_hook, post_bead_close_hook, validation_failure_hook
and their interactions with config toggles, concurrency locks, and
scope filtering.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lexibrary.archivist.change_checker import ChangeLevel
from lexibrary.archivist.pipeline import FileResult
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
# post_edit_hook reactive bootstrap (curator-freshness task 2.5)
# ---------------------------------------------------------------------------


def _make_bootstrap_config(
    *,
    prepare_indexes: bool = True,
    reactive_bootstrap_regenerate: bool = False,
    max_llm_calls_per_run: int = 50,
) -> LexibraryConfig:
    """Build a config with the curator-freshness bootstrap flags set."""
    return LexibraryConfig.model_validate(
        {
            "curator": {
                "reactive": {
                    "enabled": True,
                    "post_edit": True,
                    "post_bead_close": True,
                    "validation_failure": True,
                    "severity_threshold": "error",
                },
                "prepare_indexes": prepare_indexes,
                "reactive_bootstrap_regenerate": reactive_bootstrap_regenerate,
                "max_llm_calls_per_run": max_llm_calls_per_run,
            },
        }
    )


class TestPostEditHookBootstrap:
    """Tests for the always-on index-refresh bootstrap in post_edit_hook.

    Covers curator-freshness task 2.5 scenarios:
      * Bootstrap runs regardless of source_hash equality.
      * reactive_bootstrap_regenerate=False (default) -> update_file skipped.
      * reactive_bootstrap_regenerate=True -> update_file called; LLM call
        counts against max_llm_calls_per_run via pre_charged_llm_calls.
      * prepare_indexes=False -> neither refresh nor update_file invoked.
      * symbols.db absent -> refresh_file log-skipped, build_index still runs.
      * PID lock held -> bootstrap log-skips without raising.
    """

    @pytest.mark.asyncio
    async def test_bootstrap_runs_regardless_of_hash_equality(
        self, tmp_path: Path
    ) -> None:
        """Bootstrap refresh_file + build_index run even when source_hash
        matches the cached frontmatter hash — the hook does not short-circuit
        on hash equality."""
        project = _setup_project(tmp_path)
        fp = _make_source_file(project, "src/lexibrary/foo.py")
        # Materialise a stub symbols.db so refresh_file isn't skipped for the
        # "missing DB" reason — we want to assert the hook drives refresh_file
        # unconditionally in the hash-matches-cache case.
        (project / ".lexibrary" / "symbols.db").write_bytes(b"")
        config = _make_bootstrap_config()

        with (
            patch(
                "lexibrary.symbolgraph.builder.refresh_file"
            ) as mock_refresh,
            patch(
                "lexibrary.linkgraph.builder.build_index"
            ) as mock_build_index,
            patch("lexibrary.curator.coordinator.Coordinator") as mock_coord,
        ):
            mock_coord.return_value.pre_charged_llm_calls = 0
            mock_coord.return_value.run = AsyncMock(return_value=_default_report())

            await post_edit_hook(fp, project, config=config)

            mock_refresh.assert_called_once_with(project, config, fp)
            mock_build_index.assert_called_once_with(project, changed_paths=[fp])

    @pytest.mark.asyncio
    async def test_regenerate_false_does_not_call_update_file(
        self, tmp_path: Path
    ) -> None:
        """reactive_bootstrap_regenerate=False (default) -> update_file NOT
        invoked by the bootstrap."""
        project = _setup_project(tmp_path)
        fp = _make_source_file(project, "src/lexibrary/foo.py")
        config = _make_bootstrap_config(reactive_bootstrap_regenerate=False)

        with (
            patch("lexibrary.symbolgraph.builder.refresh_file"),
            patch("lexibrary.linkgraph.builder.build_index"),
            patch(
                "lexibrary.archivist.pipeline.update_file",
                new_callable=AsyncMock,
            ) as mock_update,
            patch(
                "lexibrary.archivist.service.build_archivist_service"
            ) as mock_build_arch,
            patch("lexibrary.curator.coordinator.Coordinator") as mock_coord,
        ):
            mock_coord.return_value.pre_charged_llm_calls = 0
            mock_coord.return_value.run = AsyncMock(return_value=_default_report())

            await post_edit_hook(fp, project, config=config)

            mock_update.assert_not_awaited()
            mock_build_arch.assert_not_called()

    @pytest.mark.asyncio
    async def test_regenerate_true_charges_llm_budget(
        self, tmp_path: Path
    ) -> None:
        """reactive_bootstrap_regenerate=True -> update_file called; a
        successful regeneration increments pre_charged_llm_calls so the call
        counts against max_llm_calls_per_run via the coordinator's counter."""
        project = _setup_project(tmp_path)
        fp = _make_source_file(project, "src/lexibrary/foo.py")
        config = _make_bootstrap_config(
            reactive_bootstrap_regenerate=True, max_llm_calls_per_run=10
        )

        # update_file returns a ChangeLevel that corresponds to an actual
        # LLM call — anything other than UNCHANGED / AGENT_UPDATED /
        # skip_reason-set / the specific failure reasons listed in
        # _bootstrap_archivist_regenerate counts.  CONTENT_CHANGED is a
        # non-interface content edit that drives a full LLM regeneration.
        successful_result = FileResult(change=ChangeLevel.CONTENT_CHANGED)

        # Build a real coordinator-like object so += 1 works and is
        # observable after the hook returns.
        coord_instance = MagicMock()
        coord_instance.pre_charged_llm_calls = 0
        coord_instance.run = AsyncMock(return_value=_default_report())

        with (
            patch("lexibrary.symbolgraph.builder.refresh_file"),
            patch("lexibrary.linkgraph.builder.build_index"),
            patch(
                "lexibrary.archivist.pipeline.update_file",
                new_callable=AsyncMock,
                return_value=successful_result,
            ) as mock_update,
            patch(
                "lexibrary.archivist.service.build_archivist_service"
            ) as mock_build_arch,
            patch(
                "lexibrary.curator.coordinator.Coordinator",
                return_value=coord_instance,
            ),
        ):
            await post_edit_hook(fp, project, config=config)

            mock_build_arch.assert_called_once_with(config)
            mock_update.assert_awaited_once()
            # The LLM call was charged to the coordinator's budget counter.
            assert coord_instance.pre_charged_llm_calls == 1
            # And the counter is strictly below the cap, so the dispatch
            # phase still has budget remaining.
            assert (
                coord_instance.pre_charged_llm_calls
                < config.curator.max_llm_calls_per_run
            )

    @pytest.mark.asyncio
    async def test_prepare_indexes_false_skips_refresh_and_update(
        self, tmp_path: Path
    ) -> None:
        """prepare_indexes=False -> neither the refresh pair nor update_file
        is invoked; the hook hands straight off to the coordinator."""
        project = _setup_project(tmp_path)
        fp = _make_source_file(project, "src/lexibrary/foo.py")
        config = _make_bootstrap_config(
            prepare_indexes=False, reactive_bootstrap_regenerate=True
        )

        with (
            patch(
                "lexibrary.symbolgraph.builder.refresh_file"
            ) as mock_refresh,
            patch(
                "lexibrary.linkgraph.builder.build_index"
            ) as mock_build_index,
            patch(
                "lexibrary.archivist.pipeline.update_file",
                new_callable=AsyncMock,
            ) as mock_update,
            patch("lexibrary.curator.coordinator.Coordinator") as mock_coord,
        ):
            mock_coord.return_value.pre_charged_llm_calls = 0
            mock_coord.return_value.run = AsyncMock(return_value=_default_report())

            await post_edit_hook(fp, project, config=config)

            mock_refresh.assert_not_called()
            mock_build_index.assert_not_called()
            mock_update.assert_not_awaited()
            # The coordinator still runs (the short-circuit path awaits
            # _run_coordinator directly).
            mock_coord.return_value.run.assert_awaited_once_with(
                scope=fp, trigger="reactive_post_edit"
            )

    @pytest.mark.asyncio
    async def test_symbols_db_absent_skips_refresh_but_keeps_build_index(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """When symbols.db is missing, refresh_file log-skips silently (its
        own internal guard) but build_index still runs."""
        project = _setup_project(tmp_path)
        fp = _make_source_file(project, "src/lexibrary/foo.py")
        # Do NOT materialise .lexibrary/symbols.db — the real refresh_file
        # guard logs a debug message and returns, leaving build_index to
        # drive the incremental link-graph rebuild.
        assert not (project / ".lexibrary" / "symbols.db").exists()

        config = _make_bootstrap_config()

        # We run the REAL refresh_file here (not mocked) so the DB-missing
        # guard gets exercised; the symbolgraph helper is a plain sync
        # function with no side effects when symbols.db is absent.
        with (
            patch(
                "lexibrary.linkgraph.builder.build_index"
            ) as mock_build_index,
            patch("lexibrary.curator.coordinator.Coordinator") as mock_coord,
        ):
            mock_coord.return_value.pre_charged_llm_calls = 0
            mock_coord.return_value.run = AsyncMock(return_value=_default_report())

            import logging

            with caplog.at_level(logging.DEBUG, logger="lexibrary.symbolgraph.builder"):
                await post_edit_hook(fp, project, config=config)

            # Bootstrap did not raise — build_index still ran even though
            # symbols.db was absent.
            mock_build_index.assert_called_once_with(project, changed_paths=[fp])
            # refresh_file's internal guard emitted a log note about the
            # missing DB.
            assert any(
                "symbols.db does not exist" in rec.getMessage()
                for rec in caplog.records
            )

    @pytest.mark.asyncio
    async def test_pid_lock_held_skips_bootstrap_without_racing(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A held PID lock -> bootstrap log-skips without raising or racing.

        Simulates a concurrent curator run by writing a lock file with the
        current PID and a fresh timestamp. ``_acquire_lock`` sees the live
        PID and raises ``CuratorLockError`` which the bootstrap catches and
        turns into a log-skip.
        """
        project = _setup_project(tmp_path)
        fp = _make_source_file(project, "src/lexibrary/foo.py")
        config = _make_bootstrap_config()

        # Simulate a held lock by planting a fresh PID/timestamp entry
        # owned by THIS process — _pid_alive(os.getpid()) returns True and
        # the age is ~0 so _acquire_lock treats the lock as live.
        lock_path = project / ".lexibrary" / "curator" / ".curator.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text(
            json.dumps({"pid": os.getpid(), "timestamp": time.time()}),
            encoding="utf-8",
        )

        with (
            patch(
                "lexibrary.symbolgraph.builder.refresh_file"
            ) as mock_refresh,
            patch(
                "lexibrary.linkgraph.builder.build_index"
            ) as mock_build_index,
            patch("lexibrary.curator.coordinator.Coordinator") as mock_coord,
        ):
            mock_coord.return_value.pre_charged_llm_calls = 0
            # The coordinator's own .run() call will also observe the held
            # lock via CuratorLockError — the existing _run_coordinator
            # wrapper already handles that; return a value to keep the
            # assertion crisp.
            mock_coord.return_value.run = AsyncMock(
                side_effect=CuratorLockError("lock held")
            )

            import logging

            with caplog.at_level(logging.INFO, logger="lexibrary.curator.hooks"):
                # Must NOT raise — the lock-held path is a log-skip.
                await post_edit_hook(fp, project, config=config)

            # Bootstrap did not touch the indexes.
            mock_refresh.assert_not_called()
            mock_build_index.assert_not_called()
            # And the bootstrap emitted a log note about the held lock.
            assert any(
                "lock held" in rec.getMessage().lower()
                or "skipping reactive post_edit bootstrap" in rec.getMessage()
                for rec in caplog.records
            )


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
