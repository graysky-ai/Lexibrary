# Lexibrary — Editing Rules

These rules activate when you edit source files.

## Before Editing

- Run `lexi lookup <file>` before editing any source file under `src/`.
  This does not apply to test files.
- Read the corresponding design file in `.lexibrary/designs/` if one exists.

## After Editing

- Update the corresponding design file if one exists (source files under
  `src/`). Set `updated_by: agent` in the frontmatter and update relevant
  sections to reflect your changes.
- If the design file is stale or missing, run `lexi design update <file>` to
  regenerate it via the archivist pipeline. Use `--force` to regenerate even
  when the file appears up-to-date.
- Run `lexi validate` after modifying or creating files under `.lexibrary/`,
  or after changing artifact metadata. Skip for pure code changes under
  `src/` that don't affect library artifacts.
