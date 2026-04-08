"""Hard deletion of expired deprecated concepts.

Provides TTL expiry checking, pre-deletion reference scanning, and
hard deletion of deprecated concept ``.md`` files and their sibling
``.comments.yaml`` files.  Designed to be called from the
``lexictl update`` pipeline alongside the existing design-file
deprecation pass.

Public API
----------
- :func:`check_concept_ttl_expiry` -- check if a deprecated concept has
  exceeded its TTL
- :func:`find_concept_references` -- scan active artefacts for references
  to a concept
- :func:`hard_delete_expired_concepts` -- delete expired concepts with
  reference protection
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from lexibrary.lifecycle.concept_comments import concept_comment_path
from lexibrary.lifecycle.deprecation import _count_commits_since
from lexibrary.wiki.parser import parse_concept_file

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ConceptDeletionResult:
    """Result of a concept hard-deletion pass."""

    deleted: list[Path]
    """Paths of deleted concept ``.md`` files."""

    skipped_referenced: list[tuple[Path, list[str]]]
    """Concepts skipped because active artefacts still reference them.
    Each entry is (concept_path, list_of_referencing_artefact_paths)."""

    comments_deleted: list[Path]
    """Paths of deleted ``.comments.yaml`` files."""


# ---------------------------------------------------------------------------
# TTL expiry check
# ---------------------------------------------------------------------------


def check_concept_ttl_expiry(
    concept_path: Path,
    project_root: Path,
    ttl_commits: int,
) -> bool:
    """Check whether a deprecated concept has exceeded its TTL.

    Returns ``True`` if the concept is deprecated, has a
    ``deprecated_at`` timestamp, and the number of commits since that
    timestamp exceeds *ttl_commits*.

    Parameters
    ----------
    concept_path:
        Absolute path to the concept ``.md`` file.
    project_root:
        Absolute path to the project root (for git operations).
    ttl_commits:
        Maximum number of commits before the concept should be deleted.

    Returns
    -------
    bool
        ``True`` if TTL has expired.
    """
    concept = parse_concept_file(concept_path)
    if concept is None:
        return False
    if concept.frontmatter.status != "deprecated":
        return False
    if concept.frontmatter.deprecated_at is None:
        return False

    since_iso = concept.frontmatter.deprecated_at.isoformat()
    commit_count = _count_commits_since(project_root, since_iso)
    return commit_count > ttl_commits


# ---------------------------------------------------------------------------
# Reference check
# ---------------------------------------------------------------------------


def find_concept_references(
    concept_title: str,
    concept_aliases: list[str],
    project_root: Path,
    lexibrary_dir: Path,
) -> list[str]:
    """Scan active artefacts for wikilink references to a concept.

    Checks design files and other concept files for ``[[Title]]`` or
    ``[[Alias]]`` wikilinks that reference the given concept.  Only
    active artefacts are checked (deprecated artefacts are excluded).

    Parameters
    ----------
    concept_title:
        The concept's title (used for wikilink matching).
    concept_aliases:
        The concept's aliases (also used for wikilink matching).
    project_root:
        Absolute path to the project root.
    lexibrary_dir:
        Absolute path to the ``.lexibrary`` directory.

    Returns
    -------
    list[str]
        Relative paths of artefacts that reference this concept.
    """
    from lexibrary.artifacts.design_file_parser import (  # noqa: PLC0415
        parse_design_file,
    )
    from lexibrary.utils.paths import DESIGNS_DIR  # noqa: PLC0415
    from lexibrary.wiki.patterns import WIKILINK_RE as wikilink_re  # noqa: N811, PLC0415

    # Build a set of normalised names to match against
    names_to_match: set[str] = {concept_title.strip().lower()}
    for alias in concept_aliases:
        names_to_match.add(alias.strip().lower())

    referencing: list[str] = []

    # 1. Check design files for wikilinks
    designs_root = lexibrary_dir / DESIGNS_DIR
    if designs_root.is_dir():
        for design_path in sorted(designs_root.rglob("*.md")):
            if not design_path.is_file():
                continue
            design = parse_design_file(design_path)
            if design is None:
                continue
            # Skip deprecated/unlinked design files
            if design.frontmatter.status in ("deprecated", "unlinked"):
                continue
            # Check wikilinks field
            for link in design.wikilinks:
                if link.strip().lower() in names_to_match:
                    try:
                        rel = str(design_path.relative_to(project_root))
                    except ValueError:
                        rel = str(design_path)
                    referencing.append(rel)
                    break

    # 2. Check other active concept files for wikilinks in body
    concepts_dir = lexibrary_dir / "concepts"
    if concepts_dir.is_dir():
        for md_path in sorted(concepts_dir.glob("*.md")):
            other = parse_concept_file(md_path)
            if other is None:
                continue
            # Skip deprecated concepts and the concept itself
            if other.frontmatter.status != "active":
                continue
            if other.frontmatter.title.strip().lower() == concept_title.strip().lower():
                continue
            # Check wikilinks in body
            body_links = wikilink_re.findall(other.body)
            for link in body_links:
                if link.strip().lower() in names_to_match:
                    try:
                        rel = str(md_path.relative_to(project_root))
                    except ValueError:
                        rel = str(md_path)
                    referencing.append(rel)
                    break

    return referencing


# ---------------------------------------------------------------------------
# Hard deletion
# ---------------------------------------------------------------------------


def hard_delete_expired_concepts(
    project_root: Path,
    lexibrary_dir: Path,
    ttl_commits: int,
) -> ConceptDeletionResult:
    """Delete deprecated concepts whose TTL has expired.

    For each deprecated concept past its TTL:

    1. Check for active artefact references -- skip if references exist.
    2. Delete the concept ``.md`` file.
    3. Delete the sibling ``.comments.yaml`` if it exists.

    Parameters
    ----------
    project_root:
        Absolute path to the project root.
    lexibrary_dir:
        Absolute path to the ``.lexibrary`` directory.
    ttl_commits:
        Maximum number of commits before a deprecated concept is deleted.

    Returns
    -------
    ConceptDeletionResult
        Summary of deleted and skipped concepts.
    """
    concepts_dir = lexibrary_dir / "concepts"
    if not concepts_dir.is_dir():
        return ConceptDeletionResult(deleted=[], skipped_referenced=[], comments_deleted=[])

    deleted: list[Path] = []
    skipped_referenced: list[tuple[Path, list[str]]] = []
    comments_deleted: list[Path] = []

    for concept_path in sorted(concepts_dir.glob("*.md")):
        if not concept_path.is_file():
            continue

        concept = parse_concept_file(concept_path)
        if concept is None:
            continue
        if concept.frontmatter.status != "deprecated":
            continue

        # Check TTL expiry
        if not check_concept_ttl_expiry(concept_path, project_root, ttl_commits):
            continue

        # Pre-deletion reference check
        refs = find_concept_references(
            concept.frontmatter.title,
            list(concept.frontmatter.aliases),
            project_root,
            lexibrary_dir,
        )
        if refs:
            skipped_referenced.append((concept_path, refs))
            logger.warning(
                "Skipping deletion of expired concept '%s': still referenced by %d artefact(s)",
                concept.frontmatter.title,
                len(refs),
            )
            continue

        # Delete concept file
        concept_path.unlink()
        deleted.append(concept_path)
        logger.info(
            "TTL-expired concept deleted: %s (%s)",
            concept_path.name,
            concept.frontmatter.title,
        )

        # Delete sibling .comments.yaml if it exists
        comment_file = concept_comment_path(concept_path)
        if comment_file.exists():
            comment_file.unlink()
            comments_deleted.append(comment_file)
            logger.info(
                "Deleted concept comment file: %s",
                comment_file.name,
            )

    return ConceptDeletionResult(
        deleted=deleted,
        skipped_referenced=skipped_referenced,
        comments_deleted=comments_deleted,
    )
