# init/rules/codex

**Summary:** Codex (OpenAI) environment rule generator -- produces `AGENTS.md` with marker-delimited Lexibrarian section containing core rules plus embedded orient and search skills.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `generate_codex_rules` | `(project_root: Path) -> list[Path]` | Create/update `AGENTS.md` (marker-based append or replace) with combined core rules + orient + search skills; returns list of created/updated file paths |

## Dependencies

- `lexibrarian.init.rules.base` -- `get_core_rules`, `get_orient_skill_content`, `get_search_skill_content`
- `lexibrarian.init.rules.markers` -- `has_lexibrarian_section`, `replace_lexibrarian_section`, `append_lexibrarian_section`

## Dependents

- `lexibrarian.init.rules.__init__` -- registered in `_GENERATORS` dict as `"codex"`

## Key Concepts

- Unlike Claude Code (which uses separate command files), Codex receives all instructions in a single `AGENTS.md` file
- The section content combines core rules, orient skill, and search skill into one marker-delimited block
- Uses the same marker-based approach as Claude: existing user content outside markers is preserved
- Only produces one file (vs Claude's three) since Codex reads `AGENTS.md` from the project root
