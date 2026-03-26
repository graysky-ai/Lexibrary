# Project Topology

**Lexibrary** is an AI-friendly codebase indexer that produces `.aindex` files and per-file design documents so LLM-based coding agents can navigate, understand, and edit a repository with structured context.

## Directory Tree Legend

Directory descriptions in the tree below are synthesised keyword fragments drawn from the individual file descriptions within that directory. Fragments are separated by `;` -- each fragment describes a **different file** in that directory, not multiple aspects of the same file. Use these fragments to decide which directory to explore next without opening every file.

## Entry Points

| Command / Import | Role | Entry File |
|-----------------|------|-----------|
| `lexi` | Agent-facing CLI -- lookups, search, orientation, validation, Stack/convention/design helpers | `src/lexibrary/cli/lexi_app.py` |
| `lexictl` | Maintainer-facing CLI -- init, bootstrap, index, update, validate, sweep, agent-rules management | `src/lexibrary/cli/lexictl_app.py` |
| `python -m lexibrary` | Module entry point, starts the agent-facing CLI (`lexi_app`) | `src/lexibrary/__main__.py` |

Registered via `[project.scripts]` in `pyproject.toml`. Both entry points are re-exported from `src/lexibrary/cli/__init__.py`.

## Project Config

| Property | Value |
|----------|-------|
| Language / runtime | Python 3.11+ |
| Build system | `hatchling` |
| Package manager | `uv` |
| Type checker | `mypy` (strict mode) |
| Linter / formatter | `ruff` (line-length 100, target py311) |
| Test runner | `pytest` (testpaths: `tests/`, pythonpath: `src/`) |
| LLM integration | `baml-py` 0.218.1, prompt definitions in `baml_src/` |

## Directory Tree

```
Lexibrarian/
  baml_src/                  -- LLM prompt definitions (BAML DSL): archivist, summarizer, types
  docs/
    agent/                   -- Agent-facing docs: CLI reference, workflows, prohibited commands
    user/                    -- User-facing docs: getting-started, configuration, troubleshooting
  src/
    lexibrary/               -- Main package: error aggregation; package metadata; exception hierarchy
      archivist/             -- Non-LLM skeleton generator; archivist facade; deterministic topology generator from .aindex summaries
      artifacts/             -- Pydantic models for convention frontmatter; design-file schemas; atomic file writer
      ast_parser/            -- Tree-sitter extractors (Python/JS/TS); interface skeleton serializer; canonical schemas
      cli/                   -- Agent-facing CLI (lexi); maintainer CLI (lexictl); concept management commands
      config/                -- Config namespace re-exports; two-tier YAML config loader; Pydantic v2 config schema
      conventions/           -- Convention subsystem API; markdown serializer; scope-aware convention index
      crawler/               -- Bottom-up crawl engine with LLM summarization; safe text extraction; directory discovery with ignore filtering
      hooks/                 -- Git hook installers (pre-commit, post-commit)
      ignore/                -- Ignore matcher factory; unified matcher; small adapter
      indexer/               -- Package init; in-memory AIndexFile builder; end-to-end .aindex orchestrator
      init/                  -- Environment/metadata auto-detection; interactive 9-step wizard; scaffolding helper
        rules/               -- Marker-delimited section utilities; Markdown template loader; environment-specific rule generators
      iwh/                   -- IWH signal cleanup; signal writer; Pydantic schema for .iwh files
      lifecycle/             -- Concept deprecation/deletion; enrichment queue; batch design-file bootstrap
      linkgraph/             -- SQLite link-graph: health metadata; read-only query API; schema/DDL management
      llm/                   -- Async BAML adapter; client-registry factory; async rate limiter
      playbooks/             -- Playbook parser; in-memory index with trigger-glob matching; public API re-exports
      stack/                 -- Stack post template generator; Pydantic models; public API re-exports
      templates/             -- Template loader utility
        claude/agents/       -- Agent workflow templates; reusable prompt templates
        claude/hooks/        -- Post-edit hook; PreToolUse hook
        config/              -- Default project config template (created by lexictl init)
          skills/            -- Skill templates: lexi-concepts, lexi-lookup, lexi-orient, lexi-search, lexi-stack, topology-builder
        hooks/               -- Git post-commit hook template; pre-commit validation hook template
        scaffolder/          -- Comment header template; .lexignore header template
      tokenizer/             -- Token counter factory; API re-exports; chars/4 heuristic fallback
      utils/                 -- Source-to-designs path mapping; language detection; merge-conflict detection
      validator/             -- Validation check coordinator; result models; individual check functions
      wiki/                  -- Wikilink resolver; concept file creator; concept serializer
  tests/                     -- Mirror of src/ layout, plus fixtures in tests/fixtures/sample_project/
```

