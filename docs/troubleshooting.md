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

**Cause:** None of the directories listed in `scope_roots` match your project structure, the listed roots are missing on disk, or ignore patterns are too aggressive.

**Fix:**

1. Check the declared roots:
   ```bash
   grep -A 5 "scope_roots" .lexibrary/config.yaml
   ```
   If any listed `path` points at a directory that does not exist on disk
   (for example `src/` when your code lives at the project root), that root is
   logged as a warning (`scope_root '<path>' does not exist on disk; skipping`)
   and is skipped during the crawl. Other declared roots still run.

2. Verify each declared root contains source files, e.g.:
   ```bash
   for dir in src/ baml_src/; do ls "$dir" 2>/dev/null; done
   ```

3. If every declared root is wrong, the update reports zero files scanned.
   Edit `scope_roots:` in `.lexibrary/config.yaml` so at least one entry
   points at a real source directory.

4. Check ignore patterns. Files may be excluded by `.gitignore`, `.lexignore`, or `ignore.additional_patterns` in config:
   ```bash
   cat .lexignore
   grep -A 20 "additional_patterns" .lexibrary/config.yaml
   ```

5. Check the file size limit. Large files are skipped:
   ```yaml
   crawl:
     max_file_size_kb: 1024    # Increase from default 512 KB
   ```

See [Ignore Patterns](ignore-patterns.md) for the complete ignore system documentation.

### Design files not generated for new files

**Symptoms:** After adding new source files, running `lexictl update` does not create design files for them.

**Cause:** New files may be excluded by ignore patterns, may have binary extensions, may exceed the file size limit, or may live outside every declared `scope_roots` entry.

**Fix:**

