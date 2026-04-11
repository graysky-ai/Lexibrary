"""Tests for AST parser Pydantic models."""

from __future__ import annotations

import pytest

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


class TestParameterSig:
    """Tests for ParameterSig model."""

    def test_parameter_with_all_fields(self) -> None:
        param = ParameterSig(name="timeout", type_annotation="float", default="30.0")
        assert param.name == "timeout"
        assert param.type_annotation == "float"
        assert param.default == "30.0"

    def test_parameter_with_name_only(self) -> None:
        param = ParameterSig(name="args")
        assert param.name == "args"
        assert param.type_annotation is None
        assert param.default is None

    def test_parameter_model_dump(self) -> None:
        param = ParameterSig(name="x", type_annotation="int", default="0")
        dumped = param.model_dump()
        assert set(dumped.keys()) == {"name", "type_annotation", "default"}
        assert dumped["name"] == "x"


class TestConstantSig:
    """Tests for ConstantSig model."""

    def test_constant_with_type(self) -> None:
        const = ConstantSig(name="MAX_RETRIES", type_annotation="int")
        assert const.name == "MAX_RETRIES"
        assert const.type_annotation == "int"

    def test_constant_without_type(self) -> None:
        const = ConstantSig(name="DEFAULT_TIMEOUT")
        assert const.name == "DEFAULT_TIMEOUT"
        assert const.type_annotation is None


class TestFunctionSig:
    """Tests for FunctionSig model."""

    def test_simple_function(self) -> None:
        func = FunctionSig(name="process")
        assert func.name == "process"
        assert func.parameters == []
        assert func.return_type is None
        assert func.is_async is False
        assert func.is_method is False
        assert func.is_static is False
        assert func.is_class_method is False
        assert func.is_property is False

    def test_async_method_with_parameters(self) -> None:
        func = FunctionSig(
            name="fetch",
            is_async=True,
            is_method=True,
            parameters=[
                ParameterSig(name="self"),
                ParameterSig(name="url", type_annotation="str"),
            ],
            return_type="Response",
        )
        assert func.is_async is True
        assert func.is_method is True
        assert len(func.parameters) == 2
        assert func.return_type == "Response"

    def test_static_method(self) -> None:
        func = FunctionSig(name="create", is_static=True, is_method=True)
        assert func.is_static is True
        assert func.is_method is True

    def test_class_method(self) -> None:
        func = FunctionSig(name="from_dict", is_class_method=True, is_method=True)
        assert func.is_class_method is True

    def test_property(self) -> None:
        func = FunctionSig(name="value", is_property=True, is_method=True)
        assert func.is_property is True


class TestClassSig:
    """Tests for ClassSig model."""

    def test_class_with_bases_and_methods(self) -> None:
        cls = ClassSig(
            name="AuthService",
            bases=["BaseService"],
            methods=[FunctionSig(name="login", is_method=True)],
        )
        assert cls.name == "AuthService"
        assert cls.bases == ["BaseService"]
        assert len(cls.methods) == 1
        assert cls.methods[0].name == "login"

    def test_empty_class(self) -> None:
        cls = ClassSig(name="EmptyMixin")
        assert cls.name == "EmptyMixin"
        assert cls.bases == []
        assert cls.methods == []
        assert cls.class_variables == []

    def test_class_with_class_variables(self) -> None:
        cls = ClassSig(
            name="Config",
            class_variables=[ConstantSig(name="DEBUG", type_annotation="bool")],
        )
        assert len(cls.class_variables) == 1
        assert cls.class_variables[0].name == "DEBUG"


