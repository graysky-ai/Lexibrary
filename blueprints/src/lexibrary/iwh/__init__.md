# iwh

**Summary:** Public API re-exports for the IWH (I Was Here) ephemeral inter-agent signal file module.

## Re-exports

`IWHFile`, `IWHScope`, `consume_iwh`, `ensure_iwh_gitignored`, `parse_iwh`, `read_iwh`, `serialize_iwh`, `write_iwh`

## Dependents

- `lexibrarian.init.scaffolder` -- imports `ensure_iwh_gitignored` for gitignore integration during `lexictl init`
- `lexibrarian.cli.lexictl_app` -- `setup` command calls `ensure_iwh_gitignored`
- `lexibrarian.utils.paths` -- `iwh_path()` computes `.iwh` file locations inside `.lexibrary/`
