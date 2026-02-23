# stack/models

**Summary:** Pydantic 2 models for Stack posts — the Q&A knowledge base artifact type.

## Interface

| Name | Key Fields | Purpose |
| --- | --- | --- |
| `StackStatus` | `Literal["open", "resolved", "outdated", "duplicate"]` | Type alias for valid post statuses |
| `StackPostRefs` | `concepts: list[str]`, `files: list[str]`, `designs: list[str]` | Cross-references from a Stack post to other artifacts |
| `StackPostFrontmatter` | `id`, `title`, `tags` (min 1), `status`, `created: date`, `author`, `bead?`, `votes`, `duplicate_of?`, `refs` | Validated YAML frontmatter for a Stack post |
| `StackAnswer` | `number`, `date`, `author`, `votes`, `accepted`, `body`, `comments: list[str]` | A single answer within a Stack post |
| `StackPost` | `frontmatter`, `problem`, `evidence: list[str]`, `answers: list[StackAnswer]`, `raw_body` | Full Stack post with all sections parsed |

## Dependencies

- `pydantic` -- `BaseModel`, `Field`

## Dependents

- `lexibrarian.stack.index` -- queries `StackPost` fields
- `lexibrarian.stack.mutations` -- modifies `StackPost` and `StackAnswer` in-place
- `lexibrarian.stack.parser` -- constructs models from parsed markdown
- `lexibrarian.stack.serializer` -- serializes models to markdown
- `lexibrarian.search` -- reads frontmatter fields for search results

## Key Concepts

- `tags` requires at least one entry (`min_length=1`)
- `refs` defaults to empty `StackPostRefs` — cross-references to concepts, files, and design files
- `bead` is optional — links a post to a Beads work item
- `duplicate_of` is set only when `status == "duplicate"`
