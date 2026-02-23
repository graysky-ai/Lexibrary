# Lexibrary v2 — Master Implementation Plan

**Reference:** `lexibrary-overview.md` (the authoritative design document)
**Previous plans:** `plans/archive/v1/` (original aindex-only approach)

---

## Strategic Decision: Restructure, Not Scrap

The v1 codebase built a solid foundation of reusable infrastructure. The new vision is substantially richer — design files, wikilinks, concepts, The Stack, START_HERE.md — but the core plumbing survives.

### Keep As-Is

| Module | Reason |
|--------|--------|
| `utils/hashing.py` | SHA-256 hashing directly reusable; two-tier hashing extends it |
| `ignore/` | gitignore + pathspec matching is unchanged; extended in Phase 4 to load `.lexignore` |
| `tokenizer/` | Token counting still needed for budget validation |
| `llm/rate_limiter.py` | Token-bucket logic is provider-agnostic |
| `daemon/watcher.py`, `debouncer.py`, `scheduler.py` | Watchdog infrastructure is correct; rewire triggers only |

### Rewrite / Redesign

| Module | What Changes |
|--------|--------------|
| `cli.py` | Split into two CLIs: `lexi` (agent-facing: `lookup`, `index`, `concepts`, `stack`, `describe`, `search`) and `lexictl` (maintenance: `init`, `update`, `validate`, `status`, `setup`, `daemon`) |
| `config/schema.py` | Two-tier YAML config (`~/.config/` global + `.lexibrary/config.yaml` project) |
| `config/loader.py` | Walk up to find `.lexibrary/` instead of `lexibrary.toml` |
| `crawler/engine.py` | Now orchestrates design files + .aindex, not just .aindex |
| `crawler/change_detector.py` | Add interface hash tier alongside content hash |
| `indexer/generator.py` | Generate design files + .aindex (two separate artifact types) |
| `baml_src/` | New Archivist prompt; old summarise prompts retired |
| `llm/factory.py`, `llm/service.py` | Wire to new BAML functions |

### New Modules

| Module | Purpose |
|--------|---------|
| `src/lexibrary/ast_parser/` | Tree-sitter multi-language AST + interface extraction |
| `src/lexibrary/artifacts/` | Pydantic models for design files, .aindex, concepts, stack posts |
| `src/lexibrary/archivist/` | Orchestrate AST → skeleton → LLM → design file pipeline |
| `src/lexibrary/wiki/` | Wikilink parsing, resolution, concept file management (originally `knowledge_graph/`) |
| `src/lexibrary/stack/` | Stack post CRUD, voting, search |
| `src/lexibrary/init/` | Project init wizard + agent environment rule generation |
| `src/lexibrary/validator/` | Consistency checks (links, token bounds, bidirectional deps) |
| `src/lexibrary/linkgraph/` | SQLite link graph index — schema, builder, read-only query interface |
| `src/lexibrary/iwh/` | I Was Here (IWH) system — ephemeral inter-agent signals |

---

## New `.lexibrary/` Output Structure

```
project-root/
  .lexignore             # Lexibrary-specific ignore patterns (gitignore format)
  .lexibrary/
    config.yaml          # project config (version controlled)
    index.db             # link graph index (gitignored, rebuilt by lexictl update)
    START_HERE.md        # bootloader — agent entry point (< 2KB)
    .iwh                 # project-root I Was Here signal (gitignored, ephemeral)
    concepts/            # concept files (cross-cutting knowledge)
      Authentication.md
      MoneyHandling.md
    stack/               # Stack posts (problems, solutions, votes)
      ST-001-timezone-naive-datetimes.md
    src/                 # design file mirror tree (1:1 within scope_root)
      auth/
        .aindex
        .iwh             # directory-scoped I Was Here signal (gitignored, ephemeral)
        login.py.md      # design file with YAML frontmatter + markdown body + metadata footer
      api/
        .aindex
        user_controller.py.md
```

`.iwh` files are ephemeral inter-agent signals, gitignored (pattern: `**/.iwh`). See overview §1 for full IWH specification.

Config lives at `.lexibrary/config.yaml` (project) and `~/.config/lexibrary/config.yaml` (global).
Project root is found by walking upward from CWD to locate `.lexibrary/`.

### Ignore System

Three-layer ignore: `.gitignore` + `.lexignore` + `config.ignore.additional_patterns`. A `.lexignore` file at the project root follows gitignore format and specifies files that exist in git but shouldn't get design files (generated code, vendored deps, data files).

### Scope Root

`scope_root` in config (default: `.`, project root) controls which files get design files. Files outside `scope_root` appear in `.aindex` directory listings but don't get design files.

---

## Phase Overview

| Phase | Name | Produces | Key Dependency |
|-------|------|----------|----------------|
| 1 | Foundation Reset | CLI skeleton, config system, project structure | — |
| 2 | Directory Indexes | `.aindex` files in `.lexibrary/` mirror tree | Phase 1 |
| 3 | AST Parser | Interface skeletons, two-tier hashing | Phase 1 |
| 4 | Archivist | Design files, START_HERE.md, `lexictl update` / `lexi lookup` | Phase 3 |
| 5 | Concepts Wiki | Concept files, wikilink resolution, `lexi concepts` / `lexi concept new` | Phase 4 |
| 6 | The Stack | Stack posts, voting, `lexi stack post` / `lexi stack search`, unified `lexi search` | Phase 5 (wikilink resolver) |
| 7 | Validation & Status | `lexictl validate`, `lexictl status`, `lexi lookup` convention inheritance | Phases 4, 5, 6 |
| 8a | CLI Split | Split `lexi`/`lexictl` entry points, move commands | Phase 7 |
| 8b | Init Wizard | `lexictl init` wizard, `lexictl setup --update`, config persistence | Phase 8a |
| 8c | Agent Rules + IWH | Rule templates per env, IWH system, skills/commands | Phase 8b |
| 9 | Update Triggers & CI | Git hooks (primary), periodic sweep (safety net), CI integration, watchdog (deprecated) | Phase 4 |
| 10 | Unified Link Graph | SQLite index (`index.db`), reverse dependency lookups, accelerated tag/cross-artifact search, bidirectional validation | Phases 4, 5, 6 |

**Critical path:** 1 → 3 → 4 → 7 → 8a → 8b → 8c

