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
2. Review concept matches — wiki entries whose title, alias, or tag matches your query.
3. Review stack matches — Q&A posts whose title or body matches your query; note any previous attempts and dead ends.
4. Review design file matches — design files whose source path or content matches your query.
5. Follow up with `lexi lookup <file>` on any specific files of interest to get design intent, conventions, and known issues.

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
- **Follow up with `lexi lookup`.** Search results tell you what exists; `lexi lookup <file>` tells you why it was designed that way and what conventions apply.
