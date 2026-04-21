"""Tests for the recursive descendant walk in dependency_extractor.

Exercises §2.3 of the design-cleanup change: the extractor now walks every
descendant of the AST root so imports nested inside function bodies,
``try/except`` blocks, class bodies, and top-level conditional branches all
contribute edges. Imports under ``if TYPE_CHECKING:`` guards MUST be excluded
from the walk to preserve runtime-only ``ast_import`` semantics.

Group 1 owns the Python cases below. Group 2 appends JS/TS cases to the same
file.
"""

from __future__ import annotations

from pathlib import Path

from lexibrary.archivist.dependency_extractor import extract_dependencies


def _make_package(tmp_path: Path) -> Path:
    """Create a minimal in-project package ``src/mypkg`` with common modules.

    Used by the recursive-walk tests so the extractor has something to resolve
    against. Returns the package directory path.
    """
    pkg = tmp_path / "src" / "mypkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "utils.py").write_text("# utils\n")
    (pkg / "optional.py").write_text("# optional\n")
    (pkg / "helpers.py").write_text("# helpers\n")
    (pkg / "types_only.py").write_text("# types_only\n")
    (pkg / "platform_darwin.py").write_text("# darwin helper\n")
    (pkg / "deferred.py").write_text("# deferred\n")
    return pkg


class TestPythonRecursiveWalk:
    """Each test targets a distinct nesting depth the old depth-1 walk missed."""

    def test_deferred_import_inside_function_body_extracted(self, tmp_path: Path) -> None:
        """Imports placed inside function bodies (e.g. to avoid circular imports
        or to defer heavy modules) SHALL surface in the dep list.
        """
        pkg = _make_package(tmp_path)
        main_py = pkg / "main.py"
        main_py.write_text(
            "def run():\n"
            "    from mypkg.deferred import do_thing  # noqa: PLC0415\n"
            "    return do_thing()\n"
        )

        deps = extract_dependencies(main_py, tmp_path)

        assert "src/mypkg/deferred.py" in deps

    def test_import_inside_try_except_extracted(self, tmp_path: Path) -> None:
        """Imports inside ``try: ... except ImportError: ...`` SHALL surface.
        The guarded-import pattern is common for optional dependencies.
        """
        pkg = _make_package(tmp_path)
        main_py = pkg / "main.py"
        main_py.write_text(
            "try:\n    from mypkg.optional import OptX\nexcept ImportError:\n    OptX = None\n"
        )

        deps = extract_dependencies(main_py, tmp_path)

        assert "src/mypkg/optional.py" in deps

    def test_import_inside_class_body_extracted(self, tmp_path: Path) -> None:
        """Imports placed inside a class body (rare but valid Python) SHALL
        surface.
        """
        pkg = _make_package(tmp_path)
        main_py = pkg / "main.py"
        main_py.write_text(
            "class Widget:\n"
            "    from mypkg.helpers import helper\n"
            "    def run(self):\n"
            "        return self.helper()\n"
        )

        deps = extract_dependencies(main_py, tmp_path)

        assert "src/mypkg/helpers.py" in deps

    def test_import_inside_platform_conditional_extracted(self, tmp_path: Path) -> None:
        """Imports under ``if platform.system() == "Darwin":`` SHALL surface.

        Only TYPE_CHECKING is a valid reason to skip — other top-level
        conditionals gate runtime behaviour and their imports are real edges.
        """
        pkg = _make_package(tmp_path)
        main_py = pkg / "main.py"
        main_py.write_text(
            "import platform\n"
            "\n"
            "if platform.system() == 'Darwin':\n"
            "    from mypkg.platform_darwin import mac_helper\n"
        )

        deps = extract_dependencies(main_py, tmp_path)

        assert "src/mypkg/platform_darwin.py" in deps

    def test_import_under_type_checking_guard_excluded(self, tmp_path: Path) -> None:
        """Imports guarded by ``if TYPE_CHECKING:`` SHALL NOT appear as runtime
        dependencies — they never execute at runtime.
        """
        pkg = _make_package(tmp_path)
        main_py = pkg / "main.py"
        main_py.write_text(
            "from typing import TYPE_CHECKING\n"
            "\n"
            "if TYPE_CHECKING:\n"
            "    from mypkg.types_only import SomeType\n"
        )

        deps = extract_dependencies(main_py, tmp_path)

        assert "src/mypkg/types_only.py" not in deps

    def test_type_checking_guard_does_not_hide_sibling_imports(self, tmp_path: Path) -> None:
        """A TYPE_CHECKING guard MUST NOT accidentally suppress imports that
        live outside its body. Regression guard against an overly-broad skip.
        """
        pkg = _make_package(tmp_path)
        main_py = pkg / "main.py"
        main_py.write_text(
            "from typing import TYPE_CHECKING\n"
            "from mypkg.utils import u\n"
            "\n"
            "if TYPE_CHECKING:\n"
            "    from mypkg.types_only import SomeType\n"
            "\n"
            "from mypkg.helpers import helper\n"
        )

        deps = extract_dependencies(main_py, tmp_path)

        assert "src/mypkg/utils.py" in deps
        assert "src/mypkg/helpers.py" in deps
        assert "src/mypkg/types_only.py" not in deps

    def test_top_level_imports_still_resolved(self, tmp_path: Path) -> None:
        """Regression guard for the pre-fix depth-1 behaviour: top-level
        ``import X`` AND top-level ``from .y import Z`` SHALL both appear.
        """
        pkg = _make_package(tmp_path)
        (pkg / "sibling.py").write_text("# sibling\n")
        main_py = pkg / "main.py"
        main_py.write_text(
            "import mypkg.utils\nfrom .sibling import value\n",
        )

        deps = extract_dependencies(main_py, tmp_path)

        assert "src/mypkg/utils.py" in deps
        assert "src/mypkg/sibling.py" in deps


