"""DDL constants and schema management for the link graph index.

The link graph uses 8 tables plus an FTS5 virtual table:

1. ``meta``        — key-value store for schema version, build metadata, counts
2. ``artifacts``   — every indexed entity (source, design, concept, stack, convention)
3. ``links``       — directed edges between artifacts with type and optional context
4. ``tags``        — artifact-to-tag associations (shared namespace per D-037)
5. ``aliases``     — concept alias resolution (case-insensitive, unique)
6. ``conventions`` — local conventions scoped to directories
7. ``build_log``   — per-artifact build tracking with timing and errors
8. ``artifacts_fts`` — FTS5 full-text search (trigger-synced)
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

SCHEMA_VERSION = 4
"""Schema version. Mismatch on open triggers a full rebuild."""


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

_CREATE_ARTIFACTS = """\
CREATE TABLE IF NOT EXISTS artifacts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    path          TEXT    NOT NULL UNIQUE,
    kind          TEXT    NOT NULL CHECK (kind IN (
                      'source', 'design', 'concept', 'stack', 'convention',
                      'playbook'
                  )),
    title         TEXT,
    status        TEXT    CHECK (status IS NULL OR status IN (
                      'active', 'deprecated', 'draft',
                      'open', 'resolved', 'outdated', 'duplicate'
                  )),
    last_hash     TEXT,
    created_at    TEXT,
    artifact_code TEXT    UNIQUE
);
"""

_CREATE_LINKS = """\
CREATE TABLE IF NOT EXISTS links (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id    INTEGER NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
    target_id    INTEGER NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
    link_type    TEXT    NOT NULL CHECK (link_type IN (
                     'ast_import',
                     'wikilink',
                     'stack_file_ref',
                     'stack_concept_ref',
                     'design_stack_ref',
                     'design_source',
                     'concept_file_ref',
                     'convention_concept_ref'
                 )),
    link_context TEXT,
    UNIQUE(source_id, target_id, link_type)
);
"""

_CREATE_TAGS = """\
CREATE TABLE IF NOT EXISTS tags (
    artifact_id INTEGER NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
    tag         TEXT    NOT NULL,
    UNIQUE(artifact_id, tag)
);
"""

_CREATE_ALIASES = """\
CREATE TABLE IF NOT EXISTS aliases (
    artifact_id INTEGER NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
    alias       TEXT    NOT NULL COLLATE NOCASE,
    UNIQUE(alias)
);
"""

_CREATE_CONVENTIONS = """\
CREATE TABLE IF NOT EXISTS conventions (
    artifact_id    INTEGER NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
    directory_path TEXT    NOT NULL,
    ordinal        INTEGER NOT NULL DEFAULT 0,
    body           TEXT    NOT NULL,
    source         TEXT    NOT NULL DEFAULT 'user',
    status         TEXT    NOT NULL DEFAULT 'active',
    priority       INTEGER NOT NULL DEFAULT 0,
    UNIQUE(directory_path, ordinal)
);
"""

_CREATE_BUILD_LOG = """\
CREATE TABLE IF NOT EXISTS build_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    build_started TEXT    NOT NULL,
    build_type    TEXT    NOT NULL CHECK (build_type IN ('full', 'incremental')),
    artifact_path TEXT    NOT NULL,
    artifact_kind TEXT    NOT NULL,
    action        TEXT    NOT NULL CHECK (action IN (
                      'created', 'updated', 'deleted', 'unchanged', 'failed'
                  )),
    duration_ms   INTEGER,
    error_message TEXT
);
"""

# FTS5 virtual table — standalone (no content table reference).
# The builder manages all inserts, updates, and deletes directly:
#   INSERT: INSERT INTO artifacts_fts (rowid, title, body) VALUES (?, ?, ?)
#   DELETE: DELETE FROM artifacts_fts WHERE rowid = ?
#   UPDATE: DELETE then INSERT (no in-place update for FTS5)
# Body content comes from reading actual files (not stored on ``artifacts``),
# so trigger-syncing from artifacts is not possible.
# Uses porter stemming + unicode61 tokenizer for broad search recall.
_CREATE_FTS = """\
CREATE VIRTUAL TABLE IF NOT EXISTS artifacts_fts USING fts5(
    title,
    body,
    tokenize='porter unicode61'
);
"""


# ---------------------------------------------------------------------------
# Indexes
# ---------------------------------------------------------------------------

_INDEXES = [
    # artifacts
    "CREATE INDEX IF NOT EXISTS idx_artifacts_path   ON artifacts(path);",
    "CREATE INDEX IF NOT EXISTS idx_artifacts_kind   ON artifacts(kind);",
    (
        "CREATE INDEX IF NOT EXISTS idx_artifacts_status"
        " ON artifacts(status) WHERE status IS NOT NULL;"
    ),
    (
        "CREATE INDEX IF NOT EXISTS idx_artifacts_code"
        " ON artifacts(artifact_code) WHERE artifact_code IS NOT NULL;"
    ),
    # links
    "CREATE INDEX IF NOT EXISTS idx_links_source      ON links(source_id);",
    "CREATE INDEX IF NOT EXISTS idx_links_target      ON links(target_id);",
    "CREATE INDEX IF NOT EXISTS idx_links_type        ON links(link_type);",
    "CREATE INDEX IF NOT EXISTS idx_links_target_type ON links(target_id, link_type);",
    # tags
    "CREATE INDEX IF NOT EXISTS idx_tags_tag      ON tags(tag);",
    "CREATE INDEX IF NOT EXISTS idx_tags_artifact ON tags(artifact_id);",
    # aliases
    "CREATE INDEX IF NOT EXISTS idx_aliases_artifact ON aliases(artifact_id);",
    # conventions
    "CREATE INDEX IF NOT EXISTS idx_conventions_dir ON conventions(directory_path);",
    "CREATE INDEX IF NOT EXISTS idx_conventions_status ON conventions(status);",
    # build_log
    "CREATE INDEX IF NOT EXISTS idx_build_log_started ON build_log(build_started);",
    "CREATE INDEX IF NOT EXISTS idx_build_log_path    ON build_log(artifact_path);",
]


# ---------------------------------------------------------------------------
# All DDL statements in execution order
# ---------------------------------------------------------------------------

_ALL_DDL: list[str] = [
    _CREATE_META,
    _CREATE_ARTIFACTS,
    _CREATE_LINKS,
    _CREATE_TAGS,
    _CREATE_ALIASES,
    _CREATE_CONVENTIONS,
    _CREATE_BUILD_LOG,
    _CREATE_FTS,
    *_INDEXES,
]

# Tables to drop on schema reset (order matters for foreign keys).
_DROP_ORDER: list[str] = [
    "build_log",
    "conventions",
    "aliases",
    "tags",
    "links",
    "artifacts_fts",
    "artifacts",
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
    """Create or recreate the link graph schema.

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

    # Seed schema version
    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
        ("schema_version", str(SCHEMA_VERSION)),
    )
    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
        ("built_at", datetime.now(UTC).isoformat()),
    )
    conn.commit()
    return True


def _drop_all(conn: sqlite3.Connection) -> None:
    """Drop all link graph tables. Order respects foreign key dependencies."""
    for table in _DROP_ORDER:
        conn.execute(f"DROP TABLE IF EXISTS {table}")


def _create_all(conn: sqlite3.Connection) -> None:
    """Execute all DDL statements to create the schema."""
    for ddl in _ALL_DDL:
        conn.executescript(ddl)
