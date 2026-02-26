## MODIFIED Requirements

### Requirement: AIndexFile model
The system SHALL define an `AIndexFile` Pydantic 2 model representing a `.aindex` file artifact. Fields SHALL include: `directory_path` (str), `billboard` (str), `entries` (list[AIndexEntry]), `metadata` (StalenessMetadata).

`AIndexEntry` SHALL have fields: `name` (str), `description` (str), `is_directory` (bool).

The `local_conventions` field SHALL NOT exist on this model.

#### Scenario: AIndexFile validates with entries
- **WHEN** creating an `AIndexFile` with directory_path, billboard, and a list of AIndexEntry items
- **THEN** the model validates successfully

#### Scenario: AIndexEntry distinguishes files from directories
- **WHEN** creating an `AIndexEntry` with is_directory=True
- **THEN** `entry.is_directory` returns True

#### Scenario: AIndexFile has no local_conventions field
- **WHEN** inspecting `AIndexFile` model fields
- **THEN** there SHALL be no `local_conventions` field

### Requirement: Artifacts module exports
`src/lexibrary/artifacts/__init__.py` SHALL re-export: DesignFile, DesignFileFrontmatter, AIndexFile, ConceptFile, ConventionFile, ConventionFileFrontmatter, StalenessMetadata. The `GuardrailThread` export SHALL NOT exist.

#### Scenario: DesignFileFrontmatter importable from artifacts
- **WHEN** `from lexibrary.artifacts import DesignFileFrontmatter` is used
- **THEN** the import SHALL succeed

#### Scenario: ConventionFile importable from artifacts
- **WHEN** `from lexibrary.artifacts import ConventionFile` is used
- **THEN** the import SHALL succeed

#### Scenario: GuardrailThread no longer exported
- **WHEN** `from lexibrary.artifacts import GuardrailThread` is attempted
- **THEN** the import SHALL raise `ImportError`
