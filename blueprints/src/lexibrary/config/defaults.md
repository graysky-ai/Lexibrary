# config/defaults

**Summary:** Holds the default `config.yaml` template string written by `lexictl init` to `.lexibrary/config.yaml`.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `DEFAULT_PROJECT_CONFIG_TEMPLATE` | `str` | YAML template with all config keys and inline comments, including `scope_root`, `project_name`, `agent_environment`, `iwh`, `llm`, `token_budgets`, `mapping`, `ignore`, `daemon`, `crawl`, and `ast` sections |

## Dependents

- `lexibrarian.config.__init__` -- re-exports it
- `lexibrarian.init.scaffolder` -- writes it to `.lexibrary/config.yaml` on `create_lexibrary_skeleton()`

## Key Concepts

- Template includes all configuration sections: `scope_root`, `project_name`, `agent_environment`, `iwh`, `llm`, `token_budgets`, `mapping`, `ignore`, `daemon`, `crawl`, `ast`
- `project_name` and `agent_environment` were added for Phase 8b init wizard
- `iwh` section controls I Was Here (IWH) agent trace files
- `daemon` section includes:
  - `debounce_seconds: 2.0` -- coalesce rapid file events
  - `sweep_interval_seconds: 3600` -- full re-index safety net (1 hour)
  - `sweep_skip_if_unchanged: true` -- skip sweep if no files changed
  - `git_suppression_seconds: 5` -- suppress watchdog events after git ops
  - `watchdog_enabled: false` -- opt-in real-time watching (not `enabled`)
  - `log_level: info` -- daemon log level (debug, info, warning, error)
