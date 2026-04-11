"""JavaScript/JSX parser: extract public interface using tree-sitter.

Handles function declarations, arrow functions assigned to const,
class declarations, ES module exports, and CommonJS module.exports.
JavaScript has no native type annotations, so all type fields are None.

Parse-tree entry points are split so callers that need multiple extractors
against the same file can parse once and reuse the tree:

- ``parse_js_tree(file_path)`` runs ``tree_sitter.Parser.parse`` and returns
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

if TYPE_CHECKING:
    from tree_sitter import Node, Tree

from lexibrary.ast_parser.models import (
    CallSite,
    ClassEdgeSite,
    ClassSig,
    ConstantSig,
    FunctionSig,
    InterfaceSkeleton,
    ParameterSig,
    SymbolDefinition,
    SymbolExtract,
)
from lexibrary.ast_parser.registry import get_parser

logger = logging.getLogger(__name__)


def parse_js_tree(file_path: Path) -> tuple[Tree, bytes] | None:
    """Parse a JavaScript/JSX source file once and return tree + source bytes.

    Reads the file bytes, invokes ``tree_sitter.Parser.parse`` exactly once,
    and returns the ``(tree, source_bytes)`` tuple. Returns ``None`` when the
    grammar is unavailable or the file cannot be read.

    Args:
        file_path: Path to the .js or .jsx file.

    Returns:
        ``(tree, source_bytes)`` or ``None`` on unavailable grammar /
        I/O failure.
    """
    extension = file_path.suffix
    parser = get_parser(extension)
    if parser is None:
        return None

    try:
        source_bytes = file_path.read_bytes()
    except OSError:
        logger.exception("Failed to read file: %s", file_path)
        return None

    tree = parser.parse(source_bytes)
    return tree, source_bytes


def extract_interface(file_path: Path) -> InterfaceSkeleton | None:
    """Extract the public interface from a JavaScript or JSX file.

    Thin wrapper around :func:`parse_js_tree` and
    :func:`extract_interface_from_tree`.

    Args:
        file_path: Path to the .js or .jsx file.

    Returns:
        InterfaceSkeleton with extracted signatures, or None if the file
        cannot be parsed.
    """
    parsed = parse_js_tree(file_path)
    if parsed is None:
        return None
    tree, source_bytes = parsed
    return extract_interface_from_tree(tree, source_bytes, file_path)


def extract_interface_from_tree(
    tree: Tree,
    source_bytes: bytes,
    file_path: Path,
) -> InterfaceSkeleton | None:
    """Extract the public interface from a pre-parsed JavaScript/JSX tree.

    Args:
        tree: A ``tree_sitter.Tree`` produced by :func:`parse_js_tree`.
        source_bytes: The raw source bytes that ``tree`` was parsed from.
            Retained for callers that want to derive additional artifacts
            (symbol extraction, slicing) from the same buffer without
            re-reading the file.
        file_path: Path to the source file. Used to populate
            :attr:`InterfaceSkeleton.file_path`.

    Returns:
        :class:`InterfaceSkeleton` describing the public API, or ``None`` if
        the tree has no root node.
    """
    del source_bytes  # Present for symmetry with extract_symbols_from_tree.

    root = tree.root_node
    if root is None:
        return None

    if root.has_error:
        logger.warning("Syntax errors detected in %s; extracting partial interface", file_path)

    functions: list[FunctionSig] = []
    classes: list[ClassSig] = []
    constants: list[ConstantSig] = []
    exports: list[str] = []

    for child in root.children:
        if child.type == "function_declaration":
            func = _extract_function_declaration(child)
            if func is not None:
                functions.append(func)

        elif child.type == "lexical_declaration":
            _extract_lexical_declaration(child, functions, constants)

        elif child.type == "class_declaration":
            cls = _extract_class_declaration(child)
            if cls is not None:
                classes.append(cls)

        elif child.type == "export_statement":
            _extract_export_statement(child, functions, classes, constants, exports)

        elif child.type == "expression_statement":
            _extract_commonjs_exports(child, exports)

    return InterfaceSkeleton(
        file_path=str(file_path),
        language="javascript",
        constants=constants,
        functions=functions,
        classes=classes,
        exports=exports,
    )


def extract_symbols(file_path: Path) -> SymbolExtract | None:
    """Extract symbol definitions and call sites from a JavaScript file."""
    parsed = parse_js_tree(file_path)
    if parsed is None:
        return None
    tree, source_bytes = parsed
    return extract_symbols_from_tree(tree, source_bytes, file_path)


def extract_symbols_from_tree(
    tree: Tree,
    source_bytes: bytes,
    file_path: Path,
) -> SymbolExtract | None:
    """Extract symbol definitions, call sites and class edges from a JS tree.

    Mirrors the TypeScript extractor: ``function_declaration``,
    ``class_declaration``, ``method_definition`` inside classes and
    ``lexical_declaration`` entries with an ``arrow_function`` value
    become :class:`SymbolDefinition` rows. ``call_expression`` descendants
    become :class:`CallSite` rows. ``this.method()`` is the JS analog of
    Python's ``self.method()`` — the receiver is the literal string
    ``"this"``.

    Class edges include ``inherits`` edges from every ``extends`` clause
    on a ``class_declaration`` and ``instantiates`` edges from every
    ``new_expression`` with a bare ``identifier`` constructor. JavaScript
    has no ``implements`` clause, so there is no interface fan-out.
    """
    del source_bytes  # Reserved for future walkers.

    root = tree.root_node
    if root is None:
        return None

    module_path = file_path.stem
    definitions: list[SymbolDefinition] = []
    def_nodes: list[tuple[object, SymbolDefinition]] = []

    for child in root.children:
        _collect_js_top_level_definitions(
            child,
            module_path,
            definitions,
            def_nodes,
        )

    calls = _collect_js_calls(def_nodes)
    class_edges = _collect_js_class_edges(def_nodes)

    return SymbolExtract(
        file_path=str(file_path),
        language="javascript",
        definitions=definitions,
        calls=calls,
        class_edges=class_edges,
    )


def _collect_js_top_level_definitions(
    node: object,
    module_path: str,
    definitions: list[SymbolDefinition],
    def_nodes: list[tuple[object, SymbolDefinition]],
) -> None:
    """Walk a top-level JS node and emit any function/class definitions."""
    node_type = getattr(node, "type", "")

    if node_type == "function_declaration":
        _emit_js_function(
            node,
            module_path,
            definitions,
            def_nodes,
            parent_class=None,
        )
    elif node_type == "class_declaration":
        _emit_js_class(
            node,
            module_path,
            definitions,
            def_nodes,
        )
    elif node_type == "lexical_declaration":
        _emit_js_lexical_declaration(
            node,
            module_path,
            definitions,
            def_nodes,
        )
    elif node_type == "export_statement":
        for child in getattr(node, "children", []):
            _collect_js_top_level_definitions(
                child,
                module_path,
                definitions,
                def_nodes,
            )


def _emit_js_function(
    node: object,
    qualified_prefix: str,
    definitions: list[SymbolDefinition],
    def_nodes: list[tuple[object, SymbolDefinition]],
    *,
    parent_class: str | None,
) -> None:
    """Emit a ``function_declaration`` node as a definition."""
    name_node = _sym_find_child_by_type(node, "identifier")
    if name_node is None:
        return
    name = _sym_node_text(name_node)
    if not name:
        return

    qualified_name = f"{qualified_prefix}.{name}" if qualified_prefix else name
    line_start, line_end = _line_range(node)
    definition = SymbolDefinition(
        name=name,
        qualified_name=qualified_name,
        symbol_type="function",
        line_start=line_start,
        line_end=line_end,
        visibility=_js_visibility(name),
        parent_class=parent_class,
    )
    definitions.append(definition)
    def_nodes.append((node, definition))


def _emit_js_class(
    node: object,
    qualified_prefix: str,
    definitions: list[SymbolDefinition],
    def_nodes: list[tuple[object, SymbolDefinition]],
) -> None:
    """Emit a ``class_declaration`` node along with its methods."""
    name_node = _sym_find_child_by_type(node, "identifier")
    if name_node is None:
        return
    name = _sym_node_text(name_node)
    if not name:
        return

    qualified_name = f"{qualified_prefix}.{name}" if qualified_prefix else name
    line_start, line_end = _line_range(node)
    class_def = SymbolDefinition(
        name=name,
        qualified_name=qualified_name,
        symbol_type="class",
        line_start=line_start,
        line_end=line_end,
        visibility=_js_visibility(name),
        parent_class=None,
    )
    definitions.append(class_def)
    def_nodes.append((node, class_def))

    class_prefix = qualified_name
    body = _sym_find_child_by_type(node, "class_body")
    if body is None:
        return
    for member in getattr(body, "children", []):
        if getattr(member, "type", "") == "method_definition":
            _emit_js_method(
                member,
                class_prefix,
                name,
                definitions,
                def_nodes,
            )


def _emit_js_method(
    node: object,
    class_prefix: str,
    parent_class: str,
    definitions: list[SymbolDefinition],
    def_nodes: list[tuple[object, SymbolDefinition]],
) -> None:
    """Emit a ``method_definition`` node as a definition."""
    name_node = _sym_find_child_by_type(node, "property_identifier")
    if name_node is None:
        return
    method_name = _sym_node_text(name_node)
    if not method_name:
        return

    qualified_name = f"{class_prefix}.{method_name}" if class_prefix else method_name
    line_start, line_end = _line_range(node)
    definition = SymbolDefinition(
        name=method_name,
        qualified_name=qualified_name,
        symbol_type="method",
        line_start=line_start,
        line_end=line_end,
        visibility=_js_visibility(method_name),
        parent_class=parent_class,
    )
    definitions.append(definition)
    def_nodes.append((node, definition))


def _emit_js_lexical_declaration(
    node: object,
    module_path: str,
    definitions: list[SymbolDefinition],
    def_nodes: list[tuple[object, SymbolDefinition]],
) -> None:
    """Emit ``const foo = () => ...`` as a function definition."""
    for child in getattr(node, "children", []):
        if getattr(child, "type", "") != "variable_declarator":
            continue
        name_node = _sym_find_child_by_type(child, "identifier")
        if name_node is None:
            continue
        name = _sym_node_text(name_node)
        if not name:
            continue
        arrow = _sym_find_child_by_type(child, "arrow_function")
        if arrow is None:
            continue

        line_start, line_end = _line_range(child)
        qualified_name = f"{module_path}.{name}" if module_path else name
        definition = SymbolDefinition(
            name=name,
            qualified_name=qualified_name,
            symbol_type="function",
            line_start=line_start,
            line_end=line_end,
            visibility=_js_visibility(name),
            parent_class=None,
        )
        definitions.append(definition)
        def_nodes.append((arrow, definition))


def _collect_js_calls(
    def_nodes: list[tuple[object, SymbolDefinition]],
) -> list[CallSite]:
    """Walk every definition body and emit :class:`CallSite` entries.

    Dedup uses ``(start_byte, end_byte)`` because tree-sitter-python
    returns fresh wrapper objects on every traversal.
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
        for call_node in _iter_js_call_descendants(def_node):
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

            call = _build_js_call_site(call_node, owner.qualified_name)
            if call is not None:
                calls.append(call)

    calls.sort(key=lambda c: (c.line, c.callee_name, c.caller_name))
    return calls