1. Confirm the file is under at least one declared root in `scope_roots`:
   ```bash
   grep -A 5 "scope_roots" .lexibrary/config.yaml
   ```
   Running `lexi design update <file>` on a file that lives outside every
   declared root surfaces an explicit error — see
   [File reported as outside all configured scope_roots](#file-reported-as-outside-all-configured-scope_roots)
   below.

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

See [Concepts](concepts.md) for concept lifecycle management.

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

## Sweep Issues

### Sweep not detecting changes

**Symptoms:** `lexictl sweep --watch` runs periodic sweeps but reports no files changed, even though source files have been modified.

**Cause:**

- `sweep.sweep_skip_if_unchanged` is `true` (the default), and the sweep's change detection is not picking up your changes. This can happen if files were modified but their SHA-256 hashes happen to match (extremely rare), or if the files are excluded by ignore patterns.
- The sweep interval may be too long for your workflow.

**Fix:**

1. Run a one-shot sweep to verify changes are detected:
   ```bash
   lexictl sweep
   ```

2. If the one-shot sweep detects no changes, check that modified files are under at least one declared `scope_roots` entry and not excluded by ignore patterns.

3. To reduce the sweep interval for more responsive detection:
   ```yaml
   sweep:
     sweep_interval_seconds: 300    # Every 5 minutes instead of every hour
   ```

4. To force sweeps to always run (even when no changes are detected):
   ```yaml
   sweep:
     sweep_skip_if_unchanged: false
   ```

### File reported as outside all configured scope_roots

**Symptoms:** A CLI command such as `lexi design update <file>`,
`lexi lookup <file>`, `lexi impact <file>`, `lexictl update --scope <file>`,
or `bootstrap` exits non-zero with a message in the form:

```
<path> is outside all configured scope_roots: ['src/', 'baml_src/']
```

The declared-root list in the brackets matches whatever is in your current
`config.yaml`.

**Cause:** The target path does not resolve inside any of the directories
listed under `scope_roots:` in `.lexibrary/config.yaml`. Multi-root gating
uses first-match ownership: a file must live inside at least one declared
root or the command refuses to run.

**Fix:**

1. Confirm the path is spelled correctly and is relative to the project root.
2. Re-check your `scope_roots`:
   ```bash
   grep -A 5 "scope_roots" .lexibrary/config.yaml
   ```
3. Either move the file into an existing root or add a new root entry. For
   example, to extend coverage to a new `baml_src/` tree:
   ```yaml
   scope_roots:
     - path: src/
     - path: baml_src/
   ```
   Then re-run `lexictl update` so the new root is crawled. See
   [Configuration — scope_roots](configuration.md#scope_roots) for the rules
   on nesting, duplicates, and path traversal.

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
   - `scope-roots` instead of `scope_roots` (underscores, not hyphens)
   - A bare `scope_root:` scalar left over from pre-multi-root configs — this
     one does NOT fail silently; the loader raises `Unknown config key
     'scope_root'` with migration instructions. Rename to `scope_roots:` and
     restructure as a list of mappings.
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

## Symbol Graph Issues

### `lexi trace` reports "No symbol named X"

**Symptoms:** Running `lexi trace SomeSymbol` exits with code 1 and prints `No symbol named SomeSymbol` to stderr.

**Cause:** The symbol does not exist in `symbols.db`. Possible reasons:

- The file defining the symbol has not been indexed yet (new file, never updated).
- The symbol is in a file excluded by ignore patterns or outside every declared `scope_roots` entry.
- The name is misspelled or uses an unexpected casing.
- `symbols.enabled` is `false` in the config, so the symbol graph is not being built.

**Fix:**

1. Verify the symbol name is correct:
   ```bash
   lexi search --type symbol SomeSymbol
   ```
   This runs a fuzzy match and may surface the correct spelling.

2. If the symbol is new, refresh the file's symbol graph entry:
   ```bash
   lexi design update path/to/file.py
   ```

3. If the file has never been indexed, run a full update:
   ```bash
   lexictl update
   ```

4. Verify symbols are enabled:
   ```bash
   grep "enabled" .lexibrary/config.yaml
   ```

### Trace output shows unexpected unresolved callees

**Symptoms:** `lexi trace` shows many entries in "Unresolved callees (external or dynamic)" that you expect to be resolved (e.g., calls to other project functions).

**Cause:** The resolver could not map the call site to a definition. Common reasons:

- The called function is in a file that has not been indexed yet.
- The import path is dynamic or uses patterns the resolver does not handle (e.g., `importlib.import_module`).
- For TypeScript/JavaScript, the `tsconfig.json` path aliases may not match the actual import specifiers.
- The symbol graph is stale -- the file was edited since the last rebuild.

**Fix:**

1. Check for a stale-graph warning in the trace output. If present, refresh:
   ```bash
   lexi design update path/to/caller_file.py
   ```

2. For cross-file resolution issues, ensure both the caller and callee files are indexed:
   ```bash
   lexi design update path/to/callee_file.py
   lexi design update path/to/caller_file.py
   ```

3. For TypeScript path alias issues, verify `tsconfig.json` is at the project root and that `baseUrl` and `paths` are correct.

4. Run a full rebuild to resolve all cross-file references:
   ```bash
   lexictl update
   ```

### Symbol graph is out of sync after a rename

**Symptoms:** After renaming a function or class, `lexi trace` shows stale entries -- the old name still appears, or callers of the old name are not updated.

**Cause:** The symbol graph indexes each file independently. When you rename a symbol in file A, the graph updates file A, but files B and C that call the old name still have stale call records pointing at the old symbol.

**Fix:**

1. Refresh the renamed file:
   ```bash
   lexi design update path/to/renamed_file.py
   ```

2. Refresh all callers. Use `lexi impact` to find files that import the renamed file, then update each:
   ```bash
   lexi impact path/to/renamed_file.py --quiet | xargs -I{} lexi design update {}
   ```

3. Alternatively, run a full rebuild to catch all stale references:
   ```bash
   lexictl update
   ```

### `symbols.db` is corrupt or missing

**Symptoms:** Symbol graph commands (`lexi trace`, `lexi search --type symbol`) fail with SQLite errors, or the database file is absent.

**Cause:** The database was deleted, moved, or corrupted (e.g., by an interrupted write). Since `symbols.db` is gitignored and rebuilt from source, data loss is not permanent.

**Fix:**

1. Delete the corrupt database (if present) and rebuild:
   ```bash
   rm -f .lexibrary/symbols.db
   lexictl update
   ```

2. If the error persists, check file permissions on the `.lexibrary/` directory.

3. If you see a schema version mismatch error, the database was built by a different version of Lexibrary. The rebuild will recreate it with the current schema:
   ```bash
   rm -f .lexibrary/symbols.db
   lexictl update
   ```

See [Symbol Graph](symbol-graph.md) for details on the schema, extraction, and resolution pipeline.

## Related Documentation

- [Configuration](configuration.md) -- Full `config.yaml` reference
- [CLI Reference](cli-reference.md) -- Complete CLI command reference with exit codes
- [Design Files](design-files.md) -- How `lexictl update` works end-to-end
- [Validation](validation.md) -- The 13 validation checks and their meanings
- [Ignore Patterns](ignore-patterns.md) -- Pattern sources, precedence, and debugging
- [Link Graph](link-graph.md) -- The SQLite index, rebuilding, and graceful degradation
- [Symbol Graph](symbol-graph.md) -- The symbol-level SQLite index and query commands
- [CI Integration](ci-integration.md) -- Git hooks, periodic sweeps, and CI pipeline recipes
- [Project Setup](project-setup.md) -- Init wizard, re-init guard, changing settings
- [Upgrading](upgrading.md) -- Version upgrade guide
