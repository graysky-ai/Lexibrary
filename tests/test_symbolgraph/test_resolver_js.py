"""Tests for the JavaScript/TypeScript resolver.

Covers: ``resolve_js_module``, ``_strip_json_comments``, ``_load_tsconfig``,
``TsConfig``, and ``JsTsResolver``.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from lexibrary.symbolgraph.resolver_js import (
    JsTsResolver,
    TsConfig,
    _load_tsconfig,
    _strip_json_comments,
    resolve_js_module,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_project(tmp_path: Path) -> Path:
    """Create a minimal project root with ``.lexibrary/``."""
    (tmp_path / ".lexibrary").mkdir(exist_ok=True)
    return tmp_path


def _write_file(project_root: Path, rel_path: str, content: str = "") -> Path:
    """Write a file under *project_root* and return its absolute path."""
    p = project_root / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


def _make_db_with_symbols(
    tmp_path: Path,
    symbols: list[dict[str, Any]],
) -> tuple[sqlite3.Connection, Path]:
    """Create an in-memory symbols.db with seeded symbols.

    Returns the open connection and the project root.
    """
    project_root = _make_project(tmp_path)
    conn = sqlite3.connect(":memory:")

    # Minimal schema sufficient for resolver queries
    conn.executescript("""
        CREATE TABLE files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL UNIQUE,
            language TEXT NOT NULL,
            last_hash TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE symbols (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL REFERENCES files(id),
            name TEXT NOT NULL,
            qualified_name TEXT,
            symbol_type TEXT NOT NULL,
            line_start INTEGER NOT NULL DEFAULT 0,
            line_end INTEGER NOT NULL DEFAULT 0,
            visibility TEXT,
            parent_class TEXT
        );
    """)

    # Track inserted files
    file_ids: dict[str, int] = {}
    for sym in symbols:
        fp = sym["file_path"]
        if fp not in file_ids:
            cur = conn.execute(
                "INSERT INTO files (path, language, last_hash) VALUES (?, ?, ?)",
                (fp, sym.get("language", "typescript"), ""),
            )
            file_ids[fp] = cur.lastrowid or 0

        conn.execute(
            "INSERT INTO symbols "
            "(file_id, name, qualified_name, symbol_type, line_start, line_end, "
            "visibility, parent_class) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                file_ids[fp],
                sym["name"],
                sym.get("qualified_name", sym["name"]),
                sym.get("symbol_type", "function"),
                sym.get("line_start", 1),
                sym.get("line_end", 5),
                sym.get("visibility", "public"),
                sym.get("parent_class"),
            ),
        )

    conn.commit()
    return conn, project_root


# ---------------------------------------------------------------------------
# resolve_js_module tests
# ---------------------------------------------------------------------------


class TestResolveJsRelativeImport:
    """Test ``resolve_js_module`` with relative import specifiers."""

    def test_resolver_js_relative_import(self, tmp_path: Path) -> None:
        """Relative import ``../a`` resolves to ``src/a/index.ts``."""
        project_root = _make_project(tmp_path)
        _write_file(project_root, "src/a/index.ts", "export function foo() {}")
        caller = _write_file(project_root, "src/b/user.ts", "")

        result = resolve_js_module(caller, "../a", project_root=project_root)
        assert result is not None
        assert result.name == "index.ts"
        assert "src/a" in str(result)

    def test_resolves_ts_extension(self, tmp_path: Path) -> None:
        """``./module`` resolves to ``module.ts`` when it exists."""
        project_root = _make_project(tmp_path)
        _write_file(project_root, "src/module.ts", "")
        caller = _write_file(project_root, "src/main.ts", "")

        result = resolve_js_module(caller, "./module", project_root=project_root)
        assert result is not None
        assert result.name == "module.ts"

    def test_resolves_explicit_extension(self, tmp_path: Path) -> None:
        """``./module.ts`` resolves directly."""
        project_root = _make_project(tmp_path)
        _write_file(project_root, "src/module.ts", "")
        caller = _write_file(project_root, "src/main.ts", "")

        result = resolve_js_module(caller, "./module.ts", project_root=project_root)
        assert result is not None
        assert result.name == "module.ts"


class TestResolveJsPathAlias:
    """Test ``resolve_js_module`` with tsconfig path aliases."""

    def test_resolver_js_path_alias(self, tmp_path: Path) -> None:
        """Path alias ``@/utils/parse`` resolves via tsconfig paths."""
        project_root = _make_project(tmp_path)
        _write_file(project_root, "src/utils/parse.ts", "export function parse() {}")
        caller = _write_file(project_root, "src/app/main.ts", "")

        tsconfig = TsConfig(
            base_url=(project_root / "src").resolve(),
            paths={"@/*": ["*"]},
        )

        result = resolve_js_module(
            caller,
            "@/utils/parse",
            project_root=project_root,
            tsconfig=tsconfig,
        )
        assert result is not None
        assert "parse.ts" in result.name

    def test_resolver_js_base_url_without_paths(self, tmp_path: Path) -> None:
        """Base URL alone does not resolve non-relative specifiers without paths."""
        project_root = _make_project(tmp_path)
        _write_file(project_root, "src/utils.ts", "")
        caller = _write_file(project_root, "src/main.ts", "")

        tsconfig = TsConfig(
            base_url=(project_root / "src").resolve(),
            paths={},
        )

        # "utils" is not relative and has no path alias -> None
        result = resolve_js_module(
            caller,
            "utils",
            project_root=project_root,
            tsconfig=tsconfig,
        )
        assert result is None

    def test_resolver_js_no_tsconfig_falls_back_to_node_resolution(self, tmp_path: Path) -> None:
        """Without tsconfig, non-relative specifiers return None."""
        project_root = _make_project(tmp_path)
        caller = _write_file(project_root, "src/main.ts", "")

        result = resolve_js_module(
            caller,
            "lodash",
            project_root=project_root,
            tsconfig=None,
        )
        assert result is None

    def test_resolver_js_node_module_specifier_returns_none(self, tmp_path: Path) -> None:
        """Bare module specifiers (npm packages) always return None."""
        project_root = _make_project(tmp_path)
        caller = _write_file(project_root, "src/main.ts", "")

        # Even with a tsconfig, bare specifiers that don't match paths return None
        tsconfig = TsConfig(
            base_url=(project_root / "src").resolve(),
            paths={"@/*": ["*"]},
        )

        result = resolve_js_module(
            caller,
            "lodash",
            project_root=project_root,
            tsconfig=tsconfig,
        )
        assert result is None


# ---------------------------------------------------------------------------
# _strip_json_comments tests
# ---------------------------------------------------------------------------


class TestStripJsonComments:
    """Test the JSON-with-comments stripping state machine."""

    def test_strip_json_comments_preserves_url_in_string(self) -> None:
        """URLs inside strings are not treated as comments."""
        text = '{"url": "https://example.com"}'
        assert _strip_json_comments(text) == text

    def test_strip_json_comments_line_comment(self) -> None:
        """Single-line ``//`` comments are stripped."""
        text = '{"key": "value"} // this is a comment\n'
        result = _strip_json_comments(text)
        parsed = json.loads(result.strip())
        assert parsed == {"key": "value"}

    def test_strip_json_comments_block_comment(self) -> None:
        """Block ``/* */`` comments are stripped."""
        text = '/* header */\n{"key": "value"}'
        result = _strip_json_comments(text)
        parsed = json.loads(result.strip())
        assert parsed == {"key": "value"}

    def test_strip_json_comments_escape_in_string(self) -> None:
        """Escaped quotes inside strings do not break the state machine."""
        text = r'{"msg": "escaped \" quote"}'
        result = _strip_json_comments(text)
        assert result == text

    def test_strip_json_comments_comment_like_in_string(self) -> None:
        """Comment-like sequences inside strings are preserved."""
        text = '{"comment": "/* not a comment */"}'
        result = _strip_json_comments(text)
        assert result == text

    def test_strip_json_comments_preserves_line_count(self) -> None:
        """Output has the same number of newlines as input."""
        text = '{\n  // line comment\n  /* block\n  comment */\n  "key": "val"\n}'
        result = _strip_json_comments(text)
        assert result.count("\n") == text.count("\n")


