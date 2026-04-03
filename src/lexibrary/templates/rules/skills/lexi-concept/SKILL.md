---
name: lexi-concept
description: Concept search. Use before making architectural decisions to check for existing patterns and design rationale.
license: MIT
compatibility: Requires lexi CLI.
metadata:
  author: lexibrary
  version: "1.0"
---

Search the project wiki for concepts and design rationale
before introducing new patterns or interpreting domain-specific terminology.

## When to use

- Before introducing a new abstraction or pattern — check if one already exists
- Before making an architectural decision — check for documented constraints
- When you encounter a wikilink (e.g., `[[Some Concept]]`) in a design file
- When reviewing code that uses domain-specific terminology you don't recognise

## Steps

1. **Search by topic** — run `lexi search --type concept <topic>` to find
   concepts matching a keyword or phrase. Review the returned titles, tags,
   and summaries before proceeding with your design decision.

2. **Filter by tag** — run `lexi search --type concept --tag <tag>` to narrow
   results. Common tags are `pattern`, `architecture`, and `decision`.

3. **Read a concept** — run `lexi view <concept-id>` (e.g. `lexi view CN-005`)
   to read the full concept content.

4. **Act on what you find** — if a concept constrains your approach, follow it.
   If no concept exists for your area, consider documenting one after you
   finish with `lexi concept new`.

## Examples

```
lexi search --type concept "context allocation"
```
Returns concepts matching "context allocation" — useful before deciding how
to partition LLM context across sub-agents.

```
lexi search --type concept --tag pattern
```
Returns architectural and design patterns documented for this project.

```
lexi view CN-005
```
Reads the full content of concept CN-005.

## Edge cases

- **Wikilinks** — a wikilink like `[[Some Concept]]` can be resolved by
  running `lexi search --type concept "Some Concept"`. The search is fuzzy,
  so partial matches will surface related entries.
- **Conventions are not concepts** — coding standards and project conventions
  are their own artifact type. Do not add them as concepts. Use
  `lexi search --type convention` to find conventions or `lexi convention new`
  to document them.
- **No results** — if a search returns nothing, the project has not yet
  documented that concept. Check `lexi search --type stack <topic>` for
  informal discussion, then consider capturing the knowledge with
  `lexi concept new`.
- **New concepts** — after discovering or defining a new pattern, document it
  with `lexi concept new --title "..." --tags "..." --body "..."` so future
  sessions can find it.
