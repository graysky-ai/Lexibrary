# archivist/start_here

**Summary:** Generates `.lexibrary/START_HERE.md` from project directory tree and .aindex billboard summaries via LLM.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `generate_start_here` | `async (project_root, config, archivist) -> Path` | Build directory tree, collect .aindex summaries, call LLM, assemble and write START_HERE.md |

## Dependencies

- `lexibrarian.archivist.service` -- `ArchivistService`, `StartHereRequest`
- `lexibrarian.artifacts.aindex_parser` -- `parse_aindex`
- `lexibrarian.config.schema` -- `LexibraryConfig`
- `lexibrarian.ignore` -- `create_ignore_matcher`
- `lexibrarian.utils.paths` -- `LEXIBRARY_DIR`

## Dependents

- `lexibrarian.cli` -- `update` command calls `generate_start_here` when no path argument given

## Key Concepts

- Directory tree builder excludes `.lexibrary/`, `.git/`, and ignored directories; produces ASCII tree with `+--` / `|` connectors
- Collects billboard summaries from all `.aindex` files in `.lexibrary/` mirror tree
- Reads existing `START_HERE.md` for continuity and passes it to the LLM
- `StartHereOutput` sections: `topology`, `ontology`, `navigation_by_intent`, `convention_index`, `navigation_protocol`
- Token budget validation: warns if output exceeds `config.token_budgets.start_here_tokens` but still writes
- Raises `RuntimeError` on LLM failure (unlike `ArchivistService` which returns error results)
