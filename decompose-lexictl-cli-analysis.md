# Decompose Lexictl CLI — Analysis

**Date:** 2026-03-28
**Status:** Analysis — decisions resolved.

---

## Problem

The `lexictl` CLI (`lexictl_app.py`, 1,166 lines) contains inline stat rendering, orchestration logic, and domain utilities that could be extracted into service/render modules. While less severe than the `lexi` decomposition (most core business logic already delegates to `archivist.pipeline`, `indexer.orchestrator`, `lifecycle.bootstrap`, etc.), the remaining inline code has three problems:

- **Stat rendering duplication** — `update` and `bootstrap` both contain 50-90 line blocks of inline stat formatting that follow similar patterns but can't be reused or tested independently
- **Domain logic in CLI handlers** — `_has_changes()` (filesystem scanning), `iwh_clean` (TTL cleanup), and `sweep` (watch loop) contain logic that belongs in service or domain modules
- **Backlog gate** — the BACKLOG.md dependency gate (line 235) blocks all CLI modifications until decomposition is complete; planned features like `lexictl diff`, `lexictl metrics`, and `lexictl export` cannot proceed

**Goal:** Extract inline stat rendering and domain logic from CLI handlers into service/render/domain modules, leaving `lexictl_app.py` as a thin orchestration shell. Follow the patterns established in the `lexi` decomposition and the `cli-service-extraction-pattern` convention.

---

## Current State

### Comparison with lexi decomposition

The `lexi` decomposition extracted ~1,205 lines of **data-gathering business logic** (lookup, orient, impact, status, describe) that was entirely inline. `lexictl` is structurally different — its commands already delegate core business logic to existing modules:

| lexi pattern (pre-decomposition) | lexictl pattern (current) |
|---|---|
| CLI handler gathers data inline | CLI handler calls existing pipeline/indexer/bootstrap modules |
| No dataclass for results | Results already returned as `UpdateStats`, `IndexStats`, etc. |
| Rendering mixed with data gathering | Rendering mixed with orchestration |

The extractable content in lexictl is therefore predominantly **stat rendering** and **domain utilities**, not data-gathering logic.

### Line counts and logic placement

| Command | Lines | Inline logic? | Notes |
|---------|-------|---------------|-------|
| `update` | ~351 | **Heavy** | Largest command; 6 execution branches (--skeleton, --topology, --dry-run, --changed-only, single file, full project), ~90 lines of stat rendering, lifecycle/queue stats, IWH cleanup |
| `bootstrap` | ~157 | **Medium** | 3-phase orchestration (index, design files, topology), ~45 lines stat rendering |
| `init` | ~103 | **Medium** | Wizard orchestration, rule generation, hook installation, post-init update (~25 lines duplicates `update` setup) |
| `setup` | ~97 | **Medium** | Hook installation, rule generation, environment validation |
| `sweep` + `_has_changes` | ~112 | **Medium** | Watch mode loop with signal handling, filesystem change detection |
| `iwh_clean` | ~63 | **Medium** | TTL-based signal cleanup; partially duplicates `iwh.cleanup.iwh_cleanup` |
| `index` | ~61 | **Light** | Path validation + delegation to `index_directory`/`index_recursive` |
| `maintainer_help` | ~53 | **None** | Static help text |
| `validate` | ~50 | **None** | Thin delegation to `_run_validate` |
| `status` | ~20 | **None** | Already delegates to `services/status` (completed in lexi decomposition) |

### What already works well

- **`status`** already follows the service pattern (delegates to `collect_status()` from `services/status.py`)
- **`validate`** delegates to `_run_validate` (shared with lexi)
- **Core business logic** is in appropriate domain modules: `archivist.pipeline.update_project()`, `indexer.orchestrator.index_recursive()`, `lifecycle.bootstrap.bootstrap_quick()`
- **Result dataclasses** already exist: `UpdateStats`, `IndexStats`, `BootstrapStats`
- **Test coverage** is strong (2,543 lines, 129 tests in `test_lexictl.py`)
- **`iwh.cleanup`** already has a proper `CleanupResult` dataclass and `iwh_cleanup()` function

### Existing plans that interact

- **`plans/BACKLOG.md` line 240** — "Refactor and functional decomposition of `lexictl` CLI" is listed as high priority / planned, prerequisite for all other `lexictl` CLI changes
- **`plans/BACKLOG.md` line 235** — Dependency gate: all CLI modifications blocked until decomposition complete
- **`plans/shelved/mcp-server.md`** — MCP server exposes `lexi` commands as tools; lexictl extraction is lower priority for MCP but maintains consistency
- **`decompose-lexi-cli-analysis.md`** — The completed lexi decomposition established the patterns this analysis follows

