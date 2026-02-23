## Why

Phase 1 delivered the foundational data models, config system, CLI skeleton, and project init. Phase 2 makes `lexi index` functional: it produces `.aindex` files inside the `.lexibrary/` mirror tree so that agents can navigate the codebase via directory indexes without loading individual source files.

## What Changes

- **New**: `.aindex` markdown serializer (`artifacts/aindex_serializer.py`) — converts `AIndexFile` model to v2 markdown format
- **New**: `.aindex` markdown parser (`artifacts/aindex_parser.py`) — parses v2 `.aindex` files back into `AIndexFile` models
- **New**: Atomic file writer (`artifacts/writer.py`) — generic write-to-temp-then-rename utility
- **New**: Index generator (`indexer/generator.py`) — produces structural `AIndexFile` for a single directory (no LLM)
- **New**: Index orchestrator (`indexer/orchestrator.py`) — single-directory and recursive bottom-up indexing pipelines
- **Modified**: `AIndexEntry` model — replace `is_directory: bool` with `entry_type: Literal["file", "dir"]` (**BREAKING** to model, no persisted data yet)
- **Modified**: `CrawlConfig` — add `binary_extensions: list[str]` field alongside existing fields
- **Modified**: `lexi index` CLI command — replace stub with real implementation using `-r`/`--recursive` flag
- **New test fixtures**: `tests/fixtures/sample_project/` extended with binary file, subdirectory, build dir

## Capabilities

### New Capabilities

- `aindex-serializer`: Serialize `AIndexFile` Pydantic model to v2 `.aindex` markdown format with Child Map table, Local Conventions section, and staleness metadata HTML footer
- `aindex-parser`: Parse v2 `.aindex` markdown files back into `AIndexFile` models; also supports metadata-only parse for cheap staleness checks
- `artifact-writer`: Atomic file write utility — write to temp file then rename, creating parent directories as needed
- `index-generator`: Generate structural `AIndexFile` for a directory using directory listing + language detection + line counting (no LLM)
- `index-orchestrator`: Orchestrate single-directory and bottom-up recursive indexing, writing `.aindex` files to `.lexibrary/` mirror tree

### Modified Capabilities

- `iandex-data-models`: Replace `is_directory: bool` with `entry_type: Literal["file", "dir"]` on `AIndexEntry`; add `AIndexFile.local_conventions` field and `StalenessMetadata` model
- `cli-commands`: Implement `lexi index <directory> [-r/--recursive]` with Rich progress display and summary stats
- `config-system`: Add `binary_extensions: list[str]` to `CrawlConfig` (alongside existing fields)

## Impact

- **Files changed**: `src/lexibrary/artifacts/aindex.py`, `src/lexibrary/config/schema.py`, `src/lexibrary/cli.py`
- **Files added**: `src/lexibrary/artifacts/aindex_serializer.py`, `src/lexibrary/artifacts/aindex_parser.py`, `src/lexibrary/artifacts/writer.py`, `src/lexibrary/indexer/generator.py`, `src/lexibrary/indexer/orchestrator.py`
- **Test files added**: `tests/test_artifacts/test_aindex_serializer.py`, `tests/test_artifacts/test_aindex_parser.py`, `tests/test_artifacts/test_aindex_roundtrip.py`, `tests/test_artifacts/test_writer.py`, `tests/test_indexer/test_generator.py`, `tests/test_indexer/test_orchestrator.py`
- **Dependencies**: No new external deps — uses existing `pathspec`, `pydantic`, `rich`, `typer`, `hashlib` (stdlib)
- **Breaking change**: `AIndexEntry.is_directory` removed; all code referencing it updated in same change
