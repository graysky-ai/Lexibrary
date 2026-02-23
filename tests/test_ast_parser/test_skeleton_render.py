"""Tests for the deterministic skeleton renderer."""

from __future__ import annotations

from lexibrary.ast_parser.models import (
    ClassSig,
    ConstantSig,
    FunctionSig,
    InterfaceSkeleton,
    ParameterSig,
)
from lexibrary.ast_parser.skeleton_render import render_skeleton


class TestVersionPrefix:
    """Tests for version prefix in rendered output."""

    def test_output_starts_with_version_prefix(self) -> None:
        skeleton = InterfaceSkeleton(file_path="test.py", language="python")
        result = render_skeleton(skeleton)
        assert result.startswith("skeleton:v1\n")

    def test_empty_skeleton_is_version_prefix_only(self) -> None:
        skeleton = InterfaceSkeleton(file_path="empty.py", language="python")
        result = render_skeleton(skeleton)
        assert result == "skeleton:v1\n"


class TestDeterminism:
    """Tests for deterministic rendering."""

    def test_same_skeleton_produces_same_output(self) -> None:
        skeleton = InterfaceSkeleton(
            file_path="test.py",
            language="python",
            functions=[
                FunctionSig(name="alpha"),
                FunctionSig(name="beta"),
            ],
        )
        assert render_skeleton(skeleton) == render_skeleton(skeleton)

    def test_reordered_functions_produce_same_output(self) -> None:
        skeleton_a = InterfaceSkeleton(
            file_path="test.py",
            language="python",
            functions=[
                FunctionSig(name="zebra"),
                FunctionSig(name="alpha"),
                FunctionSig(name="middle"),
            ],
        )
        skeleton_b = InterfaceSkeleton(
            file_path="test.py",
            language="python",
            functions=[
                FunctionSig(name="alpha"),
                FunctionSig(name="middle"),
                FunctionSig(name="zebra"),
            ],
        )
        assert render_skeleton(skeleton_a) == render_skeleton(skeleton_b)

    def test_reordered_classes_produce_same_output(self) -> None:
        skeleton_a = InterfaceSkeleton(
            file_path="test.py",
            language="python",
            classes=[ClassSig(name="Zebra"), ClassSig(name="Alpha")],
        )
        skeleton_b = InterfaceSkeleton(
            file_path="test.py",
            language="python",
            classes=[ClassSig(name="Alpha"), ClassSig(name="Zebra")],
        )
        assert render_skeleton(skeleton_a) == render_skeleton(skeleton_b)

    def test_reordered_exports_produce_same_output(self) -> None:
        skeleton_a = InterfaceSkeleton(
            file_path="test.py",
            language="python",
            exports=["zebra", "alpha"],
        )
        skeleton_b = InterfaceSkeleton(
            file_path="test.py",
            language="python",
            exports=["alpha", "zebra"],
        )
        assert render_skeleton(skeleton_a) == render_skeleton(skeleton_b)


class TestConstantRendering:
    """Tests for constant rendering."""

    def test_constant_with_type(self) -> None:
        skeleton = InterfaceSkeleton(
            file_path="test.py",
            language="python",
            constants=[ConstantSig(name="MAX_RETRIES", type_annotation="int")],
        )
        result = render_skeleton(skeleton)
        assert "const:MAX_RETRIES:int" in result

    def test_constant_without_type(self) -> None:
        skeleton = InterfaceSkeleton(
            file_path="test.py",
            language="python",
            constants=[ConstantSig(name="DEBUG")],
        )
        result = render_skeleton(skeleton)
        assert "const:DEBUG\n" in result

    def test_constants_sorted_alphabetically(self) -> None:
        skeleton = InterfaceSkeleton(
            file_path="test.py",
            language="python",
            constants=[
                ConstantSig(name="ZEBRA"),
                ConstantSig(name="ALPHA"),
            ],
        )
        result = render_skeleton(skeleton)
        alpha_pos = result.index("const:ALPHA")
        zebra_pos = result.index("const:ZEBRA")
        assert alpha_pos < zebra_pos


