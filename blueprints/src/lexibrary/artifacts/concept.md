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

- `lexibrarian.artifacts.__init__` — re-exports
- `lexibrarian.wiki.parser` — parses markdown into `ConceptFile` / `ConceptFileFrontmatter`
- `lexibrarian.wiki.serializer` — serializes `ConceptFile` back to markdown
- `lexibrarian.wiki.index` — indexes by `frontmatter.title`
- `lexibrarian.wiki.resolver` — `ResolvedLink.concept: ConceptFile | None`
