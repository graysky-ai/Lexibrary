# Changelog

All notable changes to Lexibrary are documented in this file.

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
