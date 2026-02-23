# utils/conflict

**Summary:** Git conflict marker detection -- checks whether a source file contains unresolved merge conflict markers (`<<<<<<<`) at the start of any line.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `has_conflict_markers` | `(source_path: Path) -> bool` | Return `True` if any line starts with `<<<<<<<`; `False` for clean files, non-existent files, and binary files |

## Dependencies

- None (stdlib only: `pathlib`)

## Dependents

- `lexibrarian.archivist.pipeline` -- `update_file` skips files with conflict markers (returns `FileResult(failed=True)`)

## Key Concepts

- Only markers at the **start of a line** (`<<<<<<<`) are detected; mid-line occurrences are ignored
- Uses `errors="replace"` when opening files to tolerate binary content gracefully
- Returns `False` (not an error) for non-existent files and `OSError`/`FileNotFoundError`
