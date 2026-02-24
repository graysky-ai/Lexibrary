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

## Upgrades

### 1. Add File Role Summary Section

**Problem:** The design file content is dumped as raw markdown. Agents must parse it themselves to find the role.

**Solution:** Extract and display the `role` frontmatter field as a prominent first-line summary before the full design content.

```
## src/lexibrary/search.py
Role: Unified cross-artifact search combining concepts, design files, and Stack posts.
Status: current (hash matches)

--- Design File ---
[full design content]
```

**Implementation:** Parse `DesignFileFrontmatter.description` (which contains the role) and emit it as a header before `console.print(content)`.

### 2. Add Related Concepts Section

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

### 3. Add Recent Stack Posts Section

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

### 4. Add `--format json` Output Mode

**Problem:** The pre-edit hook injects raw Rich output. Structured JSON would be cleaner for programmatic consumption and MCP integration (future).

**Solution:** Add `--format json` flag that outputs:

```json
{
  "file": "src/lexibrary/search.py",
  "role": "Unified cross-artifact search...",
  "stale": false,
  "conventions": ["from __future__ import annotations in every module", ...],
  "dependents": ["src/lexibrary/cli/lexi_app.py"],
  "concepts": [{"name": "link-graph", "status": "active", "summary": "..."}],
  "stack_posts": [{"id": "ST-012", "status": "resolved", "title": "..."}],
  "design_content": "..."
}
```

This is essential for MCP integration later — tools return structured data, not terminal output.

### 5. Add `--brief` Flag for Hook Context

**Problem:** Full lookup output is long. The pre-edit hook injects everything, which can be overwhelming.

**Solution:** `--brief` emits only: role, staleness, conventions, and concept names (no full design content, no dependents list).

```
## src/lexibrary/search.py
Role: Unified cross-artifact search...
Status: current

Conventions: from __future__ import annotations; pathspec "gitignore" pattern name
Related: [[error-handling]], [[link-graph]]
```

Update the pre-edit hook to use `lexi lookup <file> --brief` to keep injected context concise.

### 6. Add Sibling File Awareness

**Problem:** When editing one file in a directory, the agent doesn't see what else lives alongside it.

**Solution:** List sibling source files in the same directory that also have design files, with their roles.

```
## Sibling Files

- search.py — Unified cross-artifact search (this file)
- linkgraph.py — SQLite-backed bidirectional link index
- config/loader.py — YAML config loading and validation
```

**Implementation:** Scan the parent `.aindex` for the `members` list (already available from the aindex parser).

---

## Files Changed

| File | Change |
|------|--------|
| `src/lexibrary/cli/lexi_app.py` | Restructure `lookup()` output, add `--format`, `--brief` flags |
| `src/lexibrary/init/rules/claude.py` | Update pre-edit hook to use `--brief` |
| `src/lexibrary/init/rules/base.py` | Update lookup skill content mentioning new flags |
| `tests/test_cli/test_lexi.py` | Tests for new output sections, JSON format, brief mode |

---

## Priority Order

1. **File role summary** (quick win, immediately clearer output)
2. **`--brief` flag + hook update** (reduces noise in auto-injected context)
3. **Related concepts section** (enriches the most common lookup scenario)
4. **Recent Stack posts section** (useful but lower frequency)
5. **`--format json`** (prep for MCP, not urgent until MCP work starts)
6. **Sibling file awareness** (nice-to-have context)
