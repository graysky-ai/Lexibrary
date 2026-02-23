# daemon-logging Specification

## Purpose
TBD - created by archiving change update-triggers. Update Purpose after archive.
## Requirements
### Requirement: Daemon-specific logging setup
The system SHALL provide a `setup_daemon_logging(project_root, log_level)` function in `daemon/logging.py` that configures a `RotatingFileHandler` for `.lexibrary.log`.

#### Scenario: Log file creation
- **WHEN** `setup_daemon_logging()` is called
- **THEN** a `RotatingFileHandler` SHALL be attached to the `lexibrary` logger
- **AND** the handler SHALL write to `<project_root>/.lexibrary.log`

#### Scenario: Log rotation configuration
- **WHEN** the `RotatingFileHandler` is created
- **THEN** `maxBytes` SHALL be 5MB (5 * 1024 * 1024)
- **AND** `backupCount` SHALL be 3

#### Scenario: Configurable log level
- **WHEN** `setup_daemon_logging()` is called with `log_level="debug"`
- **THEN** the logger and handler SHALL be set to `logging.DEBUG`

#### Scenario: Default log level
- **WHEN** `setup_daemon_logging()` is called with `log_level="info"` (the default)
- **THEN** the logger and handler SHALL be set to `logging.INFO`

#### Scenario: Console logging not configured
- **WHEN** `setup_daemon_logging()` is called
- **THEN** it SHALL NOT configure console logging (callers add their own console handler if needed)

### Requirement: Log file is gitignored
The `.lexibrary.log` file SHALL be gitignored.

#### Scenario: Init scaffolder includes log file pattern
- **WHEN** `lexictl init` creates the project skeleton
- **THEN** `.lexibrary.log` SHALL be included in the `.gitignore` additions

