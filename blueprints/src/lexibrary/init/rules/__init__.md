# init/rules

**Summary:** Agent environment rule generation -- dispatches to per-environment generators (Claude Code, Cursor, Codex) and provides the public API for `lexictl setup --update`.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `supported_environments` | `() -> list[str]` | Return sorted list of supported environment names (currently `["claude", "codex", "cursor"]`) |
| `generate_rules` | `(project_root: Path, environments: list[str]) -> dict[str, list[Path]]` | Generate agent rule files for specified environments; raises `ValueError` for unsupported environment names; returns mapping of env name to list of created/updated file paths |

## Dependencies

- `lexibrarian.init.rules.claude` -- `generate_claude_rules`
- `lexibrarian.init.rules.cursor` -- `generate_cursor_rules`
- `lexibrarian.init.rules.codex` -- `generate_codex_rules`

## Dependents

- `lexibrarian.cli.lexictl_app` -- `setup --update` command calls `generate_rules()`

## Key Concepts

- `_GENERATORS` dict maps environment name strings to callable generators
- `generate_rules()` validates all environment names before calling any generator (fail-fast on unsupported names)
- Each generator takes `project_root: Path` and returns `list[Path]` of files created/updated
