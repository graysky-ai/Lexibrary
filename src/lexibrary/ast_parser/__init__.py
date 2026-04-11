"""AST-based interface and symbol extraction for source files.

Provides public API for extracting, rendering, and hashing public interface
skeletons and per-file symbol extracts from Python, TypeScript, and
JavaScript files.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from lexibrary.ast_parser.models import (
    CallSite,
    InterfaceSkeleton,
    SymbolDefinition,
    SymbolExtract,
)
from lexibrary.ast_parser.registry import GRAMMAR_MAP
from lexibrary.ast_parser.skeleton_render import render_skeleton
from lexibrary.exceptions import ParseError
from lexibrary.utils.hashing import hash_file, hash_string

logger = logging.getLogger(__name__)

__all__ = [
    "CallSite",
    "InterfaceSkeleton",
    "SymbolDefinition",
    "SymbolExtract",
    "compute_hashes",
    "extract_symbols",
    "hash_interface",
    "parse_interface",
    "render_skeleton",
]

# Lazy mapping from language name to parser module. Both extractor families
# (``extract_interface`` and ``extract_symbols``) live in the same module
# per language, so the same map drives both dispatches.
_EXTRACTOR_MAP: dict[str, str] = {
    "python": "lexibrary.ast_parser.python_parser",
    "typescript": "lexibrary.ast_parser.typescript_parser",
    "tsx": "lexibrary.ast_parser.typescript_parser",
    "javascript": "lexibrary.ast_parser.javascript_parser",
}


_InterfaceExtractorFn = Callable[[Path], InterfaceSkeleton | None]
_SymbolExtractorFn = Callable[..., SymbolExtract | None]


def _get_extractor_module(extension: str) -> object | None:
    """Return the language module registered for ``extension``, or ``None``.

    Centralises the lazy import so both :func:`parse_interface` and
    :func:`extract_symbols` share a single registry lookup.
    """
    import importlib

    info = GRAMMAR_MAP.get(extension)
    if info is None:
        return None

    module_path = _EXTRACTOR_MAP.get(info.language_name)
    if module_path is None:
        return None

    try:
        return importlib.import_module(module_path)
    except ImportError:
        logger.debug("No extractor module available for extension %s", extension)
        return None


def _get_extractor(
    extension: str,
) -> _InterfaceExtractorFn | None:
    """Return the ``extract_interface`` callable for ``extension``."""
    module = _get_extractor_module(extension)
    if module is None:
        return None
    fn = getattr(module, "extract_interface", None)
    if fn is None:
        logger.debug("Module for %s has no extract_interface", extension)
        return None
    return fn  # type: ignore[no-any-return]


def _get_symbol_extractor(
    extension: str,
) -> _SymbolExtractorFn | None:
    """Return the ``extract_symbols`` callable for ``extension``."""
    module = _get_extractor_module(extension)
    if module is None:
        return None
    fn = getattr(module, "extract_symbols", None)
    if fn is None:
        logger.debug("Module for %s has no extract_symbols", extension)
        return None
    return fn  # type: ignore[no-any-return]


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
    except Exception as exc:
        raise ParseError(f"Failed to parse interface for {file_path}: {exc}") from exc


def extract_symbols(
    file_path: Path,
    project_root: Path | None = None,
) -> SymbolExtract | None:
    """Extract symbol definitions and call sites from a source file.

    Dispatches on the file extension exactly like :func:`parse_interface`.
    Returns ``None`` when the file extension has no registered grammar,
    the grammar package is not installed, or the file cannot be read.

    The Python extractor accepts an optional ``project_root`` so callers
    can pin the dotted-module prefix for qualified names (used extensively
    by the test fixtures). TypeScript and JavaScript extractors ignore
    the argument because their qualified names are rooted at the file
    stem.

    Args:
        file_path: Path to the source file to parse.
        project_root: Optional project root for Python qualified names.

    Returns:
        :class:`SymbolExtract` or ``None``.
    """
    extension = file_path.suffix.lower()
    extractor = _get_symbol_extractor(extension)
    if extractor is None:
        return None

    try:
        if extension in {".py", ".pyi"}:
            return extractor(file_path, project_root=project_root)
        return extractor(file_path)
    except Exception as exc:
        raise ParseError(
            f"Failed to extract symbols for {file_path}: {exc}",
        ) from exc


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

    interface_hash: str | None = None
    try:
        skeleton = parse_interface(file_path)
    except ParseError:
        logger.warning("Parse error computing interface hash for %s", file_path, exc_info=True)
        skeleton = None
    if skeleton is not None:
        interface_hash = hash_interface(skeleton)

    return (content_hash, interface_hash)
