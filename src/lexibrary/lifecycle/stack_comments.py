"""Stack-post comment operations.

Thin layer on top of the shared comment primitives in
:mod:`lexibrary.lifecycle.comments`.  These functions accept a
*stack post ID* (e.g. ``"ST-001"``) and a *project root*, resolve the
stack post file path inside ``.lexibrary/stack/``, derive the sibling
``.comments.yaml`` path, and delegate to the generic read/append/count
helpers.

Public API
----------
- :func:`stack_comment_path` -- derive ``.comments.yaml`` from a
  stack post ``.md`` path
- :func:`append_stack_comment` -- append a comment for a stack post
- :func:`read_stack_comments` -- read all comments for a stack post
- :func:`stack_comment_count` -- count comments for a stack post
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from lexibrary.lifecycle.comments import append_comment, comment_count, read_comments
from lexibrary.lifecycle.models import ArtefactComment

STACK_DIR = "stack"
"""Subdirectory name under ``.lexibrary/`` where stack posts live."""


def _resolve_post_path(project_root: Path, post_id: str) -> Path:
    """Resolve a stack post ID to its ``.md`` file path.

    Scans ``.lexibrary/stack/`` for a file matching the pattern
    ``<post_id>-*.md`` (e.g. ``ST-001-some-slug.md``).

    Parameters
    ----------
    project_root:
        Absolute path to the project root.
    post_id:
        The stack post ID (e.g. ``"ST-001"``).

    Returns
    -------
    Path
        Absolute path to the stack post ``.md`` file.

    Raises
    ------
    FileNotFoundError
        If no matching stack post file is found.
    """
    stack_dir = project_root / ".lexibrary" / STACK_DIR
    if stack_dir.is_dir():
        for f in stack_dir.glob(f"{post_id}-*.md"):
            return f
    msg = f"Stack post not found: {post_id}"
    raise FileNotFoundError(msg)


def stack_comment_path(post_md_path: Path) -> Path:
    """Derive the ``.comments.yaml`` path from a stack post file path.

    Replaces the ``.md`` suffix with ``.comments.yaml``::

        .lexibrary/stack/ST-001-some-slug.md
        -> .lexibrary/stack/ST-001-some-slug.comments.yaml

    Parameters
    ----------
    post_md_path:
        Absolute or relative path to the stack post file (must end in
        ``.md``).

    Returns
    -------
    Path
        Path to the sibling comment file.
    """
    return post_md_path.with_suffix(".comments.yaml")


def append_stack_comment(
    project_root: Path,
    post_id: str,
    body: str,
) -> None:
    """Append a comment to a stack post's comment file.

    Resolves the *post_id* to its stack post ``.md`` file under
    ``.lexibrary/stack/``, derives the sibling ``.comments.yaml``
    path, and appends a new
    :class:`~lexibrary.lifecycle.models.ArtefactComment` with the
    current UTC timestamp.

    The ``.comments.yaml`` file is created on first comment.

    Parameters
    ----------
    project_root:
        Absolute path to the project root.
    post_id:
        The stack post ID (e.g. ``"ST-001"``).
    body:
        Free-form comment text.

    Raises
    ------
    FileNotFoundError
        If no matching stack post file is found.
    """
    post_path = _resolve_post_path(project_root, post_id)
    comment_file = stack_comment_path(post_path)

    comment = ArtefactComment(
        body=body,
        date=datetime.now(tz=UTC),
    )

    append_comment(comment_file, comment)


def read_stack_comments(
    project_root: Path,
    post_id: str,
) -> list[ArtefactComment]:
    """Read all comments for a stack post from its comment file.

    Parameters
    ----------
    project_root:
        Absolute path to the project root.
    post_id:
        The stack post ID (e.g. ``"ST-001"``).

    Returns
    -------
    list[ArtefactComment]
        Comments in file order (oldest first).  Returns an empty list
        if the ``.comments.yaml`` file does not exist.

    Raises
    ------
    FileNotFoundError
        If no matching stack post file is found.
    """
    post_path = _resolve_post_path(project_root, post_id)
    comment_file = stack_comment_path(post_path)
    return read_comments(comment_file)


def stack_comment_count(
    project_root: Path,
    post_id: str,
) -> int:
    """Count the number of comments for a stack post.

    Parameters
    ----------
    project_root:
        Absolute path to the project root.
    post_id:
        The stack post ID (e.g. ``"ST-001"``).

    Returns
    -------
    int
        Number of comments.  Returns ``0`` if the ``.comments.yaml``
        file does not exist.

    Raises
    ------
    FileNotFoundError
        If no matching stack post file is found.
    """
    post_path = _resolve_post_path(project_root, post_id)
    comment_file = stack_comment_path(post_path)
    return comment_count(comment_file)
