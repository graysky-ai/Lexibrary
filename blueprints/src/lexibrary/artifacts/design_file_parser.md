# artifacts/design_file_parser

**Summary:** Parses design file markdown artifacts from disk into `DesignFile`, `StalenessMetadata`, or `DesignFileFrontmatter` models. Three entry points — full parse, metadata-only, or frontmatter-only.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `parse_design_file` | `(path: Path) -> DesignFile \| None` | Full parse; returns None if file missing, no frontmatter, no footer, or corrupt footer |
| `parse_design_file_metadata` | `(path: Path) -> StalenessMetadata \| None` | Cheap footer-only extraction; returns None if footer absent or corrupt |
| `parse_design_file_frontmatter` | `(path: Path) -> DesignFileFrontmatter \| None` | Frontmatter-only extraction; returns None if no YAML frontmatter |

## Parser Behaviour

- Footer regex: `<!-- lexibrarian:meta\n...\n-->` (multiline, DOTALL)
- Frontmatter regex: `^---\n...\n---\n` (matched at start of file)
- Footer fields are YAML-style `key: value` lines (not `key="value"` — that's .aindex format)
- `design_hash` required in design file footer; absent → `None` from `_parse_footer` → parse returns `None`
- `summary` is derived from `frontmatter.description` during parsing (no separate body section)
- `updated_by` defaults to `"archivist"` if missing from frontmatter YAML

## Notes

- Use `parse_design_file_metadata` for staleness checks (cheap — searches footer only)
- Use `parse_design_file_frontmatter` when only the description is needed
- All three functions return `None` gracefully on any IO error or malformation

## Dependencies

- `lexibrarian.artifacts.design_file` -- `DesignFile`, `DesignFileFrontmatter`, `StalenessMetadata`
- `yaml` (PyYAML)
- `re`, `pathlib`, `datetime` (stdlib)

## Dependents

- `lexibrarian.archivist.change_checker` -- imports `_FOOTER_RE`, `parse_design_file_metadata`
- `lexibrarian.archivist.pipeline` -- imports `parse_design_file`, `parse_design_file_frontmatter`, `parse_design_file_metadata`, `_FOOTER_RE`
- `lexibrarian.indexer.generator` -- imports `parse_design_file_frontmatter`
- `lexibrarian.cli` -- `lookup` command imports `parse_design_file_metadata`
