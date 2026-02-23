"""Daemon service with three entry points for library maintenance.

Provides ``run_once`` (single sweep), ``run_watch`` (periodic sweeps),
and ``run_watchdog`` (deprecated real-time file watching).  Uses the
archivist pipeline (``update_project``) instead of the retired
crawler engine.

Watchdog imports are lazy -- the module loads and ``run_once`` /
``run_watch`` work even when the ``watchdog`` package is not installed.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import threading
from pathlib import Path
from types import FrameType

from rich.console import Console

from lexibrary.archivist.pipeline import update_project
from lexibrary.archivist.service import ArchivistService
from lexibrary.config.loader import load_config
from lexibrary.config.schema import LexibraryConfig
from lexibrary.daemon.logging import setup_daemon_logging
from lexibrary.daemon.scheduler import PeriodicSweep
from lexibrary.ignore import create_ignore_matcher
from lexibrary.llm.rate_limiter import RateLimiter
from lexibrary.utils.paths import LEXIBRARY_DIR

logger = logging.getLogger(__name__)
console = Console()

_PID_FILENAME = "daemon.pid"


def _has_changes(root: Path, last_sweep: float) -> bool:
    """Check whether any file under *root* has mtime newer than *last_sweep*.

    Uses ``os.scandir()`` for a fast stat walk.  Returns ``True`` on the
    first file found with a newer mtime (short-circuit).  Skips the
    ``.lexibrary/`` directory to avoid self-triggered loops.

    If *last_sweep* is ``0.0`` (first run), always returns ``True``.
    """
    if last_sweep == 0.0:
        return True

    lexibrary_abs = (root / LEXIBRARY_DIR).resolve()

    def _scan(directory: Path) -> bool:
        try:
            with os.scandir(directory) as it:
                for entry in it:
                    entry_path = Path(entry.path).resolve()

                    # Skip the .lexibrary directory entirely
                    if entry.is_dir(follow_symlinks=False):
                        if entry_path == lexibrary_abs:
                            continue
                        if _scan(entry_path):
                            return True
                    elif entry.is_file(follow_symlinks=False):
                        try:
                            if entry.stat().st_mtime > last_sweep:
                                return True
                        except OSError:
                            continue
        except OSError:
            pass
        return False

    return _scan(root)


class DaemonService:
    """Orchestrates library maintenance via sweep, periodic watch, or watchdog.

    Constructor accepts only a ``root`` path.  Call one of the three entry
    points to start:

    - ``run_once()`` -- single sweep then exit
    - ``run_watch()`` -- periodic sweeps, blocks until interrupted
    - ``run_watchdog()`` -- deprecated real-time file watching
    """

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._shutdown_event = threading.Event()
        self._observer: object | None = None
        self._sweep: PeriodicSweep | None = None
        self._last_sweep: float = 0.0

    # -- public entry points ------------------------------------------------

    def run_once(self) -> None:
        """Run a single project update sweep, then return.

        Respects ``sweep_skip_if_unchanged``: if enabled and no files have
        an mtime newer than the last sweep, the sweep is skipped.
        """
        config = self._load_config()
        setup_daemon_logging(self._root, config.daemon.log_level)

        if config.daemon.sweep_skip_if_unchanged and not _has_changes(self._root, self._last_sweep):
            console.print("[dim]No changes detected -- skipping sweep.[/dim]")
            logger.debug("run_once: no changes detected, skipping sweep")
            return

        self._run_sweep(config)
        console.print("[green]Sweep complete.[/green]")

    def run_watch(self) -> None:
        """Run periodic sweeps in the foreground until interrupted.

        Blocks on a shutdown event.  SIGTERM and SIGINT trigger graceful
        shutdown.
        """
        config = self._load_config()
        setup_daemon_logging(self._root, config.daemon.log_level)

        interval = float(config.daemon.sweep_interval_seconds)

        self._sweep = PeriodicSweep(
            interval=interval,
            callback=lambda: self._periodic_callback(config),
        )

        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        self._sweep.start()
        console.print(
            f"[green]Watching[/green] [cyan]{self._root}[/cyan] "
            f"(sweep every {interval:.0f}s). Press Ctrl+C to stop."
        )
        logger.info("run_watch started, sweep every %.0fs", interval)

        self._shutdown_event.wait()
        self.stop()

    def run_watchdog(self) -> None:
        """Start the deprecated real-time file watchdog.

        Requires ``daemon.watchdog_enabled: true`` in config.  If disabled,
        prints a message suggesting ``lexictl sweep --watch`` and returns.
        Watchdog dependencies are imported lazily.
        """
        config = self._load_config()
        setup_daemon_logging(self._root, config.daemon.log_level)

        if not config.daemon.watchdog_enabled:
            console.print(
                "[yellow]Watchdog mode is disabled.[/yellow]\n"
                "Use [cyan]lexictl sweep --watch[/cyan] for periodic sweeps, "
                "or set [cyan]daemon.watchdog_enabled: true[/cyan] in config."
            )
            return

        console.print(
            "[yellow]Warning:[/yellow] Watchdog mode is deprecated. "
            "Consider using [cyan]lexictl sweep --watch[/cyan] instead."
        )

        # Lazy imports -- only needed for watchdog mode
        try:
            from watchdog.observers import Observer

            from lexibrary.daemon.debouncer import Debouncer
            from lexibrary.daemon.watcher import LexibraryEventHandler
        except ImportError as exc:
            msg = (
                "The 'watchdog' package is required for watchdog mode. "
                "Install it with: pip install watchdog"
            )
            raise ImportError(msg) from exc

        ignore_matcher = create_ignore_matcher(config, self._root)
        interval = float(config.daemon.sweep_interval_seconds)

        debouncer = Debouncer(
            delay=config.daemon.debounce_seconds,
            callback=lambda dirs: self._run_sweep(config),
        )

        self._sweep = PeriodicSweep(
            interval=interval,
            callback=lambda: self._periodic_callback(config),
        )

        handler = LexibraryEventHandler(
            debouncer=debouncer,
            ignore_matcher=ignore_matcher,
        )
        observer = Observer()
        observer.schedule(handler, str(self._root), recursive=True)
        self._observer = observer

        self._write_pid_file()

        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        observer.start()
        self._sweep.start()

        pid = os.getpid()
        console.print(
            f"[green]Daemon running[/green] (PID {pid}) watching "
            f"[cyan]{self._root}[/cyan]\nPress Ctrl+C to stop."
        )
        logger.info("Watchdog daemon started (PID %d) watching %s", pid, self._root)

        self._shutdown_event.wait()
        self.stop()

    # -- lifecycle ----------------------------------------------------------

    def stop(self) -> None:
        """Gracefully stop all daemon components."""
        logger.info("Daemon shutting down...")

        if self._sweep is not None:
            self._sweep.stop()

        if self._observer is not None:
            # Observer has stop/join -- call via attribute to satisfy typing
            observer = self._observer
            if hasattr(observer, "stop"):
                observer.stop()
            if hasattr(observer, "join"):
                observer.join(timeout=5.0)

        self._remove_pid_file()
        console.print("[yellow]Daemon stopped.[/yellow]")
        logger.info("Daemon stopped.")

    # -- internal helpers ---------------------------------------------------

    def _load_config(self) -> LexibraryConfig:
        """Load project configuration from the project root."""
        return load_config(project_root=self._root)

    def _signal_handler(self, signum: int, frame: FrameType | None) -> None:
        """Handle SIGTERM/SIGINT by triggering shutdown."""
        logger.info("Received signal %d, shutting down...", signum)
        self._shutdown_event.set()

    def _write_pid_file(self) -> None:
        """Write the current PID to the PID file."""
        pid_dir = self._root / ".lexibrary"
        pid_dir.mkdir(parents=True, exist_ok=True)
        pid_path = pid_dir / _PID_FILENAME
        pid_path.write_text(str(os.getpid()), encoding="utf-8")

    def _remove_pid_file(self) -> None:
        """Remove the PID file, tolerating if already gone."""
        pid_path = self._root / ".lexibrary" / _PID_FILENAME
        pid_path.unlink(missing_ok=True)

    def _run_sweep(self, config: LexibraryConfig) -> None:
        """Execute a single project update sweep via the archivist pipeline."""
        logger.info("Sweep triggered")
        try:
            archivist = ArchivistService(
                rate_limiter=RateLimiter(),
                config=config.llm,
            )
            stats = asyncio.run(
                update_project(
                    project_root=self._root,
                    config=config,
                    archivist=archivist,
                )
            )
            self._last_sweep = _current_time()
            logger.info(
                "Sweep complete: %d scanned, %d updated, %d created, %d unchanged, %d failed",
                stats.files_scanned,
                stats.files_updated,
                stats.files_created,
                stats.files_unchanged,
                stats.files_failed,
            )
        except Exception:
            logger.exception("Sweep failed")

    def _periodic_callback(self, config: LexibraryConfig) -> None:
        """Callback for PeriodicSweep: check for changes then sweep."""
        if config.daemon.sweep_skip_if_unchanged and not _has_changes(self._root, self._last_sweep):
            logger.debug("Periodic sweep: no changes detected, skipping")
            return
        self._run_sweep(config)


def _current_time() -> float:
    """Return the current time as a float (seconds since epoch).

    Extracted into a function for testability.
    """
    import time

    return time.time()
