# Stack Knowledge Base

This guide explains what Stack posts are, how they work, and how operators and agents use the Stack to capture and retrieve debugging knowledge.

## What Are Stack Posts?

Stack posts are structured issue records that capture debugging knowledge, design decisions, and solutions to non-trivial problems. They live as Markdown files in `.lexibrary/stack/` and form a searchable knowledge base.

Think of the Stack as a project-specific issue tracker: when an agent encounters a tricky bug or discovers a non-obvious pattern, it records the issue -- what went wrong, what was tried, and the eventual fix -- as a Stack post so future agents (and humans) can find it.

## Creating Posts

Posts are created using the `lexi` CLI:

```bash
lexi stack post --title "Auth tokens expire during long-running requests" --tag auth --tag timeout
```

This creates a new Stack post file at `.lexibrary/stack/ST-001-auth-tokens-expire-during-long-running-requests.md` with scaffolded frontmatter and four body sections ready to be filled in.

### Post Naming Convention

Post files follow the pattern `ST-{NNN}-{slug}.md`, where `{NNN}` is an auto-incrementing number and `{slug}` is derived from the title. The `ST-{NNN}` portion serves as the post ID (e.g., `ST-001`, `ST-042`).

### One-Shot Post Creation

Agents can create a fully populated post in a single command using content flags:

```bash
lexi stack post --title "Config loader silently ignores unknown keys" --tag config --tag bug \
  --problem "Unknown keys in config.yaml are silently dropped. Expected: validation error." \
  --context "Discovered while adding a new config field; typo in key name produced no error." \
  --evidence "Pydantic model uses extra='ignore' by default" \
  --evidence "Adding unknown_key: true to config.yaml triggers no warning" \
  --attempts "Tried setting extra='forbid' but it broke backward compatibility"
```

When any content flag (`--problem`, `--context`, `--evidence`, `--attempts`) is provided, only sections with content are written. When no content flags are provided, the post is scaffolded with all four sections containing HTML comment placeholders for manual editing.

### One-Shot with Inline Finding

An agent can also attach a finding and optionally resolve the post in one command:

```bash
lexi stack post --title "Config loader silently ignores unknown keys" --tag config --tag bug \
  --problem "Unknown keys in config.yaml are silently dropped." \
  --finding "Set extra='forbid' on the Pydantic model and add a migration note." \
  --resolve --resolution-type fix
```

This creates the post, appends finding F1, marks it as accepted, sets the post status to `resolved`, and records the resolution type.

### Additional Options

```bash
# Link to relevant files
lexi stack post --title "Race condition in order processing" --tag concurrency --file src/orders/processor.py

# Link to a concept
lexi stack post --title "Pattern for retry logic" --tag resilience --concept retry-pattern

# Link to a bead (work item)
lexi stack post --title "Migration script fails on empty tables" --tag migration --bead lexibrary-42.3
```

## Post Anatomy

A Stack post is a Markdown file with YAML frontmatter and structured body sections.

### Four-Section Body Structure

Every post body can contain up to four sections in canonical order:

1. **Problem** (`## Problem`) -- What went wrong. Always present.
2. **Context** (`### Context`) -- What the agent was doing when the issue occurred. Prerequisites, environment state, and circumstances.
3. **Evidence** (`### Evidence`) -- Supporting data: error messages, stack traces, reproduction steps.
4. **Attempts** (`### Attempts`) -- Known dead ends. Approaches that were tried and why they failed. This is one of the most valuable sections -- it prevents future agents from repeating the same unsuccessful approaches.

All sections except Problem are conditional. If a section has no content, it is omitted from the file entirely.

### Full Post Example

```markdown
---
id: ST-001
title: Auth tokens expire during long-running requests
tags:
  - auth
  - timeout
status: resolved
created: 2024-06-15
author: agent
votes: 0
resolution_type: fix
refs:
  concepts:
    - authentication-flow
  files:
    - src/auth/token_manager.py
  designs:
    - .lexibrary/src/auth/token_manager.py.md
---

## Problem

Long-running API requests (>60 seconds) fail with 401 Unauthorized because the
JWT access token expires mid-request. The token refresh logic only runs at the
start of request processing.

### Context

Investigating report generation endpoint performance. The /api/reports/generate
endpoint has p95 latency of 90 seconds, well beyond the 300s token TTL when
clock skew is factored in.

### Evidence

- Stack trace shows TokenExpiredError at src/auth/middleware.py:42
- Only affects requests to /api/reports/generate (p95 latency: 90s)
- Token TTL is configured at 300s but effective window is shorter due to clock skew

### Attempts

- Increased token TTL to 600s -- worked but security team rejected it
- Added retry-on-401 logic -- caused infinite retry loop when token was truly invalid

## Findings

### F1

**Date:** 2024-06-15 | **Author:** agent | **Votes:** 1 | **Accepted:** true

Implemented a token refresh check at the middleware level that proactively
refreshes tokens when they are within 120 seconds of expiration. This runs
on every request, not just at the start of processing.
```

