# iandex-data-models Specification

## Purpose
TBD - created by archiving change iandex-format. Update Purpose after archive.
## Requirements
### Requirement: AIndexEntry Pydantic model
The system SHALL provide an `AIndexEntry` Pydantic 2 model in `src/lexibrary/artifacts/aindex.py` with the following fields:
- `name` (str): The entry name — filename (e.g., `"cli.py"`) or subdirectory name (e.g., `"config"`)
- `entry_type` (Literal["file", "dir"]): Whether this entry is a file or directory
- `description` (str): A structural description of the entry

#### Scenario: Create a file AIndexEntry
- **WHEN** an `AIndexEntry` is instantiated with `name="cli.py"`, `entry_type="file"`, `description="Python source (42 lines)"`
- **THEN** the instance SHALL have all three fields accessible with the provided values

#### Scenario: Create a dir AIndexEntry
- **WHEN** an `AIndexEntry` is instantiated with `name="config"`, `entry_type="dir"`, `description="Contains 3 files"`
- **THEN** the instance SHALL have `entry_type == "dir"`

#### Scenario: Invalid entry_type rejected
- **WHEN** an `AIndexEntry` is instantiated with `entry_type="symlink"` or any value outside `Literal["file", "dir"]`
- **THEN** Pydantic SHALL raise a `ValidationError`

