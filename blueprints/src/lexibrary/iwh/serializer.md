# iwh/serializer

**Summary:** Serializes `IWHFile` instances to markdown format with YAML frontmatter, producing the on-disk representation of `.iwh` signal files.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `serialize_iwh` | `(iwh: IWHFile) -> str` | Serialize an `IWHFile` to markdown string with `---` delimited YAML frontmatter (author, created as ISO 8601, scope) followed by body; always ends with trailing newline |

## Dependencies

- `lexibrarian.iwh.model` -- `IWHFile`
- `yaml` (PyYAML) -- frontmatter serialization

## Dependents

- `lexibrarian.iwh.writer` -- `write_iwh()` calls `serialize_iwh()` before writing to disk

## Key Concepts

- Frontmatter fields: `author`, `created` (ISO 8601 string), `scope`
- Empty body produces frontmatter-only output with trailing newline
- Non-empty body is appended after `---` delimiter with its own trailing newline