def _collect_js_class_edges(
    def_nodes: list[tuple[object, SymbolDefinition]],
) -> list[ClassEdgeSite]:
    """Emit ``ClassEdgeSite`` entries for JS definitions.

    JavaScript has only ``extends`` heritage (no ``implements``). Each
    ``class_declaration`` with a ``class_heritage`` child contributes one
    ``inherits`` edge per ``identifier`` or ``member_expression`` inside
    the heritage node. ``new_expression`` descendants with bare
    ``identifier`` constructors contribute ``instantiates`` edges.
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
        heritage_node = _sym_find_child_by_type(class_node, "class_heritage")
        if heritage_node is None:
            continue
        for base_name in _iter_js_heritage_names(heritage_node):
            edges.append(
                ClassEdgeSite(
                    source_name=class_def.qualified_name,
                    target_name=base_name,
                    edge_type="inherits",
                    line=class_def.line_start,
                ),
            )

    # ---- instantiates edges ----
    seen_new_keys: set[tuple[int, int]] = set()
    for def_node, _definition in def_nodes:
        for new_node in _iter_js_new_expression_descendants(def_node):
            key = _node_byte_key(new_node)
            if key in seen_new_keys:
                continue
            seen_new_keys.add(key)

            constructor_name = _js_bare_new_constructor(new_node)
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


def _iter_js_heritage_names(heritage_node: object) -> list[str]:
    """Return base-class names from a ``class_heritage`` node.

    Skips the ``extends`` keyword and any commas. ``identifier`` and
    ``member_expression`` entries are emitted verbatim.
    """
    names: list[str] = []
    for child in getattr(heritage_node, "children", []):
        child_type = getattr(child, "type", "")
        if child_type in ("identifier", "member_expression"):
            text = _sym_node_text(child)
            if text:
                names.append(text)
    return names


def _iter_js_new_expression_descendants(node: object) -> list[object]:
    """Return every ``new_expression`` descendant of ``node``."""
    results: list[object] = []
    stack: list[object] = list(getattr(node, "children", []))
    while stack:
        current = stack.pop(0)
        if getattr(current, "type", "") == "new_expression":
            results.append(current)
        stack = list(getattr(current, "children", [])) + stack
    return results


def _js_bare_new_constructor(new_node: object) -> str | None:
    """Return the bare constructor name of a ``new_expression``, or ``None``.

    Only bare ``identifier`` constructors are returned.
    ``new mod.Foo()`` (a ``member_expression`` constructor) and chained
    expressions return ``None`` — Phase 3 resolution only handles bare
    names.
    """
    getter = getattr(new_node, "child_by_field_name", None)
    constructor_node: object | None = None
    if getter is not None:
        constructor_node = cast("object | None", getter("constructor"))
    if constructor_node is None:
        for child in getattr(new_node, "children", []):
            child_type = getattr(child, "type", "")
            if child_type in ("new", "arguments"):
                continue
            constructor_node = child
            break
    if constructor_node is None:
        return None
    if getattr(constructor_node, "type", "") != "identifier":
        return None
    text = _sym_node_text(constructor_node)
    return text or None


def _node_byte_key(node: object) -> tuple[int, int]:
    """Return ``(start_byte, end_byte)`` for tree-sitter dedup."""
    start = getattr(node, "start_byte", -1)
    end = getattr(node, "end_byte", -1)
    return int(start), int(end)


def _sym_find_child_by_type(node: object, type_name: str) -> object | None:
    """Return the first direct child of ``node`` with the given type.

    Mirrors :func:`_find_child_by_type` but accepts an ``object`` so the
    symbol-extractor helpers (which are independent of tree-sitter's
    ``Node`` TYPE_CHECKING import) can use it without mypy errors.
    """
    for child in getattr(node, "children", []):
        if getattr(child, "type", "") == type_name:
            return cast("object", child)
    return None


def _sym_node_text(node: object) -> str:
    """Safely decode a tree-sitter node's text, returning ``""`` on None."""
    text = getattr(node, "text", None)
    if text is None:
        return ""
    if isinstance(text, bytes):
        return text.decode("utf-8", errors="replace")
    return str(text)


