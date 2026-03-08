# Lexibrary CLI Commands: Comprehensive Analysis

**Project:** Lexibrary (AI-friendly codebase indexer)  
**CLI File:** `/Users/shanngray/AI_Projects/Lexibrarian/src/lexibrary/cli/lexi_app.py`  
**Date:** 2026-03-09

---

## Executive Summary

The Lexibrary CLI (`lexi`) is an agent-facing command suite with **31 distinct commands** organized into **6 command groups** (stack, concept, convention, iwh, design, plus 11 top-level commands). The CLI demonstrates thoughtful agent usability principles:

- Commands are primarily **stateless**, requiring explicit arguments and options
- Output uses structured **Rich tables** for consistency
- Multi-step workflows have **one-shot alternatives** (e.g., `lexi stack post --finding ... --resolve`)
- Token budgets and truncation prevent overwhelming agents with excessive context
- Commands follow **Unix design principles** (one job per command, composable)

**Overall Assessment:** CLI is **well-designed for agent usability** with moderate-to-complex nesting. Token budget awareness and structured output are strengths. Main usability gap: documentation of command interactions and workflow ordering.

---

## Commands by Group

### 1. TOP-LEVEL COMMANDS (11 commands)

#### **`lookup <file>`** — COMPLEX, Stateless
- **Arguments:** 1 required (source file or directory)
- **Options:** None
- **Output:** Structured markdown + tables
- **Complexity Drivers:**
  - Performs 6+ distinct lookups internally (design file, conventions, issues, IWH, dependents, refs)
  - Implements token budget truncation with priority-based section ordering
  - Handles scope validation, staleness checking, design file scaffolding
- **Features:**
  - Design file rendering with frontmatter extraction
  - Applicable conventions grouped by scope
  - Known issues from Stack posts (limited to `config.stack.lookup_display_limit`)
  - Dependents showing inbound `ast_import` links
  - "Also Referenced By" showing other link types with labels
  - IWH signal peeking without consumption
- **Agent-Usability Notes:**
  - Agents call this before editing any file (per CLAUDE.md rules)
  - Automatically discovers stale design files and warns
  - Excellent one-stop context source — no chaining needed
  - Token budget aware (design > conventions > issues > iwh > links priority)

---

#### **`concepts [topic]`** — MODERATE, Stateless
- **Arguments:** 1 optional (search topic)
- **Options:** 5 optional
  - `--tag` (repeatable, AND logic)
  - `--status` (active/draft/deprecated)
  - `--all` (include deprecated)
- **Output:** Rich table (name, status, tags, summary)
- **Complexity Drivers:**
  - Tag filtering uses AND logic (multiple tags narrow results)
  - Status validation with 3 values
  - Excludes deprecated by default unless `--all` or `--status deprecated`
- **Agent-Usability Notes:**
  - Clean table output
  - Deprecation handling is non-obvious (excluded by default unless explicitly included)
  - Tags are AND-filtered (less intuitive for agents than OR)

---

#### **`conventions [query]`** — MODERATE, Stateless
- **Arguments:** 1 optional (free-text or path)
- **Options:** 5 optional
  - `--tag` (repeatable, AND logic)
  - `--status` (active/draft/deprecated)
  - `--scope` (project or directory path)
  - `--all` (include deprecated)
- **Output:** Rich table (title, scope, status, tags, rule)
- **Complexity Drivers:**
  - Dual-mode argument: if query contains `/` or `.`, treated as scope-based retrieval; else free-text search
  - Complex filtering chain (tag AND-logic, status filter, scope filter)
  - Deprecation handling matches concepts (excluded by default)
- **Agent-Usability Notes:**
  - Dual-mode argument is non-obvious (no explicit flag to switch modes)
  - Path vs. query distinction requires agents to know the heuristic

---

#### **`search [query]`** — MODERATE, Stateless
- **Arguments:** 1 optional (search query)
- **Options:** 2 optional
  - `--tag` (cross-artifact)
  - `--scope` (file scope path)
