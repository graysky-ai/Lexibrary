"""Tests for the grammar registry module."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from lexibrary.ast_parser.registry import (
    GRAMMAR_MAP,
    clear_caches,
    get_grammar_info,
    get_language,
    get_parser,
    get_supported_extensions,
)


@pytest.fixture(autouse=True)
def _clean_registry() -> None:  # type: ignore[misc]
    """Clear registry caches before and after each test."""
    clear_caches()
    yield  # type: ignore[misc]
    clear_caches()


# --- Extension mapping tests ---


class TestGrammarMap:
    """Tests for the extension-to-grammar mapping."""

    def test_python_extension_mapped(self) -> None:
        info = get_grammar_info(".py")
        assert info is not None
        assert info.language_name == "python"
        assert info.module_name == "tree_sitter_python"

    def test_pyi_extension_mapped(self) -> None:
        info = get_grammar_info(".pyi")
        assert info is not None
        assert info.language_name == "python"
        assert info.module_name == "tree_sitter_python"

    def test_typescript_extension_mapped(self) -> None:
        info = get_grammar_info(".ts")
        assert info is not None
        assert info.language_name == "typescript"
        assert info.module_name == "tree_sitter_typescript"

    def test_tsx_extension_mapped(self) -> None:
        info = get_grammar_info(".tsx")
        assert info is not None
        assert info.language_name == "tsx"
        assert info.module_name == "tree_sitter_typescript"

    def test_javascript_extension_mapped(self) -> None:
        info = get_grammar_info(".js")
        assert info is not None
        assert info.language_name == "javascript"
        assert info.module_name == "tree_sitter_javascript"

    def test_jsx_extension_mapped(self) -> None:
        info = get_grammar_info(".jsx")
        assert info is not None
        assert info.language_name == "javascript"
        assert info.module_name == "tree_sitter_javascript"

    def test_unknown_extension_returns_none(self) -> None:
        assert get_grammar_info(".rs") is None
        assert get_grammar_info(".go") is None
        assert get_grammar_info(".java") is None
        assert get_grammar_info("") is None

    def test_all_six_extensions_present(self) -> None:
        expected = {".py", ".pyi", ".ts", ".tsx", ".js", ".jsx"}
        assert expected == set(GRAMMAR_MAP.keys())

    def test_get_supported_extensions_sorted(self) -> None:
        extensions = get_supported_extensions()
        assert extensions == sorted(extensions)
        assert len(extensions) == 6


# --- Grammar loading tests ---


class TestGrammarLoading:
    """Tests that grammars actually load and produce working parsers."""

    def test_python_grammar_loads(self) -> None:
        lang = get_language(".py")
        assert lang is not None

    def test_python_parser_creates(self) -> None:
        parser = get_parser(".py")
        assert parser is not None

    def test_python_parser_parses_code(self) -> None:
        parser = get_parser(".py")
        assert parser is not None
        tree = parser.parse(b"def foo(x: int) -> str: return str(x)")
        assert tree is not None
        assert tree.root_node.type == "module"
        assert not tree.root_node.has_error

    def test_typescript_grammar_loads(self) -> None:
        lang = get_language(".ts")
        assert lang is not None

    def test_typescript_parser_parses_code(self) -> None:
        parser = get_parser(".ts")
        assert parser is not None
        tree = parser.parse(b"function greet(name: string): string { return name; }")
        assert tree is not None
        assert tree.root_node.type == "program"
        assert not tree.root_node.has_error

    def test_tsx_grammar_loads(self) -> None:
        lang = get_language(".tsx")
        assert lang is not None

    def test_tsx_parser_parses_jsx(self) -> None:
        parser = get_parser(".tsx")
        assert parser is not None
        tree = parser.parse(b"const App = (): JSX.Element => <div>hello</div>;")
        assert tree is not None
        assert tree.root_node.type == "program"
        assert not tree.root_node.has_error

    def test_javascript_grammar_loads(self) -> None:
        lang = get_language(".js")
        assert lang is not None

    def test_javascript_parser_parses_code(self) -> None:
        parser = get_parser(".js")
        assert parser is not None
        tree = parser.parse(b"function foo() { return 1; }")
        assert tree is not None
        assert tree.root_node.type == "program"
        assert not tree.root_node.has_error

    def test_jsx_uses_javascript_grammar(self) -> None:
        """JSX files use tree-sitter-javascript which handles JSX natively."""
        parser = get_parser(".jsx")
        assert parser is not None
        tree = parser.parse(b"const App = () => <div>hello</div>;")
        assert tree is not None
        assert tree.root_node.type == "program"
        assert not tree.root_node.has_error

    def test_pyi_uses_python_grammar(self) -> None:
        parser = get_parser(".pyi")
        assert parser is not None
        tree = parser.parse(b"def foo(x: int) -> str: ...")
        assert tree is not None
        assert not tree.root_node.has_error


# --- Caching tests ---


class TestCaching:
    """Tests that Language and Parser objects are cached."""

    def test_language_is_cached(self) -> None:
        lang1 = get_language(".py")
        lang2 = get_language(".py")
        assert lang1 is lang2

    def test_parser_is_cached(self) -> None:
        parser1 = get_parser(".py")
        parser2 = get_parser(".py")
        assert parser1 is parser2

    def test_py_and_pyi_share_cache(self) -> None:
        """Both .py and .pyi use the same Python grammar."""
        parser_py = get_parser(".py")
        parser_pyi = get_parser(".pyi")
        assert parser_py is parser_pyi

    def test_js_and_jsx_share_cache(self) -> None:
        """Both .js and .jsx use the same JavaScript grammar."""
        parser_js = get_parser(".js")
        parser_jsx = get_parser(".jsx")
        assert parser_js is parser_jsx

    def test_clear_caches_resets(self) -> None:
        _ = get_parser(".py")
        clear_caches()
        # After clear, a fresh load should still work
        parser = get_parser(".py")
        assert parser is not None


# --- Graceful fallback tests ---


class TestGracefulFallback:
    """Tests for behavior when grammar packages are not installed."""

    def test_missing_grammar_returns_none_for_language(self) -> None:
        with patch("lexibrary.ast_parser.registry.importlib") as mock_importlib:
            mock_importlib.import_module.side_effect = ImportError("no module")
            lang = get_language(".py")
            assert lang is None

    def test_missing_grammar_returns_none_for_parser(self) -> None:
        with patch("lexibrary.ast_parser.registry.importlib") as mock_importlib:
            mock_importlib.import_module.side_effect = ImportError("no module")
            parser = get_parser(".py")
            assert parser is None

    def test_unknown_extension_returns_none_for_language(self) -> None:
        assert get_language(".rs") is None

    def test_unknown_extension_returns_none_for_parser(self) -> None:
        assert get_parser(".rs") is None

    def test_warning_emitted_once_per_language(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Warning for missing grammar should only be printed once per language."""
        with patch("lexibrary.ast_parser.registry.importlib") as mock_importlib:
            mock_importlib.import_module.side_effect = ImportError("no module")

            # First call: should warn
            get_language(".py")
            # Second call: should not warn again
            get_language(".py")
            # Third call via .pyi (same language): should not warn again
            get_language(".pyi")

        # We can't easily capture rich console output to stderr in tests,
        # but we can verify the warned set contains the language
        from lexibrary.ast_parser.registry import _warned_languages

        assert "python" in _warned_languages

    def test_warning_not_emitted_for_unknown_extension(self) -> None:
        """No warning should be emitted for unsupported extensions."""
        get_language(".rs")
        from lexibrary.ast_parser.registry import _warned_languages

        assert len(_warned_languages) == 0


# --- TypeScript/TSX independence tests ---


class TestTypeScriptTSXIndependence:
    """Verify that TypeScript and TSX are separate grammars loaded independently."""

    def test_ts_and_tsx_are_different_languages(self) -> None:
        ts_lang = get_language(".ts")
        tsx_lang = get_language(".tsx")
        assert ts_lang is not None
        assert tsx_lang is not None
        # They should be different Language objects
        assert ts_lang is not tsx_lang

    def test_ts_and_tsx_are_different_parsers(self) -> None:
        ts_parser = get_parser(".ts")
        tsx_parser = get_parser(".tsx")
        assert ts_parser is not None
        assert tsx_parser is not None
        assert ts_parser is not tsx_parser
