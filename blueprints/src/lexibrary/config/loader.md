# config/loader

**Summary:** Loads and shallow-merges global (`~/.config/lexibrarian/config.yaml`) and project (`.lexibrary/config.yaml`) YAML files into a validated `LexibraryConfig`.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `load_config` | `(project_root: Path | None, global_config_path: Path | None) -> LexibraryConfig` | Load, merge, and validate config |
| `GLOBAL_CONFIG_PATH` | `Path` | Default global config path (`~/.config/lexibrarian/config.yaml`); respects `XDG_CONFIG_HOME` |

## Dependencies

- `lexibrarian.config.schema` — `LexibraryConfig`

## Dependents

- `lexibrarian.config.__init__` — re-exports `load_config`
- `lexibrarian.daemon.service` — calls `load_config`

## Key Concepts

- Merge strategy: global keys → overridden by project top-level keys (shallow merge only — nested keys are fully replaced, not deep-merged)
- Missing config files are silently skipped; pydantic defaults apply
