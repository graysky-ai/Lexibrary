# init/rules/generic

**Summary:** Generic environment rule generator -- produces `LEXIBRARY_RULES.md` at the project root with core rules plus embedded orient and search skills. For agents without first-class Lexibrary integration.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `generate_generic_rules` | `(project_root: Path) -> list[Path]` | Create/overwrite `LEXIBRARY_RULES.md` with combined core rules + orient + search skills; returns list of created/updated file paths |

## Dependencies

- `lexibrary.init.rules.base` -- `get_core_rules`, `get_orient_skill_content`, `get_search_skill_content`

## Dependents

- `lexibrary.init.rules.__init__` -- registered in `_GENERATORS` dict as `"generic"`

## Key Concepts

- Unlike Claude/Codex which use marker-based sections in shared files, generic produces a standalone `LEXIBRARY_RULES.md` that is fully Lexibrary-owned
- File is overwritten on each generation (no marker management needed)
- Suitable for any AI coding agent that can be pointed to a markdown file
- Only produces one file with all rules and skills combined
