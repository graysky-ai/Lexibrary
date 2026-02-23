## Why

The CLI currently has 5 placeholder commands that print "not yet implemented" messages using `typer.echo()`. Phase 6 replaces these with full implementations using Rich console output, progress bars, and real integrations with the config, ignore, tokenizer, LLM, and crawler subsystems — making the tool actually usable end-to-end.

## What Changes

- **`lexi init`**: Creates `lexibrary.toml` from a provider-aware template, updates/creates `.gitignore` with Lexibrary entries, shows next-steps guidance
- **`lexi crawl`**: Runs the crawler engine with Rich progress bar, supports `--full` (ignore cache), `--dry-run` (preview only), `--verbose` (debug logging), prints summary statistics table
- **`lexi status`**: Shows config info, index counts (directories indexed, files cached, stale files), and daemon PID status in a Rich panel
- **`lexi clean`**: Finds and removes all `.aindex` files, cache, and log files with confirmation prompt (`--yes` to skip)
- **`lexi daemon`**: Thin CLI wrapper for the daemon service (Phase 7 dependency — stub with guard for now)
- **Config defaults**: Add `render_default_config()` to generate provider-specific TOML templates
- **CLI module**: Switch from `typer.echo()` to `rich.console.Console`, add proper option flags and Annotated types
- All existing tests unaffected; new CLI tests added using Typer's `CliRunner`

## Capabilities

### New Capabilities

- `cli-commands`: Full implementations of all 5 CLI commands (init, crawl, status, clean, daemon) with Rich output, progress reporting, and integration with existing subsystems

### Modified Capabilities

- `cli-skeleton`: Command signatures gain new options (`--full`, `--dry-run`, `--verbose`, `--yes`, `--provider`, `--foreground`) and switch from `typer.echo()` to Rich console output

## Impact

- **Code**: Replaces `src/lexibrary/cli.py` (placeholder → full implementation), adds `render_default_config()` to `src/lexibrary/config/defaults.py`
- **Dependencies**: No new runtime deps (Typer and Rich already present). Phase 5 crawler engine must exist for `lexi crawl` to work; `lexi daemon` deferred to Phase 7
- **APIs**: No external API changes. Internal: depends on `load_config()`, `create_ignore_matcher()`, `create_tokenizer()`, `create_llm_service()`, and crawler engine (Phase 5)
- **Phase**: Touches Phase 6. Depends on Phase 1 (config, CLI skeleton) and Phase 5 (crawler engine). Daemon command depends on Phase 7
