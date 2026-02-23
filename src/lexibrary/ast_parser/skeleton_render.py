"""Deterministic canonical renderer for InterfaceSkeleton models."""

from __future__ import annotations

from lexibrary.ast_parser.models import (
    ClassSig,
    ConstantSig,
    FunctionSig,
    InterfaceSkeleton,
    ParameterSig,
)

VERSION_PREFIX = "skeleton:v1"


def render_skeleton(skeleton: InterfaceSkeleton) -> str:
    """Render an InterfaceSkeleton into a deterministic canonical text string.

    The output is suitable for hashing. The same skeleton always produces
    byte-identical output regardless of declaration order in the source.

    All lists are sorted alphabetically by name before rendering.
    Sections appear in fixed order: constants, functions, classes, exports.

    Args:
        skeleton: The interface skeleton to render.

    Returns:
        Canonical text string prefixed with version identifier.
    """
    lines: list[str] = [VERSION_PREFIX]

    # Constants (sorted by name)
    for const in sorted(skeleton.constants, key=lambda c: c.name):
        lines.append(_render_constant(const))

    # Functions (sorted by name)
    for func in sorted(skeleton.functions, key=lambda f: f.name):
        lines.append(_render_function(func))

    # Classes (sorted by name)
    for cls in sorted(skeleton.classes, key=lambda c: c.name):
        lines.extend(_render_class(cls))

    # Exports (sorted alphabetically)
    for export in sorted(skeleton.exports):
        lines.append(f"export:{export}")

    return "\n".join(lines) + "\n"


def _render_constant(const: ConstantSig) -> str:
    """Render a constant signature to a compact line."""
    if const.type_annotation is not None:
        return f"const:{const.name}:{const.type_annotation}"
    return f"const:{const.name}"


def _render_parameter(param: ParameterSig) -> str:
    """Render a parameter signature to compact format."""
    parts = param.name
    if param.type_annotation is not None:
        parts += f":{param.type_annotation}"
    if param.default is not None:
        parts += f"={param.default}"
    return parts


def _render_function(func: FunctionSig, indent: str = "") -> str:
    """Render a function/method signature to a compact line."""
    modifiers: list[str] = []
    if func.is_async:
        modifiers.append("async")
    if func.is_static:
        modifiers.append("static")
    if func.is_class_method:
        modifiers.append("classmethod")
    if func.is_property:
        modifiers.append("property")

    prefix = "func"
    if modifiers:
        prefix = ",".join(modifiers) + " func"

    params = ",".join(_render_parameter(p) for p in func.parameters)
    result = f"{indent}{prefix}:{func.name}({params})"

    if func.return_type is not None:
        result += f"->{func.return_type}"

    return result


def _render_class(cls: ClassSig) -> list[str]:
    """Render a class signature to compact lines (header + indented members)."""
    lines: list[str] = []

    # Class header with bases
    if cls.bases:
        bases_str = ",".join(cls.bases)
        lines.append(f"class:{cls.name}({bases_str})")
    else:
        lines.append(f"class:{cls.name}")

    # Class variables (sorted by name)
    for var in sorted(cls.class_variables, key=lambda v: v.name):
        lines.append(f"  {_render_constant(var)}")

    # Methods (sorted by name)
    for method in sorted(cls.methods, key=lambda m: m.name):
        lines.append(_render_function(method, indent="  "))

    return lines
