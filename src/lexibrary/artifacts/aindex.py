"""Pydantic 2 models for .aindex file artifacts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from lexibrary.artifacts.design_file import StalenessMetadata


class AIndexEntry(BaseModel):
    """A single entry in a directory's .aindex file."""

    name: str
    entry_type: Literal["file", "dir"]
    description: str


class AIndexFile(BaseModel):
    """Represents a .aindex file artifact for a directory."""

    directory_path: str
    billboard: str
    entries: list[AIndexEntry]
    metadata: StalenessMetadata
