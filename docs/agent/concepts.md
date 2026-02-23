# Using the Concepts Wiki

The concepts wiki is a collection of project-specific vocabulary, architectural patterns, and domain terms stored in `.lexibrary/concepts/`. Each concept is a markdown file with YAML frontmatter that defines a canonical term the project uses.

Concepts prevent you from reinventing conventions that already exist and ensure you use the right terminology when communicating about the codebase.

## Searching Concepts

Before making architectural decisions, search for existing concepts:

```bash
lexi concepts validation
```

This searches concept titles, aliases, and tags for matches. The output is a table:

```
                  Concepts matching 'validation'
Name                Status    Tags              Summary
pydantic-validation active    config, schema    Pydantic 2 BaseModel validation...
hash-freshness      active    validation, hash  SHA-256 hash comparison for sta...
```

To list all concepts without filtering:

```bash
lexi concepts
```

## When to Search

Search concepts in these situations:

- **Before introducing a new pattern.** Check whether the project already has a convention for what you are about to do. For example, before writing a custom config validator, search `lexi concepts config` to see if there is an existing pattern.
- **Before naming something.** Check whether the project has canonical terminology. If a concept called `design-file` exists, use that term rather than inventing "blueprint" or "spec file."
- **When you encounter unfamiliar terminology.** If source code or documentation uses a term you do not recognise, search for it -- there may be a concept explaining what it means.

## Creating a Concept

When you discover a pattern, convention, or term that deserves a canonical definition, create a concept:

```bash
lexi concept new change-detection
```

This creates `.lexibrary/concepts/change-detection.md` with a template:

```yaml
---
title: change-detection
aliases: []
tags: []
status: draft
---

<!-- Describe the concept here -->
```

You can add tags at creation time:

```bash
lexi concept new pydantic-validation --tag config --tag schema
```

### When to Create a Concept

Create a concept when:

- **Three or more files share a common pattern.** If you see the same approach used across multiple files, document it as a concept so future agents follow the same pattern.
- **A domain term needs a canonical definition.** If the project uses specific terminology (e.g., "ChangeLevel", "design file", "mirror tree"), define it so all agents use the same language.
- **An architectural decision should be recorded.** If you make a decision about how something should work (e.g., "all config validation uses Pydantic 2 validators, not manual checks"), record it as a concept.

### What to Write in a Concept

After creating the concept file, fill in:

1. **A clear definition.** What does this concept mean in the context of this project?
2. **Why it exists.** What problem does it solve or what convention does it establish?
3. **How to apply it.** When an agent encounters a situation where this concept applies, what should they do?
4. **Examples.** Show concrete code examples or file references where the concept is in use.

Update the frontmatter:

- **aliases** -- alternative names for the concept (e.g., `["sha256-check", "hash-check"]`)
- **tags** -- classification tags for searchability (e.g., `["config", "validation"]`)
- **status** -- set to `draft` initially; the operator can promote to `active` or mark as `deprecated`

## Linking Concepts to Files

After creating a concept, link it to the source files where it is implemented or referenced:

```bash
lexi concept link change-detection src/lexibrary/archivist/change_checker.py
lexi concept link change-detection src/lexibrary/crawler/change_detector.py
```

This adds a `[[change-detection]]` wikilink to the design file's frontmatter. When another agent runs `lexi lookup` on that file, the concept will appear as a cross-reference, leading them to the concept's documentation.

Link a concept to every file where it is meaningfully applied -- not just the primary implementation, but also files that follow the pattern or depend on the concept.

## Concept Lifecycle

Concepts have three statuses:

| Status | Meaning |
|--------|---------|
| `draft` | Newly created, may need review or refinement |
| `active` | Reviewed and accepted as a project convention |
| `deprecated` | No longer the recommended approach; may include a pointer to the replacement |

You can create concepts with `draft` status. The operator decides when to promote them to `active` or mark them as `deprecated`.

## Example Workflow

Suppose you notice that three different modules all validate file paths the same way -- resolving them, checking they exist, and verifying they are within `scope_root`. This is a pattern worth documenting:

```bash
# Check if a concept already exists
lexi concepts "path validation"

# No results -- create one
lexi concept new path-validation --tag validation --tag paths

# Edit the concept file to describe the pattern
# (edit .lexibrary/concepts/path-validation.md)

# Link it to the files that implement the pattern
lexi concept link path-validation src/lexibrary/cli/lexi_app.py
lexi concept link path-validation src/lexibrary/config/loader.py
lexi concept link path-validation src/lexibrary/artifacts/writer.py
```

## See Also

- [lexi Reference](lexi-reference.md) -- full reference for `concepts`, `concept new`, and `concept link`
- [Search](search.md) -- unified search that includes concepts alongside design files and Stack posts
- [Concepts Wiki (User Docs)](../user/concepts-wiki.md) -- operator guide to concepts: lifecycle, validation, and concept index internals
