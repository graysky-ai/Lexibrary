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

1. Read `.lexibrary/START_HERE.md` to understand the project structure and conventions.
2. Run `lexi iwh list` to check for IWH (I Was Here) signals left by a previous session.
   - If signals exist, run `lexi iwh read <directory>` for each to understand the context
     and consume the signal.
   - IWH files live in `.lexibrary/<mirror-path>/.iwh` (e.g., `.lexibrary/src/auth/.iwh`
     for the `src/auth/` directory).

## Before Editing Files

- Run `lexi lookup <file>` before editing any source file to understand
  its role, dependencies, and conventions.
- Read the corresponding design file in `.lexibrary/designs/` if one exists.

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

Orientate yourself in this Lexibrary-managed project.

## Steps

1. Read `.lexibrary/START_HERE.md` to understand the project layout,
   package map, and navigation protocol.
2. Run `lexi iwh list` to check for IWH signals across the project.
   - If any signals exist, run `lexi iwh read <directory>` for each to understand the context
     and consume the signal.
3. Run `lexi status` to see a summary of library health, including design file counts and staleness.

# /lexi-search — Cross-Artifact Search

Search across the entire Lexibrary knowledge base for a topic.

## Usage

Run `lexi search <query>` to perform a unified search that combines:

- **Concept lookup** — matching concepts from the wiki by title, alias, or tag.
- **Stack search** — matching Stack Q&A posts by title or content.
- **Design file search** — matching design files by source path or content.

Review all results to build a complete picture before proceeding.

# /lexi-lookup — File Lookup

Look up design context for a source file before editing it.

## Usage

Run `lexi lookup <file>` with the path to any source file to see:

- The corresponding design file content (role, dependencies, conventions)
- Related concepts and cross-references
- Staleness information (whether the design file is up to date)

Always run this before editing a file to understand its context and
avoid breaking conventions or dependencies.

# /lexi-concepts — Concept Search

Search for project concepts, conventions, and architectural patterns.

## Usage

- `lexi concepts <topic>` — search for concepts matching a topic
- `lexi concepts --tag <tag>` — filter concepts by tag (e.g., `--tag convention`, `--tag pattern`)
- `lexi concepts --all` — list all concepts in the project wiki

Use this before making architectural decisions to check for existing
conventions, patterns, or design rationale documented in the project.

# /lexi-stack — Stack Q&A

Search, post, and answer questions in the project's Stack knowledge base.

## Usage

- `lexi stack search <query>` — search for existing Q&A posts matching your query.
  Run this before debugging to check if a solution already exists.
- `lexi stack post` — create a new question post after encountering a non-trivial
  bug or issue. Document the problem clearly for future reference.
- `lexi stack answer <post-id>` — add an answer to an existing Stack post after
  solving the problem. Include the solution and any relevant context.

The Stack is the project's persistent knowledge base for debugging insights
and solutions. Contributing to it helps future sessions avoid repeating work.
<!-- lexibrary:end -->