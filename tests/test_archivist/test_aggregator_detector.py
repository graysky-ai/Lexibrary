"""Tests for the aggregator detector in ``archivist/skeleton.py``.

Covers the three gates (re-export ratio, body size, conditional logic) and
the ``reexports_by_source`` grouping emitted for aggregator modules. See
SHARED_BLOCK_D in ``openspec/changes/design-cleanup/tasks.md`` for the
contract under test.
"""

from __future__ import annotations

from pathlib import Path

from lexibrary.archivist.skeleton import (
    AggregatorClassification,
    classify_aggregator,
    is_constants_only,
)


def _write_source(tmp_path: Path, rel: str, content: str) -> Path:
    """Write ``content`` to ``tmp_path/rel`` and return the absolute path."""
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


# ---------------------------------------------------------------------------
# Spec scenarios (a) through (e) from tasks.md §12.5.
# ---------------------------------------------------------------------------


class TestSpecScenarios:
    """Scenarios explicitly named in the tasks.md §12.5 contract."""

    def test_pure_aggregator_classified(self, tmp_path: Path) -> None:
        """Pure aggregator (only `from ... import ...` + `__all__`)."""
        content = 'from .a import X\nfrom .b import Y, Z\n__all__ = ["X", "Y", "Z"]\n'
        source = _write_source(tmp_path, "src/pkg/__init__.py", content)

        result = classify_aggregator(source)

        assert isinstance(result, AggregatorClassification)
        assert result.is_aggregator is True
        assert result.reexports_by_source == {".a": ["X"], ".b": ["Y", "Z"]}

    def test_body_size_gate_fails_with_long_function(
        self,
        tmp_path: Path,
    ) -> None:
        """Re-exports + a 10-line function body fail the body-size gate."""
        content = (
            "from .a import X\n"
            "from .b import Y\n"
            "from .c import Z\n"
            "\n"
            "def do_stuff() -> int:\n"
            "    total = 0\n"
            "    for i in range(10):\n"
            "        total += i\n"
            "    for j in range(5):\n"
            "        total -= j\n"
            "    if total < 0:\n"
            "        total = 0\n"
            "    return total\n"
        )
        source = _write_source(tmp_path, "src/pkg/mixed.py", content)

        result = classify_aggregator(source)

        assert result.is_aggregator is False

    def test_platform_conditional_fails_gate(self, tmp_path: Path) -> None:
        """A top-level ``if platform.system() == ...`` fails gate 3."""
        content = (
            "import platform\n"
            "from .a import X\n"
            "\n"
            'if platform.system() == "Darwin":\n'
            "    from .mac import helper\n"
            "else:\n"
            "    from .other import helper\n"
        )
        source = _write_source(tmp_path, "src/pkg/platform_gated.py", content)

        result = classify_aggregator(source)

        assert result.is_aggregator is False

    def test_sys_version_info_guard_allowed(self, tmp_path: Path) -> None:
        """``if sys.version_info >= (3, 11):`` is an allowed conditional."""
        content = (
            "import sys\n"
            "from .a import X\n"
            "from .b import Y\n"
            "\n"
            "if sys.version_info >= (3, 11):\n"
            "    from .new_api import NewThing\n"
            "else:\n"
            "    from .old_api import NewThing\n"
            '__all__ = ["NewThing", "X", "Y"]\n'
        )
        source = _write_source(tmp_path, "src/pkg/version_gated.py", content)

        result = classify_aggregator(source)

        assert result.is_aggregator is True

    def test_80_20_reexport_ratio_passes(self, tmp_path: Path) -> None:
        """4 re-exports + 1 tiny standalone fn = 80% ratio, gate passes."""
        content = (
            "from .a import A\n"
            "from .b import B\n"
            "from .c import C\n"
            "from .d import D\n"
            "\n"
            "def short() -> None:\n"
            "    pass\n"
            '__all__ = ["A", "B", "C", "D", "short"]\n'
        )
        source = _write_source(tmp_path, "src/pkg/mostly_agg.py", content)

        result = classify_aggregator(source)

        assert result.is_aggregator is True


