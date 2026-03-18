# Configuration

Lexibrary is configured via `.lexibrary/config.yaml`, created during `lexictl init`. This document is a complete reference for every configuration key, organized to mirror the YAML nesting structure.

All configuration models use `extra="ignore"`, which means unknown keys are silently ignored. This provides forward compatibility -- upgrading Lexibrary will never break your existing config even if new keys are added.

To change settings after initialization, edit `.lexibrary/config.yaml` directly and (optionally) run `lexictl setup --update` to regenerate agent rules.

## Top-level Keys

### `scope_root`

- **Type:** string
- **Default:** `"."`
- **Description:** Only files under this path (relative to the project root) get design files. Set to `"src/"` to restrict design file generation to your source directory.

```yaml
scope_root: "src/"
```

### `project_name`

- **Type:** string
- **Default:** `""` (empty -- set during `lexictl init`)
- **Description:** The name of the project. Detected from `pyproject.toml`, `package.json`, or the directory name during initialization. Used in generated artifacts like `TOPOLOGY.md`.

```yaml
project_name: "my-project"
```

### `agent_environment`

- **Type:** list of strings
- **Default:** `[]` (empty list)
- **Description:** Agent environments configured during `lexictl init`. Each environment name corresponds to a set of agent rule files that Lexibrary generates. Supported values: `claude`, `cursor`.

```yaml
agent_environment:
  - claude
  - cursor
```

## `iwh` Section

Configuration for the I Was Here (IWH) agent trace system.

### `iwh.enabled`

- **Type:** boolean
- **Default:** `true`
- **Description:** Enable IWH agent trace files. When enabled, agents can create `.iwh` signal files to leave context for subsequent agents. Recommended for multi-agent workflows.

```yaml
iwh:
  enabled: true
```

## `llm` Section

LLM provider settings for design file generation.

### `llm.provider`

- **Type:** string
- **Default:** `"anthropic"`
- **Description:** LLM provider to use. Supported values: `anthropic`, `openai`, `google`, `ollama`.

### `llm.model`

- **Type:** string
- **Default:** `"claude-sonnet-4-6"`
- **Description:** Model identifier passed to the LLM provider. Must be a valid model name for the selected provider.

### `llm.api_key_env`

- **Type:** string
- **Default:** `"ANTHROPIC_API_KEY"`
- **Description:** Name of the environment variable holding the API key. Lexibrary reads this environment variable at runtime -- the actual key is never stored in configuration.

### `llm.max_retries`

- **Type:** integer
- **Default:** `3`
- **Description:** Number of retry attempts when an LLM API call fails (e.g., rate limiting, transient errors).

### `llm.timeout`

- **Type:** integer
- **Default:** `60`
- **Description:** Request timeout in seconds for LLM API calls.

```yaml
llm:
  provider: anthropic
  model: claude-sonnet-4-6
  api_key_env: ANTHROPIC_API_KEY
  max_retries: 3
  timeout: 60
```

## `token_budgets` Section

Per-artifact token budget targets. These are validation targets for generated content -- the validator warns when generated artifacts exceed these sizes. They do not hard-limit generation; they guide the LLM prompts and flag oversized output.

### `token_budgets.design_file_tokens`

- **Type:** integer
- **Default:** `400`
- **Description:** Target token budget for a full design file.

### `token_budgets.design_file_abridged_tokens`

- **Type:** integer
- **Default:** `100`
- **Description:** Target token budget for an abridged design file summary.

### `token_budgets.aindex_tokens`

- **Type:** integer
- **Default:** `200`
- **Description:** Target token budget for an `.aindex` routing table.

### `token_budgets.concept_file_tokens`

- **Type:** integer
- **Default:** `400`
- **Description:** Target token budget for a concept file.

```yaml
token_budgets:
  design_file_tokens: 400
  design_file_abridged_tokens: 100
  aindex_tokens: 200
  concept_file_tokens: 400
```

## `mapping` Section

Mapping strategy configuration. This controls how source files map to design files.

### `mapping.strategies`

- **Type:** list of objects
- **Default:** `[]` (empty list -- uses default 1:1 mapping)
- **Description:** List of mapping strategy definitions using glob patterns. When empty, each source file maps to exactly one design file. Custom strategies can group multiple source files into a single design file or apply different generation parameters.

```yaml
mapping:
  strategies: []
```

## `ignore` Section

Configuration for the file discovery ignore system. Lexibrary combines multiple sources of ignore patterns during file discovery.

### `ignore.use_gitignore`

- **Type:** boolean
- **Default:** `true`
- **Description:** When `true`, Lexibrary respects `.gitignore` files found in the project tree. This prevents indexing of files that are already excluded from version control.

### `ignore.additional_patterns`

- **Type:** list of strings
- **Default:** (see below)
- **Description:** Additional glob patterns to exclude from file discovery. Uses pathspec gitignore-style pattern syntax. These patterns are applied on top of any `.gitignore` rules.

Default patterns:

