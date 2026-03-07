"""Convention-file comment operations.

Thin layer on top of the shared comment primitives in
:mod:`lexibrary.lifecycle.comments`.  These functions accept a
*convention file* path, derive the sibling ``.comments.yaml`` path,
and delegate to the generic read/append/count helpers.

Public API
----------
- :func:`convention_comment_path` -- derive ``.comments.yaml`` from a
  convention ``.md`` path
- :func:`append_convention_comment` -- append a comment for a convention
- :func:`read_convention_comments` -- read all comments for a convention
- :func:`convention_comment_count` -- count comments for a convention
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from lexibrary.lifecycle.comments import append_comment, comment_count, read_comments
from lexibrary.lifecycle.models import ArtefactComment


def convention_comment_path(convention_path: Path) -> Path:
    """Derive the ``.comments.yaml`` path from a convention file path.

    Replaces the ``.md`` suffix with ``.comments.yaml``::

        .lexibrary/conventions/use-dataclasses.md
        -> .lexibrary/conventions/use-dataclasses.comments.yaml

    Parameters
    ----------
    convention_path:
        Absolute or relative path to the convention file (must end in
        ``.md``).

    Returns
    -------
    Path
        Path to the sibling comment file.
    """
    return convention_path.with_suffix(".comments.yaml")


def append_convention_comment(
    convention_path: Path,
    body: str,
) -> None:
    """Append a comment to a convention's comment file.

    Derives the sibling ``.comments.yaml`` path from *convention_path*
    and appends a new
    :class:`~lexibrary.lifecycle.models.ArtefactComment` with the
    current UTC timestamp.

    The ``.comments.yaml`` file is created on first comment.

    Parameters
    ----------
    convention_path:
        Absolute path to the convention ``.md`` file.
    body:
        Free-form comment text.
    """
    comment_file_path = convention_comment_path(convention_path)

    comment = ArtefactComment(
        body=body,
        date=datetime.now(tz=UTC),
    )

    append_comment(comment_file_path, comment)


def read_convention_comments(
    convention_path: Path,
) -> list[ArtefactComment]:
    """Read all comments for a convention from its comment file.

    Parameters
    ----------
    convention_path:
        Absolute path to the convention ``.md`` file.

    Returns
    -------
    list[ArtefactComment]
        Comments in file order (oldest first).  Returns an empty list
        if the ``.comments.yaml`` file does not exist.
    """
    comment_file_path = convention_comment_path(convention_path)
    return read_comments(comment_file_path)


def convention_comment_count(
    convention_path: Path,
) -> int:
    """Count the number of comments for a convention.

    Parameters
    ----------
    convention_path:
        Absolute path to the convention ``.md`` file.

    Returns
    -------
    int
        Number of comments.  Returns ``0`` if the ``.comments.yaml``
        file does not exist.
    """
    comment_file_path = convention_comment_path(convention_path)
    return comment_count(comment_file_path)
