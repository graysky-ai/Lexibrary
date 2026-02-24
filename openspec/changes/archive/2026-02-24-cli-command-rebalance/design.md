## Context

The `lexi`/`lexictl` CLI split (Phase 8a) separated commands by intent: `lexi` for agent-facing day-to-day operations, `lexictl` for setup and maintenance. The dividing principle was agent safety — preventing agents from triggering expensive LLM operations or infrastructure mutations.

In practice, the split has a few misalignments:

1. **`lexi index`** generates `.aindex` infrastructure files. While fast and deterministic (no LLM), it's a maintenance/generation operation that agents don't need during normal coding sessions. Agents *consume* `.aindex` files; they don't need to produce them.

2. **`lexictl validate` and `lexictl status`** are read-only inspection commands blocked from agents by the blanket "never run `lexictl`" rule. The `library-status` spec already references `lexi status` in 6 of 7 requirements, and the orient skill already calls `lexi status` — but the implementation puts both on `lexictl`.

3. **Index regeneration is manual-only**. There's no automated path to keep `.aindex` files fresh. The post-commit hook runs `lexictl update --changed-only` but doesn't regenerate indexes.

The `agent-navigation` change (just completed) added `lexi help` with command reference text that must be updated to reflect any command movements.

## Goals / Non-Goals

**Goals:**

- Move `index` from `lexi` to `lexictl` so agents cannot accidentally trigger infrastructure generation
- Add `validate` and `status` to `lexi` so agents can inspect library health during sessions
- Automate `.aindex` regeneration via hooks and sweep so manual indexing is rarely needed
- Update `lexi help` content, agent rules, and `lexi --help` to reflect the rebalanced commands
- Maintain backward compatibility for `lexictl validate` and `lexictl status` (they stay on `lexictl` too)

**Non-Goals:**

