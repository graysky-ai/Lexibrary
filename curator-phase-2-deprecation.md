# Curator Phase 2: Deprecation Workflow

> Implement the Deprecation Analyst sub-agent, cascade analysis via the link
> graph, and autonomy-gated execution of artifact lifecycle transitions.

**Prerequisites**: Phases 0, 1a, 1b, 1.5a, and 1.5b must be complete. The
coordinator skeleton, validation integration, Staleness Resolver, Consistency
Checker, comment integration, and agent-edit reconciliation are all in place.

### Prerequisites Checklist

The following artifacts and modules must exist before Phase 2
implementation begins. These are delivered by Phases 0–1.5b, which are
currently in progress.

- [ ] `src/lexibrary/curator/` package with `__init__.py`
- [ ] Coordinator skeleton (`coordinator.py`) with collect / triage /
  dispatch / report phases
- [ ] `CuratorConfig` in `src/lexibrary/config/schema.py` with
  `autonomy`, `max_llm_calls_per_run`, and `risk_overrides` fields
- [ ] Risk taxonomy (`risk_taxonomy.py`) with `ActionRisk` table
- [ ] At least one working BAML sub-agent (Staleness Resolver or
  Consistency Checker) demonstrating the dispatch pattern
- [ ] Shared test fixture at `tests/fixtures/curator_library/`
- [ ] Comment integration and agent-edit reconciliation (Phase 1.5a/b)

**Deferred to Phase 3+**: Fuzzy match alias discovery (deferred from Phase
1b) is not in scope for Phase 2. It remains queued for a future phase where
the Consistency Checker gains alias-expansion capabilities.

---

## 1. What Ships

- **Deprecation Analyst sub-agent** — BAML function (`CuratorDeprecateArtifact`)
  invoked via `BamlAsyncClient`, following the same pattern as the archivist's
  `ArchivistService`. Model tier: Heavy (Opus). The sub-agent receives focused
  work items from the coordinator and returns structured results; it does not
  make coordinator-level decisions.

- **Cascade analysis** — Before deprecating any artifact with dependents, the
  coordinator traces inbound links via `reverse_deps()` and multi-hop traversal
  via `traverse()` to quantify downstream impact and generate a migration brief.

- **Autonomy-gated execution** — All deprecation actions are gated by the
  project's `curator.autonomy` setting and the per-action risk classification.
  Under `auto_low` (default), only low-risk deprecations execute automatically;
  medium and high are proposed for human review. Under `full`, all execute.
  Under `propose`, all are proposed.

- **Migration execution** — When a concept is deprecated with
  `superseded_by`, the coordinator scans all referencing artifacts and
  generates a batch migration plan. Depending on the autonomy level, the
  coordinator either executes the migration (updating wikilinks and concept
  references in dependent artifacts) or proposes it for human review.
  Migration is a separate dispatch cycle that runs after the deprecation
  itself is committed.

- **Stack post deduplication** — Before creating a Stack post for a recurring
  deprecation issue, the coordinator checks for existing open posts with
  matching problem fingerprints. If a match exists, a Finding is added to the
  existing post rather than creating a duplicate.

---

## 2. Artifact State Machines

The Deprecation Analyst must enforce valid state transitions. Each artifact
type has a distinct lifecycle:

**Design Files**: `active → deprecated` (source deleted/renamed/manual) or
`active → unlinked` (source outside scope). `unlinked → active` on
re-addition. Deprecated is terminal. The `deprecated_reason` field records
the cause: `source_deleted`, `source_renamed`, or `manual`.

**Concepts**: `draft → active → deprecated → HARD DELETED` (after
`config.deprecation.ttl_commits` with 0 active references). Sets
`superseded_by` and `deprecated_at` on deprecation. Hard deletion removes
the `.md` file and its sibling `.comments.yaml`. Confirm policy:
`config.concepts.deprecation_confirm`.