- **Output:** Structured results with concept/design/stack sections
- **Complexity Drivers:**
  - Unified search across 3 artifact types (concepts, design files, Stack posts)
  - Link graph integration for scope-based filtering
  - Optional query (must provide at least one of query/tag/scope)
- **Agent-Usability Notes:**
  - Good entry point for broad exploration
  - Links back to concepts, design files, and Stack posts
  - Prevents empty queries (at least one filter required)

---

#### **`impact <file>`** — MODERATE, Stateless
- **Arguments:** 1 required (source file)
- **Options:** 2 optional
  - `--depth N` (1-3, default 1) — traversal depth clamped
  - `--quiet` (paths only, one per line)
- **Output:** Tree-structured dependents with design descriptions + open Stack warnings
- **Complexity Drivers:**
  - Traverses link graph's `ast_import` edges in reverse
  - Clamping depth to 1-3 prevents runaway traversal
  - Inline Stack post warnings for open issues on dependents
  - Design file description retrieval for each dependent
- **Agent-Usability Notes:**
  - Excellent for impact analysis before refactoring
  - `--quiet` mode makes output piping-friendly
  - Open Stack warnings are contextually helpful
  - Depth clamping is invisible to agents but prevents runaway traversal

---

#### **`orient`** — SIMPLE, Stateless
- **Arguments:** None
- **Options:** None
- **Output:** Plain text (no Rich formatting) containing:
  - TOPOLOGY.md content
  - File-level descriptions from .aindex entries
  - Library stats (concept count, convention count, open Stack posts)
  - IWH signal summaries
- **Complexity Drivers:**
  - Token budget aware (_ORIENT_TOKEN_BUDGET = 2000 tokens)
  - Collects .aindex data from entire project
- **Agent-Usability Notes:**
  - Called at session start per CLAUDE.md rules
  - Plain text output integrates cleanly with LLM context windows
  - Budget truncation is silent (no agent feedback on truncation)
  - Excellent project orientation but no feedback on what was omitted

---

#### **`help`** — SIMPLE, Stateless
- **Arguments:** None
- **Options:** None
- **Output:** Structured guidance in 3 Rich panels:
  1. **Available Commands** — grouped by workflow (session start, lookup, knowledge management, stack issues, IWH signals, design files, inspection)
  2. **Common Workflows** — 6 example workflows with command sequences
  3. **Navigation Tips** — wikilinks, reverse deps, cross-artifact search, filtering, no-project context
- **Agent-Usability Notes:**
  - Works without .lexibrary/ directory (graceful degradation)
  - Excellent reference for new agents
  - Workflows section shows command chaining patterns
  - Panel-based layout is readable in terminal and LLM context

---

#### **`validate`** — SIMPLE, Stateless
- **Arguments:** None
- **Options:** 3 optional
  - `--severity` (error/warning/info)
  - `--check` (run only named check)
  - `--json` (structured output)
- **Output:** Rich tables (default) or JSON
- **Complexity Drivers:**
  - Delegates to shared `_run_validate()` helper
  - Multiple check types available (filtered by name)
  - Two output formats
- **Agent-Usability Notes:**
  - Catches broken wikilinks, stale design files, other library health issues
  - JSON output supports structured parsing
  - Severity filtering prevents noise

---

#### **`status [path]`** — SIMPLE, Stateless
- **Arguments:** 1 optional (directory to check)
- **Options:** 1 optional
  - `--quiet` / `-q` (single-line output for hooks/CI)
- **Output:** Library health summary (truncated or quiet)
- **Complexity Drivers:**
  - Shared with `_run_status()` helper
  - Quiet mode for CI/hooks integration
- **Agent-Usability Notes:**
  - Quick health check without deep analysis
  - Quiet mode enables automated workflows

---

