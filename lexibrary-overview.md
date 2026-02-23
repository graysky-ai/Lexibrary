# Lexibrarian: Architecture Overview

A library of a codebase that agents can use to quickly understand it and navigate it. Written by agents, for agents.

The fundamental constraint of AI coding today is **context window efficiency vs. knowledge retrieval**. We treat the codebase not as raw text but as a **queryable semantic database** — moving from "reading the whole book" to "checking the index."

---

## Principles

- **Agent-first** — every design decision optimises for machine consumption. Human readability is a bonus, not a goal.
- **Two CLIs, one product** — `lexi` is the agent-facing interface for day-to-day use (lookups, search, concepts, Stack). `lexictl` is the control plane for setup, maintenance, and generation (init, update, validate). This separation prevents agents from accidentally triggering expensive maintenance operations. No GUI, no web UI.
- **Installed once, initialised per-project** — `pipx install lexibrarian` (or `uv tool install`) puts both `lexi` and `lexictl` on PATH globally; `lexictl init` sets up each project individually. Lexibrarian is a dev tool like a linter, never a project dependency.
- **Zero infrastructure** — no external services, no servers, no Docker. Source of truth is always files in the repo: markdown, YAML, wikilinks. A local SQLite link graph index accelerates cross-cutting queries and enables reverse lookups (see §7a).
- **Context is tiered** — cheap overview always loaded, detail loaded on demand, heavy context loaded only when explicitly needed.

---

## 1. The Bootloader: `START_HERE.md`

The single entry point for any agent entering the project.
**Size target:** < 2KB.

Contains no code. It is a high-level routing protocol:

- **Project Topology** — Mermaid diagram (preferred — structured and agent-parseable) or ASCII tree of the repository structure and high-level architecture. Format is configurable.
- **Project Ontology** — key domain terms and their definitions (ensures agents use correct search terms and understand business semantics).
- **Navigation by Intent** — task-oriented routing table. Agents think in tasks, not directories: *"I need to change how users authenticate"* → `[[Authentication]]`. *"I need to add an API endpoint"* → `.lexibrary/backend/api/.aindex`. Maps common agent goals directly to entry points in the library.
- **Navigation Protocol** — instructions on how to use the library (e.g., "always check the `.aindex` of a directory before reading its files").
- **Convention Index** — a compact list of convention/decision names with one-line descriptions. When an agent needs detail, it follows the wikilink. This keeps the bootloader tiny but makes the agent aware of what exists.
**Note:** `START_HERE.md` deliberately excludes work-in-progress state. Transient inter-agent state is handled by the I Was Here system (see below).

### I Was Here (`.iwh`) — ephemeral inter-agent signals

**I Was Here (IWH)** is a directory-scoped, ephemeral signalling system for inter-agent communication. An agent leaving something incomplete in a directory creates a `.iwh` file as a warning for the next agent to enter that scope. IWH files live inside the `.lexibrary/` mirror tree alongside `.aindex` files.

**Why IWH instead of a project-wide handoff file?**

- A single project-wide handoff file assumes sequential agent sessions — one agent always handing off to the next. In multi-agent and parallel workflows, this model breaks down.
- Mandatory session-end writes produce empty or formulaic content when agents complete their work cleanly (the common case). This creates noise, not signal.
- Directory-scoped signals are more precise — an agent working in `src/auth/` leaves a note specifically there, not in a project-wide file every agent must parse.

**IWH files are gitignored** — they are ephemeral, per-workspace artifacts. They survive editor restarts, machine reboots, and `git stash`/`git checkout`, but do not persist across fresh clones. This is intentional: transient inter-agent state should not live in version control.

**Location:**

```
.lexibrary/
  .iwh                    # project-root level signal
  src/
    auth/
      .aindex
      .iwh                # directory-scoped signal
      login.py.md
```

**Format:**

```markdown
---
author: agent-session-abc123
created: 2026-02-22T14:30:00Z
scope: incomplete
---

Auth middleware refactor is half-done. `verify_token()` updated but
`refresh_token()` still uses the old pattern. Do NOT call
`refresh_token()` until it matches.

Files affected:
- src/auth/middleware.py (partial)
- src/auth/refresh.py (not started)
```

The `scope` field signals urgency:
- **warning** — "be aware of this before working here"
- **incomplete** — "work was started but not finished"
- **blocked** — "something is broken here, fix before proceeding"

**Key rules:**

1. **Created only when needed** — if an agent finishes its work cleanly, no `.iwh` is created. The most common case produces no file. Zero noise.
2. **Consumed on read** — the next agent to enter a directory reads the `.iwh`, acts on it, and deletes it. Self-cleaning.
3. **Directory-scoped** — each `.iwh` applies to its directory only. A project-root `.iwh` (at `.lexibrary/.iwh`) serves as a general project-level signal.
4. **Parallel-safe (best-effort)** — agents in different directories don't interfere. Same-directory race conditions (two agents reading simultaneously) are accepted as a known limitation; IWH is advisory, not transactional.
5. **Configurable** — IWH can be enabled/disabled in `.lexibrary/config.yaml` via `iwh.enabled` (default: `true`).

**Agent workflow:**

```
Agent enters directory
  → checks .lexibrary/<mirror-path>/.iwh
  → if found: read, act on it, delete
  → does work
  → if leaving something incomplete: create .iwh
  → if work is clean: no .iwh (the common case)
```

**Git worktrees:** IWH works correctly with git worktrees. Each worktree has its own working tree, so `.iwh` files are worktree-local. Since they're gitignored, there's no cross-worktree interference.

---

## 2. Design Files (Shadow Files)

**Purpose:** Explain the *intent* of code, not just the syntax.

### Authoring model: agent-first, Archivist as backup

Design files are primarily authored by **the agent writing the code** — it has the best context for explaining *why* a change was made. The Archivist (LLM pipeline) is a safety net that catches files agents forgot to document.

The workflow:
1. Agent edits source code → agent also updates the corresponding design file
2. `lexictl update` runs later (maintenance process) → detects whether the agent already updated the design file
3. If agent updated → refresh tracking hashes only (no LLM call)
4. If agent forgot → run the Archivist LLM to generate/update the design file

Agent environment rules (§8) instruct agents to update design files directly during coding sessions. Agents never invoke `lexictl update` — that is a maintenance operation.

### Hybrid mirroring (configurable)

The default is a **1-to-1 mirror structure** — deterministic and unambiguous. If an agent is looking at `src/auth/login.py`, it can algorithmically predict the design file is at `.lexibrary/src/auth/login.py.md`. No search needed.

However, not every file warrants a full design file. Lexibrarian supports configurable controls for how files are mapped:

| Strategy | When to use | Example |
|----------|------------|---------|
| **1:1 per file** | Core domain models, services, controllers | `auth_service.py` → `auth_service.py.md` |
| **Grouped per directory** | Utility/helper files, config files | `utils/*.py` → `utils/_group.md` |
| **Abridged** | Simple files with minimal logic | Shortened template, interface-only |
| **Skipped** | Generated files, lockfiles, build output | Migrations, `package-lock.json` |
| **Reference from source** | Test files | Tests documented in their source file's design file |

These strategies are configured in `.lexibrary/config.yaml` via glob patterns. The default is 1:1 for everything; users tune from there.

### Scope root

`scope_root` controls which files get design files. Files outside `scope_root` appear in `.aindex` directory listings but don't get design files. See §10 for full configuration details.

### Design file format

Design files have three sections with distinct ownership:

**YAML frontmatter** (agent-editable):
```yaml
---
description: "Single sentence summary of what this file does."
updated_by: archivist  # "archivist" or "agent"
---
```

The `description` field is the canonical short description — it propagates to `.aindex` Child Map entries. Agents should keep it current when editing the design file.

**Markdown body** (agent-editable):
- **Interface Contract** — inputs (arguments) and outputs (return types / side effects). Crucial for preventing hallucinations.
- **Dependencies** — what external services or local modules this file touches.
- **Dependents** — what depends on this file (reverse links). Not stored in the file; served at query time by `lexi lookup` from the link graph index (see §7a). The serializer annotates this section with a pointer to `lexi lookup`.
- **Tests** — reference to where tests for this file live.
- **Complexity Warning** — flagged note if the file contains legacy code or dragons.
- **Wikilinks** — `[[ConceptName]]` tags linking to relevant concepts, conventions, or decisions.
- **Tags** — lightweight labels for search and filtering (e.g., `auth`, `security`, `jwt`). Complements wikilinks — tags enable `lexi search --tag auth` without requiring graph traversal.
- **Stack** — cross-references to relevant Stack posts (`[[ST-NNN]]`).

**HTML comment footer** (machine-managed):
```html
<!-- lexibrarian:meta
source: src/services/auth_service.py
source_hash: a3f2b8c1
interface_hash: 7e2d4f90
design_hash: c4d5e6f7
generated: 2026-01-15T10:30:00Z
generator: lexibrarian v0.2.0
-->
```

The `design_hash` is the hash of the design file content (frontmatter + body, excluding footer) at the time the Archivist last wrote it. If the current file hashes differently, an agent has edited it — `lexictl update` detects this and skips LLM regeneration.

### Auto-generation

Use AST parsing (Tree-sitter) to auto-generate the skeleton of design files (function signatures, class names, interface contracts). An LLM fills in descriptions only when the code actually changes, as determined by change detection. Non-code files (YAML, markdown, configs) also get design files using content-only change detection (no interface hash).

### Dependents: reverse-index discovery

The "Dependents" field (what uses this file) is served from the SQLite link graph index (§7a) at query time. When an agent runs `lexi lookup <file>`, the command queries the index for all inbound links and displays them inline after the design file content. This covers not just AST import dependencies but all link types — wikilinks from concepts, Stack post references, and cross-artifact relationships.

Rather than writing computed dependents back into design files (which would create dual ownership, cascading writes, and merge conflicts), the `DesignFile.dependents` field remains empty in the persisted file. The index is built during `lexictl update` and is always rebuildable from the source files. If the index is unavailable, `lexi lookup` still works — it just omits the reverse links section.

