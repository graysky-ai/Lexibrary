# /lexi-lookup — File and Directory Lookup

Use this **before editing any source file** to understand its role,
constraints, and known issues. The pre-edit hook runs this automatically,
but invoke it manually when you need context before planning changes.

## When to use

- Before editing a file -- understand design intent, dependencies, and conventions
- Before planning changes to a module -- look up the directory for a broad view
- When a wikilink or cross-reference points to a file you have not seen yet

## File lookup

Run `lexi lookup <file>` to see:

- **Design file** -- role, dependencies, and architectural context
- **Applicable conventions** -- coding standards that govern this file
- **Known Issues** -- open Stack posts referencing this file (with status, attempts, and votes)
- **IWH signals** -- any "I Was Here" signals for this file's directory (peek mode, not consumed)
- **Cross-references** -- reverse dependency links from the link graph

## Directory lookup

Run `lexi lookup <directory>` to see:

- **AIndex content** -- the directory's file map and entry descriptions
- **Applicable conventions** -- coding standards scoped to this directory
- **IWH signals** -- any signals left in this directory (peek mode)
