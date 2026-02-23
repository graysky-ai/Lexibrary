# daemon/watcher

**Summary:** Watchdog `FileSystemEventHandler` that filters filesystem events and notifies the `Debouncer` for valid file changes.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `LexibrarianEventHandler` | `FileSystemEventHandler` subclass | Filters and forwards events to debouncer |
| `LexibrarianEventHandler.__init__` | `(debouncer: Debouncer, ignore_matcher: IgnoreMatcher)` | Wire debouncer and matcher |
| `LexibrarianEventHandler.on_any_event` | `(event: FileSystemEvent) -> None` | Main filter: skip dirs, `.aindex*`, internal files, ignored paths |

## Dependencies

- `lexibrarian.daemon.debouncer` — `Debouncer`
- `lexibrarian.ignore.matcher` — `IgnoreMatcher`

## Dependents

- `lexibrarian.daemon.service` — instantiates and schedules handler on the observer

## Key Concepts

- Ignored events: directory events, `.aindex*` files (prevents re-index loops), internal files (`_INTERNAL_FILES` frozenset), patterns matching `IgnoreMatcher`
- Valid events: calls `debouncer.notify(parent_directory)`
