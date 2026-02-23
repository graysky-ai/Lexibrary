## Context

Phase 5 builds on the completed Phase 1 (Foundation) and Phase 4 (Archivist) infrastructure. The codebase already has:
- A stub `ConceptFile` model in `src/lexibrary/artifacts/concept.py` (no callers yet)
- Design file parser/serializer with wikilinks support (stored as plain strings)
- Archivist BAML prompts and pipeline for design file generation
- CLI with Typer, Rich console output

The concepts wiki introduces cross-cutting knowledge management — concept files live in `.lexibrary/concepts/` and are referenced via `[[wikilinks]]` from design files and other concepts. Agents are the primary authors; the Archivist only suggests wikilinks to existing concepts.

## Goals / Non-Goals

**Goals:**
- Provide a `wiki/` module with concept parsing, indexing, wikilink resolution, and template generation
- Replace the `ConceptFile` stub with a full model separating frontmatter (validated) from body (freeform)
- Deliver CLI commands for listing, searching, creating, and linking concepts
- Make the Archivist concept-aware (suggest wikilinks from known concepts)
- Standardize wikilink serialization as `[[brackets]]` in design files

**Non-Goals:**
- LLM-generated concept content (concepts are agent-authored only)
- Reverse dependency index (deferred)
- Graph traversal queries (Phase 10 concern)
- Concept merge/split tooling
- Performance optimization / caching (concept count < 50 for MVP, O(n) scanning is fine)
- Guardrail thread resolution (Phase 6 builds on the resolver, but guardrail files don't exist yet)

## Decisions

### D-1: Module placement — `src/lexibrary/wiki/`
The phase plan calls this `wiki/` rather than the master plan's `knowledge_graph/`. This better reflects the evolved design — it's a wiki of markdown files with wikilinks, not a graph database.

**Alternative considered:** Putting everything in `artifacts/`. Rejected because the wiki module has distinct responsibilities (resolution, indexing, search) beyond data modeling.

### D-2: ConceptFile model — separate frontmatter from body
The current stub has a flat model. The new design splits into `ConceptFileFrontmatter` (Pydantic-validated YAML fields) and `ConceptFile` (frontmatter + raw body + parsed fields). Parsed fields (`summary`, `related_concepts`, etc.) are extracted from the body for programmatic access but the body is the source of truth.

**Alternative considered:** Storing parsed sections as separate fields and reconstructing the body. Rejected because agents add arbitrary sections — we must preserve the full body as-is.

### D-3: Wikilink resolver as shared utility
The resolver in `wiki/resolver.py` handles both concept and guardrail links. Resolution order: bracket stripping → guardrail pattern (`GR-NNN`) → exact name → alias (case-insensitive) → fuzzy match. Returns typed `ResolvedLink` or `UnresolvedLink` with suggestions.

**Alternative considered:** Separate resolvers per link type. Rejected because the resolution algorithm is the same; only the lookup target differs.

### D-4: Fuzzy search strategy — normalized substring matching
For MVP, fuzzy search uses case-insensitive normalized matching (lowercase, strip hyphens/underscores/spaces) across names, aliases, tags, and summaries. No external fuzzy matching library — keep it simple with stdlib.

**Alternative considered:** `thefuzz`/`rapidfuzz` for Levenshtein distance. Deferred — substring matching is sufficient for < 50 concepts. Can be upgraded later without API changes.

### D-5: Archivist concept awareness — lightweight parameter
Pass concept names (not full content) as an optional `available_concepts` string list to the BAML prompt. The Archivist can suggest existing concept names as wikilinks rather than inventing non-existent ones. Backward-compatible — works without concepts.

### D-6: Concept CLI — `concepts` list command + `concept` sub-app
`lexi concepts [topic]` is the search/list entry point. `lexi concept new` and `lexi concept link` are under a `concept` Typer sub-app. This follows the singular/plural CLI convention pattern already in the plan.

### D-7: No metadata footer for concept files
Unlike design files, concept files have no HTML comment footer. They are fully agent/human authored with no LLM generation to track. The `status` frontmatter field and `lexi validate` (Phase 7) handle lifecycle.

## Risks / Trade-offs

**[Fuzzy match false positives]** → Conservative threshold. Return suggestions in `UnresolvedLink` rather than auto-resolving uncertain matches. Better to surface "did you mean X?" than silently resolve to the wrong concept.

**[Design file bracket transition]** → Existing design files may have wikilinks without brackets (from Phase 4 LLM output). The parser handles both formats; the serializer always writes brackets going forward. No migration needed — this is purely a forward-compatible change.

**[BAML prompt compatibility]** → Adding `available_concepts` is an optional parameter addition. Existing BAML functions work without it. The fallback is the Archivist suggesting wikilinks without concept awareness (same as current behavior).

**[Concept count scaling]** → O(n) directory scanning for every `lexi concepts` call. Acceptable for < 50 concepts. Phase 10 adds a query index if needed. No premature optimization.
