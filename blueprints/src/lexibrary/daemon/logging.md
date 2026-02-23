# daemon/logging

**Summary:** Daemon-specific logging setup with a `RotatingFileHandler` that writes to `<project_root>/.lexibrarian.log`.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `setup_daemon_logging` | `(project_root: Path, log_level: str = "info") -> logging.Logger` | Attach a `RotatingFileHandler` to the `lexibrarian` logger; returns the configured logger |

## Dependencies

- None (stdlib only: `logging`, `logging.handlers`, `pathlib`)

## Dependents

- `lexibrarian.daemon.service` -- called at the start of `run_once`, `run_watch`, and `run_watchdog`

## Key Concepts

- Log file path: `<project_root>/.lexibrarian.log`
- Rotation: 5 MB max per file, 3 backup files
- Log format: `%(asctime)s %(name)s %(levelname)s %(message)s`
- `log_level` is case-insensitive; falls back to `INFO` if unrecognised
- No console handler is added -- callers attach their own if needed
- Logger name is `"lexibrarian"` (package root logger)
