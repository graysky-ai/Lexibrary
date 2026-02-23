## Context

Lexibrary is an AI-friendly codebase indexer that produces a `.lexibrary/` directory containing design files, `.aindex` routing tables, a concepts wiki, a Stack Q&A knowledge base, and a link graph index. It has two CLIs: `lexictl` (operator-facing maintenance) and `lexi` (agent-facing lookups and queries). All current documentation is implementation-focused — `blueprints/` for agent-contributors, `plans/` for roadmap, and `openspec/` for change tracking. No documentation exists for the two primary audiences: (1) operators/teams adopting Lexibrary for their projects, and (2) AI agents working within Lexibrary-managed codebases.

The config system uses `.lexibrary/config.yaml` with Pydantic 2 validation. The init wizard guides first-time setup. Agent rules are injected into environment-specific files (CLAUDE.md, .cursor/rules/, AGENTS.md) via `lexictl setup --update`.

## Goals / Non-Goals

**Goals:**
- Create a complete `docs/` directory with two clearly separated doc sets: User Docs and Agent Docs
- User Docs: enable an operator to install, configure, and maintain Lexibrary without reading source code
- Agent Docs: enable an AI agent to navigate and use all Lexibrary features with just the docs and CLI help
- Cover all existing features exhaustively (CLI commands, config keys, artifact types, workflows)
- Keep docs maintainable — reference concepts and workflows rather than duplicating implementation details
- Provide a landing page (`docs/README.md`) that routes readers to the right doc set

