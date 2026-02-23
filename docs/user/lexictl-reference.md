# lexictl CLI Reference

`lexictl` is the operator-facing maintenance CLI for Lexibrary. It provides commands for project initialization, design file generation, validation, health monitoring, agent environment setup, background sweeps, and daemon management.

Run `lexictl --help` for a summary of all commands.

## Commands

| Command | Purpose |
|---------|---------|
| `init` | Initialize Lexibrary in a project (setup wizard) |
| `update` | Re-index changed files and regenerate design files |
| `validate` | Run consistency checks on the library |
| `status` | Show library health and staleness summary |
| `setup` | Install or update agent environment rules |
| `sweep` | Run a library update sweep (one-shot or watch mode) |
| `daemon` | Manage the watchdog daemon (deprecated -- prefer `sweep`) |

---

## init

Initialize Lexibrary in a project. Runs an interactive 8-step setup wizard that detects project configuration and guides you through setup.

```
lexictl init [--defaults]
```

### Options

| Option | Description |
|--------|-------------|
| `--defaults` | Accept all detected defaults without prompting. Required for CI/scripting and non-interactive environments. |

### Behavior

1. **Re-init guard** -- If `.lexibrary/` already exists, the command exits with code 1 and directs you to `lexictl setup --update`.
2. **Non-TTY detection** -- If stdin is not a terminal and `--defaults` is not set, the command exits with code 1 and suggests using `--defaults`.
3. **Wizard flow** -- Runs the 8-step wizard (see [Project Setup](project-setup.md) for a detailed walkthrough of each step).
4. **Skeleton creation** -- On confirmation, creates the `.lexibrary/` directory with `config.yaml`, `START_HERE.md`, subdirectories (`concepts/`, `stack/`), and a `.lexignore` file.

### Examples

```bash
# Interactive initialization
lexictl init

# Non-interactive initialization (CI/scripting)
lexictl init --defaults
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Initialization completed successfully |
| 1 | Already initialized, non-TTY without `--defaults`, or user cancelled |

---

## update

Re-index changed files and regenerate design files. This is the primary command for keeping the Lexibrary in sync with source code changes.

```
lexictl update [PATH] [--changed-only FILE1 FILE2 ...]
```

### Arguments

| Argument | Description |
|----------|-------------|
| `PATH` | (Optional) File or directory to update. Omit to update the entire project. |

### Options

| Option | Description |
|--------|-------------|
| `--changed-only FILE [FILE ...]` | Only update the specified files. Designed for git hooks and CI pipelines. Mutually exclusive with the `PATH` argument. |

### Modes

The command operates in three modes depending on arguments:

**Full project update** (no arguments):

```bash
lexictl update
```

Discovers all source files under `scope_root`, compares SHA-256 hashes against existing design files, sends changed files to the LLM for regeneration, rebuilds `.aindex` routing tables, regenerates `START_HERE.md`, and builds the link graph index. Displays a progress bar during processing.

**Single file or directory update** (with `PATH`):

```bash
# Single file
lexictl update src/mypackage/module.py

# Directory (runs full project pipeline)
lexictl update src/mypackage/
```

When `PATH` is a file, updates only that file's design file and reports the change level. When `PATH` is a directory, runs the full project update pipeline.

**Changed-only update** (with `--changed-only`):

```bash
lexictl update --changed-only src/module.py src/utils.py
```

Updates design files for only the specified files. Does not regenerate `START_HERE.md` or rebuild the full link graph. Designed for use in git post-commit hooks where only recently changed files need updating.

### Output

After a project or changed-only update, a summary is displayed:

```
Update summary:
  Files scanned:       42
  Files unchanged:     38
  Files created:       2
  Files updated:       2
  Files agent-updated: 0
  .aindex refreshed:   3
```

| Counter | Meaning |
|---------|---------|
| Files scanned | Total files discovered and examined |
| Files unchanged | Files whose SHA-256 hash matched the existing design file |
| Files created | New design files generated for previously unindexed files |
| Files updated | Design files regenerated due to source changes |
| Files agent-updated | Design files where `updated_by: agent` was preserved (not overwritten) |
| .aindex refreshed | Number of `.aindex` routing tables that were regenerated |
| Token budget warnings | Files where generated content exceeded the configured token budget |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Update completed successfully |
| 1 | Path not found, path outside project root, `PATH` and `--changed-only` used together, or one or more files failed |

### Examples

```bash
# Update the entire project
lexictl update

# Update a single file
lexictl update src/lexibrary/config/schema.py

