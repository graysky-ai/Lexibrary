## 1. Claude Code Agent Integration (Phase 1)

- [x] 1.1 Add `_generate_settings_json()` to `src/lexibrary/init/rules/claude.py` — generate `.claude/settings.json` with permissions (allow/deny) and merge logic for existing files
- [x] 1.2 Add `_generate_hook_scripts()` to `src/lexibrary/init/rules/claude.py` — generate `.claude/hooks/lexi-pre-edit.sh` and `.claude/hooks/lexi-post-edit.sh` as executable scripts
- [x] 1.3 Extend `_generate_settings_json()` to include `hooks` section (PreToolUse/PostToolUse) in settings.json with merge support
- [x] 1.4 Update `generate_claude_rules()` to call settings and hook generators and include all paths in return value
- [x] 1.5 Add `get_lookup_skill_content()`, `get_concepts_skill_content()`, `get_stack_skill_content()` to `src/lexibrary/init/rules/base.py`
- [x] 1.6 Generate `.claude/commands/lexi-lookup.md`, `.claude/commands/lexi-concepts.md`, `.claude/commands/lexi-stack.md` from `generate_claude_rules()`
- [x] 1.7 Update `generate_cursor_rules()` to generate `.cursor/rules/lexibrary-editing.mdc` (glob-scoped) and include new skills in `.cursor/skills/lexi.md`
- [x] 1.8 Update `generate_codex_rules()` to embed new lookup/concepts/stack skills in `AGENTS.md`
- [x] 1.9 Write tests for settings.json generation, merge, idempotency in `tests/test_init/test_rules/test_claude.py`
- [x] 1.10 Write tests for hook script generation and executability in `tests/test_init/test_rules/test_claude.py`
- [x] 1.11 Write tests for new skill content functions in `tests/test_init/test_rules/test_base.py`
- [x] 1.12 Write tests for Cursor editing rule generation in `tests/test_init/test_rules/test_cursor.py`

## 2. CLI Feature Additions (Phase 2)

- [x] 2.1 Add `dry_run_project()` and `dry_run_files()` to `src/lexibrary/archivist/pipeline.py` — change detection only, no LLM calls or writes
- [x] 2.2 Add `--dry-run` flag to `lexictl update` in `src/lexibrary/cli/lexictl_app.py` with formatted output showing ChangeLevel per file
- [x] 2.3 Add `--start-here` flag to `lexictl update` — call `generate_start_here()` directly, mutually exclusive with `--changed-only` and path
- [x] 2.4 Add `counts_by_severity()` method to `ValidationReport` in `src/lexibrary/validator/report.py`
- [x] 2.5 Add `ci_mode` parameter to `_run_validate()` in `src/lexibrary/cli/_shared.py` with compact single-line output
- [x] 2.6 Add `--ci` flag to `lexictl validate` in `src/lexibrary/cli/lexictl_app.py`
- [x] 2.7 Create `src/lexibrary/validator/fixes.py` with `FixResult` model, `fix_hash_freshness()`, `fix_orphan_artifacts()`, `fix_aindex_coverage()`, and `FIXERS` registry
- [x] 2.8 Add `fix` parameter to `_run_validate()` with fix orchestration and output formatting
- [x] 2.9 Add `--fix` flag to `lexictl validate` (lexictl only, not lexi)
- [x] 2.10 Write tests for dry-run functions in `tests/test_archivist/test_pipeline.py`
- [x] 2.11 Write tests for --dry-run, --start-here, --ci, --fix CLI flags in `tests/test_cli/test_lexictl.py`
- [x] 2.12 Write tests for each fixer function in `tests/test_validator/test_fixes.py`

## 3. Agent Tooling Improvements (Phase 3)

- [x] 3.1 Add `generate_design_scaffold()` to the archivist module — template-based scaffold without LLM
- [x] 3.2 Add `lexi design update <source-file>` command to `src/lexibrary/cli/lexi_app.py` — display existing or scaffold new design file
- [x] 3.3 Add `lexi stack mark-outdated <post-id>` command to `src/lexibrary/cli/lexi_app.py` wrapping `mark_outdated()` mutation
- [x] 3.4 Add `lexi stack duplicate <post-id> --of <original-id>` command to `src/lexibrary/cli/lexi_app.py` wrapping `mark_duplicate()` mutation
- [x] 3.5 Write tests for design scaffold generation and design command in `tests/test_cli/test_lexi.py`
- [x] 3.6 Write tests for stack lifecycle commands in `tests/test_cli/test_lexi.py`

## 4. Git Hook Enhancements (Phase 4)

- [x] 4.1 Create `src/lexibrary/hooks/pre_commit.py` with `install_pre_commit_hook()` using `# lexibrary:pre-commit` marker pattern
- [x] 4.2 Update `src/lexibrary/hooks/__init__.py` to export `install_pre_commit_hook`
- [x] 4.3 Update `lexictl setup --hooks` in `src/lexibrary/cli/lexictl_app.py` to call both `install_post_commit_hook()` and `install_pre_commit_hook()`
- [x] 4.4 Write tests for pre-commit hook installation in `tests/test_hooks/test_pre_commit.py`

## 5. Generic Agent Rules (Phase 5)

- [x] 5.1 Create `src/lexibrary/init/rules/generic.py` with `generate_generic_rules()` generating `LEXIBRARY_RULES.md`
- [x] 5.2 Register `"generic"` environment in `src/lexibrary/init/rules/__init__.py` and update `supported_environments()`
- [x] 5.3 Write tests for generic rules generation in `tests/test_init/test_rules/test_generic.py`

## 6. Init Wizard Improvements (Phase 6)

- [x] 6.1 Add `install_hooks: bool` field to `WizardAnswers` in `src/lexibrary/init/models.py`
- [x] 6.2 Add Step 9 (Git Hooks prompt) to `run_wizard()` in `src/lexibrary/init/wizard.py`
- [x] 6.3 Call hook installers from `lexictl init` when `answers.install_hooks` is True
- [x] 6.4 Add post-init prompt to run `lexictl update` in `src/lexibrary/cli/lexictl_app.py`
- [x] 6.5 Write tests for new wizard step and init hooks in `tests/test_init/test_wizard.py`

## 7. Backlog Triage

- [x] 7.1 Review and update `plans/BACKLOG.md` to ensure all deferred items are tracked: MCP server (L1), IDE workspace settings (L3), `lexictl metrics` dashboard (L6), hook/sweep coordination (M5), Windows hook support (M8), post-merge/post-checkout git hooks
