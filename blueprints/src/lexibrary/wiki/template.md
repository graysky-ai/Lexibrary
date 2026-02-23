# wiki/template

**Summary:** Scaffolding helpers for new concept files — renders a blank template with placeholder sections and derives a PascalCase file path from a concept name.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `render_concept_template` | `(name: str, tags: list[str] \| None = None) -> str` | Render a new concept file with YAML frontmatter + body scaffold (`## Details`, `## Decision Log`, `## Related`) |
| `concept_file_path` | `(name: str, concepts_dir: Path) -> Path` | Derive `PascalCase.md` path for a concept name within `concepts_dir` |

## Key Concepts

- `render_concept_template` sets `status: draft` and empty `aliases: []` in frontmatter; body includes placeholder comment and section headings
- `concept_file_path` splits on non-alphanumeric characters, capitalizes each word (PascalCase), appends `.md`

## Dependencies

*(stdlib only: `re`, `pathlib.Path`, `yaml`)*

## Dependents

- `lexibrarian.wiki.__init__` — re-exports
