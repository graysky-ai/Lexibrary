## 1. Shared CLI Helpers

- [x] 1.1 Extract validate command logic into `_run_validate(severity, check, json_output)` helper in `src/lexibrary/cli/_shared.py` — accepts parsed args, calls `validate_library()`, renders output via Rich or JSON, returns exit code
- [x] 1.2 Extract status command logic into `_run_status(path, quiet, cli_prefix)` helper in `src/lexibrary/cli/_shared.py` — accepts parsed args plus CLI prefix string ("lexi" or "lexictl"), calls status collection, renders dashboard or quiet line, returns exit code

## 2. Lexi CLI Command Registration

- [x] 2.1 Register `lexi validate` command in `src/lexibrary/cli/lexi_app.py` — thin wrapper calling `_run_validate()` with `--severity`, `--check`, and `--json` options
- [x] 2.2 Register `lexi status` command in `src/lexibrary/cli/lexi_app.py` — thin wrapper calling `_run_status(cli_prefix="lexi")` with `[path]` argument and `--quiet` flag
- [x] 2.3 Remove `index` command registration from `src/lexibrary/cli/lexi_app.py`

## 3. Lexictl CLI Command Updates

- [x] 3.1 Register `lexictl index` command in `src/lexibrary/cli/lexictl_app.py` — move the command function from `lexi_app.py` with identical interface (`directory` arg, `-r`/`--recursive` flag)
- [x] 3.2 Refactor `lexictl validate` in `src/lexibrary/cli/lexictl_app.py` to call shared `_run_validate()` helper
- [x] 3.3 Refactor `lexictl status` in `src/lexibrary/cli/lexictl_app.py` to call shared `_run_status(cli_prefix="lexictl")` helper

## 4. Automated Index Regeneration

- [x] 4.1 Add index regeneration step to `update_project()` in `src/lexibrary/archivist/pipeline.py` — after design file generation, collect directories containing changed files and regenerate `.aindex` files for those directories plus ancestors up to `scope_root`
- [x] 4.2 Add `reindex_directories(directories, project_root, lexibrary_dir)` helper function (in indexer module or pipeline) that regenerates `.aindex` for a list of directories and their ancestors
- [x] 4.3 Skip re-indexing when `UpdateStats` reports zero changes (no files created, updated, or failed)

## 5. Help Text and Documentation

- [x] 5.1 Update `lexi help` command content in `src/lexibrary/cli/lexi_app.py` — replace "Indexing & Maintenance" section with "Inspection & Annotation" containing `lexi status`, `lexi validate`, `lexi describe`
- [x] 5.2 Update `lexi help` workflows — replace "Index a new directory" with "Check library health" workflow using `lexi status` and `lexi validate`
- [x] 5.3 Remove all `lexi index` references from `lexi help` output

## 6. Agent Rule Templates

- [x] 6.1 Update `_CORE_RULES` in `src/lexibrary/init/rules/base.py` — add `lexi validate` to "After Editing Files" section; remove any `lexi index` references
- [x] 6.2 Verify `_ORIENT_SKILL` in `base.py` references `lexi status` correctly (already does — confirm no `lexi index` references)
- [x] 6.3 Run `lexictl setup --update` against test fixtures to verify generated Claude/Cursor/Codex rule files reflect updated core rules

## 7. Tests

- [x] 7.1 Add tests for `lexi validate` command — execution, severity filter, check filter, JSON output, exit codes, requires project root
- [x] 7.2 Add tests for `lexi status` command — full dashboard, quiet mode with "lexi:" prefix, exit codes, requires project root
- [x] 7.3 Add tests for `lexictl index` command — single directory, recursive, requires project root, summary output
- [x] 7.4 Verify `lexi index` is no longer registered — test that `lexi --help` does not list `index`
- [x] 7.5 Add tests for automated index regeneration — verify `.aindex` files regenerated for affected directories and ancestors after `update_project()`
- [x] 7.6 Add tests for skip-when-no-changes — verify no re-indexing when UpdateStats has zero changes
- [x] 7.7 Update existing `lexi help` tests to verify new section names, removed `lexi index` references, and new "Check library health" workflow
- [x] 7.8 Add tests for agent rule content — verify `get_core_rules()` includes `lexi validate`, excludes `lexi index`, excludes `lexictl` instructions

## 8. Blueprint Updates

- [x] 8.1 Update blueprint design files for all modified source files: `lexi_app.py`, `lexictl_app.py`, `_shared.py`, `pipeline.py`, `base.py`
