# Project Topology

**Lexibrary** is an AI-friendly codebase indexer that produces `.aindex` files, per-file design documents, a queryable symbol graph, and a link graph so LLM-based coding agents can navigate, understand, and edit a repository with structured context.

## Directory Tree Legend

Directory descriptions in the tree below are synthesised keyword fragments drawn from the individual file descriptions within that directory. Fragments are separated by `;` -- each fragment describes a **different file** in that directory, not multiple aspects of the same file. Use these fragments to decide which directory to explore next without opening every file.

## Entry Points

| Command / Import | Role | Entry File |
|-----------------|------|-----------|
| `lexi` | Agent-facing CLI -- lookups, search, orientation, validation, symbols, trace, Stack/convention/playbook/design helpers | [src/lexibrary/cli/lexi_app.py](src/lexibrary/cli/lexi_app.py) |
| `lexictl` | Maintainer-facing CLI -- init, bootstrap, index, update, validate, sweep, curate, agent-rules management | [src/lexibrary/cli/lexictl_app.py](src/lexibrary/cli/lexictl_app.py) |
| `python -m lexibrary` | Module entry point; delegates to the agent-facing CLI (`lexi_app`) | [src/lexibrary/__main__.py](src/lexibrary/__main__.py) |

Registered via `[project.scripts]` in [pyproject.toml](pyproject.toml). Both Typer apps are re-exported from [src/lexibrary/cli/__init__.py](src/lexibrary/cli/__init__.py), which also silences BAML prompt/response logging by defaulting `BAML_LOG=WARN`. Agents must never run `lexictl` -- it owns destructive and expensive operations.

## Project Config

| Property | Value |
|----------|-------|
| Language / runtime | Python 3.11+ (with BAML DSL under [baml_src/](baml_src/)) |
| Build system | `hatchling` |
| Package manager | `uv` |
| Type checker | `mypy` (strict mode; generated `baml_client/` and legacy `crawler/engine.py` excluded) |
| Linter / formatter | `ruff` (line-length 100, target py311; `baml_client/` excluded) |
| Test runner | `pytest` (testpaths: `tests/`, pythonpath: `src/`) |
| LLM integration | `baml-py` 0.218.1, prompt definitions in [baml_src/](baml_src/) |
| AST parsing | `tree-sitter` (Python, JavaScript, TypeScript grammars) |

## Scope Roots

Lexibrary indexes only files under the declared scope roots: files under them get design files generated and are searchable via `lexi`. Files outside every scope root still appear in the tree below but lack design-file annotations. Scope roots are declared in [.lexibrary/config.yaml](.lexibrary/config.yaml).

| Path | Role |
|------|------|
| [src/](src/) | Python package `lexibrary` (primary product code: CLI, services, artifacts, curator, archivist, symbol graph, link graph, etc.) |
| [baml_src/](baml_src/) | BAML DSL prompts for LLM interactions (archivist, summarisers, curator reconciliation / audit / consistency / staleness / deprecation / budget) |

The two roots use different primary languages (Python vs BAML). The generated [src/lexibrary/baml_client/](src/lexibrary/baml_client/) package is derived from `baml_src/` and is excluded from ruff and mypy. Tests under [tests/](tests/) are *not* a scope root -- they run via pytest but are not indexed as artefacts.

## Directory Tree

