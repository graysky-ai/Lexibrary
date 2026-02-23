# Stack Q&A

This guide explains what Stack posts are, how they work, and how operators and agents use the Stack Q&A knowledge base.

## What Are Stack Posts?

Stack posts are structured problem/solution entries that capture debugging knowledge, design decisions, and solutions to non-trivial issues. They live as Markdown files in `.lexibrary/stack/` and form a searchable Q&A knowledge base.

Think of Stack as a project-specific Stack Overflow: when an agent solves a tricky bug or discovers a non-obvious pattern, it records the problem and solution as a Stack post so future agents (and humans) can find it.

## Creating Posts

Posts are created using the `lexi` CLI:

```bash
lexi stack post --title "Auth tokens expire during long-running requests" --tag auth --tag timeout
```

This creates a new Stack post file at `.lexibrary/stack/ST-001-auth-tokens-expire-during-long-running-requests.md` with scaffolded frontmatter and sections for the problem description and evidence.

### Post Naming Convention

Post files follow the pattern `ST-{NNN}-{slug}.md`, where `{NNN}` is an auto-incrementing number and `{slug}` is derived from the title. The `ST-{NNN}` portion serves as the post ID (e.g., `ST-001`, `ST-042`).

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

A Stack post is a Markdown file with YAML frontmatter and structured body sections:

```markdown
---
id: ST-001
title: Auth tokens expire during long-running requests
tags:
  - auth
  - timeout
status: open
created: 2024-06-15
author: agent
votes: 0
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

## Evidence

- Stack trace shows TokenExpiredError at src/auth/middleware.py:42
- Only affects requests to /api/reports/generate (p95 latency: 90s)
- Token TTL is configured at 300s but effective window is shorter due to clock skew

## Answer 1

**Date:** 2024-06-15 | **Author:** agent | **Votes:** 1 | **Accepted:** true

Implemented a token refresh check at the middleware level that proactively
refreshes tokens when they are within 120 seconds of expiration...
```

### Frontmatter Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | Yes | Unique identifier (e.g., `ST-001`). Auto-generated. |
| `title` | string | Yes | Descriptive title of the problem. |
| `tags` | list of strings | Yes | At least one tag is required. Used for search and filtering. |
| `status` | string | Yes | One of `open`, `resolved`, `outdated`, or `duplicate`. |
| `created` | date | Yes | Creation date (YYYY-MM-DD format). |
| `author` | string | Yes | Who created the post (e.g., `agent`, a username). |
| `bead` | string | No | Link to a bead (work tracking item). |
| `votes` | integer | Yes | Net vote count for the question. Default: 0. |
| `duplicate_of` | string | No | ID of the original post if this is a duplicate. |
| `refs.concepts` | list of strings | No | Referenced concept names. |
| `refs.files` | list of strings | No | Referenced source file paths (project-relative). |
| `refs.designs` | list of strings | No | Referenced design file paths (project-relative). |

## Answer Workflow

### Adding an Answer

```bash
lexi stack answer ST-001 --body "The fix is to add a token refresh check..."
```

Answers are appended to the post file as numbered sections. Each answer includes:

- **number** -- Sequential answer number (auto-incremented).
- **date** -- When the answer was posted.
- **author** -- Who posted the answer.
- **votes** -- Net vote count for this answer.
- **accepted** -- Whether this answer has been accepted as the solution.
- **body** -- The answer text (Markdown).
- **comments** -- Optional follow-up comments.

### Voting

Vote on posts or answers to surface the most helpful content:

```bash
# Upvote a post
lexi stack vote ST-001 up

# Downvote a post
lexi stack vote ST-001 down

# Vote on a specific answer
lexi stack vote ST-001 up --answer 2
```

### Accepting an Answer

Mark an answer as the accepted solution:

```bash
lexi stack accept ST-001 --answer 1
```

This sets `accepted: true` on the specified answer and changes the post status to `resolved`.

## Status Lifecycle

Stack posts progress through four statuses:

| Status | Meaning |
|---|---|
| `open` | Problem is described, no accepted solution yet |
| `resolved` | An answer has been accepted as the solution |
| `outdated` | The problem or solution is no longer relevant (e.g., the code it describes has been rewritten) |
| `duplicate` | This post duplicates another; see `duplicate_of` for the original |

## Searching and Filtering

### Text Search

```bash
lexi stack search "token expiration"
```

Searches post titles, problem descriptions, and answer bodies using the link graph FTS5 index (when available) or file scanning as a fallback.

### Filtering by Tag

```bash
lexi stack search --tag auth
```

### Filtering by Status

```bash
lexi stack list --status open
lexi stack list --status resolved
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

Displays the full post including all answers and metadata.

## How Agents Use the Stack

Agents are encouraged to:

1. **Search before debugging** -- Run `lexi stack search <query>` before spending time debugging a problem. A previous agent may have already solved it.
2. **Post after solving** -- After resolving a non-trivial bug, create a Stack post documenting the problem, evidence, and solution.
3. **Answer existing posts** -- If an agent discovers a solution to an open Stack post, add an answer using `lexi stack answer`.
4. **Vote to signal quality** -- Upvote helpful answers to surface them for future agents.

## Stack in the Link Graph

During `lexictl update`, Stack posts are indexed in the link graph with:

- **Artifact entry** -- Kind `stack`, with title and status.
- **`stack_file_ref` links** -- From the post to referenced source files (`refs.files`).
- **`stack_concept_ref` links** -- From the post to referenced concepts (`refs.concepts`).
- **Tags** -- Searchable via `lexi search --tag`.
- **FTS row** -- Problem text and answer bodies are indexed for full-text search.

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
- [Agent Stack Guide](../agent/stack.md) -- How agents use Stack Q&A
