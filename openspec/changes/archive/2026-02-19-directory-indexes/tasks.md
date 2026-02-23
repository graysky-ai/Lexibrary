## 1. Config and Data Model Updates

- [x] 1.1 Add `CrawlConfig` with `binary_extensions: list[str]` to `src/lexibrary/config/schema.py` and wire into `LexibraryConfig`
- [x] 1.2 Update `src/lexibrary/config/defaults.py` if YAML template needs a `crawl:` section
- [x] 1.3 Replace `AIndexEntry.is_directory: bool` with `entry_type: Literal["file", "dir"]` in `src/lexibrary/artifacts/aindex.py`
- [x] 1.4 Update tests in `tests/test_config/test_schema.py` for `CrawlConfig` defaults and override
- [x] 1.5 Update tests in `tests/test_artifacts/test_models.py` to use `entry_type` instead of `is_directory`

## 2. Artifact Serializer

- [x] 2.1 Create `src/lexibrary/artifacts/aindex_serializer.py` with `serialize_aindex(data: AIndexFile) -> str`
- [x] 2.2 Implement v2 format: H1 heading, billboard, Child Map table (files before dirs, alphabetical each group), Local Conventions section, staleness metadata HTML comment footer
- [x] 2.3 Create `tests/test_artifacts/test_aindex_serializer.py` with all serializer scenarios from spec

## 3. Artifact Parser

- [x] 3.1 Create `src/lexibrary/artifacts/aindex_parser.py` with `parse_aindex(path: Path) -> AIndexFile | None`
- [x] 3.2 Implement `parse_aindex_metadata(path: Path) -> StalenessMetadata | None` in same module
- [x] 3.3 Create `tests/test_artifacts/test_aindex_parser.py` with all parser scenarios from spec

## 4. Round-Trip Test

- [x] 4.1 Create `tests/test_artifacts/test_aindex_roundtrip.py` verifying serialize → write → parse produces identical `AIndexFile`
- [x] 4.2 Add round-trip tests for empty directory, local conventions, and Unicode names/descriptions

## 5. Atomic Writer

- [x] 5.1 Create `src/lexibrary/artifacts/writer.py` with `write_artifact(target: Path, content: str) -> Path`
- [x] 5.2 Implement write-to-temp-then-rename pattern with `parents=True` directory creation
- [x] 5.3 Create `tests/test_artifacts/test_writer.py` with all writer scenarios from spec

## 6. Index Generator

- [x] 6.1 Create `src/lexibrary/indexer/__init__.py` (module init)
- [x] 6.2 Create `src/lexibrary/indexer/generator.py` with `generate_aindex()` function and extension-to-language mapping
- [x] 6.3 Implement file description logic: language + line count for text files, binary description for binary extensions
- [x] 6.4 Implement directory description logic: use child `.aindex` entry counts if available, fall back to direct listing
- [x] 6.5 Implement billboard generation: dominant language, mixed-language, binary-only, or empty directory
- [x] 6.6 Create `tests/test_indexer/test_generator.py` with all generator scenarios from spec (using `tmp_path`)

## 7. Index Orchestrator

- [x] 7.1 Create `src/lexibrary/indexer/orchestrator.py` with `IndexStats` dataclass, `index_directory()`, and `index_recursive()`
- [x] 7.2 Implement `index_directory()`: generator → serializer → writer pipeline, compute mirror output path
- [x] 7.3 Implement `index_recursive()`: bottom-up directory discovery, call `index_directory()` for each, invoke progress callback
- [x] 7.4 Ensure `.lexibrary/` itself is excluded from recursive indexing
- [x] 7.5 Create `tests/test_indexer/test_orchestrator.py` with all orchestrator scenarios from spec (using `tmp_path`)

## 8. CLI Integration

- [x] 8.1 Replace `lexi index` stub in `src/lexibrary/cli.py` with real implementation using `-r`/`--recursive` flag
- [x] 8.2 Add project root validation (error if no `.lexibrary/` found) and directory validation (exists, within project root)
- [x] 8.3 Wire `--recursive` to `index_recursive()` with Rich progress bar; single mode to `index_directory()`
- [x] 8.4 Print summary stats on completion using `rich.console.Console`
- [x] 8.5 Add CLI tests in `tests/test_cli.py` for single index, recursive index, missing project, missing dir, outside-project-root

## 9. Test Fixtures and Verification

- [x] 9.1 Extend `tests/fixtures/sample_project/` with `src/utils/` subdirectory (2-3 Python files), `assets/logo.png` (binary), `.gitignore` ignoring `build/`, and `build/` directory
- [x] 9.2 Run `uv run pytest tests/ -v` — all tests pass
- [x] 9.3 Run `uv run ruff check src/ tests/` — linting passes
- [x] 9.4 Run `uv run mypy src/` — type checking passes
