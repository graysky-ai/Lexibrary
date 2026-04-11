"""Read-only health reporter for the symbol graph database.

Provides :func:`read_symbol_graph_health` which inspects
``.lexibrary/symbols.db`` under a project root and returns a
:class:`SymbolGraphHealth` dataclass describing the database's
existence, schema version, build timestamp, and per-table row counts.

Contract
--------

- This module is **read-only**. It never creates the database, never
  calls :func:`~lexibrary.symbolgraph.schema.ensure_schema`, and never
  calls :func:`~lexibrary.symbolgraph.schema.set_pragmas` (writing
  pragmas to a corrupt or locked DB could itself raise).
- If the database file does not exist, :func:`read_symbol_graph_health`
  returns ``SymbolGraphHealth(exists=False, schema_version=None,
  built_at=None, ...=0)`` without creating anything.
- On any :class:`sqlite3.Error` (missing ``meta`` table, IO error,
  corrupt file, locked DB, missing tables), it returns
  ``SymbolGraphHealth(exists=True, schema_version=None, built_at=None,
  ...=0)`` — the file exists but cannot be read reliably.

Callers that need to open or mutate the symbol graph should use
:func:`~lexibrary.symbolgraph.query.open_symbol_graph` instead.
"""

from __future__ import annotations

import contextlib
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from lexibrary.utils.paths import symbols_db_path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SymbolGraphHealth:
    """Summary of the symbol graph database state.

    Attributes
    ----------
    exists:
        ``True`` when ``.lexibrary/symbols.db`` exists on disk,
        ``False`` otherwise. A ``True`` value does not imply the
        database is readable — a corrupt file still returns
        ``exists=True`` with the remaining fields at their safe
        defaults.
    schema_version:
        Stored schema version from the ``meta`` table, or ``None``
        when the database is absent, corrupt, or missing the
        ``meta.schema_version`` row.
    built_at:
        ISO-8601 timestamp from the ``meta`` table's ``built_at``
        row, or ``None`` when absent or unreadable.
    file_count:
        Number of rows in ``files``. ``0`` when the database is
        absent, corrupt, or empty.
    symbol_count:
        Number of rows in ``symbols``.
    call_count:
        Number of rows in ``calls``.
    unresolved_call_count:
        Number of rows in ``unresolved_calls``.
    class_edge_count:
        Number of rows in ``class_edges``.
    member_count:
        Number of rows in ``symbol_members``.
    """

    exists: bool
    schema_version: int | None
    built_at: str | None
    file_count: int
    symbol_count: int
    call_count: int
    unresolved_call_count: int
    class_edge_count: int
    member_count: int


def _safe_default(*, exists: bool) -> SymbolGraphHealth:
    """Build a safe-default :class:`SymbolGraphHealth` with zeroed counts."""
    return SymbolGraphHealth(
        exists=exists,
        schema_version=None,
        built_at=None,
        file_count=0,
        symbol_count=0,
        call_count=0,
        unresolved_call_count=0,
        class_edge_count=0,
        member_count=0,
    )


def _read_meta_value(conn: sqlite3.Connection, key: str) -> str | None:
    """Return ``meta.value`` for *key*, or ``None`` when missing."""
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    if row is None:
        return None
    return str(row[0])


def _read_schema_version(conn: sqlite3.Connection) -> int | None:
    """Return the stored schema version as ``int``, or ``None`` when unreadable."""
    raw = _read_meta_value(conn, "schema_version")
    if raw is None:
        return None
    try:
        return int(raw)
    except (ValueError, TypeError):
        return None


def _count_rows(conn: sqlite3.Connection, table: str) -> int:
    """Return ``SELECT COUNT(*) FROM table``."""
    row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()  # noqa: S608
    return int(row[0])


def read_symbol_graph_health(project_root: Path) -> SymbolGraphHealth:
    """Read symbol graph health from ``.lexibrary/symbols.db``.

    Opens the symbol graph database under *project_root* in a
    read-only fashion (no pragmas, no schema enforcement) and reads:

    - ``schema_version`` and ``built_at`` from the ``meta`` table.
    - ``SELECT COUNT(*)`` over every DDL table: ``files``,
      ``symbols``, ``calls``, ``unresolved_calls``, ``class_edges``,
      and ``symbol_members``.

    The function never creates the database, never calls
    :func:`~lexibrary.symbolgraph.schema.ensure_schema`, and never
    calls :func:`~lexibrary.symbolgraph.schema.set_pragmas`. It is
    safe to call against a missing, empty, or corrupt file.

    Parameters
    ----------
    project_root:
        Absolute path to the project root.

    Returns
    -------
    SymbolGraphHealth
        A summary of the database state. When the file is missing,
        ``exists=False`` with all counts at ``0`` and version/built
        fields ``None``. When the file exists but cannot be read,
        ``exists=True`` with the same safe defaults.
    """
    db_path = symbols_db_path(project_root)
    if not db_path.exists():
        return _safe_default(exists=False)

    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(str(db_path))

        schema_version = _read_schema_version(conn)
        built_at = _read_meta_value(conn, "built_at")

        file_count = _count_rows(conn, "files")
        symbol_count = _count_rows(conn, "symbols")
        call_count = _count_rows(conn, "calls")
        unresolved_call_count = _count_rows(conn, "unresolved_calls")
        class_edge_count = _count_rows(conn, "class_edges")
        member_count = _count_rows(conn, "symbol_members")
    except sqlite3.Error as exc:
        logger.warning("Cannot read symbol graph health from %s: %s", db_path, exc)
        return _safe_default(exists=True)
    finally:
        if conn is not None:
            with contextlib.suppress(Exception):
                conn.close()

    return SymbolGraphHealth(
        exists=True,
        schema_version=schema_version,
        built_at=built_at,
        file_count=file_count,
        symbol_count=symbol_count,
        call_count=call_count,
        unresolved_call_count=unresolved_call_count,
        class_edge_count=class_edge_count,
        member_count=member_count,
    )
