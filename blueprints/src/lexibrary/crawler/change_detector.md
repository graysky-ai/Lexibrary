# crawler/change_detector

**Summary:** SHA-256 hash-based file change detection with a JSON cache persisted at `.lexibrary/.lexibrarian_cache.json`.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `FileState` | `@dataclass` | Cached state: `hash`, `tokens`, `summary`, `last_indexed` (ISO timestamp) |
| `CrawlCache` | class | Serializable dict of `str → FileState`; `to_dict()` / `from_dict()` |
| `ChangeDetector` | class | Main API: load/save cache, check/update per-file state |
| `ChangeDetector.load` | `() -> None` | Load cache from disk; no-op if file missing; resets on corrupt cache |
| `ChangeDetector.save` | `() -> None` | Write cache to disk if dirty |
| `ChangeDetector.has_changed` | `(path: Path) -> bool` | True if file is new or hash differs |
| `ChangeDetector.get_cached` | `(path: Path) -> FileState | None` | Return cached state or None |
| `ChangeDetector.update` | `(path, file_hash, tokens, summary) -> None` | Store new state, mark dirty |
| `ChangeDetector.prune_deleted` | `(existing_paths: set[str]) -> None` | Remove stale entries for deleted files |
| `ChangeDetector.clear` | `() -> None` | Wipe all cached entries |

## Dependencies

- `lexibrarian.utils.hashing` — `hash_file`

## Dependents

- `lexibrarian.crawler.engine` — instantiates and drives `ChangeDetector`
- `lexibrarian.daemon.service` — instantiates and passes to `full_crawl`

## Key Concepts

- Cache version (`_CACHE_VERSION = 1`) guards against format changes; corrupt or version-mismatch resets to empty
- Keys are absolute path strings