```
Lexibrarian/
  baml_src/                  -- BAML DSL prompts: archivist design-file generation; summarizers (file, batch, directory); curator prompts (reconciliation, comment auditing/integration, consistency, deprecation, staleness, budget trimming); BAML clients and generators
  docs/                      -- Flat documentation: CLI reference, design files, concepts, conventions, stack, playbooks, configuration, symbol graph, getting-started, troubleshooting
  openspec/                  -- OpenSpec change proposals and specs (workflow-only; not indexed)
  plans/                     -- Human-authored planning docs and backlogs (not indexed)
  scripts/                   -- One-off maintenance and debugging scripts (not indexed)
  src/
    lexibrary/               -- Cross-artifact search (search.py); structured error aggregation (errors.py); exception hierarchy (exceptions.py); module entry (__main__.py); py.typed marker
      archivist/             -- Stale-file detection and per-file design generation via LLM; non-LLM skeleton generator; import-target resolver; symbol-graph context builder; topology emitter; public facade
      artifacts/             -- Pydantic models and parser/serializer pairs for .aindex, design-file, concept, convention, playbook; artifact ID registry; duplicate-title detector; atomic writer; slug helpers
      ast_parser/            -- Resilient tree-sitter extractors (Python/JS/TS); canonical interface-skeleton serializer; shared AST walker and schemas
      baml_client/           -- Generated BAML client code (do not edit; excluded from ruff and mypy)
      cli/                   -- Two Typer apps and per-domain subcommand modules (concepts, conventions, curate, design, iwh, playbooks, stack); shared helpers (_shared, _output, _format, banner)
      config/                -- Namespace re-exports; two-tier YAML config loader with deprecation migration; Pydantic v2 schema
      conventions/           -- Parser, serializer, and scope-aware in-memory index for convention markdown files
      crawler/               -- Bottom-up project crawl with SHA-256 change cache and LLM billboard summarization; ignore-filtered directory discovery
      curator/               -- Autonomous maintenance agent: coordinator, collect filters, risk taxonomy, budget tracking, hook runners, reconciliation, staleness/consistency/consistency fixes/deprecation/migration/cascade/auditing/iwh actions, comments handling, write contract, fingerprinting, dispatch context, validation fixers
      hooks/                 -- Idempotent git pre-commit and post-commit hook installers
      ignore/                -- IgnoreMatcher factory, unified matcher, and parsing of .gitignore / .lexignore files
      indexer/               -- In-memory AIndexFile generator and the .aindex write orchestrator
      init/                  -- Project metadata auto-detection; guided 9-step wizard; idempotent scaffolding
        rules/               -- Marker-delimited section utilities; Markdown template loader; environment-specific rule generators
      iwh/                   -- Parser, writer, Pydantic schema, cleanup, and readers for .iwh "I Was Here" signal files
      lifecycle/             -- Batch design-file bootstrap (quick / full modes); concept deprecation and deletion with TTL guards; sidecar comment helpers
      linkgraph/             -- Safe read-only facade over the SQLite link-graph; health metadata reader; builder
      llm/                   -- Async BAML adapter; ClientRegistry factory; public facade; rate limiter
      playbooks/             -- Markdown playbook parser and serializer; trigger-glob matching index; public API re-exports
      services/              -- Domain logic extracted from CLI: lookup, design, impact, status, describe, sweep, view, symbols, bootstrap, curate, update -- core services paired with *_render.py modules for terminal formatting
      stack/                 -- Stack post Pydantic models, validator, template generator, filename helpers, and public API
      symbolgraph/           -- SQLite-backed symbol graph: schema/DDL with version checks, builder, read-only query API, health metadata, Python import resolver, cross-file call-site resolver
      templates/             -- Bundled text-template loader
        claude/agents/       -- Agent workflow templates; reusable prompt templates
        claude/hooks/        -- Post-edit hook; PreToolUse hook
        config/              -- Default project config template (created by lexictl init)
        cursor/              -- Cursor rules snippet
        help/                -- Bundled help reference text
        hooks/               -- Git post-commit update hook; pre-commit validation hook
        lifecycle/           -- Commented header template for lifecycle files
        rules/               -- Core agent rules; lexi command skill templates
          skills/            -- Skill templates: lexi-concept, lexi-lookup, lexi-search, lexi-stack, topology-builder (with assets/)
        scaffolder/          -- Standard commented header templates
      tokenizer/             -- Token counter abstraction and factory; chars/4 heuristic; Anthropic count_tokens wrapper
      utils/                 -- Project-root discovery; source-to-designs path mapping; SHA-256 hashing; atomic writes; language detection; merge-conflict detection
      validator/             -- Validation check functions, immutable result models, renderers, and auto-fix registry
      wiki/                  -- Wikilink regex utilities; concept file creator; concept parser, serializer, resolver, and in-memory index
  tests/                     -- Mirror of src/ layout, plus tests/fixtures/ (sample_project, curator_library, curator_library_no_graph)
```

