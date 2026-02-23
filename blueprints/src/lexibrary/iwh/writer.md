# iwh/writer

**Summary:** Writes IWH signal files to disk with automatic directory creation and overwrite semantics (latest signal wins).

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `IWH_FILENAME` | `str = ".iwh"` | Canonical filename for IWH signal files |
| `write_iwh` | `(directory: Path, *, author: str, scope: IWHScope, body: str = "") -> Path` | Create an `IWHFile` with current UTC timestamp, serialize it, write to `directory/.iwh`; creates parent dirs; overwrites existing; returns path to written file |

## Dependencies

- `lexibrarian.iwh.model` -- `IWHFile`, `IWHScope`
- `lexibrarian.iwh.serializer` -- `serialize_iwh`

## Dependents

- `lexibrarian.iwh.__init__` -- re-exports `write_iwh`

## Key Concepts

- Overwrites any existing `.iwh` file in the directory -- only the latest signal matters
- Automatically creates parent directories (`mkdir(parents=True, exist_ok=True)`)
- Timestamps use `datetime.now(UTC)` for consistent UTC creation times
