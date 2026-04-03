---
name: lexi-search
description: Cross-artifact search. Use to map territory before zooming in on unfamiliar parts of the codebase.
license: MIT
compatibility: Requires lexi CLI.
metadata:
  author: lexibrary
  version: "1.0"
---

Map the territory before zooming in. Run a broad search first to discover what exists, then follow up with targeted lookups.

## When to use

- Starting work in an unfamiliar area of the codebase
- Investigating how a concept or pattern is used across the project
- Looking for prior art before implementing something new

## Steps

1. Run `lexi search <query>` with a topic, file name, or keyword.
2. Review the results across all artifact types: concepts, conventions,
   design files, playbooks, and stack posts.
3. Drill into results:
   - **Design file hits** — run `lexi lookup <path>` to get design intent,
     conventions, known issues, and cross-references.
   - **All other hits** (concepts, conventions, stack posts, playbooks) —
     run `lexi view <artifact-id>` (e.g. `lexi view CN-003`, `lexi view ST-042`)
     to read the full artifact content.
4. Use `--type` to narrow results when the broad search returns too many hits
   (e.g. `lexi search --type stack <query>`).

## Examples

```
lexi search "error handling"
lexi search "wikilink resolver"
lexi search "config loading"
lexi search "rate limit"
```

## Edge cases

- **Start broad, then narrow.** If a query returns too many results, add a qualifying word. If it returns nothing, remove a word or try a synonym.
- **`lexi search` does not search source code.** It searches concepts, stack posts, and design files only. To find a symbol or string in source code, use `grep` or the Grep tool.
- **Follow up with `lexi lookup` or `lexi view`.** Search results tell you what exists; `lexi lookup <file>` tells you why a file was designed that way and what conventions apply; `lexi view <artifact-id>` gives you the full content of any non-design artifact.
