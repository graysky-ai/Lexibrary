## Context

The CLI has 5 placeholder commands from Phase 1 that use `typer.echo()` and do nothing. All supporting subsystems (config loading, ignore matching, tokenizer, LLM service, indexer format) are implemented. The crawler engine (Phase 5) is not yet implemented — the `src/lexibrary/crawler/` module is empty. The daemon service (Phase 7) is also pending.

The existing `config/defaults.py` already has a `DEFAULT_CONFIG_TEMPLATE` string. The config schema uses `OutputConfig` with fields `index_filename`, `cache_filename`, and `log_filename` (not the names in the phase-6 plan like `daemon.log_file`).

## Goals / Non-Goals

**Goals:**
- Replace all 5 placeholder CLI commands with working implementations
- Use Rich console output for all user-facing messages (no `typer.echo()` or `print()`)
- Add `render_default_config(provider)` for provider-aware config generation in `lexi init`
- Show Rich progress bars during `lexi crawl`
- Display status as a Rich panel in `lexi status`
- Support confirmation prompts and `--yes` flag in `lexi clean`
- Provide comprehensive CLI tests using Typer's `CliRunner`

**Non-Goals:**
- Implementing the crawler engine (Phase 5 responsibility — `lexi crawl` will fail gracefully if missing)
- Implementing the daemon service (Phase 7 responsibility — `lexi daemon` provides a guard message)
- Adding new runtime dependencies beyond what's already in `pyproject.toml`
- Changing the config schema or Pydantic models

## Decisions

### D1: Rich Console as module-level singleton

Use a single `console = Console()` at module level in `cli.py`. All output goes through this instance.

**Why not typer.echo():** The project constraint mandates Rich console output. Rich provides tables, panels, progress bars, and styled text that `typer.echo()` cannot.

**Alternative considered:** Passing console as a parameter — unnecessary complexity for a CLI module where there's one console.

### D2: `render_default_config()` in `config/defaults.py`

Add a `render_default_config(provider: str)` function that uses string `.format()` on the existing `DEFAULT_CONFIG_TEMPLATE` to substitute provider-specific values (model name, API key env var).

**Why not tomli_w:** The existing template already has comments; TOML writers strip comments. String formatting preserves the commented template exactly.

**Why not a separate template file:** The template is already in `defaults.py` as `DEFAULT_CONFIG_TEMPLATE`. Adding a function alongside it keeps things co-located.

**Provider defaults mapping:**
- `anthropic` → `claude-sonnet-4-5-20250514`, `ANTHROPIC_API_KEY`
- `openai` → `gpt-4o-mini`, `OPENAI_API_KEY`
- `ollama` → `llama3.2`, `""` (no API key needed)

### D3: `asyncio.run()` bridge for crawl command

The crawler engine uses async (for concurrent LLM calls). The Typer command is synchronous. Bridge with `asyncio.run(full_crawl(...))` at the command level.

**Alternative considered:** Making the CLI command async with `anyio` — adds dependency complexity. `asyncio.run()` is idiomatic for "sync entry point calling async code."

### D4: Progress callback pattern

The crawl command creates a Rich `Progress` context and passes a `on_progress(current, total, dir_name)` callback to the crawler engine. This decouples the crawler from Rich.

**Why a callback:** The crawler shouldn't import or know about Rich. A simple callable keeps the engine testable without UI dependencies.

### D5: Daemon command as Phase 7 guard

The daemon command imports `DaemonService` and calls `svc.start()`. Until Phase 7 implements it, the import will fail. Wrap in try/except with a clear "not yet available" message.

**Alternative considered:** Omitting the daemon command entirely — but the CLI skeleton spec requires all 5 commands, and having the command present with a clear message is better UX.

### D6: Config field name alignment

The phase-6 plan references `config.daemon.log_file` and `config.output.filename`, but the actual schema has `config.daemon` (no log_file field — that's in `OutputConfig`) and `config.output.index_filename`. Use the actual schema field names from `config/schema.py`, not the plan's names.

Specifically:
- Index filename: `config.output.index_filename` (not `config.output.filename`)
- Cache filename: `config.output.cache_filename`
- Log filename: `config.output.log_filename` (not `config.daemon.log_file`)

### D7: `lexi status` uses defaults when no config exists

If no `lexibrary.toml` is found, `load_config()` returns default config. The status command works in all cases, showing "not found (using defaults)" for the config path.

## Risks / Trade-offs

- **[Crawler not implemented]** → `lexi crawl` will fail at import time when trying to use `crawler.engine.full_crawl`. **Mitigation:** Guard the import and show a clear error message. The crawl command structure is ready for when Phase 5 lands.

- **[Template drift]** → `render_default_config()` duplicates field names from the schema. If schema changes, template may drift. **Mitigation:** The existing `DEFAULT_CONFIG_TEMPLATE` is already the source of truth; `render_default_config()` only substitutes 3 provider-specific values into it.

- **[CliRunner test limitations]** → Typer's `CliRunner` captures output as plain text (no Rich markup). Tests must assert on stripped text content, not styled output. **Mitigation:** Assert substrings and structure rather than exact styled output.

- **[Stale PID detection]** → `lexi status` checks daemon PID via `os.kill(pid, 0)`. On some systems this may require specific permissions. **Mitigation:** Catch `PermissionError` alongside `ProcessLookupError`.