## Key Architectural Insights

### Two-CLI Design

Lexibrary exposes two separate Typer apps from the same package. `lexi` ([src/lexibrary/cli/lexi_app.py](src/lexibrary/cli/lexi_app.py)) is the agent-facing CLI for lookups, search, orientation, symbols, trace, and artifact management -- agents may run it freely. `lexictl` ([src/lexibrary/cli/lexictl_app.py](src/lexibrary/cli/lexictl_app.py)) owns destructive or expensive operations: init, bootstrap, update (LLM calls), index, sweep, curate, rules generation. Agents must never run `lexictl`. Both apps share helpers from [src/lexibrary/cli/_shared.py](src/lexibrary/cli/_shared.py) and output through [src/lexibrary/cli/_output.py](src/lexibrary/cli/_output.py) (no bare `print`, no Rich). Registered via `[project.scripts]` in [pyproject.toml](pyproject.toml).

### CLI / Services Separation

The CLI layer ([src/lexibrary/cli/](src/lexibrary/cli/)) contains thin command handlers; all domain logic lives in [src/lexibrary/services/](src/lexibrary/services/). Most services have a paired `*_render.py` module that formats results for terminal output -- CLI handlers call into services and renderers but contain no business logic. This separation lets domain logic be tested and reused without invoking Typer, and makes new output formats a matter of adding a renderer. When adding a new command, implement the core logic in `services/` first and keep the `cli/` handler a thin wrapper.

### Artifact Mirror Layout

Every source file under a configured scope root can have a corresponding design file under `.lexibrary/designs/` that mirrors the source tree. Path mapping is handled by [src/lexibrary/utils/paths.py](src/lexibrary/utils/paths.py). Design files carry YAML frontmatter (metadata) and a markdown body describing role, interface, and dependencies; IWH `.iwh` signals and `.comments.yaml` sidecars live alongside them. When editing a source file, agents must run `lexi lookup <file>` first and `lexi design update <file>` after.

### Dual SQLite Indexes (Link Graph vs Symbol Graph)

The project maintains two distinct SQLite indexes with different purposes. The **link graph** ([src/lexibrary/linkgraph/](src/lexibrary/linkgraph/)) tracks wikilink references between artifacts (concepts, designs, Stack posts, conventions, playbooks). The **symbol graph** ([src/lexibrary/symbolgraph/](src/lexibrary/symbolgraph/)) is a separate SQLite database tracking code-level symbols -- classes, functions, methods, enum members, constants, and call sites resolved across files. Do not conflate them: [symbolgraph/query.py](src/lexibrary/symbolgraph/query.py) is read-only and schema-version-checked, [symbolgraph/builder.py](src/lexibrary/symbolgraph/builder.py) rebuilds from AST parser output, and cross-file resolution happens in [resolver_python.py](src/lexibrary/symbolgraph/resolver_python.py) using [python_imports.py](src/lexibrary/symbolgraph/python_imports.py). `lexi symbols` and `lexi trace` (service: [services/symbols.py](src/lexibrary/services/symbols.py)) are the agent-facing query surfaces.

### Curator Collect/Triage/Dispatch Pipeline

The curator ([src/lexibrary/curator/](src/lexibrary/curator/)) is an autonomous maintenance agent invoked via `lexictl curate`. [coordinator.py](src/lexibrary/curator/coordinator.py) runs a collect/triage/dispatch cycle: [collect_filters.py](src/lexibrary/curator/collect_filters.py) gathers signals (staleness, consistency, deprecation, migration, cascade, auditing, IWH actions), [risk_taxonomy.py](src/lexibrary/curator/risk_taxonomy.py) classifies them, and per-action modules dispatch under LLM budgets ([budget.py](src/lexibrary/curator/budget.py)) gated by an autonomy level ([config.py](src/lexibrary/curator/config.py)). [reconciliation.py](src/lexibrary/curator/reconciliation.py) merges agent-edited design files with current source; [fingerprint.py](src/lexibrary/curator/fingerprint.py) SHA-256-dedups Stack posts against the link graph; [write_contract.py](src/lexibrary/curator/write_contract.py) enforces atomic write semantics across all curator mutations.

