# iwh/reader

**Summary:** High-level reader functions for IWH files: non-destructive `read_iwh()` and consume-on-read `consume_iwh()` that always deletes the file (even if corrupt).

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `IWH_FILENAME` | `str = ".iwh"` | Canonical filename for IWH signal files |
| `read_iwh` | `(directory: Path) -> IWHFile \| None` | Read `.iwh` from directory without deleting; returns `None` if missing or invalid |
| `consume_iwh` | `(directory: Path) -> IWHFile \| None` | Read `.iwh` from directory and delete it; always deletes even if parse fails (corrupt cleanup) |

## Dependencies

- `lexibrarian.iwh.model` -- `IWHFile`
- `lexibrarian.iwh.parser` -- `parse_iwh`

## Dependents

- `lexibrarian.iwh.__init__` -- re-exports both functions

## Key Concepts

- `consume_iwh()` implements "read-once" semantics: the file is always removed after reading, ensuring corrupt files do not block subsequent agents
- Both functions take a directory path (not a file path) and append `IWH_FILENAME` internally
