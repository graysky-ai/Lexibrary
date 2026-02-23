# concept-serializer Specification

## Purpose
TBD - created by archiving change concepts-wiki. Update Purpose after archive.
## Requirements
### Requirement: serialize_concept_file function
The system SHALL provide `serialize_concept_file(concept: ConceptFile) -> str` in `src/lexibrary/wiki/serializer.py` that produces a markdown string with:
1. YAML frontmatter delimited by `---` containing `title`, `aliases`, `tags`, `status`, and `superseded_by` (only if not None)
2. The raw `body` content as-is (no modification)
3. A trailing newline

#### Scenario: Serialize fully populated concept
- **WHEN** `serialize_concept_file()` is called with a ConceptFile with frontmatter fields and body
- **THEN** the output SHALL contain YAML frontmatter followed by the body content followed by a trailing newline

#### Scenario: Serialize concept with empty aliases and tags
- **WHEN** `serialize_concept_file()` is called with a ConceptFile with empty `aliases` and `tags`
- **THEN** the YAML frontmatter SHALL include `aliases: []` and `tags: []`

#### Scenario: Body preserved exactly
- **WHEN** `serialize_concept_file()` is called with a body containing wikilinks, headings, and code blocks
- **THEN** the body SHALL appear in the output unchanged (no bracket modification, no section rewriting)

### Requirement: Concept file round-trip integrity
The system SHALL preserve all data through a serialize-parse cycle: `serialize_concept_file(cf)` written to disk and then `parse_concept_file(path)` SHALL produce a ConceptFile with equivalent frontmatter and body.

#### Scenario: Round-trip with all fields
- **WHEN** a fully populated ConceptFile is serialized, written, and parsed back
- **THEN** frontmatter fields and body SHALL match the original

