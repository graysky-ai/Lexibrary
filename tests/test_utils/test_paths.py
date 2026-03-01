"""Tests for path utilities — root resolution and mirror tree construction."""

from __future__ import annotations

from pathlib import Path

import pytest

from lexibrary.exceptions import LexibraryNotFoundError
from lexibrary.utils.paths import aindex_path, iwh_path, mirror_path
from lexibrary.utils.root import find_project_root


def test_find_project_root_in_cwd(tmp_path: Path) -> None:
    """find_project_root should find .lexibrary/ in the start directory."""
    (tmp_path / ".lexibrary").mkdir()

    result = find_project_root(tmp_path)
    assert result == tmp_path


def test_find_project_root_in_parent(tmp_path: Path) -> None:
    """find_project_root should walk up to find .lexibrary/."""
    (tmp_path / ".lexibrary").mkdir()
    subdir = tmp_path / "src" / "nested"
    subdir.mkdir(parents=True)

    result = find_project_root(subdir)
    assert result == tmp_path


def test_find_project_root_not_found(tmp_path: Path) -> None:
    """find_project_root should raise LexibraryNotFoundError when not found."""
    subdir = tmp_path / "some" / "nested" / "dir"
    subdir.mkdir(parents=True)

    with pytest.raises(LexibraryNotFoundError):
        find_project_root(subdir)


def test_find_project_root_nearest(tmp_path: Path) -> None:
    """find_project_root should return the nearest .lexibrary/ directory."""
    (tmp_path / ".lexibrary").mkdir()
    nested = tmp_path / "project"
    nested.mkdir()
    (nested / ".lexibrary").mkdir()

    result = find_project_root(nested / "src")
    assert result == nested


# ---------------------------------------------------------------------------
# mirror_path / aindex_path
# ---------------------------------------------------------------------------


def test_mirror_path_simple(tmp_path: Path) -> None:
    """mirror_path maps a source file into .lexibrary/designs/ with .md suffix."""
    result = mirror_path(tmp_path, tmp_path / "src" / "auth" / "login.py")
    assert result == tmp_path / ".lexibrary" / "designs" / "src" / "auth" / "login.py.md"


def test_mirror_path_relative(tmp_path: Path) -> None:
    """mirror_path accepts a project-relative path."""
    result = mirror_path(tmp_path, Path("src/auth/login.py"))
    assert result == tmp_path / ".lexibrary" / "designs" / "src" / "auth" / "login.py.md"


def test_mirror_path_deeply_nested(tmp_path: Path) -> None:
    """mirror_path preserves full directory depth."""
    result = mirror_path(tmp_path, Path("backend/api/v2/users/controller.py"))
    expected = (
        tmp_path / ".lexibrary" / "designs"
        / "backend" / "api" / "v2" / "users" / "controller.py.md"
    )
    assert result == expected


def test_aindex_path_simple(tmp_path: Path) -> None:
    """aindex_path maps a directory to .lexibrary/<dir>/.aindex."""
    result = aindex_path(tmp_path, tmp_path / "src" / "auth")
    assert result == tmp_path / ".lexibrary" / "src" / "auth" / ".aindex"


def test_aindex_path_relative(tmp_path: Path) -> None:
    """aindex_path accepts a project-relative path."""
    result = aindex_path(tmp_path, Path("src/auth"))
    assert result == tmp_path / ".lexibrary" / "src" / "auth" / ".aindex"


# ---------------------------------------------------------------------------
# iwh_path
# ---------------------------------------------------------------------------


def test_iwh_path_subdirectory(tmp_path: Path) -> None:
    """iwh_path maps a subdirectory to .lexibrary/<dir>/.iwh."""
    result = iwh_path(tmp_path, tmp_path / "src" / "auth")
    assert result == tmp_path / ".lexibrary" / "src" / "auth" / ".iwh"


def test_iwh_path_project_root(tmp_path: Path) -> None:
    """iwh_path maps the project root itself to .lexibrary/.iwh."""
    result = iwh_path(tmp_path, tmp_path)
    assert result == tmp_path / ".lexibrary" / ".iwh"


def test_iwh_path_nested_directory(tmp_path: Path) -> None:
    """iwh_path preserves full directory depth for nested paths."""
    result = iwh_path(tmp_path, tmp_path / "src" / "auth" / "middleware")
    assert result == tmp_path / ".lexibrary" / "src" / "auth" / "middleware" / ".iwh"


def test_iwh_path_relative(tmp_path: Path) -> None:
    """iwh_path accepts a project-relative path."""
    result = iwh_path(tmp_path, Path("src/auth"))
    assert result == tmp_path / ".lexibrary" / "src" / "auth" / ".iwh"
