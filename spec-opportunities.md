# Spec Improvement Opportunities — Inspired by Symphony SPEC.md

**Origin:** Analysis of [openai/symphony SPEC.md](https://github.com/openai/symphony/blob/main/SPEC.md)
**Date:** 2026-03-15
**Context:** Symphony is OpenAI's agent orchestration service. Its spec is a ~2,175-line markdown
document designed to be consumed directly by coding agents as a build-from-scratch prompt. We
analysed it for patterns that could improve Lexibrary's own documentation and artefacts.

**How to use this document:** Each opportunity is self-contained. Pick one, read it fully, and
implement it. You do not need to read the Symphony spec — all relevant lessons are captured here.

---

## Opportunity 1: Add Goals and Non-Goals to Architecture Overview

### What It Solves

`plans/lexibrary-overview.md` has a "Principles" section (agent-first, two CLIs, zero
infrastructure, tiered context) but no explicit **Goals** or **Non-Goals**. This matters because
AI agents working on the codebase have no guardrails against scope creep — they may build features
that are explicitly unwanted (a web UI, runtime tracing, dependency management) because nothing
tells them not to.

Symphony's SPEC.md opens with a dedicated Section 2 "Goals and Non-Goals" where Goals are concrete,
testable statements and Non-Goals explicitly rule out categories of work. This is one of the
highest-value patterns for agent-consumed documentation.

### How to Implement

**File to edit:** `plans/lexibrary-overview.md`

**Location:** Insert a new `## Goals` and `## Non-Goals` section immediately after the existing
`## Principles` section (which ends around line 16) and before `## 1. The Bootloader`.

**Current structure of the file (section headings in order):**
1. Principles
2. 1. The Bootloader: `START_HERE.md`
3. 2. Design Files (Shadow Files)
4. 3. Directory Indexes: Recursive Routing
5. 4. Concepts Wiki: Wikilinks
6. 5. Handling Abstractions, Conventions, and Design Decisions
7. 6. The Stack
8. 7. Change Detection
9. 7a. Link Graph Index
10. 8. Project Setup & Agent Environment
11. 9. CLI Design
12. 10. Packaging and Distribution
13. Tech Stack
14. Open Design Notes
15. Decision Log

**No Goals or Non-Goals section exists currently.**

**Goals section should contain** concrete, testable statements derived from the existing Principles.
Examples:
- Provide agents with tiered context loading: cheap overview always available, detail on demand
- Enable cross-artefact search across concepts, conventions, design files, and Stack posts
- Maintain zero external infrastructure — all data in repo files + local SQLite
- Support multiple agent environments (Claude, Cursor, Codex) from a single project setup
- Detect codebase changes via SHA-256 hashing and regenerate stale artefacts

**Non-Goals section should explicitly exclude:**
- Web UI, dashboard, or browser-based artefact viewer
- Runtime code analysis, execution tracing, or profiling
- Project dependency management or package resolution
- Replacing IDE features (go-to-definition, refactoring, symbol search)
- Multi-tenant or multi-project management from a single instance
- Real-time collaboration or concurrent editing of artefacts
- Version control for artefacts beyond what git provides

**Also add Non-Goals to active plans.** Each of the 10 active plans in `plans/` could benefit from
a brief Non-Goals section scoped to that plan's feature area.

### Complexity and Value

- **Complexity:** Very low. Pure prose addition, no code changes.
- **Value:** High. Directly prevents agents from over-engineering. Every agent session that reads
  the overview will be scoped correctly.
- **Estimated effort:** 15-30 minutes.

---

## Opportunity 2: Formal Domain Model Specification

### What It Solves

Lexibrary has 5 artefact types (Design File, Concept, Convention, Stack Post, AIndex) each defined
as Pydantic 2 models in source code. But there is no single prose document that describes all entity
types, their fields, relationships, identifier conventions, and lifecycle in one place. An agent
must read multiple blueprint files and source modules to reconstruct the full picture.

Symphony's Section 4 "Core Domain Model" defines every entity with typed fields, stable identifier
rules, and normalisation conventions — separate from implementation code. This gives agents a
conceptual reference without needing to read source.

### How to Implement

**Create new file:** `plans/domain-model.md`

**Content structure:**

```
# Lexibrary Domain Model

## Entities

### Design File
- Source model: src/lexibrary/artifacts/design_file.py
- Frontmatter fields: description (str, required), updated_by (archivist|agent|bootstrap-quick|maintainer),
  status (active|unlinked|deprecated), deprecated_at (datetime|None), deprecated_reason (source_deleted|source_renamed|manual|None)
- Full model fields: source_path, frontmatter, summary, interface_contract, dependencies, dependents,
  tests, complexity_warning, wikilinks, tags, stack_refs, metadata (StalenessMetadata)
- Identity: derived from source_path — mirrors source tree under .lexibrary/designs/
  (e.g., src/lexibrary/cli.py → .lexibrary/designs/src/lexibrary/cli.py.md)
- Relationships: design_source (→ source file), wikilinks (→ concepts/conventions),
  stack_refs (→ Stack posts via "ST-NNN" references)

### Concept
- Source model: src/lexibrary/artifacts/concept.py
- Frontmatter fields: title (str, required), aliases (list[str]), tags (list[str]),
  status (draft|active|deprecated), superseded_by (str|None), deprecated_at (datetime|None)
- Full model fields: frontmatter, body, summary, related_concepts, linked_files, decision_log
- Identity: slugify(title) → .lexibrary/concepts/<slug>.md; collision suffix -2, -3, ...
- Relationships: related_concepts (→ other concepts via wikilinks), linked_files (→ source files),
  concept_file_ref (link graph edge)

### Convention
... (similar structure)

### Stack Post
... (similar structure, noting StackFinding sub-entity)

### AIndex
... (similar structure)

## Identifier Rules
- Concept/Convention slugs: title.lower(), spaces→hyphens, collision suffix -2, -3, ...
- Stack post IDs: ST-<NNN> (zero-padded 3 digits, monotonically increasing)
- Design file paths: mirror source tree under .lexibrary/designs/
- Tag comparison: case-sensitive exact match
- Wikilink resolution: case-insensitive, convention-first precedence

## Shared Infrastructure

### StalenessMetadata (footer)
Used by Design Files and AIndex files. Hidden HTML comment footer with fields:
source, source_hash (SHA-256), interface_hash, design_hash, generated (datetime), generator (str)

### Link Graph Edges (8 types)
ast_import, wikilink, stack_file_ref, stack_concept_ref, design_stack_ref, design_source,
concept_file_ref, convention_concept_ref
```

**Data sources for populating this document** (exact field definitions are in these files):
- `src/lexibrary/artifacts/design_file.py` — DesignFile, DesignFileFrontmatter, StalenessMetadata
- `src/lexibrary/artifacts/concept.py` — ConceptFile, ConceptFileFrontmatter
- `src/lexibrary/artifacts/convention.py` — ConventionFile, ConventionFileFrontmatter
- `src/lexibrary/stack/models.py` — StackPost, StackPostFrontmatter, StackFinding, StackPostRefs
- `src/lexibrary/artifacts/aindex.py` — AIndexFile, AIndexEntry
- `src/lexibrary/linkgraph/schema.py` — DDL constants defining the 8 link types and table structure

### Complexity and Value

- **Complexity:** Medium. Requires reading all model files and synthesising into prose. No code
  changes.
- **Value:** Very high. Single reference document for the entire conceptual model. Every agent
  working on artefacts benefits.
- **Estimated effort:** 1-2 hours for a thorough first draft.

---

## Opportunity 3: Explicit State Machine Documentation

### What It Solves

Artefact status values exist as Literal type enums in code, but the valid transitions between
states are implicit — embedded in mutation functions without a documented diagram. An agent working
on Stack post mutations, convention deprecation, or concept lifecycle has to read the implementation
to understand what transitions are legal.

Symphony's Section 7 documents two explicit state machines with named states, transition triggers,
and idempotency rules. Even simple 3-state lifecycles benefit from this explicitness.

### How to Implement

**Where to add:** Either as a section in the new `plans/domain-model.md` (Opportunity 2) or as
a standalone section in `plans/lexibrary-overview.md` under the relevant artefact sections.

**State machines to document (derived from reading the actual code):**

#### Design File Lifecycle
```
States: active, unlinked, deprecated
Transitions:
  active ──[source file deleted]──> deprecated (reason: source_deleted)
  active ──[source file renamed]──> deprecated (reason: source_renamed)
  active ──[manual deprecation]──> deprecated (reason: manual)
  active ──[source file not in scope_root]──> unlinked
  unlinked ──[source file re-added to scope]──> active
  deprecated: terminal state (no revival; create new design file for new source)
```
- `updated_by` tracks who last touched it: archivist (LLM), agent, bootstrap-quick, maintainer

#### Concept Lifecycle
```
States: draft, active, deprecated
Transitions:
  draft ──[ready for use]──> active
  active ──[superseded by newer concept]──> deprecated (sets superseded_by, deprecated_at)
  deprecated: terminal state (create new concept instead; superseded_by points to replacement)
```
- Deprecation confirm policy: `config.concepts.deprecation_confirm` (human|maintainer)

#### Convention Lifecycle
```
States: draft, active, deprecated
Transitions:
  draft ──[user/agent activates]──> active
  active ──[no longer applicable]──> deprecated (sets deprecated_at)
  deprecated ──[TTL expires (config.deprecation.ttl_commits)]──> HARD DELETED
```
- Hard deletion logic: `src/lexibrary/lifecycle/convention_deprecation.py`
  - `check_convention_ttl_expiry()` counts git commits since `deprecated_at`
  - `hard_delete_expired_conventions()` removes `.md` and sibling `.comments.yaml` files
  - TTL default: 50 commits (from `config.deprecation.ttl_commits`)
  - Deprecation confirm policy: `config.conventions.deprecation_confirm` (human|maintainer)
- Source field tracks origin: user, agent, config

#### Stack Post Lifecycle
```
States: open, resolved, outdated, duplicate, stale
Transitions:
  open ──[accept_finding(finding_num, resolution_type)]──> resolved
  open ──[mark_duplicate(duplicate_of)]──> duplicate (sets duplicate_of field)
  open ──[mark_outdated()]──> outdated
  resolved ──[mark_stale()]──> stale (sets stale_at timestamp)
  stale ──[mark_unstale()]──> resolved (clears stale_at)
  any ──[manual close]──> resolved
```
- Mutation functions live in `src/lexibrary/stack/mutations.py` (7 public functions)
- `accept_finding()` is the primary resolution path — sets `finding.accepted = True` and
  optionally sets `resolution_type` (fix|workaround|wontfix|cannot_reproduce|by_design)
- `mark_stale()` requires current status = "resolved"; `mark_unstale()` requires "stale"
- Staleness TTL: `config.stack.staleness_ttl_commits` (default 200) and
  `staleness_ttl_short_commits` (default 100)
- Finding votes: rate-limited to 60s between votes; downvotes require a comment

### Complexity and Value

- **Complexity:** Low-medium. The transitions are already known from reading the code (captured
  above). Just needs to be written as clean documentation.
- **Value:** High. Prevents incorrect state transitions. Makes mutation behaviour predictable
  for agents.
- **Estimated effort:** 30-45 minutes.

---

## Opportunity 4: Reference Algorithms in Pseudocode

### What It Solves

Lexibrary's critical algorithms (wikilink resolution, search routing, link graph build, validation
orchestration) exist only in Python implementation. There's no language-agnostic "what should
happen" contract. If the implementation drifts from design intent, there's no spec to catch it.

