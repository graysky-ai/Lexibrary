# Lexibrary CLI Analysis — Executive Summary

**Date:** 2026-03-09  
**Scope:** Thorough analysis of `lexi` agent-facing CLI commands  
**Files Analyzed:**
- `src/lexibrary/cli/lexi_app.py` (2925 lines) — ALL command definitions
- `CLAUDE.md` (lines 49-106) — Agent usage rules
- `plans/lookup-upgrade.md` — Future architecture decisions
- `plans/search-upgrade.md` — Hook integration plans
- `MEMORY.md` — Architectural constraints

---

## Key Findings

### 1. Command Inventory
- **31 total commands** across 6 command groups
- **15 simple** (1-2 args, minimal validation)
- **12 moderate** (3-5 options, filtering chains)
- **4 complex** (6+ options, conditional validation, multi-step)

### 2. Overall Assessment
✅ **WELL-DESIGNED FOR AGENTS**
- All commands are stateless
- Output uses structured Rich tables
- Token budgets prevent overwhelming context
- One-shot workflow alternatives (e.g., `stack post ... --resolve`)
- Comprehensive project orientation (`orient` command)

⚠️ **MAIN USABILITY GAPS**
1. No `--format json` or `--format plain` (output not programmatic)
2. Slug vs. title ambiguity in concept commands
3. Deprecated items hidden by default (non-obvious)
4. Dual-mode conventions query (path vs. text) with no explicit flag
5. Token budget truncation is silent (agents don't know what's omitted)

### 3. Command Groups

#### Top-Level (11 commands)
- **Navigation:** `lookup`, `search`, `impact`, `concepts`, `conventions`
- **Orientation:** `orient`, `help`, `status`, `validate`
- **Utilities:** `describe`

Key complexity: `lookup` performs 6+ internal searches with token budget truncation.

#### Concept (5 commands)
- **Create:** `concept new`
- **Link:** `concept link`
- **Manage:** `concept comment`, `concept deprecate`

Key gotcha: `concept comment` and `concept deprecate` use **slug** (filename), not title. Other commands use title.

#### Convention (5 commands)
- **Create:** `convention new` (all-options style)
- **Lifecycle:** `convention approve`, `convention deprecate`
- **Manage:** `convention comment`

Better UX than concepts: all accept title OR slug (flexible matching).

#### Design (2 commands)
- **Update:** `design update` (display or scaffold)
- **Manage:** `design comment`

Simple and straightforward.

#### Stack (11 commands)
- **Create:** `stack post` (with one-shot `--finding ... --resolve`)
- **Search:** `stack search`, `stack list`
- **View:** `stack view`
- **Findings:** `stack finding`, `stack accept`, `stack vote`
- **Lifecycle:** `stack mark-outdated`, `stack duplicate`, `stack comment`, `stack stale`, `stack unstale`

Most complex group. `stack post` has 11 options with conditional validation.

#### IWH (3 commands)
- **Write:** `iwh write` (create signal)
- **Read:** `iwh read` (read/consume signal, with `--peek`)
- **List:** `iwh list` (show all signals)

Simple and consistent.

---

## Complexity Assessment

### Simple Commands (15)
These are trivial and require minimal agent reasoning:
```
orient, help, status, validate, describe
concept new, concept link, concept comment, concept deprecate
convention approve, convention deprecate, convention comment
design update, design comment
iwh write, iwh read, iwh list
```

### Moderate Commands (12)
These have filtering/validation but are understandable:
```
concepts, conventions, search, impact
convention new
stack search, stack finding, stack vote, stack accept, stack list
stack mark-outdated, stack view
```

### Complex Commands (4)
These require careful attention:
- **`lookup`** — 6+ internal searches, priority-based token budget truncation
- **`stack post`** — 11 options, conditional validation, one-shot workflow
- **`impact`** — depth-limited traversal with Stack warning integration
- **`concept comment`** — uses slug (not title) — inconsistent with other commands

---

## Agent-Facing Workflows

From `CLAUDE.md`, agents are instructed to follow these patterns:

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

