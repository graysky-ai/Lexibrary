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

### 2.3 Validation Sweep

- Run the full `lexi validate` check suite (13 checks across error/warning/info).
- Triage results by severity, grouping related issues into actionable work items.
- Auto-fix trivially correctable issues (e.g. missing bidirectional dep entries).

### 2.4 Staleness Management

- **Hash freshness**: Compare `source_hash` in design files against current
  source SHA-256. Rank staleness by age and downstream impact.
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

### 2.7 Index Health (Speculative)

- **aindex coverage**: Identify source files missing from `.aindex` output.
- **Link graph integrity**: Verify SQLite index is consistent with on-disk
  artifacts.
- **Alias collisions**: Detect duplicate or ambiguous aliases in the link graph.

### 2.8 Migration Assistance (Speculative)

- When a concept is deprecated with `superseded_by`, scan all referencing
  artifacts and generate a batch migration plan (or execute it, depending on
  autonomy level).

### 2.9 Agent-Edited Design File Reconciliation

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

### 3.2 Sub-Agents

| Sub-Agent | Responsibility | Model Tier |
|-----------|---------------|------------|
| **Staleness Resolver** | Regenerate stale design files from source; reconcile agent-edited designs via hybrid merge (2.9) | Heavy (Opus) |
| **Deprecation Analyst** | Assess impact, draft migration briefs, execute deprecations | Heavy (Opus) |
| **Comment Curator** | Audit and clean descriptions, TODOs, summaries | Light (Haiku/Sonnet) |
| **Consistency Checker** | Fix wikilinks, bidirectional deps, alias conflicts | Light (Haiku) |
| **Budget Trimmer** | Condense files exceeding token budgets | Medium (Sonnet) |

Sub-agents receive a focused work item (not the full triage), do their task, and
return a structured result.

### 3.3 Trigger Modes

#### Scheduled (Periodic)

- Full health sweep: daily or weekly (configurable).
- Lightweight hash-freshness check: after every N commits or on a short interval.
- Implementation: cron job or daemon integration (watchdog already exists).

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
- The sub-agent must distinguish **mechanical sections** (interface skeleton,
  dependency list, file description accuracy) from **agent-added value**
  (custom notes, refined summaries, added context, wikilinks the LLM
  wouldn't generate).
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
  interface stable): **Low risk** — mechanical update, interface skeleton
  refresh.
- If the source change is large (e.g. new public API, renamed functions,
  removed exports): **Medium risk** — LLM must reason about what agent notes
  still apply.
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
| **Daemon** (watchdog) | Potential trigger source for reactive mode. |

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

### Phase 4: Scheduled + Daemon Integration

- Cron/daemon integration for periodic sweeps.
- Report persistence and history.
- `/curator` skill for interactive invocation.

---

## 8. Non-Goals (For Now)

- **Content generation**: The Curator does not write new concepts, conventions,
  or design files from scratch. It maintains existing ones.
- **Code changes**: The Curator does not modify source code (only knowledge-layer
  artifacts).
- **PR review**: Out of scope — this is a maintenance agent, not a review agent.
- **Cross-repo**: Single-repo only. No multi-repo federation.
