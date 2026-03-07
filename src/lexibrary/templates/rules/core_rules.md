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
