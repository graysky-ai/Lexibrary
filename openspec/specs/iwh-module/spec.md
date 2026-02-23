# iwh-module Specification

## Purpose
TBD - created by archiving change agent-rules-iwh. Update Purpose after archive.
## Requirements
### Requirement: IWH Pydantic model
The system SHALL define an `IWHFile` Pydantic 2 `BaseModel` in `src/lexibrary/iwh/model.py` with fields: `author: str` (non-empty, free-form), `created: datetime` (timezone-aware), `scope: IWHScope` (Literal `"warning"`, `"incomplete"`, `"blocked"`), and `body: str` (freeform markdown, may be empty).

#### Scenario: Valid IWH model construction
- **WHEN** constructing `IWHFile(author="agent-abc", created=datetime.now(UTC), scope="incomplete", body="Work in progress")`
- **THEN** the model SHALL be created successfully with all fields accessible

#### Scenario: All scope values accepted
- **WHEN** constructing IWHFile with scope set to `"warning"`, `"incomplete"`, or `"blocked"` respectively
- **THEN** each SHALL succeed without validation error

#### Scenario: Invalid scope rejected
- **WHEN** constructing IWHFile with `scope="critical"`
- **THEN** Pydantic SHALL raise a `ValidationError`

#### Scenario: Empty body is valid
- **WHEN** constructing IWHFile with `body=""`
- **THEN** the model SHALL be created successfully (scope alone is meaningful)

#### Scenario: Empty author rejected
- **WHEN** constructing IWHFile with `author=""`
- **THEN** Pydantic SHALL raise a `ValidationError`

### Requirement: IWH parser
The system SHALL provide `parse_iwh(path: Path) -> IWHFile | None` in `src/lexibrary/iwh/parser.py` that reads a `.iwh` file with YAML frontmatter and markdown body. It SHALL follow the same frontmatter regex pattern as `stack/parser.py`.

#### Scenario: Valid .iwh file parsed
- **WHEN** calling `parse_iwh(path)` on a file with valid YAML frontmatter containing author, created, scope and a markdown body
- **THEN** it SHALL return an `IWHFile` with all fields populated

#### Scenario: Missing file returns None
- **WHEN** calling `parse_iwh(path)` on a path that does not exist
- **THEN** it SHALL return `None`

#### Scenario: No frontmatter returns None
- **WHEN** calling `parse_iwh(path)` on a file with no YAML frontmatter delimiters
- **THEN** it SHALL return `None`

#### Scenario: Invalid frontmatter returns None
- **WHEN** calling `parse_iwh(path)` on a file with malformed YAML in frontmatter
- **THEN** it SHALL return `None`

#### Scenario: Missing scope field returns None
- **WHEN** calling `parse_iwh(path)` on a file with valid YAML but no `scope` field
- **THEN** it SHALL return `None`

#### Scenario: Unknown scope value returns None
- **WHEN** calling `parse_iwh(path)` on a file with `scope: critical` (not in allowed values)
- **THEN** it SHALL return `None`

#### Scenario: Empty body parsed correctly
- **WHEN** calling `parse_iwh(path)` on a file with valid frontmatter but no body after the closing `---`
- **THEN** it SHALL return an `IWHFile` with `body == ""`

### Requirement: IWH serializer
The system SHALL provide `serialize_iwh(iwh: IWHFile) -> str` in `src/lexibrary/iwh/serializer.py` that produces a markdown string with YAML frontmatter containing `author`, `created` (ISO 8601), `scope`, followed by the body.

#### Scenario: Complete serialization
- **WHEN** calling `serialize_iwh()` on a fully populated IWHFile
- **THEN** the result SHALL start with `---\n`, contain YAML key-value pairs for author/created/scope, end frontmatter with `---\n`, and include the body

#### Scenario: ISO 8601 datetime
- **WHEN** serializing an IWHFile with a timezone-aware datetime
- **THEN** the `created` field in YAML SHALL be formatted as ISO 8601 (e.g., `2026-02-22T14:30:00+00:00`)

#### Scenario: Markdown body preserved
- **WHEN** serializing an IWHFile with multiline markdown body including headers and lists
- **THEN** the body SHALL appear verbatim after the closing `---` frontmatter delimiter

### Requirement: IWH roundtrip fidelity
The system SHALL support lossless roundtrip: `parse_iwh(path)` after writing `serialize_iwh(iwh)` to disk SHALL produce an equivalent `IWHFile`.

#### Scenario: All scopes roundtrip
- **WHEN** serializing an IWHFile with any valid scope, writing to disk, and parsing back
- **THEN** the parsed IWHFile SHALL have identical field values to the original

