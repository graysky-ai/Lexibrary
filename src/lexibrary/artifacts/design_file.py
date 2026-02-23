"""Pydantic 2 models for design file artifacts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class DesignFileFrontmatter(BaseModel):
    """Agent-editable YAML frontmatter for a design file."""

    description: str
    updated_by: Literal["archivist", "agent"] = "archivist"


class StalenessMetadata(BaseModel):
    """Metadata embedded in the HTML comment footer of every generated artifact."""

    source: str
    source_hash: str
    interface_hash: str | None = None
    design_hash: str | None = None
    generated: datetime
    generator: str


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
    wikilinks: list[str] = []
    tags: list[str] = []
    stack_refs: list[str] = []
    metadata: StalenessMetadata
