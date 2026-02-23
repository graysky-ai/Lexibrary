# cli/lexictl_app

**Summary:** Maintenance Typer CLI app (`lexictl`) providing wizard-based project initialization, design file generation (with `--changed-only` support), validation, status reporting, agent rule setup (with `--hooks`), library sweeps, and deprecated watchdog daemon management.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `lexictl_app` | `typer.Typer` | Root maintenance CLI application registered as the `lexictl` entry point |
| `init` | `(*, defaults: bool) -> None` | Run the 8-step init wizard via `run_wizard()`; `--defaults` flag accepts all detected values without prompting; re-init guard prevents overwriting existing `.lexibrary/`; non-TTY guard requires `--defaults` |
| `update` | `(path: Path \| None, *, changed_only: list[Path] \| None) -> None` | Generate/update design files via archivist pipeline; supports `--changed-only` for git-hook usage (calls `update_files`); mutually exclusive with `path`; single file, directory, or full project mode |
| `validate` | `(*, severity: str \| None, check: str \| None, json_output: bool) -> None` | Run consistency checks with optional severity/check filters; outputs Rich tables or JSON; exits with `report.exit_code()` |
| `status` | `(path: Path \| None, *, quiet: bool) -> None` | Dashboard showing design file counts/staleness, concept counts by status, stack post counts, link graph health (artifact/link counts + built_at timestamp), validation issues summary, last updated timestamp; `--quiet`/`-q` for CI/hooks single-line output (omits link graph line) |
| `setup` | `(*, update_flag: bool, env: list[str] \| None, hooks: bool) -> None` | Install or update agent environment rules; `--hooks` flag installs the git post-commit hook; `--update` flag regenerates agent rules; reads `agent_environment` from config |
| `sweep` | `(*, watch: bool) -> None` | Run a library update sweep; one-shot by default, `--watch` for periodic sweeps in foreground |
| `daemon` | `(action: str \| None) -> None` | Deprecated watchdog daemon management; actions: `start`, `stop`, `status`; defaults to `start` |

## Dependencies

- `lexibrary.cli._shared` -- `console`, `require_project_root`
- `lexibrary.cli.banner` -- `render_banner` (lazy import in `init`)
- `lexibrary.init.wizard` -- `run_wizard` (lazy import in `init`)
- `lexibrary.init.scaffolder` -- `create_lexibrary_from_wizard` (lazy import in `init`)
- `lexibrary.archivist.pipeline` -- `UpdateStats`, `update_file`, `update_files`, `update_project` (lazy import in `update`)
- `lexibrary.archivist.service` -- `ArchivistService` (lazy import in `update`)
- `lexibrary.config.loader` -- `load_config` (lazy import in `update`, `status`, `setup`, `daemon`)
- `lexibrary.llm.rate_limiter` -- `RateLimiter` (lazy import in `update`)
- `lexibrary.validator` -- `AVAILABLE_CHECKS`, `validate_library` (lazy imports in `validate`, `status`)
- `lexibrary.artifacts.design_file_parser` -- `parse_design_file_metadata` (lazy import in `status`)
- `lexibrary.stack.parser` -- `parse_stack_post` (lazy import in `status`)
- `lexibrary.wiki.parser` -- `parse_concept_file` (lazy import in `status`)
- `lexibrary.linkgraph.health` -- `read_index_health` (lazy import in `status`)
- `lexibrary.init.rules` -- `generate_rules`, `supported_environments` (lazy import in `setup`)
- `lexibrary.iwh.gitignore` -- `ensure_iwh_gitignored` (lazy import in `setup`)
- `lexibrary.hooks.post_commit` -- `install_post_commit_hook` (lazy import in `setup`)
- `lexibrary.daemon.service` -- `DaemonService` (lazy import in `sweep`, `daemon`)

## Dependents

- `lexibrary.cli.__init__` -- re-exports `lexictl_app`
- `pyproject.toml` -- `lexictl` entry point

## Key Concepts

- `init` displays a startup banner (truecolor block art or ASCII fallback) via `render_banner()` before running the wizard
- `init` uses `run_wizard()` + `create_lexibrary_from_wizard()` instead of the old `create_lexibrary_skeleton()`
- `init` does not call `require_project_root()` -- it creates the project root (uses `Path.cwd()` instead)
- `init` has a re-init guard (checks for existing `.lexibrary/`) and a non-TTY guard (requires `--defaults`)
- `update` supports `--changed-only` flag: accepts a list of file paths, calls `update_files()` for batch processing (designed for git hooks / CI)
- `update` enforces mutual exclusivity: providing both `path` and `--changed-only` prints an error and exits
- `setup --hooks` calls `install_post_commit_hook()` and reports the result; returns early (does not generate agent rules)
- `setup --update` with optional `--env` overrides; reads `agent_environment` list from config; validates against `supported_environments()`
- `sweep` command: one-shot (`run_once`) by default; `--watch` for periodic sweeps (`run_watch`)
- `daemon` command: deprecated watchdog management; `start` checks `watchdog_enabled` config; `stop` sends SIGTERM to PID; `status` checks PID file and process liveness
- `status` full dashboard includes a link graph health line (placed after Stack, before Issues): shows `"Link graph: N artifacts, M links (built <timestamp>)"` when index exists, or `"Link graph: not built (run lexictl update to create)"` when absent; uses `read_index_health()` from `linkgraph.health`
- `status` quiet mode (`-q`) outputs a single line for CI/hooks integration; prefix is `"lexictl:"` (not `"lexi:"`); quiet mode omits the link graph line
- All heavy imports are lazy (inside command functions) to keep CLI startup fast

## Dragons

- `validate` exits non-zero when errors are found via `report.exit_code()`; `status` mirrors this behavior
- `status` quiet-mode output changes based on whether there are errors, warnings, both, or neither
- `daemon stop` reads PID from `.lexibrary.pid`, sends `SIGTERM`, and cleans up stale PID files
- `daemon status` checks process liveness via `os.kill(pid, 0)`; handles `ProcessLookupError` and `PermissionError`
- `update` for a directory argument falls through to the full project update path (pipeline respects `scope_root`)
