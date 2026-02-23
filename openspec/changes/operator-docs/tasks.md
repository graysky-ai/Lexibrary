## 1. Documentation Skeleton + Landing Page

> **Depends on:** Nothing (can start immediately)
> **Unlocks:** Groups 2, 3

- [x] 1.1 Create `docs/` directory with `user/` and `agent/` subdirectories
- [x] 1.2 Write `docs/README.md` — landing page with project description, audience routing (operators → `user/`, agents → `agent/`), and table of contents for both doc sets

## 2. User Docs — Core (Getting Started, How It Works, Configuration)

> **Depends on:** Group 1
> **Unlocks:** Groups 4, 5, 6, 7

- [x] 2.1 Write `docs/user/getting-started.md` — prerequisites (Python 3.11+, uv or pip), installation (`uv sync` / `pip install`), first `lexictl init` walkthrough, first `lexictl update`, verifying output (`lexictl status`), next steps
- [x] 2.2 Write `docs/user/how-it-works.md` — what Lexibrary is, the artifact lifecycle (source files → design files → START_HERE.md), the two CLIs (`lexi` for agents, `lexictl` for operators), how agents and operators collaborate, ChangeLevel classification (none/cosmetic/structural/new) and how it prevents overwriting agent edits, the `.lexibrary/` output directory
- [x] 2.3 Write `docs/user/configuration.md` — full config.yaml reference structured to mirror the YAML nesting: top-level keys (`scope_root`, `project_name`, `agent_environment`), `iwh` section, `llm` section (provider, model, api_key_env, max_retries, timeout), `token_budgets` section (all 5 budget keys), `mapping` section, `ignore` section (use_gitignore, additional_patterns), `daemon` section (all 6 keys), `crawl` section (max_file_size_kb, binary_extensions), `ast` section (enabled, languages). Include default values and explanations for each key
- [x] 2.4 Write `docs/user/library-structure.md` — anatomy of `.lexibrary/`: config.yaml, START_HERE.md, mirror tree of design files (.md), .aindex routing tables, concepts/ directory, stack/ directory, index.db (link graph, gitignored), daemon.pid and logs. Explain what each artifact type is and how it's produced

## 3. Agent Docs — Core (Orientation, CLI Reference, Workflows)

> **Depends on:** Group 1
> **Unlocks:** Groups 4, 5, 6, 7

- [x] 3.1 Write `docs/agent/README.md` — what Lexibrary is from the agent's perspective, what `.lexibrary/` provides (design files as context, .aindex as routing, concepts as vocabulary, Stack as institutional memory), how using Lexibrary makes agents more effective
- [x] 3.2 Write `docs/agent/orientation.md` — session start protocol in detail: step 1 read `.lexibrary/START_HERE.md` (what it contains: topology, package map, navigation), step 2 check for `.iwh` signal files (what they look like, how to act on them), step 3 get library health overview. Include examples
- [x] 3.3 Write `docs/agent/lexi-reference.md` — complete `lexi` CLI reference: `lookup <file>` (output: design file + conventions + dependents + reverse refs), `index <dir> [-r]`, `describe <dir> <description>`, `concepts [topic]`, `concept new <name> [--tag]`, `concept link <concept> <file>`, `stack post --title --tag [--bead --file --concept]`, `stack search [query] [--tag --scope --status --concept]`, `stack answer <id> --body`, `stack vote <id> <up|down> [--answer --comment]`, `stack accept <id> --answer`, `stack view <id>`, `stack list [--status --tag]`, `search [query] [--tag --scope]`. Include usage examples for each command

## 4. User Docs — CLI and Setup

> **Depends on:** Group 2 (needs configuration doc as prerequisite context)
> **Unlocks:** Group 7

- [x] 4.1 Write `docs/user/lexictl-reference.md` — complete `lexictl` CLI reference: `init [--defaults]` (re-init guard, non-TTY detection), `update [path] [--changed-only <files>]` (single file, directory, full project modes), `validate [--severity --check --json]` (available checks list), `status [path] [--quiet]` (dashboard vs quiet mode), `setup [--update --env --hooks]`, `sweep [--watch]`, `daemon [start|stop|status]`. Include usage examples and exit codes
- [x] 4.2 Write `docs/user/project-setup.md` — init wizard deep dive: the 8 wizard steps (project name detection, scope root selection, agent environment detection, LLM provider detection, ignore patterns, token budgets, IWH toggle, summary confirmation), `--defaults` for CI/scripting, non-TTY handling, re-init guard, changing settings after init (edit config.yaml + `lexictl setup --update`), agent environment setup (`lexictl setup --update --env`)

