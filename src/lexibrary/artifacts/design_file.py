"""Pydantic 2 models for design file artifacts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class DesignFileFrontmatter(BaseModel):
    """Agent-editable YAML frontmatter for a design file."""

    description: str
    id: str
    updated_by: Literal[
        "archivist", "agent", "bootstrap-quick", "maintainer", "curator", "skeleton-fallback"
    ] = "archivist"
    status: Literal["active", "unlinked", "deprecated"] = "active"
    deprecated_at: datetime | None = None
    deprecated_reason: Literal["source_deleted", "source_renamed", "manual"] | None = None


class StalenessMetadata(BaseModel):
    """Metadata embedded in the HTML comment footer of every generated artifact."""

    source: str
    source_hash: str
    interface_hash: str | None = None
    design_hash: str | None = None
    generated: datetime
    generator: str
    dependents_complete: bool = False


class EnumNote(BaseModel):
    """A single enum or constant note surfaced in the `## Enums & constants` section.

    Mirrors `EnumNote` in `baml_src/types.baml`. The `values` list is the literal
    enum members or constant values (e.g. ["PENDING", "RUNNING", "SUCCESS"]).
    """

    name: str
    role: str
    values: list[str] = Field(default_factory=list)


class CallPathNote(BaseModel):
    """A single narrative call-path note surfaced in the `## Call paths` section.

    Mirrors `CallPathNote` in `baml_src/types.baml`. `entry` is the entry-point
    symbol (e.g. `update_project()`) and `key_hops` lists the important symbols
    visited along the way — not a mechanical call stack, but the narratively
    meaningful hops.
    """

    entry: str
    narrative: str
    key_hops: list[str] = Field(default_factory=list)


class DataFlowNote(BaseModel):
    """A single data-flow note surfaced in the `## Data flows` section.

    Mirrors `DataFlowNote` in `baml_src/types.baml`. Records how a parameter
    appearing in branch conditions affects control flow: `parameter` is the
    parameter name, `location` is the function where the branching occurs,
    and `effect` is a one-sentence description of the behavioural impact.
    """

    parameter: str
    location: str
    effect: str


class DesignFile(BaseModel):
    """Represents a design file artifact for a single source file."""

    source_path: str
    frontmatter: DesignFileFrontmatter
    summary: str
    interface_contract: str
    dependencies: list[str] = []
    dependents: list[str] = []
    tests: str | None = None
    complexity_warning: str | None = None
    enum_notes: list[EnumNote] = Field(default_factory=list)
    call_path_notes: list[CallPathNote] = Field(default_factory=list)
    data_flow_notes: list[DataFlowNote] = Field(default_factory=list)
    wikilinks: list[str] = []
    tags: list[str] = []
    stack_refs: list[str] = []
    preserved_sections: dict[str, str] = {}
    # Aggregator-only: when set (non-None, non-empty), the serializer renders
    # ``## Re-exports`` instead of ``## Interface Contract``. Keys are source
    # modules (the ``X`` in ``from X import A, B``); values are the list of
    # names re-exported from that module. See §2.1 aggregator-design-rendering
    # spec and :func:`lexibrary.archivist.skeleton.classify_aggregator`.
    reexports: dict[str, list[str]] | None = None
    metadata: StalenessMetadata
