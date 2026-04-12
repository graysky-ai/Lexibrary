"""Cross-file JavaScript/TypeScript symbol resolver.

:class:`JsTsResolver` implements the :class:`SymbolResolver` protocol for
JavaScript and TypeScript source files. It replaces the intra-file
:class:`~lexibrary.symbolgraph.resolver_base.FallbackResolver` that was used
as a placeholder through Phases 2-5.

Resolution strategy (Phase 6)
-----------------------------

For call-site resolution (:meth:`resolve`):

1. Extract the bare callee name from the dotted ``callee_name``.
2. Look up in the caller's own file (same-file definition).
3. Parse import statements from the caller file and try to match the
   receiver or bare name against imported bindings.
4. Fall through to ``None`` (unresolved) for node_modules specifiers.

For class-name resolution (:meth:`resolve_class_name`):

1. Same-file class lookup by bare name.
2. Import-aware cross-file lookup, constrained to ``symbol_type='class'``.
3. Fall through to ``None`` for unresolved names.

The module also provides the shared :func:`resolve_js_module` helper,
extracted from ``archivist/dependency_extractor.py``, which handles
relative import resolution with extension probing and ``tsconfig.json``
path alias support.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lexibrary.ast_parser.models import CallSite
    from lexibrary.config.schema import LexibraryConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants extracted from dependency_extractor.py
# ---------------------------------------------------------------------------

# Extensions to try when resolving JS/TS imports without an explicit extension
_JS_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx")
_JS_INDEX_NAMES = ("index.ts", "index.tsx", "index.js", "index.jsx")


# ---------------------------------------------------------------------------
# tsconfig.json support
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TsConfig:
    """Parsed ``tsconfig.json`` compiler options relevant to module resolution.

    Only ``baseUrl`` and ``paths`` are extracted — the rest of the compiler
    options are irrelevant for symbol resolution.
    """

    base_url: Path | None
    paths: dict[str, list[str]]


def _strip_json_comments(text: str) -> str:
    """Strip ``//`` and ``/* */`` comments from JSON-with-comments text.

    Uses a character-by-character state machine with four states:
    ``normal``, ``in_string``, ``in_line_comment``, ``in_block_comment``.

    Preserves strings that contain comment-like sequences (e.g.
    ``"url": "https://example.com"``). Maintains the same number of
    ``\\n`` characters in the output so line numbers in error messages
    stay correct.
    """
    result: list[str] = []
    i = 0
    n = len(text)
    state = "normal"

    while i < n:
        ch = text[i]

        if state == "normal":
            if ch == '"':
                state = "in_string"
                result.append(ch)
                i += 1
            elif ch == "/" and i + 1 < n and text[i + 1] == "/":
                state = "in_line_comment"
                i += 2
            elif ch == "/" and i + 1 < n and text[i + 1] == "*":
                state = "in_block_comment"
                i += 2
            else:
                result.append(ch)
                i += 1

        elif state == "in_string":
            if ch == "\\" and i + 1 < n:
                # Escaped character — emit both and skip past
                result.append(ch)
                result.append(text[i + 1])
                i += 2
            elif ch == '"':
                state = "normal"
                result.append(ch)
                i += 1
            else:
                result.append(ch)
                i += 1

        elif state == "in_line_comment":
            if ch == "\n":
                # Preserve the newline to maintain line count
                result.append("\n")
                state = "normal"
            i += 1

        elif state == "in_block_comment":
            if ch == "\n":
                # Preserve newlines inside block comments
                result.append("\n")
                i += 1
            elif ch == "*" and i + 1 < n and text[i + 1] == "/":
                state = "normal"
                i += 2
            else:
                i += 1

    return "".join(result)


def _load_tsconfig(project_root: Path) -> TsConfig | None:
    """Load ``tsconfig.json`` from *project_root* and extract resolution options.

    Reads ``compilerOptions.baseUrl`` and ``compilerOptions.paths``.
    If the file does not exist or fails to parse, returns ``None``.
    Supports JSON-with-comments (``//`` and ``/* */``) via
    :func:`_strip_json_comments`.

    Args:
        project_root: Absolute path to the project root directory.

    Returns:
        A :class:`TsConfig` with the extracted options, or ``None``.
    """
    tsconfig_path = project_root / "tsconfig.json"
    if not tsconfig_path.exists():
        return None

    try:
        raw = tsconfig_path.read_text(encoding="utf-8")
        cleaned = _strip_json_comments(raw)
        data = json.loads(cleaned)
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("Failed to parse tsconfig.json at %s: %s", tsconfig_path, exc)
        return None

    compiler_options = data.get("compilerOptions", {})
    if not isinstance(compiler_options, dict):
        return None

    raw_base_url = compiler_options.get("baseUrl")
    base_url: Path | None = None
    if isinstance(raw_base_url, str):
        base_url = (project_root / raw_base_url).resolve()

    raw_paths = compiler_options.get("paths", {})
    paths: dict[str, list[str]] = {}
    if isinstance(raw_paths, dict):
        for pattern, targets in raw_paths.items():
            if isinstance(targets, list):
                paths[pattern] = [t for t in targets if isinstance(t, str)]

    return TsConfig(base_url=base_url, paths=paths)


# ---------------------------------------------------------------------------
# Shared resolve_js_module helper (extracted from dependency_extractor.py)
# ---------------------------------------------------------------------------


def resolve_js_module(
    caller_file: Path,
    specifier: str,
    *,
    project_root: Path,
    tsconfig: TsConfig | None = None,
) -> Path | None:
    """Resolve a JS/TS import specifier to an absolute file path.

    Resolution order:

    1. **Relative import** (starts with ``./`` or ``../``) -- resolve
       relative to the caller file's directory. Tries the literal path
       first, then appends common extensions (``.ts``, ``.tsx``, ``.js``,
       ``.jsx``), and finally checks for index files.

    2. **Path alias** -- if *tsconfig* is provided, matches the specifier
       against ``tsconfig.paths`` patterns (supports ``@/*`` wildcards).
       Resolves the matched path relative to ``tsconfig.baseUrl``.

    3. **Node module** -- bare specifiers (e.g. ``lodash``) that don't
       match any path alias return ``None``.

    Args:
        caller_file: Absolute path to the importing file.
        specifier: The import specifier string, e.g. ``"./module"`` or
            ``"@/utils/parse"``.
        project_root: Absolute path to the project root.
        tsconfig: Parsed tsconfig options. ``None`` disables path alias
            resolution.

    Returns:
        Absolute path to the resolved file, or ``None`` if unresolvable.
    """
    source_dir = caller_file.parent

    # 1. Relative import
    if specifier.startswith("./") or specifier.startswith("../"):
        return _resolve_relative(specifier, source_dir, project_root)

    # 2. Path alias via tsconfig
    if tsconfig is not None:
        hit = _resolve_path_alias(specifier, tsconfig, project_root)
        if hit is not None:
            return hit

    # 3. Node module — return None
    return None


def _resolve_relative(
    import_path: str,
    source_dir: Path,
    project_root: Path,
) -> Path | None:
    """Resolve a relative JS/TS import to an absolute file path.

    Tries the literal path first, then appends common extensions, and
    finally checks for index files.

    Args:
        import_path: Relative import path, e.g. ``"./module"``.
        source_dir: Directory containing the importing file.
        project_root: Absolute path to the project root.

    Returns:
        Absolute path to the resolved file, or ``None``.
    """
    base = (source_dir / import_path).resolve()

    # Already has a recognised extension — check directly
    if base.suffix in _JS_EXTENSIONS:
        if base.exists():
            try:
                base.relative_to(project_root.resolve())
                return base
            except ValueError:
                return None
        return None

    # Try adding common extensions
    for ext in _JS_EXTENSIONS:
        candidate = base.with_suffix(ext)
        if candidate.exists():
            try:
                candidate.relative_to(project_root.resolve())
                return candidate
            except ValueError:
                return None

    # Try index files (e.g. ./components -> ./components/index.ts)
    for name in _JS_INDEX_NAMES:
        candidate = base / name
        if candidate.exists():
            try:
                candidate.relative_to(project_root.resolve())
                return candidate
            except ValueError:
                return None

    return None


def _resolve_path_alias(
    specifier: str,
    tsconfig: TsConfig,
    project_root: Path,
) -> Path | None:
    """Resolve a specifier against ``tsconfig.paths`` patterns.

    Supports the ``@/*`` wildcard pattern: the ``*`` in the pattern
    matches the suffix of the specifier, and the ``*`` in each target
    is replaced with the matched suffix. Resolution then probes for
    extensions and index files the same way as relative imports.

    Args:
        specifier: The import specifier, e.g. ``"@/utils/parse"``.
        tsconfig: The parsed :class:`TsConfig`.
        project_root: Project root for path resolution.

    Returns:
        Absolute path to the resolved file, or ``None``.
    """
    base_url = tsconfig.base_url or project_root

    for pattern, targets in tsconfig.paths.items():
        if "*" in pattern:
            prefix = pattern.split("*", 1)[0]
            if specifier.startswith(prefix):
                suffix = specifier[len(prefix) :]
                for target_pattern in targets:
                    target_path_str = target_pattern.replace("*", suffix)
                    target_base = (base_url / target_path_str).resolve()

                    # Try the path as-is (with explicit extension)
                    if target_base.suffix in _JS_EXTENSIONS and target_base.exists():
                        return target_base

                    # Try adding extensions
                    for ext in _JS_EXTENSIONS:
                        candidate = target_base.with_suffix(ext)
                        if candidate.exists():
                            return candidate

                    # Try index files
                    for name in _JS_INDEX_NAMES:
                        candidate = target_base / name
                        if candidate.exists():
                            return candidate
        else:
            # Exact match (no wildcard)
            if specifier == pattern:
                for target_path_str in targets:
                    target_base = (base_url / target_path_str).resolve()

                    if target_base.suffix in _JS_EXTENSIONS and target_base.exists():
                        return target_base

                    for ext in _JS_EXTENSIONS:
                        candidate = target_base.with_suffix(ext)
                        if candidate.exists():
                            return candidate

                    for name in _JS_INDEX_NAMES:
                        candidate = target_base / name
                        if candidate.exists():
                            return candidate

    return None


# ---------------------------------------------------------------------------
# JsTsResolver — SymbolResolver protocol implementation
# ---------------------------------------------------------------------------


class JsTsResolver:
    """Cross-file JavaScript/TypeScript symbol resolver.

    Replaces the :class:`~lexibrary.symbolgraph.resolver_base.FallbackResolver`
    for ``.ts``, ``.tsx``, ``.js``, and ``.jsx`` files. Uses import statement
    parsing and ``tsconfig.json`` path aliases to resolve cross-file call sites
    and class-name references.

    Instances are created once per build run and hold an open SQLite
    connection plus a per-file import cache. They must be discarded at the
    end of the build.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        project_root: Path,
        config: LexibraryConfig,
    ) -> None:
        """Initialise the resolver with a DB connection and project context.

        Args:
            conn: Open ``symbols.db`` connection (read-only for the resolver).
            project_root: Absolute path to the project root.
            config: The loaded config. Stored for future phase gates.
        """
        self._conn = conn
        self._project_root = project_root
        self._config = config
        self._tsconfig = _load_tsconfig(project_root)
        # Cache: caller_file_path -> {imported_name: resolved_file_path}
        self._import_cache: dict[str, dict[str, str]] = {}

    # ------------------------------------------------------------------
    # Protocol implementation
    # ------------------------------------------------------------------

    def resolve(
        self,
        call: CallSite,
        caller_file_id: int,
        caller_file_path: str,
    ) -> int | None:
        """Return the callee ``symbols.id`` for *call* or ``None`` if unresolved.

        Resolution steps:

        1. Same-file lookup by bare callee name.
        2. Import-aware cross-file lookup: if the call has a receiver that
           matches an imported module, look up the callee in the target file.
        3. Bare name import lookup.
        4. Fall through to ``None`` (unresolved).

        Args:
            call: A :class:`CallSite` produced by the JS/TS symbol extractor.
            caller_file_id: ``files.id`` of the file containing the call site.
            caller_file_path: Project-relative path string of the caller file.

        Returns:
            The resolved callee's ``symbols.id``, or ``None``.
        """
        bare = call.callee_name.rsplit(".", 1)[-1]

        # 1. Same-file lookup
        local_row = self._conn.execute(
            "SELECT id FROM symbols WHERE file_id = ? AND name = ? "
            "AND symbol_type IN ('function', 'method', 'class')",
            (caller_file_id, bare),
        ).fetchone()
        if local_row is not None:
            return int(local_row[0])

        # 2. Import-aware lookup
        imports = self._imports_for(caller_file_path)

        if call.receiver and call.receiver in imports:
            target_file = imports[call.receiver]
            return self._lookup_in_file(target_file, bare)

        # 3. Bare name in imports
        if bare in imports:
            target_file = imports[bare]
            return self._lookup_in_file(target_file, bare)

        # 4. Unresolved
        return None

    def resolve_class_name(
        self,
        name: str,
        caller_file_id: int,
        caller_file_path: str,
    ) -> int | None:
        """Resolve a bare class name to a ``symbols.id`` with ``symbol_type='class'``.

        Used by the builder's pass 3 to resolve :class:`ClassEdgeSite`
        target names for class edge tables.

        Args:
            name: Bare or dotted class name.
            caller_file_id: ``files.id`` of the file where the edge originates.
            caller_file_path: Project-relative path string of the originating file.

        Returns:
            The ``symbols.id`` of the matching class, or ``None``.
        """
        bare = name.rsplit(".", 1)[-1]

        # Same-file class lookup
        local_row = self._conn.execute(
            "SELECT id FROM symbols WHERE file_id = ? AND name = ? AND symbol_type = 'class'",
            (caller_file_id, bare),
        ).fetchone()
        if local_row is not None:
            return int(local_row[0])

        # Import-aware cross-file lookup
        imports = self._imports_for(caller_file_path)

        if bare in imports:
            target_file = imports[bare]
            return self._lookup_class_in_file(target_file, bare)

        # Dotted prefix walk
        if "." in name:
            parts = name.split(".")
            for i in range(len(parts) - 1, 0, -1):
                prefix = ".".join(parts[:i])
                if prefix in imports:
                    target_file = imports[prefix]
                    rest = parts[i:]
                    nested_name = ".".join(rest) if rest else bare
                    hit = self._lookup_class_in_file(target_file, nested_name)
                    if hit is not None:
                        return hit
                    return self._lookup_class_in_file(target_file, bare)

        return None

    # ------------------------------------------------------------------
    # Import parsing
    # ------------------------------------------------------------------

    def prime_imports(
        self,
        caller_file_path: str,
        source_bytes: bytes,
    ) -> None:
        """Prime the import cache for *caller_file_path*.

        Parses import statements from the raw source bytes using simple
        regex-based extraction (no tree-sitter dependency at resolve time).
        The builder calls this once per file before issuing resolve calls.

        Args:
            caller_file_path: Project-relative path string used as cache key.
            source_bytes: Raw bytes of the source file.
        """
        if caller_file_path in self._import_cache:
            return

        imports: dict[str, str] = {}
        caller_abs = self._project_root / caller_file_path

        text = source_bytes.decode("utf-8", errors="replace")

        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith("import") and not stripped.startswith("export"):
                continue

            # Extract the specifier from import/export statements
            specifier = self._extract_specifier(stripped)
            if specifier is None:
                continue

            # Extract the imported names
            names = self._extract_import_names(stripped)

            resolved = resolve_js_module(
                caller_abs,
                specifier,
                project_root=self._project_root,
                tsconfig=self._tsconfig,
            )
            if resolved is None:
                continue

            try:
                rel_resolved = str(resolved.relative_to(self._project_root))
            except ValueError:
                continue

            for name in names:
                imports[name] = rel_resolved

            # Also map the module specifier's basename as a namespace import
            # (e.g. `import * as utils from './utils'` — the `utils` name
            # is extracted by _extract_import_names)
            # No extra work needed; _extract_import_names handles namespace.

        self._import_cache[caller_file_path] = imports

    def _imports_for(self, caller_file_path: str) -> dict[str, str]:
        """Return the cached import map for *caller_file_path*.

        Returns an empty dict if the cache has not been primed.
        """
        return self._import_cache.get(caller_file_path, {})

    @staticmethod
    def _extract_specifier(line: str) -> str | None:
        """Extract the module specifier string from an import/export line.

        Handles both single-quoted and double-quoted specifiers.
        Returns ``None`` if no specifier is found.
        """
        for quote in ('"', "'"):
            start = line.find(quote)
            if start == -1:
                continue
            end = line.find(quote, start + 1)
            if end == -1:
                continue
            return line[start + 1 : end]
        return None

    @staticmethod
    def _extract_import_names(line: str) -> list[str]:
        """Extract imported symbol names from an import statement line.

        Handles:
        - ``import { A, B } from "..."`` -> ``["A", "B"]``
        - ``import X from "..."`` -> ``["X"]``
        - ``import * as NS from "..."`` -> ``["NS"]``
        - ``import "..."`` (side-effect) -> ``[]``
        """
        stripped = line.strip()
        names: list[str] = []

        # Namespace import: import * as NS from "..."
        if "* as " in stripped:
            idx = stripped.index("* as ")
            rest = stripped[idx + 5 :].strip()
            # NS is the word before "from"
            ns_name = rest.split()[0] if rest.split() else None
            if ns_name and ns_name != "from":
                names.append(ns_name)
            return names

        # Named imports: import { A, B as C } from "..."
        if "{" in stripped and "}" in stripped:
            brace_start = stripped.index("{")
            brace_end = stripped.index("}")
            inner = stripped[brace_start + 1 : brace_end]
            for part in inner.split(","):
                part = part.strip()
                if not part:
                    continue
                # Handle aliasing: A as B -> use A (the original name for lookup)
                tokens = part.split()
                if len(tokens) >= 3 and tokens[1] == "as":
                    # Use the alias as the local name for matching calls
                    names.append(tokens[2])
                else:
                    names.append(tokens[0])
            return names

        # Default import: import X from "..."
        # Pattern: import <name> from "..."
        if stripped.startswith("import "):
            after_import = stripped[7:].strip()
            # Skip "type" keyword if present
            if after_import.startswith("type "):
                after_import = after_import[5:].strip()
            # The default imported name is the first word before "from"
            first_word = after_import.split()[0] if after_import.split() else ""
            if first_word and first_word not in ('"', "'", "from", "{", "*"):
                names.append(first_word)
            return names

        return names

    # ------------------------------------------------------------------
    # Lookup helpers
    # ------------------------------------------------------------------

    def _lookup_in_file(self, file_path: str, symbol_name: str) -> int | None:
        """Return ``symbols.id`` for *symbol_name* in *file_path* or ``None``."""
        row = self._conn.execute(
            "SELECT id FROM symbols WHERE file_id = ("
            "  SELECT id FROM files WHERE path = ?"
            ") AND name = ?",
            (file_path, symbol_name),
        ).fetchone()
        if row is None:
            return None
        return int(row[0])

    def _lookup_class_in_file(self, file_path: str, symbol_name: str) -> int | None:
        """Return ``symbols.id`` for a class named *symbol_name* in *file_path*."""
        row = self._conn.execute(
            "SELECT id FROM symbols WHERE file_id = ("
            "  SELECT id FROM files WHERE path = ?"
            ") AND name = ? AND symbol_type = 'class'",
            (file_path, symbol_name),
        ).fetchone()
        if row is None:
            return None
        return int(row[0])
