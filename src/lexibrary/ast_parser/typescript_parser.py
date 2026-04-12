"""TypeScript/TSX parser: extracts public interface skeletons using tree-sitter.

Supports .ts and .tsx files. Uses the TypeScript sub-grammar for .ts files
and the TSX sub-grammar for .tsx files (both from tree-sitter-typescript).

Extracts: functions, classes, interfaces, type aliases, enums, constants,
and export declarations. Function bodies and JSX elements are ignored.

Parse-tree entry points are split so callers that need multiple extractors
against the same file can parse once and reuse the tree:

- ``parse_ts_tree(file_path)`` runs ``tree_sitter.Parser.parse`` and returns
  ``(tree, source_bytes)``.
- ``extract_interface_from_tree(tree, source_bytes, file_path)`` consumes a
  pre-parsed tuple.
- ``extract_symbols_from_tree(tree, source_bytes, file_path)`` extracts
  symbol definitions and call sites for the symbol graph.
- ``extract_interface(file_path)`` and ``extract_symbols(file_path)`` are
  thin wrappers that combine the above.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, cast

from lexibrary.ast_parser.models import (
    CallSite,
    ClassEdgeSite,
    ClassSig,
    CompositionSite,
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

# RHS node types accepted as "simple literal" for TS/JS constant extraction.
# Template strings, object literals, array literals, and arrow functions are
# intentionally excluded; see openspec/changes/symbol-graph-4 for the rationale.
_TS_CONSTANT_LITERAL_TYPES = frozenset(
    {"string", "number", "true", "false", "null", "regex"},
)

# TypeScript/JavaScript builtin type names that should be skipped during
# composition extraction because they represent primitives, not user-defined
# classes.
_TS_BUILTINS = frozenset(
    {
        "string",
        "number",
        "boolean",
        "any",
        "void",
        "never",
        "undefined",
        "null",
        "unknown",
        "object",
    }
)

# Generic wrapper types in TypeScript whose inner type arguments are the
# real composition targets.
_TS_GENERIC_WRAPPERS = frozenset(
    {
        "Array",
        "Set",
        "Map",
        "WeakMap",
        "WeakSet",
        "Promise",
        "Partial",
        "Required",
        "Readonly",
        "Record",
        "Pick",
        "Omit",
        "Exclude",
        "Extract",
        "NonNullable",
        "ReturnType",
        "InstanceType",
    }
)


def _is_ts_generic_param(name: str) -> bool:
    """Return ``True`` if ``name`` is a single uppercase letter (generic type parameter)."""
    return len(name) == 1 and name.isupper()


def _strip_ts_annotation_to_target(annotation_text: str) -> str | None:
    """Strip a TypeScript type annotation down to its composition target name.

    Generic wrappers are unwrapped: ``Array<X>`` becomes ``X``,
    ``Map<K, V>`` becomes ``V`` (last non-builtin type arg).
    ``X | null`` and ``X | undefined`` are reduced to ``X``.

    Returns ``None`` when the result is a builtin type, a single-letter
    generic parameter, or the annotation cannot be meaningfully reduced.
    """
    text = annotation_text.strip()
    if not text:
        return None

    # Handle ``X | null`` or ``X | undefined`` union syntax.
    if "|" in text:
        parts = [p.strip() for p in text.split("|")]
        candidates = [
            p for p in parts if p and p not in _TS_BUILTINS and not _is_ts_generic_param(p)
        ]
        if len(candidates) == 1:
            return _strip_ts_annotation_to_target(candidates[0])
        return None

    # Handle generic wrappers: ``Wrapper<...>``.
    angle_start = text.find("<")
    if angle_start != -1 and text.endswith(">"):
        outer = text[:angle_start].strip()
        inner = text[angle_start + 1 : -1].strip()

        if outer in _TS_GENERIC_WRAPPERS:
            args = _split_ts_type_args(inner)
            if outer in ("Map", "WeakMap", "Record"):
                # Map<K, V> -> last non-builtin arg
                for arg in reversed(args):
                    result = _strip_ts_annotation_to_target(arg)
                    if result is not None:
                        return result
                return None
            if args:
                return _strip_ts_annotation_to_target(args[0])
            return None

        # Non-wrapper generic, e.g. ``MyService<T>`` -> ``MyService``
        if outer and outer not in _TS_BUILTINS and not _is_ts_generic_param(outer):
            return outer
        return None

    # Handle array shorthand: ``X[]``.
    if text.endswith("[]"):
        inner_type = text[:-2].strip()
        return _strip_ts_annotation_to_target(inner_type)

    # Plain identifier.
    if text in _TS_BUILTINS or _is_ts_generic_param(text):
        return None
    if "." in text:
        return None
    return text


def _split_ts_type_args(inner: str) -> list[str]:
    """Split comma-separated type arguments, respecting nested angle brackets."""
    args: list[str] = []
    depth = 0
    current: list[str] = []
    for char in inner:
        if char == "<":
            depth += 1
            current.append(char)
        elif char == ">":
            depth -= 1
            current.append(char)
        elif char == "," and depth == 0:
            args.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    remaining = "".join(current).strip()
    if remaining:
        args.append(remaining)
    return args


if TYPE_CHECKING:
    from tree_sitter import Tree

logger = logging.getLogger(__name__)


def parse_ts_tree(file_path: Path) -> tuple[Tree, bytes] | None:
    """Parse a TypeScript/TSX source file once and return tree + source bytes.

    Reads the file bytes, invokes ``tree_sitter.Parser.parse`` exactly once,
    and returns the ``(tree, source_bytes)`` tuple. Returns ``None`` when the
    extension is unsupported, the grammar is unavailable, or the file cannot
    be read.

    Args:
        file_path: Path to a .ts or .tsx source file.

    Returns:
        ``(tree, source_bytes)`` or ``None`` on unsupported extension /
        unavailable grammar / I/O failure.
    """
    extension = file_path.suffix
    if extension not in (".ts", ".tsx"):
        return None

    parser = get_parser(extension)
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
    """Extract the public interface skeleton from a TypeScript or TSX file.

    Thin wrapper around :func:`parse_ts_tree` and
    :func:`extract_interface_from_tree`.

    Args:
        file_path: Path to a .ts or .tsx source file.

    Returns:
        InterfaceSkeleton with extracted interface, or None if the file
        cannot be parsed (unsupported extension, missing grammar, read error).
    """
    parsed = parse_ts_tree(file_path)
    if parsed is None:
        return None
    tree, source_bytes = parsed
    return extract_interface_from_tree(tree, source_bytes, file_path)


def extract_interface_from_tree(
    tree: Tree,
    source_bytes: bytes,
    file_path: Path,
) -> InterfaceSkeleton | None:
    """Extract the public interface from a pre-parsed TypeScript/TSX tree.

    Args:
        tree: A ``tree_sitter.Tree`` produced by :func:`parse_ts_tree`.
        source_bytes: The raw source bytes that ``tree`` was parsed from.
            Retained for callers that want to derive additional artifacts
            (symbol extraction, slicing) from the same buffer without
            re-reading the file.
        file_path: Path to the source file. Used to pick the ``tsx`` vs
            ``typescript`` language tag and populate
            :attr:`InterfaceSkeleton.file_path`.

    Returns:
        :class:`InterfaceSkeleton` describing the public API, or ``None`` if
        the tree has no root node.
    """
    del source_bytes  # Present for symmetry with extract_symbols_from_tree.

    root = tree.root_node
    if root is None:
        return None

    extension = file_path.suffix
    language = "tsx" if extension == ".tsx" else "typescript"

    skeleton = InterfaceSkeleton(
        file_path=str(file_path),
        language=language,
    )

    exports: set[str] = set()

    for child in root.children:
        _process_top_level_node(child, skeleton, exports)

    skeleton.exports = sorted(exports)
    return skeleton


def extract_symbols(file_path: Path) -> SymbolExtract | None:
    """Extract symbol definitions and call sites from a TypeScript/TSX file.

    Thin wrapper around :func:`parse_ts_tree` and
    :func:`extract_symbols_from_tree`.
    """
    parsed = parse_ts_tree(file_path)
    if parsed is None:
        return None
    tree, source_bytes = parsed
    return extract_symbols_from_tree(tree, source_bytes, file_path)


def extract_symbols_from_tree(
    tree: Tree,
    source_bytes: bytes,
    file_path: Path,
) -> SymbolExtract | None:
    """Extract symbol definitions, call sites and class edges from a pre-parsed tree.

    Definitions include ``function_declaration``, ``class_declaration``,
    ``method_definition`` inside classes, and ``lexical_declaration``
    entries whose value is an ``arrow_function``. Calls are
    ``call_expression`` descendants of each definition; ``type_arguments``
    children (``foo<T>(...)``) are ignored.

    Class edges include ``inherits`` edges emitted for every ``extends``
    or ``implements`` clause on a ``class_declaration`` (``implements`` is
    modelled as ``inherits`` so interface implementation participates in
    the class graph), and ``instantiates`` edges emitted for every
    ``new_expression`` with a bare identifier constructor. Qualified
    constructors (``new mod.Foo()``) are skipped because Phase 3
    resolution only handles bare names.

    Qualified names use the file stem as the module prefix and take the
    form ``<stem>.<class?>.<name>``. TypeScript resolution uses the
    fallback resolver in Phase 2, so the exact dotted format is not
    load-bearing — consistency with the Python format is preferred.
    """
    del source_bytes  # Reserved for future walkers.

    root = tree.root_node
    if root is None:
        return None

    extension = file_path.suffix
    language = "tsx" if extension == ".tsx" else "typescript"
    module_path = file_path.stem

    definitions: list[SymbolDefinition] = []
    def_nodes: list[tuple[object, SymbolDefinition]] = []
    enums: list[tuple[str, list[EnumMemberSig]]] = []
    constants: list[ConstantValue] = []

    for child in root.children:
        _collect_ts_top_level_definitions(
            child,
            module_path,
            definitions,
            def_nodes,
            enums,
            constants,
        )

    calls = _collect_ts_calls(def_nodes)
    class_edges = _collect_ts_class_edges(def_nodes)
    compositions = _collect_ts_compositions(def_nodes)

    return SymbolExtract(
        file_path=str(file_path),
        language=language,
        definitions=definitions,
        calls=calls,
        class_edges=class_edges,
        compositions=compositions,
        enums=enums,
        constants=constants,
    )


def _collect_ts_top_level_definitions(
    node: object,
    module_path: str,
    definitions: list[SymbolDefinition],
    def_nodes: list[tuple[object, SymbolDefinition]],
    enums: list[tuple[str, list[EnumMemberSig]]],
    constants: list[ConstantValue],
) -> None:
    """Collect a top-level TS/JS definition and recurse into classes."""
    node_type = getattr(node, "type", "")

    if node_type == "function_declaration":
        _emit_ts_function(
            node,
            module_path,
            definitions,
            def_nodes,
            parent_class=None,
            force_private=False,
        )
    elif node_type == "class_declaration":
        _emit_ts_class(
            node,
            module_path,
            definitions,
            def_nodes,
            force_private=False,
        )
    elif node_type == "enum_declaration":
        _emit_ts_enum(
            node,
            module_path,
            definitions,
            def_nodes,
            enums,
        )
    elif node_type == "lexical_declaration":
        _emit_ts_lexical_declaration(
            node,
            module_path,
            definitions,
            def_nodes,
            constants,
        )
    elif node_type == "export_statement":
        for child in getattr(node, "children", []):
            _collect_ts_top_level_definitions(
                child,
                module_path,
                definitions,
                def_nodes,
                enums,
                constants,
            )


def _emit_ts_function(
    node: object,
    qualified_prefix: str,
    definitions: list[SymbolDefinition],
    def_nodes: list[tuple[object, SymbolDefinition]],
    *,
    parent_class: str | None,
    force_private: bool,
) -> None:
    """Emit a ``function_declaration`` node as a definition.

    Also walks the body for nested function declarations, function
    expressions, and arrow functions, emitting each as a separate
    ``SymbolDefinition`` row with ``visibility='private'`` and a ``.``
    scope separator in the qualified name (mirroring Python's
    ``.<locals>.`` pattern).
    """
    name = _child_text_by_type(node, "identifier")
    if not name:
        return

    qualified_name = f"{qualified_prefix}.{name}" if qualified_prefix else name
    line_start, line_end = _line_range(node)
    visibility = "private" if force_private else _ts_visibility(name)
    body_node = _find_body_node_ts(node)
    branch_params = _extract_branch_parameters_ts(node, body_node)
    definition = SymbolDefinition(
        name=name,
        qualified_name=qualified_name,
        symbol_type="function",
        line_start=line_start,
        line_end=line_end,
        visibility=visibility,
        parent_class=parent_class,
        branch_parameters=branch_params,
    )
    definitions.append(definition)
    def_nodes.append((node, definition))

    if body_node is not None:
        nested_prefix = f"{qualified_name}.<locals>"
        _walk_nested_functions_ts(
            body_node,
            nested_prefix,
            definitions,
            def_nodes,
        )
        _walk_nested_lexical_functions_ts(
            body_node,
            nested_prefix,
            definitions,
            def_nodes,
        )


def _emit_ts_class(
    node: object,
    qualified_prefix: str,
    definitions: list[SymbolDefinition],
    def_nodes: list[tuple[object, SymbolDefinition]],
    *,
    force_private: bool,
) -> None:
    """Emit a ``class_declaration`` node as a definition with its methods."""
    name = _child_text_by_type(node, "type_identifier")
    if not name:
        return

    qualified_name = f"{qualified_prefix}.{name}" if qualified_prefix else name
    line_start, line_end = _line_range(node)
    visibility = "private" if force_private else _ts_visibility(name)
    class_def = SymbolDefinition(
        name=name,
        qualified_name=qualified_name,
        symbol_type="class",
        line_start=line_start,
        line_end=line_end,
        visibility=visibility,
        parent_class=None,
    )
    definitions.append(class_def)
    def_nodes.append((node, class_def))

    class_prefix = qualified_name
    for child in getattr(node, "children", []):
        if getattr(child, "type", "") != "class_body":
            continue
        for member in getattr(child, "children", []):
            member_type = getattr(member, "type", "")
            if member_type == "method_definition":
                _emit_ts_method(
                    member,
                    class_prefix,
                    name,
                    definitions,
                    def_nodes,
                )


def _emit_ts_enum(
    node: object,
    module_path: str,
    definitions: list[SymbolDefinition],
    def_nodes: list[tuple[object, SymbolDefinition]],
    enums: list[tuple[str, list[EnumMemberSig]]],
) -> None:
    """Emit an ``enum_declaration`` node as a ``symbol_type='enum'`` definition.

    Handles both plain ``enum Foo {...}`` and ``const enum Foo {...}`` — the
    ``const`` modifier appears as a sibling token on ``enum_declaration``
    (child with ``type='const'``) rather than a distinct node type, so no
    special branching is required.

    Members are walked out of ``enum_body``. Members of the form
    ``Name = <literal>`` appear as ``enum_assignment`` children; bare
    ``Name`` members (implicit numeric ordinal) appear as direct
    ``property_identifier`` children.
    """
    name = _child_text_by_type(node, "identifier")
    if not name:
        return

    qualified_name = f"{module_path}.{name}" if module_path else name
    line_start, line_end = _line_range(node)
    definition = SymbolDefinition(
        name=name,
        qualified_name=qualified_name,
        symbol_type="enum",
        line_start=line_start,
        line_end=line_end,
        visibility=_ts_visibility(name),
        parent_class=None,
    )
    definitions.append(definition)
    def_nodes.append((node, definition))

    members = _collect_ts_enum_members(node)
    enums.append((qualified_name, members))


def _collect_ts_enum_members(enum_node: object) -> list[EnumMemberSig]:
    """Walk an ``enum_declaration``'s ``enum_body`` and return its members.

    Returns a list of :class:`EnumMemberSig` entries with zero-based
    ``ordinal`` tracking the declaration order. Handles:

    - ``enum_assignment`` nodes (``Pending = "pending"``) — value is the
      raw source text of the RHS literal.
    - bare ``property_identifier`` children (``Active,`` with implicit
      numeric ordinal) — value is ``None``.
    """
    members: list[EnumMemberSig] = []

    body: object | None = None
    for child in getattr(enum_node, "children", []):
        if getattr(child, "type", "") == "enum_body":
            body = child
            break
    if body is None:
        return members

    ordinal = 0
    for child in getattr(body, "children", []):
        child_type = getattr(child, "type", "")

        if child_type == "enum_assignment":
            member_name: str | None = None
            value_text: str | None = None
            seen_equals = False
            for sub in getattr(child, "children", []):
                sub_type = getattr(sub, "type", "")
                if sub_type == "property_identifier" and member_name is None:
                    member_name = _node_text(sub)
                elif sub_type == "=":
                    seen_equals = True
                elif seen_equals and sub_type not in (",", ";"):
                    value_text = _node_text(sub)
                    break
            if member_name is None:
                continue
            members.append(
                EnumMemberSig(
                    name=member_name,
                    value=value_text,
                    ordinal=ordinal,
                ),
            )
            ordinal += 1

        elif child_type == "property_identifier":
            member_name = _node_text(child)
            if member_name is None:
                continue
            members.append(
                EnumMemberSig(
                    name=member_name,
                    value=None,
                    ordinal=ordinal,
                ),
            )
            ordinal += 1

    return members


def _emit_ts_method(
    node: object,
    class_prefix: str,
    parent_class: str,
    definitions: list[SymbolDefinition],
    def_nodes: list[tuple[object, SymbolDefinition]],
) -> None:
    """Emit a ``method_definition`` node as a method definition."""
    method_name: str | None = None
    for child in getattr(node, "children", []):
        if getattr(child, "type", "") == "property_identifier":
            method_name = _node_text(child)
            break
    if not method_name:
        return

    qualified_name = f"{class_prefix}.{method_name}" if class_prefix else method_name
    line_start, line_end = _line_range(node)
    body_node = _find_body_node_ts(node)
    branch_params = _extract_branch_parameters_ts(node, body_node)
    definition = SymbolDefinition(
        name=method_name,
        qualified_name=qualified_name,
        symbol_type="method",
        line_start=line_start,
        line_end=line_end,
        visibility=_ts_visibility(method_name),
        parent_class=parent_class,
        branch_parameters=branch_params,
    )
    definitions.append(definition)
    def_nodes.append((node, definition))

    if body_node is not None:
        nested_prefix = f"{qualified_name}.<locals>"
        _walk_nested_functions_ts(
            body_node,
            nested_prefix,
            definitions,
            def_nodes,
        )
        _walk_nested_lexical_functions_ts(
            body_node,
            nested_prefix,
            definitions,
            def_nodes,
        )


def _emit_ts_lexical_declaration(
    node: object,
    module_path: str,
    definitions: list[SymbolDefinition],
    def_nodes: list[tuple[object, SymbolDefinition]],
    constants: list[ConstantValue],
) -> None:
    """Emit definitions from a ``lexical_declaration`` (``const``/``let``).

    Two emission paths are supported:

    - ``const foo = () => ...`` → ``symbol_type='function'`` definition.
      Arrow functions assigned to a ``const`` binding are routed through
      the function pipeline so they participate in call extraction.
    - ``const API_URL = "..."`` → ``symbol_type='constant'`` definition
      plus a :class:`ConstantValue` entry, but only when the binding is
      ``const`` and the RHS is a primitive literal from
      :data:`_TS_CONSTANT_LITERAL_TYPES`. Object literals, array
      literals, template strings with substitutions, and arrow functions
      are intentionally excluded.
    """
    is_const = any(getattr(child, "type", "") == "const" for child in getattr(node, "children", []))

    for child in getattr(node, "children", []):
        if getattr(child, "type", "") != "variable_declarator":
            continue
        name = _child_text_by_type(child, "identifier")
        if not name:
            continue

        # Locate the RHS value node and any type annotation. The
        # ``variable_declarator`` layout is
        # ``identifier [type_annotation] = <value>`` so the value is
        # the first child after the ``=`` token (excluding trivia).
        value_node: object | None = None
        type_annotation_text: str | None = None
        seen_equals = False
        for sub in getattr(child, "children", []):
            sub_type = getattr(sub, "type", "")
            if sub_type == "type_annotation":
                type_annotation_text = _extract_type_text(sub)
            elif sub_type == "=":
                seen_equals = True
            elif seen_equals and value_node is None:
                value_node = sub

        if value_node is None:
            continue

        value_type = getattr(value_node, "type", "")
        line_start, line_end = _line_range(child)
        qualified_name = f"{module_path}.{name}" if module_path else name

        if value_type == "arrow_function":
            arrow_body = _find_body_node_ts(value_node)
            branch_params = _extract_branch_parameters_ts(value_node, arrow_body)
            definition = SymbolDefinition(
                name=name,
                qualified_name=qualified_name,
                symbol_type="function",
                line_start=line_start,
                line_end=line_end,
                visibility=_ts_visibility(name),
                parent_class=None,
                branch_parameters=branch_params,
            )
            definitions.append(definition)
            def_nodes.append((value_node, definition))
            if arrow_body is not None:
                arrow_nested_prefix = f"{qualified_name}.<locals>"
                _walk_nested_functions_ts(
                    arrow_body,
                    arrow_nested_prefix,
                    definitions,
                    def_nodes,
                )
                _walk_nested_lexical_functions_ts(
                    arrow_body,
                    arrow_nested_prefix,
                    definitions,
                    def_nodes,
                )
            continue

        if not is_const:
            continue

        if value_type not in _TS_CONSTANT_LITERAL_TYPES:
            continue

        value_text = _node_text(value_node)
        definition = SymbolDefinition(
            name=name,
            qualified_name=qualified_name,
            symbol_type="constant",
            line_start=line_start,
            line_end=line_end,
            visibility=_ts_visibility(name),
            parent_class=None,
        )
        definitions.append(definition)
        def_nodes.append((child, definition))
        constants.append(
            ConstantValue(
                name=name,
                value=value_text,
                line=line_start,
                type_annotation=type_annotation_text,
            ),
        )


# -- Branch parameter extraction (TypeScript) --
# These helpers identify which function parameters drive branching decisions
# (if/while/switch/ternary/for conditions).

# TS/JS node types whose bodies define a new scope to prune during
# branch-condition walking.
_TS_NESTED_SCOPE_TYPES = frozenset(
    {"function_declaration", "function_expression", "arrow_function", "class_declaration"},
)

# Subset of nested scope types that are named functions (not anonymous
# arrows) and should be emitted as separate ``SymbolDefinition`` rows.
_TS_NESTED_FN_TYPES = frozenset(
    {"function_declaration", "function_expression", "arrow_function"},
)

# TS/JS branch node types whose condition subtree may contain
# branch-driving identifiers.
_TS_BRANCH_NODE_TYPES = frozenset(
    {"if_statement", "while_statement", "switch_statement", "ternary_expression", "for_statement"},
)


def _walk_body_excluding_nested_scopes_ts(body_node: object) -> list[object]:
    """Return all descendant nodes of a TS/JS body, pruning nested scope bodies.

    Walks the subtree rooted at ``body_node`` and collects every node
    except those inside the body of a nested ``function_declaration``,
    ``function_expression``, ``arrow_function``, or ``class_declaration``.
    The nested definition nodes themselves ARE returned, but their children
    are NOT descended into.
    """
    results: list[object] = []
    stack: list[object] = list(getattr(body_node, "children", []))
    while stack:
        current = stack.pop(0)
        results.append(current)
        current_type = getattr(current, "type", "")
        if current_type in _TS_NESTED_SCOPE_TYPES:
            continue
        stack = list(getattr(current, "children", [])) + stack
    return results


def _function_param_names_ts(func_node: object) -> set[str]:
    """Extract raw parameter names from a TS/JS function node.

    Walks ``formal_parameters`` children to find ``required_parameter``
    and ``optional_parameter`` entries. Returns a set of bare identifier
    names (no type annotations or defaults).
    """
    names: set[str] = set()
    for child in getattr(func_node, "children", []):
        if getattr(child, "type", "") == "formal_parameters":
            for param in getattr(child, "children", []):
                param_type = getattr(param, "type", "")
                if param_type in ("required_parameter", "optional_parameter"):
                    for sub in getattr(param, "children", []):
                        if getattr(sub, "type", "") == "identifier":
                            text = _node_text(sub)
                            if text:
                                names.add(text)
                            break
                elif param_type == "identifier":
                    # Bare identifier parameter (no type annotation).
                    text = _node_text(param)
                    if text:
                        names.add(text)
            break
    return names


def _collect_branch_identifiers_ts(body_node: object) -> set[str]:
    """Collect all identifier root-names from branch conditions in a TS/JS body.

    Uses the scope-pruned walker to avoid descending into nested
    function/class bodies. For each branch node, extracts identifiers from
    the condition subtree. Attribute-access chains (``config.verbose``)
    record only the root name (``config``). ``this`` references are
    excluded.
    """
    nodes = _walk_body_excluding_nested_scopes_ts(body_node)
    ids: set[str] = set()
    for node in nodes:
        node_type = getattr(node, "type", "")
        if node_type not in _TS_BRANCH_NODE_TYPES:
            continue

        condition_node: object | None = None
        if node_type in ("if_statement", "while_statement"):
            # tree-sitter-typescript uses ``condition`` field.
            getter = getattr(node, "child_by_field_name", None)
            if getter is not None:
                condition_node = getter("condition")
            if condition_node is None:
                # Fallback: find parenthesized_expression after keyword.
                for child in getattr(node, "children", []):
                    if getattr(child, "type", "") == "parenthesized_expression":
                        condition_node = child
                        break
        elif node_type == "switch_statement":
            # The value is the parenthesized_expression after ``switch``.
            getter = getattr(node, "child_by_field_name", None)
            if getter is not None:
                condition_node = getter("value")
            if condition_node is None:
                for child in getattr(node, "children", []):
                    if getattr(child, "type", "") == "parenthesized_expression":
                        condition_node = child
                        break
        elif node_type == "ternary_expression":
            # Ternary: ``cond ? a : b`` — condition is the first named child.
            named = [c for c in getattr(node, "children", []) if getattr(c, "is_named", False)]
            if named:
                condition_node = named[0]
        elif node_type == "for_statement":
            # For-loop condition is the second expression in the header.
            # tree-sitter-typescript uses ``condition`` field.
            getter = getattr(node, "child_by_field_name", None)
            if getter is not None:
                condition_node = getter("condition")

        if condition_node is not None:
            _collect_root_identifiers_ts(condition_node, ids)
    # Remove ``this`` — it is the TS receiver, not a branch-driving parameter.
    ids.discard("this")
    return ids


def _collect_root_identifiers_ts(node: object, out: set[str]) -> None:
    """Recursively collect root identifier names from a TS/JS expression subtree.

    For ``member_expression`` chains (``config.verbose``), only the
    leftmost identifier (``config``) is recorded.
    """
    node_type = getattr(node, "type", "")
    if node_type == "identifier":
        text = _node_text(node)
        if text:
            out.add(text)
        return
    if node_type == "member_expression":
        # Walk down to the leftmost node.
        for child in getattr(node, "children", []):
            child_type = getattr(child, "type", "")
            if child_type not in (".", "?."):
                _collect_root_identifiers_ts(child, out)
                return
        return
    for child in getattr(node, "children", []):
        _collect_root_identifiers_ts(child, out)


def _extract_branch_parameters_ts(
    func_node: object,
    body_node: object | None,
) -> list[str]:
    """Return sorted parameter names appearing in branch conditions for TS/JS.

    Extracts parameter names from the function's formal_parameters, walks
    the body (pruning nested scopes) for branch-condition identifiers,
    intersects the two, and returns the sorted result. ``this`` references
    are excluded.
    """
    if body_node is None:
        return []

    param_names = _function_param_names_ts(func_node)
    if not param_names:
        return []

    branch_ids = _collect_branch_identifiers_ts(body_node)
    return sorted(branch_ids & param_names)


def _find_body_node_ts(func_node: object) -> object | None:
    """Find the body node (``statement_block``) of a TS/JS function."""
    for child in getattr(func_node, "children", []):
        if getattr(child, "type", "") == "statement_block":
            return cast("object", child)
    return None


def _walk_nested_functions_ts(
    body_node: object,
    nested_prefix: str,
    definitions: list[SymbolDefinition],
    def_nodes: list[tuple[object, SymbolDefinition]],
) -> None:
    """Recursively emit nested functions inside a TS/JS body.

    Walks direct and indirect children of ``body_node`` looking for
    ``function_declaration``, ``function_expression``, and
    ``arrow_function`` nodes. Each is emitted as a separate
    ``SymbolDefinition`` with ``visibility='private'`` and a ``.``
    scope separator mirroring Python's ``.<locals>.`` pattern.

    The walker does NOT descend into the bodies of nested scopes
    it discovers — each nested function drives its own recursion
    when emitted, so the ``<locals>`` prefix chain extends correctly.
    """
    stack: list[object] = list(getattr(body_node, "children", []))
    while stack:
        current = stack.pop(0)
        current_type = getattr(current, "type", "")

        if current_type in _TS_NESTED_FN_TYPES:
            # Determine the name.
            nested_name: str | None = None
            if current_type == "function_declaration":
                nested_name = _child_text_by_type(current, "identifier")
            elif current_type == "function_expression":
                # Named function expression: ``const x = function foo() {}``
                nested_name = _child_text_by_type(current, "identifier")
            elif current_type == "arrow_function":
                # Arrow functions are anonymous — check if parent is a
                # variable_declarator with an identifier.
                # Since we're walking flat, we can't easily get the parent.
                # Skip anonymous arrows — they don't get a separate row
                # (they're already covered by the lexical_declaration path).
                pass

            if not nested_name:
                # Anonymous arrow or function expression — skip.
                continue

            nested_qualified = f"{nested_prefix}.{nested_name}" if nested_prefix else nested_name
            n_line_start, n_line_end = _line_range(current)
            nested_body = _find_body_node_ts(current)
            nested_branch_params = _extract_branch_parameters_ts(current, nested_body)
            nested_def = SymbolDefinition(
                name=nested_name,
                qualified_name=nested_qualified,
                symbol_type="function",
                line_start=n_line_start,
                line_end=n_line_end,
                visibility="private",
                parent_class=None,
                branch_parameters=nested_branch_params,
            )
            definitions.append(nested_def)
            def_nodes.append((current, nested_def))

            if nested_body is not None:
                _walk_nested_functions_ts(
                    nested_body,
                    f"{nested_qualified}.<locals>",
                    definitions,
                    def_nodes,
                )
            # Do not descend into this node's children via the stack.
            continue

        if current_type in _TS_NESTED_SCOPE_TYPES:
            # Other scope type (e.g. class_declaration) — prune.
            continue

        # Recurse into non-scope children (e.g. if/for/while blocks).
        stack = list(getattr(current, "children", [])) + stack


# Also handle lexical_declaration (``const inner = () => ...``) inside
# function bodies by detecting variable_declarator with arrow_function
# children. This is handled by _walk_nested_functions_ts_lexical which is
# called alongside _walk_nested_functions_ts.


def _walk_nested_lexical_functions_ts(
    body_node: object,
    nested_prefix: str,
    definitions: list[SymbolDefinition],
    def_nodes: list[tuple[object, SymbolDefinition]],
) -> None:
    """Emit nested ``const name = () => ...`` arrow functions inside a body.

    Walks the body looking for ``lexical_declaration`` / ``variable_declaration``
    nodes that contain ``variable_declarator`` with an ``arrow_function`` or
    ``function_expression`` child. Each is emitted as a separate
    ``SymbolDefinition`` with ``visibility='private'``.
    """
    stack: list[object] = list(getattr(body_node, "children", []))
    while stack:
        current = stack.pop(0)
        current_type = getattr(current, "type", "")

        if current_type in _TS_NESTED_SCOPE_TYPES:
            continue

        if current_type in ("lexical_declaration", "variable_declaration"):
            for vd in getattr(current, "children", []):
                if getattr(vd, "type", "") != "variable_declarator":
                    continue
                vd_name = _child_text_by_type(vd, "identifier")
                if not vd_name:
                    continue
                # Look for arrow_function or function_expression child.
                fn_node: object | None = None
                found_eq = False
                for sub in getattr(vd, "children", []):
                    sub_type = getattr(sub, "type", "")
                    if sub_type == "=":
                        found_eq = True
                    elif found_eq and sub_type in ("arrow_function", "function_expression"):
                        fn_node = sub
                        break

                if fn_node is None:
                    continue

                vd_qualified = f"{nested_prefix}.{vd_name}" if nested_prefix else vd_name
                vd_ls, vd_le = _line_range(vd)
                vd_body = _find_body_node_ts(fn_node)
                vd_branch = _extract_branch_parameters_ts(fn_node, vd_body)
                vd_def = SymbolDefinition(
                    name=vd_name,
                    qualified_name=vd_qualified,
                    symbol_type="function",
                    line_start=vd_ls,
                    line_end=vd_le,
                    visibility="private",
                    parent_class=None,
                    branch_parameters=vd_branch,
                )
                definitions.append(vd_def)
                def_nodes.append((fn_node, vd_def))

                if vd_body is not None:
                    _walk_nested_functions_ts(
                        vd_body,
                        f"{vd_qualified}.<locals>",
                        definitions,
                        def_nodes,
                    )
                    _walk_nested_lexical_functions_ts(
                        vd_body,
                        f"{vd_qualified}.<locals>",
                        definitions,
                        def_nodes,
                    )
            # Don't recurse into the lexical_declaration's other children.
            continue

        stack = list(getattr(current, "children", [])) + stack


def _collect_ts_calls(
    def_nodes: list[tuple[object, SymbolDefinition]],
) -> list[CallSite]:
    """Walk every definition body and emit :class:`CallSite` entries.

    The dedup key is ``(start_byte, end_byte)`` because tree-sitter's
    Python bindings return fresh wrapper objects on every traversal.
    """
    if not def_nodes:
        return []

    definition_spans: list[tuple[SymbolDefinition, int, int]] = []
    for def_node, definition in def_nodes:
        start_row, end_row = _node_row_span(def_node)
        definition_spans.append((definition, start_row, end_row))

    definition_spans.sort(key=lambda item: (-item[1], item[2]))

    seen_call_keys: set[tuple[int, int]] = set()
    calls: list[CallSite] = []

    for def_node, _definition in def_nodes:
        for call_node in _iter_ts_call_descendants(def_node):
            call_key = _node_byte_key(call_node)
            if call_key in seen_call_keys:
                continue
            seen_call_keys.add(call_key)

            call_row = _node_row_span(call_node)[0]
            owner: SymbolDefinition | None = None
            for candidate, start_row, end_row in definition_spans:
                if start_row <= call_row <= end_row:
                    owner = candidate
                    break
            if owner is None:
                continue

            call = _build_ts_call_site(call_node, owner.qualified_name)
            if call is not None:
                calls.append(call)

    calls.sort(key=lambda c: (c.line, c.callee_name, c.caller_name))
    return calls


def _collect_ts_class_edges(
    def_nodes: list[tuple[object, SymbolDefinition]],
) -> list[ClassEdgeSite]:
    """Emit ``ClassEdgeSite`` entries for TS/TSX definitions.

    Two kinds of edges are recorded:

    - ``inherits``: one edge per ``extends`` or ``implements`` clause on a
      ``class_declaration``. ``implements`` is intentionally modelled as
      ``inherits`` — the symbol graph does not distinguish interfaces from
      base classes, and the refactoring playbook treats both as "things
      whose break-contract depends on this class".
    - ``instantiates``: one edge per ``new_expression`` whose constructor
      is a bare ``identifier``. ``new mod.Foo()`` and
      ``new some.chained.expr()`` are skipped because Phase 3 resolution
      only handles bare names.

    Unlike :func:`_collect_ts_calls`, the walker explicitly re-descends
    from each class-declaration root so inherits clauses sit outside any
    definition body (the class-body containing span matters for method
    members, not for the heritage clause itself).
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

    definition_spans.sort(key=lambda item: (-item[1], item[2]))

    edges: list[ClassEdgeSite] = []

    # ---- inherits edges ----
    for class_node, class_def in class_defs_by_qualified.values():
        heritage_node: object | None = None
        for child in getattr(class_node, "children", []):
            if getattr(child, "type", "") == "class_heritage":
                heritage_node = child
                break
        if heritage_node is None:
            continue
        for target_name in _iter_ts_heritage_names(heritage_node):
            edges.append(
                ClassEdgeSite(
                    source_name=class_def.qualified_name,
                    target_name=target_name,
                    edge_type="inherits",
                    line=class_def.line_start,
                ),
            )

    # ---- instantiates edges ----
    seen_new_keys: set[tuple[int, int]] = set()
    for def_node, _definition in def_nodes:
        for new_node in _iter_ts_new_expression_descendants(def_node):
            key = _node_byte_key(new_node)
            if key in seen_new_keys:
                continue
            seen_new_keys.add(key)

            constructor_name = _ts_bare_new_constructor(new_node)
            if constructor_name is None:
                continue

            call_row = _node_row_span(new_node)[0]
            owner: SymbolDefinition | None = None
            for candidate, start_row, end_row in definition_spans:
                if start_row <= call_row <= end_row:
                    owner = candidate
                    break
            if owner is None:
                continue

            edges.append(
                ClassEdgeSite(
                    source_name=owner.qualified_name,
                    target_name=constructor_name,
                    edge_type="instantiates",
                    line=call_row + 1,
                ),
            )

    edges.sort(key=lambda e: (e.line, e.target_name, e.source_name, e.edge_type))
    return edges


