# iwh/reader

**Summary:** High-level reader functions for IWH files: non-destructive `read_iwh()` and consume-on-read `consume_iwh()` that always deletes the file (even if corrupt).

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `IWH_FILENAME` | `str = ".iwh"` | Canonical filename for IWH signal files |
| `read_iwh` | `(directory: Path) -> IWHFile \| None` | Read `.iwh` from directory without deleting; returns `None` if missing or invalid |
| `consume_iwh` | `(directory: Path) -> IWHFile \| None` | Read `.iwh` from directory and delete it; always deletes even if parse fails (corrupt cleanup) |
| `find_all_iwh` | `(project_root: Path) -> list[tuple[Path, IWHFile]]` | Discover all `.iwh` files under `.lexibrary/`; walks via `rglob`, reverses mirror paths to source directories, skips unparseable files, returns sorted list of `(relative_source_dir, IWHFile)` tuples |

## Dependencies

- `lexibrary.iwh.model` -- `IWHFile`
- `lexibrary.iwh.parser` -- `parse_iwh`
- `lexibrary.utils.paths` -- `LEXIBRARY_DIR`

## Dependents

- `lexibrary.iwh.__init__` -- re-exports `read_iwh`, `consume_iwh`, and `find_all_iwh`
- `lexibrary.cli.lexi_app` -- `iwh_list` command uses `find_all_iwh`
- `lexibrary.cli.lexictl_app` -- `iwh_clean` command uses `find_all_iwh` and `IWH_FILENAME`
- `lexibrary.archivist.pipeline` -- `update_file` uses `read_iwh` for IWH awareness

## Key Concepts

- `consume_iwh()` implements "read-once" semantics: the file is always removed after reading, ensuring corrupt files do not block subsequent agents
- Both `read_iwh` and `consume_iwh` take a directory path (not a file path) and append `IWH_FILENAME` internally
- `find_all_iwh()` walks `.lexibrary/` via `rglob(IWH_FILENAME)`, reverses mirror paths by computing `relative_to(lexibrary_dir)` on each parent, silently skips files that fail to parse, and returns results sorted by path
