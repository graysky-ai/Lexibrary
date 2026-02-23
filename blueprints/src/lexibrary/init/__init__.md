# init

**Summary:** Package for project initialisation helpers: `scaffolder` for `.lexibrary/` skeleton creation, `rules/` subpackage for agent environment rule generation, plus `detection` and `wizard` for interactive init.

## Re-exports

`create_lexibrary_from_wizard`

## Dependents

- `lexibrarian.cli.lexictl_app` -- imports `create_lexibrary_from_wizard` from `lexibrarian.init`
- `lexibrarian.cli.lexictl_app` -- imports `generate_rules` from `lexibrarian.init.rules`