**Conventions**: `draft → active → deprecated → HARD DELETED` (after
`config.deprecation.ttl_commits`, default 50). Hard deletion removes the
`.md` file and its sibling `.comments.yaml`. Confirm policy:
`config.conventions.deprecation_confirm`.

**Stack Posts**: `open → resolved` (via `accept_finding`), `open → duplicate`,
`open → outdated`, `resolved → stale` (after TTL), `stale → resolved`
(unstale). `mark_stale()` requires `status="resolved"`.

**Playbooks**: `draft → active → deprecated → HARD DELETED` (after
`config.deprecation.ttl_commits` with 0 active references). Sets
`superseded_by` and `deprecated_at` on deprecation. Hard deletion removes
the `.md` file and its sibling `.comments.yaml`. Confirm policy:
`config.playbooks.deprecation_confirm`.

### Invalid Transitions

The sub-agent must reject invalid transitions with a clear error:

- `draft → deprecated` is not valid for concepts (must go through `active`).
- `draft → deprecated` is not valid for playbooks (must go through `active`).
- `deprecated` for design files is terminal — no further transitions.
- Concept and convention hard deletion can only fire after
  `config.deprecation.ttl_commits` commits have passed since deprecation
  **and** the artifact has zero active inbound references.
- Hard deletion of a concept or convention that still has active references
  is rejected — the coordinator must run migration first.

---

## 3. Deprecation Analyst Sub-Agent

### 3.1 Invocation

The coordinator dispatches the Deprecation Analyst as a BAML function call
via `BamlAsyncClient`. The sub-agent is a structured BAML prompt with
schema-validated input/output — not a subprocess or CLI call. This matches
the archivist pattern established in `src/lexibrary/archivist/service.py`.

### 3.2 Input

The coordinator assembles a work item containing:

| Field | Source | Purpose |
|-------|--------|---------|
| `artifact_path` | Triage result | Path to the artifact being deprecated |
| `artifact_kind` | Triage result | `concept`, `convention`, `design_file`, `stack_post`, or `playbook` |
| `current_status` | Artifact frontmatter | Current lifecycle state |
| `target_status` | Triage rule or user request | Desired lifecycle state |
| `superseded_by` | User input or coordinator inference | Successor artifact (concepts only) |
| `deprecated_reason` | Artifact frontmatter | Cause of deprecation (design files only): `source_deleted`, `source_renamed`, or `manual` |
| `dependents` | `reverse_deps(path)` | List of inbound links to this artifact |
| `transitive_dependents` | `traverse(path, max_depth=3)` | Multi-hop dependents for cascade analysis |
| `dependent_count` | Computed | Total number of affected artifacts |

### 3.3 Output

The sub-agent returns a structured result:

| Field | Type | Purpose |
|-------|------|---------|
| `action` | `deprecate` / `hard_delete` / `propose` / `skip` | What the coordinator should do |
| `migration_brief` | `string | None` | Human-readable brief when dependents exist |
| `cascade_summary` | `list[AffectedArtifact]` | Artifacts that need updating post-deprecation |
| `migration_edits` | `list[MigrationEdit] | None` | Concrete edits to apply to dependent artifacts |
| `confidence` | `float` | Sub-agent's confidence in the recommendation |
| `rationale` | `string` | Why this action was chosen |

Each `MigrationEdit` contains:

| Field | Type | Purpose |
|-------|------|---------|
| `artifact_path` | `string` | Path to the dependent artifact to update |
| `edit_type` | `replace_wikilink` / `update_concept_ref` / `remove_reference` | Kind of edit |
| `old_value` | `string` | Current reference (e.g. `[[OldConcept]]`) |
| `new_value` | `string | None` | Replacement reference (e.g. `[[NewConcept]]`), or `None` for removals |

### 3.4 Cascade Analysis

When an artifact has dependents, the coordinator runs cascade analysis
before dispatching to the sub-agent:

1. **Direct dependents**: `reverse_deps(artifact_path)` returns all inbound
   links (wikilinks, concept_file_ref, convention_concept_ref, etc.).
