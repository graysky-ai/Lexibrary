# cli/lexi_app

**Summary:** Agent-facing Typer CLI app (`lexi`) providing lookups, indexing, describe, concepts, Stack Q&A, and cross-artifact search for LLM context navigation.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `lexi_app` | `typer.Typer` | Root agent-facing CLI application registered as the `lexi` entry point |
| `stack_app` | `typer.Typer` | Sub-group for `lexi stack *` commands (post, search, answer, vote, accept, view, list) |
| `concept_app` | `typer.Typer` | Sub-group for `lexi concept *` commands (new, link) |
| `lookup` | `(file: Path) -> None` | Display design file for a source file; checks scope, warns if stale, shows inherited conventions, shows reverse links from link graph |
| `index` | `(directory: Path = ".", *, recursive: bool) -> None` | Generate `.aindex` for a directory; `-r` flag triggers bottom-up recursive indexing |
| `describe` | `(directory: Path, description: str) -> None` | Update the billboard description in a directory's `.aindex` file |
| `concepts` | `(topic: str \| None) -> None` | List or search concept files in a Rich table |
| `concept_new` | `(name, *, tag) -> None` | Create a new concept file from template |
| `concept_link` | `(concept_name, source_file) -> None` | Add a wikilink to a source file's design file |
| `stack_post` | `(*, title, tag, bead, file, concept) -> None` | Create a new Stack post with auto-assigned ST-NNN ID, slug filename |
| `stack_search` | `(query, *, tag, scope, status, concept) -> None` | Search Stack posts by query with optional filters |
| `stack_answer` | `(post_id, *, body, author) -> None` | Append a new answer to a Stack post |
| `stack_vote` | `(post_id, direction, *, answer, comment, author) -> None` | Record up/downvote on post or answer; downvotes require `--comment` |
| `stack_accept` | `(post_id, *, answer_num) -> None` | Mark answer as accepted, set post status to resolved |
| `stack_view` | `(post_id) -> None` | Display full post with Rich formatting (Panel header, Markdown body, answers, comments) |
| `stack_list` | `(*, status, tag) -> None` | List Stack posts in a Rich table with optional status/tag filters |
| `search` | `(query: str \| None, *, tag, scope) -> None` | Unified cross-artifact search via `unified_search()`; opens link graph for index-accelerated search with fallback to file scanning |

## Internal Functions

| Name | Purpose |
| --- | --- |
| `_stack_dir` | Return `.lexibrary/stack/` directory, creating it if needed (D2: stays in lexi_app, not shared) |
| `_next_stack_id` | Scan existing `ST-NNN-*.md` files and return the next available number |
| `_slugify` | Convert a title to a URL-friendly slug (lowercase, max 50 chars) |
| `_find_post_path` | Resolve a post ID (e.g. `ST-001`) to its file path by globbing the stack directory |

## Dependencies

- `lexibrary.cli._shared` -- `console`, `require_project_root`
- `lexibrary.config.loader` -- `load_config` (lazy import)
- `lexibrary.indexer.orchestrator` -- `index_directory`, `index_recursive` (lazy import)
- `lexibrary.artifacts.design_file_parser` -- `parse_design_file_metadata`, `parse_design_file` (lazy imports)
- `lexibrary.artifacts.design_file_serializer` -- `serialize_design_file` (lazy import in `concept_link`)
- `lexibrary.artifacts.aindex_parser` -- `parse_aindex` (lazy import in `describe`, `lookup`)
- `lexibrary.artifacts.aindex_serializer` -- `serialize_aindex` (lazy import in `describe`)
- `lexibrary.utils.paths` -- `mirror_path`, `aindex_path` (lazy imports)
- `lexibrary.wiki.index` -- `ConceptIndex` (lazy import in `concepts`, `concept_link`)
- `lexibrary.wiki.template` -- `render_concept_template`, `concept_file_path` (lazy import in `concept_new`)
- `lexibrary.stack.template` -- `render_post_template` (lazy import in `stack_post`)
- `lexibrary.stack.index` -- `StackIndex` (lazy import in `stack_search`, `stack_list`)
- `lexibrary.stack.mutations` -- `add_answer`, `record_vote`, `accept_answer` (lazy imports)
- `lexibrary.stack.parser` -- `parse_stack_post` (lazy import in `stack_view`)
- `lexibrary.search` -- `unified_search` (lazy import in `search`)
- `lexibrary.linkgraph` -- `open_index` (lazy import in `lookup` and `search`)

## Dependents

- `lexibrary.cli.__init__` -- re-exports `lexi_app`
- `pyproject.toml` -- `lexi` entry point
- `lexibrary.__main__` -- runs `lexi_app` for `python -m lexibrary`

## Key Concepts

- All commands are fully implemented; no stubs in `lexi_app`
- Cross-reference messages direct maintenance actions to `lexictl` (e.g. `"Run lexictl update ..."` in `lookup` and `concept_link`)
- Stack helpers (`_stack_dir`, `_next_stack_id`, `_slugify`, `_find_post_path`) are private to this module per design decision D2
- All heavy imports are lazy (inside command functions) to keep CLI startup fast
- Stack post IDs are auto-assigned by scanning `.lexibrary/stack/ST-*-*.md` files and incrementing
- `lookup` walks parent `.aindex` files upward to show inherited local conventions
- `lookup` opens the link graph via `open_index()` and displays reverse links in two sections: "Dependents (imports this file)" for `ast_import` links, and "Also Referenced By" for all other link types (wikilinks, stack refs, etc.) with human-readable labels; both sections are silently omitted when the index is unavailable or the file has no inbound links (graceful degradation)
- `search` opens the link graph via `open_index()` and passes it to `unified_search()` for index-accelerated tag and FTS queries; closes the graph in a `finally` block; falls back to file scanning when the index is unavailable

## Dragons

- `index` validates that the target directory exists, is a directory, and is within the project root before proceeding
- Stack ID auto-assignment uses filesystem scan -- concurrent creation could cause ID collision (mitigated by single-agent use case)
- `lookup` staleness check computes SHA-256 of the source file and compares against `metadata.source_hash`
- `concept_link` error message for missing concepts shows available concept names, but only if concepts exist
