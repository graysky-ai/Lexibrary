## ADDED Requirements

### Requirement: Three-mode DaemonService
The rewritten `DaemonService` SHALL support three entry points: `run_once()`, `run_watch()`, and `run_watchdog()`.

#### Scenario: run_once performs a single sweep
- **WHEN** `DaemonService.run_once()` is called
- **THEN** the service SHALL run a single project update sweep and exit
- **AND** it SHALL use `update_project()` from the archivist pipeline

#### Scenario: run_once skips when no changes detected
- **WHEN** `DaemonService.run_once()` is called
- **AND** `sweep_skip_if_unchanged` is `True` in config
- **AND** no files have `mtime` newer than the last sweep
- **THEN** the sweep SHALL be skipped
- **AND** a message SHALL indicate no changes were detected

#### Scenario: run_watch runs periodic sweeps
- **WHEN** `DaemonService.run_watch()` is called
- **THEN** the service SHALL run periodic sweeps using `PeriodicSweep` at the configured interval
- **AND** the service SHALL block until interrupted (SIGTERM or SIGINT)

#### Scenario: run_watchdog requires watchdog_enabled
- **WHEN** `DaemonService.run_watchdog()` is called
- **AND** `daemon.watchdog_enabled` is `False` in config
- **THEN** the service SHALL print a message indicating watchdog mode is disabled
- **AND** the service SHALL suggest using `lexictl sweep --watch` instead
- **AND** the service SHALL return without starting the watchdog

#### Scenario: run_watchdog starts deprecated watchdog
- **WHEN** `DaemonService.run_watchdog()` is called
- **AND** `daemon.watchdog_enabled` is `True` in config
- **THEN** the service SHALL print a deprecation warning
- **AND** the service SHALL start the watchdog file observer and periodic sweep
- **AND** the service SHALL block until interrupted

### Requirement: DaemonService uses archivist pipeline
The `DaemonService` SHALL use `update_project()` and `update_files()` from `archivist/pipeline.py` instead of `full_crawl()`.

#### Scenario: Sweep uses update_project
- **WHEN** a sweep is triggered (periodic or one-shot)
- **THEN** the service SHALL call `asyncio.run(update_project(...))` with the archivist pipeline

#### Scenario: No reference to full_crawl
- **WHEN** the `DaemonService` module is loaded
- **THEN** it SHALL NOT import or reference `full_crawl` from `crawler.engine`

### Requirement: Graceful shutdown
The `DaemonService` SHALL handle SIGTERM and SIGINT signals for graceful shutdown.

#### Scenario: SIGINT triggers shutdown
- **WHEN** the daemon receives SIGINT (Ctrl+C)
- **THEN** the daemon SHALL stop all components (observer, sweep) and remove the PID file

#### Scenario: SIGTERM triggers shutdown
- **WHEN** the daemon receives SIGTERM
- **THEN** the daemon SHALL stop all components and remove the PID file

### Requirement: PID file management
The `DaemonService` SHALL write and manage a PID file at `<root>/.lexibrary.pid` in watchdog mode only.

#### Scenario: PID file written on watchdog start
- **WHEN** `run_watchdog()` starts successfully
- **THEN** a PID file SHALL be written containing the current process ID

#### Scenario: PID file removed on stop
- **WHEN** `DaemonService.stop()` is called
- **THEN** the PID file SHALL be removed (tolerating if already gone)

### Requirement: Lazy watchdog imports
The `watchdog` library SHALL only be imported inside `run_watchdog()`, not at module level.

#### Scenario: Module loads without watchdog installed
- **WHEN** `daemon/service.py` is imported
- **AND** the `watchdog` package is not installed
- **THEN** the import SHALL succeed (no `ImportError`)
- **AND** `run_once()` and `run_watch()` SHALL work normally

#### Scenario: Missing watchdog raises clear error
- **WHEN** `run_watchdog()` is called
- **AND** the `watchdog` package is not installed
- **THEN** a clear `ImportError` SHALL be raised