# ---------------------------------------------------------------------------
# Additional coverage — edge cases that the scenarios don't directly exercise
# but that the implementation is obliged to handle gracefully.
# ---------------------------------------------------------------------------


class TestReexportsBySourceShape:
    """Validate the shape of the ``reexports_by_source`` mapping."""

    def test_names_sorted_deterministically(self, tmp_path: Path) -> None:
        """Names under each source module appear in sorted order."""
        content = "from .x import Zebra\nfrom .x import Apple\nfrom .x import Mango\n"
        source = _write_source(tmp_path, "src/pkg/sorted.py", content)

        result = classify_aggregator(source)

        assert result.is_aggregator is True
        assert result.reexports_by_source == {".x": ["Apple", "Mango", "Zebra"]}

    def test_multiple_modules_tracked_separately(self, tmp_path: Path) -> None:
        """Each source module gets its own key in the mapping."""
        content = "from .one import A\nfrom .two import B\nfrom .three import C\n"
        source = _write_source(tmp_path, "src/pkg/multi.py", content)

        result = classify_aggregator(source)

        assert result.is_aggregator is True
        assert result.reexports_by_source == {
            ".one": ["A"],
            ".two": ["B"],
            ".three": ["C"],
        }


class TestGateFailures:
    """Non-aggregator modules should return ``is_aggregator=False``."""

    def test_empty_module_not_aggregator(self, tmp_path: Path) -> None:
        """An empty file has no top-level named symbols → not aggregator."""
        source = _write_source(tmp_path, "src/pkg/empty.py", "")

        result = classify_aggregator(source)

        assert result.is_aggregator is False
        assert result.reexports_by_source == {}

    def test_module_with_only_local_definitions(self, tmp_path: Path) -> None:
        """No re-exports → gate 1 fails."""
        content = "def foo() -> int:\n    return 1\n\nclass Bar:\n    pass\n"
        source = _write_source(tmp_path, "src/pkg/local.py", content)

        result = classify_aggregator(source)

        assert result.is_aggregator is False

    def test_two_top_level_conditionals_fails_gate(
        self,
        tmp_path: Path,
    ) -> None:
        """Even with sys.version_info, more than one top-level if fails."""
        content = (
            "import sys\n"
            "from .a import X\n"
            "\n"
            "if sys.version_info >= (3, 11):\n"
            "    from .new import Y\n"
            "\n"
            "if sys.version_info >= (3, 12):\n"
            "    from .newer import Z\n"
        )
        source = _write_source(tmp_path, "src/pkg/two_ifs.py", content)

        result = classify_aggregator(source)

        assert result.is_aggregator is False

    def test_non_python_file_not_aggregator(self, tmp_path: Path) -> None:
        """Non-Python extensions are rejected outright."""
        source = _write_source(tmp_path, "src/pkg/notes.md", "# hi\n")

        result = classify_aggregator(source)

        assert result.is_aggregator is False

    def test_unreadable_missing_file_not_aggregator(
        self,
        tmp_path: Path,
    ) -> None:
        """Missing file returns a non-aggregator verdict without raising."""
        missing = tmp_path / "nope.py"

        result = classify_aggregator(missing)

        assert result.is_aggregator is False


class TestFromFutureImportIgnored:
    """``from __future__ import annotations`` MUST NOT count as a re-export."""

    def test_future_import_not_counted(self, tmp_path: Path) -> None:
        content = (
            "from __future__ import annotations\n"
            "from .a import X\n"
            "from .b import Y\n"
            '__all__ = ["X", "Y"]\n'
        )
        source = _write_source(tmp_path, "src/pkg/future.py", content)

        result = classify_aggregator(source)

        assert result.is_aggregator is True
        # __future__ should be absent from the mapping.
        assert "__future__" not in result.reexports_by_source
        assert result.reexports_by_source == {".a": ["X"], ".b": ["Y"]}