### BAML as Prompt Source of Truth

LLM interactions are defined declaratively in [baml_src/](baml_src/) (a second scope root), not inline in Python. BAML compiles these to the generated [src/lexibrary/baml_client/](src/lexibrary/baml_client/) package, which is gitignored-for-edits and excluded from ruff and mypy (see `pyproject.toml`). The Python side ([src/lexibrary/llm/](src/lexibrary/llm/)) is a thin async adapter plus a `ClientRegistry` factory that translates Lexibrary config into two named clients (summarisation, archivist). Editing a prompt means editing a `.baml` file and regenerating the client -- never modify `baml_client/` directly. `lexi design update` and `lexi design comment` invoke the BAML runtime and require `dangerouslyDisableSandbox: true` on macOS (see CLAUDE.md).

## Core Modules

### CLI Layer

*Thin command handlers wiring Typer to the services layer. All CLI output goes through `_output.py` helpers -- no bare `print()` allowed. Each subcommand domain lives in its own module.*

| Module | Purpose |
|--------|---------|
| [src/lexibrary/cli/lexi_app.py](src/lexibrary/cli/lexi_app.py) | Agent CLI root: registers subcommand groups and top-level commands (lookup, search, validate, status, impact, describe, symbols, view, trace) |
| [src/lexibrary/cli/lexictl_app.py](src/lexibrary/cli/lexictl_app.py) | Maintainer CLI: init, bootstrap, update, index, validate, sweep, curate, rules, status, IWH management |
| [src/lexibrary/cli/_shared.py](src/lexibrary/cli/_shared.py) | Shared helpers: project-root resolution, env loading, common status/validate logic |
| [src/lexibrary/cli/_output.py](src/lexibrary/cli/_output.py) | Plain-text output helpers (`info`, `warn`, `error`, `hint`, `markdown_table`) used by all commands |
| [src/lexibrary/cli/curate.py](src/lexibrary/cli/curate.py) | Curator CLI entry point: argument validation, lifecycle concerns, report rendering |
| [src/lexibrary/cli/design.py](src/lexibrary/cli/design.py) | `lexi design update / comment` -- routes to archivist pipeline and sidecar writer |

### Services Layer

*Domain logic extracted from CLI handlers. Each service module returns structured data; paired `*_render.py` modules format it for output.*

| Module | Purpose |
|--------|---------|
| [src/lexibrary/services/lookup.py](src/lexibrary/services/lookup.py) | Core lookup: resolves file/directory context, design files, IWH signals, conventions, and topology hints |
| [src/lexibrary/services/design.py](src/lexibrary/services/design.py) | Pre-flight policy for whether a design file should be (re)generated (IWH signals, frontmatter protection, staleness) |
| [src/lexibrary/services/impact.py](src/lexibrary/services/impact.py) | Reverse-dependent computation for a source file using the link graph |
| [src/lexibrary/services/status.py](src/lexibrary/services/status.py) | Library health collection: staleness counts, artifact stats, validation summary |
| [src/lexibrary/services/sweep.py](src/lexibrary/services/sweep.py) | Sweep logic for bulk maintenance operations |
| [src/lexibrary/services/view.py](src/lexibrary/services/view.py) | View service for rendering artifact content by ID |
| [src/lexibrary/services/symbols.py](src/lexibrary/services/symbols.py) | Symbol graph query service backing `lexi symbols` and `lexi trace` |
| [src/lexibrary/services/describe.py](src/lexibrary/services/describe.py) | Validate directory, update billboard text in `.aindex`, write atomically |

### Curator

*Autonomous maintenance pipeline: collects signals, triages by risk, dispatches actions within budgets.*

