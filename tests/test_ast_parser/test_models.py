"""Tests for AST parser Pydantic models."""

from __future__ import annotations

from lexibrary.ast_parser.models import (
    ClassSig,
    ConstantSig,
    FunctionSig,
    InterfaceSkeleton,
    ParameterSig,
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
