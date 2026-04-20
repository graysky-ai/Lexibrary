# Changelog

All notable changes to Lexibrary are documented in this file.

## [0.6.2] - 2026-04-21

### Added
- **Curator escalation pipeline** — New `src/lexibrary/cli/_escalation.py` and `ESCALATION_CHECKS` registry route `orphan_concepts`, `stale_concept`, `convention_stale`, and `playbook_staleness` through a 3-option operator prompt shared with `lexi validate --fix --interactive`; autonomous runs emit IWH signals and `PendingDecision` report entries instead of mutating
- **`lexictl curate resolve` subcommand** — Admin-only replay of `CuratorReport.pending_decisions` through the interactive operator prompt; supports `--report` and `--batch-ignore-all` for CI
- **Soft-deprecation lifecycle helpers** — New `lifecycle/playbook_deprecation.py` and `lifecycle/refresh.py` centralise status flips, `deprecated_reason`/`last_verified` stamping, and body annotation for concepts, conventions, and playbooks
- **`deprecated_reason` / `last_verified` frontmatter** — New optional fields on `ConceptFileFrontmatter`, `ConventionFileFrontmatter`, and `PlaybookFileFrontmatter`; `--reason` flag added to `concept deprecate`, `convention deprecate`, and `playbook deprecate` CLI commands
- **Validator fixer kill-switches** — New `ValidatorConfig` block with `fix_lookup_token_budget_condense` (default `False`) and `fix_orphaned_iwh_signals_delete` (default `True`) gating the new `fix_lookup_token_budget_exceeded` and `fix_orphaned_iwh_signals` fixers
- **Orphan verify TTL** — New `concepts.orphan_verify_ttl_days` config (default 90) lets `check_orphan_concepts` honour a recent operator verification window
- **Standalone `condense_file`** — New non-agent-session condensation entry point in `curator/budget.py` mirrors the `reconcile_deps_only` extraction pattern for the validator fixer and `full`-autonomy sub-agent path
- **Test coverage** — New suites covering escalation fixers, condense-file helper, pending-decisions schema, frontmatter round-trip (`deprecated_reason`, `last_verified`), lookup token-budget fixer, orphaned IWH fixer, fixer registry, curate resolve CLI, operational fixer integration, validate interactive flow, and kill-switch config

### Changed
- **`lexictl curate` is now a command group** — Default (no subcommand) still invokes the coordinator pipeline via Typer's `invoke_without_command` callback, preserving the prior `lexictl curate [flags]` behaviour; `run` and `resolve` are explicit subcommands
- **Concept/convention/playbook deprecate CLIs** — Delegate frontmatter mutation and atomic writes to the new lifecycle helpers; CLI layer retains user-facing messaging only
- **`validator/fixes.py`** — Expanded to host the escalation fixer family, lookup-token-budget condensation fixer, and orphaned IWH signal cleanup

## [0.6.1] - 2026-04-18

### Added
- **Multi-root scope support** — New `scope_roots` config field (list of `ScopeRoot` mappings) replaces single `scope_root`; new `config/scope.py` with `find_owning_root` helper funneled through archivist, conventions, validator, lookup, bootstrap, and CLI gating
- **Resolve-time config guards** — `LexibraryConfig.resolved_scope_roots()` validates path-traversal, nested roots, and duplicates; `check_config_valid` now reports these as validation errors (closes ST-043 gap)
- **Two-pass curator collection** — New config options for two-pass collection and reactive bootstrap regeneration
- **Curator coordinator expansion** — Bidirectional integration, duplicate integration, orphaned aindex integration, prepare_indexes service, wikilink resolution integration, coordinator performance tests
- **Validator fixes** — New `fix_bidirectional_deps` check with fixer, expanded info/infrastructure/warning check coverage
- **Archivist reconcile_deps_only gate** — New test coverage for partial pipeline reconciliation
- **Per-root topology sections** — `generate_raw_topology` emits one section per scope root with placeholder fallback for empty documents
- **Conventions ancestry** — `_build_ancestry` now includes normalized `file_path` for directory-scoped convention matching
- **Performance benchmark marker** — New `pyproject.toml` pytest marker for categorising perf tests
- **Curator ordering doc** — New `curator-order-of-operations.md`