class TestPassThroughFunctions:
    """Small pass-through functions (≤3 body lines) shouldn't break gate 2."""

    def test_single_line_function_body_passes(self, tmp_path: Path) -> None:
        """``def f(): return x`` is one body line and passes the gate."""
        content = (
            "from .a import X\n"
            "from .b import Y\n"
            "from .c import Z\n"
            "from .d import W\n"
            "\n"
            "def reraise() -> None:\n"
            "    raise RuntimeError\n"
        )
        source = _write_source(tmp_path, "src/pkg/pass_through.py", content)

        result = classify_aggregator(source)

        assert result.is_aggregator is True

    def test_four_line_body_fails(self, tmp_path: Path) -> None:
        """A 4-line body exceeds ≤3 and trips gate 2."""
        content = (
            "from .a import X\n"
            "from .b import Y\n"
            "\n"
            "def long_fn() -> int:\n"
            "    a = 1\n"
            "    b = 2\n"
            "    c = 3\n"
            "    return a + b + c\n"
        )
        source = _write_source(tmp_path, "src/pkg/four_line.py", content)

        result = classify_aggregator(source)

        assert result.is_aggregator is False


# ---------------------------------------------------------------------------
# is_constants_only (§2.4c — complexity_warning prompt suppression gate)
# ---------------------------------------------------------------------------


class TestIsConstantsOnly:
    """Tests for :func:`is_constants_only` (tasks.md §15.1 contract)."""

    def test_pure_constants_file_is_constants_only(self, tmp_path: Path) -> None:
        """Only top-level assignments → True."""
        content = (
            "MAX_RETRIES = 5\nDEFAULT_NAME: str = 'lexibrary'\nTHRESHOLDS: list[int] = [1, 2, 3]\n"
        )
        source = _write_source(tmp_path, "src/pkg/constants.py", content)

        assert is_constants_only(source) is True

    def test_file_with_one_function_is_not_constants_only(self, tmp_path: Path) -> None:
        """Any top-level ``def`` disqualifies the module."""
        content = "X = 1\n\ndef helper() -> int:\n    return X\n"
        source = _write_source(tmp_path, "src/pkg/has_fn.py", content)

        assert is_constants_only(source) is False

    def test_file_with_one_class_is_not_constants_only(self, tmp_path: Path) -> None:
        """Any top-level ``class`` disqualifies the module."""
        content = "X = 1\n\nclass Helper:\n    pass\n"
        source = _write_source(tmp_path, "src/pkg/has_class.py", content)

        assert is_constants_only(source) is False

    def test_empty_file_is_constants_only(self, tmp_path: Path) -> None:
        """An empty file has no behaviour for complexity_warning to describe."""
        source = _write_source(tmp_path, "src/pkg/empty.py", "")

        assert is_constants_only(source) is True

    def test_docstring_and_imports_dont_disqualify(self, tmp_path: Path) -> None:
        """Module docstrings and imports are permitted alongside constants."""
        content = (
            '"""Module-level constants for the widget subsystem."""\n'
            "\n"
            "from typing import Final\n"
            "\n"
            "TIMEOUT: Final[int] = 30\n"
        )
        source = _write_source(tmp_path, "src/pkg/with_docstring.py", content)

        assert is_constants_only(source) is True

    def test_decorated_function_disqualifies(self, tmp_path: Path) -> None:
        """A decorated top-level function is still a function — disqualifies."""
        content = (
            "import functools\n\nX = 1\n\n@functools.cache\ndef helper() -> int:\n    return X\n"
        )
        source = _write_source(tmp_path, "src/pkg/decorated.py", content)

        assert is_constants_only(source) is False

    def test_non_python_extension_returns_false(self, tmp_path: Path) -> None:
        """Non-Python extensions are rejected outright."""
        source = _write_source(tmp_path, "src/pkg/notes.md", "# hi\n")

        assert is_constants_only(source) is False

    def test_missing_file_returns_false(self, tmp_path: Path) -> None:
        """Missing file returns False without raising (pipeline keeps LLM path)."""
        missing = tmp_path / "src" / "pkg" / "gone.py"

        assert is_constants_only(missing) is False
