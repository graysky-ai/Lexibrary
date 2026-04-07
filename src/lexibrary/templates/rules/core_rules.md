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