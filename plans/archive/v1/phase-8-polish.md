# Phase 8: Polish

**Goal:** Error hardening, comprehensive logging, test coverage, and final integration verification.
**Milestone:** All verification steps pass. Test suite runs with reasonable coverage.
**Depends on:** All prior phases (1-7).

---

## 8.1 Error Handling Hardening

### Network Errors (LLM calls)

| Scenario | Handling |
|----------|----------|
| API timeout | `baml-py` retries internally (configured via `max_retries`). After exhaustion, `LLMService` catches exception and returns fallback summary `"Summary unavailable (timeout)"`. |
| Rate limit (429) | Rate limiter should prevent this, but if hit: log warning, back off, retry once. |
| Auth error (401/403) | Log error with clear message: "Check your API key in lexibrary.toml". Don't retry. |
| Network unreachable | Catch `httpx.ConnectError`, log, return fallback summary. |
| Malformed LLM response | BAML handles parsing; if it fails, catch and return fallback. |

### File System Errors

| Scenario | Handling |
|----------|----------|
| Permission denied on file | Skip file, log warning, list as "Permission denied" in `.aindex`. |
| Permission denied on directory | Skip entire directory, log warning. |
| File deleted during crawl | `FileNotFoundError` caught in file reader, skip gracefully. |
| Disk full on write | `OSError` caught in writer, log error, continue with other directories. |
| Symlink loop | `os.walk` handles with `followlinks=False` (default). |
| Broken symlink | `stat()` fails, skip file. |

### Config Errors

| Scenario | Handling |
|----------|----------|
| Invalid TOML syntax | `tomllib.TOMLDecodeError` caught, print clear error with line number. |
| Invalid config values | Pydantic `ValidationError` caught, print which field is invalid. |
| Missing API key env var | Check at crawl start, print actionable error before any work begins. |
| Unknown provider | `ValueError` from factory, caught at CLI level with clear message. |

### Implementation

Add a `src/lexibrary/utils/errors.py` file:

```python
class LexibraryError(Exception):
    """Base exception for Lexibrary errors."""
    pass

class ConfigError(LexibraryError):
    """Configuration-related error."""
    pass

class CrawlError(LexibraryError):
    """Crawl-related error."""
    pass

class LLMError(LexibraryError):
    """LLM-related error."""
    pass
```

Wrap key CLI commands in try/except blocks that catch `LexibraryError` subclasses and print user-friendly messages (no tracebacks for expected errors).

---

## 8.2 Logging Strategy

### Log levels by module

| Module | DEBUG | INFO | WARNING | ERROR |
|--------|-------|------|---------|-------|
| `config.loader` | Config file path found | Config loaded | — | Parse error |
| `ignore.matcher` | Each file checked | Pattern sources loaded | — | — |
| `crawler.discovery` | Each dir discovered | Total dirs/files count | Skipped dir (permission) | — |
| `crawler.engine` | Each file processed | Directory indexed | Cached file reused | LLM call failed |
| `crawler.change_detector` | Hash comparisons | Cache loaded/saved | Corrupted cache | — |
| `crawler.file_reader` | File read details | — | Binary detected, truncated | Read error |
| `llm.service` | LLM request/response | — | Fallback summary used | API error |
| `llm.rate_limiter` | Wait times | — | — | — |
| `tokenizer` | Token counts | Backend initialized | — | Count error |
| `daemon.service` | Event details | Start/stop, sweep | — | Reindex error |
| `daemon.debouncer` | Timer events | Fire event | — | Callback error |
| `indexer.writer` | Write details | File written | — | Write error |

### Implementation
- `--verbose` flag on `lexi crawl` sets level to `DEBUG`
- Default level is `INFO` (shows progress and key events)
- Daemon always logs to file at `DEBUG` level
- Console output uses `rich.logging.RichHandler` (short format)
- File output uses stdlib `FileHandler` (full format with timestamps)

---

## 8.3 Pre-flight Checks

Add a validation step at the start of `lexi crawl` and `lexi daemon` that catches common problems early:

```python
def preflight_check(config: LexibraryConfig, root: Path) -> list[str]:
    """Run pre-flight checks. Returns list of error messages (empty = all good)."""
    errors = []

    # Check API key is available
    if config.llm.provider != "ollama":
        import os
        api_key = config.llm.api_key or os.environ.get(config.llm.api_key_env, "")
        if not api_key:
            errors.append(
                f"API key not found. Set the {config.llm.api_key_env} environment variable "
                f"or add api_key to [llm] in lexibrary.toml."
            )

    # Check root directory exists
    if not root.is_dir():
        errors.append(f"Root directory does not exist: {root}")

    # Check root is writable
    if not os.access(root, os.W_OK):
        errors.append(f"Root directory is not writable: {root}")

    # Check BAML client is generated
    try:
        from .baml_client import b  # noqa
    except ImportError:
        errors.append(
            "BAML client not generated. Run: uv run baml-cli generate"
        )

    return errors
```

Display errors with `rich` formatting and exit before starting any work.

---

## 8.4 Test Strategy

### Test categories

