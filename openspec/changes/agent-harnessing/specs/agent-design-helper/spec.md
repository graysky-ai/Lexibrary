## ADDED Requirements

### Requirement: Design update command
The system SHALL provide a `lexi design update <source-file>` command in `src/lexibrary/cli/lexi_app.py` that resolves the design file for a source file and either displays it or scaffolds a new one.

#### Scenario: Existing design file displayed
- **WHEN** `lexi design update src/foo.py` is run and a design file exists for `src/foo.py`
- **THEN** the command SHALL print the design file path (relative to project root) and its full content
- **AND** SHALL print a reminder to set `updated_by: agent` in frontmatter

#### Scenario: New design file scaffolded
- **WHEN** `lexi design update src/new_module.py` is run and no design file exists
- **THEN** a template design file SHALL be created at the mirror path in `.lexibrary/blueprints/`
- **AND** the command SHALL print `[green]Created design scaffold:[/green]` with the path and template content

#### Scenario: Source file outside scope
- **WHEN** `lexi design update` is run for a file outside the configured `scope_root`
- **THEN** the command SHALL print an error message indicating the file is outside scope

### Requirement: Design scaffold generator
The system SHALL provide `generate_design_scaffold(source_path: Path, project_root: Path) -> str` in the archivist module that creates a template design file without LLM calls.

The scaffold SHALL include:
- YAML frontmatter with `source_path`, `updated_by: agent`, and current date
- Placeholder sections matching the design file format (Purpose, Key Components, Dependencies)
- Comments indicating what the agent should fill in

#### Scenario: Scaffold has correct frontmatter
- **WHEN** `generate_design_scaffold()` is called for `src/lexibrary/cli/lexi_app.py`
- **THEN** the returned string SHALL contain `source_path: src/lexibrary/cli/lexi_app.py` and `updated_by: agent`

#### Scenario: Scaffold has placeholder sections
- **WHEN** `generate_design_scaffold()` is called
- **THEN** the returned string SHALL contain `## Purpose`, `## Key Components`, and `## Dependencies` sections with placeholder comments
