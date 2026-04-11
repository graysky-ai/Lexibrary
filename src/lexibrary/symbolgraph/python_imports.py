"""Shared Python import resolution helpers.

This module is the single source of truth for resolving Python imports to
project-relative file paths. It is consumed by both the link graph
(``archivist.dependency_extractor``) and the symbol graph
(``symbolgraph.resolver_python``).

Four public helpers and one NamedTuple are exported:

- :func:`resolve_python_module` — dotted module path (e.g. ``"lexibrary.config.schema"``)
  to absolute ``Path``; ``None`` for third-party or unresolvable modules.
- :func:`resolve_python_relative_module` — relative import (``from .b import c``)
  to absolute ``Path``; ``None`` when unresolvable.
- :func:`path_to_module` — inverse of the first two: file ``Path`` to dotted
  module path (e.g. ``lexibrary.archivist.pipeline``). Handles both
  ``src/`` layouts and flat layouts. Always includes the top-level package.
- :func:`parse_imports` — walks a pre-parsed tree-sitter Python tree and
  returns a mapping from locally-bound name (or dotted module path for
  ``import a.b``) to an :class:`ImportBinding` capturing the resolved
  **project-relative** file path string and the original (unaliased) name
  of the imported symbol inside that file.
- :class:`ImportBinding` — the ``(file_path, original_name)`` pair returned
  by :func:`parse_imports`. The ``original_name`` lets
  :class:`lexibrary.symbolgraph.resolver_python.PythonResolver` resolve
  aliased imports (``from a import foo as f; f()`` → the symbol ``foo``
  inside ``a.py``).

The first two helpers were previously private to
``archivist.dependency_extractor`` (``_resolve_python_import`` and
``_resolve_python_relative_import``). They have been moved and renamed here
without behaviour change. See CN-021 Symbol Graph and the Phase 2 design in
``plans/symbol-graph-2.md``.
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple


def resolve_python_module(module_dotted: str, project_root: Path) -> Path | None:
    """Convert a dotted Python module path to an absolute file ``Path``.

    Checks src-layout then flat-layout conventions. Returns ``None`` for
    third-party modules (``sqlite3``, ``requests``, etc.) or otherwise
    unresolvable modules.

    Args:
        module_dotted: Dotted module path, e.g. ``"lexibrary.config.schema"``.
        project_root: Absolute path to the project root.

    Returns:
        Absolute :class:`~pathlib.Path` to the resolved ``.py`` file (either
        a module or a package ``__init__.py``) if it exists inside
        ``project_root``, else ``None``.
    """
    parts = module_dotted.split(".")
    rel = Path(*parts)

    for search_root in (project_root / "src", project_root):
        # Try as a module file
        candidate = search_root / rel.with_suffix(".py")
        if candidate.exists():
            try:
                candidate.relative_to(project_root)
            except ValueError:
                continue
            return candidate

        # Try as a package (__init__.py)
        candidate = search_root / rel / "__init__.py"
        if candidate.exists():
            try:
                candidate.relative_to(project_root)
            except ValueError:
                continue
            return candidate

    return None


def resolve_python_relative_module(
    module_name: str,
    dot_count: int,
    source_dir: Path,
    project_root: Path,
) -> Path | None:
    """Resolve a Python relative import to an absolute file ``Path``.

    Handles both module-file and package (``__init__.py``) targets.

    Args:
        module_name: Module subpath after the dots, e.g. ``"module"`` in
            ``from .module import X``. May be dotted (``"sub.mod"``) for
            ``from .sub.mod import X``.
        dot_count: Number of leading dots (1 = current package,
            2 = parent package …).
        source_dir: Directory of the importing file.
        project_root: Absolute path to the project root.

    Returns:
        Absolute :class:`~pathlib.Path` to the resolved file if it exists
        inside ``project_root``, else ``None``.
    """
    base_dir = source_dir
    for _ in range(dot_count - 1):
        base_dir = base_dir.parent

    parts = module_name.split(".") if module_name else []
    target = base_dir / Path(*parts) if parts else base_dir

    # Try as a module file
    candidate = target.with_suffix(".py")
    if candidate.exists():
        try:
            candidate.relative_to(project_root)
        except ValueError:
            return None
        return candidate

    # Try as a package
    candidate = target / "__init__.py"
    if candidate.exists():
        try:
            candidate.relative_to(project_root)
        except ValueError:
            return None
        return candidate

    return None


def path_to_module(path: Path, project_root: Path) -> str:
    """Convert a file path to a dotted Python module path.

    Inverts :func:`resolve_python_module`. Handles both ``src/`` layout
    (strips the ``src/`` prefix) and flat layout (uses the path relative to
    the project root). The resulting dotted path **always** includes the
    top-level package.

    Examples::

        >>> path_to_module(
        ...     Path("src/lexibrary/archivist/pipeline.py"),
        ...     Path("/project"),
        ... )
        'lexibrary.archivist.pipeline'

        >>> path_to_module(
        ...     Path("mypkg/config.py"),
        ...     Path("/project"),
        ... )
        'mypkg.config'

    Args:
        path: Either an absolute file path inside ``project_root`` or a
            file path relative to ``project_root``.
        project_root: Absolute path to the project root.

    Returns:
        Dotted module path (without any ``.py`` suffix and without any
        trailing ``__init__``). Package ``__init__.py`` files map to their
        containing package (e.g. ``src/pkg/__init__.py`` →
        ``"pkg"``).
    """
    # Normalise to a path relative to project_root.
    if path.is_absolute():
        try:
            rel = path.relative_to(project_root)
        except ValueError:
            rel = path
    else:
        rel = path

    parts = list(rel.parts)

    # Strip leading "src/" if present (src-layout).
    if parts and parts[0] == "src":
        parts = parts[1:]

    if not parts:
        return ""

    # Drop the .py suffix on the last component.
    last = parts[-1]
    if last.endswith(".py"):
        last = last[:-3]
    parts[-1] = last

    # Package __init__.py maps to the containing package dotted path.
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]

    return ".".join(parts)


class ImportBinding(NamedTuple):
    """One entry in the result of :func:`parse_imports`.

    Attributes
    ----------
    file_path:
        Project-relative path to the resolved Python source file (the
        module the call site ultimately dispatches into).
    original_name:
        The unaliased name as it exists inside ``file_path``. For
        ``from pkg.b import bar`` the original name is ``"bar"``; for
        ``from pkg.b import bar as baz`` it is still ``"bar"`` even
        though the local binding is ``"baz"``. For plain
        ``import pkg.b`` and ``import pkg.b as lb`` the original name
        is the empty string (the target is a module, not a named symbol
        inside one), which signals the call-site resolver that the
        lookup name is whatever follows the receiver (e.g. ``foo`` in
        ``pkg.b.foo()`` or ``lb.foo()``).
    """

    file_path: str
    original_name: str


def parse_imports(
    tree: object,
    source_bytes: bytes,
    file_path: Path,
    project_root: Path,
) -> dict[str, ImportBinding]:
    """Walk a Python tree-sitter tree and return the local import binding map.

    Visits every top-level ``import_statement`` and ``import_from_statement``
    child of the tree root and resolves each imported target to a
    project-relative file path plus the original (unaliased) symbol name.
    The result is a mapping from the name that is locally bound by the
    import (or the dotted module path for plain ``import a.b``) to the
    resolved :class:`ImportBinding`.

    Binding rules:

    - ``import a.b`` → ``{"a.b": ImportBinding("src/pkg/a/b.py", "")}``
      (dotted module path is the local binding because that is the name
      used at call sites, e.g. ``a.b.foo()``; the original name is empty
      because the target is the module itself).
    - ``import a.b as lb`` → ``{"lb": ImportBinding("src/pkg/a/b.py", "")}``.
    - ``from a.b import c`` → ``{"c": ImportBinding("src/pkg/a/b.py", "c")}``.
    - ``from a.b import c as d`` → ``{"d": ImportBinding("src/pkg/a/b.py", "c")}``.
      The ``original_name`` preserves the unaliased identifier so the
      call-site resolver can find the actual symbol row.
    - ``from .b import c`` (inside ``src/pkg/sub/a.py``) →
      ``{"c": ImportBinding("src/pkg/sub/b.py", "c")}``.

    Unresolved imports (third-party modules, missing files) are silently
    dropped from the map. This is the same resolution policy as
    :func:`resolve_python_module`.

    Args:
        tree: A pre-parsed tree-sitter ``Tree`` for a Python source file.
            Only accessed via attribute lookups (``root_node``, ``children``,
            ``type``, ``text``) so the function never hard-depends on a
            specific tree-sitter API version.
        source_bytes: The raw bytes of the source file. Present for
            symmetry with other tree-walkers; not currently required
            because all necessary information is embedded in node
            ``text`` attributes.
        file_path: Absolute or project-relative path to the file that
            ``tree`` was parsed from. Used as the ``source_dir`` base for
            resolving relative imports.
        project_root: Absolute path to the project root. Used to turn
            resolved absolute paths back into project-relative strings.

    Returns:
        A ``dict[str, ImportBinding]`` mapping local name to
        ``(file_path, original_name)``. Empty when the tree has no
        imports or no imports resolve.
    """
    # Normalise file_path to an absolute path so source_dir is consistent.
    abs_file_path = file_path if file_path.is_absolute() else (project_root / file_path)
    source_dir = abs_file_path.parent

    imports: dict[str, ImportBinding] = {}

    root = getattr(tree, "root_node", None)
    if root is None:
        return imports

    for node in _children(root):
        node_type = getattr(node, "type", "")

        if node_type == "import_statement":
            _collect_import_statement(node, imports, project_root)
        elif node_type == "import_from_statement":
            _collect_import_from_statement(node, imports, source_dir, project_root)

    return imports


# ---------------------------------------------------------------------------
# Private helpers for parse_imports
# ---------------------------------------------------------------------------


def _collect_import_statement(
    node: object,
    imports: dict[str, ImportBinding],
    project_root: Path,
) -> None:
    """Handle a plain ``import X`` (possibly aliased, possibly dotted).

    - ``import a.b`` binds ``"a.b"`` → resolved file (module target,
      empty ``original_name``).
    - ``import a.b as lb`` binds ``"lb"`` → resolved file (module target,
      empty ``original_name``).
    """
    for child in _children(node):
        child_type = getattr(child, "type", "")

        if child_type == "dotted_name":
            module_dotted = _node_text(child)
            resolved = resolve_python_module(module_dotted, project_root)
            if resolved is not None:
                imports[module_dotted] = ImportBinding(
                    file_path=_relative_str(resolved, project_root),
                    original_name="",
                )

        elif child_type == "aliased_import":
            # import foo.bar as baz — extract the dotted_name and the alias.
            module_dotted = ""
            alias = ""
            for sub in _children(child):
                sub_type = getattr(sub, "type", "")
                if sub_type == "dotted_name" and not module_dotted:
                    module_dotted = _node_text(sub)
                elif sub_type == "identifier":
                    alias = _node_text(sub)
            if module_dotted:
                resolved = resolve_python_module(module_dotted, project_root)
                if resolved is not None:
                    key = alias if alias else module_dotted
                    imports[key] = ImportBinding(
                        file_path=_relative_str(resolved, project_root),
                        original_name="",
                    )


def _collect_import_from_statement(
    node: object,
    imports: dict[str, ImportBinding],
    source_dir: Path,
    project_root: Path,
) -> None:
    """Handle a ``from X import Y[, Z as W]`` statement.

    - ``from a.b import c`` binds ``"c"`` → ``ImportBinding("a/b.py", "c")``.
    - ``from a.b import c as d`` binds ``"d"`` → ``ImportBinding("a/b.py", "c")``
      (original name is preserved alongside the alias so the call-site
      resolver can find the real symbol row).
    - ``from .b import c`` binds ``"c"`` → ``ImportBinding("b.py", "c")``.

    Multiple names in a single ``from`` statement are all bound to the
    same underlying module file.
    """
    module_dotted = ""
    relative_dot_count = 0
    relative_module_name = ""
    is_relative = False
    name_nodes: list[object] = []

    # tree-sitter-python grammar: children are either
    #   - `from` keyword, dotted_name, `import` keyword, dotted_name|aliased_import, ...
    # or for relative:
    #   - `from` keyword, relative_import, `import` keyword, ...
    # Everything after the `import` keyword is a name being imported.
    after_import = False
    for child in _children(node):
        child_type = getattr(child, "type", "")

        if child_type == "import":
            after_import = True
            continue

        if not after_import:
            if child_type == "relative_import":
                is_relative = True
                # A relative_import has import_prefix (dots) and optional dotted_name.
                for rel_child in _children(child):
                    rel_type = getattr(rel_child, "type", "")
                    if rel_type == "import_prefix":
                        relative_dot_count = len(_node_text(rel_child))
                    elif rel_type == ".":
                        # Some grammars emit individual dots.
                        relative_dot_count += 1
                    elif rel_type == "dotted_name":
                        relative_module_name = _node_text(rel_child)
            elif child_type == "dotted_name":
                # Absolute from-import: from a.b import ...
                module_dotted = _node_text(child)
        else:
            # After `import`, every dotted_name / identifier / aliased_import
            # is one of the names being imported.
            if child_type in ("dotted_name", "identifier", "aliased_import"):
                name_nodes.append(child)

    # Resolve the underlying module file once.
    resolved: Path | None
    if is_relative:
        resolved = resolve_python_relative_module(
            relative_module_name,
            relative_dot_count,
            source_dir,
            project_root,
        )
    elif module_dotted:
        resolved = resolve_python_module(module_dotted, project_root)
    else:
        resolved = None

    if resolved is None:
        return

    rel_str = _relative_str(resolved, project_root)

    for name_node in name_nodes:
        bound_name, original_name = _names_from_import_name(name_node)
        if bound_name:
            imports[bound_name] = ImportBinding(
                file_path=rel_str,
                original_name=original_name,
            )


def _names_from_import_name(node: object) -> tuple[str, str]:
    """Extract the locally-bound and original names from an import target.

    Handles the three tree-sitter shapes that can appear after ``import`` in
    a ``from X import ...`` statement:

    - ``dotted_name`` → both names are the text as-is (``from a import b.c``
      binds and preserves ``"b.c"``).
    - ``identifier`` → both names are the text as-is.
    - ``aliased_import`` → the bound name is the trailing identifier (after
      ``as``) and the original name is the leading identifier (before
      ``as``). ``from a import bar as baz`` returns ``("baz", "bar")``.

    Returns ``("", "")`` for unrecognised shapes.
    """
    node_type = getattr(node, "type", "")

    if node_type == "aliased_import":
        # Find the identifiers on either side of the `as` keyword.
        # tree-sitter-python emits ``[dotted_name|identifier, "as", identifier]``
        # so the first "name-ish" child is the original and the last is
        # the alias.
        identifiers: list[str] = []
        for child in _children(node):
            child_type = getattr(child, "type", "")
            if child_type in ("identifier", "dotted_name"):
                identifiers.append(_node_text(child))
        if len(identifiers) >= 2:
            return identifiers[-1], identifiers[0]
        if identifiers:
            return identifiers[0], identifiers[0]
        return "", ""

    if node_type in ("dotted_name", "identifier"):
        text = _node_text(node)
        return text, text

    return "", ""


def _relative_str(absolute: Path, project_root: Path) -> str:
    """Return ``absolute`` as a string relative to ``project_root``."""
    return str(absolute.relative_to(project_root))


# ---------------------------------------------------------------------------
# Tree-sitter node access helpers
# (Mirrors the pattern used in archivist/dependency_extractor.py — getattr-
# based access keeps the grammar dependency optional at import time and
# decoupled from a specific py-tree-sitter version.)
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
