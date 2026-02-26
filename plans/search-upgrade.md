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

## Architecture Decision: Data Model First, CLI Second

> **IMPORTANT — do not lose this insight.**

The enrichments in this plan (snippets, format modes, limits) must be implemented at the **data model level** first, then surfaced through CLI rendering. This matters because:

- The MCP server plan (`plans/mcp-server.md`) will call `unified_search()` directly — it must return rich results without going through the CLI
- Hook scripts call the CLI today, but MCP tools call Python directly
- `--format plain` and `--format json` should render the same underlying `SearchResults` data, not implement separate query logic

**Concrete shape:** Add a `snippet` field to each result dataclass. `unified_search()` populates it. `render()` and a future `to_dict()` both consume it. CLI flags control rendering, not data gathering (except `--limit`, which caps results at the query level).

---

## Phase 1: Enrich Search Data Model

**File:** `src/lexibrary/search.py`, `src/lexibrary/cli/lexi_app.py`

### 1.1 Add snippet field to result dataclasses

Current search returns titles and paths only. Add a `snippet: str` field to each result type so agents get actionable context without a follow-up read.

**Data model changes:**

```python
@dataclass
class _ConceptResult:
    name: str
    status: str
    tags: list[str]
    summary: str          # already exists — this IS the snippet for concepts

@dataclass
class _DesignFileResult:
    source_path: str
    description: str      # already exists — this IS the snippet for design files
    tags: list[str]
    # Note: `description` comes from DesignFileFrontmatter.description,
    # which is the file's purpose/role. No new field needed.

@dataclass
class _StackResult:
    post_id: str
    title: str
    status: str
    votes: int
    tags: list[str]
    snippet: str = ""     # NEW — first sentence of accepted answer, if resolved
```

**Population strategy per code path:**

- **File-scanning fallback** (`_search_stack_posts`): Has access to full `StackPost` objects including `answers`. Extract `snippet` from first accepted answer's body (first sentence, capped at 120 chars). Cheap — data is already loaded.
- **FTS/tag index paths** (`_fts_search`, `_tag_search_from_index`): Currently only have `title`, `status`, `path` from the `artifacts` table. Snippets require Phase 1.5 (below).

**Key insight:** `_ConceptResult.summary` and `_DesignFileResult.description` already serve as snippets. Only `_StackResult` needs a new field. The Rich table rendering already truncates `summary` to 50 chars and `description` to 60 chars — `--format plain` should show more (120 chars).

### 1.2 Add `--format plain` output mode

Current Rich table output is noisy in hook context. Add `--format plain` that emits clean markdown suitable for injection into `additionalContext` JSON.

**Implementation approach:** Add a `format` parameter to `SearchResults.render()` that dispatches to `_render_rich()` (current behavior) or `_render_plain()` (new). Keep the public API simple — one entry point, two renderers.

```
## Concepts: 2 matches
- **error-handling** (convention) — All exceptions inherit LexibraryError...
- **retry-pattern** (pattern) — Exponential backoff with jitter...

## Stack: 1 match
- ST-012 (resolved) — "Import cycle between crawler and parser" — Move shared types to...
```

### 1.3 Add `--limit N` flag

Cap results per category (default 5). Prevents token-heavy output when agents search broad terms.

**Implementation:** Add `limit: int | None = None` parameter to `unified_search()`. Apply as a slice after each code path populates results. The FTS path already returns results in relevance order, so truncation preserves the best matches.

### 1.4 Update skill templates

Update `_SEARCH_SKILL` in `src/lexibrary/init/rules/base.py` to mention `--format plain` and `--limit N` flags. Update any other agent environment generators (Cursor, Codex, generic) that reference `lexi search` syntax.

---

## Phase 1.5: Linkgraph Schema Migration for Snippets

**File:** `src/lexibrary/linkgraph/schema.py`, `src/lexibrary/linkgraph/writer.py`

> **Why this is a separate phase:** The FTS and tag index code paths (`_fts_search`, `_tag_search_from_index`) populate results from the `artifacts` table only — they return `summary=""`, `tags=[]`, `votes=0`. Adding snippets to these fast paths requires storing snippet data in SQLite, populated during indexing.

### 1.5.1 Add `snippet` column to `artifacts` table

```sql
ALTER TABLE artifacts ADD COLUMN snippet TEXT DEFAULT '';
```

Populated during `lexictl update`:
- **Concepts:** `snippet` = `ConceptFile.summary` (first 120 chars)
- **Design files:** `snippet` = `DesignFileFrontmatter.description` (first 120 chars)
- **Stack posts:** `snippet` = first sentence of accepted answer body (or problem statement if no accepted answer)

