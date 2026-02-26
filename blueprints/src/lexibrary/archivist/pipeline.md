# archivist/pipeline

**Summary:** Per-file and project-wide design file generation pipeline -- coordinates change detection, IWH signal awareness, conflict marker checks, design hash TOCTOU protection, LLM generation, atomic writes, serialization, parent .aindex refresh, automated index regeneration for affected directories, and link graph builds.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `UpdateStats` | `@dataclass` | Accumulated counters: `files_scanned`, `files_unchanged`, `files_agent_updated`, `files_updated`, `files_created`, `files_failed`, `aindex_refreshed`, `token_budget_warnings`, `topology_failed`, `linkgraph_built`, `linkgraph_error` |
| `FileResult` | `@dataclass` | Public result from `update_file`: `change`, `aindex_refreshed`, `token_budget_exceeded`, `failed` |
| `update_file` | `async (source_path, project_root, config, archivist, available_concepts?) -> FileResult` | Generate or update the design file for a single source file |
| `update_files` | `async (file_paths, project_root, config, archivist, progress_callback?) -> UpdateStats` | Process a specific list of source files (for git hooks / `--changed-only`); does NOT regenerate TOPOLOGY.md; re-indexes affected directories and ancestors after processing |
| `update_project` | `async (project_root, config, archivist, progress_callback?) -> UpdateStats` | Update all design files in the project scope; generates TOPOLOGY.md; re-indexes affected directories and ancestors; then runs full link graph rebuild |
| `reindex_directories` | `(directories: list[Path], project_root: Path, config: LexibraryConfig) -> int` | Regenerate `.aindex` files for a list of directories and their ancestors up to `scope_root`; returns number of directories re-indexed |

## Internal Functions

| Name | Purpose |
| --- | --- |
| `_is_within_scope` | Check whether a source path is under the configured `scope_root` |
| `_is_binary` | Check whether a file has a binary extension |
| `_estimate_tokens` | Rough token estimate by splitting on whitespace |
| `_refresh_footer_hashes` | Re-write only the metadata footer with current source hashes (for AGENT_UPDATED files) |
| `_refresh_parent_aindex` | Update the parent directory's `.aindex` Child Map entry with description |
| `_accumulate_stats` | Update `UpdateStats` in-place from a single `FileResult` |
| `_has_meaningful_changes` | Return True if any files were created, updated, or failed; used to decide whether to run post-pipeline re-indexing |

## Dependencies

- `lexibrary.archivist.change_checker` -- `ChangeLevel`, `check_change`, `_compute_design_content_hash`
- `lexibrary.archivist.dependency_extractor` -- `extract_dependencies`
- `lexibrary.archivist.service` -- `ArchivistService`, `DesignFileRequest`
- `lexibrary.archivist.topology` -- `generate_topology`
- `lexibrary.artifacts.aindex` -- `AIndexEntry`
- `lexibrary.artifacts.aindex_parser` -- `parse_aindex`
- `lexibrary.artifacts.aindex_serializer` -- `serialize_aindex`
- `lexibrary.artifacts.design_file` -- `DesignFile`, `DesignFileFrontmatter`, `StalenessMetadata`
- `lexibrary.artifacts.design_file_parser` -- `parse_design_file`, `parse_design_file_frontmatter`, `parse_design_file_metadata`, `_FOOTER_RE`
- `lexibrary.artifacts.design_file_serializer` -- `serialize_design_file`
- `lexibrary.ast_parser` -- `compute_hashes`, `parse_interface`, `render_skeleton`
- `lexibrary.config.schema` -- `LexibraryConfig`
- `lexibrary.ignore` -- `create_ignore_matcher`
- `lexibrary.indexer.orchestrator` -- `index_directory` (used by `reindex_directories`)
- `lexibrary.linkgraph.builder` -- `build_index` (full and incremental link graph index builds)
- `lexibrary.utils.atomic` -- `atomic_write` (replaces all `Path.write_text()` calls)
- `lexibrary.utils.conflict` -- `has_conflict_markers`
- `lexibrary.utils.languages` -- `detect_language`
- `lexibrary.utils.paths` -- `LEXIBRARY_DIR`, `aindex_path`, `mirror_path`, `iwh_path` (aliased as `_iwh_path` to avoid collision)
- `lexibrary.wiki.index` -- `ConceptIndex`
- `lexibrary.iwh.reader` -- `read_iwh` (lazy import in `update_file` for IWH awareness check)

## Dependents

- `lexibrary.cli.lexictl_app` -- `update` command calls `update_file`, `update_files`, and `update_project`
- `lexibrary.daemon.service` -- `_run_sweep` calls `update_project`

## Key Concepts

- `update_file` pipeline: scope check, IWH check, compute hashes, change detection, then branch on `ChangeLevel`:
  - **IWH awareness** (step 1b, between scope check and hash computation): when `config.iwh.enabled` is True, reads the IWH signal for the source directory using `read_iwh()` (non-consuming — archivist doesn't delete signals); `blocked` scope → log warning + skip (return `FileResult(change=UNCHANGED)`); `incomplete` scope → log info + proceed; `warning` scope → no special handling; imports aliased as `_iwh_path` to avoid collision with local names
  - `UNCHANGED` -- early return
  - `AGENT_UPDATED` -- refresh footer hashes only (no LLM call), preserve agent edits
  - Others -- conflict marker check, LLM generation, design hash re-check, build model, serialize, atomic write, refresh parent `.aindex`
- **Conflict marker check** (safety): before LLM generation, calls `has_conflict_markers(source_path)`; if markers found, returns `FileResult(failed=True)` to skip the file
- **Design hash re-check** (TOCTOU protection, D-061): captures `pre_llm_design_hash` before LLM call; after generation, re-reads the design file hash; if it changed (agent edited during generation), discards the LLM output
- **Atomic writes**: all file writes use `atomic_write()` instead of `Path.write_text()` to prevent partial writes
- `update_files` processes a caller-provided list of files; skips deleted, binary, ignored, and `.lexibrary/` files; does NOT discover files or generate TOPOLOGY.md; after processing, re-indexes affected directories via `reindex_directories()` (skipped when no meaningful changes); then runs an incremental link graph update via `build_index(project_root, changed_paths=...)` passing both processed and deleted paths for CASCADE cleanup
- `update_project` discovers files via `rglob("*")`, skips `.lexibrary/`, binary, ignored, and oversized files, processes each sequentially, generates TOPOLOGY.md (procedural, no LLM), re-indexes affected directories via `reindex_directories()` (skipped when no meaningful changes), then runs a full link graph rebuild via `build_index(project_root)`
- **Automated index regeneration**: `reindex_directories()` takes a list of directories, walks each up to `scope_root` to collect ancestor directories, deduplicates, sorts deepest-first (so child `.aindex` data is available when parents are indexed), and calls `index_directory()` for each; uses the same indexer as `lexictl index` for consistent output
- **Skip-when-no-changes**: `_has_meaningful_changes()` returns False when `files_created + files_updated + files_failed == 0`, causing both `update_files` and `update_project` to skip re-indexing when nothing actually changed
- **Link graph integration**: both `update_files` and `update_project` call `build_index()` as their final step; errors are caught and logged (never block pipeline stats), recorded in `stats.linkgraph_error`; success sets `stats.linkgraph_built = True`
- Token budget validation: warns if design file exceeds `config.token_budgets.design_file_tokens` but still writes the file
- Parent `.aindex` refresh: updates the child map entry description when a design file is created or updated