| Module | Purpose |
|--------|---------|
| [src/lexibrary/curator/coordinator.py](src/lexibrary/curator/coordinator.py) | Orchestrates the collect/triage/dispatch cycle |
| [src/lexibrary/curator/config.py](src/lexibrary/curator/config.py) | Runtime configuration: autonomy level, LLM budgets, per-action risk overrides |
| [src/lexibrary/curator/collect_filters.py](src/lexibrary/curator/collect_filters.py) | Gathers signals from the library (staleness, consistency, deprecation, etc.) |
| [src/lexibrary/curator/risk_taxonomy.py](src/lexibrary/curator/risk_taxonomy.py) | Classifies maintenance actions by risk level for autonomy gating |
| [src/lexibrary/curator/budget.py](src/lexibrary/curator/budget.py) | Tracks and enforces LLM call budgets during a run |
| [src/lexibrary/curator/dispatch_context.py](src/lexibrary/curator/dispatch_context.py) | Shared context object passed to every action during dispatch |
| [src/lexibrary/curator/reconciliation.py](src/lexibrary/curator/reconciliation.py) | Merges agent-edited design files with current source, preserving agent knowledge |
| [src/lexibrary/curator/comments.py](src/lexibrary/curator/comments.py) | Classifies sidecar comments; merges durable ones into Insights, promotes actionable ones to Stack posts |
| [src/lexibrary/curator/fingerprint.py](src/lexibrary/curator/fingerprint.py) | SHA-256 dedup for curator-created Stack posts using the link graph |
| [src/lexibrary/curator/write_contract.py](src/lexibrary/curator/write_contract.py) | Shared atomic write / hashing contract used by all curator mutations |
| [src/lexibrary/curator/staleness.py](src/lexibrary/curator/staleness.py) | Detects stale design files that need regeneration |
| [src/lexibrary/curator/consistency.py](src/lexibrary/curator/consistency.py) | Checks consistency between source and design artifacts |
| [src/lexibrary/curator/consistency_fixes.py](src/lexibrary/curator/consistency_fixes.py) | Executes fix actions (orphan removal, frontmatter repair, regeneration) emitted by the consistency checker |
| [src/lexibrary/curator/validation_fixers.py](src/lexibrary/curator/validation_fixers.py) | Auto-fix actions for validator-detected issues |

### Domain Models and Artifacts

*Pydantic v2 models for every artifact type. All live under [src/lexibrary/artifacts/](src/lexibrary/artifacts/). Each model ships with paired parser and serializer modules where applicable.*

| Module | Purpose |
|--------|---------|
| [src/lexibrary/artifacts/aindex.py](src/lexibrary/artifacts/aindex.py) | Models for `.aindex` directory-level index files (`AIndexFile`, `AIndexEntry`) |
| [src/lexibrary/artifacts/design_file.py](src/lexibrary/artifacts/design_file.py) | Models for per-file design documents (`DesignFile`, `DesignFileFrontmatter`) |
| [src/lexibrary/artifacts/concept.py](src/lexibrary/artifacts/concept.py) | Models for concept wiki files (`ConceptFrontmatter`) |
| [src/lexibrary/artifacts/convention.py](src/lexibrary/artifacts/convention.py) | Models for convention files (`ConventionFrontmatter`, `ConventionFile`) |
| [src/lexibrary/artifacts/playbook.py](src/lexibrary/artifacts/playbook.py) | Models for playbook files (`PlaybookFrontmatter`, `PlaybookFile`) |
| [src/lexibrary/artifacts/ids.py](src/lexibrary/artifacts/ids.py) | Canonical artifact-ID prefix registry, parser, sequential generator, and resolver |
| [src/lexibrary/artifacts/title_check.py](src/lexibrary/artifacts/title_check.py) | Duplicate-title scanner (blocking same-kind, cross-kind warnings) |

### Orchestration