#### Scenario: Multiline body roundtrip
- **WHEN** serializing an IWHFile with a multiline markdown body containing headers, lists, and code blocks, writing to disk, and parsing back
- **THEN** the parsed body SHALL be identical to the original body

### Requirement: IWH reader
The system SHALL provide two functions in `src/lexibrary/iwh/reader.py`:
- `read_iwh(directory: Path) -> IWHFile | None` — reads `.iwh` from directory without deleting
- `consume_iwh(directory: Path) -> IWHFile | None` — reads `.iwh` from directory and deletes it

#### Scenario: Read existing .iwh
- **WHEN** calling `read_iwh(directory)` where `directory/.iwh` exists with valid content
- **THEN** it SHALL return an `IWHFile` and the file SHALL still exist on disk

#### Scenario: Read missing .iwh
- **WHEN** calling `read_iwh(directory)` where no `.iwh` file exists
- **THEN** it SHALL return `None`

#### Scenario: Consume reads and deletes
- **WHEN** calling `consume_iwh(directory)` where `directory/.iwh` exists with valid content
- **THEN** it SHALL return an `IWHFile` and the file SHALL no longer exist on disk

#### Scenario: Consume missing returns None
- **WHEN** calling `consume_iwh(directory)` where no `.iwh` file exists
- **THEN** it SHALL return `None`

#### Scenario: Consume corrupt file still deletes
- **WHEN** calling `consume_iwh(directory)` where `directory/.iwh` exists but contains unparseable content
- **THEN** it SHALL return `None` and the file SHALL no longer exist on disk

### Requirement: IWH writer
The system SHALL provide `write_iwh(directory: Path, *, author: str, scope: IWHScope, body: str) -> Path` in `src/lexibrary/iwh/writer.py` that creates a `.iwh` file in the specified directory.

#### Scenario: Creates .iwh file
- **WHEN** calling `write_iwh(directory, author="agent-1", scope="incomplete", body="WIP")`
- **THEN** a file at `directory/.iwh` SHALL exist with valid IWH content

#### Scenario: Content is parseable
- **WHEN** writing an IWH file and then parsing it with `parse_iwh()`
- **THEN** the parse SHALL succeed and return an IWHFile matching the write parameters

#### Scenario: Overwrites existing
- **WHEN** calling `write_iwh()` on a directory that already has a `.iwh` file
- **THEN** the existing file SHALL be overwritten with the new content (latest signal wins)

#### Scenario: Creates parent directories
- **WHEN** calling `write_iwh()` on a directory path that does not yet exist
- **THEN** the system SHALL create all necessary parent directories before writing the file

### Requirement: IWH gitignore integration
The system SHALL provide `ensure_iwh_gitignored(project_root: Path) -> bool` in `src/lexibrary/iwh/gitignore.py` that ensures `.gitignore` contains the `**/.iwh` pattern.

#### Scenario: Adds pattern to existing .gitignore
- **WHEN** calling `ensure_iwh_gitignored()` where `.gitignore` exists but does not contain `**/.iwh`
- **THEN** the pattern SHALL be appended and the function SHALL return `True`

#### Scenario: Creates .gitignore if missing
- **WHEN** calling `ensure_iwh_gitignored()` where no `.gitignore` file exists
- **THEN** a `.gitignore` SHALL be created containing `**/.iwh` and the function SHALL return `True`

#### Scenario: Idempotent when already present
- **WHEN** calling `ensure_iwh_gitignored()` where `.gitignore` already contains `**/.iwh`
- **THEN** the file SHALL not be modified and the function SHALL return `False`

#### Scenario: Recognizes alternative pattern
- **WHEN** calling `ensure_iwh_gitignored()` where `.gitignore` contains `.lexibrary/**/.iwh`
- **THEN** the function SHALL treat this as equivalent and return `False`

#### Scenario: Preserves existing content
- **WHEN** calling `ensure_iwh_gitignored()` where `.gitignore` has existing patterns
- **THEN** all existing patterns SHALL remain unchanged; the new pattern SHALL be appended

### Requirement: IWH public API
The `src/lexibrary/iwh/__init__.py` module SHALL re-export: `IWHFile`, `IWHScope`, `parse_iwh`, `serialize_iwh`, `read_iwh`, `consume_iwh`, `write_iwh`, `ensure_iwh_gitignored`.

#### Scenario: All public names importable from package
- **WHEN** importing `from lexibrary.iwh import IWHFile, IWHScope, parse_iwh, serialize_iwh, read_iwh, consume_iwh, write_iwh, ensure_iwh_gitignored`
- **THEN** all imports SHALL succeed without error

