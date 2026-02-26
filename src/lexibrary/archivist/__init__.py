"""Archivist module: LLM pipeline for generating design files and project documentation."""

from __future__ import annotations

from lexibrary.archivist.change_checker import ChangeLevel, check_change
from lexibrary.archivist.pipeline import UpdateStats, update_file, update_project
from lexibrary.archivist.scaffold import generate_design_scaffold
from lexibrary.archivist.service import (
    ArchivistService,
    DesignFileRequest,
    DesignFileResult,
)

__all__ = [
    "ArchivistService",
    "ChangeLevel",
    "DesignFileRequest",
    "DesignFileResult",
    "UpdateStats",
    "check_change",
    "generate_design_scaffold",
    "update_file",
    "update_project",
]