def _iter_js_call_descendants(node: object) -> list[object]:
    """Return every ``call_expression`` descendant of ``node``."""
    results: list[object] = []
    stack: list[object] = list(getattr(node, "children", []))
    while stack:
        current = stack.pop(0)
        if getattr(current, "type", "") == "call_expression":
            results.append(current)
        stack = list(getattr(current, "children", [])) + stack
    return results


def _build_js_call_site(
    call_node: object,
    caller_qualified_name: str,
) -> CallSite | None:
    """Translate a ``call_expression`` into a :class:`CallSite`."""
    func_node = _js_call_function_child(call_node)
    if func_node is None:
        return None

    line = _node_row_span(call_node)[0] + 1
    func_type = getattr(func_node, "type", "")

    if func_type == "identifier":
        callee_name = _sym_node_text(func_node)
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
        prop_name = _sym_node_text(prop_node)
        if not prop_name:
            return None
        receiver, display = _js_member_receiver(obj_node)
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


def _js_call_function_child(call_node: object) -> object | None:
    """Return the function/callee subtree of a ``call_expression``."""
    getter = getattr(call_node, "child_by_field_name", None)
    if getter is not None:
        result: object | None = getter("function")
        if result is not None:
            return result
    for child in getattr(call_node, "children", []):
        child_type = getattr(child, "type", "")
        if child_type in ("(", "arguments", ","):
            continue
        return cast("object", child)
    return None


