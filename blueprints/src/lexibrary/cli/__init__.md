# cli/__init__

**Summary:** Package initializer for the CLI package; re-exports `lexi_app` and `lexictl_app` so that entry points and `__main__.py` can import them from `lexibrarian.cli`.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `lexi_app` | `typer.Typer` | Re-exported from `lexi_app.py` -- agent-facing CLI |
| `lexictl_app` | `typer.Typer` | Re-exported from `lexictl_app.py` -- maintenance CLI |

## Dependencies

- `lexibrarian.cli.lexi_app` -- `lexi_app`
- `lexibrarian.cli.lexictl_app` -- `lexictl_app`

## Dependents

- `pyproject.toml` entry points -- `lexi = "lexibrarian.cli:lexi_app"`, `lexictl = "lexibrarian.cli:lexictl_app"`
- `lexibrarian.__main__` -- imports `lexi_app` for `python -m lexibrarian`

## Key Concepts

- The old `from lexibrarian.cli import app` import path no longer works (pre-1.0, no backwards-compatibility alias)
- `__all__` explicitly lists `lexi_app` and `lexictl_app`
