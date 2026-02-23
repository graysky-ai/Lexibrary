## Why

The Lexibrary library currently generates structural `.aindex` files (language + line count descriptions) and v1 LLM summaries, but has no mechanism for producing rich, per-file **design files** — the core artifact that explains *intent*, interface contracts, dependencies, and architectural context. Phase 4 (Archivist) closes this gap by introducing LLM-powered design file generation with an **agent-first authoring model**: agents write design files during coding sessions, and the Archivist LLM pipeline acts as a safety net for files agents forgot to document.

## What Changes

- **Design file generation pipeline** — `lexi update [<path>]` generates or refreshes design files (YAML frontmatter + markdown body + HTML metadata footer) for all source files within `scope_root`.
- **Agent-first change detection** — `design_hash` in the metadata footer detects when an agent has already updated a design file, avoiding unnecessary LLM regeneration. Footer-less design files (agent-authored from scratch) are trusted, not overwritten.
- **BAML Archivist functions** — New `ArchivistGenerateDesignFile` and `ArchivistGenerateStartHere` BAML functions with per-provider client routing via `ClientRegistry`.
- **Dependency extraction** — Tree-sitter AST-based import extraction resolves forward dependencies to project-relative file paths.
- **`.lexignore` support** — New `.lexignore` file (gitignore format) layered on `.gitignore` + config patterns for Lexibrary-specific exclusions.
- **`scope_root` configuration** — Files within `scope_root` get design files; files outside appear in `.aindex` only.
- **`START_HERE.md` generation** — Project-level synthesis from topology and `.aindex` summaries.
- **`.aindex` enrichment** — Child Map descriptions pulled from design file YAML frontmatter when available, with structural fallback.
- **New CLI commands** — `lexi update`, `lexi lookup`, `lexi describe`.
- **Retirement of v1 summarization** — Old `SummarizeFile`/`SummarizeFilesBatch`/`SummarizeDirectory` BAML functions replaced by Archivist functions.

## Capabilities

### New Capabilities
- `design-file-models`: Design file data models (DesignFileFrontmatter, updated StalenessMetadata with design_hash), serializer, and parser
- `archivist-baml`: BAML function definitions for ArchivistGenerateDesignFile and ArchivistGenerateStartHere, plus per-provider client configuration
- `lexignore`: `.lexignore` file support — three-layer ignore system (gitignore + lexignore + config patterns)
- `scope-root`: Scope root configuration controlling which files get design files
- `archivist-change-detection`: Change checker with agent-awareness (UNCHANGED, AGENT_UPDATED, CONTENT_ONLY, CONTENT_CHANGED, INTERFACE_CHANGED, NEW_FILE)
- `dependency-extraction`: AST-based import extraction and resolution to project-relative file paths
- `archivist-service`: Archivist LLM service wrapping BAML calls with rate limiting and provider routing
- `archivist-pipeline`: Orchestrator pipeline for single-file and full-project design file generation
- `start-here-generation`: START_HERE.md generation from project topology and .aindex summaries

### Modified Capabilities
- `cli-commands`: Adding `lexi update`, `lexi lookup`, and `lexi describe` commands
- `ignore-system`: Extending IgnoreMatcher to load `.lexignore` alongside `.gitignore`
- `config-system`: Adding `scope_root` to LexibraryConfig, `max_file_size_kb` to CrawlConfig
- `artifact-data-models`: Adding DesignFileFrontmatter model, design_hash to StalenessMetadata
- `iandex-generator`: Updating .aindex generation to pull descriptions from design file frontmatter

## Impact

- **New module**: `src/lexibrary/archivist/` (change_checker, dependency_extractor, pipeline, service, start_here)
- **New module**: `src/lexibrary/artifacts/design_file_serializer.py`, `design_file_parser.py`
- **Modified**: `src/lexibrary/ignore/matcher.py` (lexignore loading), `src/lexibrary/config/schema.py` (scope_root, max_file_size_kb), `src/lexibrary/cli.py` (new commands), `src/lexibrary/indexer/generator.py` (frontmatter descriptions)
- **New BAML files**: `baml_src/archivist_design_file.baml`, `baml_src/archivist_start_here.baml`, updates to `baml_src/types.baml` and `baml_src/clients.baml`
- **New dependencies**: None expected beyond existing tree-sitter and BAML packages
- **Phase**: 4 (depends on Phases 1-3 complete)
