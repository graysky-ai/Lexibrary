# cli/lexi_app

**Summary:** Agent-facing Typer CLI app (`lexi`) providing lookups, validation, status, describe, concepts, Stack Q&A, IWH signal management, and cross-artifact search for LLM context navigation.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `lexi_app` | `typer.Typer` | Root agent-facing CLI application registered as the `lexi` entry point; uses `load_dotenv_if_configured` as its Typer callback for dotenv startup loading |
| `stack_app` | `typer.Typer` | Sub-group for `lexi stack *` commands (post, search, answer, vote, accept, view, list) |
| `concept_app` | `typer.Typer` | Sub-group for `lexi concept *` commands (new, link) |
| `iwh_app` | `typer.Typer` | Sub-group for `lexi iwh *` commands (write, read, list) |
| `lookup` | `(file: Path) -> None` | Display design file for a source file; checks scope, warns if stale, shows inherited conventions, shows reverse links from link graph |
| `describe` | `(directory: Path, description: str) -> None` | Update the billboard description in a directory's `.aindex` file |
| `validate` | `(*, severity: str \| None, check: str \| None, json_output: bool) -> None` | Thin wrapper calling `_run_validate()` with `--severity`, `--check`, and `--json` options |
| `status` | `(path: Path \| None, *, quiet: bool) -> None` | Thin wrapper calling `_run_status(cli_prefix="lexi")` with `[path]` argument and `--quiet` flag |
| `concepts` | `(topic: str \| None, *, tag: list[str] \| None, status: str \| None, show_all: bool) -> None` | List or search concept files in a Rich table; supports `--tag` (repeatable, AND logic), `--status` (`active`/`draft`/`deprecated`), and `--all` (include deprecated) filters |
| `agent_help` | `() -> None` | Display structured guidance for coding agents via Rich panels; registered as `lexi help`; does not require a project root |
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
| `iwh_write` | `(directory: Path \| None, *, scope: str, body: str, author: str) -> None` | Write an IWH signal for a directory; flags: `--scope/-s` (default `"incomplete"`), `--body/-b` (required), `--author` (default `"agent"`); validates scope against `{warning, incomplete, blocked}`; exits if IWH disabled in config; uses `iwh_path()` + `write_iwh()` |
| `iwh_read` | `(directory: Path \| None, *, peek: bool) -> None` | Read (and consume) an IWH signal for a directory; `--peek` flag reads without deleting; defaults to consume via `consume_iwh()`; exits if IWH disabled in config |
| `iwh_list` | `() -> None` | List all IWH signals in the project; calls `find_all_iwh()`, renders Rich table with directory, scope, author, age, and body preview columns; exits if IWH disabled in config |

## Internal Functions

| Name | Purpose |
| --- | --- |
| `_stack_dir` | Return `.lexibrary/stack/` directory, creating it if needed (D2: stays in lexi_app, not shared) |
| `_next_stack_id` | Scan existing `ST-NNN-*.md` files and return the next available number |
| `_slugify` | Convert a title to a URL-friendly slug (lowercase, max 50 chars) |
| `_find_post_path` | Resolve a post ID (e.g. `ST-001`) to its file path by globbing the stack directory |

## Dependencies

- `lexibrary.cli._shared` -- `console`, `load_dotenv_if_configured`, `require_project_root`, `_run_validate`, `_run_status`
- `lexibrary.exceptions` -- `LexibraryNotFoundError` (top-level import for `lookup`, `describe`)
- `lexibrary.utils.root` -- `find_project_root` (top-level import for `lookup`, `describe`)
- `lexibrary.config.loader` -- `load_config` (lazy import)
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
- `lexibrary.iwh` -- `write_iwh`, `consume_iwh`, `read_iwh` (lazy imports in `iwh_write`, `iwh_read`)
- `lexibrary.iwh.reader` -- `find_all_iwh` (lazy import in `iwh_list`)
- `lexibrary.utils.paths` -- `iwh_path` (lazy import in `iwh_write`, `iwh_read`)

