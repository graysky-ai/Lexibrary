## Why

Phase 5 delivers the Concepts Wiki — a living wiki of cross-cutting concepts that agents maintain alongside code. Currently, knowledge about conventions, patterns, and architectural decisions is either scattered across design files or exists only in agents' session context. Agents need a structured, searchable way to discover and reference cross-cutting knowledge like "all monetary values use Decimal" or "JWT auth with refresh token rotation."

## What Changes

- Replace the stub `ConceptFile` model with a full model including `ConceptFileFrontmatter` (title, aliases, tags, status) and parsed body fields
- Create new `src/lexibrary/wiki/` module with: concept parser, serializer, template renderer, concept index (search/filter), and wikilink resolver
- Implement CLI commands: `lexi concepts` (list/search), `lexi concept new` (create from template), `lexi concept link` (add wikilink to design file)
- Update design file serializer to wrap wikilinks in `[[brackets]]`
- Update design file parser to handle both bracketed and unbracketed wikilink formats
- Update Archivist BAML prompt and pipeline to accept optional `available_concepts` parameter for concept-aware wikilink suggestions

## Capabilities

### New Capabilities
- `concept-file-model`: Full ConceptFile + ConceptFileFrontmatter Pydantic 2 models with mandatory frontmatter validation
- `concept-parser`: Parse concept files from disk (YAML frontmatter + markdown body extraction, section parsing)
- `concept-serializer`: Serialize ConceptFile to markdown (used by template generation)
- `concept-template`: Render concept file templates for `lexi concept new`
- `concept-index`: Build and query concept index (search by name/alias/tag/summary, exact find, tag filter)
- `wikilink-resolver`: Shared wikilink resolution utility (bracket stripping → guardrail pattern → exact name → alias → fuzzy match)
- `concept-cli`: CLI commands for `lexi concepts`, `lexi concept new`, `lexi concept link`

### Modified Capabilities
- `design-file-models`: Wikilink serialization changes to `[[bracket]]` format; parser updated to strip brackets on parse (backward-compatible)
- `archivist-service`: Accept optional `available_concepts` parameter and pass to BAML prompt
- `archivist-pipeline`: Build concept name list and pass to Archivist service during `update_file()`
- `archivist-baml`: Add `available_concepts` optional parameter to `ArchivistGenerateDesignFile` prompt

## Impact

- **New module:** `src/lexibrary/wiki/` (resolver.py, parser.py, serializer.py, index.py, template.py)
- **Updated model:** `src/lexibrary/artifacts/concept.py` — stub replaced with full model (non-breaking, no existing callers)
- **Updated serializer:** `src/lexibrary/artifacts/design_file_serializer.py` — wikilinks wrapped in `[[brackets]]`
- **Updated parser:** `src/lexibrary/artifacts/design_file_parser.py` — bracket stripping for wikilinks
- **Updated BAML:** `baml_src/archivist_design_file.baml` — new optional parameter
- **Updated pipeline:** `src/lexibrary/archivist/pipeline.py` and `service.py` — concept awareness
- **Updated CLI:** `src/lexibrary/cli.py` — new commands
- **New directory at runtime:** `.lexibrary/concepts/` created by `lexi concept new`
- **No new external dependencies** — uses existing stdlib + pydantic + rich
- **Phase:** 5 (depends on Phase 1 Foundation + Phase 4 Archivist, both complete)