### Changed
- **Config schema** — `scope_root: str` replaced by `scope_roots: list[ScopeRoot]`; legacy `scope_root:` keys now raise an actionable validation error with migration instructions
- **`_walk_scope`** — Refactored into a single-scope helper; multi-root iteration lives in `discover_source_files`
- **`reindex_directories`** — Skips out-of-scope directories rather than indexing them as single entries
- **`check_convention_gap`** — Falls back to project root when config loading fails, preventing silent skips
- **Test helpers** — Consolidated `_make_config(scope_root | scope_roots)` replaces prior `_make_config` + `_make_multiroot_config` split
- **Config file references** — `.env.example` and docs updated to reference `.lexibrary/config.yaml` instead of the old `lexibrary.toml`
- **Documentation** — cli-reference, configuration, library-structure, troubleshooting, design-files, how-it-works, project-setup, validation refreshed for multi-root layout
- **Agent documentation** — `AGENTS.md` clarifies session-start procedures and IWH signal handling; topology-builder SKILL updated

### Removed
- **`CURATOR_REPORT_FINDINGS.md`** — Obsolete planning/findings document (503 lines)

## [0.6.0] - 2026-04-13

### Added
- **Symbol graph subsystem** — New `src/lexibrary/symbolgraph/` package with builder, query, schema, health, Python imports resolver, and language-specific resolvers (Python, JavaScript/TypeScript) for cross-file symbol relationship tracking
- **`lexi trace` command** — New CLI command for walking call chains and symbol relationships before renaming, moving, or removing symbols; includes `--help-extended` reference for interpreting trace output
- **`lexi search --type symbol`** — Symbol-scoped search now indexes enum member values and constants, surfacing canonical enums when searching for string/integer literals
- **AST parser extensions** — Enum and constant extraction, branch parameter extraction, composition edge detection, class hierarchy edges (`inherits`, `instantiates`), and call site extraction across Python, JavaScript, and TypeScript parsers
- **Design file enrichment sections** — New `Enums & constants`, `Call paths`, and `Data flows` sections in design files, with corresponding `EnumNote`, `CallPathNote`, and `DataFlowNote` BAML models
- **Symbols service** — New `services/symbols.py` and `services/symbols_render.py` powering the symbol-graph-backed CLI commands
- **Symbol graph context for archivist** — New `archivist/symbol_graph_context.py` providing symbol graph data to the design file generation pipeline
- **Curator consistency fixes** — New `curator/consistency_fixes.py`, `curator/validation_fixers.py`, `curator/iwh_actions.py`, `curator/write_contract.py`, `curator/collect_filters.py`, and `curator/dispatch_context.py` for improved autonomous reconciliation
- **Documentation** — New `docs/symbol-graph.md` (~480 lines), `docs/troubleshooting.md`, and expanded `docs/cli-reference.md`, `docs/configuration.md`, and `docs/design-files.md`
- **Symbols config block** — New configuration for toggling enum, constant, call path, and data flow extraction
- **Test coverage** — New test suites for symbol graph (builder, query, resolvers, health, schema, refresh), AST parser fixtures (enums, calls, classes, composition, branch parameters), trace CLI, symbols service, and curator consistency/validation

### Changed
- **Archivist pipeline** — Integrated symbol graph context and BAML data-flow/symbols enrichment gates; extended `ArchivistGenerateDesignFile` BAML function with enum, call path, and data flow parameters
- **Design file parser/serializer** — Extended to round-trip the new enrichment sections
- **Lookup service** — Major expansion to surface symbol graph data (key symbols, class hierarchy, call paths, data flows, enums & constants) in `lexi lookup` output
- **Curator coordinator** — Refactored dispatcher methods for improved modularity
- **Token budgets** — Increased limits in default config for design files, aindex, concept, and lookup outputs
- **`.gitignore`** — Added symbol graph database state files (`symbols.db-shm`, `symbols.db-wal`)

## [0.5.0] - 2026-04-10

