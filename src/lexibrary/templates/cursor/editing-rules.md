# Lexibrary — Editing Rules

These rules activate when you edit source files.

## Before Editing

- Run `lexi lookup <file>` before editing any source file under `src/`.
  This does not apply to test files.
- Read the corresponding design file in `.lexibrary/designs/` if one exists.

## After Editing

- Update the corresponding design file if one exists (source files under
  `src/`). If the design file is auto-generated (has `updated_by: lexictl`
  in frontmatter), set `updated_by: agent` and update relevant sections.
  Do not attempt to regenerate the full design file.
- Run `lexi validate` after modifying or creating files under `.lexibrary/`,
  or after changing artifact metadata. Skip for pure code changes under
  `src/` that don't affect library artifacts.
