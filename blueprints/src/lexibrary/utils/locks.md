# utils/locks

**Summary:** Per-directory write lock manager providing `threading.Lock` instances keyed by resolved directory path, for serialising `.aindex` writes.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `DirectoryLockManager` | class | Provides per-directory `threading.Lock` instances |
| `DirectoryLockManager.get_lock` | `(directory: Path) -> threading.Lock` | Return the lock for a directory; creates one atomically if none exists; paths are resolved before lookup |

## Dependencies

- None (stdlib only: `threading`, `pathlib`)

## Key Concepts

- Thread-safe: a `_guard` lock protects the internal `_locks` dict so concurrent calls to `get_lock` for the same directory always return the same `Lock` instance
- Paths are resolved (via `Path.resolve()`) before lookup, so different representations of the same directory map to the same lock
- Under the current sequential MVP processing model the locks are effectively no-ops (no contention), but they ensure correctness when async / concurrent processing is added later
