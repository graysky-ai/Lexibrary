## 1. IWH Module — Model, Parser, Serializer

- [x] 1.1 Create `src/lexibrary/iwh/__init__.py` with public API re-exports
- [x] 1.2 Create `src/lexibrary/iwh/model.py` — `IWHFile` Pydantic 2 model with `author`, `created`, `scope` (Literal), `body` fields; `IWHScope` type alias
- [x] 1.3 Create `src/lexibrary/iwh/parser.py` — `parse_iwh(path)` using frontmatter regex pattern from stack/parser.py
- [x] 1.4 Create `src/lexibrary/iwh/serializer.py` — `serialize_iwh(iwh)` producing markdown with YAML frontmatter
- [x] 1.5 Create `tests/test_iwh/__init__.py`, `test_model.py`, `test_parser.py`, `test_serializer.py`, `test_roundtrip.py` — all model/parser/serializer/roundtrip tests
- [x] 1.6 Run tests and verify all pass

## 2. IWH Module — Reader, Writer, Gitignore

- [x] 2.1 Create `src/lexibrary/iwh/reader.py` — `read_iwh()` and `consume_iwh()` (consume deletes even corrupt files)
- [x] 2.2 Create `src/lexibrary/iwh/writer.py` — `write_iwh()` with directory creation and overwrite semantics
- [x] 2.3 Create `src/lexibrary/iwh/gitignore.py` — `ensure_iwh_gitignored()` with idempotent append, alternative pattern recognition
- [x] 2.4 Create `tests/test_iwh/test_reader.py`, `test_writer.py`, `test_gitignore.py` — all reader/writer/gitignore tests
- [x] 2.5 Run tests and verify all pass

## 3. IWH Path Helper

- [x] 3.1 Add `iwh_path(project_root, source_directory)` to `src/lexibrary/utils/paths.py`
- [x] 3.2 Add tests to `tests/test_utils/test_paths.py` for subdirectory, project root, and nested directory cases
- [x] 3.3 Run tests and verify all pass

## 4. Config & HANDOFF.md Removal

- [x] 4.1 Remove `handoff_tokens` field from `TokenBudgetConfig` in `src/lexibrary/config/schema.py`
- [x] 4.2 Remove `handoff_tokens` line from `DEFAULT_PROJECT_CONFIG_TEMPLATE` in `src/lexibrary/config/defaults.py`
- [x] 4.3 Remove `.lexibrary/HANDOFF.md` from `IgnoreConfig.additional_patterns` default in `src/lexibrary/config/schema.py`
- [x] 4.4 Remove `HANDOFF_PLACEHOLDER` constant and `HANDOFF.md` file creation from `src/lexibrary/init/scaffolder.py`
- [x] 4.5 Update `START_HERE_PLACEHOLDER` in scaffolder to reference IWH instead of HANDOFF
- [x] 4.6 Update `tests/test_init/test_scaffolder.py` — remove HANDOFF assertions, add IWH gitignore assertions
- [x] 4.7 Update `tests/test_config/test_schema.py` — remove `handoff_tokens` assertions, add stale key tolerance test
- [x] 4.8 Run tests and verify all pass

## 5. Marker Utilities

- [x] 5.1 Create `src/lexibrary/init/rules/__init__.py` (empty initially, will be populated in group 7)
- [x] 5.2 Create `src/lexibrary/init/rules/markers.py` — `MARKER_START`, `MARKER_END`, `has_lexibrary_section()`, `replace_lexibrary_section()`, `append_lexibrary_section()`
- [x] 5.3 Create `tests/test_init/test_rules/__init__.py` and `test_markers.py` — detection, replacement, preservation, append, empty content tests
- [x] 5.4 Run tests and verify all pass

## 6. Agent Rule Templates — Base Content

- [x] 6.1 Create `src/lexibrary/init/rules/base.py` — `get_core_rules()`, `get_orient_skill_content()`, `get_search_skill_content()`
- [x] 6.2 Create `tests/test_init/test_rules/test_base.py` — verify core rules contain key instructions, no lexictl references, orient/search skill content
- [x] 6.3 Run tests and verify all pass

## 7. Agent Rule Templates — Environment Generators

- [x] 7.1 Create `src/lexibrary/init/rules/claude.py` — `generate_claude_rules()` producing CLAUDE.md (marker-based) + `.claude/commands/` files
- [x] 7.2 Create `src/lexibrary/init/rules/cursor.py` — `generate_cursor_rules()` producing `.cursor/rules/lexibrary.mdc` + `.cursor/skills/lexi.md`
- [x] 7.3 Create `src/lexibrary/init/rules/codex.py` — `generate_codex_rules()` producing AGENTS.md (marker-based)
- [x] 7.4 Implement `generate_rules()` and `supported_environments()` in `src/lexibrary/init/rules/__init__.py`
- [x] 7.5 Create `tests/test_init/test_rules/test_claude.py` — create from scratch, append to existing, update section, command file tests
- [x] 7.6 Create `tests/test_init/test_rules/test_cursor.py` — MDC format, skills file tests
- [x] 7.7 Create `tests/test_init/test_rules/test_codex.py` — create from scratch, append, update tests
- [x] 7.8 Run tests and verify all pass

## 8. CLI Integration — `lexictl setup --update`

- [x] 8.1 Replace `setup` command stub in `src/lexibrary/cli/lexictl_app.py` with real implementation calling `generate_rules()` and `ensure_iwh_gitignored()`
- [x] 8.2 Add `setup` command tests to `tests/test_cli/test_lexictl.py` — config-persisted envs, explicit env arg, --update flag, no env error, unsupported env error
- [x] 8.3 Run tests and verify all pass

## 9. Scaffolder + Gitignore Integration

- [x] 9.1 Wire `ensure_iwh_gitignored()` call into `create_lexibrary_skeleton()` in `src/lexibrary/init/scaffolder.py`
- [x] 9.2 Update scaffolder tests to verify gitignore integration on fresh init
- [x] 9.3 Run tests and verify all pass

## 10. Integration Tests

- [x] 10.1 Create `tests/test_init/test_rules/test_integration.py` — full flow per environment, multi-environment, setup --update refresh, user content preservation, unsupported env error, gitignore updated
- [x] 10.2 Run full test suite (`uv run pytest --cov=lexibrary`) and verify all pass
- [x] 10.3 Run linting (`uv run ruff check src/ tests/`) and type checking (`uv run mypy src/`)

## 11. Blueprint Updates

- [x] 11.1 Create blueprint design files for `iwh/` module (`blueprints/src/lexibrary/iwh/`)
- [x] 11.2 Create blueprint design files for `init/rules/` module (`blueprints/src/lexibrary/init/rules/`)
- [x] 11.3 Update `blueprints/START_HERE.md` package map with `iwh/` and `init/rules/` entries
- [x] 11.4 Update blueprint for `init/scaffolder.py` — HANDOFF removal, IWH gitignore integration
- [x] 11.5 Update blueprint for `config/schema.py` — handoff_tokens removal
- [x] 11.6 Update blueprint for `utils/paths.py` — iwh_path addition
