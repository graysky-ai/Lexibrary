"""SHA-256 hash-based change detection with JSON cache persistence."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from lexibrary.utils.hashing import hash_file

logger = logging.getLogger(__name__)

_CACHE_VERSION = 1


@dataclass
class FileState:
    """Cached state for a single file."""

    hash: str
    tokens: int
    summary: str
    last_indexed: str


class CrawlCache:
    """Serializable cache mapping file paths to their state."""

    def __init__(self) -> None:
        self.entries: dict[str, FileState] = {}

    def to_dict(self) -> dict[str, object]:
        return {
            "version": _CACHE_VERSION,
            "files": {k: asdict(v) for k, v in self.entries.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> CrawlCache:
        if data.get("version") != _CACHE_VERSION:
            msg = f"Unsupported cache version: {data.get('version')}"
            raise ValueError(msg)

        cache = cls()
        files = data.get("files", {})
        if isinstance(files, dict):
            for key, val in files.items():
                if isinstance(val, dict):
                    cache.entries[key] = FileState(
                        hash=val["hash"],
                        tokens=val["tokens"],
                        summary=val["summary"],
                        last_indexed=val["last_indexed"],
                    )
        return cache


class ChangeDetector:
    """Detect file changes via SHA-256 hash comparison with persistent cache."""

    def __init__(self, cache_path: Path) -> None:
        self._cache_path = cache_path
        self._cache = CrawlCache()
        self._dirty = False

    def load(self) -> None:
        """Load cache from disk. No-op if file doesn't exist."""
        if not self._cache_path.exists():
            return

        try:
            data = json.loads(self._cache_path.read_text(encoding="utf-8"))
            self._cache = CrawlCache.from_dict(data)
        except (json.JSONDecodeError, ValueError, KeyError, TypeError):
            logger.warning("Corrupted cache at %s, starting fresh", self._cache_path)
            self._cache = CrawlCache()

        self._dirty = False

    def save(self) -> None:
        """Save cache to disk if dirty."""
        if not self._dirty:
            return

        self._cache_path.write_text(
            json.dumps(self._cache.to_dict(), indent=2),
            encoding="utf-8",
        )
        self._dirty = False

    def has_changed(self, path: Path) -> bool:
        """Check if a file has changed since last indexing.

        Returns True for new files or files with different hashes.
        """
        key = str(path)
        entry = self._cache.entries.get(key)
        if entry is None:
            return True

        try:
            current_hash = hash_file(path)
        except OSError:
            return True

        return current_hash != entry.hash

    def get_cached(self, path: Path) -> FileState | None:
        """Get cached state for a file, or None if not cached."""
        return self._cache.entries.get(str(path))

    def update(
        self,
        path: Path,
        file_hash: str,
        tokens: int,
        summary: str,
    ) -> None:
        """Update the cache entry for a file."""
        self._cache.entries[str(path)] = FileState(
            hash=file_hash,
            tokens=tokens,
            summary=summary,
            last_indexed=datetime.now(UTC).isoformat(),
        )
        self._dirty = True

    def prune_deleted(self, existing_paths: set[str]) -> None:
        """Remove cache entries for files that no longer exist."""
        to_remove = [k for k in self._cache.entries if k not in existing_paths]
        for key in to_remove:
            del self._cache.entries[key]
        if to_remove:
            self._dirty = True

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.entries.clear()
        self._dirty = True
