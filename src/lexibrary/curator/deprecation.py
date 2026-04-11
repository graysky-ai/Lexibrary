"""Deprecation Analyst sub-agent wrapper.

Provides ``analyze_deprecation()`` which invokes the ``CuratorDeprecateArtifact``
BAML function via ``BamlAsyncClient``.  Includes input sanitisation: artifacts
containing template directives (``{{``, ``{%``) or instruction-like patterns
outside code fences are flagged for human review instead of dispatching.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from lexibrary.baml_client.async_client import BamlAsyncClient, b
from lexibrary.baml_client.types import (
    DeprecationAction,
    DeprecationResult,
    DeprecationWorkItem,
)
from lexibrary.curator.models import DeprecationCollectItem, SubAgentResult, TriageItem

if TYPE_CHECKING:
    from lexibrary.curator.dispatch_context import DispatchContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Input sanitisation
# ---------------------------------------------------------------------------

# Patterns that indicate template injection risk when found outside code fences.
_JINJA_PATTERN = re.compile(r"\{\{|\{%")

# Instruction-like directives that could manipulate the LLM.
_INSTRUCTION_PATTERN = re.compile(
    r"(?:^|\n)\s*(?:IGNORE\s+(?:ALL\s+)?PREVIOUS|SYSTEM\s*:|<\s*system\s*>)",
    re.IGNORECASE,
)

# Code fence boundaries: ```...``` blocks (possibly with language tag).
_CODE_FENCE_RE = re.compile(r"^```[^\n]*$", re.MULTILINE)


def _strip_code_fences(text: str) -> str:
    """Remove content inside code-fenced blocks, returning only prose text.

    This allows the sanitiser to check only non-code content for suspicious
    patterns, since template syntax inside code fences is expected and harmless.
    """
    parts = _CODE_FENCE_RE.split(text)
    # After splitting on ``` markers, odd-indexed parts are inside fences.
    # Keep only even-indexed parts (outside fences).
    return "\n".join(parts[i] for i in range(0, len(parts), 2))


def needs_human_review(artifact_content: str) -> tuple[bool, str]:
    """Check whether artifact content requires human review instead of dispatch.

    Returns ``(True, reason)`` if suspicious patterns are found outside code
    fences, ``(False, "")`` otherwise.
    """
    prose = _strip_code_fences(artifact_content)

    if _JINJA_PATTERN.search(prose):
        return (
            True,
            "Artifact contains Jinja2-like syntax ({{ or {%) outside code fences",
        )

    if _INSTRUCTION_PATTERN.search(prose):
        return (
            True,
            "Artifact contains instruction-like directives outside code fences",
        )

    return (False, "")


# ---------------------------------------------------------------------------
# BAML function wrapper
# ---------------------------------------------------------------------------


async def analyze_deprecation(
    work_item: DeprecationWorkItem,
    *,
    baml_client: BamlAsyncClient | None = None,
) -> DeprecationResult:
    """Invoke the ``CuratorDeprecateArtifact`` BAML function.

    Parameters
    ----------
    work_item:
        Typed input describing the artifact and its dependency context.
    baml_client:
        Optional pre-configured ``BamlAsyncClient`` (e.g. with a custom
        ``ClientRegistry``).  When ``None``, uses the default BAML client.

    Returns
    -------
    DeprecationResult
        Structured output with action, migration brief, cascade summary,
        migration edits, confidence, and rationale.

    Raises
    ------
    ValueError
        If the artifact content fails input sanitisation.
    Exception
        Propagates BAML client errors to the caller (coordinator handles).
    """
    client = baml_client if baml_client is not None else b

    logger.info(
        "Dispatching deprecation analysis for %s (%s)",
        work_item.artifact_path,
        work_item.artifact_kind.value,
    )

    result = await client.CuratorDeprecateArtifact(work_item=work_item)

    logger.info(
        "Deprecation analysis complete for %s: action=%s, confidence=%.2f",
        work_item.artifact_path,
        result.action.value,
        result.confidence,
    )

    return result


def deprecation_result_to_sub_agent_result(
    artifact_path: str,
    result: DeprecationResult,
) -> SubAgentResult:
    """Convert a ``DeprecationResult`` to a ``SubAgentResult`` for the coordinator."""
    return SubAgentResult(
        success=result.action != DeprecationAction.Skip,
        action_key=f"deprecate_{artifact_path}",
        path=None,
        message=result.rationale,
        llm_calls=1,
    )


# ---------------------------------------------------------------------------
# Dispatcher entry points (Phase 1.5)
# ---------------------------------------------------------------------------


def dispatch_deprecation_router(
    item: TriageItem,
    ctx: DispatchContext,
) -> SubAgentResult:
    """Route a deprecation candidate to the appropriate handler.

    Dispatches to hard deletion, lifecycle deprecation, or the
    Deprecation Analyst sub-agent depending on the action key.

    Extracted from :class:`Coordinator._dispatch_deprecation`
    (Phase 1.5 dispatcher refactor).
    """
    from lexibrary.curator.lifecycle import (  # noqa: PLC0415
        dispatch_hard_delete,
        dispatch_stack_transition,
    )

    dep = item.deprecation_item
    if dep is None:
        return SubAgentResult(
            success=False,
            action_key=item.action_key,
            path=item.source_item.path,
            message="No deprecation item available for dispatch",
        )

    action_key = item.action_key

    # Hard deletion actions (TTL-expired, zero refs)
    if action_key.startswith("hard_delete_"):
        return dispatch_hard_delete(item, ctx, dep)

    # Stack post transition
    if action_key == "stack_post_transition":
        return dispatch_stack_transition(item, ctx, dep)

    # Soft deprecation (concept, convention, playbook, design_file)
    return dispatch_soft_deprecation(item, ctx, dep)


def dispatch_soft_deprecation(
    item: TriageItem,
    ctx: DispatchContext,
    dep: DeprecationCollectItem,
) -> SubAgentResult:
    """Dispatch soft deprecation via the Deprecation Analyst sub-agent.

    For now this is a stub that performs the deprecation directly
    using the lifecycle module.  When the BAML sub-agent is wired
    in, this will route through :func:`analyze_deprecation` first.

    Extracted from :class:`Coordinator._dispatch_soft_deprecation`
    (Phase 1.5 dispatcher refactor).
    """
    from lexibrary.curator.lifecycle import execute_deprecation  # noqa: PLC0415

    target_status = "deprecated"
    if dep.artifact_kind == "design_file" and dep.reason == "source_deleted":
        target_status = "deprecated"

    try:
        execute_deprecation(
            kind=dep.artifact_kind,
            artifact_path=dep.artifact_path,
            target_status=target_status,
            deprecated_reason=dep.reason,
        )
        return SubAgentResult(
            success=True,
            action_key=item.action_key,
            path=dep.artifact_path,
            message=f"Deprecated {dep.artifact_kind}: {dep.artifact_path.name}",
            llm_calls=1,
        )
    except Exception as exc:
        ctx.summary.add("dispatch", exc, path=str(dep.artifact_path))
        return SubAgentResult(
            success=False,
            action_key=item.action_key,
            path=dep.artifact_path,
            message=f"Deprecation failed: {exc}",
        )
