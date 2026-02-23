# Project Setup

This guide is a detailed walkthrough of the `lexictl init` wizard, covering each of the 8 steps, how auto-detection works, non-interactive mode for CI, the re-init guard, and how to change settings after initialization.

For a quick-start overview, see [Getting Started](getting-started.md). For the complete CLI flag reference, see [lexictl Reference](lexictl-reference.md).

## The Init Wizard

Run `lexictl init` from the root directory of the project you want to index. The wizard walks you through 8 steps, detecting sensible defaults at each stage so you can accept them with Enter or override them.

```bash
cd /path/to/your/project
lexictl init
```

### Step 1: Project Name

```
Step 1/8: Project Name
  Detected: my-project (from pyproject.toml)
  Project name [my-project]:
```

**What it does:** Detects the project name automatically and lets you confirm or override it.

**Detection order:**

1. `pyproject.toml` -- Reads `[project].name` via `tomllib` (stdlib).
2. `package.json` -- Reads the `name` field.
3. Directory name -- Falls back to the name of the current directory.

**What it affects:** The `project_name` key in `config.yaml`. Used in generated artifacts like `START_HERE.md` to identify the project.

### Step 2: Scope Root

```
Step 2/8: Scope Root
  Detected directories: ['src/']
  Modify later in .lexibrary/config.yaml
  Scope root path [src/]:
```

**What it does:** Determines which directory tree to index. Only files under the scope root will receive design files.

**Detection:** Checks for common source directories (`src/`, `lib/`, `app/`) and suggests the first one found. If none exist, defaults to `.` (the entire project).

**What it affects:** The `scope_root` key in `config.yaml`. Files outside this path are ignored during `lexictl update`.

**Common values:**

| Value | Use case |
|-------|----------|
| `.` | Index the entire project (monorepo, small project) |
| `src/` | Python src layout, typical for libraries |
| `lib/` | Ruby, some Node.js projects |
| `app/` | Rails, some framework projects |

### Step 3: Agent Environment

```
Step 3/8: Agent Environment
  Detected: ['claude', 'cursor']
  Agent environments (comma-separated, e.g. claude, cursor) [claude, cursor]:
```

**What it does:** Identifies which AI agent tools you use so Lexibrary can generate the appropriate rule files for each.

**Detection:** Scans for environment-specific markers in the project root:

| Environment | Detected by | Rule files generated |
|-------------|-------------|---------------------|
| `claude` | `.claude/` directory or `CLAUDE.md` file | `CLAUDE.md` or `.claude/CLAUDE.md` |
| `cursor` | `.cursor/` directory | `.cursor/rules` |
| `codex` | `AGENTS.md` file | `AGENTS.md` |

If existing Lexibrary sections are found in rule files (detected by `<!-- lexibrary:` markers), the wizard notes this.

**What it affects:** The `agent_environment` list in `config.yaml`. Determines which rule files `lexictl setup --update` generates. You can specify multiple environments separated by commas.

**Entering none:** Leave the field empty and press Enter to skip agent rule generation. You can add environments later by editing `config.yaml` and running `lexictl setup --update`.

### Step 4: LLM Provider

```
Step 4/8: LLM Provider
  We never store, log, or transmit your API key.
  Detected: anthropic (env var: ANTHROPIC_API_KEY)
  Also available: openai
  Provider [anthropic]:
```

**What it does:** Selects the LLM provider used for generating design files.

**Detection:** Checks for the following environment variables in priority order:

| Provider | Environment Variable | Default Model |
|----------|---------------------|---------------|
| `anthropic` | `ANTHROPIC_API_KEY` | `claude-sonnet-4-6` |
| `openai` | `OPENAI_API_KEY` | `gpt-4o` |
| `google` | `GEMINI_API_KEY` | `gemini-2.0-flash` |
| `ollama` | `OLLAMA_HOST` | `llama3` |

All providers whose environment variable is set are listed. The first detected provider is the default. If no provider is detected, the wizard defaults to `anthropic` and reminds you to set an API key.

**What it affects:** Three keys in the `llm` section of `config.yaml`:

- `llm.provider` -- The selected provider name
- `llm.model` -- The default model for that provider
- `llm.api_key_env` -- The environment variable name holding the API key

**Security note:** Lexibrary never stores, logs, or transmits your API key. Only the name of the environment variable is stored in configuration. The key itself is read from the environment at runtime.

### Step 5: Ignore Patterns

```
Step 5/8: Ignore Patterns
  Project type: python
  Suggested patterns: ['**/migrations/', '**/__generated__/']
  Accept suggested patterns? [Y/n]:
```

**What it does:** Suggests additional ignore patterns based on your project type, beyond what `.gitignore` already covers.

**Detection:** Identifies the project type from marker files:

| Marker File | Project Type | Suggested Patterns |
|-------------|-------------|-------------------|
| `pyproject.toml` or `setup.py` | Python | `**/migrations/`, `**/__generated__/` |
| `package.json` + `tsconfig.json` | TypeScript | `dist/`, `build/`, `coverage/`, `.next/` |
| `package.json` (no tsconfig) | Node.js | `dist/`, `build/`, `coverage/`, `.next/` |
| `Cargo.toml` | Rust | `target/` |
| `go.mod` | Go | `vendor/` |

**What it affects:** Patterns are written to `.lexignore` in the project root. These patterns use `.gitignore` format and are applied during file discovery in `lexictl update`.

**Accepting vs. customizing:** Press Enter to accept the suggested patterns. Answer "n" to enter custom patterns as a comma-separated list, or leave empty for none.

### Step 6: Token Budgets

```
Step 6/8: Token Budgets
  Current defaults:
    start_here_tokens: 800
    handoff_tokens: 100
    design_file_tokens: 400
    design_file_abridged_tokens: 100
    aindex_tokens: 200
    concept_file_tokens: 400
  Customize token budgets? [y/N]:
```

**What it does:** Displays the default token budget targets for each artifact type and offers to customize them.

**What token budgets are:** These are validation targets, not hard limits. They guide the LLM prompts and the `token_budgets` validation check flags warnings when generated artifacts exceed the configured size. They help keep generated content concise and consistent.

**Default budgets:**

| Budget Key | Default | Controls |
|-----------|---------|----------|
| `start_here_tokens` | 800 | Target size for `START_HERE.md` |
| `handoff_tokens` | 100 | Target size for handoff summaries |
| `design_file_tokens` | 400 | Target size for full design files |
| `design_file_abridged_tokens` | 100 | Target size for abridged design file summaries |
| `aindex_tokens` | 200 | Target size for `.aindex` routing tables |
| `concept_file_tokens` | 400 | Target size for concept files |

**When to customize:** Most projects work well with the defaults. Consider increasing budgets for large, complex modules or decreasing them for smaller projects where context window space is at a premium.

**What it affects:** The `token_budgets` section in `config.yaml`. Only customized values (those that differ from defaults) are written to config.

### Step 7: I Was Here (IWH)

```
Step 7/8: I Was Here (IWH)
  IWH creates trace files so agents can see what previous agents did.
  Recommended for multi-agent workflows.
  Enable IWH? [Y/n]:
```

**What it does:** Enables or disables the I Was Here (IWH) trace file system.

**What IWH is:** When enabled, agents can create `.iwh` signal files in directories where they are working. These files contain context about incomplete work, next steps, and affected files. Subsequent agents check for `.iwh` files during their session start protocol and can pick up where the previous agent left off.

**What it affects:** The `iwh.enabled` key in `config.yaml`. When disabled, agents will not create or check for `.iwh` files.

**Recommendation:** Enable IWH for projects where multiple agents may work on the same codebase (which is most projects). Disable only if you work exclusively with a single agent and want to reduce file noise.

### Step 8: Summary and Confirmation

```
Step 8/8: Summary
+---------------------+---------------------------+
| Setting             | Value                     |
+---------------------+---------------------------+
| Project name        | my-project                |
| Scope root          | src/                      |
| Agent environments  | claude, cursor            |
| LLM provider        | anthropic                 |
| LLM model           | claude-sonnet-4-6         |
| API key env var     | ANTHROPIC_API_KEY         |
| Ignore patterns     | **/migrations/            |
| Token budgets       | defaults                  |
| IWH enabled         | True                      |
+---------------------+---------------------------+

  Create project with these settings? [Y/n]:
```