def _collect_ts_compositions(
    def_nodes: list[tuple[object, SymbolDefinition]],
) -> list[CompositionSite]:
    """Emit ``CompositionSite`` entries from class field annotations.

    Walks every ``class_declaration`` body looking for
    ``public_field_definition`` nodes that have a ``type_annotation``
    child. The annotation text is fed through
    :func:`_strip_ts_annotation_to_target` which unwraps generic wrappers
    and filters builtins and single-letter generic parameters.
    """
    compositions: list[CompositionSite] = []

    for def_node, definition in def_nodes:
        if definition.symbol_type != "class":
            continue

        # Find the class_body child.
        class_body: object | None = None
        for child in getattr(def_node, "children", []):
            if getattr(child, "type", "") == "class_body":
                class_body = child
                break
        if class_body is None:
            continue

        class_qualified = definition.qualified_name

        for member in getattr(class_body, "children", []):
            member_type = getattr(member, "type", "")
            if member_type != "public_field_definition":
                continue

            # Extract field name and type annotation.
            field_name: str | None = None
            type_ann_text: str | None = None

            for sub in getattr(member, "children", []):
                sub_type = getattr(sub, "type", "")
                if sub_type == "property_identifier" and field_name is None:
                    field_name = _node_text(sub)
                elif sub_type == "type_annotation" and type_ann_text is None:
                    type_ann_text = _extract_type_text(sub)

            if not field_name or not type_ann_text:
                continue

            target = _strip_ts_annotation_to_target(type_ann_text)
            if target is None:
                continue

            line_start, _ = _line_range(member)
            compositions.append(
                CompositionSite(
                    source_class=class_qualified,
                    target_name=target,
                    attribute_name=field_name,
                    line=line_start,
                ),
            )

    compositions.sort(key=lambda c: (c.line, c.target_name, c.source_class))
    return compositions