class TestFunctionRendering:
    """Tests for function rendering."""

    def test_simple_function(self) -> None:
        skeleton = InterfaceSkeleton(
            file_path="test.py",
            language="python",
            functions=[FunctionSig(name="process")],
        )
        result = render_skeleton(skeleton)
        assert "func:process()" in result

    def test_function_with_params_and_return(self) -> None:
        skeleton = InterfaceSkeleton(
            file_path="test.py",
            language="python",
            functions=[
                FunctionSig(
                    name="authenticate",
                    parameters=[
                        ParameterSig(name="username", type_annotation="str"),
                        ParameterSig(name="password", type_annotation="str"),
                    ],
                    return_type="bool",
                ),
            ],
        )
        result = render_skeleton(skeleton)
        assert "func:authenticate(username:str,password:str)->bool" in result

    def test_async_function(self) -> None:
        skeleton = InterfaceSkeleton(
            file_path="test.py",
            language="python",
            functions=[FunctionSig(name="fetch", is_async=True)],
        )
        result = render_skeleton(skeleton)
        assert "async func:fetch()" in result

    def test_static_method(self) -> None:
        skeleton = InterfaceSkeleton(
            file_path="test.py",
            language="python",
            functions=[FunctionSig(name="create", is_static=True)],
        )
        result = render_skeleton(skeleton)
        assert "static func:create()" in result

    def test_classmethod(self) -> None:
        skeleton = InterfaceSkeleton(
            file_path="test.py",
            language="python",
            functions=[FunctionSig(name="from_dict", is_class_method=True)],
        )
        result = render_skeleton(skeleton)
        assert "classmethod func:from_dict()" in result

    def test_property(self) -> None:
        skeleton = InterfaceSkeleton(
            file_path="test.py",
            language="python",
            functions=[FunctionSig(name="value", is_property=True)],
        )
        result = render_skeleton(skeleton)
        assert "property func:value()" in result

    def test_parameter_with_default(self) -> None:
        skeleton = InterfaceSkeleton(
            file_path="test.py",
            language="python",
            functions=[
                FunctionSig(
                    name="connect",
                    parameters=[
                        ParameterSig(name="timeout", type_annotation="float", default="30.0"),
                    ],
                ),
            ],
        )
        result = render_skeleton(skeleton)
        assert "func:connect(timeout:float=30.0)" in result

    def test_functions_sorted_alphabetically(self) -> None:
        skeleton = InterfaceSkeleton(
            file_path="test.py",
            language="python",
            functions=[
                FunctionSig(name="zebra"),
                FunctionSig(name="alpha"),
                FunctionSig(name="middle"),
            ],
        )
        result = render_skeleton(skeleton)
        lines = result.strip().split("\n")
        func_lines = [line for line in lines if line.startswith("func:")]
        assert func_lines == [
            "func:alpha()",
            "func:middle()",
            "func:zebra()",
        ]


class TestClassRendering:
    """Tests for class rendering."""

    def test_simple_class(self) -> None:
        skeleton = InterfaceSkeleton(
            file_path="test.py",
            language="python",
            classes=[ClassSig(name="MyClass")],
        )
        result = render_skeleton(skeleton)
        assert "class:MyClass\n" in result

    def test_class_with_bases(self) -> None:
        skeleton = InterfaceSkeleton(
            file_path="test.py",
            language="python",
            classes=[ClassSig(name="AuthService", bases=["BaseService"])],
        )
        result = render_skeleton(skeleton)
        assert "class:AuthService(BaseService)" in result

    def test_class_with_methods_sorted(self) -> None:
        skeleton = InterfaceSkeleton(
            file_path="test.py",
            language="python",
            classes=[
                ClassSig(
                    name="Service",
                    methods=[
                        FunctionSig(name="save", is_method=True),
                        FunctionSig(name="delete", is_method=True),
                        FunctionSig(name="create", is_method=True),
                    ],
                ),
            ],
        )
        result = render_skeleton(skeleton)
        lines = result.strip().split("\n")
        method_lines = [line for line in lines if "func:" in line and line.startswith("  ")]
        assert len(method_lines) == 3
        assert "create" in method_lines[0]
        assert "delete" in method_lines[1]
        assert "save" in method_lines[2]

    def test_class_with_class_variables(self) -> None:
        skeleton = InterfaceSkeleton(
            file_path="test.py",
            language="python",
            classes=[
                ClassSig(
                    name="Config",
                    class_variables=[
                        ConstantSig(name="DEBUG", type_annotation="bool"),
                    ],
                ),
            ],
        )
        result = render_skeleton(skeleton)
        assert "  const:DEBUG:bool" in result


class TestExportRendering:
    """Tests for export rendering."""

    def test_export_rendering(self) -> None:
        skeleton = InterfaceSkeleton(
            file_path="test.ts",
            language="typescript",
            exports=["authenticate"],
        )
        result = render_skeleton(skeleton)
        assert "export:authenticate" in result

    def test_exports_sorted(self) -> None:
        skeleton = InterfaceSkeleton(
            file_path="test.ts",
            language="typescript",
            exports=["zebra", "alpha"],
        )
        result = render_skeleton(skeleton)
        alpha_pos = result.index("export:alpha")
        zebra_pos = result.index("export:zebra")
        assert alpha_pos < zebra_pos


class TestSectionOrdering:
    """Tests for section ordering: constants, functions, classes, exports."""

    def test_sections_in_correct_order(self) -> None:
        skeleton = InterfaceSkeleton(
            file_path="test.py",
            language="python",
            constants=[ConstantSig(name="VERSION")],
            functions=[FunctionSig(name="process")],
            classes=[ClassSig(name="Service")],
            exports=["process", "Service"],
        )
        result = render_skeleton(skeleton)
        const_pos = result.index("const:")
        func_pos = result.index("func:")
        class_pos = result.index("class:")
        export_pos = result.index("export:")
        assert const_pos < func_pos < class_pos < export_pos


class TestNoMetadata:
    """Tests that file path and language are excluded from output."""

    def test_file_path_excluded(self) -> None:
        skeleton = InterfaceSkeleton(
            file_path="src/auth.py",
            language="python",
            functions=[FunctionSig(name="login")],
        )
        result = render_skeleton(skeleton)
        assert "src/auth.py" not in result

    def test_language_excluded(self) -> None:
        skeleton = InterfaceSkeleton(
            file_path="test.py",
            language="python",
            functions=[FunctionSig(name="login")],
        )
        result = render_skeleton(skeleton)
        # "python" should not appear as a standalone token in the output
        lines = result.strip().split("\n")
        assert not any(line.strip() == "python" for line in lines)
