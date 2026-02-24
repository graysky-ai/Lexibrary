# concept-cli Specification

## Purpose
TBD - created by archiving change concepts-wiki. Update Purpose after archive.
## Requirements
### Requirement: Concepts list command
`lexi concepts [topic] [--tag TAG] [--status STATUS] [--all]` SHALL list or search concepts in `.lexibrary/concepts/`.
- Without any arguments: list all non-deprecated concepts in a Rich table with columns: Name, Status, Tags, Summary
- With `topic`: search concepts matching the topic string and apply any additional filters
- With `--tag TAG`: filter results to only concepts having the specified tag (repeatable; multiple tags use AND logic)
- With `--status STATUS`: filter results to only concepts with the specified status (`active`, `draft`, or `deprecated`)
- With `--all`: include deprecated concepts in the listing (overrides the default exclusion)
- Filters SHALL combine with AND logic: `--tag`, `--status`, and positional `topic` all narrow the result set
- SHALL display count of results (e.g., "Found 3 concepts")
- If no concepts directory exists, SHALL print a message suggesting `lexi concept new`
- Without `--all` or `--status deprecated`, deprecated concepts SHALL be excluded from results

#### Scenario: List all concepts
- **WHEN** `lexi concepts` is run with 3 concept files (2 active, 1 deprecated)
- **THEN** a Rich table SHALL display only the 2 non-deprecated concepts with their name, status, tags, and summary

#### Scenario: Search concepts
- **WHEN** `lexi concepts auth` is run and 2 concepts match "auth"
- **THEN** a Rich table SHALL display the matching non-deprecated concepts

#### Scenario: No concepts directory
- **WHEN** `lexi concepts` is run and `.lexibrary/concepts/` doesn't exist
- **THEN** the output SHALL suggest creating concepts with `lexi concept new`

#### Scenario: No search results
- **WHEN** `lexi concepts nonexistent` is run and no concepts match
- **THEN** the output SHALL print a "no concepts matching" message

#### Scenario: Filter by tag
- **WHEN** `lexi concepts --tag auth` is run and 2 of 5 concepts have the "auth" tag
- **THEN** the result SHALL contain exactly those 2 concepts (excluding any that are deprecated)

#### Scenario: Filter by multiple tags
- **WHEN** `lexi concepts --tag auth --tag security` is run
- **THEN** the result SHALL contain only concepts that have both "auth" AND "security" tags

#### Scenario: Filter by status
- **WHEN** `lexi concepts --status draft` is run and 3 of 8 concepts are drafts
- **THEN** the result SHALL contain exactly those 3 draft concepts

#### Scenario: Filter by deprecated status
- **WHEN** `lexi concepts --status deprecated` is run
- **THEN** the result SHALL show deprecated concepts (explicit status filter overrides default exclusion)

#### Scenario: Show all including deprecated
- **WHEN** `lexi concepts --all` is run with 5 concepts (3 active, 1 draft, 1 deprecated)
- **THEN** the result SHALL show all 5 concepts

#### Scenario: Combined filters narrow results
- **WHEN** `lexi concepts auth --tag security --status active` is run
- **THEN** the result SHALL contain only concepts matching "auth" AND tagged "security" AND with status "active"

#### Scenario: Tag filter with topic
- **WHEN** `lexi concepts auth --tag security` is run
- **THEN** the result SHALL contain only non-deprecated concepts matching "auth" that also have the "security" tag

### Requirement: Concept new command
`lexi concept new <name> [--tag TAG]...` SHALL create a new concept file from template.
- SHALL create `.lexibrary/concepts/` directory if it doesn't exist
- SHALL derive file path from name using `concept_file_path()`
- SHALL render the template using `render_concept_template()`
- SHALL write the file and print confirmation with the file path
- SHALL refuse to overwrite if the concept file already exists

The `--tag` option SHALL be repeatable to add multiple tags.

#### Scenario: Create new concept
- **WHEN** `lexi concept new "JWT Auth" --tag auth --tag security` is run
- **THEN** a file SHALL be created at `.lexibrary/concepts/JWTAuth.md` with frontmatter containing `title: JWT Auth` and `tags: [auth, security]`

#### Scenario: Create concept without tags
- **WHEN** `lexi concept new "Rate Limiting"` is run
- **THEN** a file SHALL be created with `tags: []` in frontmatter

#### Scenario: Refuse overwrite
- **WHEN** `lexi concept new "JWT Auth"` is run and `.lexibrary/concepts/JWTAuth.md` already exists
- **THEN** the command SHALL print an error and exit with code 1 without modifying the existing file

#### Scenario: Creates concepts directory
- **WHEN** `lexi concept new "JWT Auth"` is run and `.lexibrary/concepts/` doesn't exist
- **THEN** the directory SHALL be created before writing the file

### Requirement: Concept link command
`lexi concept link <concept-name> <source-file>` SHALL add a `[[concept-name]]` wikilink to the specified source file's design file.
- SHALL find the design file at the mirror path in `.lexibrary/`
- SHALL parse the existing design file
- SHALL add the wikilink to the design file's wikilinks list if not already present
- SHALL re-serialize and write the design file
- SHALL print confirmation or error if the design file doesn't exist

#### Scenario: Link concept to design file
- **WHEN** `lexi concept link "JWT Auth" src/auth/service.py` is run and a design file exists for that source file
- **THEN** `[[JWT Auth]]` SHALL be added to the design file's wikilinks section

#### Scenario: Wikilink already present
- **WHEN** `lexi concept link "JWT Auth" src/auth/service.py` is run and `[[JWT Auth]]` is already in the wikilinks
- **THEN** the command SHALL print "Already linked" and not duplicate the entry

#### Scenario: Design file not found
- **WHEN** `lexi concept link "JWT Auth" src/missing.py` is run and no design file exists
- **THEN** the command SHALL print an error suggesting `lexi update src/missing.py` first

### Requirement: Rich console output for concept commands
All concept CLI commands SHALL use `rich.console.Console` for output. No command SHALL use `typer.echo()` or bare `print()`.

#### Scenario: Table output uses Rich
- **WHEN** `lexi concepts` produces a table
- **THEN** it SHALL be rendered through a Rich Console instance

