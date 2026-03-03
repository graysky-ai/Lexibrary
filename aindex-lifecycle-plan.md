# AIndex Lifecycle Plan

Companion to `design-lifecycle-plan.md`. These two artefact types work in conjunction — aindex provides directory-level navigation, design files provide file-level detail.

See `docs/user/artefact-lifecycle.md` for the question framework.

---

## Storage & Path Architecture

### Unified Mirror Tree

Both aindex and design files live under `.lexibrary/designs/`, which mirrors the source directory structure:

```
project/
  src/
    auth/
      login.py
      middleware.py
    cli/
      app.py
  .lexibrary/
    config.yaml
    designs/               ← unified mirror tree
      src/
        auth/
          .aindex          ← directory index for src/auth/
          login.py.md      ← design file for login.py
          middleware.py.md  ← design file for middleware.py
        cli/
          .aindex          ← directory index for src/cli/
          app.py.md        ← design file for app.py
        .aindex            ← directory index for src/
      .aindex              ← root-level directory index (scope root entry point)
    concepts/
    conventions/
    stack/
```

**Current state**: Design files already use `.lexibrary/designs/` (migrated in commit `e617921`). AIndex files still use `.lexibrary/<dir>/.aindex` — this plan fixes that.

### Path Computation

The `aindex_path()` function in `src/lexibrary/utils/paths.py` needs updating:

```
CURRENT:  .lexibrary/<rel-dir>/.aindex
TARGET:   .lexibrary/designs/<rel-dir>/.aindex
```

Both `mirror_path()` (design files) and `aindex_path()` (aindex) will share the `DESIGNS_DIR` constant, ensuring they always root from the same base.

### Scope Root Alignment

When the user configures `scope_root: "src/"` in the wizard:
- Only `src/` and its children are indexed
- The topmost `.aindex` is at `.lexibrary/designs/src/.aindex`
- The topmost design files are for files within `src/`
- Both artefact types start from the same folder within `.lexibrary/designs/`

Scope root controls **what gets indexed**, not the path structure. Paths are always relative to project root within the designs tree.

### Files That Need Updating (Path Migration)

| File | What Changes |
|------|-------------|
| `src/lexibrary/utils/paths.py` | `aindex_path()` adds `DESIGNS_DIR` to path computation. `iwh_path()` also migrates to `DESIGNS_DIR`. |
| `src/lexibrary/indexer/orchestrator.py` | Lines 58-59 hardcode `.lexibrary/<dir>/.aindex` — use `aindex_path()` from utils instead |
| `src/lexibrary/indexer/generator.py` | Line 60 hardcodes `.lexibrary/<dir>/.aindex` in `_get_dir_description()` — use `aindex_path()` |
| `src/lexibrary/archivist/pipeline.py` | Uses `aindex_path()` (line ~45) — will pick up the change automatically if using the utility |
| `src/lexibrary/validator/checks.py` | `find_missing_aindex()` (line ~743) — verify it resolves paths via `aindex_path()` |
| Tests | Any test that asserts `.aindex` output paths needs updating |

---

## 1. Initialization

**Decision**: Full crawl always runs (cheap, deterministic). Triggered by a new `lexictl bootstrap` command.

### The `lexictl bootstrap` Command

```
lexictl bootstrap [--full | --quick] [--scope <path>]
```

- **Purpose**: Generate all artefacts for the project. AIndex is always fully generated (cheap, deterministic). The `--full` vs `--quick` distinction only affects design files (not part of this plan).
- **Wizard integration**: The wizard calls `lexictl bootstrap` as its final step. If the user hasn't configured an API key or wants to change the LLM model, they can skip this step and run `lexictl bootstrap` manually later.
- **Idempotent**: Safe to re-run. Regenerates all aindex files. In `--quick` mode, skips design files that already exist and have a valid source_hash.
- **`--scope` override**: Defaults to `scope_root` from config. Allows one-off indexing of a different subtree.

### Bootstrap Behavior (AIndex Only)

1. Resolve scope root from config (or `--scope` flag)
2. Run bottom-up directory discovery (existing `_discover_directories_bottom_up`)
3. Generate `.aindex` for every discovered directory, writing to `.lexibrary/designs/<rel-dir>/.aindex`
4. Report stats: directories indexed, files found, errors

### New vs Existing Projects

- **Brand new project**: Few/no directories to index. First meaningful aindex appears when the user creates source structure. Not a concern — bootstrap is a no-op on an empty scope.
- **Existing project**: Full crawl is fast (filesystem only). Billboard quality starts as structural ("Directory containing Python source files") and improves as design files are created and enriched.

---

## 2. Creating New AIndex Files

**Decision**: Inline regeneration. AIndex is cheap enough to generate synchronously whenever a change is detected.

### Flow

1. Coding agent creates a new file or directory
2. PostToolUse hook runs after Write/Edit completes
3. Hook script:
   a. Resolves the parent directory of the affected file
   b. Calls `lexictl aindex-refresh <dir>` (or equivalent lightweight command)
   c. This regenerates the parent directory's `.aindex` in `.lexibrary/designs/`
   d. If a new subdirectory was created, generates its `.aindex` too
