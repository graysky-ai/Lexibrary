"""DDL constants and schema management for the symbol graph index.

The symbol graph is a **sibling** SQLite database to the link graph's
``index.db``, stored at ``.lexibrary/symbols.db``. It records *symbol-level*
edges (function calls, class hierarchy, enum members, module-level constants)
below the file/artifact granularity captured by the link graph. See
``CN-021 Symbol Graph`` and ``docs/symbol-graph.md`` for the concept.

Why a separate DB
-----------------

- **Cadence independence.** The symbol graph rebuilds on every source change
  (parse of every .py file) whereas the link graph rebuilds on artifact change.
  Cohabiting would force both to rebuild together on the slower cadence.
- **Independent lifecycle.** Each DB can be deleted and rebuilt without
  touching the other. Gitignore and ``.lexibrary/`` hygiene stay per-file.
- **Independent schema versions.** Phase 5's design-file enrichment will not
  disturb link-graph state.

Forward-compatibility strategy
------------------------------

Phase 1 shipped the symbol-graph DDL at ``SCHEMA_VERSION = 1`` including
tables and CHECK-constraint values that later phases would start populating
(``unresolved_calls``, ``class_edges_unresolved`` with ``'composes'`` in its
``edge_type`` set, the full
``('function','method','class','enum','constant')`` tuple in
``symbols.symbol_type``). Phase 2 sub-phase 2.0 bumps the version to
``SCHEMA_VERSION = 2`` to add the ``parent_class`` column on ``symbols`` and
widen the UNIQUE constraint to
``(file_id, name, symbol_type, parent_class)``. This retroactive correction
keeps Phase 2–6 free of further schema churn — extractor code and query
bodies can assume the final shape. A later phase that adds a *column* to an
existing table must still bump ``SCHEMA_VERSION`` and rely on
:func:`ensure_schema`'s force-rebuild path.

Version-mismatch behaviour
--------------------------

On mismatch, :func:`ensure_schema` drops all tables and recreates them from
the canonical DDL — the same force-rebuild-on-mismatch strategy as the link
graph. SQLite rebuilds are fast and the file is gitignored, so this is
cheaper than ``ALTER TABLE`` migrations and avoids schema drift between dev
and prod.
"""

# Phase 2 note: The force-rebuild path will expose in-flight readers
# (daemons, long-running services) to SQLITE_BUSY and transient empty state.
# Phase 1 enables WAL mode to give Phase 2 room to adopt a "build into a
# temp file + atomic rename" strategy. The concrete decision
# (temp-file-rename vs. documented transient state) is deferred to Phase 2's
# extractor design and tracked in the symbol-graph-1 change's open questions.

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

SCHEMA_VERSION = 2
"""Schema version. Mismatch on open triggers a full rebuild.

Phase 2 value: 2 (bumped from Phase 1 value: 1). Sub-phase 2.0 added the
``parent_class`` column on ``symbols`` and changed the UNIQUE constraint to
``(file_id, name, symbol_type, parent_class)`` to fix same-named-method
collisions across classes in the same file. Phase 1 databases force-rebuild
on first Phase 2 open via :func:`ensure_schema`'s version-mismatch path.
"""


# ---------------------------------------------------------------------------
# Pragmas — set on every connection open
# ---------------------------------------------------------------------------

_PRAGMAS = """\
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA synchronous = NORMAL;
"""


# ---------------------------------------------------------------------------
# DDL — table creation
# ---------------------------------------------------------------------------

_CREATE_META = """\
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY NOT NULL,
    value TEXT NOT NULL
);
"""

_CREATE_FILES = """\
CREATE TABLE IF NOT EXISTS files (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    path      TEXT    NOT NULL UNIQUE,
    language  TEXT,
    last_hash TEXT
);
"""

_CREATE_SYMBOLS = """\
CREATE TABLE IF NOT EXISTS symbols (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id        INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    name           TEXT    NOT NULL,
    qualified_name TEXT,
    symbol_type    TEXT    NOT NULL CHECK (symbol_type IN (
                       'function', 'method', 'class', 'enum', 'constant'
                   )),
    line_start     INTEGER,
    line_end       INTEGER,
    visibility     TEXT    CHECK (visibility IN ('public', 'private')),
    parent_class   TEXT,
    UNIQUE(file_id, name, symbol_type, parent_class)
);
"""

_CREATE_SYMBOL_MEMBERS = """\
CREATE TABLE IF NOT EXISTS symbol_members (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol_id  INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    name       TEXT    NOT NULL,
    value      TEXT,
    ordinal    INTEGER,
    UNIQUE(symbol_id, name)
);
"""

_CREATE_CALLS = """\
CREATE TABLE IF NOT EXISTS calls (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    caller_id    INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    callee_id    INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    line         INTEGER NOT NULL,
    call_context TEXT,
    UNIQUE(caller_id, callee_id, line)
);
"""

_CREATE_UNRESOLVED_CALLS = """\
CREATE TABLE IF NOT EXISTS unresolved_calls (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    caller_id    INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    callee_name  TEXT    NOT NULL,
    line         INTEGER NOT NULL,
    call_context TEXT,
    UNIQUE(caller_id, callee_name, line)
);
"""

_CREATE_CLASS_EDGES = """\
CREATE TABLE IF NOT EXISTS class_edges (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    target_id INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    edge_type TEXT    NOT NULL CHECK (edge_type IN (
                  'inherits', 'instantiates', 'composes'
              )),
    line      INTEGER,
    context   TEXT,
    UNIQUE(source_id, target_id, edge_type, line)
);
"""

