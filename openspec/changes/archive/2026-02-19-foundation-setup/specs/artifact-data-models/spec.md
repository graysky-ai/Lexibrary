## ADDED Requirements

### Requirement: StalenessMetadata model
The system SHALL define a `StalenessMetadata` Pydantic 2 model capturing the fields embedded in the HTML comment footer of every generated artifact: `source` (str), `source_hash` (str), `interface_hash` (str | None), `generated` (datetime), `generator` (str).

#### Scenario: StalenessMetadata validates required fields
- **WHEN** creating a `StalenessMetadata` with source, source_hash, generated, and generator
- **THEN** the model validates successfully with interface_hash defaulting to None

#### Scenario: StalenessMetadata rejects missing required fields
- **WHEN** creating a `StalenessMetadata` without the source field
- **THEN** Pydantic raises a ValidationError

### Requirement: DesignFile model
The system SHALL define a `DesignFile` Pydantic 2 model representing a design file artifact. Fields SHALL include: `source_path` (str), `summary` (str), `interface_contract` (str), `dependencies` (list[str]), `dependents` (list[str]), `tests` (str | None), `complexity_warning` (str | None), `wikilinks` (list[str]), `tags` (list[str]), `guardrail_refs` (list[str]), `metadata` (StalenessMetadata).

#### Scenario: DesignFile validates with minimal fields
- **WHEN** creating a `DesignFile` with source_path, summary, interface_contract, and metadata
- **THEN** the model validates successfully with list fields defaulting to empty lists

#### Scenario: DesignFile wikilinks are strings
- **WHEN** creating a `DesignFile` with wikilinks=["Authentication", "MoneyHandling"]
- **THEN** `design_file.wikilinks` returns ["Authentication", "MoneyHandling"]

### Requirement: AIndexFile model
The system SHALL define an `AIndexFile` Pydantic 2 model representing a `.aindex` file artifact. Fields SHALL include: `directory_path` (str), `billboard` (str), `entries` (list[AIndexEntry]), `local_conventions` (list[str]), `metadata` (StalenessMetadata).

`AIndexEntry` SHALL have fields: `name` (str), `description` (str), `is_directory` (bool).

#### Scenario: AIndexFile validates with entries
- **WHEN** creating an `AIndexFile` with directory_path, billboard, and a list of AIndexEntry items
- **THEN** the model validates successfully

#### Scenario: AIndexEntry distinguishes files from directories
- **WHEN** creating an `AIndexEntry` with is_directory=True
- **THEN** `entry.is_directory` returns True

### Requirement: ConceptFile model
The system SHALL define a `ConceptFile` Pydantic 2 model representing a concept file artifact. Fields SHALL include: `name` (str), `summary` (str), `linked_files` (list[str]), `tags` (list[str]), `decision_log` (list[str]), `wikilinks` (list[str]), `metadata` (StalenessMetadata | None).

#### Scenario: ConceptFile validates with required fields
- **WHEN** creating a `ConceptFile` with name and summary
- **THEN** the model validates successfully with list fields defaulting to empty lists and metadata defaulting to None

### Requirement: GuardrailThread model
The system SHALL define a `GuardrailThread` Pydantic 2 model representing a guardrail thread. Fields SHALL include: `thread_id` (str), `title` (str), `status` (Literal["active", "resolved", "stale"]), `scope` (list[str]), `reported_by` (str), `date` (date), `problem` (str), `failed_approaches` (list[str]), `resolution` (str | None), `evidence` (list[str]).

#### Scenario: GuardrailThread validates active thread
- **WHEN** creating a `GuardrailThread` with thread_id="GR-001", title, status="active", scope, reported_by, date, and problem
- **THEN** the model validates successfully with resolution defaulting to None

#### Scenario: GuardrailThread status is constrained
- **WHEN** creating a `GuardrailThread` with status="invalid"
- **THEN** Pydantic raises a ValidationError

### Requirement: Artifacts module exports
The `src/lexibrary/artifacts/__init__.py` SHALL re-export all public model classes so callers can write `from lexibrary.artifacts import DesignFile, AIndexFile, ConceptFile, GuardrailThread, StalenessMetadata`.

#### Scenario: All models importable from top-level artifacts
- **WHEN** importing `from lexibrary.artifacts import DesignFile, AIndexFile, ConceptFile, GuardrailThread, StalenessMetadata`
- **THEN** all five names are available without ImportError
