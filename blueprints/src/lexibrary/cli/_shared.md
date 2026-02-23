# cli/_shared

**Summary:** Shared CLI helpers used by both `lexi_app` and `lexictl_app` -- provides the Rich console instance, project root resolution with friendly error handling, a stub printer for unimplemented commands, and the dotenv startup hook.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `console` | `rich.console.Console` | Module-level Rich console instance -- all CLI output goes through this; no bare `print()` |
| `require_project_root` | `() -> Path` | Resolve the project root via `find_project_root()` or exit with a user-friendly error directing to `lexictl init` |
| `stub` | `(name: str) -> None` | Print a standard "not yet implemented" message for stub commands; calls `require_project_root()` first so stubs fail gracefully outside a project |
| `load_dotenv_if_configured` | `() -> None` | Typer callback for dotenv startup loading; reads raw YAML from `config.yaml` (no Pydantic), checks `llm.api_key_source`, and calls `load_dotenv(project_root / ".env", override=False)` when it equals `"dotenv"`; silently swallows all errors |

## Dependencies

- `lexibrary.exceptions` -- `LexibraryNotFoundError`
- `lexibrary.utils.root` -- `find_project_root`
- `yaml` (PyYAML) -- raw config reading in `load_dotenv_if_configured` (lazy import)
- `dotenv` (`python-dotenv`) -- `load_dotenv` in `load_dotenv_if_configured` (lazy import)

## Dependents

- `lexibrary.cli.lexi_app` -- imports `console`, `load_dotenv_if_configured`, `require_project_root`
- `lexibrary.cli.lexictl_app` -- imports `console`, `load_dotenv_if_configured`, `require_project_root`

## Key Concepts

- Extracted from the old monolithic `cli.py` where these were private functions (`_require_project_root`, `_stub`); now public since they are cross-module exports
- Error message in `require_project_root()` directs users to `lexictl init` (not `lexi init`)
- `stub()` is used by `lexictl_app.py` for the `setup` and `daemon` commands that are not yet implemented
- `load_dotenv_if_configured()` is registered as the Typer `callback` on both `lexi_app` and `lexictl_app`, running before any command
- `load_dotenv_if_configured()` reads raw YAML (not Pydantic-validated) to avoid importing the full config stack at startup; only activates when `llm.api_key_source` equals `"dotenv"`
- `override=False` in `load_dotenv()` means env vars already set in the shell take precedence over `.env` file values
- All errors in `load_dotenv_if_configured()` are silently swallowed -- the real error surfaces later when a command actually needs the config

## Dragons

- `require_project_root()` raises `typer.Exit(1)` on failure -- callers do not need try/except
- `stub()` calls `require_project_root()` internally, so stub commands still fail gracefully when run outside a Lexibrary project
- `load_dotenv_if_configured()` uses a bare `except Exception` to swallow all errors including `LexibraryNotFoundError` from `find_project_root()` and `FileNotFoundError` from missing `.env` files; this is intentional to avoid breaking CLI startup