```yaml
ignore:
  use_gitignore: true
  additional_patterns:
    - .lexibrary/TOPOLOGY.md
    - ".lexibrary/**/*.md"
    - ".lexibrary/**/.aindex"
    - node_modules/
    - __pycache__/
    - .git/
    - .venv/
    - venv/
    - "*.lock"
```

See [Ignore Patterns](ignore-patterns.md) for the complete ignore system documentation including `.lexignore` files and pattern precedence.

## `sweep` Section

Configuration for the background sweep system.

### `sweep.sweep_interval_seconds`

- **Type:** integer
- **Default:** `3600`
- **Description:** Interval in seconds between full library sweeps when using `lexictl sweep --watch`. Default is 1 hour.

### `sweep.sweep_skip_if_unchanged`

- **Type:** boolean
- **Default:** `true`
- **Description:** When `true`, periodic sweeps are skipped if no files have changed since the last run. Saves LLM costs when the codebase is idle.

### `sweep.log_level`

- **Type:** string
- **Default:** `"info"`
- **Description:** Log level for sweep output. Valid values: `debug`, `info`, `warning`, `error`.

```yaml
sweep:
  sweep_interval_seconds: 3600
  sweep_skip_if_unchanged: true
  log_level: info
```

## `crawl` Section

Configuration for file discovery and crawling behavior.

### `crawl.max_file_size_kb`

- **Type:** integer
- **Default:** `512`
- **Description:** Files larger than this size (in kilobytes) are skipped during `lexictl update`. Prevents sending very large files to the LLM.

### `crawl.binary_extensions`

- **Type:** list of strings
- **Default:** (see below)
- **Description:** File extensions treated as binary. Files with these extensions are always skipped during indexing.

Default binary extensions include:

- **Images:** `.png`, `.jpg`, `.jpeg`, `.gif`, `.ico`, `.svg`, `.webp`
- **Audio/video:** `.mp3`, `.mp4`, `.wav`, `.ogg`, `.webm`
- **Fonts:** `.woff`, `.woff2`, `.ttf`, `.eot`
- **Archives:** `.zip`, `.tar`, `.gz`, `.bz2`, `.7z`, `.rar`
- **Documents:** `.pdf`, `.doc`, `.docx`, `.xls`, `.xlsx`
- **Executables/compiled:** `.exe`, `.dll`, `.so`, `.dylib`, `.pyc`, `.pyo`, `.class`, `.o`, `.obj`
- **Database:** `.sqlite`, `.db`

```yaml
crawl:
  max_file_size_kb: 512
  binary_extensions:
    - .png
    - .jpg
    # ... (full list in default config)
```

## `ast` Section

Configuration for AST-based interface extraction. When enabled, Lexibrary uses tree-sitter to parse source files and extract public interface skeletons (function signatures, class definitions, exports) that are included in design files.

### `ast.enabled`

- **Type:** boolean
- **Default:** `true`
- **Description:** Enable interface skeleton extraction from source files. Requires the `ast` optional dependency group (`pip install -e ".[ast]"`).

### `ast.languages`

- **Type:** list of strings
- **Default:** `["python", "typescript", "javascript"]`
- **Description:** Programming languages to extract interfaces from. Only files in these languages will have interface skeletons in their design files.

```yaml
ast:
  enabled: true
  languages:
    - python
    - typescript
    - javascript
```

## Full Default Configuration

For reference, here is the complete default configuration as generated by `lexictl init`:

```yaml
scope_root: "."
project_name: ""
agent_environment: []

iwh:
  enabled: true

llm:
  provider: anthropic
  model: claude-sonnet-4-6
  api_key_env: ANTHROPIC_API_KEY
  max_retries: 3
  timeout: 60

token_budgets:
  design_file_tokens: 400
  design_file_abridged_tokens: 100
  aindex_tokens: 200
  concept_file_tokens: 400

mapping:
  strategies: []

ignore:
  use_gitignore: true
  additional_patterns:
    - .lexibrary/TOPOLOGY.md
    - ".lexibrary/**/*.md"
    - ".lexibrary/**/.aindex"
    - node_modules/
    - __pycache__/
    - .git/
    - .venv/
    - venv/
    - "*.lock"

sweep:
  sweep_interval_seconds: 3600
  sweep_skip_if_unchanged: true
  log_level: info

crawl:
  max_file_size_kb: 512
  binary_extensions:
    - .png
    - .jpg
    - .jpeg
    - .gif
    - .ico
    - .svg
    - .webp
    - .mp3
    - .mp4
    - .wav
    - .ogg
    - .webm
    - .woff
    - .woff2
    - .ttf
    - .eot
    - .zip
    - .tar
    - .gz
    - .bz2
    - .7z
    - .rar
    - .pdf
    - .doc
    - .docx
    - .xls
    - .xlsx
    - .exe
    - .dll
    - .so
    - .dylib
    - .pyc
    - .pyo
    - .class
    - .o
    - .obj
    - .sqlite
    - .db

ast:
  enabled: true
  languages:
    - python
    - typescript
    - javascript
```
