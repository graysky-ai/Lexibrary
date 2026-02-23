"""Python interface extraction using tree-sitter.

Extracts public interface skeletons from Python source files, including:
- Top-level functions (excluding private names except __init__/__new__)
- Class definitions with public methods and class variables
- Module-level constants (UPPER_CASE or type-annotated)
- __all__ exports (literal list/tuple only)

Handles syntax errors gracefully by extracting whatever tree-sitter can parse.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import cast

from lexibrary.ast_parser.models import (
    ClassSig,
    ConstantSig,
    FunctionSig,
    InterfaceSkeleton,
    ParameterSig,
)
from lexibrary.ast_parser.registry import get_parser

logger = logging.getLogger(__name__)

# Names that start with _ are private, except these dunder methods
_ALLOWED_DUNDER_METHODS = frozenset({"__init__", "__new__"})

# Pattern matching UPPER_CASE names (module-level constants)
_UPPER_CASE_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def extract_interface(file_path: Path) -> InterfaceSkeleton | None:
    """Extract the public interface from a Python source file.

    Returns None if the Python grammar is not available or the file
    cannot be read. Returns a partial skeleton if the file has syntax errors.

    Args:
        file_path: Path to the Python source file.

    Returns:
        InterfaceSkeleton with the file's public interface, or None.
    """
    parser = get_parser(file_path.suffix)
    if parser is None:
        return None

    try:
        source = file_path.read_bytes()
    except OSError:
        logger.warning("Cannot read file: %s", file_path)
        return None

    tree = parser.parse(source)
    root = tree.root_node

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


def _is_public_name(name: str) -> bool:
    """Check if a name should be included in the public interface.

    Private names (starting with _) are excluded, except __init__ and __new__.
    """
    if not name.startswith("_"):
        return True
    return name in _ALLOWED_DUNDER_METHODS


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
    """Check if a method name should be included in the class interface."""
    if not name.startswith("_"):
        return True
    return name in _ALLOWED_DUNDER_METHODS


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
