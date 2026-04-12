"""Tests for composition extraction from Python and TypeScript parsers."""

from __future__ import annotations

from pathlib import Path

import pytest

from lexibrary.ast_parser.python_parser import (
    _strip_annotation_to_target,
    extract_symbols,
)

FIXTURES = Path(__file__).parent / "fixtures" / "composition"


# ---------------------------------------------------------------------------
# Python: class-body annotated assignments
# ---------------------------------------------------------------------------


class TestPythonClassBodyAnnotation:
    """Test composition extraction from class body annotated assignments."""

    def test_python_class_body_annotation(self) -> None:
        """Annotated assignments like ``db: Database`` produce CompositionSite."""
        result = extract_symbols(FIXTURES / "simple_python.py")
        assert result is not None

        # Filter compositions for the Service class.
        service_comps = [c for c in result.compositions if "Service" in c.source_class]

        # Should find Database and Cache but NOT str and int (builtins).
        target_names = {c.target_name for c in service_comps}
        assert "Database" in target_names
        assert "Cache" in target_names
        assert "str" not in target_names
        assert "int" not in target_names

    def test_skip_builtin_type_annotations(self) -> None:
        """Builtin types (str, int, bool, etc.) are not composition targets."""
        result = extract_symbols(FIXTURES / "simple_python.py")
        assert result is not None

        all_targets = {c.target_name for c in result.compositions}
        for builtin in ("str", "int", "bool", "float", "list", "dict", "tuple", "set", "bytes"):
            assert builtin not in all_targets, f"Builtin '{builtin}' should be skipped"

    def test_composition_site_has_attribute_name(self) -> None:
        """Each CompositionSite records the attribute name."""
        result = extract_symbols(FIXTURES / "simple_python.py")
        assert result is not None

        service_comps = [c for c in result.compositions if "Service" in c.source_class]
        db_comp = next((c for c in service_comps if c.target_name == "Database"), None)
        assert db_comp is not None
        assert db_comp.attribute_name == "db"

        cache_comp = next((c for c in service_comps if c.target_name == "Cache"), None)
        assert cache_comp is not None
        assert cache_comp.attribute_name == "cache"

    def test_composition_site_has_line_number(self) -> None:
        """Each CompositionSite has a non-zero line number."""
        result = extract_symbols(FIXTURES / "simple_python.py")
        assert result is not None

        for comp in result.compositions:
            assert comp.line > 0


# ---------------------------------------------------------------------------
# Python: __init__ self.attr: Type
# ---------------------------------------------------------------------------


class TestPythonInitSelfAnnotation:
    """Test composition extraction from __init__ self.attr: Type patterns."""

    def test_python_init_self_annotation(self) -> None:
        """self.engine: Engine in __init__ produces a CompositionSite."""
        result = extract_symbols(FIXTURES / "init_based.py")
        assert result is not None

        app_comps = [c for c in result.compositions if "Application" in c.source_class]
        target_names = {c.target_name for c in app_comps}

        assert "Engine" in target_names
        assert "Renderer" in target_names
        # str and int should be filtered.
        assert "str" not in target_names
        assert "int" not in target_names

    def test_init_attribute_names(self) -> None:
        """Attribute names from __init__ are captured correctly."""
        result = extract_symbols(FIXTURES / "init_based.py")
        assert result is not None

        app_comps = [c for c in result.compositions if "Application" in c.source_class]
        engine_comp = next((c for c in app_comps if c.target_name == "Engine"), None)
        assert engine_comp is not None
        assert engine_comp.attribute_name == "engine"

        renderer_comp = next((c for c in app_comps if c.target_name == "Renderer"), None)
        assert renderer_comp is not None
        assert renderer_comp.attribute_name == "renderer"


# ---------------------------------------------------------------------------
# Python: generic wrapper stripping
# ---------------------------------------------------------------------------