## Dependents

- `lexibrary.cli.__init__` -- re-exports `lexi_app`
- `pyproject.toml` -- `lexi` entry point
- `lexibrary.__main__` -- runs `lexi_app` for `python -m lexibrary`

## Key Concepts

- `lexi_app` registers `load_dotenv_if_configured` as its Typer `callback`, which runs before any command; when `llm.api_key_source` is `"dotenv"` in the project config, it calls `load_dotenv(project_root / ".env", override=False)` so that env vars already set in the shell take precedence; silently handles missing project root or `.env` file
- All commands are fully implemented; no stubs in `lexi_app`
- The `index` command has been removed from `lexi` and moved to `lexictl`; `lexi` is now purely agent-facing with no indexing commands
- `validate` and `status` are thin wrappers that call shared helpers `_run_validate()` and `_run_status()` in `_shared.py`; `status` passes `cli_prefix="lexi"` so quiet-mode output reads `"lexi: ..."` instead of `"lexictl: ..."`
- `concepts` hides deprecated concepts by default (D-3); pass `--all` to include them or `--status deprecated` to show only deprecated; `--tag` is repeatable and uses AND logic across tags; `--status` validates against `{active, draft, deprecated}`; all filters combine with AND logic when used together (D-4); status filtering is inline (no `ConceptIndex.by_status()` method) per D-5
- `agent_help` is registered as `lexi help` via `@lexi_app.command("help")` (D-2); it renders three Rich panels: Available Commands (grouped into Lookup & Navigation, Concepts & Knowledge, Stack Q&A, Inspection & Annotation), Common Workflows (4 workflows including "Check library health"), and Navigation Tips; it does not call `require_project_root()` so it works outside any project
- Cross-reference messages direct maintenance actions to `lexictl` (e.g. `"Run lexictl update ..."` in `lookup` and `concept_link`)
- Stack helpers (`_stack_dir`, `_next_stack_id`, `_slugify`, `_find_post_path`) are private to this module per design decision D2
- All heavy imports are lazy (inside command functions) to keep CLI startup fast
- Stack post IDs are auto-assigned by scanning `.lexibrary/stack/ST-*-*.md` files and incrementing
- `lookup` walks parent `.aindex` files upward to show inherited local conventions
- `lookup` opens the link graph via `open_index()` and displays reverse links in two sections: "Dependents (imports this file)" for `ast_import` links, and "Also Referenced By" for all other link types (wikilinks, stack refs, etc.) with human-readable labels; both sections are silently omitted when the index is unavailable or the file has no inbound links (graceful degradation)
- `search` opens the link graph via `open_index()` and passes it to `unified_search()` for index-accelerated tag and FTS queries; closes the graph in a `finally` block; falls back to file scanning when the index is unavailable
- `iwh_app` is a Typer sub-group registered as `lexi iwh`; all three IWH commands check `config.iwh.enabled` and exit early with a warning if disabled
- `iwh_write` validates scope against `{warning, incomplete, blocked}` and uses `iwh_path()` to map the source directory to the `.lexibrary/` mirror location before calling `write_iwh()`
- `iwh_list` computes human-readable age strings (minutes/hours/days) from `IWHFile.created` timestamps
- Updated `lexi help` output includes an "IWH Signals" section documenting `lexi iwh write`, `lexi iwh read`, and `lexi iwh list`

## Dragons

- Stack ID auto-assignment uses filesystem scan -- concurrent creation could cause ID collision (mitigated by single-agent use case)
- `lookup` staleness check computes SHA-256 of the source file and compares against `metadata.source_hash`
- `concept_link` error message for missing concepts shows available concept names, but only if concepts exist
- `agent_help` output is static text -- if commands are added or removed, the help panels must be manually updated to stay in sync
