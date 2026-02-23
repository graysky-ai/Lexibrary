# concept-template Specification

## Purpose
TBD - created by archiving change concepts-wiki. Update Purpose after archive.
## Requirements
### Requirement: render_concept_template function
The system SHALL provide `render_concept_template(name: str, tags: list[str] | None = None) -> str` in `src/lexibrary/wiki/template.py` that returns a markdown string for a new concept file with:
1. YAML frontmatter with `title` set to `name`, `aliases: []`, `tags` set to provided tags or `[]`, `status: draft`
2. A body with placeholder sections: a summary paragraph prompt, `## Details`, `## Decision Log`, and `## Related` with `<!-- add [[wikilinks]] here -->` comment

#### Scenario: Render template with name only
- **WHEN** `render_concept_template("JWT Auth")` is called
- **THEN** the output SHALL contain frontmatter with `title: JWT Auth`, `status: draft`, `tags: []`, and body with placeholder sections

#### Scenario: Render template with tags
- **WHEN** `render_concept_template("JWT Auth", tags=["auth", "security"])` is called
- **THEN** the frontmatter SHALL contain `tags: [auth, security]`

### Requirement: Concept file path derivation
The system SHALL provide `concept_file_path(name: str, concepts_dir: Path) -> Path` in `src/lexibrary/wiki/template.py` that converts a concept name to a PascalCase file path by removing spaces and special characters, capitalizing word boundaries, and appending `.md`. The file SHALL be placed directly in `concepts_dir`.

#### Scenario: Derive path from name
- **WHEN** `concept_file_path("JWT Auth", Path(".lexibrary/concepts"))` is called
- **THEN** it SHALL return `Path(".lexibrary/concepts/JWTAuth.md")`

#### Scenario: Derive path with special characters
- **WHEN** `concept_file_path("Rate Limiting (API)", Path(".lexibrary/concepts"))` is called
- **THEN** it SHALL return `Path(".lexibrary/concepts/RateLimitingAPI.md")` (special characters stripped, PascalCase)

