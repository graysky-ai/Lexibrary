# stack/index

**Summary:** In-memory searchable index of Stack posts — scans `.lexibrary/stack/` and provides search + filter methods.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `StackIndex` | `class` | In-memory index of all Stack posts |
| `StackIndex.build` | `classmethod (project_root: Path) -> StackIndex` | Scan `.lexibrary/stack/ST-*-*.md` files, parse each, build index; malformed files silently skipped |
| `StackIndex.search` | `(query: str) -> list[StackPost]` | Case-insensitive substring search across titles, problems, answers, and tags; results sorted by votes descending |
| `StackIndex.by_tag` | `(tag: str) -> list[StackPost]` | Filter posts by tag (case-insensitive) |
| `StackIndex.by_scope` | `(path: str) -> list[StackPost]` | Filter posts by referenced file path prefix in `refs.files` |
| `StackIndex.by_status` | `(status: str) -> list[StackPost]` | Filter posts by status value |
| `StackIndex.by_concept` | `(concept: str) -> list[StackPost]` | Filter posts referencing a concept name (case-insensitive) |
| `__len__` | `-> int` | Number of posts in the index |
| `__iter__` | `-> Iterator[StackPost]` | Iterate over all posts |

## Dependencies

- `lexibrarian.stack.models` -- `StackPost`
- `lexibrarian.stack.parser` -- `parse_stack_post`

## Dependents

- `lexibrarian.cli` -- `stack_search`, `stack_list` commands
- `lexibrarian.search` -- `_search_stack_posts()` builds a `StackIndex`

## Key Concepts

- Posts are loaded eagerly on `build()` — all `ST-*-*.md` files in `.lexibrary/stack/` are parsed and held in memory
- Search is substring-based, not fuzzy; results sorted by vote count descending
- `by_scope` uses prefix matching on `refs.files` — a post matches if any referenced file starts with the given path
