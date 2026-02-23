# wiki/serializer

**Summary:** Serializes a `ConceptFile` back to a markdown string with YAML frontmatter; inverse of `parse_concept_file`.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `serialize_concept_file` | `(concept: ConceptFile) -> str` | Produce `---\n<YAML>\n---\n<body>` with trailing newline guaranteed |

## Key Concepts

- Frontmatter fields written: `title`, `aliases`, `tags`, `status`; `superseded_by` only written if not `None`
- Body written as-is from `ConceptFile.body`
- Trailing newline always appended if missing

## Dependencies

- `lexibrarian.artifacts.concept` — `ConceptFile`

## Dependents

- `lexibrarian.wiki.__init__` — re-exports
