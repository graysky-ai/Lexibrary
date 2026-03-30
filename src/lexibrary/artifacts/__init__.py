"""Pydantic 2 data models for all Lexibrary artifact types."""

from __future__ import annotations

from lexibrary.artifacts.aindex import AIndexEntry, AIndexFile
from lexibrary.artifacts.concept import (
    ConceptFile,
    ConceptFileFrontmatter,
    concept_file_path,
    concept_slug,
)
from lexibrary.artifacts.convention import (
    ConventionFile,
    ConventionFileFrontmatter,
    convention_file_path,
    convention_slug,
)
from lexibrary.artifacts.design_file import DesignFile, DesignFileFrontmatter, StalenessMetadata
from lexibrary.artifacts.playbook import (
    PlaybookFile,
    PlaybookFileFrontmatter,
    playbook_file_path,
    playbook_slug,
)
from lexibrary.artifacts.slugs import slugify

__all__ = [
    "AIndexEntry",
    "AIndexFile",
    "ConceptFile",
    "ConceptFileFrontmatter",
    "ConventionFile",
    "ConventionFileFrontmatter",
    "DesignFile",
    "DesignFileFrontmatter",
    "PlaybookFile",
    "PlaybookFileFrontmatter",
    "StalenessMetadata",
    "concept_file_path",
    "concept_slug",
    "convention_file_path",
    "convention_slug",
    "playbook_file_path",
    "playbook_slug",
    "slugify",
]
