# artifacts/aindex_parser

**Summary:** Parses v2 `.aindex` markdown files into `AIndexFile` models; also supports cheap metadata-only extraction for staleness checks.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `parse_aindex` | `(path: Path) -> AIndexFile \| None` | Full parse: H1→directory_path, billboard, Child Map table, Local Conventions, metadata footer |
| `parse_aindex_metadata` | `(path: Path) -> StalenessMetadata \| None` | Cheap parse: extracts only the `<!-- lexibrarian:meta ... -->` footer comment |

## Dependencies

- `lexibrarian.artifacts.aindex` — `AIndexEntry`, `AIndexFile`
- `lexibrarian.artifacts.design_file` — `StalenessMetadata`

## Dependents

- `lexibrarian.indexer.generator` — `parse_aindex` reads child `.aindex` for subdir descriptions

## Key Concepts

- Metadata footer format: `<!-- lexibrarian:meta key="val" key="val" -->`
- Returns `None` on missing file, unreadable file, or absent required sections (H1, billboard, metadata footer)
- `parse_aindex_metadata` is cheaper than full parse — only scans for the footer comment
- Tolerant of minor whitespace differences in table rows
