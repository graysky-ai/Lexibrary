## 1. UpdateStats Extension

- [x] 1.1 Add `linkgraph_built: bool = False` field to `UpdateStats` dataclass in `archivist/pipeline.py`
- [x] 1.2 Add `linkgraph_error: str | None = None` field to `UpdateStats` dataclass in `archivist/pipeline.py`
- [x] 1.3 Write unit test verifying `UpdateStats` default values for new fields

## 2. Pipeline Integration -- update_project()

- [x] 2.1 Add import for `IndexBuilder` from `linkgraph.builder` at top of `archivist/pipeline.py`
- [x] 2.2 Add link graph full build step at the end of `update_project()`, after START_HERE.md regeneration (step 7 in the pipeline)
- [x] 2.3 Wrap the full build call in try/except, logging errors at ERROR level and setting `stats.linkgraph_error`
- [x] 2.4 Set `stats.linkgraph_built = True` on successful build
- [x] 2.5 Write integration test: `update_project()` creates `index.db` in `.lexibrary/` after processing files
- [x] 2.6 Write integration test: `update_project()` returns accurate design file stats even when index build fails

## 3. Pipeline Integration -- update_files()

- [x] 3.1 Collect deleted file paths (files in input list that do not exist on disk) into a separate list before the processing loop
- [x] 3.2 Add incremental index update step at the end of `update_files()`, passing both processed and deleted paths to `IndexBuilder.incremental_update()`
- [x] 3.3 Wrap the incremental update call in try/except, logging errors at ERROR level and setting `stats.linkgraph_error`
- [x] 3.4 Set `stats.linkgraph_built = True` on successful incremental update
- [x] 3.5 Write integration test: `update_files()` with changed files triggers incremental index update
- [x] 3.6 Write integration test: `update_files()` with deleted files forwards deletions to incremental update for CASCADE cleanup
- [x] 3.7 Write integration test: `update_files()` returns accurate stats when incremental update fails

## 4. Init Scaffolder -- .gitignore

- [x] 4.1 Verify that `lexictl init` scaffolder includes `.lexibrary/index.db` in the `.gitignore` patterns; add it if missing
- [x] 4.2 Write test verifying that `lexictl init` on a fresh project results in `.gitignore` containing the `index.db` pattern

## 5. Design File and Documentation Updates

- [x] 5.1 Update the `archivist/pipeline.py` design file in `blueprints/src/` to reflect the new link graph build step
- [x] 5.2 Update `linkgraph/__init__.py` to re-export `IndexBuilder` (if not already done by Phase 10b)

## 6. Final Verification

- [x] 6.1 Run full test suite (`uv run pytest --cov=lexibrarian`) and verify all tests pass
- [x] 6.2 Run linter (`uv run ruff check src/ tests/`) and fix any issues
- [x] 6.3 Run type checker (`uv run mypy src/`) and fix any issues
- [x] 6.4 Manually test `lexictl update` on the project to verify `index.db` is created
