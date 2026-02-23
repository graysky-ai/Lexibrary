# CI Integration

This guide covers how to integrate Lexibrary into your CI/CD pipeline and development workflow -- from git hooks for automatic updates to validation gates and daemon-based continuous monitoring.

## Git Post-Commit Hook

The most common integration is a git post-commit hook that automatically updates design files for changed source files after each commit.

### Installing the Hook

```bash
lexictl setup --hooks
```

This installs a post-commit hook at `.git/hooks/post-commit` that:

1. Determines which files were changed in the most recent commit.
2. Runs `lexictl update --changed-only <changed-files>` to regenerate design files for those files only.

If a hook already exists, the command warns without overwriting it.

### How the Hook Works

When you make a commit, the hook:

1. Gets the list of changed files from `git diff-tree --no-commit-id --name-only -r HEAD`.
2. Passes those file paths to `lexictl update --changed-only`.
3. Each changed file goes through the same change detection pipeline (SHA-256 hash comparison, ChangeLevel classification).
4. Only files that actually need updating are sent to the LLM.
5. The link graph index is incrementally updated for the changed files.

The hook uses `--changed-only` mode, which means:

- No full file discovery -- only the specified files are processed.
- No `START_HERE.md` regeneration (run `lexictl update` periodically for that).
- Incremental link graph update instead of full rebuild.
- Deleted file paths are handled gracefully (link graph entries cleaned up via CASCADE).

### Manual Changed-Only Updates

You can also run the changed-only mode manually:

```bash
# Update specific files
lexictl update --changed-only src/auth/service.py src/auth/middleware.py

# Combine with git to update files changed since a specific commit
git diff --name-only HEAD~3 | xargs lexictl update --changed-only
```

## Periodic Sweep

For teams that want design files updated on a schedule rather than per-commit:

### One-Shot Sweep

```bash
lexictl sweep
```

This runs a full `lexictl update` cycle once and exits. Useful in cron jobs or scheduled CI pipelines.

### Watch Mode

```bash
lexictl sweep --watch
```

This runs periodic sweeps in the foreground at the interval configured by `daemon.sweep_interval_seconds` (default: 3600 seconds / 1 hour). The process runs until interrupted with Ctrl+C.

If `daemon.sweep_skip_if_unchanged` is `true` (the default), sweeps that detect no changed files skip the LLM generation step entirely.

## Daemon Mode

For continuous file watching using the OS file system event API:

```bash
lexictl daemon start
```

This starts a watchdog-based daemon that monitors the project for file changes and triggers incremental updates automatically. The daemon:

- Writes its PID to `.lexibrary/daemon.pid`.
- Uses debouncing (`daemon.debounce_seconds`, default: 2 seconds) to batch rapid file changes.
- Suppresses updates during git operations (`daemon.git_suppression_seconds`, default: 5 seconds).
- Requires `daemon.watchdog_enabled: true` in config (disabled by default).

### Daemon Commands

```bash
# Start the daemon (foreground, requires watchdog_enabled: true)
lexictl daemon start

# Check if the daemon is running
lexictl daemon status

# Stop the daemon
lexictl daemon stop
```

### Daemon vs Sweep

| Feature | `lexictl sweep --watch` | `lexictl daemon start` |
|---|---|---|
| Trigger | Timer-based (periodic) | File system events (immediate) |
| Config required | None | `daemon.watchdog_enabled: true` |
| Update type | Full project sweep | Incremental (changed files only) |
| Use case | CI/scheduled pipelines | Active development |

## Validation as a CI Gate

Use `lexictl validate` in CI pipelines to enforce library health:

```bash
lexictl validate
```

The command exits with:

| Exit Code | Meaning | CI Behavior |
|---|---|---|
| `0` | No issues | Pipeline passes |
| `1` | Error-severity issues found | Pipeline fails |
| `2` | Warning-severity issues found (no errors) | Pipeline passes (or fails, depending on your policy) |

