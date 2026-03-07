"""Deprecation lifecycle management for design files.

Handles orphan detection, soft deprecation, TTL expiry, hard deletion,
rename detection (via ``git diff --find-renames`` and content-hash fallback),
and design-file migration on rename.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from lexibrary.artifacts.design_file_parser import (
    parse_design_file,
    parse_design_file_frontmatter,
    parse_design_file_metadata,
)
from lexibrary.artifacts.design_file_serializer import serialize_design_file
from lexibrary.utils.paths import DESIGNS_DIR, mirror_path

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class OrphanedDesign:
    """A design file whose source file no longer exists on disk."""

    design_path: Path
    """Absolute path to the orphaned design file."""

    source_path: Path
    """The missing source path (relative to the project root)."""

    committed: bool
    """True when the source deletion has been committed to git."""


@dataclass
class RenameMapping:
    """Maps an old source path to a new source path after a rename."""

    old_path: Path
    """Previous relative path of the source file."""

    new_path: Path
    """New relative path of the source file."""


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _is_committed_deletion(project_root: Path, source_rel: Path) -> bool:
    """Return True if the source file deletion has been committed to git.

    Uses ``git ls-files`` to check whether the file is still tracked.  If the
    file is tracked (present in the index) but missing from the working tree
    it is an *uncommitted* deletion.  If git does not track the file at all
    the deletion has been committed (or the file was never tracked, which we
    treat identically -- the design is orphaned either way).
    """
    try:
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(source_rel)],
            capture_output=True,
            text=True,
            cwd=str(project_root),
            check=False,
        )
        # Exit 0 means the file is still in the index (uncommitted deletion)
        # Exit 1 means it is not tracked at all (committed deletion or never tracked)
        return result.returncode != 0
    except FileNotFoundError:
        # git not installed -- treat as committed to be safe
        return True


def _count_commits_since(project_root: Path, since_iso: str) -> int:
    """Count the number of commits since the given ISO 8601 timestamp."""
    try:
        result = subprocess.run(
            ["git", "rev-list", "--count", f"--since={since_iso}", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(project_root),
            check=False,
        )
        if result.returncode == 0:
            return int(result.stdout.strip())
    except (FileNotFoundError, ValueError):
        pass
    return 0


# ---------------------------------------------------------------------------
# Orphan detection
# ---------------------------------------------------------------------------


def detect_orphaned_designs(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[OrphanedDesign]:
    """Scan design files and find those whose source no longer exists on disk.

    Parameters
    ----------
    project_root:
        Absolute path to the project root.
    lexibrary_dir:
        Absolute path to the ``.lexibrary`` directory.

    Returns
    -------
    list[OrphanedDesign]
        Design files whose ``source_path`` is missing from the working tree.
    """
    designs_root = lexibrary_dir / DESIGNS_DIR
    if not designs_root.exists():
        return []

    orphans: list[OrphanedDesign] = []

    for design_path in sorted(designs_root.rglob("*.md")):
        # Skip non-file entries and hidden files (like .aindex)
        if not design_path.is_file():
            continue

        # Try to parse frontmatter + metadata to get source_path
        parsed = parse_design_file(design_path)
        if parsed is None:
            continue

        source_rel = Path(parsed.source_path)
        source_abs = project_root / source_rel

        if not source_abs.exists():
            committed = _is_committed_deletion(project_root, source_rel)
            orphans.append(
                OrphanedDesign(
                    design_path=design_path,
                    source_path=source_rel,
                    committed=committed,
                )
            )

    return orphans


# ---------------------------------------------------------------------------
# Frontmatter update functions
# ---------------------------------------------------------------------------


def deprecate_design(design_path: Path, reason: str) -> None:
    """Mark a design file as deprecated by updating its frontmatter.

    Sets ``status`` to ``"deprecated"``, ``deprecated_at`` to the current UTC
    timestamp, and ``deprecated_reason`` to *reason*.

    Parameters
    ----------
    design_path:
        Absolute path to the design file.
    reason:
        The deprecation reason (e.g. ``"source_deleted"``, ``"source_renamed"``).
    """
    parsed = parse_design_file(design_path)
    if parsed is None:
        return

    parsed.frontmatter.status = "deprecated"
    parsed.frontmatter.deprecated_at = datetime.now(UTC).replace(microsecond=0)
    parsed.frontmatter.deprecated_reason = reason  # type: ignore[assignment]

    design_path.write_text(serialize_design_file(parsed), encoding="utf-8")


def mark_unlinked(design_path: Path) -> None:
    """Mark a design file as unlinked (source deleted but not yet committed).

    Sets ``status`` to ``"unlinked"`` without setting ``deprecated_at``.

    Parameters
    ----------
    design_path:
        Absolute path to the design file.
    """
    parsed = parse_design_file(design_path)
    if parsed is None:
        return

    parsed.frontmatter.status = "unlinked"

    design_path.write_text(serialize_design_file(parsed), encoding="utf-8")


def restore_design(design_path: Path) -> None:
    """Restore a deprecated or unlinked design file to active status.

    Resets ``status`` to ``"active"``, ``deprecated_at`` to ``None``, and
    ``deprecated_reason`` to ``None``.

    Parameters
    ----------
    design_path:
        Absolute path to the design file.
    """
    parsed = parse_design_file(design_path)
    if parsed is None:
        return

    parsed.frontmatter.status = "active"
    parsed.frontmatter.deprecated_at = None
    parsed.frontmatter.deprecated_reason = None

    design_path.write_text(serialize_design_file(parsed), encoding="utf-8")


# ---------------------------------------------------------------------------
# TTL expiry
# ---------------------------------------------------------------------------


def check_ttl_expiry(
    design_path: Path,
    project_root: Path,
    ttl_commits: int,
) -> bool:
    """Check whether a deprecated design file has exceeded its TTL.

    Returns ``True`` if the number of commits since ``deprecated_at`` exceeds
    *ttl_commits*.

    Parameters
    ----------
    design_path:
        Absolute path to the design file.
    project_root:
        Absolute path to the project root (for git operations).
    ttl_commits:
        Maximum number of commits before the design file should be deleted.

    Returns
    -------
    bool
        ``True`` if TTL has expired.
    """
    frontmatter = parse_design_file_frontmatter(design_path)
    if frontmatter is None:
        return False
    if frontmatter.status != "deprecated" or frontmatter.deprecated_at is None:
        return False

    since_iso = frontmatter.deprecated_at.isoformat()
    commit_count = _count_commits_since(project_root, since_iso)
    return commit_count > ttl_commits


def hard_delete_expired(
    project_root: Path,
    lexibrary_dir: Path,
    ttl_commits: int,
) -> list[Path]:
    """Delete design files whose deprecation TTL has expired.

    Parameters
    ----------
    project_root:
        Absolute path to the project root.
    lexibrary_dir:
        Absolute path to the ``.lexibrary`` directory.
    ttl_commits:
        Maximum number of commits before a deprecated design file is deleted.

    Returns
    -------
    list[Path]
        Absolute paths of deleted design files.
    """
    designs_root = lexibrary_dir / DESIGNS_DIR
    if not designs_root.exists():
        return []

    deleted: list[Path] = []

    for design_path in sorted(designs_root.rglob("*.md")):
        if not design_path.is_file():
            continue

        frontmatter = parse_design_file_frontmatter(design_path)
        if frontmatter is None:
            continue
        if frontmatter.status != "deprecated":
            continue

        if check_ttl_expiry(design_path, project_root, ttl_commits):
            design_path.unlink()
            deleted.append(design_path)

    return deleted


# ---------------------------------------------------------------------------
# Rename detection
# ---------------------------------------------------------------------------


def detect_renames(project_root: Path) -> list[RenameMapping]:
    """Detect file renames using ``git diff --find-renames``.

    Compares the current HEAD against the working tree (staged changes)
    and also against ``HEAD~1`` to catch recently committed renames.

    Parameters
    ----------
    project_root:
        Absolute path to the project root.

    Returns
    -------
    list[RenameMapping]
        Detected rename mappings.
    """
    mappings: list[RenameMapping] = []

    # Check staged renames (HEAD vs index)
    for diff_args in [
        ["git", "diff", "--find-renames", "--name-status", "--cached"],
        ["git", "diff", "--find-renames", "--name-status", "HEAD~1", "HEAD"],
    ]:
        try:
            result = subprocess.run(
                diff_args,
                capture_output=True,
                text=True,
                cwd=str(project_root),
                check=False,
            )
            if result.returncode != 0:
                continue

            for line in result.stdout.strip().splitlines():
                parts = line.split("\t")
                # Rename lines look like: R100\told_path\tnew_path
                if len(parts) >= 3 and parts[0].startswith("R"):
                    old_path = Path(parts[1])
                    new_path = Path(parts[2])
                    mapping = RenameMapping(old_path=old_path, new_path=new_path)
                    # Avoid duplicates
                    if not any(m.old_path == old_path and m.new_path == new_path for m in mappings):
                        mappings.append(mapping)
        except FileNotFoundError:
            # git not available
            break

    return mappings


def migrate_design_on_rename(
    project_root: Path,
    old_source: Path,
    new_source: Path,
) -> Path:
    """Move and update a design file after its source file was renamed.

    1. Moves the design file from the old mirror location to the new one.
    2. Updates ``source_path`` in the frontmatter/metadata.
    3. Preserves all authored content (annotations, agent-edited descriptions).
    4. Resets ``status`` to ``"active"`` if it was ``"deprecated"`` or ``"unlinked"``.

    Parameters
    ----------
    project_root:
        Absolute path to the project root.
    old_source:
        Previous relative source path.
    new_source:
        New relative source path.

    Returns
    -------
    Path
        Absolute path to the new design file location.

    Raises
    ------
    FileNotFoundError
        If the old design file does not exist.
    """
    old_design = mirror_path(project_root, old_source)
    new_design = mirror_path(project_root, new_source)

    if not old_design.exists():
        msg = f"Design file not found: {old_design}"
        raise FileNotFoundError(msg)

    # Parse the existing design file
    parsed = parse_design_file(old_design)
    if parsed is None:
        # Can't parse -- just move the file as-is
        new_design.parent.mkdir(parents=True, exist_ok=True)
        old_design.rename(new_design)
        return new_design

    # Update source path
    parsed.source_path = str(new_source)
    parsed.metadata.source = str(new_source)

    # Reset status if deprecated/unlinked
    if parsed.frontmatter.status in ("deprecated", "unlinked"):
        parsed.frontmatter.status = "active"
        parsed.frontmatter.deprecated_at = None
        parsed.frontmatter.deprecated_reason = None

    # Write to new location
    new_design.parent.mkdir(parents=True, exist_ok=True)
    new_design.write_text(serialize_design_file(parsed), encoding="utf-8")

    # Remove old design file
    if old_design.exists():
        old_design.unlink()

    return new_design


# ---------------------------------------------------------------------------
# Content-hash rename detection (fallback)
# ---------------------------------------------------------------------------


def _file_content_hash(path: Path) -> str | None:
    """Compute SHA-256 of a file's content, or None if unreadable."""
    try:
        content = path.read_bytes()
        return hashlib.sha256(content).hexdigest()
    except OSError:
        return None


