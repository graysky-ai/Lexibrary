"""Change detection for source files against their existing design files.

Compares current source file hashes against the metadata footer in the
corresponding design file to classify what kind of update is needed.
"""

from __future__ import annotations

import hashlib
from enum import Enum
from pathlib import Path

from lexibrary.artifacts.design_file_parser import (
    _FOOTER_RE,
    parse_design_file_metadata,
)
from lexibrary.utils.paths import mirror_path


class ChangeLevel(Enum):
    """Classification of how a source file has changed relative to its design file."""

    UNCHANGED = "unchanged"
    AGENT_UPDATED = "agent_updated"
    CONTENT_ONLY = "content_only"
    CONTENT_CHANGED = "content_changed"
    INTERFACE_CHANGED = "interface_changed"
    NEW_FILE = "new_file"


def _compute_design_content_hash(design_file_path: Path) -> str | None:
    """Compute SHA-256 of design file content excluding the HTML comment footer.

    The design hash covers only frontmatter + body so that footer-only updates
    (hash refreshes) do not trigger false agent-edit detection.

    Returns None if the file doesn't exist or can't be read.
    """
    if not design_file_path.exists():
        return None
    try:
        text = design_file_path.read_text(encoding="utf-8")
    except OSError:
        return None
    # Strip the footer before hashing
    content = _FOOTER_RE.sub("", text).rstrip("\n")
    return hashlib.sha256(content.encode()).hexdigest()


def check_change(
    source_path: Path,
    project_root: Path,
    content_hash: str,
    interface_hash: str | None,
) -> ChangeLevel:
    """Classify how a source file has changed relative to its existing design file.

    Args:
        source_path: Absolute path to the source file.
        project_root: Absolute path to the project root.
        content_hash: SHA-256 hash of the current source file content.
        interface_hash: SHA-256 hash of the current public interface, or None for
            non-code files (no tree-sitter grammar).

    Returns:
        A ChangeLevel indicating what kind of update (if any) is needed.
    """
    design_path = mirror_path(project_root, source_path)

    # No design file at all -> new file
    if not design_path.exists():
        return ChangeLevel.NEW_FILE

    # Design file exists but has no metadata footer -> agent authored from scratch
    metadata = parse_design_file_metadata(design_path)
    if metadata is None:
        return ChangeLevel.AGENT_UPDATED

    # Source unchanged
    if content_hash == metadata.source_hash:
        return ChangeLevel.UNCHANGED

    # Source changed -- check if agent edited the design file
    current_design_hash = _compute_design_content_hash(design_path)
    if (
        current_design_hash is not None
        and metadata.design_hash is not None
        and current_design_hash != metadata.design_hash
    ):
        return ChangeLevel.AGENT_UPDATED

    # Source changed, design file not agent-edited
    # Non-code file (no interface hash)
    if interface_hash is None:
        return ChangeLevel.CONTENT_CHANGED

    # Code file -- compare interface hashes
    if interface_hash == metadata.interface_hash:
        return ChangeLevel.CONTENT_ONLY

    return ChangeLevel.INTERFACE_CHANGED
