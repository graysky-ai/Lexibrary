"""Marker-based section detection and replacement for agent rule files.

Lexibrary manages its own section in shared files like ``CLAUDE.md`` and
``AGENTS.md`` using HTML comment markers.  This module provides utilities
to detect, replace, and append marker-delimited sections without disturbing
user-authored content outside the markers.
"""

from __future__ import annotations

import re

MARKER_START = "<!-- lexibrary:start -->"
MARKER_END = "<!-- lexibrary:end -->"

_SECTION_RE = re.compile(
    re.escape(MARKER_START) + r".*?" + re.escape(MARKER_END),
    re.DOTALL,
)


def has_lexibrary_section(content: str) -> bool:
    """Return ``True`` if *content* contains both start and end markers.

    Both :data:`MARKER_START` and :data:`MARKER_END` must be present for
    the section to be considered valid.

    Args:
        content: Full text content of the file to inspect.

    Returns:
        Whether a complete Lexibrary marker pair exists.
    """
    return MARKER_START in content and MARKER_END in content


def replace_lexibrary_section(content: str, new_section: str) -> str:
    """Replace the marker-delimited section with *new_section*.

    Everything between (and including) the start and end markers is replaced
    with *new_section* wrapped in fresh markers.  Content outside the markers
    is preserved unchanged.

    Args:
        content: Full text content of the file.
        new_section: New content to place between the markers.

    Returns:
        Updated file content with the Lexibrary section replaced.
    """
    wrapped = _wrap_in_markers(new_section)
    return _SECTION_RE.sub(wrapped, content, count=1)


def append_lexibrary_section(content: str, new_section: str) -> str:
    """Append a marker-delimited section to the end of *content*.

    If *content* is non-empty, a blank line separator is inserted before
    the marker block.  If *content* is empty, only the marker block is
    returned.

    Args:
        content: Existing file content (may be empty).
        new_section: Content to wrap in markers and append.

    Returns:
        File content with the marker-delimited section appended.
    """
    wrapped = _wrap_in_markers(new_section)
    if not content:
        return wrapped
    # Ensure a single trailing newline before the marker block
    return content.rstrip("\n") + "\n\n" + wrapped


def _wrap_in_markers(section: str) -> str:
    """Wrap *section* text between start and end markers.

    Args:
        section: Content to place between the markers.

    Returns:
        Marker-delimited block with consistent formatting.
    """
    return f"{MARKER_START}\n{section}\n{MARKER_END}"
