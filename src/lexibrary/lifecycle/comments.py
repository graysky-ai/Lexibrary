"""Read, write, and count operations for artefact comment files.

All artefact types store feedback in sibling ``.comments.yaml`` files.
This module provides the shared file-level operations:

- :func:`read_comments` -- load comments from an existing file
- :func:`append_comment` -- add a comment, creating the file if needed
- :func:`comment_count` -- lightweight count without full parsing
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml
from pydantic import ValidationError

from lexibrary.lifecycle.models import ArtefactComment, ArtefactCommentFile

logger = logging.getLogger(__name__)


def read_comments(path: Path) -> list[ArtefactComment]:
    """Read all comments from a ``.comments.yaml`` file.

    Parameters
    ----------
    path:
        Absolute path to the ``.comments.yaml`` file.

    Returns
    -------
    list[ArtefactComment]
        Comments in file order (oldest first).  Returns an empty list
        if the file does not exist, is empty, or cannot be parsed.
    """
    if not path.exists():
        return []

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        logger.warning("Failed to read comment file: %s", path)
        return []

    if not text.strip():
        return []

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        logger.warning("Malformed YAML in comment file: %s", path)
        return []

    if not isinstance(data, dict):
        logger.warning("Unexpected YAML structure in comment file: %s", path)
        return []

    try:
        comment_file = ArtefactCommentFile.model_validate(data)
    except ValidationError:
        logger.warning("Validation failed for comment file: %s", path)
        return []

    return comment_file.comments


def append_comment(path: Path, comment: ArtefactComment) -> None:
    """Append a comment to a ``.comments.yaml`` file.

    Creates the file (and parent directories) if it does not exist.
    Existing comments are preserved; the new comment is added to the
    end of the ``comments`` list.

    Parameters
    ----------
    path:
        Absolute path to the ``.comments.yaml`` file.
    comment:
        The comment to append.
    """
    existing = read_comments(path)
    existing.append(comment)

    comment_file = ArtefactCommentFile(comments=existing)

    # Serialize to YAML with ISO timestamps as strings.
    data = comment_file.model_dump(mode="json")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump(data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


def comment_count(path: Path) -> int:
    """Return the number of comments in a ``.comments.yaml`` file.

    Uses a lightweight approach: loads the YAML and counts the
    ``comments`` list length.  Returns ``0`` if the file does not
    exist, is empty, or cannot be parsed.

    Parameters
    ----------
    path:
        Absolute path to the ``.comments.yaml`` file.

    Returns
    -------
    int
        Number of comments in the file.
    """
    if not path.exists():
        return 0

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return 0

    if not text.strip():
        return 0

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return 0

    if not isinstance(data, dict):
        return 0

    comments_raw = data.get("comments")
    if not isinstance(comments_raw, list):
        return 0

    return len(comments_raw)