### Strict Validation (Fail on Warnings)

To fail on warnings as well as errors:

```bash
lexictl validate
exit_code=$?
if [ $exit_code -ne 0 ]; then
  echo "Validation failed with exit code $exit_code"
  exit 1
fi
```

### JSON Output for Parsing

For pipelines that need to parse results:

```bash
lexictl validate --json
```

### Targeted Checks

To run only specific checks in CI:

```bash
# Only check for broken wikilinks
lexictl validate --check wikilink_resolution

# Only check hash freshness (stale design files)
lexictl validate --check hash_freshness
```

## Quiet Status for Notifications

For dashboards, Slack notifications, or monitoring:

```bash
lexictl status --quiet
```

This outputs a single line:

```
lexictl: library healthy
```

Or, if there are issues:

```
lexictl: 2 errors, 5 warnings -- run `lexictl validate`
```

The exit code mirrors `lexictl validate`: 0 for clean, 1 for errors, 2 for warnings.

## Example CI Pipelines

### GitHub Actions

```yaml
name: Lexibrary Validation
on:
  push:
    branches: [main]
  pull_request:

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          pip install uv
          uv sync

      - name: Validate library
        run: uv run lexictl validate

      - name: Check library status
        run: uv run lexictl status --quiet
```

### GitHub Actions -- Update on Push

```yaml
name: Update Design Files
on:
  push:
    branches: [main]

jobs:
  update:
    runs-on: ubuntu-latest
    env:
      ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 2  # Need parent commit for diff

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          pip install uv
          uv sync

      - name: Update changed files
        run: |
          CHANGED=$(git diff --name-only HEAD~1)
          if [ -n "$CHANGED" ]; then
            echo "$CHANGED" | xargs uv run lexictl update --changed-only
          fi

      - name: Commit updated design files
        run: |
          git config user.name "Lexibrary Bot"
          git config user.email "lexibrary@noreply"
          git add .lexibrary/
          git diff --staged --quiet || git commit -m "Update design files"
          git push
```

### GitLab CI

```yaml
stages:
  - validate
  - update

validate-library:
  stage: validate
  image: python:3.11
  script:
    - pip install uv
    - uv sync
    - uv run lexictl validate
  rules:
    - if: $CI_MERGE_REQUEST_IID

update-design-files:
  stage: update
  image: python:3.11
  variables:
    ANTHROPIC_API_KEY: $ANTHROPIC_API_KEY
  script:
    - pip install uv
    - uv sync
    - >
      CHANGED=$(git diff --name-only HEAD~1)
      && echo "$CHANGED" | xargs uv run lexictl update --changed-only
  rules:
    - if: $CI_COMMIT_BRANCH == "main"
```

## Non-Interactive Init for CI

When initializing Lexibrary in a CI environment where stdin is not a TTY:

```bash
lexictl init --defaults
```

This accepts all detected defaults without prompting. Without `--defaults`, `lexictl init` detects the non-TTY environment and exits with an error, directing you to use the flag.

## Configuration for CI

Key config settings that affect CI behavior:

| Setting | Default | CI Recommendation |
|---|---|---|
| `daemon.sweep_skip_if_unchanged` | `true` | Keep `true` to avoid unnecessary LLM calls |
| `llm.max_retries` | `3` | Consider lowering to `1` for faster CI failures |
| `llm.timeout` | `60` | Consider lowering for CI time constraints |
| `crawl.max_file_size_kb` | `512` | Increase if your project has large source files |

## Related Documentation

- [Design File Generation](design-file-generation.md) -- How `lexictl update` and `--changed-only` work
- [Validation](validation.md) -- The 13 checks and their exit codes
- [Configuration](configuration.md) -- `daemon`, `llm`, and `crawl` settings
- [Project Setup](project-setup.md) -- `lexictl init --defaults` and `lexictl setup --hooks`
