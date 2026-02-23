## Why

The link graph index (`.lexibrary/index.db`) is built by `IndexBuilder` but has no automatic trigger -- it must be invoked manually. Wiring the builder into the existing `update_project()` and `update_files()` pipeline functions ensures the index is always kept in sync with the design files it indexes, without requiring a separate maintenance step. This is the critical integration point on the 10a -> 10b -> **10d** -> 10e path that unlocks CLI features (reverse lookups, FTS search, tag acceleration) in Phase 10e.

## What Changes

- `update_project()` in `archivist/pipeline.py` calls `IndexBuilder.full_build()` after all design files are generated and START_HERE.md is refreshed (pipeline step 6, after existing step 5)
- `update_files()` in `archivist/pipeline.py` calls `IndexBuilder.incremental_update(changed_paths)` after processing all files in the batch
- `UpdateStats` gains a `linkgraph_built` boolean and `linkgraph_error` optional string for reporting
- File deletions passed to `update_files()` (files that no longer exist) are collected and forwarded to `incremental_update()` so artifact rows and cascaded links are cleaned up
- `lexictl init` scaffolder ensures `index.db` is included in `.gitignore`
- The link graph build step is wrapped in a try/except so failures never block the design file pipeline -- errors are logged and reported in stats

## Capabilities

### New Capabilities
- `linkgraph-pipeline-integration`: Automatic link graph index building as a post-processing step in the archivist pipeline

### Modified Capabilities
- `archivist-pipeline`: Pipeline gains a final step that builds/updates the link graph index after design file generation
- `changed-only-pipeline`: Batch file processing gains incremental link graph update and deletion handling

## Impact

- **Modified code:** `src/lexibrary/archivist/pipeline.py` -- `update_project()`, `update_files()`, `UpdateStats`
- **Dependencies (consumed):** `src/lexibrary/linkgraph/builder.py` (Phase 10b), `src/lexibrary/linkgraph/query.py` (Phase 10c) -- both must exist before this phase
- **Config:** No new config keys required -- the builder uses project root and `.lexibrary/` path already available in the pipeline context
- **New dependencies:** None -- `sqlite3` is stdlib
- **Init scaffolder:** `.gitignore` update to include `index.db` pattern (may already be present from Phase 10a)
- **Testing:** Integration tests with `tmp_path` verifying index is built after pipeline runs
