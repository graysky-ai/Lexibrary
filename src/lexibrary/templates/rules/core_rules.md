# Lexibrary — Agent Rules

## Session Start

Read `.lexibrary/TOPOLOGY.md` for project layout, then run `lexi iwh list`
to check for pending signals. Do not begin coding without this context.

If signals exist in a directory you are working in, run `lexi iwh read <dir>` to
consume the signal and understand what the previous session left behind.

Do not consume IWH signals for directories you are not actively working in —
consuming deletes the signal permanently. Sub-agents must not consume IWH signals.
Do not create an IWH signal if all work is complete.

## Before Reading or Editing Files

- Always run `lexi lookup <file>` before reading or editing any source file under `src/`.
  This does not apply to test files.

## After Editing Files

- Update the corresponding design file if one exists (source files under
  `src/`). Set `updated_by: agent` in the frontmatter and update relevant
  sections to reflect your changes.
- If the design file is stale or missing, run `lexi design update <file>` to
  regenerate it via the archivist pipeline. Use `--force` to regenerate even
  when the file appears up-to-date.
- Run `lexi validate` after modifying or creating files under `.lexibrary/`,
  or after changing artifact metadata. Skip for pure code changes under
  `src/` that don't affect library artifacts.

## Architectural Decisions

- Always run `lexi search --type stack <query>` before making architectural decisions
  to check for existing project conventions and concepts.

## Debugging and Problem Solving

- Always run `lexi stack search <query>` before starting to debug an issue
  -- a solution may already exist.
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