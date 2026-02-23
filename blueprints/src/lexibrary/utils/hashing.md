# utils/hashing

**Summary:** Computes SHA-256 content hashes for files in chunks, used by change detection to identify modified files.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `hash_file` | `(file_path: Path, chunk_size: int = 8192) -> str` | Return 64-char hex SHA-256 digest; raises `OSError` if unreadable |

## Dependents

- `lexibrarian.crawler.change_detector` — calls `hash_file` to check/store state
- `lexibrarian.crawler.engine` — calls `hash_file` directly on changed files
