## MODIFIED Requirements

### Requirement: artifacts module structure
The system SHALL have `src/lexibrary/artifacts/` as a proper Python package with `__init__.py` re-exporting all public model classes.

#### Scenario: artifacts package is importable
- **WHEN** importing `from lexibrary.artifacts import DesignFile`
- **THEN** the import succeeds without error

#### Scenario: artifacts package has module files
- **WHEN** inspecting `src/lexibrary/artifacts/`
- **THEN** it contains `__init__.py`, `design_file.py`, `aindex.py`, and `concept.py` (guardrail.py removed)

#### Scenario: stack module exists
- **WHEN** inspecting `src/lexibrary/stack/`
- **THEN** it contains `__init__.py`, `models.py`, `parser.py`, `serializer.py`, `template.py`, `index.py`, and `mutations.py`

## ADDED Requirements

### Requirement: Stack directory in scaffolding
`lexi init` SHALL create a `.lexibrary/stack/` directory (instead of `.lexibrary/guardrails/`) in the project skeleton.

#### Scenario: Init creates stack directory
- **WHEN** running `lexi init` in an empty directory
- **THEN** `.lexibrary/stack/` SHALL be created

#### Scenario: Init does not create guardrails directory
- **WHEN** running `lexi init` in an empty directory
- **THEN** `.lexibrary/guardrails/` SHALL NOT be created
