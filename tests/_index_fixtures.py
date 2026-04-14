"""Shared SQLite index fixtures for validator / archivist tests.

Historically ``_create_index_with_links`` lived in
``tests/test_validator/test_info_checks.py``.  Phase 1a of the
bidirectional-deps migration (OpenSpec change ``curator-freshness``)
introduced a second class of tests — the archivist reconciler and the
validator fixer — that need the same helper, so we moved the
definition here and left the original file importing from this module.

Keep the helper minimal; tests that need richer fixtures should wrap
this helper rather than complicate it.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from lexibrary.linkgraph.schema import ensure_schema


def _create_index_with_links(
    lexibrary_dir: Path,
    artifacts: list[tuple[int, str, str]],
    links: list[tuple[int, int, str]],
) -> None:
    """Create an ``index.db`` with the given artifacts and links.

    Args:
        lexibrary_dir: Path to the ``.lexibrary`` directory that owns the
            index.  The DB is written to ``<lexibrary_dir>/index.db``.
        artifacts: List of ``(id, path, kind)`` tuples to insert into the
            ``artifacts`` table.
        links: List of ``(source_id, target_id, link_type)`` tuples to
            insert into the ``links`` table.
    """
    db_path = lexibrary_dir / "index.db"
    conn = sqlite3.connect(str(db_path))
    ensure_schema(conn)
    for art_id, art_path, kind in artifacts:
        conn.execute(
            "INSERT INTO artifacts (id, path, kind, title, status) VALUES (?, ?, ?, ?, ?)",
            (art_id, art_path, kind, f"Artifact {art_id}", None),
        )
    for src_id, tgt_id, link_type in links:
        conn.execute(
            "INSERT INTO links (source_id, target_id, link_type) VALUES (?, ?, ?)",
            (src_id, tgt_id, link_type),
        )
    conn.commit()
    conn.close()
