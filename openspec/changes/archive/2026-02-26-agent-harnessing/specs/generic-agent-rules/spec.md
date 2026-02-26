## ADDED Requirements

### Requirement: Generic rules file generation
The system SHALL provide `generate_generic_rules(project_root: Path) -> list[Path]` in `src/lexibrary/init/rules/generic.py` that generates a `LEXIBRARY_RULES.md` file at the project root containing core rules and all skill content.

#### Scenario: Generate generic rules
- **WHEN** `generate_generic_rules()` is called
- **THEN** `LEXIBRARY_RULES.md` SHALL be created at the project root
- **AND** it SHALL contain the output of `get_core_rules()` and all skill content functions

#### Scenario: Overwrites on regeneration
- **WHEN** `generate_generic_rules()` is called and `LEXIBRARY_RULES.md` already exists
- **THEN** the file SHALL be overwritten with current content

#### Scenario: Returns created paths
- **WHEN** `generate_generic_rules()` is called
- **THEN** the returned list SHALL contain the path to `LEXIBRARY_RULES.md`

### Requirement: Generic environment registered
The `"generic"` environment SHALL be registered in `src/lexibrary/init/rules/__init__.py` so that `generate_rules(root, ["generic"])` works and `supported_environments()` includes `"generic"`.

#### Scenario: Generate for generic environment
- **WHEN** `generate_rules(root, ["generic"])` is called
- **THEN** it SHALL return `{"generic": [path_to_LEXIBRARY_RULES.md]}`

#### Scenario: Supported environments includes generic
- **WHEN** `supported_environments()` is called
- **THEN** the returned list SHALL include `"generic"`
