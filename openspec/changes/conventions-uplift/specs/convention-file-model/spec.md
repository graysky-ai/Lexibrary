## ADDED Requirements

### Requirement: ConventionFileFrontmatter model
The system SHALL define a `ConventionFileFrontmatter` Pydantic 2 model in `src/lexibrary/artifacts/convention.py` with fields:
- `title` (str) — display name of the convention
- `scope` (str) — scope identifier: `"project"` for project-wide, or a directory path (e.g., `"src/auth"`) for directory-scoped conventions. Default `"project"`.
- `tags` (list[str]) — categorization tags, default empty list
- `status` (Literal["draft", "active", "deprecated"]) — lifecycle status, default `"draft"`
- `source` (Literal["user", "agent", "config"]) — provenance of the convention, default `"user"`
- `priority` (int) — display ordering within same scope. Higher values appear first. Default `0`. Agent-created conventions default to `-1`.

#### Scenario: Frontmatter with defaults
- **WHEN** a `ConventionFileFrontmatter` is created with only `title="Use UTC everywhere"`
- **THEN** `scope` SHALL default to `"project"`, `tags` SHALL default to `[]`, `status` SHALL default to `"draft"`, `source` SHALL default to `"user"`, and `priority` SHALL default to `0`

#### Scenario: Frontmatter with all fields
- **WHEN** a `ConventionFileFrontmatter` is created with `title="Future annotations"`, `scope="project"`, `tags=["python"]`, `status="active"`, `source="config"`, `priority=10`
- **THEN** all fields SHALL be stored correctly

#### Scenario: Invalid status rejected
- **WHEN** a `ConventionFileFrontmatter` is created with `status="archived"`
- **THEN** Pydantic SHALL raise a `ValidationError`

#### Scenario: Invalid source rejected
- **WHEN** a `ConventionFileFrontmatter` is created with `source="llm"`
- **THEN** Pydantic SHALL raise a `ValidationError`

### Requirement: ConventionFile model
The system SHALL define a `ConventionFile` Pydantic 2 model in `src/lexibrary/artifacts/convention.py` with fields:
- `frontmatter` (ConventionFileFrontmatter) — validated YAML frontmatter
- `body` (str) — raw markdown body content (source of truth, preserved as-is)
- `rule` (str) — extracted from first paragraph of body (up to first blank line), default empty string
- `file_path` (Path | None) — path to the source file on disk, default None

The `name` property SHALL return `frontmatter.title`.
The `scope` property SHALL return `frontmatter.scope`.

#### Scenario: ConventionFile with rule extraction
- **WHEN** a `ConventionFile` is created with body containing a first paragraph and rationale section separated by a blank line
- **THEN** `rule` SHALL contain only the first paragraph text

#### Scenario: ConventionFile name property
- **WHEN** `convention.name` is accessed
- **THEN** it SHALL return `convention.frontmatter.title`

#### Scenario: ConventionFile with minimal fields
- **WHEN** a `ConventionFile` is created with only `frontmatter` and `body=""`
- **THEN** `rule` SHALL default to empty string and `file_path` SHALL default to None

### Requirement: Convention file slug naming
The system SHALL provide a `convention_slug(title: str) -> str` function in `src/lexibrary/artifacts/convention.py` that derives a file-system-safe slug from a convention title:
1. Lowercase the title
2. Replace spaces and non-alphanumeric characters with hyphens
3. Collapse consecutive hyphens
4. Strip leading/trailing hyphens
5. Truncate to 60 characters at a word boundary

And a `convention_file_path(title: str, conventions_dir: Path) -> Path` function that returns `conventions_dir / f"{slug}.md"`, appending a numeric suffix (`-2`, `-3`, etc.) if the path already exists on disk.

#### Scenario: Simple title slug
- **WHEN** `convention_slug("Future annotations import")` is called
- **THEN** it SHALL return `"future-annotations-import"`

#### Scenario: Title with special characters
- **WHEN** `convention_slug("Use `from __future__` import")` is called
- **THEN** it SHALL return `"use-from-future-import"`

#### Scenario: Long title truncation
- **WHEN** `convention_slug()` is called with a title longer than 60 characters
- **THEN** the result SHALL be at most 60 characters, truncated at a word boundary

#### Scenario: File path without collision
- **WHEN** `convention_file_path("Use UTC", conventions_dir)` is called and no file exists at that path
- **THEN** it SHALL return `conventions_dir / "use-utc.md"`

#### Scenario: File path with collision
- **WHEN** `convention_file_path("Use UTC", conventions_dir)` is called and `use-utc.md` already exists
- **THEN** it SHALL return `conventions_dir / "use-utc-2.md"`

### Requirement: Convention parser
The system SHALL provide a `parse_convention_file(path: Path) -> ConventionFile | None` function in `src/lexibrary/conventions/parser.py` that:
- Reads the file at `path`
- Extracts YAML frontmatter between `---` delimiters
- Validates frontmatter into `ConventionFileFrontmatter`
- Extracts the markdown body (everything after closing `---`)
- Extracts the `rule` from the first paragraph of the body
- Returns `None` if the file does not exist or frontmatter is malformed

#### Scenario: Parse well-formed convention file
- **WHEN** `parse_convention_file()` is called with a path to a valid convention file
- **THEN** it SHALL return a `ConventionFile` with frontmatter, body, rule, and file_path correctly populated

#### Scenario: Parse extracts rule from first paragraph
- **WHEN** the convention body is `"Every module must use X.\n\n**Rationale**: Because Y."`
- **THEN** `rule` SHALL be `"Every module must use X."`

#### Scenario: Parse returns None for missing file
- **WHEN** `parse_convention_file()` is called with a nonexistent path
- **THEN** it SHALL return `None`

#### Scenario: Parse returns None for malformed frontmatter
- **WHEN** `parse_convention_file()` is called with a file that has invalid YAML frontmatter
- **THEN** it SHALL return `None`

### Requirement: Convention serializer
The system SHALL provide a `serialize_convention_file(convention: ConventionFile) -> str` function in `src/lexibrary/conventions/serializer.py` that produces a markdown string with:
1. YAML frontmatter between `---` delimiters containing all `ConventionFileFrontmatter` fields
2. A blank line after the closing `---`
3. The full body text
4. A trailing newline

#### Scenario: Serialize convention with all fields
- **WHEN** `serialize_convention_file()` is called with a complete `ConventionFile`
- **THEN** the output SHALL contain YAML frontmatter with title, scope, tags, status, source, priority, followed by the body

#### Scenario: Serialize round-trip
- **WHEN** a convention file is serialized and then parsed back
- **THEN** the resulting `ConventionFile` SHALL have identical frontmatter and body values

#### Scenario: Output ends with trailing newline
- **WHEN** `serialize_convention_file()` is called with any valid input
- **THEN** the returned string SHALL end with `\n`

### Requirement: Artifacts module exports ConventionFile
`src/lexibrary/artifacts/__init__.py` SHALL re-export `ConventionFile` and `ConventionFileFrontmatter` alongside existing exports.

#### Scenario: ConventionFile importable from artifacts
- **WHEN** `from lexibrary.artifacts import ConventionFile` is used
- **THEN** the import SHALL succeed

#### Scenario: ConventionFileFrontmatter importable from artifacts
- **WHEN** `from lexibrary.artifacts import ConventionFileFrontmatter` is used
- **THEN** the import SHALL succeed
