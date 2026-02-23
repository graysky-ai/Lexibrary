## Context

v1 Lexibrary has a single-file TOML config (`lexibrary.toml`), a single `crawl` command, and produces `.aindex` files directly in the source tree. v2 replaces all three with a two-tier YAML config, a richer CLI surface, and a mirrored `.lexibrary/` output directory. This design document covers the Phase 1 architectural decisions that every later phase inherits.

Existing modules to keep unchanged: `ignore/`, `tokenizer/`, `utils/hashing.py`, `llm/rate_limiter.py`, `daemon/watcher.py`, `daemon/debouncer.py`, `daemon/scheduler.py`. Modules to retire: `indexer/` (temporary). Modules to rewrite: `config/schema.py`, `config/loader.py`, `cli.py`. Module to add: `artifacts/`.

## Goals / Non-Goals

**Goals:**
- Stable config schema, artifact data models, root-resolution, and CLI surface that all later phases build on
- `lexi init` creates a valid `.lexibrary/` skeleton; all other commands are stubs returning "not yet implemented"
- Two-tier config loading merges global and project YAML with project taking precedence
- Artifact data models define the canonical Python representation of every artifact type

**Non-Goals:**
- LLM generation, Tree-sitter parsing, wikilink resolution, validation, or daemon integration — these are Phases 3–9
- Performance tuning of config loading or root resolution

## Decisions

### D1: Config format — YAML via PyYAML (not TOML, not pydantic-settings)

v1 used `lexibrary.toml` via `stdlib tomllib`. v2 switches to YAML because:
- YAML is more readable for nested structures (token budgets per artifact type, glob-pattern mapping strategies)
- PyYAML is the only new dep added in Phase 1 — small footprint
- BAML and many agent-adjacent tools use YAML; consistency reduces agent cognitive load

**Alternative considered:** Keep TOML. Rejected — the v2 config structure (nested mapping strategies, per-artifact token budgets) is verbose in TOML and familiar in YAML.

**Alternative considered:** `pydantic-settings` for automatic env-var merging. Rejected — adds complexity; Phase 1 only needs file-based loading. Env-var support can be added later.

### D2: Two-tier loading — explicit merge, project wins

Global config (`~/.config/lexibrary/config.yaml`, XDG) provides defaults so `lexi init` works without manual setup. Project config (`.lexibrary/config.yaml`) overrides only the fields it declares. Merge strategy: load global → load project → `model_validate(global.model_dump() | project_partial_dict)`.

**Why not deep merge?** Pydantic models have a flat structure at each level. Shallow merge (top-level keys) is sufficient; nested dicts within a key (e.g., `mapping.strategies`) are replaced wholesale to avoid partial-merge surprises.

### D3: Root resolution — walk upward for `.lexibrary/`

`find_project_root(start: Path) -> Path` walks from `start` upward to filesystem root. Returns the directory containing `.lexibrary/` if found, raises `LexibraryNotFoundError` (a custom exception, not `SystemExit`) if not found. The caller (CLI commands) catches this and calls `console.print("[red]No .lexibrary/ found...")` before exiting.

**Why a custom exception?** Keeps `find_project_root` testable without mocking `sys.exit`. CLI layer handles the user-facing message.

### D4: Artifact data models — Pydantic 2 in `artifacts/` module

Five model files:
- `artifacts/design_file.py` — `DesignFile`, `InterfaceContract`, `StalenessMetadata`
- `artifacts/aindex.py` — `AIndexFile`, `AIndexEntry`
- `artifacts/concept.py` — `ConceptFile`
- `artifacts/guardrail.py` — `GuardrailThread`, `GuardrailEntry`
- `artifacts/__init__.py` — re-exports all public models

`StalenessMetadata` captures the HTML comment footer fields (`source`, `source_hash`, `interface_hash`, `generated`, `generator`). Serialisation/deserialisation from the comment block is handled in Phase 4 when generation is implemented; Phase 1 only defines the model.

**Why Pydantic 2 not dataclasses?** Phase 4 needs `model_validate`, `model_dump`, and JSON schema generation for BAML integration. Pydantic 2 provides all three.

### D5: CLI stubs — Typer with explicit "not yet implemented" messages

All v2 commands are registered in `cli.py` with correct help text. Non-implemented commands call `console.print("[yellow]Not yet implemented.[/yellow]")` and `raise typer.Exit(0)`. This ensures `lexi --help` shows the full v2 surface from Phase 1 onward, and agents don't hit `command not found` errors during development.

**Commands to register:** `init`, `lookup`, `index`, `concepts`, `guardrails`, `guardrail` (subgroup: `new`), `search`, `update`, `validate`, `status`, `setup`, `daemon`. `init` is the only command with a real implementation in Phase 1.

### D6: `lexi init` implementation scope in Phase 1

`lexi init [--agent cursor|claude|codex]` creates the `.lexibrary/` skeleton:
```
.lexibrary/
  config.yaml     # project config template with comments
  START_HERE.md   # placeholder ("Run lexi update to generate")
  HANDOFF.md      # placeholder ("No active session")
  concepts/       # empty directory (add .gitkeep)
  guardrails/     # empty directory (add .gitkeep)
```

It does NOT write agent environment rules — that is `lexi setup` (Phase 8). The `--agent` flag in `init` is accepted but ignored in Phase 1 with a note that `lexi setup` will handle it.

## Risks / Trade-offs

- **Config schema churn** — later phases may add fields; Pydantic's `model_config = ConfigDict(extra="ignore")` prevents validation errors when old configs encounter new fields. New required fields should always have defaults.
- **Root resolution ambiguity** — in monorepos with nested `.lexibrary/` directories, the walk-up finds the nearest one. This is intentional (project-scoped), but should be documented clearly.
- **Retiring `indexer/`** — any tests that import from `indexer/` will break. Audit and remove/stub them in Phase 1.

## Migration Plan

1. Delete `src/lexibrary/config/schema.py` and `config/loader.py`; write new versions
2. Delete `src/lexibrary/cli.py`; write new version
3. Delete `src/lexibrary/indexer/` (or move to `indexer/_v1_retired/` if tests need phased migration)
4. Create `src/lexibrary/artifacts/` with data models
5. Add `PyYAML>=6.0.0,<7.0.0` to `pyproject.toml`; run `uv sync`
6. Update `.gitignore`: add `.lexibrary/START_HERE.md`, `.lexibrary/HANDOFF.md`, `.lexibrary/**/*.md`, `.lexibrary/**/.aindex`; keep `.lexibrary/config.yaml` tracked
7. Run `uv run pytest` to confirm test suite passes; update any tests that import retired modules

No rollback strategy needed — this is a pre-release tool with no deployed instances.

## Open Questions

- **Token budget defaults:** The overview lists `START_HERE.md ~500–800 tokens`, design file `~200–400 tokens`, etc. Should the Phase 1 config schema encode these as integer fields (tokens) or as KB estimates? **Leaning: integer tokens** — consistent with existing `tokenizer/` module which counts tokens directly.
- **Mapping strategy config shape:** The overview describes glob-pattern strategies (1:1, grouped, abridged, skipped). Should Phase 1 config include a `mapping` section as a stub (empty list, ignored) or defer it entirely to Phase 4? **Leaning: include stub** — locks in the YAML key name so Phase 4 doesn't break existing project configs.
