# Backlog

Living backlog for Lexibrary. Extracted from the master plan's "Implementation Backlog"
section, inline TODOs, open questions, and deferred plans.

**Workflow:** Items start here as quick captures. When ready to implement, promote to an
OpenSpec change (`opsx:new`) or GitHub Issue.

## Statuses

| Status | Meaning |
|--------|---------|
| `planned` | Confirmed — we intend to build this |
| `proposed` | Likely useful but needs design/scoping before committing |
| `suggestion` | Nice-to-have idea — not committed, may never happen |
| `blocked` | Waiting on a prerequisite or decision |
| `resolved` | Done or no longer relevant (keep briefly for audit trail, then delete) |

## Importance

| Level | Meaning |
|-------|---------|
| `critical` | Blocks launch or core workflows |
| `high` | Significant usability or correctness gap |
| `medium` | Meaningful improvement, not blocking |
| `low` | Polish, convenience, or edge-case coverage |

---

## CLI Gaps

Items where the overview or design describes a CLI command/flag that doesn't exist yet.

| Importance | Status | Item | Context |
|------------|--------|------|---------|
| medium | resolved | `lexi concepts --tag <t>` | Delivered via OpenSpec change `agent-navigation`. |
| low | resolved | `lexi concepts --status <s>` | Delivered via OpenSpec change `agent-navigation`. |
| low | resolved | `lexi concepts --all` | Delivered via OpenSpec change `agent-navigation`. |
| critical | resolved | `lexi iwh write/read/list`, `lexictl iwh clean` | Delivered via IWH gap fix. `find_all_iwh()` discovery, archivist IWH awareness, docs/rules aligned. |
| medium | planned | `lexi stack mark-outdated <post-id>` | Mutation `mark_outdated()` exists in code but has no CLI surface. Scoped in agent-harnessing plan Phase 3.2. |
| low | planned | `lexi stack duplicate <post-id> --of <id>` | Mutation `mark_duplicate()` exists in code but has no CLI surface. Scoped in agent-harnessing plan Phase 3.2. |
| high | planned | `lexictl update --dry-run` | Preview what would change without LLM calls. Scoped in agent-harnessing plan Phase 2.1. |
| medium | planned | `lexictl update --start-here` | Regenerate START_HERE.md independently without a full project update. Scoped in agent-harnessing plan Phase 2.2. |
| medium | planned | `lexictl validate --fix` | Auto-remediate fixable issues (refresh stale hashes, remove orphans, rebuild .aindex). Scoped in agent-harnessing plan Phase 2.4. |
| high | resolved | `lexi help` | Delivered via OpenSpec change `agent-navigation`. |
| high | proposed | `lexictl help` | Operator-facing help command with workflow guidance beyond `--help` flag descriptions — e.g., "how do I set up CI?", "how do I add a new language?" |
| high | planned | `lexi design update <file>` | Agent design file update helper — scaffold or display design file for a source file, set `updated_by: agent`. Scoped in agent-harnessing plan Phase 3.1. |
| medium | planned | `lexictl validate --ci` | CI validation gate — exits non-zero when the library is stale or unhealthy. Scoped in agent-harnessing plan Phase 2.3. |
| medium | proposed | `lexictl diff` / `lexictl changelog` | Show what changed in the library since a given commit or date. Staleness report across artifacts. |
| medium | proposed | `lexi browse` | Interactive TUI (Rich/Textual) for navigating design files, concepts, link graph, and stack posts visually. |
| medium | proposed | `lexictl export` | Export the lexibrary as JSON or other structured formats for consumption by external tools and integrations. |
| low | proposed | `lexictl metrics` | Coverage stats dashboard — % of source files with design files, concept density, staleness distribution, link graph health. Deferred from agent-harnessing plan (analysis item L6). |
| medium | planned | `lexi search --format plain` | Plain markdown output suitable for hook injection and MCP responses. Part of search upgrade plan (`plans/search-upgrade.md` Phase 1.2). |
| medium | planned | `lexi search --limit N` | Cap results per category (default 5) to prevent token-heavy output. Part of search upgrade plan Phase 1.3. |
| high | planned | `lexi lookup --format json` | Structured JSON output for MCP tool responses and programmatic consumption. Prerequisite for MCP server. Part of lookup upgrade plan (`plans/lookup-upgrade.md` item 4). |
| medium | planned | `lexi lookup --brief` | Concise output (role + conventions + concept names only) for pre-edit hook injection. Part of lookup upgrade plan item 5. |
| high | planned | `lexi conventions [path]` | List conventions applicable to a file/directory, with `--scope`, `--tag`, `--status` filters. Part of conventions-artifact plan. |
| high | planned | `lexi convention new --scope <s> --body <b>` | Create a new convention file. **Primary population mechanism** — coding agents create conventions via this command. Agent-created start as `status: draft`, `source: agent`. Part of conventions-artifact plan. |
| medium | planned | `lexi convention approve <name>` | Promote a convention from `draft` to `active`. Human-only action (agents do not approve). Part of conventions-artifact plan sign-off workflow. |

