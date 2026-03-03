# Design File Lifecycle Plan

Companion to `aindex-lifecycle-plan.md`. These two artefact types are designed to work in conjunction — aindex provides directory-level navigation, design files provide file-level detail.

See `docs/user/artefact-lifecycle.md` for the question framework.

---

## 1. Initialization

**Decision**: `lexictl bootstrap` with `--full` and `--quick` modes. Wizard calls this as its final step; users can re-run independently.

### Quick mode (default)

Structural skeleton generation — no LLM required:
1. Tree-sitter extracts interface contracts (method signatures, class definitions) for all source files
2. Frontmatter `description` auto-generated from heuristics (filename, module docstring, class docstring)
3. Dependencies extracted via AST import analysis
4. Metadata records `updated_by: bootstrap-quick` to signal LLM enrichment is pending
5. Enrichment happens progressively: background sweeps, on-access via `lexi lookup`, or explicit `lexictl update`

### Full mode

LLM-powered generation for all source files:
1. Everything in quick mode, plus:
2. LLM generates rich `description` in frontmatter
3. LLM produces human-quality billboard summaries
4. `updated_by: archivist` recorded in metadata

### Why a separate command?

- User may need to configure API key or change LLM model after wizard completes
- `lexictl bootstrap` is idempotent — safe to re-run
- Separating it from the wizard means CI/automation can call it directly
- Mode choice can be overridden: `lexictl bootstrap --full` after an initial `--quick` run enriches all skeleton files

**Brand new project**: No source files → no design files. First design files created reactively when agent creates source files (see §2).

**Existing project**: Bootstrap generates design files for all source files in the scope root.

---

## 2. Creating New Design Files

**Decision**: Coding agent creates files → PostToolUse hook detects → queue for generation.

**Flow**:
1. Coding agent creates or edits a source file
2. PostToolUse hook script runs after Write/Edit tool completes
3. Script resolves the expected design file path: `.lexibrary/src/<relative-path>.md`
4. If design file doesn't exist:
   a. Generate structural skeleton immediately (tree-sitter + heuristics — fast, no LLM)
   b. Append file path to `.lexibrary/queue/design-pending.txt`
5. Background process or next `lexictl update` picks up the queue and runs LLM enrichment

**Safety net layers**:
- **Layer 1 (immediate)**: PostToolUse hook creates skeleton + queues enrichment
- **Layer 2 (soon)**: Background sweep (`lexictl sweep --watch`) processes queue
- **Layer 3 (guaranteed)**: Post-commit git hook runs `lexictl update --changed-only`

**Queue format** (`.lexibrary/queue/design-pending.txt`):
```
# Queued for LLM enrichment
# Format: <relative-source-path> <queued-timestamp>
src/lexibrary/new_module.py 2026-03-03T14:22:01
src/lexibrary/cli/new_command.py 2026-03-03T14:23:15
```

**Key points**:
- Skeleton creation is synchronous (fast) — agent immediately benefits from structural design file
- LLM enrichment is asynchronous — no blocking the agent's workflow
- Queue is append-only, deduplicated on processing

---

## 3. Maintaining Design Files

**Decision**: Comment/Annotation Layer — inline annotations with maintainer-agent pruning.

### Direction

Design files will have a **comment/annotation layer** where agents can append observations, corrections, and insights without modifying the canonical sections. A maintainer-agent periodically reviews annotations and decides whether to incorporate them.

### Preliminary Design

**Annotation format** (appended to the bottom of the design file, directly above the footer):
```markdown
<!-- annotation agent="claude-opus-4" timestamp="2026-03-03T14:30:00" confidence="high" -->
The `process_batch` method silently drops items that fail validation.
This is intentional — see commit abc123 for the design rationale.
<!-- /annotation -->

<!-- annotation agent="claude-sonnet-4" timestamp="2026-03-04T09:15:00" confidence="speculative" -->
This module may have a race condition when called from multiple threads.
Needs investigation.
<!-- /annotation -->
```

**Quality signals on annotations**:
- `confidence`: high | medium | speculative
- `verified_by`: test name, commit hash, or human reviewer
- ~~`votes` or `confirmations`~~: **Deferred.** Voting/confirmation mechanics don't work well with inline comment format. May revisit if a better interaction model emerges.

**Maintainer-agent responsibilities**:
- Runs on a separate cycle when no coding agents are active (async, never concurrent with coding work)
- For each annotation: reads the current source file and checks whether the implementation backs up the observation
- Incorporates verified annotations into the canonical design file sections (description, interface contract, notes)
- Discards annotations that are contradicted by or no longer relevant to the current source
- Prunes all processed annotations — once incorporated or discarded, the annotation has served its purpose
- Updates `updated_by: maintainer` field when incorporating changes

**Managed vs Authored sections** (regeneration behavior):
- **Managed** (auto-regenerated by archivist): Interface Contract, Dependencies, Dependents
- **Authored** (never overwritten): Notes/Annotations section
- **Hybrid** (auto-generated initially, preserved if agent-edited): Frontmatter `description`. If `updated_by: agent`, description is not overwritten on regeneration.

### Resolved Design Decisions

| Question | Decision |
|---|---|
| How does the maintainer-agent decide what to incorporate vs discard? | Analyzes the current source file — if implementation backs up the annotation, incorporate; if contradicted or stale, discard. |
| Should annotations have an expiry/TTL? | No TTL. Annotations persist until the maintainer-agent processes them. |
| How do we prevent the Notes section from growing unboundedly? | Maintainer-agent prunes all processed annotations (incorporated or discarded). A warning is emitted after 10 annotations accumulate to signal maintenance is overdue. |
| Should annotations be inline or in a sidecar file? | Inline, appended to the bottom of the design file directly above the footer. |
| Synchronous or async interaction model? | Async. Maintainer-agent runs on a separate cycle when no coding agents are active. |
| How do votes/confirmations work? | **Deferred.** Voting doesn't work well with inline comments. May revisit later. |
| Maximum annotation count before forced maintenance? | No hard cap. Warning emitted after 10 annotations to prompt a maintenance run. |

