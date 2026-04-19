"""Consistency fix helpers for the curator coordinator (Phase 3 — group 8).

Every helper in this module implements a single :class:`FixInstruction`
action string emitted by :class:`lexibrary.curator.consistency.ConsistencyChecker`.
Helpers receive a :class:`TriageItem` and :class:`DispatchContext`, perform
the fix, and return a :class:`SubAgentResult` with
``outcome="fixed"`` / ``"fixer_failed"`` / ``"errored"``.

Design-file rewrites MUST go through
:func:`lexibrary.curator.write_contract.write_design_file_as_curator` --
no helper writes a design file directly.  The shared contract stamps
``updated_by="curator"``, recomputes ``source_hash``/``interface_hash``,
serializes, and atomically writes.

Non-design-file rewrites (deleting orphan ``.aindex`` / ``.comments.yaml``,
deleting orphan concepts, writing warning IWH signals for stale
conventions / playbooks) do not go through the design-file write
contract -- they are simple ``unlink``s or IWH writes.

Every helper SHALL be unit-testable without spinning up a full
coordinator; helpers receive only ``item`` and ``ctx`` so tests can
fabricate minimal stubs.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from lexibrary.artifacts.design_file_parser import (
    parse_design_file,
)
from lexibrary.curator.models import SubAgentResult, TriageItem
from lexibrary.curator.write_contract import write_design_file_as_curator

if TYPE_CHECKING:
    from lexibrary.curator.dispatch_context import DispatchContext

logger = logging.getLogger(__name__)


CONSISTENCY_ACTION_KEYS: dict[str, str] = {
    # Cleanup
    "delete_orphaned_comments": "delete_orphaned_comments",
    # Convention / playbook staleness handlers retired in curator-4 Group 22 —
    # replaced by the validator escalation fixers
    # (``escalate_convention_stale`` / ``escalate_playbook_staleness``).
    # Bidirectional dep cross-reference
    "add_missing_reverse_dep": "add_missing_reverse_dep",
    # Medium-risk (deferred under auto_low)
    "suggest_new_concept": "suggest_new_concept",
    "promote_blocked_iwh": "promote_blocked_iwh",
}


# ---------------------------------------------------------------------------
# Helper internals
# ---------------------------------------------------------------------------


def _result(
    *,
    action_key: str,
    path: Path | None,
    message: str,
    success: bool = True,
    outcome: str = "fixed",
) -> SubAgentResult:
    """Build a :class:`SubAgentResult` with standardised defaults."""
    return SubAgentResult(
        success=success,
        action_key=action_key,
        path=path,
        message=message,
        llm_calls=0,
        outcome=outcome,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Wikilink hygiene helpers retired in Phase 4 Family D of the
# ``curator-freshness`` change. Detection + fix now route through the
# validator's ``check_wikilink_resolution`` paired with the
# archivist-delegated ``fix_wikilink_resolution`` fixer
# (``src/lexibrary/validator/fixes.py``). The validation bridge surfaces
# the narrow ``fix_wikilink_resolution`` action key in curator reports.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Slug / alias collision helpers — retired in Phase 4 Family B of the
# ``curator-freshness`` change. Collision detection + resolution now lives
# in the validator (``check_duplicate_slugs`` / ``check_duplicate_aliases``
# + the propose-only ``fix_duplicate_slugs`` / ``fix_duplicate_aliases``
# fixers). The coordinator's validation bridge routes these issues through
# the narrow action keys registered in ``CHECK_TO_ACTION_KEY``.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Bidirectional dep cross-reference helpers
# ---------------------------------------------------------------------------


def apply_add_reverse_dep(item: TriageItem, ctx: DispatchContext) -> SubAgentResult:
    """Add a missing reverse-dep entry to a design file's dependents list.

    The detail string carries the source path that should appear in the
    target design file's dependents.  Format produced by
    ``detect_design_dep_mismatch``::

        src/a.py lists src/b.py as a dependency but src/b.py does not list src/a.py as a dependent
    """
    action_key = item.action_key
    design_path = item.source_item.path
    if design_path is None:
        return _result(
            action_key=action_key,
            path=None,
            message="No design path for add_missing_reverse_dep",
            success=False,
            outcome="fixer_failed",
        )

    detail = item.source_item.fix_instruction_detail
    missing_dep = _extract_missing_dep_from_detail(detail)
    if missing_dep is None:
        return _result(
            action_key=action_key,
            path=design_path,
            message="Could not extract missing dependent from detail",
            success=False,
            outcome="fixer_failed",
        )

    design = parse_design_file(design_path)
    if design is None:
        return _result(
            action_key=action_key,
            path=design_path,
            message="Failed to parse design file",
            success=False,
            outcome="fixer_failed",
        )

    existing = {d.strip() for d in design.dependents}
    if missing_dep in existing:
        return _result(
            action_key=action_key,
            path=design_path,
            message=f"{missing_dep} already in dependents; nothing to add",
            outcome="fixed",
        )

    design.dependents.append(missing_dep)

    try:
        write_design_file_as_curator(design, design_path, ctx.project_root)
    except Exception as exc:
        ctx.summary.add("dispatch", exc, path=str(design_path))
        return _result(
            action_key=action_key,
            path=design_path,
            message=f"Failed to write design file: {exc}",
            success=False,
            outcome="errored",
        )

    return _result(
        action_key=action_key,
        path=design_path,
        message=f"Added {missing_dep} to dependents",
        outcome="fixed",
    )


def _extract_missing_dep_from_detail(detail: str) -> str | None:
    """Extract the source path that should be added as a dependent.

    Detail format::

        src/a.py lists src/b.py as a dependency but src/b.py does not list src/a.py as a dependent

    Returns ``src/a.py`` (the path that should be added to the target's dependents).
    """
    match = re.match(r"^(\S+) lists \S+ as a dependency", detail)
    if match is None:
        return None
    return match.group(1)


# ---------------------------------------------------------------------------
# Cleanup helpers (non-design-file deletions)
# ---------------------------------------------------------------------------


def apply_orphaned_comments_delete(item: TriageItem, ctx: DispatchContext) -> SubAgentResult:
    """Delete an orphaned ``.comments.yaml`` whose parent artifact is missing."""
    action_key = item.action_key
    target_path = item.source_item.path
    if target_path is None:
        return _result(
            action_key=action_key,
            path=None,
            message="No target path for delete_orphaned_comments",
            success=False,
            outcome="fixer_failed",
        )

    if not target_path.exists():
        return _result(
            action_key=action_key,
            path=target_path,
            message=".comments.yaml already absent",
            outcome="fixed",
        )

    try:
        target_path.unlink()
    except OSError as exc:
        ctx.summary.add("dispatch", exc, path=str(target_path))
        return _result(
            action_key=action_key,
            path=target_path,
            message=f"Failed to delete .comments.yaml: {exc}",
            success=False,
            outcome="errored",
        )

    return _result(
        action_key=action_key,
        path=target_path,
        message=f"Deleted orphaned {target_path.name}",
        outcome="fixed",
    )


# ---------------------------------------------------------------------------
# Convention / playbook / medium-risk helpers
# ---------------------------------------------------------------------------


def _write_flag_iwh(
    target_path: Path,
    *,
    project_root: Path,
    lexibrary_dir: Path,
    body: str,
) -> Path | None:
    """Write a ``scope=warning`` IWH signal next to *target_path*.

    Chooses the mirror directory under ``.lexibrary/`` when *target_path*
    is already inside the library (typical for conventions/playbooks),
    otherwise writes alongside the file.  Returns the written path or
    ``None`` on failure.
    """
    from lexibrary.iwh.writer import write_iwh  # noqa: PLC0415

    try:
        rel = target_path.relative_to(lexibrary_dir)
        dest_dir = lexibrary_dir / rel.parent
    except ValueError:
        try:
            rel = target_path.relative_to(project_root)
            dest_dir = lexibrary_dir / rel.parent
        except ValueError:
            dest_dir = target_path.parent

    try:
        return write_iwh(dest_dir, author="curator", scope="warning", body=body)
    except OSError as exc:
        logger.warning("Failed to write flag IWH at %s: %s", dest_dir, exc)
        return None


# ---------------------------------------------------------------------------
# ``apply_flag_stale_convention`` / ``apply_flag_stale_playbook`` retired in
# curator-4 Group 22.  Convention / playbook staleness now flows through the
# validator's ``check_convention_stale`` / ``check_playbook_staleness`` checks
# paired with the escalation fixers ``escalate_convention_stale`` /
# ``escalate_playbook_staleness`` (see ``validator/fixes.py``).  The escalation
# fixers write an IWH breadcrumb and surface a ``PendingDecision`` in the
# curator report instead of mutating artifacts directly.
# ---------------------------------------------------------------------------


def apply_suggest_new_concept(item: TriageItem, ctx: DispatchContext) -> SubAgentResult:
    """Medium-risk: propose a new concept for a recurring unresolved term.

    Under ``auto_low``, this action is deferred (see autonomy gating in
    :func:`should_dispatch`).  Under ``full``, the helper writes a
    ``scope=warning`` IWH next to the first referencing design file so
    a human reviewer sees the proposal.  Concept creation itself is
    left to the reviewer -- the helper is read-only with respect to
    concept files.
    """
    action_key = item.action_key
    target_path = item.source_item.path
    if target_path is None:
        return _result(
            action_key=action_key,
            path=None,
            message="No target path for suggest_new_concept",
            success=False,
            outcome="fixer_failed",
        )

    body = (
        f"Suggested new concept proposal:\n"
        f"{item.source_item.fix_instruction_detail}\n"
        f"Action: create a concept artifact or ignore."
    )
    iwh_path = _write_flag_iwh(
        target_path,
        project_root=ctx.project_root,
        lexibrary_dir=ctx.lexibrary_dir,
        body=body,
    )
    if iwh_path is None:
        return _result(
            action_key=action_key,
            path=target_path,
            message="Failed to write IWH for suggest_new_concept",
            success=False,
            outcome="errored",
        )

    return _result(
        action_key=action_key,
        path=target_path,
        message="Flagged suggest_new_concept proposal",
        outcome="fixed",
    )


def apply_promote_blocked_iwh(item: TriageItem, ctx: DispatchContext) -> SubAgentResult:
    """Escalation-only: mark a blocked IWH signal for promotion to a Stack post.

    Under ``auto_low``, this action is deferred.  Under ``full``, the
    helper overwrites the blocked ``.iwh`` with a ``scope=warning`` signal
    indicating promotion should happen.  The original blocked body content
    is lost.  Actual Stack post creation is left to the human reviewer or
    a future Stack-transition sub-agent.
    """
    action_key = item.action_key
    target_path = item.source_item.path
    if target_path is None:
        return _result(
            action_key=action_key,
            path=None,
            message="No target path for promote_blocked_iwh",
            success=False,
            outcome="fixer_failed",
        )

    body = (
        f"Blocked IWH promotion proposal:\n"
        f"{item.source_item.fix_instruction_detail}\n"
        f"Action: promote to Stack post and consume the signal."
    )
    iwh_path = _write_flag_iwh(
        target_path,
        project_root=ctx.project_root,
        lexibrary_dir=ctx.lexibrary_dir,
        body=body,
    )
    if iwh_path is None:
        return _result(
            action_key=action_key,
            path=target_path,
            message="Failed to write promotion IWH",
            success=False,
            outcome="errored",
        )

    return _result(
        action_key=action_key,
        path=target_path,
        message="Flagged promote_blocked_iwh proposal",
        outcome="fixed",
    )
