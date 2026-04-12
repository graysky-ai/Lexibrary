# Design Files

Design files are per-source-file documentation artifacts that capture what a file does, its public interface, dependencies, and cross-references to concepts and Stack posts. They are stored as Markdown files with YAML frontmatter in a mirror tree under `.lexibrary/` that matches the project directory structure.

Design files are generated and maintained by the archivist pipeline -- updates are triggered via CLI commands rather than by editing design files directly.

## What Design Files Contain

Each design file is a Markdown file with the following structure:

- **Frontmatter** -- YAML block with `description` (what the file does) and `updated_by` (either `archivist` for LLM-generated or `agent` for agent-maintained).
- **Summary** -- A narrative description of the file's purpose and role in the project.
- **Interface Contract** -- For code files, the public API surface: function signatures, class definitions, exported symbols, and their docstrings.
- **Dependencies** -- Project-relative paths of files this source imports.
- **Dependents** -- Files that import this source (populated by the link graph).
- **Enums & constants** -- Structured notes about enums and module-level constants defined by the file, sourced from the symbol graph (see subsection below).
- **Call paths** -- Narrative notes about the important call paths flowing into and out of the file's functions, sourced from the symbol graph (see subsection below).
- **Data flows** -- Notes about how function parameters influence control flow through branching, gated on a deterministic AST signal (see subsection below).
- **Wikilinks** -- `[[concept-name]]` references linking to relevant concept files.
- **Tags** -- Classification tags for search and filtering.
- **Stack refs** -- References to related Stack Q&A posts.
- **Metadata Footer** -- An HTML comment block containing `source_hash`, `interface_hash`, `design_hash`, `generated` timestamp, and `generator` identifier. These fields drive change detection.

### Enums & constants

The `## Enums & constants` section captures every enum, `StrEnum`/`IntEnum`/`Flag` subclass, and module-level constant defined in the file. It is populated by the archivist pipeline from the [symbol graph](symbol-graph.md), not by the LLM reading the source directly, so it only appears when the symbol graph has already indexed the file's enums and constants.

Each entry has two fields:

- **`name`** -- The enum or constant name (e.g. `BuildStatus`, `SCHEMA_VERSION`).
- **`role`** -- A one-clause description of what the enum or constant represents in the system. The archivist writes the role prose from the enum's members and surrounding context.
- **`values`** -- The literal enum members (e.g. `PENDING, RUNNING, FAILED, SUCCESS`) or the single literal value for a constant. Emitted on the line below `role`.

Example:

```markdown
## Enums & constants

- **BuildStatus** — Tracks pipeline execution state across the update lifecycle.
  Values: PENDING, RUNNING, FAILED, SUCCESS.
- **SCHEMA_VERSION** — Monotonic version number for the library schema; bumped whenever a migration is required.
  Values: 2.
```

