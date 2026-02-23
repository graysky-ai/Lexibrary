# utils/root

**Summary:** Walks upward from the start directory looking for a `.lexibrary/` directory to locate the project root.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `find_project_root` | `(start: Path | None = None) -> Path` | Return project root containing `.lexibrary/`; defaults to `Path.cwd()` |

## Dependencies

- `lexibrarian.exceptions` — raises `LexibraryNotFoundError` if not found

## Dependents

- `lexibrarian.utils.__init__` — re-exports
- `lexibrarian.cli` — calls via `_require_project_root()`
