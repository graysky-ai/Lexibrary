"""Tests for linkgraph health helper -- read_index_health() and IndexHealth.

Covers five scenarios per task 1.2:
  1. Index exists with data -- returns correct counts and built_at
  2. Index exists but empty -- returns zero counts, built_at from schema init
  3. Index does not exist -- returns all-None IndexHealth
  4. Index is corrupt -- returns all-None IndexHealth
  5. Schema version mismatch -- returns all-None IndexHealth
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from lexibrary.linkgraph.health import IndexHealth, read_index_health
from lexibrary.linkgraph.schema import SCHEMA_VERSION, ensure_schema
from lexibrary.utils.paths import LEXIBRARY_DIR

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def project_root(tmp_path: Path) -> Path:
    """Create a project root with a .lexibrary/ directory."""
    lex_dir = tmp_path / LEXIBRARY_DIR
    lex_dir.mkdir()
    return tmp_path


@pytest.fixture()
def populated_project(project_root: Path) -> Path:
    """Create a project root with a populated index.db.

    Contains 3 artifacts and 2 links with a known built_at timestamp.
    """
    db_path = project_root / LEXIBRARY_DIR / "index.db"
    conn = sqlite3.connect(str(db_path))
    ensure_schema(conn)

    # Insert artifacts
    conn.execute(
        "INSERT INTO artifacts (id, path, kind, title, status) "
        "VALUES (1, 'src/auth/service.py', 'source', 'Auth service', 'active')"
    )
    conn.execute(
        "INSERT INTO artifacts (id, path, kind, title, status) "
        "VALUES (2, '.lexibrary/src/auth/service.py.md', 'design', 'Auth design', NULL)"
    )
    conn.execute(
        "INSERT INTO artifacts (id, path, kind, title, status) "
        "VALUES (3, 'src/api/controller.py', 'source', 'API controller', 'active')"
    )

    # Insert links
    conn.execute(
        "INSERT INTO links (source_id, target_id, link_type) VALUES (2, 1, 'design_source')"
    )
    conn.execute("INSERT INTO links (source_id, target_id, link_type) VALUES (3, 1, 'ast_import')")

    # Update meta with a known built_at timestamp
    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('built_at', '2026-02-20T10:30:00+00:00')"
    )
    conn.commit()
    conn.close()

    return project_root


@pytest.fixture()
def empty_project(project_root: Path) -> Path:
    """Create a project root with an empty (schema-only) index.db."""
    db_path = project_root / LEXIBRARY_DIR / "index.db"
    conn = sqlite3.connect(str(db_path))
    ensure_schema(conn)
    conn.close()
    return project_root


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestIndexExistsWithData:
    """Scenario 1: Index exists with data -- correct counts and built_at."""

    def test_returns_correct_artifact_count(self, populated_project: Path) -> None:
        health = read_index_health(populated_project)
        assert health.artifact_count == 3

    def test_returns_correct_link_count(self, populated_project: Path) -> None:
        health = read_index_health(populated_project)
        assert health.link_count == 2

    def test_returns_correct_built_at(self, populated_project: Path) -> None:
        health = read_index_health(populated_project)
        assert health.built_at == "2026-02-20T10:30:00+00:00"

    def test_returns_index_health_dataclass(self, populated_project: Path) -> None:
        health = read_index_health(populated_project)
        assert isinstance(health, IndexHealth)


class TestIndexExistsButEmpty:
    """Scenario 2: Index exists but has no data rows -- zero counts."""

    def test_returns_zero_artifact_count(self, empty_project: Path) -> None:
        health = read_index_health(empty_project)
        assert health.artifact_count == 0

    def test_returns_zero_link_count(self, empty_project: Path) -> None:
        health = read_index_health(empty_project)
        assert health.link_count == 0

    def test_built_at_is_present(self, empty_project: Path) -> None:
        """ensure_schema sets built_at in the meta table."""
        health = read_index_health(empty_project)
        assert health.built_at is not None


class TestIndexDoesNotExist:
    """Scenario 3: No index.db file -- all-None IndexHealth."""

    def test_returns_none_when_no_db(self, project_root: Path) -> None:
        """No index.db in .lexibrary/ directory."""
        health = read_index_health(project_root)
        assert health.artifact_count is None
        assert health.link_count is None
        assert health.built_at is None

    def test_returns_none_when_no_lexibrary_dir(self, tmp_path: Path) -> None:
        """No .lexibrary/ directory at all."""
        health = read_index_health(tmp_path)
        assert health.artifact_count is None
        assert health.link_count is None
        assert health.built_at is None


class TestIndexIsCorrupt:
    """Scenario 4: index.db exists but is corrupt -- all-None IndexHealth."""

    def test_returns_none_for_corrupt_db(self, project_root: Path) -> None:
        db_path = project_root / LEXIBRARY_DIR / "index.db"
        db_path.write_bytes(b"this is not a valid sqlite database at all")
        health = read_index_health(project_root)
        assert health.artifact_count is None
        assert health.link_count is None
        assert health.built_at is None

    def test_returns_none_for_empty_file(self, project_root: Path) -> None:
        db_path = project_root / LEXIBRARY_DIR / "index.db"
        db_path.write_bytes(b"")
        health = read_index_health(project_root)
        assert health.artifact_count is None
        assert health.link_count is None
        assert health.built_at is None


class TestSchemaVersionMismatch:
    """Scenario 5: index.db has wrong schema version -- all-None IndexHealth."""

    def test_returns_none_for_wrong_version(self, project_root: Path) -> None:
        db_path = project_root / LEXIBRARY_DIR / "index.db"
        conn = sqlite3.connect(str(db_path))
        ensure_schema(conn)
        # Override schema_version to a wrong value
        conn.execute(
            "UPDATE meta SET value = ? WHERE key = 'schema_version'",
            (str(SCHEMA_VERSION + 999),),
        )
        conn.commit()
        conn.close()

        health = read_index_health(project_root)
        assert health.artifact_count is None
        assert health.link_count is None
        assert health.built_at is None

    def test_returns_none_for_missing_version(self, project_root: Path) -> None:
        """Meta table exists but schema_version row is missing."""
        db_path = project_root / LEXIBRARY_DIR / "index.db"
        conn = sqlite3.connect(str(db_path))
        ensure_schema(conn)
        # Delete the schema_version row
        conn.execute("DELETE FROM meta WHERE key = 'schema_version'")
        conn.commit()
        conn.close()

        health = read_index_health(project_root)
        assert health.artifact_count is None
        assert health.link_count is None
        assert health.built_at is None
