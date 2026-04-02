# Lexibrary Documentation

Lexibrary is an AI-friendly codebase indexer that produces a `.lexibrary/` directory containing design files, routing tables, a concepts wiki, a Stack Q&A knowledge base, and a link graph index. It helps AI agents understand your codebase and helps operators maintain that understanding over time.

Lexibrary provides two CLIs:

- **`lexictl`** -- Operator-facing maintenance commands (init, update, validate, status, setup, sweep)
- **`lexi`** -- Agent-facing lookup and query commands (lookup, index, describe, concepts, stack, search)

## Who are you?

This documentation is split into two sets based on audience. Pick the one that matches your role.

### I am an operator or team member

You install, configure, and maintain Lexibrary for your project. You run `lexictl` commands to initialize the library, generate design files, validate health, and set up CI hooks.

Start here: [User Docs](user/)

### I am an AI agent

You work within a codebase that has Lexibrary set up. You use `lexi` commands to look up files, search across artifacts, read concepts, and consult the Stack Q&A before and after making changes.

Start here: [Agent Docs](agent/)

---

## User Docs -- Table of Contents

Documentation for operators and team members who install, configure, and maintain Lexibrary.

### Getting Started

| Document | Description |
|----------|-------------|
| [Getting Started](user/getting-started.md) | Prerequisites, installation, first `lexictl init`, first `lexictl update`, verifying output |
| [How It Works](user/how-it-works.md) | What Lexibrary produces, the artifact lifecycle, the operator/agent split, change detection |
| [Configuration](user/configuration.md) | Full `config.yaml` reference -- every key, default value, and what it controls |
| [Library Structure](user/library-structure.md) | Anatomy of the `.lexibrary/` directory -- what each artifact type is and where it lives |

### CLI and Setup

| Document | Description |
|----------|-------------|
| [lexictl Reference](user/lexictl-reference.md) | Complete `lexictl` CLI reference -- every command, flag, and argument with examples |
| [Project Setup](user/project-setup.md) | Init wizard deep dive -- the 8 wizard steps, `--defaults` for CI, re-init guard, changing settings |

### Feature Deep Dives

| Document | Description |
|----------|-------------|
| [Design File Generation](user/design-file-generation.md) | How `lexictl update` works end-to-end -- file discovery, change detection, LLM generation |
| [Validation](user/validation.md) | How `lexictl validate` works -- 13 checks, severity levels, JSON output, exit codes |
| [CI Integration](user/ci-integration.md) | CI/CD recipes -- git hooks, periodic sweeps, validation as CI gate |
| [Concepts Wiki](user/concepts-wiki.md) | Project-specific vocabulary and architectural patterns -- creating, linking, and managing concepts |
| [Stack Q&A](user/stack-qa.md) | Structured problem/solution knowledge base -- posts, findings, voting, searching |
| [Link Graph](user/link-graph.md) | The SQLite index -- what it indexes, what queries it accelerates, how to rebuild |
| [Ignore Patterns](user/ignore-patterns.md) | The ignore system -- `.lexignore`, `.gitignore` integration, pattern precedence |

### Operational

| Document | Description |
|----------|-------------|
| [Troubleshooting](user/troubleshooting.md) | Common issues organized by category -- symptoms, causes, and fixes |
| [Upgrading](user/upgrading.md) | Version upgrade guide -- config evolution, when to re-run commands |

---

## Agent Docs -- Table of Contents

Documentation for AI agents working within Lexibrary-managed codebases.

### Overview

| Document | Description |
|----------|-------------|
| [Agent Overview](agent/README.md) | What Lexibrary is from the agent's perspective, what `.lexibrary/` provides, how to use it |

### CLI Reference

| Document | Description |
|----------|-------------|
| [lexi Reference](agent/lexi-reference.md) | Complete `lexi` CLI reference -- every command, flag, and argument with usage examples |

### Workflows

| Document | Description |
|----------|-------------|
| [Lookup Workflow](agent/lookup-workflow.md) | Before-edit workflow -- run `lexi lookup`, understand design files, check conventions and dependents |
| [Update Workflow](agent/update-workflow.md) | After-edit workflow -- update design files, set `updated_by: agent`, when to let `lexictl update` handle it |
| [Concepts](agent/concepts.md) | Using the concepts wiki -- searching, creating, and linking concepts |
| [Stack Q&A](agent/stack.md) | Using Stack Q&A -- searching before debugging, posting after solving, voting and adding findings |
| [Search](agent/search.md) | Unified cross-artifact search -- `lexi search`, filters, when to use search vs lookup |
| [I Was Here (IWH)](agent/iwh.md) | IWH signals -- preventing lost context, creating and consuming signal files |

### Rules and Reference

| Document | Description |
|----------|-------------|
| [Prohibited Commands](agent/prohibited-commands.md) | What agents must NOT do -- `lexictl` commands, config edits, direct file deletions |
| [Quick Reference](agent/quick-reference.md) | Single-page cheat sheet -- checklists, key commands table, common scenarios |
