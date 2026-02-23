## ADDED Requirements

### Requirement: .lexignore file loading
The system SHALL load patterns from a `.lexignore` file at the project root, using pathspec with `"gitignore"` pattern name (same as `.gitignore` parsing). The `.lexignore` file follows `.gitignore` format and rules.

#### Scenario: .lexignore patterns applied
- **WHEN** a `.lexignore` file exists with pattern `**/migrations/`
- **THEN** files under any `migrations/` directory SHALL be ignored by the IgnoreMatcher

#### Scenario: .lexignore file missing
- **WHEN** no `.lexignore` file exists at the project root
- **THEN** the IgnoreMatcher SHALL operate normally without error (no lexignore patterns applied)

### Requirement: Three-layer ignore system
The `IgnoreMatcher` SHALL merge patterns from three sources in order:
1. `.gitignore` — standard git ignores
2. `.lexignore` — Lexibrary-specific ignores (files in git that shouldn't get design files)
3. `config.ignore.additional_patterns` — programmatic patterns from config

A file ignored by ANY layer SHALL be excluded.

#### Scenario: File ignored by lexignore only
- **WHEN** a file matches a `.lexignore` pattern but not `.gitignore` or config patterns
- **THEN** the file SHALL be excluded by `is_ignored()`

#### Scenario: All three layers merged
- **WHEN** patterns exist in all three layers
- **THEN** a file matching any single layer SHALL be excluded

### Requirement: lexi init creates .lexignore
The `lexi init` command SHALL create an empty `.lexignore` file at the project root with a comment header explaining its purpose.

#### Scenario: Init creates .lexignore
- **WHEN** `lexi init` is run in a project without `.lexignore`
- **THEN** a `.lexignore` file SHALL be created with a comment header

#### Scenario: Init preserves existing .lexignore
- **WHEN** `lexi init` is run in a project that already has a `.lexignore`
- **THEN** the existing `.lexignore` SHALL NOT be overwritten
