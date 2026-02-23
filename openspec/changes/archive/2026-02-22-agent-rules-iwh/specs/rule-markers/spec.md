## ADDED Requirements

### Requirement: Marker constants
The system SHALL define in `src/lexibrary/init/rules/markers.py`:
- `MARKER_START = "<!-- lexibrary:start -->"`
- `MARKER_END = "<!-- lexibrary:end -->"`

#### Scenario: Constants are accessible
- **WHEN** importing `from lexibrary.init.rules.markers import MARKER_START, MARKER_END`
- **THEN** `MARKER_START` SHALL equal `"<!-- lexibrary:start -->"` and `MARKER_END` SHALL equal `"<!-- lexibrary:end -->"`

### Requirement: Section detection
The system SHALL provide `has_lexibrary_section(content: str) -> bool` that returns `True` if the content contains both `MARKER_START` and `MARKER_END`.

#### Scenario: Detects markers present
- **WHEN** calling `has_lexibrary_section()` with content containing both markers
- **THEN** it SHALL return `True`

#### Scenario: No markers returns False
- **WHEN** calling `has_lexibrary_section()` with content containing neither marker
- **THEN** it SHALL return `False`

#### Scenario: Only start marker returns False
- **WHEN** calling `has_lexibrary_section()` with content containing only the start marker
- **THEN** it SHALL return `False`

### Requirement: Section replacement
The system SHALL provide `replace_lexibrary_section(content: str, new_section: str) -> str` that replaces everything between markers (inclusive of markers) with the new section wrapped in markers.

#### Scenario: Replaces content between markers
- **WHEN** calling `replace_lexibrary_section()` with content containing markers and old text between them
- **THEN** the returned string SHALL contain the new section between markers, with content outside markers unchanged

#### Scenario: Surrounding content preserved
- **WHEN** calling `replace_lexibrary_section()` with content before and after the marker block
- **THEN** both the preceding and following content SHALL remain unchanged

#### Scenario: Handles whitespace around markers
- **WHEN** calling `replace_lexibrary_section()` with extra blank lines around markers
- **THEN** the replacement SHALL succeed and produce clean output

### Requirement: Section append
The system SHALL provide `append_lexibrary_section(content: str, new_section: str) -> str` that appends the new section wrapped in markers to the end of the content.

#### Scenario: Appends to existing content
- **WHEN** calling `append_lexibrary_section()` with non-empty content
- **THEN** the returned string SHALL contain the original content followed by the marker-delimited section

#### Scenario: Appends to empty content
- **WHEN** calling `append_lexibrary_section()` with `content=""`
- **THEN** the returned string SHALL contain only the marker-delimited section