### Frontmatter Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | Yes | Unique identifier (e.g., `ST-001`). Auto-generated. |
| `title` | string | Yes | Descriptive title of the issue. |
| `tags` | list of strings | Yes | At least one tag is required. Used for search and filtering. |
| `status` | string | Yes | One of `open`, `resolved`, `outdated`, or `duplicate`. |
| `created` | date | Yes | Creation date (YYYY-MM-DD format). |
| `author` | string | Yes | Who created the post (e.g., `agent`, a username). |
| `bead` | string | No | Link to a bead (work tracking item). |
| `votes` | integer | Yes | Net vote count for the post. Default: 0. |
| `duplicate_of` | string | No | ID of the original post if this is a duplicate. |
| `resolution_type` | string | No | How the issue was resolved: `fix`, `workaround`, `wontfix`, `cannot_reproduce`, or `by_design`. Only present on resolved posts. |
| `refs.concepts` | list of strings | No | Referenced concept names. |
| `refs.files` | list of strings | No | Referenced source file paths (project-relative). |
| `refs.designs` | list of strings | No | Referenced design file paths (project-relative). |

### Resolution Types

When a finding is accepted (marking a post as resolved), an optional `resolution_type` classifies how the issue was resolved:

| Resolution Type | Meaning |
|---|---|
| `fix` | The root cause was identified and corrected |
| `workaround` | A workaround was applied; the root cause remains |
| `wontfix` | The issue is acknowledged but will not be addressed |
| `cannot_reproduce` | The issue could not be reproduced |
| `by_design` | The observed behavior is intentional |

## Finding Workflow

### Adding a Finding

```bash
lexi stack finding ST-001 --body "The fix is to add a token refresh check..."
```

Findings are appended to the post file as numbered sections. Each finding includes:

- **number** -- Sequential finding number (auto-incremented).
- **date** -- When the finding was posted.
- **author** -- Who posted the finding.
- **votes** -- Net vote count for this finding.
- **accepted** -- Whether this finding has been accepted as the solution.
- **body** -- The finding text (Markdown).
- **comments** -- Optional follow-up comments.

### Voting

Vote on posts or findings to surface the most helpful content:

```bash
# Upvote a post
lexi stack vote ST-001 up

# Downvote a post
lexi stack vote ST-001 down

# Vote on a specific finding
lexi stack vote ST-001 up --finding 2
```

### Accepting a Finding

Mark a finding as the accepted solution:

```bash
lexi stack accept ST-001 --finding 1
```

This sets `accepted: true` on the specified finding and changes the post status to `resolved`.

You can also specify a resolution type:

```bash
lexi stack accept ST-001 --finding 1 --resolution-type fix
```

## Status Lifecycle

Stack posts progress through four statuses:

| Status | Meaning |
|---|---|
| `open` | Issue is described, no accepted finding yet |
| `resolved` | A finding has been accepted as the solution |
| `outdated` | The issue or solution is no longer relevant (e.g., the code it describes has been rewritten) |
| `duplicate` | This post duplicates another; see `duplicate_of` for the original |

## Searching and Filtering

### Text Search

```bash
lexi stack search "token expiration"
```

Searches post titles, problem descriptions, context, attempts, and finding bodies using the link graph FTS5 index (when available) or file scanning as a fallback.

### Filtering by Tag

```bash
lexi stack search --tag auth
```

### Filtering by Status

```bash
lexi stack list --status open
lexi stack list --status resolved
```

### Filtering by Resolution Type

```bash
lexi stack search --resolution-type fix
lexi stack search --resolution-type workaround
```

### Listing All Posts

```bash
lexi stack list
```

Shows all posts with their IDs, titles, statuses, and tags.

### Viewing a Specific Post

```bash
lexi stack view ST-001
```

Displays the full post including all findings, resolution type, and metadata.

## How Agents Use the Stack

Agents are encouraged to:

1. **Search before debugging** -- Run `lexi stack search <query>` before spending time debugging an issue. A previous agent may have already solved it.
2. **Document issues after solving** -- After resolving a non-trivial bug, create a Stack post documenting the problem, context, evidence, attempts, and solution.
3. **Record dead ends in Attempts** -- When something does not work, document it in the Attempts section so future agents do not waste time repeating the same approaches.
4. **Add findings to existing posts** -- If an agent discovers a solution to an open Stack post, add a finding using `lexi stack finding`.
5. **Vote to signal quality** -- Upvote helpful findings to surface them for future agents.
6. **Use resolution types** -- When accepting a finding, classify the resolution (`fix`, `workaround`, etc.) to help future agents quickly assess the nature of the solution.

## Stack in the Link Graph

During `lexictl update`, Stack posts are indexed in the link graph with:

- **Artifact entry** -- Kind `stack`, with title and status.
- **`stack_file_ref` links** -- From the post to referenced source files (`refs.files`).
- **`stack_concept_ref` links** -- From the post to referenced concepts (`refs.concepts`).
- **Tags** -- Searchable via `lexi search --tag`.
- **FTS row** -- Problem text, context, attempts, and finding bodies are indexed for full-text search.

## Validation

The following validation checks relate to Stack posts:

| Check | Severity | What It Does |
|---|---|---|
| `wikilink_resolution` | error | Verifies wikilinks in post bodies and `refs.concepts` resolve |
| `file_existence` | error | Verifies `refs.files` and `refs.designs` entries exist on disk |
| `stack_staleness` | info | Flags posts whose referenced files have stale design files |

## Related Documentation

- [How It Works](how-it-works.md) -- Overview of the artifact lifecycle
- [Library Structure](library-structure.md) -- Where Stack posts live in `.lexibrary/`
- [Concepts Wiki](concepts-wiki.md) -- Concepts referenced by Stack posts
- [Link Graph](link-graph.md) -- How Stack posts are indexed
- [Validation](validation.md) -- Checks that affect Stack posts
- [Agent Stack Guide](../agent/stack.md) -- How agents use the Stack knowledge base
