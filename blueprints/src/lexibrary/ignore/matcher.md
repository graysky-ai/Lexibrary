# ignore/matcher

**Summary:** `IgnoreMatcher` combines config patterns, hierarchical `.gitignore` specs, and `.lexignore` patterns via pathspec to decide whether files/directories should be ignored or descended into.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `IgnoreMatcher` | class | Unified ignore checker for files and directories |
| `IgnoreMatcher.__init__` | `(root: Path, config_spec: PathSpec, gitignore_specs: list[tuple[Path, PathSpec]], lexignore_patterns: list[str] \| None = None)` | Accept pre-built specs plus optional `.lexignore` patterns |
| `IgnoreMatcher.is_ignored` | `(path: Path) -> bool` | True if path matches any ignore pattern (config, gitignore, or lexignore) |
| `IgnoreMatcher.should_descend` | `(directory: Path) -> bool` | True if directory should be traversed (inverse of ignored) |

## Dependencies

- `pathspec` (third-party)

## Dependents

- `lexibrarian.ignore.__init__` -- `create_ignore_matcher` instantiates this
- `lexibrarian.crawler.discovery` -- passes to traversal functions
- `lexibrarian.daemon.watcher` -- used to filter events
- `lexibrarian.archivist.pipeline` -- `update_project` uses ignore matcher for file discovery
- `lexibrarian.archivist.start_here` -- directory tree builder uses ignore matcher

## Key Concepts

- Three-layer pattern matching: config patterns (cheap, checked first), `.gitignore` specs (hierarchical, most specific first), `.lexignore` patterns (project-level archivist exclusions)
- `.lexignore` patterns compiled to a `PathSpec` in `__init__` from the `lexignore_patterns` list
- Directory paths use trailing slash for pathspec directory matching
- `"gitignore"` pattern style -- NOT `"gitwildmatch"`
