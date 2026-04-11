"""Tests for template-seeded ``.gitignore`` content.

These tests assert that the scaffolder — the single source of truth for
project-level ignore patterns seeded into a new project's ``.gitignore`` —
includes the symbol graph database (``.lexibrary/symbols.db``) alongside
its WAL/SHM sidecars. The scaffolder's ``_GENERATED_GITIGNORE_PATTERNS``
constant is the authoritative template; calling
:func:`create_lexibrary_skeleton` materialises those patterns into a
freshly-created ``.gitignore`` under a temp project root, which is the
surface this test exercises.
"""

from __future__ import annotations

from pathlib import Path

from lexibrary.init.scaffolder import create_lexibrary_skeleton


def test_gitignore_template_includes_symbols_db(tmp_path: Path) -> None:
    """Scaffolder-seeded ``.gitignore`` must list ``.lexibrary/symbols.db``.

    Creating a fresh ``.lexibrary/`` skeleton in an empty project root
    should produce a ``.gitignore`` containing the symbol graph database
    pattern. Asserting the bare ``.lexibrary/symbols.db`` line (rather
    than just a substring) guards against accidental deletion or
    renaming of the template entry while remaining robust to ordering
    or additional sidecar entries.
    """
    create_lexibrary_skeleton(tmp_path)

    gitignore_path = tmp_path / ".gitignore"
    assert gitignore_path.is_file(), ".gitignore should be created"

    lines = {line.strip() for line in gitignore_path.read_text().splitlines() if line.strip()}
    assert ".lexibrary/symbols.db" in lines
    # The WAL/SHM sidecars belong with the primary DB pattern — they
    # must be seeded together so SQLite artefacts never leak into commits.
    assert ".lexibrary/symbols.db-wal" in lines
    assert ".lexibrary/symbols.db-shm" in lines
