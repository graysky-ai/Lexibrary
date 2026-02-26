# Lookup Upgrade Plan

> **Purpose:** Make `lexi lookup` a comprehensive context surface that gives agents everything they need about a file in one call.
> **Date:** 2026-02-25
> **Depends on:** Current `lookup` command in `src/lexibrary/cli/lexi_app.py:97-233`

---

## Current State

`lexi lookup <file>` already returns:
- Design file content (full markdown)
- Staleness warning (SHA-256 hash comparison)
- Inherited conventions (walking parent `.aindex` files)
- Dependents (inbound `ast_import` links from link graph)
- Also Referenced By (other link types — concepts, Stack posts, etc.)

This is already good. The gaps are in **structured output** and **missing sections** that would make it the definitive pre-edit context.

---

## Architecture Decision: Extract Lookup Logic into a Reusable Module

> **IMPORTANT — do not lose this insight.**

The lookup command currently lives entirely in CLI glue code (`lexi_app.py`). Before implementing these upgrades, **extract the core lookup logic into a dedicated module** (e.g., `src/lexibrary/lookup.py`) that returns a structured `LookupResult` dataclass.

**Why this matters:**
- `lexi lookup` (CLI) and `lexi design update` both interact with design files and could share enriched context
- `--format json` output should serialize a well-defined data structure, not scrape CLI output
- The future MCP server will call the same logic — it must not depend on CLI internals
- Hook scripts call `lexi lookup --brief` via subprocess today, but an MCP tool would call Python directly

**Shape of `LookupResult`:**
```python
@dataclasses.dataclass
class LookupResult:
    file: str
    description: str          # from DesignFileFrontmatter.description
    stale: bool
    conventions: list[str]
    dependents: list[str]
    concepts: list[ConceptSummary]
    stack_posts: list[StackPostSummary]
    siblings: list[SiblingSummary]
    design_content: str
```

The CLI `lookup` command becomes a thin renderer over `LookupResult`. `--format json` serializes it directly. `--brief` selects which fields to render. This is the single source of truth.

---

## Upgrades

### 1. Add File Description Summary Section

**Problem:** The design file content is dumped as raw markdown. Agents must parse it themselves to find the file's purpose.

**Solution:** Extract and display the `description` frontmatter field (from `DesignFileFrontmatter.description`) as a prominent first-line summary before the full design content.

```
## src/lexibrary/search.py
Description: Unified cross-artifact search combining concepts, design files, and Stack posts.
Status: current (hash matches)

--- Design File ---
[full design content]
```

**Implementation:** Call `parse_design_file_frontmatter()` (cheap — reads only the YAML header) and emit `frontmatter.description` as the header line. Note: the model field is `description`, not `role`.

### 2. Add Sibling File Awareness

**Problem:** When editing one file in a directory, the agent doesn't see what else lives alongside it.

**Solution:** List sibling source files in the same directory, with their descriptions from the parent `.aindex`.

```
## Sibling Files

- search.py — Unified cross-artifact search (this file)
- linkgraph.py — SQLite-backed bidirectional link index
- config/loader.py — YAML config loading and validation
```

**Implementation:** The parent `.aindex` file is already parsed for directory context. `AIndexFile.entries` (not `members`) gives a list of `AIndexEntry` objects with `name`, `entry_type`, and `description`. Filter to `entry_type == "file"` to exclude subdirectory entries. Note: convention retrieval is being decoupled from `.aindex` walking — conventions will come from `.lexibrary/conventions/` files via `ConventionIndex` (see `plans/conventions-artifact.md` D1). The sibling file data still comes from `.aindex` entries.

### 3. Add Related Concepts Section

**Problem:** "Also Referenced By" shows concept wikilinks but only as link paths — not the concept content or why it's relevant.

**Solution:** When the link graph shows concept references, inline each concept's one-line summary and its status.

```
## Related Concepts

- **error-handling** (active, convention) — All module-level exceptions inherit from LexibraryError.
- **link-graph** (active, architecture) — SQLite-backed bidirectional link index.
```

**Implementation:**
- Filter `other_links` for `wikilink` and `concept_file_ref` types
- For each, load the concept frontmatter (title, status, tags) and summary line
- Display as a compact list

**Graceful degradation:** When the link graph index is unavailable (e.g., `open_index()` returns `None`), fall back to `parse_design_file().wikilinks` — this gives concept names from the design file's own wikilinks without needing the index. The output shows names only (no status/summary) but still provides useful cross-references:

```
## Related Concepts (index unavailable — names only)

- [[error-handling]]
- [[link-graph]]
```

