"""Tests for ``extract_symbols`` across Python, TypeScript, and JavaScript.

Covers symbol definition walks (including nested functions and ``super()``
chains) and call-site extraction for every shape the tests/plan calls out:
free-function calls, ``self.<method>``, attribute calls, and the
``super().foo()`` special case. Each language gets a minimal fixture under
``tests/test_ast_parser/fixtures/calls/``.

Fixture files are checked into the repo so the tests stay deterministic
regardless of tree-sitter grammar availability (missing grammars skip).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lexibrary.ast_parser import extract_symbols
from lexibrary.ast_parser.models import CallSite, SymbolDefinition
from lexibrary.ast_parser.python_parser import (
    extract_symbols as extract_symbols_py,
)
from lexibrary.ast_parser.registry import get_parser

FIXTURES = Path(__file__).parent / "fixtures" / "calls"
REPO_ROOT = Path(__file__).resolve().parents[2]

_EXPECTED_MODULE = "tests.test_ast_parser.fixtures.calls"


def _skip_if_no_python_grammar() -> None:
    if get_parser(".py") is None:
        pytest.skip("tree-sitter Python grammar not available")


def _skip_if_no_ts_grammar() -> None:
    if get_parser(".ts") is None:
        pytest.skip("tree-sitter TypeScript grammar not available")


def _skip_if_no_js_grammar() -> None:
    if get_parser(".js") is None:
        pytest.skip("tree-sitter JavaScript grammar not available")


def _by_qualified_name(defs: list[SymbolDefinition]) -> dict[str, SymbolDefinition]:
    return {d.qualified_name: d for d in defs}


def _by_name(defs: list[SymbolDefinition]) -> dict[str, SymbolDefinition]:
    return {d.name: d for d in defs}


def _calls_by_callee(calls: list[CallSite]) -> dict[str, list[CallSite]]:
    mapping: dict[str, list[CallSite]] = {}
    for call in calls:
        mapping.setdefault(call.callee_name, []).append(call)
    return mapping


# ---------------------------------------------------------------------------
# 1. simple_calls.py
# ---------------------------------------------------------------------------


def test_extract_symbols_simple_calls_py() -> None:
    _skip_if_no_python_grammar()
    extract = extract_symbols(
        FIXTURES / "simple_calls.py",
        project_root=REPO_ROOT,
    )
    assert extract is not None
    assert extract.language == "python"

    by_name = _by_name(extract.definitions)
    assert set(by_name) == {"callee", "caller"}
    assert all(d.symbol_type == "function" for d in extract.definitions)
    assert all(d.visibility == "public" for d in extract.definitions)
    assert by_name["callee"].qualified_name == f"{_EXPECTED_MODULE}.simple_calls.callee"
    assert by_name["caller"].qualified_name == f"{_EXPECTED_MODULE}.simple_calls.caller"

    assert len(extract.calls) == 1
    call = extract.calls[0]
    assert call.callee_name == "callee"
    assert call.receiver is None
    assert call.is_method_call is False
    assert call.caller_name == by_name["caller"].qualified_name
    # Line 9 in the fixture: ``return callee() + 1``.
    assert call.line == 9


# ---------------------------------------------------------------------------
# 2. class_methods.py — self.bar and helper free call
# ---------------------------------------------------------------------------


def test_extract_symbols_self_method_py() -> None:
    _skip_if_no_python_grammar()
    extract = extract_symbols(
        FIXTURES / "class_methods.py",
        project_root=REPO_ROOT,
    )
    assert extract is not None

    by_qn = _by_qualified_name(extract.definitions)
    example_foo_qn = f"{_EXPECTED_MODULE}.class_methods.Example.foo"
    example_bar_qn = f"{_EXPECTED_MODULE}.class_methods.Example.bar"
    helper_qn = f"{_EXPECTED_MODULE}.class_methods.helper"
    assert example_foo_qn in by_qn
    assert example_bar_qn in by_qn
    assert helper_qn in by_qn

    # Method metadata
    foo_def = by_qn[example_foo_qn]
    assert foo_def.symbol_type == "method"
    assert foo_def.parent_class == "Example"
    assert foo_def.visibility == "public"

    foo_calls = [c for c in extract.calls if c.caller_name == example_foo_qn]
    callees = _calls_by_callee(foo_calls)
    # helper() free call inside foo
    assert "helper" in callees
    helper_call = callees["helper"][0]
    assert helper_call.receiver is None
    assert helper_call.is_method_call is False
    # self.bar() attribute call
    assert "self.bar" in callees
    self_bar = callees["self.bar"][0]
    assert self_bar.receiver == "self"
    assert self_bar.is_method_call is True


# ---------------------------------------------------------------------------
# 3. attribute_calls.py
# ---------------------------------------------------------------------------


def test_extract_symbols_attribute_calls_py() -> None:
    _skip_if_no_python_grammar()
    extract = extract_symbols(
        FIXTURES / "attribute_calls.py",
        project_root=REPO_ROOT,
    )
    assert extract is not None

    by_name = _by_name(extract.definitions)
    assert "run" in by_name
    assert "find" in by_name  # static method on ConceptIndex

    run_qn = by_name["run"].qualified_name
    run_calls = [c for c in extract.calls if c.caller_name == run_qn]
    by_callee = _calls_by_callee(run_calls)

    # logging.getLogger(__name__)
    assert "logging.getLogger" in by_callee
    logging_call = by_callee["logging.getLogger"][0]
    assert logging_call.receiver == "logging"
    assert logging_call.is_method_call is True

    # logger.info("starting")
    assert "logger.info" in by_callee
    info_call = by_callee["logger.info"][0]
    assert info_call.receiver == "logger"
    assert info_call.is_method_call is True

    # ConceptIndex.find("x")
    assert "ConceptIndex.find" in by_callee
    ci_call = by_callee["ConceptIndex.find"][0]
    assert ci_call.receiver == "ConceptIndex"
    assert ci_call.is_method_call is True

    # os.path.join("a", "b") — receiver text is the multi-segment ``os.path``.
    assert "os.path.join" in by_callee
    os_call = by_callee["os.path.join"][0]
    assert os_call.receiver == "os.path"
    assert os_call.is_method_call is True


# ---------------------------------------------------------------------------
# 4. nested_calls.py — inner def captured; inner-body calls attributed
# ---------------------------------------------------------------------------


def test_extract_symbols_nested_functions_py() -> None:
    _skip_if_no_python_grammar()
    extract = extract_symbols(
        FIXTURES / "nested_calls.py",
        project_root=REPO_ROOT,
    )
    assert extract is not None

    by_qn = _by_qualified_name(extract.definitions)
    outer_qn = f"{_EXPECTED_MODULE}.nested_calls.Outer.method"
    inner_qn = f"{outer_qn}.<locals>.inner"
    assert outer_qn in by_qn, f"outer method missing. Seen: {sorted(by_qn)}"
    assert inner_qn in by_qn, f"inner nested function missing. Seen: {sorted(by_qn)}"
    # Nested def must be visibility='private'.
    assert by_qn[inner_qn].visibility == "private"
    assert by_qn[inner_qn].symbol_type == "function"

    # helper() call sits inside the inner body and must be attributed to inner.
    helper_calls = [c for c in extract.calls if c.callee_name == "helper"]
    assert len(helper_calls) == 1
    assert helper_calls[0].caller_name == inner_qn

    # inner() call sits inside method but outside inner — attributed to method.
    inner_invocations = [c for c in extract.calls if c.callee_name == "inner"]
    assert len(inner_invocations) == 1
    assert inner_invocations[0].caller_name == outer_qn


# ---------------------------------------------------------------------------
# 5. super_call.py
# ---------------------------------------------------------------------------


def test_extract_symbols_super_call_py() -> None:
    _skip_if_no_python_grammar()
    extract = extract_symbols(
        FIXTURES / "super_call.py",
        project_root=REPO_ROOT,
    )
    assert extract is not None

    b_foo_qn = f"{_EXPECTED_MODULE}.super_call.B.foo"
    super_calls = [
        c for c in extract.calls if c.callee_name == "super.foo" and c.caller_name == b_foo_qn
    ]
    assert len(super_calls) == 1, f"expected one super.foo call, got {extract.calls}"
    super_call = super_calls[0]
    assert super_call.receiver == "super"
    assert super_call.is_method_call is True

    # Bare ``super`` must NOT be emitted as an additional free call.
    assert not any(c.callee_name == "super" for c in extract.calls)


# ---------------------------------------------------------------------------
# 6. simple_calls.ts
# ---------------------------------------------------------------------------


def test_extract_symbols_ts_simple() -> None:
    _skip_if_no_ts_grammar()
    extract = extract_symbols(FIXTURES / "simple_calls.ts")
    assert extract is not None
    assert extract.language == "typescript"

    names = {d.name for d in extract.definitions}
    assert names == {"callee", "caller"}

    caller_def = next(d for d in extract.definitions if d.name == "caller")
    assert len(extract.calls) == 1
    call = extract.calls[0]
    assert call.callee_name == "callee"
    assert call.receiver is None
    assert call.caller_name == caller_def.qualified_name


# ---------------------------------------------------------------------------
# 7. simple_calls.js
# ---------------------------------------------------------------------------


def test_extract_symbols_js_simple() -> None:
    _skip_if_no_js_grammar()
    extract = extract_symbols(FIXTURES / "simple_calls.js")
    assert extract is not None
    assert extract.language == "javascript"

    names = {d.name for d in extract.definitions}
    assert names == {"callee", "caller"}

    caller_def = next(d for d in extract.definitions if d.name == "caller")
    assert len(extract.calls) == 1
    call = extract.calls[0]
    assert call.callee_name == "callee"
    assert call.receiver is None
    assert call.caller_name == caller_def.qualified_name


# ---------------------------------------------------------------------------
# 8. Missing grammar returns None
# ---------------------------------------------------------------------------


def test_extract_symbols_missing_grammar_returns_none(tmp_path: Path) -> None:
    fake = tmp_path / "mystery.abc"
    fake.write_text("whatever\n", encoding="utf-8")
    assert extract_symbols(fake) is None


# ---------------------------------------------------------------------------
# 9. Qualified-name builder: src/ and tests/ paths
# ---------------------------------------------------------------------------


def test_qualified_name_python(tmp_path: Path) -> None:
    _skip_if_no_python_grammar()
    # src-layout file
    src_file = tmp_path / "src" / "pkg" / "module.py"
    src_file.parent.mkdir(parents=True)
    src_file.write_text("def alpha() -> int:\n    return 1\n", encoding="utf-8")

    extract = extract_symbols_py(src_file, project_root=tmp_path)
    assert extract is not None
    by_name = _by_name(extract.definitions)
    assert by_name["alpha"].qualified_name == "pkg.module.alpha"

    # tests/ layout file (flat layout under project_root)
    test_file = tmp_path / "tests" / "pkg" / "test_something.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("def beta() -> int:\n    return 2\n", encoding="utf-8")

    extract = extract_symbols_py(test_file, project_root=tmp_path)
    assert extract is not None
    by_name = _by_name(extract.definitions)
    assert by_name["beta"].qualified_name == "tests.pkg.test_something.beta"


# ---------------------------------------------------------------------------
# 10. Qualified-name format consistency with Block B
# ---------------------------------------------------------------------------


def test_qualified_name_format_consistency(tmp_path: Path) -> None:
    _skip_if_no_python_grammar()
    project_root = tmp_path
    pipeline_path = project_root / "src" / "lexibrary" / "archivist" / "pipeline.py"
    pipeline_path.parent.mkdir(parents=True)
    pipeline_path.write_text(
        """\
from __future__ import annotations


def update_project() -> int:
    def _scan_files() -> int:
        return 0

    return _scan_files()


class Builder:
    def full_build(self) -> int:
        return 42
""",
        encoding="utf-8",
    )

    extract = extract_symbols_py(pipeline_path, project_root=project_root)
    assert extract is not None
    by_qn = _by_qualified_name(extract.definitions)

    assert "lexibrary.archivist.pipeline.update_project" in by_qn
    assert "lexibrary.archivist.pipeline.Builder" in by_qn
    assert "lexibrary.archivist.pipeline.Builder.full_build" in by_qn
    assert "lexibrary.archivist.pipeline.update_project.<locals>._scan_files" in by_qn
    nested_def = by_qn["lexibrary.archivist.pipeline.update_project.<locals>._scan_files"]
    assert nested_def.visibility == "private"
    assert nested_def.symbol_type == "function"
