## ADDED Requirements

### Requirement: Pre-commit hook installation
The system SHALL provide `install_pre_commit_hook(project_root: Path) -> HookInstallResult` in `src/lexibrary/hooks/pre_commit.py` that installs a git pre-commit hook running `lexictl validate --ci --severity error`.

The hook script SHALL use the marker `# lexibrary:pre-commit` for idempotency, following the same pattern as the post-commit hook.

#### Scenario: No existing pre-commit hook
- **WHEN** `install_pre_commit_hook()` is called and no `.git/hooks/pre-commit` file exists
- **THEN** a new pre-commit hook SHALL be created with the Lexibrary validation script
- **AND** the file SHALL be made executable

#### Scenario: Existing pre-commit hook without Lexibrary
- **WHEN** `install_pre_commit_hook()` is called and an existing `.git/hooks/pre-commit` file exists without the Lexibrary marker
- **THEN** the Lexibrary hook section SHALL be appended to the existing hook
- **AND** existing hook content SHALL be preserved

#### Scenario: Idempotent installation
- **WHEN** `install_pre_commit_hook()` is called twice
- **THEN** the second call SHALL detect the existing `# lexibrary:pre-commit` marker and not duplicate the hook

#### Scenario: No .git directory
- **WHEN** `install_pre_commit_hook()` is called and no `.git` directory exists
- **THEN** a status message SHALL be returned indicating no git repository found
- **AND** no crash SHALL occur

### Requirement: Pre-commit hook script content
The generated hook script SHALL run `lexictl validate --ci --severity error` and block the commit (exit 1) if validation fails. It SHALL print instructions to bypass with `git commit --no-verify`.

#### Scenario: Validation passes
- **WHEN** the pre-commit hook runs and `lexictl validate --ci --severity error` exits 0
- **THEN** the hook SHALL exit 0 (commit proceeds)

#### Scenario: Validation fails
- **WHEN** the pre-commit hook runs and `lexictl validate --ci --severity error` exits non-zero
- **THEN** the hook SHALL print "Lexibrary validation failed" with bypass instructions and exit 1

### Requirement: Setup command installs both hooks
The `lexictl setup --hooks` command SHALL install both the post-commit and pre-commit hooks and report results for each.

#### Scenario: Both hooks installed
- **WHEN** `lexictl setup --hooks` is run
- **THEN** both `install_post_commit_hook()` and `install_pre_commit_hook()` SHALL be called
- **AND** status messages SHALL be displayed for each
