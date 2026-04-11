# CLI Reference

Lexibrary provides two CLIs from the same package. `lexi` is the agent-facing CLI for lookups, search, and artifact management. `lexictl` is the operator-facing CLI for project initialization, design file generation, validation, and maintenance.

Run `lexi --help` or `lexictl --help` for a quick summary, or `<command> --help` for any specific command.

---

## lexi Commands

### Global Options

| Option | Description |
|--------|-------------|
| `--format [markdown\|json\|plain]` | Output format (default: `markdown`). |

---

### lookup

Look up context for a source file or directory before editing. For a file: shows the design summary, applicable conventions, and open issues. For a directory: shows the `.aindex` overview and child map.

```
lexi lookup <path> [--full]
```

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `path` | Yes | Relative or absolute path to a source file or directory. |

**Options:**

| Option | Description |
|--------|-------------|
| `--full` | Show full output (default is brief: description + conventions + issue count). |

**What it outputs (file mode):**

1. **Design file content** -- the full markdown design file including YAML frontmatter (source path, source_hash, generated timestamp, updated_by, wikilinks), summary, interface skeleton, and key details.
2. **Staleness warning** -- if the source file's SHA-256 hash does not match the hash stored in the design file frontmatter, a warning is printed suggesting `lexictl update`.
3. **Applicable conventions** -- conventions from `.aindex` files walked upward from the file's directory to the scope root. Each convention is shown with its originating directory.
4. **Key symbols** (`--full`) -- public functions, classes, and methods from the symbol graph with caller and callee counts. Omitted when `symbols.enabled` is `false` or `symbols.db` is missing.
5. **Class hierarchy** (`--full`) -- Phase 3 table listing every class defined in the file with its resolved bases, unresolved external bases (suffixed `*`), subclass count, method count, and starting line number. Omitted when the file defines no classes or `symbols.db` is missing. See the ["Class hierarchy in lookup output"](symbol-graph.md#class-hierarchy-in-lookup-output) section of the symbol graph docs for the full table format.
6. **Known Issues** -- Stack posts that reference this file, showing status, title, attempts summary, and vote count. Open posts shown first, then resolved. Maximum controlled by `stack.lookup_display_limit` (default: 3). Stale posts excluded.
7. **IWH signals** -- peek at IWH signals for the file's directory (read without consuming).
8. **Dependents** -- files that import this file (from the link graph, if available).
9. **Also referenced by** -- other inbound references: concept wikilinks, Stack post file refs, design file refs, convention concept refs.

**What it outputs (directory mode):**

1. **AIndex content** -- the directory's `.aindex` billboard and file listing.
2. **Applicable conventions** -- conventions scoped to this directory.
3. **IWH signals** -- peek at IWH signals for this directory.

**Token budget:** Controlled by `lookup_total_tokens` in `TokenBudgetConfig` (default: 1200). Sections are truncated in priority order: design > conventions > issues > IWH > links.

**Exit codes:**

| Code | Meaning |
|------|---------|
| 0 | Design file found and displayed |
| 1 | File is outside scope_root, or no design file exists |

**Examples:**

```bash
# Look up a specific source file
lexi lookup src/lexibrary/config/schema.py

# Look up with full output
lexi lookup src/lexibrary/config/schema.py --full

# Look up a directory
lexi lookup src/lexibrary/config/
```

---

### search

Search across concepts, conventions, design files, playbooks, Stack posts, and symbols in a single query. This is the unified cross-artifact search command.

```
lexi search [query] [--type TYPE] [--tag TAG] [--status STATUS] [--scope PATH]
    [--all] [--concept NAME] [--resolution-type TYPE] [--include-stale] [--limit N]
```

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `query` | No | Free-text search query (quote multi-word phrases). |

**Options:**

| Option | Description |
|--------|-------------|
| `--type` | Restrict to artifact type: `concept`, `convention`, `design`, `playbook`, `stack`, or `symbol`. |
| `--tag` | Filter by tag (repeatable, AND logic). Not supported with `--type symbol`. |
| `--status` | Filter by artifact status value. |
| `--scope` | Filter by file scope path. |
| `--all` | Include deprecated/hidden artifacts. |
| `--concept` | Stack-only: filter by referenced concept. |
| `--resolution-type` | Stack-only: filter by resolution type. |
| `--include-stale` | Stack-only: include stale posts. |
| `--limit` | Maximum results returned from full-text search (default: 20). |

At least one of `query`, `--tag`, `--scope`, or other filters must be provided.

**Output:** Results grouped by artifact type with a formatted table for each type that has matches. When the link graph index is available, search is accelerated with full-text search.

**Symbol search (`--type symbol`):** Dispatches directly to the symbol
graph (`.lexibrary/symbols.db`) and runs a `LIKE` match against
`symbols.name` and `symbols.qualified_name`. Results are rendered in a
`### Symbols` section with a `| Name | Type | Location |` table
(markdown mode), a `symbol  <qualified_name>  <file>:<line>` line (plain
mode), or a `{"type": "symbol", ...}` entry (JSON mode). Stack-only
filters (`--tag`, `--concept`, `--resolution-type`, `--include-stale`)
are rejected with exit code 1 when combined with `--type symbol` — use
`lexi trace` for resolved call graph queries. `--limit` still applies.

**Examples:**

```bash
# Search for a topic across all artifacts
lexi search "change detection"

# Search only Stack posts
lexi search --type stack "timeout"

# Search for a symbol by bare or partial name
lexi search --type symbol update_project

# Filter by tag
lexi search --tag validation

# Combine query, type, and filters
lexi search --type stack "timeout" --tag llm --status open

# Find resolved Stack posts about a concept
lexi search --type stack --concept change-detection --status resolved

# Find Stack workarounds
lexi search --type stack --resolution-type workaround
```

---

### impact

Show reverse dependents of a source file -- which files import it and would be affected by changes.

```
lexi impact <file> [--depth N] [--quiet]
```

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `file` | Yes | Source file to analyse for reverse dependents. |

**Options:**

| Option | Default | Description |
|--------|---------|-------------|
| `--depth` | 1 | Maximum traversal depth (1-3, clamped). Higher values follow transitive dependents. |
| `--quiet` | -- | Output paths only, one per line. Suitable for piping to other tools. |

**What it outputs:**

- A tree of files that depend on the given file, with design file descriptions for each.
- Warning indicators when a dependent has an open Stack post.
- With `--quiet`, outputs bare paths only (one per line, no decoration).

**Exit codes:**

| Code | Meaning |
|------|---------|
| 0 | Analysis completed (even if no dependents found) |
| 1 | File not found or outside scope |

**Examples:**

```bash
# Show immediate dependents
lexi impact src/lexibrary/config/schema.py

# Show transitive dependents up to depth 2
lexi impact src/lexibrary/config/schema.py --depth 2

# Get bare paths for piping
lexi impact src/lexibrary/config/schema.py --quiet
```

---

### trace

Trace a symbol's callers and callees through the symbol graph
(`.lexibrary/symbols.db`). The symbol-level analogue of `lexi impact`:
where `impact` answers "which files import me?", `trace` answers "which
functions call me, and which functions do I call?". Use it when tracking
a bug across more than two files or sizing the blast radius of a rename
or signature change.

```
lexi trace <symbol> [--file PATH]
```

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `symbol` | Yes | A symbol name to trace. A bare name (e.g. `update_project`) is matched against `symbols.name` and may return multiple results. A dotted name (e.g. `lexibrary.archivist.pipeline.update_project`) is matched **exactly** against `symbols.qualified_name`. Any argument containing a `.` is treated as qualified. |

**Options:**

| Option | Description |
|--------|-------------|
| `--file` | Narrow a bare-name match to a single file path. Useful when the same symbol name exists in multiple modules. Ignored for qualified-name matches. |

**What it outputs:**

For each matching symbol, a section containing:

1. **Header** — `## <qualified_name>  [<symbol_type>]` with the
   `file_path:line_start` on the next line in backticks.
2. **`### Callers`** — markdown table of `| Caller | Location |`
   showing every in-project symbol that invokes this one. Omitted if
   there are no callers.
3. **`### Callees`** — markdown table of `| Callee | Location |`
   showing every in-project symbol this one invokes. Omitted if there
   are no callees.
4. **`### Unresolved callees (external or dynamic)`** — table of
   `| Name | Line |` rows for calls the symbol resolver could not map
   to a definition. Typical entries are standard library calls
   (`logger.info`, `sqlite3.connect`) and dynamic dispatch. As of
   Phase 3, `self.method()` calls are walked through the MRO, so a
   subclass method calling an inherited base method appears as a
   resolved callee rather than an unresolved one.
5. **`### Base classes`** — Phase 3 markdown table of
   `| Base | Location |` listing every class this symbol inherits
   from or implements. Populated from Python `class Foo(Bar):`
   declarations and TS/JS `extends` / `implements` clauses. Omitted
   if the symbol has no resolved bases (or is not a class).
6. **`### Subclasses and instantiation sites`** — Phase 3 markdown
   table of `| Type | Source | Location |` listing every class that
   inherits from this one (`Type = inherits`) plus every call site
   that constructs it (`Type = instantiates`). Populated from the
   Python PascalCase instantiation heuristic
   (`^[A-Z][A-Za-z0-9]*$`) and TS/JS `new` expressions. Omitted if
   the symbol has no inbound class edges.
7. **`Unresolved bases: ...`** — Phase 3 trailing line listing base
   names the resolver could not map to a project symbol (typically
   external libraries like Pydantic `BaseModel` or stdlib `Enum`).
   Treat these as out-of-scope for refactoring. Omitted when there
   are no unresolved bases.

Multiple matches are separated by a blank line. All output is rendered
via the same `info()` helper used by `lexi lookup`, so it is safe to
pipe into other tools.

**Stale-graph warning:** When the file containing the matched symbol has
a stale `last_hash` in `symbols.db`, a
`Symbol graph may be stale for <file> — run lexi design update <file>
to refresh.` warning is printed to stderr. The command still exits 0
and still renders the (possibly outdated) results.

**Exit codes:**

| Code | Meaning |
|------|---------|
| 0 | At least one matching symbol was found and rendered |
| 1 | No matching symbol exists in the symbol graph |

On a miss, stderr contains `No symbol named ...` and a hint suggesting
`lexi design update <file>` (to refresh the graph) or
`lexi search --type symbol` (to fuzzy-find the right name).

**Examples:**

```bash
# Trace every symbol named `update_project`
lexi trace update_project

# Trace exactly one symbol by qualified name
lexi trace lexibrary.archivist.pipeline.update_project

# Narrow an ambiguous bare name to a single file
lexi trace build_index --file src/lexibrary/linkgraph/builder.py

# Trace a class — shows base classes, subclasses, instantiation
# sites, and unresolved external bases
lexi trace LexibraryConfig
```

Sample class output:

```
## lexibrary.config.schema.LexibraryConfig  [class]
`src/lexibrary/config/schema.py:42`

### Base classes
| Base                                    | Location                                  |
|-----------------------------------------|-------------------------------------------|
| lexibrary.config.schema._ConfigBase     | src/lexibrary/config/schema.py:18         |

### Subclasses and instantiation sites
| Type          | Source                                  | Location                                 |
|---------------|------------------------------------------|------------------------------------------|
| instantiates  | lexibrary.config.loader.load_config      | src/lexibrary/config/loader.py:87        |

Unresolved bases: BaseModel
```

**Related:**

- [`lexi search --type symbol`](#search) — fuzzy-find a symbol by name
  before tracing it.
- [`lexi lookup --full`](#lookup) — lists the file's public symbols in
  the "Key symbols" section with caller and callee counts and a
  "Class hierarchy" table of the file's classes with base/subclass
  counts.
- Playbook: [[Tracing a symbol with lexi trace]] (`PB-008`).
- Playbook: [[Refactoring with the call graph]] (`PB-009`) — the
  step-by-step procedure for renaming, splitting, or removing a
  symbol that has downstream dependents.
- [Symbol graph](symbol-graph.md) — what the symbol graph is and how it
  is built.

---

### view

Display the full content of any artifact by its ID.

```
lexi view <artifact_id>
```

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `artifact_id` | Yes | Artifact ID in XX-NNN format (e.g., CN-001, ST-042, DS-017, CV-003, PB-001). |

Accepts concept (CN), convention (CV), playbook (PB), design (DS), and Stack (ST) IDs.

**Examples:**

```bash
lexi view ST-001
lexi view CN-003
lexi view DS-017
```

---

### describe

Update the billboard description in a directory's `.aindex` file. The billboard is the brief description of what the directory contains and its purpose.

```
lexi describe <directory> <description>
```

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `directory` | Yes | Directory whose `.aindex` to update. |
| `description` | Yes | New billboard description text. |

**Exit codes:**

| Code | Meaning |
|------|---------|
| 0 | Billboard updated successfully |
| 1 | Directory not found, not a directory, outside project root, or no `.aindex` file exists |

**Examples:**

```bash
# Update the billboard for a directory
lexi describe src/lexibrary/config/ "Configuration schema, YAML loader, and default values"

# Update the project root billboard
lexi describe . "AI-friendly codebase indexer producing .lexibrary/ design files"
```

---

### validate

Run consistency checks on the library. Reports issues grouped by severity level.

```
lexi validate [--severity LEVEL] [--check NAME] [--json]
```

**Options:**

| Option | Description |
|--------|-------------|
| `--severity` | Minimum severity to report: `error`, `warning`, or `info`. |
| `--check` | Run only the named check (see checks table below). |
| `--json` | Output results as JSON instead of tables. |

**Available checks:**

Error-level checks (indicate broken state):

| Check | Description |
|-------|-------------|
| `wikilink_resolution` | Wikilinks in design files and concepts resolve to valid targets |
| `file_existence` | Source files referenced in design file frontmatter still exist |
| `concept_frontmatter` | Concept files have valid YAML frontmatter (title, status, tags) |

Warning-level checks (indicate potential issues):

| Check | Description |
|-------|-------------|
| `hash_freshness` | Design file source hashes match the current source file content |
| `token_budgets` | Generated artifacts stay within configured token budget targets |
| `orphan_concepts` | Concepts are linked to at least one design file |
| `deprecated_concept_usage` | Deprecated concepts are not referenced in active design files |

Info-level checks (informational):

| Check | Description |
|-------|-------------|
| `forward_dependencies` | Design files declare forward dependency relationships |
| `stack_staleness` | Open Stack posts have not been idle for too long |
| `aindex_coverage` | Directories with design files also have `.aindex` routing tables |
| `bidirectional_deps` | Dependency relationships are declared in both directions |
| `dangling_links` | Links in the link graph point to existing artifacts |
| `orphan_artifacts` | Design files in `.lexibrary/` have corresponding source files |

**Exit codes:**

| Code | Meaning |
|------|---------|
| 0 | No issues found (clean) |
| 1 | One or more error-level issues found, or an invalid check/severity was specified |
| 2 | Warning-level issues found but no errors |

**Examples:**

```bash
# Run all checks
lexi validate

# Show only errors and warnings
lexi validate --severity warning

# Run a single check
lexi validate --check hash_freshness

# JSON output for CI
lexi validate --json
```

---

### status

Show library health and staleness summary. Provides a quick overview of the library's current state.

```
lexi status [path] [--quiet]
```

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `path` | No | Project directory to check. Defaults to the current directory. |

**Options:**

| Option | Description |
|--------|-------------|
| `-q`, `--quiet` | Single-line output suitable for hooks, CI, and notifications. |

**Dashboard mode (default):**

Displays a full dashboard with:

| Section | What it reports |
|---------|-----------------|
| Files | Count of tracked design files and how many are stale (source hash mismatch) |
| Concepts | Count by status: active, deprecated, draft |
| Stack | Total posts with open/resolved breakdown |
| Link graph | Artifact and link counts with build timestamp, or "not built" if missing |
| Issues | Error and warning counts from a lightweight validation pass |
| Updated | Time since the most recent design file was generated |

**Quiet mode (`--quiet`):**

Outputs a single line:

| Output | Condition |
|--------|-----------|
| `lexictl: N error(s), M warning(s) -- run 'lexictl validate'` | Errors and warnings found |
| `lexictl: library healthy` | No errors or warnings |

**Exit codes:**

| Code | Meaning |
|------|---------|
| 0 | No issues found |
| 1 | One or more error-level issues found |
| 2 | Warning-level issues found but no errors |

**Examples:**

```bash
# Full dashboard
lexi status

# Quick check in a script or hook
lexi status --quiet
```

---

### concept

Concept management commands for working with the project's knowledge wiki.

#### concept new

Create a new concept file from a template.

```
lexi concept new <name> [--tag TAG]
```

| Argument/Option | Required | Description |
|-----------------|----------|-------------|
| `name` | Yes | Name for the new concept. |
| `--tag` | No | Tag to add to the concept (repeatable). |

The new concept file is created at `.lexibrary/concepts/<name>.md` with YAML frontmatter (title, aliases, tags, status: draft) and a markdown body template.

```bash
lexi concept new change-detection
lexi concept new pydantic-validation --tag config --tag schema
```

#### concept link

Add a wikilink reference from a concept to a source file's design file.

```
lexi concept link <slug> <source_file>
```

| Argument | Required | Description |
|----------|----------|-------------|
| `slug` | Yes | Concept slug (filename stem, e.g., `scope-root`). |
| `source_file` | Yes | Source file whose design file should receive the wikilink. |

```bash
lexi concept link change-detection src/lexibrary/archivist/change_checker.py
```

#### concept comment

Append a comment to a concept.

```
lexi concept comment <slug> --body TEXT
```

| Argument/Option | Required | Description |
|-----------------|----------|-------------|
| `slug` | Yes | Concept slug (filename stem). |
| `-b`, `--body` | Yes | Comment text to append. |

```bash
lexi concept comment scope-root --body "Clarified: scope_root is always relative to project root."
```

#### concept deprecate

Set a concept's status to deprecated.

```
lexi concept deprecate <slug> [--superseded-by NAME]
```

| Argument/Option | Required | Description |
|-----------------|----------|-------------|
| `slug` | Yes | Concept slug (filename stem). |
| `--superseded-by` | No | Title of the concept that replaces this one. |

```bash
lexi concept deprecate old-auth --superseded-by "new-auth-pattern"
```

---

### convention

Convention lifecycle management commands.

#### convention new

Create a new convention file.

```
lexi convention new --scope SCOPE --body TEXT [--tag TAG] [--title TEXT]
    [--source TEXT] [--alias TEXT]
```

| Option | Required | Description |
|--------|----------|-------------|
| `--scope` | Yes | Convention scope: `project` for repo-wide, or comma-separated directory paths. |
| `--body` | Yes | Convention body text (first paragraph is the rule). |
| `--tag` | No | Tag to add (repeatable). |
| `--title` | No | Convention title (derived from body if omitted). |
| `--source` | No | Convention source: `user` or `agent` (default: `user`). |
| `--alias` | No | Short alias for the convention (repeatable). |

```bash
lexi convention new --scope project --body "All modules must use from __future__ import annotations." --tag python
lexi convention new --scope "src/lexibrary/config/" --body "Config models use Pydantic 2 BaseModel." --tag config
```

#### convention approve

Promote a draft convention to active status.

```
lexi convention approve <slug>
```

| Argument | Required | Description |
|----------|----------|-------------|
| `slug` | Yes | Convention file slug (filename stem). |

```bash
lexi convention approve use-pathspec-gitignore
```

#### convention deprecate

Set a convention's status to deprecated.

```
lexi convention deprecate <slug>
```

| Argument | Required | Description |
|----------|----------|-------------|
| `slug` | Yes | Convention file slug (filename stem). |

```bash
lexi convention deprecate old-output-style
```

#### convention comment

Append a comment to a convention.

```
lexi convention comment <slug> --body TEXT
```

| Argument/Option | Required | Description |
|-----------------|----------|-------------|
| `slug` | Yes | Convention file slug (filename stem). |
| `--body` | Yes | Comment text to append. |

```bash
lexi convention comment use-pathspec-gitignore --body "Confirmed: this applies to all ignore matchers."
```

---

### stack

Stack issue management commands for the project's debugging knowledge base.

#### stack post

Create a new Stack issue post with an auto-assigned ID.

```
lexi stack post --title TEXT --tag TAG [--bead ID] [--file PATH] [--concept NAME]
    [--problem TEXT] [--context TEXT] [--evidence TEXT] [--attempts TEXT]
    [--finding TEXT] [--resolve] [--resolution-type TYPE]
    [--fix TEXT] [--workaround TEXT]
```

| Option | Required | Description |
|--------|----------|-------------|
| `--title` | Yes | Title for the new issue post. |
| `--tag` | Yes | Tag for the post (repeatable, at least one required). |
| `--bead` | No | Bead ID to associate with the post. |
| `--file` | No | Source file reference (repeatable). |
| `--concept` | No | Concept reference (repeatable). |
| `--problem` | No | Problem description for the issue. |
| `--context` | No | Context for the issue. |
| `--evidence` | No | Evidence item (repeatable). |
| `--attempts` | No | Attempt description (repeatable). |
| `--finding` | No | Inline finding body text. |
| `--resolve` | No | Auto-accept inline finding and set status to resolved. |
| `--resolution-type` | No | Resolution type (e.g., `fix`, `workaround`). Requires `--resolve`. |
| `--fix` | No | Shortcut: add a finding, resolve, and set resolution-type to `fix`. |
| `--workaround` | No | Shortcut: add a finding, resolve, and set resolution-type to `workaround`. |

The post is created at `.lexibrary/stack/ST-NNN-<slug>.md` where NNN is auto-incremented and the slug is derived from the title.

**Scaffold mode:** When no content flags (`--problem`, `--context`, etc.) are provided, all four body sections are scaffolded with HTML comment placeholders for manual editing.

**One-shot mode:** When content flags are provided, a fully populated post is created in a single command.

```bash
# Scaffold mode
lexi stack post --title "Config loader silently ignores unknown keys" --tag config --tag bug

# One-shot with inline finding and resolution
lexi stack post --title "Race condition in sweep watch mode" --tag sweep --tag concurrency \
  --problem "Concurrent sweep iterations cause duplicate index entries." \
  --finding "Added a sweep-in-progress flag." \
  --resolve --resolution-type fix

# Quick fix shortcut
lexi stack post --title "Missing null check in parser" --tag parser \
  --problem "Parser crashes on empty input." \
  --fix "Added null check before parsing."
```

#### stack finding

Append a finding to an existing Stack post.

```
lexi stack finding <post_id> --body TEXT [--author NAME]
```

| Argument/Option | Required | Description |
|-----------------|----------|-------------|
| `post_id` | Yes | Post ID (e.g., `ST-001`). |
| `-b`, `--body` | Yes | Finding body text. |
| `--author` | No | Author of the finding (default: `user`). |

```bash
lexi stack finding ST-001 --body "The fix is to increase the timeout in config.yaml to 120 seconds."
```

#### stack vote

Record a vote on a post or finding.

```
lexi stack vote <post_id> <up|down> [--finding NUM] [--comment TEXT] [--author NAME]
```

| Argument/Option | Required | Description |
|-----------------|----------|-------------|
| `post_id` | Yes | Post ID (e.g., `ST-001`). |
| direction | Yes | Vote direction: `up` or `down`. |
| `--finding` | No | Finding number to vote on (omit to vote on the post itself). |
| `--comment` | For downvotes | Comment explaining the downvote (required for downvotes). |
| `--author` | No | Author of the vote (default: `user`). |

```bash
lexi stack vote ST-001 up
lexi stack vote ST-001 up --finding 2
lexi stack vote ST-003 down --comment "This solution introduces a memory leak"
```

#### stack accept

Mark a finding as accepted and set the post status to resolved.

```
lexi stack accept <post_id> --finding NUM [--resolution-type TYPE]
```

| Argument/Option | Required | Description |
|-----------------|----------|-------------|
| `post_id` | Yes | Post ID (e.g., `ST-001`). |
| `--finding` | Yes | Finding number to accept. |
| `--resolution-type` | No | Resolution type: `fix`, `workaround`, `wontfix`, `cannot_reproduce`, or `by_design`. |

```bash
lexi stack accept ST-001 --finding 2
lexi stack accept ST-001 --finding 2 --resolution-type fix
```

#### stack view

Display the full content of a Stack post, including all findings, votes, and metadata.

```
lexi stack view <post_id>
```

| Argument | Required | Description |
|----------|----------|-------------|
| `post_id` | Yes | Post ID (e.g., `ST-001`). |

```bash
lexi stack view ST-001
```

#### stack comment

Append a comment to a Stack post.

```
lexi stack comment <post_id> --body TEXT
```

| Argument/Option | Required | Description |
|-----------------|----------|-------------|
| `post_id` | Yes | Post ID (e.g., `ST-001`). |
| `-b`, `--body` | Yes | Comment text to append. |

```bash
lexi stack comment ST-001 --body "This may also affect the sweep module."
```

#### stack mark-outdated

Set a Stack post's status to outdated.

```
lexi stack mark-outdated <post_id>
```

| Argument | Required | Description |
|----------|----------|-------------|
| `post_id` | Yes | Post ID (e.g., `ST-001`). |

```bash
lexi stack mark-outdated ST-003
```

#### stack duplicate

Set a Stack post's status to duplicate and link it to the original post.

```
lexi stack duplicate <post_id> --of ORIGINAL_ID
```

| Argument/Option | Required | Description |
|-----------------|----------|-------------|
| `post_id` | Yes | Post ID to mark as duplicate (e.g., `ST-003`). |
| `--of` | Yes | Original post ID this is a duplicate of. |

```bash
lexi stack duplicate ST-003 --of ST-001
```

#### stack stale

Set a resolved Stack post's status to stale for re-evaluation.

```
lexi stack stale <post_id>
```

| Argument | Required | Description |
|----------|----------|-------------|
| `post_id` | Yes | Post ID (e.g., `ST-001`). |

```bash
lexi stack stale ST-005
```

#### stack unstale

Reverse staleness on a Stack post, setting status back to resolved.

```
lexi stack unstale <post_id>
```

| Argument | Required | Description |
|----------|----------|-------------|
| `post_id` | Yes | Post ID (e.g., `ST-001`). |

```bash
lexi stack unstale ST-005
```

---

### design

Design file management commands.

#### design update

Generate or update the design file for a source file via the archivist pipeline.

```
lexi design update <source_file> [--force] [--unlimited]
```

| Argument/Option | Required | Description |
|-----------------|----------|-------------|
| `source_file` | Yes | Source file to generate or update a design file for. |
| `-f`, `--force` | No | Bypass updated_by protection and staleness checks. |
| `--unlimited` | No | Bypass token-budget size gate for large files. |

```bash
lexi design update src/lexibrary/config/schema.py
lexi design update src/lexibrary/config/schema.py --force
```

#### design comment

Append a comment to a design file.

```
lexi design comment <source_file> --body TEXT
```

| Argument/Option | Required | Description |
|-----------------|----------|-------------|
| `source_file` | Yes | Source file to add a design comment for. |
| `-b`, `--body` | Yes | Comment text to append. |

```bash
lexi design comment src/lexibrary/config/schema.py --body "Added validate_token_budget() method."
```

---

### iwh

IWH (I Was Here) signal management commands. IWH signals are inter-session coordination markers that agents leave behind to communicate incomplete work, blockers, or warnings to subsequent agents.

#### iwh write

Create an IWH signal for a directory.

```
lexi iwh write [directory] --body TEXT [--scope SCOPE]
```

| Argument/Option | Required | Description |
|-----------------|----------|-------------|
| `directory` | No | Source directory for the signal. Defaults to project root. |
| `-b`, `--body` | Yes | Signal body text describing the situation. |
| `-s`, `--scope` | No | Signal scope: `incomplete`, `blocked`, or `warning` (default: `incomplete`). |

```bash
lexi iwh write src/lexibrary/config/ --body "Remaining: add validation for new topology fields."
lexi iwh write --scope blocked --body "Waiting for schema.py changes to merge."
```

#### iwh read

Read and consume an IWH signal for a directory.

```
lexi iwh read [directory] [--peek]
```

| Argument/Option | Required | Description |
|-----------------|----------|-------------|
| `directory` | No | Source directory to read signal from. Defaults to project root. |
| `--peek` | No | Read without consuming (do not delete the signal). |

```bash
lexi iwh read src/lexibrary/config/
lexi iwh read src/lexibrary/config/ --peek
```

#### iwh list

List all IWH signals in the project.

```
lexi iwh list
```

Returns a table showing directory, scope, author, age, and body for each signal.

---

### playbook

Playbook lifecycle management commands.

#### playbook new

Create a scaffolded playbook file.

```
lexi playbook new <title> [--trigger-file GLOB] [--tag TAG] [--estimated-minutes N]
```

| Argument/Option | Required | Description |
|-----------------|----------|-------------|
| `title` | Yes | Playbook title -- use a semantic name (e.g., `Version Bump`). |
| `--trigger-file` | No | Glob pattern for file-context discovery (repeatable). |
| `--tag` | No | Tag to add (repeatable). |
| `--estimated-minutes` | No | Estimated time in minutes to complete the playbook. |

```bash
lexi playbook new "Version Bump" --trigger-file "pyproject.toml" --tag release
```

#### playbook approve

Promote a draft playbook to active status.

```
lexi playbook approve <slug>
```

| Argument | Required | Description |
|----------|----------|-------------|
| `slug` | Yes | Playbook file slug (filename stem). |

```bash
lexi playbook approve version-bump
```

#### playbook verify

Update a playbook's `last_verified` date to today.

```
lexi playbook verify <slug>
```

| Argument | Required | Description |
|----------|----------|-------------|
| `slug` | Yes | Playbook file slug (filename stem). |

```bash
lexi playbook verify version-bump
```

#### playbook deprecate

Set a playbook's status to deprecated.

```
lexi playbook deprecate <slug> [--superseded-by SLUG] [--reason TEXT]
```

| Argument/Option | Required | Description |
|-----------------|----------|-------------|
| `slug` | Yes | Playbook file slug (filename stem). |
| `--superseded-by` | No | Slug of the playbook that supersedes this one. |
| `--reason` | No | Reason for deprecation. |

```bash
lexi playbook deprecate old-release --superseded-by version-bump --reason "Replaced by automated workflow"
```

#### playbook comment

Append a comment to a playbook's sidecar comment file.

```
lexi playbook comment <slug> --body TEXT
```

| Argument/Option | Required | Description |
|-----------------|----------|-------------|
| `slug` | Yes | Playbook file slug (filename stem). |
| `--body` | Yes | Comment text to append. |

```bash
lexi playbook comment version-bump --body "Step 3 now requires running tests first."
```

---

## lexictl Commands

### init

Initialize Lexibrary in a project. Runs an interactive setup wizard that detects project configuration.

```
lexictl init [--defaults]
```

| Option | Description |
|--------|-------------|
| `--defaults` | Accept all detected defaults without prompting. Required for CI/scripting and non-interactive environments. |

**Behavior:**

1. **Re-init guard** -- If `.lexibrary/` already exists, exits with code 1 and directs to `lexictl setup --update`.
2. **Non-TTY detection** -- If stdin is not a terminal and `--defaults` is not set, exits with code 1 and suggests `--defaults`.
3. **Wizard flow** -- Runs the setup wizard (see [Project Setup](project-setup.md) for a detailed walkthrough).
4. **Skeleton creation** -- Creates the `.lexibrary/` directory with `config.yaml`, `START_HERE.md`, subdirectories (`concepts/`, `stack/`), and a `.lexignore` file.

**Exit codes:**

| Code | Meaning |
|------|---------|
| 0 | Initialization completed successfully |
| 1 | Already initialized, non-TTY without `--defaults`, or user cancelled |

```bash
lexictl init
lexictl init --defaults
```

---

### update

Re-index changed files and regenerate design files. This is the primary command for keeping the library in sync with source code changes.

```
lexictl update [PATH] [--changed-only FILE ...] [--dry-run] [--topology]
    [--skeleton] [--unlimited] [--force] [--reindex]
```

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `PATH` | No | File or directory to update. Omit to update the entire project. |

**Options:**

| Option | Description |
|--------|-------------|
| `--changed-only FILE [...]` | Only update the specified files (for git hooks / CI). Mutually exclusive with `PATH`. |
| `--dry-run` | Preview which files would change without making any modifications. |
| `--topology` | Regenerate raw-topology.md only, without running the full update. |
| `--skeleton` | Generate a skeleton design file without LLM enrichment. Requires a single file path argument. |
| `--unlimited` | Bypass the size gate so large files are sent to the LLM instead of receiving a skeleton fallback. |
| `--force` | Force a full rebuild regardless of modification timestamps. Regenerates all design files and rebuilds the link graph index from scratch. |
| `--reindex` | Rebuild the link graph index from existing artifacts on disk. Does not regenerate design files or invoke the LLM. |

**Modes:**

- **Full project update** (no arguments): Discovers all source files, compares hashes, regenerates changed design files, rebuilds `.aindex` routing tables, regenerates `TOPOLOGY.md`, and builds the link graph index.
- **Single file update** (with `PATH` as file): Updates only that file's design file and reports the change level.
- **Directory update** (with `PATH` as directory): Runs the full project update pipeline.
- **Changed-only update** (with `--changed-only`): Updates only the specified files. Does not regenerate `TOPOLOGY.md` or rebuild the full link graph.

**Exit codes:**

| Code | Meaning |
|------|---------|
| 0 | Update completed successfully |
| 1 | Path not found, path outside project root, `PATH` and `--changed-only` used together, or one or more files failed |

```bash
# Full project update
lexictl update

# Single file
lexictl update src/lexibrary/config/schema.py

# Changed files only (for git hooks)
lexictl update --changed-only src/module.py src/utils.py

# Preview changes without modifying
lexictl update --dry-run

# Force full rebuild
lexictl update --force

# Rebuild link graph only
lexictl update --reindex
```

---

### bootstrap

Batch-create design files for a project. Designed for initial setup or bulk generation after adding many new files.

```
lexictl bootstrap [--scope DIR] [--full] [--quick]
```

**Options:**

| Option | Description |
|--------|-------------|
| `--scope` | Override the scope root from config (directory relative to project root). |
| `--full` | Full bootstrap with LLM-enriched design file generation. |
| `--quick` | Quick bootstrap with heuristic-only design files (no LLM calls). |

When neither `--full` nor `--quick` is provided, the command runs a quick bootstrap followed by an optional full enrichment pass.

```bash
# Default: quick bootstrap with optional enrichment
lexictl bootstrap

# Quick mode only (no LLM)
lexictl bootstrap --quick

# Full LLM-enriched bootstrap
lexictl bootstrap --full

# Bootstrap a specific directory
lexictl bootstrap --scope src/lexibrary/config/
```

---

### index

Generate `.aindex` routing table files for a directory. These provide a billboard summary and file listing for navigation.

```
lexictl index [directory] [-r/--recursive]
```

**Arguments:**

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `directory` | No | `.` (current directory) | Directory to index. |

**Options:**

| Option | Description |
|--------|-------------|
| `-r`, `--recursive` | Recursively index all subdirectories. |

**Exit codes:**

| Code | Meaning |
|------|---------|
| 0 | Indexing completed successfully |
| 1 | Directory not found, not a directory, or outside project root |

```bash
lexictl index
lexictl index src/lexibrary/config/
lexictl index src/ -r
```

---

### validate

Run consistency checks on the library (same checks as `lexi validate`).

```
lexictl validate [--severity LEVEL] [--check NAME] [--json]
```

See `lexi validate` above for full documentation of options, available checks, and exit codes.

---

### status

Show library health and staleness summary (same output as `lexi status`).

```
lexictl status [PATH] [--quiet]
```

See `lexi status` above for full documentation of options and output modes.

---

### setup

Install or update agent environment rules and git hooks.

```
lexictl setup [--update] [--env ENV] [--hooks]
```

**Options:**

| Option | Description |
|--------|-------------|
| `--update` | Update agent rules for the configured environments. Required to perform rule generation. |
| `--env` | Explicit environment(s) to generate rules for (repeatable). Overrides `agent_environment` config. |
| `--hooks` | Install the git post-commit hook for automatic design file updates. |

**Supported environments:**

| Environment | Generated Files |
|-------------|----------------|
| `claude` | `CLAUDE.md` or `.claude/CLAUDE.md` |
| `cursor` | `.cursor/rules` |
| `codex` | `AGENTS.md` |

Running `lexictl setup` without `--update` or `--hooks` displays usage instructions.

```bash
lexictl setup --update
lexictl setup --update --env claude --env cursor
lexictl setup --hooks
```

---

### sweep

Run a library update sweep. A sweep performs the same work as `lexictl update` but is designed for automated/periodic use.

```
lexictl sweep [--watch]
```

**Options:**

| Option | Description |
|--------|-------------|
| `--watch` | Run periodic sweeps in the foreground until interrupted with Ctrl+C. |

**Modes:**

- **One-shot** (default): Performs a single full library update and exits.
- **Watch mode**: Runs periodic sweeps at the interval configured in `sweep.sweep_interval_seconds` (default: 3600 seconds).

```bash
lexictl sweep
lexictl sweep --watch
```

---

### curate

Run autonomous maintenance using the curator agent. Collects maintenance signals, triages by risk, and dispatches actions within configured budgets.

```
lexictl curate [options]
```

See `lexictl curate --help` for full option documentation.

---

## Command Summary

### lexi commands

| Command | Purpose |
|---------|---------|
| `lexi lookup <path> [--full]` | Get design file, conventions, known issues, IWH, and dependents |
| `lexi search [query] [filters]` | Unified cross-artifact search |
| `lexi impact <file> [--depth] [--quiet]` | Show reverse dependents (who imports this file) |
| `lexi trace <symbol> [--file]` | Show callers, callees, and unresolved external calls for a symbol |
| `lexi view <artifact_id>` | Display any artifact by its ID |
| `lexi describe <dir> <desc>` | Update a directory's `.aindex` billboard description |
| `lexi validate [--severity] [--check] [--json]` | Run consistency checks |
| `lexi status [--quiet]` | Show library health summary |
| `lexi concept new <name> [--tag]` | Create a new concept file |
| `lexi concept link <slug> <file>` | Add a wikilink from a concept to a design file |
| `lexi concept comment <slug> --body` | Append a comment to a concept |
| `lexi concept deprecate <slug>` | Deprecate a concept |
| `lexi convention new --scope --body` | Create a new convention file |
| `lexi convention approve <slug>` | Promote a convention to active |
| `lexi convention deprecate <slug>` | Deprecate a convention |
| `lexi convention comment <slug> --body` | Append a comment to a convention |
| `lexi stack post --title --tag [content flags]` | Create a Stack issue post |
| `lexi stack finding <id> --body` | Add a finding to a Stack post |
| `lexi stack vote <id> <up\|down>` | Vote on a post or finding |
| `lexi stack accept <id> --finding` | Accept a finding (sets status to resolved) |
| `lexi stack view <id>` | Display full post content |
| `lexi stack comment <id> --body` | Append a comment to a post |
| `lexi stack mark-outdated <id>` | Set a post's status to outdated |
| `lexi stack duplicate <id> --of` | Mark a post as duplicate |
| `lexi stack stale <id>` | Set a resolved post to stale for re-evaluation |
| `lexi stack unstale <id>` | Reverse staleness on a post |
| `lexi design update <file> [--force] [--unlimited]` | Generate or update a design file |
| `lexi design comment <file> --body` | Append a comment to a design file |
| `lexi iwh write [dir] --body [--scope]` | Create an IWH signal |
| `lexi iwh read [dir] [--peek]` | Read (and consume) an IWH signal |
| `lexi iwh list` | List all IWH signals |
| `lexi playbook new <title> [options]` | Create a scaffolded playbook |
| `lexi playbook approve <slug>` | Promote a playbook to active |
| `lexi playbook verify <slug>` | Update a playbook's last_verified date |
| `lexi playbook deprecate <slug>` | Deprecate a playbook |
| `lexi playbook comment <slug> --body` | Append a comment to a playbook |

### lexictl commands

| Command | Purpose |
|---------|---------|
| `lexictl init [--defaults]` | Initialize Lexibrary in a project |
| `lexictl update [PATH] [options]` | Re-index and regenerate design files |
| `lexictl bootstrap [--scope] [--full\|--quick]` | Batch-create design files |
| `lexictl index [dir] [-r]` | Generate `.aindex` routing table(s) |
| `lexictl validate [--severity] [--check] [--json]` | Run consistency checks |
| `lexictl status [--quiet]` | Show library health summary |
| `lexictl setup [--update] [--env] [--hooks]` | Install agent rules and git hooks |
| `lexictl sweep [--watch]` | Run library update sweep |
| `lexictl curate` | Run autonomous maintenance |
