"""Tests for ``lexibrary.symbolgraph.python_imports`` — shared Python import
resolution helpers.

Covers:

- :func:`resolve_python_module` — src-layout and third-party cases (the
  relative-path helpers were moved verbatim from
  ``archivist.dependency_extractor`` and are already exercised there; these
  tests pin the new name and the minimum behaviour called out in Block B /
  task 4.2).
- :func:`resolve_python_relative_module` — single-dot sibling resolution.
- :func:`path_to_module` — src-layout and flat-layout round-trips.
- :func:`parse_imports` — the four shapes required by task 4.2
  (``from`` import, aliased ``from`` import, plain ``import`` of a dotted
  module, and relative ``from`` import).
"""

from __future__ import annotations

from pathlib import Path

from lexibrary.ast_parser.registry import get_parser
from lexibrary.symbolgraph.python_imports import (
    ImportBinding,
    parse_imports,
    path_to_module,
    resolve_python_module,
    resolve_python_relative_module,
)

PROJECT_ROOT = Path(__file__).parent.parent.parent  # → Lexibrary project root


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_python(source: str) -> tuple[object, bytes]:
    """Parse Python source via tree-sitter and return ``(tree, source_bytes)``.

    Centralised so every parse_imports test uses the same grammar instance
    and byte encoding.
    """
    parser = get_parser(".py")
    assert parser is not None, "tree-sitter-python grammar must be installed for tests"
    source_bytes = source.encode("utf-8")
    tree = parser.parse(source_bytes)
    return tree, source_bytes


# ---------------------------------------------------------------------------
# resolve_python_module
# ---------------------------------------------------------------------------


class TestResolvePythonModule:
    def test_resolve_python_module_src_layout(self) -> None:
        """Absolute module in src-layout resolves to the .py file."""
        result = resolve_python_module("lexibrary.config.schema", PROJECT_ROOT)
        assert result is not None
        assert result == PROJECT_ROOT / "src" / "lexibrary" / "config" / "schema.py"

    def test_resolve_python_module_third_party_returns_none(self) -> None:
        """Stdlib/third-party modules are not in the project tree → None."""
        result = resolve_python_module("sqlite3", PROJECT_ROOT)
        assert result is None

    def test_resolve_python_module_package_init(self, tmp_path: Path) -> None:
        """Package import resolves to the package __init__.py file."""
        pkg = tmp_path / "src" / "mypkg"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("")

        result = resolve_python_module("mypkg", tmp_path)
        assert result == tmp_path / "src" / "mypkg" / "__init__.py"

    def test_resolve_python_module_missing_returns_none(self, tmp_path: Path) -> None:
        result = resolve_python_module("does.not.exist", tmp_path)
        assert result is None

    def test_resolve_python_module_flat_layout(self, tmp_path: Path) -> None:
        """Flat-layout project (no ``src/`` directory) still resolves modules."""
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "config.py").write_text("")

        result = resolve_python_module("mypkg.config", tmp_path)
        assert result == tmp_path / "mypkg" / "config.py"

    def test_resolve_python_module_prefers_src_layout(self, tmp_path: Path) -> None:
        """When both ``src/`` and flat layouts exist, ``src/`` is preferred."""
        src_pkg = tmp_path / "src" / "pkg"
        src_pkg.mkdir(parents=True)
        (src_pkg / "mod.py").write_text("# src layout")

        flat_pkg = tmp_path / "pkg"
        flat_pkg.mkdir()
        (flat_pkg / "mod.py").write_text("# flat layout")

        result = resolve_python_module("pkg.mod", tmp_path)
        assert result == tmp_path / "src" / "pkg" / "mod.py"


# ---------------------------------------------------------------------------
# resolve_python_relative_module
# ---------------------------------------------------------------------------


class TestResolvePythonRelativeModule:
    def test_resolve_python_relative_module_single_dot(self, tmp_path: Path) -> None:
        """``from .b import c`` inside ``src/pkg/sub/a.py`` resolves to sibling ``b.py``."""
        pkg_sub = tmp_path / "src" / "pkg" / "sub"
        pkg_sub.mkdir(parents=True)
        (pkg_sub / "a.py").write_text("")
        (pkg_sub / "b.py").write_text("")

        source_dir = pkg_sub  # directory of a.py
        result = resolve_python_relative_module(
            module_name="b",
            dot_count=1,
            source_dir=source_dir,
            project_root=tmp_path,
        )
        assert result == tmp_path / "src" / "pkg" / "sub" / "b.py"


# ---------------------------------------------------------------------------
# path_to_module
# ---------------------------------------------------------------------------


class TestPathToModule:
    def test_path_to_module_src_layout(self) -> None:
        """src-layout path strips the ``src/`` prefix and keeps the package."""
        result = path_to_module(
            Path("src/lexibrary/archivist/pipeline.py"),
            Path("/project"),
        )
        assert result == "lexibrary.archivist.pipeline"

    def test_path_to_module_flat_layout(self) -> None:
        """Flat layout (no ``src/`` prefix) uses the path as-is."""
        result = path_to_module(
            Path("mypkg/config.py"),
            Path("/project"),
        )
        assert result == "mypkg.config"

    def test_path_to_module_absolute_path(self, tmp_path: Path) -> None:
        """Absolute path inside project_root is normalised to relative first."""
        abs_path = tmp_path / "src" / "pkg" / "mod.py"
        result = path_to_module(abs_path, tmp_path)
        assert result == "pkg.mod"

    def test_path_to_module_package_init(self) -> None:
        """``__init__.py`` collapses to the containing package dotted path."""
        result = path_to_module(
            Path("src/lexibrary/__init__.py"),
            Path("/project"),
        )
        assert result == "lexibrary"


