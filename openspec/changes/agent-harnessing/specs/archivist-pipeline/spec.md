## ADDED Requirements

### Requirement: Dry-run project preview
The system SHALL provide `async dry_run_project(project_root: Path, config: LexibraryConfig) -> list[tuple[Path, ChangeLevel]]` in `src/lexibrary/archivist/pipeline.py` that discovers source files, runs change detection on each, and returns a list of files that would be processed with their change levels. No LLM calls SHALL be made and no files SHALL be written.

#### Scenario: Dry-run detects changed files
- **WHEN** `dry_run_project()` is called and 2 files have changed, 1 is new, and 5 are unchanged
- **THEN** the returned list SHALL contain 3 entries (the 2 changed + 1 new) with their respective `ChangeLevel` values

#### Scenario: Dry-run makes no side effects
- **WHEN** `dry_run_project()` is called
- **THEN** no design files SHALL be created, updated, or deleted
- **AND** no LLM calls SHALL be made

#### Scenario: Dry-run returns empty for clean project
- **WHEN** `dry_run_project()` is called and all files are unchanged
- **THEN** the returned list SHALL be empty

### Requirement: Dry-run files preview
The system SHALL provide `async dry_run_files(file_paths: list[Path], project_root: Path, config: LexibraryConfig) -> list[tuple[Path, ChangeLevel]]` for previewing specific files.

#### Scenario: Dry-run specific files
- **WHEN** `dry_run_files()` is called with 3 file paths
- **THEN** only those 3 files SHALL be checked and results returned for any that would change

### Requirement: Standalone START_HERE regeneration
The `generate_start_here()` function SHALL be independently callable (not only from `update_project()`). The `lexictl update --start-here` flag SHALL call `generate_start_here()` directly without running the full update pipeline.

#### Scenario: Regenerate START_HERE only
- **WHEN** `generate_start_here(project_root, config, archivist)` is called independently
- **THEN** `START_HERE.md` SHALL be regenerated based on current library state
- **AND** no design files SHALL be created or updated

### Requirement: lexictl update --dry-run flag
The `lexictl update` command SHALL accept a `--dry-run` flag. When set, it SHALL call `dry_run_project()` or `dry_run_files()` and display results in a table format showing `ChangeLevel` and file path. A summary line SHALL show total files and breakdown by category.

#### Scenario: Dry-run output format
- **WHEN** running `lexictl update --dry-run`
- **THEN** output SHALL show a `[yellow]DRY-RUN MODE — no files will be modified[/yellow]` header followed by lines like `NEW src/foo.py` and `CHANGED src/bar.py`, and a summary of file counts

### Requirement: lexictl update --start-here flag
The `lexictl update` command SHALL accept a `--start-here` flag that regenerates `START_HERE.md` only. It SHALL be mutually exclusive with `--changed-only` and positional path argument.

#### Scenario: Start-here only
- **WHEN** running `lexictl update --start-here`
- **THEN** only `START_HERE.md` SHALL be regenerated and a success message displayed

#### Scenario: Mutual exclusivity
- **WHEN** running `lexictl update --start-here --changed-only`
- **THEN** the command SHALL exit with an error about incompatible flags
