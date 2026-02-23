# Troubleshooting

This guide covers common issues you may encounter when using Lexibrary, organized by category. Each issue includes symptoms, likely cause, and the recommended fix.

## Init Issues

### Re-init error: "Project already initialised"

**Symptoms:** Running `lexictl init` prints "Project already initialised. Use lexictl setup --update to modify settings." and exits with code 1.

**Cause:** The `.lexibrary/` directory already exists. The re-init guard prevents accidental overwriting of your configuration and generated artifacts.

**Fix:** Do not re-initialize. Instead, edit settings directly or use `lexictl setup`:

```bash
# Edit the config file directly
$EDITOR .lexibrary/config.yaml

# Regenerate agent rules after config changes
lexictl setup --update
```

If you truly need to start from scratch (this deletes all generated design files):

```bash
rm -rf .lexibrary/
lexictl init
```

See [Project Setup](project-setup.md) for details on changing settings after init.

### Non-TTY error in CI

**Symptoms:** Running `lexictl init` in a CI pipeline or Docker build prints "Non-interactive environment detected. Use lexictl init --defaults to run without prompts." and exits with code 1.

**Cause:** The init wizard requires interactive terminal input (stdin must be a TTY). When running in a non-interactive environment without the `--defaults` flag, the command refuses to proceed rather than hang waiting for input.

**Fix:** Use the `--defaults` flag:

```bash
lexictl init --defaults
```

This accepts all auto-detected values without prompting. See [CI Integration](ci-integration.md) for CI pipeline recipes.

### No LLM provider detected

**Symptoms:** During the LLM Provider step (Step 4) of `lexictl init`, the wizard shows no detected providers and defaults to `anthropic`.

**Cause:** None of the expected API key environment variables are set:

| Provider | Expected Environment Variable |
|----------|-------------------------------|
| `anthropic` | `ANTHROPIC_API_KEY` |
| `openai` | `OPENAI_API_KEY` |
| `google` | `GEMINI_API_KEY` |
| `ollama` | `OLLAMA_HOST` |

**Fix:** Set the appropriate environment variable before running `lexictl init`:

```bash
export ANTHROPIC_API_KEY="your-api-key-here"
lexictl init
```

If you already initialized without an API key, edit the config and set the environment variable before running `lexictl update`:

```bash
$EDITOR .lexibrary/config.yaml    # Verify llm.api_key_env is correct
export ANTHROPIC_API_KEY="your-api-key-here"
lexictl update
```

## Update Issues

### LLM API errors and timeouts

**Symptoms:** `lexictl update` reports failed files in the summary. The `files_failed` counter is non-zero. Error messages may mention connection timeouts, rate limiting, authentication failures, or HTTP 4xx/5xx errors.

**Cause:** The LLM API is unreachable, rate-limited, or rejecting requests. Common reasons:

- The API key environment variable is not set or contains an invalid key.
- The provider's API is temporarily unavailable or rate-limiting your requests.
- The `llm.timeout` setting (default: 60 seconds) is too short for large files.
- Network connectivity issues.

**Fix:**

1. Verify the API key is set and valid:
   ```bash
   echo $ANTHROPIC_API_KEY    # or whichever provider you use
   ```

2. Check the provider and model in config:
   ```bash
   grep -A 4 "^llm:" .lexibrary/config.yaml
   ```

3. For timeout issues, increase the timeout:
   ```yaml
   llm:
     timeout: 120    # Increase from default 60 seconds
   ```

4. For rate limiting, increase the retry count:
   ```yaml
   llm:
     max_retries: 5    # Increase from default 3
   ```

5. Re-run the update -- unchanged files are skipped automatically, so only failed files are retried:
   ```bash
   lexictl update
   ```

### "No files found" or empty update summary

**Symptoms:** `lexictl update` reports 0 files scanned, or all files are skipped. The update summary shows no work done.

**Cause:** The `scope_root` setting does not match your project structure, or ignore patterns are too aggressive.

**Fix:**

1. Check the scope root:
   ```bash
   grep "scope_root" .lexibrary/config.yaml
   ```
   If `scope_root` is set to a directory that does not exist (e.g., `src/` when your code is at the project root), no files will be found.

2. Verify the scope root contains source files:
   ```bash
   ls $(grep "scope_root" .lexibrary/config.yaml | awk '{print $2}' | tr -d '"')
   ```

3. Check ignore patterns. Files may be excluded by `.gitignore`, `.lexignore`, or `ignore.additional_patterns` in config:
   ```bash
   cat .lexignore
   grep -A 20 "additional_patterns" .lexibrary/config.yaml
   ```