| Category | Location | What it covers |
|----------|----------|----------------|
| Unit tests | `tests/test_config/`, `test_tokenizer/`, `test_ignore/`, `test_indexer/` | Individual modules in isolation |
| Integration tests | `tests/test_crawler/test_engine.py` | Crawler with mocked LLM on fixture project |
| CLI tests | `tests/test_cli.py` | Typer commands via `CliRunner` |
| Daemon tests | `tests/test_daemon/` | Debouncer timing, watcher filtering, service lifecycle |

### Mock strategy

- **LLM calls:** Always mocked in tests. Use `unittest.mock.patch` on `baml_client.async_client.b.SummarizeFile` etc.
- **File system:** Use `tmp_path` (pytest built-in) for all tests that write files.
- **Network:** No real network calls in tests. Mock `httpx` where needed.
- **Timing:** Use short intervals (0.1s) for debouncer/scheduler tests.

### Test fixtures: `tests/fixtures/sample_project/`

```
sample_project/
├── main.py              # print("hello world")
├── README.md            # # Sample Project\nA test fixture.
├── image.png            # 16 bytes of binary data (b"\x89PNG" + nulls)
├── src/
│   ├── __init__.py      # (empty)
│   ├── app.py           # def main():\n    print("app")
│   └── utils.py         # def helper():\n    return 42
├── tests/
│   └── test_app.py      # def test_main():\n    assert True
└── .gitignore           # __pycache__/\n*.pyc
```

### `tests/conftest.py` shared fixtures

```python
import pytest
from pathlib import Path
from unittest.mock import AsyncMock

@pytest.fixture
def sample_project(tmp_path) -> Path:
    """Create the sample project tree in a temp directory."""
    # ... create files as specified above ...
    return tmp_path

@pytest.fixture
def mock_llm_service():
    """Mock LLMService that returns deterministic summaries."""
    from lexibrary.llm.service import LLMService, FileSummaryResult
    service = AsyncMock(spec=LLMService)
    service.summarize_file.return_value = FileSummaryResult(
        path=Path("test.py"), summary="Test file summary."
    )
    service.summarize_files_batch.return_value = []
    service.summarize_directory.return_value = "Test directory summary."
    return service
```

### Coverage target
- Aim for **80%+ line coverage** across the project
- Critical paths (engine, parser, generator) should be **90%+**
- Daemon tests may have lower coverage due to threading complexity

### Running tests
```bash
uv run pytest --cov=lexibrary --cov-report=term-missing -v
```

---

## 8.5 Edge Cases to Test

| Edge case | Expected behavior |
|-----------|-------------------|
| Empty project (no files) | Creates `.aindex` with `(none)` sections |
| Single file, no subdirs | `.aindex` has file entry, `(none)` subdirectories |
| Very deep nesting (10+ levels) | Works correctly, bottom-up ordering maintained |
| File with no extension | Language detected as "Text" |
| Unicode filenames | Handled correctly in `.aindex` |
| File modified during crawl | Graceful handling (use hash at time of read) |
| `.gitignore` with negation patterns (`!important.log`) | pathspec handles this correctly |
| Empty `.gitignore` | No patterns, nothing ignored |
| No `.gitignore` | Config patterns still apply |
| Config with all defaults | Works without any `lexibrary.toml` |
| Symlinks to files | Followed (file read works) |
| Symlinks to directories | Not followed (os.walk default) |

---

## 8.6 Final Verification Checklist

Run these in order to verify the complete system:

```bash
# 1. Clean slate
cd /tmp && mkdir test-project && cd test-project
git init

# 2. Create some files
echo 'print("hello")' > main.py
mkdir src && echo 'def add(a, b): return a + b' > src/math.py
echo '# Test Project' > README.md

# 3. Initialize Lexibrary
uv run lexi init

# 4. Verify config created
cat lexibrary.toml

# 5. Run first crawl
uv run lexi crawl -v

# 6. Verify .aindex files
cat .aindex
cat src/.aindex

# 7. Check status
uv run lexi status

# 8. Modify a file
echo 'def sub(a, b): return a - b' >> src/math.py

# 9. Incremental crawl
uv run lexi crawl -v
# Should show "1 file summarized, N cached"

# 10. Dry run
uv run lexi crawl --dry-run

# 11. Full re-crawl
uv run lexi crawl --full -v

# 12. Daemon mode
uv run lexi daemon --foreground &
sleep 2
echo 'NEW_CONSTANT = 42' > src/config.py
sleep 5  # wait for debounce + indexing
cat src/.aindex  # should include config.py
kill %1  # stop daemon

# 13. Clean
uv run lexi clean --yes
ls -la .aindex  # should not exist

# 14. Run tests
uv run pytest --cov=lexibrary --cov-report=term-missing -v
```

---

## Acceptance Criteria

- [ ] No unhandled exceptions for any expected error scenario
- [ ] Clear, actionable error messages for config/auth problems
- [ ] Pre-flight check catches missing API key before any work starts
- [ ] All tests pass with 80%+ line coverage
- [ ] Critical paths have 90%+ coverage
- [ ] All 14 verification steps pass end-to-end
- [ ] Daemon recovers gracefully from LLM errors (logs, continues)
- [ ] `--verbose` flag produces useful debug output
- [ ] Daemon log file contains detailed event history
