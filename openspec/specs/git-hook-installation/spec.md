# git-hook-installation Specification

## Purpose
TBD - created by archiving change update-triggers. Update Purpose after archive.
## Requirements
### Requirement: Post-commit hook installation
The system SHALL provide an `install_post_commit_hook(project_root)` function in `hooks/post_commit.py` that installs or updates a git post-commit hook for automatic library updates.

#### Scenario: No existing hook
- **WHEN** `install_post_commit_hook()` is called
- **AND** no `.git/hooks/post-commit` file exists
- **THEN** a new post-commit hook SHALL be created with the Lexibrary hook script
- **AND** the file SHALL be made executable

#### Scenario: Existing hook without Lexibrary
- **WHEN** `install_post_commit_hook()` is called
- **AND** an existing `.git/hooks/post-commit` file exists without the Lexibrary marker
- **THEN** the Lexibrary hook section SHALL be appended to the existing hook
- **AND** the existing hook content SHALL be preserved

#### Scenario: Idempotent installation
- **WHEN** `install_post_commit_hook()` is called twice
- **THEN** the second call SHALL detect the existing Lexibrary marker (`# lexibrary:post-commit`)
- **AND** the hook SHALL NOT be duplicated
- **AND** a message SHALL indicate the hook is already installed

#### Scenario: No .git directory
- **WHEN** `install_post_commit_hook()` is called
- **AND** no `.git` directory exists in the project root
- **THEN** a status message SHALL be returned indicating no git repository was found
- **AND** no crash SHALL occur

### Requirement: Hook script content
The generated hook script SHALL list changed files from the most recent commit and pass them to `lexictl update --changed-only` in the background.

#### Scenario: Hook uses git diff-tree
- **WHEN** the hook script runs after a commit
- **THEN** it SHALL use `git diff-tree --no-commit-id --name-only -r HEAD` to list changed files

#### Scenario: Hook runs in background
- **WHEN** the hook script invokes `lexictl update`
- **THEN** the invocation SHALL run in the background (`&`)
- **AND** output SHALL be redirected to `.lexibrary.log`

#### Scenario: Hook uses --changed-only
- **WHEN** the hook script passes files to lexictl
- **THEN** it SHALL use the `--changed-only` flag

### Requirement: CLI integration via lexictl setup --hooks
The `lexictl setup` command SHALL accept a `--hooks` flag that installs the git post-commit hook.

#### Scenario: Install hooks
- **WHEN** `lexictl setup --hooks` is run in a git repository
- **THEN** the post-commit hook SHALL be installed via `install_post_commit_hook()`
- **AND** a status message SHALL be displayed

#### Scenario: Hook installation in non-git project
- **WHEN** `lexictl setup --hooks` is run in a directory without `.git`
- **THEN** an appropriate error message SHALL be displayed