4. Check the file size limit. Large files are skipped:
   ```yaml
   crawl:
     max_file_size_kb: 1024    # Increase from default 512 KB
   ```

See [Ignore Patterns](ignore-patterns.md) for the complete ignore system documentation.

### Design files not generated for new files

**Symptoms:** After adding new source files, running `lexictl update` does not create design files for them.

**Cause:** New files may be excluded by ignore patterns, may have binary extensions, may exceed the file size limit, or may be outside the `scope_root`.

**Fix:**

1. Confirm the file is under `scope_root`:
   ```bash
   grep "scope_root" .lexibrary/config.yaml
   ```

2. Check if the file extension is in `crawl.binary_extensions`:
   ```bash
   grep -A 40 "binary_extensions" .lexibrary/config.yaml
   ```

3. Check if the file matches an ignore pattern (see the checklist in [Ignore Patterns -- Debugging](ignore-patterns.md#debugging-ignore-patterns)).

4. Check the file size:
   ```bash
   ls -lh path/to/new/file.py
   grep "max_file_size_kb" .lexibrary/config.yaml
   ```

### Stale design files after source changes

**Symptoms:** `lexictl validate` reports `hash_freshness` warnings. Design files do not reflect recent source changes.

**Cause:** Design files are only regenerated when `lexictl update` is run. If you edit source files without running `lexictl update` (and without a post-commit hook), design files become stale.

**Fix:**

1. Run a full update to regenerate stale design files:
   ```bash
   lexictl update
   ```

2. To prevent this in the future, install the git post-commit hook:
   ```bash
   lexictl setup --hooks
   ```
   This runs `lexictl update --changed-only` automatically after each commit.

3. Alternatively, set up periodic sweeps:
   ```bash
   lexictl sweep --watch
   ```

See [CI Integration](ci-integration.md) for automated update strategies.

### Conflict markers prevent update

**Symptoms:** `lexictl update` skips specific files and counts them as failed. The files contain unresolved git merge conflicts.

**Cause:** Lexibrary checks for conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`) before sending a file to the LLM. Files with conflict markers are skipped to avoid generating design files from inconsistent content.

**Fix:** Resolve the merge conflicts in the source file first, then re-run the update:

```bash
# Resolve conflicts in your editor
$EDITOR path/to/conflicted/file.py

# Commit the resolution
git add path/to/conflicted/file.py
git commit -m "Resolve merge conflict"

# Update the design file
lexictl update path/to/conflicted/file.py
```

## Validation Issues

### hash_freshness warnings after manual edits

**Symptoms:** `lexictl validate` reports `hash_freshness` warnings for files you recently edited.

**Cause:** The `source_hash` in the design file metadata footer no longer matches the SHA-256 hash of the current source file. This is expected after editing source files -- it means the design file needs to be regenerated to reflect the changes.

**Fix:**

```bash
# Regenerate design files for all stale files
lexictl update

# Or update a specific file
lexictl update path/to/edited/file.py
```

If you edited the design file directly (as an agent or manually), the `design_hash` check will detect this and classify the file as `AGENT_UPDATED`. In this case, `lexictl update` refreshes the footer hashes without calling the LLM, preserving your edits.

### Orphan concepts warning

**Symptoms:** `lexictl validate` reports `orphan_concepts` warnings listing concept files with zero inbound references.

**Cause:** The concept exists in `.lexibrary/concepts/` but no design file, Stack post, or other concept references it via a `[[wikilink]]`. The concept may be newly created and not yet linked, or it may have become unused after code was removed.

**Fix:**

- If the concept is still relevant, add wikilink references in relevant design files or other artifacts.
- If the concept is no longer needed, delete the concept file:
  ```bash
  rm .lexibrary/concepts/unused-concept.md
  ```
- If the concept is being phased out, set its status to `deprecated`:
  ```yaml
  ---
  title: Old Concept
  aliases: []
  tags: []
  status: deprecated
  ---
  ```

See [Concepts Wiki](concepts-wiki.md) for concept lifecycle management.

### Broken wikilinks (wikilink_resolution errors)

**Symptoms:** `lexictl validate` reports `wikilink_resolution` errors with messages like "`[[concept-name]] does not resolve`".

**Cause:** A `[[wikilink]]` in a design file or Stack post references a concept that does not exist (by title or alias). The concept may have been renamed, deleted, or never created.

**Fix:**

1. Check the suggestion in the validation output -- it often includes a fuzzy match (e.g., "Did you mean `[[authentication-middleware]]`?").

2. If the concept was renamed, update the wikilink in the referencing artifact to use the new name.

3. If the concept should exist but does not, create it:
   ```bash
   lexi concept new concept-name --tag relevant-tag
   ```

4. If the wikilink is no longer relevant, remove it from the design file or Stack post. Note that design files are regenerated by `lexictl update`, so the wikilink may reappear. You can add the concept as an alias to an existing concept to resolve the reference permanently.

### Concept frontmatter errors

**Symptoms:** `lexictl validate` reports `concept_frontmatter` errors for concept files in `.lexibrary/concepts/`.

**Cause:** A concept file has invalid or missing YAML frontmatter. The validator checks for:

- A YAML frontmatter block delimited by `---`
- Valid YAML syntax
- All four mandatory fields: `title`, `aliases`, `tags`, `status`
- A valid `status` value: `draft`, `active`, or `deprecated`

**Fix:** Edit the concept file to include valid frontmatter:

```markdown
---
title: My Concept
aliases: [my-concept-alias]
tags: [architecture]
status: active
---

Concept description goes here.
```

## Daemon Issues

### Stale PID file

**Symptoms:** `lexictl daemon status` reports the daemon is running, but no daemon process is actually active. Or `lexictl daemon start` refuses to start because it thinks a daemon is already running.

**Cause:** The daemon process was terminated without cleaning up its PID file at `.lexibrary/daemon.pid` (e.g., the system was rebooted, or the process was killed with `kill -9`).

**Fix:** `lexictl daemon stop` handles stale PID files gracefully -- it checks whether the process is actually running and cleans up the PID file if not:

```bash
lexictl daemon stop
lexictl daemon start
```

If that does not work, manually remove the PID file:

```bash
rm .lexibrary/daemon.pid
lexictl daemon start
```

### Watchdog not starting

**Symptoms:** `lexictl daemon start` prints a message suggesting `lexictl sweep --watch` instead, and does not start the daemon.

**Cause:** The daemon requires `daemon.watchdog_enabled: true` in config. By default, watchdog mode is disabled.

**Fix:** Enable watchdog mode in config:

```yaml
daemon:
  watchdog_enabled: true
```

Then start the daemon:

```bash
lexictl daemon start
```

Alternatively, use the sweep command which does not require watchdog to be enabled:

```bash
lexictl sweep --watch
```

See [CI Integration -- Daemon vs Sweep](ci-integration.md#daemon-vs-sweep) for guidance on which to use.

### Sweep not detecting changes

**Symptoms:** `lexictl sweep --watch` runs periodic sweeps but reports no files changed, even though source files have been modified.

**Cause:**

- `daemon.sweep_skip_if_unchanged` is `true` (the default), and the sweep's change detection is not picking up your changes. This can happen if files were modified but their SHA-256 hashes happen to match (extremely rare), or if the files are excluded by ignore patterns.
- The sweep interval may be too long for your workflow.

**Fix:**

1. Run a one-shot sweep to verify changes are detected:
   ```bash
   lexictl sweep
   ```

2. If the one-shot sweep detects no changes, check that modified files are under `scope_root` and not excluded by ignore patterns.

3. To reduce the sweep interval for more responsive detection:
   ```yaml
   daemon:
     sweep_interval_seconds: 300    # Every 5 minutes instead of every hour
   ```

4. To force sweeps to always run (even when no changes are detected):
   ```yaml
   daemon:
     sweep_skip_if_unchanged: false
   ```

## Config Issues

### YAML parse errors

**Symptoms:** Any `lexictl` command fails with a YAML parsing error when reading `.lexibrary/config.yaml`.

**Cause:** The config file contains invalid YAML syntax. Common mistakes:

- Incorrect indentation (YAML requires consistent spaces, not tabs).
- Missing colons after keys.
- Unquoted special characters in values.
- Strings containing `:` or `#` that need quoting.

**Fix:**

1. Check the error message for the line number and character position.

2. Validate the YAML syntax using an online YAML validator or a command-line tool:
   ```bash
   python -c "import yaml; yaml.safe_load(open('.lexibrary/config.yaml'))"
   ```

3. Common fixes:
   ```yaml
   # Wrong: tab indentation
   llm:
   	provider: anthropic    # Tab character -- will cause an error

   # Right: space indentation
   llm:
     provider: anthropic    # Two spaces

   # Wrong: unquoted special characters
   ignore:
     additional_patterns:
       - .lexibrary/**/*.md    # The * characters may cause issues

   # Right: quoted patterns
   ignore:
     additional_patterns:
       - ".lexibrary/**/*.md"
   ```

4. If the file is beyond repair, regenerate it from defaults:
   ```bash
   rm .lexibrary/config.yaml
   rm -rf .lexibrary/
   lexictl init
   ```

### Unknown config keys ignored silently

**Symptoms:** You added a config key but it has no effect. No error or warning is shown.

**Cause:** All Pydantic config models use `extra="ignore"`, which means unrecognized keys are silently discarded during parsing. This is intentional for forward compatibility (so upgrading Lexibrary never breaks existing configs), but it also means typos in key names go unnoticed.

**Fix:**

1. Check the key name against the [Configuration](configuration.md) reference. Common typos:
   - `scope-root` instead of `scope_root` (underscores, not hyphens)
   - `llm_provider` instead of `llm.provider` (nested under `llm:` section)
   - `binary-extensions` instead of `binary_extensions`

2. Verify the nesting level is correct. For example, `provider` must be nested under `llm:`:
   ```yaml
   # Wrong: provider at top level
   provider: anthropic

   # Right: provider nested under llm
   llm:
     provider: anthropic
   ```

3. Compare your config against the [Full Default Configuration](configuration.md#full-default-configuration) to verify structure.

### API key not found at runtime

**Symptoms:** `lexictl update` fails with an authentication error even though you believe the API key is set.

**Cause:** The environment variable name in `llm.api_key_env` does not match the environment variable you have set, or the variable is set in a different shell session.

**Fix:**

1. Check which environment variable Lexibrary is looking for:
   ```bash
   grep "api_key_env" .lexibrary/config.yaml
   ```

2. Verify that environment variable is set in the current shell:
   ```bash
   echo $ANTHROPIC_API_KEY    # or whichever variable name is configured
   ```

3. If the variable is set in a `.env` file or another shell profile, ensure it is loaded in the current session:
   ```bash
   source .env    # or source ~/.bashrc, etc.
   ```

4. If you use a different variable name, update the config:
   ```yaml
   llm:
     api_key_env: MY_CUSTOM_API_KEY_VAR
   ```

## Link Graph Issues

### Link graph not built

**Symptoms:** `lexictl status` shows "Link graph: not built". `lexi lookup` does not show dependents or reverse references.

**Cause:** The link graph is built during `lexictl update`. If you have not run a full update, or if the build failed, the link graph will be absent.

**Fix:**

```bash
lexictl update
```

Check the update summary for `linkgraph_built: true`. If it shows `false` or a `linkgraph_error`, see the next section.

### Link graph build error

**Symptoms:** The update summary shows `linkgraph_built: false` and a `linkgraph_error` message.

**Cause:** The link graph build encountered an unrecoverable error. Per-artifact parse errors are caught and logged without aborting the build, but schema creation failures or transaction errors will prevent the build.

**Fix:**

1. Delete the database and rebuild:
   ```bash
   rm .lexibrary/index.db
   lexictl update
   ```

2. If the error persists, check for file permission issues on the `.lexibrary/` directory.

### Schema version mismatch after upgrade

**Symptoms:** After upgrading Lexibrary, link graph queries return empty results, or `lexictl status` shows unexpected link graph metadata.

**Cause:** The link graph schema version has changed between Lexibrary versions. The schema version is stored in the `meta` table and checked on each access. A mismatch causes queries to return empty results (graceful degradation).

**Fix:** The schema is automatically recreated during the next full build:

```bash
lexictl update
```

If that does not resolve it, force a rebuild:

```bash
rm .lexibrary/index.db
lexictl update
```

See [Link Graph -- Schema Version](link-graph.md#schema-version) for details.

## Related Documentation

- [Configuration](configuration.md) -- Full `config.yaml` reference
- [lexictl Reference](lexictl-reference.md) -- Complete CLI command reference with exit codes
- [Design File Generation](design-file-generation.md) -- How `lexictl update` works end-to-end
- [Validation](validation.md) -- The 13 validation checks and their meanings
- [Ignore Patterns](ignore-patterns.md) -- Pattern sources, precedence, and debugging
- [Link Graph](link-graph.md) -- The SQLite index, rebuilding, and graceful degradation
- [CI Integration](ci-integration.md) -- Git hooks, periodic sweeps, and CI pipeline recipes
- [Project Setup](project-setup.md) -- Init wizard, re-init guard, changing settings
- [Upgrading](upgrading.md) -- Version upgrade guide
