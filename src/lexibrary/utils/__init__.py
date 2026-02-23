"""Utility functions for Lexibrary."""

from __future__ import annotations

from lexibrary.utils.hashing import hash_file
from lexibrary.utils.languages import detect_language
from lexibrary.utils.logging import setup_logging
from lexibrary.utils.root import find_project_root

__all__ = [
    "detect_language",
    "hash_file",
    "setup_logging",
    "find_project_root",
]
