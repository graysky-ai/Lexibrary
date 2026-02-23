## ADDED Requirements

### Requirement: parse_concept_file function
The system SHALL provide `parse_concept_file(path: Path) -> ConceptFile | None` in `src/lexibrary/wiki/parser.py` that:
1. Reads the file at `path`
2. Extracts YAML frontmatter delimited by `---`
3. Validates frontmatter into `ConceptFileFrontmatter`
4. Extracts body content (everything after the closing `---`)
5. Parses body to populate `summary`, `related_concepts`, `linked_files`, and `decision_log`
6. Returns a populated `ConceptFile` or `None` if the file doesn't exist or is malformed

#### Scenario: Parse well-formed concept file
- **WHEN** `parse_concept_file()` is called on a valid concept file with frontmatter and body
- **THEN** it SHALL return a `ConceptFile` with all fields populated from the file content

#### Scenario: Parse file with no frontmatter
- **WHEN** `parse_concept_file()` is called on a markdown file without `---` delimiters
- **THEN** it SHALL return `None`

#### Scenario: Parse nonexistent file
- **WHEN** `parse_concept_file()` is called on a path that doesn't exist
- **THEN** it SHALL return `None`

#### Scenario: Parse file with invalid frontmatter
- **WHEN** `parse_concept_file()` is called on a file with YAML frontmatter that fails validation (e.g., missing `title`)
- **THEN** it SHALL return `None`

### Requirement: Summary extraction from body
The parser SHALL extract the `summary` from the first non-empty paragraph of the body (text before the first `##` heading or end of body, whichever comes first). Leading/trailing whitespace SHALL be stripped.

#### Scenario: Summary from first paragraph
- **WHEN** a concept file body starts with "This concept covers authentication patterns.\n\n## Details\n..."
- **THEN** `summary` SHALL be `"This concept covers authentication patterns."`

#### Scenario: Empty body yields empty summary
- **WHEN** a concept file body is empty or whitespace-only
- **THEN** `summary` SHALL be `""`

### Requirement: Wikilink extraction from body
The parser SHALL extract all `[[wikilink]]` references from the body into `related_concepts`. Bracket delimiters SHALL be stripped from the extracted names.

#### Scenario: Extract wikilinks
- **WHEN** a concept file body contains `"See [[JWT Auth]] and [[Rate Limiting]]"`
- **THEN** `related_concepts` SHALL be `["JWT Auth", "Rate Limiting"]`

#### Scenario: No wikilinks
- **WHEN** a concept file body contains no `[[...]]` patterns
- **THEN** `related_concepts` SHALL be `[]`

### Requirement: Decision log extraction from body
The parser SHALL extract bullet items from a `## Decision Log` section into `decision_log`. Each bullet item (lines starting with `- ` or `* `) SHALL be included as a string with the bullet prefix stripped.

#### Scenario: Extract decision log
- **WHEN** a concept file body contains a `## Decision Log` section with three bullet items
- **THEN** `decision_log` SHALL contain three strings matching the bullet text

#### Scenario: No decision log section
- **WHEN** a concept file body has no `## Decision Log` heading
- **THEN** `decision_log` SHALL be `[]`

### Requirement: File reference extraction from body
The parser SHALL extract file path references from the body into `linked_files`. File references are backtick-delimited strings matching common source file patterns (containing `/` and ending in a known extension like `.py`, `.ts`, `.js`, `.yaml`, `.toml`, `.md`).

#### Scenario: Extract file references
- **WHEN** a concept file body contains `` `src/auth/service.py` `` and `` `src/auth/models.py` ``
- **THEN** `linked_files` SHALL be `["src/auth/service.py", "src/auth/models.py"]`

#### Scenario: No file references
- **WHEN** a concept file body contains no backtick-delimited file paths
- **THEN** `linked_files` SHALL be `[]`
