# artifacts/writer

**Summary:** Atomic artifact file writer — writes UTF-8 content via a temp file then renames into place to prevent partial writes.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `write_artifact` | `(target: Path, content: str) -> Path` | Write content atomically to target, creating parent dirs if needed; returns target path |

## Dependencies

- None (stdlib only: `os`, `tempfile`, `pathlib`)

## Dependents

- `lexibrarian.indexer.orchestrator` — writes `.aindex` files

## Key Concepts

- Uses `tempfile.mkstemp` in the same directory as target then `Path.rename()` for atomic POSIX swap
- Cleans up temp file on any exception
- Parent directories are created automatically via `mkdir(parents=True, exist_ok=True)`