4. Agent continues without delay (aindex generation takes milliseconds)

### Safety Net

Post-commit git hook runs `lexictl update --changed-only`, which catches any directories whose listings changed since last index. Three layers:

1. **Immediate**: PostToolUse hook regenerates inline
2. **Guaranteed**: Post-commit hook catches anything the session missed
3. **Manual**: `lexictl bootstrap` re-indexes everything

### Key Point

AIndex creation never needs queueing — it's always fast enough to do synchronously. This is a fundamental difference from design files (which need LLM and are queued).

---

## 3. Maintaining AIndex Files

**Decision**: Full regeneration on every update (deterministic, no authored content to preserve).

- AIndex files contain no human-authored content — billboard, entries, and metadata are all computed from filesystem state + design file frontmatter.
- On each regeneration: re-scan directory listing, rebuild entries, recompute billboard, update metadata hashes.
- **Billboard enrichment**: When design files exist for child source files, the generator pulls their `description` frontmatter to produce richer billboards. This creates a natural dependency: aindex quality improves as design files are enriched. After `lexictl bootstrap --full` or background enrichment runs, a follow-up aindex regeneration picks up the richer descriptions.

**No comment/annotation layer for aindex** — all content is derived. There's nothing for agents to annotate.

---

## 4. Deprecating AIndex Files

**Decision**: Hard delete when directory is removed.

- AIndex files contain no authored content — no historical value to preserve.
- When `lexictl update` detects that a source directory no longer exists → delete its `.aindex` from `.lexibrary/designs/` immediately.
- Also clean up empty parent directories in the designs tree (avoid orphaned empty folders).
- No soft deprecation or archiving needed.
- **Rename handling**: If a directory is renamed, the old `.aindex` is deleted and a new one generated at the new path. No migration needed since aindex content is fully derivable.

### Orphan Detection

During `lexictl update` or `lexictl validate`:
1. Walk `.lexibrary/designs/` for `.aindex` files
2. For each, check if the corresponding source directory exists
3. If not → delete the `.aindex` (and clean up empty parent dirs in designs tree)

---

## 5. Reading and Using AIndex Files

> **DEFERRED**: This section will be implemented alongside the design file lifecycle plan. The hook injection and command integration for aindex and design files need to be designed together to get the tiered context model right.

**Decision**: Hybrid — automatic lightweight injection + agent-driven deep exploration.

### Tier 1 — Always injected (automatic via hooks)

- **Session start**: Root `.aindex` billboard + top-level directory summaries. Gives the agent a mental map of the project structure.
- Injected via SubagentStart hook or session-start context dump.
- **Token budget**: New `orientation_tokens: 300` field in `TokenBudgetConfig` (alongside existing `aindex_tokens: 200` which covers a single aindex file). The orientation budget covers root billboard + first-level directory summaries aggregated from multiple aindex files. Configurable via wizard step 6 alongside other budgets.

### Tier 2 — Injected on relevant activity (conditional hooks)

- **Directory access**: When agent reads/globs a directory → inject that directory's `.aindex` via PostToolUse hook on Read/Glob. Agent discovers what else is nearby.
- **No cooldown for now**: Subagents share sessions and aindex files are small (~200 tokens each). Re-injection is low cost. Revisit if context bloat becomes an issue in practice.

### Tier 3 — Agent-driven (commands, on demand)

- `lexi lookup <path>` — When given a file, includes sibling context from parent aindex. When given a directory, shows the full aindex with enriched descriptions from design files (no separate `lexi navigate` command).
- `lexi orient` — Project-wide orientation with directory tree and billboards.

### How AIndex Supports Design Files

| Agent Activity | AIndex Provides |
|---|---|
| Orienting to project | Root + top-level billboards |
| Finding the right directory | Directory billboards + child maps |
| Understanding a file's neighborhood | Sibling files from parent aindex |
| Understanding impact of a change | Other files in same directory that may be affected |

---

## Resolved Decisions

| Question | Decision | Rationale |
|----------|----------|-----------|
| `lexi navigate` as separate command? | No — fold into `lexi lookup` | `lookup <dir>` returns aindex; `lookup <file>` returns design file + siblings. One command, context-dependent. |
| Orientation token budget | New `orientation_tokens: 300` in `TokenBudgetConfig` | Root billboard (~10 tokens) + ~5-10 top-level dirs (~20 tokens each) = ~60-210 tokens. 300 gives headroom. Configurable via wizard step 6. |
| Tier 2 per-directory cooldown | No cooldown for now | Subagents share sessions, aindex files are small. Revisit if context bloat becomes a real problem. |
| `.iwh` files migrate to `designs/`? | Yes | Same mirror-tree pattern as aindex. `iwh_path()` updated alongside `aindex_path()` in the path migration. |
| `lexictl bootstrap` as new command? | Yes — new command | Distinct from `index` (which is aindex-only) and `update` (which is archivist pipeline). Bootstrap orchestrates both and is the wizard's final step. |
| §5 implementation timing | Deferred | Built alongside design file lifecycle. Hook injection for aindex and designs must be designed together. |