This ensures the Related Concepts section works even before the link graph has been built.

### 4. Add Recent Stack Posts Section

**Problem:** Stack references appear in "Also Referenced By" but with no context about whether they're relevant or resolved.

**Solution:** Show Stack posts that reference this file, with their status and first-line summary.

```
## Recent Stack Posts

- ST-012 (resolved) — "Import cycle between crawler and parser"
- ST-045 (open) — "Search timeout on large repos"
```

**Implementation:**
- Filter `other_links` for `stack_file_ref` types
- Load each post's frontmatter for title, status, votes
- Sort by recency (post ID as proxy) and limit to 5

**Performance note:** Items 3 and 4 each require loading additional files (concept frontmatter, stack post frontmatter). For a file with 5 concept refs and 3 stack refs, that's 8 extra file reads. `--brief` mode skips these file reads entirely (see §5) to stay within hook timeout budgets.

### 5. Add `--brief` Flag for Hook Context

**Problem:** Full lookup output is too long for automatic injection. The PreToolUse hook (see §Hook Integration below) should inject concise context, not the full design file.

**Solution:** `--brief` emits only: description, staleness, conventions, sibling names, and concept names (no full design content, no dependents list, no concept summaries, no Stack posts).

```
## src/lexibrary/search.py
Description: Unified cross-artifact search...
Status: current

Conventions: from __future__ import annotations; pathspec "gitignore" pattern name
Siblings: linkgraph.py, config/loader.py
Related: [[error-handling]], [[link-graph]]
```

`--brief` is intentionally cheap: it reads only frontmatter + walks parent `.aindex` files (already done for conventions). No concept/Stack file reads, no link graph queries. This keeps it well within the 10-second hook timeout.

The PreToolUse hook uses `lexi lookup <file> --brief` to keep injected context concise.

### 6. Add `--format json` Output Mode

**Problem:** Rich terminal output isn't suitable for programmatic consumption. Structured JSON is needed for MCP integration and for the PreToolUse hook to parse results reliably.

**Solution:** Add `--format json` flag that serializes the `LookupResult` dataclass directly:

```json
{
  "file": "src/lexibrary/search.py",
  "description": "Unified cross-artifact search...",
  "stale": false,
  "conventions": ["from __future__ import annotations in every module"],
  "dependents": ["src/lexibrary/cli/lexi_app.py"],
  "concepts": [{"name": "link-graph", "status": "active", "summary": "..."}],
  "stack_posts": [{"id": "ST-012", "status": "resolved", "title": "..."}],
  "siblings": [{"name": "linkgraph.py", "description": "SQLite-backed bidirectional link index"}],
  "design_content": "..."
}
```

**`--brief --format json` interaction:** `--brief` and `--format` are orthogonal. `--brief` controls *which data is gathered* (fewer fields, no file reads for concepts/Stack). `--format json` controls *how data is rendered* (JSON vs terminal). Combined, `--brief --format json` emits a reduced JSON:

```json
{
  "file": "src/lexibrary/search.py",
  "description": "Unified cross-artifact search...",
  "stale": false,
  "conventions": ["from __future__ import annotations in every module"],
  "siblings": ["linkgraph.py", "config/loader.py"],
  "concepts": ["error-handling", "link-graph"]
}
```

**MCP note:** This JSON schema will become a de facto API contract once MCP tools consume it. Design it intentionally as a stable interface — field additions are fine, removals/renames are breaking. MCP implementation is not imminent but the schema should be treated as a public surface from day one.

---

## Hook Integration: Update Existing PreToolUse on Edit/Write

**File:** `src/lexibrary/init/rules/claude.py`

This is the write-time counterpart to the Grep read-time hook defined in `plans/search-upgrade.md` Phase 2. Together they form a complete loop: agents get Lexibrary context when **searching** (PostToolUse on Grep → `lexi search`) and when **editing** (PreToolUse on Edit/Write → `lexi lookup`).

> **Cross-plan alignment notes:**
>
> 1. **Hook output format:** Both this plan and `plans/search-upgrade.md` generate hook scripts that emit `hookSpecificOutput` JSON. The output format must stay consistent across both hooks. When implementing either plan, verify the other plan's hook format matches.
>
> 2. **Combined context budget:** When both hooks are active, an agent doing Grep → Edit fires two hooks injecting separate Lexibrary context (search augment on Grep, lookup on Edit). In an exploration sequence (Grep × 3 → Edit), that's up to 4 context injections. The `--brief` flag on lookup and `--limit 3` on search keep each injection small, but monitor combined context volume during testing. If it proves excessive, consider deduplicating (e.g., the lookup hook skips concept names already surfaced by a recent search augment).
>
> 3. **Linkgraph synergy:** The search-upgrade plan (Phase 1.5) adds a `snippet` column to the linkgraph `artifacts` table. The Related Concepts and Stack Posts sections here (§3, §4) currently load full artifact files for summaries. Once the snippet column exists, these sections could read summaries directly from the link graph instead of doing file I/O — a performance improvement worth noting for implementation.

