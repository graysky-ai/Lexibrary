## REMOVED Requirements

### Requirement: StartHereRequest and StartHereResult data classes
**Reason**: START_HERE generation is removed entirely. The `StartHereRequest` and `StartHereResult` dataclasses in `service.py` are no longer needed since topology generation is procedural (no LLM call).
**Migration**: Delete `StartHereRequest` and `StartHereResult` from `service.py`. Remove any imports of these types.

## MODIFIED Requirements

### Requirement: ArchivistService class
The system SHALL provide an `ArchivistService` class in `src/lexibrary/archivist/service.py` with:
- Constructor accepting `rate_limiter: RateLimiter` and `config: LLMConfig`
- `async generate_design_file(request: DesignFileRequest) -> DesignFileResult`

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