### 1.5.2 Update `ArtifactResult` to include snippet

The `ArtifactResult` dataclass (returned by `full_text_search()` and `search_by_tag()`) needs a `snippet: str` field so the search code paths can populate result objects without additional file I/O.

### 1.5.3 Update search code paths

`_fts_search()` and `_tag_search_from_index()` use `hit.snippet` (from the new column) instead of hardcoding empty strings.

**Migration note:** Existing link graph databases will have `snippet = ''` for all rows until the next `lexictl update`. This is acceptable — snippets degrade gracefully to empty strings (same as current behavior).

---

## Phase 2: Search Augment Hook (Claude Code)

**File:** `src/lexibrary/init/rules/claude.py`

> **Cross-plan alignment note:** This hook and the PreToolUse Edit/Write hook in `plans/lookup-upgrade.md` together form the complete agent context loop: agents get Lexibrary context when **searching** (PostToolUse on Grep → `lexi search`) and when **editing** (PreToolUse on Edit/Write → `lexi lookup`). Both emit the same `hookSpecificOutput` JSON format. When implementing either, verify the other plan's hook format matches.
>
> **Important:** The existing `lexi-pre-edit.sh` has a format bug — it emits bare `{"additionalContext": ...}` instead of wrapping in `hookSpecificOutput`. That fix is scoped in the lookup-upgrade plan (§Hook Integration). Both plans should be implemented with the same output format.

### 2.1 Add a Grep post-hook that appends Lexibrary context

When agents use Grep, a PostToolUse hook runs `lexi search` with the same query and appends matching concepts/conventions as `additionalContext`. This doesn't block or replace the built-in search — it augments it.

**Why Grep only, not Grep|Glob:** Glob patterns (e.g., `**/*.tsx`, `src/auth/**`) are file path patterns, not semantic queries. Running `lexi search "**/*.tsx"` returns garbage. Grep's `pattern` field contains a regex that usually represents a meaningful term (function name, concept, error message) suitable for `lexi search`. If Glob augmentation is desired later, it would need heuristic extraction of directory/file names from the pattern — deferred to a future iteration.

