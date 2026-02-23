## Why

Lexibrary needs a well-defined file format for its `.aindex` index files — the Markdown documents placed in each directory that give AI agents a quick navigational map of the codebase. Without a structured format with generation, writing, and parsing capabilities, the crawler (Phase 5) has no way to produce or consume index files. This is a core building block that must exist before the crawl engine can be assembled.

## What Changes

- Introduce `IandexData`, `FileEntry`, and `DirEntry` dataclasses as the canonical in-memory representation of an `.aindex` file
- Add a generator that transforms `IandexData` into a precisely formatted Markdown string (sorted tables, backtick-wrapped filenames, trailing slashes on directories, `(none)` for empty sections)
- Add an atomic writer that safely persists `.aindex` content to disk using temp-file-then-rename
- Add a parser that reads existing `.aindex` files back into `IandexData` (used for incremental crawls to reuse cached summaries)
- Add a round-trip guarantee: `generate → write → parse` produces identical data

## Capabilities

### New Capabilities
- `iandex-data-models`: Dataclasses (`IandexData`, `FileEntry`, `DirEntry`) that represent the structured contents of a single `.aindex` file
- `iandex-generator`: Transforms `IandexData` into precisely formatted Markdown following the `.aindex` format specification
- `iandex-writer`: Atomically writes `.aindex` content to disk, preventing corruption from interrupted writes
- `iandex-parser`: Parses existing `.aindex` Markdown files back into `IandexData` for cache reuse during incremental crawls

### Modified Capabilities
(none)

## Impact

- **New code**: `src/lexibrary/indexer/` package with `__init__.py`, `generator.py`, `writer.py`, `parser.py`
- **New tests**: `tests/test_indexer/` with tests for generator, writer, parser, and round-trip verification
- **Dependencies**: No new external dependencies — uses only stdlib (`dataclasses`, `re`, `os`, `tempfile`, `pathlib`)
- **Downstream**: Phase 5 (Crawler Engine) will import these modules to produce and consume `.aindex` files
- **Upstream dependency**: Phase 1 must provide the project scaffolding and package structure
