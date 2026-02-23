# Design File Generation

This guide explains how `lexictl update` works end-to-end -- from discovering source files to writing design files and rebuilding the link graph index.

## Overview

When you run `lexictl update`, Lexibrary:

1. Discovers all source files under `scope_root`.
2. Filters out binary files, ignored files, and oversized files.
3. Compares each file's SHA-256 hash against the hash stored in its existing design file.
4. Classifies the type of change (unchanged, agent-updated, content-only, content-changed, interface-changed, new file).
5. Sends files that need updating to the configured LLM for design file generation.
6. Writes design files into the `.lexibrary/` mirror tree.
7. Refreshes parent `.aindex` routing tables.
8. Regenerates `START_HERE.md` with the updated project topology.
9. Builds or rebuilds the link graph index.

## File Discovery

`lexictl update` scans the configured `scope_root` directory (default: `.`, the project root) recursively using `rglob("*")`. Files are filtered at three levels:

- **Ignore matching** -- Files matching any ignore pattern (from `.gitignore`, `.lexignore`, or `ignore.additional_patterns` in config) are skipped. See [Ignore Patterns](ignore-patterns.md) for details.
- **Binary detection** -- Files with extensions listed in `crawl.binary_extensions` are skipped. The default list covers images, audio/video, fonts, archives, documents, executables, compiled objects, and database files.
- **Size limit** -- Files larger than `crawl.max_file_size_kb` (default: 512 KB) are skipped.
- **Scope boundary** -- Files outside the `scope_root` directory are excluded.
- **Library contents** -- Files inside `.lexibrary/` are never processed as source files.

After filtering, remaining files are sorted by path for deterministic processing order.

## Change Detection

For each discovered source file, Lexibrary computes a SHA-256 hash of the file content and (for code files with supported languages) a separate hash of the public interface extracted via AST parsing. These hashes are compared against the metadata footer stored in the existing design file.

### ChangeLevel Classification

Every source file is classified into one of six change levels:

| ChangeLevel | Meaning | Action Taken |
|---|---|---|
| `UNCHANGED` | Source hash matches the stored hash | No action -- file is skipped |
| `AGENT_UPDATED` | An agent has edited the design file body since the last generation | Footer hashes are refreshed, but the LLM is **not** called (preserves agent edits) |
| `CONTENT_ONLY` | Source content changed but the public interface (function signatures, class definitions) did not | LLM is called to regenerate |
| `CONTENT_CHANGED` | Source content changed (non-code file, or no interface hash available) | LLM is called to regenerate |
| `INTERFACE_CHANGED` | The public interface of the source file changed | LLM is called to regenerate |
| `NEW_FILE` | No design file exists for this source file | LLM is called to generate a new design file |

### How Agent Edits Are Detected

Lexibrary stores a `design_hash` in the metadata footer of each design file. This hash covers the frontmatter and body (excluding the footer itself). When an agent manually edits the design file body, the computed hash of the current design file content will differ from the stored `design_hash`, triggering the `AGENT_UPDATED` classification. This ensures that agent edits are never overwritten by LLM regeneration.

### Conflict Marker Check

