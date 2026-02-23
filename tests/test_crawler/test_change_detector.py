"""Tests for SHA-256 hash-based change detection and cache persistence."""

from __future__ import annotations

import json
from pathlib import Path

from lexibrary.crawler.change_detector import ChangeDetector


def test_new_file_detected_as_changed(tmp_path: Path) -> None:
    """File with no cached entry is detected as changed."""
    f = tmp_path / "new.py"
    f.write_text("pass\n")

    detector = ChangeDetector(tmp_path / "cache.json")
    assert detector.has_changed(f) is True


def test_unchanged_file_not_changed(tmp_path: Path) -> None:
    """File whose hash matches cached hash is not changed."""
    f = tmp_path / "stable.py"
    f.write_text("pass\n")

    detector = ChangeDetector(tmp_path / "cache.json")
    from lexibrary.utils.hashing import hash_file

    detector.update(f, hash_file(f), tokens=5, summary="A module")
    assert detector.has_changed(f) is False


def test_modified_file_detected_as_changed(tmp_path: Path) -> None:
    """File whose hash differs from cached hash is changed."""
    f = tmp_path / "changing.py"
    f.write_text("v1\n")

    detector = ChangeDetector(tmp_path / "cache.json")
    detector.update(f, "oldhash", tokens=3, summary="Old version")

    assert detector.has_changed(f) is True


def test_save_load_roundtrip(tmp_path: Path) -> None:
    """Entries survive save/load cycle with correct fields."""
    cache_path = tmp_path / "cache.json"
    f = tmp_path / "file.py"
    f.write_text("pass\n")

    detector = ChangeDetector(cache_path)
    detector.update(f, "abc123", tokens=42, summary="Test file")
    detector.save()

    detector2 = ChangeDetector(cache_path)
    detector2.load()

    cached = detector2.get_cached(f)
    assert cached is not None
    assert cached.hash == "abc123"
    assert cached.tokens == 42
    assert cached.summary == "Test file"
    assert cached.last_indexed  # Non-empty ISO timestamp


def test_noop_save_when_not_dirty(tmp_path: Path) -> None:
    """Save with no updates does not write the cache file."""
    cache_path = tmp_path / "cache.json"
    detector = ChangeDetector(cache_path)
    detector.save()
    assert not cache_path.exists()


def test_corrupted_cache_starts_fresh(tmp_path: Path) -> None:
    """Invalid JSON cache results in empty cache, no error."""
    cache_path = tmp_path / "cache.json"
    cache_path.write_text("not valid json!!!", encoding="utf-8")

    detector = ChangeDetector(cache_path)
    detector.load()

    assert detector.get_cached(Path("anything")) is None


def test_wrong_version_starts_fresh(tmp_path: Path) -> None:
    """Cache with incompatible version results in empty cache."""
    cache_path = tmp_path / "cache.json"
    cache_path.write_text(json.dumps({"version": 999, "files": {}}), encoding="utf-8")

    detector = ChangeDetector(cache_path)
    detector.load()

    assert detector.get_cached(Path("anything")) is None


def test_missing_cache_file_noop(tmp_path: Path) -> None:
    """Loading from non-existent path is a no-op."""
    detector = ChangeDetector(tmp_path / "nonexistent.json")
    detector.load()  # Should not raise
    assert detector.get_cached(Path("anything")) is None


def test_prune_deleted_files(tmp_path: Path) -> None:
    """Pruning removes entries for files not in the existing set."""
    detector = ChangeDetector(tmp_path / "cache.json")
    detector.update(Path("/a.py"), "h1", tokens=1, summary="a")
    detector.update(Path("/b.py"), "h2", tokens=2, summary="b")
    detector.update(Path("/c.py"), "h3", tokens=3, summary="c")

    detector.prune_deleted({"/a.py", "/c.py"})

    assert detector.get_cached(Path("/a.py")) is not None
    assert detector.get_cached(Path("/b.py")) is None
    assert detector.get_cached(Path("/c.py")) is not None


def test_clear_all_entries(tmp_path: Path) -> None:
    """Clearing removes all entries and marks dirty."""
    cache_path = tmp_path / "cache.json"
    detector = ChangeDetector(cache_path)
    detector.update(Path("/a.py"), "h1", tokens=1, summary="a")
    detector.save()

    detector.clear()
    assert detector.get_cached(Path("/a.py")) is None

    # Save should write since clear marks dirty
    detector.save()
    data = json.loads(cache_path.read_text(encoding="utf-8"))
    assert data["files"] == {}


def test_update_stores_iso_timestamp(tmp_path: Path) -> None:
    """Update stores an ISO 8601 last_indexed timestamp."""
    detector = ChangeDetector(tmp_path / "cache.json")
    detector.update(Path("/f.py"), "hash", tokens=10, summary="test")

    cached = detector.get_cached(Path("/f.py"))
    assert cached is not None
    # Should be parseable as ISO format
    from datetime import datetime

    datetime.fromisoformat(cached.last_indexed)
