# utils/paths

**Summary:** Computes mirrored output paths inside `.lexibrary/` for design files (`.md`), directory indexes (`.aindex`), and IWH signal files (`.iwh`).

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `mirror_path` | `(project_root: Path, source_file: Path) -> Path` | Map `src/auth/login.py` -> `.lexibrary/src/auth/login.py.md` |
| `aindex_path` | `(project_root: Path, directory: Path) -> Path` | Map `src/auth/` -> `.lexibrary/src/auth/.aindex` |
| `iwh_path` | `(project_root: Path, source_directory: Path) -> Path` | Map `src/auth/` -> `.lexibrary/src/auth/.iwh` |
| `LEXIBRARY_DIR` | `str = ".lexibrary"` | Constant for the output directory name |

## Dependents

- Used by artifact writers, lookup commands, and IWH path computation
