## ADDED Requirements

### Requirement: Conventions list command
`lexi conventions [path] [--tag TAG] [--status STATUS] [--scope SCOPE] [--all]` SHALL list or filter conventions in `.lexibrary/conventions/`.
- Without arguments: list all non-deprecated conventions in a Rich table with columns: Title, Scope, Status, Tags, Rule (truncated to 60 chars)
- With `path`: show conventions applicable to that file/directory path, ordered by scope specificity
- With `--tag TAG`: filter to conventions having the specified tag (repeatable; multiple tags use AND logic)
- With `--status STATUS`: filter to conventions with the specified status (`active`, `draft`, or `deprecated`)
- With `--scope SCOPE`: filter to conventions with the specified scope value
- With `--all`: include deprecated conventions (overrides default exclusion)
- Filters SHALL combine with AND logic
- SHALL display count of results (e.g., "Found 3 conventions")
- If no conventions directory exists, SHALL print a message suggesting `lexi convention new`

#### Scenario: List all conventions
- **WHEN** `lexi conventions` is run with 4 convention files (2 active, 1 draft, 1 deprecated)
- **THEN** a Rich table SHALL display only the 3 non-deprecated conventions

#### Scenario: List conventions for a file path
- **WHEN** `lexi conventions src/auth/login.py` is run
- **THEN** the table SHALL show only conventions whose scope matches that file path, ordered by specificity

#### Scenario: Filter by tag
- **WHEN** `lexi conventions --tag python` is run and 2 of 5 conventions have the "python" tag
- **THEN** the result SHALL contain exactly those 2 non-deprecated conventions

#### Scenario: Filter by status
- **WHEN** `lexi conventions --status draft` is run and 3 conventions are drafts
- **THEN** the result SHALL show those 3 draft conventions

#### Scenario: No conventions directory
- **WHEN** `lexi conventions` is run and `.lexibrary/conventions/` does not exist
- **THEN** the output SHALL suggest creating conventions with `lexi convention new`

#### Scenario: No results
- **WHEN** `lexi conventions --tag nonexistent` is run
- **THEN** the output SHALL print a "no conventions matching" message

### Requirement: Convention new command
`lexi convention new --scope <scope> --body <body> [--tag TAG]... [--title TITLE] [--source SOURCE]` SHALL create a new convention file.
- SHALL create `.lexibrary/conventions/` directory if it does not exist
- If `--title` is not provided, SHALL derive a title from the first 60 characters of the body
- SHALL derive the file path using `convention_file_path()` from the title
- SHALL serialize and write the convention file
- Agent-created conventions (`--source agent`) SHALL default to `status: draft` and `priority: -1`
- User-created conventions (default `--source user`) SHALL default to `status: active` and `priority: 0`
- SHALL print confirmation with the file path
- SHALL refuse to create if a convention with the same slug already exists (suggest editing the existing file)

#### Scenario: Create convention with all flags
- **WHEN** `lexi convention new --scope src/auth --body "All endpoints require auth" --tag auth --title "Auth required"` is run
- **THEN** a file SHALL be created at `.lexibrary/conventions/auth-required.md` with the correct frontmatter and body

#### Scenario: Create convention with auto-generated title
- **WHEN** `lexi convention new --scope project --body "Use from __future__ import annotations in every module"` is run without `--title`
- **THEN** the title SHALL be derived from the body text

#### Scenario: Agent-created convention defaults
- **WHEN** `lexi convention new --scope project --body "Use rich console" --source agent` is run
- **THEN** the convention SHALL have `status: draft`, `source: agent`, and `priority: -1`

#### Scenario: Creates conventions directory
- **WHEN** `lexi convention new` is run and `.lexibrary/conventions/` does not exist
- **THEN** the directory SHALL be created before writing the file

#### Scenario: Refuse duplicate slug
- **WHEN** `lexi convention new --scope project --body "..." --title "Auth required"` is run and `auth-required.md` already exists
- **THEN** the command SHALL print an error suggesting to edit the existing file, and exit with code 1

### Requirement: Convention approve command
`lexi convention approve <name>` SHALL promote a convention from `status: draft` to `status: active`.
- SHALL find the convention by searching title (case-insensitive) or file slug
- SHALL read, update the status field, and re-serialize the file
- SHALL print confirmation with the convention title
- SHALL refuse if the convention is already active or deprecated

#### Scenario: Approve draft convention
- **WHEN** `lexi convention approve "auth required"` is run and the convention has `status: draft`
- **THEN** the convention file SHALL be updated with `status: active` and a confirmation message SHALL be printed

#### Scenario: Approve by slug
- **WHEN** `lexi convention approve auth-required` is run
- **THEN** the convention SHALL be found by matching the slug and approved

#### Scenario: Convention not found
- **WHEN** `lexi convention approve "nonexistent"` is run
- **THEN** the command SHALL print an error listing available conventions and exit with code 1

#### Scenario: Already active convention
- **WHEN** `lexi convention approve "auth required"` is run and the convention has `status: active`
- **THEN** the command SHALL print "Already active" and exit with code 0

### Requirement: Convention deprecate command
`lexi convention deprecate <name>` SHALL set a convention's status to `deprecated`.
- SHALL find the convention by title or slug
- SHALL update the status field and re-serialize
- SHALL print confirmation

#### Scenario: Deprecate active convention
- **WHEN** `lexi convention deprecate "auth required"` is run and the convention has `status: active`
- **THEN** the convention file SHALL be updated with `status: deprecated`

#### Scenario: Convention not found
- **WHEN** `lexi convention deprecate "nonexistent"` is run
- **THEN** the command SHALL print an error and exit with code 1

### Requirement: Rich console output for convention commands
All convention CLI commands SHALL use `rich.console.Console` for output. No command SHALL use `typer.echo()` or bare `print()`.

#### Scenario: Table output uses Rich
- **WHEN** `lexi conventions` produces a table
- **THEN** it SHALL be rendered through a Rich Console instance
