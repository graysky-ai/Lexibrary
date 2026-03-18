# Symphony SPEC.md Analysis — Lessons for Lexibrary

**Source:** [openai/symphony SPEC.md](https://github.com/openai/symphony/blob/main/SPEC.md)
**Date:** 2026-03-14

---

## What Symphony Is

Symphony is a long-running automation service that polls an issue tracker (Linear), creates
isolated per-issue workspaces, and runs coding agent sessions against them. It is a
**scheduler/runner and tracker reader** — the agent does the actual coding work; Symphony
orchestrates when and where it runs.

Key design characteristics:
- Daemon with poll-loop architecture (not event-driven)
- Single authoritative in-memory orchestrator state (no persistent DB)
- Workspace isolation: one directory per issue, sanitised paths
- Policy-in-repo via `WORKFLOW.md` (YAML frontmatter + prompt template)
- Dynamic config reload without restart
- Explicit concurrency control, retry with exponential backoff, stall detection
- Language-agnostic spec: pseudocode algorithms, no implementation language assumed

The spec is ~2,175 lines of markdown across 18 sections plus an appendix. It is written to
be **implementable by a coding agent** — OpenAI's README literally says "instruct a coding
agent to build Symphony using the spec."

---

## Structural Comparison

| Aspect | Symphony SPEC.md | Lexibrary artefacts |
|--------|-----------------|-------------------|
| **Purpose** | Prescriptive service specification | Knowledge layer for codebase navigation |
| **Audience** | Coding agents building an implementation | Coding agents navigating/editing a codebase |
| **Entry point** | Single SPEC.md (~2,175 lines) | START_HERE.md (<2KB) + tiered artefacts |
| **Config contract** | WORKFLOW.md (YAML frontmatter + prompt body) | .lexibrary/config.yaml (Pydantic-validated) |
| **Domain model** | Formal entity definitions with typed fields | Pydantic 2 models in code (no prose spec) |
| **State machines** | Explicit named states + transition triggers | Implicit in status enums (draft/active/deprecated) |
| **Algorithms** | Pseudocode in spec (language-agnostic) | Implementation in Python (no pseudocode spec) |
| **Test contract** | Validation matrix (spec requirement -> test) | Tests exist but no spec-to-test mapping |
| **Failure model** | Dedicated section with classified failure types | ErrorSummary in code; no high-level taxonomy doc |
| **Scope separation** | Core conformance vs extension conformance | No formal conformance levels |
| **Information density** | Single monolithic document | Distributed across 5 artefact types + link graph |

### The Fundamental Difference

Symphony's spec is a **build document** — it tells an agent what to create from scratch.
Lexibrary's artefacts are **navigation documents** — they tell an agent what already exists
and how to find things. These are complementary purposes, not competing ones.

Symphony could benefit from Lexibrary-style navigation once it's built. Lexibrary could
benefit from Symphony-style specification rigour in its own plans and design docs.

---

## Lessons Worth Adopting

### 1. Goals and Non-Goals (Section 2)

**What Symphony does:** Opens with an explicit Goals / Non-Goals section. Goals are concrete,
testable statements ("poll the issue tracker on a fixed cadence and dispatch work with bounded
concurrency"). Non-Goals rule out scope creep ("rich web UI or multi-tenant control plane").

**What we have:** `plans/lexibrary-overview.md` has Principles but no explicit Non-Goals.
Individual plans have task lists but don't formally exclude what's out of scope.

**Recommendation:** Add a `## Non-Goals` section to `plans/lexibrary-overview.md` and to each
active plan. Non-Goals are especially valuable for AI agents — they prevent the agent from
over-engineering or building features that are explicitly unwanted.

Example additions:
- Non-Goal: web UI or dashboard for browsing artefacts
- Non-Goal: runtime code analysis or execution tracing
- Non-Goal: project dependency management or package resolution
- Non-Goal: replacing IDE features (go-to-definition, refactoring)

---

### 2. Formal Domain Model Section (Section 4)

**What Symphony does:** Defines every entity (Issue, Workspace, RunAttempt, LiveSession,
RetryEntry, OrchestratorState) with typed fields, stable identifier rules, and normalisation
conventions. This is separate from implementation code — it's the conceptual contract.

**What we have:** Pydantic 2 models in `src/lexibrary/artifacts/` define the schemas, but
there's no single prose document that describes all entity types, their relationships, and
identifier conventions in one place. An agent must read multiple blueprint files and source
modules to reconstruct the full picture.

**Recommendation:** Create a `plans/domain-model.md` (or a Lexibrary concept) that serves as
the prose specification for all artefact types. Structure:

```
## Entities
### Design File
- Fields: (listed with types and descriptions)
- Identity: derived from source_path
- Lifecycle: active -> deprecated (with deprecated_at, deprecated_reason)
- Relationships: links to concepts (wikilinks), Stack posts (stack_refs), source file (design_source)

### Concept
...

### Convention
...

### Stack Post
...

### AIndex
...

## Identifier Rules
- Concept/Convention slugs: slugify(title), collision suffix -2, -3, ...
- Stack post IDs: ST-<NNN> auto-incremented
- Design file paths: mirror source tree under .lexibrary/designs/
...
```

This gives agents a single reference for the conceptual model without needing to read source
code. Our Pydantic models remain the implementation truth, but the prose spec is the
design truth.

---

### 3. Explicit State Machine Documentation (Section 7)

**What Symphony does:** Defines two state machines:
- Issue Orchestration States (5 states: Unclaimed -> Claimed -> Running -> RetryQueued -> Released)
- Run Attempt Lifecycle (11 phases: PreparingWorkspace -> ... -> Succeeded/Failed/TimedOut/Stalled)

Each state has named transition triggers (Poll Tick, Worker Exit, Retry Timer, etc.) and
explicit idempotency/recovery rules.

**What we have:** Artefact statuses exist as enum values:
- Design files: `active | unlinked | deprecated`
- Concepts: `draft | active | deprecated`
- Conventions: `draft | active | deprecated`
- Stack posts: `open | resolved | outdated | duplicate | stale`

But transitions between states are implicit — embedded in mutation functions (`mark_duplicate()`,
`mark_outdated()`, `accept_answer()`) without a documented state diagram.

**Recommendation:** Document the state machines for each artefact type. Even simple ones
benefit from explicitness:

```
Convention lifecycle:
  draft ──[user/agent activates]──> active
  active ──[deprecation trigger]──> deprecated
  deprecated ──[no revival; create new convention instead]

Stack post lifecycle:
  open ──[finding accepted + fix verified]──> resolved
  open ──[matches existing post]──> duplicate (sets duplicate_of)
  open ──[referenced code changed significantly]──> outdated
  resolved ──[no activity for N days]──> stale
  any ──[manual close]──> resolved
```

The convention deprecation module (`lifecycle/convention_deprecation.py`) already implements
some of this logic — documenting it as a state machine would make the design intent visible
without reading the code.

---

### 4. Reference Algorithms in Pseudocode (Section 16)

**What Symphony does:** Provides 6 pseudocode algorithms covering all critical paths:
service startup, poll-and-dispatch tick, reconcile active runs, dispatch one issue, worker
attempt, and worker exit/retry handling. These are language-agnostic and directly translatable.

**What we have:** Algorithms live only in Python implementation. Key algorithms that would
benefit from pseudocode documentation:

- **Wikilink resolution chain** (convention-first -> concept -> fuzzy match -> unresolved)
- **Link graph build pipeline** (scan artefacts -> extract links -> populate tables -> build FTS)
- **Unified search routing** (tag path vs FTS path vs file-scan fallback)
- **Validation orchestration** (check selection -> parallel execution -> report aggregation)
- **Archivist pipeline** (change detection -> LLM generation -> atomic write -> aindex regen)

**Recommendation:** Add pseudocode to the domain-model doc or to individual plan files for
the 3-5 most critical algorithms. These serve as the "what should happen" contract — if the
implementation drifts, the pseudocode reveals the drift.

Priority: Wikilink resolution and unified search are the most agent-facing and would benefit
most from a language-agnostic spec.

---

### 5. Test and Validation Matrix (Section 17)

**What Symphony does:** Every section of the spec maps to testable assertions, organised into
three profiles:
- **Core Conformance** — deterministic tests required for all implementations
- **Extension Conformance** — required only for optional features
- **Real Integration Profile** — environment-dependent smoke tests

Each bullet is a specific, verifiable assertion: "Workspace path sanitization and root
containment invariants are enforced before agent launch."

**What we have:** ~35 test files covering models, parsers, serializers, CLI, and validators.
But no document that maps *what property is being tested* to *which test file verifies it*.
An agent looking at test failures has to reverse-engineer what specification the test enforces.

**Recommendation:** Create a lightweight test matrix — either as a concept artefact or a
section in the domain-model doc:

```
## Test Matrix

| Specification Property | Test File | Notes |
|----------------------|-----------|-------|
| Design file frontmatter validates status enum | test_convention_models.py | |
| Wikilink resolver: convention-first precedence | test_query.py | |
| Stack post parser: missing sections default to empty | test_parser.py | |
| Atomic writes survive crash (temp + rename) | test_serializer_roundtrip.py | |
| Search: FTS fallback when no link graph | test_search.py | |
```

This also helps identify gaps — spec requirements without tests.

---

### 6. Implementation Checklist / Definition of Done (Section 18)

**What Symphony does:** A flat checklist that defines what "done" means. Separated into
Required (core conformance), Recommended Extensions, and Operational Validation. Includes
explicit TODOs for future work.

**What we have:** Plans have task lists and phases, but they describe *what to build next*
rather than *what constitutes a complete feature*. There's no single "definition of done"
for, say, "the wikilink system is complete" or "the Stack subsystem is production-ready."

**Recommendation:** Add a `## Definition of Done` section to each plan or feature spec.
Keep it flat and checkable:

```
## Definition of Done: Wikilink System
- [ ] Resolver handles convention, concept, and Stack post targets
- [ ] Alias resolution with case-insensitive matching
- [ ] Fuzzy suggestions for unresolved links (cutoff 0.6)
- [ ] Validator check: wikilink_resolution catches broken links
- [ ] Link graph: wikilink edges stored with source/target
- [ ] Round-trip: serialize(parse(x)) preserves wikilinks
- [ ] CLI: `lexi search` surfaces wikilink targets
```

---

### 7. Failure Model as First-Class Documentation (Section 14)

**What Symphony does:** Classifies all failures into 5 categories (Workflow/Config, Workspace,
Agent Session, Tracker, Observability) with explicit recovery behaviour for each. Also defines
"Partial State Recovery" rules for restart scenarios and "Operator Intervention Points."

**What we have:** `ErrorSummary` aggregates errors by phase. `exceptions.py` defines a
hierarchy. The validator classifies issues by severity (error/warning/info). But there's no
unified failure taxonomy that tells an agent: "when X fails, here's what happens and what
you should do."

**Recommendation:** Add a failure model section to the overview or as a dedicated concept:

```
## Failure Classes

1. Config Failures
   - Missing .lexibrary/ -> LexibraryNotFoundError -> CLI exits with guidance
   - Invalid config.yaml -> ConfigError -> CLI exits with validation details

2. Parse Failures
   - Malformed artefact -> ParseError or None return -> ErrorSummary records, pipeline continues
   - Corrupt link graph -> LinkGraphError -> graceful degradation to file-scan

3. LLM Failures
   - Provider unreachable -> LLMServiceError -> archivist skips file, records error
   - Rate limit -> RateLimiter queues retry

4. Validation Failures
   - Error severity -> exit code 1 (broken links, missing files)
   - Warning severity -> exit code 0 (stale hashes, orphans)
   - Info severity -> exit code 0 (coverage gaps)
```

---

### 8. Config Cheat Sheet (Section 6.4)

**What Symphony does:** Provides an "intentionally redundant" flat listing of every config
field with type, default, and parent key. Designed explicitly so "a coding agent can implement
the config layer quickly."

**What we have:** Config is defined in `config/schema.py` as Pydantic models. Agents must
read source code or the blueprint to understand available fields.

**Recommendation:** Add a config cheat sheet as a Stack post, concept, or section in the
overview. Even a simple flat table would help:

```
| Field | Type | Default | Notes |
|-------|------|---------|-------|
| scope_root | list[str] | ["src/"] | Directories to index |
| llm.provider | str | "anthropic" | LLM provider for archivist |
| llm.model | str | "claude-sonnet-4-20250514" | Model for generation |
| ast.enabled | bool | true | Enable tree-sitter parsing |
| iwh.enabled | bool | true | Enable I Was Here signals |
```

---

### 9. Normalisation Rules as Explicit Contracts (Section 4.2)

**What Symphony does:** Defines exactly how identifiers are derived, compared, and composed:
- Workspace keys: replace `[^A-Za-z0-9._-]` with `_`
- Issue states: compare after `lowercase`
- Session IDs: compose from `<thread_id>-<turn_id>`

**What we have:** `slugify()` exists in code. Wikilink resolution does case-insensitive
matching. But these rules aren't documented as contracts — they're implementation details.

**Recommendation:** Include normalisation rules in the domain model doc:
- Concept/Convention slugs: `title.lower().replace(' ', '-')`, collision suffix `-2`, `-3`
- Tag comparison: case-sensitive exact match
- Wikilink resolution: case-insensitive title match, convention-first precedence
- Stack post IDs: `ST-<NNN>` zero-padded to 3 digits, monotonically increasing

---

### 10. Extension Points Clearly Marked (Sections 13.7, Appendix A)

**What Symphony does:** Uses consistent terminology throughout:
- "required" — must be in all implementations
- "optional" / "extension" — clearly marked, with separate conformance level
- "implementation-defined" — up to the port, but must be documented
- Appendix for major optional extensions (SSH worker)

**What we have:** Some features are implicitly optional (LLM-based archivist requires API
keys; link graph is rebuilt on demand) but we don't formally distinguish core vs optional
capabilities.

**Recommendation:** Adopt "core" vs "extension" terminology in plans and the overview:

```
Core (always available, no external dependencies):
- Artefact models, parsers, serializers
- Link graph (SQLite, local)
- Validation checks
- CLI commands (lexi)
- IWH system

Extension (requires additional setup):
- Archivist pipeline (requires LLM provider)
- Sweep (periodic background updates via `lexictl sweep --watch`)
- Token counting (requires tiktoken or anthropic SDK)
- Agent rule generation (per-environment: Claude, Cursor, Codex)
```

---

## Patterns We Already Do Well (That Symphony Lacks)

Not everything is a lesson to learn — some things Lexibrary already does better:

### Tiered Context Loading
Symphony's SPEC.md is one 2,175-line monolith. Lexibrary's tiered approach (START_HERE.md
-> .aindex -> design files -> concepts -> Stack posts) is fundamentally better for agent
context windows. An agent building Symphony must load the entire spec; an agent using
Lexibrary loads only what it needs.

### Cross-Artefact Search
Symphony has no search mechanism — agents must read the spec linearly or Ctrl+F. Lexibrary's
unified search with FTS, tag filtering, and link graph traversal is a major advantage.

### Wikilink Graph
Symphony's entities don't reference each other through a queryable graph. Lexibrary's link
graph with 8 typed edge types enables reverse lookups, dependency traversal, and impact
analysis that Symphony can't do.

### Structured Knowledge Capture
Symphony has no equivalent to Stack posts (debugging knowledge), concepts (cross-cutting
ideas), or conventions (coding standards). All knowledge lives in the spec or in code
comments. Lexibrary's separation of knowledge types is more sophisticated.

### Validator as Living Spec
Lexibrary's 13 validation checks act as executable specifications — they continuously verify
that the artefact system is internally consistent. Symphony mentions tests but has no
self-validation mechanism.

### Graceful Degradation
Lexibrary explicitly handles missing link graphs (falls back to file scanning), missing
sections (defaults to empty), and parse errors (returns None, continues). Symphony specifies
this for some cases but Lexibrary's approach is more systematic.

---

## Concrete Next Steps

Ranked by impact-to-effort ratio:

1. **Add Non-Goals to `plans/lexibrary-overview.md`** — 15 minutes, high value for scope
   containment. Prevents agents from building unwanted features.

2. **Document state machines for artefact lifecycles** — 30 minutes, add to overview or as
   a concept. Small effort, clarifies implicit knowledge.

3. **Create a config cheat sheet** — 20 minutes, add as a section in the overview or as a
   Stack post. Saves every agent from reading schema.py.

4. **Add a failure model section to the overview** — 30 minutes. Tells agents what to expect
   when things go wrong.

5. **Create domain-model spec** — 1-2 hours for a first draft. High value but higher effort.
   Could start with just the entity list and expand over time.

6. **Add Definition of Done to active plans** — 15 minutes per plan. Makes completion criteria
   testable.

7. **Create test matrix** — 1 hour for initial mapping. Reveals test gaps and makes the
   spec-to-test relationship explicit.

8. **Add pseudocode for key algorithms** — 1 hour for top 3 algorithms. Useful for
   documentation and for porting to other languages in the future.

---

## Meta-Observation: Spec as Agent Prompt

The most striking thing about Symphony's SPEC.md is that it is designed to be **consumed
directly as an LLM prompt**. The README says to "instruct a coding agent to build Symphony
using the spec." This means the spec is simultaneously:

1. A technical specification for human engineers
2. A prompt for coding agents
3. A test oracle (Section 17 defines pass/fail criteria)

This "spec-as-prompt" pattern is worth studying. Our `CLAUDE.md` and agent rules serve a
similar purpose for agent behaviour, but our architectural specs (plans, overview) are written
more for human consumption. If we ever want agents to implement new Lexibrary features from
spec alone, adopting Symphony's level of precision and explicitness would be valuable.

The key techniques that make Symphony's spec agent-friendly:
- **Exhaustive field listings** — every entity lists every field with type and default
- **Pseudocode algorithms** — unambiguous, directly translatable
- **Redundant cheat sheets** — the same info presented in implementation-friendly format
- **Explicit error categories** — agents know exactly what to catch and how to handle it
- **Test matrix** — agents can verify their own implementation
- **No ambiguity** — "implementation-defined" is used explicitly when the spec leaves a choice;
  everything else is prescriptive
