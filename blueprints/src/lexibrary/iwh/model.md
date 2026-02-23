# iwh/model

**Summary:** Pydantic 2 model for IWH (I Was Here) inter-agent signal files -- ephemeral, directory-scoped signals left by one agent session to inform the next.

## Interface

| Name | Type / Signature | Purpose |
| --- | --- | --- |
| `IWHScope` | `Literal["warning", "incomplete", "blocked"]` | Type alias for valid IWH severity levels |
| `IWHFile` | `BaseModel` | Parsed `.iwh` signal file with `author` (str, min_length=1), `created` (datetime), `scope` (IWHScope), `body` (str, default="") |

## Dependencies

- None (only pydantic)

## Dependents

- `lexibrarian.iwh.parser` -- validates parsed frontmatter into `IWHFile`
- `lexibrarian.iwh.serializer` -- serializes `IWHFile` to markdown with YAML frontmatter
- `lexibrarian.iwh.reader` -- returns `IWHFile | None`
- `lexibrarian.iwh.writer` -- constructs `IWHFile` instances for writing

## Key Concepts

- IWH files are ephemeral: they are consumed (read and deleted) by the next agent session
- `IWHScope` determines severity: `warning` (advisory), `incomplete` (unfinished work), `blocked` (cannot proceed)
- `body` is free-form markdown -- can contain task lists, context, next steps
