# Error Handling & Logging — Production Readiness Plan

## Current State

The codebase has solid foundations: centralized logging via `RichHandler`, per-module loggers
(`logging.getLogger(__name__)`), error counters in stats dataclasses, and no unintentional
silent failures. This plan addresses the gaps needed before production use.

**Out of scope:** Daemon health file (daemon being decommissioned), LLM retry logic (failed
LLM calls are tracked in error summaries and can be re-run).

---

## 1. Exception Hierarchy

**Goal:** Replace bare `except Exception` catches with specific, catchable error types so
callers can distinguish between recoverable and non-recoverable failures.

**File:** `src/lexibrary/exceptions.py`

```python
class LexibraryError(Exception):
    """Base exception for all Lexibrary errors."""

class ConfigError(LexibraryError):
    """Invalid configuration, missing config files, bad YAML."""

class IndexingError(LexibraryError):
    """Failure during crawl, indexing, or .aindex generation."""

class LLMServiceError(LexibraryError):
    """LLM API call failure — timeout, auth, rate limit, malformed response."""

class ParseError(LexibraryError):
    """AST/file parsing failure — bad syntax, unsupported language, read error."""

class LinkGraphError(LexibraryError):
    """Link graph build or query failure."""

# Already exists — re-parent under LexibraryError:
class LexibraryNotFoundError(LexibraryError):
    """No .lexibrary/ directory found walking up from start path."""
```

**Migration rules:**
- Do NOT convert every `except Exception` at once. Migrate incrementally per-module as each
  module is touched in tasks 2–4 below.
- Keep the outer `except Exception` as a final safety net in pipeline-level code (archivist,
  crawler) — but log it as `logger.exception(...)` with a note that it was unexpected.
- Inner/leaf functions (AST parser, LLM service, file reader) should raise the specific
  exception type, letting the pipeline-level code decide whether to skip or abort.

**Changes per module:**

| Module | Current catch | New raise/catch |
|--------|--------------|-----------------|
| `llm/service.py` | `except Exception` → returns `error=True` | Raise `LLMServiceError`; pipeline catches it |
| `ast_parser/__init__.py` | `except Exception` → returns `None` | Raise `ParseError`; pipeline catches it |
| `ast_parser/registry.py` | `except ImportError`, `except Exception` | Raise `ParseError` wrapping original |
| `crawler/engine.py` | `except Exception` → `stats.errors += 1` | Catch `IndexingError` specifically, `Exception` as fallback |
| `indexer/orchestrator.py` | `except Exception` → `stats.errors += 1` | Same pattern as crawler |
| `linkgraph/builder.py` | `except Exception` → appends to `errors` list | Raise `LinkGraphError` from inner methods; `full_build`/`incremental_update` catch it |
| `stack/parser.py` | `except (yaml.YAMLError, ...)` | Raise `ConfigError` wrapping original |
| `validator/__init__.py` | `except Exception: pass` | Catch `LexibraryError`, log warning, continue; catch `Exception` separately and log as unexpected |

---

## 2. Structured Error Collection

**Goal:** Every pipeline run produces a machine-readable error list, not just counters. This
enables the end-of-run summary (task 4) and future integrations (CI, monitoring).

### 2a. ErrorRecord dataclass

**New file:** `src/lexibrary/errors.py`

```python
@dataclass
class ErrorRecord:
    """A single error encountered during a pipeline run."""

    timestamp: str          # ISO 8601
    phase: str              # "crawl", "archivist", "linkgraph", "llm", "parse", "validate"
    path: str | None        # File or directory path, if applicable
    error_type: str         # Exception class name (e.g. "LLMServiceError")
    message: str            # Human-readable description
    traceback: str | None   # Formatted traceback string (optional, for verbose/debug)


@dataclass
class ErrorSummary:
    """Aggregated error collection for a pipeline run."""

    records: list[ErrorRecord] = field(default_factory=list)

    def add(self, phase: str, error: Exception, path: str | None = None) -> None:
        """Capture an error with metadata."""
        ...

    @property
    def count(self) -> int:
        return len(self.records)

    def by_phase(self) -> dict[str, list[ErrorRecord]]:
        """Group errors by phase for reporting."""
        ...

    def has_errors(self) -> bool:
        return self.count > 0
```

