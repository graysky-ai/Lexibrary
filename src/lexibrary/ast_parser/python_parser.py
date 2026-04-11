"""Python interface and symbol extraction using tree-sitter.

Two extractor families share the same parse tree:

**Interface skeleton** (original Phase 1 behaviour):

- Top-level functions (dunders and non-underscored names are public)
- Class definitions with public methods and class variables
- Module-level constants (UPPER_CASE or type-annotated)
- ``__all__`` exports (literal list/tuple only)

**Symbol extract** (Phase 2 addition for the symbol graph):

- Definitions for every top-level function, class, method, nested function
  and nested class (nested definitions get ``visibility='private'`` and a
  ``<locals>`` qualified name).
- Call sites inside each definition body: free-function calls, attribute
  calls, ``self.method()``, ``ClassName.method()`` and ``super().foo()``.

Both families handle syntax errors gracefully by extracting whatever
tree-sitter can parse.

Parse-tree entry points are split so callers that need multiple extractors
against the same file can parse once and reuse the tree:

- ``parse_python_tree(file_path)`` runs ``tree_sitter.Parser.parse`` and
  returns ``(tree, source_bytes)``.
- ``extract_interface_from_tree(tree, source_bytes, file_path)`` consumes a
  pre-parsed tuple and returns an :class:`InterfaceSkeleton`.
- ``extract_symbols_from_tree(tree, source_bytes, file_path)`` consumes the
  same pre-parsed tuple and returns a :class:`SymbolExtract`.
- ``extract_interface(file_path)`` and ``extract_symbols(file_path)`` remain
  thin wrappers for single-shot callers.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, cast

from lexibrary.ast_parser.models import (
    CallSite,
    ClassEdgeSite,
    ClassSig,
    ConstantSig,
    ConstantValue,
    EnumMemberSig,
    FunctionSig,
    InterfaceSkeleton,
    ParameterSig,
    SymbolDefinition,
    SymbolExtract,
)
from lexibrary.ast_parser.registry import get_parser
from lexibrary.symbolgraph.python_imports import path_to_module
from lexibrary.utils.root import find_project_root

if TYPE_CHECKING:
    from tree_sitter import Tree

logger = logging.getLogger(__name__)

# Dunder pattern: names of the form ``__name__``.
_DUNDER_RE = re.compile(r"^__.+__$")

# Pattern matching UPPER_CASE names (module-level constants)
_UPPER_CASE_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")

# Pattern matching PascalCase identifiers used to heuristically detect class
# instantiation sites. Intentionally rejects ``_Config`` (leading underscore),
# ``SCREAMING_CASE`` (consecutive uppercase with underscores), and
# ``some_func`` (lowercase start). Pass-3 resolution in the symbol-graph
# builder filters the resulting candidates down to actual ``class`` symbols,
# so we can afford to emit a few false positives here.
_PASCAL_CASE_RE = re.compile(r"^[A-Z][A-Za-z0-9]*$")

# Python standard-library enum base-class names used for syntactic enum
# detection. Both unqualified (``StrEnum``) and ``enum.``-prefixed
# (``enum.StrEnum``) spellings are matched so either ``from enum import ...``
# or a plain ``import enum`` import style is covered. Classes inheriting from
# a project-local enum base — e.g. ``class MyBase(StrEnum)`` followed by
# ``class Status(MyBase)`` — are resolved transitively in the symbol-graph
# builder, not in this module.
_PY_ENUM_BASES = frozenset(
    {
        "Enum",
        "IntEnum",
        "StrEnum",
        "Flag",
        "IntFlag",
        "enum.Enum",
        "enum.IntEnum",
        "enum.StrEnum",
        "enum.Flag",
        "enum.IntFlag",
    }
)

# Node types whose text can be taken verbatim as a Python constant literal
# RHS. A tuple/list/set of literals is also accepted when every element is
# one of these types (checked dynamically in :func:`_is_literal_rhs_python`).
_PY_LITERAL_SIMPLE_TYPES = frozenset(
    {
        "string",
        "concatenated_string",
        "integer",
        "float",
        "true",
        "false",
        "none",
    }
)


def parse_python_tree(file_path: Path) -> tuple[Tree, bytes] | None:
    """Parse a Python source file once and return the tree plus source bytes.

    Reads the file bytes, invokes ``tree_sitter.Parser.parse`` exactly once,
    and returns the resulting ``(tree, source_bytes)`` tuple. Returns ``None``
    when the Python grammar is unavailable or the file cannot be read.

    Args:
        file_path: Path to the Python source file.

    Returns:
        ``(tree, source_bytes)`` or ``None`` on unavailable grammar / I/O
        failure.
    """
    parser = get_parser(file_path.suffix)
    if parser is None:
        return None

    try:
        source_bytes = file_path.read_bytes()
    except OSError:
        logger.warning("Cannot read file: %s", file_path)
        return None

    tree = parser.parse(source_bytes)
    return tree, source_bytes


def extract_interface(file_path: Path) -> InterfaceSkeleton | None:
    """Extract the public interface from a Python source file.

    Thin wrapper around :func:`parse_python_tree` and
    :func:`extract_interface_from_tree` for callers that only need the
    interface skeleton.

    Returns None if the Python grammar is not available or the file
    cannot be read. Returns a partial skeleton if the file has syntax errors.

    Args:
        file_path: Path to the Python source file.

    Returns:
        InterfaceSkeleton with the file's public interface, or None.
    """
    parsed = parse_python_tree(file_path)
    if parsed is None:
        return None
    tree, source_bytes = parsed
    return extract_interface_from_tree(tree, source_bytes, file_path)


def extract_interface_from_tree(
    tree: Tree,
    source_bytes: bytes,
    file_path: Path,
) -> InterfaceSkeleton | None:
    """Extract the public interface from a pre-parsed Python tree.

    Args:
        tree: A ``tree_sitter.Tree`` produced by :func:`parse_python_tree`.
        source_bytes: The raw source bytes that ``tree`` was parsed from.
            Retained for callers that want to derive additional artifacts
            (symbol extraction, slicing) from the same buffer without
            re-reading the file.
        file_path: Path to the Python source file. Only used to populate
            :attr:`InterfaceSkeleton.file_path`.

    Returns:
        :class:`InterfaceSkeleton` describing the public API, or ``None``
        if the tree has no root node.
    """
    del source_bytes  # Present for symmetry with extract_symbols_from_tree.

    root = tree.root_node
    if root is None:
        return None

    constants: list[ConstantSig] = []
    functions: list[FunctionSig] = []
    classes: list[ClassSig] = []
    exports: list[str] = []

    for child in root.children:
        if child.type == "function_definition":
            func = _extract_function(child, is_method=False)
            if func is not None and _is_public_name(func.name):
                functions.append(func)

        elif child.type == "decorated_definition":
            inner = child.child_by_field_name("definition")
            if inner is not None and inner.type == "function_definition":
                func = _extract_function(inner, is_method=False)
                if func is not None and _is_public_name(func.name):
                    # Top-level decorated functions: detect modifiers from decorators
                    _apply_decorators(child, func)
                    functions.append(func)
            elif inner is not None and inner.type == "class_definition":
                cls = _extract_class(inner)
                if cls is not None and _is_public_name(cls.name):
                    classes.append(cls)

        elif child.type == "class_definition":
            cls = _extract_class(child)
            if cls is not None and _is_public_name(cls.name):
                classes.append(cls)

        elif child.type == "expression_statement":
            _extract_from_expression_statement(
                child,
                constants,
                exports,
            )

    return InterfaceSkeleton(
        file_path=str(file_path),
        language="python",
        constants=constants,
        functions=functions,
        classes=classes,
        exports=sorted(exports),
    )


def extract_symbols(
    file_path: Path,
    project_root: Path | None = None,
) -> SymbolExtract | None:
    """Extract symbol definitions and call sites from a Python source file.

    Thin wrapper around :func:`parse_python_tree` and
    :func:`extract_symbols_from_tree`. Returns ``None`` if the Python
    grammar is not available or the file cannot be read.

    Args:
        file_path: Path to the Python source file.
        project_root: Optional absolute path to the project root. Used to
            compute the dotted module path for qualified names. When
            omitted, the root is auto-detected by walking up for a
            ``.lexibrary/`` directory; if no root can be found, the
            qualified name falls back to the filename stem.

    Returns:
        :class:`SymbolExtract` with definitions and calls, or ``None``
        when the tree cannot be parsed.
    """
    parsed = parse_python_tree(file_path)
    if parsed is None:
        return None
    tree, source_bytes = parsed
    return extract_symbols_from_tree(
        tree,
        source_bytes,
        file_path,
        project_root=project_root,
    )


def extract_symbols_from_tree(
    tree: Tree,
    source_bytes: bytes,
    file_path: Path,
    *,
    project_root: Path | None = None,
) -> SymbolExtract | None:
    """Extract symbol definitions and call sites from a pre-parsed tree.

    Walks the tree twice: first to collect every function, class, method,
    nested function and nested class as a :class:`SymbolDefinition`; then
    to collect every ``call`` descendant inside each definition body as a
    :class:`CallSite` and every ``class_definition`` / PascalCase call as a
    :class:`ClassEdgeSite`.

    Call extraction runs on the full parse tree (not the pruned interface
    skeleton) because function bodies are the whole point of the symbol
    graph.

    Args:
        tree: A ``tree_sitter.Tree`` produced by :func:`parse_python_tree`.
        source_bytes: The raw source bytes that ``tree`` was parsed from.
            Currently retained for symmetry — all data the walker needs is
            reachable via ``node.text`` — but kept in the signature so
            callers can reuse a single file read.
        file_path: Path to the Python source file. Used to populate
            :attr:`SymbolExtract.file_path` and to derive the dotted module
            path for :attr:`SymbolDefinition.qualified_name`.
        project_root: Optional absolute path to the project root. When
            omitted, the root is auto-detected via
            :func:`lexibrary.utils.root.find_project_root`.

    Returns:
        :class:`SymbolExtract` describing every definition, call and class
        edge, or ``None`` when the tree has no root node.
    """
    del source_bytes  # Not currently required; reserved for future walkers.

    root = tree.root_node
    if root is None:
        return None

    module_path = _module_path_for_file(file_path, project_root)

    definitions: list[SymbolDefinition] = []
    def_nodes: list[tuple[object, SymbolDefinition]] = []
    enums: list[tuple[str, list[EnumMemberSig]]] = []
    constants: list[ConstantValue] = []

    for child in root.children:
        _collect_top_level_definitions(
            child,
            module_path,
            definitions,
            def_nodes,
            enums,
        )
        _collect_top_level_constants(child, module_path, definitions, constants)

    calls: list[CallSite] = _collect_all_calls(def_nodes)
    class_edges: list[ClassEdgeSite] = _collect_all_class_edges(def_nodes)

    return SymbolExtract(
        file_path=str(file_path),
        language="python",
        definitions=definitions,
        calls=calls,
        class_edges=class_edges,
        enums=enums,
        constants=constants,
    )


def _module_path_for_file(
    file_path: Path,
    project_root: Path | None,
) -> str:
    """Return the dotted module path for ``file_path``.

    When ``project_root`` is ``None`` the Lexibrary root is auto-detected
    by walking up from the file's parent directory. If no ``.lexibrary/``
    marker exists anywhere above the file, the dotted path degrades to the
    file's stem so the qualified-name format stays well-formed.
    """
    if project_root is None:
        try:
            project_root = find_project_root(file_path.parent)
        except Exception:  # LexibraryNotFoundError or permission errors.
            return file_path.stem

    try:
        return path_to_module(file_path, project_root)
    except Exception:  # Defensive — path_to_module should not raise.
        logger.debug(
            "path_to_module failed for %s (project_root=%s)",
            file_path,
            project_root,
            exc_info=True,
        )
        return file_path.stem


def _collect_top_level_definitions(
    node: object,
    module_path: str,
    definitions: list[SymbolDefinition],
    def_nodes: list[tuple[object, SymbolDefinition]],
    enums: list[tuple[str, list[EnumMemberSig]]],
) -> None:
    """Collect a top-level function, class, or decorated variant.

    Descends one level into ``decorated_definition`` nodes. Calls
    :func:`_emit_definition` for each hit so nested walkers can share the
    same emit path. Classes whose bases match :data:`_PY_ENUM_BASES` are
    emitted with ``symbol_type='enum'`` and their members are appended to
    ``enums``; all other classes go through the normal class path.
    """
    node_type = getattr(node, "type", "")

    if node_type == "function_definition":
        _emit_definition(
            node,
            definitions,
            def_nodes,
            symbol_type="function",
            qualified_prefix=module_path,
            parent_class=None,
            force_private=False,
        )
    elif node_type == "class_definition":
        _emit_top_level_class_or_enum(
            node,
            module_path,
            definitions,
            def_nodes,
            enums,
        )
    elif node_type == "decorated_definition":
        inner = _child_by_field(node, "definition")
        if inner is None:
            return
        inner_type = getattr(inner, "type", "")
        if inner_type == "function_definition":
            _emit_definition(
                inner,
                definitions,
                def_nodes,
                symbol_type="function",
                qualified_prefix=module_path,
                parent_class=None,
                force_private=False,
            )
        elif inner_type == "class_definition":
            _emit_top_level_class_or_enum(
                inner,
                module_path,
                definitions,
                def_nodes,
                enums,
            )


def _emit_top_level_class_or_enum(
    node: object,
    module_path: str,
    definitions: list[SymbolDefinition],
    def_nodes: list[tuple[object, SymbolDefinition]],
    enums: list[tuple[str, list[EnumMemberSig]]],
) -> None:
    """Route a top-level ``class_definition`` to the class or enum emitter.

    When any direct base class name is in :data:`_PY_ENUM_BASES` the class
    is emitted as a ``symbol_type='enum'`` symbol and its body is walked for
    :class:`EnumMemberSig` entries, which are appended to ``enums`` as
    ``(qualified_name, members)``. Otherwise the node falls through to the
    regular :func:`_emit_class_definition` path. Nested (non-top-level)
    classes never become enums — the transitive-base second pass in the
    symbol-graph builder handles project-local enum bases.
    """
    if _class_has_enum_base(node):
        _emit_enum_definition(node, module_path, definitions, def_nodes, enums)
    else:
        _emit_class_definition(
            node,
            module_path,
            definitions,
            def_nodes,
            force_private=False,
        )


def _class_has_enum_base(class_node: object) -> bool:
    """Return ``True`` if any base class name is in :data:`_PY_ENUM_BASES`.

    Walks the ``superclasses`` field and uses :func:`_base_class_name` to
    extract the textual base identifier (e.g. ``Enum``, ``enum.StrEnum``).
    Generic and subscripted bases like ``Generic[T]`` collapse to their
    head identifier, which is almost never an enum base, so they are
    filtered naturally by set membership.
    """
    superclasses_node = _child_by_field(class_node, "superclasses")
    if superclasses_node is None:
        return False
    for base_node in _named_children(superclasses_node):
        base_name = _base_class_name(base_node)
        if base_name and base_name in _PY_ENUM_BASES:
            return True
    return False


def _emit_enum_definition(
    node: object,
    module_path: str,
    definitions: list[SymbolDefinition],
    def_nodes: list[tuple[object, SymbolDefinition]],
    enums: list[tuple[str, list[EnumMemberSig]]],
) -> None:
    """Emit an enum ``SymbolDefinition`` and record its members.

    The enum itself is emitted with ``symbol_type='enum'``; its methods
    (and any nested classes) are walked exactly like a normal class so the
    rest of the symbol graph still sees the surrounding structure. Member
    detection is delegated to :func:`_collect_enum_members`, which only
    picks up literal assignments at the class-body level.
    """
    name_node = _child_by_field(node, "name")
    if name_node is None:
        return
    name = _node_text(name_node)
    if not name:
        return

    visibility = _visibility_for(name, force_private=False)
    qualified_name = f"{module_path}.{name}" if module_path else name
    line_start, line_end = _line_range(node)
    enum_def = SymbolDefinition(
        name=name,
        qualified_name=qualified_name,
        symbol_type="enum",
        line_start=line_start,
        line_end=line_end,
        visibility=visibility,
        parent_class=None,
    )
    definitions.append(enum_def)
    def_nodes.append((node, enum_def))

    body_node = _child_by_field(node, "body")
    if body_node is not None:
        members = _collect_enum_members(body_node)
        enums.append((qualified_name, members))

        # Walk the body for methods and nested classes so the enum still
        # contributes methods to the symbol graph (e.g. ``__str__``
        # overrides on a StrEnum subclass).
        class_prefix = qualified_name
        for member in _children(body_node):
            member_type = getattr(member, "type", "")

            if member_type == "function_definition":
                _emit_definition(
                    member,
                    definitions,
                    def_nodes,
                    symbol_type="method",
                    qualified_prefix=class_prefix,
                    parent_class=name,
                    force_private=False,
                )
            elif member_type == "decorated_definition":
                inner = _child_by_field(member, "definition")
                if inner is None:
                    continue
                inner_type = getattr(inner, "type", "")
                if inner_type == "function_definition":
                    _emit_definition(
                        inner,
                        definitions,
                        def_nodes,
                        symbol_type="method",
                        qualified_prefix=class_prefix,
                        parent_class=name,
                        force_private=False,
                    )
                elif inner_type == "class_definition":
                    _emit_class_definition(
                        inner,
                        class_prefix,
                        definitions,
                        def_nodes,
                        force_private=True,
                    )
            elif member_type == "class_definition":
                _emit_class_definition(
                    member,
                    class_prefix,
                    definitions,
                    def_nodes,
                    force_private=True,
                )


def _collect_enum_members(body_node: object) -> list[EnumMemberSig]:
    """Walk an enum class body and return :class:`EnumMemberSig` entries.

    Each assignment inside an ``expression_statement`` whose LHS is a
    bare identifier becomes a member, with an auto-incremented
    zero-based ``ordinal``. The RHS is recorded as literal source text
    when it is a simple literal (see :data:`_PY_LITERAL_SIMPLE_TYPES`),
    as ``None`` for ``auto()`` calls or any other non-literal expression.
    Annotated assignments (``VALUE: int = 1``) are accepted with the
    ``right`` field treated the same way. Non-assignment body members
    (``def`` methods, docstrings, ``...``) are skipped silently.
    """
    members: list[EnumMemberSig] = []
    ordinal = 0
    for child in _children(body_node):
        if getattr(child, "type", "") != "expression_statement":
            continue
        for inner in _named_children(child):
            if getattr(inner, "type", "") != "assignment":
                continue
            left_node = _child_by_field(inner, "left")
            if left_node is None:
                continue
            if getattr(left_node, "type", "") != "identifier":
                continue
            member_name = _node_text(left_node)
            if not member_name:
                continue
            right_node = _child_by_field(inner, "right")
            value = _enum_member_value(right_node)
            members.append(
                EnumMemberSig(
                    name=member_name,
                    value=value,
                    ordinal=ordinal,
                ),
            )
            ordinal += 1
    return members


def _enum_member_value(right_node: object | None) -> str | None:
    """Return the literal value text for an enum member RHS, or ``None``.

    ``auto()`` and any other call/expression that is not a simple literal
    returns ``None`` — these members still get an :class:`EnumMemberSig`
    row but with a null ``value`` so the symbol-graph builder can insert a
    ``symbol_members`` row that records the ordinal without a value.
    """
    if right_node is None:
        return None
    right_type = getattr(right_node, "type", "")
    if right_type == "string":
        return _node_text(right_node)
    if right_type in _PY_LITERAL_SIMPLE_TYPES:
        return _node_text(right_node)
    if right_type == "unary_operator":
        # Covers ``-1`` and ``+1`` literal RHS.
        operand = None
        for sub in _named_children(right_node):
            operand = sub
            break
        if operand is not None:
            operand_type = getattr(operand, "type", "")
            if operand_type in _PY_LITERAL_SIMPLE_TYPES:
                return _node_text(right_node)
    return None


def _collect_top_level_constants(
    node: object,
    module_path: str,
    definitions: list[SymbolDefinition],
    constants: list[ConstantValue],
) -> None:
    """Collect a module-level constant from a top-level AST child node.

    Examines one direct child of the ``module`` node. If it is an
    ``expression_statement`` that wraps a qualifying assignment, a
    :class:`SymbolDefinition` with ``symbol_type='constant'`` is appended
    to ``definitions`` and a :class:`ConstantValue` is appended to
    ``constants``. Qualification rules: LHS must be a bare identifier that
    either passes :func:`_is_constant_name` (ALL_CAPS or
    underscore-prefixed ALL_CAPS) or carries a type annotation, and RHS
    must be a simple literal per :func:`_is_literal_rhs_python`. Nested
    assignments (inside a class or function body) are intentionally NOT
    reached — this walker is only called from the top-level loop in
    :func:`extract_symbols_from_tree`.
    """
    if getattr(node, "type", "") != "expression_statement":
        return

    for child in _named_children(node):
        child_type = getattr(child, "type", "")
        if child_type == "assignment":
            _collect_constant_from_assignment(
                child,
                module_path,
                definitions,
                constants,
            )
        elif child_type == "augmented_assignment":
            # ``X += 1`` is never treated as a constant definition.
            continue


def _collect_constant_from_assignment(
    assignment_node: object,
    module_path: str,
    definitions: list[SymbolDefinition],
    constants: list[ConstantValue],
) -> None:
    """Append a :class:`ConstantValue` from an assignment, when eligible.

    The LHS must be a bare ``identifier`` — tuple/list unpacking targets
    like ``A, B = 1, 2`` are skipped because the heuristic cannot express
    multi-target constants cleanly. The name qualifies when ANY of the
    following hold:

    1. The name matches :data:`_UPPER_CASE_RE` (``MAX_RETRIES``).
    2. The name is an underscore-prefixed ALL_CAPS identifier
       (``_PRIVATE``, ``_MAX_RETRIES``). This is the conventional spelling
       for a private module constant; the extractor preserves it so
       visibility (``private``) can be recorded later by the symbol
       emitter.
    3. The assignment carries a type annotation — e.g.
       ``DEFAULT_TIMEOUT: float = 30.0`` or even ``timeout: float = 30.0``.

    The RHS must be literal per :func:`_is_literal_rhs_python`. The
    recorded ``value`` is the raw source text of the RHS; ``line`` is the
    1-indexed start line of the assignment node.
    """
    left_node = _child_by_field(assignment_node, "left")
    if left_node is None:
        return
    if getattr(left_node, "type", "") != "identifier":
        return
    name = _node_text(left_node)
    if not name:
        return

    type_node = _child_by_field(assignment_node, "type")
    type_ann = _node_text(type_node) if type_node is not None else None

    if type_ann is None and not _is_constant_name(name):
        return

    right_node = _child_by_field(assignment_node, "right")
    if right_node is None:
        return
    if not _is_literal_rhs_python(right_node):
        return

    value = _node_text(right_node)
    if not value:
        return

    line_start, line_end = _line_range(assignment_node)
    qualified_name = f"{module_path}.{name}" if module_path else name
    visibility = _visibility_for(name, force_private=False)
    definitions.append(
        SymbolDefinition(
            name=name,
            qualified_name=qualified_name,
            symbol_type="constant",
            line_start=line_start,
            line_end=line_end,
            visibility=visibility,
            parent_class=None,
        ),
    )
    constants.append(
        ConstantValue(
            name=name,
            value=value,
            line=line_start,
            type_annotation=type_ann,
        ),
    )


def _is_constant_name(name: str) -> bool:
    """Return ``True`` if ``name`` is an ALL_CAPS or private ALL_CAPS identifier.

    Matches ``MAX_RETRIES`` (public) and ``_PRIVATE`` / ``_MAX_RETRIES``
    (private — conventional leading-underscore private constant). The
    plain :data:`_UPPER_CASE_RE` regex does not match leading underscores,
    so this helper strips one leading underscore before testing so we can
    still record ``_PRIVATE = "secret"`` as a constant with
    ``visibility='private'``.
    """
    if not name:
        return False
    probe = name[1:] if name.startswith("_") else name
    return bool(_UPPER_CASE_RE.fullmatch(probe))


def _is_literal_rhs_python(node: object) -> bool:
    """Return ``True`` if ``node`` is a simple Python literal RHS.

    A literal is one of the entries in :data:`_PY_LITERAL_SIMPLE_TYPES`, a
    unary-prefixed literal (``-1``, ``+3.14``), or a ``tuple``/``list``/
    ``set`` whose every named child is itself one of the above. Dict
    literals, comprehensions, function calls, attribute accesses, binary
    operators, and name references are all rejected.
    """
    node_type = getattr(node, "type", "")
    if node_type in _PY_LITERAL_SIMPLE_TYPES:
        return True
    if node_type == "unary_operator":
        for child in _named_children(node):
            child_type = getattr(child, "type", "")
            return child_type in _PY_LITERAL_SIMPLE_TYPES
        return False
    if node_type in {"tuple", "list", "set"}:
        # Empty collection literals count as literals; otherwise every
        # named child must itself be a simple literal.
        children = list(_named_children(node))
        if not children:
            return True
        return all(_is_literal_rhs_python(child) for child in children)
    return False


def _emit_class_definition(
    node: object,
    module_path: str,
    definitions: list[SymbolDefinition],
    def_nodes: list[tuple[object, SymbolDefinition]],
    *,
    force_private: bool,
) -> None:
    """Emit a class symbol and its methods and inner classes.

    Descends one level into the class body to capture methods. Nested
    classes are recursed into so their methods are also recorded, but the
    call walker below still attributes calls to the innermost definition.
    """
    name_node = _child_by_field(node, "name")
    if name_node is None:
        return
    name = _node_text(name_node)
    if not name:
        return

    visibility = _visibility_for(name, force_private=force_private)
    qualified_name = f"{module_path}.{name}" if module_path else name
    line_start, line_end = _line_range(node)
    cls_def = SymbolDefinition(
        name=name,
        qualified_name=qualified_name,
        symbol_type="class",
        line_start=line_start,
        line_end=line_end,
        visibility=visibility,
        parent_class=None,
    )
    definitions.append(cls_def)
    def_nodes.append((node, cls_def))

    body_node = _child_by_field(node, "body")
    if body_node is None:
        return

    class_prefix = qualified_name
    for member in _children(body_node):
        member_type = getattr(member, "type", "")

        if member_type == "function_definition":
            _emit_definition(
                member,
                definitions,
                def_nodes,
                symbol_type="method",
                qualified_prefix=class_prefix,
                parent_class=name,
                force_private=False,
            )
        elif member_type == "decorated_definition":
            inner = _child_by_field(member, "definition")
            if inner is None:
                continue
            inner_type = getattr(inner, "type", "")
            if inner_type == "function_definition":
                _emit_definition(
                    inner,
                    definitions,
                    def_nodes,
                    symbol_type="method",
                    qualified_prefix=class_prefix,
                    parent_class=name,
                    force_private=False,
                )
            elif inner_type == "class_definition":
                _emit_class_definition(
                    inner,
                    class_prefix,
                    definitions,
                    def_nodes,
                    force_private=True,
                )
        elif member_type == "class_definition":
            _emit_class_definition(
                member,
                class_prefix,
                definitions,
                def_nodes,
                force_private=True,
            )


def _emit_definition(
    node: object,
    definitions: list[SymbolDefinition],
    def_nodes: list[tuple[object, SymbolDefinition]],
    *,
    symbol_type: str,
    qualified_prefix: str,
    parent_class: str | None,
    force_private: bool,
) -> None:
    """Emit a function or method definition and recurse into nested defs.

    Walks the function body once more looking for nested
    ``function_definition`` and ``class_definition`` descendants. Nested
    defs get ``visibility="private"`` and a ``<locals>`` qualified-name
    segment.
    """
    name_node = _child_by_field(node, "name")
    if name_node is None:
        return
    name = _node_text(name_node)
    if not name:
        return

    visibility = _visibility_for(name, force_private=force_private)
    qualified_name = f"{qualified_prefix}.{name}" if qualified_prefix else name
    line_start, line_end = _line_range(node)
    fn_def = SymbolDefinition(
        name=name,
        qualified_name=qualified_name,
        symbol_type=symbol_type,
        line_start=line_start,
        line_end=line_end,
        visibility=visibility,
        parent_class=parent_class,
    )
    definitions.append(fn_def)
    def_nodes.append((node, fn_def))

    body_node = _child_by_field(node, "body")
    if body_node is None:
        return

    nested_prefix = f"{qualified_name}.<locals>"
    _walk_nested_definitions(
        body_node,
        nested_prefix,
        definitions,
        def_nodes,
    )


def _walk_nested_definitions(
    node: object,
    nested_prefix: str,
    definitions: list[SymbolDefinition],
    def_nodes: list[tuple[object, SymbolDefinition]],
) -> None:
    """Recursively emit nested functions and classes inside a body.

    The walker intentionally does not descend into ``function_definition``
    or ``class_definition`` children — :func:`_emit_definition` and
    :func:`_emit_class_definition` manage their own recursion so each
    definition drives its own ``<locals>`` prefix chain.
    """
    for child in _children(node):
        child_type = getattr(child, "type", "")

        if child_type == "function_definition":
            _emit_definition(
                child,
                definitions,
                def_nodes,
                symbol_type="function",
                qualified_prefix=nested_prefix,
                parent_class=None,
                force_private=True,
            )
        elif child_type == "class_definition":
            _emit_class_definition(
                child,
                nested_prefix,
                definitions,
                def_nodes,
                force_private=True,
            )
        elif child_type == "decorated_definition":
            inner = _child_by_field(child, "definition")
            if inner is None:
                continue
            inner_type = getattr(inner, "type", "")
            if inner_type == "function_definition":
                _emit_definition(
                    inner,
                    definitions,
                    def_nodes,
                    symbol_type="function",
                    qualified_prefix=nested_prefix,
                    parent_class=None,
                    force_private=True,
                )
            elif inner_type == "class_definition":
                _emit_class_definition(
                    inner,
                    nested_prefix,
                    definitions,
                    def_nodes,
                    force_private=True,
                )
        else:
            # Recurse into statement/expression containers (e.g. ``if`` /
            # ``for`` / ``with`` blocks) so nested defs buried inside
            # control flow are still captured.
            _walk_nested_definitions(
                child,
                nested_prefix,
                definitions,
                def_nodes,
            )


def _collect_all_calls(
    def_nodes: list[tuple[object, SymbolDefinition]],
) -> list[CallSite]:
    """Walk every definition body and emit :class:`CallSite` entries.

    Call attribution belongs to the *innermost* enclosing definition. We
    compute that by sorting definitions deepest-first (largest
    ``line_start``, tie-break smallest ``line_end``) and, for every call
    node anywhere in the file, we pick the first definition whose row
    span strictly contains the call row. Each call is therefore recorded
    exactly once and attributed to the tightest enclosing symbol — the
    behaviour required by the nested-functions test in the plan.

    **Dedup note:** tree-sitter-python's bindings return fresh Python
    wrapper objects on every node traversal, so ``id()`` of a wrapper is
    not stable between walks. The dedup key is therefore
    ``(start_byte, end_byte)`` of the call node, which uniquely
    identifies the underlying C tree-sitter node.
    """
    if not def_nodes:
        return []

    definition_spans: list[tuple[SymbolDefinition, int, int]] = []
    for def_node, definition in def_nodes:
        start_row, end_row = _node_row_span(def_node)
        definition_spans.append((definition, start_row, end_row))

    # Deepest definitions first so the innermost match is found quickly.
    definition_spans.sort(key=lambda item: (-item[1], item[2]))

    seen_call_keys: set[tuple[int, int]] = set()
    calls: list[CallSite] = []

    for def_node, _definition in def_nodes:
        for call_node in _iter_call_descendants(def_node):
            call_key = _node_byte_key(call_node)
            if call_key in seen_call_keys:
                continue
            seen_call_keys.add(call_key)

            call_row = _node_row_span(call_node)[0]
            owner = _innermost_definition_for_row(
                call_row,
                definition_spans,
            )
            if owner is None:
                continue

            call = _build_call_site(call_node, owner.qualified_name)
            if call is not None:
                calls.append(call)

    # Stable order: by line then by callee to keep snapshot tests stable.
    calls.sort(key=lambda c: (c.line, c.callee_name, c.caller_name))
    return calls


def _collect_all_class_edges(
    def_nodes: list[tuple[object, SymbolDefinition]],
) -> list[ClassEdgeSite]:
    """Emit ``ClassEdgeSite`` entries for every class base and instantiation.

    Two kinds of edges are recorded:

    - ``inherits``: for every class definition with ``superclasses``, emit
      one edge per base clause. Generic bases (``Generic[T]``) collapse to
      their identifier (``Generic``); qualified bases (``mod.Base``) are
      kept verbatim so the resolver can strip attribute prefixes later.
    - ``instantiates``: for every call whose bare callee name matches
      :data:`_PASCAL_CASE_RE`, emit an edge from the innermost enclosing
      definition to that callee. Qualified calls (``mod.Foo()``) and
      attribute calls (``obj.Foo()``) are skipped because Phase 3 resolves
      only bare identifiers. Function false positives (e.g. a PascalCase
      helper function) are filtered later by the builder's pass 3 — the
      symbol-type check lives there so this walker stays a pure AST
      layer.
    """
    if not def_nodes:
        return []

    definition_spans: list[tuple[SymbolDefinition, int, int]] = []
    class_defs_by_qualified: dict[str, tuple[object, SymbolDefinition]] = {}
    for def_node, definition in def_nodes:
        start_row, end_row = _node_row_span(def_node)
        definition_spans.append((definition, start_row, end_row))
        if definition.symbol_type == "class":
            class_defs_by_qualified[definition.qualified_name] = (
                def_node,
                definition,
            )

    # Deepest definitions first so the innermost match is found quickly.
    definition_spans.sort(key=lambda item: (-item[1], item[2]))

    edges: list[ClassEdgeSite] = []

    # ---- inherits edges ----
    for class_node, class_def in class_defs_by_qualified.values():
        superclasses_node = _child_by_field(class_node, "superclasses")
        if superclasses_node is None:
            continue
        for base_node in _named_children(superclasses_node):
            base_name = _base_class_name(base_node)
            if not base_name:
                continue
            edges.append(
                ClassEdgeSite(
                    source_name=class_def.qualified_name,
                    target_name=base_name,
                    edge_type="inherits",
                    line=class_def.line_start,
                ),
            )

    # ---- instantiates edges ----
    seen_call_keys: set[tuple[int, int]] = set()
    for def_node, _definition in def_nodes:
        for call_node in _iter_call_descendants(def_node):
            call_key = _node_byte_key(call_node)
            if call_key in seen_call_keys:
                continue
            seen_call_keys.add(call_key)

            callee_name = _bare_identifier_callee(call_node)
            if callee_name is None:
                continue
            if not _PASCAL_CASE_RE.fullmatch(callee_name):
                continue

            call_row = _node_row_span(call_node)[0]
            owner = _innermost_definition_for_row(call_row, definition_spans)
            if owner is None:
                continue

            edges.append(
                ClassEdgeSite(
                    source_name=owner.qualified_name,
                    target_name=callee_name,
                    edge_type="instantiates",
                    line=call_row + 1,
                ),
            )

    # Stable order: by line then by target name then by source name so
    # snapshot tests stay deterministic.
    edges.sort(key=lambda e: (e.line, e.target_name, e.source_name, e.edge_type))
    return edges


def _base_class_name(node: object) -> str:
    """Return the textual name of a base class clause.

    - ``identifier`` → ``Animal``
    - ``attribute`` → ``mod.Base`` (kept verbatim; builder strips modules)
    - ``subscript`` → first identifier child (``Generic[T]`` → ``Generic``)
    - anything else (string, call, ...) → empty string (skip)
    """
    node_type = getattr(node, "type", "")
    if node_type == "identifier":
        return _node_text(node)
    if node_type == "attribute":
        return _node_text(node)
    if node_type == "subscript":
        # ``Generic[T]`` — use the value (identifier) before the brackets.
        value_node = _child_by_field(node, "value")
        if value_node is not None:
            return _node_text(value_node)
        for child in _named_children(node):
            child_type = getattr(child, "type", "")
            if child_type in ("identifier", "attribute"):
                return _node_text(child)
            break
        return ""
    return ""


def _bare_identifier_callee(call_node: object) -> str | None:
    """Return the bare identifier name of a call, or ``None``.

    Attribute callees (``obj.method()``), subscript callees (``foo[0]()``),
    chained calls (``foo()()``), and lambda callees all return ``None`` —
    the PascalCase instantiation heuristic only fires on bare identifiers.
    """
    func_node = _child_by_field(call_node, "function")
    if func_node is None:
        return None
    if getattr(func_node, "type", "") != "identifier":
        return None
    text = _node_text(func_node)
    return text or None


def _node_byte_key(node: object) -> tuple[int, int]:
    """Return a dedup key for a tree-sitter node.

    Uses ``(start_byte, end_byte)`` because tree-sitter-python creates
    fresh Python wrapper objects on each traversal — ``id()`` of the
    wrapper is NOT stable across walks, so it can not be used as a
    dedup key. Byte offsets, on the other hand, uniquely identify the
    underlying node within a single parse tree.
    """
    start = getattr(node, "start_byte", -1)
    end = getattr(node, "end_byte", -1)
    return int(start), int(end)


def _innermost_definition_for_row(
    call_row: int,
    definition_spans: list[tuple[SymbolDefinition, int, int]],
) -> SymbolDefinition | None:
    """Return the tightest definition whose row span contains ``call_row``.

    ``definition_spans`` must already be sorted deepest-first (largest
    ``line_start``, tie-break smallest ``line_end``). The first match
    wins.
    """
    for definition, start_row, end_row in definition_spans:
        if start_row <= call_row <= end_row:
            return definition
    return None


def _iter_call_descendants(node: object) -> list[object]:
    """Return every ``call`` descendant of ``node`` in document order.

    Uses an explicit stack to avoid blowing the recursion limit on deeply
    nested bodies and to keep the walker independent of tree-sitter's
    cursor API (which differs between versions).
    """
    results: list[object] = []
    stack: list[object] = list(_children(node))
    while stack:
        current = stack.pop(0)
        if getattr(current, "type", "") == "call":
            results.append(current)
        stack = list(_children(current)) + stack
    return results


def _build_call_site(
    call_node: object,
    caller_qualified_name: str,
) -> CallSite | None:
    """Translate a tree-sitter ``call`` node into a :class:`CallSite`.

    Returns ``None`` for calls we intentionally skip: calls on literals,
    subscripts, lambdas, chained calls, bare ``super()`` expressions
    (represented by the enclosing ``super().method()`` call instead), and
    other shapes we cannot name textually. Keeping the skip logic here —
    rather than at the walker — ensures the emitter stays in lockstep
    with the tests.
    """
    func_node = _child_by_field(call_node, "function")
    if func_node is None:
        return None

    func_type = getattr(func_node, "type", "")
    line = _node_row_span(call_node)[0] + 1

    if func_type == "identifier":
        callee_name = _node_text(func_node)
        if not callee_name:
            return None
        # ``super()`` alone is a subexpression of a ``super().method()``
        # call; the attribute branch below represents it as
        # ``callee_name='super.method'``. Emitting ``super`` on its own
        # would double-count the call.
        if callee_name == "super":
            return None
        return CallSite(
            caller_name=caller_qualified_name,
            callee_name=callee_name,
            receiver=None,
            line=line,
            is_method_call=False,
        )

    if func_type == "attribute":
        obj_node = _child_by_field(func_node, "object")
        attr_node = _child_by_field(func_node, "attribute")
        if attr_node is None:
            return None
        attr_name = _node_text(attr_node)
        if not attr_name:
            return None

        receiver, receiver_display = _attribute_receiver(obj_node)
        if receiver is None:
            return None

        callee_name = f"{receiver_display}.{attr_name}"
        return CallSite(
            caller_name=caller_qualified_name,
            callee_name=callee_name,
            receiver=receiver,
            line=line,
            is_method_call=True,
        )

    # Skip lambdas, chained calls (``foo()()``), and everything else.
    return None


def _attribute_receiver(
    obj_node: object | None,
) -> tuple[str | None, str]:
    """Derive the receiver text for an attribute-call target.

    Returns ``(receiver, display)`` where ``receiver`` is stored on the
    :class:`CallSite` and ``display`` is the rendered text used to build
    ``callee_name``. ``super()`` is special-cased so both the receiver and
    the display name collapse to the string ``"super"``. Calls on literals
    (``"".join(...)``), subscripts (``foo[0](...)``), other calls
    (``foo()()``) and lambdas return ``(None, "")`` to signal a skip.
    """
    if obj_node is None:
        return None, ""

    obj_type = getattr(obj_node, "type", "")

    if obj_type == "call":
        inner_func = _child_by_field(obj_node, "function")
        if inner_func is not None and getattr(inner_func, "type", "") == "identifier":
            inner_name = _node_text(inner_func)
            if inner_name == "super":
                return "super", "super"
        return None, ""

    if obj_type in {
        "string",
        "concatenated_string",
        "integer",
        "float",
        "true",
        "false",
        "none",
        "list",
        "tuple",
        "dictionary",
        "set",
        "subscript",
        "lambda",
        "parenthesized_expression",
    }:
        return None, ""

    text = _node_text(obj_node)
    if not text:
        return None, ""
    return text, text


def _line_range(node: object) -> tuple[int, int]:
    """Return (line_start, line_end) as 1-indexed source line numbers."""
    start_row, end_row = _node_row_span(node)
    return start_row + 1, end_row + 1


def _node_row_span(node: object) -> tuple[int, int]:
    """Return (start_row, end_row) as 0-indexed tree-sitter rows."""
    start = getattr(node, "start_point", (0, 0))
    end = getattr(node, "end_point", start)
    start_row = start[0] if isinstance(start, (tuple, list)) else 0
    end_row = end[0] if isinstance(end, (tuple, list)) else start_row
    return int(start_row), int(end_row)


def _visibility_for(name: str, *, force_private: bool) -> str:
    """Return the visibility string for a symbol name.

    ``force_private=True`` is used for nested definitions, where the plan
    specifies ``visibility='private'`` regardless of the name shape. All
    other definitions follow :func:`_is_public_name`.
    """
    if force_private:
        return "private"
    return "public" if _is_public_name(name) else "private"


def _is_public_name(name: str) -> bool:
    """Check whether a name is public under the Phase 2 visibility rule.

    - Dunder names (``__x__``) are always public.
    - Names with a single leading underscore (``_x``) are private.
    - All other names are public.

    Phase 2 replaces the earlier short allow-list of dunders
    (``__init__``/``__new__``). The interface skeleton and the symbol graph
    now agree on dunder visibility — every ``__*__`` name is surfaced.
    """
    return not (name.startswith("_") and not _DUNDER_RE.match(name))


def _node_text(node: object) -> str:
    """Get the UTF-8 text of a tree-sitter node."""
    text = getattr(node, "text", None)
    if text is None:
        return ""
    if isinstance(text, bytes):
        return text.decode("utf-8", errors="replace")
    return str(text)


def _extract_function(
    node: object,
    is_method: bool = False,
) -> FunctionSig | None:
    """Extract a FunctionSig from a function_definition node.

    Args:
        node: A tree-sitter function_definition node.
        is_method: Whether this function is a class method.

    Returns:
        FunctionSig or None if the node is malformed.
    """
    # Use field-based access for tree-sitter nodes
    name_node = _child_by_field(node, "name")
    if name_node is None:
        return None

    name = _node_text(name_node)
    if not name:
        return None

    # Detect async
    is_async = False
    for child in _children(node):
        if getattr(child, "type", None) == "async":
            is_async = True
            break

    # Parameters
    params_node = _child_by_field(node, "parameters")
    parameters = _extract_parameters(params_node, is_method)

    # Return type
    return_type_node = _child_by_field(node, "return_type")
    return_type = _node_text(return_type_node) if return_type_node is not None else None

    return FunctionSig(
        name=name,
        parameters=parameters,
        return_type=return_type,
        is_async=is_async,
        is_method=is_method,
    )


def _extract_parameters(
    params_node: object | None,
    is_method: bool,
) -> list[ParameterSig]:
    """Extract parameter signatures from a parameters node.

    Skips 'self' and 'cls' for methods.
    """
    if params_node is None:
        return []

    parameters: list[ParameterSig] = []
    skip_first_self = is_method

    for child in _named_children(params_node):
        child_type = getattr(child, "type", "")

        if child_type == "identifier":
            # Simple parameter without type annotation
            param_name = _node_text(child)
            if skip_first_self and param_name in ("self", "cls"):
                skip_first_self = False
                continue
            parameters.append(ParameterSig(name=param_name))

        elif child_type == "typed_parameter":
            param = _extract_typed_parameter(child)
            if param is not None:
                if skip_first_self and param.name in ("self", "cls"):
                    skip_first_self = False
                    continue
                parameters.append(param)

        elif child_type == "typed_default_parameter":
            param = _extract_typed_default_parameter(child)
            if param is not None:
                if skip_first_self and param.name in ("self", "cls"):
                    skip_first_self = False
                    continue
                parameters.append(param)

        elif child_type == "default_parameter":
            param = _extract_default_parameter(child)
            if param is not None:
                if skip_first_self and param.name in ("self", "cls"):
                    skip_first_self = False
                    continue
                parameters.append(param)

        elif child_type in ("list_splat_pattern", "dictionary_splat_pattern"):
            # *args or **kwargs
            param_name = ""
            for sub in _children(child):
                if getattr(sub, "type", "") == "identifier":
                    param_name = _node_text(sub)
                    break
            if param_name:
                prefix = "*" if child_type == "list_splat_pattern" else "**"
                parameters.append(ParameterSig(name=f"{prefix}{param_name}"))

    return parameters


def _extract_typed_parameter(node: object) -> ParameterSig | None:
    """Extract a ParameterSig from a typed_parameter node."""
    # typed_parameter: identifier ':' type
    # The first named child is the identifier (field name not always available)
    name = ""
    type_ann = None
    for child in _children(node):
        child_type = getattr(child, "type", "")
        if child_type == "identifier" and not name:
            name = _node_text(child)
        elif child_type == "type":
            type_ann = _node_text(child)
    if not name:
        return None
    return ParameterSig(name=name, type_annotation=type_ann)


def _extract_typed_default_parameter(node: object) -> ParameterSig | None:
    """Extract a ParameterSig from a typed_default_parameter node."""
    name_node = _child_by_field(node, "name")
    type_node = _child_by_field(node, "type")
    value_node = _child_by_field(node, "value")

    if name_node is None:
        return None

    name = _node_text(name_node)
    type_ann = _node_text(type_node) if type_node is not None else None
    default = _node_text(value_node) if value_node is not None else None

    return ParameterSig(name=name, type_annotation=type_ann, default=default)


def _extract_default_parameter(node: object) -> ParameterSig | None:
    """Extract a ParameterSig from a default_parameter node (no type)."""
    name_node = _child_by_field(node, "name")
    value_node = _child_by_field(node, "value")

    if name_node is None:
        return None

    name = _node_text(name_node)
    default = _node_text(value_node) if value_node is not None else None

    return ParameterSig(name=name, default=default)


def _extract_class(node: object) -> ClassSig | None:
    """Extract a ClassSig from a class_definition node.

    Args:
        node: A tree-sitter class_definition node.

    Returns:
        ClassSig or None if the node is malformed.
    """
    name_node = _child_by_field(node, "name")
    if name_node is None:
        return None

    name = _node_text(name_node)
    if not name:
        return None

    # Base classes
    bases: list[str] = []
    superclasses_node = _child_by_field(node, "superclasses")
    if superclasses_node is not None:
        for child in _named_children(superclasses_node):
            child_type = getattr(child, "type", "")
            if child_type in ("identifier", "attribute"):
                bases.append(_node_text(child))

    # Body
    body_node = _child_by_field(node, "body")
    methods: list[FunctionSig] = []
    class_variables: list[ConstantSig] = []

    if body_node is not None:
        for child in _children(body_node):
            child_type = getattr(child, "type", "")

            if child_type == "function_definition":
                func = _extract_function(child, is_method=True)
                if func is not None and _is_public_method_name(func.name):
                    methods.append(func)

            elif child_type == "decorated_definition":
                inner = _child_by_field(child, "definition")
                if inner is not None and getattr(inner, "type", "") == "function_definition":
                    func = _extract_function(inner, is_method=True)
                    if func is not None and _is_public_method_name(func.name):
                        _apply_decorators(child, func)
                        methods.append(func)

            elif child_type == "expression_statement":
                _extract_class_variable(child, class_variables)

    return ClassSig(
        name=name,
        bases=bases,
        methods=methods,
        class_variables=class_variables,
    )


def _is_public_method_name(name: str) -> bool:
    """Check whether a method name is public under the Phase 2 rule.

    Delegates to :func:`_is_public_name`. The method and top-level function
    checks share the same policy: all dunders are public, all single-leading-
    underscore names are private.
    """
    return _is_public_name(name)


def _apply_decorators(decorated_node: object, func: FunctionSig) -> None:
    """Detect structural modifiers from decorator nodes.

    Only detects staticmethod, classmethod, and property.
    Other decorators are ignored per design decision D-009.
    """
    for child in _children(decorated_node):
        if getattr(child, "type", "") != "decorator":
            continue
        # Decorator content is the child after @
        for dec_child in _named_children(child):
            dec_text = _node_text(dec_child)
            if dec_text == "staticmethod":
                func.is_static = True
            elif dec_text == "classmethod":
                func.is_class_method = True
            elif dec_text == "property":
                func.is_property = True


def _extract_from_expression_statement(
    node: object,
    constants: list[ConstantSig],
    exports: list[str],
) -> None:
    """Extract constants and __all__ from an expression_statement node."""
    for child in _named_children(node):
        if getattr(child, "type", "") != "assignment":
            continue

        left_node = _child_by_field(child, "left")
        if left_node is None:
            continue

        left_text = _node_text(left_node)

        if left_text == "__all__":
            _extract_all_exports(child, exports)
        else:
            _extract_constant(child, left_text, constants)


def _extract_all_exports(assignment_node: object, exports: list[str]) -> None:
    """Extract __all__ exports from a literal list/tuple assignment."""
    right_node = _child_by_field(assignment_node, "right")
    if right_node is None:
        return

    right_type = getattr(right_node, "type", "")
    if right_type not in ("list", "tuple"):
        # Dynamic __all__ -- ignore per spec
        return

    for child in _named_children(right_node):
        if getattr(child, "type", "") == "string":
            # Extract string content (excluding quotes)
            string_text = _extract_string_content(child)
            if string_text:
                exports.append(string_text)


def _extract_string_content(string_node: object) -> str:
    """Extract the content of a string node, excluding quotes."""
    # In tree-sitter-python, string nodes have children:
    # string_start, string_content, string_end
    for child in _children(string_node):
        if getattr(child, "type", "") == "string_content":
            return _node_text(child)
    # Fallback: strip quotes from the full text
    full = _node_text(string_node)
    if len(full) >= 2 and full[0] in ('"', "'") and full[-1] in ('"', "'"):
        return full[1:-1]
    return full


def _extract_constant(
    assignment_node: object,
    name: str,
    constants: list[ConstantSig],
) -> None:
    """Extract a constant from an assignment if it qualifies.

    A constant qualifies if it has an UPPER_CASE name or a type annotation.
    """
    # Check for type annotation
    type_node = _child_by_field(assignment_node, "type")
    type_ann = _node_text(type_node) if type_node is not None else None

    if type_ann is not None:
        constants.append(ConstantSig(name=name, type_annotation=type_ann))
    elif _UPPER_CASE_RE.match(name):
        constants.append(ConstantSig(name=name))


def _extract_class_variable(
    expr_stmt_node: object,
    class_variables: list[ConstantSig],
) -> None:
    """Extract class-level variables from expression statements in a class body."""
    for child in _named_children(expr_stmt_node):
        if getattr(child, "type", "") != "assignment":
            continue

        left_node = _child_by_field(child, "left")
        if left_node is None:
            continue

        name = _node_text(left_node)
        if not name or name.startswith("_"):
            continue

        type_node = _child_by_field(child, "type")
        type_ann = _node_text(type_node) if type_node is not None else None

        if type_ann is not None:
            class_variables.append(ConstantSig(name=name, type_annotation=type_ann))
        elif _UPPER_CASE_RE.match(name):
            class_variables.append(ConstantSig(name=name))


# -- Tree-sitter node access helpers --
# These use getattr to avoid importing tree_sitter.Node at module level,
# keeping the grammar dependency optional.


def _child_by_field(node: object, field_name: str) -> object | None:
    """Get a child node by field name, or None."""
    fn = getattr(node, "child_by_field_name", None)
    if fn is not None:
        return cast("object | None", fn(field_name))
    return None


def _children(node: object) -> list[object]:
    """Get all children of a node."""
    return getattr(node, "children", [])


def _named_children(node: object) -> list[object]:
    """Get all named children of a node."""
    return getattr(node, "named_children", [])
