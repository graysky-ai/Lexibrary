"""Tests for ``ClassEdgeSite`` extraction in the AST parsers.

Covers the Python, TypeScript and JavaScript parsers. Fixture files live
under ``tests/test_ast_parser/fixtures/classes/`` so the tests stay
deterministic regardless of tree-sitter grammar availability.

Two kinds of edges are exercised:

- ``inherits``: every ``class <Name>(Base):`` / ``extends``/``implements``
  clause produces an ``inherits`` edge (``implements`` is modelled as
  ``inherits`` in the TS parser).
- ``instantiates``: PascalCase calls (Python) and bare-identifier
  ``new_expression`` constructors (TS/JS) produce an ``instantiates``
  edge attributed to the innermost enclosing definition.

Two Python fixtures — ``underscore_class.py`` and
``aliased_instantiation.py`` — are negative-case anchors that pin the
documented parser limitations (PascalCase heuristic cannot see
``_Config()`` or ``cls = MyClass; cls()``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lexibrary.ast_parser import extract_symbols
from lexibrary.ast_parser.models import ClassEdgeSite
from lexibrary.ast_parser.registry import get_parser

FIXTURES = Path(__file__).parent / "fixtures" / "classes"
REPO_ROOT = Path(__file__).resolve().parents[2]

_EXPECTED_MODULE = "tests.test_ast_parser.fixtures.classes"


def _skip_if_no_python_grammar() -> None:
    if get_parser(".py") is None:
        pytest.skip("tree-sitter Python grammar not available")


def _skip_if_no_ts_grammar() -> None:
    if get_parser(".ts") is None:
        pytest.skip("tree-sitter TypeScript grammar not available")


def _skip_if_no_js_grammar() -> None:
    if get_parser(".js") is None:
        pytest.skip("tree-sitter JavaScript grammar not available")


def _edges_by_type(edges: list[ClassEdgeSite]) -> dict[str, list[ClassEdgeSite]]:
    mapping: dict[str, list[ClassEdgeSite]] = {}
    for edge in edges:
        mapping.setdefault(edge.edge_type, []).append(edge)
    return mapping


# ---------------------------------------------------------------------------
# Python — inherits
# ---------------------------------------------------------------------------


def test_python_single_inheritance() -> None:
    _skip_if_no_python_grammar()
    extract = extract_symbols(
        FIXTURES / "single_inheritance.py",
        project_root=REPO_ROOT,
    )
    assert extract is not None

    edges = extract.class_edges
    assert len(edges) == 1
    edge = edges[0]
    assert edge.edge_type == "inherits"
    assert edge.target_name == "Animal"
    assert edge.source_name == f"{_EXPECTED_MODULE}.single_inheritance.Dog"
    assert edge.line == 8  # ``class Dog(Animal):`` on line 8 in the fixture.


def test_python_multi_inheritance() -> None:
    _skip_if_no_python_grammar()
    extract = extract_symbols(
        FIXTURES / "multi_inheritance.py",
        project_root=REPO_ROOT,
    )
    assert extract is not None

    edges = [e for e in extract.class_edges if e.edge_type == "inherits"]
    # ``class M(A, B, C):`` emits three inherits edges, one per base.
    m_qualified = f"{_EXPECTED_MODULE}.multi_inheritance.M"
    m_edges = [e for e in edges if e.source_name == m_qualified]
    assert len(m_edges) == 3
    assert {e.target_name for e in m_edges} == {"A", "B", "C"}
    assert all(e.line == 16 for e in m_edges)


def test_python_generic_base_collapses_subscript() -> None:
    _skip_if_no_python_grammar()
    extract = extract_symbols(
        FIXTURES / "generic_base.py",
        project_root=REPO_ROOT,
    )
    assert extract is not None

    # ``class Foo(Generic[T]):`` should emit a single inherits edge whose
    # target is the bare ``Generic`` identifier, not ``Generic[T]``.
    inherits = [e for e in extract.class_edges if e.edge_type == "inherits"]
    foo_qualified = f"{_EXPECTED_MODULE}.generic_base.Foo"
    foo_edges = [e for e in inherits if e.source_name == foo_qualified]
    assert len(foo_edges) == 1
    assert foo_edges[0].target_name == "Generic"


def test_python_pydantic_base() -> None:
    _skip_if_no_python_grammar()
    extract = extract_symbols(
        FIXTURES / "pydantic_base.py",
        project_root=REPO_ROOT,
    )
    assert extract is not None

    inherits = [e for e in extract.class_edges if e.edge_type == "inherits"]
    assert len(inherits) == 1
    edge = inherits[0]
    assert edge.target_name == "BaseModel"
    assert edge.source_name == f"{_EXPECTED_MODULE}.pydantic_base.X"


# ---------------------------------------------------------------------------
# Python — instantiates
# ---------------------------------------------------------------------------


def test_python_instantiates_pascal_case_only() -> None:
    _skip_if_no_python_grammar()
    extract = extract_symbols(
        FIXTURES / "instantiations.py",
        project_root=REPO_ROOT,
    )
    assert extract is not None

    # ``Builder()`` matches the PascalCase heuristic; ``process_data()`` does
    # not. Only one instantiates edge is expected.
    inst_edges = [e for e in extract.class_edges if e.edge_type == "instantiates"]
    assert len(inst_edges) == 1
    edge = inst_edges[0]
    assert edge.target_name == "Builder"
    assert edge.source_name == f"{_EXPECTED_MODULE}.instantiations.build_thing"
    # ``Builder()`` call lives on line 9 of the fixture file.
    assert edge.line == 9


def test_python_instantiates_underscore_class_not_emitted() -> None:
    """Known limitation: leading-underscore classes are invisible to the heuristic."""
    _skip_if_no_python_grammar()
    extract = extract_symbols(
        FIXTURES / "underscore_class.py",
        project_root=REPO_ROOT,
    )
    assert extract is not None

    # ``_Config()`` fails the ``^[A-Z]`` PascalCase check, so no
    # instantiates edge is emitted. The ``class _Config:`` has no bases
    # so no inherits edges either.
    assert extract.class_edges == []


def test_python_instantiates_aliased_not_emitted() -> None:
    """Known limitation: aliased class names hide from the PascalCase regex."""
    _skip_if_no_python_grammar()
    extract = extract_symbols(
        FIXTURES / "aliased_instantiation.py",
        project_root=REPO_ROOT,
    )
    assert extract is not None

    # ``cls = MyClass`` then ``cls()`` — ``cls`` is lowercase so the
    # heuristic ignores it. No instantiates edge is emitted.
    instantiates = [e for e in extract.class_edges if e.edge_type == "instantiates"]
    assert instantiates == []


# ---------------------------------------------------------------------------
# TypeScript
# ---------------------------------------------------------------------------


def test_typescript_extends_and_implements() -> None:
    _skip_if_no_ts_grammar()
    extract = extract_symbols(FIXTURES / "ts_extends.ts")
    assert extract is not None

    # ``class Dog extends Animal implements Walker {}`` emits two
    # inherits edges — both ``extends`` and ``implements`` are modelled
    # as ``inherits`` in the symbol graph.
    inherits = [e for e in extract.class_edges if e.edge_type == "inherits"]
    dog_qualified = "ts_extends.Dog"
    dog_edges = [e for e in inherits if e.source_name == dog_qualified]
    assert len(dog_edges) == 2
    assert {e.target_name for e in dog_edges} == {"Animal", "Walker"}


# ---------------------------------------------------------------------------
# JavaScript
# ---------------------------------------------------------------------------


def test_javascript_new_expression_emits_instantiates() -> None:
    _skip_if_no_js_grammar()
    extract = extract_symbols(FIXTURES / "js_new_expression.js")
    assert extract is not None

    instantiates = [e for e in extract.class_edges if e.edge_type == "instantiates"]
    # ``main`` calls ``new A()`` and ``new B()`` — two edges.
    main_qualified = "js_new_expression.main"
    main_edges = [e for e in instantiates if e.source_name == main_qualified]
    assert len(main_edges) == 2
    assert {e.target_name for e in main_edges} == {"A", "B"}


# ---------------------------------------------------------------------------
# Shape sanity
# ---------------------------------------------------------------------------


def test_python_edge_shape_round_trip() -> None:
    _skip_if_no_python_grammar()
    extract = extract_symbols(
        FIXTURES / "single_inheritance.py",
        project_root=REPO_ROOT,
    )
    assert extract is not None
    # model_dump keeps the edges serializable so downstream builders can
    # cache SymbolExtract blobs on disk without special-casing edges.
    dumped = extract.model_dump()
    assert isinstance(dumped["class_edges"], list)
    assert dumped["class_edges"][0]["edge_type"] == "inherits"
    assert dumped["class_edges"][0]["target_name"] == "Animal"