```python
_HOOKS_CONFIG = {
    # ... existing PreToolUse/PostToolUse for Edit/Write ...
    "PostToolUse": [
        # existing edit hook...
        {
            "matcher": "Grep",
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
1. Read JSON from stdin, extract `tool_input.pattern` (Grep's search pattern field)
2. Sanitize the pattern: strip regex metacharacters to extract likely search terms (e.g., `log.*Error` → `log Error`, `function\s+\w+` → `function`). Skip if the sanitized query is empty or under 3 characters.
3. Run `lexi search "<sanitized_query>" --format plain --limit 3`
4. If results exist, emit `hookSpecificOutput` with `additionalContext`:
   ```json
   {
     "hookSpecificOutput": {
       "hookEventName": "PostToolUse",
       "additionalContext": "Lexibrary context:\n..."
     }
   }
   ```
5. If no results or timeout, exit silently (exit 0, no output)

**Key constraint:** 3-second timeout. If search is slow, the hook silently skips rather than blocking the agent. This means the FTS/index path must be fast.

**Performance budget:** Shell spawn (~50ms) + Python/CLI init (~200ms) + SQLite FTS query (~50ms) + format + JSON emit = ~300-500ms typical. Within the 3s timeout with headroom. See backlog item for caching if repeated rapid queries become an issue.

### 2.2 Update settings.json generator

Add the new hook to `_HOOKS_CONFIG` and the corresponding script to the file generation list. `_generate_hook_scripts()` returns 3 paths instead of 2. `generate_claude_rules()` return list grows from 9 to 10 items.

### 2.3 Update permissions

`Bash(lexi search *)` is already covered by `Bash(lexi *)` in `_PERMISSIONS_ALLOW`. No change needed, but verify during implementation.

### 2.4 Upgrade path for existing projects

Projects that have already run `lexictl setup` won't have the new hook script. `lexictl setup --update` (or re-running `lexictl init` with agent env selection) must write the new script and merge the new hook entry into `settings.json`. The existing additive merge logic in `_generate_settings_json()` handles this — it deduplicates by hook command path. Verify this works in tests.

---

## Phase 3: Search Quality Improvements

**File:** `src/lexibrary/search.py`, `src/lexibrary/wiki/index.py`

### 3.1 Fuzzy matching for concept names

Current `ConceptIndex.search()` in `wiki/index.py` is exact substring (`needle in field`). Add fuzzy matching so `lexi search "err handling"` finds the `error-handling` concept.

**Approach options:**
- **Option A: `rapidfuzz` library** — High-quality Levenshtein/trigram matching. Adds a new dependency (`rapidfuzz>=3.0.0,<4.0.0`). Fast C extension.
- **Option B: stdlib `difflib.get_close_matches()`** — No new dependency. Lower quality but may be sufficient for concept name matching (typically < 100 concepts per project).

**Recommendation:** Start with Option B (zero deps). Upgrade to `rapidfuzz` only if `difflib` proves insufficient for real-world concept name matching. This follows the project constraint of confirming deps are needed before adding them.

**Scope:** Fuzzy matching applies to the file-scanning fallback path only. The FTS5 index already provides stemming via the porter tokenizer, which handles most morphological variations (e.g., "handling" → "handl" matches "handler"). Fuzzy matching fills the gap for typos and abbreviations that stemming doesn't cover.

### 3.2 Scope-aware ranking

When a search includes scope context, boost results in the same directory tree. An agent grepping in `src/auth/` should see auth-related concepts first.

**Design gap:** Currently `lexi search` has `--scope` for *filtering* (exclude non-matching results), not *boosting* (rank matching results higher). The hook would need to pass file context, but Grep's `tool_input` has `path` (optional — the directory being searched) which could serve as boost scope.

**Proposed mechanism:** Add `--boost-scope <path>` flag to `lexi search`. Unlike `--scope` (which filters), `--boost-scope` sorts results with scope-matching items first, then others. The hook script extracts Grep's `path` field (if present) and passes it as `--boost-scope`.

**Fallback:** When `--boost-scope` is omitted, ranking is unchanged (FTS relevance or alphabetical). No regression for direct CLI usage.

### 3.3 "Did you mean" suggestions

When search returns zero results, suggest the closest concept/tag names. Reduces dead-end searches that push agents back to raw grep.

**Implementation:** When `SearchResults.has_results()` is False and a query was provided, run fuzzy matching (from 3.1) against all concept names and tags. Return up to 3 suggestions as a new `suggestions: list[str]` field on `SearchResults`. The plain format renderer emits: `No results. Did you mean: error-handling, error-recovery?`

---

## Files Changed

| File | Change |
|------|--------|
| `src/lexibrary/search.py` | Add `snippet` to `_StackResult`, render format dispatch, limit parameter, fuzzy matching, suggestions |
| `src/lexibrary/cli/lexi_app.py` | Add `--format plain`, `--limit N` to `lexi search` CLI |
| `src/lexibrary/linkgraph/schema.py` | Add `snippet` column to `artifacts` table |
| `src/lexibrary/linkgraph/writer.py` | Populate `snippet` during indexing |
| `src/lexibrary/linkgraph/query.py` | Include `snippet` in `ArtifactResult` and query results |
| `src/lexibrary/wiki/index.py` | Add fuzzy matching to `ConceptIndex.search()` |
| `src/lexibrary/init/rules/claude.py` | Add Grep post-hook config and `lexi-search-augment.sh` script |
| `src/lexibrary/init/rules/base.py` | Update `_SEARCH_SKILL` to mention `--format plain`, `--limit N` |
| `tests/test_search.py` | Tests for snippets, plain format, limit, fuzzy matching, suggestions |
| `tests/test_init/test_rules/test_claude.py` | Test hook generation for search augment script |

---

## Implementation Order

1. **Phase 1.1–1.3** — Data model changes + CLI flags (can ship independently, immediate value)
2. **Phase 1.4** — Skill template updates (trivial, do alongside 1.1–1.3)
3. **Phase 1.5** — Linkgraph schema migration (prerequisite for snippets in FTS path; can defer if file-scanning snippets are sufficient initially)
4. **Phase 2.1–2.4** — Grep hook (the big payoff — requires `--format plain` from Phase 1.2)
5. **Phase 3.1** — Fuzzy matching (independent, low risk)
6. **Phase 3.3** — "Did you mean" (depends on 3.1)
7. **Phase 3.2** — Scope-aware ranking (needs `--boost-scope` design, lowest priority)

---

## Success Criteria

- Agents naturally see Lexibrary context when grepping, without changing their habits
- `lexi search` output is useful enough that agents cite it in their reasoning
- Hook adds < 500ms typical latency to Grep operations (FTS path)
- Zero impact when Lexibrary has no relevant results (silent exit)
- Snippets appear in search results across all code paths (file-scanning immediately, FTS after next `lexictl update`)