2. **Transitive dependents**: `traverse(artifact_path, max_depth=3,
   direction='outbound')` discovers multi-hop impact with cycle detection.
3. **Migration brief**: The sub-agent generates a brief listing all affected
   artifacts and what needs to change. When `superseded_by` is set, the brief
   references the successor concept and describes the migration path.

### 3.5 Actions by Artifact Type

**Concepts** (`draft → active → deprecated → HARD DELETED`):

- `draft → active`: Low risk. Minimal downstream impact at draft stage.
  Auto-executed under `auto_low`.
- `active → deprecated`: High risk. All dependents require migration. The
  sub-agent produces a cascade analysis, migration brief, and migration
  edits. `superseded_by` is set in the concept frontmatter. `deprecated_at`
  timestamp is recorded. Under `auto_low`, this is proposed (not
  auto-executed).
- Hard delete after `ttl_commits` with 0 active references: Low risk.
  Protected by reference-count check. Removes the `.md` file.
  Auto-executed under `auto_low`.
- Delete orphaned `.comments.yaml` sidecar after artifact hard deletion:
  Low risk. Cleanup of orphaned metadata. Auto-executed under `auto_low`.
  Function ref: `deprecation.delete_comments_sidecar()`.

**Conventions** (`draft → active → deprecated → HARD DELETED`):

- `draft → active`: Low risk. Auto-executed under `auto_low`.
- `active → deprecated`: Medium risk. Affects scoped files. Under `auto_low`,
  this is proposed for review.
- Hard delete after `ttl_commits` with 0 active references: Low risk.
  Removes the `.md` file. Auto-executed under `auto_low`.
- Delete orphaned `.comments.yaml` sidecar after artifact hard deletion:
  Low risk. Cleanup of orphaned metadata. Auto-executed under `auto_low`.
  Function ref: `deprecation.delete_comments_sidecar()`.

**Playbooks** (`draft → active → deprecated → HARD DELETED`):

- `draft → active`: Low risk. Auto-executed under `auto_low`.
- `active → deprecated`: Medium risk. Affects triggered workflows. Under
  `auto_low`, this is proposed for review.
- Hard delete after `ttl_commits` with 0 active references: Low risk.
  Removes the `.md` file. Auto-executed under `auto_low`.
- Delete orphaned `.comments.yaml` sidecar after artifact hard deletion:
  Low risk. Cleanup of orphaned metadata. Auto-executed under `auto_low`.
  Function ref: `deprecation.delete_comments_sidecar()`.

**Design Files** (`active → deprecated` or `active → unlinked`):

- Deprecate (source deleted/renamed): Medium risk. Cascade may affect
  dependents. Under `auto_low`, proposed for review.
- Mark as unlinked (source outside scope): Low risk. Reversible on
  re-addition. Auto-executed under `auto_low`.

**Stack Posts**:

- `open → resolved`: Low risk. Metadata state change only.
- `open → duplicate`: Low risk. Deduplication; points to canonical post.
- `open → outdated`: Low risk. Metadata state change only.
- `resolved → stale` (after TTL): Low risk. Time-based metadata transition.
- `stale → resolved` (unstale): Low risk. Reversal of staleness flag.
- Generate migration brief for deprecated concept: Low risk. Read-only
  analysis, written as report.

All stack post transitions are auto-executed under `auto_low`.

**Migration Edits** (updating dependent artifacts post-deprecation):

- Apply migration edits to dependent artifacts (replace wikilinks, update
  concept references): Medium risk. Modifies artifacts beyond the deprecated
  one. Under `auto_low`, the full migration plan is proposed for review.
  Function ref: `deprecation.apply_migration_edits()`.

### 3.6 Migration Execution

When a concept is deprecated with `superseded_by`, the coordinator runs a
migration cycle after the deprecation is committed:

1. **Plan**: The sub-agent's `migration_edits` list contains concrete edits
   for each dependent artifact (replace wikilink, update concept reference,
   or remove reference). When `superseded_by` is set, replacements point to
   the successor concept; otherwise, references are removed.