### 2b. Thread the ErrorSummary through pipelines

Each pipeline entry point creates an `ErrorSummary` instance and passes it down. Where
errors are currently caught and counted, they are additionally recorded:

```python
# Before (archivist/pipeline.py, line ~668):
except Exception:
    logger.exception("Unexpected error processing %s", source_path)
    stats.files_failed += 1

# After:
except Exception as exc:
    logger.exception("Unexpected error processing %s", source_path)
    stats.files_failed += 1
    error_summary.add("archivist", exc, path=str(source_path))
```

**Modules to update:**

| Module | How ErrorSummary is passed |
|--------|--------------------------|
| `archivist/pipeline.py` (`update_project`, `update_files`) | Created at entry; passed to inner functions |
| `crawler/engine.py` (`full_crawl`) | Created at entry; replaces bare `stats.errors += 1` |
| `indexer/orchestrator.py` (`index_recursive`) | Created at entry; replaces bare `stats.errors += 1` |
| `linkgraph/builder.py` (`full_build`, `incremental_update`) | Replace `errors: list[str]` in BuildResult with `ErrorSummary` |
| `validator/__init__.py` (`validate_library`) | Created at entry; records check-level failures that are currently swallowed silently |

**Return path:** Each stats dataclass gains an `error_summary: ErrorSummary` field alongside
(not replacing) existing counters. Existing counters remain for quick checks; the summary
provides detail.

---

## 3. Fix Silent Swallowing in Validator

**Goal:** The validator's `except Exception: pass` at `validator/__init__.py:129-137` should
log errors and record them.

**Before:**
```python
for _name, (check_fn, _sev) in checks_to_run.items():
    try:
        issues = check_fn(project_root, lexibrary_dir)
        all_issues.extend(issues)
    except Exception:
        pass
```

**After:**
```python
for name, (check_fn, _sev) in checks_to_run.items():
    try:
        issues = check_fn(project_root, lexibrary_dir)
        all_issues.extend(issues)
    except LexibraryError:
        logger.warning("Validation check %r failed", name, exc_info=True)
        error_summary.add("validate", exc, path=name)
    except Exception:
        logger.warning("Validation check %r failed unexpectedly", name, exc_info=True)
        error_summary.add("validate", exc, path=name)
```

The `ErrorSummary` is attached to `ValidationReport` so the CLI can include it in output.

---

## 4. End-of-Run Error Summary

**Goal:** When a pipeline finishes, print a consolidated error report so users know exactly
what failed and why — not just "3 errors occurred."

### 4a. Summary formatter

**New function in:** `src/lexibrary/errors.py`

```python
def format_error_summary(summary: ErrorSummary, console: Console) -> None:
    """Print a grouped error summary to the Rich console."""
    if not summary.has_errors():
        return

    console.print()
    console.print(f"[bold red]Errors ({summary.count}):[/bold red]")

    for phase, records in summary.by_phase().items():
        console.print(f"\n  [bold]{phase}[/bold] — {len(records)} error(s)")
        for rec in records:
            path_str = f" [dim]{rec.path}[/dim]" if rec.path else ""
            console.print(f"    [{rec.error_type}]{path_str}: {rec.message}")
```

### 4b. Integration points

| CLI Command | Where summary is printed |
|-------------|------------------------|
| `lexi index` | After crawl completes, before exit |
| `lexi update` / `lexi update-files` | After archivist pipeline completes |
| `lexi validate` | After validation completes |
| `lexictl reindex` | After full reindex |

Each command already receives a stats object. With `error_summary` on the stats, the CLI
calls `format_error_summary(stats.error_summary, console)` before returning.

### 4c. Example output

```
Errors (4):

  archivist — 2 error(s)
    [LLMServiceError] src/lexibrary/llm/service.py: API rate limit exceeded (429)
    [LLMServiceError] src/lexibrary/crawler/engine.py: Request timeout after 30s

  parse — 1 error(s)
    [ParseError] src/vendor/legacy.js: Unsupported grammar for .js extension

  linkgraph — 1 error(s)
    [LinkGraphError] src/lexibrary/linkgraph/builder.py: Failed to resolve import 'foo.bar'
```

