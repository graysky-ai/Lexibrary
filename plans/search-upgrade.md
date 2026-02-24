# Search Upgrade Plan

> **Purpose:** Make `lexi search` the agent's first instinct for codebase exploration, and add hooks that augment built-in search with Lexibrary context.
> **Date:** 2026-02-25
> **Depends on:** Current `unified_search()` in `src/lexibrary/search.py`, hook infrastructure in `src/lexibrary/init/rules/claude.py`

---

## Problem

Agents have built-in search (Glob, Grep, Read) that they reach for instinctively. `lexi search` is richer (concepts + design files + Stack posts) but agents only use it when explicitly told to. The current search also lacks features that would make it clearly superior to raw grep.

## Goals

1. Make `lexi search` output more useful than raw grep for common agent queries
2. Add hooks that inject Lexibrary context alongside built-in search results
3. Keep search fast — agents won't wait more than 2-3 seconds

---

## Phase 1: Enrich Search Output

**File:** `src/lexibrary/search.py`, `src/lexibrary/cli/lexi_app.py`

### 1.1 Add snippet context to results

Current search returns titles and paths only. Add a `snippet` field (first 2-3 relevant lines) to each result type so agents get actionable context without a follow-up read.

- `_DesignFileResult` — include the `role` line from design file frontmatter
- `_StackResult` — include first sentence of the accepted answer (if resolved)
- `_ConceptResult` — include the body summary (already partially there)

### 1.2 Add `--format plain` output mode

Current Rich table output is noisy in hook context. Add `--format plain` that emits clean markdown suitable for injection into `additionalContext` JSON.

```
## Concepts: 2 matches
- **error-handling** (convention) — All exceptions inherit LexibraryError...
- **retry-pattern** (pattern) — Exponential backoff with jitter...

## Stack: 1 match
- ST-012 (resolved) — "Import cycle between crawler and parser" — Move shared types to...
```

### 1.3 Add `--limit N` flag

Cap results per category (default 5). Prevents token-heavy output when agents search broad terms.

---

## Phase 2: Pre-Search Hook (Claude Code)

**File:** `src/lexibrary/init/rules/claude.py`

### 2.1 Add a Grep/Glob post-hook that appends Lexibrary context

When agents use Grep or Glob, a PostToolUse hook runs `lexi search` with the same query and appends matching concepts/conventions as a `systemMessage`. This doesn't block or replace the built-in search — it augments it.

```python
_HOOKS_CONFIG = {
    # ... existing PreToolUse/PostToolUse for Edit/Write ...
    "PostToolUse": [
        # existing edit hook...
        {
            "matcher": "Grep|Glob",
            "hooks": [
                {
                    "type": "command",
                    "command": '"$CLAUDE_PROJECT_DIR"/.claude/hooks/lexi-search-augment.sh',
                    "timeout": 3000,
                },
            ],
        },
    ],
}
```

**Hook script logic:**
1. Extract the `pattern` or `query` from tool input JSON
2. Run `lexi search "<pattern>" --format plain --limit 3`
3. If results exist, emit `{"systemMessage": "Lexibrary context: ..."}`
4. If no results or timeout, exit silently (exit 0, no output)

**Key constraint:** 3-second timeout. If search is slow, the hook silently skips rather than blocking the agent. This means the FTS/index path must be fast.

### 2.2 Update settings.json generator

Add the new hook to `_HOOKS_CONFIG` and the corresponding script to the file generation list.

### 2.3 Update permissions

Add `Bash(lexi search *)` with `--format` flag to allowed patterns (already covered by `Bash(lexi *)` glob but worth being explicit).

---

## Phase 3: Search Quality Improvements

**File:** `src/lexibrary/search.py`

### 3.1 Fuzzy matching for concept names

Current concept search is exact substring. Add fuzzy matching (e.g., Levenshtein or trigram) so `lexi search "err handling"` finds the `error-handling` concept.

### 3.2 Scope-aware ranking

When a search comes from a hook with a file path context, boost results that are in the same directory tree. An agent grepping in `src/auth/` should see auth-related concepts first.

### 3.3 "Did you mean" suggestions

When search returns zero results, suggest the closest concept/tag names. Reduces dead-end searches that push agents back to raw grep.

---

## Files Changed

| File | Change |
|------|--------|
| `src/lexibrary/search.py` | Add snippets, fuzzy matching, scope-aware ranking |
| `src/lexibrary/cli/lexi_app.py` | Add `--format plain`, `--limit N` to `lexi search` |
| `src/lexibrary/init/rules/claude.py` | Add Grep/Glob post-hook config and script |
| `src/lexibrary/init/rules/base.py` | Update search skill content to mention new flags |
| `tests/test_search.py` | Tests for snippets, plain format, fuzzy, ranking |
| `tests/test_init/test_rules/test_claude.py` | Test hook generation for search augment |

---

## Success Criteria

- Agents naturally see Lexibrary context when grepping, without changing their habits
- `lexi search` output is useful enough that agents cite it in their reasoning
- Hook adds < 500ms latency to Grep/Glob operations (FTS path)
- Zero impact when Lexibrary has no relevant results (silent exit)
