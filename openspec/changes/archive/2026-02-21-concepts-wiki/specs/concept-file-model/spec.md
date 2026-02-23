## ADDED Requirements

### Requirement: ConceptFileFrontmatter model
The system SHALL define a `ConceptFileFrontmatter` Pydantic 2 model in `src/lexibrary/artifacts/concept.py` with fields:
- `title` (str) — display name of the concept
- `aliases` (list[str]) — alternative names for wikilink resolution, default empty list
- `tags` (list[str]) — categorization tags, default empty list
- `status` (Literal["draft", "active", "deprecated"]) — lifecycle status, default `"draft"`
- `superseded_by` (str | None) — concept name that replaces this one when status is "deprecated", default None

#### Scenario: Frontmatter with defaults
- **WHEN** a `ConceptFileFrontmatter` is created with only `title="JWT Auth"`
- **THEN** `aliases` SHALL default to `[]`, `tags` SHALL default to `[]`, and `status` SHALL default to `"draft"`

#### Scenario: Frontmatter with all fields
- **WHEN** a `ConceptFileFrontmatter` is created with `title="JWT Auth"`, `aliases=["json-web-token"]`, `tags=["auth", "security"]`, `status="active"`
- **THEN** all fields SHALL be stored correctly

#### Scenario: Invalid status rejected
- **WHEN** a `ConceptFileFrontmatter` is created with `status="archived"`
- **THEN** Pydantic SHALL raise a `ValidationError`

#### Scenario: Deprecated with superseded_by
- **WHEN** a `ConceptFileFrontmatter` is created with `status="deprecated"` and `superseded_by="NewAuth"`
- **THEN** both fields SHALL be stored correctly

#### Scenario: Superseded_by defaults to None
- **WHEN** a `ConceptFileFrontmatter` is created without `superseded_by`
- **THEN** `superseded_by` SHALL default to `None`

### Requirement: ConceptFile model with frontmatter
The system SHALL replace the existing stub `ConceptFile` model with a full model containing:
- `frontmatter` (ConceptFileFrontmatter) — validated YAML frontmatter
- `body` (str) — raw markdown body content (source of truth, preserved as-is)
- `summary` (str) — extracted from first paragraph of body, default empty string
- `related_concepts` (list[str]) — wikilinks extracted from body, default empty list
- `linked_files` (list[str]) — source file paths referenced in body, default empty list
- `decision_log` (list[str]) — items extracted from `## Decision Log` section, default empty list

The `name` property SHALL return `frontmatter.title`.

#### Scenario: ConceptFile with full body
- **WHEN** a `ConceptFile` is created with frontmatter and a body containing wikilinks and decisions
- **THEN** `related_concepts`, `linked_files`, and `decision_log` SHALL be populated from the body

#### Scenario: ConceptFile name property
- **WHEN** `concept.name` is accessed
- **THEN** it SHALL return `concept.frontmatter.title`

#### Scenario: ConceptFile with minimal fields
- **WHEN** a `ConceptFile` is created with only `frontmatter` and `body=""`
- **THEN** `summary`, `related_concepts`, `linked_files`, and `decision_log` SHALL all default to empty

### Requirement: Artifacts module exports ConceptFileFrontmatter
`src/lexibrary/artifacts/__init__.py` SHALL re-export `ConceptFileFrontmatter` alongside the existing `ConceptFile` export.

#### Scenario: ConceptFileFrontmatter importable
- **WHEN** `from lexibrary.artifacts import ConceptFileFrontmatter` is used
- **THEN** the import SHALL succeed