---

## 5. Structured JSON Logging (Optional Mode)

**Goal:** Enable machine-readable log output for log aggregation tools (ELK, CloudWatch,
Datadog) when running in production/CI environments.

### 5a. Add JSON formatter

**File:** `src/lexibrary/utils/logging.py`

```python
import json

class JSONFormatter(logging.Formatter):
    """Emit log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0] is not None:
            entry["exception"] = self.formatException(record.exc_info)
        # Include extra fields if present
        for key in ("phase", "path", "error_type"):
            if hasattr(record, key):
                entry[key] = getattr(record, key)
        return json.dumps(entry)
```

### 5b. Activation

Modify `setup_logging()` to accept a `log_format` parameter:

```python
def setup_logging(
    verbose: bool = False,
    log_file: Path | str | None = None,
    log_format: str = "rich",  # "rich" | "json"
) -> None:
```

When `log_format="json"`, use `JSONFormatter` instead of `RichHandler`. Activated via:
- Environment variable: `LEXIBRARY_LOG_FORMAT=json`
- CLI flag: `--log-format json`

### 5c. CLI integration

Add `--log-format` option to `_shared.py` callback (where `--verbose` is already handled).
Read `LEXIBRARY_LOG_FORMAT` env var as fallback.

---

## 6. Fix Indexer Orchestrator Silent Errors

**Goal:** `indexer/orchestrator.py:index_recursive` currently increments `stats.errors += 1`
with no logging at all. Add logging and error collection.

**Before (`indexer/orchestrator.py` ~line 130):**
```python
except Exception:
    stats.errors += 1
```

**After:**
```python
except Exception as exc:
    logger.exception("Failed to index directory: %s", dir_path)
    stats.errors += 1
    error_summary.add("indexer", exc, path=str(dir_path))
```

---

## Implementation Order

| Step | Task | Files Changed | Depends On |
|------|------|---------------|------------|
| **1** | Create exception hierarchy | `exceptions.py` | — |
| **2** | Create `ErrorRecord` / `ErrorSummary` / `format_error_summary` | `errors.py` (new) | — |
| **3** | Add `error_summary` field to all stats dataclasses | `pipeline.py`, `engine.py`, `orchestrator.py`, `builder.py` | Steps 1–2 |
| **4** | Wire error collection into archivist pipeline | `pipeline.py` | Step 3 |
| **5** | Wire error collection into crawler | `engine.py` | Step 3 |
| **6** | Wire error collection into indexer orchestrator + add logging | `orchestrator.py` | Step 3 |
| **7** | Wire error collection into link graph builder | `builder.py` | Step 3 |
| **8** | Fix validator silent swallowing | `validator/__init__.py` | Steps 1–2 |
| **9** | Migrate leaf modules to raise specific exceptions | `llm/service.py`, `ast_parser/__init__.py`, `ast_parser/registry.py`, `stack/parser.py` | Step 1 |
| **10** | Add end-of-run summary to CLI commands | `lexi_app.py`, `lexictl_app.py`, `_shared.py` | Steps 2–8 |
| **11** | Add JSON log formatter + `--log-format` flag | `utils/logging.py`, `_shared.py` | — |
| **12** | Update tests for new exception types + error summaries | `tests/` | Steps 1–10 |
| **13** | Update blueprints to document error handling conventions | `blueprints/` | Steps 1–11 |

---

## Conventions Going Forward

Once implemented, all new code should follow these rules:

1. **Leaf functions** raise specific `LexibraryError` subclasses — never return error flags
   or None as a failure signal in new code.
2. **Pipeline/orchestrator functions** catch specific exceptions, record them in
   `ErrorSummary`, and continue processing. A final `except Exception` remains as a safety
   net with `logger.exception()`.
3. **CLI commands** call `format_error_summary()` before exiting and set exit code 1 if
   errors occurred.
4. **No bare `except Exception: pass`** — every catch block must either log or record.
5. **Error context matters** — always include the file path or operation context in error
   messages.