#### **`describe <dir> <description>`** — SIMPLE, Stateless
- **Arguments:** 2 required (directory, new billboard description)
- **Options:** None
- **Output:** Confirmation message
- **Complexity Drivers:**
  - Parses, mutates, re-serializes .aindex file
  - Minimal business logic
- **Agent-Usability Notes:**
  - Straightforward file manipulation
  - No confirmation prompt (direct mutation)

---

### 2. CONCEPT COMMANDS (5 commands)

All concept commands assume agents already have a concepts directory. Stateless (no session state).

#### **`concept new <name>`** — SIMPLE
- **Arguments:** 1 required (concept name)
- **Options:** 1 optional (`--tag` repeatable)
- **Output:** Confirmation with file path
- **Mutation:** Creates new concept file from template
- **Agent-Usability Notes:**
  - Straightforward — name to file path mapping is obvious
  - Tags optional (allows tagging during creation)

---

#### **`concept link <name> <file>`** — SIMPLE
- **Arguments:** 2 required (concept name, source file)
- **Options:** None
- **Output:** Confirmation with wikilink added
- **Mutation:** Adds wikilink to design file
- **Agent-Usability Notes:**
  - Requires design file to exist (returns error if missing)
  - Concept existence check prevents dangling links
  - Idempotent (double-linking returns "already linked" and exits cleanly)

---

#### **`concept comment <slug>`** — SIMPLE
- **Arguments:** 1 required (concept slug, NOT name)
- **Options:** 1 required (`--body`)
- **Output:** Confirmation with comment file path
- **Mutation:** Appends to .comments.yaml file
- **Agent-Usability Notes:**
  - Uses slug (filename stem), not title — requires agents to know mapping
  - `--body` is required (no interactive prompt)

---

#### **`concept deprecate <slug>`** — SIMPLE
- **Arguments:** 1 required (concept slug)
- **Options:** 1 optional (`--superseded-by`)
- **Output:** Confirmation with deprecation status
- **Mutation:** Sets status to deprecated, records timestamp
- **Agent-Usability Notes:**
  - Slug-based (not title) — inconsistent with other concept commands
  - Idempotent (already-deprecated returns "already deprecated" and exits cleanly)
  - Optional supersession tracking

---

### 3. CONVENTION COMMANDS (5 commands)

All convention commands assume agents already have a conventions directory. Stateless.

#### **`convention new`** — MODERATE
- **Arguments:** None (all options)
- **Options:** 6 total, 2 required
  - Required: `--scope`, `--body`
  - Optional: `--tag` (repeatable), `--title` (auto-derived if omitted), `--source` (user/agent, default user), `--alias` (repeatable)
- **Output:** Confirmation with file path
- **Mutation:** Creates new convention file with status/priority set based on source
- **Complexity Drivers:**
  - Title auto-derivation from body (first 60 chars)
  - Status/priority set based on source (agent → draft/-1, user → active/0)
  - Alias support for short references
- **Agent-Usability Notes:**
  - All-options interface (no positional args) is non-standard but avoids ambiguity
  - Source parameter controls approval workflow implicitly
  - Slug collision detection prevents duplicates

---

#### **`convention approve <name>`** — SIMPLE
- **Arguments:** 1 required (convention title or slug)
- **Options:** None
- **Output:** Confirmation with new status
- **Mutation:** Sets status to active
- **Agent-Usability Notes:**
  - Accepts title OR slug (flexible matching)
  - Idempotent (already-active returns "already active" and exits)
  - Rejects deprecated conventions (cannot approve deprecated)

---

#### **`convention deprecate <name>`** — SIMPLE
- **Arguments:** 1 required (convention title or slug)
- **Options:** None
- **Output:** Confirmation with timestamp
- **Mutation:** Sets status to deprecated, records UTC timestamp
- **Agent-Usability Notes:**
  - Flexible matching (title or slug)
  - Idempotent (already-deprecated returns "already deprecated" and exits)
  - No supersession tracking (unlike concepts)

---