# ---------------------------------------------------------------------------
# _load_tsconfig / TsConfig tests
# ---------------------------------------------------------------------------


class TestTsConfig:
    """Test tsconfig.json loading."""

    def test_resolver_js_tsconfig_with_comments(self, tmp_path: Path) -> None:
        """tsconfig.json with comments is parsed successfully."""
        project_root = _make_project(tmp_path)
        tsconfig_content = """{
  // This is a comment
  "compilerOptions": {
    "baseUrl": "src",
    /* paths mapping */
    "paths": {
      "@/*": ["*"]
    }
  }
}"""
        (project_root / "tsconfig.json").write_text(tsconfig_content)

        config = _load_tsconfig(project_root)
        assert config is not None
        assert config.base_url is not None
        assert config.base_url == (project_root / "src").resolve()
        assert "@/*" in config.paths
        assert config.paths["@/*"] == ["*"]

    def test_load_tsconfig_no_file(self, tmp_path: Path) -> None:
        """Returns None when tsconfig.json does not exist."""
        project_root = _make_project(tmp_path)
        assert _load_tsconfig(project_root) is None

    def test_load_tsconfig_invalid_json(self, tmp_path: Path) -> None:
        """Returns None when tsconfig.json is invalid JSON."""
        project_root = _make_project(tmp_path)
        (project_root / "tsconfig.json").write_text("not valid json {{{")
        assert _load_tsconfig(project_root) is None

    def test_tsconfig_frozen(self) -> None:
        """TsConfig is immutable (frozen dataclass)."""
        config = TsConfig(base_url=None, paths={})
        with pytest.raises(AttributeError):
            config.base_url = Path("/new")  # type: ignore[misc]

    def test_load_tsconfig_no_compiler_options(self, tmp_path: Path) -> None:
        """Handles tsconfig.json without compilerOptions gracefully."""
        project_root = _make_project(tmp_path)
        (project_root / "tsconfig.json").write_text("{}")

        config = _load_tsconfig(project_root)
        assert config is not None
        assert config.base_url is None
        assert config.paths == {}


