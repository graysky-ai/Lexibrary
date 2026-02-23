"""TypeScript/TSX parser: extracts public interface skeletons using tree-sitter.

Supports .ts and .tsx files. Uses the TypeScript sub-grammar for .ts files
and the TSX sub-grammar for .tsx files (both from tree-sitter-typescript).

Extracts: functions, classes, interfaces, type aliases, enums, constants,
and export declarations. Function bodies and JSX elements are ignored.
"""

from __future__ import annotations

import logging
from pathlib import Path

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
    """Extract the public interface skeleton from a TypeScript or TSX file.

    Args:
        file_path: Path to a .ts or .tsx source file.

    Returns:
        InterfaceSkeleton with extracted interface, or None if the file
        cannot be parsed (unsupported extension, missing grammar, read error).
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
    root = tree.root_node

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