---

## Dependency Analysis

### `lexictl_app.py` — internal call graph

```
update() [command, 351 lines]
  ├─ --skeleton branch → _generate_quick_design(), queue_for_enrichment()
  ├─ --topology branch → generate_raw_topology()
  ├─ --dry-run branch → dry_run_files(), dry_run_project()
  │    └─ [inline dry-run result rendering, ~35 lines]
  ├─ --changed-only branch → update_files()
  │    └─ [inline stat rendering, ~25 lines]
  ├─ single file branch → update_file()
  ├─ directory/project branch → update_directory(), update_project()
  │    ├─ _progress_callback() [closure, inline]
  │    └─ [inline stat rendering, ~90 lines]
  │         ├─ update summary (scanned/unchanged/created/updated/failed)
  │         ├─ lifecycle stats (renames, deprecations, TTL deletions)
  │         ├─ enrichment queue stats
  │         ├─ error summary rendering
  │         └─ IWH cleanup → iwh_cleanup()

bootstrap() [command, 157 lines]
  ├─ Phase 1: index_recursive() + _index_progress() [closure]
  ├─ Phase 2: bootstrap_quick() or bootstrap_full() + _design_progress() [closure]
  │    └─ [inline stat rendering, ~30 lines]
  └─ Phase 3: generate_raw_topology()

init() [command, 103 lines]
  ├─ Re-init guard + TTY detection
  ├─ render_banner()
  ├─ run_wizard()
  ├─ create_lexibrary_from_wizard()
  ├─ generate_rules() [inline rendering]
  ├─ install_post_commit_hook(), install_pre_commit_hook()
  └─ Post-init update offer [interactive, ~25 lines]
       └─ asyncio.run(update_project()) [duplicates update setup]

setup() [command, 97 lines]
  ├─ --hooks branch → install_post_commit_hook(), install_pre_commit_hook()
  ├─ --update branch
  │    ├─ generate_rules() [inline rendering]
  │    └─ ensure_iwh_gitignored()
  └─ no-flag branch → usage text

sweep() [command, 72 lines]
  ├─ _run_single_sweep() [closure]
  │    └─ asyncio.run(update_project())
  └─ watch mode → threading.Event loop + signal handlers
       └─ _has_changes() [private helper, 40 lines]

iwh_clean() [command, 63 lines]
  ├─ find_all_iwh()
  ├─ TTL threshold determination (--all / --older-than / config)
  └─ [inline file deletion + age calculation, ~25 lines]
```

### External modules consumed by inline logic

| Function group | External modules used (deferred imports) |
|---|---|
| **update** | `archivist.pipeline` (UpdateStats, dry_run_files, dry_run_project, update_file, update_files, update_directory, update_project), `archivist.service`, `config.loader`, `llm.client_registry`, `llm.rate_limiter`, `lifecycle.bootstrap._generate_quick_design`, `lifecycle.queue`, `archivist.topology`, `iwh.cleanup`, `errors` |
| **bootstrap** | `config.loader`, `indexer.orchestrator`, `lifecycle.bootstrap`, `llm.client_registry`, `archivist.topology`, `errors` |
| **init** | `init.scaffolder`, `init.wizard`, `cli.banner`, `init.rules`, `hooks.post_commit`, `hooks.pre_commit`, `archivist.pipeline`, `archivist.service`, `config.loader`, `llm.client_registry`, `llm.rate_limiter` |
| **setup** | `config.loader`, `init.rules`, `hooks.post_commit`, `hooks.pre_commit`, `iwh.gitignore` |
| **sweep** | `archivist.pipeline`, `archivist.service`, `config.loader`, `llm.client_registry`, `llm.rate_limiter`, `utils.paths` |
| **iwh_clean** | `config.loader`, `iwh.reader` (find_all_iwh, IWH_FILENAME), `utils.paths` |

### Who imports from `lexictl_app.py` externally

Only `lexictl_app` (the Typer instance) is imported by other production code (`cli/__init__.py`). No external code imports private functions.

### Test direct imports

No test files directly import private functions from `lexictl_app.py`. All 129 tests use CliRunner. The only direct reference is a mock target:
- `test_lexictl.py` line 1245: `patch("lexibrary.cli.lexictl_app._has_changes", return_value=False)` — must be updated when `_has_changes` moves.

### Duplication: `iwh_clean` CLI vs `iwh.cleanup.iwh_cleanup`

