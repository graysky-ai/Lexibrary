<p align="center">
  <img src="Lexibrary.png" alt="Lexibrary" width="200">
</p>

# Lexibrary

AI-friendly codebase indexer that creates `.aindex` files for LLM context navigation.

## About

Lexibrary turns your codebase into a queryable semantic library that AI coding agents can navigate efficiently. Instead of dumping entire files into context windows, agents use Lexibrary to look up exactly what they need — design summaries, dependency graphs, public API skeletons, and cross-file relationships.

**Key capabilities:**

- **Crawl & index** — Bottom-up traversal with SHA-256 change detection
- **Design files** — LLM-generated per-file summaries with dependency maps
- **Link graph** — SQLite-backed cross-file dependency analysis and reverse lookups
- **Unified search** — Full-text search across indexes, design files, and conventions
- **AST parsing** — Language-aware public API extraction (Python, JS, TS)
- **Conventions** — Project-wide rules and patterns as first-class artifacts
- **Stack** — Contextual working-set management for focused exploration
- **Daemon mode** — Watchdog-based background indexing with debounce

**Architecture:** Two CLIs — `lexi` (agent-facing queries) and `lexictl` (setup/maintenance). Zero infrastructure — all state lives in repo files and a local SQLite graph.

## Installation

```bash
uv sync --dev
```

## Usage

```bash
# Initialize a project
lexictl init

# Crawl and index a codebase
lexi crawl

# Check indexing status
lexi status

# Start background daemon
lexi daemon

# Clean all .aindex files
lexi clean
```

## Configuration

Lexibrary is configured through two layers:

1. **`lexibrary.toml`** — project-level config (created by `lexictl init`)
2. **`.env`** — local environment overrides (gitignored)

Copy the template to get started:

```bash
cp .env.example .env
```

### Environment variables

| Variable | Description |
|---|---|
| `LEXI_PROJECT_PATH` | Project root to crawl. Defaults to current working directory. |
| `LEXI_LLM_PROVIDER` | LLM provider override: `anthropic`, `openai`, or `ollama` |
| `LEXI_LLM_MODEL` | Model identifier override (e.g. `claude-sonnet-4-5-20250514`, `gpt-4o-mini`) |
| `LEXI_API_KEY` | API key override — applies to whichever provider is active |
| `ANTHROPIC_API_KEY` | Anthropic API key (used when `LEXI_API_KEY` is not set) |
| `OPENAI_API_KEY` | OpenAI API key (used when `LEXI_API_KEY` is not set) |

Environment variables override values from `lexibrary.toml`. The `.env` file is loaded automatically when running any `lexi` command.

## Development

This project uses:
- **uv** for dependency management
- **Typer** for CLI
- **Pydantic** for configuration
- **Pytest** for testing
- **Ruff** for linting
- **Mypy** for type checking

```bash
uv run pytest --cov=lexibrary    # tests + coverage
uv run ruff check src/ tests/    # lint
uv run ruff format src/ tests/   # format
uv run mypy src/                 # type check (strict)
```

## License

MIT