# Update only files changed in the last commit (for git hooks)
lexictl update --changed-only $(git diff-tree --no-commit-id --name-only -r HEAD)
```

---

## validate

Run consistency checks on the library. Reports issues grouped by severity level.

```
lexictl validate [--severity LEVEL] [--check NAME] [--json]
```

### Options

| Option | Description |
|--------|-------------|
| `--severity LEVEL` | Minimum severity to report. Valid values: `error`, `warning`, `info`. When set, only checks at or above this severity level are run. |
| `--check NAME` | Run only the named check. See the available checks table below. |
| `--json` | Output results as JSON instead of Rich-formatted tables. Useful for CI pipelines and programmatic consumption. |

### Available Checks

Lexibrary includes 13 validation checks organized by severity:

**Error-level checks** (indicate broken state):

| Check | Description |
|-------|-------------|
| `wikilink_resolution` | Wikilinks in design files and concepts resolve to valid targets |
| `file_existence` | Source files referenced in design file frontmatter still exist |
| `concept_frontmatter` | Concept files have valid YAML frontmatter (title, status, tags) |

**Warning-level checks** (indicate potential issues):

| Check | Description |
|-------|-------------|
| `hash_freshness` | Design file source hashes match the current source file content |
| `token_budgets` | Generated artifacts stay within configured token budget targets |
| `orphan_concepts` | Concepts are linked to at least one design file |
| `deprecated_concept_usage` | Deprecated concepts are not referenced in active design files |

**Info-level checks** (informational):

| Check | Description |
|-------|-------------|
| `forward_dependencies` | Design files declare forward dependency relationships |
| `stack_staleness` | Open Stack posts have not been idle for too long |
| `aindex_coverage` | Directories with design files also have `.aindex` routing tables |
| `bidirectional_deps` | Dependency relationships are declared in both directions |
| `dangling_links` | Links in the link graph point to existing artifacts |
| `orphan_artifacts` | Design files in `.lexibrary/` have corresponding source files |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | No issues found (clean) |
| 1 | One or more error-level issues found, or an invalid check/severity was specified |
| 2 | Warning-level issues found but no errors |

See [Validation](validation.md) for a detailed explanation of exit codes and how to use them as CI gates.

### Examples

```bash
# Run all checks
lexictl validate

# Show only errors and warnings
lexictl validate --severity warning

# Show only errors
lexictl validate --severity error

# Run a single check
lexictl validate --check hash_freshness

# JSON output for CI
lexictl validate --json

# Use as a CI gate (exits 1 on errors)
lexictl validate --severity error || echo "Validation failed"
```

---

## status

Show library health and staleness summary. Provides a quick overview of the library's current state.

```
lexictl status [PATH] [--quiet | -q]
```

### Arguments

| Argument | Description |
|----------|-------------|
| `PATH` | (Optional) Project directory to check. Defaults to the current directory. |

### Options

| Option | Description |
|--------|-------------|
| `--quiet`, `-q` | Single-line output suitable for hooks, CI, and notifications. |

### Dashboard Mode (default)

Without `--quiet`, displays a full dashboard:

```
Lexibrary Status

  Files: 42 tracked, 2 stale
  Concepts: 5 active, 1 deprecated, 2 draft
  Stack: 3 posts (2 resolved, 1 open)
  Link graph: 42 artifacts, 156 links (built 2026-02-23)
  Issues: 0 errors, 2 warnings
  Updated: 15 minutes ago

Run `lexictl validate` for details.
```

The dashboard shows:

| Section | What it reports |
|---------|-----------------|
| Files | Count of tracked design files and how many are stale (source hash mismatch) |
| Concepts | Count by status: active, deprecated, draft |
| Stack | Total posts with open/resolved breakdown |
| Link graph | Artifact and link counts with build timestamp, or "not built" if missing |
| Issues | Error and warning counts from a lightweight validation pass |
| Updated | Time since the most recent design file was generated |

### Quiet Mode

With `--quiet`, outputs a single line:

```bash
$ lexictl status --quiet
lexictl: 2 warnings -- run `lexictl validate`

$ lexictl status --quiet
lexictl: library healthy
```

Quiet mode output patterns:

| Output | Condition |
|--------|-----------|
| `lexictl: N error(s), M warning(s) -- run 'lexictl validate'` | Errors and warnings found |
| `lexictl: N error(s) -- run 'lexictl validate'` | Only errors found |
| `lexictl: N warning(s) -- run 'lexictl validate'` | Only warnings found |
| `lexictl: library healthy` | No errors or warnings |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | No issues found |
| 1 | One or more error-level issues found |
| 2 | Warning-level issues found but no errors |

### Examples

```bash
# Full dashboard
lexictl status

# Quick check in a script or hook
lexictl status --quiet

