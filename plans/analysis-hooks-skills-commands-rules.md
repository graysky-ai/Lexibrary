# Lexibrary Deep Analysis: Hooks, Skills, Commands, Rules & End-to-End Workflows

> **Date:** 2026-02-24 (revised 2026-02-24 post agent-navigation, cli-command-rebalance & iwh-gap-fix)
> **Scope:** Full audit of automation infrastructure, agent integration surfaces, and workflow completeness

---

## Table of Contents

1. [What Lexibrary Does — Complete Capability Inventory](#1-capability-inventory)
2. [End-to-End Workflow Analysis](#2-end-to-end-workflow-analysis)
3. [Current State: Hooks, Skills, Commands, Rules](#3-current-state)
4. [Environment-Specific Analysis (Claude, Cursor, Neither)](#4-environment-specific-analysis)
5. [Agent vs lexictl Split](#5-agent-vs-lexictl-split)
6. [Archivist Needs](#6-archivist-needs)
7. [Gap Analysis & Recommendations](#7-gap-analysis--recommendations)

---

## 1. Capability Inventory

Everything Lexibrary is supposed to do, organized by actor:

### Operator Capabilities (via `lexictl`)

| # | Capability | Status | Command |
|---|-----------|--------|---------|
| O1 | Initialize project with wizard | Done | `lexictl init [--defaults]` |
| O2 | Generate/update design files (LLM) | Done | `lexictl update [path \| --changed-only]` |
| O3 | Regenerate START_HERE.md | Done (bundled with update) | `lexictl update` (full project only) |
| O4 | Validate library health | Done | `lexictl validate [--severity \| --check \| --json]` |
| O5 | Show status dashboard | Done | `lexictl status [-q]` |
| O6 | Generate/refresh agent rules | Done | `lexictl setup --update [--env]` |
| O7 | Install git post-commit hook | Done | `lexictl setup --hooks` |
| O8 | Run one-shot sweep | Done | `lexictl sweep` |
| O9 | Run periodic sweep (foreground) | Done | `lexictl sweep --watch` |
| O10 | Run watchdog daemon (deprecated) | Done | `lexictl daemon start/stop/status` |
| O11 | Build link graph (SQLite) | Done (bundled with update) | Automatic in `lexictl update` |
| O12 | Generate .aindex for directory | Done (moved from `lexi`) | `lexictl index [dir] [-r]` |
| O13 | Preview changes without LLM (dry-run) | **Missing** | Planned: `lexictl update --dry-run` |
| O14 | Regenerate START_HERE independently | **Missing** | Planned: `lexictl update --start-here` |
| O15 | Auto-fix validation issues | **Missing** | Proposed: `lexictl validate --fix` |
| O16 | CI validation gate | **Missing** | Proposed: `lexictl validate --ci` |

### Agent Capabilities (via `lexi`)

| # | Capability | Status | Command |
|---|-----------|--------|---------|
| A1 | Look up design file + context for a source file | Done | `lexi lookup <file>` |
| A2 | ~~Generate .aindex for directory~~ | Moved to `lexictl` | ~~`lexi index`~~ → `lexictl index [dir] [-r]` |
| A3 | Search concepts wiki | Done | `lexi concepts [topic] [--tag \| --status \| --all]` |
| A4 | Create new concept | Done | `lexi concept new <name> [--tag]` |
| A5 | Link concept to design file | Done | `lexi concept link <name> <file>` |
| A6 | Create Stack Q&A post | Done | `lexi stack post --title --tag [--bead \| --file \| --concept]` |
| A7 | Search Stack posts | Done | `lexi stack search [query] [--tag \| --scope \| --status \| --concept]` |
| A8 | Answer/vote/accept Stack posts | Done | `lexi stack answer/vote/accept` |
| A9 | View Stack post | Done | `lexi stack view <id>` |
| A10 | List Stack posts | Done | `lexi stack list [--status \| --tag]` |
| A11 | Update .aindex billboard description | Done | `lexi describe <dir> <desc>` |
| A12 | Cross-artifact search | Done | `lexi search [query] [--tag \| --scope]` |
| A13 | Agent help/guidance | Done | `lexi help` |
| A14 | Validate library health (agent-facing) | Done | `lexi validate [--severity \| --check \| --json]` |
| A15 | Show status dashboard (agent-facing) | Done | `lexi status [path] [-q]` |
| A16 | Mark Stack post outdated | **Missing** | Proposed: `lexi stack mark-outdated <id>` |
| A17 | Mark Stack post duplicate | **Missing** | Proposed: `lexi stack duplicate <id> --of <id>` |

### Automation Capabilities

| # | Capability | Status | Mechanism |
|---|-----------|--------|-----------|
| AU1 | Auto-update after commit | Done | Git post-commit hook → `lexictl update --changed-only` |
| AU2 | Periodic sweeps | Done | `lexictl sweep --watch` / daemon |
| AU3 | Agent session orientation | Done | Rules instruct: read START_HERE, check .iwh, run `lexi status` |
| AU4 | Agent handoff signals (IWH) | Done | `lexi iwh write/read/list`, `lexictl iwh clean`; archivist respects `blocked` signals; `find_all_iwh()` discovery; rules/docs aligned |
| AU5 | Auto-rebuild link graph | Done | Bundled with `lexictl update` |
| AU6 | Agent rules injection | Done | `lexictl init` + `lexictl setup --update` |
| AU7 | Auto-rebuild .aindex after updates | Done | `reindex_directories()` in archivist pipeline |

---

## 2. End-to-End Workflow Analysis

For each major workflow, traced start to finish with gap identification.

### W1: First-Time Project Setup

```
Operator runs: lexictl init
  ├── Banner display
  ├── 8-step wizard (project name, scope root, agent envs, LLM provider,
  │   API key storage, ignore patterns, token budgets, IWH toggle)
  ├── Create .lexibrary/ skeleton (config.yaml, START_HERE placeholder,
  │   concepts/, stack/, .lexignore, .gitignore updates)
  ├── Generate agent rules for selected environments
  │   ├── Claude: CLAUDE.md (markers), .claude/commands/lexi-orient.md, .claude/commands/lexi-search.md
  │   ├── Cursor: .cursor/rules/lexibrary.mdc, .cursor/skills/lexi.md
  │   └── Codex: AGENTS.md (markers)
  └── Print "run lexictl update to generate design files"

Operator runs: lexictl update
  ├── Discover all source files in scope_root
  ├── For each file: change detection → LLM generation → atomic write
  ├── Regenerate START_HERE.md
  └── Full link graph build

Operator runs: lexictl setup --hooks (optional)
  └── Install git post-commit hook
```

**Gaps:**
- No `lexictl setup --hooks` prompt during init wizard (operator must remember)
- No prompt to run `lexictl update` automatically after init
- No MCP server configs generated (Claude Desktop, Cursor MCP)
- No IDE settings generated (.vscode/settings.json, etc.)
- No `.claude/settings.json` generated (permissions for lexi/lexictl commands)
- No `.claude/hooks/` generated (e.g., pre-tool-use hooks for auto-lookup)

### W2: Agent Session Start (e.g. Claude Code)

```
Agent reads CLAUDE.md → finds Lexibrary rules section
Agent follows rules:
  1. Read .lexibrary/START_HERE.md
  2. Check for .iwh signal files
  3. Run lexi status

Or: Agent runs /lexi-orient command
  1. Read .lexibrary/START_HERE.md
  2. Check for .lexibrary/.iwh
  3. Run lexi status
```

**Gaps:**
- No Claude hook to automatically run `/lexi-orient` on session start
- No Claude hook to auto-run `lexi lookup` before file edits (pre-tool-use hook on Edit/Write)
- Agent must remember to follow rules manually; no enforcement
- ~~`.iwh` check in orient skill only checks `.lexibrary/.iwh`, but rules say "any directory"~~ → **RESOLVED** by iwh-gap-fix: orient now uses `lexi iwh list` which discovers all signals
- No MCP tool that wraps `lexi` commands (agent must use bash)

### W3: Agent Edits a File

```
Rules say:
  BEFORE: Run lexi lookup <file>
  EDIT: Make changes
  AFTER: Update design file, set updated_by: agent
  AFTER: Run lexi validate
```

**Gaps:**
- No Claude hook to auto-trigger `lexi lookup` before Edit tool (feasible with `.claude/hooks/`)
- No Claude hook to remind about design file update after Edit tool
- Agent must manually update design files — no tooling to help (no `lexi update-design <file>`)
- ~~**CRITICAL BUG**: `lexi validate` didn't exist~~ → **RESOLVED** by cli-command-rebalance: `lexi validate` now exists as a shared wrapper (both CLIs call `_run_validate()` in `_shared.py`)

### W4: Agent Makes Architectural Decision

```
Rules say:
  1. Run lexi concepts <topic>
  2. Review existing concepts
  3. Make informed decision
  4. Optionally: lexi concept new <name> to document new concept
```

**Gaps:**
- No integration with link graph for "what depends on this concept"
- No `lexi concept edit <name>` command (agent must manually edit files)
- Workflow is reasonable but relies on agent discipline

### W5: Agent Debugs a Problem

```
Rules say:
  1. Run lexi stack search <query> first
  2. Debug the issue
  3. Run lexi stack post to document solution
```

**Gaps:**
- `lexi stack post` requires manual filling of Problem/Evidence sections (agent gets template, must edit file)
- No `lexi stack post --body <text>` for inline content (all required via flags or file editing)
- No easy way to attach code snippets or diffs to a Stack post
- Workflow is reasonable but could be smoother

### W6: Operator Runs Update After Code Changes

```
lexictl update
  ├── Discover files in scope_root
  ├── For each file:
  │   ├── Compute source_hash, interface_hash
  │   ├── check_change() → ChangeLevel
  │   ├── UNCHANGED → skip
  │   ├── AGENT_UPDATED → refresh footer hashes only (preserve agent work)
  │   ├── NEW_FILE/CONTENT_CHANGED/INTERFACE_CHANGED → LLM generation
  │   │   ├── Extract interface skeleton (AST/tree-sitter)
  │   │   ├── Read existing design file
  │   │   ├── Call archivist.generate_design_file() via BAML
  │   │   ├── TOCTOU re-check (did agent edit during LLM call?)
  │   │   ├── Build DesignFile model
  │   │   ├── Serialize → atomic write
  │   │   └── Refresh parent .aindex
  │   └── CONTENT_ONLY → LLM generation (lighter change)
  ├── Regenerate START_HERE.md (full project only)
  ├── Full link graph rebuild
  └── Auto-rebuild .aindex for affected directories (reindex_directories)
```

**Gaps:**
- No `--dry-run` to preview what would change (backlog: planned, high priority)
- No `--start-here` flag to regenerate START_HERE independently
- Sequential processing only (no concurrency) — backlog item
- No progress indication for individual files during update
- Token budget violations are warnings only — could silently produce oversized artifacts

### W7: Git Post-Commit Hook Fires

```
git commit triggers .git/hooks/post-commit:
  ├── git diff-tree to get changed files
  └── lexictl update --changed-only <FILES> >> .lexibrary/daemon.log 2>&1 &
      ├── Filter: skip deleted, binary, ignored, .lexibrary/ files
      ├── For each valid file: update_file()
      ├── Incremental link graph update (changed paths only)
      └── Does NOT regenerate START_HERE.md
```

**Gaps:**
- Runs in background — operator gets no feedback on success/failure
- No notification mechanism when update completes or fails
- `--changed-only` skips START_HERE.md regeneration (may become stale)
- No coordination with daemon if both running (could cause concurrent LLM calls)
- Windows not supported (shell script only)
- No pre-commit hook option for validation gate

### W8: Agent Handoff via IWH

```
Agent A leaves work incomplete:
  Run: lexi iwh write --scope incomplete --body "description of state"

Agent B starts session:
  Run: lexi iwh list (or /lexi-orient which includes this)
  Run: lexi iwh read <directory> (consumes signal after reading)

Archivist (lexictl update):
  Checks IWH signals per-directory before generating design files
  blocked → skip file, incomplete → proceed with caution
```

**Gaps** (consolidated as **C3** in Section 7 — all **RESOLVED** by iwh-gap-fix)**:**
- ~~**IWH is fully built but completely unused in production**~~ → CLI commands delivered: `lexi iwh write/read/list`, `lexictl iwh clean`
- ~~No `lexi iwh write <message>` or `lexi iwh read` commands~~ → Done
- ~~Agent must create .iwh files manually~~ → `lexi iwh write` handles format and mirror paths
- ~~Orient skill only checks `.lexibrary/.iwh`, not per-directory signals~~ → Orient now uses `lexi iwh list` (discovers all signals via `find_all_iwh()`)
- ~~No `lexi iwh list` to find all .iwh files across project~~ → Done
- ~~Gitignore integration exists but no CLI surface~~ → CLI commands use existing gitignore infrastructure
- ~~Archivist doesn't check for .iwh "don't regenerate" signals~~ → `update_file()` checks IWH: `blocked` → skip, `incomplete` → proceed with warning

### W9: Library Validation

```
lexi validate / lexictl validate (shared implementation via _run_validate)
  ├── 13 checks across 3 severity levels:
  │   ├── ERROR: wikilink_resolution, file_existence, concept_frontmatter
  │   ├── WARNING: hash_freshness, token_budgets, orphan_concepts,
  │   │   deprecated_concept_usage
  │   └── INFO: forward_dependencies, stack_staleness, aindex_coverage,
  │       bidirectional_deps, dangling_links, orphan_artifacts
  ├── Returns ValidationReport with exit code
  └── Supports --json, --severity, --check filtering
```

**Gaps:**
- No `--fix` flag to auto-remediate (proposed in backlog)
- No `--ci` mode with clean exit codes (proposed in backlog)
- ~~No `lexi validate` for agents~~ → **RESOLVED** by cli-command-rebalance

---

## 3. Current State: Hooks, Skills, Commands, Rules

### Git Hooks (What Lexibrary Generates for Target Projects)

| Hook | Status | What It Does |
|------|--------|-------------|
| `post-commit` | Done | Runs `lexictl update --changed-only` on changed files (background) |
| `pre-commit` | **Missing** | Could run `lexictl validate` as a gate |
| `post-merge` | **Missing** | Could refresh design files after merge |
| `post-checkout` | **Missing** | Could rebuild link graph after branch switch |

### Agent Rules (Injected into Target Projects)

Generated by `lexictl init` + `lexictl setup --update`:

| Environment | Files | Format |
|-------------|-------|--------|
| Claude | `CLAUDE.md` (markers), `.claude/commands/lexi-orient.md`, `.claude/commands/lexi-search.md` | Markdown with HTML comment markers |
| Cursor | `.cursor/rules/lexibrary.mdc`, `.cursor/skills/lexi.md` | MDC (YAML frontmatter), Markdown |
| Codex | `AGENTS.md` (markers) | Markdown with HTML comment markers |

**Rule Content (shared across all envs via base.py):**
- 7 behavioral sections: Session Start, Before Editing, After Editing, Architectural Decisions, Debugging, Leaving Work Incomplete, Prohibited Commands
- 2 skills: `/lexi-orient` (session start), `/lexi-search` (cross-artifact)

### Skills/Commands (Generated for Target Projects)

| Skill | Environment | Files |
|-------|-------------|-------|
| `/lexi-orient` | Claude: `.claude/commands/lexi-orient.md` | Session start checklist |
| `/lexi-search` | Claude: `.claude/commands/lexi-search.md` | Cross-artifact search |
| Combined | Cursor: `.cursor/skills/lexi.md` | Both skills in one file |
| Combined | Codex: embedded in `AGENTS.md` | Both skills inline |

### What Is NOT Generated

| Item | Impact | Difficulty |
|------|--------|-----------|
| `.claude/settings.json` | Agent can't run lexi/lexictl without manual approval each time | Low |
| `.claude/hooks/` | No auto-trigger for lookup before edits | Medium |
| MCP server config | Agent must use bash for all lexi commands instead of native tools | High |
| `.cursor/settings.json` | No permission pre-configuration | Low |
| Pre-commit hook | No validation gate before commits | Low |
| IDE workspace settings | No editor integration | Low |

---

## 4. Environment-Specific Analysis

### Claude Code Environment

**What's Generated:**
- `CLAUDE.md` section with core rules (marker-delimited)
- `.claude/commands/lexi-orient.md`
- `.claude/commands/lexi-search.md`

**What's Missing:**

| Item | Description | Priority |
|------|-------------|----------|
| **`.claude/settings.json`** | Pre-approve `lexi` bash commands so agents don't need manual permission for every lookup/search | High |
| **`.claude/hooks/PreToolUse` (Edit)** | Auto-run `lexi lookup <file>` before any file edit, injecting design context into conversation | High |
| **`.claude/hooks/PostToolUse` (Edit)** | Remind agent to update design file after edits, or auto-check for design file staleness | Medium |
| **`.claude/hooks/SessionStart`** | Auto-run `/lexi-orient` on session start instead of relying on agent reading CLAUDE.md | Medium |
| **Additional commands** | `/lexi-lookup`, `/lexi-status`, `/lexi-concepts` as convenience wrappers | Low |
| **MCP server** | Expose `lexi` commands as native Claude tools instead of bash commands | Future |

### Cursor Environment

**What's Generated:**
- `.cursor/rules/lexibrary.mdc` (always-apply rule with core rules)
- `.cursor/skills/lexi.md` (combined orient + search)

**What's Missing:**

| Item | Description | Priority |
|------|-------------|----------|
| **Additional rules files** | Break rules into context-specific files (e.g., `editing.mdc` with glob triggers for source files) | Medium |
| **Glob-scoped rules** | Rule that auto-triggers on `src/**` edits to remind about design file updates | Medium |
| **`.cursor/settings.json`** | Pre-configured terminal commands or allowed tools | Low |
| **MCP server config** | Cursor supports MCP — could expose lexi as native tools | Future |

### Neither (Plain Git Project / Other IDE)

**What's Generated:**
- Nothing (unless Codex is selected → AGENTS.md)

**What's Missing:**

| Item | Description | Priority |
|------|-------------|----------|
| **Generic `.editorconfig`** | Basic editor configuration | Low |
| **VS Code workspace recommendations** | `.vscode/extensions.json` with recommended extensions | Low |
| **Generic agent rules** | A `LEXIBRARY_RULES.md` for environments without specific integration | Medium |
| **Makefile / justfile targets** | `make lexi-update`, `make lexi-validate` convenience targets | Low |

---

## 5. Agent vs lexictl Split

### What Agents Should Do (via `lexi` or manual actions)

| Action | Tool | Current Status |
|--------|------|---------------|
| Read design file before editing | `lexi lookup <file>` | Done |
| Search for existing knowledge | `lexi search`, `lexi concepts`, `lexi stack search` | Done |
| Create new concepts | `lexi concept new` | Done |
| Link concepts to code | `lexi concept link` | Done |
| Document solutions | `lexi stack post`, `lexi stack answer` | Done |
| Update .aindex descriptions | `lexi describe` | Done |
| Check library health | `lexi validate`, `lexi status` | Done |
| Get agent-oriented help | `lexi help` | Done |
| Leave handoff signals | `lexi iwh write` | Done |
| Update design files after edits | Manual file editing | **Needs tooling** |

### What lexictl Should Do (programmatic/operator)

| Action | Tool | Current Status |
|--------|------|---------------|
| Initialize project | `lexictl init` | Done |
| Generate design files (LLM) | `lexictl update` | Done |
| Generate .aindex for directory | `lexictl index [dir] [-r]` | Done (moved from `lexi`) |
| Validate library | `lexictl validate` | Done |
| Show health status | `lexictl status` | Done |
| Install/update agent rules | `lexictl setup --update` | Done |
| Install git hooks | `lexictl setup --hooks` | Done |
| Run sweeps | `lexictl sweep [--watch]` | Done |
| Build link graph | Automatic in `lexictl update` | Done |
| Preview changes (dry-run) | **Missing** | Planned |
| Auto-fix issues | **Missing** | Proposed |
| CI validation gate | **Missing** | Proposed |
| Generate agent hooks/settings | **Missing** | **Needed** |

### Blurred Lines — Commands That Exist in Both

| Capability | Agent Need | Operator Need | Status |
|-----------|-----------|---------------|--------|
| Validate | `lexi validate` (read-only, same flags) | `lexictl validate` (same; future: `--fix`) | **Done** — shared via `_run_validate()` in `_shared.py` |
| Status | `lexi status` (orient, health check) | `lexictl status` (dashboard) | **Done** — shared via `_run_status()` in `_shared.py` |
| IWH write | `lexi iwh write <msg>` (agent handoff) | Not needed | **Done** by iwh-gap-fix |
| IWH read/list | `lexi iwh read` / `lexi iwh list` | `lexictl iwh clean` (cleanup) | **Done** by iwh-gap-fix |

> **Previously noted bug (RESOLVED):** `lexi status` and `lexi validate` were referenced in rules/skills but didn't exist. Both were added by the cli-command-rebalance change, with shared implementations in `_shared.py`.

---

## 6. Archivist Needs

The archivist is the LLM pipeline that generates design files and START_HERE.md.

### What the Archivist Currently Has

- Full LLM pipeline via BAML (generate_design_file, generate_start_here)
- Change detection (6-level: UNCHANGED → NEW_FILE)
- TOCTOU protection (design hash re-check after LLM call)
- Rate limiting for API calls
- Atomic writes for design files
- Dependency extraction via tree-sitter
- Link graph building (full + incremental)
- **Automated .aindex rebuilds** via `reindex_directories()` — re-indexes affected directories + ancestors after updates

### What the Archivist Needs

| Need | Why | Priority |
|------|-----|----------|
| **Automatic triggers** | Currently only runs when operator explicitly calls `lexictl update` or post-commit hook fires. No event-driven updates. | High |
| **Agent edit awareness** | Archivist respects `AGENT_UPDATED` (refreshes hashes only) but has no way to know *what* the agent changed to validate it | Medium |
| **Concept index caching** | Loads full concept index for every file during `update_project()` — should cache in memory | Medium |
| **Incremental START_HERE** | Currently rebuilds from scratch every time; should only update when structure changes | Medium |
| **Design file template for agents** | Agents are told to "update design files" but have no template or tooling to help | High |
| ~~**Batch .aindex refresh**~~ | ~~Updates parent .aindex after each file~~ → **RESOLVED**: `reindex_directories()` batches per-directory after all file updates | ~~Low~~ Done |
| **Claude hooks integration** | A PreToolUse hook could call a lightweight archivist check before edits | Medium |
| ~~**IWH integration**~~ | ~~Archivist should check for .iwh signals~~ → **RESOLVED** by iwh-gap-fix: `update_file()` checks IWH signals (`blocked` → skip, `incomplete` → proceed with warning) | ~~Low~~ Done |

### Does the Archivist Need Hooks/Skills/Rules?

**No, the archivist itself doesn't need agent-environment artifacts.** The archivist is a backend service called by `lexictl`. However:

1. **The archivist's output quality depends on agents following rules** — if agents don't update design files with `updated_by: agent`, the archivist will overwrite their work.
2. **Claude hooks would protect agent work** — a PostToolUse hook after Edit could automatically set `updated_by: agent` in the design file frontmatter, ensuring the archivist respects it.
3. ~~**The archivist should be aware of IWH signals**~~ → **RESOLVED**: `update_file()` now checks IWH signals; `blocked` scope skips the file, `incomplete` logs a warning and proceeds.

---

## 7. Gap Analysis & Recommendations

### Critical Issues (Fix Immediately)

| # | Issue | Impact | Fix | Status |
|---|-------|--------|-----|--------|
| C1 | ~~`lexi validate` doesn't exist~~ | ~~Agents get errors~~ | Added `lexi validate` (shared `_run_validate()`) | **RESOLVED** by cli-command-rebalance |
| C2 | ~~`lexi status` doesn't exist~~ | ~~Orient skill fails~~ | Added `lexi status` (shared `_run_status()`) | **RESOLVED** by cli-command-rebalance |
| C3 | **IWH has no CLI surface** but rules tell agents to create .iwh files (see also W8 gaps, M4, Appendix C) | Agents must manually create YAML files; orient skill only checks `.lexibrary/.iwh` not per-directory; no list/clean commands; archivist doesn't respect .iwh "don't regenerate" signals | Add `lexi iwh write/read/list`, `lexictl iwh clean`; fix orient skill to check per-directory; add archivist .iwh awareness | **RESOLVED** by iwh-gap-fix |
| C4 | ~~Rules reference non-existent commands~~ | ~~Agent trust undermined~~ | `base.py` updated: `lexi validate` in After Editing, `lexi status` in orient skill, IWH CLI commands now valid | **RESOLVED** |

### High Priority (Next Sprint)

| # | Item | Type | Description | Status |
|---|------|------|-------------|--------|
| H1 | Generate `.claude/settings.json` | Rules gen | Pre-approve `lexi` and `lexictl` bash commands for Claude Code | Open |
| H2 | Generate `.claude/hooks/` | Rules gen | PreToolUse(Edit): auto-lookup; PostToolUse(Edit): remind design update | Open |
| H3 | `lexictl update --dry-run` | CLI | Preview what would change without LLM calls | Open |
| H4 | Agent design file update helper | CLI | `lexi design update <file>` — opens/scaffolds design file for agent editing | Open |
| H5 | Pre-commit hook option | Hooks | `lexictl setup --hooks` should offer pre-commit validation gate | Open |
| H6 | ~~Fix rule content bugs~~ | Rules | ~~Update `base.py`~~ → commands now exist, rules are accurate | **RESOLVED** |

### Medium Priority

| # | Item | Type | Description |
|---|------|------|-------------|
| M1 | Cursor glob-scoped rules | Rules gen | Auto-trigger rules when editing files in scope_root |
| M2 | More Claude commands | Rules gen | `/lexi-lookup`, `/lexi-concepts`, `/lexi-stack` convenience wrappers |
| M3 | `lexictl update --start-here` | CLI | Independent START_HERE regeneration |
| ~~M4~~ | ~~IWH CLI commands~~ | — | Consolidated into **C3** (critical: rules reference IWH with no tooling) |
| M5 | Hook/sweep coordination | Daemon | Prevent concurrent updates from post-commit hook + daemon |
| M6 | `lexictl validate --ci` | CLI | Clean exit codes for CI pipelines |
| M7 | Additional Claude commands | Rules gen | `/lexi-concept-new`, `/lexi-stack-post` with guided prompts |
| M8 | Windows hook support | Hooks | PowerShell alternative for post-commit hook |

### Low Priority / Future

| # | Item | Type | Description |
|---|------|------|-------------|
| L1 | MCP server for lexi commands | Integration | Native tool integration for Claude/Cursor |
| L2 | Additional environments (Windsurf, Copilot, Aider) | Rules gen | As ecosystem evolves |
| L3 | IDE workspace settings | Rules gen | .vscode/settings.json, etc. |
| L4 | `lexictl validate --fix` | CLI | Auto-remediate fixable issues |
| L5 | `lexi stack mark-outdated/duplicate` | CLI | Surface existing mutations |
| L6 | `lexictl metrics` | CLI | Coverage stats dashboard |

---

## Appendix A: Complete Command Inventory

### lexi (Agent-Facing) — 19 commands

| Command | Flags | Status |
|---------|-------|--------|
| `lexi lookup <file>` | — | Done |
| `lexi concepts [topic]` | `--tag`, `--status`, `--all` | Done |
| `lexi concept new <name>` | `--tag` | Done |
| `lexi concept link <name> <file>` | — | Done |
| `lexi stack post` | `--title`, `--tag`, `--bead`, `--file`, `--concept` | Done |
| `lexi stack search [query]` | `--tag`, `--scope`, `--status`, `--concept` | Done |
| `lexi stack answer <id>` | `--body`, `--author` | Done |
| `lexi stack vote <id> <dir>` | `--answer`, `--comment`, `--author` | Done |
| `lexi stack accept <id>` | `--answer` | Done |
| `lexi stack view <id>` | — | Done |
| `lexi stack list` | `--status`, `--tag` | Done |
| `lexi describe <dir> <desc>` | — | Done |
| `lexi validate` | `--severity`, `--check`, `--json` | Done (added by cli-command-rebalance) |
| `lexi status [path]` | `-q/--quiet` | Done (added by cli-command-rebalance) |
| `lexi help` | — | Done (added by agent-navigation) |
| `lexi search [query]` | `--tag`, `--scope` | Done |
| `lexi iwh write` | `--scope/-s`, `--body/-b`, `--author` | Done (delivered by iwh-gap-fix) |
| `lexi iwh read` | `--peek` | Done (delivered by iwh-gap-fix) |
| `lexi iwh list` | — | Done (delivered by iwh-gap-fix) |

### lexictl (Operator-Facing) — 9 commands

| Command | Flags | Status |
|---------|-------|--------|
| `lexictl init` | `--defaults` | Done |
| `lexictl update [path]` | `--changed-only` | Done |
| `lexictl index [dir]` | `-r/--recursive` | Done (moved from `lexi` by cli-command-rebalance) |
| `lexictl validate` | `--severity`, `--check`, `--json` | Done |
| `lexictl status [path]` | `-q/--quiet` | Done |
| `lexictl setup` | `--update`, `--env`, `--hooks` | Done |
| `lexictl sweep` | `--watch` | Done |
| `lexictl daemon [action]` | — | Done (deprecated) |
| `lexictl iwh clean` | `--older-than` | Done (delivered by iwh-gap-fix) |

---

## Appendix B: Generated Files Per Environment

### Claude Code

| File | Content | Generated By |
|------|---------|-------------|
| `CLAUDE.md` (section) | Core rules | `lexictl init` / `setup --update` |
| `.claude/commands/lexi-orient.md` | Orient skill | `lexictl init` / `setup --update` |
| `.claude/commands/lexi-search.md` | Search skill | `lexictl init` / `setup --update` |
| `.claude/settings.json` | Permission config | **NOT GENERATED** |
| `.claude/hooks/*.md` | Auto-trigger hooks | **NOT GENERATED** |

### Cursor

| File | Content | Generated By |
|------|---------|-------------|
| `.cursor/rules/lexibrary.mdc` | Core rules (MDC format) | `lexictl init` / `setup --update` |
| `.cursor/skills/lexi.md` | Combined skills | `lexictl init` / `setup --update` |
| `.cursor/settings.json` | IDE settings | **NOT GENERATED** |

### Codex

| File | Content | Generated By |
|------|---------|-------------|
| `AGENTS.md` (section) | Core rules + skills | `lexictl init` / `setup --update` |

---

## Appendix C: Rule Content Bugs

| Location | Bug | Fix | Status |
|----------|-----|-----|--------|
| `base.py` | ~~`Run lexi validate` — command doesn't exist~~ | `lexi validate` created (shared `_run_validate()`) | **RESOLVED** |
| `base.py` | ~~Orient skill: `Run lexi status` — command doesn't exist~~ | `lexi status` created (shared `_run_status()`) | **RESOLVED** |
| `base.py` | "Check for `.iwh` signal files" — no tooling to create/read them | See **C3** — consolidated IWH gap | **RESOLVED** by iwh-gap-fix |

---

## Appendix D: Archivist-Specific Needs Summary

The archivist (LLM pipeline) **does not need its own hooks/skills/rules**. It is a backend service. However, it depends on the following being in place:

1. **Agent rules must be accurate** — agents updating `updated_by: agent` correctly protects their work from archivist overwrite
2. **Triggers must exist** — post-commit hook and/or daemon ensure archivist runs
3. **IWH awareness** — archivist checks for .iwh signals (`blocked` → skip, `incomplete` → proceed with warning)
4. **Concept index** — archivist uses available concepts for LLM context; must be populated
5. **Link graph** — built by archivist after design file generation; self-contained

The archivist's main need is **reliable triggering** (post-commit hook, daemon, or CI) and **accurate agent behavior** (enforced via rules/hooks).
