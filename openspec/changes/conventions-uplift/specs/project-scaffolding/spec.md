## MODIFIED Requirements

### Requirement: Stack directory in scaffolding
`lexictl init` SHALL create a `.lexibrary/stack/` directory, a `.lexibrary/concepts/` directory, and a `.lexibrary/conventions/` directory in the project skeleton. It SHALL NOT create a `HANDOFF.md` file.

#### Scenario: Init creates stack directory
- **WHEN** running `lexictl init` in an empty directory
- **THEN** `.lexibrary/stack/` SHALL be created

#### Scenario: Init creates conventions directory
- **WHEN** running `lexictl init` in an empty directory
- **THEN** `.lexibrary/conventions/` SHALL be created with a `.gitkeep` file

#### Scenario: Init does not create HANDOFF.md
- **WHEN** running `lexictl init` in an empty directory
- **THEN** `.lexibrary/HANDOFF.md` SHALL NOT be created

#### Scenario: Init creates IWH gitignore entry
- **WHEN** running `lexictl init` in an empty directory
- **THEN** `.gitignore` SHALL contain the `**/.iwh` pattern

### Requirement: Wizard-based scaffolder
`create_lexibrary_from_wizard(project_root: Path, answers: WizardAnswers) -> list[Path]` SHALL create the `.lexibrary/` skeleton using wizard answers. It SHALL return a list of all created file paths.

The function SHALL create:
- `.lexibrary/` directory
- `.lexibrary/concepts/` directory with `.gitkeep`
- `.lexibrary/conventions/` directory with `.gitkeep`
- `.lexibrary/stack/` directory with `.gitkeep`
- `.lexibrary/config.yaml` generated dynamically from `answers`
- `.lexibrary/START_HERE.md` placeholder
- `.lexignore` with wizard-provided ignore patterns

The function SHALL NOT create `HANDOFF.md`.

#### Scenario: Creates directory structure
- **WHEN** `create_lexibrary_from_wizard()` is called with valid answers
- **THEN** `.lexibrary/`, `.lexibrary/concepts/`, `.lexibrary/conventions/`, and `.lexibrary/stack/` SHALL exist

#### Scenario: Creates config from answers
- **WHEN** answers has `project_name="my-app"` and `llm_provider="anthropic"`
- **THEN** `.lexibrary/config.yaml` SHALL contain `project_name: my-app` and `provider: anthropic`

#### Scenario: Does NOT create HANDOFF.md
- **WHEN** `create_lexibrary_from_wizard()` is called
- **THEN** `.lexibrary/HANDOFF.md` SHALL NOT exist

#### Scenario: Creates .lexignore with patterns
- **WHEN** answers has `ignore_patterns=["dist/", "build/"]`
- **THEN** `.lexignore` SHALL contain those patterns

#### Scenario: Creates .lexignore empty when no patterns
- **WHEN** answers has `ignore_patterns=[]`
- **THEN** `.lexignore` SHALL exist with a header comment but no patterns

#### Scenario: Returns list of created paths
- **WHEN** `create_lexibrary_from_wizard()` completes
- **THEN** the returned list SHALL contain all created file paths including the conventions directory gitkeep
