"""Logging configuration utilities."""

from __future__ import annotations

import logging
from pathlib import Path

from rich.logging import RichHandler


def setup_logging(
    verbose: bool = False,
    log_file: Path | str | None = None,
) -> None:
    """
    Configure logging with Rich handler for console and optional file handler.

    Args:
        verbose: If True, set logging level to DEBUG. Otherwise INFO.
        log_file: Optional path to log file for persistent logs.
    """
    # Determine log level
    level = logging.DEBUG if verbose else logging.INFO

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear existing handlers
    root_logger.handlers.clear()

    # Add Rich handler for console output
    console_handler = RichHandler(
        rich_tracebacks=True,
        show_time=False,  # Rich shows its own time
        show_path=False,
    )
    console_handler.setLevel(level)
    root_logger.addHandler(console_handler)

    # Add file handler if specified
    if log_file is not None:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)
