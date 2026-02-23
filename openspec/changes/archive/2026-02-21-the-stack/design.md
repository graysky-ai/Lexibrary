## Context

Lexibrary currently has a placeholder `GuardrailThread` model (Phase 5) with stub CLI commands (`lexi guardrail new`, `lexi guardrails`). The model is minimal — it tracks a problem and resolution but lacks Q&A structure, voting, multi-answer support, and cross-artifact search. Design files reference guardrails via `guardrail_refs` and a `## Guardrails` section. The wikilink resolver handles `GR-NNN` patterns.

Phase 6 replaces this with The Stack — a richer knowledge base with posts, answers, comments, voting, and cross-linking. The existing parser/serializer patterns from design files and concepts provide a proven template for the new `stack/` module.

**Current modules involved:**
- `artifacts/design_file.py` — has `guardrail_refs: list[str]` field
- `artifacts/design_file_serializer.py` — serializes `## Guardrails` section
- `artifacts/design_file_parser.py` — parses `## Guardrails` section
- `artifacts/guardrail.py` — `GuardrailThread` model (to be removed)
- `wiki/resolver.py` — resolves `GR-NNN` pattern
- `cli.py` — has `guardrail_app` stubs
- `init/scaffolder.py` — creates `guardrails/` directory

## Goals / Non-Goals

**Goals:**
- Implement the full StackPost lifecycle: create, answer, vote, accept, search
- Provide a `lexi stack` CLI command group with search, post, answer, vote, accept, view, list
- Enable unified cross-artifact search via `lexi search` (concepts + design files + Stack posts)
- Cleanly replace all guardrail references with Stack equivalents
- Maintain backward compatibility for existing `## Guardrails` sections in design files during transition

**Non-Goals:**
- SQLite query index (deferred to Phase 10 if needed)
- Hot/trending ranking
- Auto-search on error (requires daemon, Phase 9)
- Post templates by category (MVP uses single template)
- Merge posts functionality
- Post verification workflow
- Graph traversal queries
- Reputation system

## Decisions

### D1: New `stack/` module follows existing patterns

The `stack/` module mirrors the structure of `wiki/` (concepts): separate `models.py`, `parser.py`, `serializer.py`, `template.py`, `index.py`, plus `mutations.py` for state changes. This follows the established codebase pattern and keeps concerns separated.

**Alternative considered:** Putting everything in `artifacts/` alongside `guardrail.py`. Rejected because Stack posts have significantly more logic (mutations, indexing, search) than simple data models.

### D2: Parse-modify-serialize for mutations

All mutations (add answer, record vote, accept answer) follow the same pattern: parse the full post from disk, modify the in-memory model, re-serialize to disk. No string concatenation or partial file writes.

**Rationale:** The append-only body constraint is enforced at the application level — the serializer always writes the full model. This prevents corruption from partial writes and ensures frontmatter updates are atomic with body changes.

### D3: File-scanning search for MVP

All search operations scan the `.lexibrary/stack/` directory and parse YAML frontmatter. No SQLite index. This is acceptable for < 500 total artifacts across all types.

**Alternative considered:** SQLite from the start. Rejected — adds complexity without clear benefit at current scale. The CLI interface is designed so the backend can change later without affecting users.

### D4: Backward compatibility for `## Guardrails` → `## Stack`

The design file parser will recognize both `## Guardrails` and `## Stack` sections, treating them identically. The serializer will always output `## Stack`. Existing design files are updated naturally as `lexi update` runs — no bulk migration needed.

### D5: ID assignment via filesystem scan

New post IDs are assigned by scanning existing `ST-NNN-*.md` files in `.lexibrary/stack/`, extracting the highest NNN, and incrementing. File creation uses the pattern `ST-{NNN:03d}-{slug}.md`.

**Risk:** Concurrent creation could cause ID collision. Mitigated by: single-agent sessions are the expected use case, and the frontmatter `id` field is the canonical identifier (not the filename).

### D6: Slug generation from title

Post slugs are derived from the title: lowercase, non-alphanumeric chars replaced with hyphens, consecutive hyphens collapsed, truncated to ~50 chars. Used for human readability in file listings only.

### D7: Unified search groups results by artifact type

`lexi search` queries all three artifact types (concepts via `ConceptIndex`, design files via frontmatter scan, Stack posts via `StackIndex`) and groups results under `── Concepts ──`, `── Design Files ──`, `── Stack ──` headers. Tag search filters across all types; free-text search matches titles/summaries/bodies.

### D8: `GuardrailThread` model removed entirely

The `GuardrailThread` model in `artifacts/guardrail.py` is removed (not deprecated). The `StackPost` model in `stack/models.py` is its replacement. The `artifacts/__init__.py` exports are updated to remove `GuardrailThread`.

## Risks / Trade-offs

- **Search performance at scale** — file scanning is O(n) across all artifacts. For MVP this is fine (< 500 artifacts). If slow, Phase 10 adds SQLite. → Mitigation: design the search API so the backend can change without affecting CLI interface.

- **Frontmatter vote count drift** — if an agent edits the file directly and changes a vote count without recording a comment, the count and comment trail diverge. → Mitigation: accept as a soft constraint. Git history is the audit trail. The CLI always keeps them in sync.

- **Breaking changes to existing design files** — renaming `guardrail_refs` → `stack_refs` breaks any code that reads the old field. → Mitigation: parser handles both `## Guardrails` and `## Stack` sections. The model field rename is internal and handled in one commit.

- **BAML prompt references to "guardrails"** — BAML prompts may reference guardrails in their instructions. → Mitigation: check `baml_src/` during implementation and update any references.

## Open Questions

None — all design decisions for Phase 6 are settled in the phase plan (D-035 through D-044). Implementation can proceed.