Symphony provides 6 pseudocode algorithms in Section 16 covering all critical paths. These are
directly translatable to any language.

### How to Implement

**Where to add:** Either in `plans/domain-model.md` or as appendices to the relevant plan files.

**Priority algorithms to document (with current implementation locations):**

#### Algorithm 1: Wikilink Resolution

Current implementation: `src/lexibrary/wiki/resolver.py`, class `WikilinkResolver`, method `resolve()`

```
function resolve_wikilink(raw):
  text = strip_brackets(raw)  // Remove [[ and ]]

  // Step 1: Stack post pattern match
  if text matches /^ST-\d+$/i:
    scan stack_dir for file matching "ST-{number}-*.md"
    if found: return ResolvedLink(kind="stack", path=matched_file)

  // Step 2: Convention exact title match (case-insensitive)
  for each convention_file in conventions_dir:
    if convention.frontmatter.title.lower() == text.lower():
      return ResolvedLink(kind="convention", path=convention_file)

  // Step 3: Convention alias match (case-insensitive)
  for each convention_file in conventions_dir:
    for alias in convention.frontmatter.aliases:
      if alias.lower() == text.lower():
        return ResolvedLink(kind="convention", path=convention_file)

  // Step 4: Concept exact title match (case-insensitive)
  for each concept_file in concepts_dir:
    if concept.frontmatter.title.lower() == text.lower():
      return ResolvedLink(kind="concept", path=concept_file)

  // Step 5: Concept alias match (case-insensitive)
  for each concept_file in concepts_dir:
    for alias in concept.frontmatter.aliases:
      if alias.lower() == text.lower():
        return ResolvedLink(kind="alias", path=concept_file)

  // Step 6: Fuzzy match across all names
  all_names = convention_titles + convention_aliases + concept_titles + concept_aliases
  suggestions = fuzzy_match(text, all_names, cutoff=0.6, max=3)
  return UnresolvedLink(suggestions=suggestions)
```