---

## 3. Directory Indexes: Recursive Routing

Every directory in the library contains an `.aindex` file enabling agents to traverse the codebase tree without loading leaf nodes.

- **Billboard** — explains the purpose of the directory (e.g., "All React components related to User Settings"). Written once when the directory is first indexed; not auto-updated on subsequent runs (a directory's purpose rarely changes). `lexi describe <dir> "..."` is available for manual updates.
- **Child Map** — a 3-column table (`Name`, `Type`, `Description`) listing every file and subdirectory. Files listed before directories, each group sorted alphabetically. No token count column — token budgets are validated at the artifact level, not per-entry. **File descriptions are extracted from the YAML frontmatter `description` field of the corresponding design file** (with a structural fallback when no design file exists yet). This means `.aindex` descriptions get richer as design files are created.
- **Local Conventions** *(optional)* — scoped conventions and contextual warnings that apply within this directory. Things an agent should know *given where it's working right now*, but that aren't universally true across the project.

### Local Conventions: conditional conventions

Many important guidelines are scoped, not universal: "use `Decimal` for money in this module," "migration from sync to async in progress here," "tests require a specific fixture." These don't belong in `START_HERE.md` (too specific) or in individual design files (they apply to a scope, not a single file).

The `.aindex` is the right home because agents already read it when entering a directory. Placing scoped conventions there means agents see them at exactly the right time — when they enter the scope.

```markdown
## Local Conventions
- All monetary values use `Decimal`, never `float` — see [[MoneyHandling]]
- Tests in this directory require the `payments` fixture — `conftest.py` has details
- Migration in progress from sync to async — check [[AsyncMigration]] before adding new endpoints
```

**Inheritance:** Local Conventions sections inherit downward. If `.lexibrary/src/.aindex` says "use UTC everywhere" and `.lexibrary/src/payments/.aindex` says "use Decimal for money," an agent in `src/payments/` sees both — it sees its current `.aindex` plus any parent `.aindex` Local Conventions sections it traversed to get there. This matches the existing navigation model. NOTE: If the agent has jumped to a subdirectory rather than traversing the directory tree, it will only see the Local Conventions for the current directory, not the parent directories.

**Population:** Local Conventions are initially empty. They are intended to be populated by agents (via a future CLI command or Stack-like workflow) or by humans editing `.aindex` files directly. **Open question:** How should `lexictl update` preserve agent/human-authored Local Conventions when regenerating the `.aindex` file? The convention content must survive regeneration — either by parsing and re-injecting it, or by treating Local Conventions as a separate section that regeneration never touches.

**Agent workflow:**

1. Reads `.lexibrary/START_HERE.md` → sees `.lexibrary/backend/`
2. Reads `.lexibrary/backend/.aindex` → sees `.lexibrary/backend/api/`
3. Reads `.lexibrary/backend/api/.aindex` → finds `user_controller.py.md`
4. Reads the design file

The agent finds specific logic without ever loading irrelevant frontend code or database migrations.

---

## 4. Concepts Wiki: Wikilinks

**Purpose:** A living wiki of cross-cutting concepts that agents maintain alongside code. Links disconnected knowledge that lives in different files, directories, or even repos.

Implementation is **wikilinks in markdown** — no graph database, no infrastructure. `[[Authentication]]` in a design file tells the agent there's a concept file to follow if it needs more context. Agents are the primary authors — they create and update concepts during normal development. The wiki grows organically with the codebase.

### Concept files

A flat `concepts/` directory containing one file per cross-cutting concept. No subdirectories — hierarchy is expressed through wikilinks between concepts, not filesystem structure. `[[ConceptName]]` always resolves to `concepts/ConceptName.md`.

```
.lexibrary/concepts/
  Authentication.md
  JWTTokens.md
  SessionManagement.md
  MoneyHandling.md
  RepositoryPattern.md
```

### Concept file format

Concept files have **mandatory YAML frontmatter** and a freeform markdown body:

```yaml
---
title: Money Handling
aliases: [currency, monetary values, pricing]
tags: [domain, finance, data-integrity]
status: active
---
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | string | yes | Human-readable concept name |
| `aliases` | list[string] | yes (min 1) | Alternative names for discovery. Agents think in different terms — "currency", "money", "pricing" should all find this concept. |
| `tags` | list[string] | yes (min 1) | Lowercase labels for `lexi search --tag` |
| `status` | enum | yes | `active`, `deprecated`, or `draft` |
| `superseded_by` | string | no | Concept that replaces this one (when deprecated) |

The markdown body contains:
- **Summary** (required) — 1-3 sentences. What and why.
- **Rules** — prescriptive guidelines ("Do X, not Y, because Z"). Highest-value section.
- **Where It Applies** — file/directory scopes.
- **Related** — wikilinks to other concepts, Stack posts, files.
- **Decision Log** — append-only record of key decisions.

**Design principle:** Concepts should be **prescriptive, not descriptive**. "Do X, not Y, because Z" is worth 10x more than "X is a pattern where..." Agents need actionable rules.

Unlike design files, concept files have **no metadata footer** — they are fully agent/human authored with no LLM generation to track.

### Concept index

The concept index is accessed via `lexi concepts` — a CLI command, not embedded in `START_HERE.md`. This keeps `START_HERE.md` within its token budget as the concept count grows. The convention index section in `START_HERE.md` remains as a lightweight routing aid for project-level conventions; the full concept catalog is CLI-accessed.

```
$ lexi concepts
Authentication     — JWT-based auth with refresh token rotation
MoneyHandling      — All monetary values use Decimal, never float
RepositoryPattern  — Data access via repository classes, not direct ORM

$ lexi concepts auth           # fuzzy search by name, alias, tag
$ lexi concepts --tag security # filter by tag (planned)
$ lexi concepts --status draft # filter by status (planned)
```

### Concept lifecycle

- **Creation:** Agents create concepts when they encounter cross-cutting patterns during coding. The trigger: "Would a future agent in a different part of the codebase benefit from knowing this?" If scoped to one directory, it belongs in `.aindex` Local Conventions instead.
- **Updates:** Agents update concepts when code changes affect the convention. The decision log section is append-only; rules/summary sections reflect current truth.
- **Deprecation:** `status: deprecated` with `superseded_by` pointer. Concept still resolves but displays a notice.
- **Deletion:** Manual. `lexictl validate` flags orphan concepts (zero inbound references) for review.

### Nested concepts

Related concepts (e.g., `Authentication` → `JWTTokens`, `SessionManagement`, `OAuthFlow`) are separate files linked via wikilinks. One file per concept keeps token budgets manageable and links precise — `[[JWTTokens]]` is more useful than `[[Authentication]]` when only tokens are relevant.

### Why wikilinks over a graph database?

- **Zero infrastructure** — just files and `[[links]]`. Agents already understand wikilinks from training data (Obsidian, Notion, etc.).
- **Agents can follow them** — see `[[Authentication]]`, look up `.lexibrary/concepts/Authentication.md`, done. It's just file navigation.
- **Upgrade path is clear** — if graph queries are ever needed ("what's 2 hops from Authentication?"), build an adjacency list from the wikilinks at index time. The wikilinks *are* the edges.

---

## 5. Handling Abstractions, Conventions, and Design Decisions

The hardest problem. Abstractions don't live in files — they span the codebase. A file-centric library misses them entirely unless we handle them explicitly.

### Tier 1: Concept files (loaded on demand via wikilinks)

The `concepts/` directory entries. When a design file mentions `[[RepositoryPattern]]`, the agent pulls in `concepts/RepositoryPattern.md` which explains the pattern, why it was chosen, the interface contract, and exceptions.

### Tier 2: Convention index + Concept catalog

Two complementary views:
- **Convention index** in `START_HERE.md` — a compact list naming project conventions with one-line descriptions. Cheap to load (< 1KB). Tells the agent *what exists*. When it needs detail, it follows the wikilink.
- **Concept catalog** via `lexi concepts` — the full searchable index of all concept files, accessed on demand via CLI. Not embedded in START_HERE (keeps the bootloader within token budget as concept count grows).

### Tier 3: Decision records / ADRs (loaded on demand)

For "why did we choose X over Y" questions. These are linked from concept files and are heavy — never loaded by default, only when an agent is about to make a decision in that space.

### Context loading strategy

| Tier | When loaded | Example |
|------|------------|---------|
| Always | Session start | `START_HERE.md` (topology, conventions, navigation) |
| On directory entry | Agent enters a directory | That directory's `.aindex` (including Local Conventions) + `.iwh` if present (consumed and deleted) |
| On file touch | Agent reads/edits a file | That file's design file (includes wikilinks) |
| On demand | Agent follows a wikilink or runs `lexi concepts` | Concept files, decision records |

This keeps base context tiny but makes full knowledge accessible. The agent environment rules (see section 8) tell agents *when* to pull each tier.

### Token budgets (configurable defaults)

Each artifact type has a target token size. These are configurable in `.lexibrary/config.yaml` — the defaults below are starting points to be tuned per project:

| Artifact | Default target | Rationale |
|----------|---------------|-----------|
| `START_HERE.md` | ~500–800 tokens | Must fit in a single context load. If it's bigger, it's doing too much. |
| Design file (1:1) | ~200–400 tokens | Agent should be able to load 3–5 without significant context burn. |
| Design file (abridged) | ~50–100 tokens | Interface-only skeleton for simple files. |
| `.aindex` file | ~100–200 tokens | Routing tables, not documentation. |
| Concept file | ~200–400 tokens | Comparable to a design file. Decision logs may push larger. |
| Stack post | Unbounded (append-only body) | Evidence and answers accumulate. Search filters keep retrieval scoped. |
| `.iwh` file | Not budgeted | Ephemeral and gitignored. Consumed on read. Keep concise by convention, not enforcement. |

The LLM generation step validates output against these targets. If a design file exceeds its budget, the generator flags the source file as potentially over-scoped — a useful architectural signal.

---

## 6. The Stack

The Stack is a **Stack Overflow–inspired knowledge base embedded in the codebase**. Agents record problems they've hit, solutions they've found, and approaches that failed — so future agents don't repeat the same mistakes.

### Why a dedicated system, not just a field in design files?

- Issues often span multiple files — a post about timezone handling touches `utils/`, `models/`, `api/`, and `tests/`.
- Posts need Q&A structure: the problem, evidence, multiple answers with votes, accepted solutions.
- Agents need to *search* across the codebase ("has anyone hit a timezone issue before?"), not just see issues scoped to a single file.

### Structure: posts with answers

Each post is a markdown file in `.lexibrary/stack/`:

```
stack/
  ST-001-timezone-naive-datetimes.md
  ST-002-circular-import-services.md
  ...
```

**Post format:**

```markdown
---
id: ST-001
title: "Timezone-naive datetimes cause silent data corruption"
tags: [datetime, data-integrity, utils]
status: resolved
created: 2026-01-15
author: agent-session-abc123
bead: null
votes: 3
duplicate_of: null
refs:
  concepts: [DateHandling]
  files: [src/models/event.py, src/api/events.py]
  designs: [src/models/event.py.md]
---

## Problem
Using `datetime.now()` anywhere in this codebase produces timezone-naive
datetimes that silently corrupt data when compared against the DB (which
stores UTC).

### Evidence
- Test failure: `tests/test_events.py::test_event_overlap`
- Stack trace: `TypeError: can't compare offset-naive and offset-aware datetimes`

---

## Answers

### A1
**Date:** 2026-01-15 | **Author:** agent-session-def456 | **Votes:** 2 | **Accepted:** true

All datetime creation must go through `utils/time.py:now()` which enforces
UTC. The linter rule `TZ001` catches bare `datetime.now()` calls.

#### Comments
- **2026-01-16 agent-session-ghi789:** Also patch `datetime.utcnow()` —
  deprecated in Python 3.12+.

---

### A2
**Date:** 2026-01-17 | **Author:** agent-session-xyz000 | **Votes:** -1

Wrapping individual call sites with `timezone.now()` also works.

#### Comments
- **2026-01-17 agent-session-abc123 [downvote]:** This misses call sites
  and causes intermittent bugs. Use the centralized approach (A1).
```

### Key rules

1. **Body is append-only** — answers and comments are appended, never edited or deleted. Frontmatter (votes, status, accepted) is mutable. Git history provides the full audit trail.
2. **Evidence required** — every post must cite a specific error, test failure, or observable behaviour in the `### Evidence` section. No speculation.
3. **Votes are net scores** — each post and answer has a `votes` field (up minus down). Vote actions are recorded as comments showing `[upvote]` or `[downvote]` context. Downvotes require an accompanying comment explaining why.
4. **Cross-linked everywhere** — posts reference concepts, files, and designs via `refs` frontmatter. Design files link back with a `## Stack` section listing relevant post IDs. The wikilink resolver handles `[[ST-NNN]]` patterns.
5. **Tags are shared** — tags in Stack posts use the same namespace as concept and design file tags (lowercase, hyphenated). `lexi search --tag auth` returns results from all three artifact types.
6. **Searchable via CLI** — `lexi stack search "timezone"` for full-text search. `lexi stack search --scope src/auth/` for path-scoped search. `lexi stack search --concept Authentication` for concept-scoped search.
7. **Staleness-aware** — `lexictl validate` flags posts whose referenced source files have changed significantly. Agents verify the solution still applies or mark the post outdated.
8. **Accepted answers** — answers can be marked accepted (`lexi stack accept ST-001 --answer 1`), which sets the post status to `resolved`. This signals to future agents: "this solution is verified."

### Post lifecycle

```
Created (open)  →  Answer added  →  Answer accepted (resolved)
                                          ↓
                              Referenced files change significantly
                                          ↓
                              lexictl validate flags as potentially outdated
                                          ↓
                         Agent verifies (still valid) or marks outdated
```

Posts can also be marked `duplicate` with a `duplicate_of` pointer to consolidate knowledge.

### Cross-linking with design files

Design files include a lightweight Stack reference section:

```markdown
## Stack
- [[ST-001]] Timezone-naive datetimes — use `utils/time.py:now()`
- [[ST-015]] UTC conversion edge case — check boundary conditions
```

This keeps design files slim while making Stack posts discoverable at the point of relevance.

### Unified search

`lexi search` is the single cross-artifact search command. It searches design files, concepts, and Stack posts in one query:

```
$ lexi search --tag auth
── Concepts ──
Authentication     — JWT-based auth with refresh token rotation

── Design Files ──
src/api/auth_controller.py  — Handles login/logout/refresh endpoints

── Stack ──
ST-007  [resolved] ▲4  Refresh token rotation breaks on clock skew
```

Specialized commands (`lexi concepts`, `lexi stack search`) still exist for focused browsing.

---

## 7. Change Detection

**SHA-256 content hashing** is the primary change detection mechanism.

### Why SHA-256 over git diff?

- **Works outside git** — if someone drops Lexibrarian on a non-git project, hashes still work.
- **Catches uncommitted changes** — `git diff` only covers committed changes. SHA-256 on the working tree catches saves that haven't been committed yet, which is the common case when an agent is mid-session.
- **Cheap and deterministic** — hash the file, compare to stored hash, done. No need to keep old copies or compute diffs just to know *whether* something changed.

### Two-tier hashing

| Tier | What's hashed | Triggers |
|------|--------------|----------|
| Content hash | Full file content (SHA-256) | "Has anything changed at all?" — triggers analysis |
| Interface hash | AST public signatures only | "Has the public API changed?" — triggers design file rewrite |

Internal refactors that don't change the public interface get a lighter touch (update the description, leave the interface contract alone). Signature changes trigger a full design file regeneration.

### The update engine

1. **Trigger** — git post-commit hook, periodic sweep, manual `lexictl update` invocation, or CI pipeline step.
2. **Detection** — SHA-256 content hash compared to stored hash. If unchanged, skip.
3. **Analysis** — if content changed, check interface hash:
   - **Non-code file** (no interface hash) — full design file regeneration (`CONTENT_CHANGED`).
   - **Interface unchanged** — lightweight description update only (`CONTENT_ONLY`).
   - **Interface changed** — full design file regeneration via AST parse + LLM (`INTERFACE_CHANGED`).
4. **Action** — the Archivist (specialised LLM prompt) reads the diff, reads the existing design file, rewrites it. Updates the `.aindex` if files were added/deleted.
5. **Commit** — updated library files committed alongside code changes (or on next commit).

### Update triggers (configurable)

The update engine supports multiple trigger modes, configured in `.lexibrary/config.yaml`. The recommended default is git hooks + periodic sweep.

| Trigger | Mode | When to use | Default |
|---------|------|-------------|---------|
| **Git hook** | Post-commit hook | Primary — fires at the natural "work is done" boundary | Recommended (`lexictl setup --hooks`) |
| **Periodic sweep** | Timer-based | Safety net — catches drift from missed hooks, non-git edits | 60 min, skip-if-unchanged |
| **CLI** | `lexictl update [<path>]` | Manual invocation — on demand or scripted | Always available |
| **CI/CD** | Pipeline step | PR gate — validates and regenerates as part of CI | Per-project |
| **Watchdog daemon** | watchdog + debounce | Real-time file watching (deprecated, off by default) | `watchdog_enabled: false` |

CI/CD integration is configured per-project. All modes use the same detection and generation pipeline. Agents never invoke `lexictl update` directly — they update design files during coding, and the maintenance pipeline catches anything missed.

### Why git hooks over a real-time daemon

The agent-first authoring model (D-019) means agents update design files *during coding*. The Archivist catches what agents miss. The key insight: the right trigger boundary is when work is *done* (commit), not when a file is *saved* (mid-edit).

A real-time watchdog daemon creates problems:
- **Adversarial with agent-first model** — during active agent sessions, the daemon wastes LLM calls producing output that gets discarded (agent work wins via D-061).
- **Race conditions** — requires TOCTOU protection (D-061), git suppression windows (D-062), conflict marker detection (D-063), and write locks (D-064).
- **Cost** — LLM calls scale with save frequency, not meaningful change boundaries.
- **Complexity** — persistent process management, PID files, signal handling.

Git post-commit hooks eliminate all of these: they fire after the commit is recorded, changes are settled, and the agent has finished editing. The periodic sweep (skip-if-unchanged) catches everything else.

The watchdog daemon is retained but deprecated (D-065). It may be useful for teams with mostly human developers or demo environments.

### Periodic sweep: skip-if-unchanged

Before running a scheduled sweep, the engine scans `scope_root` for any file with `mtime` newer than the last sweep timestamp. If nothing changed, the sweep is skipped entirely (D-066). This is a cheap `os.scandir()` stat walk — no hashing, no file reads. The configured interval (default: 60 minutes) becomes a *maximum*; in practice sweeps only fire when there's actual work.

### Safety mechanisms

These apply across all trigger modes:

**Atomic writes (D-060)** — all writes to `.lexibrary/` use write-to-temp-then-`os.replace()`. Atomic on POSIX, near-atomic on Windows. Agents reading design files via `lexi lookup` always see either the old or new version, never a partial write.

**Design hash re-check (D-061)** — the Archivist re-checks `design_hash` *after* LLM generation, immediately before writing. If an agent edited the design file during the LLM call, the hash will have changed and the Archivist discards its output rather than overwriting the agent's work. This closes the TOCTOU window in the agent-first authoring model (D-019).

**Conflict marker detection (D-063)** — before invoking the Archivist on a changed source file, the engine checks for git conflict markers (`<<<<<<<`). Files with unresolved merge conflicts are skipped and logged as warnings.

**`.aindex` write serialisation (D-064)** — a per-directory lock prevents concurrent `.aindex` writes when async processing is enabled (D-025). Implemented from the start so the concurrency upgrade is safe.

### Watchdog daemon (deprecated)

The watchdog daemon is retained for specific use cases but off by default (`daemon.watchdog_enabled: false`). If enabled, additional safety mechanisms apply:

**Git operation awareness (D-062)** — the daemon watches `.git/HEAD` for changes. After a branch switch, stash pop, or rebase, a suppression window (configurable, default 5 seconds) accumulates file change events without acting on them. After the window, a single consolidated update runs.

**Platform model (D-059)** — foreground-only. No background daemonization (no double-fork, `setsid`, or platform-specific process management). The user's terminal, IDE, or process manager handles lifecycle. `watchdog` abstracts platform differences internally (FSEvents on macOS, inotify on Linux, ReadDirectoryChangesW on Windows).

### Logging

All trigger modes log to `.lexibrarian.log` (project root, gitignored). Log rotation via `RotatingFileHandler` (5MB max, 3 backups). Log level configurable via `daemon.log_level` (default: `info`). Logged events include: files processed, change levels, LLM call durations, design hash re-check discards, sweep skips, and errors.

### Staleness metadata

Every generated artifact includes a metadata footer for change tracking:

```markdown
<!-- lexibrarian:meta
source: src/services/auth_service.py
source_hash: a3f2b8c1
interface_hash: 7e2d4f90
design_hash: c4d5e6f7
generated: 2026-01-15T10:30:00Z
generator: lexibrarian v0.2.0
-->
```

- **`design_hash`** — SHA-256 of the design file content (frontmatter + body, excluding the footer itself) at the time the Archivist last wrote it. If the current file content hashes differently, an agent or human has edited the design file since the Archivist last ran. `lexictl update` uses this to detect agent edits and skip unnecessary LLM regeneration.

A staleness check compares `source_hash` against the current file. If they diverge and no update has run, the artifact is flagged:

```markdown
> ⚠️ This doc may be outdated. Source file changed since last update.
```

### Validation pipeline

Post-generation checks ensure library consistency:

1. **Link resolution** — all `[[wikilinks]]` resolve to existing concept files or Stack posts.
2. **Token bounds** — generated artifacts are within their configured size targets.
3. **Bidirectional consistency** — if file A lists B as a dependency, B's dependents should include A. (Implemented via the link graph index — see §7a and D-072.)
4. **File existence** — all referenced source files and test paths still exist.
5. **Hash freshness** — no artifacts have stale `source_hash` values.
6. **Stack post references** — Stack posts only reference existing files/concepts.

Validation issues are grouped by severity: **errors** (blocks work — broken references, missing files), **warnings** (drift — stale hashes, token budget violations, orphan concepts), **info** (hygiene — bidirectional gaps, potentially outdated Stack posts).

Validation runs automatically after generation and can be invoked standalone via `lexictl validate`. Failures are surfaced in `lexictl status`.

### Maintenance service pattern

Library health (`lexictl validate`, `lexictl status`) is a **maintenance concern, not a coding workflow concern**. The CLI split between `lexi` and `lexictl` enforces this separation at the tool boundary level — agents literally cannot run maintenance commands because they only have access to `lexi`.

The operational model:

| Role | CLI | Commands | When |
|------|-----|----------|------|
| **Coding agents** | `lexi` | `lookup`, `search`, `concepts`, `stack *`, `describe`, direct design file edits | During development — read and write-back |
| **Maintenance service** | `lexictl` | `update`, `validate`, `status`, staleness remediation | Scheduled or triggered — library upkeep |
| **CI/CD pipeline** | `lexictl` | `validate` as a gate | On commit/PR — like a linter |
| **Agent hooks** | `lexictl` | `status --quiet` at session start | Passive health signal — "library has 3 warnings" |

Agent environment rules (Section 8) direct coding agents to `lexi` read operations (`lookup`, `search`, `concepts`) and write-back operations (direct design file edits, Stack posts, concept creation). The Archivist (`lexictl update`) runs as a separate maintenance process, catching anything agents missed.

### Archivist prompt design

The Archivist is the specialised LLM prompt (defined in BAML) that generates and updates design files. Quality guidelines:

- **Describe *why*, not *what*** — the code itself shows what it does. The design file should explain intent, constraints, and non-obvious behaviour.
- **Flag edge cases and dragons** — surprising behaviour is the highest-value content a design file can contain.
- **Respect the token budget** — if a generated doc exceeds its target, flag the source file as potentially over-scoped rather than writing a longer doc.
- **Preserve continuity** — when updating an existing design file, carry forward human-added notes and Stack references that are still relevant.

---

## 7a. Link Graph Index

The markdown/YAML files are the source of truth. A derived SQLite index (`.lexibrary/index.db`, gitignored) accelerates cross-cutting queries and enables reverse lookups that are not feasible via file scanning alone.

The index is built during `lexictl update` and covers all relationship types in the library. It is always rebuildable from the source files — delete `index.db` and run `lexictl update` to recreate it. No new dependencies are required (`sqlite3` is in Python's standard library).

### Why an index is necessary

Several operations — reverse dependency lookups, tag search across artifact types, full-text search, concept graph traversal, Stack post scoping — require scanning many files to answer a single question. File scanning is O(n) per query; an index makes these O(1). More critically, reverse lookups ("what imports this file?", "what references this concept?") require scanning *every* artifact to find inbound links. There is no file-scanning approach that makes this efficient.

### Schema overview

The database uses 8 tables plus an FTS5 virtual table. SQLite WAL mode enables concurrent readers alongside a single writer (`lexictl update`). Schema version is tracked in `meta`; version mismatch triggers a full rebuild.

**Table 1: `meta`** — key-value store for schema version, build timestamp, builder version, artifact count, and link count. Key-value format is extensible without schema migration.

**Table 2: `artifacts`** — every indexed entity. Both source files and their corresponding design files get separate rows (connected via `design_source` link type). This tracks hashes per file and supports grouped design files later.

| Column | Type | Purpose |
|--------|------|---------|
| `id` | INTEGER PK | Internal FK target |
| `path` | TEXT UNIQUE | File path relative to project root |
| `kind` | TEXT | `source`, `design`, `concept`, `stack`, or `convention` |
| `title` | TEXT | Short description (from frontmatter) — enables rich search results without file I/O |
| `status` | TEXT | Lifecycle status where applicable (concept: active/deprecated/draft; stack: open/resolved/outdated/duplicate) |
| `last_hash` | TEXT | SHA-256 for incremental update detection |
| `created_at` | TEXT | ISO 8601 timestamp — from frontmatter where available, file mtime otherwise |

**Table 3: `links`** — directed edges between artifacts.

| Column | Type | Purpose |
|--------|------|---------|
| `source_id` | FK → artifacts | The artifact that *has* the reference |
| `target_id` | FK → artifacts | The artifact being *referenced* |
| `link_type` | TEXT | Edge type (see link types table below) |
| `link_context` | TEXT | Optional metadata — import statement text, section heading, or role context |

Constraints: `UNIQUE(source_id, target_id, link_type)`, `ON DELETE CASCADE`.

### What the index covers

The index captures a unified link graph of all cross-artifact relationships:

| Link Type | From | To | Extraction |
|-----------|------|----|------------|
| `ast_import` | Source file | Source file | AST import extraction (tree-sitter) |
| `wikilink` | Design file | Concept | `[[ConceptName]]` in design file body |
| `wikilink` | Concept | Concept | `[[ConceptName]]` in concept body |
| `stack_file_ref` | Stack post | Source file | `refs.files` in post frontmatter |
| `stack_concept_ref` | Stack post | Concept | `refs.concepts` in post frontmatter |
| `design_stack_ref` | Design file | Stack post | `[[ST-NNN]]` in design file `## Stack` section |
| `design_source` | Design file | Source file | Path derivation (1:1 mirror structure) |
| `concept_file_ref` | Concept | Source file | `ConceptFile.linked_files` |
| `convention_concept_ref` | Convention | Concept | `[[ConceptName]]` in convention text |

**Table 4: `tags`** — artifact-to-tag associations. Tags from design files, concepts, and Stack posts share one namespace (per D-037). Constraints: `UNIQUE(artifact_id, tag)`, `ON DELETE CASCADE`.

**Table 5: `aliases`** — concept alias resolution. Populated from `ConceptFileFrontmatter.aliases`. `UNIQUE(alias) COLLATE NOCASE` ensures no two concepts claim the same alias, matching the `WikilinkResolver`'s case-insensitive behaviour. Enables O(1) concept lookup by any name or alias, replacing the linear scan in the in-memory resolver.

**Table 6: `conventions`** — local conventions scoped to directories. Each bullet in `AIndexFile.local_conventions` becomes one row with a `directory_path`, `ordinal` (preserves list ordering), and `body`. Each convention has a corresponding `kind='convention'` artifact with a synthetic path (`{directory_path}::convention::{ordinal}`), allowing conventions to participate in the link graph (via `convention_concept_ref` for `[[wikilinks]]` in convention text), FTS, and tags.

**Table 7: `build_log`** — per-artifact build tracking. Records which artifacts were processed in each index build, with timing (`duration_ms`), action (`created`/`updated`/`deleted`/`unchanged`/`failed`), and error messages. Enables build summaries for `lexictl status`, failure diagnosis, and performance profiling. Application-level cleanup retains the last 30 days.

**Table 8: `artifacts_fts`** — FTS5 full-text search virtual table (standalone, builder-managed). Indexes `title` and `body` content with `porter unicode61` tokenization (Unicode-aware + Porter stemming — "authentication" matches "authenticated"). Body content by artifact kind: source files index their design file's summary + interface contract; concepts index summary + body; Stack posts index problem + answer bodies; conventions index the full convention text. Replaces O(N) file scanning in `lexi search` with O(1) ranked full-text queries.

### Key design decisions

**Reverse deps at query time, not in files (D-070):** Reverse dependencies are served from the index when `lexi lookup` runs — they are **not** written back into design file `## Dependents` sections. This avoids dual ownership conflicts with the agent-first authoring model (D-019), cascading writes across many files for a single import change, and spurious merge conflicts.

**Source + Design as separate artifacts (D-074):** Both source files and design files get rows in the `artifacts` table, connected by a `design_source` link. This tracks hashes correctly per file, attributes links honestly to their origin (AST imports come from source files; wikilinks come from design files), and supports grouped design files later (one `_group.md` → multiple source files).

**Multi-hop graph traversal (D-081):** The `LinkGraph` query interface supports recursive CTEs for transitive queries ("what's 2 hops from Authentication?", "what's the full import tree of this file?"). A configurable `max_depth` parameter (default: 3) prevents runaway recursion.

### Graceful degradation

If the index is missing, corrupt, or stale, all CLI commands still work:
- `lexi lookup` shows the design file without the reverse links section.
- `lexi search` falls back to file scanning for tag queries (same results, slower). Full-text search requires the index.
- `lexictl status` reports the index as missing or stale.
- `lexictl validate` flags missing/stale index as info-severity.

### Storage

```
.lexibrary/
  index.db          # SQLite — gitignored, rebuilt by `lexictl update`
```

---

## 8. Project Setup & Agent Environment

Setup and agent configuration are handled by `lexictl`, the maintenance CLI. The process is split into first-time initialisation (wizard) and ongoing rule updates.

### `lexictl init` — the setup wizard

`lexictl init` is a combined init + setup wizard that creates the `.lexibrary/` directory structure and configures agent environment rules in a single guided flow. Running `lexictl init` on an already-initialised project errors with a message pointing to `lexictl setup --update`.

**Wizard steps:**

1. **Project Detection** — auto-detect name from `pyproject.toml`, `package.json`, or directory name. Confirm with user. *(Default: directory name)*
2. **Scope Root** — "Which directories contain your source code?" Auto-suggest based on common patterns (`src/`, `lib/`, `app/`). *(Default: `.` / project root). "Modify later: `.lexibrary/config.yaml` → `scope_root`"*
3. **Agent Environment** — auto-detect from existing `.claude/`, `.cursor/` directories or `CLAUDE.md`/`AGENTS.md` files. Confirm or select. Multi-select supported (a project can have both Claude and Cursor users). If agent folders are missing, ask the user before creating them. If existing files like `AGENTS.md` or `CLAUDE.md` are found, grep for a Lexibrarian section — if found, advise user; if not, append a Lexibrarian section. *(Default: auto-detected environment)*
4. **LLM Provider** — "Which LLM provider for design file generation?" Detect available environment variables (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, etc.). Display: "Lexibrarian reads this variable at runtime. We never store, log, or transmit your API key." Store provider name + env var name in config, never the key value itself. If the env var is not found, advise the user what to set — `lexictl update` will fail with a clear message later. Users with keys managed by credential managers or editor settings just need to ensure the env var is available in their shell. *(Default: first detected provider). "Modify later: `.lexibrary/config.yaml` → `llm.provider`, `llm.api_key_env`"*
5. **Ignore Patterns** — "Any file patterns to exclude beyond `.gitignore`?" Suggest common patterns based on detected project type (generated code, vendored deps, data files). *(Default: none). "Modify later: `.lexignore` (gitignore format)"*
6. **Token Budgets** — "Accept default token budgets?" Show defaults: design file ~200–400, `.aindex` ~100–200, concept ~200–400. *(Default: accept defaults). "Customize later: `.lexibrary/config.yaml` → `token_budgets`"*
7. **I Was Here** — brief explanation of the IWH inter-agent signalling system. "Enable I Was Here signals?" *(Default: yes). "Configure later: `.lexibrary/config.yaml` → `iwh.enabled`"*
8. **Summary + Confirm** — show everything that will be created/modified. Confirm before proceeding.

The wizard persists the agent environment selection in project config (`agent_environment` field) so that `lexictl setup --update` does not require the env argument again.

### `lexictl setup --update` — refresh agent rules

Refreshes agent environment rules when Lexibrarian's conventions evolve, without re-running the full wizard. Reads the persisted `agent_environment` from project config. Detects user-added sections in rules files (comment-delimited regions) and preserves them during updates.

### Supported environments

| Environment | Config location | What gets written |
|-------------|----------------|-------------------|
| **Cursor** | `.cursor/rules/`, `.cursor/skills/` | Rules (`.mdc`), skills (`SKILL.md`), commands |
| **Claude Code** | `CLAUDE.md`, `.claude/commands/`, `.claude/skills/` | Rules, commands, skills |
| **Codex** | `AGENTS.md` or equivalent | Agent instructions |

### What the rules contain

The auto-installed rules tell the agent:

- Always read `.lexibrary/START_HERE.md` at session start.
- When entering a directory, check for `.lexibrary/<path>/.iwh` — if present, read it, act on it, and delete it.
- Before editing a file, run `lexi lookup <file>` to load its design file and reverse dependencies (what depends on this file).
- **After editing a file, update its design file directly** — you have the best context for explaining *why* the change was made. Update the YAML frontmatter `description` and the markdown body. Set `updated_by: agent` in frontmatter.
- Before making architectural decisions, run `lexi concepts <topic>` to check for existing conventions/decisions.
- When introducing a cross-cutting pattern or convention, create a concept file with `lexi concept new <name>`. The test: "Would a future agent in a different part of the codebase benefit from knowing this?" If scoped to one directory, use `.aindex` Local Conventions instead.
- When code changes affect an existing concept's rules, update the concept file directly. Append to the Decision Log section if the change represents a decision.
- Before debugging an unfamiliar error, run `lexi stack search "<error or topic>"` to check if a previous agent has solved it. After solving a non-trivial bug (one that took >1 attempt), run `lexi stack post --title "..." --tag ...` to record the problem and solution for future agents.
- If leaving something incomplete in a directory, create a `.iwh` file in `.lexibrary/<mirror-path>/` with a description of what's unfinished and any warnings for the next agent. If work is complete, do not create a `.iwh`.

**Note:** Agents are never instructed to run `lexictl update`, `lexictl validate`, or `lexictl status`. Those are maintenance operations handled by separate processes. The agent's only obligation is to update design files directly during coding.

### Integration mechanisms beyond rules

Rules files tell agents what to do, but deeper integration makes library usage automatic rather than opt-in. The agent setup should generate environment-appropriate integration points:

**Hooks** (environment-specific, event-driven):
- **Session start hook** — runs `lexictl status --quiet` and surfaces a one-line health warning if the library needs attention. Agents see this passively without having to remember to check.
- **Pre-edit hook** — runs `lexi lookup <file>` before file modifications, ensuring the agent always has the design file context. (Note: may be too aggressive for some workflows — configurable.)

**Skills / Commands** (agent-invocable, on-demand):
- **Orient skill** (`/lexi-orient` or equivalent) — reads `START_HERE.md` + checks for project-root `.iwh` + runs `lexictl status --quiet`, returning a single consolidated context block for session start.
- **Search skill** (`/lexi-search <topic>`) — wraps `lexi search` with richer context, combining concept lookup + Stack search + relevant design files into one response.

**Subagent patterns** (for multi-agent environments):
- A **library maintenance subagent** that handles `lexictl validate` issues, runs periodic `lexictl update`, and keeps the library healthy — freeing coding agents from maintenance tasks entirely.
- A **knowledge capture subagent** that monitors coding sessions and prompts for Stack posts when non-trivial debugging occurs, or suggests concept creation when cross-cutting patterns emerge.

The specific mechanisms depend on the agent environment's capabilities. The principle: **make the right thing automatic, the useful thing easy, and the maintenance thing invisible.**

---

## 9. CLI Design

Two CLIs serve different audiences. `lexi` is the agent-facing interface for day-to-day coding. `lexictl` is the control plane for setup, generation, and maintenance. Both are installed together as part of the same package.

### Design principles

- **Query-oriented** — single commands return everything an agent needs for a given scope.
- **Agent-readable by default** — Concise structured text output designed for agent consumption.
- **Minimal round-trips** — agents are token-constrained. One call, scoped output. Don't make agents chain multiple commands for basic lookups.
- **Pipeable** — commands support composition. `lexi lookup` output includes wikilinks that can feed into `lexi concepts`, reducing multi-step lookups to a single piped invocation.
- **Read and write** — agents consume the library *and* contribute back to it (Stack posts, design file updates, concepts).
- **Separation of concerns** — agents only have access to `lexi`; maintenance operations live in `lexictl`. This prevents agents from accidentally triggering expensive LLM calls or running maintenance tasks mid-coding.

### `lexi` — agent-facing commands

> Commands marked **(planned)** are part of the target design but not yet implemented.

```
lexi lookup <file>                        Return design file + reverse links from link graph index
lexi index <directory> [-r]               Return .aindex for a directory (-r for recursive)
lexi describe <directory> "description"   Update billboard description in .aindex
lexi concepts [<topic>]                   List or search concept files
  (planned) --tag <t>                       Filter by tag
  (planned) --status <s>                    Filter by status
  (planned) --all                           Include deprecated concepts
lexi concept new <name>                    Create a new concept from template
lexi concept link <file> <concept>         Add wikilink to a design file
lexi stack search <query> [--tag <t>] [--scope <path>] [--status <s>]
                                          Search Stack posts
lexi stack post --title "..." [--tag ...] [--bead <id>]
                                          Create a new Stack post
lexi stack answer <post-id> --body "..."  Add an answer to a post
lexi stack vote <post-id> [--answer <n>] up|down [--comment "..."]
                                          Vote on a post or answer
lexi stack accept <post-id> --answer <n>  Accept an answer (marks resolved)
lexi stack view <post-id>                 View a post with answers
lexi stack list [--status <s>] [--tag <t>] List Stack posts with optional filters
lexi stack mark-outdated <post-id>        Mark a Stack post as outdated (planned)
lexi stack duplicate <post-id> --of <id>  Mark a Stack post as duplicate (planned)
lexi search --tag <t> [--scope <path>]    Search by tags across the library
```

### `lexictl` — setup and maintenance commands

```
lexictl init                               Setup wizard (creates .lexibrary/ + agent env rules)
lexictl setup --update                     Refresh agent environment rules from config
lexictl setup --hooks                      Install git post-commit hook for auto-updates
lexictl update [<path>]                    Generate/refresh design files (Archivist)
lexictl update --changed-only <files>      Update only specified files (used by hooks/CI)
lexictl update --start-here                Regenerate START_HERE.md only (planned)
lexictl validate [--severity <s>]          Run consistency checks on library
  (planned) --fix                            Auto-fix certain issues
lexictl status [--quiet]                   Show library health / staleness dashboard
lexictl sweep                              Run one update sweep (process pending changes, exit)
lexictl sweep --watch                      Run periodic sweeps in foreground (safety net)
lexictl daemon start|stop|status           Watchdog daemon (deprecated, requires watchdog_enabled)
```

---

## 10. Packaging and Distribution

- **Build system** — hatchling, src layout (`src/lexibrarian/`).
- **Global install** — `pipx install lexibrarian` or `uv tool install lexibrarian`. Both `lexi` and `lexictl` go on PATH.
- **Per-project init** — `lexictl init` runs the setup wizard to create the `.lexibrary/` directory, its structure, an empty `.lexignore` file, and agent environment rules. Config is version-controlled with the project.
- **Not a project dependency** — Lexibrarian never appears in a project's `requirements.txt` or `pyproject.toml` dependencies. It's a tool, not a library.
- **Project root resolution** — both CLIs walk up from CWD to find `.lexibrary/`, like git finds `.git/`. `lexictl init` is the one exception (creates `.lexibrary/` if not found).
- **Multi-repo awareness** — MVP targets single-repo projects. Multi-repo support is a fast-follow: a root `.lexibrary/config.yaml` references child repos, `START_HERE.md` spans all of them, and the knowledge graph links concepts across repo boundaries. The initial architecture (wikilinks, relative paths, per-project config) is designed to extend to multi-repo without structural changes.

### Ecosystem relationship

Lexibrarian is the knowledge layer in a three-tool stack:

| Tool | Role |
|------|------|
| **OpenSpec** | Change management — specifies *what* is being built and tracks implementation tasks |
| **Beads** | Issue and progress tracking — the source of truth for task state |
| **Lexibrarian** | Codebase knowledge — tells agents *how* the existing code works so they can implement changes correctly |

The typical agent workflow: read `START_HERE.md` to orient → check for `.iwh` signals → check Beads for the active task → use `lexi lookup` to understand relevant code → implement → update design files directly → leave `.iwh` if work is incomplete. Lexibrarian does not replace OpenSpec's task specs or Beads' issue tracking; it answers the question those tools leave open: *"what does the existing code actually do?"*

### Two-tier configuration

| Level | Location | What it configures |
|-------|----------|--------------------|
| **Global** | `~/.config/lexibrarian/config.yaml` (XDG) | Default LLM provider, API key env var names, default agent environment, personal preferences |
| **Project** | `.lexibrary/config.yaml` (project root) | Mapping strategies, token budgets, ignore patterns, trigger modes, project-specific conventions |

Project config overrides global config where they overlap. Global config provides defaults so that `lexictl init` in a new project works without manual setup.

### Project directory structure

`lexictl init` creates the following structure at the project root:

```
project-root/
  .lexignore             # Lexibrarian-specific ignore patterns (gitignore format)
  .lexibrary/
    config.yaml          # project config (version controlled)
    index.db             # link graph index (gitignored, rebuilt by lexictl update)
    START_HERE.md        # bootloader — agent entry point
    concepts/            # concept files (cross-cutting knowledge)
    stack/               # Stack posts (problems, solutions, votes)
    src/                 # design file mirror tree (1:1 within scope_root)
      auth/
        .aindex
        .iwh             # ephemeral I Was Here signal (gitignored)
        login.py.md      # YAML frontmatter + markdown body + metadata footer
```

The `.lexibrary/` directory co-locates config with artifacts — everything Lexibrarian owns lives in one place. The `.lexignore` file lives at the project root (alongside `.gitignore`) and follows gitignore format. `.iwh` files are ephemeral and gitignored (pattern: `**/.iwh`). The link graph index (`index.db`) lives in `.lexibrary/` and is gitignored (see §7a).

### Ignore system

Three layers of ignore patterns are merged:

| Layer | File | Purpose |
|-------|------|---------|
| `.gitignore` | Standard git ignores | Build output, dependencies, etc. |
| `.lexignore` | Lexibrarian-specific ignores | Files in git that shouldn't get design files (generated code, vendored deps, data files) |
| `config.ignore.additional_patterns` | Programmatic patterns | Patterns from `.lexibrary/config.yaml` |

### Scope root

`scope_root` in `.lexibrary/config.yaml` (default: `.`, project root) controls which files get design files. Files within `scope_root` get full design file treatment. Files outside `scope_root` still appear in `.aindex` directory listings (agents can see they exist) but don't get design files. This allows projects to focus documentation on their core code (e.g., `scope_root: "src/"`) without generating design files for scripts, configs, or other peripheral files.

---

## Tech Stack

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Parsing | Tree-sitter | Robust multi-language AST parsing for structural change detection and interface extraction |
| Config | PyYAML + Pydantic 2 | YAML for human/agent readability; Pydantic validates on load |
| Validation | Pydantic 2 | Config and data model validation |
| Output | `rich.console.Console` | Rich terminal output for human mode |
| Graph | Wikilinks (`[[Link]]`) | Zero-infrastructure, agent-native. Upgrade to adjacency list if graph queries needed later |
| Change detection | SHA-256 (hashlib) | Content + interface hashing |
| Daemon | watchdog + debounce | File system monitoring for auto-updates |
| LLM prompts | BAML | Provider-agnostic prompt definitions |
| CLI | Typer | Agent-friendly command structure |
| Packaging | hatchling | src layout, standard Python packaging |

---

## Open Design Notes

> Items below are recognized as important but don't yet have a settled home in the architecture. They'll be incorporated as the design matures.

### Agent context budget guidance

Different agents have different context budgets. `START_HERE.md` (or the agent environment rules) should include navigation strategies by context size:

- **Small context (4K–8K tokens):** Read `START_HERE.md` → one `.aindex` → one design file. Use the graph sparingly (one concept at a time). Rely heavily on Navigation by Intent.
- **Medium context (32K–128K tokens):** Load `START_HERE.md` + several `.aindex` files + 5–10 design files + 2–3 concept nodes. The sweet spot for this system.
- **Large context (200K+ tokens):** Load `START_HERE.md` + all `.aindex` files for relevant scope + concept nodes. Load design files on demand. The library prevents the "loaded everything but now confused" failure mode.

### Non-code artifacts

Database schemas, API specs (OpenAPI), infrastructure definitions (Terraform), CI configs — these exist in most projects and agents need to understand them. They should get design files with adapted templates. The hybrid mapping config (Section 2) should support custom templates per file type or glob pattern.

### Global state and event-driven patterns

Redux stores, event buses, and pub/sub systems are structurally owned by no single file — the state shape, action types, reducers, selectors, and dispatching components are spread across the codebase. A file-centric index will never surface this implicitly.

The recommended approach is a dedicated concept file (e.g., `[[AppState]]`, `[[EventBus]]`) that centrally documents the state schema or event contract, lists all producers and consumers as file links, and flags invariants agents must respect. Individual design files for reducers, selectors, and event handlers then link *to* the concept file rather than describing global state themselves.

This keeps each design file scoped to what *it* does while making the global structure discoverable in one place.

---

## Decision Log

Decisions made during implementation that refine the architecture above. Referenced by phase plans in `plans/`.

| # | Phase | Decision | Resolution | Date |
|---|-------|----------|------------|------|
| D-001 | 2 | LLM usage for `.aindex` generation | Structural-only in Phase 2 (language + line count descriptions). LLM enrichment deferred to Phase 4 (Archivist). | 2026-02-19 |
| D-002 | 2 | `lexi index` scope | Single directory by default; `-r`/`--recursive` flag for bottom-up recursive indexing. | 2026-02-19 |
| D-003 | 2 | Token column in Child Map | Dropped. `AIndexEntry` has `name`, `entry_type`, `description` — no per-entry token count. Token budgets validated at artifact level. | 2026-02-19 |
| D-004 | 2 | `.aindex` change detection | Always regenerate in Phase 2 (no LLM cost). Revisit with directory-level composite hashing when Phase 4 introduces LLM costs. | 2026-02-19 |
| D-005 | 2 | Crawl config in schema | `CrawlConfig` added to `LexibraryConfig` with `binary_extensions` and `max_file_size_kb`. | 2026-02-19 |
| D-006 | 2 | Local Conventions population | Empty placeholder in Phase 2. Future phase adds agent/human population mechanism with preservation on `lexictl update`. | 2026-02-19 |
| D-011 | 4 | File scope | All files within `scope_root` get design files. Non-code files use content hash only. Files outside `scope_root` appear in `.aindex` but don't get design files. | 2026-02-20 |
| D-012 | 4 | LLM client routing | Config-driven via BAML `ClientRegistry`. Provider selected based on `LLMConfig.provider` at runtime. | 2026-02-20 |
| D-013 | 4 | LLM input strategy | Always send interface skeleton + full source file content. | 2026-02-20 |
| D-014 | 4 | Dependency tracking | Forward dependencies only in Phase 4 (AST imports). Reverse dependency index deferred to Phase 10 (Link Graph Index — D-068). | 2026-02-20 |
| D-015 | 4 | Change detection source | Read `StalenessMetadata` from design file HTML comment footer — no separate cache file. | 2026-02-20 |
| D-016 | 4 | Archivist service placement | New `archivist/` module, separate from `llm/service.py`. | 2026-02-20 |
| D-017 | 4 | Old BAML functions | Retire `SummarizeFile`, `SummarizeFilesBatch`, `SummarizeDirectory`. | 2026-02-20 |
| D-018 | 4 | Design file format | YAML frontmatter (agent-facing: description, updated_by) + markdown body + HTML comment footer (machine-facing: hashes, timestamps). | 2026-02-20 |
| D-019 | 4 | Authoring model | Agent-first. Agents write/update design files during coding. `lexictl update` is maintenance backup. `design_hash` in footer detects agent edits. | 2026-02-20 |
| D-020 | 4 | `.lexignore` | New `.lexignore` file (gitignore format) layered on top of `.gitignore` + `config.ignore.additional_patterns`. | 2026-02-20 |
| D-021 | 4 | Scope root | `scope_root` config (default: project root). Files within scope get design files; files outside appear in `.aindex` only. | 2026-02-20 |
| D-022 | 4 | `.aindex` descriptions | File descriptions extracted from design file YAML frontmatter. Directory descriptions written once (`lexi describe` for manual updates). | 2026-02-20 |
| D-023 | 4 | `.aindex` refresh | `lexictl update` on a single file also refreshes the parent directory's `.aindex` Child Map entry. | 2026-02-20 |
| D-024 | 4 | Content-only changes | Call LLM with focused prompt for content-only changes (interface unchanged). | 2026-02-20 |
| D-025 | 4 | Concurrency | Sequential processing for MVP. Async architecture designed for concurrency from the start. Concurrent execution as future optimisation. | 2026-02-20 |
| D-026 | 4 | Footer-less design files | If design file exists but has no footer, treat as `AGENT_UPDATED` — trust content, add footer. Prevents overwriting agent-authored files. | 2026-02-20 |
| D-027 | 4 | Non-code change level | Non-code files use `CONTENT_CHANGED` state (not `INTERFACE_CHANGED`). Same LLM behavior, distinct label for clarity. | 2026-02-20 |
| D-028 | 5 | Concept index location | `lexi concepts` command, NOT embedded in START_HERE.md. Convention index in START_HERE stays as lightweight routing aid; full concept catalog is CLI-accessed. | 2026-02-21 |
| D-029 | 5 | Concept frontmatter fields | `title`, `aliases`, `tags`, and `status` are mandatory. Aliases enable fuzzy discovery; tags enable search. | 2026-02-21 |
| D-030 | 5 | Concept directory structure | Flat `concepts/` directory — no subdirectories. Hierarchy expressed through wikilinks between concepts. | 2026-02-21 |
| D-031 | 5 | Concept lifecycle | `status` field: `active`, `deprecated`, `draft`. Deprecated concepts resolve with notice + `superseded_by` pointer. `lexictl validate` flags orphans. | 2026-02-21 |
| D-032 | 5 | Concept authoring model | Agent-first, no LLM generation. Archivist's role limited to suggesting wikilinks to existing concepts in design files. | 2026-02-21 |
| D-033 | 5 | Wikilink format | `[[ConceptName]]` in design file `## Wikilinks` sections. Resolver strips brackets for lookup. | 2026-02-21 |
| D-034 | 5 | Concept deletion | Soft delete via `status: deprecated`. Hard deletion manual. `lexictl validate` flags orphans for review. | 2026-02-21 |
| D-035 | 6 | Rename Guardrail Forum → The Stack | All references become "The Stack" / "stack posts." CLI: `lexi stack`. Directory: `.lexibrary/stack/`. Wikilink pattern: `ST-NNN`. | 2026-02-21 |
| D-036 | 6 | Vote model | Posts and answers have net `votes` field (up minus down). Vote actions recorded as comments with `[upvote]`/`[downvote]` context. Downvotes require comment. | 2026-02-21 |
| D-037 | 6 | Tags unified across artifact types | Tags in Stack posts, concepts, and design files share the same namespace. `lexi search --tag` returns results from all three. | 2026-02-21 |
| D-038 | 6 | Unified search | `lexi search` is the single cross-artifact search command. Returns grouped results from design files, concepts, and Stack posts. | 2026-02-21 |
| D-039 | 6 | Post storage model | Markdown files. YAML frontmatter (mutable: votes, status, accepted). Body is append-only (answers and comments never edited/deleted). | 2026-02-21 |
| D-040 | 6 | Post statuses | `open`, `resolved`, `outdated`, `duplicate`. Transitions: open → resolved (answer accepted), any → outdated (files changed), any → duplicate (with pointer). | 2026-02-21 |
| D-041 | 6 | Staleness detection for Stack posts | `lexictl validate` flags posts whose referenced source files changed significantly (hash comparison). Agents verify or mark outdated. | 2026-02-21 |
| D-042 | 6 | Downvotes require comment | CLI enforces `--comment` on `lexi stack vote <id> down`. Comment appended with `[downvote]` context. | 2026-02-21 |
| D-043 | 6 | Wikilink pattern for Stack | `[[ST-NNN]]` format. Resolver extended to recognise `ST-NNN` alongside concept names. | 2026-02-21 |
| D-044 | 6 | Bead integration | Optional `bead` field in post frontmatter. No hard dependency on Beads. | 2026-02-21 |
| D-045 | 7 | Validate severity tiers | Validation issues grouped into three tiers: **error** (broken references, missing files), **warning** (stale hashes, token budget violations, orphan concepts), **info** (bidirectional gaps, potentially outdated Stack posts). | 2026-02-21 |
| D-046 | 7 | `lexictl status` output model | Compact summary: artifact counts by type, stale count, issue counts by severity, last update timestamp. Non-zero exit code when errors or warnings exist (enables hooks/CI). | 2026-02-21 |
| D-047 | 7 | Validate is read-only | `lexictl validate` never modifies files. Reports issues only. Fixes via `lexictl update`, agent edits, or future `--fix` flag. | 2026-02-21 |
| D-048 | 7 | Bidirectional consistency — deferred scope | Full bidirectional validation requires the reverse dependency index (not yet implemented). Phase 7 validates forward direction only: files in `## Dependencies` must exist. Reverse check deferred to Phase 10 (Link Graph Index). Resolved by D-072. | 2026-02-21 |
| D-049 | 7 | Local Conventions — future structural upgrade | Current `list[str]` model doesn't support titles, tags, or search. Future phase upgrades to structured model with search integration and agent-friendly creation workflow. See Q-004. | 2026-02-21 |
| D-050 | 7 | `lexi lookup` convention inheritance | `lexi lookup <file>` appends applicable Local Conventions by walking up parent `.aindex` files. Surfaces scoped conventions at the moment of highest agent attention. | 2026-02-21 |
| D-051 | 7 | Maintenance service pattern | Library health (`lexictl validate`, `lexictl status`) is a maintenance concern, not a coding workflow concern. Coding agents use `lexi` read/write-back operations; maintenance handled by `lexictl` via dedicated service, CI, or scheduled process. | 2026-02-21 |
| D-052 | 8 | CLI split — `lexi` / `lexictl` | Two CLIs: `lexi` (agent-facing: lookup, search, concepts, stack, describe) and `lexictl` (setup/maintenance: init, update, validate, status, daemon). Same package, two entry points. Enforces D-051 at the tool boundary. | 2026-02-22 |
| D-053 | 8 | Replace HANDOFF.md with I Was Here (IWH) | Directory-scoped, ephemeral, pull-based inter-agent signals. `.iwh` files in `.lexibrary/` mirror tree, gitignored. Created only when needed, consumed (deleted) on read. Replaces mandatory project-wide HANDOFF.md. | 2026-02-22 |
| D-054 | 8 | Combined init+setup wizard | `lexictl init` replaces separate `lexi init` + `lexi setup`. Guided wizard: project detection, scope root, agent environment (auto-detected), LLM provider, ignore patterns, token budgets, IWH. Re-init on existing project errors with pointer to `lexictl setup --update`. | 2026-02-22 |
| D-055 | 8 | API key security model | Store LLM provider name + env var name in config, never the key value. Runtime reads from env var. Lexibrarian never stores, logs, or transmits API keys. Wizard detects available env vars and confirms with user. | 2026-02-22 |
| D-056 | 8 | `lexictl update` replaces `lexi update` | Agents never invoke update directly — they edit design files during coding. `lexictl update` is the maintenance-only Archivist safety net. Reinforces agent-first authoring model (D-019). | 2026-02-22 |
| D-057 | 8 | IWH scope field | `.iwh` files include a `scope` field: `warning` (be aware), `incomplete` (work started, not finished), `blocked` (something broken, fix first). | 2026-02-22 |
| D-058 | 8 | Persist agent environment in config | `lexictl init` stores `agent_environment` in project config. `lexictl setup --update` reads from config without requiring the env argument again. Resolves Q-008. | 2026-02-22 |
| D-059 | 9 | Foreground-only daemon | No background daemonization (no double-fork, `setsid`, or platform-specific process management). The user's terminal/IDE/process manager handles lifecycle. Aligns with zero-infrastructure principle. Revisit if user feedback shows strong demand for background mode — `subprocess.Popen` with detach is the cross-platform fallback if needed. | 2026-02-22 |
| D-060 | 9 | Atomic writes for daemon output | All daemon writes to `.lexibrary/` use write-to-temp-then-`os.replace()`. Atomic on POSIX, near-atomic on Windows. Prevents agents from reading partially-written design files or `.aindex` files. | 2026-02-22 |
| D-061 | 9 | Design hash re-check before write | After LLM generation completes, re-check `design_hash` before writing. If an agent edited the design file during the LLM call, discard the LLM output. Closes the TOCTOU window in the agent-first authoring model (D-019). | 2026-02-22 |
| D-062 | 9 | Git operation suppression window | Daemon watches `.git/HEAD` for changes. After branch switches, stash pops, or rebases, suppresses file change events for a configurable window (default 5s), then runs a single consolidated update. Prevents per-file LLM calls during bulk file changes. | 2026-02-22 |
| D-063 | 9 | Conflict marker detection | Daemon skips source files containing git conflict markers (`<<<<<<<`) before invoking the Archivist. Logged as warning. Re-checked on next file save. | 2026-02-22 |
| D-064 | 9 | `.aindex` per-directory write lock | A per-directory lock prevents concurrent `.aindex` writes when async processing is enabled (D-025). Implemented from the start so the concurrency upgrade is safe. No-op under sequential MVP. | 2026-02-22 |
| D-065 | 9 | Watchdog daemon deprecated | The watchdog-based real-time daemon is retained but deprecated and off by default (`daemon.watchdog_enabled: false`). It creates an adversarial relationship with the agent-first authoring model (D-019) — during active agent sessions, it wastes LLM calls producing output that gets discarded. Git post-commit hooks are the recommended primary trigger (fires at "work is done" boundary, zero race conditions). Periodic sweep (60 min, skip-if-unchanged) is the safety net. The daemon remains available for human-heavy teams or demo environments via config opt-in. | 2026-02-22 |
| D-066 | 9 | Sweep skip-if-unchanged | Before running a scheduled sweep, scan `scope_root` for any file with `mtime` newer than the last sweep timestamp. If nothing changed, skip entirely. Cheap `os.scandir()` stat walk, no hashing. The sweep interval (default: 60 min) becomes a maximum — sweeps only fire when there's actual work. | 2026-02-22 |
| D-067 | 9 | Git post-commit hook as primary trigger | `lexictl setup --hooks` installs a post-commit hook running `lexictl update --changed-only` in the background. Post-commit (not pre-commit) because the library should never block code delivery. Hook runs in background (`&`) with output to `.lexibrarian.log`. Installation detects and preserves existing hooks. | 2026-02-22 |
| D-068 | 10 | Merge Phase 10 (Reverse Deps) + Phase 11 (Query Index) | Merged into single Phase 10: Unified Link Graph. SQLite index covers all cross-artifact link types (AST imports, wikilinks, Stack refs, tags). Reverse deps served at query time, not written to files. Old Phase 11 eliminated — the index is required for reverse lookups, not an optional performance optimisation. | 2026-02-22 |
| D-069 | 10 | Link graph storage | `sqlite3` (stdlib). `.lexibrary/index.db`, gitignored, always rebuildable from source files. No new dependencies. SQLite WAL mode for concurrent read/write. | 2026-02-22 |
| D-070 | 10 | Reverse deps NOT written to design files | Computed dependents served via `lexi lookup` at read time from the link graph index. Avoids dual ownership of agent-authored files, cascading writes across many files for a single import change, and spurious merge conflicts. `DesignFile.dependents` field kept on the model for backward compatibility but never populated by the pipeline. | 2026-02-22 |
| D-071 | 10 | Graceful degradation | If `index.db` is missing, corrupt, or stale, all CLI commands still work. `lexi lookup` omits the reverse links section. `lexi search --tag` falls back to file scanning. `lexictl status` reports index health. No hard dependency on the index existing. | 2026-02-22 |
| D-072 | 10 | D-048 bidirectional validation now implementable | With the link graph, bidirectional consistency validation becomes a SQL query rather than a full file scan. Implemented as an info-severity check in `lexictl validate`. Resolves the deferral in D-048. | 2026-02-22 |
| D-073 | 10 | `meta` table format | Key-value pairs (`key TEXT PK`, `value TEXT`) — extensible without schema migration. Includes `artifact_count` and `link_count` keys for fast `lexictl status` reporting without `SELECT COUNT(*)`. | 2026-02-22 |
| D-074 | 10 | Source + Design as separate artifact kinds | Both source files and design files get rows in the `artifacts` table, connected by a `design_source` link type. Tracks hashes correctly per file, attributes links to their true origin (AST imports from source, wikilinks from design files), and supports grouped design files later (one `_group.md` → multiple source files via multiple `design_source` links). | 2026-02-22 |
| D-075 | 10 | FTS5 full-text search | Standalone `artifacts_fts` FTS5 virtual table with `porter unicode61` tokenization. Builder-managed (no trigger sync — body content requires file reads, not stored on `artifacts`). Replaces O(N) file scanning in `lexi search` with ranked full-text queries. | 2026-02-22 |
| D-076 | 10 | Alias table for concept resolution | `aliases` table with `UNIQUE(alias) COLLATE NOCASE`. Populated from `ConceptFileFrontmatter.aliases`. Enables O(1) concept lookup by any name/alias, replacing the linear scan in `WikilinkResolver`. | 2026-02-22 |
| D-077 | 10 | Conventions as indexed artifacts | `kind='convention'` artifacts with synthetic paths (`{directory_path}::convention::{ordinal}`). Dedicated `conventions` table stores directory scope and ordering. Conventions participate in link graph (via `convention_concept_ref`), FTS, and tags. | 2026-02-22 |
| D-078 | 10 | `link_context` on links | Free-form TEXT column for link metadata. Stores import statement text for `ast_import`, section headings for `wikilink`, NULL when not applicable. No rigid schema — callers parse as needed. | 2026-02-22 |
| D-079 | 10 | `build_log` table | Per-artifact build tracking with `build_started`, `build_type` (full/incremental), `action` (created/updated/deleted/unchanged/failed), `duration_ms`, and `error_message`. Application-level cleanup retains last 30 days. | 2026-02-22 |
| D-080 | 10 | `created_at` on artifacts | ISO 8601 TEXT column. Populated from frontmatter `created` fields where available, file `mtime` otherwise. Enables time-based queries and staleness reporting without per-file `stat()` calls. | 2026-02-22 |
| D-081 | 10 | Multi-hop query support | Recursive CTEs in SQLite enable transitive queries ("what's 2 hops from Authentication?", "full import tree"). Exposed via `LinkGraph.traverse()` with configurable `max_depth` (default: 3). No schema changes needed. | 2026-02-22 |

### Open Questions

| # | Phase | Question | Status |
|---|-------|----------|--------|
| Q-001 | 2+ | How should `lexictl update` preserve agent/human-authored Local Conventions when regenerating `.aindex`? Options: parse-and-reinject vs. treat as untouchable section. | Open |
| Q-002 | 4 | When LLM enrichment replaces structural descriptions, should change detection use directory listing hash or composite hash? | Resolved — D-022/D-023: `.aindex` file descriptions are extracted from design file frontmatter (not regenerated by LLM). Directory descriptions are written once. `lexictl update` refreshes individual Child Map entries, not the whole `.aindex`. |
| Q-003 | 4 | Should `lexictl update` on a single file also update the parent directory's `.aindex`? | Resolved — D-023: Yes, refresh the parent `.aindex` Child Map entry with the description from the design file's YAML frontmatter. |
| Q-004 | 7+ | Local Conventions in `.aindex` files need a structural upgrade to become first-class searchable artifacts. Current `list[str]` model doesn't support titles, tags, concept links, or search integration. The solution must: (a) support structured convention metadata (title, tags, concept links), (b) be searchable via `lexi search`, (c) be easy for agents to add new conventions (e.g., `lexi convention add <dir> "..."`), (d) surface inherited conventions in `lexi lookup`, (e) survive `.aindex` regeneration (relates to Q-001). Requires `.aindex` format revision + search integration + creation workflow. | Open |
| Q-005 | 4+ | Should `lexictl update` support a `--dry-run` flag that reports what would change (files needing updates, change levels) without making LLM calls? Useful for cost estimation on large projects and for previewing the scope of an update. | Open |
| Q-006 | 6+ | Stack posts are "unbounded (append-only body)" by design. Should there be an optional warning threshold (e.g., `stack_post_tokens: 2000` in `token_budgets`) so `lexictl validate` can flag runaway posts? Or is unbounded the right call? | Open |
| Q-007 | 8+ | Should `scope_root` support a list of paths or glob patterns (e.g., `["src/", "lib/"]`) for monorepos with multiple source roots? Currently a single string. | Open |
| Q-008 | 8 | Should `lexictl init` persist the agent environment selection in project config so that `lexictl setup --update` doesn't require the env argument again? | Resolved — D-058: Yes. `lexictl init` wizard stores `agent_environment` in project config. |
| Q-009 | 4 | Section 1 says START_HERE.md topology format is "configurable" (Mermaid vs ASCII) but no config key exists. Should config include `start_here.topology_format: mermaid | ascii`? Or is this an Archivist prompt concern, not a config concern? | Open |
| Q-010 | 4+ | The "Non-code artifacts" design note mentions "adapted templates" for database schemas, API specs, Terraform, etc. Should config support per-file-type template overrides (e.g., `mapping.templates: [{pattern: "*.sql", template: "database"}]`)? This relates to the unimplemented `mapping.strategies` config. | Open |
| Q-011 | 8+ | Should `lexi health` exist as a lightweight agent-facing health check? One-line output: "3 warnings, 0 errors, 2 stale." Alternative to agents calling `lexictl status`. | Open |
| Q-012 | 8+ | Should `lexi verify` (or `lexi validate`) exist for end-of-session agent self-checks? Agent runs this before ending to verify it hasn't missed design file updates. Lighter than `lexictl validate`. | Open |
| Q-013 | 8+ | Billboard staleness detection — how should `lexictl` determine if a directory billboard is outdated? File additions/removals change directory content but the billboard describes *purpose*, which rarely changes. Possible: flag when Child Map changes significantly. | Open |
| Q-014 | 8 | IWH same-directory race condition — accept or mitigate? MVP: accept as known limitation. IWH is advisory, not transactional. Document that in same-directory parallel work, agents should coordinate through task systems. | Accepted as known limitation. IWH is advisory, not transactional. Same-directory parallel agents coordinate through task systems (Beads). |
| Q-015 | 8+ | Should `scope_root` in the init wizard support multiple paths from day one? Relates to Q-007. Multi-root is common in monorepos. Wizard could accept comma-separated paths. | Open |
| Q-016 | 10+ | Should `lexi lookup --no-index` flag exist to explicitly skip index queries (for debugging or when the index is suspected stale)? Or is graceful degradation (D-071) sufficient? | Open |
| Q-017 | 10+ | Should the link graph index support graph traversal queries (e.g., "what's 2 hops from Authentication?")? MVP indexes direct links only. Multi-hop queries could enable impact analysis but add complexity. | Open |
