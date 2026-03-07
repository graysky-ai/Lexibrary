# Lexibrary — Editing Rules

These rules activate when you edit source files.

## Before Editing

- Run `lexi lookup <file>` before editing any source file to understand
  its role, dependencies, and conventions.
- Read the corresponding design file in `.lexibrary/designs/` if one exists.

## After Editing

- Update the corresponding design file to reflect your changes.
  Set `updated_by: agent` in the frontmatter.
- Run `lexi validate` to check for broken wikilinks, stale design
  files, or other library health issues introduced by your changes.
