"""Parser for v2 .aindex file artifacts."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from lexibrary.artifacts.aindex import AIndexEntry, AIndexFile
from lexibrary.artifacts.design_file import StalenessMetadata

_META_RE = re.compile(r"<!-- lexibrary:meta\s+(.*?)\s*-->", re.DOTALL)
_ATTR_RE = re.compile(r'(\w+)="([^"]*)"')
_TABLE_ROW_RE = re.compile(r"^\|\s*`(.+?)`\s*\|\s*(file|dir)\s*\|\s*(.*?)\s*\|$")


def _parse_meta(meta_str: str) -> StalenessMetadata | None:
    """Parse key=value pairs from the metadata string into StalenessMetadata."""
    attrs = dict(_ATTR_RE.findall(meta_str))
    try:
        return StalenessMetadata(
            source=attrs["source"],
            source_hash=attrs["source_hash"],
            interface_hash=attrs.get("interface_hash"),
            generated=datetime.fromisoformat(attrs["generated"]),
            generator=attrs["generator"],
        )
    except (KeyError, ValueError):
        return None


def parse_aindex_metadata(path: Path) -> StalenessMetadata | None:
    """Parse only the staleness metadata footer from a .aindex file.

    Cheaper than parse_aindex() — searches for the footer comment without
    fully parsing table sections. Returns None if file does not exist or
    the footer is absent.
    """
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = _META_RE.search(text)
    if not match:
        return None
    return _parse_meta(match.group(1))


def parse_aindex(path: Path) -> AIndexFile | None:
    """Parse a v2 .aindex file into an AIndexFile model.

    Returns None if the file does not exist or content is malformed beyond
    recovery (missing H1 heading, empty billboard, or absent metadata footer).
    Tolerant of minor whitespace differences.
    """
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    lines = text.splitlines()

    # --- Extract directory_path from H1 heading ---
    directory_path: str | None = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# "):
            directory_path = stripped[2:].strip().rstrip("/")
            break
    if directory_path is None:
        return None

    # --- Extract billboard: non-empty text between H1 and first H2 ---
    billboard_lines: list[str] = []
    in_billboard = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# ") and not in_billboard:
            in_billboard = True
            continue
        if in_billboard:
            if stripped.startswith("## "):
                break
            if stripped:
                billboard_lines.append(stripped)
    billboard = " ".join(billboard_lines).strip()
    if not billboard:
        return None

    # --- Locate section boundaries ---
    section_starts: dict[str, int] = {}
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("## "):
            section_name = stripped[3:].strip()
            section_starts[section_name] = i

    def _section_lines(name: str) -> list[str]:
        if name not in section_starts:
            return []
        start = section_starts[name]
        end = len(lines)
        for _, idx in section_starts.items():
            if idx > start:
                end = min(end, idx)
        return lines[start + 1 : end]

    # --- Parse Child Map table ---
    entries: list[AIndexEntry] = []
    for line in _section_lines("Child Map"):
        stripped = line.strip()
        if stripped == "(none)":
            break
        match = _TABLE_ROW_RE.match(stripped)
        if match:
            name_raw, entry_type, description = match.groups()
            name = name_raw.rstrip("/")
            entries.append(
                AIndexEntry(
                    name=name,
                    entry_type=entry_type,  # type: ignore[arg-type]
                    description=description,
                )
            )

    # NOTE: Legacy files may contain a "## Local Conventions" section.
    # The parser silently ignores it for backward compatibility.

    # --- Parse metadata footer ---
    meta_match = _META_RE.search(text)
    if not meta_match:
        return None
    metadata = _parse_meta(meta_match.group(1))
    if metadata is None:
        return None

    return AIndexFile(
        directory_path=directory_path,
        billboard=billboard,
        entries=entries,
        metadata=metadata,
    )
