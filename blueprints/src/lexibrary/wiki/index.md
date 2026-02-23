# wiki/index

**Summary:** In-memory index of concept files for search and retrieval by title, alias, tag, or substring.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `ConceptIndex` | `class` | In-memory map of `ConceptFile` keyed by title |
| `ConceptIndex.load` | `classmethod (concepts_dir: Path) -> ConceptIndex` | Scan directory for `*.md` files, parse each, and build index; silently skips unparseable files |
| `ConceptIndex.names` | `() -> list[str]` | Return sorted list of all concept titles |
| `ConceptIndex.find` | `(name: str) -> ConceptFile | None` | Exact title or alias match (case-insensitive) |
| `ConceptIndex.search` | `(query: str) -> list[ConceptFile]` | Substring match across titles, aliases, tags, and summaries; results sorted by title |
| `ConceptIndex.by_tag` | `(tag: str) -> list[ConceptFile]` | Return all concepts with a given tag (case-insensitive); results sorted by title |
| `ConceptIndex.__len__` | `() -> int` | Number of concepts in the index |
| `ConceptIndex.__contains__` | `(name: str) -> bool` | True if `find(name)` returns a result |

## Dependencies

- `lexibrarian.artifacts.concept` — `ConceptFile`
- `lexibrarian.wiki.parser` — `parse_concept_file`

## Dependents

- `lexibrarian.wiki.__init__` — re-exports
- `lexibrarian.wiki.resolver` — `WikilinkResolver` queries the index
