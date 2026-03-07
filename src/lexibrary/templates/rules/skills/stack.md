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
