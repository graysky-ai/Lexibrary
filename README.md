<p align="center">
  <img src="Lexibrary.png" alt="Lexibrary" width="600">
</p>

# Lexibrary

A semantic code library that gives AI coding agents structured, queryable context — so they look up what they need instead of guessing or dumping entire files into their context window.

## About

Lexibrary indexes your codebase into a layered knowledge base of design summaries, dependency graphs, conventions, domain concepts, and known-issue records. Agents query this library through the `lexi` CLI to orient themselves, understand file roles before editing, trace cross-file dependencies, and avoid repeating past debugging dead ends.

**For project maintainers**, the `lexictl` CLI handles initialization, indexing, design file generation, and library health maintenance.

## Features

| Feature | What it does |
|---|---|
| **Design files** | LLM-generated per-file summaries with dependency maps and interface contracts |
| **Link graph** | SQLite-backed cross-file dependency analysis with reverse lookups and full-text search |
| **Conventions** | Project-wide and scope-local coding rules as first-class, enforceable artifacts |
| **Concepts** | Domain vocabulary definitions with aliases, wikilink resolution, and lifecycle management |
| **Stack** | Stack Overflow-style Q&A knowledge base for bugs, decisions, and workarounds — including failed attempts so agents don't repeat dead ends |
| **IWH signals** | Ephemeral "I Was Here" breadcrumbs for inter-agent handoff of incomplete or blocked work |
| **Validator** | 40+ library health checks across frontmatter, wikilinks, staleness, orphans, and cross-artifact consistency |
| **Impact analysis** | Reverse dependency lookups to understand what breaks when a file changes |
| **AST parsing** | Language-aware public API extraction (Python, JS, TS) |
| **Unified search** | Full-text search across all artifact types with format options (JSON, plain, markdown) |

## How It Works

Lexibrary builds and maintains a layered knowledge base alongside your source code:

```
lexictl init          Set up config + directory structure
       │
       ▼
lexictl bootstrap     Batch-generate .aindex files + design files
       │
       ▼
lexictl update        Re-index changed files, regenerate stale designs
       │
       ▼
  ┌────┴────┐
  │ SQLite  │         Link graph: dependencies, tags, aliases, FTS index
  │  graph  │
  └────┬────┘
       │
       ▼
  .lexibrary/         Artifacts on disk: designs/, concepts/, conventions/,
                      stack/, .aindex files — all version-controlled
```

Agents then query this library at runtime through `lexi`:

```
lexi lookup      →  File role, dependencies, conventions before editing
lexi search      →  Find concepts, conventions, designs, stack posts
lexi impact      →  What depends on this file?
lexi validate    →  Check library health after changes
```

**Key design choices:**
- **Two CLIs** — `lexi` is read-only and agent-safe; `lexictl` mutates state and is for maintainers
- **Zero infrastructure** — all state lives in repo files and a local SQLite graph
- **File-first** — artifacts are markdown with YAML frontmatter, easily diffable and version-controlled

## Agent Integration

Lexibrary is designed to slot into an AI coding agent's workflow. The typical session:

```
1. Read .lexibrary/TOPOLOGY.md     # Understand project structure
2. lexi iwh list                   # Check for pending handoff signals
3. lexi iwh read <dir>             # Consume any handoff signals from previous agents
4. lexi lookup <file>              # Before editing — understand role, deps, conventions
5. lexi search <topic>             # Before architectural decisions — find existing patterns
6. lexi stack post --title "..."   # After solving a bug — document the fix + failed attempts
7. lexi validate                   # After editing — check for broken links, stale artifacts
8. lexi iwh write <dir>            # If stopping early — leave a breadcrumb for the next agent
```

Agents also have access to `concept`, `convention`, `design`, and `stack` subcommand groups for managing those artifact types. See the full reference at [docs/agent/lexi-reference.md](docs/agent/lexi-reference.md).

## Quick Start

**Prerequisites:** Python 3.11+ and [uv](https://docs.astral.sh/uv/)

```bash
# Install dependencies
uv sync

# Initialize Lexibrary in your project
lexictl init

# Generate the initial library (indexes + design files)
lexictl bootstrap

# Verify library health
lexi validate

# Look up a specific file
lexi lookup src/main.py

# Search for a topic
lexi search "authentication"
```

## Configuration

Lexibrary is configured through two layers:

1. **`.lexibrary/config.yaml`** — project-level config (created by `lexictl init`)
2. **`.env`** — local environment overrides (gitignored)

Copy the template to get started:

```bash
cp .env.example .env
```

### Environment variables

| Variable | Description |
|---|---|
| `LEXI_PROJECT_PATH` | Project root to crawl. Defaults to current working directory. |
| `LEXI_LLM_PROVIDER` | LLM provider: `anthropic`, `openai`, or `ollama` |
| `LEXI_LLM_MODEL` | Model identifier (e.g. `claude-sonnet-4-5-20250514`, `gpt-4o-mini`) |
| `LEXI_API_KEY` | API key override — applies to whichever provider is active |
| `ANTHROPIC_API_KEY` | Anthropic API key (used when `LEXI_API_KEY` is not set) |
| `OPENAI_API_KEY` | OpenAI API key (used when `LEXI_API_KEY` is not set) |

Environment variables override values from `.lexibrary/config.yaml`. The `.env` file is loaded automatically when running any command.

## CLI Reference

### lexi (agent-facing)

| Command | Purpose |
|---|---|
| `lookup <path>` | File context: role, dependencies, conventions |
| `search <query>` | Full-text search across all artifact types |
| `impact <file>` | Reverse dependency lookup |
| `validate` | Library consistency checks (read-only) |
| `status` | Library health and staleness summary |
| **Subcommand groups** | `stack`, `concept`, `convention`, `design`, `iwh` |

Full reference: [docs/agent/lexi-reference.md](docs/agent/lexi-reference.md)

### lexictl (maintenance)

| Command | Purpose |
|---|---|
| `init` | Project setup wizard |
| `bootstrap` | Batch-generate indexes and design files |
| `update` | Re-index changed files, regenerate stale designs |
| `validate` | Consistency checks with `--fix` support |
| `status` | Library health summary |
| `setup` | Install/update agent rules and hooks |
| `sweep` | One-shot or watch-mode library update |

Full reference: [docs/user/lexictl-reference.md](docs/user/lexictl-reference.md)

## Development

This project uses:
- **uv** for dependency management
- **Typer** for CLI
- **Pydantic 2** for configuration and models
- **BAML** for LLM prompt definitions
- **tree-sitter** for AST parsing
- **Pytest** for testing
- **Ruff** for linting and formatting
- **Mypy** for strict type checking

```bash
uv sync --dev                        # install with dev deps
uv run pytest --cov=lexibrary        # tests + coverage
uv run ruff check src/ tests/        # lint
uv run ruff format src/ tests/       # format
uv run mypy src/                     # type check (strict)
```

## License

MIT
