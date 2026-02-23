"""Lightweight index health helper for the link graph.

Provides :func:`read_index_health` which opens ``index.db``, reads
counts and the ``built_at`` timestamp from the ``meta`` table, and
returns a :class:`IndexHealth` dataclass.  Designed for use by
``lexictl status`` and validation checks that need quick metadata
without instantiating the full :class:`LinkGraph` query interface.
"""

from __future__ import annotations

import contextlib
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from lexibrarian.linkgraph.schema import SCHEMA_VERSION, check_schema_version, set_pragmas
from lexibrarian.utils.paths import LEXIBRARY_DIR

logger = logging.getLogger(__name__)

_INDEX_DB_NAME = "index.db"
"""Filename of the SQLite index database within ``.lexibrary/``."""


@dataclass
class IndexHealth:
    """Summary of the link graph index state.

    All fields are ``None`` when the index is absent, corrupt, or has
    a schema version mismatch.  Callers should check for ``None`` on
    any field to determine whether the index is usable.
    """

    artifact_count: int | None
    link_count: int | None
    built_at: str | None


def read_index_health(project_root: Path) -> IndexHealth:
    """Read link graph index health from ``index.db``.

    Opens ``.lexibrary/index.db`` under *project_root*, sets pragmas,
    verifies the schema version, and reads:

    - ``artifact_count``: ``SELECT COUNT(*) FROM artifacts``
    - ``link_count``: ``SELECT COUNT(*) FROM links``
    - ``built_at``: ``meta`` table value for key ``'built_at'``

    Returns an :class:`IndexHealth` with all ``None`` fields when:

    - The database file does not exist
    - The database is corrupt (cannot be opened or queried)
    - The schema version is missing or does not match
      :data:`~lexibrarian.linkgraph.schema.SCHEMA_VERSION`

    Parameters
    ----------
    project_root:
        Absolute path to the repository root.

    Returns
    -------
    IndexHealth
        Health summary with counts and timestamp, or all-``None``
        fields for graceful degradation.
    """
    _empty = IndexHealth(artifact_count=None, link_count=None, built_at=None)

    db_path = project_root / LEXIBRARY_DIR / _INDEX_DB_NAME
    if not db_path.is_file():
        return _empty

    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(str(db_path))
        set_pragmas(conn)

        # Verify schema version
        version = check_schema_version(conn)
        if version is None or version != SCHEMA_VERSION:
            logger.warning(
                "Schema version mismatch for %s: expected %s, got %s",
                db_path,
                SCHEMA_VERSION,
                version,
            )
            return _empty

        # Read counts
        artifact_count = conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
        link_count = conn.execute("SELECT COUNT(*) FROM links").fetchone()[0]

        # Read built_at from meta table
        row = conn.execute("SELECT value FROM meta WHERE key = 'built_at'").fetchone()
        built_at = row[0] if row is not None else None

    except (sqlite3.Error, OSError) as exc:
        logger.warning("Cannot read index health from %s: %s", db_path, exc)
        return _empty

    finally:
        if conn is not None:
            with contextlib.suppress(Exception):
                conn.close()

    return IndexHealth(
        artifact_count=artifact_count,
        link_count=link_count,
        built_at=built_at,
    )