| Module | Purpose |
|--------|---------|
| [src/lexibrary/archivist/pipeline.py](src/lexibrary/archivist/pipeline.py) | End-to-end update pipeline: diff detection, LLM generation, post-processing |
| [src/lexibrary/archivist/skeleton.py](src/lexibrary/archivist/skeleton.py) | Non-LLM fallback: lightweight design files from AST analysis |
| [src/lexibrary/archivist/topology.py](src/lexibrary/archivist/topology.py) | Generates `raw-topology.md` from `.aindex` billboards for this skill |
| [src/lexibrary/lifecycle/bootstrap.py](src/lexibrary/lifecycle/bootstrap.py) | Batch design-file creation (quick heuristic or full LLM mode) |
| [src/lexibrary/search.py](src/lexibrary/search.py) | Unified cross-artifact search (concepts, conventions, designs, Stack posts, playbooks) |
| [src/lexibrary/indexer/orchestrator.py](src/lexibrary/indexer/orchestrator.py) | Coordinates `.aindex` generation across all directories |
| [src/lexibrary/indexer/generator.py](src/lexibrary/indexer/generator.py) | In-memory `AIndexFile` builder from filesystem + `.lexibrary` mirror |

### Symbol Graph

| Module | Purpose |
|--------|---------|
| [src/lexibrary/symbolgraph/schema.py](src/lexibrary/symbolgraph/schema.py) | Canonical DDL, pragmas, and schema-version policy; rebuilds DB on version mismatch |
| [src/lexibrary/symbolgraph/builder.py](src/lexibrary/symbolgraph/builder.py) | Populates symbols.db from AST parser output |
| [src/lexibrary/symbolgraph/query.py](src/lexibrary/symbolgraph/query.py) | Read-only, audited Python API for querying symbols.db |
| [src/lexibrary/symbolgraph/health.py](src/lexibrary/symbolgraph/health.py) | Fast health metadata (counts, built-at) for status/validation |
| [src/lexibrary/symbolgraph/resolver_python.py](src/lexibrary/symbolgraph/resolver_python.py) | Phase-2 cross-file resolution of Python call sites to concrete symbol row IDs |
| [src/lexibrary/symbolgraph/python_imports.py](src/lexibrary/symbolgraph/python_imports.py) | Per-file import cache used by the Python resolver |

### Configuration

| Module | Purpose |
|--------|---------|
| [src/lexibrary/config/loader.py](src/lexibrary/config/loader.py) | Discovers and merges global + project YAML config into `LexibraryConfig`; handles deprecated-section migration |
| [src/lexibrary/config/schema.py](src/lexibrary/config/schema.py) | Pydantic v2 config schema with defaults for scope roots, LLM, token budgets, playbooks, IWH |

### Utilities

| Module | Purpose |
|--------|---------|
| [src/lexibrary/utils/paths.py](src/lexibrary/utils/paths.py) | Maps source files to `.lexibrary/designs/` mirror paths and locates the symbol-graph DB |
| [src/lexibrary/utils/hashing.py](src/lexibrary/utils/hashing.py) | SHA-256 digest utilities for caching and deduplication |
| [src/lexibrary/utils/atomic.py](src/lexibrary/utils/atomic.py) | Atomic file writes via temp-file-then-rename |
| [src/lexibrary/utils/root.py](src/lexibrary/utils/root.py) | Discovers project root by walking up to find `.lexibrary/` |
| [src/lexibrary/ignore/matcher.py](src/lexibrary/ignore/matcher.py) | Unified ignore matcher combining config, `.gitignore`, and `.lexignore` |

## Test Structure

Tests mirror the source layout under [tests/](tests/). Each `tests/test_<subpackage>/` directory corresponds to `src/lexibrary/<subpackage>/`.