def _js_member_receiver(
    obj_node: object | None,
) -> tuple[str | None, str]:
    """Derive the receiver text for a member-expression callee."""
    if obj_node is None:
        return None, ""
    obj_type = getattr(obj_node, "type", "")

    if obj_type == "call_expression":
        inner_func = _js_call_function_child(obj_node)
        if inner_func is not None and getattr(inner_func, "type", "") == "identifier":
            inner_name = _sym_node_text(inner_func)
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

    text = _sym_node_text(obj_node)
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


def _js_visibility(name: str) -> str:
    """JS visibility rule: names starting with ``_`` are private."""
    return "private" if name.startswith("_") else "public"


def _extract_function_declaration(node: Node) -> FunctionSig | None:
    """Extract a FunctionSig from a function_declaration node."""
    name_node = _find_child_by_type(node, "identifier")
    if name_node is None:
        return None

    name = _node_text(name_node)
    is_async = _has_child_type(node, "async")
    params = _extract_parameters(node)

    return FunctionSig(
        name=name,
        parameters=params,
        return_type=None,
        is_async=is_async,
    )


def _extract_lexical_declaration(
    node: Node,
    functions: list[FunctionSig],
    constants: list[ConstantSig],
) -> None:
    """Extract functions or constants from a lexical_declaration (const/let).

    Arrow functions assigned to const are extracted as FunctionSig.
    Other const declarations are extracted as ConstantSig.
    """
    is_const = _has_child_type(node, "const")
    if not is_const:
        return

    for child in node.children:
        if child.type == "variable_declarator":
            _extract_variable_declarator(child, functions, constants)


