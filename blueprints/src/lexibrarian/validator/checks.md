# validator/checks

**Summary:** Individual validation check functions for library health, each following the `(project_root: Path, lexibrary_dir: Path) -> list[ValidationIssue]` signature. Checks are grouped by default severity: error (3), warning (4), info (6). The three link-graph checks (`bidirectional_deps`, `dangling_links`, `orphan_artifacts`) degrade gracefully when `index.db` is absent, corrupt, or has a schema version mismatch -- returning empty lists.

## Interface

### Error-Severity Checks

| Name | Signature | Purpose |
| --- | --- | --- |
| `check_wikilink_resolution` | `(project_root, lexibrary_dir) -> list[ValidationIssue]` | Parse design files and Stack posts for `[[wikilinks]]`, verify each resolves via `WikilinkResolver`; unresolved links produce errors with fuzzy-match suggestions |
| `check_file_existence` | `(project_root, lexibrary_dir) -> list[ValidationIssue]` | Verify `source_path` in design files, `refs.files` and `refs.designs` in Stack posts point to existing files |
| `check_concept_frontmatter` | `(project_root, lexibrary_dir) -> list[ValidationIssue]` | Validate all concept files have mandatory YAML frontmatter fields (`title`, `aliases`, `tags`, `status`) and valid `status` values |

### Warning-Severity Checks

| Name | Signature | Purpose |
| --- | --- | --- |
| `check_hash_freshness` | `(project_root, lexibrary_dir) -> list[ValidationIssue]` | Compare design file `source_hash` metadata against current SHA-256 of source files; mismatches produce warnings |
| `check_token_budgets` | `(project_root, lexibrary_dir) -> list[ValidationIssue]` | Count tokens via `ApproximateCounter` for START_HERE, HANDOFF, design files, concepts, and .aindex files; over-budget produces warnings |
| `check_orphan_concepts` | `(project_root, lexibrary_dir) -> list[ValidationIssue]` | Scan all artifacts for `[[wikilink]]` references; concepts with zero inbound references produce warnings |
| `check_deprecated_concept_usage` | `(project_root, lexibrary_dir) -> list[ValidationIssue]` | Find deprecated concepts still referenced by active artifacts; includes `superseded_by` in suggestion when available |

### Info-Severity Checks

| Name | Signature | Purpose |
| --- | --- | --- |
| `check_forward_dependencies` | `(project_root, lexibrary_dir) -> list[ValidationIssue]` | Parse design file `## Dependencies` sections; verify listed paths exist on disk |
| `check_stack_staleness` | `(project_root, lexibrary_dir) -> list[ValidationIssue]` | For Stack posts with `refs.files`, check if referenced files' design files have stale `source_hash` |
| `check_aindex_coverage` | `(project_root, lexibrary_dir) -> list[ValidationIssue]` | Walk `scope_root` directory tree; report directories lacking corresponding `.aindex` files |
| `check_bidirectional_deps` | `(project_root, lexibrary_dir) -> list[ValidationIssue]` | Compare design file `## Dependencies` lists against `ast_import` links in the link graph index; report mismatches in both directions (design lists dep not in graph, graph has link not in design file); returns empty list if index is absent/corrupt/version-mismatch |
| `check_dangling_links` | `(project_root, lexibrary_dir) -> list[ValidationIssue]` | Query all non-convention artifacts (`source`, `design`, `concept`, `stack`) from `index.db` and verify backing files exist on disk; returns empty list if index is absent/corrupt/version-mismatch |
| `check_orphan_artifacts` | `(project_root, lexibrary_dir) -> list[ValidationIssue]` | Query all non-convention artifacts from `index.db` and report entries whose backing files have been deleted; suggests rebuilding the index; returns empty list if index is absent/corrupt/version-mismatch |

## Internal Helpers

| Name | Purpose |
| --- | --- |
| `_WIKILINK_RE` | Regex to extract `[[wikilink]]` targets from markdown content |
| `_FRONTMATTER_RE` | Regex to match YAML frontmatter blocks (`---` delimited) |
| `_INDEX_DB_NAME` | Constant `"index.db"` -- filename of the SQLite index database within `.lexibrary/` |
| `_rel(path, root)` | Return relative path string, falling back to full path on error |
| `_iter_design_files(lexibrary_dir)` | Iterate design file paths, excluding START_HERE, HANDOFF, stack, and concepts |
| `_iter_directories(scope_root, project_root, lexibrary_dir)` | Recursive directory walker, skipping hidden dirs, `.lexibrary`, `node_modules`, `__pycache__`, `venv` |

## Dependencies

- `lexibrarian.artifacts.design_file_parser` -- `parse_design_file`, `parse_design_file_metadata`
- `lexibrarian.config.loader` -- `load_config` (for token budgets and scope_root)
- `lexibrarian.linkgraph.schema` -- `SCHEMA_VERSION`, `check_schema_version`, `set_pragmas` (for link-graph checks)
- `lexibrarian.stack.parser` -- `parse_stack_post`
- `lexibrarian.tokenizer.approximate` -- `ApproximateCounter`
- `lexibrarian.utils.hashing` -- `hash_file`
- `lexibrarian.utils.paths` -- `aindex_path`
- `lexibrarian.validator.report` -- `ValidationIssue`
- `lexibrarian.wiki.index` -- `ConceptIndex`
- `lexibrarian.wiki.resolver` -- `WikilinkResolver`, `UnresolvedLink`

## Dependents

- `lexibrarian.validator.__init__` -- imports all check functions into `AVAILABLE_CHECKS` registry
