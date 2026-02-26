## 1. Remove BAML START_HERE infrastructure

- [x] 1.1 Delete `StartHereOutput` class from `baml_src/types.baml`
- [x] 1.2 Delete `baml_src/archivist_start_here.baml` entirely
- [x] 1.3 Run `uv run baml-cli generate` to regenerate Python client

## 2. Remove archivist service START_HERE support

- [x] 2.1 Delete `StartHereRequest` and `StartHereResult` dataclasses from `src/lexibrary/archivist/service.py`
- [x] 2.2 Delete `generate_start_here()` method from `ArchivistService`
- [x] 2.3 Remove any imports of `StartHereOutput` from `service.py`

## 3. Create procedural topology module

- [x] 3.1 Create `src/lexibrary/archivist/topology.py` with `_build_procedural_topology()` implementing adaptive-depth tree from `.aindex` data
- [x] 3.2 Add `generate_topology()` entry point that wraps the tree in markdown and writes to `.lexibrary/TOPOLOGY.md`

## 4. Update archivist pipeline

- [x] 4.1 Replace `generate_start_here()` call in `pipeline.py` step 5 with `generate_topology()` call
- [x] 4.2 Rename `start_here_failed` to `topology_failed` in `UpdateStats` dataclass
- [x] 4.3 Update all references to `start_here_failed` across codebase (pipeline, CLI output, tests)

## 5. Delete old start_here module

- [x] 5.1 Delete `src/lexibrary/archivist/start_here.py`
- [x] 5.2 Remove `start_here_tokens` from `TokenBudgetConfig` in `src/lexibrary/config/schema.py`

## 6. Update tests

- [x] 6.1 Delete `tests/test_archivist/test_start_here.py`
- [x] 6.2 Create `tests/test_archivist/test_topology.py` with tests for `_build_procedural_topology()` (small/medium/large projects, no .aindex, billboard annotations, hidden children)
- [x] 6.3 Create test for `generate_topology()` end-to-end (writes TOPOLOGY.md)
- [x] 6.4 Update pipeline tests to expect `generate_topology()` call instead of `generate_start_here()`

## 7. Update docs and specs

- [x] 7.1 Update `docs/agent/orientation.md` to reference `TOPOLOGY.md` instead of `START_HERE.md`
- [x] 7.2 Update `openspec/specs/start-here-generation/spec.md` with removal notice
- [x] 7.3 Mark `plans/agent-start-plan.md` as superseded with note at top

## 8. Verify

- [x] 8.1 Run `uv run baml-cli generate` — no errors
- [x] 8.2 Run `uv run pytest tests/test_archivist/test_topology.py -v` — all pass
- [x] 8.3 Run `uv run pytest --cov=lexibrary` — no regressions (2313 passed, 86% coverage; fixed 5 stale start_here_tokens test references)
- [x] 8.4 Run `uv run ruff check src/ tests/` — no new lint errors (11 pre-existing in crawler/engine.py + linkgraph tests)
- [x] 8.5 Run `uv run mypy src/` — no new type errors (3 pre-existing unused-ignore in init/rules/claude.py)
