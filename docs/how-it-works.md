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

### `lexi` -- For AI agents

Agents use `lexi` for lookups and queries:

- `lexi lookup <file>` -- Get the design file, conventions, and dependents for a source file.
- `lexictl index <dir>` -- Generate `.aindex` routing tables for a directory.
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
| `agent_updated` | The design file body was modified since last generation (e.g. by a maintainer) | Preserve modified version |
| `content_only` | Internal implementation changed but the public interface is identical | Regenerate with lower priority |
| `content_changed` | Content has changed in meaningful ways | Regenerate design file |
| `interface_changed` | Public API, exports, or function signatures changed | Regenerate design file (high priority) |
| `new_file` | No existing design file found | Generate new design file |

The `agent_updated` level is important: Lexibrary detects it by comparing a hash of the design file's body against the `design_hash` stored in frontmatter. If the body has been modified since the last generation -- whether by a maintainer, an agent, or any other process -- the design file is classified as `agent_updated` and its content is preserved during the next `lexictl update`. This ensures that manual edits are never silently overwritten.

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

After all design files are updated, Lexibrary regenerates `.lexibrary/TOPOLOGY.md`. This file is a procedural topology of the project -- it contains the directory tree, package map, and navigation guidance. Agents read this file at the start of every session to understand the project layout.

### 7. .aindex routing tables

During the update, Lexibrary also refreshes `.aindex` files. These are per-directory routing tables that list the files in a directory, their summaries, and any local conventions. They serve as an index that agents can read to quickly understand what a directory contains without reading every design file.

### 8. Link graph index

After design files are generated, Lexibrary builds a SQLite link graph index (`index.db`) that maps relationships between artifacts: import dependencies, wikilinks, tag assignments, concept references, and file references. This index accelerates queries like reverse dependency lookups and cross-artifact search.

### 9. Symbol graph

Alongside the link graph, Lexibrary builds a second SQLite database (`.lexibrary/symbols.db`) that records relationships **inside** files: function and method definitions, call edges between them, class hierarchy and composition edges, enum members, module-level constants, and external/dynamic calls that can't be resolved to a project symbol. Where the link graph answers "which files import this file?", the symbol graph answers "which functions call this function?", "which classes inherit from this class?", and "which classes compose this class as an attribute?".

**Build pipeline.** The symbol graph is built in the following order during `lexictl update`:

1. **File discovery** -- the builder walks source files under `scope_root`, filtered by ignore patterns.
2. **AST extraction** -- language-specific extractors (`python_parser.py`, `typescript_parser.py`) parse each file with tree-sitter to extract function, method, and class definitions; call sites; class edges (inheritance, instantiation); composition sites (type-annotated class attributes); and enum/constant definitions with their members.
3. **Symbol insertion** -- all extracted definitions are written to the `symbols` table.
4. **Call resolution** -- the Python resolver (`resolver_python.py`) resolves cross-file call sites using import analysis. The JS/TS resolver (`resolver_js.py`) resolves cross-file calls using `tsconfig.json` path aliases and extension probing.
5. **Class edge resolution** -- inheritance, instantiation, and composition targets are resolved through the same resolvers. Unresolved targets land in `class_edges_unresolved`.
6. **Enum classification** -- a transitive pass walks the `class_edges` inherits graph to classify indirect enum subclasses.

The parser maintains a per-file tree-sitter cache so both the symbol extractor and other AST-backed analyses share a single parsed tree per file, keeping the cost of a full rebuild close to the cost of the link-graph rebuild alone.