# Check a specific project directory
lexictl status /path/to/project
```

---

## setup

Install or update agent environment rules. Generates rule files that teach AI agents how to use the Lexibrary in your project.

```
lexictl setup [--update] [--env ENV] [--hooks]
```

### Options

| Option | Description |
|--------|-------------|
| `--update` | Update agent rules for the configured environments. Required to perform any rule generation. |
| `--env ENV` | Explicit environment(s) to generate rules for. Can be specified multiple times. Overrides the `agent_environment` config value. |
| `--hooks` | Install the git post-commit hook for automatic design file updates. |

### Supported Environments

| Environment | Generated Files |
|-------------|----------------|
| `claude` | `CLAUDE.md` or `.claude/CLAUDE.md` |
| `cursor` | `.cursor/rules` |
| `codex` | `AGENTS.md` |

### Rule Generation (--update)

Reads the `agent_environment` list from `.lexibrary/config.yaml` and generates rule files for each environment. These files contain instructions that tell AI agents how to use Lexibrary commands and follow the proper workflows.

```bash
# Generate rules for all configured environments
lexictl setup --update

# Generate rules for specific environments (overrides config)
lexictl setup --update --env claude --env cursor
```

Also ensures `.iwh` files are added to `.gitignore` (so IWH trace files are not committed).

### Hook Installation (--hooks)

Installs a git `post-commit` hook that automatically runs `lexictl update --changed-only` on files changed in each commit. The hook runs in the background so it never blocks the developer workflow.

```bash
lexictl setup --hooks
```

Behavior:

- If no `.git/` directory exists, reports an error and exits.
- If the hook is already installed (idempotent check via marker comment), reports that it is already present.
- If a `post-commit` hook already exists, appends the Lexibrary section to the existing file.
- If no hook exists, creates a new hook script.

### Usage Without Flags

Running `lexictl setup` without `--update` or `--hooks` displays usage instructions.

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Rules generated or hook installed successfully |
| 1 | No agent environments configured, unsupported environment specified, or no `.git/` directory |

### Examples

```bash
# Update agent rules
lexictl setup --update

# Update rules for a specific environment
lexictl setup --update --env claude

# Install the git post-commit hook
lexictl setup --hooks

# Both together
lexictl setup --update --hooks
```

---

## sweep

Run a library update sweep. A sweep performs the same work as `lexictl update` but is designed for automated/periodic use.

```
lexictl sweep [--watch]
```

### Options

| Option | Description |
|--------|-------------|
| `--watch` | Run periodic sweeps in the foreground until interrupted with Ctrl+C. |

### Modes

**One-shot** (default): Performs a single full library update and exits.

```bash
lexictl sweep
```

**Watch mode**: Runs periodic sweeps at the interval configured in `daemon.sweep_interval_seconds` (default: 3600 seconds / 1 hour). Runs in the foreground and can be interrupted with Ctrl+C.

```bash
lexictl sweep --watch
```

The sweep interval and skip-if-unchanged behavior are controlled by the `daemon` section of `config.yaml`:

- `daemon.sweep_interval_seconds` -- Time between sweeps (default: 3600)
- `daemon.sweep_skip_if_unchanged` -- Skip sweeps when no files have changed (default: true)

### Examples

```bash
# One-shot sweep
lexictl sweep

# Continuous sweeps in the foreground
lexictl sweep --watch
```

---

## daemon

Manage the watchdog daemon for real-time file monitoring. The daemon uses the `watchdog` library to detect file changes and trigger updates in real time.

**Note:** The daemon command is deprecated in favor of `lexictl sweep --watch`. It remains available for real-time file watching use cases that require immediate response to file changes (rather than periodic polling).

```
lexictl daemon [ACTION]
```

### Arguments

| Argument | Description |
|----------|-------------|
| `ACTION` | Action to perform: `start`, `stop`, or `status`. Defaults to `start` if omitted. |

### Prerequisite

The daemon requires `daemon.watchdog_enabled: true` in `config.yaml`. If watchdog mode is disabled (the default), `lexictl daemon start` will display a message suggesting `lexictl sweep --watch` instead.

### Actions

**start** -- Start the watchdog daemon. Writes a PID file to `.lexibrary/daemon.pid`.

```bash
lexictl daemon start
# or equivalently:
lexictl daemon
```

**stop** -- Send SIGTERM to the running daemon process using the PID from `.lexibrary/daemon.pid`. Cleans up stale PID files if the process is no longer running.

```bash
lexictl daemon stop
```

**status** -- Check whether the daemon is running by reading the PID file and verifying the process exists.

```bash
lexictl daemon status
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Action completed successfully |
| 1 | Invalid action, cannot read PID file, or permission denied |

### Examples

```bash
# Start the daemon (requires watchdog_enabled: true)
lexictl daemon start

# Check if the daemon is running
lexictl daemon status

# Stop the daemon
lexictl daemon stop
```

---

## See Also

- [Project Setup](project-setup.md) -- Detailed walkthrough of the `lexictl init` wizard
- [Configuration](configuration.md) -- Full `config.yaml` reference
- [Design File Generation](design-file-generation.md) -- How `lexictl update` works under the hood
- [Validation](validation.md) -- Deep dive into the 13 validation checks
- [CI Integration](ci-integration.md) -- Recipes for git hooks and CI pipelines
- [Troubleshooting](troubleshooting.md) -- Common issues and fixes
