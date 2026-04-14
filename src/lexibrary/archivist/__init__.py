"""Archivist module: LLM pipeline for generating design files and project documentation."""

from __future__ import annotations

from lexibrary.archivist.change_checker import ChangeLevel, check_change
from lexibrary.archivist.pipeline import UpdateStats, update_file, update_project
from lexibrary.archivist.service import (
    ArchivistService,
    DesignFileRequest,
    DesignFileResult,
    build_archivist_service,
)

__all__ = [
    "ArchivistService",
    "ChangeLevel",
    "DesignFileRequest",
    "DesignFileResult",
    "UpdateStats",
    "build_archivist_service",
    "check_change",
    "update_file",
    "update_project",
]
