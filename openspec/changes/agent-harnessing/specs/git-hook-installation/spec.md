## MODIFIED Requirements

### Requirement: CLI integration via lexictl setup --hooks
The `lexictl setup` command SHALL accept a `--hooks` flag that installs both the git post-commit hook and the git pre-commit hook. Status messages SHALL be displayed for each hook installation.

#### Scenario: Install hooks
- **WHEN** `lexictl setup --hooks` is run in a git repository
- **THEN** both `install_post_commit_hook()` and `install_pre_commit_hook()` SHALL be called
- **AND** status messages SHALL be displayed for each

#### Scenario: Hook installation in non-git project
- **WHEN** `lexictl setup --hooks` is run in a directory without `.git`
- **THEN** an appropriate error message SHALL be displayed
