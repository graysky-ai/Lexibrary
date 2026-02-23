## Context

Lexibrary Phases 1-3 established the foundation: project scaffolding, config system, ignore matching, directory discovery, `.aindex` generation with structural descriptions, and AST-based interface extraction with tree-sitter. The existing `LLMService` provides v1 single-file and batch summarization via BAML, but produces only short summary strings — not the rich design files the architecture requires.

Phase 4 introduces the Archivist: an LLM pipeline that generates per-file design files with YAML frontmatter, structured markdown body, and machine-readable metadata footer. The key architectural shift is the **agent-first authoring model** — agents write design files during coding sessions; the Archivist is a safety net, not the primary author.

Current state:
- `StalenessMetadata` exists but lacks `design_hash` for agent-edit detection
- `DesignFile` model exists but lacks `DesignFileFrontmatter` (no YAML frontmatter support)
- No design file serializer or parser
- `IgnoreMatcher` loads `.gitignore` + config patterns but not `.lexignore`
- No `scope_root` configuration
- `.aindex` descriptions are structural only (language + line count)
- BAML has `SummarizeFile`/`SummarizeFilesBatch`/`SummarizeDirectory` — to be replaced by Archivist functions

## Goals / Non-Goals

**Goals:**
- Generate rich design files (YAML frontmatter + markdown body + metadata footer) for all source files within `scope_root`
- Detect and respect agent edits via `design_hash` — never overwrite agent-authored content
- Extract forward dependencies from source files using tree-sitter AST
- Support `.lexignore` as a dedicated ignore layer
- Generate `START_HERE.md` from project topology
- Enrich `.aindex` descriptions from design file frontmatter
- Provide `lexi update`, `lexi lookup`, and `lexi describe` CLI commands

**Non-Goals:**
- Reverse dependency index (dependents) — Phase 5
- Wikilink resolution/validation — Phase 5
- Guardrail cross-references — Phase 6
- `lexi validate` consistency checks — Phase 7
- Daemon integration (file watching triggers) — Phase 9
- HANDOFF.md generation — agent-written only
- Concurrent processing — sequential for MVP (async architecture ready for future concurrency)
- Grouped/abridged mapping strategies — all in-scope files get 1:1 design files

## Decisions

### D-1: Design file format — three-section split
YAML frontmatter (agent-editable: description, updated_by) + markdown body (agent-editable: interface contract, dependencies, etc.) + HTML comment footer (machine-managed: hashes, timestamps). This separates agent-facing fields from machine-facing tracking data. Standard YAML frontmatter convention is well-understood by agents from Obsidian/Jekyll training data.

**Alternative considered:** Single metadata block at top → rejected because agents would need to edit around machine fields.

### D-2: Agent-edit detection via design_hash
The metadata footer stores a `design_hash` — SHA-256 of the design file content (frontmatter + body, excluding footer) at last Archivist write. If current content hashes differently, an agent edited it → skip LLM regeneration, refresh footer hashes only. This avoids a separate cache file and makes the design file self-contained.

**Alternative considered:** Separate `.lexibrary/.archivist_cache.json` → rejected per D-015 (design file metadata *is* the cache).

### D-3: Footer-less design files treated as AGENT_UPDATED
If a design file exists but has no metadata footer, an agent created it from scratch. The system trusts the content and adds the footer — it does NOT classify as NEW_FILE (which would overwrite via LLM). This prevents destroying agent work.

### D-4: Archivist as separate module from v1 LLMService
New `archivist/` module rather than extending `llm/service.py`. Clean separation between v1 summarization (short strings) and v2 design file generation (structured output). Old BAML functions (`SummarizeFile`, etc.) remain but are unused.

### D-5: BAML ClientRegistry for provider routing
BAML's `ClientRegistry` Python API overrides which client a function uses at runtime based on `LLMConfig.provider`. Spike (Task 4.2) validates this works. Fallback: env var switching if ClientRegistry doesn't support per-call override.

### D-6: Forward dependencies only — reverse deferred
Phase 4 extracts imports via tree-sitter and resolves to project-relative paths. Third-party imports excluded. The `dependents` field remains empty until Phase 5 builds the reverse index.

### D-7: Non-code files use CONTENT_CHANGED, not INTERFACE_CHANGED
Non-code files (no tree-sitter grammar) have no interface hash. Content changes are classified as `CONTENT_CHANGED` — same LLM treatment as `INTERFACE_CHANGED` but the distinct label avoids implying non-code files have an "interface."

### D-8: Sequential processing for MVP
All file updates are sequential. The pipeline uses async functions and stateless service design so concurrency can be added later without a rewrite. First-run on large projects may take 10-30 minutes.

## Risks / Trade-offs

**BAML ClientRegistry API uncertainty** → Spike in Task 4.2 resolves this before service implementation. Fallback is env var switching.

**First-run performance on large projects** → Sequential LLM calls for all NEW_FILE entries. Mitigated by: Rich progress bar, `scope_root` limiting scope, `max_file_size_kb` skipping large files, subsequent runs are fast (most files UNCHANGED).

**Agent-first model depends on Phase 8 rules** → Before Phase 8, `lexi update` is the only path. The agent-awareness logic is latent — it activates when agents start editing design files directly.

**Design file format is a serialization contract** → Must be stable after adoption. Mitigated by: careful spec, tolerant parser, standard YAML frontmatter convention.

**Import resolution is best-effort** → Some imports may not resolve (dynamic imports, namespace packages). Acceptable — dependency list is informational, not load-bearing until Phase 5.

**Token cost for large projects** → Mitigated by two-tier hashing (most files skip), agent-first model (reduces LLM calls 50-80%), rate limiter, max_file_size_kb, scope_root.
