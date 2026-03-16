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

1. Run `lexi orient` to orient yourself in this project. This displays the
   project topology, library health, and any IWH (I Was Here) signals left
   by a previous session.
   - If IWH signals are listed, run `lexi iwh read <directory>` for each
     to understand the context and consume the signal before proceeding.

## Before Editing Files

- Run `lexi lookup <file>` before editing any source file to understand
  its role, dependencies, and conventions.

## After Editing Files

- Update the corresponding design file to reflect your changes.
  Set `updated_by: agent` in the frontmatter.
- Run `lexi validate` to check for broken wikilinks, stale design
  files, or other library health issues introduced by your changes.

## Architectural Decisions

- Run `lexi concepts <topic>` before making architectural decisions
  to check for existing project conventions and concepts.

## Debugging and Problem Solving

- Run `lexi stack search <query>` before starting to debug an issue
  -- a solution may already exist.
- For complex research or investigation, delegate to the `lexi-research`
  subagent rather than doing extensive exploration inline.
- After solving a non-trivial bug, run `lexi stack post` to document
  the problem and solution for future reference.

## Leaving Work Incomplete

- If you must stop before completing a task, run:
  `lexi iwh write <directory> --scope incomplete --body "description of what remains"`
- Use `--scope blocked` if work cannot proceed until a condition is met.
- Do NOT create an IWH signal if all work is clean and complete.

## Prohibited Commands

- Never run `lexictl` commands. These are maintenance-only operations
  reserved for project administrators.
  - Do not run `lexictl update`, `lexictl validate`, `lexictl status`,
    `lexictl init`, or any other `lexictl` subcommand.
  - Use only `lexi` commands for your work.

# /lexi-orient — Session Start

Use this at the **start of every session** to orient yourself in the project.

## Usage

Run `lexi orient` -- a single command that returns:

- **Project topology** -- directory structure and module map
- **Library stats** -- concept count, convention count, open stack post count
- **IWH signals** -- any "I Was Here" signals left by previous sessions (peek mode, not consumed)

If IWH signals are present, the output includes consumption guidance.
Only consume signals (via `lexi iwh read <dir>`) when you are committed
to working in that directory. Sub-agents must not consume IWH signals.

# /lexi-search — Cross-Artifact Search

Use this to **map the territory before zooming in**. When you receive a
task that touches unfamiliar parts of the codebase, start with a broad
search to discover what exists before diving into specific files.

## When to use

- Starting work in an unfamiliar area of the codebase
- Investigating how a concept or pattern is used across the project
- Looking for prior art before implementing something new

## Usage

Run `lexi search <query>` to perform a unified search that combines:

- **Concept lookup** -- matching concepts from the wiki by title, alias, or tag
- **Stack search** -- matching Stack Q&A posts by title or content
- **Design file search** -- matching design files by source path or content

Review all results to build a complete picture before proceeding.
Follow up with `lexi lookup <file>` on specific files of interest.

# /lexi-lookup — File and Directory Lookup

Use this **before editing any source file** to understand its role,
constraints, and known issues. The pre-edit hook runs this automatically,
but invoke it manually when you need context before planning changes.

## When to use

- Before editing a file -- understand design intent, dependencies, and conventions
- Before planning changes to a module -- look up the directory for a broad view
- When a wikilink or cross-reference points to a file you have not seen yet

## File lookup

Run `lexi lookup <file>` to see:

- **Design file** -- role, dependencies, and architectural context
- **Applicable conventions** -- coding standards that govern this file
- **Known Issues** -- open Stack posts referencing this file (with status, attempts, and votes)
- **IWH signals** -- any "I Was Here" signals for this file's directory (peek mode, not consumed)
- **Cross-references** -- reverse dependency links from the link graph

## Directory lookup

Run `lexi lookup <directory>` to see:

- **AIndex content** -- the directory's file map and entry descriptions
- **Applicable conventions** -- coding standards scoped to this directory
- **IWH signals** -- any signals left in this directory (peek mode)

# /lexi-concepts — Concept Search

Use this **before making architectural decisions** to check whether the
project already has conventions, patterns, or design rationale that
constrain your choices. Also use it when you encounter a wikilink
(e.g., ``[[Some Concept]]``) and need to understand what it refers to.

## When to use

- Before introducing a new pattern or abstraction -- check if one already exists
- When you encounter a wikilink in a design file or concept page
- When reviewing code that uses domain-specific terminology

## Usage

- `lexi concepts <topic>` -- search for concepts matching a topic
- `lexi concepts --tag <tag>` -- filter concepts by tag (e.g., `--tag convention`, `--tag pattern`)
- `lexi concepts --all` -- list all concepts in the project wiki

# /lexi-stack — Stack Q&A

Use this **before debugging** to check if a solution already exists, and
**after solving a non-trivial bug** to document the problem and solution
for future sessions. For complex research across multiple stack posts and
concepts, delegate to the `lexi-research` subagent instead.

## When to use

- Before starting to debug an issue -- search first to avoid repeating work
- After solving a non-trivial bug -- document it so the next agent benefits
- When adding a finding to an existing open post

## Usage

- `lexi stack search <query>` -- search for existing posts matching your query
- `lexi stack post --title "..." --tag ... --problem "..." --resolve`
  -- create a post documenting a solved issue (include `--attempts` for dead ends)
- `lexi stack finding <post-id>` -- add a finding to an existing Stack post

## Research subagent

For deep investigation that requires reading multiple stack posts, cross-referencing
concepts, and synthesizing findings, use the `lexi-research` subagent rather than
running multiple stack commands manually.
<!-- lexibrary:end -->