def _iter_ts_heritage_names(heritage_node: object) -> list[str]:
    """Return base-class / interface names from a ``class_heritage`` node.

    Each ``extends_clause`` and ``implements_clause`` child is scanned for
    ``identifier``, ``type_identifier`` and ``member_expression`` entries.
    Type argument subtrees (``type_arguments``) and separators (``,``) are
    ignored. ``member_expression`` (qualified bases like ``mod.Base``) are
    emitted with their full dotted text — the resolver strips module
    prefixes in a later pass.
    """
    names: list[str] = []
    for clause in getattr(heritage_node, "children", []):
        clause_type = getattr(clause, "type", "")
        if clause_type not in ("extends_clause", "implements_clause"):
            continue
        for sub in getattr(clause, "children", []):
            sub_type = getattr(sub, "type", "")
            if sub_type in ("identifier", "type_identifier", "member_expression"):
                text = _node_text(sub) or ""
                if text:
                    names.append(text)
    return names


def _iter_ts_new_expression_descendants(node: object) -> list[object]:
    """Return every ``new_expression`` descendant of ``node``."""
    results: list[object] = []
    stack: list[object] = list(getattr(node, "children", []))
    while stack:
        current = stack.pop(0)
        if getattr(current, "type", "") == "new_expression":
            results.append(current)
        stack = list(getattr(current, "children", [])) + stack
    return results