#### **`convention comment <name>`** — SIMPLE
- **Arguments:** 1 required (convention title or slug)
- **Options:** 1 required (`--body`)
- **Output:** Confirmation with comment file path
- **Mutation:** Appends to .comments.yaml file
- **Agent-Usability Notes:**
  - Flexible matching (title or slug)
  - `--body` required (no interactive prompt)
  - Consistent with concept comment pattern

---

### 4. DESIGN COMMANDS (2 commands)

#### **`design update <file>`** — SIMPLE
- **Arguments:** 1 required (source file)
- **Options:** None
- **Output:** Either existing design file content or scaffolded content
- **Side Effects:** Creates .lexibrary design file if missing (scaffolding)
- **Agent-Usability Notes:**
  - Dual-mode: display existing or scaffold new
  - Automatically creates directory structure (mkdir -p)
  - Hint printed: "set `updated_by: agent` in frontmatter after making changes"

---

#### **`design comment <file>`** — SIMPLE
- **Arguments:** 1 required (source file)
- **Options:** 1 required (`--body` or `-b`)
- **Output:** Confirmation
- **Mutation:** Appends to design file's .comments.yaml sibling
- **Agent-Usability Notes:**
  - Requires design file to exist (errors if missing)
  - `-b` short form available

---

### 5. STACK COMMANDS (11 commands)

All Stack commands are stateless but heavily interlinked via post IDs. Multi-step workflows have one-shot shortcuts.

#### **`stack post`** — COMPLEX
- **Arguments:** None (all options)
- **Options:** 10+ total
  - Required: `--title`, `--tag` (repeatable, at least one)
  - Optional: `--bead`, `--file` (repeatable), `--concept` (repeatable), `--problem`, `--context`, `--evidence` (repeatable), `--attempts` (repeatable), `--finding`, `--resolve`, `--resolution-type`
- **Output:** Post ID and confirmation
- **One-Shot Workflow:** `--finding ... --resolve --resolution-type ...` creates post + adds finding + marks resolved in single call
- **Complexity Drivers:**
  - 11 options with complex conditional validation
  - `--resolve` requires `--finding`
  - `--resolution-type` requires `--resolve`
  - Auto-assigns post ID (ST-NNN)
  - Two-step mutation inside one command (post creation, then finding addition if `--finding` provided)
- **Agent-Usability Notes:**
  - Comprehensive one-shot alternative to multi-step flow
  - Conditional validation prevents invalid state (good UX)
  - Post ID auto-generation is transparent to agents

---

#### **`stack search [query]`** — MODERATE
- **Arguments:** 1 optional (search query)
- **Options:** 6 optional
  - `--tag`, `--scope`, `--status`, `--concept`, `--resolution-type`, `--include-stale`
- **Output:** Rich table (ID, status, votes, title, tags)
- **Complexity Drivers:**
  - All filters are optional but at least one recommended
  - Status validation (open/resolved/outdated/duplicate/stale)
  - Stale posts excluded by default unless `--include-stale` or explicit `--status stale`
- **Agent-Usability Notes:**
  - Excellent for finding related issues
  - Stale filtering prevents noise
  - Votes prominently displayed (helps agents prioritize)

---

#### **`stack view <id>`** — SIMPLE
- **Arguments:** 1 required (post ID, e.g., ST-001)
- **Options:** None
- **Output:** Formatted panel + markdown sections (problem, context, evidence, attempts, findings)
- **Agent-Usability Notes:**
  - Complete post display in one call
  - Rich markdown rendering of findings
  - Status badge prominently displayed

---

#### **`stack finding <id>`** — SIMPLE
- **Arguments:** 1 required (post ID)
- **Options:** 2 optional (`--body` required, `--author` default "user")
- **Output:** Confirmation with finding number
- **Mutation:** Appends finding to post, auto-assigns finding number
- **Agent-Usability Notes:**
  - Straightforward append operation
  - Auto-numbering is transparent

---