### When Debugging
```bash
lexi stack search <query>  # Find related issues + attempts
```

### After Solving an Issue (One-Shot)
```bash
lexi stack post \
  --title "Config fails" \
  --tag config \
  --problem "Description..." \
  --finding "Set extra=forbid" \
  --resolve \
  --resolution-type fix
```

### Leaving Work Incomplete
```bash
lexi iwh write <dir> --scope incomplete --body "..."
lexi iwh write <dir> --scope blocked --body "..."
```

All patterns are **stateless** — no session management needed.

---

## Output Format Summary

| Format | Commands | Pros | Cons |
|--------|----------|------|------|
| Rich Tables | concepts, conventions, stack search/list | Colored, aligned | Not machine-parseable |
| Markdown | lookup design content, stack view | Readable, structured | Silent truncation |
| Tree ASCII | impact | Clear dependencies | Only one format |
| Plain Text | orient | Lightweight, LLM-friendly | No structure |
| Confirmation | mutations | Simple | No details |

**Gap:** No `--format json` or `--format plain` across any command. Plans exist but not implemented.

---

## Gotchas for Agents

### 1. Slug vs. Title Inconsistency
```bash
concept new <name>                # ✓ accepts title
concept link <name> <file>        # ✓ accepts title
concept comment <slug>            # ✗ accepts SLUG ONLY
concept deprecate <slug>          # ✗ accepts SLUG ONLY
```

**Fix:** Conventions do it right — accept both title and slug everywhere.

### 2. Deprecated Items Hidden
```bash
lexi concepts                      # Hides deprecated by default
lexi concepts --all                # Shows all
lexi concepts --status deprecated  # Shows only deprecated
```

**Impact:** Agents might be surprised by hidden results.

### 3. Dual-Mode Conventions Query
```bash
lexi conventions "topic"           # Free-text search
lexi conventions "src/auth"        # Path-based retrieval (has / or .)
```

**Issue:** No explicit flag to control mode. Heuristic is: if query has `/` or `.`, treat as path; else treat as text. Non-obvious.

### 4. Token Budget Truncation is Silent
`lookup` and `orient` truncate sections silently. No feedback to agents on what was omitted.

**Should show:** `[dim]... 5 additional links omitted due to token budget[/dim]`

### 5. Stack Post One-Shot Conditional Validation
```bash
lexi stack post --title "X" --tag issue --resolve  # ERROR: requires --finding
lexi stack post --title "X" --tag issue --resolution-type fix  # ERROR: requires --resolve
```

**Impact:** Agents need to read help to understand dependencies.

---

## Statelessness & Idempotency

### All Commands Are Stateless
- No session object or in-memory state
- Each command reads/writes files independently
- Multiple runs don't interfere (except for non-idempotent mutations)

### Idempotent Commands (Safe to Repeat)
- `concept link` — "already linked" → noop
- `concept deprecate` — "already deprecated" → noop
- `convention approve` — "already active" → noop
- `iwh write` — overwrites existing signal → deterministic

### Non-Idempotent Commands (Accumulate)
- `stack post` → new post with new ID
- `stack finding` → appends new finding (F1, F2, ...)
- `stack vote` → increments vote count
- `<X> comment` → appends new comment

**Good design:** Agents can safely repeat simple commands but must be careful with mutations.

---

## Token Budget Awareness

Two commands implement token budgets:

### `lookup`
- Total budget: `config.token_budgets.lookup_total_tokens`
- Priority-based truncation:
  1. Design file (always shown)
  2. Conventions (always shown)
  3. Known issues (priority 2)
  4. IWH signals (priority 3)
  5. Links (priority 4)
- **Issue:** Truncation is silent

### `orient`
- Total budget: 2000 tokens (~8KB)
- Sections: TOPOLOGY.md, file descriptions, stats, IWH summaries
- **Issue:** Truncation is silent

**Fix:** Add footer messages:
```
[dim]... 5 additional links omitted due to token budget[/dim]
```

---

## Recommendations (Prioritized)