### Added
- **Curator agent subsystem** — New `src/lexibrary/curator/` package with coordinator, auditing, budget, cascade, comments, consistency, deprecation, fingerprint, hooks, lifecycle, migration, reconciliation, risk taxonomy, and staleness modules for autonomous library maintenance
- **`lexi curate` CLI command** — New command surface for running curator workflows (audit, reconcile, deprecate, sweep)
- **Curator BAML functions** — Seven new BAML functions: `curator_budget_trimmer`, `curator_comment_auditing`, `curator_comment_integration`, `curator_consistency_checker`, `curator_deprecation`, `curator_reconcile_design_file`, `curator_staleness_resolver`
- **Curate render service** — New `services/curate_render.py` for curator output formatting
- **Stack mutations module** — New `stack/mutations.py` exposing stack mutation helpers
- **Curator config schema** — New configuration fields on the config schema for curator tuning
- **Archivist pipeline section preservation** — Pipeline now preserves curator-authored sections in design files across regeneration
- **Design file comment metadata** — Parser and serializer support for `.comments.yaml` sidecar files
- **Validator checks** — New checks for curator-managed artifact consistency
- **Curator test suite** — Comprehensive test coverage for curator subsystem (~15k lines across `tests/test_curator/`)
- **Curator fixtures library** — New `tests/fixtures/curator_library/` with concepts, conventions, designs, and source files for integration testing
- **CI integration guide** — New `docs/ci-integration.md`

### Changed
- **Documentation restructure** — Flattened `docs/user/` and `docs/agent/` into top-level `docs/`; consolidated agent reference into unified user-facing docs (`concepts.md`, `configuration.md`, `conventions.md`, `design-files.md`, `iwh.md`, `playbooks.md`, `search.md`, `stack.md`)
- **Archivist pipeline** — Refactored to integrate curator comment preservation and section merging
- **Design file parser/serializer** — Extended to round-trip curator comment metadata
- **`lexictl` app** — Updated to expose curator maintenance operations
- **Topology** — Updated `.lexibrary/TOPOLOGY.md` and topology template to reflect the curator subsystem
- **Rules template** — Updated `core_rules.md` with curator-related guidance
- **Agent rules** — Updated `AGENTS.md` and `README.md` to reference the new docs layout

### Removed
- **Obsolete planning and analysis files** — Removed `architecture-analysis.md`, `curator-agent.md`, `decompose-lexictl-cli-analysis.md`, `harness-opportunities.md`, `harness-opportunities-status.md`, `harness-update-plan.md`, `oai-harness-engineering-analysis.md`, `spec-opportunities.md`, `symphony-spec-analysis.md`, `coverage-baseline.txt`
- **Legacy agent docs** — Removed `docs/agent/concepts.md`, `docs/agent/iwh.md`, `docs/agent/lexi-reference.md`, `docs/agent/lookup-workflow.md`, `docs/agent/prohibited-commands.md`, `docs/agent/quick-reference.md`, `docs/agent/stack.md`, `docs/agent/update-workflow.md`, `docs/agent/README.md` (content migrated to flattened docs layout)
- **Legacy user docs** — Removed `docs/user/artefact-lifecycle.md`, `docs/user/configuration.md`, `docs/user/conventions-concepts-exploration.md`, `docs/user/design-file-generation.md`, `docs/user/lexictl-reference.md` (content migrated or consolidated)

## [0.4.0] - 2026-04-08

### Added
- **Search suggestions** — Fuzzy "did you mean?" suggestions when search returns no results
- **Sweep service** — New `sweep.py` service for batch design file maintenance
- **Bootstrap render service** — New `bootstrap_render.py` for initial design file generation
- **Update render service** — New `update_render.py` for incremental design file updates
- **Wikilink patterns module** — Extracted `wiki/patterns.py` with `extract_wikilinks` supporting HTML comment handling
- **Convention scope splitting** — `split_scope()` helper and `scope_paths` property for multi-path convention scopes
- **Validator lifecycle checks** — New validation checks for artifact lifecycle consistency
- **Coverage baseline** — Recorded test coverage baseline for lexictl CLI decomposition

### Changed
- **Search engine** — Enhanced scoring, filtering, and output formatting across all render modes (JSON, plain, markdown)
- **Design file pipeline** — Refactored archivist pipeline to use dedicated bootstrap/update render services
- **Linkgraph builder** — Extracted wikilink logic to `wiki/patterns`, improved robustness
- **Lexictl CLI** — Major refactoring for maintainability and decomposition readiness
- **Validator checks** — Expanded and restructured validation with new check categories
- **Wiki index** — Improved wikilink extraction and index building
- **Documentation** — Updated agent docs, user docs, and templates to reflect new workflows

