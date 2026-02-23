# ignore/patterns

**Summary:** Builds a pathspec `PathSpec` from the config's `additional_patterns` list for use in `IgnoreMatcher`.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `load_config_patterns` | `(config: IgnoreConfig) -> PathSpec` | Create `PathSpec` from `config.additional_patterns` using `"gitignore"` style |

## Dependencies

- `lexibrarian.config.schema` — `IgnoreConfig`
- `pathspec` (third-party)

## Dependents

- `lexibrarian.ignore.__init__` — called by `create_ignore_matcher`