class TestStripGenericWrappers:
    """Test the generic wrapper stripping helper."""

    def test_strip_generic_wrappers(self) -> None:
        """Generic wrappers are unwrapped to their inner type."""
        result = extract_symbols(FIXTURES / "generic_wrappers.py")
        assert result is not None

        pipeline_comps = [c for c in result.compositions if "Pipeline" in c.source_class]
        target_names = {c.target_name for c in pipeline_comps}

        # list[Handler] -> Handler
        assert "Handler" in target_names
        # Optional[Middleware] -> Middleware
        assert "Middleware" in target_names
        # dict[str, Plugin] -> Plugin
        assert "Plugin" in target_names
        # Router | None -> Router
        assert "Router" in target_names

    def test_skip_builtin_wrapper_contents(self) -> None:
        """list[str] and dict[str, int] should NOT produce compositions."""
        result = extract_symbols(FIXTURES / "generic_wrappers.py")
        assert result is not None

        pipeline_comps = [c for c in result.compositions if "Pipeline" in c.source_class]
        attr_names = {c.attribute_name for c in pipeline_comps}
        # 'names: list[str]' and 'items: dict[str, int]' should be skipped.
        assert "names" not in attr_names
        assert "items" not in attr_names

    def test_strip_annotation_list(self) -> None:
        assert _strip_annotation_to_target("list[Handler]") == "Handler"

    def test_strip_annotation_dict(self) -> None:
        assert _strip_annotation_to_target("dict[str, Plugin]") == "Plugin"

    def test_strip_annotation_optional(self) -> None:
        assert _strip_annotation_to_target("Optional[Middleware]") == "Middleware"

    def test_strip_annotation_union_none(self) -> None:
        assert _strip_annotation_to_target("Union[Router, None]") == "Router"

    def test_strip_annotation_pipe_none(self) -> None:
        assert _strip_annotation_to_target("Router | None") == "Router"

    def test_strip_annotation_builtin(self) -> None:
        assert _strip_annotation_to_target("str") is None
        assert _strip_annotation_to_target("int") is None
        assert _strip_annotation_to_target("bool") is None

    def test_strip_annotation_list_of_builtin(self) -> None:
        assert _strip_annotation_to_target("list[str]") is None
        assert _strip_annotation_to_target("dict[str, int]") is None


# ---------------------------------------------------------------------------
# Python: single-letter generic parameters
# ---------------------------------------------------------------------------


class TestSkipSingleLetterGenericParameters:
    """Test that single uppercase letters (generic params) are skipped."""

    def test_skip_single_letter_generic_parameters(self) -> None:
        """list[T] should not produce a CompositionSite."""
        result = extract_symbols(FIXTURES / "generic_wrappers.py")
        assert result is not None

        pipeline_comps = [c for c in result.compositions if "Pipeline" in c.source_class]
        # The single_letter field with list[T] should be skipped.
        assert "single_letter" not in {c.attribute_name for c in pipeline_comps}

    def test_strip_annotation_single_letter(self) -> None:
        assert _strip_annotation_to_target("T") is None
        assert _strip_annotation_to_target("K") is None
        assert _strip_annotation_to_target("V") is None

    def test_strip_annotation_list_of_single_letter(self) -> None:
        assert _strip_annotation_to_target("list[T]") is None


# ---------------------------------------------------------------------------
# TypeScript: class field annotations
# ---------------------------------------------------------------------------


class TestTsFieldAnnotation:
    """Test composition extraction from TypeScript class field annotations."""

    @pytest.fixture()
    def ts_result(self):
        """Parse the TypeScript composition fixture."""
        from lexibrary.ast_parser.typescript_parser import extract_symbols as ts_extract

        result = ts_extract(FIXTURES / "ts_composition.ts")
        # If TS grammar is not available, skip the test.
        if result is None:
            pytest.skip("TypeScript grammar not available")
        return result

    def test_ts_field_annotation(self, ts_result) -> None:
        """TypeScript class fields with type annotations produce CompositionSite."""
        service_comps = [c for c in ts_result.compositions if "Service" in c.source_class]
        target_names = {c.target_name for c in service_comps}

        assert "Database" in target_names
        assert "Cache" in target_names
        assert "Logger" in target_names
        # Builtins should be filtered.
        assert "string" not in target_names
        assert "number" not in target_names

    def test_ts_generic_wrapper(self, ts_result) -> None:
        """Array<Cache> should produce a composition for Cache."""
        service_comps = [c for c in ts_result.compositions if "Service" in c.source_class]
        items_comp = next((c for c in service_comps if c.attribute_name == "items"), None)
        assert items_comp is not None
        assert items_comp.target_name == "Cache"

    def test_ts_field_attribute_names(self, ts_result) -> None:
        """Field names from TS classes are captured correctly."""
        service_comps = [c for c in ts_result.compositions if "Service" in c.source_class]
        db_comp = next((c for c in service_comps if c.target_name == "Database"), None)
        assert db_comp is not None
        assert db_comp.attribute_name == "db"

    def test_ts_field_line_numbers(self, ts_result) -> None:
        """Each TS CompositionSite has a non-zero line number."""
        for comp in ts_result.compositions:
            assert comp.line > 0
