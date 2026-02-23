# indexer/orchestrator

**Summary:** Coordinates generation, serialization, and atomic writing of `.aindex` files for single directories or full recursive trees.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `IndexStats` | `@dataclass` | Counters: `directories_indexed`, `files_found`, `errors` |
| `index_directory` | `(directory, project_root, config) -> Path` | Generate and write one `.aindex`; returns output path |
| `index_recursive` | `(directory, project_root, config, *, progress_callback) -> IndexStats` | Bottom-up recursive indexing of all subdirs; returns stats |

## Dependencies

- `lexibrarian.artifacts.aindex_serializer` — `serialize_aindex`
- `lexibrarian.artifacts.writer` — `write_artifact`
- `lexibrarian.config.schema` — `LexibraryConfig`
- `lexibrarian.ignore` — `create_ignore_matcher`
- `lexibrarian.indexer.generator` — `generate_aindex`

## Dependents

- `lexibrarian.cli` — `index` command calls both `index_directory` and `index_recursive`

## Key Concepts

- Output path: `<project_root>/.lexibrary/<rel_dir>/.aindex`
- Recursive traversal skips `.lexibrary/` and any ignore-matched directories
- Bottom-up order ensures child `.aindex` files exist before parents are processed
- `progress_callback(current, total, dir_name)` is optional; invoked after each directory
