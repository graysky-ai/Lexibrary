# Concepts Wiki

Concepts are project-specific vocabulary entries stored in `.lexibrary/concepts/`. Each concept is a Markdown file with YAML frontmatter that defines a canonical term, architectural pattern, or domain convention used by the project.

Concepts serve as a shared knowledge base for both operators and AI agents. They prevent reinventing conventions that already exist and ensure consistent terminology when communicating about the codebase.

## What Makes a Good Concept

Examples of concepts worth documenting:

- **Domain terms** -- "authentication-flow", "order-lifecycle", "tenant-isolation"
- **Architectural patterns** -- "repository-pattern", "middleware-chain", "event-sourcing"
- **Project conventions** -- "error-handling-policy", "api-versioning-strategy"
- **Technology decisions** -- "why-pydantic", "sqlite-vs-postgres"

Concepts are referenced from design files and Stack posts using wikilink syntax (`[[concept-name]]`), creating a navigable knowledge graph.

## Creating Concepts

Create a concept using the `lexi concept new` command:

```bash
lexi concept new authentication-flow --tag auth --tag security
```

This creates `.lexibrary/concepts/authentication-flow.md` with scaffolded frontmatter and an empty body.

### When to Create a Concept

Create a concept when:

- **Three or more files share a common pattern.** If the same approach appears across multiple files, document it so the pattern is followed consistently.
- **A domain term needs a canonical definition.** If the project uses specific terminology (e.g., "ChangeLevel", "design file", "mirror tree"), define it so everyone uses the same language.
- **An architectural decision should be recorded.** If a decision about how something should work has been made (e.g., "all config validation uses Pydantic 2 validators, not manual checks"), record it.

### What to Write in a Concept

After creating the concept file, fill in:

1. **A clear definition.** What does this concept mean in the context of this project?
2. **Why it exists.** What problem does it solve or what convention does it establish?
3. **How to apply it.** When this concept is encountered, what should be done?
4. **Examples.** Concrete code examples or file references where the concept is in use.

## File Anatomy

A concept file is a Markdown document with YAML frontmatter:

```markdown
---
title: authentication-flow
aliases:
  - auth-flow
  - login-flow
tags:
  - auth
  - security
status: draft
---

## Summary

Brief description of the authentication flow pattern used in this project.

## Details

The authentication flow uses JWT tokens issued by the auth service...

## Decision Log

- 2024-01-15: Chose JWT over session cookies for stateless scaling.
```

### Frontmatter Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `title` | string | Yes | The canonical name of the concept. Used as the primary wikilink target. |
| `aliases` | list of strings | Yes | Alternative names that also resolve to this concept. Case-insensitive matching. |
| `tags` | list of strings | Yes | Categorization tags for search and filtering. |
| `status` | string | Yes | One of `draft`, `active`, or `deprecated`. |
| `superseded_by` | string | No | When status is `deprecated`, the name of the replacement concept. |

### Body Sections

The body is free-form Markdown. Common sections include:

- **Summary** -- A concise description (1-3 sentences).
- **Details** -- Full explanation of the concept, its usage, and rationale.
- **Related Concepts** -- Cross-references to other concepts using `[[wikilink]]` syntax.
- **Linked Files** -- Source files where this concept is implemented.
- **Decision Log** -- A chronological record of decisions related to this concept.

## Wikilink Syntax

Concepts are referenced using double-bracket wikilink syntax:

```markdown
This module implements the [[authentication-flow]] pattern.
```

Wikilinks resolve to concepts by matching against:

1. The concept's `title` field (exact match, case-insensitive).
2. Any of the concept's `aliases` (exact match, case-insensitive).

The `WikilinkResolver` handles resolution and provides fuzzy-match suggestions when a wikilink does not resolve.

### Where Wikilinks Are Used

- **Design files** -- In the `wikilinks` field and body text. LLM-generated design files include wikilinks to relevant concepts from the project's concept index.
- **Stack posts** -- In the body text and `refs.concepts` frontmatter field.
- **Concept files** -- Cross-referencing other concepts in the body text.
- **Convention text** -- In `.aindex` local conventions.

## Linking Concepts to Files

After creating a concept, link it to the source files where it is implemented or referenced:

```bash
lexi concept link authentication-flow src/auth/service.py
```

This adds the file to the concept's linked files and creates a `concept_file_ref` link in the link graph index. A `[[authentication-flow]]` wikilink appears in the design file's frontmatter, so anyone looking up that file sees the concept cross-reference.

Link a concept to every file where it is meaningfully applied -- not just the primary implementation, but also files that follow the pattern or depend on the concept.

## Searching Concepts

Search for existing concepts before making architectural decisions:

```bash
# Search by topic
lexi search --type concept "validation"

# Search across all artifact types (concepts included)
lexi search "change detection"
```

To view a specific concept:

```bash
lexi view CN-001
```

## Lifecycle

Concepts progress through three statuses:

| Status | Meaning |
|--------|---------|
| `draft` | Newly created, may need review or refinement. Not yet considered authoritative. |
| `active` | Reviewed and accepted as a project convention. The primary knowledge base for the project. |
| `deprecated` | No longer the recommended approach. May include a pointer to the replacement via `superseded_by`. |

### Promoting and Deprecating

```bash
# Deprecate a concept (optionally with replacement)
lexi concept deprecate old-auth --superseded-by "new-auth-pattern"
```

When a concept is deprecated with `superseded_by`, the `deprecated_concept_usage` validation check flags any design files or Stack posts that still reference it, including a suggestion to use the replacement.

### Adding Comments

```bash
lexi concept comment scope-root --body "Clarified: scope_root is always relative to project root."
```

## Concept Index

Internally, Lexibrary maintains a `ConceptIndex` that loads all concept files from `.lexibrary/concepts/` and provides:

- Name lookup (by title, case-insensitive).
- Alias resolution (any alias maps to its parent concept).
- Listing all concept names for wikilink guidance during design file generation.

The concept index is rebuilt every time concepts are accessed. It is also populated into the link graph index during `lexictl update`, where concept artifacts, aliases, wikilinks, and tags are all indexed for fast querying.

## Validation

The following validation checks relate to concepts:

| Check | Severity | What It Does |
|---|---|---|
| `concept_frontmatter` | error | Verifies all concept files have valid frontmatter with mandatory fields |
| `wikilink_resolution` | error | Verifies all `[[wikilink]]` references resolve to existing concepts |
| `orphan_concepts` | warning | Identifies concepts with zero inbound references |
| `deprecated_concept_usage` | warning | Finds references to deprecated concepts |
| `token_budgets` | warning | Checks concept files against the `concept_file_tokens` budget |

## Example Workflow

Suppose three different modules all validate file paths the same way -- resolving them, checking they exist, and verifying they are within `scope_root`. This pattern is worth documenting:

```bash
# Check if a concept already exists
lexi search --type concept "path validation"

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

- [CLI Reference](cli-reference.md) -- Full reference for `lexi concept` commands
- [Search](search.md) -- Unified search that includes concepts alongside all artifact types
- [Stack](stack.md) -- Stack posts that reference concepts
- [Validation](validation.md) -- All 13 checks, including concept-related ones
- [Library Structure](library-structure.md) -- Where concept files live in `.lexibrary/`
- [Link Graph](link-graph.md) -- How concepts are indexed in the SQLite database
