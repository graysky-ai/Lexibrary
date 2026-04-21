"""Dependency extractor: resolve forward imports to project-relative paths.

Uses tree-sitter to find import statements in Python, TypeScript, and JavaScript
source files, then resolves them to relative file paths within the project.
Third-party imports and unresolvable imports are silently omitted.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import cast

from lexibrary.ast_parser.registry import get_parser
from lexibrary.symbolgraph.python_imports import (
    resolve_python_module,
    resolve_python_relative_module,
)
from lexibrary.symbolgraph.resolver_js import resolve_js_module

logger = logging.getLogger(__name__)


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

    Delegates to :func:`lexibrary.symbolgraph.resolver_js.resolve_js_module`
    for the actual resolution logic. This thin wrapper maintains the original
    signature (accepts ``source_dir``, returns a project-relative string)
    for backward compatibility.

    Args:
        import_path: Relative import path, e.g. ``"./module"``.
        source_dir: Directory containing the importing file.
        project_root: Absolute path to the project root.

    Returns:
        Project-relative path string if the file is found, else None.
    """
    # resolve_js_module expects a caller *file* path, but we only have the
    # directory. Create a synthetic file path in source_dir so the relative
    # import resolution starts from the right place.
    synthetic_caller = source_dir / "__caller__"
    resolved = resolve_js_module(
        synthetic_caller,
        import_path,
        project_root=project_root,
        tsconfig=None,
    )
    if resolved is None:
        return None
    try:
        return str(resolved.relative_to(project_root.resolve()))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _extract_python_deps(
    root: object,
    file_path: Path,
    project_root: Path,
) -> list[str]:
    """Extract Python import dependencies from an AST root node.

    Walks every descendant of the root so that imports nested inside function
    bodies, ``try``/``except`` blocks, class bodies, and top-level conditional
    branches are all captured. Imports guarded by ``if TYPE_CHECKING:`` are
    skipped during the walk so they do not appear as runtime dependencies —
    matches the semantics of runtime-only ``ast_import`` edges.
    """
    source_dir = file_path.parent
    deps: list[str] = []

    for node in _walk_descendants(root, skip_type_checking=True):
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
    """Extract JavaScript/TypeScript import dependencies from an AST root node.

    Walks the entire AST (not just depth-1 children) so deferred imports inside
    function bodies, class bodies, or conditional branches are also captured.

    TypeScript type-only imports (``import type { X } from ...``) are excluded:
    in the current tree-sitter-typescript grammar the ``type`` keyword appears
    as a direct child token of ``import_statement``, so we detect it by
    inspecting the statement's direct children rather than relying on a
    separate node type.
    """
    source_dir = file_path.parent
    deps: list[str] = []

    for node in _walk_descendants(root, skip_type_checking=False):
        node_type = getattr(node, "type", "")

        if node_type in ("import_statement", "export_statement"):
            if node_type == "import_statement" and _is_type_only_import(node):
                continue
            import_path = _find_string_import_path(node)
            if import_path and (import_path.startswith("./") or import_path.startswith("../")):
                resolved = _resolve_js_import(import_path, source_dir, project_root)
                if resolved is not None:
                    deps.append(resolved)

    return sorted(set(deps))


def _is_type_only_import(node: object) -> bool:
    """Return True when an ``import_statement`` is a type-only import.

    Detects the ``import type ... from ...`` form, where tree-sitter-typescript
    emits a bare ``type`` token as a direct child of the ``import_statement``
    between the ``import`` keyword and the ``import_clause``.
    """
    for child in _children(node):
        child_type = getattr(child, "type", "")
        if child_type == "import_clause":
            # Reached the clause without seeing a standalone ``type`` — regular import.
            return False
        if child_type == "type":
            return True
    return False


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


def _condition_contains_type_checking(node: object) -> bool:
    """Return True iff the ``if_statement`` condition subtree references TYPE_CHECKING.

    Extracts the ``condition`` field of the ``if_statement`` node (tree-sitter-python
    names the if-predicate via a field) and walks ONLY that subtree for an
    identifier whose text equals ``TYPE_CHECKING``. The attribute-access form
    ``typing.TYPE_CHECKING`` is also detected — we scan every identifier
    descendant, not just the root.

    If the grammar does not expose ``child_by_field_name`` (older tree-sitter
    bindings) we fall back to scanning everything BEFORE the first ``:`` token
    in the node's direct children, which is still condition-scoped but is a
    coarser heuristic.
    """
    condition_node = _child_by_field(node, "condition")
    if condition_node is not None:
        return _subtree_has_identifier(condition_node, "TYPE_CHECKING")

    # Fallback for grammars without field-name support: iterate direct
    # children in document order (list preserves order) and stop at ``:``.
    for child in _children(node):
        child_type = getattr(child, "type", "")
        if child_type == ":":
            return False
        if _subtree_has_identifier(child, "TYPE_CHECKING"):
            return True
    return False


def _subtree_has_identifier(root: object, target_text: str) -> bool:
    """Return True iff ``root``'s subtree contains an identifier whose text
    equals ``target_text`` (bare) OR an attribute access whose rightmost
    segment equals ``target_text`` (e.g. ``typing.TYPE_CHECKING``).
    """
    stack: list[object] = [root]
    while stack:
        current = stack.pop()
        current_type = getattr(current, "type", "")
        if current_type == "identifier":
            if _node_text(current) == target_text:
                return True
        elif current_type == "attribute":
            # tree-sitter-python: attribute has fields "object" and "attribute".
            # We only consider the trailing "attribute" segment here — the
            # object chain is descended via normal recursion if needed.
            attr = _child_by_field(current, "attribute")
            if attr is not None and _node_text(attr) == target_text:
                return True
        stack.extend(_children(current))
    return False


def _child_by_field(node: object, field_name: str) -> object | None:
    """Return the tree-sitter field-named child of ``node``, or None.

    Mirrors ``Node.child_by_field_name`` while keeping the grammar dependency
    optional at import time (matches the ``getattr(node, ...)`` pattern used
    elsewhere in this module).
    """
    method = getattr(node, "child_by_field_name", None)
    if callable(method):
        result = method(field_name)
        if result is None:
            return None
        return cast("object", result)
    return None


def _walk_descendants(
    root: object,
    *,
    skip_type_checking: bool = True,
) -> list[object]:
    """Yield every descendant node beneath ``root`` (iterative DFS).

    Uses an explicit stack (list) instead of recursion to avoid Python's
    recursion limit on deep ASTs. The returned list preserves depth-first
    ordering from the root.

    When ``skip_type_checking`` is True AND a visited node is an
    ``if_statement`` whose condition subtree contains an identifier with text
    ``TYPE_CHECKING``, the walker does NOT descend into that node's body.
    The ``if_statement`` itself is still yielded (callers typically dispatch
    only on ``import_statement`` / ``import_from_statement`` types so this is
    harmless), but none of its descendants are yielded.

    The grammar-optional pattern of :func:`_children` is preserved — any node
    without a ``children`` attribute simply yields no descendants.
    """
    results: list[object] = []
    stack: list[object] = list(_children(root))
    while stack:
        current = stack.pop()
        results.append(current)
        current_type = getattr(current, "type", "")
        if (
            skip_type_checking
            and current_type == "if_statement"
            and _condition_contains_type_checking(current)
        ):
            # Skip descending into the TYPE_CHECKING-guarded body.
            continue
        stack.extend(_children(current))
    return results