**Parallelisable pairs:**
- Phase 2 (.aindex) can run alongside Phase 3 (AST)
- Phase 5 (Concepts Wiki) and Phase 6 (The Stack) can run in parallel once Phase 4 is complete (Phase 6 depends on Phase 5's wikilink resolver but core model/parser work is independent)
- Phase 9 (Update Triggers & CI) can run alongside Phase 8 (no dependency between them)
- Phase 10 (Unified Link Graph) can run alongside Phases 8 and 9 (no dependency between them)

---

## Phase 1 — Foundation Reset

**Goal:** Working `lexi` and `lexictl` binaries with the new command surface, new config system, and the `.lexibrary/` directory structure. Nothing generates content yet — stubs return "not implemented."

### What Phase 1 Must Settle

Before writing any further phase, the foundation establishes the decisions everything else builds on:

1. **Config schema** — two-tier YAML, Pydantic 2 models, sensible defaults (including `iwh.enabled`, `agent_environment`, `llm.api_key_env`)
2. **Artifact data models** — Pydantic types for each artifact (design file, .aindex, concept, stack post, IWH). These are the shared vocabulary all later phases write and read.
3. **Root resolution** — walk upward from CWD to find `.lexibrary/`; graceful error if not found
4. **Project init** — `lexictl init` creates the correct directory skeleton (Phase 8b adds the wizard flow)
5. **CLI skeleton** — both `lexi` and `lexictl` commands registered with proper help text; non-implemented commands return a clear message

### Reuse Assessment in Phase 1

- **Keep `ignore/`** entirely; wire it to new config path
- **Keep `tokenizer/`** entirely; it's called later for token budget checks
- **Keep `utils/hashing.py`** entirely
- **Retire `indexer/`** temporarily — rewrite it per-phase as artifact formats stabilise
- **Retire old `config/schema.py`** — new schema is structurally different

### What to Watch Out For

- The old root-finding logic looks for `lexibrary.toml`; update it to look for `.lexibrary/`
- Config format changes from TOML → YAML; existing `pyproject.toml` tooling is unaffected
- `pathspec` pattern name stays `"gitignore"` (not `"gitwildmatch"`) — existing `ignore/` code is correct
- `from __future__ import annotations` in every module — enforce from the start

---

## Phase 2 — Directory Indexes (`.aindex`)

**Goal:** `lexi index <directory>` produces `.aindex` files inside the `.lexibrary/` mirror tree.

This is the closest phase to existing v1 behaviour but output location and content format evolve:
- Files land in `.lexibrary/<mirrored-path>/.aindex`, not in the source tree
- Format gains a **Local Conventions** section
- Child Map table format is the same as v1

### Key Dependency

Needs Phase 1's artifact data models and config system.

### What to Watch Out For

- Mirror path construction: `src/auth/` → `.lexibrary/src/auth/.aindex`
- Local Conventions inheritance: when generating, collect parent `.aindex` Local Conventions up the tree and make them available (agents may not traverse top-down)
- `.aindex` files themselves must appear in the ignore list so they don't get indexed

---

## Phase 3 — AST Parser & Two-Tier Hashing

**Goal:** Given a source file, produce a structured interface skeleton (function signatures, class names, public API) and compute both a content hash and an interface hash.

### New Dependency

**Tree-sitter** (`tree-sitter>=0.21.0`, plus language grammars). This is the only significant new dep not in v1. Start with Python + TypeScript; expand per demand.

### Two-Tier Hashing

Extends `utils/hashing.py`:
- **Content hash** (SHA-256 of full file) — "has anything changed?"
- **Interface hash** (SHA-256 of extracted public signatures) — "has the public API changed?"

Interface hash prevents expensive LLM regeneration when only internal implementation details changed.

### What to Watch Out For

- Tree-sitter grammars are installed separately from the Python binding; the init sequence needs to handle missing grammars gracefully
- Files with unrecognised extensions fall back to content-only (no interface hash)
- The interface skeleton should be deterministic (same input → same hash) — avoid including line numbers or comments in the hashed representation

---

## Phase 4 — Archivist: LLM-Powered Design Files

**Goal:** `lexictl update [<path>]` generates or refreshes design files as a **fallback** when agents haven't updated them directly. `lexi lookup <file>` returns the design file. START_HERE.md generation. `lexi describe` for directory descriptions.

This is the core value proposition of Lexibrary.

### Agent-First Authoring Model

Agents writing code are the best authors of design files (they have full context). The Archivist LLM is the safety net for files agents missed. `lexictl update` detects whether an agent already updated a design file and skips LLM regeneration if so. Agents never invoke `lexictl update` — it runs as a maintenance process.

### Design File Format

Design files have three sections:
- **YAML frontmatter** (agent-editable): `description` (single sentence, propagates to `.aindex`), `updated_by` (archivist or agent)
- **Markdown body** (agent-editable): Interface Contract, Dependencies, Dependents, Tests, Complexity Warning, Wikilinks, Tags, Guardrails
- **HTML comment footer** (machine-managed): source_hash, interface_hash, design_hash, generated, generator

The `design_hash` field (hash of frontmatter + body, excluding footer) enables detecting agent edits without comparing full file content.

### Pipeline

```
Source file
  ↓  Phase 3: AST parser
Interface skeleton + content hash + interface hash
  ↓  Compare against existing design file footer
Changed?
  ├─ No → skip (up to date)
  ├─ Agent already updated design file → refresh footer hashes only (no LLM)
  ├─ Non-code file (no interface) → full Archivist LLM generation (CONTENT_CHANGED)
  ├─ Interface unchanged → lightweight LLM description update (CONTENT_ONLY)
  └─ Interface changed → full Archivist LLM generation (INTERFACE_CHANGED)
        ↓  BAML Archivist prompt
        ↓  LLM fills: summary, intent, constraints, edge cases, wikilinks, tags
        ↓  YAML frontmatter + markdown body + metadata footer
Design file written to .lexibrary/<path>.md
  ↓  Refresh parent .aindex Child Map entry with frontmatter description
```

### `.aindex` Integration

- File descriptions in `.aindex` Child Map are pulled from design file YAML frontmatter `description` field (with structural fallback when no design file exists)
- Directory descriptions (`.aindex` billboard) are written once and not auto-updated; `lexi describe <dir> "..."` command available for manual updates
- `lexictl update` on a single file also refreshes the parent directory's `.aindex` entry

### `.lexignore` and Scope Root

- New `.lexignore` file (gitignore format) layered on top of `.gitignore` + config patterns
- `scope_root` config (default: project root) limits which files get design files; files outside scope still appear in `.aindex`

### BAML Changes

Retire `SummarizeFile`, `SummarizeFilesBatch`, `SummarizeDirectory`. Add:
- `ArchivistGenerateDesignFile(source_path, source_content, skeleton?, language?, existing?) → DesignFileOutput`
- `ArchivistGenerateStartHere(project_name, directory_tree, aindex_summaries, existing?) → StartHereOutput`

Config-driven LLM client routing via BAML `ClientRegistry` (spike needed to verify API).

### Staleness Metadata

Every generated artifact gets a footer:

```markdown
<!-- lexibrary:meta
source: src/services/auth_service.py
source_hash: a3f2b8c1
interface_hash: 7e2d4f90
design_hash: c4d5e6f7
generated: 2026-01-15T10:30:00Z
generator: lexibrary v0.2.0
-->
```

### What to Watch Out For

- **Agent-first model requires Phase 8c (agent environment rules) to be effective.** Before Phase 8c, `lexictl update` is the primary path. Phase 8c rules must be explicit: agents update design files *directly* during coding. `lexictl update` is a maintenance-only safety net that agents never invoke. The CLI split (D-052) enforces this — agents can't accidentally run `lexictl update` because it's in a different binary.
- Design file generation is async and LLM-expensive; rate limiter from v1 applies
- Token budget validation runs after generation: flag if design file exceeds config target
- `lexi lookup` must handle the case where no design file exists yet (inform agent, do not offer to generate — generation is `lexictl`'s domain)
- START_HERE.md is a special case: generated from project topology, not a single file
- `.aindex` refresh on single file update requires read-modify-write of parent `.aindex`
- Footer-less design files (agent-authored from scratch before Archivist runs) must be treated as `AGENT_UPDATED`, not `NEW_FILE` — otherwise agent work gets overwritten by LLM regeneration (D-026)
- First-run `lexictl update` on a large project is slow (sequential LLM calls, 10–30 min for 300+ files). Set expectations via progress bar and documentation. Design async architecture for future concurrency from the start (D-025)

---

## Phase 5 — Concepts Wiki

**Goal:** A living wiki of cross-cutting concepts maintained by agents alongside code. `lexi concepts` lists/searches. `lexi concept new` creates from template. `lexi concept link` adds wikilinks to design files. Wikilink resolver shared across design files, Stack posts, and concepts.

**Detailed plan:** `plans/phase-5-concepts-wiki.md`

### Key Decisions

- Concept index is a CLI command (`lexi concepts`), NOT embedded in START_HERE.md (D-028)
- YAML frontmatter with `title`, `aliases`, `tags`, `status` — all mandatory (D-029)
- Flat `concepts/` directory, hierarchy via wikilinks not filesystem (D-030)
- Agent-first authoring, no LLM generation of concept content (D-032)
- `[[ConceptName]]` wikilink format standardised across all artifacts (D-033)

### Wikilink Resolution

A wikilink `[[Authentication]]` resolves to `.lexibrary/concepts/Authentication.md`. Resolution chain: exact name → alias match (case-insensitive) → fuzzy match → unresolved with suggestions. Guardrail pattern (`GR-NNN`) detected and routed separately.

### New Module: `wiki/`

`src/lexibrary/wiki/` — resolver, parser, serializer, index, template. The master plan called this `knowledge_graph/` but `wiki/` better reflects the evolved design.

### What to Watch Out For

- Wikilinks also appear in Stack posts (Phase 6) — resolver is a shared utility
- Concept files contain wikilinks to other concepts; cycles are allowed (bidirectional relationships) but reported by `lexictl validate`
- Tags in concept files feed the `lexi search --tag` command (Phase 7)
- Design file wikilink format transitions from plain names to `[[bracketed]]` — parser handles both

---

## Phase 6 — The Stack

**Goal:** A Stack Overflow–inspired knowledge base where agents record problems, solutions, and hard-won lessons. `lexi stack post` creates a post. `lexi stack search` finds posts. `lexi stack answer`, `lexi stack vote`, `lexi stack accept` manage the Q&A lifecycle. Unified `lexi search` returns results from concepts, design files, and Stack posts in a single query. Design files gain a `## Stack` cross-reference section (replacing `## Guardrails`).

**Detailed plan:** `plans/phase-6-the-stack.md`

### Key Decisions

- Renamed from "Guardrail Forum" to "The Stack" — `lexi stack` commands, `.lexibrary/stack/` directory, `ST-NNN` post IDs (D-035)
- Posts have net vote count (up minus down); downvotes require a comment (D-036, D-042)
- Tags unified across concepts, design files, and Stack posts — `lexi search --tag` returns all three (D-037, D-038)
- Post body is append-only (answers, comments); frontmatter is mutable (votes, status) (D-039)
- Post statuses: `open`, `resolved`, `outdated`, `duplicate` (D-040)
- Staleness detection: `lexictl validate` flags posts whose referenced files have changed (D-041)
- Optional Bead ID in frontmatter for traceability (D-044)

### Sub-Phases

Phase 6 is structured into sub-phases that can partially overlap:

| Sub-Phase | Name | Depends On | Can Parallel With |
|-----------|------|------------|-------------------|
| 6a | Models & Parser/Serializer | Phase 1 (foundation) | 6b (once models stable) |
| 6b | Stack Index & Search | 6a (models) | 6c |
| 6c | Mutations & Voting | 6a (models + parser) | 6b |
| 6d | CLI Commands | 6a, 6b, 6c | — |
| 6e | Design File Integration | 6a, Phase 4 (design files) | 6b, 6c |
| 6f | Wikilink Resolver Update | 6a, Phase 5 (resolver) | 6d |
| 6g | Unified Search (`lexi search`) | 6b, Phase 5 (concept index) | 6d |

**Critical path:** 6a → 6c → 6d
**Parallelisable:** 6b and 6c can run in parallel once 6a is done. 6e and 6f are independent of 6b/6c.

### What to Watch Out For

- Post ID assignment must scan existing `ST-NNN` files atomically
- The `## Guardrails` → `## Stack` rename in design files — parser must handle both section names during transition
- Tags share a namespace across concepts, design files, and Stack posts — tag conventions must be consistent
- Unified search performance is O(concepts + design_files + stack_posts) — acceptable for MVP, Phase 10 (Unified Link Graph) adds SQLite-accelerated search

---

## Phase 7 — Validation & Search

**Goal:** `lexictl validate` runs all consistency checks. `lexictl status` shows library health. `lexi search --tag <t>` finds artifacts by tag.

### Validation Checks (in order)

1. **Link resolution** — all `[[wikilinks]]` resolve to existing concept files or Stack posts
2. **Token bounds** — all generated artifacts within their configured size targets
3. **Bidirectional consistency** — if A lists B as dependency, B's dependents include A
4. **File existence** — all referenced source files and test paths still exist
5. **Hash freshness** — no artifacts have stale `source_hash` values (not yet updated)
6. **Stack post references** — Stack posts only reference existing files/concepts

### Status Output

`lexictl status` shows:
- Total artifacts: N design files, M .aindex files, K concept files, J Stack posts
- Stale artifacts: X files need updating
- Unresolved links: Y broken wikilinks
- Token budget violations: Z oversized artifacts
- Last update: timestamp

### What to Watch Out For

- Validation is the first command that touches every artifact — it will surface design choices made in earlier phases. Plan for iteration.
- `lexi search --tag` scans all markdown frontmatter before the link graph index (Phase 10) is built. Acceptable for < 500 files; Phase 10 adds SQLite-accelerated tag queries.

---

## Phase 8 — CLI Restructure, Init Wizard & Agent Environment

**Goal:** Split the CLI into `lexi` (agent-facing) and `lexictl` (maintenance). Combine `init` and `setup` into a guided wizard (`lexictl init`). Implement agent environment rules, I Was Here (IWH) system, and skills/commands for supported environments.

Phase 8 is structured into three sequential sub-phases:

| Sub-Phase | Name | Scope | Depends On |
|-----------|------|-------|------------|
| **8a** | CLI Split | Split `lexi`/`lexictl` entry points, move commands to correct CLI | Phase 7 (existing CLI) |
| **8b** | Init Wizard + Setup | `lexictl init` wizard, `lexictl setup --update`, config persistence | 8a |
| **8c** | Agent Rules + IWH | Rule templates per environment, IWH system, skills/commands | 8b |

**Critical path:** 8a → 8b → 8c (sequential — each builds on the previous)

---

### Phase 8a — CLI Split

**Goal:** Two CLI entry points (`lexi`, `lexictl`) defined in `pyproject.toml`, with existing commands moved to the correct CLI. No new functionality — purely structural.

**What moves where:**

| `lexi` (agent day-to-day) | `lexictl` (setup/maintenance) |
|---|---|
| `lookup`, `index`, `describe` | `init` (wizard — 8b) |
| `concepts`, `concept new`, `concept link` | `setup --update` (8b) |
| `stack search/post/answer/vote/accept/view/list/mark-outdated/duplicate` | `update [<path>]` |
| `search` | `validate [--severity] [--fix]` |
| | `status [--quiet]` |
| | `setup --hooks` (Phase 9) |
| | `sweep` / `sweep --watch` (Phase 9) |
| | `daemon start/stop/status` (Phase 9, deprecated) |

**Implementation:**
- Two `[project.scripts]` entries in `pyproject.toml`: `lexi` and `lexictl`
- Two Typer/Click app instances sharing the same underlying modules
- Existing command implementations move without logic changes — only the CLI registration changes
- Both CLIs share root resolution (walk up to find `.lexibrary/`); `lexictl init` is the exception (creates `.lexibrary/`)

**What to Watch Out For:**
- CLI tests must be updated to invoke the correct binary
- Existing `lexi update`, `lexi validate`, `lexi status` commands become `lexictl` commands — all references in docs, tests, and agent rules must update
- No backwards-compatibility shims needed (pre-1.0, not yet live)

---

### Phase 8b — Init Wizard + Setup

**Goal:** `lexictl init` runs a guided wizard combining project initialisation and agent environment setup. `lexictl setup --update` refreshes agent rules.

**Wizard steps (8 steps, all have documented defaults for quick pass-through):**

1. **Project Detection** — auto-detect name from `pyproject.toml`/`package.json`/directory name. *(Default: directory name)*
2. **Scope Root** — "Which directories contain your source code?" Auto-suggest `src/`, `lib/`, `app/`. *(Default: `.`). "Modify later: `.lexibrary/config.yaml` → `scope_root`"*
3. **Agent Environment** — auto-detect from `.claude/`, `.cursor/`, `CLAUDE.md`/`AGENTS.md`. Multi-select. If folders missing, ask before creating. If existing files found, grep for Lexibrary section: found → advise user; not found → will append. *(Default: auto-detected). "Modify later: `.lexibrary/config.yaml` → `agent_environment`"*
4. **LLM Provider** — detect env vars (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`). "We never store, log, or transmit your API key." Store provider + env var name in config. If env var not found, advise what to set. *(Default: first detected). "Modify later: `.lexibrary/config.yaml` → `llm.provider`, `llm.api_key_env`"*
5. **Ignore Patterns** — suggest common patterns based on detected project type. *(Default: none). "Modify later: `.lexignore`"*
6. **Token Budgets** — show defaults, offer to customize. *(Default: accept). "Customize later: `.lexibrary/config.yaml` → `token_budgets`"*
7. **I Was Here** — brief explanation, enable/disable. *(Default: enabled). "Configure later: `.lexibrary/config.yaml` → `iwh.enabled`"*
8. **Summary + Confirm** — show everything, confirm.

**Re-init guard:** Running `lexictl init` on an already-initialised project errors with: "Project already initialised. Use `lexictl setup --update` to refresh agent rules."

**`lexictl setup --update`:** Reads persisted `agent_environment` from config (D-058). Refreshes agent rules/skills/commands for configured environments. Preserves user-added sections (comment-delimited regions).

**Config additions:**
- `agent_environment: [claude, cursor]` — list of configured environments
- `llm.api_key_env: ANTHROPIC_API_KEY` — env var name, never the value
- `iwh.enabled: true` — I Was Here toggle

**What to Watch Out For:**
- API key security: never prompt for the key itself; detect from environment only; display clear transparency message
- Agent environment detection: check for folders AND files (`.claude/` dir, `CLAUDE.md` file)
- `AGENTS.md`/`CLAUDE.md` editing: grep for `<!-- lexibrary:` markers before modifying; append section if no marker found; warn user if existing section found
- Wizard should work non-interactively with `--defaults` flag for CI/scripting

---

### Phase 8c — Agent Rules + IWH

**Goal:** Generate agent environment rules, skills, and commands. Implement the I Was Here (IWH) system.

**Supported Environments (MVP):**

| Environment | Files Written |
|-------------|--------------|
| `claude` | `CLAUDE.md` (append section), `.claude/commands/lexi-*.md`, `.claude/skills/` |
| `cursor` | `.cursor/rules/lexibrary.mdc`, `.cursor/skills/lexi.md` |
| `codex` | `AGENTS.md` (append section) |

**Rule Content — agents are instructed to:**
- Read `.lexibrary/START_HERE.md` at session start
- When entering a directory, check for `.iwh` — read, act, delete
- Before editing a file, run `lexi lookup <file>`
- After editing a file, update its design file directly (set `updated_by: agent`)
- Before architectural decisions, run `lexi concepts <topic>`
- Before debugging, run `lexi stack search`; after solving non-trivial bugs, run `lexi stack post`
- If leaving something incomplete, create `.iwh`; if work is clean, don't
- **Never invoke `lexictl` commands** — those are maintenance operations

**I Was Here (IWH) System:**

New module: `src/lexibrary/iwh/`

| Component | Purpose |
|-----------|---------|
| `model.py` | Pydantic model for `.iwh` files (author, created, scope, body) |
| `reader.py` | Read + consume (delete) `.iwh` from a directory |
| `writer.py` | Create `.iwh` in a directory |
| `gitignore.py` | Ensure `**/.iwh` pattern exists in `.gitignore` |

IWH scope values: `warning`, `incomplete`, `blocked`.

**Skills / Commands:**
- `/lexi-orient` — reads `START_HERE.md` + checks for `.iwh` + runs `lexictl status --quiet`
- `/lexi-search <topic>` — wraps `lexi search` with richer context

**Hooks:**
- Session start hook: `lexictl status --quiet` (passive health signal)
- Pre-edit hook: `lexi lookup <file>` (configurable, may be too aggressive)

**What to Watch Out For:**
- IWH files must be gitignored; `lexictl init` and `iwh/gitignore.py` must ensure the pattern exists
- Git worktrees: `.iwh` files are worktree-local (gitignored), which is correct behaviour
- Same-directory race condition for parallel agents is accepted (Q-014) — IWH is advisory, not transactional
- Skills/commands generation is environment-specific; template system needed
- Rule generation must escape special characters in `.mdc` files (Cursor MDC format)

---

## Phase 9 — Update Triggers & CI Integration

**Goal:** Automated library maintenance via git hooks (primary), periodic sweep (safety net), and CI integration. The watchdog daemon is retained but deprecated and off by default.

### Strategy: Trigger at the Right Boundary

The agent-first authoring model (D-019) means agents update design files during coding. Automated triggers catch what agents miss. The key insight: the right trigger boundary is *when work is done* (commit), not *when a file is saved* (mid-edit). This eliminates race conditions with running agents, avoids wasted LLM calls on intermediate saves, and requires no persistent process.

### Trigger Tiers (in priority order)

| Tier | Trigger | Config | Default | Notes |
|------|---------|--------|---------|-------|
| **Primary** | Git post-commit hook | `lexictl setup --hooks` | Recommended | Fires at natural "work is done" boundary. Zero race conditions. |
| **Safety net** | Periodic sweep | `daemon.sweep_interval_seconds` | 3600 (60 min) | Catches drift that hooks missed. Skip-if-unchanged by default. |
| **Manual** | CLI | `lexictl update [<path>]` | Always available | On-demand, explicit. |
| **CI/CD** | Pipeline step | `lexictl validate` | Per-project | PR gate, like a linter. |
| **Deprecated** | Watchdog daemon | `daemon.watchdog_enabled` | `false` | Real-time file watching. Off by default. See rationale below. |

### Tier 1: Git Post-Commit Hook (Primary)

`lexictl setup --hooks` writes a `.git/hooks/post-commit` script that runs `lexictl update --changed-only` on files modified in the commit.

**Why post-commit, not pre-commit:**
- Pre-commit blocks the commit while LLM calls run (potentially minutes for many files). Users hate this.
- Post-commit runs after the commit is recorded. If it fails, the commit isn't lost.
- The library is a documentation layer — it should never block code delivery.

**Implementation:**
```bash
#!/bin/sh
# Lexibrary post-commit hook — update design files for committed changes
# Generated by: lexictl setup --hooks

changed_files=$(git diff-tree --no-commit-id --name-only -r HEAD)
if [ -n "$changed_files" ]; then
    lexictl update --changed-only $changed_files &
fi
```

The hook runs `lexictl update` in the background (`&`) so it doesn't block the user's terminal after commit. Output goes to `.lexibrary.log`.

**What to Watch Out For:**
- Hook must be executable (`chmod +x`)
- `--no-verify` skips hooks — accepted; the periodic sweep catches it
- If the user has an existing post-commit hook, append rather than overwrite (or use a hook manager like `husky` / `pre-commit` framework)
- Amend commits (`git commit --amend`) trigger the hook again — this is correct (re-process changed files)
- Merge commits may touch many files — same as a large commit, processed sequentially

### Tier 2: Periodic Sweep (Safety Net)

The existing `scheduler.py` runs `lexictl update` at a configurable interval (default: 60 minutes). This catches:
- Files missed by hooks (e.g., `--no-verify`, manual file edits outside git)
- Drift from branch switches that didn't trigger hooks
- Projects not using git hooks

**Skip-if-unchanged (D-066):**
Before running a sweep, scan `scope_root` for any file with `mtime` newer than the last sweep timestamp. If nothing changed, skip the sweep entirely. This is a cheap stat walk (no hashing, no file reads). The 60-minute interval becomes a *maximum* — in practice, sweeps only fire when there's actual work.

**Implementation:**
- Store last sweep timestamp in memory (not persisted — resets on process restart, which is correct)
- `os.scandir()` walk comparing `st_mtime` against the timestamp
- Skip `.lexibrary/` and ignored paths during the scan
- Log "sweep skipped — no changes detected" at debug level

**Running the sweep:**
- As a one-shot: `lexictl sweep` (runs once, exits)
- As a long-running timer: `lexictl sweep --watch` (runs `scheduler.py` in a loop, foreground)
- Via external scheduler: cron, systemd timer, launchd, or Task Scheduler

### Tier 3: CI/CD Integration

**PR validation gate:**
```yaml
# GitHub Actions example
- name: Validate Lexibrary library
  run: |
    lexictl update --changed-only $(git diff --name-only origin/main...HEAD)
    lexictl validate --severity warning
```

**Full rebuild (nightly/weekly):**
```yaml
- name: Full library rebuild
  run: |
    lexictl update
    lexictl validate
```

### Watchdog Daemon (Deprecated — D-065)

The watchdog-based real-time daemon (`daemon/watcher.py`, `debouncer.py`) is retained in the codebase but **deprecated and off by default** (`daemon.watchdog_enabled: false`).

**Rationale for deprecation:**
- The daemon creates an adversarial relationship with the agent-first authoring model — during active agent sessions, it wastes LLM calls producing output that gets discarded (agent work wins via D-061)
- All safety mechanisms D-059 through D-064 exist solely because the daemon runs alongside active development. Without it, most are unnecessary for the primary trigger modes.
- Git hooks trigger at the natural "work is done" boundary, eliminating race conditions entirely
- The periodic sweep catches the same drift with far less complexity

**When to enable it:**
- Teams with mostly human developers (no agents) who want real-time design file updates
- Demo or evaluation environments where real-time feedback is important
- Projects where git hooks are not available or not used

**If enabled (`daemon.watchdog_enabled: true`):**
All safety mechanisms from D-059 through D-064 apply:
- Foreground-only (D-059)
- Atomic writes via `os.replace()` (D-060)
- Design hash re-check after LLM generation (D-061)
- Git branch switch suppression window (D-062)
- Conflict marker detection (D-063)
- Per-directory `.aindex` write lock (D-064)

### Reuse from v1

- `daemon/scheduler.py` — reused directly for periodic sweep
- `daemon/debouncer.py` — retained for watchdog mode (deprecated)
- `daemon/watcher.py` — retained for watchdog mode (deprecated)
- `daemon/service.py` — refactored: sweep mode is primary, watchdog mode is optional

### Safety Mechanisms (All Trigger Modes)

These apply regardless of which trigger is used:

**Atomic writes (D-060):**
All writes to `.lexibrary/` use write-to-temp-then-`os.replace()`. Atomic on POSIX, near-atomic on Windows. Agents reading design files via `lexi lookup` always see either the old or new version, never a partial write.

**Design hash re-check (D-061):**
Re-check `design_hash` *after* LLM generation, immediately before writing. If an agent edited the design file during the LLM call, discard the LLM output. Agent work always wins. Relevant for post-commit hooks (agent may still be running) and sweeps.

**Conflict marker detection (D-063):**
Before invoking the Archivist on a changed source file, check for git conflict markers (`<<<<<<<` at start of line). Files with unresolved merge conflicts are skipped and logged as warnings.

**`.aindex` write serialisation (D-064):**
Per-directory lock prevents concurrent `.aindex` writes when async processing is enabled (D-025). Implemented from the start (no-op under sequential MVP).

### Git Worktrees

Worktrees are naturally safe across all trigger modes:
- Each worktree has its own working tree and `.lexibrary/` directory
- Git hooks are per-worktree (each has its own `.git/hooks/` or linked hooks)
- The periodic sweep watches a specific project root — worktree A's sweep never touches worktree B
- `.iwh` files are gitignored (worktree-local)

### Logging

All trigger modes log to `.lexibrary.log` (project root, gitignored):
- File change events processed (source file path, change level)
- LLM calls initiated and completed (with duration and token usage)
- Design hash re-check discards ("agent edited during generation, discarding")
- Sweep skip events ("no changes detected, skipping")
- Git suppression window activation (watchdog mode only)
- Errors and exceptions

Log rotation via `RotatingFileHandler` (5MB max, 3 backups). Log level configurable via `daemon.log_level` (default: `info`).

### Config

```yaml
daemon:
  sweep_interval_seconds: 3600          # Periodic sweep interval (default: 60 min)
  sweep_skip_if_unchanged: true         # Skip sweep if no files changed since last run
  git_suppression_seconds: 5            # Watchdog: suppression window after branch switches
  watchdog_enabled: false               # Real-time file watching (deprecated, off by default)
  debounce_seconds: 2.0                 # Watchdog: coalesce rapid file events
```

### CLI Changes

```
lexictl setup --hooks                   # Install git post-commit hook
lexictl sweep                           # Run one sweep (process all pending changes, then exit)
lexictl sweep --watch                   # Run periodic sweeps in foreground (uses scheduler.py)
lexictl daemon start|stop|status        # Watchdog daemon (deprecated, requires watchdog_enabled: true)
```

### What to Watch Out For

- Git hook installation must detect and preserve existing hooks (append, don't overwrite)
- `lexictl sweep` must not trigger on `.lexibrary/` changes (avoid infinite loops)
- PID file management from v1 daemon applies to `sweep --watch` and `daemon` modes
- Conflict marker detection is a simple string scan (cheap) — check for `<<<<<<<` at start of line
- Atomic write via `os.replace()` requires temp file in the same filesystem as the target (use same directory)
- The `--changed-only` flag for `lexictl update` must accept a file list from stdin or arguments (for hook integration)
- Log file must be in `.gitignore` — `lexictl init` should ensure this

---

## Phase 10 — Unified Link Graph

**Goal:** Build a SQLite-backed link graph index covering all cross-artifact relationships in the library. Enable reverse dependency lookups, accelerated tag search, and bidirectional consistency validation. Merges the old Phase 10 (Reverse Dependency Index) and Phase 11 (Query Index) — see D-068.

### Why Merge

The old Phase 10 proposed writing computed reverse dependencies back into design file `## Dependents` sections. This approach has fundamental problems:

1. **Dual ownership** — design files are agent-authored (D-019). Writing machine-computed data into them conflicts with the `design_hash` TOCTOU protection (D-061) and creates ownership confusion.
2. **Cascading writes** — changing one file's imports requires reading and writing many other design files to update their dependents. O(degree) file modifications per change.
3. **Throwaway work** — the file-writing approach would be torn out once SQLite arrived in the old Phase 11.
4. **Scope too narrow** — only tracked AST imports, missing wikilinks, Stack refs, concept links, and tags.

The old Phase 11 was marked "optional, add if queries exceed 2 seconds." But reverse lookups are inherently O(N) against files — there is no file-scanning approach that makes them efficient. The index is required, not optional.

### Link Types Indexed

| Link Type | From | To | Extraction |
|-----------|------|----|------------|
| `ast_import` | Source file | Source file | `dependency_extractor` (tree-sitter) |
| `wikilink` | Design file | Concept | `DesignFile.wikilinks` |
| `wikilink` | Concept | Concept | Regex scan of concept body |
| `stack_file_ref` | Stack post | Source file | `StackPostFrontmatter.refs.files` |
| `stack_concept_ref` | Stack post | Concept | `StackPostFrontmatter.refs.concepts` |
| `design_stack_ref` | Design file | Stack post | `DesignFile.stack_refs` |
| `design_source` | Design file | Source file | Path derivation (1:1 mirror structure) |
| `concept_file_ref` | Concept | Source file | `ConceptFile.linked_files` |
| `convention_concept_ref` | Convention | Concept | `[[ConceptName]]` in convention text |

Tags are also indexed (design file, concept, and Stack post tags in a shared namespace per D-037), stored in a dedicated `tags` table.

### SQLite Schema

Database: `.lexibrary/index.db` (gitignored, always rebuildable). 8 tables + FTS5 virtual table. Implementation: `src/lexibrary/linkgraph/schema.py`.

**Pragmas** (set on every connection open):
```sql
PRAGMA journal_mode = WAL;        -- concurrent readers + single writer
PRAGMA foreign_keys = ON;         -- enforce referential integrity
PRAGMA synchronous = NORMAL;      -- safe with WAL, better write perf
```

**Table 1: `meta`** — key-value store (D-073). Keys: `schema_version`, `built_at`, `builder`, `artifact_count`, `link_count`.

**Table 2: `artifacts`** — every indexed entity.

| Column | Type | Purpose |
|--------|------|---------|
| `id` | INTEGER PK | Internal FK target |
| `path` | TEXT UNIQUE | File path relative to project root |
| `kind` | TEXT | `source`, `design`, `concept`, `stack`, or `convention` |
| `title` | TEXT | Short description from frontmatter — enables rich search results without file I/O (D-080) |
| `status` | TEXT | Lifecycle status: concept (`active`/`deprecated`/`draft`), stack (`open`/`resolved`/`outdated`/`duplicate`), NULL for others |
| `last_hash` | TEXT | SHA-256 for incremental update detection |
| `created_at` | TEXT | ISO 8601 timestamp from frontmatter or file mtime (D-080) |

Both source files and design files get separate rows, connected via `design_source` (D-074). Source `title` = design file `frontmatter.description`; source `last_hash` = source file SHA-256; design `last_hash` = design file SHA-256.

**Table 3: `links`** — directed edges with optional context.

| Column | Type | Purpose |
|--------|------|---------|
| `source_id` | FK → artifacts | The artifact that *has* the reference |
| `target_id` | FK → artifacts | The artifact being *referenced* |
| `link_type` | TEXT | Edge type (see link types table) |
| `link_context` | TEXT | Optional metadata — import statement, section heading, etc. (D-078) |

Constraints: `UNIQUE(source_id, target_id, link_type)`, `ON DELETE CASCADE`.

**Table 4: `tags`** — `artifact_id`, `tag` (text). `UNIQUE(artifact_id, tag)`. `ON DELETE CASCADE`.

**Table 5: `aliases`** — concept alias resolution (D-076). `artifact_id` FK, `alias` TEXT `UNIQUE COLLATE NOCASE`. Populated from `ConceptFileFrontmatter.aliases`. Enables O(1) concept lookup, replacing linear scan in `WikilinkResolver`.

**Table 6: `conventions`** — local conventions scoped to directories (D-077). `artifact_id` FK, `directory_path` TEXT, `ordinal` INTEGER, `body` TEXT. `UNIQUE(directory_path, ordinal)`. Each convention has a corresponding `kind='convention'` artifact with synthetic path `{directory_path}::convention::{ordinal}`.

**Table 7: `build_log`** — per-artifact build tracking (D-079). `build_started`, `build_type` (full/incremental), `artifact_path`, `artifact_kind`, `action` (created/updated/deleted/unchanged/failed), `duration_ms`, `error_message`. 30-day retention.

**Table 8: `artifacts_fts`** — FTS5 full-text search (D-075). Standalone virtual table (builder-managed, no trigger sync). `title` + `body` columns with `porter unicode61` tokenizer. Body content: source files → design file summary + interface contract; concepts → summary + body; Stack posts → problem + answers; conventions → full text.

**13 indexes** on: `artifacts(path, kind, status)`, `links(source_id, target_id, link_type, target_id+link_type)`, `tags(tag, artifact_id)`, `aliases(artifact_id)`, `conventions(directory_path)`, `build_log(build_started, artifact_path)`.

### Key Queries

- **Reverse deps** ("what imports this file?"): `SELECT source_id FROM links WHERE target_id = ? AND link_type = 'ast_import'`
- **All references to a concept**: `SELECT source_id, link_type FROM links WHERE target_id = ?`
- **Tag search**: `SELECT a.path, a.kind, a.title FROM tags t JOIN artifacts a ON a.id = t.artifact_id WHERE t.tag = ?`
- **Full-text search**: `SELECT a.path, a.kind, a.title FROM artifacts_fts JOIN artifacts a ON a.id = artifacts_fts.rowid WHERE artifacts_fts MATCH ? ORDER BY rank`
- **Alias resolution**: `SELECT a.id, a.path, a.title FROM aliases al JOIN artifacts a ON a.id = al.artifact_id WHERE al.alias = ? COLLATE NOCASE`
- **Convention inheritance**: `SELECT c.body, c.directory_path FROM conventions c WHERE c.directory_path IN (?, ?, ?) ORDER BY c.directory_path, c.ordinal`
- **Multi-hop traversal** (D-081): Recursive CTEs with configurable `max_depth` (default: 3). See `LinkGraph.traverse()`.
- **Build summary**: `SELECT action, COUNT(*), SUM(duration_ms) FROM build_log WHERE build_started = (SELECT MAX(build_started) FROM build_log) GROUP BY action`

### New Module: `src/lexibrary/linkgraph/`

| File | Purpose | Status |
|------|---------|--------|
| `__init__.py` | Public API: `build_index()`, `open_index()`, re-exports | **Done** |
| `schema.py` | DDL constants (8 tables + FTS5), `ensure_schema()`, `check_schema_version()` | **Done** |
| `builder.py` | `IndexBuilder`: `full_build()` and `incremental_update(changed_paths)` | **Done** |
| `query.py` | `LinkGraph`: read-only query interface with graceful degradation + `traverse()` for multi-hop | **Done** |

### Build Pipeline

**Full build** (`lexictl update` with no path):
1. Open/create `index.db`, ensure schema (version mismatch → drop all, recreate)
2. Clear all rows
3. Scan design files → for each:
   - Insert `kind='source'` artifact (path, title from frontmatter, last_hash, created_at)
   - Insert `kind='design'` artifact for the design file itself
   - Insert `design_source` link (design → source)
   - Insert `ast_import` links from `extract_dependencies()` (source → source)
   - Insert `wikilink` links from `DesignFile.wikilinks` (design → concept)
   - Insert `design_stack_ref` links from `DesignFile.stack_refs` (design → stack)
   - Insert tags from `DesignFile.tags` (on design artifact)
   - Insert FTS row with body = summary + interface_contract (via delete+reinsert)
4. Scan concept files → for each:
   - Insert `kind='concept'` artifact (path, title, status, aliases, tags)
   - Insert aliases into `aliases` table
   - Insert `wikilink` links (concept → concept) from body scan
   - Insert `concept_file_ref` links from `ConceptFile.linked_files`
   - Insert tags, insert FTS row
5. Scan Stack posts → for each:
   - Insert `kind='stack'` artifact (path, title, status, tags)
   - Insert `stack_file_ref` links from `refs.files`
   - Insert `stack_concept_ref` links from `refs.concepts`
   - Insert tags, insert FTS row
6. Scan `.aindex` files → for each local convention:
   - Insert `kind='convention'` artifact (synthetic path, title = first 120 chars)
   - Insert convention row (directory_path, ordinal, body)
   - Extract `[[wikilinks]]` from convention text → insert `convention_concept_ref` links
   - Insert FTS row
7. Update `meta` (built_at, builder, artifact_count, link_count)
8. Log build results to `build_log`

**Incremental update** (`lexictl update --changed-only <files>`):
1. For each changed file, delete its outbound links, tags, aliases, and FTS row
2. Re-extract and re-insert from the current file content
3. If a file was deleted, delete its artifact row (CASCADE cleans links/tags/aliases)
4. Update `meta` counts and `build_log`

The index build runs at the end of `update_project()` / `update_files()` in `archivist/pipeline.py`, after design files have been generated.

### CLI Integration

**`lexi lookup <file>`** — after displaying the design file and inherited Local Conventions, queries the LinkGraph for inbound links and displays a `## Referenced By` section:

```
## Dependents (imports this file)
- src/api/auth_controller.py
- src/middleware/auth.py

## Also Referenced By
- [[Authentication]] (concept wikilink)
- [[ST-007]] (stack post)
```

If the index does not exist, this section is simply omitted. Graceful degradation — the agent still gets the design file.

**`lexi search --tag <t>`** — queries the `tags` table for O(1) lookup. Falls back to file scanning if the index is unavailable.

**`lexictl status`** — gains an index health line: artifact count, link count, build timestamp, or "not built."

**`lexictl validate`** — gains a `bidirectional_deps` check (info severity) that validates link graph consistency with design file dependency lists. Resolves D-048.

### `DesignFile.dependents` Field

**Keep the field on the model** (backward compatibility with existing files that have a `## Dependents` section). **Never populate it** from the pipeline — dependents are served at query time via `lexi lookup`. The serializer annotates the section: `(see lexi lookup for reverse references)`.

### Graceful Degradation

| Scenario | Behaviour |
|----------|-----------|
| `index.db` missing | `LinkGraph.open()` returns `None`. CLI commands work without reverse links. |
| `index.db` corrupt | `LinkGraph.open()` catches `sqlite3.DatabaseError`, returns `None`. Same fallback. |
| `index.db` stale | Reverse links may be incomplete. `lexictl status` reports staleness. |
| Schema version mismatch | `check_schema_version()` returns `None`. Next `lexictl update` rebuilds. |

### Sub-Phases

| Sub-Phase | Name | Depends On | Status |
|-----------|------|------------|--------|
| 10a | Schema (DDL, `ensure_schema()`, version check) | Phases 4, 5, 6 (artifacts exist) | **Done** |
| 10b | Builder (`full_build()`, `incremental_update()`, FTS population) | 10a | **Done** |
| 10c | Query Interface (`LinkGraph` read-only queries, `traverse()` multi-hop) | 10a | **Done** |
| 10d | Pipeline Integration (wire builder into `update_project`/`update_files`) | 10b, 10c | **Done** |
| 10e | CLI Integration (`lexi lookup` reverse links, `lexi search` FTS + tag acceleration) | 10c | **Done** |
| 10f | Validation + Status (bidirectional deps check, index health in `lexictl status`) | 10c | **Done** |
| 10g | Cleanup (serializer annotation, docs) | 10e | **Done** |

**Critical path:** 10a → 10b → 10d → 10e
**Parallelisable:** 10c can run alongside 10b once 10a is complete. 10f can run alongside 10e.

### What to Watch Out For

- SQLite WAL mode must be enabled on connection open for concurrent read/write safety
- `index.db` must be in `.gitignore` — `lexictl init` scaffolder must include it
- Circular dependencies (A imports B, B imports A) are valid in the link graph — report but don't error
- External package imports (not project files) should not create artifact rows — filter to project-internal paths only
- Temp file for atomic write of `index.db` must be in the same filesystem (same directory) for `os.replace()` to work
- Full rebuild on a large project scans all design files, concepts, and Stack posts — this is I/O-bound (parsing existing markdown), not LLM-bound, so it should be fast
- The `--changed-only` incremental path must handle file deletions (remove artifact + CASCADE)
- FTS5 is a standalone table (no content sync) — the builder must explicitly delete+reinsert FTS rows when updating artifacts, since body content comes from file reads not the `artifacts` table
- Convention synthetic paths (`{dir}::convention::{ordinal}`) use `::` separator which must not collide with real file paths
- `aliases.alias` UNIQUE constraint means the builder must handle the case where two concepts claim the same alias — first one wins, log a warning
- `build_log` grows unboundedly — the builder should clean up entries older than 30 days at the start of each build
- Multi-hop recursive CTEs need a `max_depth` guard to prevent runaway queries on cyclic graphs

---

## New Dependencies to Add

| Package | Phase | Reason |
|---------|-------|--------|
| `tree-sitter>=0.21.0,<1.0.0` | 3 | AST parsing |
| `tree-sitter-python>=0.21.0` | 3 | Python grammar |
| `tree-sitter-typescript>=0.21.0` | 3 | TypeScript/JS grammar |
| `PyYAML>=6.0.0,<7.0.0` | 1 | Config format (replaces TOML) |

Phase 10 (Unified Link Graph) requires no new dependencies — `sqlite3` is in Python's standard library.

**Retire when safe:**
- `tiktoken` (if token budget validation moves to approximate counting)
- `anthropic` direct SDK (kept for tokenizer backend; BAML handles LLM calls)

---

## Test Strategy

Each phase ships with tests before moving to the next:
- Unit tests: pure functions (hashing, wikilink parsing, schema validation)
- Integration tests: `tmp_path`-based fixtures simulating real project trees
- Snapshot tests: generated artifact content checked against expected output
- CLI tests: `typer.testing.CliRunner` for command surface

The `tests/fixtures/sample_project/` from v1 should be extended to include a multi-language sample project that exercises Tree-sitter grammars.

---

## Open Questions (Decide in Phase 1)

1. **Config file name:** `.lexibrary/config.yaml` (YAML) — confirm, since v1 used `lexibrary.toml` (TOML)
2. **Mapping strategy config:** Confirm glob-pattern approach in config for 1:1 / grouped / abridged / skipped
3. **Tree-sitter grammar installation:** Bundled in the package or installed on demand? (Leaning: on demand, with a clear error message)
4. **baml-py version:** Current pin is `0.218.0`; check if it needs to bump for new prompt patterns
5. ~~**`lexi init` vs `lexi setup`:** `init` creates `.lexibrary/`; `setup` configures agent environment — keep distinct~~ **Resolved — D-054:** Combined into `lexictl init` wizard. `lexictl setup --update` refreshes rules only.

---

## Implementation Backlog

Items not covered by existing phases. These are gaps identified during design review — features the overview describes or implies but that no phase explicitly delivers. Grouped by origin.

### CLI Gaps (commands specified in overview but not implemented)

| Item | Status | Relates To | Notes |
|------|--------|------------|-------|
| `lexi concepts --tag <t>` | Not implemented | Phase 5 | Overview §4/§9 specifies this flag. Current implementation only accepts positional `<topic>`. |
| `lexi concepts --status <s>` | Not implemented | Phase 5 | Useful for filtering draft/deprecated concepts. Added to overview §4/§9. |
| `lexi concepts --all` | Not implemented | Phase 5 | Listed in overview §9. May be moot if `lexi concepts` with no args already shows all. Decide if default should be "active only" (making `--all` meaningful) or "everything." |
| `lexi stack list` | Implemented, not in spec | Phase 6 | Working in CLI but was missing from overview §9. Now added. |
| `lexi stack mark-outdated <post-id>` | Not implemented | Phase 6 | Mutation exists in code (`mark_outdated()`). Overview describes the lifecycle transition but had no CLI command. Now added to overview §9. |
| `lexi stack duplicate <post-id> --of <id>` | Not implemented | Phase 6 | Mutation exists in code (`mark_duplicate()`). Overview describes duplicate lifecycle but had no CLI command. Now added to overview §9. |
| `lexictl update --dry-run` | Not implemented | Phase 4 | Preview what would change without LLM calls. See overview Q-005. |
| `lexictl update --start-here` | Not implemented | Phase 4 | Regenerate START_HERE.md independently without full project update. Currently START_HERE is only regenerated as part of `lexictl update` (no path). |
| `lexictl validate --fix` | Not implemented | Phase 7 | Auto-remediate fixable issues. Referenced in D-047. Scope TBD — likely limited to safe fixes (refresh stale hashes, remove broken wikilinks). |

### Feature Gaps (design described but not delivered)

| Item | Phase | Notes |
|------|-------|-------|
| **Mapping strategy evaluation** | Post-Phase 4 | `mapping.strategies` config field exists as an empty list stub. The 1:1/grouped/abridged/skipped strategies described in overview §2 are never evaluated. All files get 1:1 treatment. Implementing this requires: pattern matching engine, strategy-specific design file templates, grouped file aggregation logic. See overview Q-010 for template overrides. |
| **Skills / commands generation** | Phase 8c | Overview §8 describes `/lexi-orient` and `/lexi-search` skills for agent environments. Now explicitly scoped in Phase 8c: rules + skills + commands for each environment. |
| **Concurrency for `lexictl update`** | Post-Phase 4 | D-025 establishes sequential MVP with async architecture. When concurrency is added, needs a config key (e.g., `update.max_concurrent: 4`). Not urgent but should be tracked. |
| **`start_here.topology_format` config** | Phase 8b | Overview §1 says topology format is "configurable" (Mermaid vs ASCII). No config key exists. See overview Q-009. |
| ~~**Persist agent environment in config**~~ | ~~Phase 8~~ | Resolved — D-058. `lexictl init` wizard persists `agent_environment` in config. `lexictl setup --update` reads from config. |

### Configuration Suggestions (for future consideration)

These are not gaps in the design — they're potential improvements to consider as the tool matures:

| Suggestion | Rationale |
|-----------|-----------|
| `llm.archivist_model` | Allow a different (cheaper/faster) model for design file generation vs. START_HERE generation. The Archivist does repetitive work on many files; a cheaper model may suffice. |
| `crawl.max_files` | Hard limit on files processed per `lexictl update` run. Safety valve for enormous projects where accidental full-project updates are expensive. |
| `validate.disabled_checks` | Persist disabled checks in project config (e.g., suppress `orphan_concepts` during early setup). Currently filtering is CLI-invocation-only via `--check` and `--severity`. |
| `scope_root` as list | Support multiple source roots for monorepos (e.g., `["src/", "lib/"]`). See overview Q-007. |
| Stack post token warning | Optional warning threshold for large Stack posts. See overview Q-006. |
