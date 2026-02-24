"""Unit tests for find_all_iwh() discovery function."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from lexibrary.iwh import IWHFile, serialize_iwh
from lexibrary.iwh.reader import find_all_iwh


def _write_iwh(directory: Path, *, scope: str = "incomplete", body: str = "WIP") -> None:
    """Write a valid .iwh file into *directory*."""
    iwh = IWHFile(
        author="agent-test",
        created=datetime(2026, 2, 24, 10, 0, 0, tzinfo=UTC),
        scope=scope,
        body=body,
    )
    directory.mkdir(parents=True, exist_ok=True)
    (directory / ".iwh").write_text(serialize_iwh(iwh), encoding="utf-8")


class TestFindAllIWH:
    """Tests for find_all_iwh()."""

    def test_no_lexibrary_dir_returns_empty(self, tmp_path: Path) -> None:
        """Missing .lexibrary/ → empty list."""
        assert find_all_iwh(tmp_path) == []

    def test_no_iwh_files_returns_empty(self, tmp_path: Path) -> None:
        """Existing .lexibrary/ with no .iwh files → empty list."""
        (tmp_path / ".lexibrary").mkdir()
        assert find_all_iwh(tmp_path) == []

    def test_project_root_signal(self, tmp_path: Path) -> None:
        """IWH at .lexibrary/.iwh → [(Path("."), iwh)]."""
        _write_iwh(tmp_path / ".lexibrary", scope="warning", body="heads up")
        results = find_all_iwh(tmp_path)
        assert len(results) == 1
        rel, iwh = results[0]
        assert rel == Path(".")
        assert iwh.scope == "warning"
        assert iwh.body == "heads up"

    def test_multiple_signals_sorted(self, tmp_path: Path) -> None:
        """Multiple .iwh files are returned sorted by path."""
        _write_iwh(tmp_path / ".lexibrary" / "src" / "auth", scope="blocked", body="auth blocked")
        _write_iwh(tmp_path / ".lexibrary", scope="incomplete", body="root wip")
        _write_iwh(tmp_path / ".lexibrary" / "src" / "api", scope="warning", body="api note")

        results = find_all_iwh(tmp_path)
        assert len(results) == 3
        paths = [str(rel) for rel, _ in results]
        assert paths == [".", "src/api", "src/auth"]

    def test_corrupt_file_skipped(self, tmp_path: Path) -> None:
        """Unparseable .iwh files are silently skipped."""
        lex_dir = tmp_path / ".lexibrary"
        lex_dir.mkdir()
        (lex_dir / ".iwh").write_text("not valid frontmatter", encoding="utf-8")
        _write_iwh(lex_dir / "src", scope="incomplete", body="valid")

        results = find_all_iwh(tmp_path)
        assert len(results) == 1
        rel, iwh = results[0]
        assert rel == Path("src")
        assert iwh.scope == "incomplete"

    def test_source_directory_path_reversal(self, tmp_path: Path) -> None:
        """IWH at .lexibrary/src/auth/.iwh → relative path is Path("src/auth")."""
        _write_iwh(tmp_path / ".lexibrary" / "src" / "auth", body="deep")
        results = find_all_iwh(tmp_path)
        assert len(results) == 1
        rel, _ = results[0]
        assert rel == Path("src/auth")
