# Concepts Wiki

This guide explains what concepts are, how they are created and managed, and how they integrate with the rest of Lexibrary.

## What Are Concepts?

Concepts are project-specific vocabulary entries that capture architectural patterns, domain terms, and recurring themes. They live as Markdown files in `.lexibrary/concepts/` and serve as a shared knowledge base for both operators and AI agents.

Examples of good concepts:

- **Domain terms** -- "authentication-flow", "order-lifecycle", "tenant-isolation"
- **Architectural patterns** -- "repository-pattern", "middleware-chain", "event-sourcing"
- **Project conventions** -- "error-handling-policy", "api-versioning-strategy"
- **Technology decisions** -- "why-pydantic", "sqlite-vs-postgres"

Concepts are referenced from design files and Stack posts using wikilink syntax (`[[concept-name]]`), creating a navigable knowledge graph.

## Creating Concepts

Concepts are created using the `lexi` CLI (the agent-facing tool):

```bash
lexi concept new authentication-flow --tag auth --tag security
```

This creates a new concept file at `.lexibrary/concepts/authentication-flow.md` with scaffolded frontmatter and an empty body.

### Concept File Anatomy

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

## Concept Lifecycle

Concepts progress through three statuses:

### draft

A newly created concept that is being developed. It may be incomplete or not yet reviewed. Agents can reference draft concepts, but they are not considered authoritative.

### active

A concept that is complete, reviewed, and actively used in the project. Active concepts are the primary knowledge base for agents.

### deprecated

A concept that is no longer relevant or has been replaced. When deprecating a concept, set `superseded_by` to the name of the replacement concept:

```yaml
status: deprecated
superseded_by: new-auth-pattern
```

The `deprecated_concept_usage` validation check will flag any design files or Stack posts that still reference deprecated concepts, including a suggestion to use the replacement.

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

To associate a concept with specific source files:

```bash
lexi concept link authentication-flow src/auth/service.py
```

This adds the file to the concept's `linked_files` list and creates a `concept_file_ref` link in the link graph index.

## Searching Concepts

To search the concepts wiki:

```bash
# Search by topic
lexi concepts auth

# List all concepts
lexi concepts
```

This returns matching concepts with their titles, statuses, and summaries.

## How Agents Use Concepts

When an agent runs `lexi lookup <file>`, the output includes wikilinks from the design file. The agent can then look up referenced concepts to understand the architectural context before making changes.

When an agent runs `lexi concepts <topic>` before an architectural decision, it can discover existing patterns and conventions documented as concepts.

Agents are encouraged to create new concepts when:

- A recurring pattern appears in 3 or more files.
- A domain term needs a project-specific definition.
- An architectural decision should be recorded for future reference.

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

Run `lexictl validate` to check all of these, or target a specific check:

```bash
lexictl validate --check concept_frontmatter
```

## Related Documentation

- [How It Works](how-it-works.md) -- Overview of the artifact lifecycle
- [Library Structure](library-structure.md) -- Where concept files live in `.lexibrary/`
- [Link Graph](link-graph.md) -- How concepts are indexed in the SQLite database
- [Validation](validation.md) -- All 13 checks, including concept-related ones
- [Agent Concepts Guide](../agent/concepts.md) -- How agents use the concepts wiki
