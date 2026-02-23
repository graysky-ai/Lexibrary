## 1. Config Template Renderer

- [x] 1.1 Add `render_default_config(provider: str)` function to `src/lexibrary/config/defaults.py` that formats `DEFAULT_CONFIG_TEMPLATE` with provider-specific values (model, api_key_env) using a provider defaults mapping for anthropic, openai, and ollama
- [x] 1.2 Add unit test for `render_default_config()` verifying each provider produces correct values and unknown providers fall back to anthropic

## 2. CLI Module Setup

- [x] 2.1 Replace `typer.echo()` imports in `src/lexibrary/cli.py` with `rich.console.Console` and `rich.progress`, `rich.table`, `rich.panel` imports; create module-level `console = Console()` instance
- [x] 2.2 Add `from __future__ import annotations` if not already present in cli.py

## 3. Init Command

- [x] 3.1 Implement `lexi init` command: accept `--provider` option, call `render_default_config()`, write `lexibrary.toml`, exit with code 1 if config already exists
- [x] 3.2 Implement `.gitignore` management in init: create or update `.gitignore` with entries for `.aindex`, `.lexibrary_cache.json`, `.lexibrary.log`, `.lexibrary.pid`
- [x] 3.3 Add "Next steps" output after successful init
- [x] 3.4 Write tests: `test_init_creates_config`, `test_init_already_exists`, `test_init_provider_openai`, `test_init_updates_gitignore`, `test_init_creates_gitignore`

## 4. Crawl Command

- [x] 4.1 Implement `lexi crawl` command: accept `--full`, `--dry-run`, `--verbose` options; load config, create ignore matcher, tokenizer, LLM service, and change detector
- [x] 4.2 Add Rich progress bar with spinner, text, bar, and task progress columns; wire up `on_progress` callback
- [x] 4.3 Add summary table output after crawl (directories indexed, files summarized, files cached, files skipped, LLM calls, errors)
- [x] 4.4 Add graceful error handling if crawler engine is not yet implemented (catch ImportError for `crawler.engine`)
- [x] 4.5 Write test: `test_crawl_dry_run` with mocked LLM service

## 5. Status Command

- [x] 5.1 Implement `lexi status` command: load config (with fallback to defaults), count `.aindex` files, load cache and count entries, detect stale files
- [x] 5.2 Add daemon PID detection: check `.lexibrary.pid`, verify process exists with `os.kill(pid, 0)`, handle stale PID files
- [x] 5.3 Display results in a Rich Panel with title "Lexibrary Status"
- [x] 5.4 Write tests: `test_status_no_config`, `test_status_with_cache`

## 6. Clean Command

- [x] 6.1 Implement `lexi clean` command: find all `.aindex` files, cache file, and log file; show count and prompt for confirmation (skip with `--yes`)
- [x] 6.2 Write tests: `test_clean_removes_files`, `test_clean_nothing_to_clean`

## 7. Daemon Command

- [x] 7.1 Implement `lexi daemon` command stub: accept `--foreground` flag, try to import `DaemonService`, show "not yet available" message on `ImportError`
- [x] 7.2 Write test: `test_daemon_not_implemented` verifying the guard message is shown

## 8. Integration Tests

- [x] 8.1 Write `test_help` verifying `lexi --help` lists all 5 commands with descriptions
- [x] 8.2 Run full test suite (`uv run pytest tests/test_cli.py -v`) and fix any failures
- [x] 8.3 Run linting and type checking (`uv run ruff check src/lexibrary/cli.py` and `uv run mypy src/lexibrary/cli.py`) and fix any issues
