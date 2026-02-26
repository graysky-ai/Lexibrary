## Why

Conventions are referenced in 8+ locations across the codebase (model, generator, serializer, parser, link graph, CLI, validator, BAML prompts) but produce zero data. The pipeline is fully plumbed with `local_conventions=[]` hard-coded in the generator, making every downstream consumer a no-op. Meanwhile, the only conventions agents can find are hallucinated by the START_HERE LLM prompt. This change replaces the broken pipeline with file-based conventions as a first-class artifact — mirroring the concepts system — so agents get real, user-controlled, scope-aware coding rules at edit time.

## What Changes

- **New convention file artifact**: `.lexibrary/conventions/*.md` files with YAML frontmatter (title, scope, tags, status, source, priority) and markdown body. Parallel to concepts.
- **New `ConventionIndex` class**: Load, query, and filter conventions from the file system. Primary retrieval path for CLI and lookup.
- **New CLI commands**: `lexi convention new`, `lexi convention approve`, `lexi conventions` (list/filter) for convention lifecycle management.
- **`lexi lookup` convention delivery rewrite**: Replace the `.aindex` parent-directory walk with `ConventionIndex.find_by_scope()`, respecting display limit (default 5) and priority ordering.
- **Config extensions**: `ConventionConfig` with `lookup_display_limit`, and `conventions` list for user-declared baseline conventions that get materialized as files during build.
- **Remove `local_conventions` from `.aindex`**: **BREAKING** — Drop the field from `AIndexFile`, remove `## Local Conventions` section from serializer/parser, remove `local_conventions=[]` from generator.
- **Link graph convention processing rewrite**: Builder reads from `.lexibrary/conventions/*.md` instead of `.aindex` `local_conventions`. Extend `conventions` table schema with `source`, `status`, `priority` columns. Extend `ConventionResult` with metadata.
- **Scaffolder update**: Add `.lexibrary/conventions/` directory with `.gitkeep` to skeleton.
- **START_HERE cleanup**: Remove `convention_index` from BAML prompt and assembly; replace with pointer to `lexi lookup` / `lexi conventions`.
- **Sign-off workflow**: Agent-created conventions start as `status: draft`, promoted via `lexi convention approve`.

## Capabilities

### New Capabilities
- `convention-file-model`: ConventionFile Pydantic model, parser, and serializer for `.lexibrary/conventions/*.md` files with YAML frontmatter
- `convention-index`: ConventionIndex class for loading, querying by scope, filtering by tag/status, and scope resolution algorithm
- `convention-cli`: CLI commands for convention lifecycle — `lexi convention new`, `lexi convention approve`, `lexi conventions` list/filter
- `convention-config`: Config schema extensions for user-declared conventions and display limit

### Modified Capabilities
- `lookup-conventions`: Rewrite from `.aindex` walk to `ConventionIndex.find_by_scope()` with display limit and priority ordering
- `artifact-data-models`: Remove `local_conventions: list[str]` from `AIndexFile`
- `aindex-serializer`: Remove `## Local Conventions` section from output
- `aindex-parser`: Remove convention parsing block
- `linkgraph-full-build`: Rewrite convention processing to read from convention files; extend schema with source/status/priority columns
- `project-scaffolding`: Add `.lexibrary/conventions/` directory to skeleton
- `start-here-generation`: Remove `convention_index` from BAML prompt and assembly
- `cli-commands`: Add `lexi conventions` and `lexi convention` to agent command list

## Impact

- **Artifacts**: New `src/lexibrary/conventions/` package (4 modules: `__init__`, `index`, `parser`, `serializer`). New `src/lexibrary/artifacts/convention.py` model.
- **Config**: New fields on `LexibraryConfig` for convention config and user-declared conventions.
- **CLI**: New command group `convention` (new, approve) and `conventions` (list/filter) on the `lexi` app.
- **Link graph**: Schema migration (new columns on `conventions` table). Builder rewrite for convention processing.
- **BAML**: Remove `convention_index` from `archivist_start_here.baml` and `types.baml`.
- **Breaking**: `.aindex` files lose `## Local Conventions` section (pre-launch, no migration needed per D8).
- **No new dependencies** — uses existing Pydantic 2, PyYAML, pathlib, Rich.
