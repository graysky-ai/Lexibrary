## ADDED Requirements

### Requirement: FileEntry dataclass
The system SHALL provide a `FileEntry` dataclass in `src/lexibrary/indexer/__init__.py` with the following fields:
- `name` (str): The filename (e.g., `"cli.py"`)
- `tokens` (int): Token count for the file (0 for binary files)
- `description` (str): A one-sentence summary of the file

#### Scenario: Create a FileEntry
- **WHEN** a `FileEntry` is instantiated with `name="cli.py"`, `tokens=150`, `description="CLI entry point"`
- **THEN** the instance SHALL have `name == "cli.py"`, `tokens == 150`, `description == "CLI entry point"`

#### Scenario: FileEntry with zero tokens
- **WHEN** a `FileEntry` is instantiated with `tokens=0`
- **THEN** the instance SHALL store `tokens == 0` without error

### Requirement: DirEntry dataclass
The system SHALL provide a `DirEntry` dataclass in `src/lexibrary/indexer/__init__.py` with the following fields:
- `name` (str): The subdirectory name with trailing slash (e.g., `"config/"`)
- `description` (str): A 1-2 sentence summary of the subdirectory

#### Scenario: Create a DirEntry
- **WHEN** a `DirEntry` is instantiated with `name="config/"`, `description="Configuration loading and validation"`
- **THEN** the instance SHALL have `name == "config/"` and `description == "Configuration loading and validation"`

### Requirement: IandexData dataclass
The system SHALL provide an `IandexData` dataclass in `src/lexibrary/indexer/__init__.py` with the following fields:
- `directory_name` (str): The directory name (e.g., `"lexibrary/"`)
- `summary` (str): A 1-3 sentence directory summary
- `files` (list[FileEntry]): File entries, defaulting to an empty list
- `subdirectories` (list[DirEntry]): Subdirectory entries, defaulting to an empty list

#### Scenario: Create IandexData with files and subdirectories
- **WHEN** an `IandexData` is instantiated with a directory name, summary, a list of `FileEntry` objects, and a list of `DirEntry` objects
- **THEN** all fields SHALL be accessible and contain the provided values

#### Scenario: Create IandexData with defaults
- **WHEN** an `IandexData` is instantiated with only `directory_name` and `summary`
- **THEN** `files` SHALL default to an empty list and `subdirectories` SHALL default to an empty list

### Requirement: Data models use stdlib dataclasses
The data models SHALL be implemented using Python's stdlib `dataclasses` module with no external dependencies.

#### Scenario: No external imports
- **WHEN** the `src/lexibrary/indexer/__init__.py` module is inspected
- **THEN** it SHALL import only from `dataclasses` and `pathlib` (stdlib modules)
