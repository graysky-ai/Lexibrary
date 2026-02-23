"""AST-based interface extraction for source files.

Provides public API for extracting, rendering, and hashing
public interface skeletons from Python, TypeScript, and JavaScript files.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from lexibrary.ast_parser.models import InterfaceSkeleton
from lexibrary.ast_parser.registry import GRAMMAR_MAP
from lexibrary.ast_parser.skeleton_render import render_skeleton
from lexibrary.utils.hashing import hash_file, hash_string

logger = logging.getLogger(__name__)

__all__ = [
    "InterfaceSkeleton",
    "compute_hashes",
    "hash_interface",
    "parse_interface",
    "render_skeleton",
]

# Lazy mapping from language name to parser module's extract_interface function.
# Populated on first call to _get_extractor().
_EXTRACTOR_MAP: dict[str, str] = {
    "python": "lexibrary.ast_parser.python_parser",
    "typescript": "lexibrary.ast_parser.typescript_parser",
    "tsx": "lexibrary.ast_parser.typescript_parser",
    "javascript": "lexibrary.ast_parser.javascript_parser",
}


_ExtractorFn = Callable[[Path], InterfaceSkeleton | None]


def _get_extractor(
    extension: str,
) -> _ExtractorFn | None:
    """Return the extract_interface callable for a file extension, or None."""
    import importlib

    info = GRAMMAR_MAP.get(extension)
    if info is None:
        return None

    module_path = _EXTRACTOR_MAP.get(info.language_name)
    if module_path is None:
        return None

    try:
        mod = importlib.import_module(module_path)
        fn: _ExtractorFn = mod.extract_interface
        return fn
    except (ImportError, AttributeError):
        logger.debug("No extractor available for extension %s", extension)
        return None


def parse_interface(file_path: Path) -> InterfaceSkeleton | None:
    """Extract the public interface from a source file.

    Returns None if the file extension has no registered grammar,
    the grammar package is not installed, or the file cannot be read.

    Args:
        file_path: Path to the source file to parse.

    Returns:
        InterfaceSkeleton with the file's public interface, or None.
    """
    extension = file_path.suffix.lower()
    extractor = _get_extractor(extension)
    if extractor is None:
        return None

    try:
        return extractor(file_path)
    except Exception:
        logger.exception("Failed to parse interface for %s", file_path)
        return None


def hash_interface(skeleton: InterfaceSkeleton) -> str:
    """Render a skeleton to canonical text and return its SHA-256 hex digest.

    Args:
        skeleton: The interface skeleton to hash.

    Returns:
        64-character hexadecimal SHA-256 digest string.
    """
    canonical = render_skeleton(skeleton)
    return hash_string(canonical)


def compute_hashes(file_path: Path) -> tuple[str, str | None]:
    """Compute content hash and interface hash for a file.

    The content_hash is always available (SHA-256 of full file contents).
    The interface_hash is None if no grammar is available for the file type.

    Args:
        file_path: Path to the source file.

    Returns:
        Tuple of (content_hash, interface_hash). interface_hash may be None.
    """
    content_hash = hash_file(file_path)

    skeleton = parse_interface(file_path)
    interface_hash: str | None = None
    if skeleton is not None:
        interface_hash = hash_interface(skeleton)

    return (content_hash, interface_hash)