## 5. User Docs — Feature Deep Dives

> **Depends on:** Group 2 (needs core docs as foundation)
> **Unlocks:** Group 7

- [x] 5.1 Write `docs/user/design-file-generation.md` — how `lexictl update` works end-to-end: file discovery (scope_root, ignore matching), change detection (SHA-256 hash comparison against frontmatter), ChangeLevel classification and what each level means, LLM generation pipeline (ArchivistService → BAML prompts → design file), `update_file` vs `update_project`, `--changed-only` mode for git hooks, START_HERE.md regeneration, progress reporting, update summary stats
- [x] 5.2 Write `docs/user/validation.md` — how `lexictl validate` works: the 13 checks with descriptions (error: wikilink_resolution, file_existence, concept_frontmatter; warning: hash_freshness, token_budgets, orphan_concepts, deprecated_concept_usage; info: forward_dependencies, stack_staleness, aindex_coverage, bidirectional_deps, dangling_links, orphan_artifacts), severity levels, `--check` for running a single check, `--severity` filter, `--json` output format, exit codes (0 = clean, 1 = errors)
- [x] 5.3 Write `docs/user/ci-integration.md` — CI/CD recipes: git post-commit hook setup (`lexictl setup --hooks`), how the hook runs `lexictl update --changed-only`, periodic sweep setup (`lexictl sweep --watch`), daemon mode (`lexictl daemon start` with `watchdog_enabled: true`), validation as CI gate (`lexictl validate` exit codes), quiet status for notifications (`lexictl status --quiet`), example CI pipeline snippets (GitHub Actions, GitLab CI)
- [x] 5.4 Write `docs/user/concepts-wiki.md` — concepts wiki for operators: what concepts are (project-specific vocabulary, architectural patterns, domain terms), creating concepts (`lexi concept new <name> --tag`), concept file anatomy (YAML frontmatter: title, aliases, tags, status + markdown body), concept lifecycle (draft → active → deprecated), wikilink syntax (`[[concept-name]]`), linking concepts to design files (`lexi concept link`), searching concepts, how agents use concepts
- [x] 5.5 Write `docs/user/stack-qa.md` — Stack Q&A for operators: what Stack posts are (structured problem/solution knowledge), creating posts (`lexi stack post --title --tag`), post anatomy (frontmatter + problem + evidence + answers), answer workflow (`lexi stack answer`), voting (`lexi stack vote up/down`), accepting answers (`lexi stack accept --answer`), status lifecycle (open → resolved / outdated / duplicate), searching and filtering (`lexi stack search`, `lexi stack list`), how agents use the Stack
- [x] 5.6 Write `docs/user/link-graph.md` — link graph for operators: what the SQLite index contains (8 tables + FTS5), what it indexes (ast_import dependencies, wikilinks, tag assignments, concept refs, file refs, conventions), how it's built (full build during `lexictl update`), what queries it accelerates (reverse deps in `lexi lookup`, tag search in `lexi search`, FTS), health metadata in `lexictl status`, rebuilding the index (delete index.db + `lexictl update`)
- [x] 5.7 Write `docs/user/ignore-patterns.md` — ignore system: `.lexignore` file (pathspec gitignore format), `.gitignore` integration (`ignore.use_gitignore` config), `ignore.additional_patterns` config list, built-in defaults, pattern precedence (built-in → .gitignore → config → .lexignore), how patterns affect file discovery during `lexictl update` and `lexi index`, examples for common exclusions

## 6. Agent Docs — Workflows and Knowledge Base

> **Depends on:** Group 3 (needs core agent docs as foundation)
> **Unlocks:** Group 7

