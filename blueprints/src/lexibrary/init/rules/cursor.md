# init/rules/cursor

**Summary:** Cursor environment rule generator -- produces `.cursor/rules/lexibrarian.mdc` (MDC format with YAML frontmatter) and `.cursor/skills/lexi.md` (combined orient and search skills).

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `generate_cursor_rules` | `(project_root: Path) -> list[Path]` | Create/overwrite `.cursor/rules/lexibrarian.mdc` and `.cursor/skills/lexi.md`; returns list of created file paths |

## Dependencies

- `lexibrarian.init.rules.base` -- `get_core_rules`, `get_orient_skill_content`, `get_search_skill_content`

## Dependents

- `lexibrarian.init.rules.__init__` -- registered in `_GENERATORS` dict as `"cursor"`

## Key Concepts

- No marker-based management needed: Cursor scans dedicated directories, so files are standalone and overwritten on each generation
- MDC file uses YAML frontmatter with `description`, `globs` (empty), `alwaysApply: true`
- Skills file combines orient and search skills into a single markdown file
- Creates `.cursor/rules/` and `.cursor/skills/` directory trees if they do not exist
