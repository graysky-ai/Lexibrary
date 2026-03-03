"""Index orchestrator: coordinates generation, serialization, and writing of .aindex files."""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from lexibrary.artifacts.aindex_serializer import serialize_aindex
from lexibrary.artifacts.writer import write_artifact
from lexibrary.config.schema import LexibraryConfig
from lexibrary.errors import ErrorSummary
from lexibrary.ignore import create_ignore_matcher
from lexibrary.indexer.generator import generate_aindex
from lexibrary.utils.paths import LEXIBRARY_DIR, aindex_path

logger = logging.getLogger(__name__)


@dataclass
class IndexStats:
    """Statistics from an indexing run."""

    directories_indexed: int = 0
    files_found: int = 0
    errors: int = 0
    error_summary: ErrorSummary = field(default_factory=ErrorSummary)


def index_directory(
    directory: Path,
    project_root: Path,
    config: LexibraryConfig,
) -> Path:
    """Generate and write a .aindex file for a single directory.

    Constructs an IgnoreMatcher, calls the generator to produce an AIndexFile
    model, serializes it to markdown, and writes it atomically to the
    .lexibrary mirror path.

    Args:
        directory: The directory to index.
        project_root: The project root (contains .lexibrary/).
        config: Project configuration.

    Returns:
        Path to the written .aindex file.
    """
    ignore_matcher = create_ignore_matcher(config, project_root)
    binary_extensions = set(config.crawl.binary_extensions)

    aindex_model = generate_aindex(directory, project_root, ignore_matcher, binary_extensions)
    markdown = serialize_aindex(aindex_model)

    output_path = aindex_path(project_root, directory)

    write_artifact(output_path, markdown)
    return output_path


def _discover_directories_bottom_up(
    root: Path,
    project_root: Path,
    config: LexibraryConfig,
) -> list[Path]:
    """Discover all directories under *root* in bottom-up (deepest-first) order.

    Skips the .lexibrary/ directory and any directories the IgnoreMatcher
    says should not be descended into.
    """
    ignore_matcher = create_ignore_matcher(config, project_root)
    lexibrary_path = (project_root / LEXIBRARY_DIR).resolve()

    directories: list[Path] = []
    stack: list[Path] = [root]

    while stack:
        current = stack.pop()
        directories.append(current)
        try:
            children = sorted(current.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            continue
        for child in children:
            if not child.is_dir():
                continue
            # Skip .lexibrary/ itself
            if child.resolve() == lexibrary_path:
                continue
            if not ignore_matcher.should_descend(child):
                continue
            stack.append(child)

    # Reverse so deepest directories come first (bottom-up)
    directories.reverse()
    return directories


def index_recursive(
    directory: Path,
    project_root: Path,
    config: LexibraryConfig,
    *,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> IndexStats:
    """Recursively index all directories under *directory* in bottom-up order.

    Discovers directories deepest-first so child .aindex files exist before
    their parents are processed. The .lexibrary/ directory is always excluded.

    Args:
        directory: Root directory to start recursive indexing from.
        project_root: The project root (contains .lexibrary/).
        config: Project configuration.
        progress_callback: Optional callback invoked after each directory is
            indexed, with (current_count, total_count, directory_name).

    Returns:
        IndexStats with counts of directories indexed, files found, and errors.
    """
    dirs = _discover_directories_bottom_up(directory, project_root, config)
    total = len(dirs)
    stats = IndexStats()

    for i, dir_path in enumerate(dirs, start=1):
        try:
            index_directory(dir_path, project_root, config)
            stats.directories_indexed += 1
            # Count files in the directory for stats
            with contextlib.suppress(OSError):
                stats.files_found += sum(1 for child in dir_path.iterdir() if child.is_file())
        except Exception as exc:
            logger.exception("Failed to index directory: %s", dir_path)
            stats.errors += 1
            stats.error_summary.add("indexer", exc, path=str(dir_path))

        if progress_callback is not None:
            progress_callback(i, total, dir_path.name)

    return stats
