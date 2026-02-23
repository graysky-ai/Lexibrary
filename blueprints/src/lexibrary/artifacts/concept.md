# artifacts/concept

**Summary:** Pydantic 2 models for concept file artifacts — cross-cutting design ideas tracked in `.lexibrary/concepts/`.

## Interface

| Name | Key Fields | Purpose |
| --- | --- | --- |
| `ConceptFileFrontmatter` | `title: str`, `aliases: list[str]`, `tags: list[str]`, `status: "draft" \| "active" \| "deprecated"`, `superseded_by: str \| None` | Validated YAML frontmatter for a concept file |
| `ConceptFile` | `frontmatter: ConceptFileFrontmatter`, `body: str`, `summary: str`, `related_concepts: list[str]`, `linked_files: list[str]`, `decision_log: list[str]`; property `name -> str` | Represents one concept document with parsed body fields |

## Dependencies

*(stdlib + Pydantic 2 only — no internal imports)*

## Dependents

- `lexibrary.artifacts.__init__` — re-exports
- `lexibrary.wiki.parser` — parses markdown into `ConceptFile` / `ConceptFileFrontmatter`
- `lexibrary.wiki.serializer` — serializes `ConceptFile` back to markdown
- `lexibrary.wiki.index` — indexes by `frontmatter.title`
- `lexibrary.wiki.resolver` — `ResolvedLink.concept: ConceptFile | None`
