# Lexibrary CLI Quick Reference

**31 Commands across 6 Command Groups**

## Command Inventory by Complexity

### SIMPLE (15 commands) — 1-2 options, minimal validation
- `orient` — project orientation + stats
- `help` — structured guidance + workflows
- `status [path]` — library health (optionally quiet)
- `validate` — consistency checks
- `describe <dir> <desc>` — update .aindex billboard
- `concept new <name>` — create concept
- `concept link <name> <file>` — add wikilink
- `concept comment <slug>` — append comment (USES SLUG)
- `concept deprecate <slug>` — set deprecated (USES SLUG)
- `convention approve <name>` — promote draft to active (accepts title/slug)
- `convention deprecate <name>` — set deprecated (accepts title/slug)
- `convention comment <name>` — append comment (accepts title/slug)
- `design update <file>` — display or scaffold design file
- `design comment <file>` — append comment
- `iwh write [dir]` — create IWH signal
- `iwh read [dir]` — read/consume IWH signal (--peek preserves)
- `iwh list` — list all IWH signals

### MODERATE (12 commands) — 3-5 options, filtering/validation
- `concepts [topic]` — list/search concepts (--tag AND, --status, --all)
- `conventions [query]` — list/search conventions (dual-mode: path or query)
- `search [query]` — cross-artifact search (--tag, --scope)
- `impact <file>` — show reverse dependents (--depth 1-3, --quiet)
- `convention new` — create convention (all options, no positionals)
- `stack search [query]` — find issues (--tag, --scope, --status, --concept, --resolution-type)
- `stack finding <id>` — add finding (--body required, --author)
- `stack vote <id> up|down` — vote on issue (--finding, --comment required for downvote)
- `stack accept <id>` — accept finding (--finding required)
- `stack list` — list issues (--status, --tag, --include-stale)
- `stack mark-outdated <id>` — mark outdated
- `stack view <id>` — display full post

### COMPLEX (4 commands) — 6+ options, conditional validation, one-shot workflows
- `lookup <file>` — design file + conventions + issues + links (token budget truncation)
- `stack post` — create issue (--title, --tag, --finding, --resolve ONE-SHOT workflow)
- `impact <file>` — reverse dependency traversal with descriptions + Stack warnings
- `concept comment <slug>` — uses slug not title (inconsistent with other commands)

---

## Gotchas for Agents

### 1. Slug vs. Title Confusion
- `concept new <name>` → accepts title
- `concept link <name> <file>` → accepts title
- `concept comment <slug>` → **accepts SLUG ONLY** ⚠️
- `concept deprecate <slug>` → **accepts SLUG ONLY** ⚠️
- Slug = lowercase filename with hyphens, max 50 chars

**Fix:** Conventions are better — accept both title and slug everywhere.

### 2. Deprecated Items Hidden by Default
- `lexi concepts` — hides deprecated unless `--all` or `--status deprecated`
- `lexi conventions` — hides deprecated unless `--all` or `--status deprecated`

**Impact:** Query results may be surprising if deprecated items exist but aren't shown.

### 3. Dual-Mode Conventions Query
- `lexi conventions [query]` switches based on presence of `/` or `.`:
  - With `/` or `.` → scope-based retrieval (path)
  - Without → free-text search
- **No explicit flag to control mode** ⚠️

**Fix:** Add `--by-scope` flag or separate command.

### 4. IWH Configuration Silent Failure
- If IWH disabled in config, commands exit cleanly with code 0
- No feedback that operation was skipped

### 5. Slug-vs-Name in Conventions is Flexible
- `convention approve <name>` — accepts title OR slug
- `convention deprecate <name>` — accepts title OR slug
- `convention comment <name>` — accepts title OR slug

**Better than concepts, but still requires knowing the slug format.**

### 6. Stack Post One-Shot Validation
```bash
lexi stack post --resolve              # ERROR: requires --finding
lexi stack post --resolution-type fix  # ERROR: requires --resolve
```

Conditional validation is correct but non-obvious.

### 7. Token Budget Truncation is Silent
- `lexi lookup` and `lexi orient` truncate sections silently
- No feedback on what was omitted