| Aspect | `iwh_clean` CLI (lexictl_app.py) | `iwh_cleanup()` (iwh/cleanup.py) |
|---|---|---|
| Discovery | `find_all_iwh()` from `iwh.reader` | `rglob(IWH_FILENAME)` under `.lexibrary/designs/` |
| TTL source | CLI flags (--all, --older-than) or config | `ttl_hours` parameter |
| Orphan detection | No | Yes |
| Unparseable handling | No (skips implicitly) | Yes (treats as expired) |
| Result type | Prints directly, returns count | Returns `CleanupResult` dataclass |
| --all mode | Bypasses TTL entirely | Not supported |

The CLI version is less robust (no orphan detection, no unparseable handling) and doesn't return structured data. Consolidation should extend `iwh.cleanup` to support the `--all` and `--older-than` use cases.

### Test coverage summary

| Test file | Lines | Tests | Covers |
|---|---|---|---|
| `test_cli/test_lexictl.py` | 2,543 | 129 | All maintainer CLI commands (init, update, bootstrap, index, validate, status, setup, sweep, iwh clean, help) |
| **Total** | **2,543** | **129** | |

Testing approach: exclusively black-box via Typer's `CliRunner`. No direct imports of private functions.

---

## Proposed Phases

Each phase extracts one logical unit, includes tests, and leaves the CLI fully functional.

### Phase 0: Already complete (from lexi decomposition)

`src/lexibrary/services/__init__.py` and `tests/test_services/__init__.py` already exist.

### Phase 1: Extract update stat rendering → `services/update_render.py`

**Risk: Low** — pure formatting extraction, no logic changes

The `update` command contains ~105 lines of inline stat rendering spread across multiple branches (--changed-only, single file, directory/project). All branches render `UpdateStats` in similar patterns.

**Render module** (`services/update_render.py`) — extract from `lexictl_app.py`:
- `render_update_summary(stats, project_root)` → update summary block (scanned/unchanged/created/updated/agent-updated/failed)
- `render_lifecycle_stats(stats)` → lifecycle block (renames, deprecations, TTL deletions)
- `render_enrichment_queue(stats)` → enrichment queue block
- `render_dry_run_results(results, project_root)` → dry-run preview table with summary line
- `render_failed_files(stats, project_root)` → failed file list with relative paths

No new service module — `UpdateStats` already lives in `archivist.pipeline`.

**CLI handler** (`lexictl_app.py update()`) becomes:
```python
# After pipeline call:
info(render_update_summary(stats, project_root))
if has_lifecycle_stats(stats):
    info(render_lifecycle_stats(stats))
if has_enrichment_queue(stats):
    info(render_enrichment_queue(stats))
```

**Test:** `tests/test_services/test_update_render.py` — unit tests with mock `UpdateStats` instances verifying rendered string content. All existing CLI tests pass.

**Lines moved:** ~105 lines out of `lexictl_app.py`

### Phase 2: Extract sweep logic → `services/sweep.py`

**Risk: Low** — self-contained, clean extraction boundary

**Service module** (`services/sweep.py`) — extract from `lexictl_app.py`:
- `_has_changes()` → `has_changes(root, last_sweep, lexibrary_dir=LEXIBRARY_DIR) -> bool`
- `run_single_sweep(project_root, config) -> UpdateStats` — encapsulates rate limiter + registry + archivist setup + `update_project()` call
- `run_sweep_watch(project_root, config, *, interval, skip_unchanged, on_complete, on_skip, on_error, shutdown_event)` — watch loop with callback hooks for output

The watch loop uses callbacks (`on_complete`, `on_skip`, `on_error`) instead of calling `info()`/`error()` directly, keeping the service module CLI-free per the convention.

**CLI handler** (`lexictl_app.py sweep()`) becomes:
```python
if not watch:
    if skip_unchanged and not has_changes(project_root, 0.0):
        info("No changes detected -- skipping sweep.")
        return
    stats = run_single_sweep(project_root, config)
    info(render_sweep_summary(stats))
    return

run_sweep_watch(
    project_root, config,
    interval=config.sweep.sweep_interval_seconds,
    skip_unchanged=config.sweep.sweep_skip_if_unchanged,
    on_complete=lambda stats: info(render_sweep_summary(stats)),
    on_skip=lambda: info("No changes detected -- skipping sweep."),
    on_error=lambda exc: error(f"Sweep failed: {exc}"),
    shutdown_event=shutdown_event,
)
```

**Test:** `tests/test_services/test_sweep.py` — unit tests for `has_changes()` with temporary directories, mock tests for `run_single_sweep()`. Update mock target in `test_lexictl.py` from `lexibrary.cli.lexictl_app._has_changes` to `lexibrary.services.sweep.has_changes`.