The section is omitted entirely when the file defines no enums or constants, or when `symbols.include_enums` is `false`. Truncation applies when the file has more than `symbols.max_enum_items` entries -- the tail of the list is replaced with `- ... N more`. See [Configuration](configuration.md#symbols) for the full flag reference.

### Call paths

The `## Call paths` section captures narrative summaries of how functions and methods in the file connect to the rest of the codebase. Unlike a raw call trace, the archivist writes prose describing the *behaviour* flowing along each path -- what the entry point is for, which hops carry important side effects, and where the chain terminates.

Each entry has three fields:

- **`entry`** -- The starting symbol for the call path (e.g. `update_project()`).
- **`narrative`** -- A one- to two-sentence description of what the entry point orchestrates.
- **`key_hops`** -- A short list of the narratively important callees visited along the path, not the full mechanical call stack.

Example:

```markdown
## Call paths

- **update_project()** — Orchestrates a full project build: discovers source files, regenerates changed design files, refreshes aindexes, rebuilds the link graph, then the symbol graph.
  Key hops: discover_source_files, update_file, build_index, build_symbol_graph.
```

Call paths are **opt-in**. Set `symbols.include_call_paths: true` in your config to enable them -- see [Configuration](configuration.md#symbols). The depth of each path is controlled by `symbols.call_path_depth` (default `2` hops in each direction). The section is truncated at `symbols.max_call_path_items` entries. Enabling call paths increases archivist prompt size by roughly `call_path_depth × 50` tokens per file, so the flag is off by default to avoid surprise prompt bloat.

### Data flows

The `## Data flows` section captures how function parameters influence control flow through branching. It is gated on a deterministic AST signal: the archivist only produces data flow notes for files whose symbol graph contains at least one function with branch parameters (parameters that appear in `if`, `match`, `switch`, or similar conditions). Files without branching parameters never produce this section, regardless of configuration.

Each entry has three fields:

- **`parameter`** -- The name of the parameter that drives branching (e.g. `changed_paths`, `config`).
- **`location`** -- The function or method where the branching occurs (e.g. `build_index()`).
- **`effect`** -- A one-sentence description of the behavioural impact when the parameter varies.

Example:

```markdown
## Data flows

- **changed_paths** in **build_index()** — `None` triggers a full build; a non-None list triggers incremental update.
- **config** in **render()** — Controls output format and verbosity.
```

Data flows are **opt-in**. Set `symbols.include_data_flows: true` in your config to enable them -- see [Configuration](configuration.md#symbols). Even when enabled, the two-layer gate (file-level check for any branch parameters, then per-symbol extraction) ensures the LLM is only asked to generate data flow notes when there is concrete evidence of branching behaviour, keeping prompt costs predictable.

### Mirror Tree

Design files are stored in a mirror tree under `.lexibrary/` that matches the project directory structure:

```
src/auth/service.py       -->  .lexibrary/src/auth/service.py.md
src/utils/helpers.py      -->  .lexibrary/src/utils/helpers.py.md
tests/test_auth.py        -->  .lexibrary/tests/test_auth.py.md
```

Parent directories are created automatically as needed.

## How Generation Works

When `lexictl update` runs, it:

1. Discovers all source files under `scope_root`.
2. Filters out binary files, ignored files, and oversized files.
3. Compares each file's SHA-256 hash against the hash stored in its existing design file.
4. Classifies the type of change (see ChangeLevel below).
5. Sends files that need updating to the configured LLM for design file generation.
6. Writes design files into the `.lexibrary/` mirror tree.
7. Refreshes parent `.aindex` routing tables.
8. Regenerates `TOPOLOGY.md` with the updated project topology.
9. Builds or rebuilds the link graph index.

### File Discovery

`lexictl update` scans the configured `scope_root` directory recursively. Files are filtered at several levels:

- **Ignore matching** -- Files matching any ignore pattern (from `.gitignore`, `.lexignore`, or `ignore.additional_patterns` in config) are skipped. See [Ignore Patterns](ignore-patterns.md).
- **Binary detection** -- Files with extensions listed in `crawl.binary_extensions` are skipped.
- **Size limit** -- Files larger than `crawl.max_file_size_kb` (default: 512 KB) are skipped.
- **Scope boundary** -- Files outside `scope_root` are excluded.
- **Library contents** -- Files inside `.lexibrary/` are never processed as source files.

### ChangeLevel Classification

Every source file is classified into one of six change levels:

| ChangeLevel | Meaning | Action Taken |
|---|---|---|
| `UNCHANGED` | Source hash matches the stored hash | No action -- file is skipped |
| `AGENT_UPDATED` | Design file body was modified since last generation | Footer hashes refreshed, LLM **not** called (preserves modifications) |
| `CONTENT_ONLY` | Source content changed but public interface did not | LLM called to regenerate |
| `CONTENT_CHANGED` | Source content changed (non-code file, or no interface hash) | LLM called to regenerate |
| `INTERFACE_CHANGED` | Public interface of the source file changed | LLM called to regenerate |
| `NEW_FILE` | No design file exists for this source file | LLM called to generate new design file |

### Manual Edit Detection

Lexibrary stores a `design_hash` in the metadata footer. When the design file body is modified after generation, the computed hash differs from the stored `design_hash`, triggering the `AGENT_UPDATED` classification. This ensures manual edits are never silently overwritten by LLM regeneration.

### Conflict Marker Check

Before sending a file to the LLM, Lexibrary checks for unresolved merge conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`). Files containing conflict markers are skipped and counted as failed.

### LLM Generation Pipeline

Files classified as `NEW_FILE`, `CONTENT_ONLY`, `CONTENT_CHANGED`, or `INTERFACE_CHANGED` are sent to the LLM via the `ArchivistService`. For each file, the pipeline prepares:

- **source_path** -- Project-relative path.
- **source_content** -- Full text of the source file.
- **interface_skeleton** -- For code files with AST support, a rendered skeleton of public interfaces.
- **language** -- Detected programming language.
- **existing_design_file** -- Current design file text (if one exists).
- **available_concepts** -- All concept names, used to guide wikilink generation.

### TOCTOU Protection

To prevent race conditions, Lexibrary captures the `design_hash` before sending a request to the LLM. After the LLM returns, it re-checks the hash. If the design file was modified during generation, the LLM output is discarded and the file is treated as `AGENT_UPDATED`.

### Token Budget Validation

After generating a design file, Lexibrary estimates the token count. If the count exceeds `token_budgets.design_file_tokens` (default: 400 tokens), a warning is logged. The design file is still written -- the warning is informational and surfaced by `lexi validate`.

### Skeleton Mode

When LLM enrichment is not available or a file exceeds the size gate, Lexibrary generates a lightweight skeleton design file using AST analysis only. Skeleton mode extracts function signatures, class definitions, and import statements without calling the LLM. This mode is also used by the `lexictl update --skeleton` flag for PostToolUse hooks.

## Lookup Workflow

Before editing any source file, run `lexi lookup` to understand what is about to change:

```bash
lexi lookup src/lexibrary/config/schema.py
```

The output provides up to seven sections of context:

1. **Design file content** -- The full design file with summary, interface contract, and metadata.
2. **Staleness warning** -- Indicates if the source file has changed since the design file was last generated. The design file may be outdated; rely on the source file itself for current state, but use the design file for architectural context.
3. **Applicable conventions** -- Rules inherited from `.aindex` files walked upward from the file's directory to the scope root. These represent project-wide and directory-specific standards that must be followed when editing.
4. **Known Issues** -- Stack posts referencing this file, with status, title, and vote counts.
5. **IWH signals** -- Inter-session coordination signals for the file's directory.
6. **Dependents** -- Files that import this file (from the link graph). These may need updates if a public interface changes.
7. **Also referenced by** -- Cross-references from concepts, Stack posts, and other design files.

**Exit codes:**

| Code | Meaning |
|------|---------|
| 0 | Design file found and displayed |
| 1 | File is outside `scope_root`, or no design file exists |

If exit code 1 occurs because no design file exists, the file has not yet been indexed. The operator can generate one with `lexictl update`.

## Update and Comment Workflow

After making meaningful changes to a source file, update its design file so the next person or agent working on the file has accurate context.

### When to Run `lexi design update`

Run `lexi design update <file>` after changes affect:

- **What the file does** -- new functionality, changed purpose, removed features.
- **The public interface** -- new functions, changed signatures, renamed classes, new constants.
- **Key implementation details** -- changed algorithms, new dependencies, architectural decisions.
- **Dependencies** -- new imports or removed imports.

Use `--force` to regenerate even when the file appears up-to-date (e.g., when the design file is known to be stale but hashes have not changed). If the command fails, write an IWH signal noting the failure so the next person can investigate.

### When to Run `lexi design comment`

Run `lexi design comment <file> --body "..."` when changes affect:

- **Behavior** -- the file does something differently at runtime.
- **Contracts** -- function signatures, return types, or error handling changed.
- **Cross-file responsibilities** -- the change shifts work to or from other modules.

The archivist captures structure (signatures, imports, class hierarchy). Comments capture intent -- **why** a change was made, what trade-offs were considered, and how the change interacts with the rest of the system. Comments are appended to the design file and preserved across regeneration.

**Skip** `lexi design comment` for trivial or purely mechanical changes: renames, formatting, import reordering.

### When NOT to Update Manually

Let `lexictl update` handle updates instead when:

- **Cosmetic changes** -- formatting, whitespace, comment rewording.
- **Bulk refactors** -- renaming a variable across many files (the operator can regenerate all design files at once).

### What NOT to Modify Manually

Do not manually edit design files. Specifically, do not modify:

- **Design file body** -- the Summary, Interface Contract, and Key Details sections are managed by the archivist pipeline.
- **Frontmatter fields** -- do not set `updated_by` or other frontmatter values by hand.
- **Staleness metadata** -- the HTML comment block at the bottom containing `source`, `source_hash`, `interface_hash`, `design_hash`, `generated`, and `generator`.
- **Generated timestamps** and **source hashes** -- modifying these will confuse change detection.

### Example

After adding a new validation method to `src/lexibrary/config/schema.py`:

1. Run `lexi design update src/lexibrary/config/schema.py` to regenerate the design file.
2. Run `lexi design comment src/lexibrary/config/schema.py --body "Added validate_token_budget() to enforce ceiling on per-file token allocation."` to capture the rationale.

## update_file vs update_project

Lexibrary provides two pipeline entry points:

### update_project (full project update)

Invoked by `lexictl update` with no arguments:

1. Discovers all source files under `scope_root`.
2. Processes each file sequentially through the change detection and LLM pipeline.
3. Regenerates `TOPOLOGY.md` after all files are processed.
4. Performs a full rebuild of the link graph index.

### update_files (targeted file update)

Invoked by `lexictl update --changed-only <files>`:

1. Processes only the specified file paths (no file discovery).
2. Skips deleted, binary, ignored, and `.lexibrary/` files.
3. Does not regenerate `TOPOLOGY.md`.
4. Performs an incremental update of the link graph index.

This mode is designed for git hooks and CI where the set of changed files is already known.

## .aindex Refresh

After writing a design file, Lexibrary checks whether the parent directory has an `.aindex` routing table. If so, it updates the entry for the source file with the new description from the design file, keeping `.aindex` entries in sync with design file summaries.

## TOPOLOGY.md Regeneration

After a full project update, Lexibrary regenerates `.lexibrary/TOPOLOGY.md` via a separate BAML prompt that receives the project name, directory tree, and `.aindex` summaries. TOPOLOGY.md is not regenerated during `--changed-only` updates.

## Progress Reporting

During a full update, `lexictl update` displays a progress bar. After completion, a summary is printed:

```
Update summary:
  Files scanned:       42
  Files unchanged:     30
  Files created:        5
  Files updated:        4
  Files agent-updated:  3
  Files failed:         0
  .aindex refreshed:    3
  Token budget warnings: 1
```

## See Also

- [CLI Reference](cli-reference.md) -- Full command reference for `lexi design update`, `lexi design comment`, and `lexictl update`
- [Configuration](configuration.md) -- `crawl`, `llm`, `token_budgets`, `ignore`, and `scope_root` settings
- [Library Structure](library-structure.md) -- Anatomy of the `.lexibrary/` directory
- [Validation](validation.md) -- Checks that detect stale design files and token budget overruns
- [CI Integration](ci-integration.md) -- Using `--changed-only` in git hooks and CI pipelines
- [Link Graph](link-graph.md) -- How the SQLite index is built during `lexictl update`
- [Ignore Patterns](ignore-patterns.md) -- How files are filtered during discovery
