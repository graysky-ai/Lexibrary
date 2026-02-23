# ignore/gitignore

**Summary:** Discovers and parses all `.gitignore` files under the project root into pathspec `PathSpec` objects sorted by depth.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `load_gitignore_specs` | `(root: Path) -> list[tuple[Path, PathSpec]]` | Recursively find `.gitignore` files; return `(directory, spec)` pairs sorted root-first |

## Dependencies

- `pathspec` (third-party)

## Dependents

- `lexibrarian.ignore.__init__` — called by `create_ignore_matcher` when `config.ignore.use_gitignore` is True

## Key Concepts

- Uses `"gitignore"` pattern style (not `"gitwildmatch"`)
- Unreadable `.gitignore` files are silently skipped
- Sorted by `len(parts)` so root `.gitignore` is first in the list
