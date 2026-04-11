"""Tests for the Python parser interface extraction.

Covers: functions, classes, constants, __all__, private exclusion,
async, staticmethod/classmethod/property, syntax errors.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lexibrary.ast_parser.python_parser import extract_interface

# Path to the fixtures directory
FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _write_py(tmp_path: Path, code: str) -> Path:
    """Write a temporary Python file and return its path."""
    p = tmp_path / "test_module.py"
    p.write_text(code, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Fixture-based tests
# ---------------------------------------------------------------------------


class TestSimpleModule:
    """Tests using the simple_module.py fixture."""

    @pytest.fixture()
    def skeleton(self):
        return extract_interface(FIXTURES / "simple_module.py")

    def test_returns_skeleton(self, skeleton):
        assert skeleton is not None
        assert skeleton.language == "python"

    def test_constants(self, skeleton):
        names = {c.name for c in skeleton.constants}
        assert "MAX_RETRIES" in names
        assert "DEFAULT_TIMEOUT" in names

    def test_constant_type_annotation(self, skeleton):
        by_name = {c.name: c for c in skeleton.constants}
        assert by_name["DEFAULT_TIMEOUT"].type_annotation == "float"
        assert by_name["MAX_RETRIES"].type_annotation is None

    def test_functions(self, skeleton):
        names = {f.name for f in skeleton.functions}
        assert "process_data" in names
        assert "validate" in names
        assert "fetch_resource" in names

    def test_async_function(self, skeleton):
        by_name = {f.name: f for f in skeleton.functions}
        assert by_name["fetch_resource"].is_async is True
        assert by_name["process_data"].is_async is False

    def test_function_parameters(self, skeleton):
        by_name = {f.name: f for f in skeleton.functions}
        process = by_name["process_data"]
        param_names = [p.name for p in process.parameters]
        assert param_names == ["input_path", "output_path", "verbose"]

    def test_function_parameter_types(self, skeleton):
        by_name = {f.name: f for f in skeleton.functions}
        process = by_name["process_data"]
        by_pname = {p.name: p for p in process.parameters}
        assert by_pname["input_path"].type_annotation == "str"
        assert by_pname["verbose"].type_annotation == "bool"

    def test_function_default_values(self, skeleton):
        by_name = {f.name: f for f in skeleton.functions}
        process = by_name["process_data"]
        by_pname = {p.name: p for p in process.parameters}
        assert by_pname["verbose"].default == "False"
        assert by_pname["input_path"].default is None

    def test_function_return_type(self, skeleton):
        by_name = {f.name: f for f in skeleton.functions}
        assert by_name["process_data"].return_type == "int"
        assert by_name["validate"].return_type == "bool"
        assert by_name["fetch_resource"].return_type == "bytes"

    def test_exports(self, skeleton):
        assert skeleton.exports == ["DEFAULT_TIMEOUT", "MAX_RETRIES", "process_data"]


class TestClassesAndFunctions:
    """Tests using the classes_and_functions.py fixture."""

    @pytest.fixture()
    def skeleton(self):
        return extract_interface(FIXTURES / "classes_and_functions.py")

    def test_constants(self, skeleton):
        names = {c.name for c in skeleton.constants}
        assert "API_VERSION" in names
        assert "base_url" in names

    def test_classes_found(self, skeleton):
        names = {c.name for c in skeleton.classes}
        assert "BaseService" in names
        assert "AuthService" in names

    def test_base_classes(self, skeleton):
        by_name = {c.name: c for c in skeleton.classes}
        assert by_name["BaseService"].bases == []
        assert by_name["AuthService"].bases == ["BaseService"]

    def test_public_functions(self, skeleton):
        names = {f.name for f in skeleton.functions}
        assert "create_service" in names
        assert "_private_helper" not in names

    def test_private_method_excluded(self, skeleton):
        by_name = {c.name: c for c in skeleton.classes}
        base = by_name["BaseService"]
        method_names = {m.name for m in base.methods}
        assert "_internal_setup" not in method_names

    def test_all_dunders_public(self, skeleton):
        # Phase 2: dunder methods are always public, including __repr__,
        # __enter__, __aiter__, etc. The short _ALLOWED_DUNDER_METHODS
        # allow-list was removed so the interface skeleton and symbol
        # graph agree on visibility.
        by_name = {c.name: c for c in skeleton.classes}
        base = by_name["BaseService"]
        method_names = {m.name for m in base.methods}
        assert "__init__" in method_names
        assert "__repr__" in method_names

    def test_init_included(self, skeleton):
        by_name = {c.name: c for c in skeleton.classes}
        auth = by_name["AuthService"]
        method_names = {m.name for m in auth.methods}
        assert "__init__" in method_names

    def test_staticmethod(self, skeleton):
        by_name = {c.name: c for c in skeleton.classes}
        auth = by_name["AuthService"]
        methods = {m.name: m for m in auth.methods}
        assert methods["hash_password"].is_static is True
        assert methods["hash_password"].is_method is True

    def test_classmethod(self, skeleton):
        by_name = {c.name: c for c in skeleton.classes}
        auth = by_name["AuthService"]
        methods = {m.name: m for m in auth.methods}
        assert methods["from_env"].is_class_method is True

    def test_classmethod_skips_cls(self, skeleton):
        by_name = {c.name: c for c in skeleton.classes}
        auth = by_name["AuthService"]
        methods = {m.name: m for m in auth.methods}
        param_names = [p.name for p in methods["from_env"].parameters]
        assert "cls" not in param_names
        assert "env_prefix" in param_names

    def test_property(self, skeleton):
        by_name = {c.name: c for c in skeleton.classes}
        auth = by_name["AuthService"]
        methods = {m.name: m for m in auth.methods}
        assert methods["is_configured"].is_property is True

    def test_property_skips_self(self, skeleton):
        by_name = {c.name: c for c in skeleton.classes}
        auth = by_name["AuthService"]
        methods = {m.name: m for m in auth.methods}
        params = methods["is_configured"].parameters
        assert len(params) == 0

    def test_async_method(self, skeleton):
        by_name = {c.name: c for c in skeleton.classes}
        auth = by_name["AuthService"]
        methods = {m.name: m for m in auth.methods}
        assert methods["authenticate_async"].is_async is True
        assert methods["authenticate"].is_async is False

    def test_class_variables(self, skeleton):
        by_name = {c.name: c for c in skeleton.classes}
        base = by_name["BaseService"]
        var_names = {v.name for v in base.class_variables}
        assert "timeout" in var_names

        auth = by_name["AuthService"]
        var_names = {v.name for v in auth.class_variables}
        assert "max_attempts" in var_names


class TestEmptyModule:
    """Tests using the empty_module.py fixture."""

    @pytest.fixture()
    def skeleton(self):
        return extract_interface(FIXTURES / "empty_module.py")

    def test_returns_skeleton(self, skeleton):
        assert skeleton is not None

    def test_no_constants(self, skeleton):
        assert skeleton.constants == []

    def test_no_functions(self, skeleton):
        assert skeleton.functions == []

    def test_no_classes(self, skeleton):
        assert skeleton.classes == []

    def test_no_exports(self, skeleton):
        assert skeleton.exports == []


class TestNoPublicApi:
    """Tests using the no_public_api.py fixture."""

    @pytest.fixture()
    def skeleton(self):
        return extract_interface(FIXTURES / "no_public_api.py")

    def test_returns_skeleton(self, skeleton):
        assert skeleton is not None

    def test_no_public_functions(self, skeleton):
        assert skeleton.functions == []

    def test_no_public_classes(self, skeleton):
        assert skeleton.classes == []

    def test_no_public_constants(self, skeleton):
        # _INTERNAL_FLAG starts with _, _counter is not UPPER_CASE nor typed
        assert skeleton.constants == []


# ---------------------------------------------------------------------------
# Inline tests for edge cases
# ---------------------------------------------------------------------------


class TestAllExports:
    """Tests for __all__ extraction."""

    def test_literal_list(self, tmp_path: Path):
        p = _write_py(tmp_path, '__all__ = ["Foo", "Bar", "Baz"]')
        skel = extract_interface(p)
        assert skel is not None
        assert skel.exports == ["Bar", "Baz", "Foo"]

    def test_literal_single_quotes(self, tmp_path: Path):
        p = _write_py(tmp_path, "__all__ = ['Alpha', 'Beta']")
        skel = extract_interface(p)
        assert skel is not None
        assert skel.exports == ["Alpha", "Beta"]

    def test_dynamic_all_ignored(self, tmp_path: Path):
        p = _write_py(tmp_path, "__all__ = get_exports()")
        skel = extract_interface(p)
        assert skel is not None
        assert skel.exports == []

    def test_empty_all(self, tmp_path: Path):
        p = _write_py(tmp_path, "__all__ = []")
        skel = extract_interface(p)
        assert skel is not None
        assert skel.exports == []


class TestConstants:
    """Tests for constant extraction."""

    def test_upper_case_constant(self, tmp_path: Path):
        p = _write_py(tmp_path, "MAX_RETRIES = 3")
        skel = extract_interface(p)
        assert skel is not None
        names = {c.name for c in skel.constants}
        assert "MAX_RETRIES" in names

    def test_type_annotated_constant(self, tmp_path: Path):
        p = _write_py(tmp_path, "timeout: float = 30.0")
        skel = extract_interface(p)
        assert skel is not None
        names = {c.name for c in skel.constants}
        assert "timeout" in names
        by_name = {c.name: c for c in skel.constants}
        assert by_name["timeout"].type_annotation == "float"

    def test_regular_assignment_excluded(self, tmp_path: Path):
        p = _write_py(tmp_path, "result = compute()")
        skel = extract_interface(p)
        assert skel is not None
        assert skel.constants == []

    def test_private_upper_excluded(self, tmp_path: Path):
        """_PRIVATE_CONST starts with _ so does not match UPPER_CASE pattern."""
        p = _write_py(tmp_path, "_PRIVATE_CONST = 42")
        skel = extract_interface(p)
        assert skel is not None
        # _PRIVATE_CONST does not match ^[A-Z][A-Z0-9_]*$ because it starts
        # with underscore, so it is correctly excluded from constants.
        assert skel.constants == []


class TestFunctions:
    """Tests for function extraction edge cases."""

    def test_function_without_types(self, tmp_path: Path):
        p = _write_py(tmp_path, "def process(data):\n    pass")
        skel = extract_interface(p)
        assert skel is not None
        func = skel.functions[0]
        assert func.name == "process"
        assert func.parameters[0].type_annotation is None
        assert func.return_type is None

    def test_function_with_defaults(self, tmp_path: Path):
        p = _write_py(
            tmp_path, "def retry(attempts: int = 3, delay: float = 1.0) -> None:\n    pass"
        )
        skel = extract_interface(p)
        assert skel is not None
        func = skel.functions[0]
        by_pname = {p.name: p for p in func.parameters}
        assert by_pname["attempts"].default == "3"
        assert by_pname["delay"].default == "1.0"

    def test_private_function_excluded(self, tmp_path: Path):
        code = "def public():\n    pass\n\ndef _private():\n    pass"
        p = _write_py(tmp_path, code)
        skel = extract_interface(p)
        assert skel is not None
        names = {f.name for f in skel.functions}
        assert "public" in names
        assert "_private" not in names


class TestNestedDeclarations:
    """Test that nested declarations are excluded (top-level only)."""

    def test_nested_function_excluded(self, tmp_path: Path):
        code = "def outer():\n    def inner():\n        pass\n    return inner"
        p = _write_py(tmp_path, code)
        skel = extract_interface(p)
        assert skel is not None
        names = {f.name for f in skel.functions}
        assert "outer" in names
        assert "inner" not in names

    def test_nested_class_excluded(self, tmp_path: Path):
        code = "class Outer:\n    class Inner:\n        pass\n    def __init__(self): pass"
        p = _write_py(tmp_path, code)
        skel = extract_interface(p)
        assert skel is not None
        class_names = {c.name for c in skel.classes}
        assert "Outer" in class_names
        assert "Inner" not in class_names


class TestSyntaxErrors:
    """Test graceful handling of files with syntax errors."""

    def test_partial_extraction_on_syntax_error(self, tmp_path: Path):
        code = (
            "def good_func(x: int) -> int:\n"
            "    return x\n"
            "\n"
            "def bad_func(:\n"  # syntax error
            "    pass\n"
            "\n"
            "MAX_VALUE = 100\n"
        )
        p = _write_py(tmp_path, code)
        skel = extract_interface(p)
        assert skel is not None
        # Should extract what it can
        func_names = {f.name for f in skel.functions}
        assert "good_func" in func_names
        const_names = {c.name for c in skel.constants}
        assert "MAX_VALUE" in const_names

    def test_completely_broken_file(self, tmp_path: Path):
        code = "}{}{}{def class if while"
        p = _write_py(tmp_path, code)
        skel = extract_interface(p)
        # Should not raise, should return a skeleton (possibly empty)
        assert skel is not None


class TestNonExistentFile:
    """Test handling of files that cannot be read."""

    def test_missing_file_returns_none(self):
        skel = extract_interface(Path("/nonexistent/file.py"))
        assert skel is None


class TestUnsupportedExtension:
    """Test handling of unsupported file extensions."""

    def test_unsupported_extension_returns_none(self, tmp_path: Path):
        p = tmp_path / "test.rs"
        p.write_text("fn main() {}", encoding="utf-8")
        skel = extract_interface(p)
        assert skel is None


class TestMethodModifiers:
    """Detailed tests for staticmethod, classmethod, property detection."""

    @pytest.fixture()
    def skeleton(self, tmp_path: Path):
        code = (
            "class Example:\n"
            "    @staticmethod\n"
            "    def static_one(a: int) -> int:\n"
            "        return a\n"
            "\n"
            "    @classmethod\n"
            "    def class_one(cls, b: str) -> None:\n"
            "        pass\n"
            "\n"
            "    @property\n"
            "    def prop_one(self) -> str:\n"
            "        return ''\n"
            "\n"
            "    def regular(self, x: int) -> int:\n"
            "        return x\n"
        )
        p = _write_py(tmp_path, code)
        return extract_interface(p)

    def test_static_method(self, skeleton):
        cls = skeleton.classes[0]
        methods = {m.name: m for m in cls.methods}
        assert methods["static_one"].is_static is True
        assert methods["static_one"].is_class_method is False
        assert methods["static_one"].is_property is False

    def test_class_method(self, skeleton):
        cls = skeleton.classes[0]
        methods = {m.name: m for m in cls.methods}
        assert methods["class_one"].is_class_method is True
        assert methods["class_one"].is_static is False

    def test_property_method(self, skeleton):
        cls = skeleton.classes[0]
        methods = {m.name: m for m in cls.methods}
        assert methods["prop_one"].is_property is True
        assert methods["prop_one"].is_static is False

    def test_regular_method_no_modifiers(self, skeleton):
        cls = skeleton.classes[0]
        methods = {m.name: m for m in cls.methods}
        assert methods["regular"].is_static is False
        assert methods["regular"].is_class_method is False
        assert methods["regular"].is_property is False

    def test_staticmethod_has_no_self(self, skeleton):
        cls = skeleton.classes[0]
        methods = {m.name: m for m in cls.methods}
        param_names = [p.name for p in methods["static_one"].parameters]
        assert "self" not in param_names
        assert "a" in param_names

    def test_classmethod_has_no_cls(self, skeleton):
        cls = skeleton.classes[0]
        methods = {m.name: m for m in cls.methods}
        param_names = [p.name for p in methods["class_one"].parameters]
        assert "cls" not in param_names
        assert "b" in param_names

    def test_property_has_no_self(self, skeleton):
        cls = skeleton.classes[0]
        methods = {m.name: m for m in cls.methods}
        params = methods["prop_one"].parameters
        assert len(params) == 0
