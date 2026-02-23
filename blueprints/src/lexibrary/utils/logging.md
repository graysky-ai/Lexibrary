# utils/logging

**Summary:** Configures the root logger with a Rich console handler and an optional file handler for persistent daemon logs.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `setup_logging` | `(verbose: bool = False, log_file: Path | str | None = None) -> None` | Set level, attach `RichHandler`; add file handler if `log_file` given |

## Dependents

- `lexibrarian.cli` (planned) — will call `setup_logging` early in CLI entry
- `lexibrarian.daemon.service` — currently uses `logging.basicConfig` directly; should migrate to `setup_logging`