2. **Validate**: Before gating, the coordinator validates the
   `superseded_by` target:
   - Verify the target artifact exists and has `status: active`. If the
     target is itself deprecated, escalate the action to `propose`
     regardless of the current autonomy level.
   - Traverse the successor chain (A → B → C …) to detect cycles. If a
     cycle is found, reject the migration with a clear error and record
     it in `ErrorSummary`.
   - If validation fails, the deprecation itself may still proceed
     (marking the artifact deprecated), but migration edits are not
     generated — the issue is surfaced as a proposal for human review.

3. **Gate**: Each migration edit is gated by autonomy level. Migration edits
   are classified as **Medium** risk (they modify artifact content beyond
   the deprecated artifact itself). Under `auto_low`, the full migration
   plan is proposed for review. Under `full`, edits are executed. Under
   `propose`, the plan is written to the report and an IWH signal.

4. **Execute**: The coordinator applies `migration_edits` to dependent
   artifacts. Design file edits follow the design file write contract
   (§5.5 Write Contract). Concept and convention frontmatter edits use
   `atomic_write()`.
   Each edit is tracked in the on-disk report.

5. **Verify**: After applying edits, the coordinator re-runs
   `reverse_deps()` on the deprecated artifact to confirm zero remaining
   inbound references. Any remaining references are logged as warnings.

Migration execution is a separate dispatch cycle from the deprecation
itself — the deprecation must be committed before migration begins. This
ensures that if migration is interrupted, the deprecation state is
consistent and migration can resume on the next run.

### 3.7 Stack Post Fingerprinting

Before creating a Stack post for a deprecation issue, the coordinator
computes a deterministic problem fingerprint to check for duplicates.

The fingerprint is a SHA-256 hash of the following normalized fields,
concatenated with newline separators:

1. `problem_type` — the deprecation action category (e.g.
   `deprecate_concept`, `hard_delete_convention`, `migration_blocked`).
2. `artifact_path` — the path of the primary artifact involved,
   relative to the project root.
3. `error_signature` — a normalized form of the error or issue
   description (lowercased, whitespace-collapsed).

The coordinator queries existing open Stack posts via
`full_text_search(problem_type + artifact_path)` and compares
fingerprints. A match is defined as an exact fingerprint match on an
open post (status `open`). Resolved, outdated, or duplicate posts are
not considered matches.

When a match is found, the coordinator adds a new Finding to the
existing post rather than creating a duplicate. The Finding includes
the current run's timestamp and any updated rationale from the
sub-agent.

---

## 4. Autonomy Gating

Every artifact-modifying action is gated by the project's autonomy setting
and the action's risk level. Read-only actions (detection, analysis,
reporting) are never gated.

| Autonomy | Low Risk | Medium Risk | High Risk |
|----------|----------|-------------|-----------|
| `auto_low` | Auto-execute | Propose for review | Propose for review |
| `full` | Auto-execute | Auto-execute | Auto-execute |
| `propose` | Propose for review | Propose for review | Propose for review |

### Confirmation Policies

Per-artifact-type confirmation policies override even `full` autonomy:

- `config.concepts.deprecation_confirm`: When `true`, concept deprecation
  is proposed even under `full` autonomy.
- `config.conventions.deprecation_confirm`: When `true`, convention
  deprecation is proposed even under `full` autonomy.

When a deprecation is proposed (not auto-executed), the coordinator writes
an IWH signal (`scope: warning`) describing the proposed action and its
rationale, so the next agent session or human reviewer can act on it.

### Risk Override

Projects can override the default risk level for any action in
`config.yaml`:

```yaml
curator:
  autonomy: auto_low
  risk_overrides:
    # Treat convention deprecation as high-risk in this project
    deprecate_convention: high
    # Allow concept deprecation without review
    deprecate_concept: low
```

Override values are validated against `{low, medium, high}`. Unknown action
keys produce a validation warning.

---

## 5. Coordinator Integration

### 5.1 Collect Phase

During the collect phase, the coordinator discovers deprecation candidates:

- **Orphan detection**: Artifacts with zero inbound links in the link graph.
  When the link graph is unavailable (`LinkGraph.open()` returns `None`),
  orphan detection is skipped and a warning is logged recommending
  `lexictl update`.
- **Source deletion**: Design files whose source files no longer exist on
  disk.
- **TTL expiry**: Deprecated concepts and conventions past
  `config.deprecation.ttl_commits` with zero active references.
- **Stack post staleness**: Resolved posts whose referenced code has changed
  substantially.

All link graph queries for the run are executed during the collect phase
and cached as an immutable snapshot. The coordinator works from this
snapshot for the entire triage and dispatch cycle. This prevents cascade
effects between deprecations within the same run and ensures
deterministic, reproducible results. The snapshot is discarded at the end
of the run.

### 5.2 Triage Phase

The coordinator classifies each candidate by artifact type, target
transition, and risk level (looked up from the risk taxonomy in
`src/lexibrary/curator/risk_taxonomy.py`). Items are ranked by:

1. Risk level (low first, so auto-executable items are processed before
   items that may hit the LLM call cap).
2. Number of reverse dependents (more dependents = higher priority within
   the same risk level).

### 5.3 Dispatch Phase

The coordinator dispatches to the Deprecation Analyst sub-agent via BAML
call. Before each dispatch:

- Check the running LLM call count against `curator.max_llm_calls_per_run`
  (default: 50). If the cap is reached, record remaining items as "deferred"
  in the report.
- Check `git status` — skip artifacts with uncommitted changes.
- Check for open IWH signals (`incomplete` or `blocked` scope) in the
  artifact's directory — skip artifacts under active agent work.

### 5.4 Dry-Run Mode

`lexictl curate --dry-run` (established in Phase 1a) must report Phase 2
actions without executing them. Dry-run output for deprecation includes:

- Number of deprecation candidates discovered (by artifact type).
- Number of cascade analyses that would be dispatched.
- Number of migration edits that would be applied (with affected paths).
- Estimated sub-agent call count against the `max_llm_calls_per_run` cap.
- Which actions would be auto-executed vs. proposed (based on current
  autonomy level and risk classification).

### 5.5 Write Contract

All deprecation writes must follow the established write contracts:

**Design files** (deprecation status changes, migration edits to design file
bodies): Writes must use `serialize_design_file()` and `atomic_write()` per
§3.6 of the main curator spec. The coordinator sets `updated_by` in
frontmatter before calling the serializer. `source_hash` and
`interface_hash` are computed by the coordinator via `compute_hashes()`.

**Concepts and conventions** (frontmatter status changes, `superseded_by`,
`deprecated_at`): Writes use `atomic_write()` from
`src/lexibrary/utils/atomic.py`. The coordinator reads the current YAML,
updates the relevant fields, and writes the complete file atomically. Partial
writes are never written to the final path.

**Sidecar `.comments.yaml` deletion** (hard deletion cleanup): The
coordinator deletes the sidecar only after the parent artifact's `.md` file
has been successfully removed. Deletion order: `.md` first, then
`.comments.yaml`. If `.md` deletion fails, the sidecar is left in place.

### 5.6 Report Phase

Deprecation results are reported through four channels:

1. **IWH signals** — For proposed (not auto-executed) deprecations, write
   a `scope: warning` signal describing the proposed action so the next
   agent or human sees it.
2. **Stack posts** — For recurring deprecation patterns or escalated
   blockers. Deduplicated by problem fingerprint before creation.
3. **On-disk report** — Full audit trail in
   `.lexibrary/curator/reports/` (gitignored). Includes what was deprecated,
   what was proposed, what was deferred, and LLM call count.
4. **Console output** — High-level counts for the operator.

---

## 6. Python APIs Used