**Lines moved:** ~112 lines out of `lexictl_app.py`

### Phase 3: Consolidate iwh_clean → extend `iwh/cleanup.py`

**Risk: Low** — extending an existing module, not creating a new one

The `iwh_clean` CLI command partially duplicates `iwh.cleanup.iwh_cleanup()` with a different discovery mechanism and fewer safety checks (no orphan detection, no unparseable handling). Rather than creating a new service module, extend the existing `iwh.cleanup` module.

**Extend** `iwh/cleanup.py`:
- Add `iwh_manual_clean(project_root, *, ttl_hours=None, remove_all=False) -> CleanupResult` — supports `--all` mode (bypass TTL) and custom `--older-than` threshold
- Reuse `CleanupResult` and `CleanedSignal` dataclasses (add a `"manual"` reason value)
- Discovery via `find_all_iwh()` to match the CLI's current behaviour
- Include orphan detection and unparseable handling (improving on current CLI behaviour)

**CLI handler** (`lexictl_app.py iwh_clean()`) becomes:
```python
result = iwh_manual_clean(project_root, ttl_hours=ttl_threshold, remove_all=all_signals)
for signal in result.expired:
    info(f"  Removed {signal.source_dir}/ ({signal.scope})")
info(f"\nCleaned {len(result.expired) + len(result.orphaned)} signal(s)")
```

**Test:** Add tests to `tests/test_iwh/test_cleanup.py` for the new `iwh_manual_clean()` function. Existing `lexictl iwh clean` CLI tests pass.

**Lines moved:** ~35 lines out of `lexictl_app.py` (CLI keeps arg handling + rendering). ~25 lines added to `iwh/cleanup.py`.

### Phase 4: Extract bootstrap rendering → `services/bootstrap_render.py`

**Risk: Low** — same pattern as Phase 1

**Render module** (`services/bootstrap_render.py`) — extract from `lexictl_app.py`:
- `render_index_summary(index_stats)` → Phase 1 (indexing) summary
- `render_bootstrap_summary(design_stats)` → Phase 2 (design files) summary with error list
- Progress callback signature type for consistency

No new service module — `IndexStats` lives in `indexer.orchestrator`, `BootstrapStats` in `lifecycle.bootstrap`.

**Test:** `tests/test_services/test_bootstrap_render.py`. Existing CLI tests pass.

**Lines moved:** ~45 lines out of `lexictl_app.py`

### Phase 5: Slim down init and setup

**Risk: Low** — mechanical extraction of repeated patterns

