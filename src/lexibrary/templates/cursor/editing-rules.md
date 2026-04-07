# Lexibrary — Editing Rules

These rules activate when you edit source files.

## Before Editing

- Run `lexi lookup <file>` before editing any source file under `src/`.
  This does not apply to test files.
- Read the corresponding design file in `.lexibrary/designs/` if one exists.

## After Editing

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