**Should show:** `[dim]... N additional links omitted due to token budget[/dim]`

### 8. No `--format json` or `--format plain`
- Most commands output Rich tables (hard to parse)
- Plans exist (`lookup-upgrade.md`, `search-upgrade.md`) but not yet implemented

---

## Command Chaining Patterns (from CLAUDE.md)

### Session Start
```bash
lexi orient              # Get project context + stats
lexi iwh list            # Check for previous-session signals
lexi iwh read <dir>      # Consume any signals found
```

### Before Editing a File
```bash
lexi lookup <file>       # Design file + conventions + reverse links
```

### Before Making Architectural Decisions
```bash
lexi concepts <topic>    # Search concept wiki
```

### When Debugging
```bash
lexi stack search <query>     # Find related issues + attempts
```

### After Solving an Issue (One-Shot)
```bash
lexi stack post \
  --title "Config validation" \
  --tag config \
  --problem "Description..." \
  --finding "The solution was..." \
  --resolve \
  --resolution-type fix
```

### Or Multi-Step
```bash
lexi stack post --title "..." --tag ... --problem "..."
lexi stack finding ST-001 --body "Finding body..."
lexi stack accept ST-001 --finding 1 --resolution-type fix
```

### Leaving Work Incomplete
```bash
lexi iwh write <dir> --scope incomplete --body "What remains..."
lexi iwh write <dir> --scope blocked --body "Blocked on..."
```

---

## Statelessness & Side Effects

### Stateless (No Session State)
All 31 commands are **stateless** — they read/write files directly, no in-memory session.

### Idempotent Commands (Safe to Repeat)
- `concept link` — double-linking returns "already linked"
- `convention approve` — already-active returns "already active"
- `concept deprecate` — already-deprecated returns "already deprecated"
- `IWH write` — overwrites existing signal

### Non-Idempotent Commands (Mutations Accumulate)
- `stack post` — each run creates new post with new ID
- `stack finding` — each run appends new finding (increments number)
- `stack vote` — each run increments vote count
- `<X> comment` — each run appends new comment

---

## Output Format Summary

| Command | Output Format | Parseable |
|---------|---------------|-----------|
| `lookup` | Markdown + tables | No (needs better format) |
| `concepts` | Rich table | No |
| `conventions` | Rich table | No |
| `stack search` | Rich table | No |
| `stack view` | Markdown panels | No |
| `stack list` | Rich table | No |
| `orient` | Plain text | No |
| `impact` | Tree ASCII | No (has `--quiet` for paths) |
| `search` | Structured sections | No |
| Most mutations | Confirmation text | Yes (trivial) |

**Gap:** No `--format json` or `--format plain` for structured output.

---

## Validation Patterns

### Status Enum Validation
```
concepts --status {active | draft | deprecated}
conventions --status {active | draft | deprecated}
stack search --status {open | resolved | outdated | duplicate | stale}
```

### Scope Validation
```
convention new --scope {project | <path>}
iwh write --scope {incomplete | blocked | warning}
```

### Required Options
```
lexi stack post --tag <value> --title <value>  # At least 1 tag
lexi stack vote <id> {up|down} --comment <msg> # If downvote
lexi convention new --scope <path> --body <msg>
```

### Optional-with-Dependencies
```
stack post --resolve             # Requires --finding
stack post --resolution-type <t> # Requires --resolve
stack vote ... --finding N       # Toggles post vs. finding vote
```

---

## Prohibited Commands (Reserved for Admins)

**Never call in agent sessions:**
- `lexictl init`
- `lexictl update`
- `lexictl validate`
- `lexictl index`
- `lexictl status`

---

## Design Patterns Used Throughout

### 1. Project Root Discovery
- Walk upward from target to find `.lexibrary/` directory
- Graceful handling of "not found" (error or silent exit)

### 2. Scope Validation
- Verify target is within `config.scope_root` before operating
- Prevents operations on out-of-scope files

### 3. Priority-Based Truncation
```
lookup sections priority:
  1. Design file (always shown)
  2. Conventions (always shown)
  3. Known issues (priority 2)
  4. IWH signals (priority 3)
  5. Links (priority 4)
```

