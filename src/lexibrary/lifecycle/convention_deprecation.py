"""Convention deprecation primitives.

Provides both *soft-deprecate* (frontmatter status flip) and
*hard-delete* (TTL-expired removal) operations for convention files.

Soft-deprecate is a reusable primitive shared by the CLI
(``lexi convention deprecate``) and the validator escalation flow
(`lexi validate --fix --interactive`).  Hard-delete is invoked from the
``lexictl update`` pipeline to reap conventions whose deprecation TTL
has expired.

Public API
----------
- :func:`deprecate_convention` -- soft-deprecate: flip status, stamp
  ``deprecated_at`` and ``deprecated_reason`` in frontmatter
- :func:`check_convention_ttl_expiry` -- check if a deprecated convention
  has exceeded its TTL
- :func:`hard_delete_expired_conventions` -- delete expired conventions
  and their comment files
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from lexibrary.conventions.parser import parse_convention_file
from lexibrary.conventions.serializer import serialize_convention_file
from lexibrary.lifecycle.convention_comments import convention_comment_path
from lexibrary.lifecycle.deprecation import _count_commits_since
from lexibrary.utils.atomic import atomic_write

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ConventionDeletionResult:
    """Result of a convention hard-deletion pass."""

    deleted: list[Path]
    """Paths of deleted convention ``.md`` files."""

    comments_deleted: list[Path]
    """Paths of deleted ``.comments.yaml`` files."""


# ---------------------------------------------------------------------------
# Soft-deprecate
# ---------------------------------------------------------------------------


def deprecate_convention(
    convention_path: Path,
    *,
    reason: str,
) -> None:
    """Mark a convention as deprecated by updating its frontmatter.

    Sets ``status`` to ``"deprecated"``, ``deprecated_at`` to the current
    UTC timestamp (seconds precision), and ``deprecated_reason`` to
    *reason*.  The convention file is re-serialized and written atomically
    (temp file + ``os.replace``).

    ``ConventionFileFrontmatter`` has no ``superseded_by`` field, so the
    helper signature omits the parameter (intentional divergence from the
    concept / playbook equivalents).

    Idempotent: if the convention is already deprecated, the helper is a
    no-op and preserves the existing ``deprecated_at`` / ``deprecated_reason``
    values.  Returns ``None`` on parse failure (parity with
    :func:`lexibrary.lifecycle.deprecation.deprecate_design`).

    Parameters
    ----------
    convention_path:
        Absolute path to the convention ``.md`` file.
    reason:
        Free-text deprecation reason (e.g. ``"scope_path_missing"``).

    Returns
    -------
    None
    """
    convention = parse_convention_file(convention_path)
    if convention is None:
        return

    # Idempotent: already deprecated -- do not re-stamp deprecated_at.
    if convention.frontmatter.status == "deprecated":
        return

    convention.frontmatter.status = "deprecated"
    convention.frontmatter.deprecated_at = datetime.now(UTC).replace(microsecond=0)
    convention.frontmatter.deprecated_reason = reason

    atomic_write(convention_path, serialize_convention_file(convention))


# ---------------------------------------------------------------------------
# TTL expiry check
# ---------------------------------------------------------------------------


def check_convention_ttl_expiry(
    convention_path: Path,
    project_root: Path,
    ttl_commits: int,
) -> bool:
    """Check whether a deprecated convention has exceeded its TTL.

    Returns ``True`` if the convention is deprecated, has a
    ``deprecated_at`` timestamp, and the number of commits since that
    timestamp exceeds *ttl_commits*.

    Parameters
    ----------
    convention_path:
        Absolute path to the convention ``.md`` file.
    project_root:
        Absolute path to the project root (for git operations).
    ttl_commits:
        Maximum number of commits before the convention should be deleted.

    Returns
    -------
    bool
        ``True`` if TTL has expired.
    """
    convention = parse_convention_file(convention_path)
    if convention is None:
        return False
    if convention.frontmatter.status != "deprecated":
        return False
    if convention.frontmatter.deprecated_at is None:
        return False

    since_iso = convention.frontmatter.deprecated_at.isoformat()
    commit_count = _count_commits_since(project_root, since_iso)
    return commit_count > ttl_commits


# ---------------------------------------------------------------------------
# Hard deletion
# ---------------------------------------------------------------------------


def hard_delete_expired_conventions(
    project_root: Path,
    lexibrary_dir: Path,
    ttl_commits: int,
) -> ConventionDeletionResult:
    """Delete deprecated conventions whose TTL has expired.

    For each deprecated convention past its TTL:

    1. Delete the convention ``.md`` file.
    2. Delete the sibling ``.comments.yaml`` if it exists.

    Parameters
    ----------
    project_root:
        Absolute path to the project root.
    lexibrary_dir:
        Absolute path to the ``.lexibrary`` directory.
    ttl_commits:
        Maximum number of commits before a deprecated convention is deleted.

    Returns
    -------
    ConventionDeletionResult
        Summary of deleted conventions and comment files.
    """
    conventions_dir = lexibrary_dir / "conventions"
    if not conventions_dir.is_dir():
        return ConventionDeletionResult(deleted=[], comments_deleted=[])

    deleted: list[Path] = []
    comments_deleted: list[Path] = []

    for convention_path in sorted(conventions_dir.glob("*.md")):
        if not convention_path.is_file():
            continue

        convention = parse_convention_file(convention_path)
        if convention is None:
            continue
        if convention.frontmatter.status != "deprecated":
            continue

        # Check TTL expiry
        if not check_convention_ttl_expiry(convention_path, project_root, ttl_commits):
            continue

        # Delete convention file
        convention_path.unlink()
        deleted.append(convention_path)
        logger.info(
            "TTL-expired convention deleted: %s (%s)",
            convention_path.name,
            convention.frontmatter.title,
        )

        # Delete sibling .comments.yaml if it exists
        comment_file = convention_comment_path(convention_path)
        if comment_file.exists():
            comment_file.unlink()
            comments_deleted.append(comment_file)
            logger.info(
                "Deleted convention comment file: %s",
                comment_file.name,
            )

    return ConventionDeletionResult(
        deleted=deleted,
        comments_deleted=comments_deleted,
    )