**Non-Goals:**
- API/library documentation (Lexibrary is a CLI tool, not a library)
- Contributor/developer docs (that's `blueprints/` and `plans/`)
- Auto-generated docs from code (may come later, out of scope here)
- Hosting or publishing infrastructure (GitHub Pages, ReadTheDocs, etc.)
- Internationalisation

## Decisions

### D1: Two-set split — User Docs vs Agent Docs

Documentation is split into `docs/user/` and `docs/agent/` because the two audiences have fundamentally different needs. Operators need setup/config/maintenance guidance. Agents need workflow protocols and CLI reference for the `lexi` command set. Mixing them would force readers to skip irrelevant sections.

**Alternative considered:** Single flat `docs/` directory with audience tags in each file. Rejected because it complicates navigation and agents are better served by a focused, concise set.

### D2: Markdown-only, no build step

All docs are plain Markdown files. No static site generator, no build step, no YAML frontmatter beyond what's standard. This keeps docs readable in GitHub, in IDEs, and by agents consuming them as context.

**Alternative considered:** MkDocs or Docusaurus. Rejected for v1 — adds dependency and build complexity. Can be layered on later without changing content.

### D3: Config reference derived from schema.py

The configuration reference doc (`docs/user/configuration.md`) documents every key from `LexibraryConfig` and its sub-models. Structure mirrors the YAML nesting. Default values are documented inline. This is manually written (not auto-generated) to include explanations and usage guidance.

### D4: CLI reference documents actual commands

CLI reference docs list every command, subcommand, flag, and argument currently implemented. They reference the Typer app definitions in `cli/lexictl_app.py` and `cli/lexi_app.py`. Not auto-generated — manually written with examples and context.

### D5: Agent docs are self-contained

Agent docs do not assume the agent has read User Docs. Each agent doc is self-contained enough that an agent can understand it without cross-referencing. This aligns with how agents consume context — they may only see a subset of docs.

### D6: Exhaustive then trim

Per user request, the initial doc set is exhaustive. Individual docs can be merged or removed in future iterations based on feedback.

## Document Inventory

### docs/README.md — Landing Page
Routes readers to the correct doc set based on audience. Brief project description, links to both sets.

### User Docs (`docs/user/`)

| # | File | Purpose |
|---|------|---------|
| 1 | `getting-started.md` | Prerequisites, installation (`uv`/`pip`), first `lexictl init`, first `lexictl update`, verifying it worked |
| 2 | `how-it-works.md` | Conceptual overview: what Lexibrary produces, the artifact lifecycle (source → design file → START_HERE), the operator/agent split, how `ChangeLevel` prevents overwriting agent edits |
| 3 | `configuration.md` | Full config.yaml reference — every key, sub-model, default value, and what it controls. Covers: `scope_root`, `project_name`, `agent_environment`, `iwh`, `llm`, `token_budgets`, `mapping`, `ignore`, `daemon`, `crawl`, `ast` |
| 4 | `lexictl-reference.md` | Complete `lexictl` CLI reference: `init`, `update`, `validate`, `status`, `setup`, `sweep`, `daemon`. Every flag and argument with examples |
| 5 | `project-setup.md` | Detailed init wizard walkthrough — what each of the 8 steps does, `--defaults` for CI, re-init guard, how to change settings after init |
| 6 | `design-file-generation.md` | How `lexictl update` works: file discovery, change detection (SHA-256 hash comparison), ChangeLevel classification (none/cosmetic/structural/new), LLM generation pipeline, `--changed-only` for hooks, progress reporting |
| 7 | `validation.md` | How `lexictl validate` works: 13 checks grouped by severity (error/warning/info), `--check` for single checks, `--severity` filter, `--json` for CI, exit codes |
| 8 | `ci-integration.md` | CI/CD recipes: post-commit hook via `lexictl setup --hooks`, `lexictl update --changed-only` in hooks, `lexictl validate` as CI gate, `lexictl status --quiet` for notifications, daemon sweep modes |
| 9 | `library-structure.md` | What `.lexibrary/` contains: directory layout, design files (mirror tree), START_HERE.md, concepts/, stack/, .aindex files, config.yaml, index.db link graph. What each artifact type is and where it lives |
| 10 | `concepts-wiki.md` | Concepts wiki for operators: what concepts are, how they're created (`lexi concept new`), frontmatter fields (title, aliases, tags, status), wikilink syntax, concept lifecycle (draft → active → deprecated) |
| 11 | `stack-qa.md` | Stack Q&A for operators: what Stack posts are, creating posts, answer workflow, voting, accepting answers, status lifecycle (open → resolved), searching and filtering |
| 12 | `link-graph.md` | The SQLite link graph index: what it indexes (dependencies, wikilinks, tags), how it's built (`lexictl update`), what queries it accelerates (`lexi search`, `lexi lookup` reverse deps), health metadata in `lexictl status` |
| 13 | `ignore-patterns.md` | Ignore system: `.lexignore` file, `.gitignore` integration (`ignore.use_gitignore`), `ignore.additional_patterns` config, built-in defaults, how patterns interact during file discovery |
| 14 | `troubleshooting.md` | Common issues: LLM API errors, stale design files, missing design files, validation failures, daemon issues, init problems, config parsing errors. Each with symptoms, cause, and fix |
| 15 | `upgrading.md` | Version upgrade guide: config schema changes, new config keys with defaults, re-running `lexictl setup --update`, when to re-run `lexictl update` |

### Agent Docs (`docs/agent/`)

| # | File | Purpose |
|---|------|---------|
| 1 | `README.md` | Agent overview: what Lexibrary is (from the agent's perspective), what `.lexibrary/` contains, how to use it to be more effective |
| 2 | `orientation.md` | Session start protocol: read START_HERE.md, check for .iwh files, run `lexi search` to orient. Detailed walkthrough of what each step reveals |
| 3 | `lexi-reference.md` | Complete `lexi` CLI reference: `lookup`, `index`, `describe`, `concepts`, `concept new`, `concept link`, `stack post/search/answer/vote/accept/view/list`, `search`. Every flag and argument |
| 4 | `lookup-workflow.md` | Before-edit workflow: run `lexi lookup <file>`, understand the design file sections (frontmatter, summary, interface skeleton, wikilinks), check conventions from .aindex, read dependents |
| 5 | `update-workflow.md` | After-edit workflow: update the design file in `.lexibrary/` to reflect changes, set `updated_by: agent` in frontmatter, when to update vs when to let `lexictl update` handle it |
| 6 | `concepts.md` | Using the concepts wiki: `lexi concepts <topic>` to search, `lexi concept new` to create, `lexi concept link` to link to design files. When to create a concept (recurring pattern, architectural decision, domain term) |
| 7 | `stack.md` | Using Stack Q&A: `lexi stack search` before debugging, `lexi stack post` after solving bugs, answering existing posts, voting, searching by tag/scope/concept/status |
| 8 | `search.md` | Cross-artifact unified search: `lexi search <query>`, `--tag`, `--scope` filters. What results include (concepts, design files, Stack posts). When to use search vs lookup |
| 9 | `iwh.md` | I Was Here signals: when to create (leaving work incomplete), what to include (description, next steps, scope), where to place them, how to consume them (read → act → delete) |
| 10 | `prohibited-commands.md` | What agents must NOT do: never run `lexictl` commands, never modify `.lexibrary/config.yaml`, never delete `.lexibrary/` contents directly. Why these restrictions exist |
| 11 | `quick-reference.md` | Single-page cheat sheet: session start checklist, before-edit checklist, after-edit checklist, key commands table, common scenarios |

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| Docs drift from code over time | Keep docs conceptual/workflow-focused. Avoid duplicating implementation details. Link to `--help` output for flag details. Add "maintaining docs" to future change proposals that modify CLI or config. |
| Exhaustive doc set may be overwhelming | Clear landing page with audience routing. Each doc has a focused scope. Table of contents in README.md. Can merge docs later based on feedback. |
| Agent docs may duplicate injected rules | Agent docs expand on rules with examples and context. Rules are terse directives; docs explain the "why" and "how". |
| Config reference may lag behind schema.py | Configuration doc structure mirrors schema.py. When schema changes, the config doc should be updated in the same change. |

## Directory Layout

```
docs/
├── README.md                        # Landing page
├── user/
│   ├── getting-started.md           # Installation + first run
│   ├── how-it-works.md              # Conceptual overview
│   ├── configuration.md             # Full config reference
│   ├── lexictl-reference.md         # lexictl CLI reference
│   ├── project-setup.md             # Init wizard walkthrough
│   ├── design-file-generation.md    # lexictl update deep dive
│   ├── validation.md                # lexictl validate deep dive
│   ├── ci-integration.md            # CI/CD recipes
│   ├── library-structure.md         # .lexibrary/ anatomy
│   ├── concepts-wiki.md             # Concepts for operators
│   ├── stack-qa.md                  # Stack Q&A for operators
│   ├── link-graph.md                # Link graph index
│   ├── ignore-patterns.md           # Ignore system
│   ├── troubleshooting.md           # Common issues + fixes
│   └── upgrading.md                 # Version upgrade guide
└── agent/
    ├── README.md                    # Agent overview
    ├── orientation.md               # Session start protocol
    ├── lexi-reference.md            # lexi CLI reference
    ├── lookup-workflow.md            # Before-edit workflow
    ├── update-workflow.md            # After-edit workflow
    ├── concepts.md                  # Using the concepts wiki
    ├── stack.md                     # Using Stack Q&A
    ├── search.md                    # Unified search
    ├── iwh.md                       # I Was Here signals
    ├── prohibited-commands.md       # What NOT to do
    └── quick-reference.md           # Cheat sheet
```

## Open Questions

None — the scope is documentation-only with no design decisions requiring external input. Content can be refined during implementation.