## Key Architectural Insights

### Two-CLI Design

Lexibrary exposes two separate CLIs from the same package. `lexi` (defined in `src/lexibrary/cli/lexi_app.py`) is the agent-facing CLI for lookups, search, orientation, and artifact management -- agents may run it freely. `lexictl` (defined in `src/lexibrary/cli/lexictl_app.py`) handles destructive or expensive operations: init, bootstrap, update (LLM calls), sweep, and agent-rule generation. Agents must never run `lexictl` commands. Both are Typer apps sharing common helpers from `src/lexibrary/cli/_shared.py` and registered via `[project.scripts]` in `pyproject.toml`.

### Artifact Mirror Layout

Every source file under `src/` can have a corresponding design file under `.lexibrary/designs/` that mirrors the source tree structure. The path mapping is handled by `src/lexibrary/utils/paths.py`. Design files contain YAML frontmatter with metadata and a markdown body describing the file's role, interface, and dependencies. When editing a source file, the corresponding design file should be updated if it exists.

### Pipeline as Coordination Point

The archivist pipeline (`src/lexibrary/archivist/pipeline.py`) orchestrates the full update cycle: diff detection, LLM-based design-file generation (or skeleton fallback), then post-processing (indexing, topology generation, deprecation, link-graph rebuild). Individual subsystems (indexer, topology, linkgraph) are designed to be called from the pipeline rather than invoked directly.

## Core Modules

### CLI Layer

*Command handlers and output infrastructure. All CLI output goes through `_output.py` helpers -- no bare `print()` allowed.*

| Module | Purpose |
|--------|---------|
| `src/lexibrary/cli/lexi_app.py` | Agent-facing CLI: orient, lookup, search, validate, status, impact, and subcommand groups for Stack/concepts/conventions/designs/playbooks |
| `src/lexibrary/cli/lexictl_app.py` | Maintainer CLI: init, bootstrap, update, index, validate, sweep, rules, status, IWH management |
| `src/lexibrary/cli/_shared.py` | Shared helpers: project-root resolution, env loading, common status/validate logic |
| `src/lexibrary/cli/_output.py` | Plain-text output helpers (`info`, `warn`, `error`, `hint`, `markdown_table`) used by all commands |

### Domain Models and Artifacts

*Pydantic v2 models for every artifact type. All live under `src/lexibrary/artifacts/`.*

| Module | Purpose |
|--------|---------|
| `src/lexibrary/artifacts/aindex.py` | Models for `.aindex` directory-level index files (`AIndexFile`, `AIndexEntry`) |
| `src/lexibrary/artifacts/design_file.py` | Models for per-file design documents (`DesignFile`, `DesignFileFrontmatter`) |
| `src/lexibrary/artifacts/concept.py` | Models for concept wiki files (`ConceptFrontmatter`) |
| `src/lexibrary/artifacts/convention.py` | Models for convention files (`ConventionFrontmatter`, `ConventionFile`) |
| `src/lexibrary/artifacts/playbook.py` | Models for playbook files (`PlaybookFrontmatter`, `PlaybookFile`) |

### Services and Orchestration

