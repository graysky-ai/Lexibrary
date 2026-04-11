"""Tests for enum and constant extraction from AST parsers.

Covers the Python, TypeScript, and JavaScript parsers' symbol-graph
pipelines where enum definitions (Python/TS only) and module-level
constants (all three languages) are emitted alongside regular
``SymbolDefinition`` entries.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lexibrary.ast_parser.javascript_parser import extract_symbols as extract_js_symbols
from lexibrary.ast_parser.models import EnumMemberSig, SymbolDefinition
from lexibrary.ast_parser.python_parser import extract_symbols as extract_py_symbols
from lexibrary.ast_parser.registry import get_parser
from lexibrary.ast_parser.typescript_parser import extract_symbols as extract_ts_symbols

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "enums"
REPO_ROOT = Path(__file__).resolve().parents[2]

_PY_ENUM_MODULE = "tests.test_ast_parser.fixtures.enums"


def _skip_if_no_python_grammar() -> None:
    if get_parser(".py") is None:
        pytest.skip("tree-sitter Python grammar not available")


def _find_definition(
    definitions: list[SymbolDefinition],
    qualified_name: str,
) -> SymbolDefinition | None:
    for definition in definitions:
        if definition.qualified_name == qualified_name:
            return definition
    return None


# ── Python ──────────────────────────────────────────────────────────────────


class TestPythonEnumExtraction:
    """Python parser enum extraction.

    Fixtures live under ``tests/test_ast_parser/fixtures/enums``:

    - ``string_enum.py`` — ``class BuildStatus(StrEnum)`` with three string
      members.
    - ``int_enum.py`` — ``class Priority(IntEnum)`` with integer members.
    - ``auto_enum.py`` — ``class Mode(Enum)`` with ``auto()`` members whose
      ``value`` field must be ``None``.
    """

    def test_string_enum_members_extracted(self) -> None:
        """StrEnum subclasses emit ``symbol_type='enum'`` plus three members
        whose ``value`` is the raw quoted source text."""
        _skip_if_no_python_grammar()
        extract = extract_py_symbols(
            FIXTURES_DIR / "string_enum.py",
            project_root=REPO_ROOT,
        )
        assert extract is not None

        qualified = f"{_PY_ENUM_MODULE}.string_enum.BuildStatus"
        enum_def = _find_definition(extract.definitions, qualified)
        assert enum_def is not None
        assert enum_def.symbol_type == "enum"
        assert enum_def.visibility == "public"
        assert enum_def.name == "BuildStatus"

        assert len(extract.enums) == 1
        enum_qualified, members = extract.enums[0]
        assert enum_qualified == qualified
        assert [m.name for m in members] == ["PENDING", "RUNNING", "FAILED"]
        assert [m.ordinal for m in members] == [0, 1, 2]
        # Values include the surrounding quotes — raw RHS source text.
        assert members[0].value == '"pending"'
        assert members[1].value == '"running"'
        assert members[2].value == '"failed"'

        # EnumMemberSig round-trip: parser must emit validated Pydantic
        # instances, not plain dicts or tuples.
        for member in members:
            assert isinstance(member, EnumMemberSig)

    def test_int_enum_values_as_strings(self) -> None:
        """IntEnum member values are stored as string source text."""
        _skip_if_no_python_grammar()
        extract = extract_py_symbols(
            FIXTURES_DIR / "int_enum.py",
            project_root=REPO_ROOT,
        )
        assert extract is not None

        qualified = f"{_PY_ENUM_MODULE}.int_enum.Priority"
        enum_def = _find_definition(extract.definitions, qualified)
        assert enum_def is not None
        assert enum_def.symbol_type == "enum"

        assert len(extract.enums) == 1
        _, members = extract.enums[0]
        assert [m.name for m in members] == ["LOW", "HIGH"]
        assert members[0].value == "0"
        assert members[1].value == "10"
        assert [m.ordinal for m in members] == [0, 1]

    def test_auto_enum_values_are_none(self) -> None:
        """Members using ``auto()`` get ``value=None`` but valid ordinals."""
        _skip_if_no_python_grammar()
        extract = extract_py_symbols(
            FIXTURES_DIR / "auto_enum.py",
            project_root=REPO_ROOT,
        )
        assert extract is not None

        qualified = f"{_PY_ENUM_MODULE}.auto_enum.Mode"
        enum_def = _find_definition(extract.definitions, qualified)
        assert enum_def is not None
        assert enum_def.symbol_type == "enum"

        assert len(extract.enums) == 1
        _, members = extract.enums[0]
        assert [m.name for m in members] == ["READ", "WRITE"]
        assert [m.value for m in members] == [None, None]
        assert [m.ordinal for m in members] == [0, 1]


class TestPythonConstantExtraction:
    """Python parser module-level constant extraction.

    The ``constants.py`` fixture exercises all branches of the heuristic:
    ALL_CAPS without annotation, type-annotated non-ALL_CAPS,
    tuple-of-literals RHS, underscore-prefixed private constants, nested
    assignments (must NOT be extracted), and non-literal RHS (must NOT be
    extracted).
    """

    def test_module_constants_public_vs_private(self) -> None:
        """ALL_CAPS and type-annotated constants are extracted with the
        correct visibility: ``MAX_RETRIES`` is public, ``_PRIVATE`` is
        private."""
        _skip_if_no_python_grammar()
        extract = extract_py_symbols(
            FIXTURES_DIR / "constants.py",
            project_root=REPO_ROOT,
        )
        assert extract is not None

        names = {c.name for c in extract.constants}
        assert names == {
            "MAX_RETRIES",
            "DEFAULT_TIMEOUT",
            "SUPPORTED_EXTS",
            "_PRIVATE",
        }

        # Matching SymbolDefinition rows exist for each constant with the
        # correct symbol_type and visibility.
        max_retries_def = _find_definition(
            extract.definitions,
            f"{_PY_ENUM_MODULE}.constants.MAX_RETRIES",
        )
        assert max_retries_def is not None
        assert max_retries_def.symbol_type == "constant"
        assert max_retries_def.visibility == "public"

        private_def = _find_definition(
            extract.definitions,
            f"{_PY_ENUM_MODULE}.constants._PRIVATE",
        )
        assert private_def is not None
        assert private_def.symbol_type == "constant"
        assert private_def.visibility == "private"

        timeout_def = _find_definition(
            extract.definitions,
            f"{_PY_ENUM_MODULE}.constants.DEFAULT_TIMEOUT",
        )
        assert timeout_def is not None
        assert timeout_def.symbol_type == "constant"
        assert timeout_def.visibility == "public"

        # Raw source text round-trip: quotes and tuple brackets preserved.
        by_name = {c.name: c for c in extract.constants}
        assert by_name["MAX_RETRIES"].value == "3"
        assert by_name["MAX_RETRIES"].type_annotation is None
        assert by_name["DEFAULT_TIMEOUT"].value == "30.0"
        assert by_name["DEFAULT_TIMEOUT"].type_annotation == "float"
        assert by_name["SUPPORTED_EXTS"].value == '(".py", ".ts")'
        assert by_name["SUPPORTED_EXTS"].type_annotation is None
        assert by_name["_PRIVATE"].value == '"secret"'
        assert by_name["_PRIVATE"].type_annotation is None

    def test_multiline_constant_value_is_none(self) -> None:
        """A constant with a non-literal RHS must NOT be extracted.

        ``COMPUTED = _compute()`` is a function call, not a simple
        literal, so it should appear in neither ``extract.constants`` nor
        ``extract.definitions``.
        """
        _skip_if_no_python_grammar()
        extract = extract_py_symbols(
            FIXTURES_DIR / "constants.py",
            project_root=REPO_ROOT,
        )
        assert extract is not None

        constant_names = {c.name for c in extract.constants}
        assert "COMPUTED" not in constant_names

        computed_def = _find_definition(
            extract.definitions,
            f"{_PY_ENUM_MODULE}.constants.COMPUTED",
        )
        assert computed_def is None

    def test_nested_constant_not_extracted(self) -> None:
        """A constant-shaped assignment inside a function body is skipped.

        ``NESTED_VALUE = 42`` lives inside ``_compute``; the walker only
        descends from the module root, so nested assignments must never
        surface as ``ConstantValue`` or ``SymbolDefinition`` constants.
        """
        _skip_if_no_python_grammar()
        extract = extract_py_symbols(
            FIXTURES_DIR / "constants.py",
            project_root=REPO_ROOT,
        )
        assert extract is not None

        constant_names = {c.name for c in extract.constants}
        assert "NESTED_VALUE" not in constant_names

        for definition in extract.definitions:
            if definition.symbol_type == "constant":
                assert definition.name != "NESTED_VALUE"


# ── JavaScript ──────────────────────────────────────────────────────────────


class TestJavaScriptConstantsOnly:
    """JS has no enum keyword — only constants should be extracted."""

    def test_js_constants_only(self):
        """Primitive-literal constants are extracted; objects, Object.freeze,
        and arrow functions are not constants.

        The fixture ``js_constants.js`` contains:

        - ``const APP_NAME = "myapp";`` — string literal → constant
        - ``const MAX_RETRIES = 5;`` — number literal → constant
        - ``const defaults = { retries: 3 };`` — object literal → skipped
        - ``const Status = Object.freeze({ ... });`` — call expression → skipped
        - ``const handler = () => {};`` — arrow function → function, not constant
        """
        path = FIXTURES_DIR / "js_constants.js"
        extract = extract_js_symbols(path)
        assert extract is not None
        assert extract.language == "javascript"

        # No enums for JS — the keyword does not exist.
        assert extract.enums == []

        # Constants: APP_NAME and MAX_RETRIES only.
        const_by_name = {c.name: c for c in extract.constants}
        assert set(const_by_name.keys()) == {"APP_NAME", "MAX_RETRIES"}

        app_name = const_by_name["APP_NAME"]
        assert app_name.value == '"myapp"'
        assert app_name.line == 1
        assert app_name.type_annotation is None

        max_retries = const_by_name["MAX_RETRIES"]
        assert max_retries.value == "5"
        assert max_retries.line == 2
        assert max_retries.type_annotation is None

        # Symbol definitions: two constants + one arrow-function (handler).
        definitions_by_name = {d.name: d for d in extract.definitions}
        # Object.freeze and object-literal declarations are NOT emitted as
        # symbols at all (their RHS is not a primitive literal and not an
        # arrow function).
        assert "defaults" not in definitions_by_name
        assert "Status" not in definitions_by_name

        assert definitions_by_name["APP_NAME"].symbol_type == "constant"
        assert definitions_by_name["MAX_RETRIES"].symbol_type == "constant"
        assert definitions_by_name["handler"].symbol_type == "function"

        # Qualified names use the file stem as the module path.
        assert definitions_by_name["APP_NAME"].qualified_name == "js_constants.APP_NAME"
        assert definitions_by_name["MAX_RETRIES"].qualified_name == "js_constants.MAX_RETRIES"

        # Visibility: ALL_CAPS public names map to "public".
        assert definitions_by_name["APP_NAME"].visibility == "public"
        assert definitions_by_name["MAX_RETRIES"].visibility == "public"


# ── TypeScript ──────────────────────────────────────────────────────────────


class TestTypeScriptEnumAndConstantExtraction:
    """TypeScript parser enum and constant extraction.

    Fixtures live under ``tests/test_ast_parser/fixtures/enums``:

    - ``ts_enum.ts`` — ``export enum BuildStatus`` with three string members.
    - ``ts_const_enum.ts`` — ``const enum Direction`` with two numeric members.
    - ``ts_constants.ts`` — mix of primitive-literal, object-literal, and
      arrow-function ``const`` bindings.
    """

    def test_ts_enum_extracted(self):
        """``enum BuildStatus { ... }`` is emitted with ``symbol_type='enum'``
        and three string-valued members with monotonic ordinals."""
        path = FIXTURES_DIR / "ts_enum.ts"
        extract = extract_ts_symbols(path)
        assert extract is not None
        assert extract.language == "typescript"

        # Symbol definition surface.
        definitions_by_name = {d.name: d for d in extract.definitions}
        assert "BuildStatus" in definitions_by_name
        assert definitions_by_name["BuildStatus"].symbol_type == "enum"
        assert definitions_by_name["BuildStatus"].qualified_name == "ts_enum.BuildStatus"
        assert definitions_by_name["BuildStatus"].visibility == "public"

        # Enum member surface.
        assert len(extract.enums) == 1
        qualified_name, members = extract.enums[0]
        assert qualified_name == "ts_enum.BuildStatus"
        assert len(members) == 3

        by_ordinal = {m.ordinal: m for m in members}
        assert by_ordinal[0].name == "Pending"
        assert by_ordinal[0].value == '"pending"'
        assert by_ordinal[1].name == "Running"
        assert by_ordinal[1].value == '"running"'
        assert by_ordinal[2].name == "Failed"
        assert by_ordinal[2].value == '"failed"'

    def test_ts_const_enum_extracted(self):
        """``const enum Direction { ... }`` produces the same
        ``symbol_type='enum'`` structure as a plain enum; the ``const``
        modifier is a sibling token, not a distinct node type."""
        path = FIXTURES_DIR / "ts_const_enum.ts"
        extract = extract_ts_symbols(path)
        assert extract is not None

        definitions_by_name = {d.name: d for d in extract.definitions}
        assert "Direction" in definitions_by_name
        assert definitions_by_name["Direction"].symbol_type == "enum"
        assert definitions_by_name["Direction"].qualified_name == "ts_const_enum.Direction"

        assert len(extract.enums) == 1
        qualified_name, members = extract.enums[0]
        assert qualified_name == "ts_const_enum.Direction"
        assert len(members) == 2

        by_ordinal = {m.ordinal: m for m in members}
        assert by_ordinal[0].name == "Up"
        assert by_ordinal[0].value == "0"
        assert by_ordinal[1].name == "Down"
        assert by_ordinal[1].value == "1"

    def test_ts_constants_extracted(self):
        """Primitive-literal ``const`` bindings are indexed as constants;
        object literals are skipped; arrow functions remain on the function
        pipeline (``symbol_type='function'``)."""
        path = FIXTURES_DIR / "ts_constants.ts"
        extract = extract_ts_symbols(path)
        assert extract is not None

        # No enums in this fixture.
        assert extract.enums == []

        # Constants: API_URL and MAX_RETRIES only; config (object literal)
        # and handler (arrow function) must be skipped.
        const_by_name = {c.name: c for c in extract.constants}
        assert set(const_by_name.keys()) == {"API_URL", "MAX_RETRIES"}

        api_url = const_by_name["API_URL"]
        assert api_url.value == '"https://api.example.com"'
        assert api_url.line == 3
        assert api_url.type_annotation is None

        max_retries = const_by_name["MAX_RETRIES"]
        assert max_retries.value == "5"
        assert max_retries.line == 4
        assert max_retries.type_annotation is None

        # Symbol-definition pipeline: the two constants and the arrow
        # function all surface, but with distinct ``symbol_type`` values.
        definitions_by_name = {d.name: d for d in extract.definitions}
        assert definitions_by_name["API_URL"].symbol_type == "constant"
        assert definitions_by_name["MAX_RETRIES"].symbol_type == "constant"
        assert definitions_by_name["handler"].symbol_type == "function"
        # Object-literal bindings carry no primitive value and are not
        # routed through the function pipeline — they are silently
        # dropped from the definition surface.
        assert "config" not in definitions_by_name

        # Qualified names use the file stem as the module path.
        assert definitions_by_name["API_URL"].qualified_name == "ts_constants.API_URL"
        assert definitions_by_name["MAX_RETRIES"].qualified_name == "ts_constants.MAX_RETRIES"
