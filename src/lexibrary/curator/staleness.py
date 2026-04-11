"""Staleness Resolver sub-agent for the curator.

Handles regeneration of stale design files where `updated_by` is NOT
`"agent"` or `"maintainer"`.  Non-agent files receive full regeneration
via the archivist pipeline.  Agent-edited files are deferred for the
reconciliation sub-agent (Phase 1.5b).

The write contract is owned by the shared helper
:func:`lexibrary.curator.write_contract.write_design_file_as_curator`,
which stamps ``updated_by="curator"``, recomputes
``source_hash``/``interface_hash`` from the current source file,
serializes via :func:`serialize_design_file` (which computes
``design_hash`` as a footer field), and writes atomically.  This module
is responsible only for building the in-memory :class:`DesignFile`;
hashing and writing are delegated.
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

# updated_by values that indicate agent authorship -- these are NOT
# dispatched to the staleness resolver; they go to the reconciliation
# sub-agent instead.
_AGENT_UPDATED_BY = frozenset({"agent", "maintainer"})


@dataclass
class StalenessWorkItem:
    """A single work item for the Staleness Resolver."""

    source_path: Path
    design_path: Path
    source_hash_stale: bool = True
    interface_hash_stale: bool = False
    updated_by: str = ""


@dataclass
class StalenessResult:
    """Result from a single staleness resolution attempt."""

    success: bool
    source_path: Path
    design_path: Path
    message: str = ""
    llm_calls: int = 0
    deferred: bool = False


def is_agent_edited(updated_by: str) -> bool:
    """Return True if the file was edited by an agent or maintainer."""
    return updated_by in _AGENT_UPDATED_BY


def resolve_stale_design(
    work_item: StalenessWorkItem,
    project_root: Path,
) -> StalenessResult:
    """Resolve a stale non-agent design file via full regeneration.

    For non-agent-edited files, reads the current source, regenerates
    the design file content using the BAML staleness resolver stub,
    computes fresh hashes, and writes via ``atomic_write()``.

    Agent-edited files are returned as deferred -- they are NOT
    dispatched here.

    Args:
        work_item: Details of the stale design file.
        project_root: Root directory of the project.

    Returns:
        A StalenessResult indicating success, deferral, or failure.
    """
    # Guard: agent-edited files are deferred, not resolved here
    if is_agent_edited(work_item.updated_by):
        return StalenessResult(
            success=False,
            source_path=work_item.source_path,
            design_path=work_item.design_path,
            message=(
                f"Deferred: agent-edited file (updated_by={work_item.updated_by!r}) "
                f"requires reconciliation, not regeneration"
            ),
            deferred=True,
        )

    # Read the current source file
    try:
        source_content = work_item.source_path.read_text(encoding="utf-8")
    except OSError as exc:
        return StalenessResult(
            success=False,
            source_path=work_item.source_path,
            design_path=work_item.design_path,
            message=f"Failed to read source file: {exc}",
        )

    # Read the existing design file (for context)
    existing_design: str | None = None
    try:
        if work_item.design_path.exists():
            existing_design = work_item.design_path.read_text(encoding="utf-8")
    except OSError:
        pass  # Non-fatal; proceed without existing design context

    # Parse existing design file to preserve structure
    existing_df = None
    if existing_design is not None:
        import contextlib  # noqa: PLC0415

        with contextlib.suppress(Exception):
            existing_df = parse_design_file(work_item.design_path)

    source_rel = str(work_item.source_path.relative_to(project_root))

    # Call the BAML stub to get regenerated content
    regen_result = _staleness_resolver_stub(
        source_path=source_rel,
        source_content=source_content,
        existing_design_content=existing_design,
        source_hash_stale=work_item.source_hash_stale,
        interface_hash_stale=work_item.interface_hash_stale,
    )

    if not regen_result.success:
        return StalenessResult(
            success=False,
            source_path=work_item.source_path,
            design_path=work_item.design_path,
            message=f"BAML resolver failed: {regen_result.message}",
            llm_calls=regen_result.llm_calls,
        )

    # Get existing frontmatter to preserve the design file ID
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

    # Preserve any preserved_sections from existing design
    preserved_sections: dict[str, str] = {}
    if existing_df is not None:
        preserved_sections = dict(existing_df.preserved_sections)

    # Build the regenerated DesignFile.  ``updated_by`` and the
    # ``source_hash``/``interface_hash`` metadata fields are set by
    # :func:`write_design_file_as_curator` -- the helper both stamps
    # curator authorship and recomputes hashes from the on-disk source.
    # Passing empty-string placeholders here keeps the Pydantic model
    # valid until the helper overwrites them.
    df = DesignFile(
        source_path=source_rel,
        frontmatter=DesignFileFrontmatter(
            description=description,
            id=design_id,
            updated_by="archivist",  # overwritten by the shared write helper
            status="active",
        ),
        summary=regen_result.summary,
        interface_contract=regen_result.interface_contract,
        dependencies=regen_result.dependencies or [],
        dependents=regen_result.dependents or [],
        preserved_sections=preserved_sections,
        metadata=StalenessMetadata(
            source=source_rel,
            source_hash="",  # overwritten by the shared write helper
            interface_hash=None,
            generated=datetime.now(UTC),
            generator="curator-staleness-resolver",
        ),
    )

    # Delegate the write contract: the helper sets updated_by,
    # recomputes hashes, serializes, and atomically writes.
    try:
        write_design_file_as_curator(df, work_item.design_path, project_root)
    except Exception as exc:
        return StalenessResult(
            success=False,
            source_path=work_item.source_path,
            design_path=work_item.design_path,
            message=f"Failed to write design file: {exc}",
            llm_calls=regen_result.llm_calls,
        )

    logger.info(
        "Regenerated stale design file for %s (source_hash=%s, interface_hash=%s)",
        source_rel,
        df.metadata.source_hash[:12],
        df.metadata.interface_hash[:12] if df.metadata.interface_hash else "n/a",
    )

    return StalenessResult(
        success=True,
        source_path=work_item.source_path,
        design_path=work_item.design_path,
        message=f"Regenerated design file for {source_rel}",
        llm_calls=regen_result.llm_calls,
    )


def staleness_result_to_sub_agent_result(result: StalenessResult) -> SubAgentResult:
    """Convert a StalenessResult to a SubAgentResult for the coordinator."""
    return SubAgentResult(
        success=result.success,
        action_key="regenerate_stale_design",
        path=result.source_path,
        message=result.message,
        llm_calls=result.llm_calls,
    )


def dispatch_staleness_resolver(
    item: TriageItem,
    ctx: DispatchContext,
) -> SubAgentResult:
    """Dispatch a staleness item to the Staleness Resolver.

    For non-agent-edited files, the resolver regenerates the design
    file via the archivist pipeline (BAML stub for now).  Agent-edited
    files are returned as deferred.

    Extracted from :class:`Coordinator._dispatch_staleness_resolver`
    (Phase 1.5 dispatcher refactor).  The coordinator method is now a
    one-line delegation.
    """
    from lexibrary.utils.paths import mirror_path  # noqa: PLC0415

    source_path = item.source_item.path
    if source_path is None:
        return SubAgentResult(
            success=False,
            action_key="regenerate_stale_design",
            path=None,
            message="No source path available for staleness resolution",
        )

    design_path = mirror_path(ctx.project_root, source_path)

    work_item = StalenessWorkItem(
        source_path=source_path,
        design_path=design_path,
        source_hash_stale=item.source_item.source_hash_stale,
        interface_hash_stale=item.source_item.interface_hash_stale,
        updated_by=item.source_item.updated_by,
    )

    try:
        result = resolve_stale_design(work_item, ctx.project_root)
        return staleness_result_to_sub_agent_result(result)
    except Exception as exc:
        ctx.summary.add(
            "dispatch",
            exc,
            path=str(source_path),
        )
        return SubAgentResult(
            success=False,
            action_key="regenerate_stale_design",
            path=source_path,
            message=f"Staleness resolver error: {exc}",
        )


# ---------------------------------------------------------------------------
# BAML Staleness Resolver stub
# ---------------------------------------------------------------------------


@dataclass
class _ResolverStubResult:
    """Result from the BAML staleness resolver stub."""

    success: bool
    summary: str = ""
    interface_contract: str = ""
    dependencies: list[str] | None = None
    dependents: list[str] | None = None
    message: str = ""
    llm_calls: int = 0

    @property
    def dependencies_list(self) -> list[str]:
        return self.dependencies or []

    @property
    def dependents_list(self) -> list[str]:
        return self.dependents or []


def _staleness_resolver_stub(
    *,
    source_path: str,
    source_content: str,
    existing_design_content: str | None,
    source_hash_stale: bool,
    interface_hash_stale: bool,
) -> _ResolverStubResult:
    """BAML stub for the Staleness Resolver (Opus).

    In production this will call the ``CuratorResolveStaleness`` BAML
    function.  The stub returns a placeholder result using minimal
    content from the source, sufficient for the coordinator to exercise
    the full write contract.

    Input fields (for future BAML function):
      - source_path: relative path to the source file
      - source_content: full content of the source file
      - existing_design_content: current design file content (if any)
      - source_hash_stale: whether source_hash differs
      - interface_hash_stale: whether interface_hash differs

    Output fields (from future BAML function):
      - summary: one-sentence description of the file's purpose
      - interface_contract: public API surface as code block content
      - dependencies: list of project-local dependency paths
      - dependents: list of reverse dependency paths
    """
    # Stub: produce minimal valid content
    # In production, this will call the BAML function which regenerates
    # via the archivist prompt with hash mismatch context
    return _ResolverStubResult(
        success=True,
        summary=f"(stub) Design file for {source_path}",
        interface_contract="# Stub: interface contract pending BAML integration",
        dependencies=[],
        dependents=[],
        message=f"stub: regenerated {source_path}",
        llm_calls=1,
    )