**Init:** Extract the post-init update block (lines 114-141) into a helper. This block duplicates the archivist pipeline setup from `update`. Create:
- `_run_post_init_update(project_root, config)` as a private function in `lexictl_app.py` (not a service — it's CLI-specific interactive logic with `input()`)

**Setup:** The `setup` command is orchestration of existing modules (`generate_rules`, `install_*_hook`, `ensure_iwh_gitignored`). No service extraction needed — the logic is already in domain modules. Minor cleanup only:
- Extract the hook installation rendering pattern (shared between `init` and `setup`) into a small helper

**Lines moved:** ~30 lines reorganised within `lexictl_app.py` (internal helpers, not new modules)

### Phase 6: Clean up and verify

**Risk: Low** — mechanical cleanup after all extractions

- Remove dead imports from `lexictl_app.py`
- Verify `lexictl_app.py` final structure: Typer app setup, thin command handlers
- Remove the `_has_changes` private function (moved to `services/sweep.py` in Phase 2)
- Update `plans/BACKLOG.md` to mark lexictl decomposition as resolved
- Verify `_shared.py` is unchanged (retains `require_project_root`, `stub`, `load_dotenv_if_configured`, `_run_validate`)

**Test:** Full test suite (`uv run pytest --cov=lexibrary`). Verify no coverage regression.

---

## Decisions (Resolved)

### 1. Module layout → **Same `services/` package**

Extracted lexictl modules go in `src/lexibrary/services/` alongside lexi service modules. The two-CLI separation is a CLI concern, not a service concern — service modules don't know which CLI calls them. This follows the `cli-service-extraction-pattern` convention exactly.

Layout additions to `services/`:
- `update_render.py` (Phase 1)
- `sweep.py` (Phase 2)
- `bootstrap_render.py` (Phase 4)

Note: no new service data modules — `UpdateStats`, `IndexStats`, and `BootstrapStats` already live in their respective domain packages.

### 2. `_run_validate` → **Leave in `_shared.py`**

Consistent with the lexi decomposition decision. It's a thin orchestrator, not business logic. Re-evaluate if/when a programmatic validation API is needed.

### 3. `iwh_clean` → **Extend existing `iwh/cleanup.py`**, not new service module

The cleanup logic belongs in the IWH domain package, not `services/`. The existing `iwh.cleanup` module already has the right dataclasses and patterns. Extending it is more natural than creating `services/iwh_clean.py`.

### 4. `init` / `setup` → **Minimal extraction**

These commands are inherently interactive/orchestrative. They call existing domain modules and render results. Forcing them into the service pattern would create thin wrappers around thin wrappers. Internal cleanup (shared helpers) is sufficient.

### 5. Render-only modules are valid

Unlike the lexi decomposition where each extraction produced a service + render pair, several lexictl extractions produce **render modules only** (Phases 1 and 4). This is correct per the convention — the service module is optional when the data already lives in an existing domain module. The render module's job is to format existing dataclasses for terminal output.

---

## Risk Mitigation

- **Phase boundaries are test boundaries** — full `pytest` run after each phase before starting the next
- **No behaviour changes** — each phase is a pure refactor; CLI output must be identical before and after
- **Smaller blast radius than lexi decomposition** — fewer lines moved, no test import rewiring (only one mock target update in Phase 2)
- **Existing modules extended, not replaced** — Phase 3 extends `iwh/cleanup.py` rather than creating a parallel implementation
- **129 CLI tests are the safety net** — all via CliRunner, so internal reorganisation is invisible to them

---

## Estimated Scope

| Phase | Lines moved | New files created | Existing files modified | Risk |
|-------|-------------|-------------------|------------------------|------|
| 0. scaffold | 0 | — (already done) | — | None |
| 1. update render | ~105 | `services/update_render.py`, `tests/test_services/test_update_render.py` | `lexictl_app.py` | Low |
| 2. sweep | ~112 | `services/sweep.py`, `tests/test_services/test_sweep.py` | `lexictl_app.py`, `test_lexictl.py` (1 mock target) | Low |
| 3. iwh consolidation | ~35 | `tests/test_iwh/test_cleanup.py` (extend) | `iwh/cleanup.py`, `lexictl_app.py` | Low |
| 4. bootstrap render | ~45 | `services/bootstrap_render.py`, `tests/test_services/test_bootstrap_render.py` | `lexictl_app.py` | Low |
| 5. init/setup cleanup | ~30 | — | `lexictl_app.py` (internal helpers) | Low |
| 6. cleanup | 0 (deletes) | — | `lexictl_app.py`, `BACKLOG.md` | Low |

**Total:** ~327 lines extracted. 5 new files (2 render modules + 1 service module + 3 test files).

**Not extracted** (already follows target pattern or too thin):
- `validate` — delegates to `_run_validate` in `_shared.py`
- `status` — delegates to `services/status.collect_status()` (done in lexi decomposition)
- `index` — thin CLI validation + delegation to `indexer.orchestrator`
- `maintainer_help` — static text, no logic

**Post-decomposition file sizes:**
- `lexictl_app.py`: ~840 lines (down from 1,166) — Typer setup, thin command handlers, internal helpers for init/setup
- `iwh/cleanup.py`: ~170 lines (up from 134) — extended with `iwh_manual_clean()`
- `_shared.py`: unchanged (~170 lines)

**Files modified (not created):**
- `src/lexibrary/cli/lexictl_app.py` — remove extracted logic, add service/render imports
- `src/lexibrary/iwh/cleanup.py` — add `iwh_manual_clean()` function
- `tests/test_cli/test_lexictl.py` — update 1 mock target (`_has_changes` path)
- `plans/BACKLOG.md` — mark lexictl decomposition as resolved

---

## Comparison with Lexi Decomposition

| Dimension | Lexi decomposition | Lexictl decomposition |
|---|---|---|
| Starting size | 1,308 lines | 1,166 lines |
| Post-decomposition | ~300-350 lines | ~840 lines |
| Lines extracted | ~1,205 | ~327 |
| New service modules | 5 (lookup, orient, impact, status, describe) | 1 (sweep) |
| New render modules | 4 (lookup, orient, impact, status) | 2 (update, bootstrap) |
| Test import rewiring | 4 direct imports | 1 mock target |
| Core issue | Business logic inline in CLI | Stat rendering + domain utilities inline |

The asymmetry is expected. Lexi commands perform data gathering and analysis — that logic belonged in service modules. Lexictl commands orchestrate existing pipeline/indexer/bootstrap modules — the core logic is already extracted. What remains is rendering and infrastructure, which produces a smaller but still valuable decomposition.