---

## 4. Deprecating Design Files

**Decision**: Git-aware detection + soft deprecation with TTL.

### Detection

- `lexictl update` checks each design file's `source_path` against the filesystem
- If source file is missing:
  - **Not committed to git** (unstaged/uncommitted deletion): Mark `status: unlinked` in frontmatter. Design file remains fully accessible. Warning emitted in `lexi lookup` output.
  - **Committed to git** (file deletion is in a commit): Mark `deprecated: true`, `deprecated_at: <timestamp>` in frontmatter. Start TTL countdown.

### Soft Deprecation Behavior

- Deprecated design files are **excluded from**:
  - PreToolUse hook injection
  - `lexi lookup` results (unless `--include-deprecated` flag)
  - AIndex child descriptions
  - Token budget calculations
- Deprecated design files are **still accessible via**:
  - `lexi search --include-deprecated`
  - Direct file read
  - Link graph queries (with deprecation warning)

### TTL and Hard Deletion

- Default TTL: 50 commits (configurable in `.lexibrary/config.yaml` as `deprecation.ttl_commits`)
- After TTL expires: design file is deleted on next `lexictl update` run
- TTL resets if source file reappears (e.g., reverted deletion)
- Commit-based TTL ensures idle projects don't lose deprecated files due to calendar time alone

### Rename Handling

Renames look like a delete + create. Detection strategies (in priority order):
1. **Git rename detection**: After commit, `git diff --find-renames` identifies renames. Migrate design file (update `source_path` in frontmatter, move to new location, preserve all authored content).
2. **Content hash heuristic**: If a new file appears with similar content hash to a recently deprecated file → treat as rename, migrate design file.
3. **Fallback**: If neither detects a rename, old design file is deprecated and new one is created from scratch. Authored notes are lost (this is the worst case, but rare).

### Frontmatter Fields for Deprecation

```yaml
---
description: Original description
updated_by: archivist
status: active          # active | unlinked | deprecated
deprecated_at: null     # ISO timestamp when deprecation started
deprecated_reason: null # "source_deleted" | "source_renamed" | "manual"
---
```

---

## 5. Reading and Using Design Files

**Decision**: Hybrid — automatic injection for the editing context + agent-driven deep exploration.

### Tier 1 — Always injected (automatic via hooks)

- **Pre-edit** (PreToolUse on Edit/Write): Full design file for the target file. This is the critical injection — the agent sees interface contract, dependencies, and authored notes before making changes.

### Tier 2 — Injected on relevant activity (conditional hooks)

- **Post-edit** (PostToolUse on Edit/Write): List of potentially stale dependents from the design file's Dependents section. Prompts the agent: "These files depend on the one you just changed — consider checking them."

### Tier 3 — Agent-driven (commands, on demand)

- `lexi lookup <file>` — Full design file + sibling context from parent aindex + related concepts + recent Stack posts
- `lexi search <query>` — Cross-artefact search including design file descriptions and annotations
- `lexi impact <file>` — Dependency graph traversal showing what might break

### How Design Files Support AIndex

| Agent Activity | Design File Provides |
|---|---|
| Understanding a file before editing | Full interface contract, dependencies, authored notes |
| Navigating directories (via aindex) | Rich file descriptions in aindex child map (from frontmatter) |
| Understanding impact of a change | Dependents list, related concepts via wikilinks |
| Learning project conventions | Annotations from previous agent sessions |

---

## Cross-Artefact Interaction Summary

```
Session Start
  └─ AIndex: root billboard + top-level dirs (Tier 1)

Agent explores directories
  └─ AIndex: directory child map injected on access (Tier 2)
  └─ Design: file descriptions enrich aindex entries

Agent focuses on a file
  └─ Design: full design file injected pre-edit (Tier 1)
  └─ AIndex: sibling context from parent (via lexi lookup, Tier 3)

Agent edits a file
  └─ Design: dependents list injected post-edit (Tier 2)
  └─ Agent may run `lexi impact` for deeper analysis (Tier 3)

Agent finishes session
  └─ PostToolUse hook queues enrichment for any new/changed files
  └─ Post-commit hook catches stragglers
```

---

## Resolved Questions

**Annotations: inline, not sidecar.**
Annotations stay in the design file's `## Notes` section. No separate `.annotations.md` file. Annotations are most useful read alongside the content they describe; a separate file adds indirection for marginal cleanliness gains. Unbounded growth is managed by a max annotation count + forced maintenance sweep (see §3 open items), not file separation.

**Bootstrap quick → full: no special upgrade path.**
Files with `updated_by: bootstrap-quick` are enriched progressively through normal maintenance — background sweeps, on-access via `lexi lookup`, or explicit `lexictl update`. No dedicated `--quick` → `--full` migration needed. The metadata already signals "enrichment pending" to all maintenance paths.

**Deprecated design files: git-committed.**
Deprecated files are committed to the repository, not gitignored. They change rarely (only at deprecation and deletion), so diff noise is minimal. If gitignored they'd be lost on clone, defeating the library's archaeological value. Commit history preserves *when* and *why* deprecation occurred.

**TTL: commit-based, configurable per-project.**
TTL is measured in commits, not calendar time. Default: 50 commits. Configurable in `.lexibrary/config.yaml` under `deprecation.ttl_commits`. Commit-based TTL is more semantically meaningful — a project idle for months shouldn't lose deprecated files just because time passed.