Highest-priority sections always shown; lower-priority truncated if over token budget.

### 4. Link Graph Management
```python
link_graph = open_index(project_root)
try:
    results = ...
finally:
    if link_graph is not None:
        link_graph.close()
```

Explicit cleanup prevents file locks.

### 5. Design File Staleness Checking
- `lookup` command warns if source file hash differs from design file hash
- Suggests `lexictl update <file>` to refresh

### 6. Flexible Identifier Matching
- Conventions: accept title (case-insensitive) OR slug
- Concepts: mostly accept name/slug, but inconsistent (concept comment uses slug only)

---

## Memory Notes (from MEMORY.md)

### Hook Output Format
Claude Code hooks must use:
```json
{
  "hookSpecificOutput": {
    "hookEventName": "...",
    "additionalContext": "..."
  }
}
```

**Current bug:** `lexi-pre-edit.sh` emits bare `{"additionalContext": ...}` at top level.

### Key Architectural Decision: Lookup Logic Extraction
From `plans/lookup-upgrade.md`:

> Extract lookup core logic into `src/lexibrary/lookup.py` returning `LookupResult` dataclass.
> CLI is thin renderer. Enables MCP server, `--format json`, and hook reuse without scraping output.

### Hook Injection Points
- **PreToolUse** (on Edit/Write) — call `lexi lookup --brief`
- **PostToolUse** (on Grep/Glob) — call `lexi search` to augment results

---

## Recommendations (Priority Order)

### 🔴 High (Blocks Agent Usability)
1. **Unify concept/convention identifier handling** — accept title OR slug everywhere
2. **Implement `--format json` and `--format plain`** — enable programmatic parsing
3. **Add `--brief` mode for lookup** — lightweight output for hook injection
4. **Document slug derivation formula** — agents need to know how slugs are generated

### 🟡 Medium (Improves DX)
5. **Improve error messages** — inline valid option values
6. **Add truncation feedback** — `[dim]... N items omitted[/dim]` when over budget
7. **Separate path/query conventions lookup** — add `--by-scope` flag or split command
8. **Document command chaining patterns** — workflow reference guide

### 🟢 Low (Nice to Have)
9. **Add `--since` flag to Stack commands** — time-based filtering
10. **Enhance orient output** — show stale design files + open Stack posts

---

## Test Coverage

Per `tests/test_cli/test_lexictl.py` and `tests/test_validator/test_info_checks.py`:

- CLI command routing covered
- Validator checks tested
- Some integration tests exist
- **Gap:** No comprehensive tests for agent usability patterns (chaining, error paths, truncation)

---

## Related Files

- **CLI Implementation:** `/Users/shanngray/AI_Projects/Lexibrarian/src/lexibrary/cli/lexi_app.py` (2925 lines)
- **Shared CLI Utilities:** `/Users/shanngray/AI_Projects/Lexibrarian/src/lexibrary/cli/_shared.py`
- **Agent Rules:** `/Users/shanngray/AI_Projects/Lexibrarian/CLAUDE.md` (lines 49-106)
- **Plan Documents:**
  - `plans/lookup-upgrade.md` — Future structured output for lookup
  - `plans/search-upgrade.md` — Future snippet/format enrichments for search
  - `plans/convention-v2-plan.md` — Convention system refinements
- **Config:** `/Users/shanngray/AI_Projects/Lexibrarian/pyproject.toml` (for CLI entry points)

---

## Summary Table

| Aspect | Status | Notes |
|--------|--------|-------|
| **Agent-Friendliness** | Good | Stateless, structured output, token budgets |
| **Command Count** | 31 | Manageable; well-organized into groups |
| **Complexity** | Moderate | Most commands simple/moderate; 4 complex |
| **Output Formats** | Limited | Rich tables, markdown, plain text; no JSON |
| **Error Handling** | Good | Validation with messages; could be richer |
| **Idempotency** | Mixed | ~4 idempotent; most mutations accumulate |
| **Documentation** | Partial | Inline help via `--help`; workflow guide missing |
| **Workflow Support** | Excellent | One-shot alternatives, chaining patterns |
| **Hook Integration** | Ready | But format `--format json` not yet available |

