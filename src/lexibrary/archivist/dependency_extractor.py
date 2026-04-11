"""Dependency extractor: resolve forward imports to project-relative paths.

Uses tree-sitter to find import statements in Python, TypeScript, and JavaScript
source files, then resolves them to relative file paths within the project.
Third-party imports and unresolvable imports are silently omitted.
"""

from __future__ import annotations

import logging
from pathlib import Path

from lexibrary.ast_parser.registry import get_parser
from lexibrary.symbolgraph.python_imports import (
    resolve_python_module,
    resolve_python_relative_module,
)

logger = logging.getLogger(__name__)

# Extensions to try when resolving JS/TS imports without an explicit extension
_JS_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx")
_JS_INDEX_NAMES = ("index.ts", "index.tsx", "index.js", "index.jsx")


def extract_dependencies(file_path: Path, project_root: Path) -> list[str]:
    """Extract forward dependencies from a source file as project-relative paths.

    Parses import statements using tree-sitter and resolves them to paths
    within the project. Third-party imports and unresolvable imports are
    silently omitted.

    Args:
        file_path: Path to the source file.
        project_root: Absolute path to the project root directory.

    Returns:
        Sorted, deduplicated list of project-relative dependency paths.
    """
    extension = file_path.suffix
    parser = get_parser(extension)
    if parser is None:
        return []

    try:
        source = file_path.read_bytes()
    except OSError:
        logger.warning("Cannot read file for dependency extraction: %s", file_path)
        return []

    tree = parser.parse(source)
    root = tree.root_node

    if extension in (".py", ".pyi"):
        return _extract_python_deps(root, file_path, project_root)
    if extension in (".ts", ".tsx", ".js", ".jsx"):
        return _extract_js_deps(root, file_path, project_root)
    return []


def _resolve_js_import(
    import_path: str,
    source_dir: Path,
    project_root: Path,
) -> str | None:
    """Resolve a JavaScript/TypeScript relative import to a project-relative path.

    Only handles relative imports (``./`` or ``../``). The caller must
    filter out bare module specifiers (npm packages) before calling.

    Tries the literal path first, then appends common extensions
    (``.ts``, ``.tsx``, ``.js``, ``.jsx``), and finally checks for
    index files.

    Args:
        import_path: Relative import path, e.g. ``"./module"``.
        source_dir: Directory containing the importing file.
        project_root: Absolute path to the project root.

    Returns:
        Project-relative path string if the file is found, else None.
    """
    base = (source_dir / import_path).resolve()

    # Already has a recognised extension — check directly
    if base.suffix in _JS_EXTENSIONS:
        if base.exists():
            try:
                return str(base.relative_to(project_root))
            except ValueError:
                return None
        return None

    # Try adding common extensions
    for ext in _JS_EXTENSIONS:
        candidate = base.with_suffix(ext)
        if candidate.exists():
            try:
                return str(candidate.relative_to(project_root))
            except ValueError:
                return None

    # Try index files (e.g. ./components → ./components/index.ts)
    for name in _JS_INDEX_NAMES:
        candidate = base / name
        if candidate.exists():
            try:
                return str(candidate.relative_to(project_root))
            except ValueError:
                return None

    return None


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _extract_python_deps(
    root: object,
    file_path: Path,
    project_root: Path,
) -> list[str]:
    """Extract Python import dependencies from an AST root node."""
    source_dir = file_path.parent
    deps: list[str] = []

    for node in _children(root):
        node_type = getattr(node, "type", "")

        if node_type == "import_statement":
            _collect_import_statement(node, deps, project_root)

        elif node_type == "import_from_statement":
            _collect_import_from_statement(node, deps, source_dir, project_root)

    return sorted(set(deps))


