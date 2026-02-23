# artifacts/aindex_serializer

**Summary:** Serializes `AIndexFile` models to v2 `.aindex` markdown format.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `serialize_aindex` | `(data: AIndexFile) -> str` | Render AIndexFile to markdown string with H1, billboard, Child Map, Local Conventions, and metadata footer |

## Dependencies

- `lexibrarian.artifacts.aindex` — `AIndexFile`

## Dependents

- `lexibrarian.indexer.orchestrator` — serializes model before writing to disk

## Key Concepts

- Child Map: files sorted alphabetically first, then directories; dirs shown with trailing `/`
- Metadata footer: `<!-- lexibrarian:meta source="..." source_hash="..." generated="..." generator="..." -->`
- `interface_hash` is omitted from the footer when `None`
- Empty entries section renders `(none)`; empty conventions section renders `(none)`
