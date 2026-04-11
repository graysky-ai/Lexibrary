"""Lifecycle state machine for curator-managed artifact transitions.

Validates state transitions per artifact type and delegates actual file
mutations to the existing ``lifecycle/`` packages.  This module does NOT
duplicate write logic -- it adds transition validation, terminal state
enforcement, and TTL + zero-reference guards.

Public API
----------
- :func:`validate_transition` -- raise on invalid state transitions
- :func:`is_terminal` -- check whether a status is terminal for an artifact kind
- :func:`can_hard_delete` -- guard hard deletion on TTL + zero-ref checks
- :func:`execute_deprecation` -- validate then delegate deprecation to lifecycle modules
- :func:`execute_hard_delete` -- validate then delete ``.md`` and sidecar files
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from lexibrary.curator.models import DeprecationCollectItem, SubAgentResult, TriageItem
from lexibrary.exceptions import LexibraryError

if TYPE_CHECKING:
    from lexibrary.curator.dispatch_context import DispatchContext
    from lexibrary.linkgraph.query import LinkGraph

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class InvalidTransitionError(LexibraryError):
    """Raised when a state transition is not allowed for an artifact kind."""

    def __init__(self, kind: str, current: str, target: str) -> None:
        self.kind = kind
        self.current = current
        self.target = target
        super().__init__(f"Invalid transition for {kind}: '{current}' -> '{target}' is not allowed")


# ---------------------------------------------------------------------------
# Valid transitions
# ---------------------------------------------------------------------------

# Maps (artifact_kind, current_status) -> set of allowed target statuses.
# Uses the exact transitions from the shared content block in tasks.md.
VALID_TRANSITIONS: dict[tuple[str, str], set[str]] = {
    # Design files: active -> deprecated, active -> unlinked, unlinked -> active.
    # deprecated is terminal.
    ("design_file", "active"): {"deprecated", "unlinked"},
    ("design_file", "unlinked"): {"active"},
    # Concepts: draft -> active -> deprecated -> HARD DELETED.
    # draft -> deprecated is INVALID.
    ("concept", "draft"): {"active"},
    ("concept", "active"): {"deprecated"},
    ("concept", "deprecated"): {"hard_deleted"},
    # Conventions: draft -> active -> deprecated -> HARD DELETED.
    ("convention", "draft"): {"active"},
    ("convention", "active"): {"deprecated"},
    ("convention", "deprecated"): {"hard_deleted"},
    # Playbooks: draft -> active -> deprecated -> HARD DELETED.
    # draft -> deprecated is INVALID.
    ("playbook", "draft"): {"active"},
    ("playbook", "active"): {"deprecated"},
    ("playbook", "deprecated"): {"hard_deleted"},
    # Stack posts: open -> resolved, open -> duplicate, open -> outdated,
    # resolved -> stale, stale -> resolved.
    ("stack_post", "open"): {"resolved", "duplicate", "outdated"},
    ("stack_post", "resolved"): {"stale"},
    ("stack_post", "stale"): {"resolved"},
}

# Terminal statuses: no further transitions allowed from these.
_TERMINAL_STATUSES: dict[str, set[str]] = {
    "design_file": {"deprecated"},
}


def validate_transition(kind: str, current: str, target: str) -> None:
    """Validate that a state transition is allowed.

    Parameters
    ----------
    kind:
        Artifact kind (``"design_file"``, ``"concept"``, ``"convention"``,
        ``"playbook"``, ``"stack_post"``).
    current:
        Current status of the artifact.
    target:
        Desired target status.

    Raises
    ------
    InvalidTransitionError
        If the transition is not in ``VALID_TRANSITIONS``.
    """
    allowed = VALID_TRANSITIONS.get((kind, current))
    if allowed is None or target not in allowed:
        raise InvalidTransitionError(kind, current, target)


# ---------------------------------------------------------------------------
# Terminal state check
# ---------------------------------------------------------------------------


def is_terminal(kind: str, status: str) -> bool:
    """Check whether *status* is terminal for *kind*.

    Design file ``"deprecated"`` is terminal -- no further transitions allowed.
    No other statuses are terminal (concepts/conventions proceed to hard delete).

    Parameters
    ----------
    kind:
        Artifact kind.
    status:
        Current status to check.

    Returns
    -------
    bool
        ``True`` if the status is terminal for the given kind.
    """
    terminal_set = _TERMINAL_STATUSES.get(kind, set())
    return status in terminal_set


# ---------------------------------------------------------------------------
# Hard deletion guard
# ---------------------------------------------------------------------------


def can_hard_delete(
    artifact_path: str | Path,
    ttl_commits: int,
    commits_since_deprecation: int,
    link_graph: LinkGraph | None,
) -> tuple[bool, str]:
    """Check whether an artifact can be hard-deleted.

    Returns ``(True, "")`` if ``commits_since_deprecation >= ttl_commits``
    AND ``reverse_deps(artifact_path)`` returns zero inbound links.
    Returns ``(False, reason)`` otherwise.

    Parameters
    ----------
    artifact_path:
        Project-relative path to the artifact (used for link graph query).
    ttl_commits:
        Minimum number of commits since deprecation before deletion is allowed.
    commits_since_deprecation:
        Actual number of commits since the artifact was deprecated.
    link_graph:
        Open link graph instance, or ``None`` if unavailable.

    Returns
    -------
    tuple[bool, str]
        ``(True, "")`` if deletion is allowed, ``(False, reason)`` otherwise.
    """
    path_str = str(artifact_path)

    if commits_since_deprecation < ttl_commits:
        return (
            False,
            f"TTL not reached: {commits_since_deprecation} commits since deprecation, "
            f"need {ttl_commits}",
        )

    if link_graph is not None:
        inbound = link_graph.reverse_deps(path_str)
        if inbound:
            refs = [r.source_path for r in inbound]
            return (
                False,
                f"Still has {len(inbound)} inbound reference(s): {', '.join(refs[:5])}",
            )

    return (True, "")


# ---------------------------------------------------------------------------
# Deprecation execution
# ---------------------------------------------------------------------------


def execute_deprecation(
    kind: str,
    artifact_path: Path,
    target_status: str,
    **kwargs: Any,
) -> None:
    """Validate transition and delegate deprecation to lifecycle modules.

    Parameters
    ----------
    kind:
        Artifact kind (``"design_file"``, ``"concept"``, ``"convention"``).
    artifact_path:
        Absolute path to the artifact file.
    target_status:
        The target status (e.g. ``"deprecated"``, ``"unlinked"``).
    **kwargs:
        Additional keyword arguments passed through to the lifecycle module.
        Supported keys: ``superseded_by``, ``deprecated_reason``,
        ``deprecated_at``.

    Raises
    ------
    InvalidTransitionError
        If the transition is not valid.
    ValueError
        If the artifact kind is not supported for deprecation.
    """
    # Determine current status -- we need to read the artifact to find it
    current_status = _read_current_status(kind, artifact_path)
    validate_transition(kind, current_status, target_status)

    if kind == "design_file":
        _deprecate_design_file(artifact_path, target_status, **kwargs)
    elif kind == "concept":
        _deprecate_concept(artifact_path, target_status, **kwargs)
    elif kind == "convention":
        _deprecate_convention(artifact_path, target_status, **kwargs)
    elif kind == "playbook":
        _deprecate_playbook(artifact_path, target_status, **kwargs)
    else:
        msg = f"Unsupported artifact kind for deprecation: {kind}"
        raise ValueError(msg)


def _read_current_status(kind: str, artifact_path: Path) -> str:
    """Read the current status of an artifact from its frontmatter."""
    if kind == "design_file":
        from lexibrary.artifacts.design_file_parser import (  # noqa: PLC0415
            parse_design_file_frontmatter,
        )

        fm = parse_design_file_frontmatter(artifact_path)
        if fm is None:
            msg = f"Cannot read frontmatter from design file: {artifact_path}"
            raise ValueError(msg)
        return fm.status or "active"

    if kind == "concept":
        from lexibrary.wiki.parser import parse_concept_file  # noqa: PLC0415

        concept = parse_concept_file(artifact_path)
        if concept is None:
            msg = f"Cannot read concept file: {artifact_path}"
            raise ValueError(msg)
        return concept.frontmatter.status or "draft"

    if kind == "convention":
        from lexibrary.conventions.parser import parse_convention_file  # noqa: PLC0415

        convention = parse_convention_file(artifact_path)
        if convention is None:
            msg = f"Cannot read convention file: {artifact_path}"
            raise ValueError(msg)
        return convention.frontmatter.status or "draft"

    if kind == "playbook":
        from lexibrary.playbooks.parser import parse_playbook_file  # noqa: PLC0415

        playbook = parse_playbook_file(artifact_path)
        if playbook is None:
            msg = f"Cannot read playbook file: {artifact_path}"
            raise ValueError(msg)
        return playbook.frontmatter.status or "draft"

    msg = f"Unsupported artifact kind: {kind}"
    raise ValueError(msg)


def _deprecate_design_file(
    artifact_path: Path,
    target_status: str,
    **kwargs: Any,
) -> None:
    """Delegate design file status change to lifecycle.deprecation."""
    from lexibrary.lifecycle.deprecation import (  # noqa: PLC0415
        deprecate_design,
        mark_unlinked,
        restore_design,
    )

    if target_status == "deprecated":
        reason = kwargs.get("deprecated_reason", "manual")
        deprecate_design(artifact_path, reason)
    elif target_status == "unlinked":
        mark_unlinked(artifact_path)
    elif target_status == "active":
        restore_design(artifact_path)
    else:
        msg = f"Unsupported target status for design file: {target_status}"
        raise ValueError(msg)


def _deprecate_concept(
    artifact_path: Path,
    target_status: str,
    **kwargs: Any,
) -> None:
    """Write concept status change via frontmatter update.

    Delegates to the concept file's frontmatter update mechanism.  The
    existing ``lifecycle/concept_deprecation.py`` handles hard deletion
    (TTL + reference checking), not soft deprecation.  For soft
    deprecation (active -> deprecated), we update the frontmatter directly
    using the concept parser/serializer.
    """
    from lexibrary.wiki.parser import parse_concept_file  # noqa: PLC0415

    concept = parse_concept_file(artifact_path)
    if concept is None:
        msg = f"Cannot parse concept file: {artifact_path}"
        raise ValueError(msg)

    concept.frontmatter.status = cast(Any, target_status)

    if target_status == "deprecated":
        if "superseded_by" in kwargs and kwargs["superseded_by"]:
            concept.frontmatter.superseded_by = kwargs["superseded_by"]
        if "deprecated_at" in kwargs and kwargs["deprecated_at"]:
            concept.frontmatter.deprecated_at = kwargs["deprecated_at"]
        else:
            from datetime import UTC, datetime  # noqa: PLC0415

            concept.frontmatter.deprecated_at = datetime.now(UTC).replace(microsecond=0)

    # Serialize and write back
    _write_concept_file(artifact_path, concept)


def _write_concept_file(artifact_path: Path, concept: Any) -> None:
    """Serialize and write a concept file back to disk."""
    from lexibrary.wiki.serializer import serialize_concept_file  # noqa: PLC0415

    content = serialize_concept_file(concept)
    artifact_path.write_text(content, encoding="utf-8")


def _deprecate_convention(
    artifact_path: Path,
    target_status: str,
    **kwargs: Any,
) -> None:
    """Write convention status change via frontmatter update.

    Similar to concepts, the existing ``lifecycle/convention_deprecation.py``
    handles hard deletion.  Soft deprecation updates frontmatter directly.
    """
    from lexibrary.conventions.parser import parse_convention_file  # noqa: PLC0415

    convention = parse_convention_file(artifact_path)
    if convention is None:
        msg = f"Cannot parse convention file: {artifact_path}"
        raise ValueError(msg)

    convention.frontmatter.status = cast(Any, target_status)

    if target_status == "deprecated":
        if "deprecated_at" in kwargs and kwargs["deprecated_at"]:
            convention.frontmatter.deprecated_at = kwargs["deprecated_at"]
        else:
            from datetime import UTC, datetime  # noqa: PLC0415

            convention.frontmatter.deprecated_at = datetime.now(UTC).replace(microsecond=0)

    # Serialize and write back
    _write_convention_file(artifact_path, convention)


def _write_convention_file(artifact_path: Path, convention: Any) -> None:
    """Serialize and write a convention file back to disk."""
    from lexibrary.conventions.serializer import serialize_convention_file  # noqa: PLC0415

    content = serialize_convention_file(convention)
    artifact_path.write_text(content, encoding="utf-8")


def _deprecate_playbook(
    artifact_path: Path,
    target_status: str,
    **kwargs: Any,
) -> None:
    """Write playbook status change via frontmatter update."""
    from lexibrary.playbooks.parser import parse_playbook_file  # noqa: PLC0415

    playbook = parse_playbook_file(artifact_path)
    if playbook is None:
        msg = f"Cannot parse playbook file: {artifact_path}"
        raise ValueError(msg)

    playbook.frontmatter.status = cast(Any, target_status)

    if target_status == "deprecated":
        if "deprecated_at" in kwargs and kwargs["deprecated_at"]:
            playbook.frontmatter.deprecated_at = kwargs["deprecated_at"]
        else:
            from datetime import UTC, datetime  # noqa: PLC0415

            playbook.frontmatter.deprecated_at = datetime.now(UTC).replace(microsecond=0)

    # Serialize and write back
    _write_playbook_file(artifact_path, playbook)


def _write_playbook_file(artifact_path: Path, playbook: Any) -> None:
    """Serialize and write a playbook file back to disk."""
    from lexibrary.playbooks.serializer import serialize_playbook_file  # noqa: PLC0415

    content = serialize_playbook_file(playbook)
    artifact_path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Hard deletion
# ---------------------------------------------------------------------------


def execute_hard_delete(
    kind: str,
    artifact_path: Path,
    ttl_commits: int,
    commits_since_deprecation: int,
    link_graph: LinkGraph | None,
) -> None:
    """Validate and execute hard deletion of an artifact.

    Steps:
    1. Call ``can_hard_delete()`` to verify TTL + zero-ref guards.
    2. Remove the ``.md`` file.
    3. Remove the sibling ``.comments.yaml`` sidecar.

    Deletion order: ``.md`` first, then ``.comments.yaml``.
    If ``.md`` deletion fails, the sidecar is left in place.

    Delegates to existing lifecycle modules where possible.

    Parameters
    ----------
    kind:
        Artifact kind (``"concept"``, ``"convention"``, ``"playbook"``).
    artifact_path:
        Absolute path to the artifact ``.md`` file.
    ttl_commits:
        Minimum number of commits since deprecation.
    commits_since_deprecation:
        Actual number of commits since the artifact was deprecated.
    link_graph:
        Open link graph instance, or ``None`` if unavailable.

    Raises
    ------
    ValueError
        If hard deletion is not allowed (TTL not reached or refs exist),
        or if the artifact kind is not supported.
    """
    # Derive project-relative path for link graph query
    path_for_query = str(artifact_path)
    # Try to make it project-relative if it's absolute
    try:
        from lexibrary.utils.root import find_project_root  # noqa: PLC0415

        root = find_project_root(artifact_path)
        path_for_query = str(artifact_path.relative_to(root))
    except Exception:  # noqa: BLE001
        pass

    allowed, reason = can_hard_delete(
        path_for_query, ttl_commits, commits_since_deprecation, link_graph
    )
    if not allowed:
        msg = f"Cannot hard-delete {kind} at {artifact_path}: {reason}"
        raise ValueError(msg)

    # Delete the .md file first
    try:
        artifact_path.unlink()
        logger.info("Hard-deleted %s: %s", kind, artifact_path.name)
    except OSError:
        logger.error("Failed to delete %s file: %s", kind, artifact_path)
        raise

    # Delete the sibling .comments.yaml sidecar
    sidecar_path = _get_sidecar_path(kind, artifact_path)
    if sidecar_path is not None and sidecar_path.exists():
        try:
            sidecar_path.unlink()
            logger.info("Deleted sidecar: %s", sidecar_path.name)
        except OSError:
            logger.warning(
                "Failed to delete sidecar %s (orphan cleanup will handle it)",
                sidecar_path,
            )


def _get_sidecar_path(kind: str, artifact_path: Path) -> Path | None:
    """Derive the ``.comments.yaml`` sidecar path for an artifact."""
    if kind == "concept":
        from lexibrary.lifecycle.concept_comments import (  # noqa: PLC0415
            concept_comment_path,
        )

        return concept_comment_path(artifact_path)

    if kind == "convention":
        from lexibrary.lifecycle.convention_comments import (  # noqa: PLC0415
            convention_comment_path,
        )

        return convention_comment_path(artifact_path)

    if kind == "playbook":
        from lexibrary.lifecycle.playbook_comments import (  # noqa: PLC0415
            playbook_comment_path,
        )

        return playbook_comment_path(artifact_path)

    return None


# ---------------------------------------------------------------------------
# Dispatcher entry points (Phase 1.5)
# ---------------------------------------------------------------------------


def dispatch_hard_delete(
    item: TriageItem,
    ctx: DispatchContext,
    dep: DeprecationCollectItem,
) -> SubAgentResult:
    """Execute hard deletion of a TTL-expired deprecated artifact.

    Extracted from :class:`Coordinator._dispatch_hard_delete`
    (Phase 1.5 dispatcher refactor).
    """
    from lexibrary.linkgraph.query import open_index  # noqa: PLC0415

    link_graph = open_index(ctx.project_root)
    try:
        execute_hard_delete(
            kind=dep.artifact_kind,
            artifact_path=dep.artifact_path,
            ttl_commits=ctx.config.curator.deprecation.ttl_commits,
            commits_since_deprecation=dep.commits_since_deprecation,
            link_graph=link_graph,
        )
        return SubAgentResult(
            success=True,
            action_key=item.action_key,
            path=dep.artifact_path,
            message=f"Hard-deleted {dep.artifact_kind}: {dep.artifact_path.name}",
            llm_calls=0,
        )
    except Exception as exc:
        ctx.summary.add("dispatch", exc, path=str(dep.artifact_path))
        return SubAgentResult(
            success=False,
            action_key=item.action_key,
            path=dep.artifact_path,
            message=f"Hard deletion failed: {exc}",
        )
    finally:
        if link_graph is not None:
            link_graph.close()


def dispatch_stack_transition(
    item: TriageItem,
    ctx: DispatchContext,
    dep: DeprecationCollectItem,
) -> SubAgentResult:
    """Dispatch a stack post state transition (e.g. resolved -> stale).

    Extracted from :class:`Coordinator._dispatch_stack_transition`
    (Phase 1.5 dispatcher refactor).
    """
    try:
        execute_deprecation(
            kind="stack_post",
            artifact_path=dep.artifact_path,
            target_status="stale",
        )
        return SubAgentResult(
            success=True,
            action_key=item.action_key,
            path=dep.artifact_path,
            message=f"Transitioned stack post to stale: {dep.artifact_path.name}",
            llm_calls=0,
        )
    except Exception as exc:
        ctx.summary.add("dispatch", exc, path=str(dep.artifact_path))
        return SubAgentResult(
            success=False,
            action_key=item.action_key,
            path=dep.artifact_path,
            message=f"Stack transition failed: {exc}",
        )
