## ADDED Requirements

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

## REMOVED Requirements

### Requirement: FileEntry dataclass
**Reason**: Replaced by `AIndexEntry` Pydantic model with `entry_type: Literal["file", "dir"]`. The `tokens` field is deferred to Phase 4+ when token counting is needed.
**Migration**: Replace `FileEntry(name=n, tokens=0, description=d)` with `AIndexEntry(name=n, entry_type="file", description=d)`.

### Requirement: DirEntry dataclass
**Reason**: Replaced by `AIndexEntry` with `entry_type="dir"`. Trailing slash on directory names is now handled by the serializer, not the model.
**Migration**: Replace `DirEntry(name=n, description=d)` with `AIndexEntry(name=n, entry_type="dir", description=d)`.

### Requirement: IandexData dataclass
**Reason**: Replaced by `AIndexFile` Pydantic model (introduced in Phase 1) with `directory_path`, `billboard`, `entries`, `local_conventions`, and `metadata` fields.
**Migration**: Replace `IandexData(directory_name=n, summary=s, files=f, subdirectories=d)` with `AIndexFile(directory_path=n, billboard=s, entries=[...], metadata=m)`.

### Requirement: Data models use stdlib dataclasses
**Reason**: The new models use Pydantic 2 (already a project dependency) for consistent validation across all config and artifact models. Stdlib dataclasses were an over-constraint.
**Migration**: No user-facing migration — internal implementation detail.