- [x] 6.1 Write `docs/agent/lookup-workflow.md` — before-edit workflow in detail: run `lexi lookup <file>`, understanding the output (design file with frontmatter: source, source_hash, generated, updated_by, wikilinks; summary; interface skeleton; applicable conventions from .aindex hierarchy; dependents from link graph; reverse references). How to use this information before making changes
- [x] 6.2 Write `docs/agent/update-workflow.md` — after-edit workflow: when the agent should update design files (always after meaningful changes), how to update (edit the .md in `.lexibrary/` mirror tree), what to update (summary, key details), setting `updated_by: agent` in frontmatter, when to let `lexictl update` handle it instead (cosmetic changes, bulk updates), what NOT to touch (frontmatter hashes, generated timestamps)
- [x] 6.3 Write `docs/agent/concepts.md` — using concepts: `lexi concepts <topic>` to search before architectural decisions, `lexi concept new <name>` to create when a recurring pattern/term emerges, `lexi concept link <concept> <file>` to connect concepts to relevant files, when to create a concept (3+ files share a pattern, domain term needs definition, architectural decision needs recording)
- [x] 6.4 Write `docs/agent/stack.md` — using Stack Q&A: `lexi stack search <query>` before debugging (check if solved), `lexi stack post --title --tag` after solving non-trivial bugs, `lexi stack answer <id> --body` to contribute solutions, `lexi stack vote <id> up` to surface good answers, searching by tag/scope/concept/status for targeted results
- [x] 6.5 Write `docs/agent/search.md` — unified search: `lexi search <query>` for cross-artifact search, `--tag` filter, `--scope` filter, what results include (concepts, design files, Stack posts), when to use `search` vs `lookup` (search = discovery, lookup = specific file context), how search uses the link graph index when available
- [x] 6.6 Write `docs/agent/iwh.md` — I Was Here signals: purpose (preventing lost context when work is interrupted), when to create an IWH (leaving task incomplete, context another agent needs), what to include (description of incomplete work, next steps, affected files), IWH file format (YAML frontmatter + markdown), where to place IWH files (directory of incomplete work), consuming IWH (read → act on instructions → delete the file)
- [x] 6.7 Write `docs/agent/prohibited-commands.md` — what agents must NOT do: never run `lexictl` commands (init, update, validate, status, setup, sweep, daemon), never modify `.lexibrary/config.yaml`, never delete files from `.lexibrary/` directly, never modify `.aindex` files directly (use `lexi describe` instead). Explain why: `lexictl` commands are expensive (LLM calls), require operator oversight, and can disrupt other agents' work
- [x] 6.8 Write `docs/agent/quick-reference.md` — single-page cheat sheet: session start checklist (3 steps), before-edit checklist (2 steps), after-edit checklist (2 steps), key commands table (command → what it does → when to use), common scenarios with command sequences (debugging a bug, understanding a file, creating a concept, leaving work incomplete)

## 7. User Docs — Operational (Troubleshooting, Upgrading)

> **Depends on:** Groups 2, 4, 5 (needs all feature docs complete for cross-referencing)
> **Unlocks:** Group 8

- [x] 7.1 Write `docs/user/troubleshooting.md` — common issues organised by category: **Init issues** (re-init error, non-TTY error, no LLM provider detected), **Update issues** (LLM API errors/timeouts, "no files found" with wrong scope_root, design files not generated for new files, stale design files), **Validation issues** (hash_freshness warnings after manual edits, orphan concepts, broken wikilinks), **Daemon issues** (stale PID file, watchdog not starting, sweep not detecting changes), **Config issues** (YAML parse errors, unknown config keys ignored silently, API key not found). Each issue: symptoms, cause, fix
- [x] 7.2 Write `docs/user/upgrading.md` — version upgrade guide: general process (update package, check release notes, re-run `lexictl setup --update`), config schema evolution (new keys have defaults, `extra="ignore"` ensures forward compatibility), when to re-run `lexictl update` (new features that change design file format, new validation checks), link graph rebuilding (delete index.db if schema version changes)

## 8. Cross-referencing, Review, and Backlog Closure

> **Depends on:** All previous groups
> **Unlocks:** Nothing (final group)

- [x] 8.1 Review all docs for internal consistency — verify cross-references between docs are correct, command names match actual CLI, config keys match schema.py, check names match validator
- [x] 8.2 Add cross-reference links between User Docs and Agent Docs where relevant (e.g., user/concepts-wiki.md links to agent/concepts.md and vice versa)
- [x] 8.3 Verify all `lexi` and `lexictl` commands documented match the actual CLI implementations in `lexi_app.py` and `lexictl_app.py`
- [x] 8.4 Verify all config keys documented in `configuration.md` match `config/schema.py` and `config/defaults.py`
- [x] 8.5 Update `plans/BACKLOG.md` — change "Operator-facing documentation" item status from `planned` to `resolved` and move it to the Resolved table