#### Algorithm 2: Unified Search Routing

Current implementation: `src/lexibrary/search.py`, function `unified_search()`

```
function unified_search(project_root, query, tag, tags, scope, artifact_type, ...):
  all_tags = merge(tag, tags)  // Single tag + list merged
  link_graph = open_index(project_root)  // Returns LinkGraph | None

  // Path 1: Index-accelerated tag search
  if link_graph AND all_tags is not empty:
    results = link_graph.search_by_tag(first_tag)
    if multiple tags: intersect results across all tags
    apply filters (artifact_type, status, scope, deprecated, stale)
    return grouped results

  // Path 2: FTS-accelerated free-text search
  if link_graph AND query is not empty AND no tags:
    results = link_graph.full_text_search(query)
    apply filters
    return grouped results

  // Path 3: Fallback file scanning (no link graph or mixed query)
  results = []
  scan .lexibrary/concepts/ for matching concept files
  scan .lexibrary/designs/ for matching design files
  scan .lexibrary/stack/ for matching Stack posts
  scan .lexibrary/conventions/ for matching convention files
  apply filters
  return grouped results
```

#### Algorithm 3: Link Graph Build Pipeline

Current implementation: `src/lexibrary/linkgraph/builder.py`, class `IndexBuilder`

```
function full_build(project_root):
  ensure_schema(db)  // Create/migrate 8 tables + FTS5

  // Phase 1: Register all artifacts
  scan .lexibrary/designs/ → register as kind="design"
  scan .lexibrary/concepts/ → register as kind="concept"
  scan .lexibrary/conventions/ → register as kind="convention"
  scan .lexibrary/stack/ → register as kind="stack"
  scan scope_root/ → register as kind="source"

  // Phase 2: Extract and store links
  for each source artifact:
    extract AST imports → insert as ast_import edges
  for each design file:
    extract wikilinks → insert as wikilink edges
    extract stack_refs → insert as design_stack_ref edges
    link to source file → insert as design_source edge
  for each concept:
    extract linked_files → insert as concept_file_ref edges
  for each convention:
    extract concept refs → insert as convention_concept_ref edges
  for each stack post:
    extract refs.files → insert as stack_file_ref edges
    extract refs.concepts → insert as stack_concept_ref edges

  // Phase 3: Build FTS index
  populate artifacts_fts from artifact titles + bodies

  // Phase 4: Store tags and aliases
  for each artifact with tags: insert into tags table
  for each concept/convention with aliases: insert into aliases table

  update meta table (built_at, artifact_count, link_count)
```