def _extract_variable_declarator(
    node: Node,
    functions: list[FunctionSig],
    constants: list[ConstantSig],
) -> None:
    """Extract a single variable declarator: arrow function or constant."""
    name_node = _find_child_by_type(node, "identifier")
    if name_node is None:
        return

    name = _node_text(name_node)

    # Check if the value is an arrow function
    value_node = _find_child_by_type(node, "arrow_function")
    if value_node is not None:
        is_async = _has_child_type(value_node, "async")
        params = _extract_parameters(value_node)
        functions.append(
            FunctionSig(
                name=name,
                parameters=params,
                return_type=None,
                is_async=is_async,
            )
        )
        return

    # Check if the value is a regular function expression
    value_node = _find_child_by_type(node, "function_expression")
    if value_node is not None:
        is_async = _has_child_type(value_node, "async")
        params = _extract_parameters(value_node)
        functions.append(
            FunctionSig(
                name=name,
                parameters=params,
                return_type=None,
                is_async=is_async,
            )
        )
        return

    # Otherwise it is a plain constant
    constants.append(ConstantSig(name=name, type_annotation=None))


def _extract_class_declaration(node: Node) -> ClassSig | None:
    """Extract a ClassSig from a class_declaration node."""
    name_node = _find_child_by_type(node, "identifier")
    if name_node is None:
        return None

    name = _node_text(name_node)
    bases = _extract_class_bases(node)
    methods = _extract_class_methods(node)

    return ClassSig(
        name=name,
        bases=bases,
        methods=methods,
    )


