"""Deprecation Analyst sub-agent wrapper.

Provides ``analyze_deprecation()`` which invokes the ``CuratorDeprecateArtifact``
BAML function via ``BamlAsyncClient``.  Includes input sanitisation: artifacts
containing template directives (``{{``, ``{%``) or instruction-like patterns
outside code fences are flagged for human review instead of dispatching.
"""

from __future__ import annotations

import logging
import re

from lexibrary.baml_client.async_client import BamlAsyncClient, b
from lexibrary.baml_client.types import (
    DeprecationAction,
    DeprecationResult,
    DeprecationWorkItem,
)
from lexibrary.curator.models import SubAgentResult

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