#### Algorithm 4: Validation Orchestration

Current implementation: `src/lexibrary/validator/__init__.py`, function `validate_library()`

```
function validate_library(project_root, checks, severity_filter):
  available_checks = AVAILABLE_CHECKS registry  // 13 named checks
  selected = checks if specified, else all available

  report = ValidationReport()
  for each check_name in selected:
    check_fn = registry[check_name]
    issues = check_fn(project_root, link_graph)
    for each issue:
      if issue.severity >= severity_filter:
        report.add(issue)

  return report  // Grouped by severity: error, warning, info
```

### Complexity and Value

- **Complexity:** Medium. Requires careful reading of each implementation to extract the algorithm
  without language-specific details.
- **Value:** High for wikilink resolution and search (agent-facing, frequently used). Medium for
  build pipeline and validation (maintenance-facing).
- **Estimated effort:** 1-1.5 hours for all 4 algorithms. Start with #1 and #2.

---

## Opportunity 5: Test Validation Matrix

### What It Solves

Lexibrary has ~169 test files but no document mapping "what specification property is being tested"
to "which test file verifies it." An agent looking at test failures has to reverse-engineer what
the test enforces. There's also no way to identify gaps — spec requirements without tests.

Symphony's Section 17 maps every spec requirement to testable assertions across three profiles:
Core Conformance, Extension Conformance, and Real Integration.

### How to Implement

**Create new file:** `plans/test-matrix.md`

**Structure:** A table mapping specification properties to test files, grouped by subsystem.

**Starting inventory** (the implementing agent should verify and expand this by reading test files):

```
## Artefact Models & Parsing

| Property | Test File(s) | Status |
|----------|-------------|--------|
| Design file frontmatter validates status enum | tests/test_artifacts/test_design_file_parser.py | |
| Design file round-trip: serialize(parse(x)) == x | tests/test_artifacts/test_design_file_roundtrip.py | |
| Concept frontmatter validates status enum | tests/test_artifacts/test_models.py | |
| Convention frontmatter validates scope, status, source | tests/test_artifacts/test_convention_models.py | |
| Stack post parser: missing sections default to empty | tests/test_stack/test_parser.py | |
| Stack post round-trip preserves all fields | tests/test_stack/test_serializer_roundtrip.py | |
| AIndex parser handles malformed input | tests/test_artifacts/test_aindex_parser.py | |
| Slug generation: collision suffix -2, -3, ... | tests/test_artifacts/test_slugs.py | |

## Wikilink & Search

| Property | Test File(s) | Status |
|----------|-------------|--------|
| Resolver: convention-first precedence | tests/test_wiki/test_resolver.py | |
| Resolver: case-insensitive matching | tests/test_wiki/test_resolver.py | |
| Resolver: fuzzy suggestions for unresolved | tests/test_wiki/test_resolver.py | |
| Unified search: FTS path when link graph available | tests/test_search.py | |
| Unified search: fallback to file scan | tests/test_search.py | |
| Link graph: FTS5 full-text search | tests/test_linkgraph/test_query.py | |
| Link graph: tag search | tests/test_linkgraph/test_query.py | |

## Stack Mutations

| Property | Test File(s) | Status |
|----------|-------------|--------|
| accept_finding transitions to "resolved" | tests/test_stack/test_mutations.py | |
| mark_duplicate sets duplicate_of field | tests/test_stack/test_mutations.py | |
| mark_stale requires status="resolved" | tests/test_stack/test_mutations.py | |
| Vote rate limiting (60s) | tests/test_stack/test_mutations.py | |

## Validation

| Property | Test File(s) | Status |
|----------|-------------|--------|
| Wikilink resolution check catches broken links | tests/test_validator/test_checks_error.py | |
| Hash freshness check detects stale designs | tests/test_validator/test_warning_checks.py | |
| Orphan concept detection | tests/test_validator/test_warning_checks.py | |
...
```

