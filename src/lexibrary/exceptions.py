"""Project-level exception classes for Lexibrary."""

from __future__ import annotations


class LexibraryNotFoundError(Exception):
    """Raised when no .lexibrary/ directory is found walking up from the start path."""
