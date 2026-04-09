"""Staleness Resolver sub-agent for the curator.

Handles regeneration of stale design files where `updated_by` is NOT
`"agent"` or `"maintainer"`.  Non-agent files receive full regeneration
via the archivist pipeline.  Agent-edited files are deferred for the
reconciliation sub-agent (Phase 1.5b).

The write contract follows the shared design file write sequence:
1. Serialize via ``serialize_design_file()``
2. Write via ``atomic_write()``
3. ``updated_by`` set by the coordinator (``"archivist"`` for full regenerations)
4. ``source_hash`` and ``interface_hash`` computed fresh by the coordinator
5. ``design_hash`` computed by the serializer
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from lexibrary.artifacts.design_file import (
    DesignFile,
    DesignFileFrontmatter,
    StalenessMetadata,
)
from lexibrary.artifacts.design_file_parser import (
    parse_design_file,
    parse_design_file_frontmatter,
)
from lexibrary.artifacts.design_file_serializer import serialize_design_file
from lexibrary.ast_parser import compute_hashes
from lexibrary.curator.models import SubAgentResult
from lexibrary.utils.atomic import atomic_write

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

    # Compute fresh hashes from current source
    try:
        fresh_source_hash, fresh_interface_hash = compute_hashes(work_item.source_path)
    except Exception as exc:
        return StalenessResult(
            success=False,
            source_path=work_item.source_path,
            design_path=work_item.design_path,
            message=f"Failed to compute hashes: {exc}",
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

    # Build the regenerated DesignFile with fresh metadata
    # updated_by is set by the coordinator: "archivist" for full regenerations
    df = DesignFile(
        source_path=source_rel,
        frontmatter=DesignFileFrontmatter(
            description=description,
            id=design_id,
            updated_by="archivist",
            status="active",
        ),
        summary=regen_result.summary,
        interface_contract=regen_result.interface_contract,
        dependencies=regen_result.dependencies or [],
        dependents=regen_result.dependents or [],
        preserved_sections=preserved_sections,
        metadata=StalenessMetadata(
            source=source_rel,
            source_hash=fresh_source_hash,
            interface_hash=fresh_interface_hash,
            generated=datetime.now(UTC),
            generator="curator-staleness-resolver",
        ),
    )

    # Serialize and write atomically
    try:
        content = serialize_design_file(df)
        atomic_write(work_item.design_path, content)
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
        fresh_source_hash[:12],
        fresh_interface_hash[:12] if fresh_interface_hash else "n/a",
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