class TestJsTsRecursiveWalk:
    """JS/TS analogues of the Python recursive-walk cases.

    tree-sitter-typescript parses static ``import`` statements nested inside
    function/class bodies and conditional branches as ``import_statement``
    nodes, so the recursive walk reaches them via descendant iteration.
    Dynamic ``import('./path')`` calls are a separate ``call_expression``
    shape and are intentionally NOT covered — the extractor only matches
    ``import_statement`` / ``export_statement`` node types today.
    """

    def test_nested_import_inside_function_body_extracted(self, tmp_path: Path) -> None:
        """Static ``import`` inside a function body is extracted."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "helper.ts").write_text("export const X = 1;\n")

        main_ts = src / "main.ts"
        main_ts.write_text(
            "export function loadIt() {\n  import { X } from './helper';\n  return X;\n}\n"
        )

        deps = extract_dependencies(main_ts, tmp_path)
        assert "src/helper.ts" in deps

    def test_type_only_import_not_extracted(self, tmp_path: Path) -> None:
        """``import type { X } from './types'`` SHALL NOT appear.

        tree-sitter-typescript emits type-only imports as ``import_statement``
        nodes with a bare ``type`` child token before the ``import_clause``.
        The extractor inspects for this token and skips the statement so
        type-only imports do not count as runtime deps.
        """
        src = tmp_path / "src"
        src.mkdir()
        (src / "types.ts").write_text("export interface Config {}\n")
        (src / "helper.ts").write_text("export const RUNTIME = 1;\n")

        main_ts = src / "main.ts"
        main_ts.write_text(
            "import type { Config } from './types';\nimport { RUNTIME } from './helper';\n"
        )

        deps = extract_dependencies(main_ts, tmp_path)
        assert "src/types.ts" not in deps
        # Sibling runtime import confirms the regular-import path still works
        # alongside the type-only skip.
        assert "src/helper.ts" in deps

    def test_relative_import_inside_class_body_extracted(self, tmp_path: Path) -> None:
        """Static ``import`` inside a class method body is extracted."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "helper.ts").write_text("export const HELP = 2;\n")

        main_ts = src / "main.ts"
        main_ts.write_text(
            "export class Foo {\n"
            "  bar() {\n"
            "    import { HELP } from './helper';\n"
            "    return HELP;\n"
            "  }\n"
            "}\n"
        )

        deps = extract_dependencies(main_ts, tmp_path)
        assert "src/helper.ts" in deps

    def test_top_level_import_still_extracted(self, tmp_path: Path) -> None:
        """Regression guard: ``import X from './y'`` at top level still works."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "y.ts").write_text("export default 3;\n")

        main_ts = src / "main.ts"
        main_ts.write_text("import X from './y';\n")

        deps = extract_dependencies(main_ts, tmp_path)
        assert "src/y.ts" in deps

    def test_import_inside_if_branch_extracted(self, tmp_path: Path) -> None:
        """Import nested under a top-level ``if`` branch is extracted.

        JS/TS has no ``TYPE_CHECKING`` equivalent, so the JS/TS walker runs
        with ``skip_type_checking=False`` and nothing is filtered.
        """
        src = tmp_path / "src"
        src.mkdir()
        (src / "platform_only.ts").write_text("export const KIND = 'mac';\n")

        main_ts = src / "main.ts"
        main_ts.write_text(
            "if (process.platform === 'darwin') {\n  import { KIND } from './platform_only';\n}\n"
        )

        deps = extract_dependencies(main_ts, tmp_path)
        assert "src/platform_only.ts" in deps

    def test_export_from_still_extracted(self, tmp_path: Path) -> None:
        """Regression guard: ``export { X } from './y'`` still extracted."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "y.ts").write_text("export const X = 1;\n")

        main_ts = src / "main.ts"
        main_ts.write_text("export { X } from './y';\n")

        deps = extract_dependencies(main_ts, tmp_path)
        assert "src/y.ts" in deps
