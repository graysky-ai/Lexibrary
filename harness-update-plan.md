# Harness Update Plan: CLAUDE.md Generator Accuracy

## Problem

The generated CLAUDE.md agent rules advertise CLI commands that don't exist or have wrong signatures. This was discovered during a topology update investigation where a subagent tried to follow the CLAUDE.md rules and hit errors.

### Specific discrepancies found

| CLAUDE.md instruction | Actual CLI reality | Impact |
|---|---|---|
| "Run `lexi concepts <topic>` before making architectural decisions" | `lexi concept` is a CRUD group with subcommands: `new`, `link`, `comment`, `deprecate`. No search/query interface exists. `concepts` (plural) is not a valid command. | Agents cannot search concept documents by topic. They get a CLI error and must fall back to manual file exploration. |
| "Run `lexi stack search <query>` before starting to debug" | `lexi stack` is a CRUD group with subcommands: `post`, `finding`, `vote`, `view`, `accept`, etc. No `search` subcommand exists. | Agents cannot search Stack Q&A posts. They get a CLI error and must fall back to manual file exploration. |

### Root cause

The CLAUDE.md was generated from templates that describe the *intended* CLI surface, not the *actual* CLI surface. The rules reference search capabilities for `concept` and `stack` that were planned but never implemented as dedicated subcommands.

Note: `lexi search` does exist and searches across design files, concepts, conventions, and stack posts. The issue is that CLAUDE.md directs agents to use non-existent command-specific search endpoints (`lexi concepts <topic>`, `lexi stack search <query>`) rather than the unified `lexi search` command.

### Scope

This is NOT just a problem with this project's CLAUDE.md — the issue is in the **generator** that produces CLAUDE.md content. Fixing it requires updating the source templates, not just patching the local file.

## What needs to change

### 1. Update the CLAUDE.md generator templates

**Location:** `src/lexibrary/init/rules/claude.py` (and potentially `base.py` for shared rule content)

The generator templates need to be audited against the actual CLI surface. Specifically:

- Replace `lexi concepts <topic>` with `lexi search <topic>` (the unified search command that actually exists)
- Replace `lexi stack search <query>` with `lexi search <query>` (same unified search)
- Audit all other command references in the templates for accuracy
- Consider adding a validation step that checks referenced commands against the actual CLI

### 2. Regenerate CLAUDE.md for this project

After fixing the templates, regenerate this project's CLAUDE.md:
```bash
lexictl init --update-rules  # or whatever the regeneration command is
```

### 3. Consider a validation mechanism

To prevent this from recurring, consider:
- A test that parses CLAUDE.md command references and validates them against the actual Click/Typer command tree
- A CI check that regenerates CLAUDE.md and fails if the output differs from the committed version

## Secondary concern: empty knowledge artifacts

Even with correct commands, the `concepts/` and `stack/` directories are empty (`.gitkeep` only). The rules tell agents to search knowledge that doesn't exist yet. This is less of a bug and more of a bootstrapping problem — as the project matures, these will be populated. But the rules should handle the empty case gracefully (e.g., "search first, but if no results found, proceed with your own analysis").
