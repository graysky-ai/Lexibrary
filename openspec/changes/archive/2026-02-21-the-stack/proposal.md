## Why

Agents solving non-trivial bugs repeat work because there's no codebase-embedded record of what's been tried, what failed, and what worked. The existing `GuardrailThread` model (Phase 5 placeholder) is too simple — it lacks Q&A structure, voting, multi-answer support, and cross-artifact search. Phase 6 replaces it with The Stack: a Stack Overflow-inspired knowledge base where agents record problems, solutions, and hard-won lessons as searchable, votable, cross-linked posts.

## What Changes

- **New `stack/` module** — `models.py`, `parser.py`, `serializer.py`, `template.py`, `index.py`, `mutations.py` implementing the full StackPost lifecycle (create, answer, vote, accept, search)
- **New CLI command group `lexi stack`** — `search`, `post`, `answer`, `vote`, `accept`, `view`, `list` sub-commands
- **Unified `lexi search` command** — cross-artifact search across concepts, design files, and Stack posts replacing the current stub
- **Rename `guardrail_refs` to `stack_refs`** in `DesignFile` model; rename `## Guardrails` section to `## Stack` in design file serializer/parser (backward compat for `## Guardrails` during transition) **BREAKING**
- **Wikilink resolver update** — `GR-NNN` pattern replaced by `ST-NNN` for Stack post resolution **BREAKING**
- **Scaffolding update** — `lexi init` creates `stack/` instead of `guardrails/` directory
- **Remove `guardrail_app`** — replace stub `lexi guardrail` and `lexi guardrails` CLI commands with `lexi stack` **BREAKING**

## Capabilities

### New Capabilities
- `stack-post-model`: Pydantic 2 models for StackPost, StackAnswer, StackPostFrontmatter, StackPostRefs
- `stack-parser`: Parse stack post markdown files (YAML frontmatter + append-only body with answers/comments)
- `stack-serializer`: Serialize StackPost model to markdown format
- `stack-template`: Post template rendering for `lexi stack post`
- `stack-index`: In-memory index with search, tag/scope/status/concept filtering
- `stack-mutations`: Append-only mutations — add answer, record vote, accept answer, mark duplicate/outdated
- `stack-cli`: CLI command group `lexi stack` with all sub-commands
- `unified-search`: Cross-artifact `lexi search` command spanning concepts, design files, and Stack posts

### Modified Capabilities
- `artifact-data-models`: `guardrail_refs` field renamed to `stack_refs` in DesignFile model; `GuardrailThread` model removed
- `design-file-models`: Serializer/parser updated for `## Stack` section (backward compat with `## Guardrails`)
- `wikilink-resolver`: `GR-NNN` pattern replaced by `ST-NNN` pattern for Stack post resolution
- `cli-commands`: Guardrail stub commands removed, replaced by `lexi stack` group; `lexi search` becomes unified cross-artifact search
- `project-scaffolding`: `guardrails/` directory replaced by `stack/` in init scaffolding

## Impact

- **New module:** `src/lexibrary/stack/` (6 files)
- **Modified files:** `artifacts/design_file.py`, `artifacts/design_file_serializer.py`, `artifacts/design_file_parser.py`, `wiki/resolver.py`, `cli.py`, `init/scaffolder.py`
- **Removed:** `artifacts/guardrail.py` (model replaced by `stack/models.py`)
- **New directory:** `.lexibrary/stack/` created by `lexi init`
- **No new dependencies** — all implementation uses existing stdlib + Pydantic + Typer + Rich
- **Phase:** 6 (depends on Phase 1 Foundation, Phase 4 Archivist, Phase 5 Concepts Wiki)
- **BAML prompts:** May need updates if any reference "guardrails" — check `baml_src/` during implementation
