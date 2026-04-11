"""Cross-file Python symbol resolver.

:class:`PythonResolver` implements the seven-step decision tree that turns a
:class:`~lexibrary.ast_parser.models.CallSite` emitted by the Python parser
into a concrete ``symbols.id`` row in ``.lexibrary/symbols.db``. It is the
language-specific counterpart to the intra-file
:class:`~lexibrary.symbolgraph.resolver_base.FallbackResolver` used for TS/JS.

Resolution strategy (Phase 2)
-----------------------------

The resolver walks the following priorities for each call, stopping at the
first match:

1. ``super().foo()`` — deliberately unresolved. MRO walking to a base class
   needs ``class_edges`` which land in Phase 3.
2. ``self.foo()`` — same-class method lookup via ``_resolve_self_method``.
3. Same-file free function or class by bare name.
4. Import-mapped call — the call's ``receiver`` matches an imported name
   (e.g. ``from pkg.b import bar; bar()`` or ``import pkg.b as lb; lb.foo()``).
5. Dotted receiver prefix walk — for calls like ``a.b.c.foo()`` where only
   ``a.b`` is imported, walk progressive prefixes (longest-first) looking
   for a match. On match, try ``<rest>.<bare>`` first and fall back to
   ``<bare>`` inside the target file.
6. Bare name in imports — ``from pkg.b import bar`` with a bare ``bar()``
   call, when step 3 did not match a same-file definition.
7. Fallthrough — return ``None`` so the builder records the call in
   ``unresolved_calls``.

Cross-file import resolution re-uses the shared helpers in
:mod:`lexibrary.symbolgraph.python_imports` so the link graph and the
symbol graph stay in lock-step. Per-file import maps are memoised against
the caller file path: the builder primes the cache once per file (passing
the pre-parsed tree-sitter tree so :func:`parse_imports` never re-reads
the file), and every subsequent :meth:`resolve` call for that file looks
up the cached mapping.

See ``CN-023 Symbol Resolution`` and ``plans/symbol-graph-2.md`` for the
full design rationale.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

from lexibrary.config.schema import LexibraryConfig
from lexibrary.symbolgraph import python_imports
from lexibrary.symbolgraph.python_imports import ImportBinding

if TYPE_CHECKING:
    from tree_sitter import Tree

    from lexibrary.ast_parser.models import CallSite


class PythonResolver:
    """Cross-file Python resolver.

    Uses the same module-resolution logic as
    :mod:`lexibrary.archivist.dependency_extractor` (via the shared
    :mod:`lexibrary.symbolgraph.python_imports` helpers) to convert an
    imported name to a file path, then looks up the symbol in that file.

    Instances are created once per full build or incremental refresh and
    must be discarded at the end of the build — they hold an open SQLite
    connection and a per-file import cache.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        project_root: Path,
        config: LexibraryConfig,
    ) -> None:
        """Initialise the resolver with a DB connection and project context.

        Args:
            conn: Open ``symbols.db`` connection. The resolver only issues
                ``SELECT`` statements; writes are owned by the builder.
            project_root: Absolute path to the project root. Passed through
                to :func:`lexibrary.symbolgraph.python_imports.parse_imports`
                so resolved import paths are normalised against a consistent
                root.
            config: The loaded :class:`LexibraryConfig`. Stored for future
                phase gates; Phase 2 does not branch on any config field.
        """
        self._conn = conn
        self._project_root = project_root
        self._config = config
        # Cache: caller_file_path → {imported_name: ImportBinding}.
        # Primed by the builder with the pre-parsed tree before any
        # ``resolve`` call for that file is issued.
        self._import_cache: dict[str, dict[str, ImportBinding]] = {}

    # ------------------------------------------------------------------
    # Protocol implementation
    # ------------------------------------------------------------------

    def resolve(
        self,
        call: CallSite,
        caller_file_id: int,
        caller_file_path: str,
    ) -> int | None:
        """Return the callee ``symbols.id`` for ``call`` or ``None`` if unresolved.

        Walks the seven-step decision tree documented in the module
        docstring. The bare name is extracted from ``call.callee_name`` by
        taking the final dotted component — e.g. ``foo.bar.baz`` becomes
        ``baz``. Receivers are inspected verbatim so
        ``self.method()``, ``ClassName.method()``, and
        ``module.submodule.foo()`` all route to their respective branches.

        Args:
            call: A :class:`CallSite` produced by the Python symbol extractor.
            caller_file_id: ``symbols.files.id`` of the file containing the
                call site. Used by the same-file and self-method lookups.
            caller_file_path: Project-relative path string of the caller
                file. Used as the cache key for the per-file import map.

        Returns:
            The ``symbols.id`` of the resolved callee, or ``None`` when no
            definite match exists. ``None`` causes the builder to record
            the call in ``unresolved_calls`` instead of ``calls``.
        """
        # 1. super() calls are intentionally unresolved in Phase 2.
        #    MRO walking to a base class needs class_edges which only
        #    land in Phase 3.
        if call.receiver == "super" or call.callee_name.startswith("super."):
            return None

        # 2. self.foo() → same-class lookup.
        if call.receiver == "self":
            return self._resolve_self_method(call, caller_file_id)

        bare = call.callee_name.rsplit(".", 1)[-1]

        # 3. Free function / class defined in the same file.
        local_row = self._conn.execute(
            "SELECT id FROM symbols WHERE file_id = ? AND name = ? "
            "AND symbol_type IN ('function', 'class')",
            (caller_file_id, bare),
        ).fetchone()
        if local_row is not None:
            return int(local_row[0])

        # 4. Resolve via imports (cached; the builder primes the cache).
        imports = self._imports_for(caller_file_path)

        if call.receiver and call.receiver in imports:
            # Direct receiver match: e.g. ``from pkg.b import bar; bar()``
            # (``call.receiver`` is the bare ``"bar"``) or
            # ``import pkg.b as lb; lb.foo()`` (``call.receiver == "lb"``).
            # For module-target imports the lookup name is the trailing
            # call attribute (``bare``); for symbol-target imports the
            # lookup name is the binding's preserved ``original_name``.
            binding = imports[call.receiver]
            lookup_name = binding.original_name or bare
            return self._lookup_in_file(binding.file_path, lookup_name)

        # 5. Dotted receiver prefix walk. Handles cases like
        #    ``import a.b; a.b.foo()`` (receiver ``"a.b"`` hits step 4
        #    because the plain-import binding is the dotted module path),
        #    as well as ``import a.b; a.b.c.foo()`` which needs a prefix
        #    walk — the longest matching prefix ``"a.b"`` points at
        #    ``a/b.py`` and we then look up ``c.foo`` or ``foo`` inside it.
        if call.receiver and "." in call.receiver:
            parts = call.receiver.split(".")
            for i in range(len(parts), 0, -1):
                prefix = ".".join(parts[:i])
                if prefix in imports:
                    binding = imports[prefix]
                    rest = parts[i:]  # attributes after the matched prefix
                    nested_name = ".".join([*rest, bare]) if rest else bare
                    hit = self._lookup_in_file(binding.file_path, nested_name)
                    if hit is not None:
                        return hit
                    # Fall through — also try the bare name as a last
                    # resort (e.g. a module's top-level function).
                    return self._lookup_in_file(binding.file_path, bare)

        # 6. Bare name in imports (no receiver, matching the imported name).
        #    e.g. ``from pkg.b import bar; bar()`` or
        #    ``from pkg.b import bar as baz; baz()`` where we must look
        #    up the original ``bar`` in ``b.py`` rather than the alias.
        if bare in imports:
            binding = imports[bare]
            lookup_name = binding.original_name or bare
            return self._lookup_in_file(binding.file_path, lookup_name)

        # 7. Fallthrough — unresolved.
        return None

    # ------------------------------------------------------------------
    # Import map caching
    # ------------------------------------------------------------------

    def _imports_for(
        self,
        caller_file_path: str,
        tree: Tree | None = None,
        source_bytes: bytes | None = None,
    ) -> dict[str, ImportBinding]:
        """Return the cached import binding map for ``caller_file_path``.

        Memoised against ``caller_file_path``. The **builder** is expected
        to call this helper once per file with the pre-parsed tree-sitter
        tree before issuing any :meth:`resolve` calls for that file — that
        priming call runs :func:`python_imports.parse_imports` against the
        already-open tree and stores the result in the cache.

        Subsequent calls (including every call from :meth:`resolve`, which
        does not have the tree on hand) return the cached value directly.
        If the cache is missing and no tree has been supplied, this helper
        returns an empty dict as a defensive fallback — it deliberately
        never re-parses the file itself. That keeps Phase 2's "parse once,
        reuse across extractors" contract intact and guarantees call
        resolution and the rest of the symbol extraction share the same
        tree buffer.

        Args:
            caller_file_path: Project-relative path string used as the
                cache key. The same key is used by :meth:`resolve`.
            tree: Optional pre-parsed tree-sitter tree. Required on the
                first call for a given path — omit on subsequent calls
                and on the defensive fallback from :meth:`resolve`.
            source_bytes: Raw bytes of the source file ``tree`` was parsed
                from. Passed through to :func:`parse_imports`.

        Returns:
            ``{imported_name: ImportBinding}`` for the file. An empty
            dict when no imports resolve or when the cache miss falls
            through to the defensive fallback.
        """
        cached = self._import_cache.get(caller_file_path)
        if cached is not None:
            return cached

        if tree is None or source_bytes is None:
            # Defensive fallback: the builder hasn't primed the cache for
            # this file and we can't re-parse here without violating the
            # parse-tree-reuse contract. Return an empty map so
            # ``resolve`` simply skips the import-aware branches and falls
            # through to step 7 (unresolved).
            return {}

        imports = python_imports.parse_imports(
            tree,
            source_bytes,
            Path(caller_file_path),
            self._project_root,
        )
        self._import_cache[caller_file_path] = imports
        return imports

    # ------------------------------------------------------------------
    # Lookup helpers
    # ------------------------------------------------------------------

    def _lookup_in_file(self, file_path: str, symbol_name: str) -> int | None:
        """Return ``symbols.id`` for ``symbol_name`` in ``file_path`` or ``None``.

        Runs the canonical single-file lookup: join ``symbols`` against
        ``files`` on ``path`` equality and match ``name``. Returns the first
        row found — ambiguity is not a concern here because the caller has
        already narrowed the search to one specific file via import
        resolution, and any duplicate ``(name, symbol_type, parent_class)``
        triple would be caught by the ``symbols`` UNIQUE constraint at
        insert time.

        Args:
            file_path: Project-relative path to the target file.
            symbol_name: Bare (or possibly dotted, for nested names)
                symbol name to look up.

        Returns:
            The resolved ``symbols.id``, or ``None`` when the file is not
            in the DB or has no matching symbol.
        """
        row = self._conn.execute(
            "SELECT id FROM symbols WHERE file_id = ("
            "  SELECT id FROM files WHERE path = ?"
            ") AND name = ?",
            (file_path, symbol_name),
        ).fetchone()
        if row is None:
            return None
        return int(row[0])

    def _resolve_self_method(
        self,
        call: CallSite,
        caller_file_id: int,
    ) -> int | None:
        """Resolve a ``self.foo()`` call to a method on the enclosing class.

        The flow:

        1. Find the caller symbol's ``line_start`` by looking up the row
           with the caller's ``name`` in the same file (``caller_file_id``).
           Used to pin which class the caller is inside.
        2. Find the smallest ``class`` row in the same file whose
           ``line_start < caller_line`` and ``line_end >= caller_line``.
           That is the enclosing class; there may be multiple candidates
           (nested classes) and we take the innermost by ``line_start``.
        3. Look up a ``method`` row in that class (``parent_class``
           matching the class's ``name``) by bare method name.

        Returns ``None`` when the caller isn't inside a class, the class
        has no matching method, or the method's extractor recorded a
        different ``parent_class``. MRO walking to a base class lands in
        Phase 3 — this Phase 2 implementation deliberately returns
        ``None`` for inherited methods so the call flows to
        ``unresolved_calls``.

        Args:
            call: The ``self.foo()`` :class:`CallSite` being resolved.
            caller_file_id: ``files.id`` of the file containing the call.

        Returns:
            The resolved method's ``symbols.id`` or ``None``.
        """
        bare = call.callee_name.rsplit(".", 1)[-1]

        # 1. Find the caller symbol row to learn its line_start. The
        #    Python parser stores the caller's fully-qualified name on the
        #    emitted :class:`CallSite`, so the lookup uses
        #    ``qualified_name`` to disambiguate same-named methods across
        #    classes in the same file.
        caller_row = self._conn.execute(
            "SELECT line_start FROM symbols "
            "WHERE file_id = ? AND qualified_name = ? "
            "  AND symbol_type IN ('function', 'method')",
            (caller_file_id, call.caller_name),
        ).fetchone()
        if caller_row is None:
            return None
        caller_line = int(caller_row[0])

        # 2. Find the enclosing class in the same file. Take the innermost
        #    (largest line_start still before the caller) to handle nested
        #    class definitions correctly.
        enclosing_class = self._conn.execute(
            "SELECT id, name FROM symbols "
            "WHERE file_id = ? AND symbol_type = 'class' "
            "  AND line_start < ? AND line_end >= ? "
            "ORDER BY line_start DESC LIMIT 1",
            (caller_file_id, caller_line, caller_line),
        ).fetchone()
        if enclosing_class is None:
            return None
        class_name = str(enclosing_class[1])

        # 3. Look up the method on that class by bare name. ``parent_class``
        #    matches the class's ``name`` — the symbol extractor records the
        #    enclosing class name there for every method row.
        method_row = self._conn.execute(
            "SELECT id FROM symbols "
            "WHERE file_id = ? AND name = ? "
            "  AND symbol_type = 'method' AND parent_class = ?",
            (caller_file_id, bare, class_name),
        ).fetchone()
        if method_row is None:
            return None
        return int(method_row[0])
