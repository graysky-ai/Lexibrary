"""Index generator: produces AIndexFile models from directory contents."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from lexibrary.artifacts.aindex import AIndexEntry, AIndexFile
from lexibrary.artifacts.aindex_parser import parse_aindex
from lexibrary.artifacts.design_file import StalenessMetadata
from lexibrary.artifacts.design_file_parser import parse_design_file_frontmatter
from lexibrary.ignore.matcher import IgnoreMatcher
from lexibrary.utils.hashing import hash_string
from lexibrary.utils.languages import EXTENSION_MAP
from lexibrary.utils.paths import mirror_path

_GENERATOR_ID = "lexibrary-v2"


def _get_structural_description(file_path: Path, binary_extensions: set[str]) -> str:
    """Return a structural description string for a file entry."""
    ext = file_path.suffix.lower()
    if ext in binary_extensions:
        return f"Binary file ({ext})"
    language = EXTENSION_MAP.get(ext)
    if language is None:
        return "Unknown file type"
    try:
        line_count = len(file_path.read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError:
        line_count = 0
    return f"{language} source ({line_count} lines)"


def _get_file_description(
    file_path: Path,
    binary_extensions: set[str],
    project_root: Path,
) -> str:
    """Return a description for a file entry.

    Checks the design file frontmatter in the .lexibrary mirror tree first.
    If a non-empty description is found there, it is used. Otherwise falls
    back to a structural description (language + line count).
    """
    design_path = mirror_path(project_root, file_path)
    frontmatter = parse_design_file_frontmatter(design_path)
    if frontmatter is not None and frontmatter.description.strip():
        return frontmatter.description.strip()

    return _get_structural_description(file_path, binary_extensions)


def _get_dir_description(subdir: Path, project_root: Path) -> str:
    """Return a description for a subdirectory entry.

    Uses entry counts from its child .aindex in the .lexibrary mirror tree
    if available; otherwise falls back to a direct filesystem count.
    """
    mirror_aindex = project_root / ".lexibrary" / subdir.relative_to(project_root) / ".aindex"
    child_aindex = parse_aindex(mirror_aindex)
    if child_aindex is not None:
        file_count = sum(1 for e in child_aindex.entries if e.entry_type == "file")
        dir_count = sum(1 for e in child_aindex.entries if e.entry_type == "dir")
        if dir_count:
            return f"Contains {file_count} files, {dir_count} subdirectories"
        return f"Contains {file_count} files"
    # Fallback: count direct children in the filesystem
    try:
        count = sum(1 for _ in subdir.iterdir())
    except OSError:
        count = 0
    return f"Contains {count} items"


def _generate_billboard(entries: list[AIndexEntry]) -> str:
    """Generate a billboard sentence from the entries' descriptions."""
    if not entries:
        return "Empty directory."

    languages: list[str] = []
    for entry in entries:
        if entry.entry_type == "file" and " source (" in entry.description:
            lang = entry.description.split(" source (")[0]
            languages.append(lang)

    if not languages:
        return "Directory containing binary and data files."

    unique = sorted(set(languages))
    if len(unique) == 1:
        return f"Directory containing {unique[0]} source files."
    return f"Mixed-language directory ({', '.join(unique)})."


def _compute_dir_hash(names: list[str]) -> str:
    """SHA-256 of the sorted directory listing."""
    content = "\n".join(sorted(names))
    return hash_string(content)


def generate_aindex(
    directory: Path,
    project_root: Path,
    ignore_matcher: IgnoreMatcher,
    binary_extensions: set[str],
) -> AIndexFile:
    """Generate an AIndexFile model for *directory* without any I/O side effects.

    Lists directory contents, filters ignored entries, builds structural
    descriptions for files and subdirs, and computes a staleness hash.
    """
    try:
        children = sorted(directory.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        children = []

    entries: list[AIndexEntry] = []
    all_names: list[str] = []

    for child in children:
        if child.is_dir():
            if not ignore_matcher.should_descend(child):
                continue
        elif ignore_matcher.is_ignored(child):
            continue
        all_names.append(child.name)
        if child.is_file():
            description = _get_file_description(child, binary_extensions, project_root)
            entries.append(
                AIndexEntry(
                    name=child.name,
                    entry_type="file",
                    description=description,
                )
            )
        elif child.is_dir():
            description = _get_dir_description(child, project_root)
            entries.append(
                AIndexEntry(
                    name=child.name,
                    entry_type="dir",
                    description=description,
                )
            )

    billboard = _generate_billboard(entries)
    source_hash = _compute_dir_hash(all_names)

    try:
        rel_source = str(directory.relative_to(project_root))
    except ValueError:
        rel_source = str(directory)

    metadata = StalenessMetadata(
        source=rel_source,
        source_hash=source_hash,
        generated=datetime.now(UTC).replace(tzinfo=None),
        generator=_GENERATOR_ID,
    )

    return AIndexFile(
        directory_path=rel_source,
        billboard=billboard,
        entries=entries,
        local_conventions=[],
        metadata=metadata,
    )
