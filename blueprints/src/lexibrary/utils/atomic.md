# utils/atomic

**Summary:** Atomic file write utility using temp-file + `os.replace()` to ensure readers never see partially-written files.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `atomic_write` | `(target: Path, content: str, encoding: str = "utf-8") -> None` | Write content atomically; creates parent dirs if needed; raises `OSError` on failure (original file unchanged, temp cleaned up) |

## Dependencies

- None (stdlib only: `os`, `tempfile`, `contextlib`, `pathlib`)

## Dependents

- `lexibrarian.archivist.pipeline` -- all design file writes (`update_file`, `_refresh_footer_hashes`, `_refresh_parent_aindex`) use `atomic_write` instead of `Path.write_text()`

## Key Concepts

- Creates a temp file in the **same directory** as the target (via `tempfile.mkstemp(dir=target.parent)`) to ensure `os.replace()` is atomic (same filesystem)
- Parent directories are created with `mkdir(parents=True, exist_ok=True)` before writing
- On failure, the temp file is cleaned up in a `finally` block; the original target file is never corrupted
- File descriptor is managed manually (`os.write` / `os.close`) rather than using Python file objects for precise control over cleanup