- Changing the underlying validation/status logic (just exposing it on `lexi`)
- Removing `lexictl validate` or `lexictl status` (both CLIs keep them)
- Changing `lexi describe` placement (it's an annotation command, correctly on `lexi`)
- Rewriting the indexer internals (just changing where/when it runs)
- Making `lexi index` a deprecated alias (clean break, no shims)

## Decisions

### D-1: Shared command registration via helper functions

**Choice:** Extract validate/status command logic into shared helpers in `_shared.py`, called from thin wrappers in both `lexi_app.py` and `lexictl_app.py`.

**Alternatives considered:**
- *Duplicate implementations* — violates DRY, risks drift
- *Single registration on both apps* — Typer doesn't natively support registering one command on multiple apps

**Rationale:** The validate and status logic already lives in library modules (`lexibrary.validator`, `lexibrary.status`). The CLI wrappers just parse args, call the library, and render output. Shared helpers keep this thin layer DRY while allowing each CLI to register with its own app and CLI-specific prefix (e.g., `lexi:` vs `lexictl:` in quiet mode).

### D-2: Index automation via update pipeline integration

**Choice:** Integrate `.aindex` regeneration as the final step of `update_project()` in the archivist pipeline. After design files are generated/refreshed, re-index directories that contained changed files.

**Alternatives considered:**
- *Separate `lexictl index` call in hook script* — makes hook script more complex; easy to get directory list wrong in shell
- *Post-step in DaemonService._run_sweep only* — misses the hook flow

**Rationale:** Both the hook (`update --changed-only`) and sweep (`run_once/run_watch`) ultimately call `update_project()`. Integrating index regeneration there means every update path gets fresh indexes automatically. The pipeline already tracks which files were processed, so it knows which directories need re-indexing.

### D-3: Targeted directory re-indexing, not full recursive

**Choice:** After an update, only re-index directories that contained updated files (plus their parent directories up to scope_root, since parent `.aindex` files reference child summaries).

**Alternatives considered:**
- *Full recursive re-index on every update* — too slow for large projects in the hook path
- *Only re-index exact directories* — misses stale parent summaries

**Rationale:** The hook path must be fast (runs in background after every commit). Re-indexing only affected directories plus ancestors keeps the scope proportional to the change size. The ancestor walk ensures parent `.aindex` child maps stay accurate.

### D-4: `lexictl index` keeps identical interface

**Choice:** `lexictl index [directory] [-r/--recursive]` has the same interface as the old `lexi index`. The command function moves from `lexi_app.py` to `lexictl_app.py` with no behavioral changes.

**Rationale:** Users (humans, CI scripts) who need manual indexing get the same interface. The only change is the CLI prefix.

### D-5: `lexi help` restructuring

**Choice:** Restructure the help command's "Available Commands" panel:
- Rename "Indexing & Maintenance" → "Inspection & Annotation"
- Contents: `lexi status`, `lexi validate`, `lexi describe`
- Replace workflow 4 ("Index a new directory") → "Check library health" using `lexi status` and `lexi validate`

**Rationale:** The help text must reflect actual available commands. With `index` moved out and `status`/`validate` moved in, the section name and contents change. "Inspection & Annotation" captures the new character — agents inspect health and annotate (describe) directories.

### D-6: Agent rules — keep "never run lexictl" prohibition

**Choice:** The core rules continue to say "Never run `lexictl` commands." Add `lexi validate` to the "After Editing Files" section as a recommended post-edit check.

**Alternatives considered:**
- *Soften to "avoid lexictl unless needed"* — introduces ambiguity; agents might call expensive operations
- *List specific prohibited commands* — fragile, grows with each new `lexictl` command

**Rationale:** The blanket prohibition is simple and safe. Now that validate and status are on `lexi`, agents have everything they need without ever touching `lexictl`. The orient skill already references `lexi status` — no change needed there.

## Risks / Trade-offs

**[Breaking change: `lexi index` removal]** → Agents, scripts, or CI jobs calling `lexi index` will break. **Mitigation:** Update agent rules (this change), document in changelog. The migration is mechanical: `lexi index` → `lexictl index`. Most use cases are replaced by automated indexing anyway.

**[Index regeneration in update pipeline adds latency]** → Each `update --changed-only` call now also re-indexes. **Mitigation:** Re-indexing is fast (no LLM, just file reading). For a typical 5-file commit, re-indexing ~5 directories + ancestors takes <1s. The hook runs in the background so it doesn't block the developer.

**[Dual CLI registration for validate/status increases maintenance surface]** → Two wrappers per command that must stay in sync. **Mitigation:** Shared helpers ensure the actual logic is in one place. The wrappers are <10 lines each (arg parsing → call helper → render).

**[Depends on agent-navigation change]** → The `lexi help` content modifications require the agent-navigation change to be merged first. **Mitigation:** Sequence this change after agent-navigation. If help command doesn't exist yet at implementation time, create it as part of this change.

## Migration Plan

1. Add shared helpers for validate/status to `_shared.py`
2. Register `validate` and `status` on `lexi_app` (using shared helpers)
3. Move `index` command from `lexi_app` to `lexictl_app`
4. Integrate index regeneration into `update_project` pipeline
5. Update `lexi help` content
6. Update agent rule templates (`base.py`, Claude/Cursor/Codex generators)
7. Update/add tests for all moved/new registrations
8. Update blueprints for modified source files

**Rollback:** Revert the command registrations. The underlying modules (validator, status, indexer) are unchanged, so rollback is a pure CLI-layer revert.

## Open Questions

- Should `lexictl index` also be added to the hook script as a fallback for cases where the pipeline integration misses directories? (Lean: no — keep the hook simple, rely on `lexictl sweep` to catch any gaps.)
- Should the `library-status` spec's first requirement (which says `lexictl status`) be corrected to say `lexi status`? (Lean: yes — it's inconsistent with the other 6 requirements in the same spec.)