def _ts_bare_new_constructor(new_node: object) -> str | None:
    """Return the bare constructor name of a ``new_expression``, or ``None``.

    tree-sitter-typescript exposes the constructor through the
    ``constructor`` field. Only bare ``identifier`` constructors are
    returned; ``member_expression`` (``new mod.Foo()``), call chains and
    function expressions return ``None``.
    """
    getter = getattr(new_node, "child_by_field_name", None)
    constructor_node: object | None = None
    if getter is not None:
        constructor_node = cast("object | None", getter("constructor"))
    if constructor_node is None:
        for child in getattr(new_node, "children", []):
            child_type = getattr(child, "type", "")
            if child_type in ("new", "arguments", "type_arguments"):
                continue
            constructor_node = child
            break
    if constructor_node is None:
        return None
    if getattr(constructor_node, "type", "") != "identifier":
        return None
    text = _node_text(constructor_node)
    return text or None


def _node_byte_key(node: object) -> tuple[int, int]:
    """Return ``(start_byte, end_byte)`` for a tree-sitter node.

    Used as a dedup key — see ``python_parser._node_byte_key`` for the
    identity-stability rationale.
    """
    start = getattr(node, "start_byte", -1)
    end = getattr(node, "end_byte", -1)
    return int(start), int(end)


