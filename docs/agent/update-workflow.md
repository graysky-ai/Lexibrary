# Update Workflow -- After Editing a File

After making meaningful changes to a source file, update its design file so the next agent (or your future self) has accurate context. Design files are generated and maintained by the archivist pipeline -- agents trigger updates via CLI commands rather than editing design files directly.

## When to Run `lexi design update`

Run `lexi design update <file>` after your changes affect:

- **What the file does** -- new functionality, changed purpose, removed features
- **The public interface** -- new functions, changed signatures, renamed classes, new constants
- **Key implementation details** -- changed algorithms, new dependencies, architectural decisions
- **Dependencies** -- new imports or removed imports

Use `--force` to regenerate even when the file appears up-to-date (e.g. when you know the design file is stale but the hashes haven't changed). If the command fails, write an IWH signal noting the failure so the next agent or operator can investigate.

## When to Run `lexi design comment`

Run `lexi design comment <file> --body "..."` whenever your change affects:

- **Behavior** -- the file does something differently at runtime
- **Contracts** -- function signatures, return types, or error handling changed
- **Cross-file responsibilities** -- the change shifts work to or from other modules

The archivist captures structure (signatures, imports, class hierarchy). The agent captures intent -- **why** a change was made, what trade-offs were considered, and how the change interacts with the rest of the system. Comments are appended to the design file and preserved across regeneration.

**Skip** `lexi design comment` for trivial or purely mechanical changes: renames, formatting, import reordering.

## When NOT to Update

Let the operator's `lexictl update` handle it instead when:

- **Cosmetic changes** -- formatting, whitespace, comment rewording
- **Bulk refactors** -- renaming a variable across many files (the operator can regenerate all design files at once)

## What NOT to Touch

Do not manually edit design files. Specifically, do not modify:

- **Design file body** -- the Summary, Interface Contract, and Key Details sections are managed by the archivist pipeline via `lexi design update`
- **Frontmatter fields** -- do not set `updated_by` or other frontmatter values by hand
- **Staleness metadata** -- the HTML comment block at the bottom containing `source`, `source_hash`, `interface_hash`, `design_hash`, `generated`, and `generator`. This is managed by `lexictl update`
- **Generated timestamps** -- these track when the LLM last generated the file
- **Source hashes** -- these are SHA-256 hashes used for change detection

Modifying these fields will confuse the change detection system and may cause unnecessary regeneration or missed updates.

## Example

Suppose you add a new validation method to `src/lexibrary/config/schema.py`. After editing the source file:

1. Run `lexi design update src/lexibrary/config/schema.py` to regenerate the design file via the archivist pipeline. The pipeline reads the source, extracts the interface, and writes an updated design file at `.lexibrary/src/lexibrary/config/schema.py.md`.

2. Run `lexi design comment src/lexibrary/config/schema.py --body "Added validate_token_budget() to enforce ceiling on per-file token allocation. This prevents runaway costs when the sweep encounters unexpectedly large files."` to capture the rationale for the new method.

That's it. The archivist handles structure extraction, and the comment preserves your intent for future agents.

## Summary Checklist

After editing a source file:

1. Run `lexi design update <file>` to regenerate the design file
2. Run `lexi design comment <file> --body "..."` if the change is non-trivial
3. If `lexi design update` fails, write an IWH signal noting the failure
4. Do not manually edit design files, frontmatter, or staleness metadata

## See Also

- [Lookup Workflow](lookup-workflow.md) -- what to do before editing a file
- [Prohibited Commands](prohibited-commands.md) -- why you should not run `lexictl update` yourself
- [Design File Generation (User Docs)](../user/design-file-generation.md) -- how `lexictl update` generates design files and how ChangeLevel classification works