def _collect_import_statement(
    node: object,
    deps: list[str],
    project_root: Path,
) -> None:
    """Collect dependencies from a plain ``import X`` statement."""
    for child in _children(node):
        child_type = getattr(child, "type", "")

        if child_type == "dotted_name":
            resolved = resolve_python_module(_node_text(child), project_root)
            if resolved is not None:
                deps.append(str(resolved.relative_to(project_root)))

        elif child_type == "aliased_import":
            # import foo.bar as baz — extract the dotted_name
            for sub in _children(child):
                if getattr(sub, "type", "") == "dotted_name":
                    resolved = resolve_python_module(_node_text(sub), project_root)
                    if resolved is not None:
                        deps.append(str(resolved.relative_to(project_root)))
                    break


def _collect_import_from_statement(
    node: object,
    deps: list[str],
    source_dir: Path,
    project_root: Path,
) -> None:
    """Collect dependencies from a ``from X import Y`` statement."""
    for child in _children(node):
        child_type = getattr(child, "type", "")

        if child_type == "relative_import":
            # from .module import X  /  from ..pkg.mod import Y
            dot_count = 0
            module_name = ""
            for rel_child in _children(child):
                rel_type = getattr(rel_child, "type", "")
                if rel_type == "import_prefix":
                    # import_prefix text is the dots, e.g. ".." for 2
                    dot_count = len(_node_text(rel_child))
                elif rel_type == ".":
                    # Fallback for grammars that emit individual dots
                    dot_count += 1
                elif rel_type == "dotted_name":
                    module_name = _node_text(rel_child)

            if module_name:
                resolved = resolve_python_relative_module(
                    module_name,
                    dot_count,
                    source_dir,
                    project_root,
                )
                if resolved is not None:
                    deps.append(str(resolved.relative_to(project_root)))
            break  # only one module source per statement

        if child_type == "dotted_name":
            # from foo.bar import baz (absolute)
            resolved = resolve_python_module(_node_text(child), project_root)
            if resolved is not None:
                deps.append(str(resolved.relative_to(project_root)))
            break  # only one module source per statement


def _extract_js_deps(
    root: object,
    file_path: Path,
    project_root: Path,
) -> list[str]:
    """Extract JavaScript/TypeScript import dependencies from an AST root node."""
    source_dir = file_path.parent
    deps: list[str] = []

    for node in _children(root):
        node_type = getattr(node, "type", "")

        if node_type in ("import_statement", "export_statement"):
            import_path = _find_string_import_path(node)
            if import_path and (import_path.startswith("./") or import_path.startswith("../")):
                resolved = _resolve_js_import(import_path, source_dir, project_root)
                if resolved is not None:
                    deps.append(resolved)

    return sorted(set(deps))


def _find_string_import_path(node: object) -> str | None:
    """Find the module specifier string in an import/export statement node."""
    for child in _children(node):
        if getattr(child, "type", "") == "string":
            return _extract_string_content(child)
    return None


def _extract_string_content(string_node: object) -> str:
    """Extract content from a string node, removing surrounding quotes."""
    # tree-sitter-python uses "string_content"; JS/TS grammars use "string_fragment"
    for child in _children(string_node):
        child_type = getattr(child, "type", "")
        if child_type in ("string_content", "string_fragment"):
            return _node_text(child)
    # Fallback: strip quotes from full text
    full = _node_text(string_node)
    if len(full) >= 2 and full[0] in ('"', "'", "`") and full[-1] in ('"', "'", "`"):
        return full[1:-1]
    return full


# ---------------------------------------------------------------------------
# Tree-sitter node access helpers
# (same pattern as python_parser.py — uses getattr to keep the grammar
# dependency optional at import time)
# ---------------------------------------------------------------------------


def _node_text(node: object) -> str:
    """Get the UTF-8 text content of a tree-sitter node."""
    text = getattr(node, "text", None)
    if text is None:
        return ""
    if isinstance(text, bytes):
        return text.decode("utf-8", errors="replace")
    return str(text)


def _children(node: object) -> list[object]:
    """Get all direct children of a tree-sitter node."""
    return list(getattr(node, "children", []))
