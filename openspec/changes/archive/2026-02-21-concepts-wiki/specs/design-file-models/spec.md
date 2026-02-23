## MODIFIED Requirements

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

The `## Wikilinks` section SHALL serialize each wikilink wrapped in `[[double brackets]]` as a bullet list item. If the wikilink already contains brackets, it SHALL NOT double-wrap.

#### Scenario: Serialize fully populated design file
- **WHEN** `serialize_design_file()` is called with a DesignFile containing all fields populated
- **THEN** the output SHALL contain YAML frontmatter, all sections, and HTML comment footer

#### Scenario: Serialize minimal design file
- **WHEN** `serialize_design_file()` is called with a DesignFile where optional fields are empty/None
- **THEN** optional sections (Tests, Complexity Warning, Wikilinks, Tags, Guardrails) SHALL be omitted from output

#### Scenario: Metadata footer format
- **WHEN** `serialize_design_file()` is called
- **THEN** the HTML comment footer SHALL use the format `<!-- lexibrary:meta\nkey: value\n-->` with fields: source, source_hash, interface_hash, design_hash, generated, generator

#### Scenario: Wikilinks serialized with brackets
- **WHEN** `serialize_design_file()` is called with `wikilinks=["JWT Auth", "Rate Limiting"]`
- **THEN** the Wikilinks section SHALL contain `- [[JWT Auth]]` and `- [[Rate Limiting]]`

#### Scenario: Wikilinks not double-wrapped
- **WHEN** `serialize_design_file()` is called with `wikilinks=["[[JWT Auth]]"]` (already bracketed)
- **THEN** the output SHALL contain `- [[JWT Auth]]` (not `- [[[[JWT Auth]]]]`)

### Requirement: Design file parser
The system SHALL provide parsing functions in `src/lexibrary/artifacts/design_file_parser.py`:
- `parse_design_file(path: Path) -> DesignFile | None` — full parse, returns None if file doesn't exist or is malformed
- `parse_design_file_metadata(path: Path) -> StalenessMetadata | None` — extracts only the HTML comment footer (cheap, reads from end of file)
- `parse_design_file_frontmatter(path: Path) -> DesignFileFrontmatter | None` — extracts only the YAML frontmatter

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
