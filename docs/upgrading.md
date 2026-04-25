# Upgrading

This guide covers how to upgrade Lexibrary to a new version, what to expect during the upgrade, and when additional steps are needed after updating the package.

## General Upgrade Process

1. **Update the package:**

   ```bash
   # With uv
   uv sync

   # With pip
   pip install -e .
   ```

2. **Check release notes** for any breaking changes, new features, or new config keys.

3. **Run `lexictl upgrade`** to bring the project's Lexibrary surface up to current standards. This persists any pending config-key migrations to disk, stamps the new Lexibrary version into `config.yaml`, backfills `.gitignore` patterns for any newly introduced generated artifacts, regenerates agent rule files, and refreshes git hooks. Every step is idempotent — `[ok]` means the project was already current for that step.

   ```bash
   lexictl upgrade
   ```

4. **Run a full update** if the release notes indicate changes to design file format, new validation checks, or link graph schema changes:

   ```bash
   lexictl update
   ```

5. **Validate the library** to confirm everything is consistent:

   ```bash
   lexictl validate
   ```

## Config Schema Evolution

Lexibrary's configuration system is designed for seamless upgrades. All Pydantic config models use `extra="ignore"`, which provides two guarantees:

### New keys have defaults

When a new version of Lexibrary introduces new config keys, they automatically use their default values if not present in your `config.yaml`. You do not need to add them manually. For example, if a future version adds a new `llm.max_concurrent` key with a default of `5`, your existing config will work without changes -- the new key will default to `5`.

### Unknown keys are ignored

If your `config.yaml` contains keys that a version of Lexibrary does not recognize (e.g., you downgrade to an older version, or a key was renamed), those keys are silently ignored. Your config will never cause a parse error due to unrecognized keys.

### When to update config manually

You only need to update your `config.yaml` when you want to customize the behavior of a new feature. Check release notes for new config keys and their defaults. If the defaults work for your project, no config changes are needed.

To see the complete default configuration for comparison:

```bash
# View the current full default config reference
cat docs/configuration.md
```

