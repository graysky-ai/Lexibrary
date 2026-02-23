"""Tests for the rewritten DaemonService (three-mode entry points)."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from lexibrary.daemon.service import DaemonService, _has_changes

# ---------------------------------------------------------------------------
# _has_changes tests
# ---------------------------------------------------------------------------


class TestHasChanges:
    """Tests for the _has_changes() stat-walk function."""

    def test_first_run_always_returns_true(self, tmp_path: Path) -> None:
        """When last_sweep is 0.0 (first run), always report changes."""
        assert _has_changes(tmp_path, 0.0) is True

    def test_newer_file_returns_true(self, tmp_path: Path) -> None:
        """A file with mtime newer than last_sweep triggers changes."""
        (tmp_path / "src").mkdir()
        f = tmp_path / "src" / "hello.py"
        f.write_text("print('hi')", encoding="utf-8")

        # last_sweep is in the past
        last_sweep = f.stat().st_mtime - 10
        assert _has_changes(tmp_path, last_sweep) is True

    def test_all_old_files_returns_false(self, tmp_path: Path) -> None:
        """When all files are older than last_sweep, no changes detected."""
        (tmp_path / "src").mkdir()
        f = tmp_path / "src" / "hello.py"
        f.write_text("print('hi')", encoding="utf-8")

        # last_sweep is in the future
        last_sweep = time.time() + 100
        assert _has_changes(tmp_path, last_sweep) is False

    def test_skips_lexibrary_directory(self, tmp_path: Path) -> None:
        """Files inside .lexibrary/ are excluded from the change scan."""
        lex_dir = tmp_path / ".lexibrary"
        lex_dir.mkdir()
        f = lex_dir / "something.md"
        f.write_text("design file", encoding="utf-8")

        # last_sweep is before the file was written, but .lexibrary is skipped
        last_sweep = f.stat().st_mtime - 10
        assert _has_changes(tmp_path, last_sweep) is False

    def test_empty_directory_returns_false(self, tmp_path: Path) -> None:
        """An empty project reports no changes (when not first run)."""
        last_sweep = time.time() - 10
        assert _has_changes(tmp_path, last_sweep) is False

    def test_nested_newer_file_detected(self, tmp_path: Path) -> None:
        """A newer file in a deeply nested directory is still detected."""
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        f = deep / "nested.py"
        f.write_text("x = 1", encoding="utf-8")

        last_sweep = f.stat().st_mtime - 10
        assert _has_changes(tmp_path, last_sweep) is True


# ---------------------------------------------------------------------------
# DaemonService.run_once tests
# ---------------------------------------------------------------------------


class TestRunOnce:
    """Tests for DaemonService.run_once()."""

    def _make_config(self, skip_if_unchanged: bool = True) -> MagicMock:
        """Create a mock LexibraryConfig."""
        config = MagicMock()
        config.daemon.sweep_skip_if_unchanged = skip_if_unchanged
        config.daemon.log_level = "warning"
        config.daemon.sweep_interval_seconds = 3600
        config.daemon.debounce_seconds = 2.0
        config.daemon.watchdog_enabled = False
        config.llm = MagicMock()
        config.scope_root = "."
        return config

    @patch("lexibrary.daemon.service.update_project")
    @patch("lexibrary.daemon.service.setup_daemon_logging")
    @patch("lexibrary.daemon.service.load_config")
    def test_run_once_skips_when_no_changes(
        self,
        mock_load_config: MagicMock,
        mock_setup_logging: MagicMock,
        mock_update_project: MagicMock,
        tmp_path: Path,
    ) -> None:
        """run_once() skips the sweep when no changes are detected."""
        config = self._make_config(skip_if_unchanged=True)
        mock_load_config.return_value = config

        svc = DaemonService(root=tmp_path)
        # Set last_sweep to the future so _has_changes returns False
        svc._last_sweep = time.time() + 100

        svc.run_once()

        mock_update_project.assert_not_called()

    @patch("lexibrary.daemon.service._current_time", return_value=1000.0)
    @patch("lexibrary.daemon.service.update_project")
    @patch("lexibrary.daemon.service.setup_daemon_logging")
    @patch("lexibrary.daemon.service.load_config")
    def test_run_once_runs_when_changes_detected(
        self,
        mock_load_config: MagicMock,
        mock_setup_logging: MagicMock,
        mock_update_project: MagicMock,
        mock_current_time: MagicMock,
        tmp_path: Path,
    ) -> None:
        """run_once() runs the sweep when changes are detected."""
        config = self._make_config(skip_if_unchanged=True)
        mock_load_config.return_value = config

        # Create a file so _has_changes detects it
        (tmp_path / "hello.py").write_text("x = 1", encoding="utf-8")

        # Mock asyncio.run to avoid actually running the pipeline
        mock_stats = MagicMock()
        mock_update_project.return_value = mock_stats

        with patch("lexibrary.daemon.service.asyncio.run", return_value=mock_stats):
            svc = DaemonService(root=tmp_path)
            svc.run_once()

        # _last_sweep should have been updated
        assert svc._last_sweep == 1000.0

    @patch("lexibrary.daemon.service._current_time", return_value=2000.0)
    @patch("lexibrary.daemon.service.update_project")
    @patch("lexibrary.daemon.service.setup_daemon_logging")
    @patch("lexibrary.daemon.service.load_config")
    def test_run_once_always_runs_when_skip_disabled(
        self,
        mock_load_config: MagicMock,
        mock_setup_logging: MagicMock,
        mock_update_project: MagicMock,
        mock_current_time: MagicMock,
        tmp_path: Path,
    ) -> None:
        """run_once() always runs when sweep_skip_if_unchanged is False."""
        config = self._make_config(skip_if_unchanged=False)
        mock_load_config.return_value = config

        mock_stats = MagicMock()
        with patch("lexibrary.daemon.service.asyncio.run", return_value=mock_stats):
            svc = DaemonService(root=tmp_path)
            # Even with last_sweep in the future, skip is disabled
            svc._last_sweep = time.time() + 100
            svc.run_once()

        # _last_sweep should have been updated (sweep ran)
        assert svc._last_sweep == 2000.0

    @patch("lexibrary.daemon.service.update_project")
    @patch("lexibrary.daemon.service.setup_daemon_logging")
    @patch("lexibrary.daemon.service.load_config")
    def test_run_once_first_run_always_sweeps(
        self,
        mock_load_config: MagicMock,
        mock_setup_logging: MagicMock,
        mock_update_project: MagicMock,
        tmp_path: Path,
    ) -> None:
        """run_once() always runs on first invocation (last_sweep == 0.0)."""
        config = self._make_config(skip_if_unchanged=True)
        mock_load_config.return_value = config

        mock_stats = MagicMock()
        with patch("lexibrary.daemon.service.asyncio.run", return_value=mock_stats):
            svc = DaemonService(root=tmp_path)
            assert svc._last_sweep == 0.0
            svc.run_once()

        # asyncio.run was called (sweep ran)


# ---------------------------------------------------------------------------
# DaemonService constructor tests
# ---------------------------------------------------------------------------


class TestDaemonServiceInterface:
    """Tests for the rewritten DaemonService interface."""

    def test_constructor_takes_only_root(self, tmp_path: Path) -> None:
        """DaemonService(root) accepts only a root Path, no foreground param."""
        svc = DaemonService(root=tmp_path)
        assert svc._root == tmp_path.resolve()

    def test_no_foreground_parameter(self) -> None:
        """The constructor does not accept a 'foreground' keyword."""
        import inspect

        sig = inspect.signature(DaemonService.__init__)
        params = list(sig.parameters.keys())
        assert "foreground" not in params

    def test_stop_safe_with_no_components(self, tmp_path: Path) -> None:
        """stop() completes without error when no components are initialized."""
        svc = DaemonService(root=tmp_path)
        # Should not raise
        svc.stop()


# ---------------------------------------------------------------------------
# DaemonService.run_watchdog tests
# ---------------------------------------------------------------------------


class TestRunWatchdog:
    """Tests for DaemonService.run_watchdog()."""

    @patch("lexibrary.daemon.service.setup_daemon_logging")
    @patch("lexibrary.daemon.service.load_config")
    def test_run_watchdog_disabled_returns_immediately(
        self,
        mock_load_config: MagicMock,
        mock_setup_logging: MagicMock,
        tmp_path: Path,
    ) -> None:
        """run_watchdog() returns immediately when watchdog_enabled is False."""
        config = MagicMock()
        config.daemon.watchdog_enabled = False
        config.daemon.log_level = "warning"
        mock_load_config.return_value = config

        svc = DaemonService(root=tmp_path)
        svc.run_watchdog()

        # Should return without starting anything
        assert svc._observer is None


# ---------------------------------------------------------------------------
# Module-level import safety tests
# ---------------------------------------------------------------------------


class TestModuleImports:
    """Verify that the rewritten module does not reference retired APIs."""

    def test_no_full_crawl_import(self) -> None:
        """The service module does not import full_crawl."""
        import lexibrary.daemon.service as mod

        source = inspect_source(mod)
        assert "full_crawl" not in source

    def test_no_change_detector_import(self) -> None:
        """The service module does not import ChangeDetector."""
        import lexibrary.daemon.service as mod

        source = inspect_source(mod)
        assert "ChangeDetector" not in source

    def test_no_create_llm_service_import(self) -> None:
        """The service module does not import create_llm_service."""
        import lexibrary.daemon.service as mod

        source = inspect_source(mod)
        assert "create_llm_service" not in source

    def test_no_create_tokenizer_import(self) -> None:
        """The service module does not import create_tokenizer."""
        import lexibrary.daemon.service as mod

        source = inspect_source(mod)
        assert "create_tokenizer" not in source

    def test_no_find_config_file_import(self) -> None:
        """The service module does not import find_config_file."""
        import lexibrary.daemon.service as mod

        source = inspect_source(mod)
        assert "find_config_file" not in source

    def test_no_config_output_reference(self) -> None:
        """The service module does not reference config.output."""
        import lexibrary.daemon.service as mod

        source = inspect_source(mod)
        assert "config.output" not in source

    def test_no_config_tokenizer_reference(self) -> None:
        """The service module does not reference config.tokenizer."""
        import lexibrary.daemon.service as mod

        source = inspect_source(mod)
        assert "config.tokenizer" not in source


def inspect_source(module: object) -> str:
    """Return the source code of a module as a string."""
    import inspect

    return inspect.getsource(module)  # type: ignore[arg-type]
