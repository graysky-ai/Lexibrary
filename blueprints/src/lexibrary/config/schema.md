# config/schema

**Summary:** Pydantic 2 models for the full Lexibrary configuration hierarchy, validated from `.lexibrary/config.yaml`.

## Interface

| Name | Key Fields | Purpose |
| --- | --- | --- |
| `CrawlConfig` | `max_file_size_kb: int = 512`, `binary_extensions: list[str]` | Crawl behaviour -- file types to treat as binary and size limits |
| `TokenizerConfig` | `backend`, `model`, `max_tokens_per_chunk` | Tokenizer backend selection |
| `LLMConfig` | `provider`, `model`, `api_key_env`, `api_key_source: str = "env"`, `max_retries`, `timeout` | LLM provider settings; `api_key_source` controls how the API key is resolved (`"env"`, `"dotenv"`, or `"manual"`) |
| `TokenBudgetConfig` | `start_here_tokens`, `design_file_tokens`, `design_file_abridged_tokens`, `aindex_tokens`, `concept_file_tokens` | Per-artifact token budgets |
| `MappingConfig` | `strategies: list[dict]` | Mapping strategy config (stub for Phase 1) |
| `IgnoreConfig` | `use_gitignore: bool`, `additional_patterns: list[str]` | Ignore pattern settings; defaults include `.env`, `.env.*`, and `*.env` to prevent API key files from being indexed |
| `DaemonConfig` | `debounce_seconds: float = 2.0`, `sweep_interval_seconds: int = 3600`, `sweep_skip_if_unchanged: bool = True`, `git_suppression_seconds: int = 5`, `watchdog_enabled: bool = False`, `log_level: str = "info"` | Daemon sweep, watchdog, and logging settings |
| `ASTConfig` | `enabled: bool`, `languages: list[str]` | AST-based interface extraction settings |
| `IWHConfig` | `enabled: bool = True` | I Was Here (IWH) agent trace configuration |
| `LexibraryConfig` | `scope_root`, `project_name`, `agent_environment`, `iwh`, `llm`, `token_budgets`, `mapping`, `ignore`, `daemon`, `crawl`, `ast` | Top-level config container |

## Dependencies

- None (only pydantic)

## Dependents

- `lexibrary.config.loader` -- validates merged YAML into `LexibraryConfig`
- `lexibrary.config.__init__` -- re-exports all models
- `lexibrary.ignore.patterns` -- consumes `IgnoreConfig`
- `lexibrary.llm.factory` -- consumes `LLMConfig`
- `lexibrary.indexer.orchestrator` -- consumes `LexibraryConfig`
- `lexibrary.archivist.pipeline` -- uses `LexibraryConfig` for scope_root, token_budgets, crawl settings
- `lexibrary.archivist.service` -- uses `LLMConfig` for provider routing
- `lexibrary.init.scaffolder` -- validates wizard answers through `LexibraryConfig.model_validate()`
- `lexibrary.cli._shared` -- `load_dotenv_if_configured()` reads raw YAML to check `llm.api_key_source`
- `lexibrary.cli.lexictl_app` -- `setup` command reads `agent_environment` from config
- `lexibrary.daemon.service` -- reads `DaemonConfig` fields for sweep, watchdog, and logging behaviour

## Key Concepts

- `LLMConfig.api_key_source` -- controls API key resolution strategy:
  - `"env"` (default) -- key is already set in the shell environment via the variable named in `api_key_env`
  - `"dotenv"` -- key is stored in a `.env` file at the project root; the CLI loads it via `python-dotenv` at startup
  - `"manual"` -- user manages the key themselves; no automatic loading
- `IgnoreConfig.additional_patterns` defaults include `.env`, `.env.*`, and `*.env` to prevent dotenv files (which may contain API keys) from being crawled or indexed
- `DaemonConfig` fields:
  - `debounce_seconds` -- coalesce rapid file-change events (watchdog mode)
  - `sweep_interval_seconds` -- period for periodic sweeps (default 3600s = 1 hour)
  - `sweep_skip_if_unchanged` -- skip sweep if no files have newer mtimes since last run
  - `git_suppression_seconds` -- suppress watchdog events after git operations
  - `watchdog_enabled` -- opt-in real-time file watching (default `False`); replaces the former `enabled` field
  - `log_level` -- daemon log level for `RotatingFileHandler` (default `"info"`)

## Dragons

- All models use `extra="ignore"` so unknown YAML keys are silently dropped
- `scope_root` defaults to `"."` (project root); archivist pipeline resolves it to an absolute path for file filtering
- `DaemonConfig.watchdog_enabled` replaces the former `enabled` field; the old `enabled` field is silently ignored via `extra="ignore"`
- `IWHConfig` was added for Phase 8b init wizard; `project_name` and `agent_environment` are top-level fields on `LexibraryConfig`