| API | Module | Purpose |
|-----|--------|---------|
| `open_index(project_root)` | `linkgraph.query` | Convenience wrapper — finds db, opens graph |
| `LinkGraph.open(db_path)` | `linkgraph.query` | Read-only graph queries; used internally by `open_index()` — coordinator should call `open_index()` directly |
| `reverse_deps(path, link_type)` | `linkgraph.query` | Inbound links for cascade analysis |
| `traverse(start_path, max_depth=3, direction='outbound')` | `linkgraph.query` | Multi-hop traversal with cycle detection |
| `get_artifact(path)` | `linkgraph.query` | Single artifact lookup |
| `resolve_alias(alias)` | `linkgraph.query` | Case-insensitive concept lookup |
| `get_conventions(directory_paths, *, include_deprecated=False)` | `linkgraph.query` | Conventions scoped to directories; needed for convention deprecation impact |
| `full_text_search(query)` | `linkgraph.query` | Stack post fingerprint matching |
| `validate_library(...)` | `validator` | Validation issues as input signal |
| `find_all_iwh(project_root)` | `iwh.reader` | Scope isolation check |
| `parse_design_file(path)` | `artifacts.design_file_parser` | Read artifact frontmatter/status |
| `serialize_design_file()` | `artifacts.design_file_serializer` | Write contract — design file serialization |
| `atomic_write()` | `utils.atomic` | Write contract — atomic file writes |
| `compute_hashes()` | AST parser | Write contract — source/interface hash computation |

---

## 7. Failure Handling

| Condition | Behaviour |
|-----------|-----------|
| Link graph unavailable | Skip orphan detection, dependent fan-out, alias resolution. Fall back to file-scanning for source-deleted design files. Log warning. |
| Sub-agent returns malformed output | Discard result, log error, record in `ErrorSummary`. Do not write partial artifacts. |
| Sub-agent times out | Kill the call, queue the work item for the next run. |
| Invalid state transition attempted | Reject with a clear error. Do not modify the artifact. |
| Artifact has uncommitted changes | Skip; record as deferred in the report. |
| Migration edit fails on a single artifact | Log error, skip that artifact, continue with remaining edits. Report includes partial migration state. |
| Migration interrupted (process killed) | Deprecation is already committed. Remaining migration edits are discovered on the next run via `reverse_deps()`. |
| Stack post deduplication check fails | Log and create the post anyway (better a duplicate than a lost signal). |

The coordinator uses the project's `ErrorSummary` pattern: leaf operations
raise, the coordinator catches and records via `summary.add(phase, error,
path)`, and processing continues. Exit code 1 if `summary.has_errors()`.

### Input Sanitisation

Artifact content passed to the Deprecation Analyst prompt must be sanitised:

- Use BAML raw string blocks for user-supplied content (no Jinja2
  interpolation).
- Flag artifacts containing suspicious patterns (`{{`, `{%`,
  instruction-like directives) for human review rather than including them
  in sub-agent dispatch.
- Code-fenced template syntax in design file bodies is not falsely flagged.

---

## 8. Testing Plan

### 8.1 Deprecation Analyst Unit Tests (Mocked BAML)

- Deprecation of a concept with zero dependents: produces a deprecation
  action with no migration brief and no migration edits.
- Deprecation of a concept with dependents: produces a cascade analysis
  listing all dependent artifacts, a migration brief, and concrete
  `migration_edits` for each dependent.
- Deprecation with `superseded_by` pointer: the migration brief references
  the successor concept; `migration_edits` contain `replace_wikilink` entries
  pointing to the successor.
- Deprecation without `superseded_by`: `migration_edits` contain
  `remove_reference` entries (no replacement target).

### 8.2 State Machine Tests

- Each artifact type (design file, concept, convention, stack post) only
  allows valid transitions as defined in §2.
- Invalid transitions are rejected with a clear error (e.g. `draft →
  deprecated` is not valid for concepts — must go through `active`).
- Terminal states are enforced: `deprecated` for design files cannot
  transition to any other state.
- Concept and convention hard deletion fires only after
  `config.deprecation.ttl_commits` commits have passed since deprecation
  **and** the artifact has zero active inbound references.
