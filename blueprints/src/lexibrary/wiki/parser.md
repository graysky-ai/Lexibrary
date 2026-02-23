# wiki/parser

**Summary:** Parses concept file markdown (YAML frontmatter + body) into a `ConceptFile` model; also extracts `[[wikilinks]]`, backtick file references, summaries, and decision log items.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `parse_concept_file` | `(path: Path) -> ConceptFile | None` | Parse a concept markdown file; returns `None` on missing file, missing frontmatter, or validation error |

## Key Concepts

- Frontmatter delimited by `---` / `---`, parsed with `yaml.safe_load` and validated against `ConceptFileFrontmatter`
- Summary: first non-empty paragraph before any `##` heading
- `[[wikilinks]]` extracted via regex (`_WIKILINK_RE`) from the body into `related_concepts`
- Backtick file references: paths containing `/` ending in known extensions (`.py`, `.ts`, `.md`, etc.) extracted into `linked_files`
- Decision log: bullet items (`- ` or `* `) from a `## Decision Log` section

## Dependencies

- `lexibrarian.artifacts.concept` — `ConceptFile`, `ConceptFileFrontmatter`

## Dependents

- `lexibrarian.wiki.__init__` — re-exports
- `lexibrarian.wiki.index` — `ConceptIndex.load` calls `parse_concept_file`