def _iter_ts_call_descendants(node: object) -> list[object]:
    """Return every ``call_expression`` descendant of ``node``."""
    results: list[object] = []
    stack: list[object] = list(getattr(node, "children", []))
    while stack:
        current = stack.pop(0)
        if getattr(current, "type", "") == "call_expression":
            results.append(current)
        stack = list(getattr(current, "children", [])) + stack
    return results


def _build_ts_call_site(
    call_node: object,
    caller_qualified_name: str,
) -> CallSite | None:
    """Translate a ``call_expression`` into a :class:`CallSite`.

    Mirrors the Python rules: identifier callees produce receiver-less
    call sites, ``member_expression`` callees produce ``receiver.name``
    call sites, and calls on literals/subscripts/lambdas/super chains are
    skipped.
    """
    func_node = _call_function_child(call_node)
    if func_node is None:
        return None

    line = _node_row_span(call_node)[0] + 1
    func_type = getattr(func_node, "type", "")

    if func_type == "identifier":
        callee_name = _node_text(func_node) or ""
        if not callee_name:
            return None
        if callee_name == "super":
            return None
        return CallSite(
            caller_name=caller_qualified_name,
            callee_name=callee_name,
            receiver=None,
            line=line,
            is_method_call=False,
        )

    if func_type == "member_expression":
        obj_node: object | None = None
        prop_node: object | None = None
        for child in getattr(func_node, "children", []):
            child_type = getattr(child, "type", "")
            if child_type == "property_identifier" and prop_node is None:
                prop_node = child
            elif child_type not in (".", "?.") and obj_node is None:
                obj_node = child
        if prop_node is None:
            return None
        prop_name = _node_text(prop_node) or ""
        if not prop_name:
            return None
        receiver, display = _ts_member_receiver(obj_node)
        if receiver is None:
            return None
        return CallSite(
            caller_name=caller_qualified_name,
            callee_name=f"{display}.{prop_name}",
            receiver=receiver,
            line=line,
            is_method_call=True,
        )

    return None