- Hard deletion of an artifact with active references is rejected.

### 8.3 Autonomy Gating Tests

- Under `propose`: deprecation is NOT executed. A proposal (IWH signal or
  report entry) is generated instead.
- Under `auto_low`: deprecation of a concept with dependents is NOT
  auto-executed (high risk). Deprecation of an orphan concept with zero
  dependents IS auto-executed (low risk).
- Under `full`: all deprecations are executed.
- Confirmation policy: when `config.concepts.deprecation_confirm` is `true`,
  deprecation is gated even under `full` autonomy (proposal instead of
  auto-execution).

### 8.4 Cascade Analysis Tests (Link Graph)

- `reverse_deps()` correctly identifies all inbound links to the artifact
  being deprecated.
- Multi-hop traversal (`traverse()`) discovers transitive dependents up to
  `max_depth`.
- Cascade analysis output includes the count and paths of affected artifacts.

### 8.5 Migration Execution Tests

- Migration edits with `superseded_by`: all dependent artifacts' wikilinks
  are updated from `[[OldConcept]]` to `[[NewConcept]]`.
- Migration edits without `superseded_by`: references to the deprecated
  concept are removed from dependent artifacts.
- Migration gated by autonomy: under `auto_low`, migration edits are
  proposed (not executed). Under `full`, edits are applied.
- Post-migration verification: `reverse_deps()` returns zero inbound links
  after successful migration.
- Migration interrupted mid-cycle: deprecation state is consistent (artifact
  is deprecated), remaining migration edits are picked up on the next run.
- Design file migration edits follow the write contract: `serialize_design_file()`
  and `atomic_write()` are used (verified by mocking).

### 8.6 Hard Deletion and Sidecar Cleanup Tests

- Concept hard deletion after `ttl_commits` with 0 active references:
  `.md` file is removed.
- Convention hard deletion after `ttl_commits` with 0 active references:
  `.md` file is removed.
- Sidecar `.comments.yaml` is deleted after parent `.md` is successfully
  removed.
- Sidecar is NOT deleted if parent `.md` deletion fails.
- Hard deletion rejected when artifact still has active inbound references.

### 8.7 Integration Tests

- End-to-end deprecation of an orphan concept: concept file updated with
  `deprecated` status and `deprecated_at` timestamp.
- End-to-end deprecation with migration: concept deprecated, dependent
  artifacts updated with successor references, report includes migration
  summary.
- End-to-end deprecation blocked by autonomy: concept remains in `active`
  status, report shows it was proposed but not executed.
- Confirmation policy override: concept deprecation gated even under `full`
  autonomy when `config.concepts.deprecation_confirm` is `true`.
- End-to-end hard deletion: deprecated concept past TTL with 0 references
  is removed along with its `.comments.yaml` sidecar.

### 8.8 Stack Post Deduplication Tests

- Before creating a Stack post for a recurring issue, the coordinator checks
  for existing open posts with matching fingerprints.
- If a match exists, a new Finding is added to the existing post rather than
  creating a duplicate.
- If no match exists, a new Stack post is created.

### 8.9 Test Fixture Extensions

The shared test fixture at `tests/fixtures/curator_library/` is extended
with:

| Planted Issue | Used By |
|---------------|---------|
| Concept in `active` status with dependents | Cascade analysis, autonomy gating |
| Orphan concept with zero inbound links | Low-risk auto-deprecation |
| Deprecated concept past TTL with 0 references | Concept hard deletion |
| Deprecated convention past TTL with 0 references | Convention hard deletion |
| Concept with `superseded_by` and active dependents | Migration execution |
| Valid, healthy artifacts (control) | Should not be touched |

### 8.10 Cross-Cutting Concerns

These apply to Phase 2 and are verified continuously:

- **Input sanitisation**: Artifact content with Jinja2 syntax or
  instruction-like directives is flagged and excluded from sub-agent prompts.
- **Scope isolation**: Artifacts with uncommitted changes or open IWH signals
  are skipped. Skipped items appear in the report as "skipped — active
  changes detected".