Or compare your config against the documented defaults in [Configuration -- Full Default Configuration](configuration.md#full-default-configuration).

## When to Re-run `lexictl update`

A full `lexictl update` regenerates design files and rebuilds the link graph. You should re-run it after upgrading when:

### Design file format changes

If a new version changes the design file format (e.g., adds new sections, modifies frontmatter fields, or changes the metadata footer structure), a full update regenerates all design files in the new format. The update summary will show how many files were regenerated:

```
Update summary:
  Files scanned:       42
  Files unchanged:     0     # All files regenerated due to format change
  Files created:       0
  Files updated:       42    # All files got new design files
```

Note: Files where the design file body was modified since last generation are classified as `AGENT_UPDATED` -- their footer hashes are refreshed but the LLM is not called, preserving the modifications. See [Design Files](design-files.md#how-manual-edits-are-detected) for details.

### New validation checks

If a new version adds validation checks, run `lexictl validate` after upgrading to see if any existing artifacts trigger the new checks. You do not need to run `lexictl update` for this -- validation reads existing artifacts without modifying them:

```bash
lexictl validate
```

### BAML prompt changes

If the LLM prompts (in `baml_src/`) have been updated to produce better design files, running `lexictl update` will regenerate files using the new prompts. Since Lexibrary uses SHA-256 hash comparison for change detection, and the prompts themselves are not part of the hash, you may need to delete existing design files to force regeneration:

```bash
# Force full regeneration by clearing existing design files
find .lexibrary/ -name "*.md" -not -name "START_HERE.md" -not -name "config.yaml" -not -path "*/concepts/*" -not -path "*/stack/*" -delete
lexictl update
```

In most cases, simply running `lexictl update` is sufficient -- files that have changed since the last update will get the new prompts automatically.

## Link Graph Rebuilding

The link graph SQLite database at `.lexibrary/index.db` stores a schema version in its `meta` table. When Lexibrary opens the index, it checks this version against the expected version.

### Automatic schema recreation

If the schema version does not match (e.g., after an upgrade that changes the schema), the schema is automatically recreated during the next full `lexictl update`. You do not need to take any manual action -- just run:

```bash
lexictl update
```

### Manual rebuild

If you encounter link graph issues after an upgrade, force a clean rebuild by deleting the database:

```bash
rm .lexibrary/index.db
lexictl update
```

The link graph rebuild does not make LLM calls -- it reads existing design files, concepts, Stack posts, and `.aindex` files from disk. It is fast and safe to run.

### Graceful degradation

If the link graph is absent or has a schema mismatch, all queries degrade gracefully:

- `lexi lookup` falls back to file scanning for dependents (slower but functional).
- `lexi search` with `--tag` returns empty results from the link graph but still searches artifact files directly.
- Validation checks that query the link graph (`bidirectional_deps`, `dangling_links`, `orphan_artifacts`) return no issues.

The link graph is always optional. Lexibrary works without it -- the index just makes certain queries faster.

See [Link Graph](link-graph.md) for full details on the index, its schema, and rebuild procedures.

## Agent Rule Updates

`lexictl upgrade`'s `agent-rules` step regenerates rule files for every environment listed in `agent_environment:` (e.g., `CLAUDE.md`, `.cursor/rules`, `AGENTS.md`). Rule content may change between versions to reflect new commands, updated workflows, or new features.

To add a new agent environment, edit `agent_environment:` in `.lexibrary/config.yaml` and re-run `lexictl upgrade`. The command reads from config — there is no per-run override flag.

## Git Hook Updates

The git post-commit hook installed by `lexictl upgrade`'s `git-hooks` step calls `lexictl update --changed-only`. Since the hook calls the `lexictl` binary directly, it automatically uses the upgraded version after a package update. No hook reinstallation is needed.

If hook behavior has changed in a new version (check release notes), re-run:

```bash
lexictl upgrade
```

Hook installation is idempotent — the underlying installers detect their hook marker and short-circuit when already present.

## Downgrading

Downgrading Lexibrary to an older version is safe:

- **Config:** Unknown keys from the newer version are silently ignored (`extra="ignore"`).
- **Design files:** Older versions can read design files generated by newer versions. Extra metadata fields are ignored.
- **Link graph:** If the schema version is newer than the downgraded version expects, the schema is recreated on the next full update. You may lose link graph data (but it is rebuilt from existing artifacts).

To downgrade:

```bash
# Check out the older version
git checkout v0.x.y

# Reinstall
uv sync

# Rebuild the link graph (if schema version changed)
rm .lexibrary/index.db
lexictl update
```

## Troubleshooting Upgrade Issues

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| YAML parse error in config | Config file was manually edited with syntax errors | See [Troubleshooting -- YAML parse errors](troubleshooting.md#yaml-parse-errors) |
| New config key has no effect | Key name is misspelled or at the wrong nesting level | Compare against [Configuration](configuration.md) reference |
| Link graph queries return empty | Schema version mismatch | Run `lexictl update` or delete `index.db` and rebuild |
| Agent rules outdated | Rule files were not regenerated after upgrade | Run `lexictl upgrade` |
| Design files look different | New version uses updated BAML prompts | Expected behavior -- new prompts produce improved output |

For other issues, see [Troubleshooting](troubleshooting.md).

## Related Documentation

- [Configuration](configuration.md) -- Full `config.yaml` reference with all keys and defaults
- [Link Graph](link-graph.md) -- Schema versioning, rebuilding, and graceful degradation
- [Design Files](design-files.md) -- How `lexictl update` detects and processes changes
- [Validation](validation.md) -- The 13 validation checks
- [CI Integration](ci-integration.md) -- Automated update and validation pipelines
- [Project Setup](project-setup.md) -- `lexictl upgrade` and agent rule generation
- [Troubleshooting](troubleshooting.md) -- Common issues and fixes
