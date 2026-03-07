# How It Works

This document explains what Lexibrary is, what it produces, how the artifact lifecycle works, and how operators and AI agents collaborate through the library.

## What Lexibrary Is

Lexibrary is an AI-friendly codebase indexer. It reads your source code and produces a `.lexibrary/` directory containing structured artifacts that help AI agents understand your codebase without reading every file. Think of it as a knowledge layer that sits alongside your code -- maintained by operators, consumed by agents.

Lexibrary does not modify your source code. It only reads source files and writes artifacts into the `.lexibrary/` directory.

## The Two CLIs

Lexibrary provides two separate command-line interfaces for its two audiences:

### `lexictl` -- For operators and team members

Operators use `lexictl` for maintenance tasks:

- `lexictl init` -- Initialize Lexibrary in a project (setup wizard).
- `lexictl update` -- Generate or regenerate design files from source code.
- `lexictl validate` -- Run health checks on the library.
- `lexictl status` -- View a dashboard of library health and staleness.
- `lexictl setup` -- Install or update agent environment rules and git hooks.
- `lexictl sweep` -- Run a library update sweep (one-shot or watch mode).
- `lexictl daemon` -- Manage the watchdog daemon for real-time file monitoring.

### `lexi` -- For AI agents

Agents use `lexi` for lookups and queries:

- `lexi lookup <file>` -- Get the design file, conventions, and dependents for a source file.
- `lexi index <dir>` -- Generate `.aindex` routing tables for a directory.
- `lexi describe <dir> <description>` -- Update a directory's billboard description.
- `lexi concepts [topic]` -- List or search concept files.
- `lexi concept new <name>` -- Create a new concept.
- `lexi concept link <concept> <file>` -- Link a concept to a source file's design file.
- `lexi stack post|search|finding|vote|accept|view|list` -- Stack Q&A management.
- `lexi search [query]` -- Search across concepts, design files, and Stack posts.

Agents should never run `lexictl` commands. Those commands involve LLM calls, cost money, and require operator oversight.

## The Artifact Lifecycle

Lexibrary produces several types of artifacts from your source code. Here is the lifecycle from source file to usable knowledge.

### 1. Source file discovery

When you run `lexictl update`, Lexibrary walks the directory tree under `scope_root` (configured in `config.yaml`). It respects ignore patterns from `.gitignore`, `.lexignore`, and the `ignore.additional_patterns` config setting. Binary files (images, archives, executables) are skipped based on file extension.

### 2. Change detection

For each discovered source file, Lexibrary computes a SHA-256 hash and compares it against the `source_hash` stored in the existing design file's frontmatter. If the hashes match, the file is unchanged and no LLM call is made.

### 3. Change classification

When a source file has changed, Lexibrary classifies the type of change into one of these levels:

| Level | Meaning | Action |
|-------|---------|--------|
| `unchanged` | Source hash matches -- no changes detected | Skip |
| `agent_updated` | An agent edited the design file directly (`updated_by: agent`) | Preserve agent's version |
| `content_only` | Internal implementation changed but the public interface is identical | Regenerate with lower priority |
| `content_changed` | Content has changed in meaningful ways | Regenerate design file |
| `interface_changed` | Public API, exports, or function signatures changed | Regenerate design file (high priority) |
| `new_file` | No existing design file found | Generate new design file |

The `agent_updated` level is important: when an AI agent manually updates a design file and sets `updated_by: agent` in the frontmatter, Lexibrary will not overwrite that agent's work during the next `lexictl update`. The agent's understanding is preserved.

### 4. LLM-powered generation

For files that need new or updated design files, Lexibrary sends the source code to the configured LLM (via BAML prompts through the `ArchivistService`). The LLM produces a structured design file containing:

- A summary of what the file does.
- Key implementation details.
- An interface skeleton (for languages with AST support: Python, TypeScript, JavaScript).
- Wikilinks to related concepts.

### 5. Design file output

The generated design file is written to the `.lexibrary/` directory in a mirror tree that matches your source directory structure. For example:

```
src/lexibrary/config/schema.py    -->    .lexibrary/src/lexibrary/config/schema.py.md
```

Each design file includes YAML frontmatter with metadata:

```yaml
---
source: src/lexibrary/config/schema.py
source_hash: a1b2c3d4...
generated: 2026-02-23T10:00:00
updated_by: lexibrary-v2
wikilinks:
  - pydantic-config
  - token-budgets
---
```

### 6. TOPOLOGY.md regeneration

After all design files are updated, Lexibrary regenerates `.lexibrary/TOPOLOGY.md`. This file is a procedural topology of the project -- it contains the directory tree, package map, and navigation guidance. Agents use the `/lexi-orient` session-start skill to orient themselves at the start of every session.

### 7. .aindex routing tables

During the update, Lexibrary also refreshes `.aindex` files. These are per-directory routing tables that list the files in a directory, their summaries, and any local conventions. They serve as an index that agents can read to quickly understand what a directory contains without reading every design file.

### 8. Link graph index

After design files are generated, Lexibrary builds a SQLite link graph index (`index.db`) that maps relationships between artifacts: import dependencies, wikilinks, tag assignments, concept references, and file references. This index accelerates queries like reverse dependency lookups and cross-artifact search.

## How Operators and Agents Collaborate

The operator-agent collaboration model follows a clear separation of concerns:

### Operators are responsible for:

- **Initializing** the library (`lexictl init`).
- **Generating** design files (`lexictl update`).
- **Validating** library health (`lexictl validate`).
- **Configuring** settings (editing `config.yaml`).
- **Setting up** CI hooks and agent rules (`lexictl setup`).
- **Monitoring** staleness and issues (`lexictl status`).

### Agents are responsible for:

- **Orienting** via the `/lexi-orient` skill (which reads `TOPOLOGY.md`) at the start of every session.
- **Looking up** design files before editing source code (`lexi lookup`).
- **Updating** design files after editing source code (manual edits to `.lexibrary/` Markdown files).
- **Creating** concepts when recurring patterns emerge (`lexi concept new`).
- **Recording** solutions to problems in Stack Q&A (`lexi stack post`).
- **Searching** across all artifacts for context (`lexi search`).

### The feedback loop

1. The operator runs `lexictl update` to generate design files from source code.
2. An agent reads design files via `lexi lookup` before making changes.
3. The agent edits source code and updates the corresponding design file, setting `updated_by: agent`.
4. The next time the operator runs `lexictl update`, the agent's design file edits are preserved (because of the `agent_updated` change level).
5. If the source code's public interface changes in a way that makes the agent's description obsolete, the design file is regenerated.

This cycle ensures that knowledge accumulates over time. Agents contribute understanding through design file edits, concepts, and Stack posts. Operators keep the library healthy and up-to-date through periodic updates and validation.

## Related Documentation

- [Getting Started](getting-started.md) -- Installation and first run
- [Library Structure](library-structure.md) -- Anatomy of the `.lexibrary/` directory
- [Design File Generation](design-file-generation.md) -- Deep dive into how `lexictl update` works
- [Configuration](configuration.md) -- Full config.yaml reference
- [Agent Overview](../agent/README.md) -- What Lexibrary is from the agent's perspective
- [Agent Orientation](../agent/orientation.md) -- How agents start each session
