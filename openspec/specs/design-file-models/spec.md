# design-file-models Specification

## Purpose
TBD - created by archiving change archivist. Update Purpose after archive.
## Requirements
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
6. Optional sections (`## Tests`, `## Complexity Warning`, `## Wikilinks`, `## Tags`, `## Stack`) omitted when empty/None
7. HTML comment metadata footer with source, source_hash, interface_hash, design_hash, generated, generator
8. Trailing newline

The `## Wikilinks` section SHALL serialize each wikilink wrapped in `[[double brackets]]` as a bullet list item. If the wikilink already contains brackets, it SHALL NOT double-wrap.

The `## Stack` section SHALL serialize each stack ref as `- [[ST-NNN]]` in a bullet list. If the ref already contains brackets, it SHALL NOT double-wrap.

#### Scenario: Serialize fully populated design file
- **WHEN** `serialize_design_file()` is called with a DesignFile containing all fields populated
- **THEN** the output SHALL contain YAML frontmatter, all sections, and HTML comment footer

#### Scenario: Serialize minimal design file
- **WHEN** `serialize_design_file()` is called with a DesignFile where optional fields are empty/None
- **THEN** optional sections (Tests, Complexity Warning, Wikilinks, Tags, Stack) SHALL be omitted from output

#### Scenario: Metadata footer format
- **WHEN** `serialize_design_file()` is called
- **THEN** the HTML comment footer SHALL use the format `<!-- lexibrary:meta\nkey: value\n-->` with fields: source, source_hash, interface_hash, design_hash, generated, generator

#### Scenario: Wikilinks serialized with brackets
- **WHEN** `serialize_design_file()` is called with `wikilinks=["JWT Auth", "Rate Limiting"]`
- **THEN** the Wikilinks section SHALL contain `- [[JWT Auth]]` and `- [[Rate Limiting]]`

#### Scenario: Wikilinks not double-wrapped
- **WHEN** `serialize_design_file()` is called with `wikilinks=["[[JWT Auth]]"]` (already bracketed)
- **THEN** the output SHALL contain `- [[JWT Auth]]` (not `- [[[[JWT Auth]]]]`)

#### Scenario: Stack section uses [[ST-NNN]] format
- **WHEN** `serialize_design_file()` is called with `stack_refs=["ST-001", "ST-015"]`
- **THEN** the `## Stack` section SHALL contain `- [[ST-001]]` and `- [[ST-015]]`

### Requirement: Design file parser
The system SHALL provide parsing functions in `src/lexibrary/artifacts/design_file_parser.py`:
- `parse_design_file(path: Path) -> DesignFile | None` — full parse, returns None if file doesn't exist or is malformed
- `parse_design_file_metadata(path: Path) -> StalenessMetadata | None` — extracts only the HTML comment footer (cheap, reads from end of file)
- `parse_design_file_frontmatter(path: Path) -> DesignFileFrontmatter | None` — extracts only the YAML frontmatter

The parser SHALL recognize both `## Stack` and `## Guardrails` section headers for backward compatibility. Both SHALL be parsed into the `stack_refs` field.

The wikilinks parser SHALL strip `[[` and `]]` brackets from wikilink entries when populating the `wikilinks` field of `DesignFile`. It SHALL handle both bracketed (`[[JWT Auth]]`) and unbracketed (`JWT Auth`) formats.

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

#### Scenario: Parse bracketed wikilinks
- **WHEN** `parse_design_file()` is called on a file with `- [[JWT Auth]]` in the Wikilinks section
- **THEN** the `wikilinks` field SHALL contain `"JWT Auth"` (brackets stripped)

#### Scenario: Parse unbracketed wikilinks (backward compat)
- **WHEN** `parse_design_file()` is called on a file with `- JWT Auth` in the Wikilinks section
- **THEN** the `wikilinks` field SHALL contain `"JWT Auth"`

#### Scenario: Parse ## Stack section
- **WHEN** `parse_design_file()` is called on a file with `## Stack` section containing `- [[ST-001]]`
- **THEN** the `stack_refs` field SHALL contain `"ST-001"` (brackets stripped)

#### Scenario: Parse ## Guardrails section (backward compat)
- **WHEN** `parse_design_file()` is called on a file with `## Guardrails` section containing `- [[ST-001]]`
- **THEN** the `stack_refs` field SHALL contain `"ST-001"` (treated same as `## Stack`)

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

