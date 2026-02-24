"""Grammar registry: maps file extensions to tree-sitter Language objects and parsers.

Handles lazy loading, caching, and graceful fallback when grammar packages
are not installed.

Import patterns (verified via spike, py-tree-sitter 0.25 API):
  - Python:     Language(tree_sitter_python.language())
  - TypeScript: Language(tree_sitter_typescript.language_typescript())
  - TSX:        Language(tree_sitter_typescript.language_tsx())
  - JavaScript: Language(tree_sitter_javascript.language())  # also handles JSX
"""

from __future__ import annotations

import importlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from rich.console import Console

if TYPE_CHECKING:
    from tree_sitter import Language, Parser

logger = logging.getLogger(__name__)

_console = Console(stderr=True)

# Track which languages have already emitted a missing-package warning,
# so we only warn once per language per session.
_warned_languages: set[str] = set()

# Module-level caches for loaded Language objects and Parser instances.
_language_cache: dict[str, Language] = {}
_parser_cache: dict[str, Parser] = {}


@dataclass(frozen=True)
class GrammarInfo:
    """Metadata for loading a tree-sitter grammar.

    Attributes:
        language_name: Human-readable language name (e.g. "python", "typescript").
        module_name: Python import path for the grammar package.
        loader: Callable that returns the raw language pointer from the grammar module.
            Receives the imported module as its sole argument.
        pip_package: The pip package name for installation instructions.
    """

    language_name: str
    module_name: str
    loader: Callable[[Any], Any]
    pip_package: str = "lexibrary[ast]"


def _load_python(mod: Any) -> Any:
    """Load the Python grammar from tree_sitter_python."""
    return mod.language()


def _load_typescript(mod: Any) -> Any:
    """Load the TypeScript sub-grammar from tree_sitter_typescript."""
    return mod.language_typescript()


def _load_tsx(mod: Any) -> Any:
    """Load the TSX sub-grammar from tree_sitter_typescript."""
    return mod.language_tsx()


def _load_javascript(mod: Any) -> Any:
    """Load the JavaScript grammar from tree_sitter_javascript."""
    return mod.language()


# Extension-to-grammar mapping.
# Each extension maps to a GrammarInfo describing how to load its grammar.
GRAMMAR_MAP: dict[str, GrammarInfo] = {
    ".py": GrammarInfo(
        language_name="python",
        module_name="tree_sitter_python",
        loader=_load_python,
    ),
    ".pyi": GrammarInfo(
        language_name="python",
        module_name="tree_sitter_python",
        loader=_load_python,
    ),
    ".ts": GrammarInfo(
        language_name="typescript",
        module_name="tree_sitter_typescript",
        loader=_load_typescript,
    ),
    ".tsx": GrammarInfo(
        language_name="tsx",
        module_name="tree_sitter_typescript",
        loader=_load_tsx,
    ),
    ".js": GrammarInfo(
        language_name="javascript",
        module_name="tree_sitter_javascript",
        loader=_load_javascript,
    ),
    ".jsx": GrammarInfo(
        language_name="javascript",
        module_name="tree_sitter_javascript",
        loader=_load_javascript,
    ),
}


def get_grammar_info(extension: str) -> GrammarInfo | None:
    """Look up grammar info for a file extension.

    Args:
        extension: File extension including the dot (e.g. ".py", ".ts").

    Returns:
        GrammarInfo if the extension is supported, None otherwise.
    """
    return GRAMMAR_MAP.get(extension)


def get_language(extension: str) -> Language | None:
    """Get a cached tree-sitter Language for the given file extension.

    Loads the grammar lazily on first access and caches it for the lifetime
    of the process. Returns None if the extension is unsupported or the
    grammar package is not installed.

    Args:
        extension: File extension including the dot (e.g. ".py").

    Returns:
        A tree_sitter.Language object, or None.
    """
    info = GRAMMAR_MAP.get(extension)
    if info is None:
        return None

    cache_key = info.language_name

    if cache_key in _language_cache:
        return _language_cache[cache_key]

    try:
        from tree_sitter import Language

        mod = importlib.import_module(info.module_name)
        raw_lang = info.loader(mod)
        language = Language(raw_lang)
        _language_cache[cache_key] = language
        return language
    except ImportError:
        if cache_key not in _warned_languages:
            _warned_languages.add(cache_key)
            _console.print(
                f"[yellow]WARNING:[/yellow] {info.module_name.replace('_', '-')} "
                f"not installed. Run: pip install {info.pip_package}"
            )
        return None
    except Exception as exc:
        from lexibrary.exceptions import ParseError  # noqa: PLC0415

        raise ParseError(
            f"Failed to load grammar for {extension}: {exc}"
        ) from exc


def get_parser(extension: str) -> Parser | None:
    """Get a cached tree-sitter Parser for the given file extension.

    Loads the grammar and creates the parser lazily on first access.
    Returns None if the extension is unsupported or the grammar package
    is not installed.

    Args:
        extension: File extension including the dot (e.g. ".py").

    Returns:
        A tree_sitter.Parser configured for the appropriate language, or None.
    """
    info = GRAMMAR_MAP.get(extension)
    if info is None:
        return None

    cache_key = info.language_name

    if cache_key in _parser_cache:
        return _parser_cache[cache_key]

    language = get_language(extension)
    if language is None:
        return None

    try:
        from tree_sitter import Parser

        parser = Parser(language)
        _parser_cache[cache_key] = parser
        return parser
    except Exception as exc:
        from lexibrary.exceptions import ParseError  # noqa: PLC0415

        raise ParseError(
            f"Failed to create parser for {extension}: {exc}"
        ) from exc


def get_supported_extensions() -> list[str]:
    """Return the list of all file extensions with registered grammars."""
    return sorted(GRAMMAR_MAP.keys())


def clear_caches() -> None:
    """Clear all cached Language and Parser objects.

    Primarily useful for testing.
    """
    _language_cache.clear()
    _parser_cache.clear()
    _warned_languages.clear()