Before sending a file to the LLM, Lexibrary checks for unresolved merge conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`). Files containing conflict markers are skipped and counted as failed.

## LLM Generation Pipeline

Files classified as `NEW_FILE`, `CONTENT_ONLY`, `CONTENT_CHANGED`, or `INTERFACE_CHANGED` are sent to the LLM for design file generation.

### Request Preparation

For each file, Lexibrary prepares a `DesignFileRequest` containing:

- **source_path** -- The project-relative path (e.g., `src/auth/service.py`).
- **source_content** -- The full text content of the source file.
- **interface_skeleton** -- For code files with AST support, a rendered skeleton of public interfaces (function signatures, class definitions). `None` for non-code files.
- **language** -- The detected programming language (e.g., `python`, `typescript`). `None` for non-code files.
- **existing_design_file** -- The full text of the current design file, if one exists (provides context for updates).
- **available_concepts** -- A list of all concept names in the project's concepts directory, used to guide wikilink generation.

### ArchivistService

The `ArchivistService` routes requests through BAML prompt definitions to the configured LLM provider. It:

1. Acquires a rate limiter token before each call.
2. Selects the correct BAML client based on the configured provider (Anthropic or OpenAI).
3. Calls the `ArchivistGenerateDesignFile` BAML function.
4. Returns a `DesignFileResult` with the generated content, or an error result on failure.

Errors are caught and returned as error results -- the service never raises exceptions to the caller.

### TOCTOU Protection

To prevent a race condition where an agent edits a design file while the LLM is generating, Lexibrary captures the `design_hash` before sending the request. After the LLM returns, it re-checks the hash. If the design file was modified during generation, the LLM output is discarded and the file is treated as `AGENT_UPDATED`.

## Design File Structure

Each generated design file is a Markdown file with:

- **Frontmatter** -- YAML block with `description` and `updated_by` fields.
- **Summary** -- A concise description of what the source file does.
- **Interface Contract** -- For code files, the public API surface (function signatures, class definitions, exported symbols).
- **Dependencies** -- Project-relative paths of files this source imports or depends on.
- **Dependents** -- (Populated by the link graph) Files that import this source.
- **Wikilinks** -- References to relevant concepts using `[[concept-name]]` syntax.
- **Tags** -- Categorization tags for search and filtering.
- **Metadata Footer** -- An HTML comment block containing `source_hash`, `interface_hash`, `design_hash`, `generated` timestamp, and `generator` identifier.

### Mirror Tree

Design files are stored in a mirror tree under `.lexibrary/` that matches the project directory structure. For example:

```
src/auth/service.py       -->  .lexibrary/src/auth/service.py.md
src/utils/helpers.py      -->  .lexibrary/src/utils/helpers.py.md
tests/test_auth.py        -->  .lexibrary/tests/test_auth.py.md
```

Parent directories are created automatically as needed.

## update_file vs update_project

Lexibrary provides two pipeline entry points:

### update_project (full project update)

Invoked by `lexictl update` with no arguments. This:

1. Discovers all source files under `scope_root`.
2. Processes each file sequentially through the change detection and LLM pipeline.
3. Regenerates `START_HERE.md` after all files are processed.
4. Performs a **full rebuild** of the link graph index.

### update_files (targeted file update)

Invoked by `lexictl update --changed-only <files>`. This:

1. Processes only the specified file paths (no file discovery).
2. Skips deleted, binary, ignored, and `.lexibrary/` files.
3. Does **not** regenerate `START_HERE.md`.
4. Performs an **incremental update** of the link graph index (only re-indexes the changed files).

This mode is designed for git hooks and CI where you already know which files changed.

## --changed-only Mode

The `--changed-only` flag is designed for use with git hooks:

```bash
lexictl update --changed-only path/to/file1.py path/to/file2.py
```

This processes only the specified files, making it much faster than a full project update. It is used by the post-commit hook installed via `lexictl setup --hooks`. The hook automatically passes the list of files changed in the most recent commit.

Key differences from a full update:

- No file discovery -- processes only the listed files.
- No `START_HERE.md` regeneration.
- Incremental link graph update instead of full rebuild.
- Handles deleted file paths gracefully (cleans up link graph entries via CASCADE).

## Token Budget Validation

After generating a design file, Lexibrary estimates the token count using a whitespace-splitting heuristic. If the count exceeds the `token_budgets.design_file_tokens` limit (default: 400 tokens), a warning is logged. The design file is still written even when over budget -- the warning is informational and surfaced by `lexictl validate`.

## START_HERE.md Regeneration

After a full project update, Lexibrary regenerates `.lexibrary/START_HERE.md`. This file provides:

- A project topology overview (directory tree).
- Summaries from `.aindex` routing tables.
- Navigation guidance for agents starting a new session.

The content is generated via a separate BAML prompt (`ArchivistGenerateStartHere`) that receives the project name, directory tree, and `.aindex` summaries.

`START_HERE.md` is **not** regenerated during `--changed-only` updates.

## .aindex Refresh

After writing a design file, Lexibrary checks whether the parent directory has an `.aindex` routing table. If so, it updates (or adds) the entry for the source file with the new description from the design file. This keeps `.aindex` Child Map entries in sync with design file summaries.

## Progress Reporting

During a full update, `lexictl update` displays progress via a Rich console progress bar. After completion, a summary is printed:

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

### UpdateStats Fields

| Field | Description |
|---|---|
| `files_scanned` | Total files examined |
| `files_unchanged` | Files with matching hashes (no action needed) |
| `files_agent_updated` | Files where agent edits were preserved |
| `files_updated` | Files regenerated by the LLM |
| `files_created` | New files generated by the LLM |
| `files_failed` | Files that failed (LLM error, conflict markers, etc.) |
| `aindex_refreshed` | `.aindex` entries updated |
| `token_budget_warnings` | Design files exceeding their token budget |
| `start_here_failed` | Whether `START_HERE.md` regeneration failed |
| `linkgraph_built` | Whether the link graph was successfully built |
| `linkgraph_error` | Error message if link graph build failed |

## Related Documentation

- [Configuration](configuration.md) -- `crawl`, `llm`, `token_budgets`, `ignore`, and `scope_root` settings
- [Library Structure](library-structure.md) -- Anatomy of the `.lexibrary/` directory
- [Validation](validation.md) -- Checks that detect stale design files and token budget overruns
- [CI Integration](ci-integration.md) -- Using `--changed-only` in git hooks and CI pipelines
- [Link Graph](link-graph.md) -- How the SQLite index is built during `lexictl update`
- [Ignore Patterns](ignore-patterns.md) -- How files are filtered during discovery
- [Agent Update Workflow](../agent/update-workflow.md) -- How agents update design files after editing source code
- [Agent Lookup Workflow](../agent/lookup-workflow.md) -- How agents use design files before editing
