"""JavaScript/JSX parser: extract public interface using tree-sitter.

Handles function declarations, arrow functions assigned to const,
class declarations, ES module exports, and CommonJS module.exports.
JavaScript has no native type annotations, so all type fields are None.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tree_sitter import Node

from lexibrary.ast_parser.models import (
    ClassSig,
    ConstantSig,
    FunctionSig,
    InterfaceSkeleton,
    ParameterSig,
)
from lexibrary.ast_parser.registry import get_parser

logger = logging.getLogger(__name__)


def extract_interface(file_path: Path) -> InterfaceSkeleton | None:
    """Extract the public interface from a JavaScript or JSX file.

    Args:
        file_path: Path to the .js or .jsx file.

    Returns:
        InterfaceSkeleton with extracted signatures, or None if the file
        cannot be parsed.
    """
    extension = file_path.suffix
    parser = get_parser(extension)
    if parser is None:
        return None

    try:
        source = file_path.read_bytes()
    except OSError:
        logger.exception("Failed to read file: %s", file_path)
        return None

    tree = parser.parse(source)
    root = tree.root_node

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
