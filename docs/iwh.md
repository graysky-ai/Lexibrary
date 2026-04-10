# I Was Here (IWH) Signals

IWH files are ephemeral signals left by one agent session to communicate with the next. They are the primary mechanism for inter-agent handoffs when work is interrupted, incomplete, or blocked.

## Purpose

Agent sessions end for many reasons -- token limits, timeouts, user interruptions, or deliberate handoffs. Without IWH files, the next agent starts from scratch and may:

- Duplicate work already in progress
- Miss context about why something was left incomplete
- Introduce conflicts with partially finished changes

IWH files prevent this by preserving just enough context for the next agent to pick up where the previous one left off.

## When IWH Files Are Created

Agents create IWH files when:

- **Work is left incomplete.** An agent started a refactor, added some files, but did not finish. The next agent needs to know what was done and what remains.
- **A blocker was encountered.** Something prevents continuation (e.g., a dependency is missing, a test environment is unavailable, a design decision needs operator input).
- **Something important was discovered.** A warning about a fragile area of the code, a gotcha that is not documented elsewhere, or a time-sensitive issue.

IWH files are NOT created for:

- Completed work (design files and commits document that)
- General observations (Stack posts or concepts are used instead)
- Problems already documented in a Stack post

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
| `author` | string | Agent identifier (e.g., `claude`, `cursor`) |
| `created` | ISO 8601 datetime | When the signal was created |
| `scope` | enum | Severity of the signal |

### Scope Values

| Scope | When It Is Used |
|-------|-----------------|
| `warning` | Something the next agent should be aware of, but no action is strictly required |
| `incomplete` | Work was started but not finished; the body describes what remains |
| `blocked` | Work cannot proceed until a specific condition is met; the body describes the blocker |

## Where IWH Files Live

IWH files are stored in the `.lexibrary/` mirror tree, not in source directories.
The path mirrors the source directory structure:

- Source directory `src/auth/` -> IWH file at `.lexibrary/src/auth/.iwh`
- Project root -> IWH file at `.lexibrary/.iwh`

Agents create signals using the CLI:

```bash
lexi iwh write src/auth/ --scope incomplete --body "Refactoring auth module..."
```

Only one `.iwh` file can exist per directory (a new one overwrites the previous).

## What the Body Contains

The body is written as a briefing for the next agent. It includes:

1. **What was done.** Which changes were made and which files were modified.
2. **What remains.** The next step and what was not finished.
3. **Affected files.** The specific files that are in a partially modified state.
4. **Context.** Why the approach was chosen and any gotchas.

The body should be concise -- enough to orient the next agent in 30 seconds.

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

## How Agents Consume IWH Files

At session start, agents check for IWH files as part of their startup protocol:

```bash
lexi iwh list
```

If signals are present, agents consume them for each directory they are working in:

```bash
lexi iwh read <directory>
```

The `read` command displays the signal and deletes the file automatically. The `--peek` flag reads without consuming.

After consuming a signal, agents either act on the instructions (complete the incomplete work, address the warning, or work around the blocker) or write a new signal describing the updated state.

## How to Inspect IWH Signals Manually

Operators and team members can inspect IWH signals without consuming them, which is useful for understanding what agents have been working on and whether any handoffs need attention.

### List all active signals

```bash
lexi iwh list
```

This shows all `.iwh` files across the project with their scope and creation time.

### Peek at a signal without consuming it

```bash
lexi iwh read <directory> --peek
```

The `--peek` flag displays the signal contents but leaves the file in place, so the next agent can still consume it.

### Read signals directly from the filesystem

IWH files are plain YAML+Markdown files in the `.lexibrary/` mirror tree. To find and read them directly:

```bash
# Find all IWH files
find .lexibrary -name ".iwh" -type f

# Read a specific signal
cat .lexibrary/src/auth/.iwh
```

### Clear a stale signal

If a signal is no longer relevant (the work was completed by other means, or the context is outdated), consume it to remove it:

```bash
lexi iwh read <directory>
```

Or delete the file directly:

```bash
rm .lexibrary/src/auth/.iwh
```

## Summary

| Step | Action | Command |
|------|--------|---------|
| **List** | See all active signals | `lexi iwh list` |
| **Peek** | Read a signal without consuming | `lexi iwh read <dir> --peek` |
| **Consume** | Read and delete a signal | `lexi iwh read <dir>` |
| **Create** | Leave a signal for the next agent | `lexi iwh write <dir> --scope ... --body "..."` |

## Related Documentation

- [CLI Reference](cli-reference.md) -- Full `iwh` subcommand reference
- [Configuration](configuration.md) -- `iwh.enabled` setting
- [How It Works](how-it-works.md) -- Overview of operator-agent collaboration