**Complete test file inventory** (169 files across these directories — the implementing agent
should use this as the starting point):
- `tests/test_artifacts/` — 10 files (models, parsers, serializers, roundtrips, slugs, writer)
- `tests/test_archivist/` — 6 files (change checker, deps, pipeline, safety, service, topology)
- `tests/test_ast_parser/` — 7 files (hash, JS/TS/Python parsers, models, registry, render)
- `tests/test_cli/` — 6 files (error messaging, format flag, lexi, lexictl, linkgraph, output)
- `tests/test_config/` — 3 files (defaults, loader, schema)
- `tests/test_conventions/` — 3 files (index, parser, serializer)
- `tests/test_crawler/` — 3 files (change detector, discovery, file reader)
- `tests/test_daemon/` — 6 files (debouncer, logging, scheduler, service, service rewrite, watcher)
- `tests/test_hooks/` — 2 files (post-commit, pre-commit)
- `tests/test_ignore/` — 1 file (matcher)
- `tests/test_indexer/` — 2 files (generator, orchestrator)
- `tests/test_init/` — 10 files (detection, rules/*, scaffolder, wizard)
- `tests/test_iwh/` — 9 files (cleanup, find_all, gitignore, model, parser, reader, roundtrip, serializer, writer)
- `tests/test_lifecycle/` — 10+ files (bootstrap, comments, concept/convention/design/stack deprecation, queue)
- `tests/test_linkgraph/` — 3 files (builder, health, query)
- `tests/test_llm/` — 3 files (languages, rate limiter, service)
- `tests/test_stack/` — 7 files (index, models, mutations, parser, serializer, roundtrip, template)
- `tests/test_validator/` — 16 files (body structure, checks error/info/warning, cross-artifact, fixes, frontmatter, infrastructure, lifecycle, lookup budget, orchestrator, orphaned*, parser hardening, report)
- `tests/test_wiki/` — 5 files (index, parser, resolver, serializer, template)
- Root: `test_errors.py`, `test_exceptions.py`, `test_search.py`

### Complexity and Value

- **Complexity:** Medium. Requires reading test files to understand what properties they verify.
  Can be done incrementally.
- **Value:** High. Reveals test gaps. Makes test failures meaningful. Helps agents understand
  what each test protects.
- **Estimated effort:** 1-2 hours for initial mapping. Can grow over time.

---

## Opportunity 6: Definition of Done Checklists

### What It Solves

Lexibrary plans describe *what to build next* but not *what constitutes a complete feature*. There's
no single "definition of done" for, say, "the wikilink system is complete" or "the Stack subsystem
is production-ready." This means agents (and humans) can't easily assess whether a feature is
finished or what remains.

Symphony's Section 18 provides flat, checkable checklists separated into Required, Recommended
Extensions, and Operational Validation.

### How to Implement

**Files to edit:** Each active plan in `plans/` gets a `## Definition of Done` section appended.

**Active plans that need this** (10 files):
1. `plans/lexibrary-overview.md` — Overall system completeness
2. `plans/v2-master-plan.md` — v2 migration completeness
3. `plans/lookup-upgrade.md` — `lexi lookup` feature completeness
4. `plans/search-upgrade.md` — `lexi search` feature completeness
5. `plans/convention-v2-plan.md` — Convention system completeness
6. `plans/replace-explore.md` — Explore → lookup migration completeness
7. `plans/navigation-protocol-review.md` — Navigation protocol completeness
8. `plans/navigation-by-intent.md` — Intent-based navigation completeness
9. `plans/claude-harnessing-update-plan.md` — Claude integration completeness
10. `plans/BACKLOG.md` — (no DoD needed — this is a backlog)

**Template for each:**
```
## Definition of Done

### Core (required for feature completeness)
- [ ] [Specific, testable requirement]
- [ ] [Specific, testable requirement]
...

### Extension (recommended but not blocking)
- [ ] [Optional enhancement]
...

### Validation
- [ ] All related tests pass: `uv run pytest tests/test_<module>/`
- [ ] `uv run ruff check src/ tests/` passes
- [ ] `uv run mypy src/` passes
- [ ] `lexi validate` shows no new errors
```

**Example for lookup-upgrade.md:**
```
## Definition of Done

### Core
- [ ] `lexi lookup <file>` returns LookupResult dataclass (not CLI scraping)
- [ ] Core logic lives in src/lexibrary/lookup.py (not CLI glue)
- [ ] --format json outputs valid JSON
- [ ] --full includes all linked issues and dependency lists
- [ ] MCP server can call lookup without CLI subprocess

### Extension
- [ ] Pre-edit hook emits correct hookSpecificOutput format
- [ ] Hook output includes design file content for context

### Validation
- [ ] Tests in tests/test_lookup/ cover all output formats
- [ ] lexi validate shows no new errors after changes
```

### Complexity and Value

- **Complexity:** Low per plan. Requires reading each plan to understand the feature scope.
- **Value:** High. Makes completion criteria testable. Prevents "is this done?" ambiguity.
- **Estimated effort:** 15-20 minutes per plan. ~2.5 hours total for all 9.

---

## Opportunity 7: Failure Model Documentation

### What It Solves

Lexibrary has `ErrorSummary` (src/lexibrary/errors.py) for error aggregation, an exception
hierarchy (src/lexibrary/exceptions.py), and validator severity levels. But there's no unified
document that tells an agent: "when X fails, here's what happens and what you should do."

Symphony dedicates Section 14 entirely to failure classification with 5 failure categories, explicit
recovery behaviour for each, partial state recovery rules, and operator intervention points.

### How to Implement

**Where to add:** New section `## Failure Model` in `plans/lexibrary-overview.md`, after the
existing `## 9. CLI Design` section (since CLI is where errors surface to users/agents).

**Content based on the actual codebase:**

```
## Failure Model

### Exception Hierarchy
All Lexibrary exceptions inherit from LexibraryError (src/lexibrary/exceptions.py):

LexibraryError
├── LexibraryNotFoundError — .lexibrary/ directory not found
├── ConfigError            — Invalid config.yaml or missing required fields
├── IndexingError          — Crawl or indexing pipeline failures
├── LLMServiceError        — LLM API unreachable, rate limited, or bad response
├── ParseError             — Malformed YAML frontmatter, broken artefact syntax
└── LinkGraphError         — SQLite link graph build or query failures

### Failure Classes and Recovery

1. Config/Setup Failures
   Trigger: Missing .lexibrary/, invalid config.yaml, unsupported field values
   Exception: LexibraryNotFoundError, ConfigError
   Recovery: CLI exits with guidance message. Agent should run `lexictl init`.
   Scope: Blocks all operations.

2. Parse Failures
   Trigger: Malformed artefact YAML, broken markdown structure, corrupt files
   Exception: ParseError (raised by leaf functions)
   Recovery: Pipeline functions catch, record in ErrorSummary, continue processing
     other files. parse_*() convenience functions return None on failure.
   Scope: Affects single artefact. Other artefacts still processed.

3. Link Graph Failures
   Trigger: Corrupt SQLite DB, schema version mismatch, query errors
   Exception: LinkGraphError
   Recovery: Graceful degradation — search falls back to file scanning,
     lookup works without reverse deps, validation skips graph-dependent checks.
   Scope: Degrades performance, never blocks core operations.

4. LLM Failures
   Trigger: Provider unreachable, rate limit, malformed response
   Exception: LLMServiceError
   Recovery: Archivist pipeline skips the file, records error in ErrorSummary.
     RateLimiter (src/lexibrary/llm/rate_limiter.py) handles retry with backoff.
   Scope: Affects archivist/generation only. All non-LLM operations unaffected.

5. Validation Failures
   Trigger: Broken wikilinks, stale hashes, orphan artefacts, missing files
   NOT exceptions — these are ValidationIssue records with severity levels:
     error   → exit code 1 (wikilink_resolution, file_existence, concept_frontmatter)
     warning → exit code 0 (hash_freshness, token_budgets, orphan_concepts, deprecated_usage)
     info    → exit code 0 (forward_deps, stack_staleness, aindex_coverage, bidirectional_deps,
               dangling_links, orphan_artifacts)
   Recovery: `lexi validate` reports all issues. Agent should fix errors, consider warnings.

### Error Collection Pattern
Pipeline/orchestrator functions use ErrorSummary (src/lexibrary/errors.py) to aggregate errors
without stopping:
  1. Leaf functions raise specific LexibraryError subclasses
  2. Orchestrators catch, record via summary.add(phase, error, path), continue
  3. Final safety net: except Exception with logger.exception()
  4. CLI calls format_error_summary() before exit, sets exit code 1 if summary.has_errors()

ErrorRecord fields: timestamp, phase, path, error_type, message, traceback
ErrorSummary methods: add(), count, by_phase(), has_errors()
```

### Complexity and Value

- **Complexity:** Low-medium. The failure model is already implemented — this documents it.
- **Value:** High. Tells agents exactly what to expect and how to handle errors. Prevents
  defensive over-catching or panic on non-fatal errors.
- **Estimated effort:** 30-45 minutes.

---

## Opportunity 8: Config Cheat Sheet

### What It Solves

Lexibrary's config is defined in `src/lexibrary/config/schema.py` as nested Pydantic 2 models.
An agent wanting to know "what config fields exist and what are their defaults" must read 237 lines
of Python model definitions, understand Pydantic Field() syntax, and navigate nested sub-models.

Symphony's Section 6.4 provides an "intentionally redundant" flat listing of every config field
with type, default, and parent key. It's designed explicitly so "a coding agent can implement the
config layer quickly."

### How to Implement

**Where to add:** New section in `plans/lexibrary-overview.md` after the existing `## 8. Project
Setup & Agent Environment` section. Alternatively, create as a Lexibrary Stack post for easy
`lexi search config` discovery.

**Complete config field listing** (extracted from `src/lexibrary/config/schema.py`):

```
## Config Cheat Sheet

Config file: .lexibrary/config.yaml
Schema: src/lexibrary/config/schema.py (LexibraryConfig model, Pydantic 2)

### Top-Level Fields
| Field | Type | Default | Notes |
|-------|------|---------|-------|
| scope_root | str | "." | Root directory for indexing |
| project_name | str | "" | Human-readable project name |
| agent_environment | list[str] | [] | Agent envs: "claude", "cursor", "codex" |

### Crawl Settings (crawl.*)
| Field | Type | Default |
|-------|------|---------|
| crawl.max_file_size_kb | int | 512 |
| crawl.binary_extensions | list[str] | [.png, .jpg, ...34 extensions] |

### LLM Settings (llm.*)
| Field | Type | Default |
|-------|------|---------|
| llm.provider | str | "anthropic" |
| llm.model | str | "claude-sonnet-4-6" |
| llm.api_key_env | str | "ANTHROPIC_API_KEY" |
| llm.api_key_source | str | "env" |
| llm.max_retries | int | 3 |
| llm.timeout | int | 60 |

### Token Budget Settings (token_budgets.*)
| Field | Type | Default |
|-------|------|---------|
| token_budgets.design_file_tokens | int | 400 |
| token_budgets.design_file_abridged_tokens | int | 100 |
| token_budgets.aindex_tokens | int | 200 |
| token_budgets.concept_file_tokens | int | 400 |
| token_budgets.convention_file_tokens | int | 500 |
| token_budgets.orientation_tokens | int | 300 |
| token_budgets.lookup_total_tokens | int | 1200 |

### Ignore Settings (ignore.*)
| Field | Type | Default |
|-------|------|---------|
| ignore.use_gitignore | bool | true |
| ignore.additional_patterns | list[str] | [.lexibrary/, node_modules/, __pycache__/, ...] |

### Daemon Settings (daemon.*)
| Field | Type | Default |
|-------|------|---------|
| daemon.debounce_seconds | float | 2.0 |
| daemon.sweep_interval_seconds | int | 3600 |
| daemon.sweep_skip_if_unchanged | bool | true |
| daemon.git_suppression_seconds | int | 5 |
| daemon.watchdog_enabled | bool | false |
| daemon.log_level | str | "info" |

### AST Settings (ast.*)
| Field | Type | Default |
|-------|------|---------|
| ast.enabled | bool | true |
| ast.languages | list[str] | ["python", "typescript", "javascript"] |

### Convention Settings (conventions.*)
| Field | Type | Default |
|-------|------|---------|
| conventions.lookup_display_limit | int | 5 |
| conventions.deprecation_confirm | "human" | "maintainer" | "human" |

### Concept Settings (concepts.*)
| Field | Type | Default |
|-------|------|---------|
| concepts.deprecation_confirm | "human" | "maintainer" | "human" |

### IWH Settings (iwh.*)
| Field | Type | Default |
|-------|------|---------|
| iwh.enabled | bool | true |
| iwh.ttl_hours | int | 72 |

### Deprecation Settings (deprecation.*)
| Field | Type | Default |
|-------|------|---------|
| deprecation.ttl_commits | int | 50 |
| deprecation.comment_warning_threshold | int | 10 |

### Stack Settings (stack.*)
| Field | Type | Default |
|-------|------|---------|
| stack.staleness_confirm | "human" | "maintainer" | "human" |
| stack.staleness_ttl_commits | int | 200 |
| stack.staleness_ttl_short_commits | int | 100 |
| stack.lookup_display_limit | int | 3 |

### Mapping Settings (mapping.*)
| Field | Type | Default |
|-------|------|---------|
| mapping.strategies | list[dict] | [] |

### Convention Declarations (convention_declarations[])
| Field | Type | Default |
|-------|------|---------|
| convention_declarations[].body | str | (required) |
| convention_declarations[].scope | str | "project" |
| convention_declarations[].tags | list[str] | [] |
```

### Complexity and Value

- **Complexity:** Very low. The data is already extracted above — just format and insert.
- **Value:** High. Every agent that touches config benefits. Saves reading 237 lines of Python.
- **Estimated effort:** 20 minutes.

---

## Opportunity 9: Normalisation Rules as Explicit Contracts

### What It Solves

Identifier derivation, comparison semantics, and composition rules are scattered across multiple
source files. An agent building a new feature that creates slugs, resolves wikilinks, or generates
Stack post IDs has to discover these rules by reading implementation code. If they get it wrong
(e.g., using case-sensitive tag comparison when it should be insensitive, or forgetting collision
suffixes on slugs), they introduce subtle bugs.

Symphony's Section 4.2 defines all normalisation rules in one place as explicit contracts.

### How to Implement

**Where to add:** As a section in `plans/domain-model.md` (Opportunity 2) or as a standalone
section in `plans/lexibrary-overview.md`.

**Rules to document** (derived from actual code):

```
## Identifier and Normalisation Rules

### Concept & Convention Slugs
- Function: slugify() (in artifact serializers/writers)
- Algorithm: title → lowercase → replace spaces with hyphens → strip non-alphanumeric
  except hyphens and underscores
- Collision handling: append suffix -2, -3, ... if slug already exists on disk
- Examples: "Config Schema" → config-schema.md, "SHA-256 Hashing" → sha256-hashing.md

### Stack Post IDs
- Format: ST-<NNN> (e.g., ST-001, ST-042)
- Zero-padded to 3 digits, monotonically increasing
- File naming: ST-<NNN>-<slug>.md (e.g., ST-001-design-files-not-updating.md)
- ID is authoritative (in frontmatter `id` field), filename is for human readability

### Design File Paths
- Mirror source tree under .lexibrary/designs/
- Example: src/lexibrary/cli.py → .lexibrary/designs/src/lexibrary/cli.py.md
- Append .md to the source filename (not replace extension)

### Wikilink Resolution
- Case-insensitive title/alias matching (via .lower() comparison)
- Convention-first precedence: conventions checked before concepts
- Fuzzy matching: difflib.get_close_matches(cutoff=0.6, n=3) for suggestions
- Stack post shorthand: [[ST-001]] resolves via regex pattern match

### Tag Comparison
- Tags are stored and compared as-is (case-sensitive in link graph tags table)
- Shared global namespace across all artefact types
- No normalisation applied — "auth" ≠ "Auth"

### Issue State Comparison (Stack Posts)
- Status values are Literal types: exact string match
- "open", "resolved", "outdated", "duplicate", "stale" — always lowercase

### Workspace Key (IWH paths)
- IWH files mirror directory structure: src/auth/ → .lexibrary/src/auth/.iwh
- Directory paths used as-is (no sanitisation beyond pathlib normalisation)
```

### Complexity and Value

- **Complexity:** Low. Pure documentation of existing rules.
- **Value:** Medium-high. Prevents subtle identifier bugs in new features. Most useful when
  combined with Opportunity 2 (domain model).
- **Estimated effort:** 20-30 minutes.

---

## Opportunity 10: Core vs Extension Conformance Levels

### What It Solves

Some Lexibrary features require external dependencies (LLM provider, tiktoken) while others work
with zero infrastructure. But this distinction is implicit — there's no formal declaration of what's
core vs optional. An agent setting up Lexibrary for a new project doesn't know which features will
work out of the box.

Symphony uses consistent terminology: "required," "optional"/"extension," and
"implementation-defined" — with separate conformance levels in the test matrix and implementation
checklist.

### How to Implement

**Where to add:** New section in `plans/lexibrary-overview.md`, ideally near the beginning after
Goals/Non-Goals (if added from Opportunity 1).

**Content:**

```
## Capability Tiers

### Core (always available, no external dependencies)
These features work immediately after `lexictl init` with no API keys or additional setup:
- Artefact models, parsers, serializers (design files, concepts, conventions, Stack posts, AIndex)
- Link graph (local SQLite, built by `lexictl update`)
- Validation checks (`lexi validate` — all 13 checks)
- Agent-facing CLI (`lexi lookup`, `lexi search`, `lexi concepts`, `lexi stack`, etc.)
- IWH inter-agent signals
- Convention lifecycle (including deprecation with TTL-based hard deletion)
- Cross-artefact search (FTS via link graph + file-scan fallback)
- Wikilink resolution
- SHA-256 change detection
- Structural .aindex generation (`lexi index`)

### Extension (requires additional setup)
These features require API keys, optional dependencies, or external tools:
- Archivist pipeline (requires LLM provider — config: llm.provider, llm.api_key_env)
  - Design file generation, TOPOLOGY.md generation, START_HERE.md generation
- Token counting with tiktoken backend (requires tiktoken package)
- Token counting with Anthropic backend (requires anthropic package)
  - Note: approximate backend (character-ratio) is always available as fallback
- Agent rule generation (per-environment: Claude, Cursor, Codex)
  - Generates CLAUDE.md, .cursor/rules/, AGENTS.md etc.
  - Requires knowing agent_environment (auto-detected or configured)

### Maintenance-Only (lexictl, not for agents)
These are admin/maintenance operations, prohibited for agent use:
- `lexictl init` — project setup
- `lexictl update` — regenerate artefacts
- `lexictl setup` — install hooks, configure agent rules
- `lexictl sweep` / `lexictl daemon` — background processing
```

### Complexity and Value

- **Complexity:** Very low. Documentation only.
- **Value:** Medium. Helps agents and users understand what works out of the box. Useful for
  the init wizard and for documentation.
- **Estimated effort:** 15-20 minutes.

---

## Implementation Priority

Ranked by impact-to-effort ratio (do these first):

| Priority | Opportunity | Effort | Value | Dependencies |
|----------|------------|--------|-------|-------------|
| 1 | **#1 Goals & Non-Goals** | 15-30 min | Very High | None |
| 2 | **#8 Config Cheat Sheet** | 20 min | High | None |
| 3 | **#10 Core vs Extension** | 15-20 min | Medium | None |
| 4 | **#7 Failure Model** | 30-45 min | High | None |
| 5 | **#3 State Machines** | 30-45 min | High | None |
| 6 | **#9 Normalisation Rules** | 20-30 min | Medium-High | Ideally after #2 |
| 7 | **#2 Domain Model** | 1-2 hours | Very High | Subsumes #3, #9 |
| 8 | **#6 Definition of Done** | 2.5 hours | High | Requires reading each plan |
| 9 | **#4 Pseudocode Algorithms** | 1-1.5 hours | Medium-High | None |
| 10 | **#5 Test Matrix** | 1-2 hours | High | None |

**Recommended grouping:**
- **Quick wins (Opportunities 1, 8, 10):** Can all be done in a single session as additions to
  `plans/lexibrary-overview.md`. ~1 hour total.
- **Foundational doc (Opportunity 2):** Do this next. It becomes the home for #3, #9, and #4.
- **Per-plan work (Opportunity 6):** Do incrementally, one plan at a time.
- **Reference work (Opportunities 4, 5):** Do when ready to invest in long-term documentation.
