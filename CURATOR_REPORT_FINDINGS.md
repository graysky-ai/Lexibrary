# Curator Run: Findings and Recommendations

**Date:** 2026-04-11
**Trigger:** User reported that `lexictl curate` produced terse output and that
`lexi validate` issues did not reduce after the run.
**Report analyzed:** `.lexibrary/curator/reports/20260410T143702Z.json`

## Observed behavior

Terminal output from `lexictl curate`:

```
Curator Run Summary
  Checked:  170
  Fixed:    156
  Deferred: 14
  Errors:   0

  Sub-agent calls:
    autofix_validation_issue: 109
    consume_superseded_iwh: 3
    integrate_sidecar_comments: 44
```

Persisted JSON report contains only the same aggregate counters — no per-item
`path`, `message`, `action`, or `dispatched`/`deferred` lists.

After the run, `lexi validate` continued to report the same issues.

## Root cause

Both symptoms — the terse report and the unchanged validator state — trace to
the same underlying problem: **most of the "fixes" the curator claimed are
stub no-ops, and the report format has no place to reveal that.**

### Finding 1: The report persists only aggregate counters

Each dispatched action returns a
[`SubAgentResult`](src/lexibrary/curator/models.py#L144-L152) with `path`,
`message`, `action_key`, and `llm_calls` fields. The coordinator's
`_write_report` at
[coordinator.py:2289-2328](src/lexibrary/curator/coordinator.py#L2289-L2328)
throws those away and writes only scalar counts:

```python
data = {
    "timestamp": ...,
    "trigger": ...,
    "checked": ..., "fixed": ..., "deferred": ..., "errored": ...,
    "sub_agent_calls": ...,   # dict[action_key, count]
    "deprecated": ..., "hard_deleted": ...,
    "migrations_applied": ..., "migrations_proposed": ...,
    "budget_condensed": ..., "budget_proposed": ...,
    "comments_flagged": ...,
    "descriptions_audited": ..., "summaries_audited": ...,
}
```

There is no `dispatched` list, no `deferred` detail, no record of *which*
paths were touched or *what* each sub-agent reported. The terminal renderer in
[curate_render.py:14-72](src/lexibrary/services/curate_render.py#L14-L72) is
a straight projection of this schema, so it cannot surface anything richer
than its input.

### Finding 2: `autofix_validation_issue` is unimplemented — the dispatcher silently stubs it

Validation items are classified at
[coordinator.py:1266-1292](src/lexibrary/curator/coordinator.py#L1266-L1292)
with a single umbrella action key:

```python
action_key = "autofix_validation_issue"
```

The risk taxonomy declares the implementation lives at
[`curator.consistency.autofix_validation_issue`](src/lexibrary/curator/risk_taxonomy.py#L112-L116):

```python
"autofix_validation_issue": ActionRisk(
    level="low",
    rationale="Pre-vetted fixes from validator registry",
    function_ref="curator.consistency.autofix_validation_issue",
),
```

**That function does not exist.** `grep` in `src/lexibrary/curator/consistency.py`
finds zero matches for `autofix_validation_issue` or `def autofix`. The
`function_ref` in the taxonomy is aspirational.

`_dispatch_to_stub` at
[coordinator.py:1536-1586](src/lexibrary/curator/coordinator.py#L1536-L1586)
has explicit branches for:

- `regenerate_stale_design`
- `reconcile_agent_interface_stable` / `_interface_changed` / `_extensive_content`
- `integrate_sidecar_comments`
- budget items (`condense_file`, etc.)
- comment-audit items
- deprecation action keys

Everything else falls through to the stub at
[coordinator.py:1573-1586](src/lexibrary/curator/coordinator.py#L1573-L1586):

```python
# Stub: return success with 1 LLM call for non-deterministic actions
llm_calls = 1 if risk in ("medium", "high") else 0
return SubAgentResult(
    success=True,
    action_key=item.action_key,
    path=item.source_item.path,
    message=f"stub: {item.action_key} (risk={risk})",
    llm_calls=llm_calls,
)
```

The stub returns `success=True` and writes nothing to disk.

### Finding 3: `consume_superseded_iwh` is also stubbed

Same pattern. Declared at
[risk_taxonomy.py:127-131](src/lexibrary/curator/risk_taxonomy.py#L127-L131)
with `function_ref="curator.consistency.consume_superseded_iwh"`, classified
at [coordinator.py:1294-1307](src/lexibrary/curator/coordinator.py#L1294-L1307),
no implementation, falls through to the stub.

### Finding 4: The `fixed` counter conflates real fixes with stub successes

`_build_report` at
[coordinator.py:2188-2190](src/lexibrary/curator/coordinator.py#L2188-L2190)
computes `fixed` as:

```python
fixed = sum(
    1 for d in dispatch.dispatched
    if d.success and d.message != "dry-run: would dispatch"
)
```

It excludes dry-run entries but does **not** exclude stub successes (whose
messages start with `"stub: "`). Every stub dispatch therefore increments
`fixed`.

## Impact on the observed run

Breakdown of the 156 reported "fixes":

| Action key | Count | Implementation | Actually mutated files? |
|---|---:|---|---|
| `integrate_sidecar_comments` | 44 | Real — [comments.py](src/lexibrary/curator/comments.py) via `_dispatch_comment_integration` at [coordinator.py:1692](src/lexibrary/curator/coordinator.py#L1692) | Yes |
| `autofix_validation_issue` | 109 | **Stub** — `function_ref` points to a function that does not exist | **No** |
| `consume_superseded_iwh` | 3 | **Stub** — same as above | **No** |

**Real fixes: 44. Stub no-ops reported as fixes: 112.** This is why
`lexi validate` shows the same issues: the 109 validation items the curator
claimed to autofix were never actually touched.

The stub pathway is acknowledged in code comments — the module docstring at
[coordinator.py:4](src/lexibrary/curator/coordinator.py#L4) says
"sub-agent stubs (BAML integration in later groups)" and the `_dispatch_to_stub`
docstring at [coordinator.py:1545-1547](src/lexibrary/curator/coordinator.py#L1545-L1547)
says "All other action keys remain as stubs until their sub-agents are
implemented in later groups." The design is known to be partial. The problem
is that the counters and report don't distinguish "real fix" from "stub
success," so from the outside a curator run looks productive when much of it
is a no-op.

## Recommendations

### Priority 1 — Make the counters honest

Stub successes should not be counted as fixes. Two changes in
[coordinator.py](src/lexibrary/curator/coordinator.py):

1. In `_build_report` (around line 2188), exclude stub messages from `fixed`:

   ```python
   fixed = sum(
       1 for d in dispatch.dispatched
       if d.success
       and not d.message.startswith("dry-run:")
       and not d.message.startswith("stub:")
   )
   ```

2. Add a new counter `stubbed` to `CuratorReport`
   ([models.py:170-197](src/lexibrary/curator/models.py#L170-L197)) that
   tallies stub dispatches, and surface it in both the JSON report and the
   renderer in [curate_render.py](src/lexibrary/services/curate_render.py).

With this change alone, the observed run would have rendered as
`Fixed: 44 / Stubbed: 112`, and the problem would have been self-evident.

### Priority 2 — Record per-item dispatch details in the report

Extend the JSON schema written by `_write_report`
([coordinator.py:2289-2328](src/lexibrary/curator/coordinator.py#L2289-L2328))
to include:

```python
"dispatched": [
    {
        "action_key": r.action_key,
        "path": str(r.path) if r.path else None,
        "message": r.message,
        "success": r.success,
        "llm_calls": r.llm_calls,
    }
    for r in dispatch.dispatched
],
"deferred": [
    {
        "action_key": t.action_key,
        "path": str(t.source_item.path) if t.source_item.path else None,
        "issue_type": t.issue_type,
        "check": t.source_item.check,
        "message": t.source_item.message,
        "risk_level": t.risk_level,
    }
    for t in dispatch.deferred
],
```

Update `render_summary` and `render_last_run` in
[curate_render.py](src/lexibrary/services/curate_render.py) to show a short
breakdown (e.g. "Fixes by action:", grouped paths, or a `--verbose` flag that
prints the list). The data is already computed — it just needs to survive the
write.

### Priority 3 — Implement (or route away from) `autofix_validation_issue`

This is the architectural decision. Two viable paths:

**Option A — Implement the umbrella handler.**
Add `autofix_validation_issue` to
[consistency.py](src/lexibrary/curator/consistency.py) as a dispatcher that
inspects `item.source_item.check` and calls the appropriate deterministic
fixer. The risk taxonomy already declares several narrower low-risk handlers
that could be called from here:

- `resolve_slug_collision` ([risk_taxonomy.py:102](src/lexibrary/curator/risk_taxonomy.py#L102))
- `resolve_alias_collision` ([risk_taxonomy.py:107](src/lexibrary/curator/risk_taxonomy.py#L107))
- `remove_orphaned_reverse_dep` ([risk_taxonomy.py:99](src/lexibrary/curator/risk_taxonomy.py#L99))
- `remove_orphan_zero_deps` ([risk_taxonomy.py:117](src/lexibrary/curator/risk_taxonomy.py#L117))
- `remove_orphaned_aindex` ([risk_taxonomy.py:122](src/lexibrary/curator/risk_taxonomy.py#L122))

Caveat: those narrower actions are also only declared in the taxonomy — their
implementation status should be verified before routing to them.

**Option B — Classify at collection time.**
Move the `check`→`action_key` mapping into `_classify_validation` at
[coordinator.py:1266-1292](src/lexibrary/curator/coordinator.py#L1266-L1292)
so that validation items are assigned a specific action key (e.g.
`resolve_slug_collision`) at triage time. Then `autofix_validation_issue`
disappears entirely, and each fix goes through a handler whose implementation
state is explicit.

Option B is cleaner (no umbrella action means no hidden stub) but requires
knowing the full set of validator check names up front. Option A is easier
to land incrementally.

Either way, until this is done, the 109 `autofix_validation_issue`
classifications per run are wasted work.

### Priority 4 — Implement `consume_superseded_iwh`

Lower volume (3 items in this run) but same class of problem. Add the handler
to `consistency.py`, or wire it through `hook_runners.py` / IWH cleanup code
if that already exists.

### Priority 5 — Audit the taxonomy against reality

Every `function_ref` in
[risk_taxonomy.py](src/lexibrary/curator/risk_taxonomy.py) is a claim that an
implementation exists. Write a test (or a `lexictl` self-check) that imports
each `function_ref` and fails if the symbol cannot be resolved. This prevents
future drift where a new action key is added to the taxonomy and classified
in the coordinator, but the dispatcher silently routes it to the stub.

## Suggested order of work

1. Priority 1 (honest counters) — ~30 minutes, no design decisions, makes the
   problem visible.
2. Priority 2 (per-item dispatch detail in report) — ~1 hour, mostly
   mechanical, enormously improves debuggability.
3. Priority 5 (taxonomy self-check test) — ~30 minutes, catches this class of
   bug at CI time.
4. Priority 3 (implement `autofix_validation_issue`) — design decision
   required; scope depends on Option A vs Option B.
5. Priority 4 (implement `consume_superseded_iwh`) — small, can be done
   alongside Priority 3.

Priorities 1, 2, and 5 together would have turned a silent 112-no-op run into
a loud one and are worth doing even before the underlying handlers are
implemented.

---

## Appendix: Why the stubs were never implemented by "later groups"

The phrase *"All other action keys remain as stubs until their sub-agents are
implemented in later groups"* at
[coordinator.py:1545-1547](src/lexibrary/curator/coordinator.py#L1545-L1547)
pointed forward to work that was scoped but never wired. Tracing the three
archived OpenSpec changes shows this is **not** a simple "later groups forgot
to land the work" oversight — the detection/fix code for consistency issues
was actually built, but the **wiring layer between the coordinator's dispatch
phase and that code was never written**, and no subsequent change re-examined
the gap.

### What each curator change delivered

**[`curator-1`](openspec/changes/archive/2026-04-09-curator-1/) — Phase 1
(core loop).**

- The risk taxonomy spec at
  [curator-1/specs/curator-risk-taxonomy/spec.md](openspec/changes/archive/2026-04-09-curator-1/specs/curator-risk-taxonomy/spec.md)
  enumerates all 22 Low-risk action keys in full, including
  `autofix_validation_issue`, `consume_superseded_iwh`,
  `fix_broken_wikilink_exact`, `strip_unresolved_wikilink`,
  `resolve_slug_collision`, `resolve_alias_collision`,
  `add_missing_bidirectional_dep`, `remove_orphan_zero_deps`,
  `remove_orphaned_aindex`, `write_reactive_iwh`,
  `flag_unresolvable_agent_design`, and the rest.
- Group 2 (risk taxonomy) registered all 22 entries in
  [risk_taxonomy.py](src/lexibrary/curator/risk_taxonomy.py) with
  `function_ref` strings pointing to handlers that would be implemented later.
  Those `function_ref` strings became load-bearing claims — the taxonomy
  presents itself as a complete mapping, but the strings were aspirational.
- Group 6 (coordinator skeleton) explicitly scoped dispatch to return stubs.
  Task 6.5 in
  [curator-1/tasks.md](openspec/changes/archive/2026-04-09-curator-1/tasks.md)
  reads: *"Sub-agent calls are stubs returning `SubAgentResult` (actual BAML
  integration in later groups)."* This was the handshake — Group 6 would land
  stubs, Groups 9-12 would replace them.
- Group 9 (Phase 1a) delivered the Staleness Resolver. The coordinator's
  dispatcher was extended with an explicit `if item.action_key ==
  "regenerate_stale_design": return self._dispatch_staleness_resolver(item)`
  branch at
  [coordinator.py:1552-1553](src/lexibrary/curator/coordinator.py#L1552-L1553).
  This is the template the other groups were supposed to follow.
- **Group 10 (Phase 1b) is where it went wrong.** Tasks 10.1-10.8 in
  [curator-1/tasks.md](openspec/changes/archive/2026-04-09-curator-1/tasks.md)
  required creating `consistency.py` with a `ConsistencyChecker`, wikilink
  hygiene, slug/alias collision resolution, bidirectional dep repair,
  orphaned `.aindex` cleanup, orphan concept detection, convention/playbook
  staleness, and blocked IWH promotion. **All of those detection methods
  exist** — [consistency.py](src/lexibrary/curator/consistency.py) is
  608 lines and contains `check_wikilinks`, `detect_slug_collisions`,
  `detect_alias_collisions`, `check_bidirectional_deps`,
  `detect_orphaned_aindex`, `detect_orphaned_comments`,
  `detect_orphan_concepts`, `detect_stale_conventions`,
  `detect_stale_playbooks`, and `detect_promotable_iwh`.

  **But `ConsistencyChecker` is never imported or instantiated by the
  coordinator.** A project-wide grep for `ConsistencyChecker` turns up only
  [consistency.py](src/lexibrary/curator/consistency.py) itself and its unit
  test file [tests/test_curator/test_consistency.py](tests/test_curator/test_consistency.py).
  No production code calls it. The 608-line module is orphaned — it cannot
  be reached from `lexictl curate`.

  The reason is that none of the Group 10 subtasks (10.1 through 10.9) said
  anything like *"extend `_dispatch_to_stub` to route `autofix_validation_issue`
  (or the narrower action keys) to `ConsistencyChecker`"*. The tasks were
  decomposed as **"build the checker module + write unit tests for the
  checker module"**. The integration step — wiring the checker into the
  coordinator's dispatch path — was simply not an item on the list. Group 10
  was marked complete when all its numbered subtasks were checked off, but
  those subtasks never included the wiring step.

  Compounding this, the coordinator's `_classify_validation` method at
  [coordinator.py:1266-1292](src/lexibrary/curator/coordinator.py#L1266-L1292)
  hardcodes `action_key = "autofix_validation_issue"` for **every** validation
  item regardless of `item.source_item.check`. So even if `ConsistencyChecker`
  were wired in, individual validator checks would never flow to their
  corresponding narrow action keys — the umbrella key would still collapse
  everything. There is no mapping table from validator check name
  (`broken_wikilink`, `slug_collision`, etc.) to action key
  (`fix_broken_wikilink_exact`, `resolve_slug_collision`, etc.).

  A similar gap exists for `consume_superseded_iwh`: the classifier at
  [coordinator.py:1294-1307](src/lexibrary/curator/coordinator.py#L1294-L1307)
  assigns the action key, the taxonomy declares a handler at
  `curator.consistency.consume_superseded_iwh`, but no such function exists.
  The general IWH consume machinery at
  [iwh/reader.py:28 `consume_iwh()`](src/lexibrary/iwh/reader.py#L28) is
  never called from the curator.
- Group 11 (Phase 1.5a, comments) wired `integrate_sidecar_comments` end-to-end.
  Dispatcher branch at
  [coordinator.py:1562-1563](src/lexibrary/curator/coordinator.py#L1562-L1563).
  This is why that action is the only one of the 109+3+44 that actually runs.
- Group 12 (Phase 1.5b, reconciliation) wired `reconcile_agent_interface_stable`
  / `_changed` / `_extensive_content` end-to-end. Dispatcher branch at
  [coordinator.py:1555-1560](src/lexibrary/curator/coordinator.py#L1555-L1560).

So within curator-1, **two of the four Phase-1 sub-agents were integrated
(Staleness Resolver, Comment Curator, Reconciliation) and the third — the
Consistency Checker — was built but never integrated.** The decomposition
treated "write the module" and "wire the module into dispatch" as the same
task, and only the first half was listed.

**[`curator-2`](openspec/changes/archive/2026-04-09-curator-2/) — Phase 2
(deprecation lifecycle).**

- Scope was strictly additive: deprecation state machine, cascade analysis,
  migration execution, Stack post dedup. Group 7 (coordinator dispatch
  integration) wired the new deprecation action keys end-to-end — visible at
  [coordinator.py:1548-1550](src/lexibrary/curator/coordinator.py#L1548-L1550)
  (`_dispatch_deprecation` branch) and
  [coordinator.py:1929-2087](src/lexibrary/curator/coordinator.py#L1929-L2087).
- Curator-2 did **not** revisit any curator-1 action key. A grep for
  `autofix_validation_issue` and `consume_superseded_iwh` across the curator-2
  tasks/design/proposal files returns nothing. The change treated curator-1
  as complete.

**[`curator-3`](openspec/changes/archive/2026-04-09-curator-3/) — Phase 3
(budget, comment auditing, reactive hooks).**

- Scope was again strictly additive: budget trimmer, comment auditor, reactive
  hook runners. Group 5 (coordinator extensions) wired the new budget/audit
  action keys end-to-end — visible at
  [coordinator.py:1565-1571](src/lexibrary/curator/coordinator.py#L1565-L1571)
  (`_dispatch_budget_condense`, `_dispatch_comment_audit`).
- Curator-3 did not revisit curator-1 either. Same grep, same empty result.

### Root cause classification

Not a forward-reference deferral. The stub fallback in `_dispatch_to_stub` was
scoped to be temporary, but the work that would have retired it was never
itemised in any tasks.md file. Concretely, two things went wrong in curator-1
Group 10's task decomposition:

1. **Missing wiring task.** Tasks 10.1-10.9 cover detection, unit tests, and
   the blocked-IWH promotion flow, but no subtask says "extend the coordinator
   dispatcher to call `ConsistencyChecker` and translate its `FixInstruction`
   objects into filesystem writes via `atomic_write()`". The equivalent task
   for the Staleness Resolver (9.3) and the Comment Curator (11.4) was present
   in those groups and they landed end-to-end. Group 10 was missing its
   equivalent, so the checker shipped as orphan code.

2. **Missing validator→action_key mapping task.** Tasks 9.1-9.2 specified hash
   staleness ranking in triage, but nothing specified how *validation* items
   should be classified into action keys. The implementation picked the path
   of least resistance and assigned the umbrella `autofix_validation_issue`
   to every validation item, deferring the real mapping indefinitely. There
   was never a task saying "`_classify_validation` must inspect
   `item.source_item.check` and assign narrower action keys based on a lookup
   table defined here".

Curator-2 and curator-3 then compounded the problem by cleanly following the
pattern established by the parts of curator-1 that *had* landed end-to-end
(Staleness, Comment, Reconciliation, plus each phase's own new sub-agents)
and not noticing that the Consistency Checker was dead code. Because every
`lexictl curate` run reports `Fixed: N` without distinguishing stub successes,
there was no visible signal that `autofix_validation_issue` and
`consume_superseded_iwh` were no-ops.

Supporting evidence that this is an integration gap rather than an
intentionally-deferred task:

- The `function_ref` strings in the risk taxonomy point to functions that
  *do not exist*: `curator.consistency.autofix_validation_issue` and
  `curator.consistency.consume_superseded_iwh`. A deliberate deferral would
  either leave `function_ref` blank or point to a sentinel. The fact that
  they point to fully-qualified paths indicates someone intended the handlers
  to be written under those names.
- Most of the fixer logic that `autofix_validation_issue` would delegate to
  *does exist* — just not in a function called `autofix_validation_issue`.
  It lives as methods on `ConsistencyChecker`. The umbrella handler was
  meant to be a thin dispatcher over those methods. This is a 50-100 line
  integration, not a multi-day sub-agent build.
- The test coverage confirms the integration was never tested. The curator
  test suite mocks sub-agent responses; the one end-to-end validator
  round-trip test that would have caught this — "run curator, then rerun
  `lexi validate` and assert the issue count decreased" — is not present in
  any `test_curator/` or `test_cli/test_curate.py` file.

### Implication for the recommendations above

The work to retire the stubs is smaller than it looks. Priority 3 in the
recommendation list maps almost directly onto the integration task that
Group 10 should have had:

1. Add a `_dispatch_consistency_checker(item)` method on the coordinator,
   modelled on
   [`_dispatch_staleness_resolver`](src/lexibrary/curator/coordinator.py#L1588)
   and
   [`_dispatch_comment_integration`](src/lexibrary/curator/coordinator.py#L1692).
2. Route `autofix_validation_issue` (and any narrower keys picked up by a
   new `_classify_validation` mapping table) to it.
3. Translate each returned `FixInstruction` into the appropriate filesystem
   write by calling `write_design_file_as_curator()` from
   [`src/lexibrary/curator/write_contract.py`](src/lexibrary/curator/write_contract.py),
   which stamps `updated_by: curator`, recomputes hashes, serializes, and
   atomically writes per the canonical write contract
   (convention [CV-012 Design File Write Contract](.lexibrary/conventions/CV-012-design-file-write-contract.md)).
4. Implement `consume_superseded_iwh` either as a method on
   `ConsistencyChecker` or as a small standalone function that delegates to
   [`iwh.reader.consume_iwh`](src/lexibrary/iwh/reader.py#L28).

The ~608 lines of `ConsistencyChecker` detection code do not need to be
rewritten — they just need a dispatcher and a write layer on top of their
`FixInstruction` output.

