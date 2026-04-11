"""Tests for dependency_extractor.

Covers: Python absolute imports, relative imports, third-party excluded,
TypeScript/JS imports, non-code empty, unresolvable omitted.

Note: unit tests for the Python import resolution helpers themselves live
with the shared implementation at ``tests/test_symbolgraph/test_python_imports.py``.
This file exercises only the ``extract_dependencies`` entry point and the
JS/TS resolver still private to this module.
"""

from __future__ import annotations

from pathlib import Path

from lexibrary.archivist.dependency_extractor import (
    _resolve_js_import,
    extract_dependencies,
)

FIXTURES = Path(__file__).parent / "fixtures"
PROJECT_ROOT = Path(__file__).parent.parent.parent  # → Lexibrary project root


# ---------------------------------------------------------------------------
# Python: absolute imports
# ---------------------------------------------------------------------------


class TestPythonAbsoluteImports:
    def test_project_import_resolved(self, tmp_path: Path) -> None:
        """Absolute import resolving to a project file appears in deps."""
        pkg = tmp_path / "src" / "mypkg"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("")
        (pkg / "config.py").write_text("# config")

        main_py = pkg / "main.py"
        main_py.write_text("from mypkg.config import Config\n")

        deps = extract_dependencies(main_py, tmp_path)
        assert "src/mypkg/config.py" in deps

    def test_third_party_excluded(self, tmp_path: Path) -> None:
        """Third-party imports that don't exist in project are excluded."""
        main_py = tmp_path / "main.py"
        main_py.write_text("import requests\nimport os\nimport sys\n")

        deps = extract_dependencies(main_py, tmp_path)
        assert deps == []

    def test_unresolvable_omitted(self, tmp_path: Path) -> None:
        """Import of a module not found in project is silently omitted."""
        main_py = tmp_path / "main.py"
        main_py.write_text("from nonexistent.module import Something\n")

        deps = extract_dependencies(main_py, tmp_path)
        assert deps == []

    def test_multiple_imports_deduped(self, tmp_path: Path) -> None:
        """Same module imported twice appears only once."""
        pkg = tmp_path / "src" / "pkg"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("")
        (pkg / "utils.py").write_text("# utils")

        main_py = tmp_path / "main.py"
        main_py.write_text("from pkg.utils import A\nfrom pkg.utils import B\n")

        deps = extract_dependencies(main_py, tmp_path)
        assert deps.count("src/pkg/utils.py") == 1

    def test_fixture_project_imports(self) -> None:
        """sample_source.py fixture resolves lexibrary imports against real project."""
        deps = extract_dependencies(FIXTURES / "sample_source.py", PROJECT_ROOT)
        assert "src/lexibrary/config/schema.py" in deps
        assert "src/lexibrary/ast_parser/registry.py" in deps

    def test_fixture_third_party_excluded(self) -> None:
        """sample_source.py fixture does not include third-party imports."""
        deps = extract_dependencies(FIXTURES / "sample_source.py", PROJECT_ROOT)
        assert not any("requests" in d for d in deps)


# ---------------------------------------------------------------------------
# Python: relative imports
# ---------------------------------------------------------------------------


class TestPythonRelativeImports:
    def test_from_dot_module_import(self, tmp_path: Path) -> None:
        """``from .utils import X`` resolves to sibling module."""
        pkg = tmp_path / "src" / "mypkg"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("")
        (pkg / "utils.py").write_text("# utils")

        main_py = pkg / "main.py"
        main_py.write_text("from .utils import helper\n")

        deps = extract_dependencies(main_py, tmp_path)
        assert "src/mypkg/utils.py" in deps

    def test_from_dotdot_module_import(self, tmp_path: Path) -> None:
        """``from ..shared import X`` resolves to parent-package sibling."""
        root_pkg = tmp_path / "src" / "mypkg"
        sub_pkg = root_pkg / "sub"
        sub_pkg.mkdir(parents=True)
        (root_pkg / "__init__.py").write_text("")
        (root_pkg / "shared.py").write_text("# shared")
        (sub_pkg / "__init__.py").write_text("")

        child_py = sub_pkg / "child.py"
        child_py.write_text("from ..shared import Common\n")

        deps = extract_dependencies(child_py, tmp_path)
        assert "src/mypkg/shared.py" in deps

    def test_relative_import_to_package(self, tmp_path: Path) -> None:
        """``from .subpkg import X`` resolves to subpackage __init__.py."""
        pkg = tmp_path / "src" / "mypkg"
        subpkg = pkg / "subpkg"
        subpkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("")
        (subpkg / "__init__.py").write_text("# subpackage")

        main_py = pkg / "main.py"
        main_py.write_text("from .subpkg import something\n")

        deps = extract_dependencies(main_py, tmp_path)
        assert "src/mypkg/subpkg/__init__.py" in deps