# ---------------------------------------------------------------------------
# parse_imports
# ---------------------------------------------------------------------------


class TestParseImports:
    def test_parse_imports_from_import(self, tmp_path: Path) -> None:
        """``from pkg.b import bar`` binds ``"bar"`` to the resolved path."""
        pkg = tmp_path / "src" / "pkg"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("")
        (pkg / "b.py").write_text("def bar():\n    pass\n")

        caller = pkg / "a.py"
        source = "from __future__ import annotations\n\nfrom pkg.b import bar\n"
        caller.write_text(source)

        tree, source_bytes = _parse_python(source)
        result = parse_imports(tree, source_bytes, caller, tmp_path)

        assert result == {
            "bar": ImportBinding(file_path="src/pkg/b.py", original_name="bar"),
        }

    def test_parse_imports_aliased_import(self, tmp_path: Path) -> None:
        """``from pkg.b import bar as baz`` binds ``"baz"`` but preserves ``"bar"``.

        The ``original_name`` on the :class:`ImportBinding` lets the
        call-site resolver look up the *real* symbol row in ``b.py`` when
        the caller invokes the alias (``baz()``).
        """
        pkg = tmp_path / "src" / "pkg"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("")
        (pkg / "b.py").write_text("def bar():\n    pass\n")

        caller = pkg / "a.py"
        source = "from pkg.b import bar as baz\n"
        caller.write_text(source)

        tree, source_bytes = _parse_python(source)
        result = parse_imports(tree, source_bytes, caller, tmp_path)

        assert result == {
            "baz": ImportBinding(file_path="src/pkg/b.py", original_name="bar"),
        }

    def test_parse_imports_module_import(self, tmp_path: Path) -> None:
        """``import pkg.b`` binds the dotted path ``"pkg.b"`` with an empty original.

        Plain module imports target the file itself rather than a single
        named symbol inside it, so ``original_name`` is the empty string
        — the call-site resolver uses the call's own trailing attribute
        (``pkg.b.foo()`` → ``foo``) instead.
        """
        pkg = tmp_path / "src" / "pkg"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("")
        (pkg / "b.py").write_text("def bar():\n    pass\n")

        caller = pkg / "a.py"
        source = "import pkg.b\n"
        caller.write_text(source)

        tree, source_bytes = _parse_python(source)
        result = parse_imports(tree, source_bytes, caller, tmp_path)

        assert result == {
            "pkg.b": ImportBinding(file_path="src/pkg/b.py", original_name=""),
        }

    def test_parse_imports_relative_import(self, tmp_path: Path) -> None:
        """``from .b import bar`` inside ``src/pkg/sub/a.py`` binds ``"bar"``."""
        pkg_sub = tmp_path / "src" / "pkg" / "sub"
        pkg_sub.mkdir(parents=True)
        (pkg_sub / "__init__.py").write_text("")
        (pkg_sub / "b.py").write_text("def bar():\n    pass\n")

        caller = pkg_sub / "a.py"
        source = "from .b import bar\n"
        caller.write_text(source)

        tree, source_bytes = _parse_python(source)
        result = parse_imports(tree, source_bytes, caller, tmp_path)

        assert result == {
            "bar": ImportBinding(file_path="src/pkg/sub/b.py", original_name="bar"),
        }

    def test_parse_imports_aliased_module_import(self, tmp_path: Path) -> None:
        """``import pkg.b as lb`` binds the alias ``"lb"`` (not the dotted path).

        Module-target imports always carry an empty ``original_name`` —
        the alias stands for the whole module, so the caller's trailing
        attribute (``lb.foo()`` → ``foo``) is the lookup key used by the
        resolver.
        """
        pkg = tmp_path / "src" / "pkg"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("")
        (pkg / "b.py").write_text("")

        caller = pkg / "a.py"
        source = "import pkg.b as lb\n"
        caller.write_text(source)

        tree, source_bytes = _parse_python(source)
        result = parse_imports(tree, source_bytes, caller, tmp_path)

        assert result == {
            "lb": ImportBinding(file_path="src/pkg/b.py", original_name=""),
        }

    def test_parse_imports_third_party_dropped(self, tmp_path: Path) -> None:
        """Third-party imports are silently dropped from the map."""
        caller = tmp_path / "a.py"
        source = "import os\nimport sys\nimport requests\n"
        caller.write_text(source)

        tree, source_bytes = _parse_python(source)
        result = parse_imports(tree, source_bytes, caller, tmp_path)

        assert result == {}

    def test_parse_imports_empty_tree(self, tmp_path: Path) -> None:
        """A file with no imports yields an empty map."""
        caller = tmp_path / "a.py"
        source = "def foo():\n    return 1\n"
        caller.write_text(source)

        tree, source_bytes = _parse_python(source)
        result = parse_imports(tree, source_bytes, caller, tmp_path)

        assert result == {}