**Incremental rebuild.** When the pipeline knows which files changed (via `changed_paths` from the archivist's discovery phase), the builder checks whether the change set is small enough for incremental rebuild (below 30% of total indexed files). If so, it uses `refresh_file` to DELETE CASCADE each changed file's rows and re-extract, avoiding a full rebuild. Above the threshold, a full rebuild runs instead. Individual file refreshes via `lexi design update <file>` always use the single-file path.

**Resolution.** The Python resolver handles free functions in the same file, `self.method()` inside a class (with MRO walking through `class_edges` for inherited methods), `from module import name`, `import module`, and relative imports, sharing its module-to-file logic with `archivist/dependency_extractor.py`. The JS/TS resolver handles relative imports with extension probing, `tsconfig.json` path aliases (`@/*` wildcards, `baseUrl`), and index file fallback. `node_modules` specifiers return `None` (correctly classified as external). Calls that can't be mapped to a definition are stored in `unresolved_calls` rather than dropped.

**Class and composition edges.** The builder records three kinds of class relationships: `inherits` (from Python `class Foo(Bar):`, TS/JS `extends`/`implements`), `instantiates` (from Python PascalCase calls and TS/JS `new` expressions), and `composes` (from type-annotated class attributes like `self.bar: Bar` in Python or typed class fields in TypeScript). Resolved edges land in `class_edges`; external bases go into `class_edges_unresolved`. The Python resolver walks the MRO for `self.method()` calls so inherited methods resolve to their base class definition.

**Consumption.** Three commands read the symbol graph:

- `lexi trace <symbol>` -- shows callers, callees, unresolved calls, class relationships (inheritance, instantiation, composition), enum members, and constant values.
- `lexi search --type symbol <query>` -- fuzzy-finds a symbol by name, qualified name, or enum member value.
- `lexi lookup <file> --full` -- appends "Key symbols" and "Class hierarchy" sections to the file's design context.

Individual files are refreshed on `lexi design update <file>`; a full rebuild happens during `lexictl update`. See [Symbol Graph](symbol-graph.md) for the full reference, and concepts [[Symbol Graph]] (`CN-021`), [[Call Edge]] (`CN-022`), and [[Symbol Resolution]] (`CN-023`) for architectural rationale.

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

- **Orienting** by reading `.lexibrary/TOPOLOGY.md` and running `lexi iwh list` at the start of every session.
- **Looking up** design files before editing source code (`lexi lookup`).
- **Updating** design files after editing source code by running `lexi design update` and adding rationale with `lexi design comment` for non-trivial changes.
- **Creating** concepts when recurring patterns emerge (`lexi concept new`).
- **Recording** solutions to problems in Stack Q&A (`lexi stack post`).
- **Searching** across all artifacts for context (`lexi search`).

### The feedback loop

1. The operator runs `lexictl update` to generate design files from source code.
2. An agent reads design files via `lexi lookup` before making changes.
3. The agent edits source code and runs `lexi design update` to regenerate the design file, then uses `lexi design comment` to capture rationale for non-trivial changes.
4. The next time the operator runs `lexictl update`, any design files whose body was modified since last generation are detected via design-hash mismatch and preserved (the `agent_updated` change level).
5. If the source code's public interface changes enough to make the existing design file obsolete, the design file is regenerated with fresh content.

This cycle ensures that knowledge accumulates over time. Agents contribute understanding through design file edits, concepts, and Stack posts. Operators keep the library healthy and up-to-date through periodic updates and validation.

## Artifact Lifecycle by Type

Each artifact type follows a different lifecycle pattern for initialization, creation, maintenance, deprecation, and consumption.

### Design files

- **Initialization:** Created automatically by `lexictl update` for every source file under `scope_root`. New projects get a full set; existing projects get design files for all discovered source files on first run.
- **Creation trigger:** Deterministic -- `lexictl update` generates design files for any source file that lacks one or has changed. Agents can also trigger regeneration via `lexi design update` after editing source code.
- **Maintenance:** Design files are regenerated when the source file changes. Agent-edited design files (detected via `design_hash` mismatch) are preserved during updates. Agents add context through `lexi design comment` for non-trivial changes.
- **Deprecation:** Design files are implicitly stale when their source file is deleted. The `file_existence` validation check flags orphaned design files. They can be cleaned up by running `lexictl update`, which removes design files for missing source files.
- **Consumption:** Agents read design files via `lexi lookup <file>` before editing source code.

### Concepts

- **Initialization:** The `concepts/` directory is created empty during `lexictl init`. No concepts are pre-seeded.
- **Creation trigger:** Agent-initiated -- agents create concepts via `lexi concept new` when they identify recurring patterns, domain terms, or architectural decisions worth documenting.
- **Maintenance:** Concepts are manually edited. Agents and operators can add comments to build up the concept over time. The curator agent can assess comment quality and incorporate feedback.
- **Deprecation:** Concepts can be set to `status: deprecated` with an optional `superseded_by` pointer. The `deprecated_concept_usage` validation check flags artifacts that still reference deprecated concepts. The `orphan_concepts` check flags concepts with zero inbound references.
- **Consumption:** Agents discover concepts via `lexi concepts [topic]` for listing and `lexi search` for cross-artifact search. Wikilinks (`[[concept-name]]`) in design files and Stack posts create navigable links.

### Stack posts

- **Initialization:** The `stack/` directory is created empty during `lexictl init`.
- **Creation trigger:** Agent-initiated -- agents create Stack posts via `lexi stack post` when they encounter and solve non-trivial bugs or discover important patterns.
- **Maintenance:** Agents contribute findings (`lexi stack finding`), vote on usefulness (`lexi stack vote`), and accept solutions (`lexi stack accept`). Posts can be marked resolved, outdated, or as duplicates.
- **Deprecation:** Posts are marked `outdated` via `lexi stack mark-outdated` when referenced source files change significantly. The `stack_staleness` validation check flags posts whose referenced files have stale design files.
- **Consumption:** Agents search for existing solutions via `lexi stack search` before debugging, and view posts via `lexi stack view`.

### .aindex routing tables

- **Initialization:** Created during `lexictl update` for each directory under `scope_root`.
- **Creation trigger:** Deterministic -- generated automatically during project updates and on demand via `lexictl index <dir>`.
- **Maintenance:** Agents can update directory descriptions via `lexi describe <dir> <description>`. Local conventions are maintained within `.aindex` files and inherited by child directories.
- **Deprecation:** Removed automatically when the corresponding directory is deleted and `lexictl update` is re-run.
- **Consumption:** Agents read `.aindex` files to understand a directory at a glance. Conventions from `.aindex` files are surfaced by `lexi lookup`.

## Related Documentation

- [Getting Started](getting-started.md) -- Installation and first run
- [Library Structure](library-structure.md) -- Anatomy of the `.lexibrary/` directory
- [Design Files](design-files.md) -- Deep dive into how `lexictl update` works
- [Configuration](configuration.md) -- Full config.yaml reference
- [Link Graph](link-graph.md) -- How the file-level SQLite index is built and queried
- [Symbol Graph](symbol-graph.md) -- How the symbol-level SQLite index is built and queried
