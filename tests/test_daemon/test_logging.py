"""Tests for daemon logging setup."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

from lexibrary.daemon.logging import setup_daemon_logging


@pytest.fixture(autouse=True)
def _clean_logger() -> Iterator[None]:
    """Remove all handlers from the 'lexibrary' logger between tests."""
    logger = logging.getLogger("lexibrary")
    yield
    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)
    logger.setLevel(logging.WARNING)


def test_log_file_created(tmp_path: Path) -> None:
    """setup_daemon_logging() creates the log file under project_root."""
    logger = setup_daemon_logging(tmp_path)
    logger.info("hello")

    log_file = tmp_path / ".lexibrary" / "daemon.log"
    assert log_file.exists()
    contents = log_file.read_text(encoding="utf-8")
    assert "hello" in contents


def test_rotating_file_handler_attached(tmp_path: Path) -> None:
    """A RotatingFileHandler is attached to the lexibrary logger."""
    logger = setup_daemon_logging(tmp_path)

    rotating_handlers = [h for h in logger.handlers if isinstance(h, RotatingFileHandler)]
    assert len(rotating_handlers) == 1

    handler = rotating_handlers[0]
    assert handler.maxBytes == 5 * 1024 * 1024
    assert handler.backupCount == 3


def test_rotation_config(tmp_path: Path) -> None:
    """RotatingFileHandler has maxBytes=5MB and backupCount=3."""
    logger = setup_daemon_logging(tmp_path)

    handler = next(h for h in logger.handlers if isinstance(h, RotatingFileHandler))
    assert handler.maxBytes == 5 * 1024 * 1024
    assert handler.backupCount == 3


def test_configurable_log_level_debug(tmp_path: Path) -> None:
    """Passing log_level='debug' sets both logger and handler to DEBUG."""
    logger = setup_daemon_logging(tmp_path, log_level="debug")

    assert logger.level == logging.DEBUG

    handler = next(h for h in logger.handlers if isinstance(h, RotatingFileHandler))
    assert handler.level == logging.DEBUG


def test_configurable_log_level_warning(tmp_path: Path) -> None:
    """Passing log_level='warning' sets both logger and handler to WARNING."""
    logger = setup_daemon_logging(tmp_path, log_level="warning")

    assert logger.level == logging.WARNING

    handler = next(h for h in logger.handlers if isinstance(h, RotatingFileHandler))
    assert handler.level == logging.WARNING


def test_default_log_level_is_info(tmp_path: Path) -> None:
    """Default log_level is 'info', so logger and handler use INFO."""
    logger = setup_daemon_logging(tmp_path)

    assert logger.level == logging.INFO

    handler = next(h for h in logger.handlers if isinstance(h, RotatingFileHandler))
    assert handler.level == logging.INFO


def test_no_console_handler_added(tmp_path: Path) -> None:
    """setup_daemon_logging() does NOT add a StreamHandler (console)."""
    logger = setup_daemon_logging(tmp_path)

    stream_handlers = [
        h
        for h in logger.handlers
        if isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler)
    ]
    # There should be no pure StreamHandler added by our function.
    # Note: the root logger may have handlers, but we check the
    # 'lexibrary' logger specifically.
    assert len(stream_handlers) == 0


def test_log_level_case_insensitive(tmp_path: Path) -> None:
    """log_level parameter is case-insensitive."""
    logger = setup_daemon_logging(tmp_path, log_level="DEBUG")
    assert logger.level == logging.DEBUG
