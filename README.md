# Lexibrary

AI-friendly codebase indexer for creating `.aindex` files

## Overview

Lexibrary automatically crawls your codebase and generates `.aindex` files - AI-friendly summaries that help language models understand your code structure and navigate context more effectively.

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

Run tests:
```bash
uv run pytest
```

## License

MIT