### Existing hook — what changes

A PreToolUse hook on Edit/Write **already exists** in `claude.py` as `lexi-pre-edit.sh`. It currently runs `lexi lookup "$FILE_PATH"` (full output) and emits the result as `additionalContext`. **Do not create a second script.** Instead, update the existing `lexi-pre-edit.sh` to:

1. Use `lexi lookup "$FILE_PATH" --brief` (once §5 is implemented)
2. Fix the JSON output format (see bug below)

### Bug fix: Hook output format

The existing `lexi-pre-edit.sh` emits `{"additionalContext": "..."}` at the top level. This is **incorrect** per the Claude Code hook spec. The correct format wraps it in `hookSpecificOutput`:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "additionalContext": "Lexibrary context for src/foo.py:\nDescription: ...\nConventions: ..."
  }
}
```

Note: `permissionDecision` is omitted intentionally. When absent, normal permission handling proceeds. The hook is purely additive — it injects context, never blocks.

### Why PreToolUse (not PostToolUse)

Context must arrive **before** the edit executes — the agent needs to know conventions and constraints *while deciding what to write*, not after it's already written. PreToolUse fires before the tool runs and can inject `additionalContext` without blocking the edit.

### Timeout

The existing hook timeout is 10,000ms. **Keep it at 10,000ms.** While `--brief` should be fast (frontmatter parse + `.aindex` walk, no LLM calls), cold-start and large repos can be slow. 10s matches the existing budget and avoids regressions.

---

## Output Rendering: Agents First

The primary consumers of `lexi lookup` output are agents, not humans. Rendering decisions should optimize for agent comprehension:

- **Default terminal output:** Use `rich.markdown.Markdown` renderables for the design file content section rather than raw `console.print(content)`. This avoids accidental Rich markup interpretation (e.g., bracket patterns like `[red]` in code examples being treated as Rich styling).
- **`--format json`:** Clean JSON, no Rich formatting — this is the agent-native path.
- **`--brief`:** Plain text, no Rich panels or tables — compact lines that read well as `additionalContext` in a hook response.
- **Structured sections** (Description, Conventions, Concepts, etc.) should use simple markdown headers (`##`) and lists (`-`) that both agents and humans parse naturally.

---

## Files Changed

| File | Change |
|------|--------|
| `src/lexibrary/lookup.py` | **New** — extracted lookup logic, `LookupResult` dataclass, `build_lookup_result()` |
| `src/lexibrary/cli/lexi_app.py` | Thin CLI renderer over `LookupResult`, add `--format`, `--brief` flags |
| `src/lexibrary/init/rules/claude.py` | Fix `lexi-pre-edit.sh` output format + add `--brief` flag to lookup call |
| `src/lexibrary/init/rules/base.py` | Update lookup skill content mentioning new flags |
| `blueprints/src/lexibrary/cli/lexi_app.md` | Update interface table for new `lookup` signature |
| `blueprints/src/lexibrary/lookup.md` | **New** — design file for extracted lookup module |
| `tests/test_lookup.py` | Tests for `LookupResult` building, JSON format, brief mode |
| `tests/test_cli/test_lexi.py` | Tests for CLI rendering of new output sections |
| `tests/test_init/test_rules/test_claude.py` | Test updated hook script content and format |

---

## Priority Order

1. **Extract lookup logic** into `src/lexibrary/lookup.py` (architectural prerequisite — everything else builds on this)
2. **File description summary** (quick win, immediately clearer output)
3. **`--brief` flag** (prerequisite for the hook fix)
4. **Hook bug fix + `--brief` integration** (the payoff — agents automatically get correct, concise context before edits)
5. **Sibling file awareness** (near-free — reuses `.aindex` already parsed during convention walk)
6. **Related concepts section** (enriches the most common lookup scenario; includes graceful degradation)
7. **Recent Stack posts section** (useful but lower frequency; extra file I/O)
8. **`--format json`** (prep for MCP, not urgent until MCP work starts — but treat schema as stable from day one)
