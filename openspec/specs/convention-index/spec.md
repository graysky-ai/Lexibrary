# convention-index Specification

## Purpose
TBD - created by archiving change conventions-uplift. Update Purpose after archive.
## Requirements
### Requirement: ConventionIndex class
The system SHALL provide a `ConventionIndex` class in `src/lexibrary/conventions/index.py` that:
- Is constructed with `conventions_dir: Path` pointing to `.lexibrary/conventions/`
- Provides `load() -> None` that scans the directory and parses all `.md` files into `ConventionFile` objects
- Stores parsed conventions in a `conventions: list[ConventionFile]` attribute

#### Scenario: Load conventions from directory
- **WHEN** `ConventionIndex(conventions_dir).load()` is called on a directory with 3 valid convention files
- **THEN** `index.conventions` SHALL contain 3 `ConventionFile` objects

#### Scenario: Load empty directory
- **WHEN** `ConventionIndex(conventions_dir).load()` is called on an empty directory
- **THEN** `index.conventions` SHALL be an empty list

#### Scenario: Load skips malformed files
- **WHEN** `ConventionIndex(conventions_dir).load()` is called on a directory with 2 valid and 1 malformed convention files
- **THEN** `index.conventions` SHALL contain 2 `ConventionFile` objects (malformed file skipped)

#### Scenario: Load nonexistent directory
- **WHEN** `ConventionIndex(conventions_dir).load()` is called on a directory that does not exist
- **THEN** `index.conventions` SHALL be an empty list (no error raised)

### Requirement: Find conventions by scope
The `ConventionIndex` SHALL provide `find_by_scope(file_path: str, scope_root: str = ".") -> list[ConventionFile]` that returns all conventions applicable to a given file path, ordered by scope specificity (root-to-leaf), then by priority descending, then by title alphabetically.

The algorithm SHALL:
1. Build an ancestry chain from the file's parent directory to `scope_root` (inclusive)
2. Collect conventions where `scope == "project"` or where the file path starts with the convention's scope (normalized with trailing `/`)
3. Order scopes root-to-leaf: `project` first, then `.`, then deeper directories
4. Within the same scope, order by priority descending, then title alphabetically

#### Scenario: File inherits project-wide and directory-scoped conventions
- **WHEN** `find_by_scope("src/auth/login.py")` is called and conventions exist with `scope="project"` and `scope="src/auth"`
- **THEN** the result SHALL contain both conventions, with the project-scoped convention first and the directory-scoped convention second

#### Scenario: File with no matching conventions
- **WHEN** `find_by_scope("src/utils/helpers.py")` is called and no conventions have matching scopes
- **THEN** the result SHALL be an empty list

#### Scenario: Priority ordering within same scope
- **WHEN** two conventions share `scope="src/auth"` with priorities 5 and -1
- **THEN** the priority-5 convention SHALL appear before the priority-(-1) convention

#### Scenario: Scope resolution stops at scope_root
- **WHEN** `find_by_scope("src/auth/login.py", scope_root="src")` is called
- **THEN** conventions with scope `"."` (project root) SHALL NOT be included (only `"project"` and paths within `"src/"` match)

### Requirement: Find conventions by scope with display limit
The `ConventionIndex` SHALL provide `find_by_scope_limited(file_path: str, scope_root: str = ".", limit: int = 5) -> tuple[list[ConventionFile], int]` that returns at most `limit` conventions and the total count of applicable conventions.

When truncating, the method SHALL keep the most specific (leaf-ward) conventions and drop the most general (root-ward) conventions. The returned tuple is `(conventions, total_count)`.

#### Scenario: Under limit returns all
- **WHEN** 3 conventions apply and limit is 5
- **THEN** all 3 conventions SHALL be returned and total_count SHALL be 3

#### Scenario: Over limit truncates root-ward
- **WHEN** 8 conventions apply (3 project-wide, 2 from `src/`, 3 from `src/auth/`) and limit is 5
- **THEN** the returned list SHALL contain the 3 from `src/auth/` and 2 from `src/`, and total_count SHALL be 8

#### Scenario: Limit of zero returns empty
- **WHEN** `find_by_scope_limited()` is called with `limit=0`
- **THEN** an empty list SHALL be returned and total_count SHALL reflect the actual count

### Requirement: Search conventions
The `ConventionIndex` SHALL provide `search(query: str) -> list[ConventionFile]` that returns conventions matching the query against title, body, and tags using case-insensitive substring matching.

#### Scenario: Search by title
- **WHEN** `index.search("annotations")` is called and a convention titled "Future annotations import" exists
- **THEN** the result SHALL include that convention

#### Scenario: Search by body content
- **WHEN** `index.search("PEP 604")` is called and a convention body mentions "PEP 604"
- **THEN** the result SHALL include that convention

#### Scenario: Search by tag
- **WHEN** `index.search("python")` is called and a convention has tag "python"
- **THEN** the result SHALL include that convention

#### Scenario: Search no results
- **WHEN** `index.search("nonexistent")` is called and no conventions match
- **THEN** the result SHALL be an empty list

### Requirement: Filter by tag
The `ConventionIndex` SHALL provide `by_tag(tag: str) -> list[ConventionFile]` that returns all conventions having the specified tag (case-insensitive comparison).

#### Scenario: Filter by tag
- **WHEN** `index.by_tag("python")` is called and 2 of 5 conventions have the "python" tag
- **THEN** the result SHALL contain exactly those 2 conventions

#### Scenario: Filter by tag no matches
- **WHEN** `index.by_tag("nonexistent")` is called
- **THEN** the result SHALL be an empty list

### Requirement: Filter by status
The `ConventionIndex` SHALL provide `by_status(status: str) -> list[ConventionFile]` that returns all conventions with the specified status.

#### Scenario: Filter by draft status
- **WHEN** `index.by_status("draft")` is called and 3 of 8 conventions are drafts
- **THEN** the result SHALL contain exactly those 3 conventions

#### Scenario: Filter by active status
- **WHEN** `index.by_status("active")` is called
- **THEN** the result SHALL contain only active conventions

### Requirement: List convention names
The `ConventionIndex` SHALL provide `names() -> list[str]` that returns a sorted list of all convention titles.

#### Scenario: List names
- **WHEN** `index.names()` is called after loading 3 conventions
- **THEN** it SHALL return a sorted list of 3 convention title strings

### Requirement: ConventionIndex exported from conventions package
`ConventionIndex` SHALL be importable from `lexibrary.conventions`.

#### Scenario: Import ConventionIndex
- **WHEN** `from lexibrary.conventions import ConventionIndex` is used
- **THEN** the import SHALL succeed