# ---------------------------------------------------------------------------
# JsTsResolver tests
# ---------------------------------------------------------------------------


class TestJsTsResolver:
    """Test the JsTsResolver class for cross-file symbol resolution."""

    def test_resolves_same_file_symbol(self, tmp_path: Path) -> None:
        """A call to a function in the same file resolves."""
        conn, project_root = _make_db_with_symbols(
            tmp_path,
            [
                {
                    "file_path": "src/app.ts",
                    "name": "helper",
                    "symbol_type": "function",
                },
                {
                    "file_path": "src/app.ts",
                    "name": "main",
                    "symbol_type": "function",
                },
            ],
        )

        from lexibrary.config.schema import LexibraryConfig

        resolver = JsTsResolver(conn, project_root, LexibraryConfig())

        # Look up the file_id for src/app.ts
        row = conn.execute("SELECT id FROM files WHERE path = ?", ("src/app.ts",)).fetchone()
        assert row is not None
        file_id = row[0]

        from lexibrary.ast_parser.models import CallSite

        call = CallSite(
            callee_name="helper",
            caller_name="main",
            line=5,
            receiver=None,
        )

        result = resolver.resolve(call, file_id, "src/app.ts")
        assert result is not None

        # Verify it resolved to the helper symbol
        sym_row = conn.execute("SELECT name FROM symbols WHERE id = ?", (result,)).fetchone()
        assert sym_row is not None
        assert sym_row[0] == "helper"

    def test_resolves_class_name_same_file(self, tmp_path: Path) -> None:
        """resolve_class_name finds a class in the same file."""
        conn, project_root = _make_db_with_symbols(
            tmp_path,
            [
                {
                    "file_path": "src/models.ts",
                    "name": "User",
                    "symbol_type": "class",
                },
            ],
        )

        from lexibrary.config.schema import LexibraryConfig

        resolver = JsTsResolver(conn, project_root, LexibraryConfig())

        row = conn.execute("SELECT id FROM files WHERE path = ?", ("src/models.ts",)).fetchone()
        assert row is not None
        file_id = row[0]

        result = resolver.resolve_class_name("User", file_id, "src/models.ts")
        assert result is not None

        sym_row = conn.execute(
            "SELECT name, symbol_type FROM symbols WHERE id = ?", (result,)
        ).fetchone()
        assert sym_row is not None
        assert sym_row[0] == "User"
        assert sym_row[1] == "class"

    def test_unresolved_returns_none(self, tmp_path: Path) -> None:
        """A call to a symbol not in DB returns None."""
        conn, project_root = _make_db_with_symbols(
            tmp_path,
            [
                {
                    "file_path": "src/app.ts",
                    "name": "main",
                    "symbol_type": "function",
                },
            ],
        )

        from lexibrary.config.schema import LexibraryConfig

        resolver = JsTsResolver(conn, project_root, LexibraryConfig())

        row = conn.execute("SELECT id FROM files WHERE path = ?", ("src/app.ts",)).fetchone()
        assert row is not None
        file_id = row[0]

        from lexibrary.ast_parser.models import CallSite

        call = CallSite(
            callee_name="nonexistent",
            caller_name="main",
            line=5,
            receiver=None,
        )

        result = resolver.resolve(call, file_id, "src/app.ts")
        assert result is None

    def test_resolve_class_name_returns_none_for_function(self, tmp_path: Path) -> None:
        """resolve_class_name does not match functions."""
        conn, project_root = _make_db_with_symbols(
            tmp_path,
            [
                {
                    "file_path": "src/app.ts",
                    "name": "NotAClass",
                    "symbol_type": "function",
                },
            ],
        )

        from lexibrary.config.schema import LexibraryConfig

        resolver = JsTsResolver(conn, project_root, LexibraryConfig())

        row = conn.execute("SELECT id FROM files WHERE path = ?", ("src/app.ts",)).fetchone()
        assert row is not None
        file_id = row[0]

        result = resolver.resolve_class_name("NotAClass", file_id, "src/app.ts")
        assert result is None
