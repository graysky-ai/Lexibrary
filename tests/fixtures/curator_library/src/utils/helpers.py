"""Utility helpers for the application."""
from __future__ import annotations


def slugify(text: str) -> str:
    """Convert text to a URL-friendly slug."""
    return text.lower().replace(" ", "-")


def truncate(text: str, max_length: int = 100) -> str:
    """Truncate text to max_length with ellipsis."""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."