## Feature Gaps

Design-described capabilities that aren't delivered yet.

| Importance | Status | Item | Context |
|------------|--------|------|---------|
| high | blocked | Mapping strategy evaluation | `mapping.strategies` config field is an empty stub. The 1:1/grouped/abridged/skipped strategies from overview §2 are never evaluated. Needs: pattern matching engine, strategy-specific templates, grouped file aggregation. Blocked on design decisions (overview Q-010). Post-Phase 4. |
| high | resolved | Operator-facing documentation (`docs/`) | Delivered via OpenSpec change `operator-docs`. See `docs/user/` (14 guides) and `docs/agent/` (12 guides). |
| medium | planned | Concurrency for `lexictl update` | D-025 establishes sequential MVP with async architecture ready. Needs config key (`update.max_concurrent`). Not urgent — locks in `utils/locks.py` are pre-wired as no-ops. Post-Phase 4. |
| high | proposed | Multi-repo support | Index and navigate across multiple related repositories. Needs design for cross-repo linking, shared concepts, and config inheritance. |
| high | proposed | Additional language parsers | Expand `ast_parser/` beyond Python/TypeScript/JavaScript. Priority languages: Go, Rust, Java, C/C++, Ruby, C#. Each needs a tree-sitter parser + `extract_interface()` impl. |
| high | planned | Conventions v1 — first-class artifact | File-based conventions in `.lexibrary/conventions/` mirroring concepts. Decisions settled in `conventions-artifact.md` (D1-D12). Includes: `ConventionFile` model, parser, serializer, `ConventionIndex` with scope resolution algorithm, link graph builder integration, CLI commands (`convention new`, `convention approve`, `conventions`), config (display limit, token budget), `.aindex` `local_conventions` removal (D9), slug-based naming (D11), structured body format (D12), priority-based display ordering. Primary population: coding agents via `lexi convention new`. |
| medium | planned | Conventions v2 — pattern scopes + archivist extraction | Pattern-based scopes (glob/fnmatch), LLM extraction via archivist pipeline (backup for agent-created), `artifact_review` config with auto/manual sign-off, staleness detection, enhanced conflict detection. Full plan in `plans/convention-v2-plan.md`. Blocked on v1 being proven in use. |
| medium | planned | Artifact review sign-off config (full) | `artifact_review` config with auto/manual sign-off per artifact type (conventions, concepts, etc.). LLM-as-judge for auto, draft→active workflow for manual. v1 has basic draft/approve workflow for conventions only. Full extensibility deferred to v2. See `conventions-artifact.md` D4, `convention-v2-plan.md` §2. |
| medium | planned | Additional agent environments | Expand `init/rules/` beyond Claude/Cursor/Codex. Generic fallback (`LEXIBRARY_RULES.md`) scoped in agent-harnessing plan Phase 5.2. Specific env integrations (Windsurf, Copilot, Aider) deferred to demand. |
| medium | resolved | Expanded agent environment setup (hooks, settings, MCP) | Covered by agent-harnessing-plan.md Phases 1.1 (settings.json), 1.2 (hooks), 5.1 (Cursor). MCP server deferred — see below. |
| high | planned | MCP server for `lexi` commands | Expose `lexi_lookup`, `lexi_search`, `lexi_concepts`, `lexi_status` as native MCP tools via stdio server. Calls library functions directly (no subprocess). Optional dep `lexibrary[mcp]`. Full plan in `plans/mcp-server.md`, analysis in `plans/mcp-vs-plans.md`. |
| low | proposed | IDE workspace settings generation | Generate `.vscode/settings.json`, `.vscode/extensions.json` etc. during `lexictl init`. Low impact — editors work fine without them. Deferred from agent-harnessing plan (analysis item L3). |
| low | proposed | Post-merge / post-checkout git hooks | Auto-refresh design files after `git merge` and rebuild link graph after `git checkout`. Same pattern as existing post-commit hook. Deferred from agent-harnessing plan (Phase 4.2). |
| low | proposed | Windows git hook support | Generate PowerShell `.ps1` equivalents of shell hook scripts. Detect platform in installer. Deferred from agent-harnessing plan — no active Windows users (analysis item M8). |
| low | proposed | Hook/sweep coordination | Prevent concurrent `lexictl update` from post-commit hook and daemon/sweep. Edge case — sweeps are periodic (full) and hooks are post-commit (quick, scoped), so conflicts are rare. Deferred from agent-harnessing plan (analysis item M5). |
| medium | proposed | Custom/pluggable parsers | Let users register their own language parsers via config or plugin directory, for languages not built-in. |
| low | proposed | Template customization | Let users override design file, concept, and stack post templates in `.lexibrary/templates/` or config. |
| low | suggestion | `start_here.topology_format` config | Overview §1 says topology format is "configurable" (Mermaid vs ASCII). No config key exists. See overview Q-009. Phase 8b. |
| high | planned | Grep search augment hook | PostToolUse hook on Grep that runs `lexi search` with the sanitized pattern and injects matching concepts/conventions as `additionalContext`. Grep only (not Glob — glob patterns aren't semantic queries). 3-second timeout, silent on empty results. Part of search upgrade plan (`plans/search-upgrade.md` Phase 2). |
| medium | planned | Search quality: fuzzy matching & ranking | Fuzzy concept name matching (trigram/Levenshtein), scope-aware result ranking (boost results in same directory tree), and "did you mean" suggestions on zero results. Part of search upgrade plan Phase 3. |
| medium | planned | Lookup enrichment: role summary, concepts, Stack posts | Restructure `lexi lookup` output with prominent role header, inline related concept summaries, recent Stack posts with status, and sibling file awareness. Full plan in `plans/lookup-upgrade.md`. |
| medium | planned | Update all agent environment skill templates for new flags | When search/lookup upgrades ship, update skill templates in `base.py` (`_SEARCH_SKILL`, `_LOOKUP_SKILL`) and environment-specific generators (Cursor, Codex, generic) to mention `--format plain`, `--limit N`, `--brief`, `--format json`. Currently only Claude rules are updated by the plans. |
| medium | proposed | Intentional `.gitignore` management for `.lexibrary/` artifacts | D3 (`conventions-artifact.md`) decides all artifacts should be committed to git. Currently `lexictl init` only gitignores `.lexibrary/index.db` and `**/.iwh` (scaffolder.py + iwh/gitignore.py), so artifacts happen to be committable — but by accident, not design. Needs: (1) explicit `lexictl init` step that adds a curated `.gitignore` block for `.lexibrary/` (ignore `index.db`, daemon files; commit everything else), (2) `lexictl validate` check that warns if `.lexibrary/` or broad `*.md` patterns in `.gitignore` would prevent artifact tracking, (3) docs/guidance on what to commit. Affects `.aindex` files, design files, concepts, Stack posts, START_HERE.md, and future conventions. Cross-ref: `conventions-artifact.md` D3 implication. |

## Hook Infrastructure

Items related to the growing hook system (search augment, pre-edit, post-edit). These are cross-cutting concerns that span both `plans/search-upgrade.md` and `plans/lookup-upgrade.md`.

| Importance | Status | Item | Context |
|------------|--------|------|---------|
| medium | proposed | Hook script integration testing strategy | Hook scripts are bash with inline Python that parse JSON, invoke `lexi` CLI, and emit JSON. This is the most fragile part of the hook system. Need a testing approach — either: (a) shell-level integration tests using `bats` or similar, (b) Python subprocess tests that feed stdin JSON and assert stdout, or (c) extract the core logic into a Python helper called from a minimal bash wrapper. Currently no test coverage for hook script *behavior* (only generation). |
| low | proposed | Hook dispatcher consolidation | After search-upgrade + lookup-upgrade, there are 3 hook scripts (`lexi-pre-edit.sh`, `lexi-post-edit.sh`, `lexi-search-augment.sh`). Each is a standalone bash script with similar boilerplate (read stdin JSON, extract fields, invoke lexi, emit JSON). Consider whether a single dispatcher script (or a Python entry point like `lexi hook <event-type>`) would be more maintainable than N separate scripts. Not urgent at 3 scripts, but worth considering before adding more. |
| low | proposed | Search augment caching for rapid queries | When an agent does 5+ Grep calls in quick succession (common during exploration), each fires the search augment hook independently — 5 CLI invocations, 5 SQLite opens. Consider a short-lived filesystem cache (e.g., `/tmp/.lexi-search-cache/<hash>` with 10s TTL) to avoid redundant work. Monitor real-world hook latency before implementing. |
| low | proposed | Glob augment via heuristic term extraction | The search augment hook fires on Grep only (Glob patterns aren't semantic queries). A future iteration could extract meaningful terms from Glob patterns — e.g., directory names from `src/auth/**` → `auth`, or file stems from `**/error_handler.*` → `error handler`. Deferred: unreliable heuristic, low value vs. Grep augment. |
| medium | planned | Linkgraph `snippet` column for search/lookup | Add `snippet TEXT` column to the `artifacts` table in the linkgraph. Populated during `lexictl update` with concept summaries, design file descriptions, and stack post answer excerpts (120 char cap). Enables snippets in FTS/tag index search paths without file I/O, and can be reused by lookup's Related Concepts/Stack Posts sections. Part of search upgrade plan Phase 1.5. |
| medium | planned | Verify `hookSpecificOutput` format against Claude Code spec | The existing `lexi-pre-edit.sh` emits bare `{"additionalContext": "..."}`. The search-upgrade and lookup-upgrade plans specify `{"hookSpecificOutput": {"hookEventName": "...", "additionalContext": "..."}}`. Need to verify which format is correct per the current Claude Code hook spec before implementing either plan. If `hookSpecificOutput` is correct, the existing pre-edit hook has a bug (noted in lookup-upgrade plan). |

## Configuration Suggestions

Potential config improvements — none committed.

| Importance | Status | Item | Rationale |
|------------|--------|------|-----------|
| medium | proposed | System keychain API key storage | Allow users to store API keys in macOS Keychain / Linux Secret Service / Windows Credential Store via the `keyring` library. Add `api_key_source: "env" \| "dotenv" \| "keychain"` config field and a `lexictl setup --store-key` command to prompt-and-persist the key securely. Builds on the `.env` wizard multi-choice (see operator-docs on API key management). Requires `keyring` as an optional dep and cross-platform testing. |
| medium | planned | `conventions.lookup_display_limit` | Default 5 conventions displayed per `lexi lookup`. Truncation favors specificity — most specific (leaf-ward) conventions survive, most general (root-ward) are dropped. Priority field controls ordering within same scope. See `conventions-artifact.md` D5, Scope Resolution Algorithm. |
| medium | suggestion | `llm.archivist_model` | Use a cheaper/faster model for design file generation vs START_HERE. Archivist does repetitive work on many files; a cheaper model may suffice. |
| medium | suggestion | `crawl.max_files` | Hard limit on files per `lexictl update` run. Safety valve for enormous projects where accidental full updates are expensive. |
| low | suggestion | `validate.disabled_checks` | Persist disabled checks in project config (suppress `orphan_concepts` during early setup). Currently CLI-only via `--check` / `--severity`. |
| low | suggestion | `scope_root` as list | Multiple source roots for monorepos (e.g., `["src/", "lib/"]`). See overview Q-007. |
| low | suggestion | Stack post token warning | Optional warning threshold for large Stack posts. See overview Q-006. |

## Bugs

| Importance | Status | Item | Context |
|------------|--------|------|---------|
| high | resolved | `lexictl init` — selecting an agent env in an uninitialised project silently does nothing | Fixed: wizard now detects missing directories, prompts to create them, and `init` calls `generate_rules()` to create agent rule files. |
| medium | planned | Remove legacy `conventions` section from `.aindex` files | Clean cut per `conventions-artifact.md` D9. Remove `local_conventions` field from `AIndexFile`, remove `## Local Conventions` from serializer/parser, remove `local_conventions=[]` from generator. Pre-launch, no migration needed (D8). |

## Tech Debt

Inline TODOs and code-level improvements.

| Importance | Status | Item | Location |
|------------|--------|------|----------|
| medium | planned | Track stale LLM fallback summaries | `src/lexibrary/crawler/engine.py:220` — Add a flag to detect files where we fell back to a cached summary so persistent LLM failures can be re-queued. |
| low | proposed | Log or surface validator check failures | `src/lexibrary/validator/__init__.py:134` — Individual check exceptions are silently swallowed. Could log them or surface as issues. |
| low | proposed | v1 crawler rework | `src/lexibrary/crawler/engine.py:19` — v1 indexer retired in Phase 1, crawler tagged for rework in a later phase. Decide if this is still relevant or should be removed entirely. |

## Refactors

Larger structural changes.

| Importance | Status | Item | Context |
|------------|--------|------|---------|
| high | planned | Rename `lexibrarian` → `lexibrary` | ~470 files across src/, tests/, blueprints/, openspec/, plans/, config. Full plan in `plans/rename-lexibrarian-to-lexibrary.md`. Daemon dotfiles: Option A chosen — move `.lexibrary.log`/`.pid` into `.lexibrary/`. |

## Open Questions

Unresolved design decisions from the master plan (some block backlog items above).

| Status | Question | Context |
|--------|----------|---------|
| proposed | Mapping strategy config — confirm glob-pattern approach for 1:1/grouped/abridged/skipped | Blocks "Mapping strategy evaluation" above. |
| proposed | Tree-sitter grammar installation — bundled or on-demand? | Leaning on-demand with clear error message. |
| proposed | `baml-py` version pin — bump from `0.218.0`? | Check if newer version needed for current prompt patterns. |

## Resolved

Items kept briefly for audit trail. Periodically delete these.

| Item | Resolution |
|------|------------|
| `lexi init` vs `lexi setup` | D-054 — Combined into `lexictl init` wizard. `lexictl setup --update` refreshes rules only. |
| Skills/commands generation | Scoped and delivered in Phase 8c. |
| Persist agent environment in config | D-058 — `lexictl init` wizard persists `agent_environment`. |
| `lexi stack list` | Implemented (was missing from spec, now added to overview §9). |
| Operator-facing documentation (`docs/`) | Delivered via OpenSpec change `operator-docs`. 26 docs in `docs/user/` and `docs/agent/` covering getting started, configuration, CLI reference, workflows, deep dives, troubleshooting, and agent orientation. |
| `lexi help` | Delivered via OpenSpec change `agent-navigation`. Agent-facing help command with Rich panels covering command groups, common workflows, and navigation tips. |
| `lexi concepts --tag <t>` | Delivered via OpenSpec change `agent-navigation`. Repeatable tag filter with AND logic. |
| `lexi concepts --status <s>` | Delivered via OpenSpec change `agent-navigation`. Filter by active/draft/deprecated status. |
| `lexi concepts --all` | Delivered via OpenSpec change `agent-navigation`. Include deprecated concepts in output. |
