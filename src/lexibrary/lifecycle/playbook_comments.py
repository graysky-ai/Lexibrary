"""Playbook-file comment operations.

Thin layer on top of the shared comment primitives in
:mod:`lexibrary.lifecycle.comments`.  These functions accept a
*playbook file* path, derive the sibling ``.comments.yaml`` path,
and delegate to the generic read/append/count helpers.

Public API
----------
- :func:`playbook_comment_path` -- derive ``.comments.yaml`` from a
  playbook ``.md`` path
- :func:`append_playbook_comment` -- append a comment for a playbook
- :func:`read_playbook_comments` -- read all comments for a playbook
- :func:`playbook_comment_count` -- count comments for a playbook
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from lexibrary.lifecycle.comments import append_comment, comment_count, read_comments
from lexibrary.lifecycle.models import ArtefactComment


def playbook_comment_path(playbook_path: Path) -> Path:
    """Derive the ``.comments.yaml`` path from a playbook file path.

    Replaces the ``.md`` suffix with ``.comments.yaml``::

        .lexibrary/playbooks/version-bump.md
        -> .lexibrary/playbooks/version-bump.comments.yaml

    Parameters
    ----------
    playbook_path:
        Absolute or relative path to the playbook file (must end in
        ``.md``).

    Returns
    -------
    Path
        Path to the sibling comment file.
    """
    return playbook_path.with_suffix(".comments.yaml")


def append_playbook_comment(
    playbook_path: Path,
    body: str,
) -> None:
    """Append a comment to a playbook's comment file.

    Derives the sibling ``.comments.yaml`` path from *playbook_path*
    and appends a new
    :class:`~lexibrary.lifecycle.models.ArtefactComment` with the
    current UTC timestamp.

    The ``.comments.yaml`` file is created on first comment.

    Parameters
    ----------
    playbook_path:
        Absolute path to the playbook ``.md`` file.
    body:
        Free-form comment text.
    """
    comment_file_path = playbook_comment_path(playbook_path)

    comment = ArtefactComment(
        body=body,
        date=datetime.now(tz=UTC),
    )

    append_comment(comment_file_path, comment)


def read_playbook_comments(
    playbook_path: Path,
) -> list[ArtefactComment]:
    """Read all comments for a playbook from its comment file.

    Parameters
    ----------
    playbook_path:
        Absolute path to the playbook ``.md`` file.

    Returns
    -------
    list[ArtefactComment]
        Comments in file order (oldest first).  Returns an empty list
        if the ``.comments.yaml`` file does not exist.
    """
    comment_file_path = playbook_comment_path(playbook_path)
    return read_comments(comment_file_path)


def playbook_comment_count(
    playbook_path: Path,
) -> int:
    """Count the number of comments for a playbook.

    Parameters
    ----------
    playbook_path:
        Absolute path to the playbook ``.md`` file.

    Returns
    -------
    int
        Number of comments.  Returns ``0`` if the ``.comments.yaml``
        file does not exist.
    """
    comment_file_path = playbook_comment_path(playbook_path)
    return comment_count(comment_file_path)
