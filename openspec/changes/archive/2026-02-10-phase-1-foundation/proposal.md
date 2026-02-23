## Why

Lexibrary needs foundational infrastructure to function. Currently, there is no project structure, configuration system, CLI entry point, or ignore-pattern handling. Without these fundamentals, we cannot build any higher-level features (crawling, indexing, LLM integration). This phase establishes the scaffolding that all subsequent phases depend on.

## What Changes

- **Project Scaffolding**: Create `pyproject.toml` with all dependencies (Typer, Pydantic, Pathspec, Tiktoken, BAML, etc.), directory structure, Python version pin, and CLI entry points
- **Configuration System**: Implement TOML-based config loading with Pydantic validation; support `lexibrary.toml` discovery via upward traversal
- **Ignore System**: Build pathspec-based .gitignore and config pattern matching with hierarchical .gitignore support and directory pruning
- **Utilities**: Add file hashing (SHA-256), logging setup (Rich handler + file), and project root detection
- **CLI Skeleton**: Create Typer app with 5 placeholder commands (`init`, `crawl`, `daemon`, `status`, `clean`)

## Capabilities

### New Capabilities

- `project-scaffolding`: Complete project structure with pyproject.toml, dependency declarations, Python version pinning, and CLI entry points
- `config-system`: TOML-based configuration with Pydantic schema, upward discovery, validation, and defaults
- `ignore-system`: Unified ignore pattern matching combining .gitignore hierarchies and config-based patterns with directory pruning
- `utilities`: File hashing, structured logging with Rich, and project root discovery
- `cli-skeleton`: Typer CLI with command structure, help text, and placeholder implementations

### Modified Capabilities

<!-- No existing capabilities are being modified; this is the initial foundation -->

## Impact

- **Code**: Affects entire project structure; subsequent phases depend on config system, ignore system, and CLI entry points
- **Dependencies**: Introduces Typer, Pydantic, Pathspec, Rich, Tiktoken, BAML, Watchdog, and dev tools (Pytest, Ruff, Mypy)
- **CLI**: Establishes `lexi` and `lexibrary` command entry points; all future commands build on this foundation
- **User Workflow**: Users can now initialize projects and see CLI help; configuration is centralized in `lexibrary.toml`
