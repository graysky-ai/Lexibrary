"""IWH residual handlers for the curator coordinator (Phase 4 — group 9).

This module hosts the public dispatch functions for the three residual
IWH-related action keys surfaced by :data:`lexibrary.curator.risk_taxonomy.RISK_TAXONOMY`
that had no wired handler before curator-fix Phase 4:

* :func:`consume_superseded_iwh` — call :func:`lexibrary.iwh.reader.consume_iwh`
  on the directory carried by the :class:`TriageItem`.  Used when a blocked
  or superseded IWH signal should be cleared so the next agent session does
  not re-read it.
* :func:`write_reactive_iwh` — write a ``scope=warning`` IWH signal at the
  directory carried by the :class:`TriageItem`.  Used by scheduled curator
  runs to leave a directory-scoped coordination message for subsequent
  sessions.
* :func:`flag_unresolvable_agent_design` — write a ``scope=warning`` IWH
  signal next to a design file that the reconciliation sub-agent returned
  with low confidence, asking a human to review.

All three helpers use the standard
``(item: TriageItem, ctx: DispatchContext) -> SubAgentResult`` signature
shared by the other extracted dispatch functions (groups 3, 5, 7, 8).
They never modify design files and never call an LLM, so they always
return ``llm_calls=0``.  On success they return ``outcome="fixed"``; on
failure they return ``outcome="errored"`` and record the error in
``ctx.summary``.

The module is deliberately free of coordinator references so tests can
exercise each helper with a hand-rolled :class:`TriageItem` /
:class:`DispatchContext` pair (see ``tests/test_curator/test_iwh_actions.py``).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from lexibrary.curator.models import SubAgentResult, TriageItem
from lexibrary.iwh.reader import consume_iwh
from lexibrary.iwh.writer import write_iwh

if TYPE_CHECKING:
    from pathlib import Path

    from lexibrary.curator.dispatch_context import DispatchContext

logger = logging.getLogger(__name__)


def _failure(
    *,
    action_key: str,
    path: Path | None,
    message: str,
    outcome: str = "fixer_failed",
) -> SubAgentResult:
    """Build a failure :class:`SubAgentResult` with standardised defaults."""
    return SubAgentResult(
        success=False,
        action_key=action_key,
        path=path,
        message=message,
        llm_calls=0,
        outcome=outcome,  # type: ignore[arg-type]
    )


def _success(
    *,
    action_key: str,
    path: Path | None,
    message: str,
) -> SubAgentResult:
    """Build a success :class:`SubAgentResult` with ``outcome="fixed"``."""
    return SubAgentResult(
        success=True,
        action_key=action_key,
        path=path,
        message=message,
        llm_calls=0,
        outcome="fixed",
    )


# ---------------------------------------------------------------------------
# consume_superseded_iwh
# ---------------------------------------------------------------------------


def consume_superseded_iwh(item: TriageItem, ctx: DispatchContext) -> SubAgentResult:
    """Consume a superseded ``.iwh`` signal via :func:`consume_iwh`.

    Reads the :class:`TriageItem`'s ``source_item.path`` (populated by
    :meth:`Coordinator._collect_iwh`) and passes it to
    :func:`lexibrary.iwh.reader.consume_iwh`, which reads and deletes the
    ``.iwh`` file in that directory.  ``consume_iwh`` returns ``None`` when
    the file does not exist or cannot be parsed; this helper surfaces that
    case as a failed :class:`SubAgentResult` so the honest counter logic
    records it as ``outcome="fixer_failed"`` rather than a spurious
    ``fixed`` count.

    Any :class:`OSError` from the underlying reader is caught, recorded in
    ``ctx.summary`` under the ``"dispatch"`` channel, and returned as
    ``outcome="errored"`` so downstream reports can flag the failure
    without aborting the whole dispatch cycle.
    """
    action_key = item.action_key
    directory = item.source_item.path
    if directory is None:
        return _failure(
            action_key=action_key,
            path=None,
            message="No directory path available for consume_superseded_iwh",
        )

    try:
        parsed = consume_iwh(directory)
    except OSError as exc:
        ctx.summary.add("dispatch", exc, path=str(directory))
        return _failure(
            action_key=action_key,
            path=directory,
            message=f"Failed to consume IWH at {directory}: {exc}",
            outcome="errored",
        )

    if parsed is None:
        return _failure(
            action_key=action_key,
            path=directory,
            message=f"No IWH signal found at {directory}",
        )

    return _success(
        action_key=action_key,
        path=directory,
        message=f"Consumed superseded IWH at {directory} (scope={parsed.scope})",
    )


# ---------------------------------------------------------------------------
# write_reactive_iwh
# ---------------------------------------------------------------------------


def write_reactive_iwh(item: TriageItem, ctx: DispatchContext) -> SubAgentResult:
    """Write a ``scope=warning`` IWH signal at the triage item's directory.

    Used when the curator wants to leave a reactive coordination message
    for the next agent session.  The directory comes from
    ``item.source_item.path``; the body is the triage item's message so
    readers of the signal see the originating check.

    On :class:`OSError` the failure is recorded in ``ctx.summary`` and
    returned as ``outcome="errored"``.
    """
    action_key = item.action_key
    directory = item.source_item.path
    if directory is None:
        return _failure(
            action_key=action_key,
            path=None,
            message="No directory path available for write_reactive_iwh",
        )

    body = (
        f"Reactive IWH signal written by curator.\n"
        f"Action key: {action_key}\n"
        f"Originating message: {item.source_item.message}"
    )
    try:
        iwh_path = write_iwh(directory, author="curator", scope="warning", body=body)
    except OSError as exc:
        ctx.summary.add("dispatch", exc, path=str(directory))
        return _failure(
            action_key=action_key,
            path=directory,
            message=f"Failed to write reactive IWH at {directory}: {exc}",
            outcome="errored",
        )

    return _success(
        action_key=action_key,
        path=directory,
        message=f"Wrote reactive IWH at {iwh_path}",
    )


# ---------------------------------------------------------------------------
# flag_unresolvable_agent_design
# ---------------------------------------------------------------------------


def flag_unresolvable_agent_design(item: TriageItem, ctx: DispatchContext) -> SubAgentResult:
    """Flag an agent-edited design file the reconciliation agent cannot resolve.

    Writes a ``scope=warning`` IWH signal at the design file's parent
    directory so the next agent session sees the warning.  The signal body
    mentions the full design-file path so reviewers can open it directly.

    This helper is an *escalation only*: it never modifies the design file
    itself.  The reconciliation dispatcher is the canonical path that
    emits :class:`SubAgentResult` with this action key (see
    :func:`lexibrary.curator.reconciliation.reconciliation_result_to_sub_agent_result`);
    this helper exists so a triage item classified with the key still has
    a resolvable handler under the taxonomy self-check.
    """
    action_key = item.action_key
    design_path = item.source_item.path
    if design_path is None:
        return _failure(
            action_key=action_key,
            path=None,
            message="No design path available for flag_unresolvable_agent_design",
        )

    body = (
        f"Unresolvable agent-edited design file: {design_path}\n"
        f"Reconciliation returned low confidence; human review required.\n"
        f"Action: inspect the design file and reconcile against the source."
    )
    dest_dir = design_path.parent
    try:
        iwh_path = write_iwh(dest_dir, author="curator", scope="warning", body=body)
    except OSError as exc:
        ctx.summary.add("dispatch", exc, path=str(design_path))
        return _failure(
            action_key=action_key,
            path=design_path,
            message=f"Failed to write warning IWH for {design_path}: {exc}",
            outcome="errored",
        )

    return _success(
        action_key=action_key,
        path=design_path,
        message=f"Flagged unresolvable agent design {design_path} via {iwh_path}",
    )
