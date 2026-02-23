## Why

Coding agents using `lexi` have no way to self-orient. There is no `lexi help` command explaining workflows and navigation patterns, and the `lexi concepts` command only supports a bare positional search — agents cannot filter by tag or status, forcing them to scan full listings and waste context tokens on draft or deprecated concepts.

## What Changes

- Add `lexi help` command that outputs structured guidance on available commands, workflows, and how to navigate the library — beyond what `--help` provides
- Add `--tag <t>` option to `lexi concepts` to filter concepts by tag (leverages existing `ConceptIndex.by_tag()`)
- Add `--status <s>` option to `lexi concepts` to filter by status (`active`, `draft`, `deprecated`)
- Add `--all` flag to `lexi concepts` to explicitly include deprecated concepts (change default to hide deprecated)

## Capabilities

### New Capabilities
- `agent-help`: Agent-facing help command providing workflow guidance, command explanations, and navigation patterns for coding agents working inside a Lexibrary project

### Modified Capabilities
- `concept-cli`: Add `--tag`, `--status`, and `--all` filtering options to the `lexi concepts` command; change default listing to exclude deprecated concepts

## Impact

- **Files modified**: `src/lexibrary/cli/lexi_app.py` (help command + concepts filters), tests
- **Files modified**: `blueprints/src/lexibrary/cli/lexi_app.md` (design file update)
- **Specs modified**: `concept-cli` (new filter requirements + scenarios)
- **Specs added**: `agent-help` (new command spec)
- **Dependencies**: None — uses existing Rich, Typer, and ConceptIndex infrastructure
- **Breaking change**: `lexi concepts` default listing will exclude deprecated concepts (minor — `--all` restores previous behaviour)
- **Phase**: Current (CLI layer only, no new deps)
