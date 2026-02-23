## 1. Design File Models, Serializer, and Parser

- [x] 1.1 Add `DesignFileFrontmatter` model to `src/lexibrary/artifacts/design_file.py` with `description` (str) and `updated_by` (Literal["archivist", "agent"])
- [x] 1.2 Add `design_hash` (str) field to `StalenessMetadata` model
- [x] 1.3 Add `frontmatter` (DesignFileFrontmatter) field to `DesignFile` model
- [x] 1.4 Update `src/lexibrary/artifacts/__init__.py` to re-export `DesignFileFrontmatter`
- [x] 1.5 Create `src/lexibrary/artifacts/design_file_serializer.py` with `serialize_design_file(DesignFile) -> str` producing YAML frontmatter + markdown body + HTML comment footer
- [x] 1.6 Create `src/lexibrary/artifacts/design_file_parser.py` with `parse_design_file()`, `parse_design_file_metadata()`, and `parse_design_file_frontmatter()`
- [x] 1.7 Write tests: `tests/test_artifacts/test_design_file_serializer.py` (full, minimal, frontmatter, footer)
- [x] 1.8 Write tests: `tests/test_artifacts/test_design_file_parser.py` (full, metadata-only, frontmatter-only, nonexistent, no footer, corrupt footer)
- [x] 1.9 Write tests: `tests/test_artifacts/test_design_file_roundtrip.py` (round-trip with all fields, optional sections, agent edit detection)

## 2. BAML Functions and Client Configuration

- [x] 2.1 Spike: verify BAML `ClientRegistry` Python API supports runtime client override for individual function calls — document outcome
- [x] 2.2 Add `DesignFileOutput`, `DesignFileDependency`, `StartHereOutput` types to `baml_src/types.baml`
- [x] 2.3 Create `baml_src/archivist_design_file.baml` with `ArchivistGenerateDesignFile` function and prompt
- [x] 2.4 Create `baml_src/archivist_start_here.baml` with `ArchivistGenerateStartHere` function and prompt
- [x] 2.5 Add `AnthropicArchivist` and `OpenAIArchivist` clients to `baml_src/clients.baml` with `max_tokens: 1500`
- [x] 2.6 Run `baml-cli generate` and verify generated Python client includes new types and functions

## 3. .lexignore Support and Scope Root Config

- [x] 3.1 Update `src/lexibrary/ignore/matcher.py` — add `lexignore_patterns` parameter to `IgnoreMatcher.__init__()` and update `create_ignore_matcher()` to load `.lexignore`
- [x] 3.2 Add `scope_root: str = "."` field to `LexibraryConfig` in `src/lexibrary/config/schema.py`
- [x] 3.3 Add `max_file_size_kb: int = 512` to `CrawlConfig` in `src/lexibrary/config/schema.py`
- [x] 3.4 Update `src/lexibrary/config/defaults.py` config template with `scope_root` and `max_file_size_kb`
- [x] 3.5 Update `src/lexibrary/init/scaffolder.py` to create empty `.lexignore` file on `lexi init`
- [x] 3.6 Write tests: `tests/test_ignore/test_matcher.py` — lexignore loaded, lexignore missing OK, three-layer merge
- [x] 3.7 Write tests: config schema tests for `scope_root` and `max_file_size_kb` defaults

## 4. Change Checker

- [x] 4.1 Create `src/lexibrary/archivist/__init__.py` with public API exports
- [x] 4.2 Create `src/lexibrary/archivist/change_checker.py` with `ChangeLevel` enum and `check_change()` function
- [x] 4.3 Write tests: `tests/test_archivist/test_change_checker.py` — new file, footerless, unchanged, agent updated, content only, interface changed, content changed (non-code)

## 5. Dependency Extractor

- [x] 5.1 Create `src/lexibrary/archivist/dependency_extractor.py` with `extract_dependencies()`, `_resolve_python_import()`, `_resolve_js_import()`
- [x] 5.2 Write tests: `tests/test_archivist/test_dependency_extractor.py` — Python imports, relative imports, third-party excluded, TypeScript/JS imports, non-code empty, unresolvable omitted
- [x] 5.3 Create test fixtures: `tests/test_archivist/fixtures/sample_source.py`, `sample_source.ts`, `sample_config.yaml`

## 6. Archivist Service

- [x] 6.1 Create `src/lexibrary/archivist/service.py` with `ArchivistService`, `DesignFileRequest`, `DesignFileResult`, `StartHereRequest`, `StartHereResult`
- [x] 6.2 Implement BAML client selection based on `LLMConfig.provider` (using ClientRegistry or env var fallback per spike outcome)
- [x] 6.3 Write tests: `tests/test_archivist/test_service.py` — mocked BAML calls, rate limiting, error handling, provider routing

## 7. Archivist Pipeline

- [x] 7.1 Create `src/lexibrary/archivist/pipeline.py` with `update_file()` async function and `UpdateStats` dataclass
- [x] 7.2 Implement `update_project()` async function with file discovery, filtering, sequential processing
- [x] 7.3 Implement token budget validation (warn on oversized, still write, increment counter)
- [x] 7.4 Implement parent `.aindex` refresh on file update (parse, update Child Map entry, re-serialize)
- [x] 7.5 Write tests: `tests/test_archivist/test_pipeline.py` — new file, unchanged, agent updated, footerless, content only, content changed, interface changed, outside scope, .aindex refresh, project discovery, binary skip, .lexibrary skip, stats, token budget warning

## 8. START_HERE.md Generation

- [x] 8.1 Create `src/lexibrary/archivist/start_here.py` with `generate_start_here()` async function
- [x] 8.2 Implement directory tree building, .aindex summary collection, LLM call, token budget validation
- [x] 8.3 Write tests: `tests/test_archivist/test_start_here.py` — generates START_HERE, collects summaries, excludes .lexibrary, token budget

## 9. CLI Commands

- [x] 9.1 Add `lexi update [<path>]` command to `src/lexibrary/cli.py` with Rich progress bar and summary stats
- [x] 9.2 Add `lexi lookup <file>` command with scope check, staleness warning, and content display
- [x] 9.3 Add `lexi describe <directory> "<description>"` command for .aindex billboard updates
- [x] 9.4 Write tests: `tests/test_cli.py` — update single file, update directory, update project, no project error, lookup exists, lookup missing, lookup stale, lookup outside scope, describe directory

## 10. .aindex Integration

- [x] 10.1 Update `src/lexibrary/indexer/generator.py` to pull file descriptions from design file frontmatter with structural fallback
- [x] 10.2 Write tests: `tests/test_indexer/test_generator.py` — frontmatter description used, structural fallback, empty description fallback

## 11. Blueprints Update

- [x] 11.1 Create design files in `blueprints/src/lexibrary/archivist/` for all new archivist modules
- [x] 11.2 Update existing blueprints for modified files (cli.py, artifacts/, ignore/, indexer/, config/)
