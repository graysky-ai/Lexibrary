# index-orchestrator Specification

## Purpose
TBD - created by archiving change directory-indexes. Update Purpose after archive.
## Requirements
### Requirement: Index a single directory
The system SHALL provide an `index_directory(directory: Path, project_root: Path, config: LexibraryConfig) -> Path` function in `src/lexibrary/indexer/orchestrator.py` that generates and writes a `.aindex` file for one directory.

The function SHALL:
- Construct an `IgnoreMatcher` from the project config
- Call `generate_aindex()` to produce the `AIndexFile` model
- Call `serialize_aindex()` to convert to markdown string
- Call `write_artifact()` to write to the correct `.lexibrary/` mirror path
- Return the path of the written `.aindex` file

The `.aindex` output path SHALL be: `project_root / ".lexibrary" / relative_directory / ".aindex"` where `relative_directory` is `directory` relative to `project_root`.

#### Scenario: Index single directory writes .aindex to mirror path
- **WHEN** `index_directory()` is called for `src/auth/` in a project rooted at `/proj/`
- **THEN** a `.aindex` file SHALL be written at `/proj/.lexibrary/src/auth/.aindex`

#### Scenario: Index single directory creates mirror parent dirs
- **WHEN** `index_directory()` is called for a directory whose `.lexibrary/` mirror subdirectories do not yet exist
- **THEN** the mirror subdirectories SHALL be created automatically

#### Scenario: Index single directory returns output path
- **WHEN** `index_directory()` is called successfully
- **THEN** it SHALL return the path to the written `.aindex` file

### Requirement: Recursively index a directory tree bottom-up
The system SHALL provide an `index_recursive(directory: Path, project_root: Path, config: LexibraryConfig, *, progress_callback: Callable[[int, int, str], None] | None = None) -> IndexStats` function in `src/lexibrary/indexer/orchestrator.py` that indexes all directories in a tree in bottom-up order.

The function SHALL:
- Discover all directories using `discover_directories_bottom_up()` (deepest-first)
- Call `index_directory()` for each discovered directory
- Skip the `.lexibrary/` directory itself
- Call `progress_callback(current, total, directory_name)` if provided, after each directory is indexed
- Return an `IndexStats` dataclass with counts of directories indexed, files found, and errors

Bottom-up ordering SHALL ensure that child `.aindex` files exist before their parent directories are processed.

#### Scenario: Recursive index processes all directories
- **WHEN** `index_recursive()` is called for a project root with multiple nested directories
- **THEN** ALL directories (including root and all subdirectories, excluding `.lexibrary/`) SHALL have `.aindex` files written

#### Scenario: Recursive index processes child before parent
- **WHEN** `index_recursive()` is called for a project with `src/` containing `src/utils/`
- **THEN** `src/utils/.aindex` SHALL be written before `src/.aindex`

#### Scenario: Parent .aindex references child count from child .aindex
- **WHEN** `index_recursive()` is called and `src/utils/` has 3 files
- **THEN** the `utils/` entry in `src/.aindex` SHALL show description using the count from `src/utils/.aindex`

#### Scenario: .lexibrary/ directory is excluded from indexing
- **WHEN** `index_recursive()` is called on a project root
- **THEN** no `.aindex` file SHALL be generated for the `.lexibrary/` directory itself

#### Scenario: Progress callback is invoked per directory
- **WHEN** `index_recursive()` is called with a progress callback
- **THEN** the callback SHALL be called once per directory processed, with (current_count, total_count, directory_name)

#### Scenario: Stats reflect indexed count
- **WHEN** `index_recursive()` completes for a project with 5 directories
- **THEN** the returned `IndexStats.directories_indexed` SHALL be 5

### Requirement: IndexStats dataclass
The system SHALL provide an `IndexStats` dataclass in `src/lexibrary/indexer/orchestrator.py` with fields:
- `directories_indexed: int = 0`
- `files_found: int = 0`
- `errors: int = 0`

#### Scenario: IndexStats defaults to zero
- **WHEN** an `IndexStats` is created with no arguments
- **THEN** all fields SHALL be 0

