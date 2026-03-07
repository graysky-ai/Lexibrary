"""Concept-file comment operations.

Thin layer on top of the shared comment primitives in
:mod:`lexibrary.lifecycle.comments`.  These functions accept a
*concept slug* and a *project root*, resolve the concept file path
inside ``.lexibrary/concepts/``, derive the sibling
``.comments.yaml`` path, and delegate to the generic read/append/count
helpers.

Public API
----------
- :func:`concept_comment_path` -- derive ``.comments.yaml`` from a
  concept ``.md`` path
- :func:`append_concept_comment` -- append a comment for a concept
- :func:`read_concept_comments` -- read all comments for a concept
- :func:`concept_comment_count` -- count comments for a concept
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from lexibrary.lifecycle.comments import append_comment, comment_count, read_comments
from lexibrary.lifecycle.models import ArtefactComment

CONCEPTS_DIR = "concepts"
"""Subdirectory name under ``.lexibrary/`` where concept files live."""


def _resolve_concept_path(project_root: Path, slug: str) -> Path:
    """Resolve a concept slug to its ``.md`` file path.

    Parameters
    ----------
    project_root:
        Absolute path to the project root.
    slug:
        The concept slug (PascalCase filename stem, e.g. ``"MyTopic"``).

    Returns
    -------
    Path
        Absolute path to the concept ``.md`` file.

    Raises
    ------
    FileNotFoundError
        If the resolved concept file does not exist.
    """
    concept_path = project_root / ".lexibrary" / CONCEPTS_DIR / f"{slug}.md"
    if not concept_path.exists():
        msg = f"Concept file not found: {concept_path}"
        raise FileNotFoundError(msg)
    return concept_path


def concept_comment_path(concept_md_path: Path) -> Path:
    """Derive the ``.comments.yaml`` path from a concept file path.

    Replaces the ``.md`` suffix with ``.comments.yaml``::

        .lexibrary/concepts/MyTopic.md
        -> .lexibrary/concepts/MyTopic.comments.yaml

    Parameters
    ----------
    concept_md_path:
        Absolute or relative path to the concept file (must end in
        ``.md``).

    Returns
    -------
    Path
        Path to the sibling comment file.
    """
    return concept_md_path.with_suffix(".comments.yaml")


def append_concept_comment(
    project_root: Path,
    slug: str,
    body: str,
) -> None:
    """Append a comment to a concept's comment file.

    Resolves the *slug* to its concept ``.md`` file under
    ``.lexibrary/concepts/``, derives the sibling ``.comments.yaml``
    path, and appends a new
    :class:`~lexibrary.lifecycle.models.ArtefactComment` with the
    current UTC timestamp.

    The ``.comments.yaml`` file is created on first comment.

    Parameters
    ----------
    project_root:
        Absolute path to the project root.
    slug:
        The concept slug (PascalCase filename stem).
    body:
        Free-form comment text.

    Raises
    ------
    FileNotFoundError
        If the concept ``.md`` file does not exist.
    """
    concept_path = _resolve_concept_path(project_root, slug)
    comment_file = concept_comment_path(concept_path)

    comment = ArtefactComment(
        body=body,
        date=datetime.now(tz=UTC),
    )

    append_comment(comment_file, comment)


def read_concept_comments(
    project_root: Path,
    slug: str,
) -> list[ArtefactComment]:
    """Read all comments for a concept from its comment file.

    Parameters
    ----------
    project_root:
        Absolute path to the project root.
    slug:
        The concept slug (PascalCase filename stem).

    Returns
    -------
    list[ArtefactComment]
        Comments in file order (oldest first).  Returns an empty list
        if the ``.comments.yaml`` file does not exist.

    Raises
    ------
    FileNotFoundError
        If the concept ``.md`` file does not exist.
    """
    concept_path = _resolve_concept_path(project_root, slug)
    comment_file = concept_comment_path(concept_path)
    return read_comments(comment_file)


def concept_comment_count(
    project_root: Path,
    slug: str,
) -> int:
    """Count the number of comments for a concept.

    Parameters
    ----------
    project_root:
        Absolute path to the project root.
    slug:
        The concept slug (PascalCase filename stem).

    Returns
    -------
    int
        Number of comments.  Returns ``0`` if the ``.comments.yaml``
        file does not exist.

    Raises
    ------
    FileNotFoundError
        If the concept ``.md`` file does not exist.
    """
    concept_path = _resolve_concept_path(project_root, slug)
    comment_file = concept_comment_path(concept_path)
    return comment_count(comment_file)
