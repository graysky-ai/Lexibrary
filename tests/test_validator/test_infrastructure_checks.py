"""Unit tests for infrastructure validation checks.

Tests check_config_valid, check_lexignore_syntax, and
check_linkgraph_version from the validator.checks module.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from lexibrary.linkgraph.schema import SCHEMA_VERSION, ensure_schema
from lexibrary.validator.checks import (
    check_config_valid,
    check_lexignore_syntax,
    check_linkgraph_version,
)

# ---------------------------------------------------------------------------
# check_config_valid
# ---------------------------------------------------------------------------


class TestCheckConfigValid:
    """Tests for check_config_valid."""

    def test_valid_config_passes(self, tmp_path: Path) -> None:
        """A valid config.yaml produces no issues."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        config_path = lexibrary_dir / "config.yaml"
        config_path.write_text(
            "project_name: test-project\nscope_root: .\n",
            encoding="utf-8",
        )

        issues = check_config_valid(project_root, lexibrary_dir)
        assert issues == []

    def test_empty_config_passes(self, tmp_path: Path) -> None:
        """An empty config.yaml is valid (all fields have defaults)."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        config_path = lexibrary_dir / "config.yaml"
        config_path.write_text("", encoding="utf-8")

        issues = check_config_valid(project_root, lexibrary_dir)
        assert issues == []

    def test_missing_config_reports_error(self, tmp_path: Path) -> None:
        """Missing config.yaml produces an error suggesting lexi init."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        issues = check_config_valid(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert issues[0].check == "config_valid"
        assert "not found" in issues[0].message
        assert "lexictl init" in issues[0].suggestion

    def test_invalid_yaml_reports_error(self, tmp_path: Path) -> None:
        """Unparseable YAML produces an error with YAML syntax message."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        config_path = lexibrary_dir / "config.yaml"
        config_path.write_text("invalid: yaml: [broken\n", encoding="utf-8")

        issues = check_config_valid(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert issues[0].check == "config_valid"
        assert "YAML" in issues[0].message

    def test_pydantic_errors_reported_per_field(self, tmp_path: Path) -> None:
        """Pydantic validation failures produce one issue per error."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        config_path = lexibrary_dir / "config.yaml"
        # crawl.max_file_size_kb expects an int, not a string
        config_path.write_text(
            "crawl:\n  max_file_size_kb: not-a-number\n",
            encoding="utf-8",
        )

        issues = check_config_valid(project_root, lexibrary_dir)
        assert len(issues) >= 1
        assert all(i.severity == "error" for i in issues)
        assert all(i.check == "config_valid" for i in issues)
        # Should mention the field path
        assert any("max_file_size_kb" in i.message for i in issues)

    def test_non_mapping_yaml_reports_error(self, tmp_path: Path) -> None:
        """YAML that parses to a non-mapping (e.g., a list) is an error."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        config_path = lexibrary_dir / "config.yaml"
        config_path.write_text("- item1\n- item2\n", encoding="utf-8")

        issues = check_config_valid(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert issues[0].check == "config_valid"
        assert "not a YAML mapping" in issues[0].message


# ---------------------------------------------------------------------------
# check_lexignore_syntax
# ---------------------------------------------------------------------------


class TestCheckLexignoreSyntax:
    """Tests for check_lexignore_syntax."""

    def test_valid_lexignore_passes(self, tmp_path: Path) -> None:
        """A .lexignore with valid patterns produces no issues."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        lexignore_path = project_root / ".lexignore"
        lexignore_path.write_text(
            "# Comment line\n\n*.pyc\n__pycache__/\n.env\n",
            encoding="utf-8",
        )

        issues = check_lexignore_syntax(project_root, lexibrary_dir)
        assert issues == []

    def test_no_lexignore_returns_empty(self, tmp_path: Path) -> None:
        """When .lexignore does not exist, no issues are returned."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        issues = check_lexignore_syntax(project_root, lexibrary_dir)
        assert issues == []

    def test_comments_and_blanks_skipped(self, tmp_path: Path) -> None:
        """Comment lines and blank lines are not validated as patterns."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        lexignore_path = project_root / ".lexignore"
        lexignore_path.write_text(
            "# This is a comment\n\n# Another comment\n   \n*.log\n",
            encoding="utf-8",
        )

        issues = check_lexignore_syntax(project_root, lexibrary_dir)
        assert issues == []

    def test_standard_gitignore_patterns_valid(self, tmp_path: Path) -> None:
        """Common gitignore patterns (negation, directory, wildcards) pass."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        lexignore_path = project_root / ".lexignore"
        lexignore_path.write_text(
            "*.pyc\n!important.pyc\nnode_modules/\n**/build/\n*.log\n",
            encoding="utf-8",
        )

        issues = check_lexignore_syntax(project_root, lexibrary_dir)
        assert issues == []


# ---------------------------------------------------------------------------
# check_linkgraph_version
# ---------------------------------------------------------------------------


class TestCheckLinkgraphVersion:
    """Tests for check_linkgraph_version."""

    def test_matching_version_passes(self, tmp_path: Path) -> None:
        """When stored schema version equals SCHEMA_VERSION, no issues."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        db_path = lexibrary_dir / "index.db"
        conn = sqlite3.connect(str(db_path))
        ensure_schema(conn, force=True)
        conn.close()

        issues = check_linkgraph_version(project_root, lexibrary_dir)
        assert issues == []

    def test_version_mismatch_reports_error(self, tmp_path: Path) -> None:
        """When stored version differs from SCHEMA_VERSION, an error is returned."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        db_path = lexibrary_dir / "index.db"
        conn = sqlite3.connect(str(db_path))
        ensure_schema(conn, force=True)
        # Overwrite with a different version
        old_version = SCHEMA_VERSION - 1
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
            ("schema_version", str(old_version)),
        )
        conn.commit()
        conn.close()

        issues = check_linkgraph_version(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert issues[0].check == "linkgraph_version"
        assert "mismatch" in issues[0].message
        assert str(old_version) in issues[0].message
        assert str(SCHEMA_VERSION) in issues[0].message

    def test_no_database_returns_empty(self, tmp_path: Path) -> None:
        """When index.db does not exist, no issues are returned."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        issues = check_linkgraph_version(project_root, lexibrary_dir)
        assert issues == []

    def test_corrupt_database_reports_error(self, tmp_path: Path) -> None:
        """When index.db is not a valid SQLite file, an error is returned."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        db_path = lexibrary_dir / "index.db"
        db_path.write_text("this is not a sqlite database", encoding="utf-8")

        issues = check_linkgraph_version(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert issues[0].check == "linkgraph_version"

    def test_missing_meta_table_reports_error(self, tmp_path: Path) -> None:
        """When the database has no meta table, an error is returned."""
        project_root = tmp_path
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir()

        db_path = lexibrary_dir / "index.db"
        conn = sqlite3.connect(str(db_path))
        # Create an empty database with no tables
        conn.execute("CREATE TABLE dummy (id INTEGER PRIMARY KEY)")
        conn.commit()
        conn.close()

        issues = check_linkgraph_version(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert issues[0].check == "linkgraph_version"
        assert "No schema version" in issues[0].message
