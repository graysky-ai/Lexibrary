# Changelog

All notable changes to Lexibrary are documented in this file.

## [0.2.0] - 2026-02-27

### Added
- **AST parsing** — Language-aware public API extraction for Python, JavaScript, and TypeScript via tree-sitter
- **Link graph** — SQLite-backed cross-file dependency analysis with reverse lookups and FTS search
- **Conventions** — First-class convention artifacts with lookup integration
- **Stack** — Contextual working-set management (posts, search, voting)
- **Daemon mode** — Watchdog-based background indexing with debounce and periodic sweep
- **Init wizard** — Interactive `lexictl init` with project detection and guided setup
- **Validation** — Library consistency checks with severity filtering and auto-fix
- **Agent rules** — IWH (I Was Here) signal files and agent-facing documentation
- **Dotenv support** — `.env` file loading for API key management
- `py.typed` marker for PEP 561 compliance
- `CHANGELOG.md`
- `.editorconfig` for contributor consistency

### Changed
- **CLI split** — Separated into `lexi` (agent-facing) and `lexictl` (maintenance)
- **Package rename** — `lexibrarian` renamed to `lexibrary`
- Improved error handling with structured `ErrorRecord`/`ErrorSummary` pipeline
- Refactored command structure for improved agent usability

### Removed
- `START_HERE.md` generation (replaced by design files and link graph)
- Agent workflow artifacts removed from git tracking (openspec, blueprints, plans, beads)

## [0.1.0] - 2026-02-10

### Added
- **Foundation** — Project scaffolding, config system (Pydantic 2 + YAML), ignore patterns (pathspec)
- **Crawler** — Bottom-up file traversal with SHA-256 change detection
- **Indexer** — `.aindex` file generation with directory-level summaries
- **Design files** — LLM-generated per-file summaries via BAML prompts
- **Token counting** — Anthropic, tiktoken, and approximate backends
- **CLI** — Typer-based command interface with Rich console output
