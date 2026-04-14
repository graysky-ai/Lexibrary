# Curator order-of-operations: AST / graph freshness and stale-finding risk

**Scope.** Trace the order in which the curator reads and writes state, identify which
inputs can be stale when the curator begins, and enumerate the points where stale
inputs lead to propagated-but-incorrect findings. Starting point: AST must be
up-to-date *before* the curator begins.

## 1. Inputs the curator consults, ordered by freshness

| Input | Where it lives | Who rebuilds it | How the curator uses it |
|---|---|---|---|
| Raw source text | filesystem (`src/**`) | n/a (authoritative) | Re-read on every curator run |
| AST / interface skeleton | computed on-the-fly from source | `ast_parser.compute_hashes` / `parse_interface` | Recomputed inside `_collect_staleness` and `_collect_agent_edits` per-run — always fresh |
| Design file `source_hash` / `interface_hash` | frontmatter of `.lexibrary/designs/**/*.md` | `archivist.pipeline.update_file` (via `write_contract`) | Read to decide staleness by comparing against freshly-computed hashes |
| Design-file `design_hash` footer | `<!-- lexibrary:meta -->` block | `design_file_serializer.serialize_design_file` | Read by `change_checker.check_change` for the `AGENT_UPDATED` classifier |
| Sidecar comments (`*.comments.yaml`) | design dir siblings | agents | Counted in `_collect_comments`, integrated by comments sub-agent |
| `.aindex` files | every source dir | `archivist.pipeline.reindex_directories` | Not read directly by curator; consumed indirectly via validator |
| `TOPOLOGY.md` | project root | `archivist.pipeline.generate_raw_topology` | Not read by curator |
| Link graph (`.lexibrary/index.db`) | SQLite | `linkgraph.builder.build_index` | Read heavily (reverse_deps, orphan detection, bidirectional checks); **never rebuilt by the curator** |
| Symbol graph (`.lexibrary/symbols.db`) | SQLite | `symbolgraph.builder.build_symbol_graph` / `refresh_file` | **Not consulted by the curator at all** |

### Key invariant gap

The AST, interface skeleton, and file-level source hashes **are always recomputed at
the top of the collect phase**, so the curator's view of individual file content is
never stale. The LINK GRAPH, however, is read as-is from `.lexibrary/index.db` and is
only ever rebuilt as a side effect of the archivist pipeline. The curator can
therefore reach a state where:

- the on-disk source has been edited
- the design file still carries the old `source_hash` (detected → flagged stale, good)
- the link graph still records the *old* imports, wikilinks, and reverse-dep edges
  (undetected → used as truth by triage, consistency, deprecation checks)

This is the root of the "stale finding propagation" risk.

## 2. Pipeline sequence (single run)

`Coordinator.run` → `_acquire_lock` → `_run_pipeline`:

### Phase 0 — (missing) AST / graph refresh

**There is no Phase 0 today.** The coordinator relies on whatever state is on disk at
invocation time. `post_edit_hook` in [src/lexibrary/curator/hooks.py](src/lexibrary/curator/hooks.py)
invokes `Coordinator.run` directly after an editor event — it does *not* call
`archivist.pipeline.update_file` first. This means:

- source-hash staleness *is* still caught because `compute_hashes` is called fresh in
  `_collect_staleness` ([src/lexibrary/curator/coordinator.py:493](src/lexibrary/curator/coordinator.py#L493))
- but link graph drift is *not* caught; there is no equivalent "hash" for the graph

### Phase 1 — Collect ([coordinator.py:333-388](src/lexibrary/curator/coordinator.py#L333-L388))

Order is significant because later steps read items collected earlier and use the same
git / IWH scope sets:

1. `_uncommitted_files` (git porcelain)
2. `_active_iwh_dirs` (scan `.iwh` files, TTL filter)
3. `_collect_validation` — runs `validate_library()` end-to-end. This re-reads
   every artifact from disk and hits the link graph for cross-artifact checks
   (dangling links, orphan artifacts, bidirectional deps). **Link-graph-dependent
   validator checks inherit any graph staleness.**
4. `_collect_staleness` — iterates all design files, reads metadata, recomputes
   `(source_hash, interface_hash)` from source. Emits `CollectItem(source="staleness")`
   per drift. Always fresh.
5. `_collect_iwh` — directory-level signals.
6. `_collect_comments` — counts unprocessed sidecar comments.
7. `_collect_agent_edits` — recomputes hashes, runs
   `change_checker.check_change` which compares the design footer's `design_hash`
   against the serialized design-body hash on disk. Classifies `AGENT_UPDATED` based
   on `updated_by` frontmatter or missing footer.
8. `_check_link_graph` — availability probe only.
9. `_collect_deprecation_candidates` — opens a `LinkGraphSnapshot` via
   `snapshot_link_graph`. **All orphan / ttl_expired / stale-stack-post findings
   here depend on the link graph being current.**
10. `_collect_budget_issues` — reads design file token counts only.
11. `_collect_comment_audit_issues` — scans `src/**/*.py` for TODO/FIXME/HACK.
12. `_collect_consistency` — per-design wikilink hygiene, slug / alias collisions,
    bidirectional dep check, orphaned `.aindex`, orphaned `.comments.yaml`, stale
    conventions / playbooks, promotable blocked IWH, and (in `full` mode) domain-term
    suggestion + orphan concept detection. **`check_bidirectional_deps` and
    `detect_orphan_concepts` both lean on link-graph data.**

### Phase 2 — Triage ([coordinator.py:1393](src/lexibrary/curator/coordinator.py#L1393))

Pure Python classification + priority scoring. Priority for staleness, agent-edit,
and deprecation items adds `reverse_dep_count * 5` (or `* 2` for deprecation), and
`reverse_dep_count` comes from `_get_reverse_dep_count`, which opens the link graph
directly ([coordinator.py:1788](src/lexibrary/curator/coordinator.py#L1788)). **Priority
ordering therefore inherits link-graph staleness too.**

### Phase 3 — Dispatch ([coordinator.py:1807](src/lexibrary/curator/coordinator.py#L1807))

- autonomy gating + LLM-call budget
- `_route_to_handler` → sub-agent handler (staleness, reconciliation, comments,
  budget, auditing, consistency fix, deprecation, migration, iwh_actions)
- Sub-agents that mutate design files go through
  `write_contract.write_design_file_as_curator`, which **recomputes
  `source_hash`/`interface_hash` from the on-disk source** before writing. This
  guarantees the newly-written design is self-consistent, but it **does not trigger
  `build_index`, `reindex_directories`, or a symbol-graph refresh**. See
  [staleness.py:206](src/lexibrary/curator/staleness.py#L206) — the resolver writes
  the design file and returns; nothing downstream propagates.

### Phase 3b — Migration dispatch ([coordinator.py:2168](src/lexibrary/curator/coordinator.py#L2168))

Applies migration edits queued by the deprecation sub-agent. Uses
`linkgraph.query.open_index` but does not rebuild.

### Phase 3c — `_verify_after_sweep`

Re-runs `validate_library()` to compute a before/after delta. Purely observational.
Does **not** rebuild the link or symbol graph first, so the "after" figure is
computed against the same potentially-stale graph used for "before".

### Phase 4 — Report

Writes `.lexibrary/curator/report-*.json`. Pure output, no reads of live state.

## 3. Cross-file dependency hazards

The curator treats each file's design as an independent unit, but design files
depend on each other through three cached artefacts:

1. **Link graph edges** — `foo.py` imports `bar.py` is recorded in `index.db`. If
   `bar.py` deletes an exported symbol, `foo.py`'s design-file `dependencies` list is
   now wrong, yet `foo.py`'s own `source_hash` and `interface_hash` haven't changed.
   Today's staleness detector cannot see this.
2. **Design-file `dependents` / `dependencies` lists** — these are produced by the
   archivist LLM call and frozen at generation time. When B's interface changes, A's
   `dependents` block referencing B's old signature is silently wrong.
3. **Wikilinks in design bodies** — if a concept or another design file is renamed
   / deleted, the consistency checker catches it *only if* the link graph has been
   rebuilt since the rename.

The current pipeline has no mechanism to mark A as stale just because B changed.
Reverse-dep cascade is used for *priority boost*, not for staleness propagation.

## 4. Where stale findings leak

| Finding | Stale-input source | Failure mode |
|---|---|---|
| `TriageItem.priority` ordering | `_get_reverse_dep_count` → stale link graph | High-impact edits get processed in the wrong order; the cap on `max_llm_calls_per_run` can then defer the item that actually matters |
| `_collect_deprecation_candidates(orphan_zero_refs)` | `LinkGraphSnapshot.reverse_deps` | Active artifacts flagged as orphans (false deprecation), or genuinely orphaned artifacts missed |
| `_collect_deprecation_candidates(ttl_expired_zero_refs)` | same | Same risk, applied to hard-delete action keys → data loss |
| `_collect_consistency.check_bidirectional_deps` | design-file `dependencies` list (generated by archivist) | Phantom missing back-edges get emitted as `add_missing_bidirectional_dep` consistency fixes |
| `_collect_consistency.detect_orphan_concepts` | link-graph availability + reverse_deps | False "remove_orphan_zero_deps" suggestions |
| Validator checks that read the link graph (`dangling_links`, `orphan_artifacts`, `bidirectional_deps`) | link graph | Same as above, surfacing through `_collect_validation` |
| Symbol-based stale-stack-post detection | none today — symbol graph isn't consulted | Missing regression: the symbol graph knows exactly which symbol a stack post referenced, but the curator doesn't query it |
| `_verify_after_sweep` "after" delta | same stale graph as "before" | The delta looks like a win even when underlying graph drift masks new problems |

After a staleness / reconciliation dispatch rewrites a design file, these stale-graph
risks **persist for the remainder of the same run** because no step inside the
pipeline rebuilds the graph between dispatches.

## 5. Proposed insertion points (no code changes — design sketch)

### 5a. Phase 0: "prepare" step before `_collect`

Insert between `_acquire_lock` and `_collect`:

1. Walk the designs tree and compute `(source_hash, interface_hash)` for each
   source — the same work `_collect_staleness` does, but done once and cached on
   `self`.
2. If any drift is detected, run:
   - `linkgraph.builder.build_index(project_root, changed_paths=drifted)` — cheap
     incremental rebuild.
   - `symbolgraph.builder.refresh_file` for each drifted source (or fall back to
     `build_symbol_graph` above the 30% threshold).
3. Only then enter `_collect`. The cached hashes can be reused so `_collect_staleness`
   does not redo the work.

This guarantees every later phase reads a link/symbol graph that reflects what's on
disk *before* the curator decides anything.

### 5b. Post-dispatch graph refresh

After sub-agents that write design files finish their batch (before Phase 3b / 3c),
call `build_index` with the set of `DispatchResult.dispatched[].path` entries whose
outcome was `fixed`. This stops one dispatch's fix from contaminating the next
dispatch's priority / consistency reads.

The same argument applies to `_verify_after_sweep` — it should refresh first, so the
"after" validator run measures reality, not the stale graph.

### 5c. `post_edit_hook` should bootstrap through the archivist

Rather than jumping straight to `Coordinator.run`, the reactive hook chain should
be:

```
run_post_edit
  → archivist.pipeline.update_file (regenerates design, refreshes symbol graph)
  → linkgraph.builder.build_index(changed_paths=[file])
  → Coordinator.run(scope=file, trigger="reactive_post_edit")
```

That matches what `lexictl update` does for batch runs and makes the reactive path
obey the same invariant.

### 5d. Cross-file staleness propagation

The harder structural fix: add a `dependents_hash` (or similar) to design frontmatter
so a file's design is considered stale when any of its *declared* dependencies'
interfaces have changed. Collect phase would then flag B's design when A's interface
hash moves, not just when B's own source changes. This is a deeper change and should
be proposed as its own OpenSpec change, not bundled with the pre-phase refresh.

## 6. TL;DR ordering recommendation

1. Lock.
2. **Refresh AST-derived state** (hashes, link graph, symbol graph) for everything
   that drifted since last build.
3. Collect — now reads fresh state everywhere.
4. Triage.
5. Dispatch batch → refresh link graph for touched files → dispatch next batch (if we
   ever introduce batching).
6. Refresh once more before `_verify_after_sweep`.
7. Report.

Today only step 3 (partially) and step 7 are honored; steps 2, 5, and 6 are missing
and are the reason stale findings can propagate.
