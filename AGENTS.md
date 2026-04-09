# Agent Instructions

This project uses **bd** (beads) for issue tracking. Run `bd onboard` to get started.

## Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --status in_progress  # Claim work
bd close <id>         # Complete work
bd sync               # Sync with git
```

## Landing the Plane (Session Completion)

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd sync
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds

<!-- lexibrary:start -->
# Lexibrary — Agent Rules

## Session Start

1. Read `.lexibrary/TOPOLOGY.md` for project layout.
2. Run `lexi iwh list` to check for pending signals.
3. Run `lexi search <keyword>` and/or `lexi search "key phrase"` for targeted
   searches related to your current task.
   - For design file hits: run `lexi lookup <path>` to get full design context.
   - For all other hits (concepts, conventions, stack posts, playbooks):
     run `lexi view <artifact-id>` to read the full artifact.

Do not begin coding without this context.

If signals exist in a directory you are working in, run `lexi iwh read <dir>` to
consume the signal and understand what the previous session left behind.

Do not consume IWH signals for directories you are not actively working in —
consuming deletes the signal permanently. Sub-agents must not consume IWH signals.
Do not create an IWH signal if all work is complete.

## Before Reading or Editing Files

- Always run `lexi lookup <file>` before reading or editing any source file under `src/`.
  This does not apply to test files.

## After Editing Files

- Run `lexi design update <file>` to regenerate the design file via the
  archivist pipeline. Use `--force` to regenerate even when the file appears
  up-to-date. If the command fails, write an IWH signal noting the failure.
  - **Sandbox note:** `lexi design update` and `lexi design comment` invoke
    BAML (Rust runtime) which requires macOS `SCDynamicStore` access. In
    Claude Code, these commands must run with `dangerouslyDisableSandbox: true`
    or they will panic with a NULL object error in
    `system-configuration/dynamic_store.rs`.
- Run `lexi design comment <file> --body "..."` whenever the change affects
  behavior, contracts, or cross-file responsibilities. The archivist captures
  structure; the agent captures intent. Skip only for trivial or purely
  mechanical changes (renames, formatting, import reordering).
- Do not manually edit design files or set `updated_by: agent` in frontmatter.
- Run `lexi validate` after modifying or creating files under `.lexibrary/`,
  or after changing artifact metadata. Skip for pure code changes under
  `src/` that don't affect library artifacts.

## Architectural Decisions

- Run `lexi search <query>` before making architectural decisions to check for
  existing patterns, conventions, and prior art across all artifact types.
  - For design file hits: `lexi lookup <path>`
  - For concept, convention, or stack hits: `lexi view <artifact-id>`

## Debugging and Problem Solving

- Always run `lexi search --type stack <query>` before starting to debug an
  issue — a solution may already exist. Use `lexi view <post-id>` to read
  matching posts.
- For complex research or investigation, delegate to the `lexi-research`
  subagent rather than doing extensive exploration inline.
- After solving a non-trivial bug, run `lexi stack post` to document
  the problem and solution for future reference.

## Leaving Work Incomplete

- If you must stop before completing a task, run:
  `lexi iwh write <directory> --scope incomplete --body "description of what remains"`
- Use `--scope blocked` if work cannot proceed until a condition is met.
- If you encounter files being modified or created by a concurrent agent, use .iwh files to coordinate.

## Prohibited Commands

- Never run `lexictl` commands. These are maintenance-only operations
  reserved for project administrators.
  - Do not run `lexictl update`, `lexictl validate`, `lexictl status`,
    `lexictl init`, or any other `lexictl` subcommand.
  - If a task requires a `lexictl` command, ask the user to run it.
  - Use only `lexi` commands for your work.

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

---
name: lexi-stack
description: Stack Q&A for debugging. Use before debugging to check for existing solutions and after solving bugs to document findings.
license: MIT
compatibility: Requires lexi CLI.
metadata:
  author: lexibrary
  version: "1.0"
---

Search for existing solutions before debugging and document solved bugs so
future sessions do not repeat the same investigation.

## When to use

- Before starting to debug an issue — search first to avoid repeating work
- After solving a non-trivial bug — post the solution so the next agent benefits
- When adding a new finding to an existing open post

## Steps

1. **Search before you dig** — run `lexi search --type stack <query>` with keywords
   that describe the symptom or area. Use `lexi view <post-id>` to read matching
   posts before writing a single line of debug code.

2. **If no matching post exists**, proceed with your investigation. Keep notes
   on approaches that did not work — these become your `--attempts` value.

3. **After solving a bug**, post the result immediately while context is fresh:
   - Include `--problem` to describe the symptom.
   - Include `--attempts` to list dead ends — this is the most valuable field.
   - Include `--resolve` to mark the post as solved.
   - Include `--resolution-type fix` (or `workaround`, `wontfix`) as appropriate.

4. **If you have a new finding on an existing open post** — use
   `lexi stack finding <post-id>` rather than creating a duplicate post.

5. **For complex multi-post research** — delegate to the `lexi-research`
   subagent instead of chaining many `lexi search --type stack` calls manually.

## Examples

Search before debugging:
```
lexi search --type stack "config loader YAML validation error"
lexi search --type stack "pathspec gitwildmatch pattern"
```

Post a solved bug:
```
lexi stack post \
  --title "Config loader rejects valid YAML when anchor tags are present" \
  --tag config loader \
  --problem "PyYAML raises ScannerError on YAML anchors during config load" \
  --attempts "Tried upgrading PyYAML — version was not the issue. Tried disabling strict mode — no strict flag exists." \
  --finding "The safe_load call strips anchor support; switch to full_load for user config files." \
  --resolve \
  --resolution-type fix
```

Add a finding to an open post:
```
lexi stack finding post-42 \
  --body "Reproduced on Python 3.12 only; 3.11 is unaffected."
```

## Edge cases

- **Always include `--attempts`** — an empty attempts field is a missed
  opportunity. Even one-line notes about what you ruled out help future agents.
- **Use `--resolve` at post time** when the issue is already solved. A post
  created and immediately resolved is better than leaving a ghost open post.
- **Do not create duplicate posts.** Run `lexi search --type stack` first; add a
  finding to the existing post if one covers the same root cause.
- **Delegate large research tasks.** If synthesizing findings requires reading
  five or more stack posts plus multiple concepts, use the `lexi-research`
  subagent. The coding agent posts the final findings — `lexi-research` does not.
<!-- lexibrary:end -->