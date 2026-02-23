"""Tests for per-directory write lock manager."""

from __future__ import annotations

import threading
from pathlib import Path

from lexibrary.utils.locks import DirectoryLockManager


def test_same_directory_returns_same_lock(tmp_path: Path) -> None:
    """get_lock() called twice with the same directory returns the same Lock."""
    mgr = DirectoryLockManager()
    lock_a = mgr.get_lock(tmp_path)
    lock_b = mgr.get_lock(tmp_path)

    assert lock_a is lock_b


def test_different_directories_return_different_locks(tmp_path: Path) -> None:
    """get_lock() called with different directories returns different Locks."""
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()

    mgr = DirectoryLockManager()
    lock_a = mgr.get_lock(dir_a)
    lock_b = mgr.get_lock(dir_b)

    assert lock_a is not lock_b


def test_lock_is_threading_lock(tmp_path: Path) -> None:
    """get_lock() should return an instance of threading.Lock."""
    mgr = DirectoryLockManager()
    lock = mgr.get_lock(tmp_path)

    # threading.Lock() returns a _thread.lock instance; the canonical
    # check is that it has acquire/release and is the type returned by
    # threading.Lock().
    assert isinstance(lock, type(threading.Lock()))
