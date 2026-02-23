# daemon/watcher

**Summary:** Watchdog `FileSystemEventHandler` that filters filesystem events and notifies the `Debouncer` for valid file changes.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `LexibraryEventHandler` | `FileSystemEventHandler` subclass | Filters and forwards events to debouncer |
| `LexibraryEventHandler.__init__` | `(debouncer: Debouncer, ignore_matcher: IgnoreMatcher)` | Wire debouncer and matcher |
| `LexibraryEventHandler.on_any_event` | `(event: FileSystemEvent) -> None` | Main filter: skip dirs, `.aindex*`, internal files, ignored paths |

## Dependencies

- `lexibrary.daemon.debouncer` — `Debouncer`
- `lexibrary.ignore.matcher` — `IgnoreMatcher`

## Dependents

- `lexibrary.daemon.service` — instantiates and schedules handler on the observer

## Key Concepts

- Ignored events: directory events, `.aindex*` files (prevents re-index loops), internal files (`_INTERNAL_FILES` frozenset), patterns matching `IgnoreMatcher`
- Valid events: calls `debouncer.notify(parent_directory)`