**What it does:** Displays all collected settings in a table and asks for final confirmation.

**Confirming:** Press Enter (or "y") to create the `.lexibrary/` skeleton with these settings.

**Cancelling:** Enter "n" to abort. No files are created.

## What Gets Created

After confirmation, `lexictl init` creates the following:

```
project-root/
  .lexibrary/
    config.yaml          # Project configuration (from wizard answers)
    START_HERE.md        # Placeholder (populated by lexictl update)
    concepts/
      .gitkeep           # Empty directory marker
    stack/
      .gitkeep           # Empty directory marker
  .lexignore             # Ignore patterns (from Step 5)
```

Additionally:

- `.gitignore` is updated to include `.lexibrary/index.db` (the link graph SQLite database).
- `.gitignore` is updated to include `.iwh` patterns (if IWH is enabled).

The skeleton is ready but empty. Run `lexictl update` to populate it with design files.

## Non-interactive Mode (--defaults)

For CI pipelines, Docker builds, or any non-interactive context, use `--defaults` to skip all prompts:

```bash
lexictl init --defaults
```

This mode:

- Accepts all auto-detected values without asking for confirmation.
- Uses the first detected LLM provider (or defaults to `anthropic`).
- Accepts all suggested ignore patterns for the detected project type.
- Uses default token budgets.
- Enables IWH.
- Auto-confirms at the summary step.

The wizard still runs all detection logic and prints each step's result, so the output is visible in CI logs for debugging.

### Non-TTY Detection

If `--defaults` is not specified and stdin is not a terminal (e.g., running in a CI pipeline), `lexictl init` exits with code 1 and prints:

```
Non-interactive environment detected. Use lexictl init --defaults to run without prompts.
```

This prevents the wizard from hanging on input prompts in automated environments.

## The Re-init Guard

If `.lexibrary/` already exists when you run `lexictl init`, the command refuses to proceed:

```
Project already initialised. Use lexictl setup --update to modify settings.
```

This prevents accidental re-initialization that would overwrite your configuration. To change settings after initialization, see the next section.

## Changing Settings After Init

### Editing config.yaml directly

The most common way to change settings is to edit `.lexibrary/config.yaml` directly. All configuration models use `extra="ignore"`, so unknown keys are silently ignored -- this means upgrading Lexibrary will never break your existing config.

```bash
# Open the config file in your editor
$EDITOR .lexibrary/config.yaml
```

After editing, your changes take effect the next time you run any `lexictl` command.

### Regenerating agent rules

If you changed the `agent_environment` list or want to refresh rule files:

```bash
lexictl setup --update
```

This regenerates agent rule files (e.g., `CLAUDE.md`, `.cursor/rules`) based on the current configuration.

### Updating for specific environments

To generate rules for environments not in your config (e.g., testing a new agent tool):

```bash
lexictl setup --update --env claude --env codex
```

The `--env` flag overrides the `agent_environment` config value for that run.

### Full re-generation

To regenerate all design files after significant config changes (such as changing `scope_root` or `llm.model`):

```bash
lexictl update
```

This re-scans all files and regenerates any that have changed or are missing design files.

## Next Steps

After initialization:

1. **Generate design files** -- Run `lexictl update` to crawl your project and generate the full library.
2. **Verify the output** -- Run `lexictl status` to see a health dashboard.
3. **Set up automation** -- Run `lexictl setup --hooks` to install the git post-commit hook.
4. **Configure your agents** -- Run `lexictl setup --update` to generate agent rule files.

See also:

- [Getting Started](getting-started.md) -- Quick-start walkthrough
- [Configuration](configuration.md) -- Full `config.yaml` reference
- [lexictl Reference](lexictl-reference.md) -- Complete CLI command reference
- [CI Integration](ci-integration.md) -- Recipes for automated setups
