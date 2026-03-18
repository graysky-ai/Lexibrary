# The Curator Agent

> Deterministic coordinator that dispatches specialised sub-agents to maintain
> Lexibrary knowledge-layer health. Hybrid trigger: scheduled, reactive, on-demand.

---

## 1. Core Mission

The Curator keeps the Lexibrary knowledge layer **accurate, coherent, and lean**.
It does not generate new knowledge — it audits, reconciles, and retires existing
artifacts so that working agents always operate against a trustworthy index.

---

## 2. Use Cases

### 2.1 Comment & Description Curation

- **Design file drift**: Detect when `source_hash` mismatches indicate a design
  file is stale, then regenerate or flag the affected sections.
- **Summary quality**: Audit `description` fields in design frontmatter for
  clarity, accuracy, and consistency with actual source behaviour.
- **Dead commentary**: Identify TODO/FIXME/HACK comments in source that reference
  completed work or no-longer-relevant issues.

### 2.2 Deprecation Proxy (Human-in-the-Loop)

- **Concept lifecycle**: Move concepts through `draft → active → deprecated`,
  setting `superseded_by` pointers.
- **Orphan detection**: Surface concepts, conventions, and design files with zero
  inbound links in the link graph.
- **Cascade analysis**: Before deprecating, trace dependents via `reverse_deps()`
  to quantify downstream impact and generate a migration brief.

#### Artifact State Machines

