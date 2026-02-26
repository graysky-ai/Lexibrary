## Why

START_HERE.md is a 5-section LLM-generated artifact where 4 of the 5 sections are redundant, hallucinated, or inferior to procedural alternatives. The LLM regenerates topology that `.aindex` already provides, invents an ontology that `lexi concepts` handles better, emits a navigation protocol duplicated in 6+ other places, and hallucinates a convention index with no backing data source. Only navigation-by-intent has editorial value — but that's blocked on richer inputs (Phase 4 in the dismantling plan).

Rather than surgically removing sections one at a time, we dismantle START_HERE entirely: delete the BAML function, remove the LLM generation pipeline, and replace the output with a purely procedural `TOPOLOGY.md` built from `.aindex` billboard summaries. Navigation-by-intent and conventions can be reintroduced later when their upstream dependencies exist.

## What Changes

- **BREAKING**: Remove `START_HERE.md` as a generated artifact — replaced by `TOPOLOGY.md`
- **BREAKING**: Delete BAML `ArchivistGenerateStartHere` function and `StartHereOutput` type
- Remove `StartHereRequest` / `StartHereResult` from archivist service
- Delete `src/lexibrary/archivist/start_here.py` entirely
- Create `src/lexibrary/archivist/topology.py` with procedural topology builder
- Output `TOPOLOGY.md` (adaptive-depth annotated tree from `.aindex` data) instead of `START_HERE.md`
- Update pipeline to call topology generation instead of START_HERE generation
- Mark `plans/agent-start-plan.md` as superseded
- Update docs and agent orientation to reference `TOPOLOGY.md`

## Capabilities

### New Capabilities
- `procedural-topology`: Procedural topology generation from `.aindex` billboard summaries, producing `.lexibrary/TOPOLOGY.md` with adaptive depth based on project scale

### Modified Capabilities
- `start-here-generation`: Entire capability removed — no more LLM-based START_HERE generation
- `archivist-pipeline`: Pipeline step 5 changes from `generate_start_here()` to `generate_topology()`
- `archivist-service`: `StartHereRequest`/`StartHereResult` and `generate_start_here()` method removed
- `archivist-baml`: `ArchivistGenerateStartHere` function and `StartHereOutput` type removed

## Impact

- **Archivist pipeline** (`pipeline.py`): Step 5 changes from LLM call to procedural function
- **BAML definitions**: `archivist_start_here.baml` deleted, `types.baml` loses `StartHereOutput`
- **Archivist service** (`service.py`): Loses start_here request/result types and method
- **Config** (`schema.py`): `start_here_tokens` budget field becomes unused (remove or repurpose)
- **Tests**: `test_start_here.py` replaced by `test_topology.py`
- **Docs**: `orientation.md` updated to reference `TOPOLOGY.md`
- **Specs**: `start-here-generation` spec superseded by new `procedural-topology` spec
- **Plans**: `agent-start-plan.md` marked superseded
- **No new dependencies** — uses only `parse_aindex` from existing `aindex_parser` module
