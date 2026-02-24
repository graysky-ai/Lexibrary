# I Was Here (IWH) Signals

IWH files are ephemeral signals left by one agent session to communicate with the next. They are the primary mechanism for inter-agent handoffs when work is interrupted, incomplete, or blocked.

## Purpose

Agent sessions end for many reasons -- token limits, timeouts, user interruptions, or deliberate handoffs. Without IWH files, the next agent starts from scratch and may:

- Duplicate work already in progress
- Miss context about why something was left incomplete
- Introduce conflicts with partially finished changes

IWH files prevent this by preserving just enough context for the next agent to pick up where you left off.

## When to Create an IWH File

Create an IWH file when:

- **You are leaving work incomplete.** You started a refactor, added some files, but did not finish. The next agent needs to know what was done and what remains.
- **You encountered a blocker.** Something prevents you from continuing (e.g., a dependency is missing, a test environment is unavailable, a design decision needs operator input).
- **You discovered something the next agent should know.** A warning about a fragile area of the code, a gotcha that is not documented elsewhere, or a time-sensitive issue.

Do NOT create an IWH file for:

- Completed work (the design files and commits document that)
- General observations (use a Stack post or concept instead)
- Problems that are already documented in a Stack post

## IWH File Format

An IWH file is named `.iwh` and contains YAML frontmatter followed by a markdown body:

```yaml
---
author: claude
created: '2026-02-23T14:30:00'
scope: incomplete
---
Refactoring the validation checks in `validator/checks.py`. Completed the
`hash_freshness` check rewrite but did not start on `orphan_concepts`.
The test for `hash_freshness` in `tests/test_validator/test_checks.py`
passes. Next step: rewrite `orphan_concepts` to use the link graph index.
```

### Frontmatter Fields

| Field | Type | Description |
|-------|------|-------------|
| `author` | string | Your agent identifier (e.g., `claude`, `cursor`) |
| `created` | ISO 8601 datetime | When the signal was created |
| `scope` | enum | Severity of the signal |

### Scope Values

| Scope | When to Use |
|-------|-------------|
| `warning` | Something the next agent should be aware of, but no action is strictly required |
| `incomplete` | Work was started but not finished; the body describes what remains |
| `blocked` | Work cannot proceed until a specific condition is met; the body describes the blocker |

## Where IWH Files Live

IWH files are stored in the `.lexibrary/` mirror tree, not in source directories.
The path mirrors the source directory structure:

- Source directory `src/auth/` → IWH file at `.lexibrary/src/auth/.iwh`
- Project root → IWH file at `.lexibrary/.iwh`

Use the CLI to create signals:

```bash
lexi iwh write src/auth/ --scope incomplete --body "Refactoring auth module..."
```

Only one `.iwh` file can exist per directory (a new one overwrites the previous).

## What to Include in the Body

Write the body as if briefing the next agent. Include:

1. **What was done.** What changes did you make? Which files were modified?
2. **What remains.** What is the next step? What was not finished?
3. **Affected files.** List the specific files that are in a partially modified state.
4. **Any context needed.** Why was this approach chosen? Are there any gotchas?

Keep it concise. The body should be enough to orient the next agent in 30 seconds.

### Good Example

```yaml
---
author: claude
created: '2026-02-23T16:00:00'
scope: incomplete
---
Adding FTS5 support to the link graph. Completed:
- Schema migration in `linkgraph/schema.py` (added `artifacts_fts` virtual table)
- Builder updates in `linkgraph/builder.py` (populates FTS table during build)

Not done:
- Query integration in `linkgraph/query.py` (need `full_text_search()` method)
- Search fallback in `search.py` (need to call FTS when link graph is available)

Tests for builder pass. No tests for query yet.
```

### Bad Example

```yaml
---
author: claude
created: '2026-02-23T16:00:00'
scope: incomplete
---
Was working on stuff. Not done yet.
```

## Consuming IWH Files

When you start a session, check for IWH files as part of the [orientation protocol](orientation.md):

```bash
lexi iwh list
```

If signals are present, consume them for each directory:

```bash
lexi iwh read <directory>
```

The `read` command displays the signal and deletes the file automatically. Use `--peek` to read without consuming.

After consuming a signal:

1. **Act on the instructions** -- complete the incomplete work, address the warning, or work around the blocker
2. If you cannot fully act on it, write a new signal describing the current state:
   `lexi iwh write <directory> --scope incomplete --body "updated status"`

## Summary

| Step | Action |
|------|--------|
| **Check** | Run `lexi iwh list` at session start |
| **Read** | Run `lexi iwh read <dir>` to consume and understand the signal |
| **Act** | Complete the work, address the warning, or work around the blocker |
| **Create** | Run `lexi iwh write <dir> --scope ... --body "..."` if leaving work incomplete |

## See Also

- [Orientation](orientation.md) -- the session start protocol that includes checking for IWH files
- [Quick Reference](quick-reference.md) -- cheat sheet with the IWH workflow summarized
