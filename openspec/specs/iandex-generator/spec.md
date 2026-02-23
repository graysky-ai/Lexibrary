# iandex-generator Specification

## Purpose
TBD - created by archiving change iandex-format. Update Purpose after archive.
## Requirements
### Requirement: Generate Markdown from IandexData
`generate_iandex(data: IandexData) -> str` function in `src/lexibrary/indexer/generator.py`. When building file descriptions for the Child Map, the generator SHALL:
1. Check if a design file exists at `mirror_path(project_root, file)`
2. If yes → call `parse_design_file_frontmatter(design_file_path)` and use the `description` field
3. If no → fall back to the structural description: `"{Language} source ({N} lines)"`

This makes `.aindex` descriptions richer as design files are created, while maintaining backwards compatibility.

#### Scenario: File with design file gets frontmatter description
- **WHEN** `generate_iandex()` processes a file that has a corresponding design file
- **THEN** the Child Map description SHALL use the `description` from the design file's YAML frontmatter

#### Scenario: File without design file gets structural description
- **WHEN** `generate_iandex()` processes a file that has no corresponding design file
- **THEN** the Child Map description SHALL use the structural fallback format: `"{Language} source ({N} lines)"`

#### Scenario: Design file with empty description
- **WHEN** `generate_iandex()` processes a file whose design file has an empty description
- **THEN** the Child Map description SHALL fall back to the structural description

### Requirement: H1 header is directory name
The generated Markdown SHALL start with an H1 header (`# `) containing the directory name.

#### Scenario: H1 contains directory name
- **WHEN** `generate_iandex()` is called with `directory_name="lexibrary/"`
- **THEN** the first line of output SHALL be `# lexibrary/`

### Requirement: Summary follows H1
The directory summary SHALL appear as a paragraph after the H1 header, separated by a blank line.

#### Scenario: Summary paragraph placement
- **WHEN** `generate_iandex()` is called with a summary string
- **THEN** the summary SHALL appear on the line after the blank line following the H1 header

### Requirement: Files table format
The Files section SHALL use a Markdown table with columns: `File`, `Tokens`, `Description`. File names SHALL be wrapped in backticks.

#### Scenario: File entry in table
- **WHEN** a `FileEntry` with `name="cli.py"`, `tokens=150`, `description="CLI entry point"` is included
- **THEN** the table SHALL contain a row `| \`cli.py\` | 150 | CLI entry point |`

### Requirement: Subdirectories table format
The Subdirectories section SHALL use a Markdown table with columns: `Directory`, `Description`. Directory names SHALL be wrapped in backticks and SHALL always have a trailing `/`.

#### Scenario: Directory entry in table
- **WHEN** a `DirEntry` with `name="config/"` is included
- **THEN** the table SHALL contain a row with `` `config/` `` in the Directory column

#### Scenario: Directory name without trailing slash
- **WHEN** a `DirEntry` has `name="config"` (no trailing slash)
- **THEN** the generator SHALL append a `/` so the output shows `` `config/` ``

### Requirement: Files sorted alphabetically
File entries in the generated table SHALL be sorted alphabetically by filename, case-insensitively.

#### Scenario: Case-insensitive file sorting
- **WHEN** files include `"Zebra.py"`, `"alpha.py"`, `"Beta.py"`
- **THEN** the table rows SHALL appear in order: `alpha.py`, `Beta.py`, `Zebra.py`

### Requirement: Subdirectories sorted alphabetically
Subdirectory entries in the generated table SHALL be sorted alphabetically by name, case-insensitively.

#### Scenario: Case-insensitive directory sorting
- **WHEN** subdirectories include `"Zutils/"`, `"api/"`, `"Config/"`
- **THEN** the table rows SHALL appear in order: `api/`, `Config/`, `Zutils/`

### Requirement: Empty sections show none marker
When there are no files or no subdirectories, the corresponding section SHALL display `(none)` instead of a table.

#### Scenario: No files
- **WHEN** `generate_iandex()` is called with an empty `files` list
- **THEN** the Files section SHALL contain `(none)` with no table headers

#### Scenario: No subdirectories
- **WHEN** `generate_iandex()` is called with an empty `subdirectories` list
- **THEN** the Subdirectories section SHALL contain `(none)` with no table headers

### Requirement: Trailing newline
The generated Markdown string SHALL end with a trailing newline character.

#### Scenario: Output ends with newline
- **WHEN** `generate_iandex()` produces output
- **THEN** the last character of the returned string SHALL be `\n`

### Requirement: Blank line separation
The generated Markdown SHALL have blank lines after the H1 header, after the summary, and after each section.

#### Scenario: Structural blank lines
- **WHEN** `generate_iandex()` produces output
- **THEN** there SHALL be a blank line between the H1 and summary, between the summary and Files section, and between the Files section and Subdirectories section

### Requirement: Pipe characters in descriptions are escaped
The generator SHALL escape literal `|` characters in file and directory descriptions as `\|` to prevent breaking the Markdown table format.

#### Scenario: Description contains pipe character
- **WHEN** a `FileEntry` has `description="Handles input | output streams"`
- **THEN** the generated table row SHALL contain `Handles input \| output streams`

