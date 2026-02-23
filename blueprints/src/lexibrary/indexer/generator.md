# indexer/generator

**Summary:** Produces `AIndexFile` models from directory contents without I/O side effects -- uses design file frontmatter descriptions when available, with structural fallback.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `generate_aindex` | `(directory, project_root, ignore_matcher, binary_extensions) -> AIndexFile` | Scan directory, build file/dir entries with descriptions, compute staleness hash |

## Dependencies

- `lexibrarian.artifacts.aindex` -- `AIndexEntry`, `AIndexFile`
- `lexibrarian.artifacts.aindex_parser` -- `parse_aindex` (reads child `.aindex` for subdir descriptions)
- `lexibrarian.artifacts.design_file` -- `StalenessMetadata`
- `lexibrarian.artifacts.design_file_parser` -- `parse_design_file_frontmatter` (reads design file descriptions)
- `lexibrarian.ignore.matcher` -- `IgnoreMatcher`
- `lexibrarian.utils.hashing` -- `hash_string`
- `lexibrarian.utils.languages` -- `EXTENSION_MAP`
- `lexibrarian.utils.paths` -- `mirror_path`

## Dependents

- `lexibrarian.indexer.orchestrator` -- calls `generate_aindex` as first step

## Key Concepts

- File description priority: (1) design file frontmatter `description` from `.lexibrary` mirror tree, (2) structural fallback `"<Language> source (<N> lines)"` for text or `"Binary file (<ext>)"` for binary
- Subdir description: reads child `.aindex` from `.lexibrary` mirror if available; falls back to filesystem item count
- Billboard: auto-generated sentence from detected languages (e.g. `"Mixed-language directory (Python, TOML)."`)
- Staleness hash: SHA-256 of sorted directory listing (entry names only, not file contents)
- `_GENERATOR_ID = "lexibrarian-v2"` stamped into metadata
