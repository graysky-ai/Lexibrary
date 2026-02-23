"""Daemon-specific logging setup with rotating file handler."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_FILENAME = "daemon.log"
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_BACKUP_COUNT = 3
_LOG_FORMAT = "%(asctime)s %(name)s %(levelname)s %(message)s"


def setup_daemon_logging(
    project_root: Path,
    log_level: str = "info",
) -> logging.Logger:
    """Configure rotating file logging for the daemon.

    Attaches a ``RotatingFileHandler`` to the ``lexibrary`` logger that
    writes to ``<project_root>/.lexibrary/daemon.log``.  No console handler is
    added -- callers should attach their own if needed.

    Args:
        project_root: The project root directory where the log file will
            be created.
        log_level: Python log-level name (case-insensitive).  Defaults to
            ``"info"``.

    Returns:
        The configured ``lexibrary`` logger instance.
    """
    log_dir = project_root / ".lexibrary"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / _LOG_FILENAME
    level = getattr(logging, log_level.upper(), logging.INFO)

    logger = logging.getLogger("lexibrary")
    logger.setLevel(level)

    handler = RotatingFileHandler(
        filename=str(log_path),
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))

    logger.addHandler(handler)

    return logger
