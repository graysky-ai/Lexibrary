"""Design-file comment operations.

Thin layer on top of the shared comment primitives in
:mod:`lexibrary.lifecycle.comments`.  These functions accept a
*source file* path (the file being documented) and a *project root*,
resolve the design-file mirror path, derive the sibling
``.comments.yaml`` path, and delegate to the generic read/append/count
helpers.

Public API
----------
- :func:`design_comment_path` -- derive ``.comments.yaml`` from a
  design-file ``.md`` path
- :func:`append_design_comment` -- append a comment for a source file
- :func:`read_design_comments` -- read all comments for a source file
- :func:`design_comment_count` -- count comments for a source file
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from lexibrary.lifecycle.comments import append_comment, comment_count, read_comments
from lexibrary.lifecycle.models import ArtefactComment
from lexibrary.utils.paths import mirror_path


def design_comment_path(design_path: Path) -> Path:
    """Derive the ``.comments.yaml`` path from a design file path.

    Replaces the ``.md`` suffix with ``.comments.yaml``::

        .lexibrary/designs/src/auth/login.py.md
        -> .lexibrary/designs/src/auth/login.py.comments.yaml

    Parameters
    ----------
    design_path:
        Absolute or relative path to the design file (must end in
        ``.md``).

    Returns
    -------
    Path
        Path to the sibling comment file.
    """
    return design_path.with_suffix(".comments.yaml")


def append_design_comment(
    project_root: Path,
    source_path: Path,
    body: str,
) -> None:
    """Append a comment to a source file's design comment file.

    Resolves the *source_path* to its design file via
    :func:`~lexibrary.utils.paths.mirror_path`, derives the sibling
    ``.comments.yaml`` path, and appends a new
    :class:`~lexibrary.lifecycle.models.ArtefactComment` with the
    current UTC timestamp.

    The ``.comments.yaml`` file is created on first comment.

    Parameters
    ----------
    project_root:
        Absolute path to the project root.
    source_path:
        Absolute or project-relative path to the source file.
    body:
        Free-form comment text.
    """
    design_path = mirror_path(project_root, source_path)
    comment_file_path = design_comment_path(design_path)

    comment = ArtefactComment(
        body=body,
        date=datetime.now(tz=UTC),
    )

    append_comment(comment_file_path, comment)


def read_design_comments(
    project_root: Path,
    source_path: Path,
) -> list[ArtefactComment]:
    """Read all comments for a source file from its design comment file.

    Parameters
    ----------
    project_root:
        Absolute path to the project root.
    source_path:
        Absolute or project-relative path to the source file.

    Returns
    -------
    list[ArtefactComment]
        Comments in file order (oldest first).  Returns an empty list
        if the ``.comments.yaml`` file does not exist.
    """
    design_path = mirror_path(project_root, source_path)
    comment_file_path = design_comment_path(design_path)
    return read_comments(comment_file_path)


def design_comment_count(
    project_root: Path,
    source_path: Path,
) -> int:
    """Count the number of comments for a source file.

    Parameters
    ----------
    project_root:
        Absolute path to the project root.
    source_path:
        Absolute or project-relative path to the source file.

    Returns
    -------
    int
        Number of comments.  Returns ``0`` if the ``.comments.yaml``
        file does not exist.
    """
    design_path = mirror_path(project_root, source_path)
    comment_file_path = design_comment_path(design_path)
    return comment_count(comment_file_path)
