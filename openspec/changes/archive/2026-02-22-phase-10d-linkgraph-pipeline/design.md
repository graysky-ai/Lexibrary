## Context

The Lexibrarian archivist pipeline (`archivist/pipeline.py`) orchestrates design file generation. It currently has two entry points:

- `update_project()` -- full project scan, processes all in-scope files, regenerates START_HERE.md
- `update_files()` -- batch processing of specific changed files (used by git hooks, `--changed-only`)

The link graph index (`index.db`) was introduced in Phase 10a (schema) with builder and query interfaces coming in Phases 10b and 10c. This phase wires the builder into the pipeline so the index stays in sync automatically. Without this integration, the index would require a separate manual rebuild step, which defeats the purpose of having it.

The pipeline currently ends after design file generation + .aindex refresh + START_HERE.md. The link graph build becomes a new final step.

### Current Pipeline Flow

```
update_project():
  1. Discover source files within scope_root
  2. For each file: update_file() -> design file generation
  3. Regenerate START_HERE.md
  4. Return UpdateStats

update_files():
  1. For each provided file path: skip deleted/binary/ignored/.lexibrary
  2. For each remaining file: update_file() -> design file generation
  3. Return UpdateStats
```

### Dependencies

- `IndexBuilder` from `linkgraph/builder.py` (Phase 10b) -- provides `full_build()` and `incremental_update(changed_paths)`
- `LinkGraph` from `linkgraph/query.py` (Phase 10c) -- not directly used here but must exist since 10d depends on 10c
- `schema.py` (Phase 10a) -- already done, provides `ensure_schema()`

## Goals / Non-Goals

**Goals:**
- Automatically build the full link graph index at the end of `update_project()`
- Automatically run incremental index updates at the end of `update_files()`
- Handle deleted files in the incremental path (remove artifacts + cascaded links)
- Report link graph build status in `UpdateStats`
- Never block the design file pipeline on index build failures
- Ensure `index.db` is gitignored by the init scaffolder

**Non-Goals:**
- Modifying the `IndexBuilder` API (that is Phase 10b's concern)
- Adding CLI flags for index-only builds (Phase 10e)
- Changing how `lexi lookup` displays reverse links (Phase 10e)
- Adding config keys for index behavior (not needed -- builder uses project root)
- Making the index build async/concurrent (follows existing sequential MVP pattern per D-025)

## Decisions

### D1: Link graph build placement -- after START_HERE.md in update_project()

The index build runs as the very last step in `update_project()`, after START_HERE.md generation. This ensures all design files, concepts, Stack posts, and .aindex files are fully up to date before the index scans them.

**Alternative considered:** Running the index build in parallel with START_HERE.md generation. Rejected because START_HERE.md may reference design file content that the index also reads, and the sequential overhead is negligible (index build is I/O-bound markdown parsing, not LLM-bound).

### D2: Incremental update in update_files() with deletion tracking

`update_files()` already silently skips deleted files (files in the input list that no longer exist on disk). This phase changes that behavior: deleted file paths are collected and forwarded to `IndexBuilder.incremental_update()` so their artifact rows and cascaded links are cleaned up.

The actual design file deletion (removing the `.md` file from `.lexibrary/`) is NOT handled here -- that is a separate concern. The index builder handles removing the index entries for files that no longer have corresponding design files.

**Alternative considered:** Ignoring deletions in the incremental path. Rejected because stale artifact rows with dangling links would accumulate, producing incorrect query results.

### D3: Fail-safe wrapping -- index errors never block the pipeline

The entire link graph build step is wrapped in a try/except. If the builder raises any exception (SQLite corruption, permission errors, disk full), the error is:
1. Logged at ERROR level
2. Recorded in `UpdateStats` (new `linkgraph_error` field)
3. The pipeline still returns success for the design file portion

This matches the graceful degradation philosophy from D-071. The index is a derived artifact; its failure should never prevent design file generation.

### D4: UpdateStats extension -- minimal additions

Two new fields on `UpdateStats`:
- `linkgraph_built: bool = False` -- set to True when the index build completes successfully
- `linkgraph_error: str | None = None` -- error message if the build failed

No counters for artifacts/links indexed (that information is in the `build_log` table and `meta` table within the database itself).

### D5: Import strategy -- conditional import of builder

The pipeline imports `IndexBuilder` at the top of the module. Since Phase 10b must be complete before this phase, the import is always available. No lazy importing or optional dependency handling needed.

However, if `index.db` cannot be created (e.g., read-only filesystem), the builder will raise an exception caught by the fail-safe wrapper (D3).

### D6: Temp file for atomic write must be in same directory

Per D-060 and the master plan warning, `os.replace()` requires the temp file to be on the same filesystem as the target. The `IndexBuilder` (Phase 10b) is responsible for this -- it writes to a temp file in `.lexibrary/` alongside `index.db`. This phase does not add any new atomic write logic; it delegates to the builder.

## Risks / Trade-offs

- **[Risk] IndexBuilder API not yet finalized** -- Phase 10b defines the builder API. If `full_build()` or `incremental_update()` signatures change, this integration code changes too.
  - Mitigation: The proposal defines clear expected signatures. Implement 10b first.

- **[Risk] Large project full rebuild adds latency to update_project()** -- On a project with thousands of design files, the full index build adds I/O time to `update_project()`.
  - Mitigation: The build is I/O-bound (parsing markdown), not LLM-bound. Expected overhead is seconds, not minutes. If profiling shows otherwise, a future phase can make it async.

- **[Risk] Incremental update misses deletions from outside the pipeline** -- If a user manually deletes a design file, the pipeline won't know about it. The index will have stale entries until the next `update_project()` full build.
  - Mitigation: Acceptable for MVP. `lexictl validate` (Phase 10f) will detect stale index entries.

- **[Trade-off] No separate "rebuild index" command** -- Users cannot rebuild the index without running the full design file pipeline.
  - Mitigation: Phase 10e may add `lexictl update --index-only`. For now, deleting `index.db` and running `lexictl update` works.