def _extract_class_bases(node: Node) -> list[str]:
    """Extract base class names from a class_heritage node."""
    heritage = _find_child_by_type(node, "class_heritage")
    if heritage is None:
        return []

    bases: list[str] = []
    for child in heritage.children:
        if child.type in ("identifier", "member_expression"):
            bases.append(_node_text(child))
    return bases


def _extract_class_methods(node: Node) -> list[FunctionSig]:
    """Extract method signatures from a class body."""
    body = _find_child_by_type(node, "class_body")
    if body is None:
        return []

    methods: list[FunctionSig] = []
    for child in body.children:
        if child.type == "method_definition":
            method = _extract_method_definition(child)
            if method is not None:
                methods.append(method)
    return methods


def _extract_method_definition(node: Node) -> FunctionSig | None:
    """Extract a FunctionSig from a method_definition node."""
    name_node = _find_child_by_type(node, "property_identifier")
    if name_node is None:
        return None

    name = _node_text(name_node)
    is_async = _has_child_type(node, "async")
    is_static = _has_child_type(node, "static")
    is_property = _has_child_type(node, "get") or _has_child_type(node, "set")
    params = _extract_parameters(node)

    return FunctionSig(
        name=name,
        parameters=params,
        return_type=None,
        is_async=is_async,
        is_method=True,
        is_static=is_static,
        is_property=is_property,
    )


def _extract_export_statement(
    node: Node,
    functions: list[FunctionSig],
    classes: list[ClassSig],
    constants: list[ConstantSig],
    exports: list[str],
) -> None:
    """Extract declarations and export names from an export_statement node."""
    is_default = _has_child_type(node, "default")

    for child in node.children:
        if child.type == "function_declaration":
            func = _extract_function_declaration(child)
            if func is not None:
                functions.append(func)
                exports.append(func.name)

        elif child.type == "function_expression":
            # export default function() {} -- anonymous default export
            if is_default:
                # Extract as a function but with no name to add to exports
                pass

        elif child.type == "class_declaration":
            cls = _extract_class_declaration(child)
            if cls is not None:
                classes.append(cls)
                exports.append(cls.name)

        elif child.type == "lexical_declaration":
            _extract_exported_lexical(child, functions, constants, exports)

        elif child.type == "export_clause":
            _extract_export_clause(child, exports)

        elif child.type == "identifier" and is_default:
            # export default SomeName;
            exports.append(_node_text(child))


def _extract_exported_lexical(
    node: Node,
    functions: list[FunctionSig],
    constants: list[ConstantSig],
    exports: list[str],
) -> None:
    """Handle `export const ...` declarations."""
    for child in node.children:
        if child.type == "variable_declarator":
            name_node = _find_child_by_type(child, "identifier")
            if name_node is None:
                continue
            name = _node_text(name_node)

            arrow = _find_child_by_type(child, "arrow_function")
            func_expr = _find_child_by_type(child, "function_expression")

            if arrow is not None:
                is_async = _has_child_type(arrow, "async")
                params = _extract_parameters(arrow)
                functions.append(
                    FunctionSig(
                        name=name,
                        parameters=params,
                        return_type=None,
                        is_async=is_async,
                    )
                )
            elif func_expr is not None:
                is_async = _has_child_type(func_expr, "async")
                params = _extract_parameters(func_expr)
                functions.append(
                    FunctionSig(
                        name=name,
                        parameters=params,
                        return_type=None,
                        is_async=is_async,
                    )
                )
            else:
                constants.append(ConstantSig(name=name, type_annotation=None))

            exports.append(name)


