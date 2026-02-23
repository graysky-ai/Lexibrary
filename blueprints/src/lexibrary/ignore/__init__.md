# ignore

**Summary:** Re-exports the public ignore API and provides `create_ignore_matcher()` as the single factory entry point.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `create_ignore_matcher` | `(config: LexibraryConfig, root: Path) -> IgnoreMatcher` | Factory: build `IgnoreMatcher` from config + optional gitignore loading |

## Re-exports

`IgnoreMatcher`, `load_gitignore_specs`, `load_config_patterns`

## Dependents

- `lexibrarian.daemon.service` — calls `create_ignore_matcher`
- Crawler setup code will call this too once implemented
