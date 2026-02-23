## ADDED Requirements

### Requirement: DesignFileFrontmatter model
The `src/lexibrary/artifacts/design_file.py` module SHALL export a `DesignFileFrontmatter` Pydantic 2 model with fields:
- `description` (str) — single sentence summary
- `updated_by` (Literal["archivist", "agent"]) — default "archivist"

#### Scenario: Frontmatter model creation
- **WHEN** a `DesignFileFrontmatter` is instantiated
- **THEN** it SHALL validate that `updated_by` is either "archivist" or "agent"

## MODIFIED Requirements

### Requirement: StalenessMetadata model
Pydantic 2 model with fields: `source` (str), `source_hash` (str), `interface_hash` (str | None), `design_hash` (str), `generated` (datetime), `generator` (str). The `design_hash` field SHALL contain the SHA-256 hash of the design file content (frontmatter + body, excluding footer) at the time the Archivist last wrote or refreshed it.

#### Scenario: StalenessMetadata includes design_hash
- **WHEN** a `StalenessMetadata` is created
- **THEN** the `design_hash` field SHALL be required (non-optional str)

#### Scenario: StalenessMetadata with interface_hash None
- **WHEN** a `StalenessMetadata` is created for a non-code file
- **THEN** `interface_hash` SHALL accept None

### Requirement: DesignFile model
Pydantic 2 model with fields: `source_path` (str), `frontmatter` (DesignFileFrontmatter), `summary` (str), `interface_contract` (str), `dependencies` (list[str]), `dependents` (list[str]), `tests` (str | None), `complexity_warning` (str | None), `wikilinks` (list[str]), `tags` (list[str]), `guardrail_refs` (list[str]), `metadata` (StalenessMetadata). The model SHALL include the `frontmatter` field containing the YAML frontmatter data.

#### Scenario: DesignFile with frontmatter
- **WHEN** a `DesignFile` is created
- **THEN** it SHALL include a `frontmatter` field of type `DesignFileFrontmatter`

#### Scenario: DesignFile optional fields
- **WHEN** a `DesignFile` is created with `tests=None` and `complexity_warning=None`
- **THEN** those fields SHALL be None

### Requirement: Artifacts module exports
`src/lexibrary/artifacts/__init__.py` SHALL re-export: DesignFile, DesignFileFrontmatter, AIndexFile, ConceptFile, GuardrailThread, StalenessMetadata.

#### Scenario: DesignFileFrontmatter importable from artifacts
- **WHEN** `from lexibrary.artifacts import DesignFileFrontmatter` is used
- **THEN** the import SHALL succeed
