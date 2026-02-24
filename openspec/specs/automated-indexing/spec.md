# automated-indexing Specification

## Purpose
TBD - created by archiving change cli-command-rebalance. Update Purpose after archive.
## Requirements
### Requirement: Update pipeline regenerates indexes for affected directories
The `update_project()` pipeline SHALL regenerate `.aindex` files for directories that contained updated files after design file generation completes. For each affected directory, the pipeline SHALL also re-index ancestor directories up to `scope_root` to ensure parent `.aindex` child maps reflect updated child summaries.

#### Scenario: Hook-triggered update regenerates indexes
- **WHEN** `lexictl update --changed-only src/auth/login.py src/auth/session.py` runs via the post-commit hook
- **THEN** `.aindex` files SHALL be regenerated for `src/auth/` and all ancestor directories up to `scope_root`

#### Scenario: Full project update regenerates all indexes
- **WHEN** `lexictl update` runs with no arguments (full project update)
- **THEN** `.aindex` files SHALL be regenerated for all directories within `scope_root`

#### Scenario: Sweep regenerates indexes
- **WHEN** `DaemonService.run_once()` or `DaemonService.run_watch()` triggers a sweep via `update_project()`
- **THEN** `.aindex` files SHALL be regenerated for directories containing files that were updated during the sweep

#### Scenario: Re-indexing includes ancestor directories
- **WHEN** a file at `src/payments/stripe/client.py` is updated
- **THEN** `.aindex` files SHALL be regenerated for `src/payments/stripe/`, `src/payments/`, and `src/`

#### Scenario: Re-indexing is skipped when no files changed
- **WHEN** `update_project()` runs and `UpdateStats` reports zero files created, updated, or failed
- **THEN** no `.aindex` regeneration SHALL occur

### Requirement: Index regeneration uses existing indexer module
The automated index regeneration SHALL use the same `IndexGenerator` (or equivalent indexer function) used by the `index` CLI command. No new indexer logic SHALL be introduced.

#### Scenario: Automated index produces identical output to manual index
- **WHEN** the pipeline regenerates `.aindex` for `src/auth/`
- **THEN** the resulting `.aindex` file SHALL be identical to one produced by running `lexictl index src/auth/`

