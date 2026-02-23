## MODIFIED Requirements

### Requirement: DesignFile model
Pydantic 2 model with fields: `source_path` (str), `frontmatter` (DesignFileFrontmatter), `summary` (str), `interface_contract` (str), `dependencies` (list[str]), `dependents` (list[str]), `tests` (str | None), `complexity_warning` (str | None), `wikilinks` (list[str]), `tags` (list[str]), `stack_refs` (list[str]), `metadata` (StalenessMetadata). The model SHALL include the `frontmatter` field containing the YAML frontmatter data.

#### Scenario: DesignFile with frontmatter
- **WHEN** a `DesignFile` is created
- **THEN** it SHALL include a `frontmatter` field of type `DesignFileFrontmatter`

#### Scenario: DesignFile optional fields
- **WHEN** a `DesignFile` is created with `tests=None` and `complexity_warning=None`
- **THEN** those fields SHALL be None

#### Scenario: DesignFile stack_refs field
- **WHEN** a `DesignFile` is created with `stack_refs=["ST-001", "ST-015"]`
- **THEN** the `stack_refs` field SHALL contain the provided values

## REMOVED Requirements

### Requirement: GuardrailThread model
**Reason**: Replaced by `StackPost` model in `src/lexibrary/stack/models.py` (see `stack-post-model` spec).
**Migration**: Use `StackPost` from `lexibrary.stack` instead of `GuardrailThread` from `lexibrary.artifacts`.

## MODIFIED Requirements

### Requirement: Artifacts module exports
`src/lexibrary/artifacts/__init__.py` SHALL re-export: DesignFile, DesignFileFrontmatter, AIndexFile, ConceptFile, StalenessMetadata. The `GuardrailThread` export SHALL be removed.

#### Scenario: DesignFileFrontmatter importable from artifacts
- **WHEN** `from lexibrary.artifacts import DesignFileFrontmatter` is used
- **THEN** the import SHALL succeed

#### Scenario: GuardrailThread no longer exported
- **WHEN** `from lexibrary.artifacts import GuardrailThread` is attempted
- **THEN** the import SHALL raise `ImportError`

## RENAMED Requirements

### Requirement: DesignFile field rename
- **FROM:** `guardrail_refs` (list[str])
- **TO:** `stack_refs` (list[str])