| Test directory | Source directory |
|----------------|-----------------|
| [tests/test_archivist/](tests/test_archivist/) | [src/lexibrary/archivist/](src/lexibrary/archivist/) |
| [tests/test_artifacts/](tests/test_artifacts/) | [src/lexibrary/artifacts/](src/lexibrary/artifacts/) |
| [tests/test_ast_parser/](tests/test_ast_parser/) | [src/lexibrary/ast_parser/](src/lexibrary/ast_parser/) |
| [tests/test_cli/](tests/test_cli/) | [src/lexibrary/cli/](src/lexibrary/cli/) |
| [tests/test_config/](tests/test_config/) | [src/lexibrary/config/](src/lexibrary/config/) |
| [tests/test_conventions/](tests/test_conventions/) | [src/lexibrary/conventions/](src/lexibrary/conventions/) |
| [tests/test_crawler/](tests/test_crawler/) | [src/lexibrary/crawler/](src/lexibrary/crawler/) |
| [tests/test_curator/](tests/test_curator/) | [src/lexibrary/curator/](src/lexibrary/curator/) |
| [tests/test_hooks/](tests/test_hooks/) | [src/lexibrary/hooks/](src/lexibrary/hooks/) |
| [tests/test_ignore/](tests/test_ignore/) | [src/lexibrary/ignore/](src/lexibrary/ignore/) |
| [tests/test_indexer/](tests/test_indexer/) | [src/lexibrary/indexer/](src/lexibrary/indexer/) |
| [tests/test_init/](tests/test_init/) | [src/lexibrary/init/](src/lexibrary/init/) |
| [tests/test_iwh/](tests/test_iwh/) | [src/lexibrary/iwh/](src/lexibrary/iwh/) |
| [tests/test_lifecycle/](tests/test_lifecycle/) | [src/lexibrary/lifecycle/](src/lexibrary/lifecycle/) |
| [tests/test_linkgraph/](tests/test_linkgraph/) | [src/lexibrary/linkgraph/](src/lexibrary/linkgraph/) |
| [tests/test_llm/](tests/test_llm/) | [src/lexibrary/llm/](src/lexibrary/llm/) |
| [tests/test_services/](tests/test_services/) | [src/lexibrary/services/](src/lexibrary/services/) |
| [tests/test_stack/](tests/test_stack/) | [src/lexibrary/stack/](src/lexibrary/stack/) |
| [tests/test_symbolgraph/](tests/test_symbolgraph/) | [src/lexibrary/symbolgraph/](src/lexibrary/symbolgraph/) |
| [tests/test_templates/](tests/test_templates/) | [src/lexibrary/templates/](src/lexibrary/templates/) |
| [tests/test_tokenizer/](tests/test_tokenizer/) | [src/lexibrary/tokenizer/](src/lexibrary/tokenizer/) |
| [tests/test_utils/](tests/test_utils/) | [src/lexibrary/utils/](src/lexibrary/utils/) |
| [tests/test_validator/](tests/test_validator/) | [src/lexibrary/validator/](src/lexibrary/validator/) |
| [tests/test_wiki/](tests/test_wiki/) | [src/lexibrary/wiki/](src/lexibrary/wiki/) |

Playbooks do not have a dedicated subdirectory -- their tests live as top-level files ([tests/test_playbook_cli.py](tests/test_playbook_cli.py), [test_playbook_index.py](tests/test_playbook_index.py), [test_playbook_model.py](tests/test_playbook_model.py), [test_playbook_parser.py](tests/test_playbook_parser.py), [test_playbook_search.py](tests/test_playbook_search.py), [test_playbook_serializer.py](tests/test_playbook_serializer.py), [test_playbook_validation.py](tests/test_playbook_validation.py)) covering [src/lexibrary/playbooks/](src/lexibrary/playbooks/). Other top-level test files: [test_errors.py](tests/test_errors.py), [test_exceptions.py](tests/test_exceptions.py), [test_search.py](tests/test_search.py), [test_search_upgrade.py](tests/test_search_upgrade.py), [test_skills_mirror.py](tests/test_skills_mirror.py).

Test fixtures live in [tests/fixtures/](tests/fixtures/) (including [tests/fixtures/sample_project/](tests/fixtures/sample_project/), [tests/fixtures/curator_library/](tests/fixtures/curator_library/), and [tests/fixtures/curator_library_no_graph/](tests/fixtures/curator_library_no_graph/)). AST parser and symbol graph tests have their own under-test fixtures directories. Shared helpers are in [tests/conftest.py](tests/conftest.py).

Convention: When adding tests for a module that already has a test file, add new test cases to the existing file rather than creating a new one. Create a new test file only when covering a module that has no existing test file.