#### **`stack vote <id> <direction>`** — MODERATE
- **Arguments:** 2 required (post ID, direction: up/down)
- **Options:** 3 optional (`--finding` number, `--comment` required for downvotes, `--author`)
- **Output:** Confirmation with new vote count
- **Mutation:** Records vote on post or finding
- **Complexity Drivers:**
  - `--comment` required for downvotes (prevents unsubstantiated downvotes)
  - Optional `--finding` toggles post vs. finding vote
  - Direction validation (up/down only)
- **Agent-Usability Notes:**
  - Conditional `--comment` requirement is good UX (prevents bad-faith downvotes)
  - Finding votes require explicit number (no ambiguity)

---

#### **`stack accept <id>`** — SIMPLE
- **Arguments:** 1 required (post ID)
- **Options:** 2 required
  - `--finding` (finding number)
  - `--resolution-type` (optional, e.g., fix, workaround)
- **Output:** Confirmation with new status
- **Mutation:** Marks finding as accepted, sets post status to resolved
- **Agent-Usability Notes:**
  - `--finding` must be explicit (no ambiguity)
  - Sets post status automatically (no separate status update needed)

---

#### **`stack list`** — SIMPLE
- **Arguments:** None
- **Options:** 2 optional (`--status`, `--tag`, `--include-stale`)
- **Output:** Rich table (ID, status, votes, title, tags)
- **Agent-Usability Notes:**
  - Simple listing with optional filters
  - Stale filtering matches search behavior

---

#### **`stack mark-outdated <id>`** — SIMPLE
- **Arguments:** 1 required (post ID)
- **Options:** None
- **Output:** Confirmation
- **Mutation:** Sets status to outdated
- **Agent-Usability Notes:**
  - Direct status mutation (no conditions)

---

#### **`stack duplicate <id>`** — SIMPLE
- **Arguments:** 1 required (post ID to mark as duplicate)
- **Options:** 1 required (`--of` original post ID)
- **Output:** Confirmation
- **Mutation:** Sets status to duplicate, records duplicate_of
- **Agent-Usability Notes:**
  - Explicit `--of` parameter prevents confusion

---

#### **`stack comment <id>`** — SIMPLE
- **Arguments:** 1 required (post ID)
- **Options:** 1 required (`--body` or `-b`)
- **Output:** Confirmation with comment count
- **Mutation:** Appends to .comments.yaml sibling
- **Agent-Usability Notes:**
  - `-b` short form available
  - Shows total comment count after append

---

#### **`stack stale <id>`** — SIMPLE
- **Arguments:** 1 required (post ID)
- **Options:** None
- **Output:** Confirmation with timestamp
- **Mutation:** Sets status to stale, records stale_at
- **Agent-Usability Notes:**
  - Only marks resolved posts as stale (validates state)
  - Timestamp feedback helps agents understand state

---

#### **`stack unstale <id>`** — SIMPLE
- **Arguments:** 1 required (post ID)
- **Options:** None
- **Output:** Confirmation
- **Mutation:** Resets status to resolved, clears stale_at
- **Agent-Usability Notes:**
  - Reverses staleness (idempotent-ish — errors if not stale)

---

### 6. IWH COMMANDS (3 commands)

All IWH commands are stateless and directly mutate .iwh files (with exception of `--peek`).

#### **`iwh write [dir]`** — SIMPLE
- **Arguments:** 1 optional (source directory, default project root)
- **Options:** 3 total, 1 required
  - Required: `--body`
  - Optional: `--scope` (incomplete/blocked/warning, default incomplete), `--author` (default "agent")
- **Output:** Confirmation with path
- **Mutation:** Creates .iwh YAML file in .lexibrary mirror directory
- **Agent-Usability Notes:**
  - Signals work per CLAUDE.md rules (incomplete/blocked/warning scopes)
  - Default scope is "incomplete" (good default for agents leaving work)
  - Mirror directory structure automatic

---

