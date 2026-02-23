## ADDED Requirements

### Requirement: DesignFileFrontmatter model
The system SHALL provide a `DesignFileFrontmatter` Pydantic 2 model in `src/lexibrary/artifacts/design_file.py` with fields:
- `description` (str) — single sentence summary of the source file
- `updated_by` (Literal["archivist", "agent"]) — who last meaningfully updated the design file body, default "archivist"

#### Scenario: Create frontmatter with defaults
- **WHEN** a `DesignFileFrontmatter` is created with only `description="Auth service"`
- **THEN** `updated_by` SHALL default to `"archivist"`

#### Scenario: Agent-authored frontmatter
- **WHEN** a `DesignFileFrontmatter` is created with `description="Auth service"` and `updated_by="agent"`
- **THEN** both fields SHALL be stored correctly

### Requirement: Design file serializer
The system SHALL provide a `serialize_design_file(data: DesignFile) -> str` function in `src/lexibrary/artifacts/design_file_serializer.py` that produces a markdown string with:
1. YAML frontmatter delimited by `---` containing `description` and `updated_by`
2. H1 header with source file path relative to project root
3. `## Interface Contract` section with fenced code block (language-tagged)
4. `## Dependencies` section with bullet list (or `(none)`)
5. `## Dependents` section with bullet list (or `(none)`)
6. Optional sections (`## Tests`, `## Complexity Warning`, `## Wikilinks`, `## Tags`, `## Guardrails`) omitted when empty/None
7. HTML comment metadata footer with source, source_hash, interface_hash, design_hash, generated, generator
8. Trailing newline

#### Scenario: Serialize fully populated design file
- **WHEN** `serialize_design_file()` is called with a DesignFile containing all fields populated
- **THEN** the output SHALL contain YAML frontmatter, all sections, and HTML comment footer

#### Scenario: Serialize minimal design file
- **WHEN** `serialize_design_file()` is called with a DesignFile where optional fields are empty/None
- **THEN** optional sections (Tests, Complexity Warning, Wikilinks, Tags, Guardrails) SHALL be omitted from output

#### Scenario: Metadata footer format
- **WHEN** `serialize_design_file()` is called
- **THEN** the HTML comment footer SHALL use the format `<!-- lexibrary:meta\nkey: value\n-->` with fields: source, source_hash, interface_hash, design_hash, generated, generator

### Requirement: Design file parser
The system SHALL provide parsing functions in `src/lexibrary/artifacts/design_file_parser.py`:
- `parse_design_file(path: Path) -> DesignFile | None` — full parse, returns None if file doesn't exist or is malformed
- `parse_design_file_metadata(path: Path) -> StalenessMetadata | None` — extracts only the HTML comment footer (cheap, reads from end of file)
- `parse_design_file_frontmatter(path: Path) -> DesignFileFrontmatter | None` — extracts only the YAML frontmatter

#### Scenario: Parse well-formed design file
- **WHEN** `parse_design_file()` is called on a valid design file with frontmatter, body, and footer
- **THEN** it SHALL return a correctly populated DesignFile model

#### Scenario: Parse metadata only
- **WHEN** `parse_design_file_metadata()` is called on a design file with a valid footer
- **THEN** it SHALL return StalenessMetadata without parsing the full file

#### Scenario: Parse frontmatter only
- **WHEN** `parse_design_file_frontmatter()` is called on a design file
- **THEN** it SHALL return the description field from YAML frontmatter

#### Scenario: Parse nonexistent file
- **WHEN** `parse_design_file()` is called on a path that doesn't exist
- **THEN** it SHALL return None

#### Scenario: Parse file with no footer
- **WHEN** `parse_design_file_metadata()` is called on a design file without an HTML comment footer
- **THEN** it SHALL return None

#### Scenario: Parse file with corrupt footer
- **WHEN** `parse_design_file_metadata()` is called on a design file with a malformed footer
- **THEN** it SHALL return None

### Requirement: Design file round-trip integrity
The system SHALL preserve all data through a serialize-write-parse cycle: `serialize_design_file(df)` written to disk and then `parse_design_file(path)` SHALL produce a DesignFile equivalent to the original.

#### Scenario: Round-trip with all fields
- **WHEN** a fully populated DesignFile is serialized, written, and parsed back
- **THEN** all fields SHALL match the original

#### Scenario: Round-trip with optional sections
- **WHEN** a DesignFile with all optional sections populated is round-tripped
- **THEN** all optional sections SHALL survive the round-trip

### Requirement: Agent edit detection via design_hash
The `design_hash` field in the metadata footer SHALL be the SHA-256 hash of the design file content (YAML frontmatter + markdown body, excluding the HTML comment footer). When the current file content hashes differently from `design_hash`, the system SHALL detect that an agent or human has edited the file.

#### Scenario: Detect agent edit
- **WHEN** a design file's body is modified after the Archivist wrote it
- **THEN** hashing the current content (excluding footer) SHALL produce a value different from the stored `design_hash`
