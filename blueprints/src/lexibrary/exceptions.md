# exceptions

**Summary:** Project-level exception classes; currently a single error type for missing `.lexibrary/` directory.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `LexibraryNotFoundError` | `Exception` | Raised when no `.lexibrary/` found walking up from start path |

## Dependents

- `lexibrary.utils.root` — raises it in `find_project_root()`
- `lexibrary.cli` — catches it in `_require_project_root()`