def _call_function_child(call_node: object) -> object | None:
    """Return the function/callee subtree of a ``call_expression``.

    tree-sitter-typescript exposes the callee through the ``function``
    field; fall back to the first non-``type_arguments`` child when
    ``child_by_field_name`` is not available on the node.
    """
    getter = getattr(call_node, "child_by_field_name", None)
    if getter is not None:
        result: object | None = getter("function")
        if result is not None:
            return result

    for child in getattr(call_node, "children", []):
        child_type = getattr(child, "type", "")
        if child_type in ("(", "arguments", "type_arguments", ","):
            continue
        return cast("object", child)
    return None


def _ts_member_receiver(
    obj_node: object | None,
) -> tuple[str | None, str]:
    """Mirror of :func:`_attribute_receiver` for TS/JS member expressions."""
    if obj_node is None:
        return None, ""
    obj_type = getattr(obj_node, "type", "")

    if obj_type == "call_expression":
        inner_func = _call_function_child(obj_node)
        if inner_func is not None and getattr(inner_func, "type", "") == "identifier":
            inner_name = _node_text(inner_func) or ""
            if inner_name == "super":
                return "super", "super"
        return None, ""

    if obj_type in {
        "string",
        "template_string",
        "number",
        "true",
        "false",
        "null",
        "undefined",
        "array",
        "object",
        "subscript_expression",
        "arrow_function",
        "parenthesized_expression",
        "function_expression",
    }:
        return None, ""

    text = _node_text(obj_node) or ""
    if not text:
        return None, ""
    return text, text


