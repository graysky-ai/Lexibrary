# cli/__init__

**Summary:** Package initializer for the CLI package; re-exports `lexi_app` and `lexictl_app` so that entry points and `__main__.py` can import them from `lexibrary.cli`.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `lexi_app` | `typer.Typer` | Re-exported from `lexi_app.py` -- agent-facing CLI |
| `lexictl_app` | `typer.Typer` | Re-exported from `lexictl_app.py` -- maintenance CLI |

## Dependencies

- `lexibrary.cli.lexi_app` -- `lexi_app`
- `lexibrary.cli.lexictl_app` -- `lexictl_app`

## Dependents

- `pyproject.toml` entry points -- `lexi = "lexibrary.cli:lexi_app"`, `lexictl = "lexibrary.cli:lexictl_app"`
- `lexibrary.__main__` -- imports `lexi_app` for `python -m lexibrary`

## Key Concepts

- The old `from lexibrary.cli import app` import path no longer works (pre-1.0, no backwards-compatibility alias)
- `__all__` explicitly lists `lexi_app` and `lexictl_app`
