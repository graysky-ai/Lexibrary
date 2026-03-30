>> Needs a universal lexi show or view command to be built first and then will need revisiting to use correct command terminology.
# Plan: Update Agent Rules — Search-First Workflow

## Context

During a recent session, the agent skipped `lexi search` and `lexi concept` checks before making changes, and nearly missed updating the design file afterward. The current rules are scattered across several sections and don't establish a clear "search first, then act" workflow. This update consolidates and strengthens the rules so agents consistently check existing knowledge before writing code.

## Changes

**File:** `CLAUDE.md` (lines 58–98, the `Lexibrary — Agent Rules` section)

### 1. Add new "Before Starting Work" section (after Session Start, before "Before Reading or Editing Files")

Insert a new section that instructs agents to run `lexi search <keyword>` (or `<"key phrase">`) before starting any non-trivial task. This searches across all artifact types (concepts, conventions, designs, stack posts, playbooks). If results are returned, the agent should open and read the relevant artifacts using the appropriate subcommand (`lexi concept show`, `lexi stack show`, etc.).

Proposed wording:

```markdown
## Before Starting Work

- Run `lexi search <keyword>` (or `lexi search "key phrase"`) before starting
  any non-trivial task. This searches across all artifact types — concepts,
  conventions, designs, stack posts, and playbooks.
- If search returns hits, open and read relevant artifacts using the
  appropriate subcommand (e.g. `lexi concept show <slug>`,
  `lexi stack show <id>`, `lexi convention show <slug>`).
- This replaces the need to separately run `lexi concept` and
  `lexi stack search` in most cases — use those when you need
  type-specific filtering.
```

### 2. Simplify "Architectural Decisions" and "Debugging" sections

- **Architectural Decisions**: Keep, but reword to say "If `lexi search` didn't surface relevant concepts, also try `lexi concept <topic>` for narrower lookup."
- **Debugging**: Keep `lexi stack search` mention but reword: "If the initial `lexi search` didn't surface a solution, try `lexi stack search <query>` with more specific terms."

This avoids redundancy while preserving the type-specific commands for targeted use.

### 3. Clarify design file workflow in "After Editing Files"

Expand the existing bullet to make the workflow explicit:

```markdown
- After editing a source file under `src/`, check whether a design file
  exists at `.lexibrary/designs/<source_path>.md`. If it does:
  1. Read it via `lexi lookup <file>` (which surfaces the design content).
  2. Update relevant sections (Interface Contract, Dependencies,
     Complexity Warning, Wikilinks, Tags) to reflect your changes.
  3. Set `updated_by: agent` in frontmatter if not already set.
  4. Do not regenerate the full design file.
```

### 4. Fix typo

Line 64: `"Before Reading orEditing Files"` → `"Before Reading or Editing Files"`

## Verification

- Read the updated CLAUDE.md and confirm the rules are internally consistent
- Manually trace through a hypothetical edit task and confirm the rules guide the agent through: search → lookup → edit → update design
