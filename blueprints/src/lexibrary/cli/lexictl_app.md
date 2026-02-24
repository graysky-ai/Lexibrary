# cli/lexictl_app

**Summary:** Maintenance Typer CLI app (`lexictl`) providing wizard-based project initialization, design file generation (with `--changed-only` support), structural indexing, validation, status reporting, agent rule setup (with `--hooks`), library sweeps, IWH signal cleanup, and deprecated watchdog daemon management.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `lexictl_app` | `typer.Typer` | Root maintenance CLI application registered as the `lexictl` entry point; uses `load_dotenv_if_configured` as its Typer callback for dotenv startup loading |
| `iwh_ctl_app` | `typer.Typer` | Sub-group for `lexictl iwh *` commands (clean) |
| `init` | `(*, defaults: bool) -> None` | Run the 8-step init wizard via `run_wizard()`; `--defaults` flag accepts all detected values without prompting; re-init guard prevents overwriting existing `.lexibrary/`; non-TTY guard requires `--defaults` |
| `update` | `(path: Path \| None, *, changed_only: list[Path] \| None) -> None` | Generate/update design files via archivist pipeline; supports `--changed-only` for git-hook usage (calls `update_files`); mutually exclusive with `path`; single file, directory, or full project mode |
| `index` | `(directory: Path = ".", *, recursive: bool) -> None` | Generate `.aindex` file(s) for a directory; `-r` flag triggers bottom-up recursive indexing; moved here from `lexi_app` |
| `validate` | `(*, severity: str \| None, check: str \| None, json_output: bool) -> None` | Thin wrapper calling shared `_run_validate()` helper; run consistency checks with optional severity/check filters; outputs Rich tables or JSON; exits with `report.exit_code()` |
| `status` | `(path: Path \| None, *, quiet: bool) -> None` | Thin wrapper calling shared `_run_status(cli_prefix="lexictl")` helper; dashboard showing design file counts/staleness, concept counts by status, stack post counts, link graph health, validation issues summary, last updated timestamp; `--quiet`/`-q` for CI/hooks single-line output |
| `setup` | `(*, update_flag: bool, env: list[str] \| None, hooks: bool) -> None` | Install or update agent environment rules; `--hooks` flag installs the git post-commit hook; `--update` flag regenerates agent rules; reads `agent_environment` from config |
| `sweep` | `(*, watch: bool) -> None` | Run a library update sweep; one-shot by default, `--watch` for periodic sweeps in foreground |
| `daemon` | `(action: str \| None) -> None` | Deprecated watchdog daemon management; actions: `start`, `stop`, `status`; defaults to `start` |
| `iwh_clean` | `(*, older_than: int \| None) -> None` | Remove IWH signal files from the project; `--older-than N` flag only removes signals older than N hours; uses `find_all_iwh()` for discovery, deletes matching `.iwh` files, reports count |

## Dependencies

- `lexibrary.cli._shared` -- `console`, `load_dotenv_if_configured`, `require_project_root`, `_run_validate`, `_run_status`
- `lexibrary.cli.banner` -- `render_banner` (lazy import in `init`)
- `lexibrary.init.wizard` -- `run_wizard` (lazy import in `init`)
- `lexibrary.init.scaffolder` -- `create_lexibrary_from_wizard` (lazy import in `init`)
- `lexibrary.archivist.pipeline` -- `UpdateStats`, `update_file`, `update_files`, `update_project` (lazy import in `update`)
- `lexibrary.archivist.service` -- `ArchivistService` (lazy import in `update`)
- `lexibrary.config.loader` -- `load_config` (lazy import in `update`, `setup`, `daemon`)
- `lexibrary.llm.rate_limiter` -- `RateLimiter` (lazy import in `update`)
- `lexibrary.indexer.orchestrator` -- `index_directory`, `index_recursive` (lazy import in `index`)
- `lexibrary.init.rules` -- `generate_rules`, `supported_environments` (lazy import in `init`, `setup`)
- `lexibrary.iwh.gitignore` -- `ensure_iwh_gitignored` (lazy import in `setup`)
- `lexibrary.hooks.post_commit` -- `install_post_commit_hook` (lazy import in `setup`)
- `lexibrary.daemon.service` -- `DaemonService` (lazy import in `sweep`, `daemon`)
- `lexibrary.iwh.reader` -- `IWH_FILENAME`, `find_all_iwh` (lazy import in `iwh_clean`)
- `lexibrary.utils.paths` -- `LEXIBRARY_DIR` (lazy import in `iwh_clean`)