def _extract_export_clause(node: Node, exports: list[str]) -> None:
    """Extract names from an export_clause: export { foo, bar }."""
    for child in node.children:
        if child.type == "export_specifier":
            # Use the local name (first identifier), not the alias
            name_node = _find_child_by_type(child, "identifier")
            if name_node is not None:
                exports.append(_node_text(name_node))


def _extract_commonjs_exports(node: Node, exports: list[str]) -> None:
    """Extract export names from CommonJS module.exports patterns.

    Handles:
      - module.exports = { foo, bar }
      - module.exports = ClassName
      - module.exports.name = value
      - exports.name = value
    """
    if node.type != "expression_statement":
        return

    assign = _find_child_by_type(node, "assignment_expression")
    if assign is None:
        return

    left = assign.children[0] if assign.child_count > 0 else None
    right = assign.children[-1] if assign.child_count > 1 else None

    if left is None or right is None:
        return

    if left.type == "member_expression":
        left_text = _node_text(left)

        if left_text == "module.exports":
            # module.exports = { foo, bar } or module.exports = SomeName
            if right.type == "object":
                for child in right.children:
                    if child.type == "shorthand_property_identifier":
                        exports.append(_node_text(child))
                    elif child.type == "pair":
                        key = child.children[0] if child.child_count > 0 else None
                        if key is not None and key.type in (
                            "property_identifier",
                            "string",
                        ):
                            exports.append(_node_text(key).strip("'\""))
            elif right.type == "identifier":
                exports.append(_node_text(right))

        elif left_text.startswith("module.exports."):
            # module.exports.name = value
            prop = _find_last_property_identifier(left)
            if prop is not None:
                exports.append(prop)

        elif left_text.startswith("exports.") and not left_text.startswith("exports.__"):
            # exports.name = value
            prop = _find_last_property_identifier(left)
            if prop is not None:
                exports.append(prop)


def _extract_parameters(node: Node) -> list[ParameterSig]:
    """Extract parameter list from a node containing formal_parameters."""
    params_node = _find_child_by_type(node, "formal_parameters")
    if params_node is None:
        return []

    params: list[ParameterSig] = []
    for child in params_node.children:
        if child.type == "identifier":
            params.append(ParameterSig(name=_node_text(child)))
        elif child.type == "assignment_pattern":
            # Parameter with a default value
            name_node = _find_child_by_type(child, "identifier")
            if name_node is not None:
                # Extract default value (everything after the =)
                default_val = None
                found_eq = False
                for sub in child.children:
                    if sub.type == "=":
                        found_eq = True
                    elif found_eq:
                        default_val = _node_text(sub)
                        break
                params.append(
                    ParameterSig(
                        name=_node_text(name_node),
                        default=default_val,
                    )
                )
        elif child.type == "rest_pattern":
            # ...args
            name_node = _find_child_by_type(child, "identifier")
            if name_node is not None:
                params.append(ParameterSig(name=f"...{_node_text(name_node)}"))
        elif child.type == "object_pattern":
            # Destructured parameter { a, b }
            params.append(ParameterSig(name=_node_text(child)))
        elif child.type == "array_pattern":
            # Destructured parameter [a, b]
            params.append(ParameterSig(name=_node_text(child)))
    return params


# ── Helpers ──────────────────────────────────────────────────────────────────


def _node_text(node: Node) -> str:
    """Safely decode node text, returning empty string if text is None."""
    if node.text is None:
        return ""
    return node.text.decode()


def _find_child_by_type(node: Node, type_name: str) -> Node | None:
    """Return the first direct child with the given type, or None."""
    for child in node.children:
        if child.type == type_name:
            return child
    return None


def _has_child_type(node: Node, type_name: str) -> bool:
    """Return True if the node has a direct child of the given type."""
    return _find_child_by_type(node, type_name) is not None


def _find_last_property_identifier(node: Node) -> str | None:
    """Find the last property_identifier in a member_expression chain."""
    for child in reversed(node.children):
        if child.type == "property_identifier":
            return _node_text(child)
    return None
