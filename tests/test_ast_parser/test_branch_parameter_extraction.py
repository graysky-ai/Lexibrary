"""Tests for branch parameter extraction from Python, TypeScript, and JavaScript parsers."""

from __future__ import annotations

from pathlib import Path

from lexibrary.ast_parser.javascript_parser import extract_symbols as extract_symbols_js
from lexibrary.ast_parser.python_parser import extract_symbols as extract_symbols_py
from lexibrary.ast_parser.typescript_parser import extract_symbols as extract_symbols_ts

FIXTURES = Path(__file__).parent / "fixtures" / "branch_parameters"


# ---------------------------------------------------------------------------
# Python branch parameter extraction
# ---------------------------------------------------------------------------


class TestPythonBranchParameters:
    """Test branch parameter extraction from Python source files."""

    def test_python_if_branch_parameter(self) -> None:
        """A parameter used in an ``if`` condition is recorded."""
        result = extract_symbols_py(FIXTURES / "python_simple.py")
        assert result is not None

        fn = next(d for d in result.definitions if d.name == "process")
        assert fn.branch_parameters == ["flag"]

    def test_python_attribute_access_records_root_name(self) -> None:
        """Attribute access ``config.verbose`` records the root name ``config``."""
        result = extract_symbols_py(FIXTURES / "python_attribute_access.py")
        assert result is not None

        fn = next(d for d in result.definitions if d.name == "render")
        assert fn.branch_parameters == ["config"]

    def test_python_match_subject(self) -> None:
        """A parameter used as a ``match`` subject is recorded."""
        result = extract_symbols_py(FIXTURES / "python_match.py")
        assert result is not None

        fn = next(d for d in result.definitions if d.name == "handle")
        assert fn.branch_parameters == ["action"]

    def test_python_nested_function_isolated(self) -> None:
        """A parameter used only in a nested function's branch is NOT on the outer function."""
        result = extract_symbols_py(FIXTURES / "python_nested_function.py")
        assert result is not None

        outer = next(d for d in result.definitions if d.name == "outer")
        # ``mode`` is used in ``inner``'s if, not directly in ``outer``'s body.
        assert "mode" not in outer.branch_parameters

    def test_python_assert_excluded(self) -> None:
        """A parameter appearing only in an ``assert`` is NOT a branch parameter."""
        result = extract_symbols_py(FIXTURES / "python_assert_only.py")
        assert result is not None

        fn = next(d for d in result.definitions if d.name == "validate")
        assert "expected" not in fn.branch_parameters

    def test_python_self_excluded(self) -> None:
        """``self`` is never recorded as a branch parameter."""
        result = extract_symbols_py(FIXTURES / "python_self_excluded.py")
        assert result is not None

        fn = next(d for d in result.definitions if d.name == "run")
        assert "self" not in fn.branch_parameters


# ---------------------------------------------------------------------------
# TypeScript branch parameter extraction
# ---------------------------------------------------------------------------


class TestTypeScriptBranchParameters:
    """Test branch parameter extraction from TypeScript source files."""

    def test_ts_ternary_extracted(self) -> None:
        """A parameter used in a ternary condition is recorded."""
        result = extract_symbols_ts(FIXTURES / "ts_ternary.ts")
        assert result is not None

        fn = next(d for d in result.definitions if d.name == "format")
        assert fn.branch_parameters == ["uppercase"]

    def test_ts_switch_subject(self) -> None:
        """A parameter used as a ``switch`` subject is recorded."""
        result = extract_symbols_ts(FIXTURES / "ts_switch.ts")
        assert result is not None

        fn = next(d for d in result.definitions if d.name == "dispatch")
        assert fn.branch_parameters == ["action"]

    def test_ts_nested_function_gets_own_branch_parameters(self) -> None:
        """A nested function has its own branch_parameters list."""
        result = extract_symbols_ts(FIXTURES / "ts_nested_function.ts")
        assert result is not None

        inner_defs = [d for d in result.definitions if d.name == "inner"]
        assert len(inner_defs) >= 1
        inner = inner_defs[0]
        assert inner.branch_parameters == ["flag"]

    def test_ts_nested_function_emitted_as_separate_symbol(self) -> None:
        """A nested function inside a function body is emitted as its own SymbolDefinition."""
        result = extract_symbols_ts(FIXTURES / "ts_nested_function.ts")
        assert result is not None

        names = [d.name for d in result.definitions]
        assert "outer" in names
        assert "inner" in names

        inner = next(d for d in result.definitions if d.name == "inner")
        assert inner.visibility == "private"
        assert ".<locals>." in inner.qualified_name


# ---------------------------------------------------------------------------
# JavaScript branch parameter extraction
# ---------------------------------------------------------------------------


class TestJavaScriptBranchParameters:
    """Test branch parameter extraction from JavaScript source files."""

    def test_js_for_loop_condition(self) -> None:
        """A parameter used in a ``for`` loop condition is recorded."""
        result = extract_symbols_js(FIXTURES / "js_for_loop.js")
        assert result is not None

        fn = next(d for d in result.definitions if d.name == "processItems")
        assert "limit" in fn.branch_parameters


# ---------------------------------------------------------------------------
# Cross-language: no-branch functions
# ---------------------------------------------------------------------------


class TestNoBranches:
    """Functions without any branch conditions should return an empty list."""

    def test_function_with_no_branches_returns_empty_list(self) -> None:
        """A simple function with no if/while/match/ternary returns empty branch_parameters."""
        result = extract_symbols_py(FIXTURES / "python_no_branches.py")
        assert result is not None

        fn = next(d for d in result.definitions if d.name == "add")
        assert fn.branch_parameters == []