#### **`iwh read [dir]`** — SIMPLE
- **Arguments:** 1 optional (source directory, default project root)
- **Options:** 1 optional (`--peek` preserves signal instead of consuming)
- **Output:** Signal content
- **Mutation:** Deletes .iwh file (unless `--peek`)
- **Agent-Usability Notes:**
  - Default consumes signal (deletion)
  - `--peek` useful for inspection without side effects
  - Called at session start per CLAUDE.md rules

---

#### **`iwh list`** — SIMPLE
- **Arguments:** None
- **Options:** None
- **Output:** Rich table (directory, scope, author, age, body preview)
- **Agent-Usability Notes:**
  - Shows all signals in project at a glance
  - Age calculated in minutes/hours/days (human-readable)
  - Body preview truncated (50 chars)

---

## CLAUDE.md Agent Rules & Command Usage

### Instructed Command Sequences

CLAUDE.md prescribes these command patterns for agent sessions:

1. **Session Start:**
   ```
   lexi orient              # Get project context + stats
   lexi iwh list            # Check for previous-session signals
   lexi iwh read <dir>      # Consume any signals found
   ```

2. **Before Editing Files:**
   ```
   lexi lookup <file>       # Get design file, conventions, reverse links
   ```

3. **Before Making Architectural Decisions:**
   ```
   lexi concepts <topic>    # Search concept wiki
   ```

4. **When Debugging:**
   ```
   lexi stack search <query> # Check for known issues + attempts
   ```

5. **After Solving Issues:**
   ```
   lexi stack post --title "..." --problem "..." --attempts "..." [--finding "..." --resolve]
   ```

6. **Leaving Work Incomplete:**
   ```
   lexi iwh write <dir> --scope incomplete --body "..."
   lexi iwh write <dir> --scope blocked --body "..." # if blocked on external condition
   ```

### Prohibited Commands in Agent Sessions

- **Never run `lexictl` commands** (maintenance-only)
  - `lexictl init`, `lexictl update`, `lexictl validate`, `lexictl index`, `lexictl status`
- These are reserved for project administrators

---

## Complexity Assessment Matrix

| Complexity | Count | Examples |
|------------|-------|----------|
| **SIMPLE** | 15 | orient, help, status, describe, validate, concept new/link/deprecate, convention approve/deprecate, design update/comment, stack list/mark-outdated/duplicate/comment/stale/unstale, iwh write/read/list |
| **MODERATE** | 12 | concepts, conventions, search, impact, convention new, stack search, stack vote, stack accept, stack finding, stack view, stack post (without --resolve), iwh write (with complex scope validation) |
| **COMPLEX** | 4 | lookup, stack post (one-shot), impact (with depth traversal), concept comment (slug vs. name) |

**Total: 31 commands**

---

## Agent-Usability Issues & Gotchas

### 1. **Slug vs. Title Ambiguity**

**Issue:** Concept commands use different identifiers:
- `concept new <name>` — takes title
- `concept link <name> <file>` — takes title
- `concept comment <slug>` — takes slug (filename stem)
- `concept deprecate <slug>` — takes slug

**Impact:** Agents must know the difference and remember file naming. The slug is derived from title (lowercase, hyphens, 50 chars), but not documented in command help.

**Mitigation:** Concepts that fail by slug should suggest using title. Or unify to accept both (like conventions do).

---

### 2. **Convention Flexible Matching vs. Concept Strict Matching**

**Issue:**
- `convention approve <name>` — accepts title OR slug
- `convention deprecate <name>` — accepts title OR slug
- `concept deprecate <slug>` — accepts ONLY slug
- `concept comment <slug>` — accepts ONLY slug

**Impact:** Inconsistent UX. Agents must remember which commands are flexible.

**Mitigation:** Unify all concept and convention commands to accept title OR slug.

---

### 3. **Dual-Mode Arguments (Conventions)**

**Issue:** `lexi conventions [query]` switches behavior based on presence of `/` or `.` in query:
- With `/` or `.` → scope-based retrieval
- Without → free-text search

