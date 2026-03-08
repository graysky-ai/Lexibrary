# Lexibrary -- Agent Overview

You are working in a codebase managed by Lexibrary. This document explains what Lexibrary provides for you and how to use it effectively.

## What Lexibrary Is

Lexibrary is a codebase indexer that maintains a `.lexibrary/` directory alongside the source code. This directory contains structured knowledge about the project -- design files that explain each source file, routing tables that summarize directories, a concepts wiki for project vocabulary, and a Stack Q&A knowledge base for solved problems.

All of this exists so that you can understand the codebase faster and make better changes.

## What `.lexibrary/` Provides

The `.lexibrary/` directory contains several types of artifacts:

### Design Files

For each source file, there is a corresponding design file (`.md`) in a mirror tree under `.lexibrary/`. A design file contains:

- **YAML frontmatter** -- source path, SHA-256 hash, generation timestamp, wikilinks to concepts
- **Summary** -- what the file does, its role in the project
- **Interface skeleton** -- extracted function signatures, class definitions, constants
- **Key details** -- important implementation notes, design decisions

Design files are your primary context source. Before editing a file, read its design file to understand what it does and how it fits into the project.

### `.aindex` Routing Tables

Each directory has a `.aindex` file that provides a billboard description of the directory's purpose and lists the files it contains with brief descriptions. These help you navigate the project structure without reading every file.

### `START_HERE.md`

A single project-level orientation file at `.lexibrary/START_HERE.md`. It contains:

- **Project topology** -- the full directory tree with annotations
- **Package map** -- what each package does
- **Navigation by intent** -- a lookup table mapping tasks to the files you should read first
- **Key constraints** -- project-wide coding rules

Read this file at the start of every session.

### Concepts Wiki

The `.lexibrary/concepts/` directory contains concept files -- project-specific vocabulary, architectural patterns, and domain terms. Each concept has a title, aliases, tags, a status (draft/active/deprecated), and a markdown body explaining the concept.

Use concepts to check for existing conventions before making architectural decisions.

### Stack Q&A

The `.lexibrary/stack/` directory contains Stack posts -- structured problem/solution records. Each post has a title, tags, status (open/resolved/outdated/duplicate), a problem description, evidence, and findings with votes.

Search the Stack before debugging to see if a problem has already been solved. Post to the Stack after solving non-trivial bugs so the knowledge is preserved.

### Link Graph Index

An SQLite database (`.lexibrary/index.db`, gitignored) that indexes cross-references between all artifacts. It accelerates reverse dependency lookups, tag searches, and full-text search. You do not interact with it directly -- the `lexi` commands use it automatically when available.

## Your CLI: `lexi`

You interact with Lexibrary through the `lexi` command. It provides:

- `lexi lookup <file>` -- get the design file, conventions, and dependents for a source file
- `lexi search <query>` -- search across concepts, design files, and Stack posts
- `lexi concepts [topic]` -- list or search concept files
- `lexi concept new <name>` -- create a new concept
- `lexi concept link <concept> <file>` -- link a concept to a source file's design file
- `lexi stack search [query]` -- search Stack posts
- `lexi stack post --title --tag` -- create a new Stack post
- `lexi stack finding <id> --body` -- add a finding to a Stack post
- `lexictl index [dir] [-r]` -- generate `.aindex` files
- `lexi describe <dir> <description>` -- update a directory's `.aindex` billboard

See [lexi-reference.md](lexi-reference.md) for the complete CLI reference.

## How Using Lexibrary Makes You More Effective

1. **Faster orientation.** Reading `START_HERE.md` gives you the full project topology and navigation table in one file instead of exploring the filesystem.

2. **Fewer mistakes.** Running `lexi lookup` before editing shows you the file's conventions, dependents, and design context -- so you know what will break and what patterns to follow.

3. **Better decisions.** Searching concepts before architectural changes tells you whether the project already has a convention for what you are about to do.

4. **Preserved knowledge.** Posting to the Stack after solving bugs means the next agent (or you in a future session) does not have to re-discover the same solution.

5. **Seamless handoffs.** Creating `.iwh` (I Was Here) signal files when leaving work incomplete ensures the next agent picks up exactly where you left off.

## What You Must Not Do

- Never run `lexictl` commands (`lexictl init`, `lexictl update`, `lexictl validate`, etc.). These are operator-only maintenance commands that make LLM calls and require human oversight.
- Never modify `.lexibrary/config.yaml` directly.
- Never delete files from `.lexibrary/` directly.
- Never modify `.aindex` files directly -- use `lexi describe` instead.

See [prohibited-commands.md](prohibited-commands.md) for details.

## Next Steps

- [Orientation](orientation.md) -- the step-by-step session start protocol
- [lexi Reference](lexi-reference.md) -- complete CLI reference with examples
- [Quick Reference](quick-reference.md) -- single-page cheat sheet
- [How It Works (User Docs)](../user/how-it-works.md) -- the full artifact lifecycle and operator/agent collaboration model
