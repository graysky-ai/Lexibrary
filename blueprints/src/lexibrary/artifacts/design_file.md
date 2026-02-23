# artifacts/design_file

**Summary:** Pydantic 2 models for design file artifacts and the shared `StalenessMetadata` footer embedded in all generated artifacts.

## Interface

| Name | Key Fields | Purpose |
| --- | --- | --- |
| `DesignFileFrontmatter` | `description: str`, `updated_by: Literal["archivist", "agent"]` (default "archivist") | Agent-editable YAML frontmatter for a design file |
| `StalenessMetadata` | `source`, `source_hash`, `interface_hash?`, `design_hash?`, `generated: datetime`, `generator` | HTML-comment footer tracking artifact provenance; shared by all artifact types; `design_hash` is set only for design files, not .aindex |
| `DesignFile` | `source_path`, `frontmatter`, `summary`, `interface_contract`, `dependencies`, `dependents`, `tests?`, `complexity_warning?`, `wikilinks`, `tags`, `stack_refs`, `metadata` | Full design file for a single source file |

## Notes

- `design_hash` in `StalenessMetadata` is `str | None = None` -- set for design files (SHA-256 of frontmatter+body, excluding footer), absent for `.aindex` files
- `frontmatter` is required on `DesignFile`; agent sets `updated_by="agent"` to signal they edited the body

## Dependents

- `lexibrarian.artifacts.__init__` -- re-exports all three models
- `lexibrarian.artifacts.aindex_parser` -- imports `StalenessMetadata`
- `lexibrarian.artifacts.concept` -- imports `StalenessMetadata`
- `lexibrarian.artifacts.design_file_serializer` -- serializes `DesignFile`
- `lexibrarian.artifacts.design_file_parser` -- parses `DesignFile` from disk
- `lexibrarian.archivist.pipeline` -- builds `DesignFile` and `DesignFileFrontmatter` models for serialization
- `lexibrarian.archivist.change_checker` -- reads `StalenessMetadata` for hash comparison
