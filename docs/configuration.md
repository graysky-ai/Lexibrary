# Configuration

Lexibrary is configured via `.lexibrary/config.yaml`, created during `lexictl init`. This document is a complete reference for every configuration key, organized to mirror the YAML nesting structure.

All configuration models use `extra="ignore"`, which means unknown keys are silently ignored. This provides forward compatibility -- upgrading Lexibrary will never break your existing config even if new keys are added.

To change settings after initialization, edit `.lexibrary/config.yaml` directly and (optionally) run `lexictl setup --update` to regenerate agent rules.

## Top-level Keys

### `scope_roots`

- **Type:** list of objects (`ScopeRoot` entries). Each entry has:
  - `path` (string, required) — directory to index, relative to the project root.
  - `name` (string, optional) — friendly label used in topology sections and
    diagnostics. Defaults to the `path` value when omitted.
  - `origin` (string, reserved) — always `"local"` today. Reserved for future
    multi-repo / multi-drive expansion; set a value here only if you know
    exactly what you are doing.
- **Default:** `[{ path: "." }]` (a single entry covering the whole project).
- **Description:** Every listed directory is crawled independently by
  `lexictl update`, producing its own subtree under `.lexibrary/designs/`,
  its own `.aindex` routing tables, and its own section in
  `.lexibrary/TOPOLOGY.md`. A file is in scope only if it lives inside at
  least one declared root. See
  [Library Structure](library-structure.md#design-files-mirror-tree) for the
  on-disk layout and [How It Works](how-it-works.md#1-source-file-discovery)
  for the crawling story.

Single-root projects still use the list shape — the scaffolder never emits a
bare `scope_root:` scalar:

```yaml
scope_roots:
  - path: src/
```

Multi-root example (this repo, for instance):

```yaml
scope_roots:
  - path: src/
  - path: baml_src/
```

**Validation rules** (enforced at config load):

- Every `path` must resolve inside the project root; `../escape` is rejected.
- Roots cannot nest (no declared root may be an ancestor of another). A config
  with both `.` and `src/` raises a config-validation error naming both paths.
- Duplicate entries are rejected; two `- path: src/` lines surface an error.
- Missing-on-disk roots do **not** fail validation; they surface a warning at
  bootstrap/update time and the crawl continues against the remaining roots.

**Legacy key:** Loading a config with a top-level `scope_root:` scalar raises
a Pydantic validation error pointing at `scope_roots` with migration
instructions. There is no silent coercion; rename the key explicitly.

**Per-root overrides are deliberately minimal today.** `path`, `name`, and
`origin` are the only recognised fields. This surface will grow (per-root
`ignore`, per-root `binary_extensions`, alternative origins for remote or
mounted roots) as demand warrants, but the schema is stable for the current
release.

**Adding a root later:** edit `config.yaml` by hand to append another entry
under `scope_roots:` and re-run `lexictl update`. A dedicated
`lexictl init --add-root <dir>` command is a planned follow-up — until it
ships, the manual edit is the supported path.

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

## `concepts` Section

Configuration for the concept wiki system.

### `concepts.lookup_display_limit`

- **Type:** integer
- **Default:** `10`
- **Description:** Maximum number of related concepts shown in `lexi lookup` output for a file.

### `concepts.deprecation_confirm`

- **Type:** string
- **Default:** `"human"`
- **Description:** Who must confirm concept deprecation. `"human"` requires interactive confirmation; `"maintainer"` allows maintainer-level tools to proceed without prompting.

### `concepts.curator_deprecation_confirm`

- **Type:** boolean
- **Default:** `false`
- **Description:** Whether the curator subsystem requires confirmation before deprecating concepts. When `false`, the curator can deprecate concepts autonomously (subject to its autonomy level).

```yaml
concepts:
  lookup_display_limit: 10
  deprecation_confirm: human
  curator_deprecation_confirm: false
```

## `conventions` Section

Configuration for the convention system.

### `conventions.lookup_display_limit`

- **Type:** integer
- **Default:** `5`
- **Description:** Maximum number of conventions shown in `lexi lookup` output for a file. Conventions are sorted by scope specificity and priority before truncation.

### `conventions.deprecation_confirm`

- **Type:** string
- **Default:** `"human"`
- **Description:** Who must confirm convention deprecation. `"human"` requires interactive confirmation; `"maintainer"` allows maintainer-level tools to proceed without prompting.

### `conventions.curator_deprecation_confirm`

- **Type:** boolean
- **Default:** `false`
- **Description:** Whether the curator subsystem requires confirmation before deprecating conventions. When `false`, the curator can deprecate conventions autonomously (subject to its autonomy level).

```yaml
conventions:
  lookup_display_limit: 5
  deprecation_confirm: human
  curator_deprecation_confirm: false
```

## `convention_declarations` Section

User-declared conventions seeded from configuration. These declarations are materialized into `.lexibrary/conventions/` files by the build pipeline with `source: config` and `status: active`.

Each entry in the list has these fields:

### Entry fields

- **`body`** (string, required): Convention body text. The first paragraph becomes the convention's rule.
- **`scope`** (string, default: `"project"`): Convention scope -- `"project"` for repo-wide, or a directory path like `"src/auth"`.
- **`tags`** (list of strings, default: `[]`): Categorization tags.

```yaml
convention_declarations:
  - body: "Use `from __future__ import annotations` in every module"
    scope: project
    tags: [python, imports]
  - body: "pathspec pattern name must be 'gitignore'"
    scope: src/lexibrary/ignore
    tags: [pathspec]
```

See [Conventions](conventions.md) for full documentation on the convention system.

## `playbooks` Section

Configuration for the playbook system.

### `playbooks.lookup_display_limit`

- **Type:** integer
- **Default:** `5`
- **Description:** Maximum number of playbooks shown in `lexi lookup` output when trigger-file patterns match the file being looked up.

### `playbooks.staleness_commits`

- **Type:** integer
- **Default:** `100`
- **Description:** Number of commits after which an unverified playbook is considered stale. Use `lexi playbook verify <slug>` to reset the counter.

### `playbooks.staleness_days`

- **Type:** integer
- **Default:** `180`
- **Description:** Number of days after which an unverified playbook is considered stale, based on the `last_verified` frontmatter field.

```yaml
playbooks:
  lookup_display_limit: 5
  staleness_commits: 100
  staleness_days: 180
```

See [Playbooks](playbooks.md) for full documentation on the playbook system.

## `stack` Section

Configuration for the Stack Q&A post system.

### `stack.staleness_confirm`

- **Type:** string
- **Default:** `"human"`
- **Description:** Who must confirm when marking a Stack post as stale. `"human"` requires interactive confirmation; `"maintainer"` allows maintainer-level tools to proceed without prompting.

### `stack.staleness_ttl_commits`

- **Type:** integer
- **Default:** `200`
- **Description:** Number of commits after which a Stack post is considered potentially stale. This is the standard TTL used for most posts.

### `stack.staleness_ttl_short_commits`

- **Type:** integer
- **Default:** `100`
- **Description:** Shortened staleness TTL in commits, used for Stack posts that are flagged for shorter review cycles.

### `stack.lookup_display_limit`

- **Type:** integer
- **Default:** `3`
- **Description:** Maximum number of Stack posts shown in `lexi lookup` output for a file.

```yaml
stack:
  staleness_confirm: human
  staleness_ttl_commits: 200
  staleness_ttl_short_commits: 100
  lookup_display_limit: 3
```

## `deprecation` Section

Global deprecation lifecycle configuration that applies across all artifact types.

### `deprecation.ttl_commits`

- **Type:** integer
- **Default:** `50`
- **Description:** Number of commits a deprecated artifact remains before it is eligible for hard deletion. Provides a grace period during which deprecated artifacts can be un-deprecated if needed.

### `deprecation.comment_warning_threshold`

- **Type:** integer
- **Default:** `10`
- **Description:** Number of remaining commits before TTL expiry at which a warning is surfaced, alerting that the deprecated artifact will soon be eligible for deletion.

```yaml
deprecation:
  ttl_commits: 50
  comment_warning_threshold: 10
```

## `topology` Section

Configuration for topology generation (`TOPOLOGY.md`).

### `topology.detail_dirs`

- **Type:** list of strings
- **Default:** `[]` (empty list)
- **Description:** Directory paths that receive expanded detail in the generated `TOPOLOGY.md` file. When empty, all directories receive the same level of detail. When specified, only the listed directories (and their children) get expanded file-level descriptions in the topology output.

```yaml
topology:
  detail_dirs:
    - src/lexibrary/cli
    - src/lexibrary/services
```

## `iwh` Section

Configuration for the I Was Here (IWH) agent trace system.

### `iwh.enabled`

- **Type:** boolean
- **Default:** `true`
- **Description:** Enable IWH agent trace files. When enabled, agents can create `.iwh` signal files to leave context for subsequent agents. Recommended for multi-agent workflows.

### `iwh.ttl_hours`

- **Type:** integer
- **Default:** `72`
- **Description:** Time-to-live in hours for IWH signals. Signals older than this are eligible for cleanup.

```yaml
iwh:
  enabled: true
  ttl_hours: 72
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

### `llm.api_key_source`

- **Type:** string
- **Default:** `"env"`
- **Description:** Source of the API key. Currently only `"env"` (environment variable) is supported.

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
  api_key_source: env
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

### `token_budgets.convention_file_tokens`

- **Type:** integer
- **Default:** `500`
- **Description:** Target token budget for a convention file.

### `token_budgets.lookup_total_tokens`

- **Type:** integer
- **Default:** `1200`
- **Description:** Maximum total token budget for all artifacts returned by a single `lexi lookup` call.

### `token_budgets.playbook_tokens`

- **Type:** integer
- **Default:** `500`
- **Description:** Target token budget for a playbook file.

### `token_budgets.summarize_max_tokens`

- **Type:** integer
- **Default:** `200`
- **Description:** Maximum tokens for LLM-generated summary text.

### `token_budgets.archivist_max_tokens`

- **Type:** integer
- **Default:** `5000`
- **Description:** Maximum tokens sent to the archivist LLM prompt for design file generation.

```yaml
token_budgets:
  design_file_tokens: 400
  design_file_abridged_tokens: 100
  aindex_tokens: 200
  concept_file_tokens: 400
  convention_file_tokens: 500
  lookup_total_tokens: 1200
  playbook_tokens: 500
  summarize_max_tokens: 200
  archivist_max_tokens: 5000
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

### `symbols`

| Key | Type | Default | Description |
|---|---|---|---|
| `symbols.enabled` | bool | `true` | Enables the `.lexibrary/symbols.db` pipeline that indexes function, class, and enum-level relationships. |
| `symbols.include_enums` | bool | `true` | When `true`, the archivist feeds extracted enums and constants into the design-file prompt so the generated prose can name them explicitly. Turned on by default -- cost is minimal. |
| `symbols.include_call_paths` | bool | `false` | Opt-in. When `true`, the archivist feeds call-path summaries (caller <- this <- callees) into the design-file prompt. Increases prompt size by roughly `call_path_depth x 50` tokens per file. |
| `symbols.include_data_flows` | bool | `false` | Opt-in. When `true`, the archivist feeds branch-parameter context into the design-file prompt so the LLM can generate data flow notes. Gated on a deterministic AST signal: files without branching parameters never trigger the LLM call, keeping cost at zero for most files. |
| `symbols.call_path_depth` | int | `2` | How many hops to include in each direction when `include_call_paths` is enabled. Depth 1 = direct callers/callees only; depth 2 = adds the next ring out. |
| `symbols.max_enum_items` | int | `20` | Maximum number of enum/constant entries rendered in a single prompt block. Files with more entries are truncated with a trailing `... N more` marker so the LLM knows the list is incomplete. |
| `symbols.max_call_path_items` | int | `10` | Maximum number of call-path entries rendered in a single prompt block. Files with more functions/methods are truncated. |

```yaml
symbols:
  enabled: true
  include_enums: true
  include_call_paths: false
  include_data_flows: false
  call_path_depth: 2
  max_enum_items: 20
  max_call_path_items: 10
```

See [Symbol Graph](symbol-graph.md) for the full feature description, including the design-file enrichment pipeline and cost trade-offs for enabling `include_call_paths` and `include_data_flows`.

## `curator` Section

Configuration for the automated curator subsystem. The curator runs via `lexictl curate` and performs autonomous maintenance: detecting stale design files, checking consistency, managing deprecation workflows, and running migrations.

### `curator.autonomy`

- **Type:** string
- **Default:** `"auto_low"`
- **Description:** Controls how much the curator can do without human approval. Values:
  - `"auto_low"` -- automatically performs low-risk actions; proposes medium/high-risk actions for review
  - `"full"` -- performs all actions automatically regardless of risk level
  - `"propose"` -- proposes all actions for review without performing any automatically

### `curator.max_llm_calls_per_run`

- **Type:** integer
- **Default:** `50`
- **Minimum:** `1`
- **Description:** Maximum number of LLM API calls the curator is allowed to make in a single run. Prevents runaway costs during large maintenance operations.

### `curator.risk_overrides`

- **Type:** object (string keys, string values)
- **Default:** `{}` (empty)
- **Description:** Per-action risk level overrides. Keys are action names (e.g., `deprecate_concept`, `apply_migration_edits`); values are risk levels (`"low"`, `"medium"`, `"high"`). Unknown action keys produce a warning but are accepted.

Known action keys include: `deprecate_concept`, `deprecate_convention`, `deprecate_playbook`, `deprecate_design_file`, `hard_delete_concept_past_ttl`, `hard_delete_convention_past_ttl`, `hard_delete_playbook_past_ttl`, `delete_comments_sidecar`, `apply_migration_edits`, `concept_draft_to_active`, `convention_draft_to_active`, `playbook_draft_to_active`, `stack_post_transition`.

### `curator.deprecation`

Deprecation-specific settings for the curator.

#### `curator.deprecation.ttl_commits`

- **Type:** integer
- **Default:** `50`
- **Minimum:** `1`
- **Description:** Number of commits before a deprecated artifact is eligible for hard deletion by the curator.

### `curator.budget`

Budget Trimmer sub-agent settings.

#### `curator.budget.token_limits.design_file`

- **Type:** integer
- **Default:** `4000`
- **Minimum:** `100`
- **Description:** Token limit for design files during budget trimming.

#### `curator.budget.token_limits.start_here`

- **Type:** integer
- **Default:** `3000`
- **Minimum:** `100`
- **Description:** Token limit for start-here documents during budget trimming.

#### `curator.budget.token_limits.handoff`

- **Type:** integer
- **Default:** `2000`
- **Minimum:** `100`
- **Description:** Token limit for handoff documents during budget trimming.

### `curator.auditing`

Comment Auditing sub-agent settings.

#### `curator.auditing.quality_threshold`

- **Type:** float
- **Default:** `0.7`
- **Range:** `0.0` to `1.0`
- **Description:** Minimum quality score for design file comments. Comments below this threshold are flagged for review.

### `curator.reactive`

Reactive hook settings for post-edit, post-bead-close, and validation-failure triggers.

#### `curator.reactive.enabled`

- **Type:** boolean
- **Default:** `false`
- **Description:** Enable reactive curator hooks. When enabled, the curator can respond to file edits, bead closures, and validation failures in real time.

#### `curator.reactive.post_edit`

- **Type:** boolean
- **Default:** `true`
- **Description:** Enable the post-edit reactive hook. Only takes effect when `curator.reactive.enabled` is `true`.

#### `curator.reactive.post_bead_close`

- **Type:** boolean
- **Default:** `true`
- **Description:** Enable the post-bead-close reactive hook. Only takes effect when `curator.reactive.enabled` is `true`.

#### `curator.reactive.validation_failure`

- **Type:** boolean
- **Default:** `true`
- **Description:** Enable the validation-failure reactive hook. Only takes effect when `curator.reactive.enabled` is `true`.

#### `curator.reactive.severity_threshold`

- **Type:** string
- **Default:** `"error"`
- **Description:** Minimum severity level that triggers the validation-failure hook. Values: `"critical"`, `"error"`, `"warning"`.

```yaml
curator:
  autonomy: auto_low
  max_llm_calls_per_run: 50
  risk_overrides:
    deprecate_concept: low
  deprecation:
    ttl_commits: 50
  budget:
    token_limits:
      design_file: 4000
      start_here: 3000
      handoff: 2000
  auditing:
    quality_threshold: 0.7
  reactive:
    enabled: false
    post_edit: true
    post_bead_close: true
    validation_failure: true
    severity_threshold: error
```

## Full Default Configuration

For reference, here is the complete default configuration as generated by `lexictl init`:

```yaml
scope_roots:
  - path: .
project_name: ""
agent_environment: []

concepts:
  lookup_display_limit: 10
  deprecation_confirm: human
  curator_deprecation_confirm: false

conventions:
  lookup_display_limit: 5
  deprecation_confirm: human
  curator_deprecation_confirm: false

convention_declarations: []

playbooks:
  lookup_display_limit: 5
  staleness_commits: 100
  staleness_days: 180

stack:
  staleness_confirm: human
  staleness_ttl_commits: 200
  staleness_ttl_short_commits: 100
  lookup_display_limit: 3

deprecation:
  ttl_commits: 50
  comment_warning_threshold: 10

topology:
  detail_dirs: []

iwh:
  enabled: true
  ttl_hours: 72

llm:
  provider: anthropic
  model: claude-sonnet-4-6
  api_key_env: ANTHROPIC_API_KEY
  api_key_source: env
  max_retries: 3
  timeout: 60

token_budgets:
  design_file_tokens: 400
  design_file_abridged_tokens: 100
  aindex_tokens: 200
  concept_file_tokens: 400
  convention_file_tokens: 500
  lookup_total_tokens: 1200
  playbook_tokens: 500
  summarize_max_tokens: 200
  archivist_max_tokens: 5000

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

symbols:
  enabled: true
  include_enums: true
  include_call_paths: false
  include_data_flows: false
  call_path_depth: 2
  max_enum_items: 20
  max_call_path_items: 10

curator:
  autonomy: auto_low
  max_llm_calls_per_run: 50
  risk_overrides: {}
  deprecation:
    ttl_commits: 50
  budget:
    token_limits:
      design_file: 4000
      start_here: 3000
      handoff: 2000
  auditing:
    quality_threshold: 0.7
  reactive:
    enabled: false
    post_edit: true
    post_bead_close: true
    validation_failure: true
    severity_threshold: error
```
