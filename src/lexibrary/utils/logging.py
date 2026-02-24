"""Logging configuration utilities."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from rich.logging import RichHandler


class JSONFormatter(logging.Formatter):
    """Emit log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0] is not None:
            entry["exception"] = self.formatException(record.exc_info)
        # Include extra fields if present
        for key in ("phase", "path", "error_type"):
            if hasattr(record, key):
                entry[key] = getattr(record, key)
        return json.dumps(entry)


def setup_logging(
    verbose: bool = False,
    log_file: Path | str | None = None,
    log_format: str = "rich",
) -> None:
    """
    Configure logging with Rich handler for console and optional file handler.

    Args:
        verbose: If True, set logging level to DEBUG. Otherwise INFO.
        log_file: Optional path to log file for persistent logs.
        log_format: Log format to use: "rich" (default) or "json".
            Can also be set via LEXIBRARY_LOG_FORMAT env var.
    """
    # Allow env var override
    log_format = os.environ.get("LEXIBRARY_LOG_FORMAT", log_format)

    # Determine log level
    level = logging.DEBUG if verbose else logging.INFO

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear existing handlers
    root_logger.handlers.clear()

    if log_format == "json":
        # JSON formatter for machine-readable output
        json_handler = logging.StreamHandler()
        json_handler.setLevel(level)
        json_handler.setFormatter(JSONFormatter())
        root_logger.addHandler(json_handler)
    else:
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
