# index-generator Specification

## Purpose
TBD - created by archiving change directory-indexes. Update Purpose after archive.
## Requirements
### Requirement: Generate structural AIndexFile for a directory
The system SHALL provide a `generate_aindex(directory: Path, project_root: Path, ignore_matcher: IgnoreMatcher, binary_extensions: set[str]) -> AIndexFile` function in `src/lexibrary/indexer/generator.py` that produces an `AIndexFile` model for a given directory without making any LLM calls.

The function SHALL:
- List directory contents and filter out ignored entries via `ignore_matcher`
- For each non-ignored file: detect language by extension, count lines, produce a structural description
- For each non-ignored subdirectory: check for child `.aindex` in the `.lexibrary/` mirror tree; use its entry count for description if available, otherwise count direct children
- Generate a billboard sentence from the dominant language of contained files
- Build a `StalenessMetadata` with `source_hash` = SHA-256 of the sorted directory listing
- Set `local_conventions=[]` (Phase 2 — population is a future phase)
- Return an `AIndexFile` model (no I/O side effects)

File description format:
- Known text file: `"{Language} source ({N} lines)"` (e.g., `"Python source (42 lines)"`)
- Binary file (extension in `binary_extensions`): `"Binary file (.{ext})"`
- Unknown extension: `"Unknown file type"`

Directory description format:
- If child `.aindex` exists: `"Contains {N} files"` or `"Contains {N} files, {M} subdirectories"`
- If no child `.aindex`: `"Contains {N} items"` (direct listing count)

Billboard format:
- Single language: `"Directory containing {Language} source files."`
- Mixed languages: `"Mixed-language directory ({lang1}, {lang2})."`
- No source files (all binary/unknown): `"Directory containing binary and data files."`
- Empty directory: `"Empty directory."`

#### Scenario: Generate basic directory with files and subdirs
- **WHEN** `generate_aindex()` is called for a directory containing Python files and a subdirectory
- **THEN** it SHALL return an `AIndexFile` with correct file entries (Python source descriptions), a dir entry, and a Python billboard

#### Scenario: Generate empty directory
- **WHEN** `generate_aindex()` is called for an empty directory
- **THEN** it SHALL return an `AIndexFile` with `entries=[]`, `billboard="Empty directory."`, and `local_conventions=[]`

#### Scenario: Generate for mixed-language directory
- **WHEN** `generate_aindex()` is called for a directory with Python and JavaScript files
- **THEN** the billboard SHALL be `"Mixed-language directory (Python, JavaScript)."` (or similar two-language format)

#### Scenario: Binary files get binary description
- **WHEN** `generate_aindex()` is called for a directory containing `logo.png` (in `binary_extensions`)
- **THEN** the `logo.png` entry description SHALL be `"Binary file (.png)"`

#### Scenario: Ignored entries are excluded
- **WHEN** `generate_aindex()` is called for a directory where some entries match the `ignore_matcher`
- **THEN** those entries SHALL NOT appear in the returned `AIndexFile.entries`

#### Scenario: Subdir with existing child .aindex uses count from it
- **WHEN** `generate_aindex()` is called for a parent directory whose subdirectory already has a `.aindex` in the `.lexibrary/` mirror
- **THEN** the subdir entry description SHALL reference the file/subdir counts from the child `.aindex`

#### Scenario: Subdir without child .aindex falls back to direct count
- **WHEN** `generate_aindex()` is called for a parent directory whose subdirectory has no `.aindex` yet
- **THEN** the subdir entry description SHALL use the direct child count from filesystem listing

### Requirement: Language detection by file extension
The system SHALL provide an extension-to-language mapping used by `generate_aindex()` to determine file language for description text.

The mapping SHALL cover at minimum: Python (`.py`), JavaScript (`.js`, `.mjs`), TypeScript (`.ts`, `.tsx`), JavaScript/React (`.jsx`), HTML (`.html`, `.htm`), CSS (`.css`, `.scss`, `.sass`), YAML (`.yaml`, `.yml`), JSON (`.json`), TOML (`.toml`), Markdown (`.md`), Shell (`.sh`, `.bash`), Go (`.go`), Rust (`.rs`), Java (`.java`), C (`.c`, `.h`), C++ (`.cpp`, `.hpp`), Ruby (`.rb`), SQL (`.sql`).

Unknown extensions SHALL return `"Unknown"`.

#### Scenario: Detect Python file
- **WHEN** the extension mapping is queried for `.py`
- **THEN** it SHALL return `"Python"`

#### Scenario: Unknown extension returns Unknown
- **WHEN** the extension mapping is queried for `.xyz`
- **THEN** it SHALL return `"Unknown"`