### 🔴 HIGH — Blocks Agent Usability

1. **Unify concept/convention identifier handling**
   - All concept commands should accept title OR slug (like conventions do)
   - Impact: Reduces cognitive load, prevents errors

2. **Implement `--format json` and `--format plain`**
   - Required for hook integration and programmatic parsing
   - Affects: lookup, search, concepts, conventions, stack search
   - Timeline: Medium (per `lookup-upgrade.md` and `search-upgrade.md` plans)

3. **Add `--brief` mode for `lookup`**
   - Lightweight output for hook injection (PreToolUse)
   - Headers only, no design content

4. **Document slug derivation formula**
   - Agents need to know: lowercase, hyphens, max 50 chars
   - Where: Update command help and agent rules

### 🟡 MEDIUM — Improves DX

5. **Add truncation feedback**
   - Show `[dim]... N items omitted[/dim]` when over token budget
   - Impact: Agents know if information is incomplete

6. **Improve error messages**
   - Inline valid option values
   - Example: `"Invalid scope. Must be one of: incomplete, blocked, warning"`

7. **Separate path-based and query-based conventions lookup**
   - Add explicit `--by-scope` flag or split into separate commands
   - Impact: Removes dual-mode ambiguity

8. **Document command chaining patterns**
   - Create CLI workflow reference guide
   - Show: session start → debug → issue → resolution sequences

### 🟢 LOW — Nice to Have

9. **Add `--since` flag to Stack commands**
   - Time-based filtering (e.g., `--since 7d`)
   - Impact: Better for cleanup workflows

10. **Enhance `orient` output**
    - Show which design files are stale
    - Show count of open Stack posts by category

---

## Related Architecture Decisions

### From `plans/lookup-upgrade.md`
> Extract lookup core logic into `src/lexibrary/lookup.py` returning `LookupResult` dataclass.
> CLI is thin renderer. Enables MCP server, `--format json`, and hook reuse without scraping output.

**Impact:** Once implemented, lookup can be called by hooks and MCP servers directly, not via CLI subprocess.

### From `plans/search-upgrade.md`
> Add snippet field to result dataclasses so agents get actionable context without follow-up reads.
> Implement `--format plain` and `--limit N` for structured output and compact results.

**Impact:** Once implemented, search will be more powerful than raw grep.

### From `MEMORY.md` (Hook Output Format Bug)
> Claude Code hooks must use `{"hookSpecificOutput": {"hookEventName": "...", "additionalContext": "..."}}`.
> **Current bug:** `lexi-pre-edit.sh` emits bare `{"additionalContext": ...}` at top level.

**Impact:** Fix required before hook integration is complete.

---

## Test Coverage Gaps

Current tests cover:
- CLI command routing
- Validator checks
- Some integration tests

Missing:
- Agent usability patterns (chaining, error paths, truncation)
- Hook integration workflows
- `--format json` output validation
- Slug vs. title matching edge cases

---

## Conclusion

The Lexibrary CLI is **well-designed for agent usability** with thoughtful statelessness, token budgets, and one-shot workflow alternatives. The main opportunities for improvement are:

1. **Structured output formats** (toward JSON/plain-text)
2. **Identifier handling unification** (slug vs. title)
3. **Error message richness** (inline suggestions)
4. **Workflow documentation** (command chaining patterns)

**Complexity verdict:** Moderate overall. Most commands are simple; 4 complex commands require careful attention. Agents can learn the patterns and apply them effectively across different command groups.

**Agent-friendliness verdict:** Good. Stateless design, comprehensive context, token budgets, and one-shot alternatives make this CLI effective for AI-assisted development.

---

## Documents Generated

1. **CLI_ANALYSIS.md** (840 lines) — Comprehensive analysis with command-by-command breakdown
2. **CLI_QUICK_REFERENCE.md** — Quick lookup guide for commands and gotchas
3. **CLI_COMPLEXITY_MATRIX.txt** — Detailed complexity assessment with matrices

All files saved to `/Users/shanngray/AI_Projects/Lexibrarian/`.

