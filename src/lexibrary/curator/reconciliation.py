"""Reconciliation sub-agent for the curator.

Handles reconciliation of agent-edited design files where ``updated_by``
is ``"agent"`` or ``"maintainer"``, or where ``change_checker`` classifies
the file as ``AGENT_UPDATED`` (no metadata footer or design_hash drift).

Unlike the staleness resolver (which does full regeneration), the
reconciliation sub-agent preserves agent-authored knowledge (Key Concepts,
Dragons, Custom Notes, Insights) while regenerating mechanical sections
(Summary, Interface, Dependencies, Dependents) from the current source.

The write contract is owned by the shared helper
:func:`lexibrary.curator.write_contract.write_design_file_as_curator`,
which stamps ``updated_by="curator"``, recomputes
``source_hash``/``interface_hash`` from the current source file,
serializes via :func:`serialize_design_file` (which computes
``design_hash`` as a footer field), and writes atomically.  This module
is responsible only for building the in-memory :class:`DesignFile` that
merges agent-authored sections with regenerated mechanical sections.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from lexibrary.artifacts.design_file import (
    DesignFile,
    DesignFileFrontmatter,
    StalenessMetadata,
)
from lexibrary.artifacts.design_file_parser import (
    parse_design_file,
    parse_design_file_frontmatter,
)
from lexibrary.curator.models import SubAgentResult, TriageItem
from lexibrary.curator.write_contract import write_design_file_as_curator

if TYPE_CHECKING:
    from lexibrary.curator.dispatch_context import DispatchContext

logger = logging.getLogger(__name__)

# Confidence threshold: below this, do NOT write the result
_CONFIDENCE_THRESHOLD = 0.6


@dataclass
class ReconciliationWorkItem:
    """A single work item for the Reconciliation sub-agent."""

    source_path: Path
    design_path: Path
    source_hash_stale: bool = True
    interface_hash_stale: bool = False
    updated_by: str = ""
    risk_level: str = "low"


@dataclass
class ReconciliationResult:
    """Result from a single reconciliation attempt."""

    success: bool
    source_path: Path
    design_path: Path
    message: str = ""
    llm_calls: int = 0
    deferred: bool = False
    low_confidence: bool = False
    iwh_written: bool = False


def reconcile_agent_design(
    work_item: ReconciliationWorkItem,
    project_root: Path,
) -> ReconciliationResult:
    """Reconcile an agent-edited design file with current source.

    Reads the current source, reads the agent-edited design file, calls
    the BAML reconciliation stub, computes fresh hashes, and writes
    via ``atomic_write()``.  On low-confidence or malformed output,
    the result is NOT written -- an IWH signal is created instead.

    Args:
        work_item: Details of the agent-edited design file.
        project_root: Root directory of the project.

    Returns:
        A ReconciliationResult indicating success, deferral, or failure.
    """
    # Read the current source file
    try:
        source_content = work_item.source_path.read_text(encoding="utf-8")
    except OSError as exc:
        return ReconciliationResult(
            success=False,
            source_path=work_item.source_path,
            design_path=work_item.design_path,
            message=f"Failed to read source file: {exc}",
        )

    # Read the agent-edited design file
    try:
        agent_design_content = work_item.design_path.read_text(encoding="utf-8")
    except OSError as exc:
        return ReconciliationResult(
            success=False,
            source_path=work_item.source_path,
            design_path=work_item.design_path,
            message=f"Failed to read agent-edited design file: {exc}",
        )

    source_rel = str(work_item.source_path.relative_to(project_root))

    # Call the BAML stub to get reconciled content
    stub_result = _reconciliation_stub(
        source_path=source_rel,
        source_content=source_content,
        agent_design_content=agent_design_content,
    )

    if not stub_result.success:
        return ReconciliationResult(
            success=False,
            source_path=work_item.source_path,
            design_path=work_item.design_path,
            message=f"BAML reconciliation failed: {stub_result.message}",
            llm_calls=stub_result.llm_calls,
        )

    # Check confidence threshold
    if stub_result.confidence < _CONFIDENCE_THRESHOLD:
        # Low confidence -- write IWH signal, do NOT write the file
        _write_low_confidence_iwh(
            work_item.source_path,
            project_root,
            stub_result.confidence,
            stub_result.recommendation,
        )
        return ReconciliationResult(
            success=False,
            source_path=work_item.source_path,
            design_path=work_item.design_path,
            message=(
                f"Low-confidence reconciliation ({stub_result.confidence:.2f}), "
                f"recommendation={stub_result.recommendation!r}. "
                f"IWH signal written; existing file left in place."
            ),
            llm_calls=stub_result.llm_calls,
            low_confidence=True,
            iwh_written=True,
        )

    # Check for "full_regen" recommendation
    if stub_result.recommendation == "full_regen":
        return ReconciliationResult(
            success=False,
            source_path=work_item.source_path,
            design_path=work_item.design_path,
            message=(
                "Reconciler recommends full regeneration instead of merge. "
                "Agent edits appear to be low-value."
            ),
            llm_calls=stub_result.llm_calls,
            deferred=True,
        )

    # Get existing frontmatter to preserve design file ID and description
    existing_frontmatter = parse_design_file_frontmatter(work_item.design_path)
    design_id = (
        existing_frontmatter.id
        if existing_frontmatter is not None
        else source_rel.replace("/", "-").replace(".", "-")
    )
    description = (
        existing_frontmatter.description
        if existing_frontmatter is not None
        else f"Design file for {source_rel}"
    )

    # Build preserved sections from agent-authored content
    preserved_sections: dict[str, str] = {}

    # Preserve existing preserved_sections from the parsed design file
    import contextlib  # noqa: PLC0415

    existing_df = None
    with contextlib.suppress(Exception):
        existing_df = parse_design_file(work_item.design_path)

    if existing_df is not None:
        preserved_sections.update(existing_df.preserved_sections)

    # Add agent-authored sections from reconciliation output
    if stub_result.key_concepts:
        preserved_sections["Key Concepts"] = stub_result.key_concepts
    if stub_result.dragons:
        preserved_sections["Dragons"] = stub_result.dragons
    if stub_result.custom_notes:
        preserved_sections["Notes"] = stub_result.custom_notes
    if stub_result.insights:
        preserved_sections["Insights"] = stub_result.insights

    # Build the reconciled DesignFile.  ``updated_by`` and hash
    # metadata are set by :func:`write_design_file_as_curator` below.
    # Passing placeholder values here keeps the Pydantic model valid
    # until the helper overwrites them.
    df = DesignFile(
        source_path=source_rel,
        frontmatter=DesignFileFrontmatter(
            description=description,
            id=design_id,
            updated_by="curator",  # re-stamped by the shared write helper
            status="active",
        ),
        summary=stub_result.summary,
        interface_contract=stub_result.interface_contract,
        dependencies=stub_result.dependencies or [],
        dependents=stub_result.dependents or [],
        preserved_sections=preserved_sections,
        metadata=StalenessMetadata(
            source=source_rel,
            source_hash="",  # overwritten by the shared write helper
            interface_hash=None,
            generated=datetime.now(UTC),
            generator="curator-reconciliation",
        ),
    )

    # Delegate the write contract: the helper sets updated_by,
    # recomputes hashes, serializes, and atomically writes.
    try:
        write_design_file_as_curator(df, work_item.design_path, project_root)
    except Exception as exc:
        return ReconciliationResult(
            success=False,
            source_path=work_item.source_path,
            design_path=work_item.design_path,
            message=f"Failed to write reconciled design file: {exc}",
            llm_calls=stub_result.llm_calls,
        )

    logger.info(
        "Reconciled agent-edited design file for %s "
        "(source_hash=%s, interface_hash=%s, confidence=%.2f)",
        source_rel,
        df.metadata.source_hash[:12],
        df.metadata.interface_hash[:12] if df.metadata.interface_hash else "n/a",
        stub_result.confidence,
    )

    return ReconciliationResult(
        success=True,
        source_path=work_item.source_path,
        design_path=work_item.design_path,
        message=f"Reconciled design file for {source_rel}",
        llm_calls=stub_result.llm_calls,
    )


def reconciliation_result_to_sub_agent_result(
    result: ReconciliationResult,
) -> SubAgentResult:
    """Convert a ReconciliationResult to a SubAgentResult for the coordinator."""
    action_key = "reconcile_agent_interface_stable"
    if result.low_confidence:
        action_key = "flag_unresolvable_agent_design"
    return SubAgentResult(
        success=result.success,
        action_key=action_key,
        path=result.source_path,
        message=result.message,
        llm_calls=result.llm_calls,
    )


def dispatch_reconciliation(
    item: TriageItem,
    ctx: DispatchContext,
) -> SubAgentResult:
    """Dispatch an agent-edit reconciliation item.

    Sends the work item to the Reconciliation sub-agent (Opus) via BAML
    stub.  On successful return: passes through ``serialize_design_file()``,
    sets ``updated_by: curator``, computes fresh hashes, writes via
    ``atomic_write()``.

    On low-confidence or malformed output: does NOT write, creates IWH
    signal (scope: warning), records failure in report, leaves existing
    stale file in place.

    Extracted from :class:`Coordinator._dispatch_reconciliation`
    (Phase 1.5 dispatcher refactor).
    """
    from lexibrary.utils.paths import mirror_path  # noqa: PLC0415

    source_path = item.source_item.path
    if source_path is None:
        return SubAgentResult(
            success=False,
            action_key=item.action_key,
            path=None,
            message="No source path available for reconciliation",
        )

    design_path = mirror_path(ctx.project_root, source_path)

    work_item = ReconciliationWorkItem(
        source_path=source_path,
        design_path=design_path,
        source_hash_stale=item.source_item.source_hash_stale,
        interface_hash_stale=item.source_item.interface_hash_stale,
        updated_by=item.source_item.updated_by,
        risk_level=item.risk_level or "low",
    )

    try:
        result = reconcile_agent_design(work_item, ctx.project_root)
        return reconciliation_result_to_sub_agent_result(result)
    except Exception as exc:
        ctx.summary.add(
            "dispatch",
            exc,
            path=str(source_path),
        )
        return SubAgentResult(
            success=False,
            action_key=item.action_key,
            path=source_path,
            message=f"Reconciliation error: {exc}",
        )


def _write_low_confidence_iwh(
    source_path: Path,
    project_root: Path,
    confidence: float,
    recommendation: str,
) -> None:
    """Write an IWH signal for a low-confidence reconciliation.

    The signal warns that reconciliation was attempted but produced
    output below the confidence threshold, so the existing stale
    design file was left in place.
    """
    from lexibrary.iwh.writer import write_iwh  # noqa: PLC0415
    from lexibrary.utils.paths import mirror_path  # noqa: PLC0415

    design_path = mirror_path(project_root, source_path)
    iwh_dir = design_path.parent

    try:
        source_rel = str(source_path.relative_to(project_root))
    except ValueError:
        source_rel = str(source_path)

    body = (
        f"Curator reconciliation produced low-confidence output "
        f"(confidence={confidence:.2f}, recommendation={recommendation!r}) "
        f"for {source_rel}. Existing stale design file left in place. "
        f"Manual review recommended."
    )

    try:
        write_iwh(iwh_dir, author="curator", scope="warning", body=body)
    except Exception as exc:
        logger.warning("Failed to write low-confidence IWH signal: %s", exc)


# ---------------------------------------------------------------------------
# BAML Reconciliation stub
# ---------------------------------------------------------------------------


@dataclass
class _ReconciliationStubResult:
    """Result from the BAML reconciliation stub."""

    success: bool
    summary: str = ""
    interface_contract: str = ""
    dependencies: list[str] | None = None
    dependents: list[str] | None = None
    key_concepts: str | None = None
    dragons: str | None = None
    custom_notes: str | None = None
    insights: str | None = None
    confidence: float = 0.85
    recommendation: str = "merge"
    message: str = ""
    llm_calls: int = 0


def _reconciliation_stub(
    *,
    source_path: str,
    source_content: str,
    agent_design_content: str,
) -> _ReconciliationStubResult:
    """BAML stub for the Reconciliation Agent (Opus).

    In production this will call the ``CuratorReconcileDesignFile`` BAML
    function.  The stub returns a placeholder result using minimal
    content from the source, sufficient for the coordinator to exercise
    the full write contract.

    Input fields (for future BAML function):
      - source_path: relative path to the source file
      - source_content: full content of the source file
      - agent_design_content: full content of the agent-edited design file

    Output fields (from future BAML function):
      - summary: regenerated one-sentence description
      - interface_contract: regenerated public API surface
      - dependencies: regenerated project-local dependency paths
      - key_concepts: preserved agent key concepts (or None)
      - dragons: preserved agent dragons (or None)
      - custom_notes: preserved agent notes (or None)
      - insights: preserved insights section (or None)
      - confidence: float 0.0-1.0
      - recommendation: "merge" | "full_regen" | "human_review"
    """
    # Extract preserved sections from the agent design content
    # In the stub, we do simple extraction of known sections
    key_concepts = _extract_section(agent_design_content, "Key Concepts")
    dragons = _extract_section(agent_design_content, "Dragons")
    insights = _extract_section(agent_design_content, "Insights")

    return _ReconciliationStubResult(
        success=True,
        summary=f"(stub) Design file for {source_path}",
        interface_contract="# Stub: interface contract pending BAML integration",
        dependencies=[],
        dependents=[],
        key_concepts=key_concepts,
        dragons=dragons,
        custom_notes=None,
        insights=insights,
        confidence=0.85,
        recommendation="merge",
        message=f"stub: reconciled {source_path}",
        llm_calls=1,
    )


def _extract_section(content: str, heading: str) -> str | None:
    """Extract the content of a markdown section by heading name.

    Returns the section body text, or None if the heading is not found.
    """
    import re  # noqa: PLC0415

    # Match "## <heading>" and capture until the next "## " or end
    pattern = rf"^##\s+{re.escape(heading)}\s*\n(.*?)(?=^##\s|\Z)"
    match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
    if match:
        body = match.group(1).strip()
        return body if body else None
    return None