class TestInterfaceSkeleton:
    """Tests for InterfaceSkeleton model."""

    def test_complete_skeleton(self) -> None:
        skeleton = InterfaceSkeleton(
            file_path="src/auth.py",
            language="python",
            constants=[ConstantSig(name="VERSION", type_annotation="str")],
            functions=[FunctionSig(name="authenticate")],
            classes=[ClassSig(name="AuthService")],
            exports=["authenticate", "AuthService"],
        )
        assert skeleton.file_path == "src/auth.py"
        assert skeleton.language == "python"
        assert len(skeleton.constants) == 1
        assert len(skeleton.functions) == 1
        assert len(skeleton.classes) == 1
        assert len(skeleton.exports) == 2

    def test_empty_skeleton(self) -> None:
        skeleton = InterfaceSkeleton(file_path="empty.py", language="python")
        assert skeleton.constants == []
        assert skeleton.functions == []
        assert skeleton.classes == []
        assert skeleton.exports == []


class TestClassEdgeSite:
    """Tests for ClassEdgeSite model."""

    def test_inherits_edge(self) -> None:
        edge = ClassEdgeSite(
            source_name="pkg.derived.Derived",
            target_name="Base",
            edge_type="inherits",
            line=3,
        )
        assert edge.source_name == "pkg.derived.Derived"
        assert edge.target_name == "Base"
        assert edge.edge_type == "inherits"
        assert edge.line == 3

    def test_instantiates_edge(self) -> None:
        edge = ClassEdgeSite(
            source_name="pkg.users.main",
            target_name="Derived",
            edge_type="instantiates",
            line=12,
        )
        assert edge.edge_type == "instantiates"
        assert edge.target_name == "Derived"

    def test_requires_all_fields(self) -> None:
        with pytest.raises(ValueError):
            ClassEdgeSite(  # type: ignore[call-arg]
                source_name="A",
                target_name="B",
                edge_type="inherits",
            )

    def test_model_dump_round_trip(self) -> None:
        edge = ClassEdgeSite(
            source_name="pkg.mod.Cls",
            target_name="BaseCls",
            edge_type="inherits",
            line=7,
        )
        dumped = edge.model_dump()
        assert dumped == {
            "source_name": "pkg.mod.Cls",
            "target_name": "BaseCls",
            "edge_type": "inherits",
            "line": 7,
        }
        restored = ClassEdgeSite.model_validate(dumped)
        assert restored == edge


class TestSymbolExtract:
    """Tests for the SymbolExtract container."""

    def test_empty_symbol_extract(self) -> None:
        extract = SymbolExtract(file_path="src/empty.py", language="python")
        assert extract.file_path == "src/empty.py"
        assert extract.language == "python"
        assert extract.definitions == []
        assert extract.calls == []
        assert extract.class_edges == []

    def test_symbol_extract_defaults_class_edges_to_empty_list(self) -> None:
        extract = SymbolExtract(
            file_path="src/mod.py",
            language="python",
            definitions=[
                SymbolDefinition(
                    name="foo",
                    qualified_name="pkg.mod.foo",
                    symbol_type="function",
                    line_start=1,
                    line_end=2,
                    visibility="public",
                )
            ],
            calls=[
                CallSite(caller_name="pkg.mod.foo", callee_name="bar", line=2),
            ],
        )
        assert extract.class_edges == []
        assert len(extract.definitions) == 1
        assert len(extract.calls) == 1

    def test_symbol_extract_round_trip_with_class_edges(self) -> None:
        extract = SymbolExtract(
            file_path="src/pkg/derived.py",
            language="python",
            definitions=[
                SymbolDefinition(
                    name="Derived",
                    qualified_name="pkg.derived.Derived",
                    symbol_type="class",
                    line_start=3,
                    line_end=5,
                    visibility="public",
                ),
            ],
            calls=[],
            class_edges=[
                ClassEdgeSite(
                    source_name="pkg.derived.Derived",
                    target_name="Base",
                    edge_type="inherits",
                    line=3,
                ),
                ClassEdgeSite(
                    source_name="pkg.derived.main",
                    target_name="Derived",
                    edge_type="instantiates",
                    line=8,
                ),
            ],
        )
        dumped = extract.model_dump()
        assert len(dumped["class_edges"]) == 2
        restored = SymbolExtract.model_validate(dumped)
        assert restored == extract
        assert restored.class_edges[0].edge_type == "inherits"
        assert restored.class_edges[1].edge_type == "instantiates"
