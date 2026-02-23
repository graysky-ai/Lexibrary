# archivist-service Specification

## Purpose
TBD - created by archiving change archivist. Update Purpose after archive.
## Requirements
### Requirement: ArchivistService class
The system SHALL provide an `ArchivistService` class in `src/lexibrary/archivist/service.py` with:
- Constructor accepting `rate_limiter: RateLimiter` and `config: LLMConfig`
- `async generate_design_file(request: DesignFileRequest) -> DesignFileResult`
- `async generate_start_here(request: StartHereRequest) -> StartHereResult`

The service SHALL be stateless (safe for future concurrent use).

When `request.available_concepts` is not None, the service SHALL pass the concept names to the BAML function call as the `available_concepts` parameter.

#### Scenario: Generate design file with rate limiting
- **WHEN** `generate_design_file()` is called
- **THEN** it SHALL respect the rate limiter before making the BAML call

#### Scenario: LLM call failure returns error result
- **WHEN** the BAML call fails (network error, API error, etc.)
- **THEN** `generate_design_file()` SHALL return a `DesignFileResult` with `error=True` and `error_message` populated

#### Scenario: Concepts passed to BAML
- **WHEN** `generate_design_file()` is called with `request.available_concepts=["JWT Auth"]`
- **THEN** the BAML function SHALL receive `available_concepts=["JWT Auth"]`

#### Scenario: No concepts passed when None
- **WHEN** `generate_design_file()` is called with `request.available_concepts=None`
- **THEN** the BAML function SHALL receive `available_concepts=None` (or omit the parameter)

### Requirement: DesignFileRequest data class
The system SHALL provide a `DesignFileRequest` dataclass with fields:
- `source_path` (str)
- `source_content` (str)
- `interface_skeleton` (str | None)
- `language` (str | None)
- `existing_design_file` (str | None)
- `available_concepts` (list[str] | None) — optional list of known concept names for wikilink suggestions, default None

#### Scenario: Request for code file
- **WHEN** a DesignFileRequest is created for a Python file
- **THEN** `interface_skeleton` and `language` SHALL be populated

#### Scenario: Request for non-code file
- **WHEN** a DesignFileRequest is created for a YAML file
- **THEN** `interface_skeleton` and `language` SHALL be None

#### Scenario: Request with available concepts
- **WHEN** a DesignFileRequest is created with `available_concepts=["JWT Auth", "Rate Limiting"]`
- **THEN** `available_concepts` SHALL be stored as the provided list

#### Scenario: Request without available concepts
- **WHEN** a DesignFileRequest is created without `available_concepts`
- **THEN** `available_concepts` SHALL default to None

### Requirement: DesignFileResult data class
The system SHALL provide a `DesignFileResult` dataclass with fields:
- `source_path` (str)
- `design_file_output` (DesignFileOutput | None)
- `error` (bool, default False)
- `error_message` (str | None, default None)

#### Scenario: Successful result
- **WHEN** the LLM call succeeds
- **THEN** `design_file_output` SHALL be populated and `error` SHALL be False

### Requirement: Provider-based client selection
The `ArchivistService` SHALL select the BAML client based on `LLMConfig.provider` using BAML's `ClientRegistry` (or env var fallback per design decision D-5).

#### Scenario: Anthropic provider selected
- **WHEN** `LLMConfig.provider` is `"anthropic"`
- **THEN** the service SHALL route BAML calls to the Anthropic client

### Requirement: Service logging
The `ArchivistService` SHALL log:
- Each LLM call (source path, provider)
- Errors with full context
- Rate limiter waits

#### Scenario: LLM call logged
- **WHEN** `generate_design_file()` is called
- **THEN** the source path and provider SHALL be logged

