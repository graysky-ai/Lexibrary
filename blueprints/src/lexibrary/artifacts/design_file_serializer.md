# artifacts/design_file_serializer

**Summary:** Serializes a `DesignFile` model to the three-section markdown format: YAML frontmatter, markdown body, and HTML comment metadata footer.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `serialize_design_file` | `(data: DesignFile) -> str` | Produces full markdown string with frontmatter, all sections, and footer |

## Output Format

1. YAML frontmatter delimited by `---` (`description`, `updated_by`)
2. `# <source_path>` H1 heading
3. `## Interface Contract` with language-tagged fenced code block
4. `## Dependencies` — bullet list or `(none)`
5. `## Dependents` — bullet list or `(none)`
6. Optional sections (omitted when empty/None): `## Tests`, `## Complexity Warning`, `## Wikilinks`, `## Tags`, `## Guardrails`
7. Multiline HTML comment footer: `<!-- lexibrarian:meta\nkey: value\n-->`
8. Trailing newline

## Notes

- `design_hash` in footer = SHA-256 of the joined `parts` text before the footer is appended
- Language tag for fenced block derived from `detect_language(source_path)` via `_LANG_TAG` map; unknown extensions → `"text"`
- YAML serialized with `yaml.dump()` (PyYAML), `default_flow_style=False`

## Dependencies

- `lexibrarian.artifacts.design_file` -- `DesignFile` model
- `lexibrarian.utils.languages` -- `detect_language()`
- `yaml` (PyYAML)
- `hashlib` (stdlib)

## Dependents

- `lexibrarian.archivist.pipeline` -- serializes generated `DesignFile` models to disk
