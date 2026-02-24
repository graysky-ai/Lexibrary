# cli/_shared

**Summary:** Shared CLI helpers used by both `lexi_app` and `lexictl_app` -- provides the Rich console instance, project root resolution with friendly error handling, a stub printer for unimplemented commands, the dotenv startup hook, and shared command implementations for `validate` and `status`.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `console` | `rich.console.Console` | Module-level Rich console instance -- all CLI output goes through this; no bare `print()` |
| `require_project_root` | `() -> Path` | Resolve the project root via `find_project_root()` or exit with a user-friendly error directing to `lexictl init` |
| `stub` | `(name: str) -> None` | Print a standard "not yet implemented" message for stub commands; calls `require_project_root()` first so stubs fail gracefully outside a project |
| `_run_validate` | `(project_root: Path, *, severity: str \| None, check: str \| None, json_output: bool) -> int` | Run validation checks and render output via Rich tables or JSON; returns exit code (0 = clean, 1 = errors, 2 = warnings only) |
| `_run_status` | `(project_root: Path, *, path: Path \| None, quiet: bool, cli_prefix: str) -> int` | Collect library health data and render a full status dashboard or quiet single-line output; returns exit code (0 = clean, 1 = errors, 2 = warnings only) |
| `load_dotenv_if_configured` | `() -> None` | Typer callback for dotenv startup loading; reads raw YAML from `config.yaml` (no Pydantic), checks `llm.api_key_source`, and calls `load_dotenv(project_root / ".env", override=False)` when it equals `"dotenv"`; silently swallows all errors |

## Dependencies

- `lexibrary.exceptions` -- `LexibraryNotFoundError`
- `lexibrary.utils.root` -- `find_project_root`
- `lexibrary.validator` -- `AVAILABLE_CHECKS`, `validate_library` (lazy import in `_run_validate`, `_run_status`)
- `lexibrary.artifacts.design_file_parser` -- `parse_design_file_metadata` (lazy import in `_run_status`)
- `lexibrary.wiki.parser` -- `parse_concept_file` (lazy import in `_run_status`)
- `lexibrary.stack.parser` -- `parse_stack_post` (lazy import in `_run_status`)
- `lexibrary.linkgraph.health` -- `read_index_health` (lazy import in `_run_status`)
- `yaml` (PyYAML) -- raw config reading in `load_dotenv_if_configured` (lazy import)
- `dotenv` (`python-dotenv`) -- `load_dotenv` in `load_dotenv_if_configured` (lazy import)

## Dependents

- `lexibrary.cli.lexi_app` -- imports `console`, `load_dotenv_if_configured`, `require_project_root`, `_run_validate`, `_run_status`
- `lexibrary.cli.lexictl_app` -- imports `console`, `load_dotenv_if_configured`, `require_project_root`, `_run_validate`, `_run_status`

## Key Concepts

- Extracted from the old monolithic `cli.py` where these were private functions (`_require_project_root`, `_stub`); now public since they are cross-module exports
- Error message in `require_project_root()` directs users to `lexictl init` (not `lexi init`)
- `stub()` is used by `lexictl_app.py` for commands that are not yet implemented
- `load_dotenv_if_configured()` is registered as the Typer `callback` on both `lexi_app` and `lexictl_app`, running before any command
- `load_dotenv_if_configured()` reads raw YAML (not Pydantic-validated) to avoid importing the full config stack at startup; only activates when `llm.api_key_source` equals `"dotenv"`
- `override=False` in `load_dotenv()` means env vars already set in the shell take precedence over `.env` file values
- All errors in `load_dotenv_if_configured()` are silently swallowed -- the real error surfaces later when a command actually needs the config
- `_run_validate()` accepts parsed CLI args, calls `validate_library()`, and renders results; shows available checks on unknown check name; returns exit code for the caller to raise `typer.Exit()`
- `_run_status()` collects library health data from multiple sources (design files, concepts, stack posts, link graph, validation report) and renders either a full Rich dashboard or a single quiet-mode line; accepts `cli_prefix` parameter so output reflects the calling CLI (`"lexi"` or `"lexictl"`)
- `_run_status()` full dashboard includes: design file counts with staleness, concept counts by status, stack post counts, link graph health (artifact/link counts and built_at timestamp), validation issues summary, last updated timestamp with human-readable relative time
- `_run_status()` quiet mode outputs a single line for CI/hooks; format varies based on error/warning counts; prefix is the `cli_prefix` value

## Dragons

- `require_project_root()` raises `typer.Exit(1)` on failure -- callers do not need try/except
- `stub()` calls `require_project_root()` internally, so stub commands still fail gracefully when run outside a Lexibrary project
- `load_dotenv_if_configured()` uses a bare `except Exception` to swallow all errors including `LexibraryNotFoundError` from `find_project_root()` and `FileNotFoundError` from missing `.env` files; this is intentional to avoid breaking CLI startup
- `_run_status()` quiet-mode output changes based on whether there are errors, warnings, both, or neither
- `_run_status()` quiet mode omits the link graph line