## [0.3.1] - 2026-04-02

### Removed
- **`lexi orient` command** -- Removed the orient command, service modules (`orient.py`, `orient_render.py`), and the `lexi-orient` skill template. Session start now uses `TOPOLOGY.md` for project layout and `lexi iwh list` for pending signals instead of the orient command.
- **`orientation_tokens` config** -- Removed from `TokenBudgetConfig` schema and default config since the orient command no longer exists.
- **`docs/agent/orientation.md`** -- Deleted; session start protocol is now documented in `quick-reference.md` and agent rule files.

### Changed
- **Agent rules and templates** -- Updated `CLAUDE.md`, core rules template, and agent templates (explore, plan, code) to replace `lexi orient` with reading `TOPOLOGY.md` and running `lexi iwh list`.
- **Documentation** -- Updated README, agent docs, and user docs to remove orient references and reflect the new session start workflow.

## [0.3.0] - 2026-03-27

### Added
- **Topology generation** — Agent-navigable `TOPOLOGY.md` produced from raw topology data, with directory trees, billboard summaries, and navigation prose
- **Topology builder skill** — New skill with template for structured topology generation
- **Skills restructure** — Skills migrated from flat `.md` files to structured `SKILL.md` directories (`lexi-concepts`, `lexi-lookup`, `lexi-orient`, `lexi-search`, `lexi-stack`)
- **Skills mirror test** — Ensures skill templates stay in sync with registered skills
- **Context allocation config** — New `context_allocation` config field for controlling token budget distribution

### Changed
- **Topology engine** — Major overhaul of `archivist/topology.py` with improved structure and generation pipeline
- **Index generator** — Refactored context allocation logic in `indexer/generator.py` for better token budget handling
- **Validator** — Significant refactoring of validation checks for improved reliability
- **Claude rules generator** — Updated rule generation to reference new skill directory structure
- **Pipeline** — Refined archivist pipeline flow and service integration

### Removed
- Obsolete plan files (`topology-update-plan.md`, `lexi-context-plan.md`)
- Legacy flat skill templates (`concepts.md`, `lookup.md`, `orient.md`, `search.md`, `stack.md`)

## [0.2.0] - 2026-02-27

### Added
- **AST parsing** — Language-aware public API extraction for Python, JavaScript, and TypeScript via tree-sitter
- **Link graph** — SQLite-backed cross-file dependency analysis with reverse lookups and FTS search
- **Conventions** — First-class convention artifacts with lookup integration
- **Stack** — Contextual working-set management (posts, search, voting)
- **Daemon mode** — Watchdog-based background indexing with debounce and periodic sweep
- **Init wizard** — Interactive `lexictl init` with project detection and guided setup
- **Validation** — Library consistency checks with severity filtering and auto-fix
- **Agent rules** — IWH (I Was Here) signal files and agent-facing documentation
- **Dotenv support** — `.env` file loading for API key management
- `py.typed` marker for PEP 561 compliance
- `CHANGELOG.md`
- `.editorconfig` for contributor consistency

### Changed
- **CLI split** — Separated into `lexi` (agent-facing) and `lexictl` (maintenance)
- **Package rename** — `lexibrarian` renamed to `lexibrary`
- Improved error handling with structured `ErrorRecord`/`ErrorSummary` pipeline
- Refactored command structure for improved agent usability

### Removed
- `START_HERE.md` generation (replaced by design files and link graph)
- Agent workflow artifacts removed from git tracking (openspec, blueprints, plans, beads)

## [0.1.0] - 2026-02-10

### Added
- **Foundation** — Project scaffolding, config system (Pydantic 2 + YAML), ignore patterns (pathspec)
- **Crawler** — Bottom-up file traversal with SHA-256 change detection
- **Indexer** — `.aindex` file generation with directory-level summaries
- **Design files** — LLM-generated per-file summaries via BAML prompts
- **Token counting** — Anthropic, tiktoken, and approximate backends
- **CLI** — Typer-based command interface with Rich console output