_CREATE_CLASS_EDGES_UNRESOLVED = """\
CREATE TABLE IF NOT EXISTS class_edges_unresolved (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id   INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    target_name TEXT    NOT NULL,
    edge_type   TEXT    NOT NULL CHECK (edge_type IN (
                    'inherits', 'instantiates', 'composes'
                )),
    line        INTEGER,
    UNIQUE(source_id, target_name, edge_type, line)
);
"""


# ---------------------------------------------------------------------------
# Indexes
# ---------------------------------------------------------------------------

_INDEXES: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_files_path        ON files(path);",
    "CREATE INDEX IF NOT EXISTS idx_symbols_file      ON symbols(file_id);",
    "CREATE INDEX IF NOT EXISTS idx_symbols_name      ON symbols(name);",
    "CREATE INDEX IF NOT EXISTS idx_symbols_type      ON symbols(symbol_type);",
    "CREATE INDEX IF NOT EXISTS idx_symbols_qname     ON symbols(qualified_name);",
    "CREATE INDEX IF NOT EXISTS idx_members_symbol    ON symbol_members(symbol_id);",
    "CREATE INDEX IF NOT EXISTS idx_calls_caller      ON calls(caller_id);",
    "CREATE INDEX IF NOT EXISTS idx_calls_callee      ON calls(callee_id);",
    "CREATE INDEX IF NOT EXISTS idx_unresolved_caller ON unresolved_calls(caller_id);",
    "CREATE INDEX IF NOT EXISTS idx_unresolved_name   ON unresolved_calls(callee_name);",
    "CREATE INDEX IF NOT EXISTS idx_class_source      ON class_edges(source_id);",
    "CREATE INDEX IF NOT EXISTS idx_class_target      ON class_edges(target_id);",
    "CREATE INDEX IF NOT EXISTS idx_class_type        ON class_edges(edge_type);",
    (
        "CREATE INDEX IF NOT EXISTS idx_class_unresolved_source"
        " ON class_edges_unresolved(source_id);"
    ),
    (
        "CREATE INDEX IF NOT EXISTS idx_class_unresolved_name"
        " ON class_edges_unresolved(target_name);"
    ),
]


# ---------------------------------------------------------------------------
# All DDL statements in execution order
# ---------------------------------------------------------------------------

_ALL_DDL: list[str] = [
    _CREATE_META,
    _CREATE_FILES,
    _CREATE_SYMBOLS,
    _CREATE_SYMBOL_MEMBERS,
    _CREATE_CALLS,
    _CREATE_UNRESOLVED_CALLS,
    _CREATE_CLASS_EDGES,
    _CREATE_CLASS_EDGES_UNRESOLVED,
    *_INDEXES,
]

# Tables to drop on schema reset (order matters for foreign keys).
# Child tables first so FK cascade direction is respected during a force
# rebuild; ``files`` is second-to-last because symbols reference it, and
# ``meta`` is last of all since it has no FK dependents.
_DROP_ORDER: list[str] = [
    "class_edges_unresolved",
    "class_edges",
    "unresolved_calls",
    "calls",
    "symbol_members",
    "symbols",
    "files",
    "meta",
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def set_pragmas(conn: sqlite3.Connection) -> None:
    """Set WAL mode, foreign keys, and synchronous pragmas on a connection."""
    for line in _PRAGMAS.strip().splitlines():
        line = line.strip()
        if line:
            conn.execute(line)


def check_schema_version(conn: sqlite3.Connection) -> int | None:
    """Return the stored schema version, or ``None`` if missing/unreadable.

    Returns ``None`` when the meta table does not exist, has no
    ``schema_version`` row, or the value is not a valid integer.
    Callers should treat ``None`` or a version mismatch as a signal
    to rebuild the index via :func:`ensure_schema` with ``force=True``.
    """
    try:
        row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    except sqlite3.OperationalError:
        # meta table does not exist
        return None
    if row is None:
        return None
    try:
        return int(row[0])
    except (ValueError, TypeError):
        return None


def ensure_schema(conn: sqlite3.Connection, *, force: bool = False) -> bool:
    """Create or recreate the symbol graph schema.

    Parameters
    ----------
    conn:
        An open SQLite connection. Pragmas are set on this connection.
    force:
        If ``True``, drop all existing tables and recreate from scratch.
        If ``False`` (default), only recreate when the schema version is
        missing or does not match :data:`SCHEMA_VERSION`.

    Returns
    -------
    bool
        ``True`` if the schema was (re)created, ``False`` if it was
        already up to date.
    """
    set_pragmas(conn)

    existing_version = check_schema_version(conn)
    if not force and existing_version == SCHEMA_VERSION:
        return False

    # Drop everything and recreate
    _drop_all(conn)
    _create_all(conn)

    # Seed schema version and build metadata
    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
        ("schema_version", str(SCHEMA_VERSION)),
    )
    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
        ("built_at", datetime.now(UTC).isoformat()),
    )
    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
        ("builder", "lexibrary-symbolgraph-v1"),
    )
    conn.commit()
    return True


def _drop_all(conn: sqlite3.Connection) -> None:
    """Drop all symbol graph tables. Order respects foreign key dependencies."""
    for table in _DROP_ORDER:
        conn.execute(f"DROP TABLE IF EXISTS {table}")


def _create_all(conn: sqlite3.Connection) -> None:
    """Execute all DDL statements to create the schema."""
    for ddl in _ALL_DDL:
        conn.executescript(ddl)
