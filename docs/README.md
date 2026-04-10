# Lexibrary Documentation

Lexibrary is an AI-friendly codebase indexer that produces a `.lexibrary/` directory containing design files, routing tables, a concepts wiki, a Stack Q&A knowledge base, conventions, playbooks, and a link graph index. It helps AI agents understand your codebase and helps operators maintain that understanding over time.

Lexibrary provides two CLIs:

- **`lexictl`** -- Operator-facing maintenance commands (init, update, bootstrap, validate, status, sweep, curate)
- **`lexi`** -- Agent-facing lookup and query commands (lookup, search, describe, impact, concepts, conventions, stack, playbooks)

---

## Table of Contents

| # | Document | Description |
|---|----------|-------------|
| 1 | [Getting Started](getting-started.md) | Prerequisites, installation, first `lexictl init`, first `lexictl update`, verifying output |
| 2 | [How It Works](how-it-works.md) | What Lexibrary produces, the artifact lifecycle, the operator/agent split, change detection |
| 3 | [Project Setup](project-setup.md) | Init wizard deep dive -- the 8 wizard steps, `--defaults` for CI, re-init guard, changing settings |
| 4 | [Configuration](configuration.md) | Full `config.yaml` reference -- every key, default value, and what it controls |
| 5 | [Library Structure](library-structure.md) | Anatomy of the `.lexibrary/` directory -- what each artifact type is and where it lives |
| 6 | [CLI Reference](cli-reference.md) | Complete CLI reference for both `lexi` and `lexictl` -- every command, flag, and argument |
| 7 | [Design Files](design-files.md) | Design file system end-to-end -- generation, lookup workflow, update/comment workflow, skeleton mode |
| 8 | [Search](search.md) | Unified cross-artifact search -- `lexi search`, filters, result types, when to use search vs lookup |
| 9 | [Concepts](concepts.md) | Project-specific vocabulary and architectural patterns -- creating, linking, and managing concepts |
| 10 | [Conventions](conventions.md) | Convention system -- scope model, creating, approving, deprecating, conventions vs concepts |
| 11 | [Stack Q&A](stack.md) | Structured problem/solution knowledge base -- posts, findings, voting, searching, lifecycle |
| 12 | [Playbooks](playbooks.md) | Playbook system -- creating, file anatomy, approve/verify/deprecate lifecycle, trigger-glob matching |
| 13 | [I Was Here (IWH)](iwh.md) | IWH signals -- preventing lost context between sessions, creating and consuming signal files |
| 14 | [Validation](validation.md) | How `lexictl validate` works -- checks, severity levels, JSON output, exit codes |
| 15 | [Ignore Patterns](ignore-patterns.md) | The ignore system -- `.lexignore`, `.gitignore` integration, pattern precedence |
| 16 | [Link Graph](link-graph.md) | The SQLite link graph -- what it indexes, what queries it accelerates, how to rebuild |
| 17 | [CI Integration](ci-integration.md) | CI/CD recipes -- git hooks, periodic sweeps, validation as CI gate |
| 18 | [Troubleshooting](troubleshooting.md) | Common issues organized by category -- symptoms, causes, and fixes |
| 19 | [Upgrading](upgrading.md) | Version upgrade guide -- config evolution, when to re-run commands |