def _line_range(node: object) -> tuple[int, int]:
    """Return (line_start, line_end) 1-indexed."""
    start_row, end_row = _node_row_span(node)
    return start_row + 1, end_row + 1


def _node_row_span(node: object) -> tuple[int, int]:
    """Return (start_row, end_row) 0-indexed from tree-sitter positions."""
    start = getattr(node, "start_point", (0, 0))
    end = getattr(node, "end_point", start)
    start_row = start[0] if isinstance(start, (tuple, list)) else 0
    end_row = end[0] if isinstance(end, (tuple, list)) else start_row
    return int(start_row), int(end_row)


def _ts_visibility(name: str) -> str:
    """TS/JS visibility rule: names starting with ``_`` are private."""
    return "private" if name.startswith("_") else "public"


def _process_top_level_node(
    node: object,
    skeleton: InterfaceSkeleton,
    exports: set[str],
) -> None:
    """Process a single top-level AST node and populate the skeleton."""
    # Use dynamic attribute access for tree-sitter node objects
    node_type: str = getattr(node, "type", "")

    if node_type == "export_statement":
        _process_export_statement(node, skeleton, exports)
    elif node_type == "function_declaration":
        func = _extract_function(node)
        if func is not None:
            skeleton.functions.append(func)
    elif node_type == "class_declaration":
        cls = _extract_class(node)
        if cls is not None:
            skeleton.classes.append(cls)
    elif node_type == "interface_declaration":
        cls = _extract_interface_decl(node)
        if cls is not None:
            skeleton.classes.append(cls)
    elif node_type == "type_alias_declaration":
        const = _extract_type_alias(node)
        if const is not None:
            skeleton.constants.append(const)
    elif node_type == "enum_declaration":
        cls = _extract_enum(node)
        if cls is not None:
            skeleton.classes.append(cls)
    elif node_type == "lexical_declaration":
        consts = _extract_lexical_constants(node)
        skeleton.constants.extend(consts)


def _process_export_statement(
    node: object,
    skeleton: InterfaceSkeleton,
    exports: set[str],
) -> None:
    """Process an export_statement node.

    This handles:
    - export function ...
    - export default class ...
    - export { name1, name2 }
    - export const ...
    - export interface ...
    - export type ...
    - export enum ...
    """
    children = getattr(node, "children", [])

    # Check for 'default' keyword
    is_default = any(getattr(c, "type", "") == "default" for c in children)

    for child in children:
        child_type = getattr(child, "type", "")

        if child_type == "function_declaration":
            func = _extract_function(child)
            if func is not None:
                skeleton.functions.append(func)
                exports.add(func.name)

        elif child_type == "class_declaration":
            cls = _extract_class(child)
            if cls is not None:
                skeleton.classes.append(cls)
                exports.add(cls.name)

        elif child_type == "interface_declaration":
            iface = _extract_interface_decl(child)
            if iface is not None:
                skeleton.classes.append(iface)
                exports.add(iface.name)

        elif child_type == "type_alias_declaration":
            const = _extract_type_alias(child)
            if const is not None:
                skeleton.constants.append(const)
                exports.add(const.name)

        elif child_type == "enum_declaration":
            enum = _extract_enum(child)
            if enum is not None:
                skeleton.classes.append(enum)
                exports.add(enum.name)

        elif child_type == "lexical_declaration":
            consts = _extract_lexical_constants(child)
            for c in consts:
                skeleton.constants.append(c)
                exports.add(c.name)
            # Also track exported arrow function variable names
            for vname in _extract_variable_names(child):
                exports.add(vname)

        elif child_type == "export_clause":
            # export { name1, name2 }
            for spec in getattr(child, "children", []):
                if getattr(spec, "type", "") == "export_specifier":
                    name = _get_export_specifier_name(spec)
                    if name:
                        exports.add(name)

        elif child_type == "identifier" and is_default:
            # export default <identifier>
            name = _node_text(child)
            if name:
                exports.add(name)


def _extract_function(node: object) -> FunctionSig | None:
    """Extract a FunctionSig from a function_declaration node."""
    name = _child_text_by_type(node, "identifier")
    if not name:
        return None

    children = getattr(node, "children", [])

    is_async = any(getattr(c, "type", "") == "async" for c in children)

    params: list[ParameterSig] = []
    return_type: str | None = None

    for child in children:
        child_type = getattr(child, "type", "")
        if child_type == "formal_parameters":
            params = _extract_parameters(child)
        elif child_type == "type_annotation":
            return_type = _extract_type_text(child)

    return FunctionSig(
        name=name,
        parameters=params,
        return_type=return_type,
        is_async=is_async,
    )


def _extract_class(node: object) -> ClassSig | None:
    """Extract a ClassSig from a class_declaration node."""
    name = _child_text_by_type(node, "type_identifier")
    if not name:
        return None

    bases: list[str] = []
    methods: list[FunctionSig] = []
    class_variables: list[ConstantSig] = []

    for child in getattr(node, "children", []):
        child_type = getattr(child, "type", "")

        if child_type == "class_heritage":
            bases = _extract_heritage(child)

        elif child_type == "class_body":
            for member in getattr(child, "children", []):
                member_type = getattr(member, "type", "")

                if member_type == "method_definition":
                    method = _extract_method(member)
                    if method is not None:
                        methods.append(method)

                elif member_type == "public_field_definition":
                    field = _extract_field(member)
                    if field is not None:
                        class_variables.append(field)

    return ClassSig(
        name=name,
        bases=bases,
        methods=methods,
        class_variables=class_variables,
    )


def _extract_interface_decl(node: object) -> ClassSig | None:
    """Extract a ClassSig from an interface_declaration node.

    Interfaces are represented as ClassSig for uniformity. Methods become
    FunctionSig entries, properties become ConstantSig entries.
    """
    name = _child_text_by_type(node, "type_identifier")
    if not name:
        return None

    methods: list[FunctionSig] = []
    class_variables: list[ConstantSig] = []
    bases: list[str] = []

    for child in getattr(node, "children", []):
        child_type = getattr(child, "type", "")

        if child_type == "extends_type_clause":
            # interface Foo extends Bar, Baz
            for sub in getattr(child, "children", []):
                sub_type = getattr(sub, "type", "")
                if sub_type in ("type_identifier", "identifier"):
                    text = _node_text(sub)
                    if text:
                        bases.append(text)

        elif child_type == "interface_body":
            for member in getattr(child, "children", []):
                member_type = getattr(member, "type", "")

                if member_type == "method_signature":
                    method = _extract_interface_method(member)
                    if method is not None:
                        methods.append(method)

                elif member_type == "property_signature":
                    prop = _extract_interface_property(member)
                    if prop is not None:
                        class_variables.append(prop)

    return ClassSig(
        name=name,
        bases=bases,
        methods=methods,
        class_variables=class_variables,
    )


def _extract_type_alias(node: object) -> ConstantSig | None:
    """Extract a ConstantSig from a type_alias_declaration node.

    Type aliases are represented as constants. The type annotation is the
    RHS of the alias (e.g., for `type UserId = string`, type_annotation="string").
    """
    name = _child_text_by_type(node, "type_identifier")
    if not name:
        return None

    # The value type is everything after the '=' sign, excluding ';'
    children = getattr(node, "children", [])
    type_annotation: str | None = None

    found_equals = False
    for child in children:
        child_type = getattr(child, "type", "")
        if child_type == "=":
            found_equals = True
            continue
        if found_equals and child_type != ";":
            type_annotation = _node_text(child)
            break

    return ConstantSig(name=name, type_annotation=type_annotation)


