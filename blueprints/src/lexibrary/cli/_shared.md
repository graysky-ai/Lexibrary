# cli/_shared

**Summary:** Shared CLI helpers used by both `lexi_app` and `lexictl_app` -- provides the Rich console instance, project root resolution with friendly error handling, and a stub printer for unimplemented commands.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `console` | `rich.console.Console` | Module-level Rich console instance -- all CLI output goes through this; no bare `print()` |
| `require_project_root` | `() -> Path` | Resolve the project root via `find_project_root()` or exit with a user-friendly error directing to `lexictl init` |
| `stub` | `(name: str) -> None` | Print a standard "not yet implemented" message for stub commands; calls `require_project_root()` first so stubs fail gracefully outside a project |

## Dependencies

- `lexibrarian.exceptions` -- `LexibraryNotFoundError`
- `lexibrarian.utils.root` -- `find_project_root`

## Dependents

- `lexibrarian.cli.lexi_app` -- imports `console`, `require_project_root`
- `lexibrarian.cli.lexictl_app` -- imports `console`, `require_project_root`, `stub`

## Key Concepts

- Extracted from the old monolithic `cli.py` where these were private functions (`_require_project_root`, `_stub`); now public since they are cross-module exports
- Error message in `require_project_root()` directs users to `lexictl init` (not `lexi init`)
- `stub()` is used by `lexictl_app.py` for the `setup` and `daemon` commands that are not yet implemented

## Dragons

- `require_project_root()` raises `typer.Exit(1)` on failure -- callers do not need try/except
- `stub()` calls `require_project_root()` internally, so stub commands still fail gracefully when run outside a Lexibrarian project
