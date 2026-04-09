"""Problem fingerprinting and duplicate detection for curator-created Stack posts.

Provides deterministic SHA-256 fingerprinting of problem descriptions and
duplicate detection via full-text search on the link graph index. When a
duplicate is found, a new Finding is appended to the existing post instead
of creating a redundant one.
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path

from lexibrary.linkgraph.query import ArtifactResult, LinkGraph
from lexibrary.stack.helpers import find_post_path
from lexibrary.stack.mutations import add_finding, create_stack_post

logger = logging.getLogger(__name__)


def compute_fingerprint(
    problem_type: str,
    artifact_path: str,
    error_signature: str,
) -> str:
    """Compute a deterministic SHA-256 fingerprint for a problem.

    The fingerprint is built from three components concatenated with newline
    separators.  The ``error_signature`` is normalised by lowercasing and
    collapsing runs of whitespace to single spaces before hashing.

    Parameters
    ----------
    problem_type:
        Category of the problem (e.g. ``"stale_design"``, ``"orphan_concept"``).
    artifact_path:
        Project-relative path of the affected artifact.
    error_signature:
        A short description or error message characterising the problem.

    Returns
    -------
    str
        Hex-encoded SHA-256 digest of the normalised input.
    """
    normalised_sig = re.sub(r"\s+", " ", error_signature.lower()).strip()
    payload = f"{problem_type}\n{artifact_path}\n{normalised_sig}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def find_duplicate_post(
    fingerprint: str,
    problem_type: str,
    artifact_path: str,
    link_graph: LinkGraph | None,
) -> str | None:
    """Search for an existing open Stack post that matches the fingerprint.

    Queries the link graph's full-text search with ``problem_type`` and
    ``artifact_path`` to find candidate posts, then filters to those with
    ``status == "open"`` and compares fingerprints.

    Parameters
    ----------
    fingerprint:
        The hex SHA-256 fingerprint to match against.
    problem_type:
        Problem category used as a search term.
    artifact_path:
        Artifact path used as a search term.
    link_graph:
        An open :class:`LinkGraph` instance, or ``None`` for graceful
        degradation (always returns ``None``).

    Returns
    -------
    str | None
        The artifact code (e.g. ``"ST-001"``) of the matching open post,
        or ``None`` if no duplicate is found.
    """
    if link_graph is None:
        return None

    query = f"{problem_type} {artifact_path}"
    results: list[ArtifactResult] = link_graph.full_text_search(query)

    for result in results:
        # Only consider open stack posts
        if result.kind != "stack_post" or result.status != "open":
            continue
        if result.artifact_code is not None and fingerprint in _get_post_fingerprints(result):
            return result.artifact_code

    return None


def _get_post_fingerprints(result: ArtifactResult) -> set[str]:
    """Extract fingerprint hashes embedded in a stack post's title or body.

    The curator embeds the fingerprint in the post title using the format
    ``[fp:<hex>]``.  This function returns all such fingerprints found.

    If no fingerprint marker is found, returns an empty set.
    """
    fingerprints: set[str] = set()
    if result.title:
        for match in re.finditer(r"\[fp:([a-f0-9]{64})\]", result.title):
            fingerprints.add(match.group(1))
    return fingerprints


def create_or_append_post(
    problem_type: str,
    artifact_path: str,
    error_signature: str,
    rationale: str,
    link_graph: LinkGraph | None,
    *,
    project_root: Path,
    author: str = "curator",
) -> str:
    """Create a new Stack post or append a Finding to an existing duplicate.

    Computes the problem fingerprint, searches for an existing open post
    with the same fingerprint, and either:

    - **Appends** a new Finding to the duplicate (returning its post ID), or
    - **Creates** a new Stack post with the fingerprint embedded in the title.

    If ``full_text_search()`` raises an exception, the error is logged and
    a new post is created regardless (fail-open behaviour).

    Parameters
    ----------
    problem_type:
        Category of the problem (e.g. ``"stale_design"``).
    artifact_path:
        Project-relative path of the affected artifact.
    error_signature:
        Short description or error message characterising the problem.
    rationale:
        Explanation of why this problem was detected (used as the Finding
        or problem body).
    link_graph:
        An open :class:`LinkGraph` instance, or ``None``.
    project_root:
        Absolute path to the repository root.
    author:
        Author identifier for the post/finding (default ``"curator"``).

    Returns
    -------
    str
        The post ID (e.g. ``"ST-001"``) of the created or updated post.
    """
    fp = compute_fingerprint(problem_type, artifact_path, error_signature)

    # Try to find an existing duplicate
    duplicate_id: str | None = None
    try:
        duplicate_id = find_duplicate_post(fp, problem_type, artifact_path, link_graph)
    except Exception:
        logger.exception(
            "full_text_search failed during duplicate check for %s at %s; creating new post",
            problem_type,
            artifact_path,
        )

    stack_directory = project_root / ".lexibrary" / "stack"

    if duplicate_id is not None:
        # Append a Finding to the existing post
        post_path = find_post_path(project_root, duplicate_id)
        if post_path is not None:
            add_finding(post_path, author=author, body=rationale)
            logger.info(
                "Appended finding to existing post %s for %s at %s",
                duplicate_id,
                problem_type,
                artifact_path,
            )
            return duplicate_id
        # Fall through to create if post file not found on disk
        logger.warning(
            "Duplicate post %s found in index but not on disk; creating new post",
            duplicate_id,
        )

    # Create a new post with fingerprint embedded in the title
    title = f"{problem_type}: {artifact_path} [fp:{fp}]"
    post_path = create_stack_post(
        stack_directory,
        title=title,
        tags=[problem_type, "curator"],
        author=author,
        problem=rationale,
        refs_files=[artifact_path],
    )

    # Extract the post ID from the filename (e.g. "ST-001-slug.md" -> "ST-001")
    post_id = _extract_post_id(post_path)
    logger.info(
        "Created new stack post %s for %s at %s",
        post_id,
        problem_type,
        artifact_path,
    )
    return post_id


def _extract_post_id(post_path: Path) -> str:
    """Extract the post ID (e.g. ``ST-001``) from a stack post filename."""
    name = post_path.stem  # e.g. "ST-001-some-slug"
    parts = name.split("-", 2)  # ["ST", "001", "some-slug"]
    if len(parts) >= 2:
        return f"{parts[0]}-{parts[1]}"
    return name