The Deprecation Analyst must enforce valid state transitions. Each artifact type
has a distinct lifecycle. Full definitions with transition triggers and
idempotency rules are in
[spec-opportunities.md §Opportunity 3](spec-opportunities.md#opportunity-3-explicit-state-machine-documentation).
Summary:

**Design Files**: `active → deprecated` (source deleted/renamed/manual) or
`active → unlinked` (source outside scope). `unlinked → active` on re-addition.
Deprecated is terminal.

**Concepts**: `draft → active → deprecated`. Deprecated is terminal; sets
`superseded_by` and `deprecated_at`. Confirm policy:
`config.concepts.deprecation_confirm`.

**Conventions**: `draft → active → deprecated → HARD DELETED` (after
`config.deprecation.ttl_commits`, default 50). Hard deletion removes `.md` and
sibling `.comments.yaml`. Confirm policy:
`config.conventions.deprecation_confirm`.

**Stack Posts**: `open → resolved` (via `accept_finding`), `open → duplicate`,
`open → outdated`, `resolved → stale` (after TTL), `stale → resolved`
(unstale). `mark_stale()` requires status="resolved".

### 2.3 Validation Sweep

- Run the full `lexi validate` check suite (13 checks across error/warning/info).
- Triage results by severity, grouping related issues into actionable work items.
- Auto-fix trivially correctable issues (e.g. missing bidirectional dep entries).
- Leverage actionable validator suggestions to self-correct — see
  [harness-opportunities.md §1](harness-opportunities.md#1-actionable-validator-remediation)
  for the plan to upgrade suggestion text to include runnable commands.

### 2.4 Staleness Management

- **Hash freshness**: Lexibrary uses two-tier hashing — a **content hash**
  (SHA-256 of the full source file, stored as `source_hash` in design file
  frontmatter) and an **interface hash** (Tree-sitter AST skeleton rendering,
  stored as `interface_hash` in `.aindex` YAML). The Curator should use both:
  a content-hash mismatch with a stable interface hash indicates an
  implementation-only change (lower impact), while an interface-hash mismatch
  signals a public API change (higher impact, more dependents affected).
  Rank staleness by age, hash tier, and downstream impact.
- **Stack post decay**: Flag stack posts whose referenced code has changed
  substantially since posting.
- **IWH signal cleanup**: Consume stale `incomplete`/`blocked` IWH signals that
  have been superseded by subsequent work.

### 2.5 Token Budget Enforcement

- Monitor `START_HERE.md`, `HANDOFF.md`, and high-traffic design files against
  token budgets defined in validation checks.
- Propose condensation edits when files exceed budgets.

### 2.6 Cross-Artifact Consistency

- Verify wikilinks resolve bidirectionally.
- Ensure convention scoping is consistent (directory-level conventions apply to
  all children).
- Detect conflicting conventions across overlapping scopes.
- Enforce identifier normalisation rules — case-sensitive tags, case-insensitive
  wikilink resolution, convention-first precedence, slug collision suffixes. The
  Consistency Checker must understand these semantics to avoid introducing bugs.
  Full normalisation rules are documented in
  [spec-opportunities.md §Opportunity 9](spec-opportunities.md#opportunity-9-normalisation-rules-as-explicit-contracts).

### 2.7 Index Health (Speculative)

- **aindex coverage**: Identify source files missing from `.aindex` output.
- **Link graph integrity**: Verify SQLite index is consistent with on-disk
  artifacts.
- **Alias collisions**: Detect duplicate or ambiguous aliases in the link graph.

### 2.8 Migration Assistance (Speculative)

- When a concept is deprecated with `superseded_by`, scan all referencing
  artifacts and generate a batch migration plan (or execute it, depending on
  autonomy level).

### 2.9 IWH Signal Triage

- React to `blocked` IWH signals — escalate to human or create a Stack post
  if the blocker persists across multiple agent sessions.
- Detect `incomplete` signals that have been superseded by subsequent commits
  touching the same directory, and consume them.
- Surface signals older than `config.iwh.ttl_hours` for cleanup.

### 2.10 Convention-from-Failure Detection (Speculative)

When the Curator observes recurring validation failures of the same type across
multiple files (e.g. repeated `wikilink_resolution` errors for the same missing
concept), it can propose a new convention or concept to prevent the pattern.
See [harness-opportunities.md §2](harness-opportunities.md#2-convention-from-failure-workflow)
for the detailed workflow design.

### 2.11 Agent-Edited Design File Reconciliation

When an agent edits a design file (setting `updated_by: agent`), the current
`lexictl update` pipeline classifies it as `AGENT_UPDATED` and **never
regenerates it** — even if the underlying source file changes substantially.
This is a safety measure (never destroy agent work), but it creates a drift
problem: agent-edited design files can go permanently stale.

The Curator is the right owner for reconciling these files because the action
requires judgment — not just hash comparison but understanding what the agent
added vs what the source now says.

**Detection** (deterministic, coordinator-level):

- Compare `source_hash` in the design file footer against the current source
  SHA-256. If they differ AND `design_hash` also differs from the computed
  design content hash, the file is agent-edited and stale.
- Optionally compare `source_path.stat().st_mtime` against the `generated`
  timestamp in the footer to gauge how stale.
- Rank by staleness age and downstream impact (number of reverse dependents
  in the link graph).

**Resolution** (LLM sub-agent, requires hybrid regeneration — see Q8):

- Send the current source, the agent-edited design file, and a diff of what
  changed in the source since the design was last generated.
- The sub-agent produces an updated design file that preserves agent-added
  insights (custom notes, refined descriptions, added wikilinks) while
  updating mechanical sections (interface skeleton, dependency list, summary
  accuracy).
- The result is written with `updated_by: curator` (new value) and a fresh
  `design_hash` + `source_hash` in the footer.

**Open decisions** — see Q8 for the full list of what needs to be resolved
before implementation.

---

## 3. Architecture

### 3.1 Coordinator (Deterministic)

The coordinator is a **non-LLM routine** — a Python function (or shell script)
that orchestrates sub-agents in a fixed sequence:

```
1. Collect  →  gather signals (validate output, hash checks, IWH scan)
2. Triage   →  classify issues by type and severity
3. Dispatch →  assign issues to the appropriate sub-agent
4. Report   →  aggregate sub-agent results into a summary
```

The coordinator does NOT make judgment calls. It routes based on issue type.

**Graceful degradation**: The coordinator must handle an unavailable link
graph (`LinkGraph.open()` returns `None`). This happens when the database file
is missing, the database is corrupt, or the schema version mismatches the
expected version. When the graph is unavailable:

- Skip checks that require it (orphan detection, bidirectional deps, alias
  collisions, dependent fan-out).
- Fall back to file-scanning for staleness detection (walk `.lexibrary/designs/`
  and compare `source_hash` against on-disk files).
- Log a warning recommending `lexictl update` to rebuild the index.

### 3.2 Sub-Agents

| Sub-Agent | Responsibility | Model Tier |
|-----------|---------------|------------|
| **Staleness Resolver** | Regenerate stale design files from source; reconcile agent-edited designs via hybrid merge (2.11) | Heavy (Opus) |
| **Deprecation Analyst** | Assess impact, draft migration briefs, execute deprecations | Heavy (Opus) |
| **Comment Curator** | Audit and clean descriptions, TODOs, summaries | Light (Haiku/Sonnet) |
| **Consistency Checker** | Fix wikilinks, bidirectional deps, alias conflicts | Light (Haiku) |
| **Budget Trimmer** | Condense files exceeding token budgets | Medium (Sonnet) |

Sub-agents receive a focused work item (not the full triage), do their task, and
return a structured result.

**Existing agent patterns to follow**: The Explore agent (Haiku, read-only,
structured output) and Bead agent (Opus, claim-work-close lifecycle) in
`.claude/agents/` are the two established sub-agent patterns. Curator sub-agents
should follow similar conventions — lightweight agents use Haiku with Read/Bash
tools; heavyweight agents use Opus with full tool access and structured reports.

### 3.3 Trigger Modes

#### Scheduled (Periodic)

- Full health sweep: daily or weekly (configurable).
- Lightweight hash-freshness check: after every N commits or on a short interval.
- Implementation: cron job or `lexictl sweep --watch` integration.

#### Reactive (Event-Driven)

- **Post-agent hook**: After a bead-agent closes a bead, the Curator runs a
  scoped check on affected files.
- **Post-edit hook**: After any agent edits a source file, check if the
  corresponding design file needs updating.
- **Validation failure**: If `lexi validate` surfaces errors during normal agent
  work, dispatch the relevant sub-agent.

#### On-Demand

- `/curator` skill — user invokes directly.
- `lexi curate [--scope <path>] [--check <check-name>]` CLI command.
- Can be scoped to a directory, a specific check, or a full sweep.

### 3.4 Python APIs (Coordinator-Level)

The coordinator should call Python APIs directly rather than scraping CLI output.
Key entry points:

| API | Module | Purpose |
|-----|--------|---------|
| `LinkGraph.open(db_path)` | `linkgraph.query` | Read-only graph queries; returns `None` if unavailable |
| `open_index(project_root)` | `linkgraph.query` | Convenience wrapper — finds db, opens graph |
| `get_artifact(path)` | `linkgraph.query` | Look up single artifact by path |
| `reverse_deps(path, link_type)` | `linkgraph.query` | Inbound links to an artifact |
| `resolve_alias(alias)` | `linkgraph.query` | Case-insensitive concept/convention lookup |
| `search_by_tag(tag)` | `linkgraph.query` | Find artifacts by tag (exact match) |
| `full_text_search(query, limit=20)` | `linkgraph.query` | FTS5 full-text search across artifacts |
| `get_conventions(directory_paths)` | `linkgraph.query` | Conventions scoped to directories; root-to-leaf ordering |
| `traverse(start_path, max_depth=3)` | `linkgraph.query` | Multi-hop graph traversal with cycle detection (max 10 depth) |
| `build_summary()` | `linkgraph.query` | Aggregate build statistics from most recent index build |
| `find_all_iwh(project_root)` | `iwh.reader` | Discover all IWH signals; returns `list[(dir, IWHFile)]` |
| `validate_library(root, checks, severity)` | `validator` | Run validation; returns `ValidationReport` |
| `parse_design_file(path)` | `artifacts.design_file_parser` | Full design file parse |
| `parse_design_file_frontmatter(path)` | `artifacts.design_file_parser` | Lightweight frontmatter-only parse |
| `WikilinkResolver` | `wiki.resolver` | Resolves `[[wikilinks]]` to concepts or Stack posts |
| `ConceptIndex` | `wiki.index` | Search concepts by title, alias, tag, or substring |

#### Key Data Models

The coordinator's triage step consumes these types from the validation and
link graph systems:

**Validation models** (`validator.report`):
- `ValidationReport` — top-level container for a validation run
- `ValidationIssue` — single issue: `path`, `severity`, `message`, `suggestions`
- `ValidationSummary` — aggregate counts by severity

**Link graph result types** (`linkgraph.query`):
- `ArtifactResult` — lookup result: `id`, `path`, `kind`, `title`, `status`
- `LinkResult` — inbound edge: `source_path`, `link_type`, `context`
- `ConventionResult` — convention body scoped to a directory
- `TraversalNode` — node in multi-hop graph traversal
- `BuildSummaryEntry` — build statistics entry

**Link types** stored in the graph (used to filter `reverse_deps` and
`traverse` calls):
- `ast_import` — source code import relationship
- `wikilink` — `[[Concept]]` cross-reference
- `concept_file_ref` — concept referencing a file
- `stack_file_ref` — Stack post referencing a file
- `convention` — scoped coding standard

The `lexi curate` CLI command is a thin wrapper over these APIs — same pattern
as `search.py` providing `SearchResults` that the CLI renders.

---

## 4. Autonomy Configuration

Configurable in `.lexibrary/config.yaml` (not in the setup wizard).
Defaults to **full autonomy**.

```yaml
# Curator autonomy level
# Controls how much the Curator can do without human approval.
#
# Options:
#   full       - (default) Curator executes all maintenance actions automatically.
#                Actions are logged for review but not gated on approval.
#                Best for: mature projects with stable conventions.
#
#   auto_low   - Curator auto-executes low-risk actions (fixing broken links,
#                updating stale hashes, cleaning orphans with zero dependents).
#                High-impact actions (deprecation, migration, budget trimming)
#                are proposed as IWH signals or PR comments for human review.
#                Best for: projects in active development with frequent changes.
#
#   propose    - Curator never modifies artifacts directly. All findings are
#                written as proposals (IWH signals, issues, or reports) for
#                human review and approval.
#                Best for: regulated environments or early adoption.
curator:
  autonomy: full
```

---

## 5. Open Questions

### Q1: Coordinator Implementation — Python or Shell?

The coordinator needs to: parse `lexi validate` JSON output, manage sub-agent
dispatch, and aggregate results. Python is the natural fit (already the project
language), but a shell script keeps it outside the package dependency graph.

**Recommendation**: Python module at `src/lexibrary/curator/coordinator.py`,
invoked via `lexi curate` CLI command. This keeps it testable and allows it to
use existing internal APIs (link graph, validation) directly.

### Q2: Sub-Agent Invocation Mechanism

How do sub-agents run?

- **Option A**: Claude Code Agent tool calls — coordinator is itself an LLM agent
  that spawns sub-agents. Simple but makes the coordinator non-deterministic.
- **Option B**: Python subprocess calls to `claude` CLI with structured prompts.
  Coordinator stays deterministic; sub-agents are LLM-powered.
- **Option C**: Bead system — coordinator creates ephemeral beads for each work
  item, sub-agents claim and close them.

**Recommendation**: Option B for simplicity. Option C if we want progress
tracking and retry semantics from the bead system.

### Q3: Report Format and Destination

Where do Curator reports go?

- **IWH signals**: Scoped to directories, ephemeral — good for "next agent" communication.
- **Stack posts**: Persistent, searchable — good for recurring issues.
- **Dedicated report file**: e.g. `.lexibrary/curator/last-run.md` — simple but
  not integrated with existing discovery tools.
- **Console output**: For on-demand runs.

**Recommendation**: Console for on-demand, `.lexibrary/curator/reports/` for
scheduled runs (with a `last-run.md` symlink), and IWH signals for reactive runs
scoped to specific directories.

### Q4: Conflict with Working Agents

If the Curator runs reactively while another agent is mid-task, edits could
conflict. Options:

- **Lockfile**: Curator acquires a lock before modifying artifacts.
- **Queue**: Curator queues actions and executes during idle periods.
- **Scope isolation**: Curator only touches files not currently being edited
  (check git status / IWH signals).

**Recommendation**: Scope isolation — skip files with open IWH signals or
uncommitted changes. Queue deferred work items for the next idle window.

### Q5: How Does the Curator Know What "Low-Risk" Means?

For `auto_low` autonomy, we need a clear, codified definition of low-risk vs
high-risk actions:

| Action | Risk Level | Rationale |
|--------|-----------|-----------|
| Fix broken wikilink | Low | Mechanical, verifiable |
| Update stale hash | Low | No content change |
| Remove orphan with 0 dependents | Low | Nothing references it |
| Deprecate concept with dependents | High | Requires migration |
| Condense file to meet token budget | High | Lossy transformation |
| Regenerate design file section | Medium | LLM output, may drift |
| Reconcile agent-edited design (small source change) | Low | Interface stable, mechanical refresh |
| Reconcile agent-edited design (large source change) | Medium | LLM must judge which agent notes still apply |
| Reconcile agent-edited design (extensive agent content) | High | Lossy merge possible, agent insights at risk |

This taxonomy should live in config or as a constant in the coordinator module.

### Q6: Relationship to `lexictl`

`lexictl` is the existing maintenance CLI (admin-only, agents prohibited from
using it). Should the Curator:

- **Wrap `lexictl`** commands internally (since it's a maintenance agent, not a
  working agent)?
- **Duplicate functionality** in `lexi curate` to stay within the agent-facing
  CLI?
- **Share a library layer** — extract common maintenance logic into a shared
  module that both `lexictl` and `lexi curate` import?

**Recommendation**: Shared library layer. The `lexi` vs `lexictl` split is an
access control boundary, not a code boundary. Both should import from
`src/lexibrary/maintenance/`.

### Q7: Testing Strategy

How do we test the Curator without running real LLM sub-agents?

- Mock sub-agent responses at the subprocess boundary.
- Use snapshot testing for coordinator dispatch logic.
- Integration tests with a fixture `.lexibrary/` directory containing known
  issues (stale hashes, broken links, orphans).

### Q8: Agent-Edited Design File Reconciliation Strategy

Agent-edited design files currently become permanently exempt from LLM
regeneration (the `AGENT_UPDATED` classification in `change_checker.py`).
When the source changes after the agent edit, these files drift silently.
The Curator needs a reconciliation strategy. Several things need deciding:

#### Q8.1: Where does detection happen?

- **Option A — `lexictl update` flags, Curator resolves later.** `lexictl update`
  already classifies `AGENT_UPDATED` files. It could emit a structured signal
  (e.g. a file in `.lexibrary/curator/pending/`, or a new validation warning)
  that the Curator picks up on its next run. Pros: no change to the update
  pipeline's behaviour. Cons: stale files sit unresolved between Curator runs.

- **Option B — `lexi validate` flags, Curator resolves later.** Add a new
  validation check (`stale_agent_design`) that fires when `source_hash`
  mismatches AND the design file was agent-edited. The Curator consumes this
  alongside other validation results. Pros: consistent with how the Curator
  already triages. Cons: same delay issue.

- **Option C — Curator runs inline during `lexictl update`.** When the update
  pipeline hits an `AGENT_UPDATED` file with a stale `source_hash`, it hands
  the file off to the Curator's reconciliation sub-agent right then. Pros:
  no drift window. Cons: couples `lexictl update` to the Curator; update
  becomes slower and requires LLM calls even for agent-edited files.

**Leaning toward**: Option B for the initial implementation (flag via
validation, Curator resolves on next sweep), with Option A as an additional
signal if we want faster turnaround. Option C only if the drift window proves
unacceptable in practice.

#### Q8.2: How does hybrid regeneration work?

The sub-agent needs to merge two inputs: the agent's version (which may
contain custom notes, refined descriptions, extra wikilinks) and the current
source reality (which may have new functions, changed signatures, removed
dependencies). This is the hardest part.

**What we know:**

- The sub-agent receives: (1) current source file content, (2) the
  agent-edited design file, (3) the source diff since the design was last
  generated (reconstructible from git or from the stored `source_hash`).
- The sub-agent must distinguish **mechanical sections** from **agent-added
  value**. Design files have a known section structure:
  - **Mechanical** (regenerable from source): Summary, Interface (table of
    public functions/classes with signatures), Dependencies (Lexibrary-internal
    imports), Dependents (which modules import this one)
  - **Agent-added value** (must be preserved): Key Concepts (wikilink
    cross-references the agent added), Dragons (real gotchas), custom notes,
    refined descriptions beyond what the archivist would generate
- The output should read as a coherent design file, not a merge-conflict
  patchwork.

**What we need to decide:**

- **Prompt design**: Do we give the LLM explicit section-by-section merge
  instructions, or a high-level "reconcile these two views" directive? The
  former is more predictable; the latter handles unexpected agent additions
  better.
- **Diff or full source?** Sending the full source is simpler but costs more
  tokens. Sending only the diff is cheaper but requires the LLM to mentally
  apply the diff to understand the current state.
- **Confidence threshold**: Should the sub-agent be allowed to drop agent
  content it judges as now-incorrect? Or should it always preserve agent
  additions and only flag potential conflicts? This ties into autonomy level.
- **BAML prompt**: This needs a new BAML function
  (`CuratorReconcileDesignFile` or similar), distinct from the archivist's
  `ArchivistGenerateDesignFile`. The prompt structure, examples, and output
  schema need design work.
- **Fallback**: If the sub-agent can't confidently reconcile (e.g. source
  changed too drastically), what happens? Options: flag for human review,
  regenerate from scratch with a note about what was lost, or leave the
  stale version and escalate.

#### Q8.3: What is `updated_by: curator`?

Currently `updated_by` has two values: `archivist` (LLM-generated) and
`agent` (manually edited). Adding `curator` as a third value lets the change
checker distinguish Curator reconciliation output from both fresh LLM
generation and agent edits.

**Implications:**

- Should `curator`-authored files be treated like `archivist` files (eligible
  for full regeneration on next source change)? Or like `agent` files
  (protected from overwrite)?
- **Leaning toward**: treat as `archivist` — once the Curator has reconciled,
  the file re-enters the normal update cycle. If an agent later edits it
  again, it becomes `agent` again and the cycle repeats.

#### Q8.4: Risk classification

For the autonomy system (Q5), where does reconciliation sit?

- If the source change is small (e.g. only internal implementation changed,
  interface stable — detectable via `interface_hash` being unchanged even
  though `source_hash` differs): **Low risk** — mechanical update, interface
  skeleton refresh.
- If the source change is large (e.g. new public API, renamed functions,
  removed exports — `interface_hash` has changed): **Medium risk** — LLM
  must reason about what agent notes still apply.
- If the agent additions are extensive (substantial custom content beyond
  what the archivist would generate): **High risk** — lossy merge possible.

This maps to the autonomy config: `full` does all of them, `auto_low` does
only the low-risk cases, `propose` flags everything for review.

---

## 6. Interaction with Existing Systems

| System | Curator Interaction |
|--------|-------------------|
| **Validation** (`lexi validate`) | Primary signal source. Curator consumes JSON output. |
| **Link Graph** (SQLite) | Query for dependents, orphans, aliases. Read-only. |
| **IWH Signals** | Reads to detect stale/blocked work. Writes for reactive reports. |
| **Stack Posts** | Reads to avoid duplicate issues. Writes for recurring problems. |
| **Bead System** | Could create ephemeral beads for tracked maintenance work. |
| **Design Files** | Primary write target for staleness resolution. |
| **Concepts/Conventions** | Lifecycle management (deprecation, migration). |
| **Sweep** (`lexictl sweep --watch`) | Potential trigger source for reactive mode. |

---

## 7. Implementation Phases (Sketch)

### Phase 0: Foundation

- Define `CuratorConfig` Pydantic model (autonomy level, schedule, scopes).
- Add `curator:` section to config schema.
- Implement coordinator skeleton with collect → triage → dispatch → report.

### Phase 1: Validation Sweep + Staleness

- Wire coordinator to `lexi validate --json`.
- Implement Staleness Resolver sub-agent (including agent-edited design file
  reconciliation via hybrid regeneration — see Q8).
- Add `stale_agent_design` validation check to detect agent-edited files
  with outdated `source_hash`.
- Design and implement `CuratorReconcileDesignFile` BAML prompt.
- Implement Consistency Checker sub-agent.
- `lexi curate` CLI command (on-demand).

### Phase 2: Deprecation Workflow

- Implement Deprecation Analyst sub-agent.
- Cascade analysis via link graph.
- Autonomy-gated execution (propose / auto / full).

### Phase 3: Comment Curation + Budget Trimming

- Implement Comment Curator sub-agent.
- Implement Budget Trimmer sub-agent.
- Reactive hooks (post-edit, post-bead-close).

### Phase 4: Scheduled + Sweep Integration

- Cron/sweep integration for periodic sweeps.
- Report persistence and history.
- `/curator` skill for interactive invocation.
- Auto-promote `draft` conventions to `active` after review threshold.
- Suggest concepts for archival when no usage detected for N days.
- Convention-from-failure detection (§2.10) — propose conventions from
  recurring validation failure patterns.

---

## 8. Non-Goals (For Now)

- **Content generation**: The Curator does not write new concepts, conventions,
  or design files from scratch. It maintains existing ones.
- **Code changes**: The Curator does not modify source code (only knowledge-layer
  artifacts).
- **PR review**: Out of scope — this is a maintenance agent, not a review agent.
- **Cross-repo**: Single-repo only. No multi-repo federation.

---

## 9. Failure Model

The Curator must never make a bad situation worse. Its failure handling follows
the project's established error collection pattern. For the full Lexibrary
failure taxonomy (exception hierarchy, recovery strategies, error collection),
see [spec-opportunities.md §Opportunity 7](spec-opportunities.md#opportunity-7-failure-model-documentation).

### Coordinator Failures

| Condition | Behaviour |
|-----------|-----------|
| Link graph missing/corrupt | Degrade gracefully: skip graph-dependent checks, fall back to file scanning. Log warning. |
| `validate_library()` raises | Log error, skip validation sweep, continue with other signal sources (hash checks, IWH scan). |
| Config parse failure | Abort run with clear error. Do not attempt partial execution with defaults. |
| IWH read failure on a single signal | Log and skip that signal. Continue with remaining signals. |

### Sub-Agent Failures

| Condition | Behaviour |
|-----------|-----------|
| Sub-agent returns malformed output | Discard result, log error, record in `ErrorSummary`. Do not write partial artifacts. |
| Sub-agent times out | Kill process, log timeout, queue the work item for the next run. |
| LLM returns garbage for design reconciliation | Do not write the result. Flag the file for human review (IWH signal with `scope: warning`). |
| Sub-agent modifies a file that has uncommitted changes | Should never happen — coordinator checks `git status` before dispatching. If it does, abort the sub-agent's write and log a conflict warning. |

### Recovery Principle

The Curator uses the project's `ErrorSummary` pattern: leaf operations raise,
the coordinator catches and records via `summary.add(phase, error, path)`, and
processing continues. The final report includes all errors encountered. Exit
code 1 if `summary.has_errors()`.

**Never silently swallow errors.** Every failure must appear in the report so
the user knows what was skipped and why.
