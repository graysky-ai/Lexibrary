"""Symbol graph builder — populates symbols.db from source files.

Phase 2 ships the first real rebuild pipeline: a two-pass full rebuild that
parses each source file exactly once and shares the resulting tree-sitter
``Tree`` between symbol extraction and the Python import resolver. Pass 1
records every definition into ``symbols``; pass 2 resolves every call-site
into either ``calls`` (when a definite callee row exists) or
``unresolved_calls`` (when not). Both passes run inside a single SQLite
transaction — per-INSERT autocommit is catastrophically slow on the 250-file
benchmark fixture.

Phase 1 shipped a no-op skeleton that prepared the schema and returned an
empty :class:`SymbolBuildResult`. Phase 3 will add class edges, Phase 4
enum/constant members, Phase 5 design-file enrichment, and Phase 6 a real
incremental refresh path plus composition edges.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from lexibrary.config.schema import LexibraryConfig
from lexibrary.symbolgraph.resolver_base import FallbackResolver
from lexibrary.symbolgraph.resolver_python import PythonResolver
from lexibrary.symbolgraph.schema import (
    SCHEMA_VERSION,
    check_schema_version,
    ensure_schema,
    set_pragmas,
)
from lexibrary.utils.hashing import hash_file
from lexibrary.utils.paths import symbols_db_path

if TYPE_CHECKING:
    from tree_sitter import Tree

    from lexibrary.ast_parser.models import EnumMemberSig, SymbolExtract

logger = logging.getLogger(__name__)


_PY_EXTENSIONS: frozenset[str] = frozenset({".py", ".pyi"})
_TS_EXTENSIONS: frozenset[str] = frozenset({".ts", ".tsx"})
_JS_EXTENSIONS: frozenset[str] = frozenset({".js", ".jsx", ".mjs", ".cjs"})


@dataclass
class SymbolBuildResult:
    """Summary of a :func:`build_symbol_graph` run.

    Every counter is zero until the builder actually populates the matching
    tables. Phase 2 fills :attr:`file_count`, :attr:`symbol_count`,
    :attr:`call_count`, and :attr:`unresolved_call_count`. Phase 3 (the
    symbol-graph-3 change) fills :attr:`class_edge_count` and
    :attr:`class_edge_unresolved_count` from the new pass-3 class-edge
    resolver; member counts remain zero until Phase 4.
    """

    file_count: int = 0
    symbol_count: int = 0
    call_count: int = 0
    unresolved_call_count: int = 0
    class_edge_count: int = 0
    class_edge_unresolved_count: int = 0
    member_count: int = 0
    duration_ms: int = 0
    errors: list[str] = field(default_factory=list)
    build_type: str = "full"  # 'full' | 'incremental'


def build_symbol_graph(
    project_root: Path,
    config: LexibraryConfig,
    *,
    changed_paths: list[Path] | None = None,
) -> SymbolBuildResult:
    """Rebuild ``.lexibrary/symbols.db`` via a two-pass full rebuild.

    Parameters
    ----------
    project_root:
        Project root containing a ``.lexibrary/`` directory (or the place to
        create one). The database lives at ``symbols_db_path(project_root)``.
    config:
        The loaded :class:`LexibraryConfig`. ``config.symbols.enabled`` gates
        the entire pipeline — a disabled config short-circuits before any
        filesystem mutation (no ``.lexibrary/`` directory is created and no
        DB file is touched).
    changed_paths:
        Accepted for API parity with :func:`lexibrary.index.build_index` but
        Phase 2 always performs a full rebuild. When ``None``, ``build_type``
        on the result is ``"full"``; when a list is passed (even empty) it is
        ``"incremental"``. The label is preserved for telemetry only — real
        incremental refresh lands in Phase 6.

    Returns
    -------
    SymbolBuildResult
        Per-run counters plus the wall-clock ``duration_ms``. Phase 2 fills
        file/symbol/call counts; class-edge and member counts stay zero until
        later phases wire those extractors in.
    """
    started = time.monotonic()
    result = SymbolBuildResult(
        build_type="full" if changed_paths is None else "incremental",
    )

    if not config.symbols.enabled:
        logger.debug("symbols.enabled=False — skipping symbol graph build")
        return result

    # Deferred import of :func:`discover_source_files` breaks the circular
    # chain: ``symbolgraph.__init__`` eagerly loads this module at package
    # import time, and the ``ast_parser`` package transitively imports from
    # ``symbolgraph.python_imports``. Pulling the archivist import inside
    # the function lets both packages finish initialising before the build
    # runs. The same technique is used by :func:`_parse_source` and
    # :func:`_extract_symbols_for` for the language-specific parsers.
    from lexibrary.archivist.pipeline import discover_source_files

    # Resolve the project root so ``Path.relative_to`` calls in pass 1 cope
    # with symlinked tempdirs (macOS ``/tmp`` → ``/private/tmp``). The
    # discovered source paths are already resolved inside
    # :func:`discover_source_files`, so without this the relative-path
    # computation fails on any unresolved project root.
    project_root = project_root.resolve()

    db_path = symbols_db_path(project_root)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        set_pragmas(conn)
        # Force rebuild: Phase 2 always wipes and recreates so cross-file
        # resolution sees a consistent snapshot. Incremental refresh lands
        # in Phase 6.
        ensure_schema(conn, force=True)

        source_files = discover_source_files(project_root, config)

        # tree_cache keeps the parse output alive across both passes so the
        # Python resolver can prime its import map from the already-parsed
        # tree instead of re-reading the file.
        tree_cache: dict[Path, tuple[Tree, bytes]] = {}
        extracts: list[tuple[Path, SymbolExtract]] = []
        file_id_map: dict[str, int] = {}

        # Wrap both passes in a single transaction. Per-INSERT autocommit is
        # catastrophically slow on SQLite for the 250-file fixture.
        with conn:
            # ---- Pass 1: definitions --------------------------------------
            for src in source_files:
                parsed = _parse_source(src)
                if parsed is None:
                    continue
                tree, source_bytes = parsed
                extract = _extract_symbols_for(
                    src,
                    tree,
                    source_bytes,
                    project_root,
                )
                if extract is None:
                    continue
                tree_cache[src] = (tree, source_bytes)

                rel_path = str(src.relative_to(project_root))
                cursor = conn.execute(
                    "INSERT INTO files (path, language, last_hash) VALUES (?, ?, ?)",
                    (rel_path, extract.language, hash_file(src)),
                )
                file_id = cursor.lastrowid
                if file_id is None:  # pragma: no cover - sqlite always sets it
                    continue
                file_id_map[rel_path] = file_id

                for definition in extract.definitions:
                    conn.execute(
                        "INSERT INTO symbols "
                        "(file_id, name, qualified_name, symbol_type, "
                        " line_start, line_end, visibility, parent_class) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            file_id,
                            definition.name,
                            definition.qualified_name,
                            definition.symbol_type,
                            definition.line_start,
                            definition.line_end,
                            definition.visibility,
                            definition.parent_class,
                        ),
                    )

                # Populate ``symbol_members`` for enums and constants. The
                # parser emits ``enum`` symbols directly (Decision D6), so
                # the matching parent row is already in place from the
                # definition-insert loop above — we just need the row id.
                result.member_count += _insert_enum_members(conn, file_id, extract)
                result.member_count += _insert_constant_values(conn, file_id, extract)

                extracts.append((src, extract))
                result.file_count += 1
                result.symbol_count += len(extract.definitions)

            # ---- Pass 2: call resolution ---------------------------------
            python_resolver = PythonResolver(conn, project_root, config)
            fallback_resolver = FallbackResolver(conn)

            for src, extract in extracts:
                rel_path = str(src.relative_to(project_root))
                file_id = file_id_map[rel_path]
                suffix = src.suffix.lower()
                is_python = suffix in _PY_EXTENSIONS
                resolver = python_resolver if is_python else fallback_resolver

                # Prime the Python resolver's import cache with the already
                # parsed tree so it never re-parses the file.
                if is_python and src in tree_cache:
                    tree, source_bytes = tree_cache[src]
                    python_resolver._imports_for(  # noqa: SLF001 — intentional priming
                        rel_path,
                        tree=tree,
                        source_bytes=source_bytes,
                    )

                for call in extract.calls:
                    caller_id = _lookup_symbol_id(conn, file_id, call.caller_name)
                    if caller_id is None:
                        # Caller definition was not captured (e.g. nested
                        # generator expression). Skip rather than emit an
                        # orphan unresolved row.
                        continue

                    callee_id = resolver.resolve(call, file_id, rel_path)
                    if callee_id is not None:
                        conn.execute(
                            "INSERT OR IGNORE INTO calls "
                            "(caller_id, callee_id, line, call_context) "
                            "VALUES (?, ?, ?, ?)",
                            (caller_id, callee_id, call.line, call.receiver),
                        )
                        result.call_count += 1
                    else:
                        conn.execute(
                            "INSERT OR IGNORE INTO unresolved_calls "
                            "(caller_id, callee_name, line, call_context) "
                            "VALUES (?, ?, ?, ?)",
                            (caller_id, call.callee_name, call.line, call.receiver),
                        )
                        result.unresolved_call_count += 1

            # ---- Pass 3: class edge resolution ---------------------------
            # Resolves :class:`ClassEdgeSite` entries emitted by the
            # parsers in pass 1 into concrete ``class_edges`` rows. Runs
            # after pass 2 so every class definition is already in the
            # ``symbols`` table before we try to resolve inheritance /
            # instantiation targets against it. Uses the same resolver
            # dispatch as pass 2: Python files use
            # :class:`PythonResolver`, everything else uses
            # :class:`FallbackResolver` (which returns ``None`` for every
            # class-name lookup until Phase 6 ships a real TS/JS class
            # resolver). Target-id sanity check for ``instantiates``
            # edges filters out PascalCase functions that would otherwise
            # look like classes to ``resolve_class_name``.
            for src, extract in extracts:
                rel_path = str(src.relative_to(project_root))
                file_id = file_id_map[rel_path]
                suffix = src.suffix.lower()
                is_python = suffix in _PY_EXTENSIONS
                resolver = python_resolver if is_python else fallback_resolver

                for edge in extract.class_edges:
                    source_id = _lookup_symbol_id(conn, file_id, edge.source_name)
                    if source_id is None:
                        continue
                    target_id = resolver.resolve_class_name(
                        edge.target_name,
                        caller_file_id=file_id,
                        caller_file_path=rel_path,
                    )
                    if target_id is None:
                        conn.execute(
                            "INSERT OR IGNORE INTO class_edges_unresolved "
                            "(source_id, target_name, edge_type, line) "
                            "VALUES (?, ?, ?, ?)",
                            (source_id, edge.target_name, edge.edge_type, edge.line),
                        )
                        result.class_edge_unresolved_count += 1
                        continue
                    if edge.edge_type == "instantiates":
                        target_row = conn.execute(
                            "SELECT symbol_type FROM symbols WHERE id = ?",
                            (target_id,),
                        ).fetchone()
                        if target_row is None or target_row[0] != "class":
                            continue
                    conn.execute(
                        "INSERT OR IGNORE INTO class_edges "
                        "(source_id, target_id, edge_type, line, context) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (source_id, target_id, edge.edge_type, edge.line, None),
                    )
                    result.class_edge_count += 1

            # ---- Pass 4: transitive enum promotion -----------------------
            # Runs after Phase 3's class edges are resolved so the
            # inherits graph is fully populated. A Python class like
            # ``class BuildStatus(MyLocalBase):`` will be emitted by the
            # parser with ``symbol_type='class'`` because ``MyLocalBase``
            # is not in :data:`_PY_ENUM_BASES`. This pass walks the
            # ``class_edges`` inherits graph outward from the known enum
            # roots (parser direct-match) and re-classifies every class
            # that transitively reaches one of them, then re-parses the
            # owning source file to capture their members.
            result.member_count += _propagate_transitive_enums(
                conn,
                extracts,
                file_id_map,
                project_root,
            )

            # ---- Meta rows ------------------------------------------------
            # Written inside the transaction so readers never see stale
            # counts after a successful rebuild.
            conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                ("symbol_count", str(result.symbol_count)),
            )
            conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                ("call_count", str(result.call_count)),
            )
            conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                ("built_at", datetime.now(UTC).isoformat()),
            )
    finally:
        conn.close()

    result.duration_ms = int((time.monotonic() - started) * 1000)
    return result


def refresh_file(
    project_root: Path,
    config: LexibraryConfig,
    file_path: Path,
) -> SymbolBuildResult:
    """Re-extract a single file and patch it into ``symbols.db``.

    Per-file incremental refresh used by ``lexi design update <file>`` to keep
    the symbol graph current between full rebuilds. Wraps the whole sequence
    in a single ``with conn:`` transaction so a failure mid-way rolls back
    cleanly.

    Steps (in order):

    1. Open the DB, set pragmas, resolve the file's existing row in
       ``files`` by ``path = ?`` — capture ``old_file_id``. If not found,
       we fall through to a fresh INSERT path.
    2. Delete old rows in FK-safe order:
       ``calls WHERE caller_id IN (SELECT id FROM symbols WHERE file_id
       = old_file_id)``,
       ``unresolved_calls WHERE caller_id IN (SELECT id FROM symbols
       WHERE file_id = old_file_id)``,
       ``symbols WHERE file_id = old_file_id``,
       ``files WHERE id = old_file_id``.
    3. Re-run :func:`extract_symbols` on the file. If it returns ``None``,
       commit the deletes and return — the file was just removed.
       Otherwise INSERT a fresh ``files`` row, then ``symbols`` rows.
    4. Re-run resolution for every call in the new extract using the same
       ``PythonResolver`` / ``FallbackResolver`` logic as pass 2 of the
       full build.
    5. **Promote previously-unresolved calls:** for each new symbol in the
       refreshed file, query ``unresolved_calls`` for rows whose
       ``callee_name`` matches the bare name (either exactly or via a
       ``"module.bare"`` dotted suffix). Re-run the Python resolver for
       each row, and on success DELETE the row from ``unresolved_calls``
       and INSERT it into ``calls``.
    6. Update ``files.last_hash`` to the SHA-256 of the on-disk file.

    Parameters
    ----------
    project_root:
        Project root containing a ``.lexibrary/`` directory with
        ``symbols.db``. Only resolved roots are used — macOS symlinked
        tempdirs (``/tmp`` → ``/private/tmp``) are handled here too.
    config:
        Loaded :class:`LexibraryConfig`. ``config.symbols.enabled`` gates
        the entire refresh — a disabled config short-circuits immediately.
    file_path:
        Absolute path to the source file being refreshed. The path is
        resolved and made project-relative before any SQL runs so it
        matches the ``files.path`` key written by :func:`build_symbol_graph`.

    Returns
    -------
    SymbolBuildResult
        ``build_type="incremental"`` on every call (the label mirrors
        :func:`build_symbol_graph` telemetry). Counters reflect only the
        rows inserted for this one file — callers who need global counts
        must query the DB directly.
    """
    started = time.monotonic()
    result = SymbolBuildResult(build_type="incremental")

    # Guard 1: disabled config — no DB mutation, no file creation.
    if not config.symbols.enabled:
        logger.debug("symbols.enabled=False — skipping refresh_file")
        return result

    # Guard 2: DB doesn't exist yet — refresh_file never bootstraps a new
    # DB. Agents must run the initial full build via the project maintainer.
    db_path = symbols_db_path(project_root)
    if not db_path.exists():
        logger.debug(
            "symbols.db does not exist at %s — skipping refresh_file",
            db_path,
        )
        return result

    # Resolve the project root so ``Path.relative_to`` cops with macOS
    # symlinked tempdirs. The discovered source paths in the builder are
    # already resolved; we resolve here too so the rel-path lookups hit the
    # existing ``files`` rows.
    project_root = project_root.resolve()
    file_path = file_path.resolve()

    # Compute project-relative path used as the ``files.path`` key.
    try:
        rel_path = str(file_path.relative_to(project_root))
    except ValueError:
        logger.debug(
            "refresh_file: %s is not under project_root %s — skipping",
            file_path,
            project_root,
        )
        return result

    conn = sqlite3.connect(db_path)
    try:
        set_pragmas(conn)

        # Guard 3: schema-version mismatch — the DB was built under an older
        # schema than the current binary. A full rebuild is required; the
        # per-file refresh path cannot migrate in place because the
        # extractor is already emitting columns the DB does not have.
        # Silently no-op so the caller (usually ``lexi design update``) does
        # not emit a noisy exception traceback — the project maintainer
        # will pick up the mismatch the next time they run a full build.
        existing_version = check_schema_version(conn)
        if existing_version != SCHEMA_VERSION:
            logger.debug(
                "refresh_file: symbols.db schema version is %s but "
                "current is %s — skipping (full rebuild required)",
                existing_version,
                SCHEMA_VERSION,
            )
            return result

        with conn:
            # Step 1 — resolve the existing row (may not exist for a
            # freshly-created file that wasn't in the last full build).
            row = conn.execute(
                "SELECT id FROM files WHERE path = ?",
                (rel_path,),
            ).fetchone()
            old_file_id = int(row[0]) if row is not None else None

            # Step 2 — delete old rows in FK-safe order. Children first so
            # FK cascade direction is respected and we never trip a
            # constraint mid-transaction.
            if old_file_id is not None:
                conn.execute(
                    "DELETE FROM calls WHERE caller_id IN ("
                    "    SELECT id FROM symbols WHERE file_id = ?"
                    ")",
                    (old_file_id,),
                )
                conn.execute(
                    "DELETE FROM unresolved_calls WHERE caller_id IN ("
                    "    SELECT id FROM symbols WHERE file_id = ?"
                    ")",
                    (old_file_id,),
                )
                conn.execute(
                    "DELETE FROM symbols WHERE file_id = ?",
                    (old_file_id,),
                )
                conn.execute(
                    "DELETE FROM files WHERE id = ?",
                    (old_file_id,),
                )

            # Step 3 — re-extract. If the file has been deleted on disk or
            # has no registered grammar, stop here after the deletes.
            if not file_path.exists():
                result.duration_ms = int((time.monotonic() - started) * 1000)
                return result

            parsed = _parse_source(file_path)
            if parsed is None:
                result.duration_ms = int((time.monotonic() - started) * 1000)
                return result
            tree, source_bytes = parsed

            extract = _extract_symbols_for(
                file_path,
                tree,
                source_bytes,
                project_root,
            )
            if extract is None:
                result.duration_ms = int((time.monotonic() - started) * 1000)
                return result

            # Insert the fresh ``files`` row. ``last_hash`` is set here and
            # (redundantly) updated in step 6 — the second write is part of
            # the contract but it's free because we're still inside the
            # same transaction.
            cursor = conn.execute(
                "INSERT INTO files (path, language, last_hash) VALUES (?, ?, ?)",
                (rel_path, extract.language, hash_file(file_path)),
            )
            new_file_id = cursor.lastrowid
            if new_file_id is None:  # pragma: no cover - sqlite always sets it
                result.duration_ms = int((time.monotonic() - started) * 1000)
                return result

            for definition in extract.definitions:
                conn.execute(
                    "INSERT INTO symbols "
                    "(file_id, name, qualified_name, symbol_type, "
                    " line_start, line_end, visibility, parent_class) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        new_file_id,
                        definition.name,
                        definition.qualified_name,
                        definition.symbol_type,
                        definition.line_start,
                        definition.line_end,
                        definition.visibility,
                        definition.parent_class,
                    ),
                )

            # Populate ``symbol_members`` for enums and constants in the
            # refreshed file. The old symbol rows were already deleted at
            # Step 2 above, and the CASCADE on ``symbol_members.symbol_id``
            # took their member rows with them, so we only need to insert
            # the new rows — no explicit DELETE required.
            result.member_count += _insert_enum_members(conn, new_file_id, extract)
            result.member_count += _insert_constant_values(conn, new_file_id, extract)

            result.file_count += 1
            result.symbol_count += len(extract.definitions)

            # Step 4 — resolve calls in the new extract using the same
            # two-resolver dispatch as pass 2 of :func:`build_symbol_graph`.
            python_resolver = PythonResolver(conn, project_root, config)
            fallback_resolver = FallbackResolver(conn)

            suffix = file_path.suffix.lower()
            is_python = suffix in _PY_EXTENSIONS
            resolver = python_resolver if is_python else fallback_resolver

            # Prime the Python resolver's import cache with the already
            # parsed tree so it never re-parses the file.
            if is_python:
                python_resolver._imports_for(  # noqa: SLF001 — intentional priming
                    rel_path,
                    tree=tree,
                    source_bytes=source_bytes,
                )

            for call in extract.calls:
                caller_id = _lookup_symbol_id(conn, new_file_id, call.caller_name)
                if caller_id is None:
                    continue

                callee_id = resolver.resolve(call, new_file_id, rel_path)
                if callee_id is not None:
                    conn.execute(
                        "INSERT OR IGNORE INTO calls "
                        "(caller_id, callee_id, line, call_context) "
                        "VALUES (?, ?, ?, ?)",
                        (caller_id, callee_id, call.line, call.receiver),
                    )
                    result.call_count += 1
                else:
                    conn.execute(
                        "INSERT OR IGNORE INTO unresolved_calls "
                        "(caller_id, callee_name, line, call_context) "
                        "VALUES (?, ?, ?, ?)",
                        (caller_id, call.callee_name, call.line, call.receiver),
                    )
                    result.unresolved_call_count += 1

            # Step 5 — promote previously-unresolved calls. For each new
            # symbol in the refreshed file, look up any unresolved row whose
            # ``callee_name`` matches by bare name (direct match or
            # ``module.bare`` dotted suffix) and re-run the Python resolver.
            # On a definite hit, DELETE from ``unresolved_calls`` and INSERT
            # into ``calls``. We resolve inside the same transaction so the
            # promotion is all-or-nothing.
            for definition in extract.definitions:
                if definition.symbol_type not in ("function", "method", "class"):
                    continue
                bare = definition.name
                # Match either an exact bare name (``foo``) or a dotted
                # suffix (``module.foo``, ``pkg.mod.foo``). The suffix
                # match lets us promote cases like
                # ``from pkg.b import bar`` where the extractor recorded
                # the callee_name as ``bar`` but a caller might have
                # written it as ``pkg.b.bar``. We use LIKE with a
                # leading wildcard because we cannot predict how deep the
                # dotted path is at extraction time.
                unresolved_rows = conn.execute(
                    "SELECT u.id, u.caller_id, u.callee_name, u.line, "
                    "       u.call_context, f.path AS caller_path "
                    "FROM unresolved_calls u "
                    "JOIN symbols caller ON u.caller_id = caller.id "
                    "JOIN files f ON caller.file_id = f.id "
                    "WHERE u.callee_name = ? OR u.callee_name LIKE ?",
                    (bare, f"%.{bare}"),
                ).fetchall()

                for unresolved_row in unresolved_rows:
                    (
                        unresolved_id,
                        caller_id,
                        callee_name,
                        line,
                        call_context,
                        caller_path,
                    ) = unresolved_row
                    # Reconstruct a lightweight CallSite for the resolver.
                    # ``caller_name`` is recorded on the unresolved row
                    # only indirectly via its FK — re-query the caller
                    # symbol row to pick up its qualified_name.
                    caller_info = conn.execute(
                        "SELECT qualified_name FROM symbols WHERE id = ?",
                        (caller_id,),
                    ).fetchone()
                    if caller_info is None:
                        continue
                    # Deferred import to avoid the ast_parser → symbolgraph
                    # circular chain that the rest of this module works
                    # around with function-local imports.
                    from lexibrary.ast_parser.models import CallSite

                    synthetic_call = CallSite(
                        caller_name=str(caller_info[0]),
                        callee_name=str(callee_name),
                        receiver=str(call_context) if call_context else None,
                        line=int(line),
                    )

                    callee_id = python_resolver.resolve(
                        synthetic_call,
                        int(caller_id),
                        str(caller_path),
                    )
                    if callee_id is None:
                        continue

                    conn.execute(
                        "DELETE FROM unresolved_calls WHERE id = ?",
                        (int(unresolved_id),),
                    )
                    conn.execute(
                        "INSERT OR IGNORE INTO calls "
                        "(caller_id, callee_id, line, call_context) "
                        "VALUES (?, ?, ?, ?)",
                        (
                            int(caller_id),
                            callee_id,
                            int(line),
                            str(call_context) if call_context else None,
                        ),
                    )
                    result.call_count += 1
                    result.unresolved_call_count = max(0, result.unresolved_call_count - 1)

            # Step 6 — update ``files.last_hash`` to the current on-disk
            # hash. This is redundant with the INSERT above but is part of
            # the documented contract and lets callers trust the row they
            # just wrote.
            conn.execute(
                "UPDATE files SET last_hash = ? WHERE id = ?",
                (hash_file(file_path), new_file_id),
            )
    finally:
        conn.close()

    result.duration_ms = int((time.monotonic() - started) * 1000)
    return result


def _parse_source(path: Path) -> tuple[Tree, bytes] | None:
    """Dispatch ``path`` to the matching parse-tree helper.

    Returns ``None`` when the extension has no registered parser (the file
    should be skipped by the caller) or when the parser itself declines the
    file (missing grammar / unreadable bytes). Imports are deferred to
    call time to match the deferred-import pattern in
    :func:`build_symbol_graph` that breaks the ``symbolgraph`` ↔
    ``ast_parser`` circular dependency.
    """
    suffix = path.suffix.lower()
    if suffix in _PY_EXTENSIONS:
        from lexibrary.ast_parser.python_parser import parse_python_tree

        return parse_python_tree(path)
    if suffix in _TS_EXTENSIONS:
        from lexibrary.ast_parser.typescript_parser import parse_ts_tree

        return parse_ts_tree(path)
    if suffix in _JS_EXTENSIONS:
        from lexibrary.ast_parser.javascript_parser import parse_js_tree

        return parse_js_tree(path)
    return None


def _extract_symbols_for(
    path: Path,
    tree: Tree,
    source_bytes: bytes,
    project_root: Path,
) -> SymbolExtract | None:
    """Dispatch ``path`` to the matching ``extract_symbols_from_tree``.

    Only the Python extractor honours ``project_root`` (for dotted-module
    qualified names). TypeScript and JavaScript extractors take the file
    stem as the module prefix and ignore the argument. Imports are
    deferred to call time to match the pattern in
    :func:`build_symbol_graph`.
    """
    suffix = path.suffix.lower()
    if suffix in _PY_EXTENSIONS:
        from lexibrary.ast_parser.python_parser import (
            extract_symbols_from_tree as py_extract_symbols_from_tree,
        )

        return py_extract_symbols_from_tree(
            tree,
            source_bytes,
            path,
            project_root=project_root,
        )
    if suffix in _TS_EXTENSIONS:
        from lexibrary.ast_parser.typescript_parser import (
            extract_symbols_from_tree as ts_extract_symbols_from_tree,
        )

        return ts_extract_symbols_from_tree(tree, source_bytes, path)
    if suffix in _JS_EXTENSIONS:
        from lexibrary.ast_parser.javascript_parser import (
            extract_symbols_from_tree as js_extract_symbols_from_tree,
        )

        return js_extract_symbols_from_tree(tree, source_bytes, path)
    return None


def _lookup_symbol_id(
    conn: sqlite3.Connection,
    file_id: int,
    qualified_name: str,
) -> int | None:
    """Return the ``symbols.id`` matching ``(file_id, qualified_name)``.

    Used by the builder's pass-2 loop to convert a ``CallSite.caller_name``
    (the fully-qualified caller name emitted by the Python extractor) into
    the row id needed by the ``calls`` / ``unresolved_calls`` foreign keys.
    Returns ``None`` when no row matches — the caller handles that case by
    skipping the call entirely (a nested generator expression inside a
    comprehension, for example, never materialises a ``symbols`` row).
    """
    row = conn.execute(
        "SELECT id FROM symbols WHERE file_id = ? AND qualified_name = ?",
        (file_id, qualified_name),
    ).fetchone()
    if row is None:
        return None
    return int(row[0])


def _insert_enum_members(
    conn: sqlite3.Connection,
    file_id: int,
    extract: SymbolExtract,
) -> int:
    """Insert ``symbol_members`` rows for every enum in ``extract``.

    Each ``(qualified_name, members)`` tuple in ``extract.enums`` points at
    a symbol already emitted by the parser with ``symbol_type='enum'`` —
    the parent row is looked up via :func:`_lookup_symbol_id`. Missing
    parent rows are skipped silently; the parser is responsible for
    keeping ``extract.enums`` in sync with the emitted definitions.

    Returns the number of member rows inserted so the caller can update
    ``SymbolBuildResult.member_count``.
    """
    inserted = 0
    for qualified_name, members in extract.enums:
        enum_symbol_id = _lookup_symbol_id(conn, file_id, qualified_name)
        if enum_symbol_id is None:
            continue
        for member in members:
            conn.execute(
                "INSERT OR IGNORE INTO symbol_members "
                "(symbol_id, name, value, ordinal) VALUES (?, ?, ?, ?)",
                (enum_symbol_id, member.name, member.value, member.ordinal),
            )
            inserted += 1
    return inserted


def _insert_constant_values(
    conn: sqlite3.Connection,
    file_id: int,
    extract: SymbolExtract,
) -> int:
    """Insert a ``symbol_members`` row for every constant in ``extract``.

    Each :class:`ConstantValue` corresponds to a ``SymbolDefinition`` with
    ``symbol_type='constant'``, ``parent_class=None`` and matching
    ``name``. The ``qualified_name`` on that definition is the parent-row
    lookup key — we find it in ``extract.definitions`` rather than
    re-deriving the module path here, which keeps the two emission paths
    (Python's dotted packages and TS/JS's file-stem prefix) uniform.

    Constants whose ``value`` is ``None`` are skipped per Decision D3 in
    ``openspec/changes/symbol-graph-4/design.md`` — a member row without a
    literal would be uninformative for value search.

    Returns the number of member rows inserted so the caller can update
    ``SymbolBuildResult.member_count``.
    """
    if not extract.constants:
        return 0

    # Build a name → qualified_name map so we can resolve each
    # ``ConstantValue`` back to the definition emitted alongside it
    # without scanning all definitions inside the per-constant loop.
    constant_qnames: dict[str, str] = {}
    for definition in extract.definitions:
        if definition.symbol_type == "constant" and definition.parent_class is None:
            constant_qnames[definition.name] = definition.qualified_name

    inserted = 0
    for const in extract.constants:
        if const.value is None:
            continue
        qualified_name = constant_qnames.get(const.name)
        if qualified_name is None:
            continue
        const_symbol_id = _lookup_symbol_id(conn, file_id, qualified_name)
        if const_symbol_id is None:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO symbol_members "
            "(symbol_id, name, value, ordinal) VALUES (?, ?, ?, 0)",
            (const_symbol_id, const.name, const.value),
        )
        inserted += 1
    return inserted


def _propagate_transitive_enums(
    conn: sqlite3.Connection,
    extracts: list[tuple[Path, SymbolExtract]],
    file_id_map: dict[str, int],
    project_root: Path,
) -> int:
    """Reclassify classes that transitively inherit from a known enum base.

    Runs as a second pass after Phase 3's ``class_edges`` are resolved so
    every inherits edge is available (either resolved or unresolved).
    Starting from every symbol already marked ``symbol_type='enum'`` in
    the ``symbols`` table (the parser's direct-base matches), this walks
    the inheritance DAG outward to find every class that reaches an enum
    root via any chain of ``inherits`` edges.

    For each newly-discovered enum, the walker:

    1. ``UPDATE``s the ``symbols`` row to set ``symbol_type='enum'``.
    2. Re-opens the owning source file, runs the Python parser's enum
       body walker on the original AST subtree, and inserts the
       resulting :class:`EnumMemberSig` rows into ``symbol_members``.

    Only Python classes are reclassified — the walker skips rows whose
    owning file is not a ``.py``/``.pyi`` file because TypeScript enums
    are already caught at parse time (``enum_declaration`` is a distinct
    node type) and JavaScript has no enum concept at all. Returns the
    number of member rows inserted so the caller can update
    ``SymbolBuildResult.member_count``.

    Unresolved-edge quirk: Phase 3's :meth:`PythonResolver.resolve_class_name`
    filters candidate rows by ``symbol_type='class'``, so an inherits
    edge whose target has already been emitted as ``symbol_type='enum'``
    by the parser (for example ``class MyBase(StrEnum)``) ends up in
    ``class_edges_unresolved`` instead of ``class_edges``. This pass
    therefore reads both tables and promotes unresolved rows whose
    ``target_name`` matches a local enum row in the same source file.
    """
    # Build a directed graph: parent_id -> set of child_ids.
    # We want "which classes inherit from this enum?", so the edge
    # direction is from the *target* (parent / base class) to the
    # *source* (derived class). Phase 3's class_edges table already
    # stores the resolved ids — no re-resolution needed for those rows.
    inherits_rows = conn.execute(
        "SELECT source_id, target_id FROM class_edges WHERE edge_type = 'inherits'",
    ).fetchall()
    children_by_parent: dict[int, list[int]] = {}
    for source_id, target_id in inherits_rows:
        children_by_parent.setdefault(int(target_id), []).append(int(source_id))

    # Promote same-file ``class_edges_unresolved`` rows whose target
    # name matches a local enum symbol. This is the path a
    # ``class BuildStatus(MyBase)`` edge travels when ``MyBase`` is
    # parser-direct-matched as an enum — the Phase 3 class-name
    # resolver skips enum rows, so the edge lands in the unresolved
    # table. Cross-file enum bases are left unresolved here (the same
    # limitation as Phase 3 cross-file class resolution).
    unresolved_rows = conn.execute(
        "SELECT ceu.source_id, ceu.target_name, source_sym.file_id "
        "FROM class_edges_unresolved ceu "
        "JOIN symbols source_sym ON source_sym.id = ceu.source_id "
        "WHERE ceu.edge_type = 'inherits'",
    ).fetchall()
    for source_id, target_name, source_file_id in unresolved_rows:
        target_row = conn.execute(
            "SELECT id FROM symbols WHERE file_id = ? AND name = ? AND symbol_type = 'enum'",
            (int(source_file_id), str(target_name)),
        ).fetchone()
        if target_row is None:
            continue
        target_id = int(target_row[0])
        children_by_parent.setdefault(target_id, []).append(int(source_id))

    if not children_by_parent:
        return 0

    # Seed the frontier with every row already marked as an enum. These
    # are the parser-direct matches (``class Foo(StrEnum)``). The graph
    # walk expands outward to the transitive cases
    # (``class Foo(LocalBase)`` where ``LocalBase(StrEnum)``).
    enum_root_rows = conn.execute(
        "SELECT id FROM symbols WHERE symbol_type = 'enum'",
    ).fetchall()
    enum_ids: set[int] = {int(row[0]) for row in enum_root_rows}

    # Breadth-first walk. Only newly-discovered ids need to be processed
    # (updated to enum + members extracted). The seed roots already have
    # their members from the parser.
    newly_enum: list[int] = []
    frontier: list[int] = list(enum_ids)
    while frontier:
        next_frontier: list[int] = []
        for parent_id in frontier:
            for child_id in children_by_parent.get(parent_id, ()):
                if child_id in enum_ids:
                    continue
                enum_ids.add(child_id)
                newly_enum.append(child_id)
                next_frontier.append(child_id)
        frontier = next_frontier

    if not newly_enum:
        return 0

    # Map each newly-promoted symbol back to its owning source file so we
    # can re-parse the file and extract enum members from the class body.
    # ``extracts`` already holds every parsed tree we saw in pass 1, so we
    # can reuse the in-memory extract objects rather than re-parsing the
    # file from disk. Match by ``(file_id, qualified_name)``.
    qname_by_id: dict[int, tuple[int, str]] = {}
    for symbol_id in newly_enum:
        row = conn.execute(
            "SELECT file_id, qualified_name FROM symbols WHERE id = ?",
            (symbol_id,),
        ).fetchone()
        if row is None:
            continue
        qname_by_id[symbol_id] = (int(row[0]), str(row[1]))

    # Build a reverse lookup ``file_id -> (path, extract)`` so we can
    # quickly find the right extract for each promoted symbol.
    extract_by_file_id: dict[int, tuple[Path, SymbolExtract]] = {}
    for src_path, extract in extracts:
        rel_path = str(src_path.relative_to(project_root))
        file_id = file_id_map.get(rel_path)
        if file_id is not None:
            extract_by_file_id[file_id] = (src_path, extract)

    inserted = 0
    for symbol_id in newly_enum:
        lookup = qname_by_id.get(symbol_id)
        if lookup is None:
            continue
        file_id, qualified_name = lookup

        src_lookup = extract_by_file_id.get(file_id)
        if src_lookup is None:
            continue
        src_path, _ = src_lookup

        # Only Python files get transitive promotion — TS enums are
        # parsed directly and JS has no enum concept.
        if src_path.suffix.lower() not in _PY_EXTENSIONS:
            continue

        # Flip the row's symbol_type so downstream queries treat it as
        # an enum. The UNIQUE constraint on ``symbols`` includes
        # ``symbol_type`` so this UPDATE cannot collide with a sibling
        # class row of the same name unless the source file actually
        # defines both — which is impossible in Python syntax.
        conn.execute(
            "UPDATE symbols SET symbol_type = 'enum' WHERE id = ?",
            (symbol_id,),
        )

        # Re-parse the file and locate the class_definition node whose
        # textual name matches this promoted symbol, then walk its body
        # with the parser's enum-member collector. This is cheaper than
        # caching every parsed tree from pass 1 and keeps the walker's
        # state isolated from the main definitions pass.
        members = _extract_enum_members_for_qualified_name(src_path, qualified_name)
        for member in members:
            conn.execute(
                "INSERT OR IGNORE INTO symbol_members "
                "(symbol_id, name, value, ordinal) VALUES (?, ?, ?, ?)",
                (symbol_id, member.name, member.value, member.ordinal),
            )
            inserted += 1

    return inserted


def _extract_enum_members_for_qualified_name(
    file_path: Path,
    qualified_name: str,
) -> list[EnumMemberSig]:
    """Re-parse ``file_path`` and return the member list for a promoted enum.

    Used only by :func:`_propagate_transitive_enums` to pick up members
    for classes that were not detected as enums at parse time. The
    transitive walker already knows the symbol's ``qualified_name``
    (``pkg.module.BuildStatus``); we match on the trailing component
    against the class name in the AST so nested classes of the same
    name in other modules cannot collide.

    Returns an empty list when the file cannot be parsed, when the
    matching class_definition cannot be located, or when the body is
    missing — the caller treats an empty list as "nothing to insert".
    """
    # Deferred import for the same reason as the other builder imports:
    # ``ast_parser.python_parser`` transitively imports from this module
    # at package-init time.
    from lexibrary.ast_parser.python_parser import (
        _child_by_field,
        _children,
        _collect_enum_members,
        _node_text,
        parse_python_tree,
    )

    parsed = parse_python_tree(file_path)
    if parsed is None:
        return []
    tree, _source_bytes = parsed
    root = tree.root_node
    if root is None:
        return []

    # Only the trailing identifier (after the last dot) needs to match —
    # the enclosing module path is already guaranteed to match because
    # we resolved the symbol row back to its owning file_id.
    class_name = qualified_name.rsplit(".", 1)[-1]

    for child in _children(root):
        child_type = getattr(child, "type", "")
        if child_type == "decorated_definition":
            inner = _child_by_field(child, "definition")
            if inner is None:
                continue
            child = inner
            child_type = getattr(child, "type", "")
        if child_type != "class_definition":
            continue
        name_node = _child_by_field(child, "name")
        if name_node is None:
            continue
        if _node_text(name_node) != class_name:
            continue
        body_node = _child_by_field(child, "body")
        if body_node is None:
            return []
        return _collect_enum_members(body_node)
    return []