def detect_renames_by_hash(
    deprecated_designs: list[Path],
    new_files: list[Path],
    project_root: Path,
) -> list[RenameMapping]:
    """Detect renames by matching source content hashes.

    This is a fallback when ``git diff --find-renames`` does not detect a
    rename.  It compares the ``source_hash`` from each deprecated design
    file's metadata with the SHA-256 hash of each new source file.

    Parameters
    ----------
    deprecated_designs:
        Absolute paths to recently deprecated design files.
    new_files:
        Absolute paths to newly created source files.
    project_root:
        Absolute path to the project root.

    Returns
    -------
    list[RenameMapping]
        Rename mappings based on content hash matching.
    """
    if not deprecated_designs or not new_files:
        return []

    # Build a map from source_hash -> deprecated design's source path
    hash_to_deprecated: dict[str, Path] = {}
    for design_path in deprecated_designs:
        metadata = parse_design_file_metadata(design_path)
        if metadata is None:
            continue
        source_hash = metadata.source_hash
        if source_hash:
            # Store the source path (relative) associated with this hash
            hash_to_deprecated[source_hash] = Path(metadata.source)

    if not hash_to_deprecated:
        return []

    # Hash each new file and look for matches
    mappings: list[RenameMapping] = []
    matched_hashes: set[str] = set()

    for new_file in new_files:
        content_hash = _file_content_hash(new_file)
        if content_hash is None:
            continue
        if content_hash in hash_to_deprecated and content_hash not in matched_hashes:
            old_source = hash_to_deprecated[content_hash]
            try:
                new_source = new_file.relative_to(project_root)
            except ValueError:
                new_source = new_file
            mappings.append(RenameMapping(old_path=old_source, new_path=new_source))
            matched_hashes.add(content_hash)

    return mappings
