---
name: lexi-lookup
description: File and directory context lookup. Use before editing any source file to understand its role, constraints, and known issues.
license: MIT
compatibility: Requires lexi CLI.
metadata:
  author: lexibrary
  version: "1.0"
---

Look up design context, conventions, and known issues for a file or directory
before making changes.

## When to use

- Before editing a file — understand design intent, dependencies, and conventions
- Before planning changes to a module — look up the directory for a broad view
- When a wikilink or cross-reference points to a file you have not seen yet

## Steps

1. **Identify your target** — use a file path when you need context for a
   specific source file; use a directory path for a broader module-level view.

2. **Run file lookup** — `lexi lookup <file>` returns:
   - **Design file** — role, dependencies, and architectural context
   - **Applicable conventions** — coding standards that govern this file
   - **Known Issues** — open Stack posts referencing this file (status, attempts, votes)
   - **IWH signals** — "I Was Here" signals for this file's directory (peek mode, not consumed)
   - **Cross-references** — reverse dependency links from the link graph
   - **Sibling files** — other files in the same directory with descriptions (brief: names only; full: with descriptions)
   - **Related concepts** — concepts linked to this file (brief: names and status; full: with summaries from the link graph)

3. **Run directory lookup** — `lexi lookup <directory>` returns:
   - **AIndex content** — the directory's file map and entry descriptions
   - **Applicable conventions** — coding standards scoped to this directory
   - **Triggered playbooks** — playbooks whose trigger globs match this directory
   - **Inbound import summary** — count of ast_import links targeting files in this directory
   - **IWH signals** — any signals left in this directory (peek mode)

4. **Act on what you find** — read any flagged Known Issues before writing
   code; consume IWH signals only when you are committed to working in that
   directory.

## Examples

```
lexi lookup src/lexibrary/archivist/service.py
```
Returns the design file for `service.py`, conventions that apply to it,
any open Stack posts that reference it, sibling files in `archivist/`,
related concepts, and IWH signals for `archivist/`.

```
lexi lookup src/lexibrary/archivist/
```
Returns the AIndex file map for the `archivist/` directory, directory-scoped
conventions, triggered playbooks, an inbound import summary, and any IWH
signals present there.

## Edge cases

- **Pre-edit hook** — the hook runs `lexi lookup` automatically before every
  Edit or Write tool call. You do not need to invoke it manually before every
  single edit, but run it manually when planning changes before touching files.
- **Directory vs file scope** — directory lookup gives a broader picture
  (module map, all conventions, triggered playbooks, inbound import counts) but
  omits the per-file design details, sibling context, related concepts, and
  Stack post cross-references that file lookup provides. Use both when starting
  work in an unfamiliar module.
- **IWH peek mode** — lookup never consumes IWH signals. Call
  `lexi iwh read <dir>` explicitly when you are ready to take over that work.
