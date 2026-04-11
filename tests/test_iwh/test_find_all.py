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
    """Tests for find_all_iwh().

    Production layout: .iwh files live under ``.lexibrary/designs/<src-path>/.iwh``.
    ``find_all_iwh`` strips the ``designs/`` prefix so callers receive
    source-relative paths that can be joined back to ``project_root`` to
    point at a valid source directory.
    """

    def test_no_lexibrary_dir_returns_empty(self, tmp_path: Path) -> None:
        """Missing .lexibrary/ → empty list."""
        assert find_all_iwh(tmp_path) == []

    def test_no_iwh_files_returns_empty(self, tmp_path: Path) -> None:
        """Existing .lexibrary/ with no .iwh files → empty list."""
        (tmp_path / ".lexibrary").mkdir()
        assert find_all_iwh(tmp_path) == []

    def test_signal_under_designs_is_source_relative(self, tmp_path: Path) -> None:
        """IWH at .lexibrary/designs/src/auth/.iwh → relative path is Path('src/auth')."""
        _write_iwh(
            tmp_path / ".lexibrary" / "designs" / "src" / "auth",
            scope="blocked",
            body="auth blocked",
        )
        results = find_all_iwh(tmp_path)
        assert len(results) == 1
        rel, iwh = results[0]
        assert rel == Path("src/auth")
        assert iwh.scope == "blocked"
        # Joining with project_root should point at a valid source directory.
        assert tmp_path / rel == tmp_path / "src" / "auth"

    def test_designs_root_signal_strips_prefix(self, tmp_path: Path) -> None:
        """IWH at .lexibrary/designs/.iwh → relative path is Path('.')."""
        _write_iwh(tmp_path / ".lexibrary" / "designs", scope="warning", body="top-level")
        results = find_all_iwh(tmp_path)
        assert len(results) == 1
        rel, iwh = results[0]
        assert rel == Path(".")
        assert iwh.scope == "warning"
        assert iwh.body == "top-level"

    def test_multiple_designs_signals_sorted_and_stripped(self, tmp_path: Path) -> None:
        """Multiple .iwh files under designs/ are sorted and all have prefix stripped."""
        _write_iwh(
            tmp_path / ".lexibrary" / "designs" / "src" / "auth",
            scope="blocked",
            body="auth blocked",
        )
        _write_iwh(
            tmp_path / ".lexibrary" / "designs" / "src" / "api",
            scope="warning",
            body="api note",
        )
        _write_iwh(
            tmp_path / ".lexibrary" / "designs" / "src" / "auth" / "oauth",
            scope="incomplete",
            body="oauth WIP",
        )

        results = find_all_iwh(tmp_path)
        assert len(results) == 3
        paths = [str(rel) for rel, _ in results]
        # Sort order follows rglob; all entries should be source-relative
        # (no ``designs/`` prefix).
        assert paths == ["src/api", "src/auth", "src/auth/oauth"]
        for rel, _ in results:
            assert not str(rel).startswith("designs")

    def test_non_designs_signal_not_stripped(self, tmp_path: Path) -> None:
        """IWH outside designs/ keeps its path as-is (no leading component to strip)."""
        _write_iwh(tmp_path / ".lexibrary", scope="incomplete", body="root wip")
        results = find_all_iwh(tmp_path)
        assert len(results) == 1
        rel, _ = results[0]
        # ``find_all_iwh`` only strips ``designs/`` as the first component; other
        # locations are returned unchanged.
        assert rel == Path(".")

    def test_corrupt_file_skipped(self, tmp_path: Path) -> None:
        """Unparseable .iwh files are silently skipped."""
        lex_designs = tmp_path / ".lexibrary" / "designs"
        lex_designs.mkdir(parents=True)
        (lex_designs / ".iwh").write_text("not valid frontmatter", encoding="utf-8")
        _write_iwh(lex_designs / "src", scope="incomplete", body="valid")

        results = find_all_iwh(tmp_path)
        assert len(results) == 1
        rel, iwh = results[0]
        assert rel == Path("src")
        assert iwh.scope == "incomplete"
