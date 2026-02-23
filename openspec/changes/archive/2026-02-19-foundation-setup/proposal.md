## Why

Lexibrary v1 produced `.aindex` files only; v2 introduces design files, concept files, guardrail threads, `START_HERE.md`/`HANDOFF.md`, and a two-tier config system — none of which fit the v1 architecture. Phase 1 resets the foundation: new CLI surface, new config system, new `.lexibrary/` project structure, and new Pydantic artifact data models that every subsequent phase reads and writes.

## What Changes

- **BREAKING**: Config format changes from TOML (`lexibrary.toml`) to two-tier YAML (global `~/.config/lexibrary/config.yaml` + project `.lexibrary/config.yaml`)
- **BREAKING**: Project root resolution changes — CLI now walks upward for `.lexibrary/` directory instead of `lexibrary.toml`
- **BREAKING**: CLI command surface replaced — `crawl` and standalone `daemon` commands retired; `init`, `lookup`, `index`, `concepts`, `guardrails`, `guardrail`, `search`, `update`, `validate`, `status`, `setup`, `daemon` added as stubs
- New `.lexibrary/` output directory structure with `config.yaml`, `START_HERE.md`, `HANDOFF.md`, `concepts/`, `guardrails/`, and `src/` mirror tree
- New `src/lexibrary/artifacts/` module with Pydantic 2 models for every artifact type (design file, `.aindex`, concept file, guardrail thread) including staleness metadata footer schema
- `pyproject.toml` gains `PyYAML>=6.0.0,<7.0.0`; `indexer/` module retired temporarily
- Keep unchanged: `ignore/`, `tokenizer/`, `utils/hashing.py`, `llm/rate_limiter.py`, `daemon/watcher.py`, `daemon/debouncer.py`, `daemon/scheduler.py`

## Capabilities

### New Capabilities

- `lexibrary-output-structure`: The `.lexibrary/` project output directory — layout rules, mirror tree path construction (`src/auth/` → `.lexibrary/src/auth/`), and special files (`START_HERE.md`, `HANDOFF.md`)
- `artifact-data-models`: Pydantic 2 models for every artifact type — design file, `.aindex` entry, concept file, guardrail thread — including the HTML comment staleness metadata footer (`source`, `source_hash`, `interface_hash`, `generated`, `generator`)
- `project-root-resolution`: Walk upward from CWD to locate `.lexibrary/`; raise a clear, user-friendly error if not found (analogous to how git handles a missing `.git/`)

### Modified Capabilities

- `config-system`: Replace single TOML file loading with two-tier YAML loading (global XDG path + project `.lexibrary/config.yaml`); update schema to v2 fields (LLM provider, token budgets per artifact type, mapping strategies, ignore patterns, trigger mode)
- `cli-skeleton`: Replace v1 command surface (`crawl`, `daemon`) with v2 surface (`init`, `lookup`, `index`, `concepts`, `guardrails`, `guardrail`, `search`, `update`, `validate`, `status`, `setup`, `daemon`); all non-implemented commands return a clear stub message via `rich.console.Console`
- `project-scaffolding`: Add `src/lexibrary/artifacts/` to package layout; update `pyproject.toml` to add `PyYAML>=6.0.0,<7.0.0`; update `.gitignore` to exclude `.lexibrary/` generated files (`START_HERE.md`, `HANDOFF.md`, generated `*.md` and `.aindex` files) while keeping `config.yaml` tracked

## Impact

- `src/lexibrary/config/schema.py`, `config/loader.py` — full rewrite (TOML → YAML, two-tier)
- `src/lexibrary/cli.py` — full rewrite (new command surface)
- `src/lexibrary/artifacts/` — new module (data models)
- `pyproject.toml` — adds `PyYAML`
- `tests/` — new tests: CLI stubs, config loader (two-tier merge), artifact model validation, root-resolution walk-up logic
- All phases 2–10 depend on the artifact data models and config schema settled here