- **Idempotency**: Running the coordinator twice with no intervening changes
  produces no additional modifications on the second run.
- **Cost control**: Coordinator respects `max_llm_calls_per_run`; remaining
  items are deferred when the cap is reached.
- **Concurrency safety**: Two coordinator runs cannot execute simultaneously
  (lockfile or equivalent mechanism from Phase 0). If a lock is held, the
  second invocation exits immediately with a clear message.
- **Dry-run compatibility**: All new deprecation actions are reported
  correctly under `--dry-run` without modifying any files.

---

## 9. Implementation Steps

1. **Config model extensions** — Add deprecation-related fields to
   `CuratorConfig` if not already present: `config.deprecation.ttl_commits`
   (default: 50), `config.concepts.deprecation_confirm` (default: `false`),
   `config.conventions.deprecation_confirm` (default: `false`). Add
   validation for these fields in the config schema. Add `risk_overrides`
   support for the new deprecation action keys.

2. **Risk taxonomy entries** — Add all deprecation-related actions to the
   `ActionRisk` table in `src/lexibrary/curator/risk_taxonomy.py` (see §3.5
   for the full list with risk levels and function refs). Include migration
   edit actions and sidecar deletion as discrete entries.

3. **State machine module** — Implement `src/lexibrary/curator/lifecycle.py`
   as a thin orchestration layer that validates state transitions and
   delegates mutation to the existing `lifecycle/` modules:
   - `lifecycle.deprecation` — design file deprecation status writes
   - `lifecycle.concept_deprecation` — concept hard deletion and sidecar cleanup
   - `lifecycle.convention_deprecation` — convention hard deletion and sidecar cleanup

   The curator module adds transition validation logic (enforcing valid
   transitions, terminal states, and TTL + zero-reference checks for hard
   deletion); the existing `lifecycle/` modules handle the actual file
   mutations. Do not duplicate mutation logic that already exists there.

4. **Deprecation Analyst BAML function** — Define `CuratorDeprecateArtifact`
   with typed input/output matching §3.2 and §3.3, including
   `MigrationEdit` output for dependent artifact updates. Use raw string
   blocks for artifact content to prevent template injection.

5. **Cascade analysis** — Implement cascade analysis in the coordinator's
   triage phase using `reverse_deps()` and `traverse()`. Assemble the
   `dependents` and `transitive_dependents` fields for the sub-agent work
   item.

6. **Migration execution** — Implement the migration dispatch cycle (§3.6):
   apply `migration_edits` to dependent artifacts, gated by autonomy level.
   Design file edits delegate to `lifecycle.deprecation` for the actual write
   operations (do not re-implement the write contract inline). Concept and
   convention frontmatter updates (setting `superseded_by`, clearing stale
   references) use the patterns already established in
   `lifecycle.concept_deprecation` and `lifecycle.convention_deprecation`.
   Verify zero remaining references after migration.

7. **Coordinator dispatch logic** — Extend the coordinator's dispatch phase
   to route deprecation candidates to the Deprecation Analyst. Gate dispatch
   on autonomy level and risk classification. Check confirmation policies
   before executing even under `full` autonomy. Ensure dry-run mode reports
   deprecation actions without executing.

8. **Stack post deduplication** — Before creating a Stack post for a
   deprecation issue, query the link graph for open posts with matching
   problem fingerprints. Add a Finding to existing posts rather than creating
   duplicates.

9. **Test fixture extensions** — Add planted deprecation candidates to the
   shared test fixture (active concept with dependents, orphan concept,
   deprecated concept past TTL with 0 references, deprecated convention
   past TTL).

10. **Unit tests** — State machine transitions, autonomy gating, cascade
    analysis, migration execution, sub-agent input/output (mocked BAML),
    deduplication, sidecar deletion, dry-run reporting.

11. **Integration tests** — End-to-end deprecation flows against the test
    fixture, verifying artifact state changes, migration edits applied,
    report contents, and IWH signal generation for proposed actions.