# ---------------------------------------------------------------------------
# TypeScript / JavaScript
# ---------------------------------------------------------------------------


class TestTypeScriptImports:
    def test_relative_import_resolved(self, tmp_path: Path) -> None:
        """Relative TS import without extension resolves to .ts file."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "schema.ts").write_text("export interface Schema {}")

        main_ts = src / "main.ts"
        main_ts.write_text("import { Schema } from './schema'\n")

        deps = extract_dependencies(main_ts, tmp_path)
        assert "src/schema.ts" in deps

    def test_npm_package_excluded(self, tmp_path: Path) -> None:
        """npm package imports (bare specifiers) are excluded."""
        src = tmp_path / "src"
        src.mkdir()
        main_ts = src / "main.ts"
        main_ts.write_text("import React from 'react'\nimport { useState } from 'react'\n")

        deps = extract_dependencies(main_ts, tmp_path)
        assert deps == []

    def test_relative_import_with_extension(self, tmp_path: Path) -> None:
        """Relative import with explicit .ts extension resolves correctly."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "utils.ts").write_text("export const X = 1")

        main_ts = src / "main.ts"
        main_ts.write_text("import { X } from './utils.ts'\n")

        deps = extract_dependencies(main_ts, tmp_path)
        assert "src/utils.ts" in deps

    def test_parent_relative_import(self, tmp_path: Path) -> None:
        """``../`` relative import resolves correctly."""
        src = tmp_path / "src"
        sub = src / "sub"
        sub.mkdir(parents=True)
        (src / "shared.ts").write_text("export const Y = 2")

        child_ts = sub / "child.ts"
        child_ts.write_text("import { Y } from '../shared'\n")

        deps = extract_dependencies(child_ts, tmp_path)
        assert "src/shared.ts" in deps


class TestJavaScriptImports:
    def test_relative_import_resolved(self, tmp_path: Path) -> None:
        """Relative JS import resolves to .js file."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "utils.js").write_text("// utils")

        main_js = src / "main.js"
        main_js.write_text("import { helper } from './utils'\n")

        deps = extract_dependencies(main_js, tmp_path)
        assert "src/utils.js" in deps

    def test_npm_package_excluded(self, tmp_path: Path) -> None:
        """npm bare specifiers are excluded from JS files."""
        src = tmp_path / "src"
        src.mkdir()
        main_js = src / "main.js"
        main_js.write_text("import express from 'express'\n")

        deps = extract_dependencies(main_js, tmp_path)
        assert deps == []


# ---------------------------------------------------------------------------
# Non-code files
# ---------------------------------------------------------------------------


class TestNonCodeFiles:
    def test_yaml_returns_empty(self, tmp_path: Path) -> None:
        config = tmp_path / "config.yaml"
        config.write_text("key: value\n")
        assert extract_dependencies(config, tmp_path) == []

    def test_markdown_returns_empty(self, tmp_path: Path) -> None:
        readme = tmp_path / "README.md"
        readme.write_text("# Hello\n")
        assert extract_dependencies(readme, tmp_path) == []

    def test_fixture_config_returns_empty(self) -> None:
        """sample_config.yaml fixture returns empty list."""
        deps = extract_dependencies(FIXTURES / "sample_config.yaml", PROJECT_ROOT)
        assert deps == []


# ---------------------------------------------------------------------------
# _resolve_js_import unit tests
# ---------------------------------------------------------------------------


class TestResolveJsImport:
    def test_resolves_with_extension_inference(self, tmp_path: Path) -> None:
        """``./schema`` resolves to schema.ts when schema.ts exists."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "schema.ts").write_text("")

        result = _resolve_js_import("./schema", src, tmp_path)
        assert result == "src/schema.ts"

    def test_resolves_js_extension(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "utils.js").write_text("")

        result = _resolve_js_import("./utils", src, tmp_path)
        assert result == "src/utils.js"

    def test_resolves_index_file(self, tmp_path: Path) -> None:
        """``./components`` resolves to components/index.ts."""
        src = tmp_path / "src"
        components = src / "components"
        components.mkdir(parents=True)
        (components / "index.ts").write_text("")

        result = _resolve_js_import("./components", src, tmp_path)
        assert result == "src/components/index.ts"

    def test_returns_none_when_unresolvable(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        result = _resolve_js_import("./nonexistent", src, tmp_path)
        assert result is None

    def test_explicit_extension(self, tmp_path: Path) -> None:
        """``./module.ts`` resolves directly when file exists."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "module.ts").write_text("")

        result = _resolve_js_import("./module.ts", src, tmp_path)
        assert result == "src/module.ts"