def _extract_enum(node: object) -> ClassSig | None:
    """Extract a ClassSig from an enum_declaration node.

    Enums are represented as class-like structures. Enum members become
    class_variables (ConstantSig entries).
    """
    name = _child_text_by_type(node, "identifier")
    if not name:
        return None

    members: list[ConstantSig] = []

    for child in getattr(node, "children", []):
        if getattr(child, "type", "") == "enum_body":
            for member in getattr(child, "children", []):
                if getattr(member, "type", "") == "property_identifier":
                    member_name = _node_text(member)
                    if member_name:
                        members.append(ConstantSig(name=member_name))

    return ClassSig(
        name=name,
        bases=[],
        methods=[],
        class_variables=members,
    )


def _extract_lexical_constants(node: object) -> list[ConstantSig]:
    """Extract ConstantSig entries from a lexical_declaration (const/let).

    Only extracts simple variable declarations with optional type annotations.
    Arrow functions assigned to const are NOT extracted as constants -- they
    would need separate handling as functions if desired.
    """
    results: list[ConstantSig] = []

    for child in getattr(node, "children", []):
        if getattr(child, "type", "") == "variable_declarator":
            # Check if the value is an arrow function -- skip those
            has_arrow = any(
                getattr(c, "type", "") == "arrow_function" for c in getattr(child, "children", [])
            )
            if has_arrow:
                continue

            name = _child_text_by_type(child, "identifier")
            if not name:
                continue

            type_annotation: str | None = None
            for sub in getattr(child, "children", []):
                if getattr(sub, "type", "") == "type_annotation":
                    type_annotation = _extract_type_text(sub)
                    break

            results.append(ConstantSig(name=name, type_annotation=type_annotation))

    return results


def _extract_method(node: object) -> FunctionSig | None:
    """Extract a FunctionSig from a method_definition node."""
    children = getattr(node, "children", [])

    name: str | None = None
    params: list[ParameterSig] = []
    return_type: str | None = None
    is_async = False
    is_static = False
    is_property = False

    for child in children:
        child_type = getattr(child, "type", "")

        if child_type == "property_identifier":
            name = _node_text(child)
        elif child_type == "formal_parameters":
            params = _extract_parameters(child)
        elif child_type == "type_annotation":
            return_type = _extract_type_text(child)
        elif child_type == "async":
            is_async = True
        elif child_type == "static":
            is_static = True
        elif child_type == "get":
            is_property = True

    if name is None:
        return None

    return FunctionSig(
        name=name,
        parameters=params,
        return_type=return_type,
        is_async=is_async,
        is_method=True,
        is_static=is_static,
        is_property=is_property,
    )


def _extract_interface_method(node: object) -> FunctionSig | None:
    """Extract a FunctionSig from a method_signature node in an interface."""
    children = getattr(node, "children", [])

    name: str | None = None
    params: list[ParameterSig] = []
    return_type: str | None = None

    for child in children:
        child_type = getattr(child, "type", "")

        if child_type == "property_identifier":
            name = _node_text(child)
        elif child_type == "formal_parameters":
            params = _extract_parameters(child)
        elif child_type == "type_annotation":
            return_type = _extract_type_text(child)

    if name is None:
        return None

    return FunctionSig(
        name=name,
        parameters=params,
        return_type=return_type,
        is_method=True,
    )


def _extract_interface_property(node: object) -> ConstantSig | None:
    """Extract a ConstantSig from a property_signature node in an interface."""
    name: str | None = None
    type_annotation: str | None = None

    for child in getattr(node, "children", []):
        child_type = getattr(child, "type", "")

        if child_type == "property_identifier":
            name = _node_text(child)
        elif child_type == "type_annotation":
            type_annotation = _extract_type_text(child)

    if name is None:
        return None

    return ConstantSig(name=name, type_annotation=type_annotation)


def _extract_field(node: object) -> ConstantSig | None:
    """Extract a ConstantSig from a public_field_definition node."""
    name: str | None = None
    type_annotation: str | None = None

    for child in getattr(node, "children", []):
        child_type = getattr(child, "type", "")

        if child_type == "property_identifier":
            name = _node_text(child)
        elif child_type == "type_annotation":
            type_annotation = _extract_type_text(child)

    if name is None:
        return None

    return ConstantSig(name=name, type_annotation=type_annotation)


def _extract_heritage(node: object) -> list[str]:
    """Extract base class and interface names from a class_heritage node."""
    bases: list[str] = []

    for child in getattr(node, "children", []):
        child_type = getattr(child, "type", "")

        if child_type in ("extends_clause", "implements_clause"):
            for sub in getattr(child, "children", []):
                sub_type = getattr(sub, "type", "")
                if sub_type in ("type_identifier", "identifier"):
                    text = _node_text(sub)
                    if text:
                        bases.append(text)

    return bases


def _extract_parameters(node: object) -> list[ParameterSig]:
    """Extract parameter signatures from a formal_parameters node."""
    params: list[ParameterSig] = []

    for child in getattr(node, "children", []):
        child_type = getattr(child, "type", "")

        if child_type in ("required_parameter", "optional_parameter"):
            param = _extract_single_parameter(child)
            if param is not None:
                params.append(param)

    return params


def _extract_single_parameter(node: object) -> ParameterSig | None:
    """Extract a ParameterSig from a required_parameter or optional_parameter node."""
    name: str | None = None
    type_annotation: str | None = None
    default: str | None = None

    children = getattr(node, "children", [])

    found_equals = False
    for child in children:
        child_type = getattr(child, "type", "")

        if child_type == "identifier":
            name = _node_text(child)
        elif child_type == "type_annotation":
            type_annotation = _extract_type_text(child)
        elif child_type == "=":
            found_equals = True
        elif found_equals and child_type not in (
            "accessibility_modifier",
            "?",
            ",",
        ):
            default = _node_text(child)
            found_equals = False

    if name is None:
        return None

    return ParameterSig(name=name, type_annotation=type_annotation, default=default)


def _extract_type_text(node: object) -> str | None:
    """Extract the type text from a type_annotation node.

    Skips the leading ':' and returns the text of the type itself.
    """
    children = getattr(node, "children", [])

    for child in children:
        if getattr(child, "type", "") != ":":
            return _node_text(child)

    return None


def _extract_variable_names(node: object) -> list[str]:
    """Extract all variable names from a lexical_declaration node.

    This returns names from ALL variable_declarator children, including
    arrow functions. Used to track exported names even when the value
    is an arrow function (which is not extracted as a constant).
    """
    names: list[str] = []
    for child in getattr(node, "children", []):
        if getattr(child, "type", "") == "variable_declarator":
            name = _child_text_by_type(child, "identifier")
            if name:
                names.append(name)
    return names


def _get_export_specifier_name(node: object) -> str | None:
    """Get the exported name from an export_specifier node."""
    for child in getattr(node, "children", []):
        if getattr(child, "type", "") == "identifier":
            return _node_text(child)
    return None


def _child_text_by_type(node: object, child_type: str) -> str | None:
    """Find the first child of a given type and return its text."""
    for child in getattr(node, "children", []):
        if getattr(child, "type", "") == child_type:
            return _node_text(child)
    return None


def _node_text(node: object) -> str | None:
    """Get the UTF-8 text content of a tree-sitter node."""
    text_bytes = getattr(node, "text", None)
    if text_bytes is None:
        return None
    if isinstance(text_bytes, bytes):
        return text_bytes.decode("utf-8")
    return str(text_bytes)