**Impact:** Non-obvious. Agents might query `src/auth` expecting path-based results but get free-text results if a concept is named "src-auth".

**Mitigation:** Add explicit flag `--by-scope` or separate commands (`conventions --scope <path>`).

---

### 4. **Deprecation Hiding (Concepts & Conventions)**

**Issue:** Deprecated items are excluded by default unless:
- `--all` flag OR
- `--status deprecated` explicit filter

**Impact:** Agents must remember this behavior. Query results might be surprising if deprecated items exist.

**Mitigation:** Mention in command help that deprecated items are hidden. Or default to showing all.

---

### 5. **IWH Scope Validation Silent Failure**

**Issue:** `lexi iwh write --scope invalid` returns error, but error message doesn't list valid scopes inline.

**Impact:** Agents must re-run with `--help` to discover valid values.

**Mitigation:** Embed valid scopes in error message: `"Invalid scope: 'invalid'. Must be one of: warning, incomplete, blocked"`

---

### 6. **Token Budget Truncation is Silent**

**Issue:** `lexi lookup` and `lexi orient` apply token budgets but don't inform agents what was omitted.

**Impact:** Agents don't know if they're seeing complete information or truncated results. Might miss critical sections.

**Mitigation:** Add footer message: `[dim]... {N} additional links omitted due to token budget[/dim]` when truncation occurs.

---

### 7. **Stack Post One-Shot Workflow Conditional Validation**

**Issue:** `lexi stack post --resolve` requires `--finding`. This is correct but unintuitive — agents might try:
```
lexi stack post --title "..." --tag issue --resolve  # ERROR: --resolve requires --finding
```

**Impact:** Agents need to read help to understand the dependency.

**Mitigation:** Better error message: `"--resolve requires --finding. Did you mean to add a finding with --finding '...'?"`

---

### 8. **No Output Format Options**

**Issue:** Most commands output Rich tables. No JSON or plain-text alternatives.

**Plans/Memory Note:** `plans/search-upgrade.md` and `plans/lookup-upgrade.md` discuss `--format json` and `--format plain` for structured output, but not yet implemented.

**Impact:** Agents can't easily parse table output programmatically. Hooks that call `lexi search` or `lexi lookup` have to scrape Rich tables.

**Mitigation:** Implement `--format json` and `--format plain` across lookup, search, and concept/convention commands.

---

### 9. **Stale Post Filtering Inconsistency**

**Issue:** Stack search and list default to excluding stale posts, but the exclusion behavior differs:
- `lexi stack search [query]` — excludes stale by default UNLESS `--include-stale` or `--status stale`
- `lexi stack list` — excludes stale by default UNLESS `--include-stale` or `--status stale`

**Impact:** Same behavior across both, which is good. But the logic is complex for agents to reason about (requires reading implementation).

**Mitigation:** Document this in command help: `"Stale posts are excluded by default. Use --include-stale or --status stale to show them."`

---

### 10. **IWH Enabled Configuration Not Enforced**

**Issue:** IWH commands check `config.iwh.enabled` and silently exit with code 0 if disabled.

**Impact:** Agents don't know if a command failed due to configuration or succeeded silently. No feedback.

**Mitigation:** Change silent exit to: `console.print("[yellow]IWH is disabled in project configuration.[/yellow]")` before exit(0).

---

## Output Format Observations

### Rich Tables (Most Commands)

- **Pros:** Colored, aligned, readable in terminal
- **Cons:** Hard to parse programmatically; no structured alternative

### Plain Text Sections (lookup, orient)

- **Pros:** Integrates cleanly with LLM context windows; lightweight
- **Cons:** No structure; agents must parse markdown manually

### Markdown Rendering (stack view, lookup design content)

- **Pros:** Renders nicely in terminal with syntax highlighting
- **Cons:** Large output; truncation silent

### Tree Output (impact)

