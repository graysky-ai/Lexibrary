"""Tests for the TypeScript/TSX parser.

Covers: functions, classes, interfaces, type aliases, enums, exports,
generics, async, static, getters, constants, TSX components.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lexibrary.ast_parser.typescript_parser import extract_interface

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Fixture-based tests
# ---------------------------------------------------------------------------


class TestSimpleModule:
    """Tests against fixtures/simple_module.ts."""

    @pytest.fixture()
    def skeleton(self):
        path = FIXTURES / "simple_module.ts"
        result = extract_interface(path)
        assert result is not None
        return result

    def test_language(self, skeleton):
        assert skeleton.language == "typescript"

    def test_constants_extracted(self, skeleton):
        names = {c.name for c in skeleton.constants}
        assert "MAX_RETRIES" in names
        assert "appName" in names

    def test_constant_type_annotation(self, skeleton):
        by_name = {c.name: c for c in skeleton.constants}
        assert by_name["MAX_RETRIES"].type_annotation == "number"
        assert by_name["appName"].type_annotation == "string"

    def test_functions_extracted(self, skeleton):
        names = {f.name for f in skeleton.functions}
        assert "greet" in names
        assert "fetchData" in names

    def test_greet_parameters(self, skeleton):
        greet = next(f for f in skeleton.functions if f.name == "greet")
        assert len(greet.parameters) == 1
        assert greet.parameters[0].name == "name"
        assert greet.parameters[0].type_annotation == "string"
        assert greet.return_type == "string"
        assert greet.is_async is False

    def test_async_function(self, skeleton):
        fetch = next(f for f in skeleton.functions if f.name == "fetchData")
        assert fetch.is_async is True
        assert fetch.return_type == "Promise<Response>"

    def test_exports(self, skeleton):
        assert "greet" in skeleton.exports
        assert "MAX_RETRIES" in skeleton.exports


class TestClassesAndFunctions:
    """Tests against fixtures/classes_and_functions.ts."""

    @pytest.fixture()
    def skeleton(self):
        path = FIXTURES / "classes_and_functions.ts"
        result = extract_interface(path)
        assert result is not None
        return result

    def test_language(self, skeleton):
        assert skeleton.language == "typescript"

    # --- Interface ---

    def test_interface_extracted(self, skeleton):
        names = {c.name for c in skeleton.classes}
        assert "IUserService" in names

    def test_interface_methods(self, skeleton):
        iface = next(c for c in skeleton.classes if c.name == "IUserService")
        method_names = {m.name for m in iface.methods}
        assert "getUser" in method_names
        assert "deleteUser" in method_names

    def test_interface_method_params(self, skeleton):
        iface = next(c for c in skeleton.classes if c.name == "IUserService")
        get_user = next(m for m in iface.methods if m.name == "getUser")
        assert len(get_user.parameters) == 1
        assert get_user.parameters[0].name == "id"
        assert get_user.parameters[0].type_annotation == "string"

    def test_interface_method_return_type(self, skeleton):
        iface = next(c for c in skeleton.classes if c.name == "IUserService")
        delete_user = next(m for m in iface.methods if m.name == "deleteUser")
        assert delete_user.return_type == "void"

    def test_interface_property(self, skeleton):
        iface = next(c for c in skeleton.classes if c.name == "IUserService")
        # IUserService has no property signatures in this fixture
        # (id is not present, getUser and deleteUser are methods)
        # Verify methods are marked as methods
        for m in iface.methods:
            assert m.is_method is True

    # --- Class ---

    def test_class_extracted(self, skeleton):
        names = {c.name for c in skeleton.classes}
        assert "UserService" in names

    def test_class_bases(self, skeleton):
        cls = next(c for c in skeleton.classes if c.name == "UserService")
        assert "BaseService" in cls.bases
        assert "IUserService" in cls.bases

    def test_class_methods(self, skeleton):
        cls = next(c for c in skeleton.classes if c.name == "UserService")
        method_names = {m.name for m in cls.methods}
        assert "constructor" in method_names
        assert "getUser" in method_names
        assert "deleteUser" in method_names
        assert "create" in method_names
        assert "fetchRemote" in method_names
        assert "count" in method_names

    def test_class_constructor(self, skeleton):
        cls = next(c for c in skeleton.classes if c.name == "UserService")
        ctor = next(m for m in cls.methods if m.name == "constructor")
        assert ctor.is_method is True
        assert len(ctor.parameters) == 1
        assert ctor.parameters[0].name == "db"

    def test_class_static_method(self, skeleton):
        cls = next(c for c in skeleton.classes if c.name == "UserService")
        create = next(m for m in cls.methods if m.name == "create")
        assert create.is_static is True
        assert create.return_type == "UserService"

    def test_class_async_method(self, skeleton):
        cls = next(c for c in skeleton.classes if c.name == "UserService")
        fetch = next(m for m in cls.methods if m.name == "fetchRemote")
        assert fetch.is_async is True
        assert fetch.return_type == "Promise<User[]>"

    def test_class_getter(self, skeleton):
        cls = next(c for c in skeleton.classes if c.name == "UserService")
        count = next(m for m in cls.methods if m.name == "count")
        assert count.is_property is True
        assert count.return_type == "number"

    def test_class_field(self, skeleton):
        cls = next(c for c in skeleton.classes if c.name == "UserService")
        field_names = {v.name for v in cls.class_variables}
        assert "db" in field_names

    # --- Type aliases ---

    def test_type_alias_simple(self, skeleton):
        by_name = {c.name: c for c in skeleton.constants}
        assert "UserId" in by_name
        assert by_name["UserId"].type_annotation == "string"

    def test_type_alias_generic(self, skeleton):
        by_name = {c.name: c for c in skeleton.constants}
        assert "Result" in by_name
        # The type annotation captures the RHS
        assert by_name["Result"].type_annotation is not None

    # --- Enum ---

    def test_enum_extracted(self, skeleton):
        names = {c.name for c in skeleton.classes}
        assert "Status" in names

    def test_enum_members(self, skeleton):
        enum = next(c for c in skeleton.classes if c.name == "Status")
        member_names = {v.name for v in enum.class_variables}
        assert "Active" in member_names
        assert "Inactive" in member_names
        assert "Pending" in member_names

    # --- Generic function ---

    def test_generic_function(self, skeleton):
        identity = next(f for f in skeleton.functions if f.name == "identity")
        assert len(identity.parameters) == 1
        assert identity.parameters[0].name == "value"
        assert identity.parameters[0].type_annotation == "T"
        assert identity.return_type == "T"

    # --- Exports ---

    def test_exports(self, skeleton):
        assert "IUserService" in skeleton.exports
        assert "UserService" in skeleton.exports
        assert "UserId" in skeleton.exports
        assert "Result" in skeleton.exports
        assert "Status" in skeleton.exports
        assert "identity" in skeleton.exports
        assert "App" in skeleton.exports

    # --- Default export ---

    def test_default_export_class(self, skeleton):
        names = {c.name for c in skeleton.classes}
        assert "App" in names
        assert "App" in skeleton.exports

    # --- Non-exported constant ---

    def test_non_exported_constant(self, skeleton):
        by_name = {c.name: c for c in skeleton.constants}
        assert "API_VERSION" in by_name
        assert by_name["API_VERSION"].type_annotation == "number"
        # Not exported
        assert "API_VERSION" not in skeleton.exports


class TestTsxComponent:
    """Tests against fixtures/jsx_component.tsx."""

    @pytest.fixture()
    def skeleton(self):
        path = FIXTURES / "jsx_component.tsx"
        result = extract_interface(path)
        assert result is not None
        return result

    def test_language(self, skeleton):
        assert skeleton.language == "tsx"

    def test_interface_extracted(self, skeleton):
        names = {c.name for c in skeleton.classes}
        assert "AppProps" in names

    def test_interface_properties(self, skeleton):
        props = next(c for c in skeleton.classes if c.name == "AppProps")
        prop_names = {v.name for v in props.class_variables}
        assert "title" in prop_names
        assert "count" in prop_names

    def test_function_extracted(self, skeleton):
        names = {f.name for f in skeleton.functions}
        assert "App" in names

    def test_function_return_type(self, skeleton):
        app = next(f for f in skeleton.functions if f.name == "App")
        assert app.return_type == "JSX.Element"

    def test_function_params(self, skeleton):
        app = next(f for f in skeleton.functions if f.name == "App")
        assert len(app.parameters) == 1
        assert app.parameters[0].name == "props"
        assert app.parameters[0].type_annotation == "AppProps"

    def test_exports(self, skeleton):
        assert "App" in skeleton.exports

    def test_const_component_exported(self, skeleton):
        # Greeting is exported as a const (arrow function assigned to const
        # with explicit type annotation is treated as a constant)
        assert "Greeting" in skeleton.exports


# ---------------------------------------------------------------------------
# Inline code tests (using tmp_path)
# ---------------------------------------------------------------------------


class TestInlineCode:
    """Tests using inline TypeScript snippets written to tmp_path."""

    def _parse(self, tmp_path: Path, code: str, ext: str = ".ts") -> object:
        """Write code to a temp file and parse it."""
        path = tmp_path / f"test{ext}"
        path.write_text(code)
        result = extract_interface(path)
        assert result is not None
        return result

    def test_unsupported_extension(self, tmp_path: Path):
        path = tmp_path / "test.go"
        path.write_text("package main")
        assert extract_interface(path) is None

    def test_empty_file(self, tmp_path: Path):
        skeleton = self._parse(tmp_path, "")
        assert skeleton.functions == []
        assert skeleton.classes == []
        assert skeleton.constants == []
        assert skeleton.exports == []

    def test_optional_parameter(self, tmp_path: Path):
        code = "function greet(name: string, greeting?: string): string { return ''; }"
        skeleton = self._parse(tmp_path, code)
        func = skeleton.functions[0]
        assert len(func.parameters) == 2
        assert func.parameters[1].name == "greeting"
        assert func.parameters[1].type_annotation == "string"

    def test_parameter_with_default(self, tmp_path: Path):
        code = "function greet(name: string = 'World'): string { return ''; }"
        skeleton = self._parse(tmp_path, code)
        func = skeleton.functions[0]
        assert func.parameters[0].default == "'World'"

    def test_export_clause(self, tmp_path: Path):
        code = "const A: number = 1;\nconst B: number = 2;\nexport { A, B };"
        skeleton = self._parse(tmp_path, code)
        assert "A" in skeleton.exports
        assert "B" in skeleton.exports

    def test_nonexistent_file(self):
        result = extract_interface(Path("/nonexistent/file.ts"))
        assert result is None

    def test_syntax_error_partial_parse(self, tmp_path: Path):
        """tree-sitter handles syntax errors gracefully with partial trees."""
        code = "function greet(name: string): string { \nexport const X: number = 1;"
        skeleton = self._parse(tmp_path, code)
        # Should still extract what it can
        assert skeleton is not None

    def test_interface_with_extends(self, tmp_path: Path):
        code = "interface Admin extends User { role: string; }"
        skeleton = self._parse(tmp_path, code)
        admin = next(c for c in skeleton.classes if c.name == "Admin")
        assert "User" in admin.bases

    def test_enum_members(self, tmp_path: Path):
        code = "enum Color { Red, Green, Blue }"
        skeleton = self._parse(tmp_path, code)
        color = next(c for c in skeleton.classes if c.name == "Color")
        member_names = {v.name for v in color.class_variables}
        assert member_names == {"Red", "Green", "Blue"}

    def test_multiple_variable_declarators(self, tmp_path: Path):
        code = "const X: number = 1, Y: string = 'hello';"
        skeleton = self._parse(tmp_path, code)
        names = {c.name for c in skeleton.constants}
        # tree-sitter may treat this as one lexical_declaration with multiple declarators
        assert "X" in names

    def test_tsx_file_uses_tsx_language(self, tmp_path: Path):
        code = "export function App(): JSX.Element { return <div/>; }"
        skeleton = self._parse(tmp_path, code, ext=".tsx")
        assert skeleton.language == "tsx"
        assert len(skeleton.functions) == 1
        assert skeleton.functions[0].name == "App"
