## ADDED Requirements

### Requirement: Daemon startup
The system SHALL provide a `DaemonService` that orchestrates startup of the file watcher, debouncer, and periodic sweep, then blocks until a shutdown signal is received.

#### Scenario: Foreground start initializes all components
- **WHEN** `DaemonService.start(foreground=True)` is called
- **THEN** the file watcher observer, debouncer, and periodic sweep are all started, and the service blocks on a shutdown event

#### Scenario: Startup prints running message
- **WHEN** the daemon starts successfully
- **THEN** a message including the PID and "Press Ctrl+C to stop" is output via Rich console

### Requirement: PID file management
The system SHALL write a PID file (`.lexibrary.pid`) containing the current process ID on startup and remove it on shutdown.

#### Scenario: PID file created on start
- **WHEN** the daemon starts
- **THEN** a `.lexibrary.pid` file is created in the project root containing the current process ID

#### Scenario: PID file removed on stop
- **WHEN** the daemon shuts down
- **THEN** the `.lexibrary.pid` file is removed from the project root

#### Scenario: PID file removal tolerates missing file
- **WHEN** the daemon shuts down but the PID file has already been deleted
- **THEN** no error is raised

### Requirement: Signal handling
The system SHALL handle SIGTERM and SIGINT signals by triggering a graceful shutdown sequence.

#### Scenario: SIGTERM triggers shutdown
- **WHEN** the daemon process receives SIGTERM
- **THEN** the shutdown event is set, triggering graceful cleanup

#### Scenario: SIGINT triggers shutdown
- **WHEN** the user presses Ctrl+C (SIGINT)
- **THEN** the shutdown event is set, triggering graceful cleanup

### Requirement: Graceful shutdown
The system SHALL perform an orderly shutdown: cancel the debouncer, stop the periodic sweep, stop the file watcher observer, and remove the PID file.

#### Scenario: All components cleaned up on shutdown
- **WHEN** the shutdown sequence executes
- **THEN** the debouncer is cancelled, periodic sweep is stopped, observer is stopped and joined (with timeout), and the PID file is removed

#### Scenario: Shutdown completes even if components are None
- **WHEN** shutdown is called before all components are initialized
- **THEN** the shutdown completes without errors (None checks on each component)

### Requirement: Incremental re-indexing callback
The system SHALL provide a callback for the debouncer that runs `full_crawl()` with the project's configuration, using the existing change detection cache to skip unchanged files.

#### Scenario: Debounce callback triggers full crawl
- **WHEN** the debouncer fires with a set of changed directories
- **THEN** the system runs `full_crawl()` using `asyncio.run()` with the project's matcher, tokenizer, LLM service, and change detector

#### Scenario: Errors in re-indexing are logged
- **WHEN** the incremental re-index callback raises an exception
- **THEN** the error is logged and the daemon continues running

### Requirement: Full sweep callback
The system SHALL provide a callback for the periodic sweep that runs `full_crawl()` and logs completion statistics.

#### Scenario: Sweep callback triggers full crawl with stats
- **WHEN** the periodic sweep fires
- **THEN** the system runs `full_crawl()` and logs the number of directories indexed, files summarized, and files cached

### Requirement: Logging configuration
The system SHALL configure logging to write to the project's log file (from `OutputConfig.log_filename`) during daemon operation.

#### Scenario: Log file receives daemon output
- **WHEN** the daemon is running and events occur
- **THEN** log messages are written to the configured log file in the project root