- **Pros:** Clear visual hierarchy
- **Cons:** Only one output format (no `--quiet` alternative)

---

## Hook Integration

Per `plans/lookup-upgrade.md` and `plans/search-upgrade.md`, hooks will inject Lexibrary context via:

1. **PreToolUse hooks** (on Edit/Write) — call `lexi lookup --brief` or similar
2. **PostToolUse hooks** (on Grep/Glob) — call `lexi search` to augment results

**Required Hook Output Format (per MEMORY.md):**
```json
{
  "hookSpecificOutput": {
    "hookEventName": "...",
    "additionalContext": "..."
  }
}
```

**Current Bug:** `lexi-pre-edit.sh` emits bare `{"additionalContext": ...}` at top level. Must be fixed to match format.

---

## Design Patterns Worth Noting

### 1. **Project Root Discovery**

All commands that need `.lexibrary/` call `find_project_root(start=...)` which walks upward from target directory. Graceful handling of "not found" (some commands error, some exit silently).

### 2. **Scope Validation**

Commands validate that target is within `config.scope_root`. Prevents operations on files outside the managed scope.

### 3. **Idempotency**

Most mutation commands are idempotent:
- Concept link — "already linked" → exit cleanly
- Convention approve — "already active" → exit cleanly
- IWH write — overwrites existing signal

**Exception:** Stack operations are NOT idempotent (new posts get new IDs, duplicate votes increment).

### 4. **Priority-Based Truncation**

`lookup` implements principled truncation:
```
Priority: design (0) > conventions (1) > issues (2) > IWH (3) > links (4)
```

Always show highest-priority sections; truncate lower-priority ones if over budget.

### 5. **Status Enum Validation**

Commands with status filters (`concepts --status`, `conventions --status`, `stack search --status`) validate against allowed values before querying. Prevents invalid states.

### 6. **Link Graph Management**

Commands that use the link graph explicitly open, use, and close it:
```python
link_graph = open_index(project_root)
try:
    results = ...
finally:
    if link_graph is not None:
        link_graph.close()
```

Resource cleanup prevents file locks.

---

## Recommendations for Agent Usability

### High Priority

1. **Unify Identifier Handling** — All concept/convention commands should accept title OR slug, with flexible matching.

2. **Implement Output Format Options** — Add `--format json` and `--format plain` to lookup, search, concepts, conventions, stack commands. Enables hook integration and programmatic parsing.

3. **Document Workflow Sequences** — Create a CLI workflow reference showing command chains (session start, debugging, issue lifecycle).

4. **Add `--brief` Mode** — For `lookup` and other context commands, add a lightweight output mode (headers only, no design content) suitable for hook injection.

### Medium Priority

5. **Improve Error Messages** — Add inline suggestions and valid option values to error messages (e.g., "Invalid scope: must be one of X, Y, Z").

6. **Add Truncation Feedback** — When sections are omitted due to token budget, show `[dim]... N more items omitted[/dim]`.

7. **Separate Path-Based and Query-Based Conventions Lookup** — Add explicit `--by-scope` or split into separate commands to avoid dual-mode ambiguity.

8. **Consistent Slug/Title Matching** — Document the slug derivation formula or accept both interchangeably.

### Low Priority

9. **Add `--since` Flag to Stack Commands** — Allow time-based filtering (e.g., `lexi stack search --since 7d`).

10. **Enhance `orient` Output** — Add section about which design files are stale or have open Stack posts.

---

## Conclusion

The Lexibrary CLI demonstrates thoughtful design for agent usability with well-organized command groups, token-budget awareness, and composable one-shot workflows. The main opportunities for improvement are:

1. **Output format consistency** (toward JSON/plain-text alternatives)
2. **Identifier handling unification** (slug vs. title)
3. **Error message richness** (inline suggestions)
4. **Workflow documentation** (command chaining patterns)

The command suite is **agent-friendly and moderately complex** — agents can learn the patterns (stateless, structured output, optional filters) and apply them across different command groups.