## Dependents

- `lexibrary.cli.__init__` -- re-exports `lexictl_app`
- `pyproject.toml` -- `lexictl` entry point

## Key Concepts

- `lexictl_app` registers `load_dotenv_if_configured` as its Typer `callback`, which runs before any command; when `llm.api_key_source` is `"dotenv"` in the project config, it calls `load_dotenv(project_root / ".env", override=False)` so that env vars already set in the shell take precedence; silently handles missing project root or `.env` file
- `init` displays a startup banner (truecolor block art or ASCII fallback) via `render_banner()` before running the wizard
- `init` uses `run_wizard()` + `create_lexibrary_from_wizard()` instead of the old `create_lexibrary_skeleton()`
- `init` calls `generate_rules()` for selected agent environments after scaffolding, creating rule files and directories (e.g. `CLAUDE.md`, `.claude/commands/`, `.cursor/rules/`); filters to supported environments only
- `init` does not call `require_project_root()` -- it creates the project root (uses `Path.cwd()` instead)
- `init` has a re-init guard (checks for existing `.lexibrary/`) and a non-TTY guard (requires `--defaults`)
- `index` command was moved from `lexi_app` to `lexictl_app` -- indexing is a maintenance operation, not an agent-facing one; identical interface with `directory` arg and `-r`/`--recursive` flag
- `update` supports `--changed-only` flag: accepts a list of file paths, calls `update_files()` for batch processing (designed for git hooks / CI)
- `update` enforces mutual exclusivity: providing both `path` and `--changed-only` prints an error and exits
- `validate` and `status` are thin wrappers that call shared helpers `_run_validate()` and `_run_status()` in `_shared.py`; this avoids duplicating the rendering logic across both CLI apps
- `status` passes `cli_prefix="lexictl"` so quiet-mode output reads `"lexictl: ..."` while `lexi status` uses `"lexi: ..."`
- `setup --hooks` calls `install_post_commit_hook()` and reports the result; returns early (does not generate agent rules)
- `setup --update` with optional `--env` overrides; reads `agent_environment` list from config; validates against `supported_environments()`
- `sweep` command: one-shot (`run_once`) by default; `--watch` for periodic sweeps (`run_watch`)
- `daemon` command: deprecated watchdog management; `start` checks `watchdog_enabled` config; `stop` sends SIGTERM to PID; `status` checks PID file and process liveness
- `iwh_ctl_app` is a Typer sub-group registered as `lexictl iwh`; `iwh_clean` uses `find_all_iwh()` for discovery, applies `--older-than` age filtering (in hours), deletes matching `.iwh` files from their `.lexibrary/` mirror locations, and reports the count removed
- All heavy imports are lazy (inside command functions) to keep CLI startup fast

## Dragons

- `validate` exits non-zero when errors are found via `report.exit_code()`; `status` mirrors this behavior
- `index` validates that the target directory exists, is a directory, and is within the project root before proceeding
- `daemon stop` reads PID from `.lexibrary.pid`, sends `SIGTERM`, and cleans up stale PID files
- `daemon status` checks process liveness via `os.kill(pid, 0)`; handles `ProcessLookupError` and `PermissionError`
- `update` for a directory argument falls through to the full project update path (pipeline respects `scope_root`)
