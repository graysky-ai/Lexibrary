# iwh/gitignore

**Summary:** Ensures `.iwh` files are listed in the project's `.gitignore` with idempotent append and alternative pattern recognition.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `IWH_GITIGNORE_PATTERN` | `str = "**/.iwh"` | Canonical gitignore pattern appended to `.gitignore` |
| `ensure_iwh_gitignored` | `(project_root: Path) -> bool` | Idempotently add `**/.iwh` to `.gitignore`; returns `True` if file was modified/created, `False` if pattern already present |

## Dependencies

- None (only pathlib)

## Dependents

- `lexibrarian.iwh.__init__` -- re-exports `ensure_iwh_gitignored`
- `lexibrarian.init.scaffolder` -- calls during `create_lexibrary_skeleton()` and `create_lexibrary_from_wizard()`
- `lexibrarian.cli.lexictl_app` -- `setup --update` calls it

## Key Concepts

- Recognises alternative equivalent patterns (`**/.iwh`, `.iwh`, `.lexibrary/**/.iwh`) to avoid duplicate entries
- Creates `.gitignore` if it does not exist
- Appends with proper newline handling (ensures newline before pattern if file doesn't end with one)
