## Context

Lexibrary must have working project scaffolding and core infrastructure before any feature work. This phase establishes the foundation: Python package structure, configuration management, CLI interface, and utility modules that all future features depend on.

Current state: Bare directory with no project structure.

## Goals / Non-Goals

**Goals:**
- Establish modular package structure under `src/lexibrary/` with logical subpackages (config, ignore, utils, cli, crawler, indexer, llm, tokenizer, daemon)
- Implement configuration system that discovers and validates `lexibrary.toml` via upward traversal with sensible defaults
- Build ignore-pattern system supporting hierarchical `.gitignore` files + config-based patterns with directory pruning
- Create reusable utilities for file hashing, logging setup, and project root detection
- Define Typer CLI with command structure, help text, and placeholder implementations
- Make `uv sync` and `uv run lexi --help` work with no errors

**Non-Goals:**
- Do not implement actual crawling, indexing, or LLM integration (those are later phases)
- Do not build daemon watch logic beyond skeleton command
- Do not optimize performance; focus on correctness and clarity
- Do not implement init/crawl/daemon commands fully; placeholders are sufficient for this phase

## Decisions

### 1. **Package Structure**: Subpackages organized by concern
- `src/lexibrary/config/` — Configuration loading and validation
- `src/lexibrary/ignore/` — Ignore pattern matching
- `src/lexibrary/utils/` — Shared utilities (hashing, logging, paths)
- `src/lexibrary/cli.py` — CLI entry point
- Future: `crawler/`, `indexer/`, `llm/`, `tokenizer/`, `daemon/`

**Rationale**: Clear separation of concerns makes testing and future expansion straightforward.

### 2. **Config System**: TOML + Pydantic + Upward Traversal
- Use `tomllib` (stdlib in Python 3.11+) to parse `lexibrary.toml`
- Define Pydantic models for nested config (LLMConfig, TokenizerConfig, CrawlConfig, IgnoreConfig, DaemonConfig, OutputConfig)
- Implement `find_config_file()` that walks parent directories for `lexibrary.toml`
- Return full defaults if no config file found
- Cache config at module level after first load

**Rationale**: Pydantic provides validation and type safety; tomllib is zero-dependency; upward traversal matches common developer expectations (like .gitignore). Defaults ensure Lexibrary works without config.

**Alternative considered**: Environment variables only → rejected because config is hierarchical and complex; .toml is more scalable.

### 3. **Ignore System**: Pathspec + Hierarchical .gitignore Support
- Use `pathspec` library to parse .gitignore patterns with "gitwildmatch" dialect
- Discover all `.gitignore` files in the project tree via `rglob()`
- Sort by directory depth (root first) to apply override rules correctly
- In `IgnoreMatcher.is_ignored()`, check config patterns first (cheap), then .gitignore specs (directory-specific)
- Implement `should_descend(directory)` for early directory pruning during traversal

**Rationale**: Pathspec handles complex globbing; hierarchical .gitignore matches Git's behavior; pruning improves crawler performance later. Config patterns checked first for speed.

**Alternative considered**: Manual glob parsing → rejected because pathspec is mature and handles edge cases.

### 4. **Utilities**: Simple, Focused Modules
- `hashing.py`: SHA-256 file hashing with chunked I/O
- `logging.py`: Setup function combining RichHandler + optional file handler
- `paths.py`: Walk upward to find project root (`.git` or `lexibrary.toml`)

**Rationale**: Single-responsibility modules; avoid premature abstraction. These are called from config, ignore, and future crawler code.

### 5. **CLI**: Typer App with 5 Commands
- `init` — Placeholder for config initialization
- `crawl` — Placeholder for crawling
- `daemon` — Placeholder for background daemon
- `status` — Placeholder for status display
- `clean` — Placeholder for cleanup

Each command takes a path argument (default `.`), prints "not yet implemented" message.

**Rationale**: Typer provides excellent help text, argument parsing, and extensibility. Placeholders allow testing infrastructure without implementing logic. Matches common CLI patterns.

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| `find_config_file()` walks entire tree on each call (could be slow on large projects) | Implement lazy caching at module level after first load. Only re-discover if config file is deleted. |
| Hierarchical .gitignore matching is complex and could have edge cases | Write comprehensive tests with nested directory fixtures. Reference Git's implementation for corner cases. |
| Large project trees with many .gitignore files could cause performance issues | Rglob is lazy; only load specs for files that are actually traversed. Profile if needed. |
| Pydantic strict validation could reject valid TOML | Use `model_validate()` with lenient defaults; document expected structure in DEFAULT_CONFIG_TEMPLATE. |

## Migration Plan

**Phase 1 Deployment:**
1. Create all directories and files as specified in project scaffolding
2. Install dependencies with `uv sync`
3. Verify `uv run lexi --help` works
4. Run all unit tests for config, ignore, utils modules
5. No rollback needed; this is additive (new repository, no existing state)

**Future Phases:**
Each subsequent phase will integrate with the config system (reading settings) and ignore system (skipping patterns), so maintain API compatibility.

## Open Questions

- Should config caching be per-file-path or global? (Proposing: global with lazy initialization for simplicity)
- Should we support environment variable overrides for config fields? (Proposing: no for Phase 1; add if requested)
- Should `find_project_root()` also check for `README.md` or `setup.py`? (Proposing: no; `.git` or `lexibrary.toml` is sufficient)
