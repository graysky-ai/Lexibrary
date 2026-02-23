"""Tests for the JavaScript/JSX parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from lexibrary.ast_parser.javascript_parser import extract_interface

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ── Fixture-based tests ─────────────────────────────────────────────────────


class TestSimpleModule:
    """Tests against simple_module.js fixture."""

    @pytest.fixture()
    def skeleton(self):
        path = FIXTURES_DIR / "simple_module.js"
        result = extract_interface(path)
        assert result is not None
        return result

    def test_language(self, skeleton):
        assert skeleton.language == "javascript"

    def test_extracts_function_declarations(self, skeleton):
        func_names = {f.name for f in skeleton.functions}
        assert "greet" in func_names
        assert "fetchData" in func_names

    def test_extracts_arrow_functions(self, skeleton):
        func_names = {f.name for f in skeleton.functions}
        assert "handler" in func_names
        assert "fetchUser" in func_names

    def test_async_function_detected(self, skeleton):
        by_name = {f.name: f for f in skeleton.functions}
        assert by_name["fetchData"].is_async is True
        assert by_name["greet"].is_async is False

    def test_async_arrow_function_detected(self, skeleton):
        by_name = {f.name: f for f in skeleton.functions}
        assert by_name["fetchUser"].is_async is True
        assert by_name["handler"].is_async is False

    def test_function_parameters(self, skeleton):
        by_name = {f.name: f for f in skeleton.functions}
        greet = by_name["greet"]
        assert len(greet.parameters) == 1
        assert greet.parameters[0].name == "name"
        assert greet.parameters[0].type_annotation is None

    def test_arrow_function_parameters(self, skeleton):
        by_name = {f.name: f for f in skeleton.functions}
        handler = by_name["handler"]
        assert len(handler.parameters) == 2
        param_names = [p.name for p in handler.parameters]
        assert param_names == ["req", "res"]

    def test_extracts_classes(self, skeleton):
        class_names = {c.name for c in skeleton.classes}
        assert "UserService" in class_names
        assert "EmptyClass" in class_names
        assert "App" in class_names

    def test_class_bases(self, skeleton):
        by_name = {c.name: c for c in skeleton.classes}
        assert by_name["UserService"].bases == ["BaseService"]
        assert by_name["EmptyClass"].bases == []

    def test_class_methods(self, skeleton):
        by_name = {c.name: c for c in skeleton.classes}
        us = by_name["UserService"]
        method_names = {m.name for m in us.methods}
        assert "constructor" in method_names
        assert "getUser" in method_names
        assert "updateUser" in method_names
        assert "create" in method_names

    def test_class_method_is_method_flag(self, skeleton):
        by_name = {c.name: c for c in skeleton.classes}
        us = by_name["UserService"]
        for m in us.methods:
            assert m.is_method is True

    def test_class_static_method(self, skeleton):
        by_name = {c.name: c for c in skeleton.classes}
        us = by_name["UserService"]
        methods_by_name = {m.name: m for m in us.methods}
        assert methods_by_name["create"].is_static is True
        assert methods_by_name["getUser"].is_static is False

    def test_class_async_method(self, skeleton):
        by_name = {c.name: c for c in skeleton.classes}
        us = by_name["UserService"]
        methods_by_name = {m.name: m for m in us.methods}
        assert methods_by_name["updateUser"].is_async is True
        assert methods_by_name["getUser"].is_async is False

    def test_class_getter_setter_are_property(self, skeleton):
        by_name = {c.name: c for c in skeleton.classes}
        us = by_name["UserService"]
        # Both get and set for "name" should be property
        name_methods = [m for m in us.methods if m.name == "name"]
        assert len(name_methods) == 2
        for m in name_methods:
            assert m.is_property is True

    def test_extracts_constants(self, skeleton):
        const_names = {c.name for c in skeleton.constants}
        assert "API_URL" in const_names
        assert "MAX_RETRIES" in const_names

    def test_constants_have_no_type(self, skeleton):
        for c in skeleton.constants:
            assert c.type_annotation is None

    def test_no_type_annotations_on_functions(self, skeleton):
        for f in skeleton.functions:
            assert f.return_type is None
            for p in f.parameters:
                assert p.type_annotation is None

    def test_es_module_exports(self, skeleton):
        """Named exports, default exports, and export clauses."""
        assert "exported_func" in skeleton.exports
        assert "App" in skeleton.exports
        assert "greet" in skeleton.exports
        assert "handler" in skeleton.exports
        assert "EXPORTED_CONST" in skeleton.exports

    def test_commonjs_exports(self, skeleton):
        """module.exports = { ... } names appear in exports."""
        assert "fetchData" in skeleton.exports
        assert "UserService" in skeleton.exports


class TestJsxComponent:
    """Tests against jsx_component.jsx fixture."""

    @pytest.fixture()
    def skeleton(self):
        path = FIXTURES_DIR / "jsx_component.jsx"
        result = extract_interface(path)
        assert result is not None
        return result

    def test_language(self, skeleton):
        assert skeleton.language == "javascript"

    def test_extracts_jsx_function_component(self, skeleton):
        func_names = {f.name for f in skeleton.functions}
        assert "Button" in func_names

    def test_extracts_jsx_arrow_component(self, skeleton):
        func_names = {f.name for f in skeleton.functions}
        assert "Card" in func_names

    def test_extracts_jsx_class_component(self, skeleton):
        class_names = {c.name for c in skeleton.classes}
        assert "Counter" in class_names

    def test_class_component_bases(self, skeleton):
        by_name = {c.name: c for c in skeleton.classes}
        assert by_name["Counter"].bases == ["React.Component"]

    def test_class_component_methods(self, skeleton):
        by_name = {c.name: c for c in skeleton.classes}
        method_names = {m.name for m in by_name["Counter"].methods}
        assert "constructor" in method_names
        assert "increment" in method_names
        assert "render" in method_names

    def test_jsx_exports(self, skeleton):
        assert "Button" in skeleton.exports
        assert "Card" in skeleton.exports
        assert "Counter" in skeleton.exports

    def test_destructured_props_parameter(self, skeleton):
        """JSX components with destructured props should capture the pattern."""
        by_name = {f.name: f for f in skeleton.functions}
        button = by_name["Button"]
        assert len(button.parameters) == 1
        # Destructured parameter should be captured as text
        assert "{" in button.parameters[0].name


# ── Inline source tests ─────────────────────────────────────────────────────


class TestFunctionDeclarations:
    """Focused tests for function extraction using inline source."""

    def _parse(self, source: str, tmp_path: Path) -> ...:
        p = tmp_path / "test.js"
        p.write_text(source)
        return extract_interface(p)

    def test_simple_function(self, tmp_path):
        skeleton = self._parse("function add(a, b) { return a + b; }", tmp_path)
        assert skeleton is not None
        assert len(skeleton.functions) == 1
        assert skeleton.functions[0].name == "add"
        assert len(skeleton.functions[0].parameters) == 2

    def test_no_params_function(self, tmp_path):
        skeleton = self._parse("function noop() {}", tmp_path)
        assert skeleton is not None
        assert skeleton.functions[0].parameters == []

    def test_async_function(self, tmp_path):
        skeleton = self._parse("async function load(url) {}", tmp_path)
        assert skeleton is not None
        assert skeleton.functions[0].is_async is True

    def test_rest_params(self, tmp_path):
        skeleton = self._parse("function variadic(first, ...rest) {}", tmp_path)
        assert skeleton is not None
        params = skeleton.functions[0].parameters
        assert params[0].name == "first"
        assert params[1].name == "...rest"

    def test_default_params(self, tmp_path):
        skeleton = self._parse('function greet(name = "world") {}', tmp_path)
        assert skeleton is not None
        params = skeleton.functions[0].parameters
        assert params[0].name == "name"
        assert params[0].default == '"world"'


class TestArrowFunctions:
    """Focused tests for arrow function extraction."""

    def _parse(self, source: str, tmp_path: Path) -> ...:
        p = tmp_path / "test.js"
        p.write_text(source)
        return extract_interface(p)

    def test_const_arrow(self, tmp_path):
        skeleton = self._parse("const fn = (x) => x * 2;", tmp_path)
        assert skeleton is not None
        assert len(skeleton.functions) == 1
        assert skeleton.functions[0].name == "fn"

    def test_async_arrow(self, tmp_path):
        skeleton = self._parse("const fn = async (x) => await x;", tmp_path)
        assert skeleton is not None
        assert skeleton.functions[0].is_async is True

    def test_arrow_not_method(self, tmp_path):
        skeleton = self._parse("const fn = () => {};", tmp_path)
        assert skeleton is not None
        assert skeleton.functions[0].is_method is False

    def test_let_not_extracted(self, tmp_path):
        """Only const arrow functions are extracted, not let."""
        skeleton = self._parse("let fn = (x) => x;", tmp_path)
        assert skeleton is not None
        assert len(skeleton.functions) == 0

    def test_const_function_expression(self, tmp_path):
        """const assigned to a function expression should also be extracted."""
        skeleton = self._parse("const fn = function(x) { return x; };", tmp_path)
        assert skeleton is not None
        assert len(skeleton.functions) == 1
        assert skeleton.functions[0].name == "fn"


class TestClassDeclarations:
    """Focused tests for class extraction."""

    def _parse(self, source: str, tmp_path: Path) -> ...:
        p = tmp_path / "test.js"
        p.write_text(source)
        return extract_interface(p)

    def test_empty_class(self, tmp_path):
        skeleton = self._parse("class Empty {}", tmp_path)
        assert skeleton is not None
        assert len(skeleton.classes) == 1
        assert skeleton.classes[0].name == "Empty"
        assert skeleton.classes[0].methods == []
        assert skeleton.classes[0].bases == []

    def test_class_with_extends(self, tmp_path):
        skeleton = self._parse("class Child extends Parent {}", tmp_path)
        assert skeleton is not None
        assert skeleton.classes[0].bases == ["Parent"]

    def test_class_constructor(self, tmp_path):
        skeleton = self._parse("class Foo { constructor(x) {} }", tmp_path)
        assert skeleton is not None
        methods = skeleton.classes[0].methods
        assert len(methods) == 1
        assert methods[0].name == "constructor"
        assert methods[0].is_method is True

    def test_class_static_method(self, tmp_path):
        skeleton = self._parse("class Foo { static create() {} }", tmp_path)
        assert skeleton is not None
        m = skeleton.classes[0].methods[0]
        assert m.is_static is True

    def test_class_getter(self, tmp_path):
        skeleton = self._parse("class Foo { get value() {} }", tmp_path)
        assert skeleton is not None
        m = skeleton.classes[0].methods[0]
        assert m.is_property is True
        assert m.name == "value"


class TestExports:
    """Focused tests for export extraction."""

    def _parse(self, source: str, tmp_path: Path) -> ...:
        p = tmp_path / "test.js"
        p.write_text(source)
        return extract_interface(p)

    def test_named_export_function(self, tmp_path):
        skeleton = self._parse("export function greet() {}", tmp_path)
        assert skeleton is not None
        assert "greet" in skeleton.exports
        assert len(skeleton.functions) == 1

    def test_named_export_class(self, tmp_path):
        skeleton = self._parse("export class Foo {}", tmp_path)
        assert skeleton is not None
        assert "Foo" in skeleton.exports
        assert len(skeleton.classes) == 1

    def test_default_export_class(self, tmp_path):
        skeleton = self._parse("export default class App {}", tmp_path)
        assert skeleton is not None
        assert "App" in skeleton.exports

    def test_default_export_function(self, tmp_path):
        skeleton = self._parse("export default function main() {}", tmp_path)
        assert skeleton is not None
        assert "main" in skeleton.exports

    def test_export_clause(self, tmp_path):
        source = "function a() {}\nconst b = 1;\nexport { a, b };"
        skeleton = self._parse(source, tmp_path)
        assert skeleton is not None
        assert "a" in skeleton.exports
        assert "b" in skeleton.exports

    def test_export_const(self, tmp_path):
        skeleton = self._parse("export const FOO = 42;", tmp_path)
        assert skeleton is not None
        assert "FOO" in skeleton.exports
        assert any(c.name == "FOO" for c in skeleton.constants)

    def test_export_const_arrow(self, tmp_path):
        skeleton = self._parse("export const handler = (req) => {};", tmp_path)
        assert skeleton is not None
        assert "handler" in skeleton.exports
        assert any(f.name == "handler" for f in skeleton.functions)

    def test_commonjs_module_exports_object(self, tmp_path):
        source = "function foo() {}\nmodule.exports = { foo, bar };"
        skeleton = self._parse(source, tmp_path)
        assert skeleton is not None
        assert "foo" in skeleton.exports
        assert "bar" in skeleton.exports

    def test_commonjs_module_exports_identifier(self, tmp_path):
        source = "class MyClass {}\nmodule.exports = MyClass;"
        skeleton = self._parse(source, tmp_path)
        assert skeleton is not None
        assert "MyClass" in skeleton.exports

    def test_commonjs_module_exports_property(self, tmp_path):
        source = "function baz() {}\nmodule.exports.baz = baz;"
        skeleton = self._parse(source, tmp_path)
        assert skeleton is not None
        assert "baz" in skeleton.exports

    def test_commonjs_exports_property(self, tmp_path):
        source = "function qux() {}\nexports.qux = qux;"
        skeleton = self._parse(source, tmp_path)
        assert skeleton is not None
        assert "qux" in skeleton.exports


class TestEdgeCases:
    """Edge cases and error handling."""

    def _parse(self, source: str, tmp_path: Path) -> ...:
        p = tmp_path / "test.js"
        p.write_text(source)
        return extract_interface(p)

    def test_empty_file(self, tmp_path):
        skeleton = self._parse("", tmp_path)
        assert skeleton is not None
        assert skeleton.functions == []
        assert skeleton.classes == []
        assert skeleton.constants == []
        assert skeleton.exports == []

    def test_syntax_error_partial_extraction(self, tmp_path):
        """Even with a syntax error, partial results should be returned."""
        source = "function valid(x) {}\nfunction broken( {}\n"
        skeleton = self._parse(source, tmp_path)
        assert skeleton is not None
        # At least the valid function should be extracted
        func_names = {f.name for f in skeleton.functions}
        assert "valid" in func_names

    def test_nonexistent_file(self, tmp_path):
        result = extract_interface(tmp_path / "does_not_exist.js")
        assert result is None

    def test_unsupported_extension(self, tmp_path):
        p = tmp_path / "test.rb"
        p.write_text("def foo; end")
        result = extract_interface(p)
        assert result is None

    def test_jsx_extension_works(self, tmp_path):
        p = tmp_path / "test.jsx"
        p.write_text("function App() { return <div />; }")
        skeleton = extract_interface(p)
        assert skeleton is not None
        assert skeleton.language == "javascript"
        assert len(skeleton.functions) == 1
        assert skeleton.functions[0].name == "App"

    def test_file_path_in_skeleton(self, tmp_path):
        p = tmp_path / "test.js"
        p.write_text("const x = 1;")
        skeleton = extract_interface(p)
        assert skeleton is not None
        assert skeleton.file_path == str(p)