| Module | Purpose |
|--------|---------|
| `src/lexibrary/archivist/pipeline.py` | End-to-end update pipeline: diff detection, LLM generation, post-processing |
| `src/lexibrary/archivist/service.py` | Async LLM service for design-file generation via BAML |
| `src/lexibrary/archivist/skeleton.py` | Non-LLM fallback: generates lightweight design files from AST analysis |
| `src/lexibrary/archivist/topology.py` | Generates raw topology from `.aindex` billboard summaries for the topology-builder skill |
| `src/lexibrary/lifecycle/bootstrap.py` | Batch design-file creation (quick heuristic or full LLM mode) |
| `src/lexibrary/search.py` | Unified cross-artifact search (concepts, conventions, designs, Stack posts, playbooks) |
| `src/lexibrary/indexer/orchestrator.py` | Coordinates `.aindex` artifact generation across all directories |

### Configuration

| Module | Purpose |
|--------|---------|
| `src/lexibrary/config/loader.py` | Discovers and merges global + project YAML config into `LexibraryConfig` |
| `src/lexibrary/config/schema.py` | Pydantic v2 config schema with defaults for daemon, crawler, LLM, token budgets, topology |

### Utilities

| Module | Purpose |
|--------|---------|
| `src/lexibrary/utils/paths.py` | Maps source files to `.lexibrary/designs/` mirror paths |
| `src/lexibrary/utils/hashing.py` | SHA-256 digest utilities for caching and deduplication |
| `src/lexibrary/utils/atomic.py` | Atomic file writes via temp-file-then-rename |
| `src/lexibrary/utils/root.py` | Discovers project root by walking up to find `.lexibrary/` |
| `src/lexibrary/ignore/matcher.py` | Unified ignore matcher combining config, `.gitignore`, and `.lexignore` |

## Test Structure

Tests mirror the source layout under `tests/`. Each `tests/test_<subpackage>/` directory corresponds to `src/lexibrary/<subpackage>/`.

| Test directory | Source directory |
|----------------|-----------------|
| `tests/test_archivist/` | `src/lexibrary/archivist/` |
| `tests/test_artifacts/` | `src/lexibrary/artifacts/` |
| `tests/test_ast_parser/` | `src/lexibrary/ast_parser/` |
| `tests/test_cli/` | `src/lexibrary/cli/` |
| `tests/test_config/` | `src/lexibrary/config/` |
| `tests/test_conventions/` | `src/lexibrary/conventions/` |
| `tests/test_crawler/` | `src/lexibrary/crawler/` |
| `tests/test_hooks/` | `src/lexibrary/hooks/` |
| `tests/test_ignore/` | `src/lexibrary/ignore/` |
| `tests/test_indexer/` | `src/lexibrary/indexer/` |
| `tests/test_init/` | `src/lexibrary/init/` |
| `tests/test_iwh/` | `src/lexibrary/iwh/` |
| `tests/test_lifecycle/` | `src/lexibrary/lifecycle/` |
| `tests/test_linkgraph/` | `src/lexibrary/linkgraph/` |
| `tests/test_llm/` | `src/lexibrary/llm/` |
| `tests/test_stack/` | `src/lexibrary/stack/` |
| `tests/test_templates/` | `src/lexibrary/templates/` |
| `tests/test_tokenizer/` | `src/lexibrary/tokenizer/` |
| `tests/test_utils/` | `src/lexibrary/utils/` |
| `tests/test_validator/` | `src/lexibrary/validator/` |
| `tests/test_wiki/` | `src/lexibrary/wiki/` |

Top-level test files: `tests/test_errors.py`, `tests/test_exceptions.py`, `tests/test_search.py`, `tests/test_playbook_cli.py`, `tests/test_playbook_index.py`, `tests/test_playbook_model.py`, `tests/test_playbook_parser.py`, `tests/test_playbook_search.py`, `tests/test_playbook_serializer.py`, `tests/test_playbook_validation.py`, `tests/test_skills_mirror.py`.

Test fixtures live in `tests/fixtures/sample_project/`. Shared helpers are in `tests/conftest.py`.

Convention: When adding tests for a module that already has a test file, add new test cases to the existing file rather than creating a new one. Create a new test file only when covering a module that has no existing test file.
