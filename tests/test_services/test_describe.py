"""Unit tests for lexibrary.services.describe — billboard update service."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from lexibrary.services.describe import DescribeError, update_billboard


def _setup_project(tmp_path: Path) -> Path:
    """Create a minimal project with .lexibrary directory."""
    (tmp_path / ".lexibrary").mkdir()
    (tmp_path / ".lexibrary" / "config.yaml").write_text("")
    (tmp_path / "src").mkdir()
    return tmp_path


def _create_aindex(project: Path, directory_rel: str, billboard: str) -> Path:
    """Create a .aindex file in the .lexibrary mirror tree."""
    aindex_file = project / ".lexibrary" / "designs" / directory_rel / ".aindex"
    aindex_file.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now().isoformat()
    content = f"""# {directory_rel}/

{billboard}

## Child Map

| Name | Type | Description |
| --- | --- | --- |
| `main.py` | file | Main module |

## Local Conventions

(none)

<!-- lexibrary:meta source="{directory_rel}" source_hash="abc123" """
    content += f"""generated="{now}" generator="lexibrary-v2" -->
"""
    aindex_file.write_text(content, encoding="utf-8")
    return aindex_file


class TestUpdateBillboard:
    """Tests for the update_billboard() service function."""

    def test_successful_update(self, tmp_path: Path) -> None:
        """update_billboard updates the .aindex billboard and returns the file path."""
        project = _setup_project(tmp_path)
        _create_aindex(project, "src", "Old description")

        result = update_billboard(project, project / "src", "New description")

        assert result == project / ".lexibrary" / "designs" / "src" / ".aindex"
        content = result.read_text(encoding="utf-8")
        assert "New description" in content
        assert "Old description" not in content

    def test_directory_not_found(self, tmp_path: Path) -> None:
        """update_billboard raises DescribeError for nonexistent directory."""
        project = _setup_project(tmp_path)

        with pytest.raises(DescribeError, match="Directory not found"):
            update_billboard(project, project / "nonexistent", "Description")

    def test_not_a_directory(self, tmp_path: Path) -> None:
        """update_billboard raises DescribeError when target is a file."""
        project = _setup_project(tmp_path)
        (project / "somefile.txt").write_text("hello")

        with pytest.raises(DescribeError, match="Not a directory"):
            update_billboard(project, project / "somefile.txt", "Description")

    def test_directory_outside_project(self, tmp_path: Path) -> None:
        """update_billboard raises DescribeError for directory outside project root."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / ".lexibrary").mkdir()
        (project_dir / ".lexibrary" / "config.yaml").write_text("")
        outside = tmp_path / "outside"
        outside.mkdir()

        with pytest.raises(DescribeError, match="outside project root"):
            update_billboard(project_dir, outside, "Description")

    def test_missing_aindex(self, tmp_path: Path) -> None:
        """update_billboard raises DescribeError when no .aindex file exists."""
        project = _setup_project(tmp_path)

        with pytest.raises(DescribeError, match="No .aindex file"):
            update_billboard(project, project / "src", "Description")

    def test_unparseable_aindex(self, tmp_path: Path) -> None:
        """update_billboard raises DescribeError for malformed .aindex files."""
        project = _setup_project(tmp_path)
        aindex_file = project / ".lexibrary" / "designs" / "src" / ".aindex"
        aindex_file.parent.mkdir(parents=True, exist_ok=True)
        # Write content that will cause parse_aindex to return None
        # (no H1 heading, no billboard, no metadata footer)
        aindex_file.write_text("", encoding="utf-8")

        with pytest.raises(DescribeError, match="Failed to parse"):
            update_billboard(project, project / "src", "Description")

    def test_no_cli_dependencies(self) -> None:
        """update_billboard is importable without pulling in CLI modules."""
        import importlib  # noqa: PLC0415

        mod = importlib.import_module("lexibrary.services.describe")

        # Verify the module source does not import CLI dependencies.
        # (sys.modules check is unreliable since other tests may load typer.)
        source = Path(mod.__file__).read_text(encoding="utf-8")
        assert "import typer" not in source
        assert "from lexibrary.cli._output" not in source
