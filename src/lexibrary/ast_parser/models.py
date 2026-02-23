"""Pydantic models for AST-based interface extraction."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ParameterSig(BaseModel):
    """Represents a function/method parameter signature."""

    name: str
    type_annotation: str | None = None
    default: str | None = None


class ConstantSig(BaseModel):
    """Represents a module-level constant or exported variable."""

    name: str
    type_annotation: str | None = None


class FunctionSig(BaseModel):
    """Represents a function or method signature."""

    name: str
    parameters: list[ParameterSig] = Field(default_factory=list)
    return_type: str | None = None
    is_async: bool = False
    is_method: bool = False
    is_static: bool = False
    is_class_method: bool = False
    is_property: bool = False


class ClassSig(BaseModel):
    """Represents a class signature."""

    name: str
    bases: list[str] = Field(default_factory=list)
    methods: list[FunctionSig] = Field(default_factory=list)
    class_variables: list[ConstantSig] = Field(default_factory=list)


class InterfaceSkeleton(BaseModel):
    """Represents the complete public interface of a source file."""

    file_path: str
    language: str
    constants: list[ConstantSig] = Field(default_factory=list)
    functions: list[FunctionSig] = Field(default_factory=list)
    classes: list[ClassSig] = Field(default_factory=list)
    exports: list[str] = Field(default_factory=list)
