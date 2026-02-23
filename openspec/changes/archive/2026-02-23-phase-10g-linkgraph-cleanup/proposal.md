## Why

Phase 10 (Unified Link Graph) introduced a SQLite-backed index for reverse dependency lookups, accelerated search, and bidirectional validation. Sub-phases 10a through 10f build the schema, builder, query interface, pipeline/CLI integration, and validation. Sub-phase 10g is the final cleanup pass: the design file serializer still writes a bare `## Dependents` section as if agents should look there for reverse references, but dependents are now served at query time via `lexi lookup` (D-070). Documentation, blueprints, and project hygiene need to catch up with the implemented linkgraph modules.

## What Changes

- **Serializer annotation (D-070):** Update `design_file_serializer.py` to annotate the `## Dependents` section with `*(see `lexi lookup` for live reverse references)*` so agents know where to find reverse deps. Preserve any hand-written dependents content for backward compatibility.
- **Blueprint creation:** Create design file blueprints for the new `linkgraph/` modules (`schema.py`, `builder.py`, `query.py`) and update `blueprints/START_HERE.md` to include the `linkgraph` package in the project topology and package map.
- **Master plan update:** Mark all Phase 10 sub-phases (10a-10g) as done in `plans/v2-master-plan.md`.
- **Overview doc consistency:** Review and update `lexibrary-overview.md` to reflect the implemented link graph behaviour — reverse deps via query, `index.db` presence, graceful degradation.
- **Gitignore hygiene:** Verify `.gitignore` includes an `index.db` pattern; verify `lexictl init` scaffolder (`init/scaffolder.py`) creates proper gitignore entries for `index.db`.
- **TODO cleanup:** Scan for and resolve any TODO comments added during Phase 10 implementation across the `linkgraph/` module and related integration points.
- **Test verification:** Ensure all Phase 10 tests pass with adequate coverage.

## Capabilities

### New Capabilities

- `dependents-annotation`: Annotate the `## Dependents` section in serialized design files with a pointer to `lexi lookup` for live reverse references (D-070 compliance)
- `linkgraph-blueprints`: Create and maintain blueprints for `linkgraph/` modules (schema.py, builder.py, query.py) and update START_HERE.md topology

### Modified Capabilities

(none -- there is no existing `design-file-serializer` spec; the serializer change is covered by the new `dependents-annotation` capability)

## Impact

- **`src/lexibrary/artifacts/design_file_serializer.py`** — modified to emit annotation in `## Dependents` section
- **`src/lexibrary/artifacts/design_file_parser.py`** — may need update to strip/ignore the annotation when parsing
- **`blueprints/`** — new files for `linkgraph/` modules; updated `START_HERE.md`
- **`plans/v2-master-plan.md`** — sub-phase status updates
- **`lexibrary-overview.md`** — consistency updates for link graph behaviour
- **`.gitignore`** / **`src/lexibrary/init/scaffolder.py`** — potential `index.db` pattern additions
- **No new dependencies** — Phase 10 uses only stdlib `sqlite3`
- **No breaking changes** — existing design files with `## Dependents` content are preserved; the annotation is additive
