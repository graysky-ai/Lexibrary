"""Tests for linkgraph builder -- data models, utility functions, and IndexBuilder foundation."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from lexibrary.linkgraph.builder import (
    _BUILDER_ID,
    BuildResult,
    IndexBuilder,
    _extract_wikilinks,
    build_index,
    open_index,
)
from lexibrary.linkgraph.schema import ensure_schema, set_pragmas

# ---------------------------------------------------------------------------
# _extract_wikilinks tests
# ---------------------------------------------------------------------------


class TestExtractWikilinks:
    """Tests for the _extract_wikilinks utility function."""

    def test_multiple_wikilinks(self) -> None:
        """Extract multiple distinct wikilinks from text."""
        text = "Uses [[Authentication]] and [[Authorization]] for access control."
        result = _extract_wikilinks(text)
        assert result == ["Authentication", "Authorization"]

    def test_deduplicated(self) -> None:
        """Duplicate wikilinks are removed, preserving first-occurrence order."""
        text = "Uses [[Authentication]] and [[Authorization]] for [[Authentication]] checks."
        result = _extract_wikilinks(text)
        assert result == ["Authentication", "Authorization"]

    def test_no_wikilinks(self) -> None:
        """Plain text without any [[...]] returns an empty list."""
        text = "This is plain text with no wikilinks at all."
        result = _extract_wikilinks(text)
        assert result == []

    def test_empty_string(self) -> None:
        """Empty input returns an empty list."""
        assert _extract_wikilinks("") == []

    def test_nested_brackets_edge_case(self) -> None:
        """Nested brackets like [[outer [[inner]]]] do not match the inner pair.

        The regex ``[^\\[\\]]+`` excludes bracket characters, so ``[[outer [[inner]]``
        does not produce a match for ``outer [[inner``. Only a valid
        non-bracket-containing match is returned.
        """
        text = "See [[outer [[inner]]]] for details."
        result = _extract_wikilinks(text)
        # The regex matches [[inner]] inside the outer brackets
        assert "inner" in result
        # "outer [[inner" is NOT a valid match (contains brackets)
        assert "outer [[inner" not in result

    def test_single_wikilink(self) -> None:
        """A single wikilink is extracted correctly."""
        text = "Refer to [[Concepts]] for more information."
        result = _extract_wikilinks(text)
        assert result == ["Concepts"]

    def test_wikilinks_with_whitespace(self) -> None:
        """Wikilinks with leading/trailing whitespace are stripped."""
        text = "See [[ Spaces ]] and [[NoSpaces]]."
        result = _extract_wikilinks(text)
        assert result == ["Spaces", "NoSpaces"]

    def test_empty_brackets_ignored(self) -> None:
        """Empty [[ ]] patterns (only whitespace) are not returned."""
        text = "See [[]] and [[ ]] and [[Valid]]."
        result = _extract_wikilinks(text)
        assert result == ["Valid"]

    def test_multiline_text(self) -> None:
        """Wikilinks spanning multiple lines of text are all extracted."""
        text = (
            "First paragraph mentions [[Alpha]].\n"
            "\n"
            "Second paragraph mentions [[Beta]] and [[Alpha]] again.\n"
        )
        result = _extract_wikilinks(text)
        assert result == ["Alpha", "Beta"]

    def test_wikilinks_in_bullet_list(self) -> None:
        """Wikilinks embedded in markdown bullet lists."""
        text = (
            "- Uses [[Authentication]] middleware\n"
            "- Requires [[Logging]] setup\n"
            "- See [[Authentication]] docs\n"
        )
        result = _extract_wikilinks(text)
        assert result == ["Authentication", "Logging"]


# ---------------------------------------------------------------------------
# BuildResult tests
# ---------------------------------------------------------------------------


class TestBuildResult:
    """Tests for the BuildResult dataclass."""

    def test_default_values(self) -> None:
        """BuildResult has sensible defaults for all fields."""
        result = BuildResult()
        assert result.artifact_count == 0
        assert result.link_count == 0
        assert result.duration_ms == 0
        assert result.errors == []
        assert result.build_type == "full"

    def test_custom_values(self) -> None:
        """BuildResult can be constructed with custom values."""
        result = BuildResult(
            artifact_count=100,
            link_count=250,
            duration_ms=1200,
            errors=["parse error in foo.md"],
            build_type="incremental",
        )
        assert result.artifact_count == 100
        assert result.link_count == 250
        assert result.duration_ms == 1200
        assert result.errors == ["parse error in foo.md"]
        assert result.build_type == "incremental"

    def test_errors_list_independence(self) -> None:
        """Each BuildResult instance has its own errors list (no shared default)."""
        a = BuildResult()
        b = BuildResult()
        a.errors.append("error A")
        assert b.errors == []


# ---------------------------------------------------------------------------
# Fixtures for IndexBuilder tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_conn() -> sqlite3.Connection:
    """Return an in-memory SQLite connection with the link graph schema ensured."""
    conn = sqlite3.connect(":memory:")
    set_pragmas(conn)
    ensure_schema(conn)
    return conn


@pytest.fixture()
def builder(db_conn: sqlite3.Connection, tmp_path: Path) -> IndexBuilder:
    """Return an IndexBuilder backed by the in-memory database."""
    return IndexBuilder(db_conn, tmp_path)


# ---------------------------------------------------------------------------
# IndexBuilder.__init__ tests
# ---------------------------------------------------------------------------


class TestIndexBuilderInit:
    """Tests for IndexBuilder construction."""

    def test_stores_conn_and_project_root(
        self, db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """Constructor stores the connection and project_root as attributes."""
        ib = IndexBuilder(db_conn, tmp_path)
        assert ib.conn is db_conn
        assert ib.project_root == tmp_path

    def test_calls_set_pragmas(self, tmp_path: Path) -> None:
        """Constructor calls set_pragmas as a safety measure.

        We verify by checking that WAL mode and foreign keys are enabled
        after construction, even on a fresh connection without prior setup.
        """
        conn = sqlite3.connect(":memory:")
        # Do NOT call set_pragmas before constructing; the constructor should do it.
        ensure_schema(conn)  # ensure_schema also calls set_pragmas internally
        ib = IndexBuilder(conn, tmp_path)
        # Verify foreign keys are ON (set_pragmas enables them)
        fk_row = ib.conn.execute("PRAGMA foreign_keys").fetchone()
        assert fk_row is not None
        assert fk_row[0] == 1


# ---------------------------------------------------------------------------
# _clean_stale_build_log tests
# ---------------------------------------------------------------------------


class TestCleanStaleBuildLog:
    """Tests for IndexBuilder._clean_stale_build_log."""

    def test_deletes_old_entries(self, builder: IndexBuilder) -> None:
        """Entries older than 30 days are deleted."""
        old_ts = (datetime.now(UTC) - timedelta(days=45)).isoformat()
        recent_ts = (datetime.now(UTC) - timedelta(days=10)).isoformat()

        builder.conn.execute(
            "INSERT INTO build_log (build_started, build_type, artifact_path, "
            "artifact_kind, action) VALUES (?, 'full', 'old.py', 'source', 'created')",
            (old_ts,),
        )
        builder.conn.execute(
            "INSERT INTO build_log (build_started, build_type, artifact_path, "
            "artifact_kind, action) VALUES (?, 'full', 'recent.py', 'source', 'created')",
            (recent_ts,),
        )
        builder.conn.commit()

        builder._clean_stale_build_log()

        rows = builder.conn.execute("SELECT artifact_path FROM build_log").fetchall()
        paths = [r[0] for r in rows]
        assert "old.py" not in paths
        assert "recent.py" in paths

    def test_empty_build_log(self, builder: IndexBuilder) -> None:
        """Cleaning an empty build_log completes without error."""
        builder._clean_stale_build_log()  # should not raise
        count = builder.conn.execute("SELECT COUNT(*) FROM build_log").fetchone()[0]
        assert count == 0

    def test_preserves_entries_exactly_30_days_old(self, builder: IndexBuilder) -> None:
        """Entries exactly 30 days old are at the boundary; recent ones survive."""
        # An entry from 29 days ago should survive
        recent_ts = (datetime.now(UTC) - timedelta(days=29)).isoformat()
        builder.conn.execute(
            "INSERT INTO build_log (build_started, build_type, artifact_path, "
            "artifact_kind, action) VALUES (?, 'full', 'border.py', 'source', 'created')",
            (recent_ts,),
        )
        builder.conn.commit()

        builder._clean_stale_build_log()

        count = builder.conn.execute("SELECT COUNT(*) FROM build_log").fetchone()[0]
        assert count == 1


# ---------------------------------------------------------------------------
# _clear_all_data tests
# ---------------------------------------------------------------------------


class TestClearAllData:
    """Tests for IndexBuilder._clear_all_data."""

    def test_clears_artifacts_and_links(self, builder: IndexBuilder) -> None:
        """All rows in artifacts, links, tags, aliases, conventions, and FTS are deleted."""
        # Insert an artifact
        builder.conn.execute("INSERT INTO artifacts (path, kind) VALUES ('src/foo.py', 'source')")
        art_id = builder.conn.execute(
            "SELECT id FROM artifacts WHERE path = 'src/foo.py'"
        ).fetchone()[0]

        # Insert a second artifact for the link target
        builder.conn.execute("INSERT INTO artifacts (path, kind) VALUES ('src/bar.py', 'source')")
        bar_id = builder.conn.execute(
            "SELECT id FROM artifacts WHERE path = 'src/bar.py'"
        ).fetchone()[0]

        # Insert link, tag, FTS
        builder.conn.execute(
            "INSERT INTO links (source_id, target_id, link_type) VALUES (?, ?, 'ast_import')",
            (art_id, bar_id),
        )
        builder.conn.execute(
            "INSERT INTO tags (artifact_id, tag) VALUES (?, 'auth')",
            (art_id,),
        )
        builder.conn.execute(
            "INSERT INTO artifacts_fts (rowid, title, body) VALUES (?, 'foo', 'body')",
            (art_id,),
        )
        builder.conn.commit()

        builder._clear_all_data()

        assert builder.conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0] == 0
        assert builder.conn.execute("SELECT COUNT(*) FROM links").fetchone()[0] == 0
        assert builder.conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0] == 0
        assert builder.conn.execute("SELECT COUNT(*) FROM artifacts_fts").fetchone()[0] == 0

    def test_preserves_meta_and_build_log(self, builder: IndexBuilder) -> None:
        """_clear_all_data does NOT delete meta or build_log rows."""
        builder.conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('test_key', 'test_value')"
        )
        builder.conn.execute(
            "INSERT INTO build_log (build_started, build_type, artifact_path, "
            "artifact_kind, action) VALUES ('2025-01-01T00:00:00', 'full', "
            "'test.py', 'source', 'created')"
        )
        builder.conn.commit()

        builder._clear_all_data()

        meta_count = builder.conn.execute("SELECT COUNT(*) FROM meta").fetchone()[0]
        log_count = builder.conn.execute("SELECT COUNT(*) FROM build_log").fetchone()[0]
        assert meta_count >= 1  # at least schema_version + our test key
        assert log_count == 1


# ---------------------------------------------------------------------------
# _update_meta tests
# ---------------------------------------------------------------------------


class TestUpdateMeta:
    """Tests for IndexBuilder._update_meta."""

    def test_updates_meta_with_counts(self, builder: IndexBuilder) -> None:
        """Meta table is updated with correct artifact_count, link_count, built_at, builder."""
        # Insert two artifacts
        builder.conn.execute("INSERT INTO artifacts (path, kind) VALUES ('src/a.py', 'source')")
        builder.conn.execute("INSERT INTO artifacts (path, kind) VALUES ('src/b.py', 'source')")
        a_id = builder.conn.execute("SELECT id FROM artifacts WHERE path = 'src/a.py'").fetchone()[
            0
        ]
        b_id = builder.conn.execute("SELECT id FROM artifacts WHERE path = 'src/b.py'").fetchone()[
            0
        ]

        # Insert one link
        builder.conn.execute(
            "INSERT INTO links (source_id, target_id, link_type) VALUES (?, ?, 'ast_import')",
            (a_id, b_id),
        )
        builder.conn.commit()

        ts = "2025-06-15T12:00:00+00:00"
        builder._update_meta(ts)

        def meta_val(key: str) -> str | None:
            row = builder.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
            return row[0] if row else None

        assert meta_val("built_at") == ts
        assert meta_val("builder") == _BUILDER_ID
        assert meta_val("artifact_count") == "2"
        assert meta_val("link_count") == "1"

    def test_updates_meta_empty_tables(self, builder: IndexBuilder) -> None:
        """Meta is updated correctly when tables are empty (zero counts)."""
        ts = "2025-06-15T12:00:00+00:00"
        builder._update_meta(ts)

        row = builder.conn.execute("SELECT value FROM meta WHERE key = 'artifact_count'").fetchone()
        assert row is not None
        assert row[0] == "0"


# ---------------------------------------------------------------------------
# _insert_artifact tests
# ---------------------------------------------------------------------------


class TestInsertArtifact:
    """Tests for IndexBuilder._insert_artifact."""

    def test_inserts_and_returns_id(self, builder: IndexBuilder) -> None:
        """An artifact row is inserted and its id is returned."""
        art_id = builder._insert_artifact(
            path="src/foo.py",
            kind="source",
            title="Foo module",
            status="active",
            last_hash="abc123",
            created_at="2025-01-01T00:00:00",
        )
        assert isinstance(art_id, int)
        assert art_id > 0

        row = builder.conn.execute(
            "SELECT path, kind, title, status, last_hash, created_at FROM artifacts WHERE id = ?",
            (art_id,),
        ).fetchone()
        assert row == (
            "src/foo.py",
            "source",
            "Foo module",
            "active",
            "abc123",
            "2025-01-01T00:00:00",
        )

    def test_nullable_fields(self, builder: IndexBuilder) -> None:
        """Artifact can be inserted with all nullable fields as None."""
        art_id = builder._insert_artifact(
            path="src/bar.py",
            kind="source",
            title=None,
            status=None,
            last_hash=None,
            created_at=None,
        )
        row = builder.conn.execute(
            "SELECT title, status, last_hash, created_at FROM artifacts WHERE id = ?",
            (art_id,),
        ).fetchone()
        assert row == (None, None, None, None)

    def test_unique_path_constraint(self, builder: IndexBuilder) -> None:
        """Inserting a duplicate path raises IntegrityError."""
        builder._insert_artifact("dup.py", "source", None, None, None, None)
        with pytest.raises(sqlite3.IntegrityError):
            builder._insert_artifact("dup.py", "source", None, None, None, None)

    def test_sequential_ids(self, builder: IndexBuilder) -> None:
        """Successive inserts produce incrementing ids."""
        id1 = builder._insert_artifact("a.py", "source", None, None, None, None)
        id2 = builder._insert_artifact("b.py", "source", None, None, None, None)
        assert id2 > id1

    def test_all_artifact_kinds(self, builder: IndexBuilder) -> None:
        """All valid artifact kinds can be inserted."""
        for kind in ("source", "design", "concept", "stack", "convention"):
            art_id = builder._insert_artifact(f"test_{kind}", kind, None, None, None, None)
            assert art_id > 0


# ---------------------------------------------------------------------------
# _get_artifact_id tests
# ---------------------------------------------------------------------------


class TestGetArtifactId:
    """Tests for IndexBuilder._get_artifact_id."""

    def test_returns_id_for_existing(self, builder: IndexBuilder) -> None:
        """Returns the id for an artifact that exists."""
        inserted_id = builder._insert_artifact("src/foo.py", "source", None, None, None, None)
        found_id = builder._get_artifact_id("src/foo.py")
        assert found_id == inserted_id

    def test_returns_none_for_missing(self, builder: IndexBuilder) -> None:
        """Returns None for a path with no artifact row."""
        assert builder._get_artifact_id("nonexistent.py") is None

    def test_exact_path_match(self, builder: IndexBuilder) -> None:
        """Only exact path matches return an id; partial matches return None."""
        builder._insert_artifact("src/foo.py", "source", None, None, None, None)
        assert builder._get_artifact_id("src/foo") is None
        assert builder._get_artifact_id("foo.py") is None
        assert builder._get_artifact_id("src/foo.py") is not None


# ---------------------------------------------------------------------------
# _get_or_create_artifact tests
# ---------------------------------------------------------------------------


class TestGetOrCreateArtifact:
    """Tests for IndexBuilder._get_or_create_artifact."""

    def test_returns_existing_id(self, builder: IndexBuilder) -> None:
        """Returns the existing id when the artifact already exists."""
        inserted_id = builder._insert_artifact(
            "src/foo.py", "source", "Foo", "active", "hash1", "2025-01-01"
        )
        found_id = builder._get_or_create_artifact("src/foo.py", "source")
        assert found_id == inserted_id

    def test_creates_stub_when_missing(self, builder: IndexBuilder) -> None:
        """Creates a stub artifact and returns its id when the path doesn't exist."""
        new_id = builder._get_or_create_artifact(
            "concepts/Auth.md", "concept", title="Authentication"
        )
        assert isinstance(new_id, int)
        assert new_id > 0

        # Verify the stub was created with correct values
        row = builder.conn.execute(
            "SELECT path, kind, title, status, last_hash, created_at FROM artifacts WHERE id = ?",
            (new_id,),
        ).fetchone()
        assert row == ("concepts/Auth.md", "concept", "Authentication", None, None, None)

    def test_idempotent(self, builder: IndexBuilder) -> None:
        """Calling twice with the same path returns the same id without creating duplicates."""
        id1 = builder._get_or_create_artifact("concepts/Auth.md", "concept")
        id2 = builder._get_or_create_artifact("concepts/Auth.md", "concept")
        assert id1 == id2

        count = builder.conn.execute(
            "SELECT COUNT(*) FROM artifacts WHERE path = 'concepts/Auth.md'"
        ).fetchone()[0]
        assert count == 1

    def test_does_not_overwrite_existing_data(self, builder: IndexBuilder) -> None:
        """When the artifact exists, the kind/title parameters are ignored."""
        builder._insert_artifact(
            "src/foo.py", "source", "Original Title", "active", "hash1", "2025-01-01"
        )
        found_id = builder._get_or_create_artifact("src/foo.py", "design", title="New Title")
        row = builder.conn.execute(
            "SELECT kind, title FROM artifacts WHERE id = ?", (found_id,)
        ).fetchone()
        # Original values preserved; the "design" kind and "New Title" are ignored
        assert row == ("source", "Original Title")

    def test_stub_has_no_optional_fields(self, builder: IndexBuilder) -> None:
        """Stubs created by _get_or_create_artifact have None for status, hash, created_at."""
        new_id = builder._get_or_create_artifact("stub.py", "source")
        row = builder.conn.execute(
            "SELECT status, last_hash, created_at FROM artifacts WHERE id = ?",
            (new_id,),
        ).fetchone()
        assert row == (None, None, None)


# ---------------------------------------------------------------------------
# Helpers for design file integration tests
# ---------------------------------------------------------------------------

_SAMPLE_DESIGN_FILE = """\
---
description: Handles user authentication
updated_by: archivist
---

# src/auth/login.py

## Interface Contract

```python
def login(username: str, password: str) -> bool: ...
```

## Dependencies

- src/config/schema.py

## Dependents

(none)

## Wikilinks

- [[Authentication]]
- [[Security]]

## Tags

- auth
- security

## Stack

- ST-001

<!-- lexibrary:meta
source: src/auth/login.py
source_hash: abc123
design_hash: def456
generated: 2025-06-15T12:00:00
generator: lexibrary-test
-->
"""

_SAMPLE_SOURCE_FILE = """\
from __future__ import annotations

def login(username: str, password: str) -> bool:
    return True
"""


def _create_design_file_tree(
    tmp_path: Path,
    *,
    source_content: str | None = _SAMPLE_SOURCE_FILE,
    design_content: str = _SAMPLE_DESIGN_FILE,
    source_relpath: str = "src/auth/login.py",
    design_relpath: str = ".lexibrary/src/auth/login.py.md",
) -> Path:
    """Create a minimal project tree with a source file and its design file.

    Returns the project root (tmp_path).
    """
    # Create source file
    if source_content is not None:
        source_path = tmp_path / source_relpath
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text(source_content, encoding="utf-8")

    # Create design file
    design_path = tmp_path / design_relpath
    design_path.parent.mkdir(parents=True, exist_ok=True)
    design_path.write_text(design_content, encoding="utf-8")

    return tmp_path


# ---------------------------------------------------------------------------
# _scan_design_files tests
# ---------------------------------------------------------------------------


class TestScanDesignFiles:
    """Tests for IndexBuilder._scan_design_files."""

    def test_discovers_md_files(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """Discovers all .md files under .lexibrary/src/."""
        _create_design_file_tree(tmp_path)
        # Add a second design file
        second = tmp_path / ".lexibrary" / "src" / "utils" / "hashing.py.md"
        second.parent.mkdir(parents=True, exist_ok=True)
        second.write_text(_SAMPLE_DESIGN_FILE, encoding="utf-8")

        builder = IndexBuilder(db_conn, tmp_path)
        files = builder._scan_design_files()

        assert len(files) == 2
        # Sorted order: auth/login.py.md before utils/hashing.py.md
        assert files[0].name == "login.py.md"
        assert files[1].name == "hashing.py.md"

    def test_empty_when_no_dir(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """Returns empty list when .lexibrary/src/ does not exist."""
        builder = IndexBuilder(db_conn, tmp_path)
        assert builder._scan_design_files() == []

    def test_empty_when_no_md_files(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """Returns empty list when .lexibrary/src/ exists but contains no .md files."""
        (tmp_path / ".lexibrary" / "src").mkdir(parents=True)
        builder = IndexBuilder(db_conn, tmp_path)
        assert builder._scan_design_files() == []


# ---------------------------------------------------------------------------
# _design_path_to_source_relpath tests
# ---------------------------------------------------------------------------


class TestDesignPathToSourceRelpath:
    """Tests for IndexBuilder._design_path_to_source_relpath."""

    def test_standard_path(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """Converts .lexibrary/src/auth/login.py.md to src/auth/login.py."""
        builder = IndexBuilder(db_conn, tmp_path)
        design_path = tmp_path / ".lexibrary" / "src" / "auth" / "login.py.md"
        result = builder._design_path_to_source_relpath(design_path)
        assert result == "src/auth/login.py"

    def test_nested_path(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """Handles deeply nested design file paths."""
        builder = IndexBuilder(db_conn, tmp_path)
        design_path = tmp_path / ".lexibrary" / "src" / "a" / "b" / "c.py.md"
        result = builder._design_path_to_source_relpath(design_path)
        assert result == "src/a/b/c.py"

    def test_top_level_source(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """Handles design file for a source file directly under src/."""
        builder = IndexBuilder(db_conn, tmp_path)
        design_path = tmp_path / ".lexibrary" / "src" / "main.py.md"
        result = builder._design_path_to_source_relpath(design_path)
        assert result == "src/main.py"


# ---------------------------------------------------------------------------
# _compute_source_hash tests
# ---------------------------------------------------------------------------


class TestComputeSourceHash:
    """Tests for IndexBuilder._compute_source_hash."""

    def test_existing_file(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """Returns SHA-256 hex digest for an existing source file."""
        _create_design_file_tree(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        result = builder._compute_source_hash("src/auth/login.py")
        assert result is not None
        assert len(result) == 64  # SHA-256 hex length

    def test_missing_file(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """Returns None when the source file does not exist."""
        builder = IndexBuilder(db_conn, tmp_path)
        result = builder._compute_source_hash("src/nonexistent.py")
        assert result is None


# ---------------------------------------------------------------------------
# _process_design_file integration tests
# ---------------------------------------------------------------------------


class TestProcessDesignFile:
    """Integration tests for IndexBuilder._process_design_file.

    Each test creates a real project tree in tmp_path, runs the processing
    method, and verifies the database contents.
    """

    def test_creates_source_and_design_artifacts(
        self, db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """Processing a design file creates both source and design artifacts."""
        _create_design_file_tree(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        build_ts = "2025-06-15T12:00:00+00:00"

        design_path = tmp_path / ".lexibrary" / "src" / "auth" / "login.py.md"
        builder._process_design_file(design_path, build_ts)

        # Check source artifact
        source_row = db_conn.execute(
            "SELECT path, kind, title FROM artifacts WHERE path = 'src/auth/login.py'"
        ).fetchone()
        assert source_row is not None
        assert source_row[1] == "source"
        assert source_row[2] == "Handles user authentication"

        # Check design artifact
        design_row = db_conn.execute(
            "SELECT path, kind, title FROM artifacts WHERE path = '.lexibrary/src/auth/login.py.md'"
        ).fetchone()
        assert design_row is not None
        assert design_row[1] == "design"
        assert design_row[2] == "Handles user authentication"

    def test_creates_design_source_link(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """A design_source link connects design to source artifact."""
        _create_design_file_tree(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        builder._process_design_file(
            tmp_path / ".lexibrary" / "src" / "auth" / "login.py.md",
            "2025-06-15T12:00:00+00:00",
        )

        link = db_conn.execute(
            "SELECT l.link_type FROM links l "
            "JOIN artifacts src ON l.source_id = src.id "
            "JOIN artifacts tgt ON l.target_id = tgt.id "
            "WHERE src.path = '.lexibrary/src/auth/login.py.md' "
            "  AND tgt.path = 'src/auth/login.py' "
            "  AND l.link_type = 'design_source'"
        ).fetchone()
        assert link is not None

    def test_source_hash_populated_when_file_exists(
        self, db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """Source artifact has a non-null last_hash when the source file exists."""
        _create_design_file_tree(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        builder._process_design_file(
            tmp_path / ".lexibrary" / "src" / "auth" / "login.py.md",
            "2025-06-15T12:00:00+00:00",
        )

        row = db_conn.execute(
            "SELECT last_hash FROM artifacts WHERE path = 'src/auth/login.py'"
        ).fetchone()
        assert row is not None
        assert row[0] is not None
        assert len(row[0]) == 64

    def test_source_hash_null_when_file_missing(
        self, db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """Source artifact has null last_hash when the source file does not exist."""
        _create_design_file_tree(tmp_path, source_content=None)
        builder = IndexBuilder(db_conn, tmp_path)
        builder._process_design_file(
            tmp_path / ".lexibrary" / "src" / "auth" / "login.py.md",
            "2025-06-15T12:00:00+00:00",
        )

        row = db_conn.execute(
            "SELECT last_hash FROM artifacts WHERE path = 'src/auth/login.py'"
        ).fetchone()
        assert row is not None
        assert row[0] is None

    def test_wikilink_links_created(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """Wikilinks in the design file create wikilink links to concept artifacts."""
        _create_design_file_tree(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        builder._process_design_file(
            tmp_path / ".lexibrary" / "src" / "auth" / "login.py.md",
            "2025-06-15T12:00:00+00:00",
        )

        wikilinks = db_conn.execute(
            "SELECT tgt.path FROM links l "
            "JOIN artifacts tgt ON l.target_id = tgt.id "
            "WHERE l.link_type = 'wikilink'"
        ).fetchall()
        paths = sorted(r[0] for r in wikilinks)
        assert ".lexibrary/concepts/Authentication.md" in paths
        assert ".lexibrary/concepts/Security.md" in paths

    def test_stub_concept_artifacts_created(
        self, db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """Wikilinks to concepts that have no file create stub concept artifacts."""
        _create_design_file_tree(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        builder._process_design_file(
            tmp_path / ".lexibrary" / "src" / "auth" / "login.py.md",
            "2025-06-15T12:00:00+00:00",
        )

        auth_concept = db_conn.execute(
            "SELECT kind, title FROM artifacts WHERE path = '.lexibrary/concepts/Authentication.md'"
        ).fetchone()
        assert auth_concept is not None
        assert auth_concept[0] == "concept"
        assert auth_concept[1] == "Authentication"

    def test_stack_ref_links_created(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """Stack references in the design file create design_stack_ref links."""
        _create_design_file_tree(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        builder._process_design_file(
            tmp_path / ".lexibrary" / "src" / "auth" / "login.py.md",
            "2025-06-15T12:00:00+00:00",
        )

        stack_links = db_conn.execute(
            "SELECT tgt.path FROM links l "
            "JOIN artifacts tgt ON l.target_id = tgt.id "
            "WHERE l.link_type = 'design_stack_ref'"
        ).fetchall()
        assert len(stack_links) == 1
        assert stack_links[0][0] == ".lexibrary/stack/ST-001.md"

    def test_tags_inserted(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """Tags from the design file are inserted into the tags table."""
        _create_design_file_tree(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        builder._process_design_file(
            tmp_path / ".lexibrary" / "src" / "auth" / "login.py.md",
            "2025-06-15T12:00:00+00:00",
        )

        tags = db_conn.execute(
            "SELECT t.tag FROM tags t "
            "JOIN artifacts a ON t.artifact_id = a.id "
            "WHERE a.path = '.lexibrary/src/auth/login.py.md'"
        ).fetchall()
        tag_names = sorted(r[0] for r in tags)
        assert tag_names == ["auth", "security"]

    def test_fts_row_inserted(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """An FTS row is inserted for the design artifact with correct content."""
        _create_design_file_tree(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        builder._process_design_file(
            tmp_path / ".lexibrary" / "src" / "auth" / "login.py.md",
            "2025-06-15T12:00:00+00:00",
        )

        design_id = db_conn.execute(
            "SELECT id FROM artifacts WHERE path = '.lexibrary/src/auth/login.py.md'"
        ).fetchone()[0]
        fts_row = db_conn.execute(
            "SELECT title, body FROM artifacts_fts WHERE rowid = ?",
            (design_id,),
        ).fetchone()
        assert fts_row is not None
        assert fts_row[0] == "Handles user authentication"
        # Body should contain the summary (frontmatter description) and interface contract
        assert "Handles user authentication" in fts_row[1]
        assert "def login" in fts_row[1]

    def test_build_log_entry_created(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """A build_log entry is created for a successfully processed design file."""
        _create_design_file_tree(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        build_ts = "2025-06-15T12:00:00+00:00"
        builder._process_design_file(
            tmp_path / ".lexibrary" / "src" / "auth" / "login.py.md",
            build_ts,
        )

        log = db_conn.execute(
            "SELECT build_type, artifact_path, artifact_kind, action "
            "FROM build_log WHERE artifact_path = '.lexibrary/src/auth/login.py.md'"
        ).fetchone()
        assert log is not None
        assert log[0] == "full"
        assert log[2] == "design"
        assert log[3] == "created"

    def test_failed_parse_logged(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """A malformed design file results in a 'failed' build_log entry."""
        # Create a malformed design file (no frontmatter)
        malformed = "# Just a heading\nNo proper format here.\n"
        _create_design_file_tree(tmp_path, design_content=malformed)
        builder = IndexBuilder(db_conn, tmp_path)
        build_ts = "2025-06-15T12:00:00+00:00"
        builder._process_design_file(
            tmp_path / ".lexibrary" / "src" / "auth" / "login.py.md",
            build_ts,
        )

        log = db_conn.execute(
            "SELECT action, error_message FROM build_log "
            "WHERE artifact_path = '.lexibrary/src/auth/login.py.md'"
        ).fetchone()
        assert log is not None
        assert log[0] == "failed"
        assert log[1] is not None
        assert "Failed to parse" in log[1]

    def test_no_wikilinks_or_stack_refs(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """A design file with no wikilinks or stack refs creates no such links."""
        minimal_design = """\
---
description: Simple module
updated_by: archivist
---

# src/simple.py

## Interface Contract

```python
def simple() -> None: ...
```

## Dependencies

(none)

## Dependents

(none)

<!-- lexibrary:meta
source: src/simple.py
source_hash: abc123
design_hash: def456
generated: 2025-06-15T12:00:00
generator: lexibrary-test
-->
"""
        _create_design_file_tree(
            tmp_path,
            source_content="def simple() -> None: pass\n",
            design_content=minimal_design,
            source_relpath="src/simple.py",
            design_relpath=".lexibrary/src/simple.py.md",
        )
        builder = IndexBuilder(db_conn, tmp_path)
        builder._process_design_file(
            tmp_path / ".lexibrary" / "src" / "simple.py.md",
            "2025-06-15T12:00:00+00:00",
        )

        wikilinks = db_conn.execute(
            "SELECT COUNT(*) FROM links WHERE link_type = 'wikilink'"
        ).fetchone()[0]
        stack_refs = db_conn.execute(
            "SELECT COUNT(*) FROM links WHERE link_type = 'design_stack_ref'"
        ).fetchone()[0]
        assert wikilinks == 0
        assert stack_refs == 0

    def test_multiple_design_files_processed(
        self, db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """Multiple design files can be processed sequentially without conflict."""
        _create_design_file_tree(tmp_path)

        # Create a second design file
        second_design = """\
---
description: Utility helpers
updated_by: archivist
---

# src/utils/helpers.py

## Interface Contract

```python
def helper() -> str: ...
```

## Dependencies

(none)

## Dependents

(none)

<!-- lexibrary:meta
source: src/utils/helpers.py
source_hash: xyz789
design_hash: uvw012
generated: 2025-06-15T12:00:00
generator: lexibrary-test
-->
"""
        second_source = "def helper() -> str: return 'hi'\n"
        helpers_design = tmp_path / ".lexibrary" / "src" / "utils" / "helpers.py.md"
        helpers_design.parent.mkdir(parents=True, exist_ok=True)
        helpers_design.write_text(second_design, encoding="utf-8")
        helpers_source = tmp_path / "src" / "utils" / "helpers.py"
        helpers_source.parent.mkdir(parents=True, exist_ok=True)
        helpers_source.write_text(second_source, encoding="utf-8")

        builder = IndexBuilder(db_conn, tmp_path)
        build_ts = "2025-06-15T12:00:00+00:00"
        for df in builder._scan_design_files():
            builder._process_design_file(df, build_ts)

        artifact_count = db_conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
        # 2 source + 2 design + 2 concept stubs (Authentication, Security) + 1 stack stub
        assert artifact_count >= 4  # at least source + design for each file

        design_source_links = db_conn.execute(
            "SELECT COUNT(*) FROM links WHERE link_type = 'design_source'"
        ).fetchone()[0]
        assert design_source_links == 2


# ---------------------------------------------------------------------------
# Helpers for concept file integration tests
# ---------------------------------------------------------------------------

_SAMPLE_CONCEPT_FILE = """\
---
title: Authentication
aliases:
  - auth
  - authn
tags:
  - security
  - identity
status: active
---

Authentication is the process of verifying identity.

See also [[Authorization]] and [[SessionManagement]] for related concepts.

## Linked Files

- `src/auth/login.py`
- `src/auth/middleware.py`

## Decision Log

- D-001: Use JWT tokens for stateless auth
"""

_SAMPLE_CONCEPT_FILE_B = """\
---
title: Authorization
aliases:
  - authz
tags:
  - security
  - access-control
status: active
---

Authorization determines what actions a user may perform.

It depends on [[Authentication]] being completed first.

## Linked Files

- `src/auth/permissions.py`
"""

_SAMPLE_CONCEPT_ALIAS_COLLISION = """\
---
title: AuthService
aliases:
  - auth
tags:
  - security
status: draft
---

The AuthService concept covers both authentication and authorization.
"""


def _create_concept_file(
    tmp_path: Path,
    filename: str = "Authentication.md",
    content: str = _SAMPLE_CONCEPT_FILE,
) -> Path:
    """Create a concept file under .lexibrary/concepts/ and return its path."""
    concept_dir = tmp_path / ".lexibrary" / "concepts"
    concept_dir.mkdir(parents=True, exist_ok=True)
    concept_path = concept_dir / filename
    concept_path.write_text(content, encoding="utf-8")
    return concept_path


# ---------------------------------------------------------------------------
# _scan_concept_files tests
# ---------------------------------------------------------------------------


class TestScanConceptFiles:
    """Tests for IndexBuilder._scan_concept_files."""

    def test_discovers_md_files(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """Discovers all .md files under .lexibrary/concepts/."""
        _create_concept_file(tmp_path, "Authentication.md")
        _create_concept_file(tmp_path, "Authorization.md", _SAMPLE_CONCEPT_FILE_B)

        builder = IndexBuilder(db_conn, tmp_path)
        files = builder._scan_concept_files()

        assert len(files) == 2
        names = [f.name for f in files]
        assert "Authentication.md" in names
        assert "Authorization.md" in names

    def test_empty_when_no_dir(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """Returns empty list when .lexibrary/concepts/ does not exist."""
        builder = IndexBuilder(db_conn, tmp_path)
        assert builder._scan_concept_files() == []

    def test_empty_when_no_md_files(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """Returns empty list when .lexibrary/concepts/ exists but has no .md files."""
        (tmp_path / ".lexibrary" / "concepts").mkdir(parents=True)
        builder = IndexBuilder(db_conn, tmp_path)
        assert builder._scan_concept_files() == []

    def test_sorted_order(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """Results are sorted by path for deterministic processing order."""
        _create_concept_file(tmp_path, "Zebra.md", _SAMPLE_CONCEPT_FILE_B)
        _create_concept_file(tmp_path, "Alpha.md", _SAMPLE_CONCEPT_FILE)

        builder = IndexBuilder(db_conn, tmp_path)
        files = builder._scan_concept_files()

        assert files[0].name == "Alpha.md"
        assert files[1].name == "Zebra.md"


# ---------------------------------------------------------------------------
# _process_concept_file integration tests
# ---------------------------------------------------------------------------


class TestProcessConceptFile:
    """Integration tests for IndexBuilder._process_concept_file.

    Each test creates a real concept file in tmp_path, runs the processing
    method, and verifies the database contents.
    """

    def test_creates_concept_artifact(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """Processing a concept file creates a concept artifact."""
        concept_path = _create_concept_file(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        build_ts = "2025-06-15T12:00:00+00:00"

        builder._process_concept_file(concept_path, build_ts)

        row = db_conn.execute(
            "SELECT path, kind, title, status FROM artifacts "
            "WHERE path = '.lexibrary/concepts/Authentication.md'"
        ).fetchone()
        assert row is not None
        assert row[0] == ".lexibrary/concepts/Authentication.md"
        assert row[1] == "concept"
        assert row[2] == "Authentication"
        assert row[3] == "active"

    def test_aliases_inserted(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """Aliases from the concept frontmatter are inserted into the aliases table."""
        concept_path = _create_concept_file(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        builder._process_concept_file(concept_path, "2025-06-15T12:00:00+00:00")

        aliases = db_conn.execute(
            "SELECT al.alias FROM aliases al "
            "JOIN artifacts a ON al.artifact_id = a.id "
            "WHERE a.path = '.lexibrary/concepts/Authentication.md'"
        ).fetchall()
        alias_names = sorted(r[0] for r in aliases)
        assert alias_names == ["auth", "authn"]

    def test_wikilink_links_created(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """Wikilinks in the concept body create wikilink links to other concept artifacts."""
        concept_path = _create_concept_file(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        builder._process_concept_file(concept_path, "2025-06-15T12:00:00+00:00")

        wikilinks = db_conn.execute(
            "SELECT tgt.path FROM links l "
            "JOIN artifacts tgt ON l.target_id = tgt.id "
            "WHERE l.link_type = 'wikilink'"
        ).fetchall()
        paths = sorted(r[0] for r in wikilinks)
        assert ".lexibrary/concepts/Authorization.md" in paths
        assert ".lexibrary/concepts/SessionManagement.md" in paths

    def test_concept_file_ref_links_created(
        self, db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """Linked files from the concept create concept_file_ref links."""
        concept_path = _create_concept_file(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        builder._process_concept_file(concept_path, "2025-06-15T12:00:00+00:00")

        file_refs = db_conn.execute(
            "SELECT tgt.path FROM links l "
            "JOIN artifacts tgt ON l.target_id = tgt.id "
            "WHERE l.link_type = 'concept_file_ref'"
        ).fetchall()
        paths = sorted(r[0] for r in file_refs)
        assert "src/auth/login.py" in paths
        assert "src/auth/middleware.py" in paths

    def test_tags_inserted(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """Tags from the concept frontmatter are inserted into the tags table."""
        concept_path = _create_concept_file(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        builder._process_concept_file(concept_path, "2025-06-15T12:00:00+00:00")

        tags = db_conn.execute(
            "SELECT t.tag FROM tags t "
            "JOIN artifacts a ON t.artifact_id = a.id "
            "WHERE a.path = '.lexibrary/concepts/Authentication.md'"
        ).fetchall()
        tag_names = sorted(r[0] for r in tags)
        assert tag_names == ["identity", "security"]

    def test_fts_row_inserted(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """An FTS row is inserted for the concept artifact with correct content."""
        concept_path = _create_concept_file(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        builder._process_concept_file(concept_path, "2025-06-15T12:00:00+00:00")

        concept_id = db_conn.execute(
            "SELECT id FROM artifacts WHERE path = '.lexibrary/concepts/Authentication.md'"
        ).fetchone()[0]
        fts_row = db_conn.execute(
            "SELECT title, body FROM artifacts_fts WHERE rowid = ?",
            (concept_id,),
        ).fetchone()
        assert fts_row is not None
        assert fts_row[0] == "Authentication"
        assert "verifying identity" in fts_row[1]

    def test_build_log_entry_created(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """A build_log entry is created for a successfully processed concept file."""
        concept_path = _create_concept_file(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        build_ts = "2025-06-15T12:00:00+00:00"
        builder._process_concept_file(concept_path, build_ts)

        log = db_conn.execute(
            "SELECT build_type, artifact_path, artifact_kind, action "
            "FROM build_log WHERE artifact_path = '.lexibrary/concepts/Authentication.md'"
        ).fetchone()
        assert log is not None
        assert log[0] == "full"
        assert log[2] == "concept"
        assert log[3] == "created"

    def test_failed_parse_logged(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """A malformed concept file results in a 'failed' build_log entry."""
        malformed = "# No frontmatter here\nJust a heading.\n"
        concept_path = _create_concept_file(tmp_path, content=malformed)
        builder = IndexBuilder(db_conn, tmp_path)
        build_ts = "2025-06-15T12:00:00+00:00"
        builder._process_concept_file(concept_path, build_ts)

        log = db_conn.execute(
            "SELECT action, error_message FROM build_log "
            "WHERE artifact_path = '.lexibrary/concepts/Authentication.md'"
        ).fetchone()
        assert log is not None
        assert log[0] == "failed"
        assert log[1] is not None
        assert "Failed to parse" in log[1]

    def test_alias_collision_first_writer_wins(
        self, db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """When two concepts define the same alias, the first processed wins.

        Concepts are processed in sorted path order, so AuthService.md
        (alphabetically before Authentication.md) gets the 'auth' alias.
        Authentication.md's duplicate 'auth' alias is skipped with a warning.
        """
        _create_concept_file(tmp_path, "Authentication.md", _SAMPLE_CONCEPT_FILE)
        _create_concept_file(tmp_path, "AuthService.md", _SAMPLE_CONCEPT_ALIAS_COLLISION)

        builder = IndexBuilder(db_conn, tmp_path)
        build_ts = "2025-06-15T12:00:00+00:00"

        # Process in sorted order (AuthService before Authentication)
        for concept in builder._scan_concept_files():
            builder._process_concept_file(concept, build_ts)

        # 'auth' alias should belong to AuthService (first alphabetically)
        alias_row = db_conn.execute(
            "SELECT a.path FROM aliases al "
            "JOIN artifacts a ON al.artifact_id = a.id "
            "WHERE al.alias = 'auth'"
        ).fetchone()
        assert alias_row is not None
        assert alias_row[0] == ".lexibrary/concepts/AuthService.md"

        # There should be only one 'auth' alias row
        auth_count = db_conn.execute(
            "SELECT COUNT(*) FROM aliases WHERE alias = 'auth' COLLATE NOCASE"
        ).fetchone()[0]
        assert auth_count == 1

    def test_alias_collision_case_insensitive(
        self, db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """Alias uniqueness is case-insensitive; 'Auth' and 'auth' collide."""
        concept_upper = """\
---
title: UpperCase
aliases:
  - Auth
tags: []
status: draft
---

Upper case alias concept.
"""
        concept_lower = """\
---
title: LowerCase
aliases:
  - auth
tags: []
status: draft
---

Lower case alias concept.
"""
        _create_concept_file(tmp_path, "LowerCase.md", concept_lower)
        _create_concept_file(tmp_path, "UpperCase.md", concept_upper)

        builder = IndexBuilder(db_conn, tmp_path)
        build_ts = "2025-06-15T12:00:00+00:00"

        for concept in builder._scan_concept_files():
            builder._process_concept_file(concept, build_ts)

        # Only one alias row should exist (case-insensitive unique)
        auth_count = db_conn.execute(
            "SELECT COUNT(*) FROM aliases WHERE alias = 'auth' COLLATE NOCASE"
        ).fetchone()[0]
        assert auth_count == 1

    def test_stub_artifact_reused(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """If a stub concept artifact was created by a design file wikilink, it is reused.

        When _process_concept_file encounters an existing stub artifact at the
        same path, it reuses its ID and updates the title/status.
        """
        builder = IndexBuilder(db_conn, tmp_path)

        # Pre-create a stub (simulating what a design file wikilink would do)
        stub_id = builder._get_or_create_artifact(
            ".lexibrary/concepts/Authentication.md", "concept", title="Authentication"
        )

        concept_path = _create_concept_file(tmp_path)
        builder._process_concept_file(concept_path, "2025-06-15T12:00:00+00:00")

        # The concept artifact should reuse the stub's ID
        concept_row = db_conn.execute(
            "SELECT id, title, status FROM artifacts "
            "WHERE path = '.lexibrary/concepts/Authentication.md'"
        ).fetchone()
        assert concept_row is not None
        assert concept_row[0] == stub_id
        assert concept_row[1] == "Authentication"
        assert concept_row[2] == "active"

        # Only one artifact row should exist for this path
        count = db_conn.execute(
            "SELECT COUNT(*) FROM artifacts WHERE path = '.lexibrary/concepts/Authentication.md'"
        ).fetchone()[0]
        assert count == 1

    def test_concept_no_aliases_or_links(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """A concept file with no aliases, wikilinks, or linked files works correctly."""
        minimal_concept = """\
---
title: SimpleConcept
aliases: []
tags: []
status: draft
---

A simple concept with no links.
"""
        concept_path = _create_concept_file(tmp_path, content=minimal_concept)
        builder = IndexBuilder(db_conn, tmp_path)
        builder._process_concept_file(concept_path, "2025-06-15T12:00:00+00:00")

        # Artifact created
        row = db_conn.execute(
            "SELECT kind FROM artifacts WHERE path = '.lexibrary/concepts/Authentication.md'"
        ).fetchone()
        assert row is not None
        assert row[0] == "concept"

        # No aliases, links, or tags
        alias_count = db_conn.execute("SELECT COUNT(*) FROM aliases").fetchone()[0]
        link_count = db_conn.execute("SELECT COUNT(*) FROM links").fetchone()[0]
        tag_count = db_conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
        assert alias_count == 0
        assert link_count == 0
        assert tag_count == 0

    def test_multiple_concepts_processed(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """Multiple concept files can be processed sequentially without conflict."""
        _create_concept_file(tmp_path, "Authentication.md", _SAMPLE_CONCEPT_FILE)
        _create_concept_file(tmp_path, "Authorization.md", _SAMPLE_CONCEPT_FILE_B)

        builder = IndexBuilder(db_conn, tmp_path)
        build_ts = "2025-06-15T12:00:00+00:00"

        for concept in builder._scan_concept_files():
            builder._process_concept_file(concept, build_ts)

        concept_count = db_conn.execute(
            "SELECT COUNT(*) FROM artifacts WHERE kind = 'concept'"
        ).fetchone()[0]
        # 2 real concepts + stub for SessionManagement (from Authentication body)
        assert concept_count >= 2

        # Both should have aliases
        alias_count = db_conn.execute("SELECT COUNT(*) FROM aliases").fetchone()[0]
        # auth, authn from Authentication + authz from Authorization = 3
        assert alias_count == 3

        # Cross-referencing wikilinks should work
        wikilink_count = db_conn.execute(
            "SELECT COUNT(*) FROM links WHERE link_type = 'wikilink'"
        ).fetchone()[0]
        # Authentication -> Authorization, SessionManagement
        # Authorization -> Authentication
        assert wikilink_count == 3


# ---------------------------------------------------------------------------
# Helpers for Stack post integration tests
# ---------------------------------------------------------------------------

_SAMPLE_STACK_POST = """\
---
id: ST-001
title: How to configure JWT token expiry
tags:
  - auth
  - jwt
status: resolved
created: 2025-06-01
author: dev-user
refs:
  concepts:
    - Authentication
    - Security
  files:
    - src/auth/login.py
    - src/auth/tokens.py
---

## Problem

We need to configure JWT token expiry for our authentication system. The default
expiry is too long and poses a security risk.

### Evidence

- Tokens currently expire after 24 hours
- Industry standard is 15-30 minutes for access tokens

## Answers

### A1

**Date:** 2025-06-02 | **Author:** senior-dev | **Votes:** 3 | **Accepted:** true

Set the `TOKEN_EXPIRY` config value in `config.yaml` to the desired duration.
Use short-lived access tokens (15 min) with refresh tokens (7 days).

#### Comments

- Good answer, thanks!

### A2

**Date:** 2025-06-03 | **Author:** another-dev | **Votes:** 1

You can also use environment variables to override the config value
for different deployment environments.
"""

_SAMPLE_STACK_POST_MINIMAL = """\
---
id: ST-002
title: Why does the linter fail on type hints
tags:
  - tooling
status: open
created: 2025-06-10
author: new-dev
---

## Problem

The linter reports errors on perfectly valid type hints using PEP 604 syntax.
"""

_SAMPLE_STACK_POST_NO_REFS = """\
---
id: ST-003
title: Stack post with no refs
tags:
  - general
status: open
created: 2025-06-15
author: someone
---

## Problem

A question with no file or concept references.
"""


def _create_stack_post(
    tmp_path: Path,
    filename: str = "ST-001.md",
    content: str = _SAMPLE_STACK_POST,
) -> Path:
    """Create a Stack post file under .lexibrary/stack/ and return its path."""
    stack_dir = tmp_path / ".lexibrary" / "stack"
    stack_dir.mkdir(parents=True, exist_ok=True)
    stack_path = stack_dir / filename
    stack_path.write_text(content, encoding="utf-8")
    return stack_path


# ---------------------------------------------------------------------------
# _scan_stack_posts tests
# ---------------------------------------------------------------------------


class TestScanStackPosts:
    """Tests for IndexBuilder._scan_stack_posts."""

    def test_discovers_st_files(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """Discovers all ST-*.md files under .lexibrary/stack/."""
        _create_stack_post(tmp_path, "ST-001.md")
        _create_stack_post(tmp_path, "ST-002.md", _SAMPLE_STACK_POST_MINIMAL)

        builder = IndexBuilder(db_conn, tmp_path)
        files = builder._scan_stack_posts()

        assert len(files) == 2
        names = [f.name for f in files]
        assert "ST-001.md" in names
        assert "ST-002.md" in names

    def test_ignores_non_st_files(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """Files not matching the ST-*.md pattern are ignored."""
        _create_stack_post(tmp_path, "ST-001.md")
        # Create a non-matching file in the same directory
        stack_dir = tmp_path / ".lexibrary" / "stack"
        (stack_dir / "README.md").write_text("# Stack readme\n", encoding="utf-8")
        (stack_dir / "notes.txt").write_text("random notes\n", encoding="utf-8")

        builder = IndexBuilder(db_conn, tmp_path)
        files = builder._scan_stack_posts()

        assert len(files) == 1
        assert files[0].name == "ST-001.md"

    def test_empty_when_no_dir(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """Returns empty list when .lexibrary/stack/ does not exist."""
        builder = IndexBuilder(db_conn, tmp_path)
        assert builder._scan_stack_posts() == []

    def test_empty_when_no_st_files(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """Returns empty list when .lexibrary/stack/ exists but has no ST-*.md files."""
        (tmp_path / ".lexibrary" / "stack").mkdir(parents=True)
        builder = IndexBuilder(db_conn, tmp_path)
        assert builder._scan_stack_posts() == []

    def test_sorted_order(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """Results are sorted by path for deterministic processing order."""
        _create_stack_post(tmp_path, "ST-010.md", _SAMPLE_STACK_POST_MINIMAL)
        _create_stack_post(tmp_path, "ST-001.md")

        builder = IndexBuilder(db_conn, tmp_path)
        files = builder._scan_stack_posts()

        assert files[0].name == "ST-001.md"
        assert files[1].name == "ST-010.md"


# ---------------------------------------------------------------------------
# _process_stack_post integration tests
# ---------------------------------------------------------------------------


class TestProcessStackPost:
    """Integration tests for IndexBuilder._process_stack_post.

    Each test creates a real Stack post file in tmp_path, runs the processing
    method, and verifies the database contents.
    """

    def test_creates_stack_artifact(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """Processing a Stack post creates a stack artifact with correct metadata."""
        stack_path = _create_stack_post(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        build_ts = "2025-06-15T12:00:00+00:00"

        builder._process_stack_post(stack_path, build_ts)

        row = db_conn.execute(
            "SELECT path, kind, title, status FROM artifacts "
            "WHERE path = '.lexibrary/stack/ST-001.md'"
        ).fetchone()
        assert row is not None
        assert row[0] == ".lexibrary/stack/ST-001.md"
        assert row[1] == "stack"
        assert row[2] == "How to configure JWT token expiry"
        assert row[3] == "resolved"

    def test_stack_file_ref_links_created(
        self, db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """File references in the Stack post create stack_file_ref links."""
        stack_path = _create_stack_post(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        builder._process_stack_post(stack_path, "2025-06-15T12:00:00+00:00")

        file_refs = db_conn.execute(
            "SELECT tgt.path FROM links l "
            "JOIN artifacts tgt ON l.target_id = tgt.id "
            "WHERE l.link_type = 'stack_file_ref'"
        ).fetchall()
        paths = sorted(r[0] for r in file_refs)
        assert "src/auth/login.py" in paths
        assert "src/auth/tokens.py" in paths

    def test_stack_concept_ref_links_created(
        self, db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """Concept references in the Stack post create stack_concept_ref links."""
        stack_path = _create_stack_post(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        builder._process_stack_post(stack_path, "2025-06-15T12:00:00+00:00")

        concept_refs = db_conn.execute(
            "SELECT tgt.path FROM links l "
            "JOIN artifacts tgt ON l.target_id = tgt.id "
            "WHERE l.link_type = 'stack_concept_ref'"
        ).fetchall()
        paths = sorted(r[0] for r in concept_refs)
        assert ".lexibrary/concepts/Authentication.md" in paths
        assert ".lexibrary/concepts/Security.md" in paths

    def test_stub_artifacts_created_for_refs(
        self, db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """Concept and source artifacts are created as stubs when referenced."""
        stack_path = _create_stack_post(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        builder._process_stack_post(stack_path, "2025-06-15T12:00:00+00:00")

        # Check stub concept artifact
        concept_row = db_conn.execute(
            "SELECT kind, title FROM artifacts WHERE path = '.lexibrary/concepts/Authentication.md'"
        ).fetchone()
        assert concept_row is not None
        assert concept_row[0] == "concept"
        assert concept_row[1] == "Authentication"

        # Check stub source artifact
        source_row = db_conn.execute(
            "SELECT kind FROM artifacts WHERE path = 'src/auth/login.py'"
        ).fetchone()
        assert source_row is not None
        assert source_row[0] == "source"

    def test_tags_inserted(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """Tags from the Stack post frontmatter are inserted into the tags table."""
        stack_path = _create_stack_post(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        builder._process_stack_post(stack_path, "2025-06-15T12:00:00+00:00")

        tags = db_conn.execute(
            "SELECT t.tag FROM tags t "
            "JOIN artifacts a ON t.artifact_id = a.id "
            "WHERE a.path = '.lexibrary/stack/ST-001.md'"
        ).fetchall()
        tag_names = sorted(r[0] for r in tags)
        assert tag_names == ["auth", "jwt"]

    def test_fts_row_inserted_with_problem_and_answers(
        self, db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """FTS row contains the problem text concatenated with all answer bodies."""
        stack_path = _create_stack_post(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        builder._process_stack_post(stack_path, "2025-06-15T12:00:00+00:00")

        stack_id = db_conn.execute(
            "SELECT id FROM artifacts WHERE path = '.lexibrary/stack/ST-001.md'"
        ).fetchone()[0]
        fts_row = db_conn.execute(
            "SELECT title, body FROM artifacts_fts WHERE rowid = ?",
            (stack_id,),
        ).fetchone()
        assert fts_row is not None
        assert fts_row[0] == "How to configure JWT token expiry"
        # Body should contain the problem text
        assert "configure JWT token expiry" in fts_row[1]
        # Body should contain answer content
        assert "TOKEN_EXPIRY" in fts_row[1]
        assert "environment variables" in fts_row[1]

    def test_fts_body_problem_only(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """FTS body contains only problem text when there are no answers."""
        stack_path = _create_stack_post(tmp_path, "ST-002.md", _SAMPLE_STACK_POST_MINIMAL)
        builder = IndexBuilder(db_conn, tmp_path)
        builder._process_stack_post(stack_path, "2025-06-15T12:00:00+00:00")

        stack_id = db_conn.execute(
            "SELECT id FROM artifacts WHERE path = '.lexibrary/stack/ST-002.md'"
        ).fetchone()[0]
        fts_row = db_conn.execute(
            "SELECT title, body FROM artifacts_fts WHERE rowid = ?",
            (stack_id,),
        ).fetchone()
        assert fts_row is not None
        assert fts_row[0] == "Why does the linter fail on type hints"
        assert "PEP 604" in fts_row[1]

    def test_build_log_entry_created(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """A build_log entry is created for a successfully processed Stack post."""
        stack_path = _create_stack_post(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        build_ts = "2025-06-15T12:00:00+00:00"
        builder._process_stack_post(stack_path, build_ts)

        log = db_conn.execute(
            "SELECT build_type, artifact_path, artifact_kind, action "
            "FROM build_log WHERE artifact_path = '.lexibrary/stack/ST-001.md'"
        ).fetchone()
        assert log is not None
        assert log[0] == "full"
        assert log[2] == "stack"
        assert log[3] == "created"

    def test_failed_parse_logged(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """A malformed Stack post results in a 'failed' build_log entry."""
        malformed = "# No frontmatter here\nJust a heading.\n"
        stack_path = _create_stack_post(tmp_path, content=malformed)
        builder = IndexBuilder(db_conn, tmp_path)
        build_ts = "2025-06-15T12:00:00+00:00"
        builder._process_stack_post(stack_path, build_ts)

        log = db_conn.execute(
            "SELECT action, error_message FROM build_log "
            "WHERE artifact_path = '.lexibrary/stack/ST-001.md'"
        ).fetchone()
        assert log is not None
        assert log[0] == "failed"
        assert log[1] is not None
        assert "Failed to parse" in log[1]

    def test_no_refs_no_links(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """A Stack post with no file or concept refs creates no such links."""
        stack_path = _create_stack_post(tmp_path, "ST-003.md", _SAMPLE_STACK_POST_NO_REFS)
        builder = IndexBuilder(db_conn, tmp_path)
        builder._process_stack_post(stack_path, "2025-06-15T12:00:00+00:00")

        file_refs = db_conn.execute(
            "SELECT COUNT(*) FROM links WHERE link_type = 'stack_file_ref'"
        ).fetchone()[0]
        concept_refs = db_conn.execute(
            "SELECT COUNT(*) FROM links WHERE link_type = 'stack_concept_ref'"
        ).fetchone()[0]
        assert file_refs == 0
        assert concept_refs == 0

    def test_stub_artifact_reused(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """If a stub stack artifact was created by a design file ref, it is reused.

        When _process_stack_post encounters an existing stub artifact at the
        same path, it reuses its ID and updates the title/status.
        """
        builder = IndexBuilder(db_conn, tmp_path)

        # Pre-create a stub (simulating what a design file stack ref would do)
        stub_id = builder._get_or_create_artifact(
            ".lexibrary/stack/ST-001.md", "stack", title="ST-001"
        )

        stack_path = _create_stack_post(tmp_path)
        builder._process_stack_post(stack_path, "2025-06-15T12:00:00+00:00")

        # The stack artifact should reuse the stub's ID
        stack_row = db_conn.execute(
            "SELECT id, title, status FROM artifacts WHERE path = '.lexibrary/stack/ST-001.md'"
        ).fetchone()
        assert stack_row is not None
        assert stack_row[0] == stub_id
        assert stack_row[1] == "How to configure JWT token expiry"
        assert stack_row[2] == "resolved"

        # Only one artifact row should exist for this path
        count = db_conn.execute(
            "SELECT COUNT(*) FROM artifacts WHERE path = '.lexibrary/stack/ST-001.md'"
        ).fetchone()[0]
        assert count == 1

    def test_multiple_stack_posts_processed(
        self, db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """Multiple Stack posts can be processed sequentially without conflict."""
        _create_stack_post(tmp_path, "ST-001.md", _SAMPLE_STACK_POST)
        _create_stack_post(tmp_path, "ST-002.md", _SAMPLE_STACK_POST_MINIMAL)

        builder = IndexBuilder(db_conn, tmp_path)
        build_ts = "2025-06-15T12:00:00+00:00"

        for sp in builder._scan_stack_posts():
            builder._process_stack_post(sp, build_ts)

        stack_count = db_conn.execute(
            "SELECT COUNT(*) FROM artifacts WHERE kind = 'stack'"
        ).fetchone()[0]
        assert stack_count == 2

        # Both should have tags
        tag_count = db_conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
        # ST-001: auth, jwt (2) + ST-002: tooling (1) = 3
        assert tag_count == 3

        # Only ST-001 has file and concept refs
        file_ref_count = db_conn.execute(
            "SELECT COUNT(*) FROM links WHERE link_type = 'stack_file_ref'"
        ).fetchone()[0]
        concept_ref_count = db_conn.execute(
            "SELECT COUNT(*) FROM links WHERE link_type = 'stack_concept_ref'"
        ).fetchone()[0]
        assert file_ref_count == 2
        assert concept_ref_count == 2


# ---------------------------------------------------------------------------
# Helpers for .aindex convention integration tests
# ---------------------------------------------------------------------------

_SAMPLE_AINDEX_FILE = """\
# src/auth

Authentication and authorization module for the application.

## Child Map

| Name | Type | Description |
|------|------|-------------|
| `login.py` | file | Handles user login |
| `middleware.py` | file | Auth middleware |
| `permissions/` | dir | Permission checks |

## Local Conventions

- All endpoints must use [[Authentication]] middleware before processing requests
- Password hashing must use bcrypt with a minimum cost factor of 12

<!-- lexibrary:meta source="src/auth" source_hash="abc123"
generated="2025-06-15T12:00:00" generator="lexibrary-test" -->
"""

_SAMPLE_AINDEX_WITH_WIKILINKS = """\
# src/api

API endpoint module.

## Child Map

| Name | Type | Description |
|------|------|-------------|
| `routes.py` | file | Route definitions |

## Local Conventions

- Use [[Logging]] for all request/response tracing
- All responses must follow [[APIStandards]] format
- Rate limiting via [[Security]] middleware required

<!-- lexibrary:meta source="src/api" source_hash="def456"
generated="2025-06-15T12:00:00" generator="lexibrary-test" -->
"""

_SAMPLE_AINDEX_NO_CONVENTIONS = """\
# src/utils

Utility functions.

## Child Map

| Name | Type | Description |
|------|------|-------------|
| `hashing.py` | file | Hash utilities |

## Local Conventions

(none)

<!-- lexibrary:meta source="src/utils" source_hash="xyz789"
generated="2025-06-15T12:00:00" generator="lexibrary-test" -->
"""

_SAMPLE_AINDEX_EMPTY_CONVENTIONS = """\
# src/config

Configuration module.

## Child Map

| Name | Type | Description |
|------|------|-------------|
| `schema.py` | file | Config schema |

<!-- lexibrary:meta source="src/config" source_hash="uvw012"
generated="2025-06-15T12:00:00" generator="lexibrary-test" -->
"""


def _create_aindex_file(
    tmp_path: Path,
    relpath: str = ".lexibrary/src/auth/.aindex",
    content: str = _SAMPLE_AINDEX_FILE,
) -> Path:
    """Create a .aindex file under .lexibrary/ and return its path."""
    aindex_path = tmp_path / relpath
    aindex_path.parent.mkdir(parents=True, exist_ok=True)
    aindex_path.write_text(content, encoding="utf-8")
    return aindex_path


# ---------------------------------------------------------------------------
# _scan_aindex_files tests
# ---------------------------------------------------------------------------


class TestScanAindexFiles:
    """Tests for IndexBuilder._scan_aindex_files."""

    def test_discovers_aindex_files(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """Discovers all .aindex files under .lexibrary/."""
        _create_aindex_file(tmp_path, ".lexibrary/src/auth/.aindex")
        _create_aindex_file(tmp_path, ".lexibrary/src/api/.aindex", _SAMPLE_AINDEX_WITH_WIKILINKS)

        builder = IndexBuilder(db_conn, tmp_path)
        files = builder._scan_aindex_files()

        assert len(files) == 2
        names = [f.parent.name for f in files]
        assert "auth" in names
        assert "api" in names

    def test_empty_when_no_dir(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """Returns empty list when .lexibrary/ does not exist."""
        builder = IndexBuilder(db_conn, tmp_path)
        assert builder._scan_aindex_files() == []

    def test_empty_when_no_aindex_files(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """Returns empty list when .lexibrary/ exists but has no .aindex files."""
        (tmp_path / ".lexibrary" / "src").mkdir(parents=True)
        builder = IndexBuilder(db_conn, tmp_path)
        assert builder._scan_aindex_files() == []

    def test_sorted_order(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """Results are sorted by path for deterministic processing order."""
        _create_aindex_file(tmp_path, ".lexibrary/src/zebra/.aindex", _SAMPLE_AINDEX_NO_CONVENTIONS)
        _create_aindex_file(tmp_path, ".lexibrary/src/alpha/.aindex", _SAMPLE_AINDEX_FILE)

        builder = IndexBuilder(db_conn, tmp_path)
        files = builder._scan_aindex_files()

        assert files[0].parent.name == "alpha"
        assert files[1].parent.name == "zebra"

    def test_nested_aindex_files(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """Discovers .aindex files in deeply nested directories."""
        _create_aindex_file(
            tmp_path, ".lexibrary/src/auth/permissions/.aindex", _SAMPLE_AINDEX_FILE
        )
        _create_aindex_file(tmp_path, ".lexibrary/src/auth/.aindex")

        builder = IndexBuilder(db_conn, tmp_path)
        files = builder._scan_aindex_files()

        assert len(files) == 2


# ---------------------------------------------------------------------------
# _process_aindex_conventions integration tests
# ---------------------------------------------------------------------------


class TestProcessAindexConventions:
    """Integration tests for IndexBuilder._process_aindex_conventions.

    Each test creates a real .aindex file in tmp_path, runs the processing
    method, and verifies the database contents.
    """

    def test_creates_convention_artifacts(
        self, db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """Processing an .aindex file creates convention artifacts with synthetic paths."""
        aindex_path = _create_aindex_file(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        build_ts = "2025-06-15T12:00:00+00:00"

        builder._process_aindex_conventions(aindex_path, build_ts)

        # Two conventions should be created
        conventions = db_conn.execute(
            "SELECT path, kind, title FROM artifacts WHERE kind = 'convention' ORDER BY path"
        ).fetchall()
        assert len(conventions) == 2

        # Check synthetic paths
        assert conventions[0][0] == "src/auth::convention::0"
        assert conventions[1][0] == "src/auth::convention::1"

        # Check kind
        assert conventions[0][1] == "convention"
        assert conventions[1][1] == "convention"

    def test_synthetic_path_format(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """Synthetic paths follow the {directory_path}::convention::{ordinal} format."""
        aindex_path = _create_aindex_file(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        builder._process_aindex_conventions(aindex_path, "2025-06-15T12:00:00+00:00")

        paths = db_conn.execute(
            "SELECT path FROM artifacts WHERE kind = 'convention' ORDER BY path"
        ).fetchall()
        assert paths[0][0] == "src/auth::convention::0"
        assert paths[1][0] == "src/auth::convention::1"

    def test_convention_title_truncated(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """Convention title is the first 120 characters of the convention text."""
        aindex_path = _create_aindex_file(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        builder._process_aindex_conventions(aindex_path, "2025-06-15T12:00:00+00:00")

        row = db_conn.execute(
            "SELECT title FROM artifacts WHERE path = 'src/auth::convention::0'"
        ).fetchone()
        assert row is not None
        # Title should be the first convention text
        assert "All endpoints must use" in row[0]

    def test_conventions_table_populated(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """Conventions table rows are inserted with correct directory_path, ordinal, and body."""
        aindex_path = _create_aindex_file(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        builder._process_aindex_conventions(aindex_path, "2025-06-15T12:00:00+00:00")

        rows = db_conn.execute(
            "SELECT directory_path, ordinal, body FROM conventions ORDER BY ordinal"
        ).fetchall()
        assert len(rows) == 2

        assert rows[0][0] == "src/auth"
        assert rows[0][1] == 0
        assert "Authentication" in rows[0][2]

        assert rows[1][0] == "src/auth"
        assert rows[1][1] == 1
        assert "bcrypt" in rows[1][2]

    def test_wikilink_extraction_from_conventions(
        self, db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """Wikilinks in convention text create convention_concept_ref links."""
        aindex_path = _create_aindex_file(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        builder._process_aindex_conventions(aindex_path, "2025-06-15T12:00:00+00:00")

        # The first convention contains [[Authentication]]
        links = db_conn.execute(
            "SELECT tgt.path FROM links l "
            "JOIN artifacts tgt ON l.target_id = tgt.id "
            "WHERE l.link_type = 'convention_concept_ref'"
        ).fetchall()
        paths = [r[0] for r in links]
        assert ".lexibrary/concepts/Authentication.md" in paths

    def test_multiple_wikilinks_in_convention(
        self, db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """Multiple wikilinks in .aindex conventions create correct concept ref links."""
        aindex_path = _create_aindex_file(
            tmp_path, ".lexibrary/src/api/.aindex", _SAMPLE_AINDEX_WITH_WIKILINKS
        )
        builder = IndexBuilder(db_conn, tmp_path)
        builder._process_aindex_conventions(aindex_path, "2025-06-15T12:00:00+00:00")

        links = db_conn.execute(
            "SELECT tgt.path FROM links l "
            "JOIN artifacts tgt ON l.target_id = tgt.id "
            "WHERE l.link_type = 'convention_concept_ref'"
        ).fetchall()
        paths = sorted(r[0] for r in links)
        assert ".lexibrary/concepts/APIStandards.md" in paths
        assert ".lexibrary/concepts/Logging.md" in paths
        assert ".lexibrary/concepts/Security.md" in paths

    def test_stub_concept_artifacts_created(
        self, db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """Wikilinks to concepts that have no file create stub concept artifacts."""
        aindex_path = _create_aindex_file(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        builder._process_aindex_conventions(aindex_path, "2025-06-15T12:00:00+00:00")

        concept_row = db_conn.execute(
            "SELECT kind, title FROM artifacts WHERE path = '.lexibrary/concepts/Authentication.md'"
        ).fetchone()
        assert concept_row is not None
        assert concept_row[0] == "concept"
        assert concept_row[1] == "Authentication"

    def test_fts_rows_inserted(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """FTS rows are inserted for each convention with the full convention text as body."""
        aindex_path = _create_aindex_file(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        builder._process_aindex_conventions(aindex_path, "2025-06-15T12:00:00+00:00")

        conv_0_id = db_conn.execute(
            "SELECT id FROM artifacts WHERE path = 'src/auth::convention::0'"
        ).fetchone()[0]
        fts_row = db_conn.execute(
            "SELECT title, body FROM artifacts_fts WHERE rowid = ?",
            (conv_0_id,),
        ).fetchone()
        assert fts_row is not None
        assert "endpoints" in fts_row[0]
        assert "Authentication" in fts_row[1]

        conv_1_id = db_conn.execute(
            "SELECT id FROM artifacts WHERE path = 'src/auth::convention::1'"
        ).fetchone()[0]
        fts_row_1 = db_conn.execute(
            "SELECT title, body FROM artifacts_fts WHERE rowid = ?",
            (conv_1_id,),
        ).fetchone()
        assert fts_row_1 is not None
        assert "bcrypt" in fts_row_1[1]

    def test_build_log_entries_created(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """Build log entries are created for each convention processed."""
        aindex_path = _create_aindex_file(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        build_ts = "2025-06-15T12:00:00+00:00"
        builder._process_aindex_conventions(aindex_path, build_ts)

        logs = db_conn.execute(
            "SELECT build_type, artifact_path, artifact_kind, action "
            "FROM build_log WHERE artifact_kind = 'convention' ORDER BY artifact_path"
        ).fetchall()
        assert len(logs) == 2
        assert logs[0][0] == "full"
        assert logs[0][1] == "src/auth::convention::0"
        assert logs[0][2] == "convention"
        assert logs[0][3] == "created"
        assert logs[1][1] == "src/auth::convention::1"

    def test_no_conventions_no_artifacts(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """An .aindex file with no local conventions creates no convention artifacts."""
        aindex_path = _create_aindex_file(
            tmp_path, ".lexibrary/src/utils/.aindex", _SAMPLE_AINDEX_NO_CONVENTIONS
        )
        builder = IndexBuilder(db_conn, tmp_path)
        builder._process_aindex_conventions(aindex_path, "2025-06-15T12:00:00+00:00")

        conv_count = db_conn.execute(
            "SELECT COUNT(*) FROM artifacts WHERE kind = 'convention'"
        ).fetchone()[0]
        assert conv_count == 0

        conv_table_count = db_conn.execute("SELECT COUNT(*) FROM conventions").fetchone()[0]
        assert conv_table_count == 0

    def test_empty_conventions_section_no_artifacts(
        self, db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """An .aindex file with missing conventions section creates no convention artifacts."""
        aindex_path = _create_aindex_file(
            tmp_path, ".lexibrary/src/config/.aindex", _SAMPLE_AINDEX_EMPTY_CONVENTIONS
        )
        builder = IndexBuilder(db_conn, tmp_path)
        builder._process_aindex_conventions(aindex_path, "2025-06-15T12:00:00+00:00")

        conv_count = db_conn.execute(
            "SELECT COUNT(*) FROM artifacts WHERE kind = 'convention'"
        ).fetchone()[0]
        assert conv_count == 0

    def test_failed_parse_logged(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """A malformed .aindex file results in a 'failed' build_log entry."""
        malformed = "No proper format here.\n"
        aindex_path = _create_aindex_file(tmp_path, content=malformed)
        builder = IndexBuilder(db_conn, tmp_path)
        build_ts = "2025-06-15T12:00:00+00:00"
        builder._process_aindex_conventions(aindex_path, build_ts)

        log = db_conn.execute(
            "SELECT action, error_message FROM build_log WHERE artifact_kind = 'convention'"
        ).fetchone()
        assert log is not None
        assert log[0] == "failed"
        assert log[1] is not None
        assert "Failed to parse" in log[1]

    def test_convention_no_wikilinks(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """A convention with no wikilinks creates no convention_concept_ref links."""
        aindex_content = """\
# src/simple

Simple module.

## Child Map

| Name | Type | Description |
|------|------|-------------|
| `main.py` | file | Entry point |

## Local Conventions

- Use consistent indentation (4 spaces)
- All functions must have docstrings

<!-- lexibrary:meta source="src/simple" source_hash="aaa111"
generated="2025-06-15T12:00:00" generator="lexibrary-test" -->
"""
        aindex_path = _create_aindex_file(tmp_path, ".lexibrary/src/simple/.aindex", aindex_content)
        builder = IndexBuilder(db_conn, tmp_path)
        builder._process_aindex_conventions(aindex_path, "2025-06-15T12:00:00+00:00")

        # Two convention artifacts but no links
        conv_count = db_conn.execute(
            "SELECT COUNT(*) FROM artifacts WHERE kind = 'convention'"
        ).fetchone()[0]
        assert conv_count == 2

        link_count = db_conn.execute(
            "SELECT COUNT(*) FROM links WHERE link_type = 'convention_concept_ref'"
        ).fetchone()[0]
        assert link_count == 0

    def test_multiple_aindex_files_processed(
        self, db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """Multiple .aindex files can be processed sequentially without conflict."""
        _create_aindex_file(tmp_path, ".lexibrary/src/auth/.aindex", _SAMPLE_AINDEX_FILE)
        _create_aindex_file(tmp_path, ".lexibrary/src/api/.aindex", _SAMPLE_AINDEX_WITH_WIKILINKS)

        builder = IndexBuilder(db_conn, tmp_path)
        build_ts = "2025-06-15T12:00:00+00:00"

        for aindex in builder._scan_aindex_files():
            builder._process_aindex_conventions(aindex, build_ts)

        conv_count = db_conn.execute(
            "SELECT COUNT(*) FROM artifacts WHERE kind = 'convention'"
        ).fetchone()[0]
        # src/auth: 2 conventions + src/api: 3 conventions = 5
        assert conv_count == 5

        # Conventions table should have all entries
        table_count = db_conn.execute("SELECT COUNT(*) FROM conventions").fetchone()[0]
        assert table_count == 5

        # Convention concept refs: src/auth has 1 (Authentication), src/api has 3
        link_count = db_conn.execute(
            "SELECT COUNT(*) FROM links WHERE link_type = 'convention_concept_ref'"
        ).fetchone()[0]
        assert link_count == 4

    def test_convention_title_long_text_truncated(
        self, db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """Convention titles longer than 120 characters are truncated."""
        long_convention = "A" * 200
        aindex_content = f"""\
# src/long

Long convention module.

## Child Map

(none)

## Local Conventions

- {long_convention}

<!-- lexibrary:meta source="src/long" source_hash="bbb222"
generated="2025-06-15T12:00:00" generator="lexibrary-test" -->
"""
        aindex_path = _create_aindex_file(tmp_path, ".lexibrary/src/long/.aindex", aindex_content)
        builder = IndexBuilder(db_conn, tmp_path)
        builder._process_aindex_conventions(aindex_path, "2025-06-15T12:00:00+00:00")

        row = db_conn.execute(
            "SELECT title FROM artifacts WHERE path = 'src/long::convention::0'"
        ).fetchone()
        assert row is not None
        assert len(row[0]) == 120


# ---------------------------------------------------------------------------
# Helper for full_build end-to-end integration test
# ---------------------------------------------------------------------------


def _create_full_project_tree(tmp_path: Path) -> None:
    """Create a sample project tree with design files, concepts, Stack posts, and .aindex files.

    This sets up a realistic project with cross-references between all artifact
    types to exercise the full_build() pipeline end-to-end.
    """
    # Source file
    source_dir = tmp_path / "src" / "auth"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "login.py").write_text(
        "from __future__ import annotations\n\ndef login(username: str, password: str) -> bool:\n"
        "    return True\n",
        encoding="utf-8",
    )

    # Design file for the source
    design_dir = tmp_path / ".lexibrary" / "src" / "auth"
    design_dir.mkdir(parents=True, exist_ok=True)
    (design_dir / "login.py.md").write_text(
        _SAMPLE_DESIGN_FILE,
        encoding="utf-8",
    )

    # Concept files
    concept_dir = tmp_path / ".lexibrary" / "concepts"
    concept_dir.mkdir(parents=True, exist_ok=True)
    (concept_dir / "Authentication.md").write_text(
        _SAMPLE_CONCEPT_FILE,
        encoding="utf-8",
    )
    (concept_dir / "Authorization.md").write_text(
        _SAMPLE_CONCEPT_FILE_B,
        encoding="utf-8",
    )

    # Stack post
    stack_dir = tmp_path / ".lexibrary" / "stack"
    stack_dir.mkdir(parents=True, exist_ok=True)
    (stack_dir / "ST-001.md").write_text(
        _SAMPLE_STACK_POST,
        encoding="utf-8",
    )

    # .aindex file with conventions
    (design_dir / ".aindex").write_text(
        _SAMPLE_AINDEX_FILE,
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# full_build end-to-end integration tests (task group 7)
# ---------------------------------------------------------------------------


class TestFullBuild:
    """End-to-end integration tests for IndexBuilder.full_build().

    Each test creates a full sample project tree and exercises the complete
    build pipeline, verifying orchestration, transaction semantics, timing,
    error handling, and correctness of the resulting database.
    """

    def test_full_build_populates_all_artifact_types(
        self, db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """full_build processes design files, concepts, Stack posts, and .aindex conventions."""
        _create_full_project_tree(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        result = builder.full_build()

        # Should have no errors
        assert result.errors == []
        assert result.build_type == "full"

        # Check artifact types are all present
        kinds = db_conn.execute("SELECT DISTINCT kind FROM artifacts ORDER BY kind").fetchall()
        kind_set = {row[0] for row in kinds}
        assert "source" in kind_set
        assert "design" in kind_set
        assert "concept" in kind_set
        assert "stack" in kind_set
        assert "convention" in kind_set

    def test_full_build_returns_correct_counts(
        self, db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """BuildResult artifact_count and link_count match the database."""
        _create_full_project_tree(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        result = builder.full_build()

        actual_artifact_count = db_conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
        actual_link_count = db_conn.execute("SELECT COUNT(*) FROM links").fetchone()[0]

        assert result.artifact_count == actual_artifact_count
        assert result.link_count == actual_link_count
        assert result.artifact_count > 0
        assert result.link_count > 0

    def test_full_build_duration_is_positive(
        self, db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """BuildResult.duration_ms is a positive integer reflecting elapsed time."""
        _create_full_project_tree(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        result = builder.full_build()

        assert result.duration_ms >= 0

    def test_full_build_updates_meta(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """Meta table is updated with correct counts, builder ID, and build timestamp."""
        _create_full_project_tree(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        result = builder.full_build()

        def meta_val(key: str) -> str | None:
            row = db_conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
            return row[0] if row else None

        assert meta_val("builder") == _BUILDER_ID
        assert meta_val("built_at") is not None
        assert meta_val("artifact_count") == str(result.artifact_count)
        assert meta_val("link_count") == str(result.link_count)

    def test_full_build_creates_links_between_artifact_types(
        self, db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """Cross-artifact links are created: design_source, wikilink, stack/convention refs."""
        _create_full_project_tree(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        builder.full_build()

        link_types = db_conn.execute(
            "SELECT DISTINCT link_type FROM links ORDER BY link_type"
        ).fetchall()
        link_type_set = {row[0] for row in link_types}

        assert "design_source" in link_type_set
        assert "wikilink" in link_type_set
        assert "design_stack_ref" in link_type_set
        assert "convention_concept_ref" in link_type_set

    def test_full_build_populates_fts(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """FTS rows are inserted for searchable artifact types."""
        _create_full_project_tree(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        builder.full_build()

        fts_count = db_conn.execute("SELECT COUNT(*) FROM artifacts_fts").fetchone()[0]
        assert fts_count > 0

        # Verify FTS search works
        search_result = db_conn.execute(
            "SELECT rowid FROM artifacts_fts WHERE artifacts_fts MATCH 'authentication'"
        ).fetchall()
        assert len(search_result) > 0

    def test_full_build_populates_aliases(
        self, db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """Aliases from concept files are populated in the aliases table."""
        _create_full_project_tree(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        builder.full_build()

        alias_count = db_conn.execute("SELECT COUNT(*) FROM aliases").fetchone()[0]
        assert alias_count > 0

        # 'auth' and 'authn' from Authentication, 'authz' from Authorization
        aliases = db_conn.execute("SELECT alias FROM aliases ORDER BY alias").fetchall()
        alias_names = [r[0] for r in aliases]
        assert "auth" in alias_names
        assert "authn" in alias_names
        assert "authz" in alias_names

    def test_full_build_populates_conventions_table(
        self, db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """Convention rows are inserted into the conventions table."""
        _create_full_project_tree(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        builder.full_build()

        conv_count = db_conn.execute("SELECT COUNT(*) FROM conventions").fetchone()[0]
        assert conv_count > 0

        # Check a convention body is populated
        conv = db_conn.execute("SELECT body FROM conventions WHERE ordinal = 0").fetchone()
        assert conv is not None
        assert len(conv[0]) > 0

    def test_full_build_populates_tags(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """Tags from design files and concept files are stored in the tags table."""
        _create_full_project_tree(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        builder.full_build()

        tag_count = db_conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
        assert tag_count > 0

        tags = db_conn.execute("SELECT DISTINCT tag FROM tags ORDER BY tag").fetchall()
        tag_names = {r[0] for r in tags}
        # Design file has tags: auth, security
        # Authentication concept has tags: security, identity
        # Authorization concept has tags: security, access-control
        # Stack post has tags: auth, jwt
        assert "auth" in tag_names
        assert "security" in tag_names

    def test_full_build_clears_previous_data(
        self, db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """Running full_build twice clears old data before rebuilding."""
        _create_full_project_tree(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)

        # First build
        result1 = builder.full_build()
        count1 = result1.artifact_count

        # Second build (should clear and rebuild)
        result2 = builder.full_build()
        count2 = result2.artifact_count

        # Counts should be the same (no duplicate data)
        assert count1 == count2

        # No duplicate artifact paths
        paths = db_conn.execute("SELECT path FROM artifacts").fetchall()
        path_list = [r[0] for r in paths]
        assert len(path_list) == len(set(path_list)), "Duplicate artifact paths found"

    def test_full_build_creates_build_log_entries(
        self, db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """Build log entries are created for each processed artifact."""
        _create_full_project_tree(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        builder.full_build()

        log_count = db_conn.execute("SELECT COUNT(*) FROM build_log").fetchone()[0]
        assert log_count > 0

        # All entries should be build_type='full' and action='created'
        created_count = db_conn.execute(
            "SELECT COUNT(*) FROM build_log WHERE build_type = 'full' AND action = 'created'"
        ).fetchone()[0]
        assert created_count == log_count

    def test_full_build_cleans_stale_build_log(
        self, db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """Stale build log entries (>30 days old) are cleaned before the build."""
        _create_full_project_tree(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)

        # Insert a stale build log entry
        old_ts = (datetime.now(UTC) - timedelta(days=45)).isoformat()
        db_conn.execute(
            "INSERT INTO build_log (build_started, build_type, artifact_path, "
            "artifact_kind, action) VALUES (?, 'full', 'old.py', 'source', 'created')",
            (old_ts,),
        )
        db_conn.commit()

        builder.full_build()

        # The stale entry should be gone
        old_entries = db_conn.execute(
            "SELECT COUNT(*) FROM build_log WHERE artifact_path = 'old.py'"
        ).fetchone()[0]
        assert old_entries == 0

    def test_full_build_per_artifact_error_collection(
        self, db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """Per-artifact errors are collected without aborting the build.

        A malformed design file should not prevent concepts and Stack posts
        from being processed.
        """
        _create_full_project_tree(tmp_path)

        # Create an additional malformed design file that will raise an exception
        # during processing (not just fail to parse -- the parser returns None for
        # parse failures and those are handled internally by _process_design_file).
        # We use a directory where .aindex should be instead of a file to cause
        # an unhandled error in one of the scan paths.
        # Instead, let's create a concept file that's valid but whose processing
        # will succeed, and rely on the fact that a parse failure is caught by
        # the individual _process_* method and logged, not raised.
        # For the per-artifact error path, we need an exception that escapes
        # _process_*. We can do this by creating a file whose content causes
        # a non-parse error.
        malformed_design = tmp_path / ".lexibrary" / "src" / "bad" / "broken.py.md"
        malformed_design.parent.mkdir(parents=True, exist_ok=True)
        # Write malformed content that won't parse
        malformed_design.write_text("not a valid design file at all", encoding="utf-8")

        builder = IndexBuilder(db_conn, tmp_path)
        result = builder.full_build()

        # Build should still complete (not raise)
        assert result.build_type == "full"
        # We should still have artifacts from the valid files
        assert result.artifact_count > 0

        # The malformed file should show up in build_log as 'failed'
        failed_entries = db_conn.execute(
            "SELECT COUNT(*) FROM build_log WHERE action = 'failed'"
        ).fetchone()[0]
        assert failed_entries >= 1

    def test_full_build_transaction_rollback_on_critical_failure(
        self, db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """If a critical (non-per-artifact) error occurs, the transaction is rolled back.

        We simulate this by monkeypatching _update_meta to raise an exception
        after all artifacts have been inserted.
        """
        _create_full_project_tree(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)

        # Monkeypatch _update_meta to raise
        original_update_meta = builder._update_meta

        def failing_update_meta(build_started: str) -> None:
            raise RuntimeError("Simulated critical failure in _update_meta")

        builder._update_meta = failing_update_meta  # type: ignore[method-assign]

        result = builder.full_build()

        # Build should report failure
        assert len(result.errors) > 0
        assert "rolled back" in result.errors[-1].lower()
        assert result.artifact_count == 0
        assert result.link_count == 0

        # After rollback, the database should have no artifact data
        # (but schema/meta from ensure_schema is preserved since it was committed
        # before the main transaction)
        artifact_count = db_conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
        assert artifact_count == 0

        # Restore for safety
        builder._update_meta = original_update_meta  # type: ignore[method-assign]

    def test_full_build_empty_project(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """full_build on a project with no .lexibrary directory succeeds with zero counts."""
        builder = IndexBuilder(db_conn, tmp_path)
        result = builder.full_build()

        assert result.errors == []
        assert result.artifact_count == 0
        assert result.link_count == 0
        assert result.build_type == "full"
        assert result.duration_ms >= 0

    def test_full_build_schema_ensured(
        self,
        tmp_path: Path,
    ) -> None:
        """full_build ensures the schema exists even on a fresh database."""
        # Use a fresh connection WITHOUT pre-calling ensure_schema
        conn = sqlite3.connect(":memory:")
        set_pragmas(conn)
        # Do NOT call ensure_schema -- full_build should do it
        builder = IndexBuilder(conn, tmp_path)

        _create_full_project_tree(tmp_path)
        result = builder.full_build()

        # Build should succeed
        assert result.errors == []
        assert result.artifact_count > 0

        # Verify schema version is in meta
        version = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
        assert version is not None

    def test_full_build_idempotent(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """Running full_build twice produces identical database state."""
        _create_full_project_tree(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)

        result1 = builder.full_build()
        result2 = builder.full_build()

        assert result1.artifact_count == result2.artifact_count
        assert result1.link_count == result2.link_count
        assert result1.errors == result2.errors


# ---------------------------------------------------------------------------
# _classify_path tests (task 8.1)
# ---------------------------------------------------------------------------


class TestClassifyPath:
    """Tests for IndexBuilder._classify_path."""

    def test_concept_file(self, builder: IndexBuilder) -> None:
        """A path under .lexibrary/concepts/ is classified as 'concept'."""
        p = builder.project_root / ".lexibrary" / "concepts" / "Auth.md"
        assert builder._classify_path(p) == "concept"

    def test_stack_file(self, builder: IndexBuilder) -> None:
        """A path under .lexibrary/stack/ is classified as 'stack'."""
        p = builder.project_root / ".lexibrary" / "stack" / "ST-001.md"
        assert builder._classify_path(p) == "stack"

    def test_aindex_file(self, builder: IndexBuilder) -> None:
        """A .aindex file under .lexibrary/ is classified as 'aindex'."""
        p = builder.project_root / ".lexibrary" / "src" / "auth" / ".aindex"
        assert builder._classify_path(p) == "aindex"

    def test_design_file(self, builder: IndexBuilder) -> None:
        """A .md file under .lexibrary/src/ is classified as 'design'."""
        p = builder.project_root / ".lexibrary" / "src" / "auth" / "login.py.md"
        assert builder._classify_path(p) == "design"

    def test_source_file(self, builder: IndexBuilder) -> None:
        """A regular source file is classified as 'source'."""
        p = builder.project_root / "src" / "auth" / "login.py"
        assert builder._classify_path(p) == "source"

    def test_relative_concept_path(self, builder: IndexBuilder) -> None:
        """Relative concept paths are correctly classified."""
        p = Path(".lexibrary/concepts/Auth.md")
        assert builder._classify_path(p) == "concept"

    def test_relative_source_path(self, builder: IndexBuilder) -> None:
        """Relative source paths are correctly classified."""
        p = Path("src/auth/login.py")
        assert builder._classify_path(p) == "source"


# ---------------------------------------------------------------------------
# _delete_artifact_outbound tests (task 8.2)
# ---------------------------------------------------------------------------


class TestDeleteArtifactOutbound:
    """Tests for IndexBuilder._delete_artifact_outbound."""

    def test_deletes_outbound_links_and_tags(self, builder: IndexBuilder) -> None:
        """Outbound links, tags, aliases, and FTS are deleted; artifact row preserved."""
        # Set up two artifacts with links, tags, alias, and FTS
        art_id = builder._insert_artifact("src/foo.py", "concept", "Foo", None, None, None)
        target_id = builder._insert_artifact("src/bar.py", "source", None, None, None, None)
        builder._insert_link(art_id, target_id, "wikilink")
        builder._insert_tag(art_id, "security")
        builder._insert_alias(art_id, "foo-alias", "src/foo.py")
        builder._insert_fts(art_id, "Foo", "foo body text")
        builder.conn.commit()

        builder._delete_artifact_outbound(art_id)

        # Artifact row still exists
        assert builder._get_artifact_id("src/foo.py") == art_id
        # Links deleted
        assert (
            builder.conn.execute(
                "SELECT COUNT(*) FROM links WHERE source_id = ?", (art_id,)
            ).fetchone()[0]
            == 0
        )
        # Tags deleted
        assert (
            builder.conn.execute(
                "SELECT COUNT(*) FROM tags WHERE artifact_id = ?", (art_id,)
            ).fetchone()[0]
            == 0
        )
        # Aliases deleted
        assert (
            builder.conn.execute(
                "SELECT COUNT(*) FROM aliases WHERE artifact_id = ?", (art_id,)
            ).fetchone()[0]
            == 0
        )
        # FTS deleted
        assert (
            builder.conn.execute(
                "SELECT COUNT(*) FROM artifacts_fts WHERE rowid = ?", (art_id,)
            ).fetchone()[0]
            == 0
        )

    def test_preserves_inbound_links(self, builder: IndexBuilder) -> None:
        """Inbound links (where artifact is the target) are preserved."""
        source_id = builder._insert_artifact("src/a.py", "source", None, None, None, None)
        target_id = builder._insert_artifact("src/b.py", "source", None, None, None, None)
        builder._insert_link(source_id, target_id, "ast_import")
        builder.conn.commit()

        # Delete outbound for target -- the inbound link should remain
        builder._delete_artifact_outbound(target_id)

        assert (
            builder.conn.execute(
                "SELECT COUNT(*) FROM links WHERE target_id = ?", (target_id,)
            ).fetchone()[0]
            == 1
        )


# ---------------------------------------------------------------------------
# Incremental update integration tests (task 8.10)
# ---------------------------------------------------------------------------


class TestIncrementalUpdate:
    """Integration tests for the incremental update pipeline.

    Each test first runs a full_build to establish baseline data, then
    makes changes to files on disk and runs incremental_update to verify
    the index is correctly updated.
    """

    def test_modified_source_file(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """Modifying a source file re-computes its hash and re-extracts AST imports."""
        _create_full_project_tree(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        result1 = builder.full_build()
        assert result1.errors == []

        # Record the old hash
        old_hash = db_conn.execute(
            "SELECT last_hash FROM artifacts WHERE path = 'src/auth/login.py'"
        ).fetchone()[0]

        # Modify the source file
        source_file = tmp_path / "src" / "auth" / "login.py"
        source_file.write_text(
            "from __future__ import annotations\n\n"
            "def login(username: str, password: str) -> bool:\n"
            "    # Modified\n"
            "    return False\n",
            encoding="utf-8",
        )

        result2 = builder.incremental_update([Path("src/auth/login.py")])

        assert result2.errors == []
        assert result2.build_type == "incremental"
        assert result2.artifact_count > 0

        # Hash should have changed
        new_hash = db_conn.execute(
            "SELECT last_hash FROM artifacts WHERE path = 'src/auth/login.py'"
        ).fetchone()[0]
        assert new_hash != old_hash
        assert new_hash is not None

    def test_deleted_file(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """Deleting a file removes its artifact and all related data via CASCADE."""
        _create_full_project_tree(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        builder.full_build()

        # Verify the concept artifact exists before deletion
        auth_concept = db_conn.execute(
            "SELECT id FROM artifacts WHERE path = '.lexibrary/concepts/Authentication.md'"
        ).fetchone()
        assert auth_concept is not None
        concept_id = auth_concept[0]

        # Verify aliases exist
        alias_count_before = db_conn.execute(
            "SELECT COUNT(*) FROM aliases WHERE artifact_id = ?", (concept_id,)
        ).fetchone()[0]
        assert alias_count_before > 0

        # Delete the concept file from disk
        concept_file = tmp_path / ".lexibrary" / "concepts" / "Authentication.md"
        concept_file.unlink()

        result = builder.incremental_update([Path(".lexibrary/concepts/Authentication.md")])

        assert result.errors == []

        # Artifact should be gone
        query = (
            "SELECT COUNT(*) FROM artifacts WHERE path = '.lexibrary/concepts/Authentication.md'"
        )
        assert db_conn.execute(query).fetchone()[0] == 0

        # Aliases should be gone (via CASCADE)
        assert (
            db_conn.execute(
                "SELECT COUNT(*) FROM aliases WHERE artifact_id = ?", (concept_id,)
            ).fetchone()[0]
            == 0
        )

        # Build log should have a 'deleted' entry
        log = db_conn.execute(
            "SELECT action FROM build_log "
            "WHERE artifact_path = '.lexibrary/concepts/Authentication.md' "
            "AND build_type = 'incremental'"
        ).fetchone()
        assert log is not None
        assert log[0] == "deleted"

    def test_modified_concept_with_alias_change(
        self, db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """Modifying a concept file updates aliases, links, tags, and FTS."""
        _create_full_project_tree(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        builder.full_build()

        # Verify old aliases exist
        concept_id = db_conn.execute(
            "SELECT id FROM artifacts WHERE path = '.lexibrary/concepts/Authentication.md'"
        ).fetchone()[0]
        old_aliases = db_conn.execute(
            "SELECT alias FROM aliases WHERE artifact_id = ?", (concept_id,)
        ).fetchall()
        old_alias_set = {r[0] for r in old_aliases}
        assert "auth" in old_alias_set
        assert "authn" in old_alias_set

        # Modify the concept file with a new alias
        modified_concept = """\
---
title: Authentication
aliases:
  - auth
  - authentication-system
tags:
  - security
  - identity
  - core
status: active
---

Authentication is the process of verifying identity.

See also [[Authorization]] for related concepts.

## Linked Files

- `src/auth/login.py`
- `src/auth/middleware.py`

## Decision Log

- D-001: Use JWT tokens for stateless auth
"""
        concept_file = tmp_path / ".lexibrary" / "concepts" / "Authentication.md"
        concept_file.write_text(modified_concept, encoding="utf-8")

        result = builder.incremental_update([Path(".lexibrary/concepts/Authentication.md")])

        assert result.errors == []

        # The old "authn" alias should be gone, replaced by "authentication-system"
        new_aliases = db_conn.execute(
            "SELECT alias FROM aliases WHERE artifact_id = ?", (concept_id,)
        ).fetchall()
        new_alias_set = {r[0] for r in new_aliases}
        assert "auth" in new_alias_set
        assert "authentication-system" in new_alias_set
        assert "authn" not in new_alias_set

        # Tags should include the new "core" tag
        tags = db_conn.execute(
            "SELECT tag FROM tags WHERE artifact_id = ?", (concept_id,)
        ).fetchall()
        tag_set = {r[0] for r in tags}
        assert "core" in tag_set
        assert "security" in tag_set

        # Wikilinks: should now only have Authorization (SessionManagement removed)
        wikilinks = db_conn.execute(
            "SELECT tgt.path FROM links l "
            "JOIN artifacts tgt ON l.target_id = tgt.id "
            "WHERE l.source_id = ? AND l.link_type = 'wikilink'",
            (concept_id,),
        ).fetchall()
        wikilink_paths = {r[0] for r in wikilinks}
        assert ".lexibrary/concepts/Authorization.md" in wikilink_paths
        # SessionManagement should NOT be linked anymore
        assert ".lexibrary/concepts/SessionManagement.md" not in wikilink_paths

    def test_modified_aindex_conventions(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """Modifying a .aindex file replaces convention artifacts."""
        _create_full_project_tree(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        builder.full_build()

        # Count conventions before
        conv_count_before = db_conn.execute(
            "SELECT COUNT(*) FROM conventions WHERE directory_path = 'src/auth'"
        ).fetchone()[0]
        assert conv_count_before == 2  # the sample has 2 conventions

        # Modify .aindex with 3 conventions
        modified_aindex = """\
# src/auth

Updated authentication module.

## Child Map

| Name | Type | Description |
|------|------|-------------|
| `login.py` | file | Handles user login |
| `middleware.py` | file | Auth middleware |

## Local Conventions

- All endpoints must use [[Authentication]] middleware
- Password hashing must use bcrypt with cost factor 12
- All auth tokens must be [[Security]] validated on every request

<!-- lexibrary:meta source="src/auth" source_hash="newdef"
generated="2025-06-15T12:00:00" generator="lexibrary-test" -->
"""
        aindex_file = tmp_path / ".lexibrary" / "src" / "auth" / ".aindex"
        aindex_file.write_text(modified_aindex, encoding="utf-8")

        result = builder.incremental_update([Path(".lexibrary/src/auth/.aindex")])

        assert result.errors == []

        # Should now have 3 conventions
        conv_count_after = db_conn.execute(
            "SELECT COUNT(*) FROM conventions WHERE directory_path = 'src/auth'"
        ).fetchone()[0]
        assert conv_count_after == 3

        # All convention artifacts should have FTS rows
        conv_ids = db_conn.execute(
            "SELECT artifact_id FROM conventions WHERE directory_path = 'src/auth'"
        ).fetchall()
        for (cid,) in conv_ids:
            fts = db_conn.execute(
                "SELECT COUNT(*) FROM artifacts_fts WHERE rowid = ?", (cid,)
            ).fetchone()[0]
            assert fts == 1

    def test_incremental_update_returns_build_result(
        self, db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """incremental_update returns a BuildResult with correct metadata."""
        _create_full_project_tree(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        builder.full_build()

        result = builder.incremental_update([Path("src/auth/login.py")])

        assert result.build_type == "incremental"
        assert result.duration_ms >= 0
        assert result.artifact_count > 0
        assert result.link_count >= 0
        assert isinstance(result.errors, list)

    def test_incremental_update_meta_updated(
        self, db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """Meta table is updated after incremental update."""
        _create_full_project_tree(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        builder.full_build()

        result = builder.incremental_update([Path("src/auth/login.py")])

        meta_artifact = db_conn.execute(
            "SELECT value FROM meta WHERE key = 'artifact_count'"
        ).fetchone()
        assert meta_artifact is not None
        assert int(meta_artifact[0]) == result.artifact_count

    def test_incremental_update_resilient_to_errors(
        self, db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """Per-file errors do not abort the update; they are collected in errors."""
        _create_full_project_tree(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        builder.full_build()

        # Provide a concept file that exists but has malformed content
        bad_concept = tmp_path / ".lexibrary" / "concepts" / "Broken.md"
        bad_concept.write_text("no frontmatter here", encoding="utf-8")

        # Also update a valid file
        source_file = tmp_path / "src" / "auth" / "login.py"
        source_file.write_text(
            "from __future__ import annotations\n\ndef login() -> bool:\n    return True\n",
            encoding="utf-8",
        )

        result = builder.incremental_update(
            [
                Path(".lexibrary/concepts/Broken.md"),
                Path("src/auth/login.py"),
            ]
        )

        # The broken concept should produce an error
        assert len(result.errors) > 0
        assert any("Broken" in err for err in result.errors)

        # But the valid source file should still have been processed
        # (hash should be updated for the source file)
        hash_row = db_conn.execute(
            "SELECT last_hash FROM artifacts WHERE path = 'src/auth/login.py'"
        ).fetchone()
        assert hash_row is not None
        assert hash_row[0] is not None

    def test_incremental_update_cleans_stale_build_log(
        self, db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """Stale build log entries are cleaned during incremental update."""
        _create_full_project_tree(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        builder.full_build()

        # Insert a stale entry
        old_ts = (datetime.now(UTC) - timedelta(days=45)).isoformat()
        db_conn.execute(
            "INSERT INTO build_log (build_started, build_type, artifact_path, "
            "artifact_kind, action) VALUES (?, 'full', 'stale.py', 'source', 'created')",
            (old_ts,),
        )
        db_conn.commit()

        builder.incremental_update([Path("src/auth/login.py")])

        # The stale entry should be gone
        stale = db_conn.execute(
            "SELECT COUNT(*) FROM build_log WHERE artifact_path = 'stale.py'"
        ).fetchone()[0]
        assert stale == 0

    def test_incremental_update_empty_changed_paths(
        self, db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """incremental_update with empty list succeeds with no changes."""
        _create_full_project_tree(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        full_result = builder.full_build()

        result = builder.incremental_update([])

        assert result.errors == []
        assert result.build_type == "incremental"
        assert result.artifact_count == full_result.artifact_count

    def test_modified_design_file(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """Modifying a design file updates wikilinks, tags, stack refs, and FTS."""
        _create_full_project_tree(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        builder.full_build()

        design_path = ".lexibrary/src/auth/login.py.md"
        design_id = db_conn.execute(
            "SELECT id FROM artifacts WHERE path = ?", (design_path,)
        ).fetchone()[0]

        # Modify the design file -- add a new wikilink, remove a tag
        modified_design = """\
---
description: Updated auth handler
updated_by: archivist
---

# src/auth/login.py

## Interface Contract

```python
def login(username: str, password: str) -> bool: ...
def logout(session_id: str) -> None: ...
```

## Dependencies

- src/config/schema.py

## Dependents

(none)

## Wikilinks

- [[Authentication]]
- [[Security]]
- [[Authorization]]

## Tags

- auth

## Stack

- ST-001

<!-- lexibrary:meta
source: src/auth/login.py
source_hash: abc123
design_hash: newdef456
generated: 2025-06-15T12:00:00
generator: lexibrary-test
-->
"""
        design_file_path = tmp_path / ".lexibrary" / "src" / "auth" / "login.py.md"
        design_file_path.write_text(modified_design, encoding="utf-8")

        result = builder.incremental_update([Path(".lexibrary/src/auth/login.py.md")])

        assert result.errors == []

        # Title should be updated
        title = db_conn.execute(
            "SELECT title FROM artifacts WHERE path = ?", (design_path,)
        ).fetchone()[0]
        assert title == "Updated auth handler"

        # Should now have 3 wikilinks (was 2: Authentication, Security; now + Authorization)
        new_wikilinks = db_conn.execute(
            "SELECT tgt.path FROM links l "
            "JOIN artifacts tgt ON l.target_id = tgt.id "
            "WHERE l.source_id = ? AND l.link_type = 'wikilink'",
            (design_id,),
        ).fetchall()
        new_wikilink_paths = {r[0] for r in new_wikilinks}
        assert ".lexibrary/concepts/Authorization.md" in new_wikilink_paths
        assert ".lexibrary/concepts/Authentication.md" in new_wikilink_paths
        assert ".lexibrary/concepts/Security.md" in new_wikilink_paths

        # Tags: should only have 'auth' (previously had 'auth' + 'security')
        tags = db_conn.execute(
            "SELECT tag FROM tags WHERE artifact_id = ?", (design_id,)
        ).fetchall()
        tag_set = {r[0] for r in tags}
        assert tag_set == {"auth"}

        # FTS should be updated
        fts_row = db_conn.execute(
            "SELECT title, body FROM artifacts_fts WHERE rowid = ?", (design_id,)
        ).fetchone()
        assert fts_row is not None
        assert fts_row[0] == "Updated auth handler"
        assert "logout" in fts_row[1]

    def test_mixed_changed_paths(self, db_conn: sqlite3.Connection, tmp_path: Path) -> None:
        """incremental_update handles a mix of source, concept, and stack changes."""
        _create_full_project_tree(tmp_path)
        builder = IndexBuilder(db_conn, tmp_path)
        builder.full_build()

        # Modify source
        source_file = tmp_path / "src" / "auth" / "login.py"
        source_file.write_text(
            "from __future__ import annotations\n\ndef login() -> bool:\n    return True\n",
            encoding="utf-8",
        )

        # Modify concept
        concept_file = tmp_path / ".lexibrary" / "concepts" / "Authentication.md"
        modified = _SAMPLE_CONCEPT_FILE.replace("authn", "authentication")
        concept_file.write_text(modified, encoding="utf-8")

        result = builder.incremental_update(
            [
                Path("src/auth/login.py"),
                Path(".lexibrary/concepts/Authentication.md"),
            ]
        )

        assert result.errors == []
        assert result.build_type == "incremental"
        assert result.artifact_count > 0


# ---------------------------------------------------------------------------
# Public API integration tests (task group 9)
# ---------------------------------------------------------------------------


class TestBuildIndex:
    """Integration tests for the module-level ``build_index()`` function."""

    def test_full_build_creates_database(self, tmp_path: Path) -> None:
        """build_index with no changed_paths creates the database and performs a full build."""
        _create_full_project_tree(tmp_path)
        result = build_index(tmp_path)

        assert result.build_type == "full"
        assert result.artifact_count > 0
        assert result.link_count > 0
        assert result.errors == []
        assert result.duration_ms >= 0

        # Verify the database file was created
        db_path = tmp_path / ".lexibrary" / "index.db"
        assert db_path.is_file()

    def test_full_build_database_is_readable(self, tmp_path: Path) -> None:
        """After build_index, the database can be opened and queried."""
        _create_full_project_tree(tmp_path)
        result = build_index(tmp_path)

        # Open the database directly and verify contents match the result
        conn = sqlite3.connect(str(tmp_path / ".lexibrary" / "index.db"))
        try:
            artifact_count = conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
            link_count = conn.execute("SELECT COUNT(*) FROM links").fetchone()[0]
            assert artifact_count == result.artifact_count
            assert link_count == result.link_count
        finally:
            conn.close()

    def test_incremental_update_via_build_index(self, tmp_path: Path) -> None:
        """build_index with changed_paths performs an incremental update."""
        _create_full_project_tree(tmp_path)

        # First do a full build
        full_result = build_index(tmp_path)
        assert full_result.errors == []

        # Modify a source file
        source_file = tmp_path / "src" / "auth" / "login.py"
        source_file.write_text(
            "from __future__ import annotations\n\ndef login() -> bool:\n    return True\n",
            encoding="utf-8",
        )

        # Incremental update
        inc_result = build_index(
            tmp_path,
            changed_paths=[Path("src/auth/login.py")],
        )

        assert inc_result.build_type == "incremental"
        assert inc_result.errors == []
        assert inc_result.artifact_count > 0

    def test_full_build_on_empty_project(self, tmp_path: Path) -> None:
        """build_index on a project with no artifacts creates an empty database."""
        # Just create the .lexibrary dir with no content
        (tmp_path / ".lexibrary").mkdir(parents=True, exist_ok=True)

        result = build_index(tmp_path)

        assert result.build_type == "full"
        assert result.artifact_count == 0
        assert result.link_count == 0
        assert result.errors == []

        # Database file should still be created
        assert (tmp_path / ".lexibrary" / "index.db").is_file()

    def test_build_index_creates_lexibrary_dir_if_needed(self, tmp_path: Path) -> None:
        """build_index creates the .lexibrary directory if it does not exist."""
        # tmp_path has no .lexibrary dir
        result = build_index(tmp_path)

        assert result.build_type == "full"
        assert (tmp_path / ".lexibrary" / "index.db").is_file()

    def test_incremental_with_empty_list(self, tmp_path: Path) -> None:
        """build_index with an empty changed_paths list is a no-op incremental update."""
        _create_full_project_tree(tmp_path)

        # Full build first
        build_index(tmp_path)

        # Incremental with empty list
        result = build_index(tmp_path, changed_paths=[])

        assert result.build_type == "incremental"
        assert result.errors == []

    def test_successive_full_builds_are_idempotent(self, tmp_path: Path) -> None:
        """Two consecutive full builds produce the same artifact and link counts."""
        _create_full_project_tree(tmp_path)

        first = build_index(tmp_path)
        second = build_index(tmp_path)

        assert first.artifact_count == second.artifact_count
        assert first.link_count == second.link_count
        assert first.errors == []
        assert second.errors == []


class TestOpenIndex:
    """Integration tests for the module-level ``open_index()`` function."""

    def test_returns_none_when_no_database(self, tmp_path: Path) -> None:
        """open_index returns None when .lexibrary/index.db does not exist."""
        result = open_index(tmp_path)
        assert result is None

    def test_returns_none_when_lexibrary_dir_missing(self, tmp_path: Path) -> None:
        """open_index returns None when the .lexibrary directory itself is missing."""
        result = open_index(tmp_path)
        assert result is None

    def test_returns_connection_after_build(self, tmp_path: Path) -> None:
        """open_index returns a valid connection after build_index has populated the database."""
        _create_full_project_tree(tmp_path)
        build_index(tmp_path)

        conn = open_index(tmp_path)
        assert conn is not None

        try:
            # Verify the connection is usable
            artifact_count = conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
            assert artifact_count > 0
        finally:
            conn.close()

    def test_pragmas_are_set(self, tmp_path: Path) -> None:
        """open_index sets WAL mode and foreign key pragmas on the returned connection."""
        _create_full_project_tree(tmp_path)
        build_index(tmp_path)

        conn = open_index(tmp_path)
        assert conn is not None

        try:
            # Check foreign keys are enabled
            fk = conn.execute("PRAGMA foreign_keys").fetchone()
            assert fk is not None
            assert fk[0] == 1

            # Check WAL mode
            journal = conn.execute("PRAGMA journal_mode").fetchone()
            assert journal is not None
            assert journal[0] == "wal"
        finally:
            conn.close()

    def test_returns_none_for_corrupt_database(self, tmp_path: Path) -> None:
        """open_index returns None when the database file is corrupt."""
        db_dir = tmp_path / ".lexibrary"
        db_dir.mkdir(parents=True, exist_ok=True)
        db_path = db_dir / "index.db"

        # Write garbage data to simulate corruption
        db_path.write_bytes(b"This is not a valid SQLite database at all!")

        result = open_index(tmp_path)
        assert result is None

    def test_returns_none_for_empty_database(self, tmp_path: Path) -> None:
        """open_index returns None when the database exists but has no meta table."""
        db_dir = tmp_path / ".lexibrary"
        db_dir.mkdir(parents=True, exist_ok=True)
        db_path = db_dir / "index.db"

        # Create an empty SQLite database with no tables
        conn = sqlite3.connect(str(db_path))
        conn.close()

        result = open_index(tmp_path)
        assert result is None

    def test_connection_can_query_schema(self, tmp_path: Path) -> None:
        """The connection from open_index can query schema version from meta."""
        _create_full_project_tree(tmp_path)
        build_index(tmp_path)

        conn = open_index(tmp_path)
        assert conn is not None

        try:
            row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
            assert row is not None
            # Schema version should be a valid integer
            version = int(row[0])
            assert version > 0
        finally:
            conn.close()
