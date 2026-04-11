"""Pydantic models for AST-based interface extraction."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

_ALLOWED_SYMBOL_TYPES = frozenset({"function", "method", "class", "enum", "constant"})
_ALLOWED_VISIBILITIES = frozenset({"public", "private"})


class ParameterSig(BaseModel):
    """Represents a function/method parameter signature."""

    name: str
    type_annotation: str | None = None
    default: str | None = None


class ConstantSig(BaseModel):
    """Represents a module-level constant or exported variable."""

    name: str
    type_annotation: str | None = None


class EnumMemberSig(BaseModel):
    """Represents a single member of an enum definition.

    Emitted by the Python and TypeScript parsers alongside the enum's
    ``SymbolDefinition``. ``value`` holds the source text of the member's
    RHS literal (for example ``'"pending"'`` for a StrEnum member or
    ``"10"`` for an IntEnum member). ``value`` is ``None`` when the RHS
    is a call like ``auto()`` or otherwise not a simple literal.
    ``ordinal`` is the zero-based position of the member within the enum
    body as it appears in source.
    """

    name: str
    value: str | None = None
    ordinal: int


class ConstantValue(BaseModel):
    """Represents a module-level constant assignment with a literal RHS.

    Emitted by the Python, TypeScript, and JavaScript parsers alongside
    the constant's ``SymbolDefinition``. ``value`` holds the source text
    of the RHS literal (for example ``'"myapp"'`` or ``"30.0"``).
    ``value`` is ``None`` when the RHS is not a simple literal (and the
    constant should not be recorded in ``symbol_members``). ``line`` is
    the 1-based line number of the assignment. ``type_annotation`` holds
    the source text of the type annotation if present, otherwise
    ``None``.
    """

    name: str
    value: str | None = None
    line: int
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


class CallSite(BaseModel):
    """A call emitted from a caller symbol.

    ``callee_name`` is the raw textual name as it appears in source (before
    resolution). ``receiver`` is the object/class the call is being made on,
    or ``None`` for free-function calls. For ``self.foo()`` calls
    ``receiver == "self"``; for ``ConceptIndex.find()``,
    ``receiver == "ConceptIndex"``; for ``super().foo()``,
    ``receiver == "super"`` and ``callee_name == "super.foo"``.
    """

    caller_name: str
    callee_name: str
    receiver: str | None = None
    line: int
    is_method_call: bool = False


class ClassEdgeSite(BaseModel):
    """A class-level edge emitted from a source file's parse tree.

    Represents either an ``inherits`` edge (class A extends/implements class
    B) or an ``instantiates`` edge (somewhere in A's body, B is constructed).
    ``source_name`` is the qualified name of the class or enclosing symbol
    that owns the edge; ``target_name`` is the raw textual name of the base
    class or instantiated class before resolution.

    The edge is the AST-level ancestor of a row in the ``class_edges`` or
    ``class_edges_unresolved`` table of ``.lexibrary/symbols.db`` — the
    symbol-graph builder's pass 3 resolves ``target_name`` to a
    ``symbols.id`` and persists the result.
    """

    source_name: str
    target_name: str
    edge_type: str
    line: int


class SymbolDefinition(BaseModel):
    """A function, method, or class definition location inside a file.

    ``qualified_name`` format rule: the fully-qualified module path ALWAYS
    includes the top-level package. Examples:

    - Function: ``lexibrary.archivist.pipeline.update_project``
    - Method: ``lexibrary.archivist.pipeline.Builder.full_build``
    - Nested: ``lexibrary.archivist.pipeline.update_project.<locals>._scan_files``

    Nested functions and inner classes are captured as ``SymbolDefinition``
    rows with ``visibility="private"`` (for accurate call attribution in the
    symbol graph). The interface skeleton extractor continues to hide nested
    definitions — only the symbol extractor surfaces them.
    """

    name: str
    qualified_name: str
    symbol_type: str
    line_start: int
    line_end: int
    visibility: str
    parent_class: str | None = None

    @field_validator("symbol_type")
    @classmethod
    def _validate_symbol_type(cls, value: str) -> str:
        if value not in _ALLOWED_SYMBOL_TYPES:
            msg = f"symbol_type must be one of {sorted(_ALLOWED_SYMBOL_TYPES)}; got {value!r}"
            raise ValueError(msg)
        return value

    @field_validator("visibility")
    @classmethod
    def _validate_visibility(cls, value: str) -> str:
        if value not in _ALLOWED_VISIBILITIES:
            msg = f"visibility must be one of {sorted(_ALLOWED_VISIBILITIES)}; got {value!r}"
            raise ValueError(msg)
        return value


class SymbolExtract(BaseModel):
    """Everything the symbol graph needs from a single file.

    Call extraction and class-edge extraction run off the same parse tree
    and share this container. ``class_edges`` records ``inherits`` and
    ``instantiates`` edges emitted by the parsers; the symbol-graph builder
    resolves them against known symbols in pass 3. ``enums`` maps each
    enum's qualified name to its list of member signatures, and
    ``constants`` holds module-level constant assignments with literal
    RHS values — both are emitted alongside ``definitions`` and consumed
    by the builder to populate ``symbol_members`` rows.
    """

    file_path: str
    language: str
    definitions: list[SymbolDefinition] = Field(default_factory=list)
    calls: list[CallSite] = Field(default_factory=list)
    class_edges: list[ClassEdgeSite] = Field(default_factory=list)
    enums: list[tuple[str, list[EnumMemberSig]]] = Field(default_factory=list)
    constants: list[ConstantValue] = Field(default_factory=list)
