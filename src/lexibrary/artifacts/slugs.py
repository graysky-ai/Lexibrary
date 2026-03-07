"""Shared slug-generation utilities for Lexibrary artifacts."""

from __future__ import annotations

import re

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_MULTI_HYPHEN_RE = re.compile(r"-{2,}")

_MAX_SLUG_LENGTH = 60


def slugify(title: str) -> str:
    """Derive a filesystem-safe slug from an artifact title.

    Steps:
    1. Lowercase the title
    2. Replace spaces and non-alphanumeric characters with hyphens
    3. Collapse consecutive hyphens
    4. Strip leading/trailing hyphens
    5. Truncate to 60 characters at a word boundary
    """
    slug = title.lower()
    slug = _NON_ALNUM_RE.sub("-", slug)
    slug = _MULTI_HYPHEN_RE.sub("-", slug)
    slug = slug.strip("-")

    if len(slug) <= _MAX_SLUG_LENGTH:
        return slug

    # Truncate at a word boundary (hyphen boundary in slug)
    truncated = slug[:_MAX_SLUG_LENGTH]
    # Find last hyphen within the truncated portion
    last_hyphen = truncated.rfind("-")
    if last_hyphen > 0:
        truncated = truncated[:last_hyphen]
    return truncated.strip("-")


def concept_slug(title: str) -> str:
    """Derive a filesystem-safe slug from a concept title.

    Delegates to :func:`slugify`.
    """
    return slugify(title)
