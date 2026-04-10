# Stack Knowledge Base

The Stack is a structured knowledge base of issues and solutions stored in `.lexibrary/stack/`. Each Stack post documents a specific issue -- what went wrong, what was tried, and the solution that worked. Posts persist across sessions so the same issue never has to be solved twice.

Think of the Stack as a project-specific issue tracker: when a tricky bug is encountered or a non-obvious pattern is discovered, the issue is recorded as a Stack post so future agents and humans can find it.

## Creating Posts

Posts are created using `lexi stack post`:

```bash
lexi stack post --title "Auth tokens expire during long-running requests" --tag auth --tag timeout
```

This creates a new Stack post file at `.lexibrary/stack/ST-001-auth-tokens-expire-during-long-running-requests.md` with scaffolded frontmatter and four body sections ready to be filled in.

### Post Naming Convention

Post files follow the pattern `ST-{NNN}-{slug}.md`, where `{NNN}` is an auto-incrementing number and `{slug}` is derived from the title. The `ST-{NNN}` portion serves as the post ID (e.g., `ST-001`, `ST-042`).

### Scaffold Mode

When no content flags are provided, the post is scaffolded with all four body sections containing HTML comment placeholders for manual editing:

```bash
lexi stack post --title "Config loader silently ignores unknown keys" --tag config --tag bug
```

### One-Shot Mode

When content flags are provided, a fully populated post is created in a single command:

```bash
lexi stack post --title "Race condition in sweep watch mode" --tag sweep --tag concurrency \
  --problem "Concurrent sweep iterations cause duplicate index entries." \
  --context "Running lexictl sweep --watch with short interval." \
  --evidence "Duplicate ST-* entries in link graph after concurrent sweep" \
  --evidence "Race window is ~200ms between file scan and index write" \
  --attempts "Tried file-level locking but it caused deadlocks" \
  --attempts "Tried debouncing sweep trigger but window was too narrow"
```

### One-Shot with Inline Finding and Resolution

A post can be created, resolved, and classified in one step:

```bash
lexi stack post --title "Race condition in sweep watch mode" --tag sweep --tag concurrency \
  --problem "Concurrent sweep iterations cause duplicate index entries." \
  --finding "Added a sweep-in-progress flag that prevents overlapping sweep iterations." \
  --resolve --resolution-type fix
```

This creates the post, appends finding F1, marks it accepted, sets status to `resolved`, and records the resolution type.

Shortcut flags `--fix` and `--workaround` combine `--finding`, `--resolve`, and `--resolution-type`:

```bash
lexi stack post --title "Missing null check in parser" --tag parser \
  --problem "Parser crashes on empty input." \
  --fix "Added null check before parsing."
```

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
2. **Context** (`### Context`) -- What was happening when the issue occurred. Prerequisites, environment state, and circumstances.
3. **Evidence** (`### Evidence`) -- Supporting data: error messages, stack traces, reproduction steps.
4. **Attempts** (`### Attempts`) -- Known dead ends. Approaches that were tried and why they failed. This is one of the most valuable sections -- it prevents repeating the same unsuccessful approaches.

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
| `status` | string | Yes | One of `open`, `resolved`, `outdated`, `stale`, or `duplicate`. |
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

When a finding is accepted, an optional `resolution_type` classifies the resolution:

| Resolution Type | Meaning |
|---|---|
| `fix` | The root cause was identified and corrected |
| `workaround` | A workaround was applied; the root cause remains |
| `wontfix` | The issue is acknowledged but will not be addressed |
| `cannot_reproduce` | The issue could not be reproduced |
| `by_design` | The observed behavior is intentional |

## Searching

Search for existing Stack posts before spending time debugging:

```bash
# Text search across all artifact types
lexi search "config loader"

# Search only Stack posts
lexi search --type stack "timeout"

# Filter by tag
lexi search --type stack --tag sweep

# Combine filters
lexi search --type stack "timeout" --tag llm --status open

# Find posts linked to a concept
lexi search --type stack --concept change-detection

# Find workarounds
lexi search --type stack --resolution-type workaround

# Include stale posts in results
lexi search --type stack --include-stale "timeout"
```

To view the full content of a post:

```bash
lexi stack view ST-001
```

This shows the problem description, context, evidence, attempts, all findings with votes, resolution type, and which finding was accepted.

## Findings, Voting, and Resolving

### Adding Findings

When a solution to an open post is discovered, add a finding:

```bash
lexi stack finding ST-005 --body "The YAML parse error occurs because PyYAML requires explicit list indentation."
```

Findings are appended as numbered sections (F1, F2, etc.) with date, author, and vote tracking.

### Voting

Vote on posts or findings to surface the most helpful content:

```bash
# Upvote a post
lexi stack vote ST-001 up

# Upvote a specific finding
lexi stack vote ST-001 up --finding 2

# Downvote with required comment
lexi stack vote ST-003 down --comment "This solution introduces a memory leak"
```

### Accepting Findings

Mark a finding as the accepted solution:

```bash
lexi stack accept ST-001 --finding 2
lexi stack accept ST-001 --finding 2 --resolution-type fix
```

This sets `accepted: true` on the specified finding and changes the post status to `resolved`.

### Adding Comments

```bash
lexi stack comment ST-001 --body "This may also affect the sweep module."
```

## Writing Good Attempts

The **Attempts** section is one of the most valuable parts of a Stack post. It saves future readers from repeating approaches that do not work. When documenting attempts:

- Describe what was tried and why it seemed reasonable.
- Explain why it did not work or what went wrong.
- Each attempt should be a separate item.

```bash
lexi stack post --title "FTS search returns stale results" --tag search --tag fts \
  --problem "Full-text search returns results for deleted Stack posts." \
  --attempts "Tried rebuilding FTS index on every query -- too slow (>2s per search)" \
  --attempts "Tried DELETE trigger on stack table -- FTS5 does not support triggers" \
  --finding "Added a post-deletion step that removes the FTS row by rowid." \
  --resolve --resolution-type fix
```

## Lifecycle

Stack posts progress through five statuses:

| Status | Meaning |
|---|---|
| `open` | Issue is described, no accepted finding yet |
| `resolved` | A finding has been accepted as the solution |
| `stale` | A resolved post flagged for re-evaluation (the solution may no longer apply) |
| `outdated` | The issue or solution is no longer relevant (e.g., the code has been rewritten) |
| `duplicate` | This post duplicates another; see `duplicate_of` for the original |

### Status Transitions

```bash
# Mark a post as outdated
lexi stack mark-outdated ST-003

# Mark a post as duplicate
lexi stack duplicate ST-003 --of ST-001

# Flag a resolved post as stale for re-evaluation
lexi stack stale ST-005

# Reverse staleness on a post
lexi stack unstale ST-005
```

### When to Create a Post

Create a Stack post when:

- **A bug took significant effort to solve.** If it took more than a few minutes to figure out, it is worth documenting.
- **The solution was non-obvious.** If the fix required understanding something subtle about the codebase, document it.
- **The issue might recur.** If the bug was caused by a pattern that could easily be repeated, create a post as a warning.
- **A workaround was found.** Document both the problem and the workaround.

Do not create a post for trivial typo fixes, obvious errors, or issues that are immediately clear from reading the error message.

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

## See Also

- [CLI Reference](cli-reference.md) -- Full reference for all `lexi stack` commands
- [Search](search.md) -- Unified search that includes Stack posts alongside all artifact types
- [Concepts](concepts.md) -- Concepts referenced by Stack posts
- [Library Structure](library-structure.md) -- Where Stack posts live in `.lexibrary/`
- [Link Graph](link-graph.md) -- How Stack posts are indexed
- [Validation](validation.md) -- Checks that affect Stack posts
