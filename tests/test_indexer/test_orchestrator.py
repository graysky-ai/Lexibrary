"""Tests for the index orchestrator."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from lexibrary.config.schema import LexibraryConfig
from lexibrary.indexer.orchestrator import IndexStats, index_directory, index_recursive


def _setup_project(tmp_path: Path) -> Path:
    """Create a minimal project structure with .lexibrary/ dir."""
    (tmp_path / ".lexibrary").mkdir()
    return tmp_path


class TestIndexStats:
    def test_defaults_to_zero(self) -> None:
        stats = IndexStats()
        assert stats.directories_indexed == 0
        assert stats.files_found == 0
        assert stats.errors == 0


class TestIndexDirectory:
    def test_writes_aindex_to_mirror_path(self, tmp_path: Path) -> None:
        project_root = _setup_project(tmp_path)
        src = project_root / "src"
        src.mkdir()
        (src / "main.py").write_text("print('hello')\n", encoding="utf-8")

        result = index_directory(src, project_root, LexibraryConfig())
        expected = project_root / ".lexibrary" / "designs" / "src" / ".aindex"
        assert result == expected
        assert expected.exists()

    def test_creates_mirror_parent_dirs(self, tmp_path: Path) -> None:
        project_root = _setup_project(tmp_path)
        deep = project_root / "src" / "auth" / "providers"
        deep.mkdir(parents=True)
        (deep / "oauth.py").write_text("x\n", encoding="utf-8")

        result = index_directory(deep, project_root, LexibraryConfig())
        expected = (
            project_root / ".lexibrary" / "designs" / "src" / "auth" / "providers" / ".aindex"
        )
        assert result == expected
        assert expected.exists()

    def test_returns_output_path(self, tmp_path: Path) -> None:
        project_root = _setup_project(tmp_path)
        src = project_root / "src"
        src.mkdir()

        result = index_directory(src, project_root, LexibraryConfig())
        assert isinstance(result, Path)
        assert result.name == ".aindex"

    def test_aindex_contains_directory_entries(self, tmp_path: Path) -> None:
        project_root = _setup_project(tmp_path)
        src = project_root / "src"
        src.mkdir()
        (src / "app.py").write_text("x = 1\n", encoding="utf-8")
        (src / "utils.py").write_text("y = 2\n", encoding="utf-8")

        result = index_directory(src, project_root, LexibraryConfig())
        content = result.read_text(encoding="utf-8")
        assert "app.py" in content
        assert "utils.py" in content

    def test_empty_directory_produces_aindex(self, tmp_path: Path) -> None:
        project_root = _setup_project(tmp_path)
        empty = project_root / "empty"
        empty.mkdir()

        result = index_directory(empty, project_root, LexibraryConfig())
        assert result.exists()
        content = result.read_text(encoding="utf-8")
        assert "Empty directory." in content


class TestIndexRecursive:
    def test_processes_all_directories(self, tmp_path: Path) -> None:
        project_root = _setup_project(tmp_path)
        src = project_root / "src"
        src.mkdir()
        utils = src / "utils"
        utils.mkdir()
        (src / "main.py").write_text("x\n", encoding="utf-8")
        (utils / "helper.py").write_text("y\n", encoding="utf-8")

        stats = index_recursive(project_root, project_root, LexibraryConfig())
        # Should index: project_root, src, utils (3 directories)
        assert stats.directories_indexed == 3

        # Check that .aindex files exist for all three
        assert (project_root / ".lexibrary" / "designs" / "src" / "utils" / ".aindex").exists()
        assert (project_root / ".lexibrary" / "designs" / "src" / ".aindex").exists()

    def test_processes_child_before_parent(self, tmp_path: Path) -> None:
        """Verify bottom-up ordering: src/utils/ is indexed before src/."""
        project_root = _setup_project(tmp_path)
        src = project_root / "src"
        src.mkdir()
        utils = src / "utils"
        utils.mkdir()
        (utils / "a.py").write_text("x\n", encoding="utf-8")
        (utils / "b.py").write_text("y\n", encoding="utf-8")
        (utils / "c.py").write_text("z\n", encoding="utf-8")

        order: list[str] = []

        def track_callback(current: int, total: int, name: str) -> None:
            order.append(name)

        index_recursive(
            project_root,
            project_root,
            LexibraryConfig(),
            progress_callback=track_callback,
        )

        utils_idx = order.index("utils")
        src_idx = order.index("src")
        assert utils_idx < src_idx, "utils should be indexed before src"

    def test_parent_aindex_references_child_count(self, tmp_path: Path) -> None:
        project_root = _setup_project(tmp_path)
        src = project_root / "src"
        src.mkdir()
        utils = src / "utils"
        utils.mkdir()
        (utils / "a.py").write_text("x\n", encoding="utf-8")
        (utils / "b.py").write_text("y\n", encoding="utf-8")
        (utils / "c.py").write_text("z\n", encoding="utf-8")

        index_recursive(project_root, project_root, LexibraryConfig())

        # Read the parent src/.aindex — utils/ entry should reference child count
        src_aindex_path = project_root / ".lexibrary" / "designs" / "src" / ".aindex"
        src_aindex = src_aindex_path.read_text(encoding="utf-8")
        assert "Contains 3 files" in src_aindex

    def test_lexibrary_excluded_from_indexing(self, tmp_path: Path) -> None:
        project_root = _setup_project(tmp_path)
        src = project_root / "src"
        src.mkdir()
        (src / "main.py").write_text("x\n", encoding="utf-8")

        index_recursive(project_root, project_root, LexibraryConfig())
        # .lexibrary/ should NOT have its own .aindex inside the mirror
        lexibrary_aindex = project_root / ".lexibrary" / "designs" / ".lexibrary" / ".aindex"
        assert not lexibrary_aindex.exists()

    def test_progress_callback_invoked_per_directory(self, tmp_path: Path) -> None:
        project_root = _setup_project(tmp_path)
        src = project_root / "src"
        src.mkdir()
        (src / "main.py").write_text("x\n", encoding="utf-8")

        callback = MagicMock()
        index_recursive(
            project_root,
            project_root,
            LexibraryConfig(),
            progress_callback=callback,
        )

        # Should be called once per directory (project_root + src = 2)
        assert callback.call_count == 2
        # Each call should have (current, total, name)
        for call_args in callback.call_args_list:
            current, total, name = call_args[0]
            assert isinstance(current, int)
            assert isinstance(total, int)
            assert isinstance(name, str)
            assert current <= total

    def test_progress_callback_none_is_ok(self, tmp_path: Path) -> None:
        project_root = _setup_project(tmp_path)
        src = project_root / "src"
        src.mkdir()

        # Should not raise
        stats = index_recursive(
            project_root,
            project_root,
            LexibraryConfig(),
            progress_callback=None,
        )
        assert stats.directories_indexed >= 1

    def test_stats_reflect_indexed_count(self, tmp_path: Path) -> None:
        project_root = _setup_project(tmp_path)
        a = project_root / "a"
        a.mkdir()
        b = project_root / "b"
        b.mkdir()
        c = project_root / "c"
        c.mkdir()
        d = a / "d"
        d.mkdir()
        e = a / "e"
        e.mkdir()

        stats = index_recursive(project_root, project_root, LexibraryConfig())
        # project_root, a, b, c, d, e = 6 directories
        assert stats.directories_indexed == 6

    def test_stats_files_found_counts_files(self, tmp_path: Path) -> None:
        project_root = _setup_project(tmp_path)
        src = project_root / "src"
        src.mkdir()
        (src / "a.py").write_text("x\n", encoding="utf-8")
        (src / "b.py").write_text("y\n", encoding="utf-8")

        stats = index_recursive(src, project_root, LexibraryConfig())
        assert stats.files_found == 2

    def test_ignored_directories_skipped(self, tmp_path: Path) -> None:
        project_root = _setup_project(tmp_path)
        src = project_root / "src"
        src.mkdir()
        pycache = src / "__pycache__"
        pycache.mkdir()
        (pycache / "mod.cpython-311.pyc").write_bytes(b"\x00")

        index_recursive(project_root, project_root, LexibraryConfig())

        # __pycache__ is in the default ignore patterns, so it should be skipped
        pycache_aindex = project_root / ".lexibrary" / "designs" / "src" / "__pycache__" / ".aindex"
        assert not pycache_aindex.exists()

    def test_deeply_nested_bottom_up_order(self, tmp_path: Path) -> None:
        """Verify deeply nested directories are processed before their parents."""
        project_root = _setup_project(tmp_path)
        a = project_root / "a"
        b = a / "b"
        c = b / "c"
        c.mkdir(parents=True)
        (c / "file.py").write_text("x\n", encoding="utf-8")

        order: list[str] = []

        def track_callback(current: int, total: int, name: str) -> None:
            order.append(name)

        index_recursive(
            project_root,
            project_root,
            LexibraryConfig(),
            progress_callback=track_callback,
        )

        c_idx = order.index("c")
        b_idx = order.index("b")
        a_idx = order.index("a")
        assert c_idx < b_idx < a_idx, "Should process c before b before a"
