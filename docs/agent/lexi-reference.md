# lexi CLI Reference

Complete reference for the `lexi` command -- the agent-facing CLI for Lexibrary. Every command, subcommand, flag, and argument is documented here with usage examples.

Run `lexi --help` for a quick overview, or `lexi <command> --help` for any specific command.

---

## orient

Show project orientation: topology, file map, library stats, and IWH signals. This replaces the former `context-dump` command.

```
lexi orient
```

**What it outputs:**

1. **Project topology** -- root billboard and top-level directory summaries from `.aindex` files
2. **Library stats** -- concept count, convention count, open stack post count
3. **IWH signals peek** -- lists all pending IWH signals with scope, directory, and body preview (without consuming them)
4. **IWH consumption guidance** -- when signals are present, includes a footer explaining how to consume them with `lexi iwh read <dir>`

**Token budget:** Controlled by `orientation_tokens` in `TokenBudgetConfig` (default: 300).

**Examples:**

```bash
# Orient at session start
lexi orient
```

**When to use:** Run at the start of every session as directed by CLAUDE.md rules. This is your first step to understand the project state and any pending work from previous sessions.

---

## lookup

Look up the design file for a source file, or show a directory overview. Includes applicable conventions, Known Issues from Stack, IWH signals, and dependents from the link graph.

```
lexi lookup <file|directory>
```

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `file` | Yes | Path to a source file or directory to look up |

**What it outputs (file mode):**

1. **Design file content** -- the full markdown design file including YAML frontmatter (source path, source_hash, generated timestamp, updated_by, wikilinks), summary, interface skeleton, and key details
2. **Staleness warning** -- if the source file's SHA-256 hash does not match the hash stored in the design file frontmatter, a warning is printed suggesting `lexictl update`
3. **Applicable conventions** -- conventions from `.aindex` files walked upward from the file's directory to the scope root. Each convention is shown with its originating directory
4. **Known Issues** -- stack posts that reference this file, showing status, title, attempts summary, and vote count. Open posts shown first, then resolved. Maximum controlled by `stack.lookup_display_limit` (default: 3). Stale posts excluded.
5. **IWH signals** -- peek at IWH signals for the file's directory (read without consuming)
6. **Dependents** -- files that import this file (from the link graph, if available)
7. **Also referenced by** -- other inbound references: concept wikilinks, Stack post file refs, design file refs, convention concept refs

**What it outputs (directory mode):**

1. **AIndex content** -- the directory's `.aindex` billboard and file listing
2. **Applicable conventions** -- conventions scoped to this directory
3. **IWH signals** -- peek at IWH signals for this directory

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

# Look up a file using a relative path
lexi lookup ./cli/lexi_app.py

# Look up a directory
lexi lookup src/lexibrary/config/
```

**When to use:** Always run `lexi lookup` before editing a source file. It shows you the file's purpose, interface, conventions to follow, known issues, and what depends on it. Use directory mode to explore what a directory contains.

---

## index

Generate `.aindex` routing table files for a directory. These provide a billboard summary and file listing for the directory.

```
lexictl index [directory] [-r/--recursive]
```

**Arguments:**

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `directory` | No | `.` (current directory) | Directory to index |

**Options:**

| Option | Description |
|--------|-------------|
| `-r`, `--recursive` | Recursively index all subdirectories |

**Exit codes:**

| Code | Meaning |
|------|---------|
| 0 | Indexing completed successfully |
| 1 | Directory not found, not a directory, or outside project root |

**Examples:**

```bash
# Index the current directory
lexictl index

# Index a specific directory
lexictl index src/lexibrary/config/

# Recursively index all directories under src/
lexictl index src/ -r
```

**When to use:** Run after creating new files or directories to ensure `.aindex` files reflect the current project structure.

---

## describe

Update the billboard description in a directory's `.aindex` file. The billboard is the brief description of what the directory contains and its purpose.

```
lexi describe <directory> <description>
```

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `directory` | Yes | Directory whose `.aindex` to update |
| `description` | Yes | New billboard description text |

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

**When to use:** Run after the purpose or contents of a directory have changed significantly. This is the correct way to update `.aindex` files -- never edit them directly.

---

## concepts

List all concepts or search for concepts matching a topic.

```
lexi concepts [topic]
```

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `topic` | No | Search query to filter concepts by |

**Output:** A table with columns: Name, Status (active/draft/deprecated), Tags, Summary.

When no topic is given, all concepts are listed. When a topic is given, only matching concepts are shown (searched by title, aliases, and tags).

**Examples:**

```bash
# List all concepts
lexi concepts

# Search for concepts related to "validation"
lexi concepts validation

# Search for concepts about "config"
lexi concepts config
```

**When to use:** Run before making architectural decisions to check whether the project already has a convention or pattern for what you are about to do.

---

## concept new

Create a new concept file from a template.

```
lexi concept new <name> [--tag <tag>]
```

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `name` | Yes | Name for the new concept |

**Options:**

| Option | Description |
|--------|-------------|
| `--tag <tag>` | Tag to add to the concept (repeatable) |

**Exit codes:**

| Code | Meaning |
|------|---------|
| 0 | Concept file created successfully |
| 1 | Concept file already exists |

The new concept file is created at `.lexibrary/concepts/<name>.md` with YAML frontmatter (title, aliases, tags, status: draft) and a markdown body template.

**Examples:**

```bash
# Create a basic concept
lexi concept new change-detection

# Create a concept with tags
lexi concept new pydantic-validation --tag config --tag schema
```

**When to use:** Create a concept when:
- Three or more files share a common pattern or convention
- A domain term needs a canonical definition
- An architectural decision should be recorded for future reference

---

## concept link

Add a wikilink reference from a concept to a source file's design file.

```
lexi concept link <concept_name> <source_file>
```

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `concept_name` | Yes | Name of the concept to link |
| `source_file` | Yes | Source file whose design file should receive the wikilink |

**Exit codes:**

| Code | Meaning |
|------|---------|
| 0 | Wikilink added successfully, or already linked (no error) |
| 1 | Concept not found, source file not found, or no design file exists |

**Examples:**

```bash
# Link a concept to a source file
lexi concept link change-detection src/lexibrary/archivist/change_checker.py

# Link a concept to multiple files (run once per file)
lexi concept link pydantic-validation src/lexibrary/config/schema.py
lexi concept link pydantic-validation src/lexibrary/artifacts/design_file.py
```

**When to use:** After creating a concept, link it to the source files where the concept is implemented or referenced. This creates a wikilink entry (`[[concept-name]]`) in the design file's frontmatter.

---

## stack post

Create a new Stack Q&A post with an auto-assigned ID.

```
lexi stack post --title <title> --tag <tag> [--bead <id>] [--file <path>] [--concept <name>]
```

**Options:**

| Option | Required | Description |
|--------|----------|-------------|
| `--title <title>` | Yes | Title for the new post |
| `--tag <tag>` | Yes | Tag for the post (repeatable, at least one required) |
| `--bead <id>` | No | Bead ID to associate with the post |
| `--file <path>` | No | Source file reference (repeatable) |
| `--concept <name>` | No | Concept reference (repeatable) |

The post is created at `.lexibrary/stack/ST-NNN-<slug>.md` where NNN is auto-incremented and the slug is derived from the title.

After creation, fill in the `## Problem` and `### Evidence` sections in the generated file.

**Examples:**

```bash
# Create a post about a bug
lexi stack post --title "Config loader silently ignores unknown keys" --tag config --tag bug

# Create a post with file and concept references
lexi stack post --title "Race condition in daemon sweep" --tag daemon --tag concurrency \
  --file src/lexibrary/daemon/service.py \
  --concept daemon-sweep
```

**When to use:** After solving a non-trivial bug or discovering an important pattern. Document the problem and solution so future agents do not have to re-discover it.

---

## stack search

Search Stack posts by query and/or filters.

```
lexi stack search [query] [--tag <tag>] [--scope <path>] [--status <status>] [--concept <name>]
```

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `query` | No | Free-text search query |

**Options:**

| Option | Description |
|--------|-------------|
| `--tag <tag>` | Filter by tag |
| `--scope <path>` | Filter by file scope path |
| `--status <status>` | Filter by status: `open`, `resolved`, `outdated`, `duplicate` |
| `--concept <name>` | Filter by concept name |

**Output:** A table with columns: ID, Status, Votes, Title, Tags.

All filters are AND-combined. You can provide a query with filters, or just filters, or just a query.

**Examples:**

```bash
# Search by text query
lexi stack search "config loader"

# Filter by tag
lexi stack search --tag daemon

# Combine query and filters
lexi stack search "timeout" --tag llm --status open

# Find resolved posts about a concept
lexi stack search --concept change-detection --status resolved
```

**When to use:** Always search the Stack before starting to debug an issue. A solution may already exist.

---

## stack finding

Append a new finding to an existing Stack post.

```
lexi stack finding <post_id> --body <text> [--author <name>]
```

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `post_id` | Yes | Post ID (e.g., `ST-001`) |

**Options:**

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `--body <text>` | Yes | -- | Finding body text |
| `--author <name>` | No | `user` | Author of the finding |

The finding is appended to the post file with an auto-assigned finding number (F1, F2, etc.).

**Examples:**

```bash
# Add a finding to a post
lexi stack finding ST-001 --body "The fix is to increase the timeout in config.yaml to 120 seconds."

# Add a finding with author attribution
lexi stack finding ST-003 --body "This was caused by a race condition in the debouncer." --author claude
```

---

## stack vote

Record an upvote or downvote on a post or a specific finding.

```
lexi stack vote <post_id> <up|down> [--finding <num>] [--comment <text>] [--author <name>]
```

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `post_id` | Yes | Post ID (e.g., `ST-001`) |
| `direction` | Yes | Vote direction: `up` or `down` |

**Options:**

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `--finding <num>` | No | -- | Finding number to vote on (omit to vote on the post itself) |
| `--comment <text>` | For downvotes | -- | Comment explaining the downvote (required for downvotes) |
| `--author <name>` | No | `user` | Author of the vote |

**Examples:**

```bash
# Upvote a post
lexi stack vote ST-001 up

# Upvote a specific finding
lexi stack vote ST-001 up --finding 2

# Downvote with required comment
lexi stack vote ST-003 down --comment "This solution introduces a memory leak"
```

**When to use:** Upvote findings that are correct and helpful. Downvote findings that are incorrect or misleading (always explain why in the comment).

---

## stack accept

Mark a finding as accepted and set the post status to resolved.

```
lexi stack accept <post_id> --finding <num>
```

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `post_id` | Yes | Post ID (e.g., `ST-001`) |

**Options:**

| Option | Required | Description |
|--------|----------|-------------|
| `--finding <num>` | Yes | Finding number to accept |

**Examples:**

```bash
# Accept finding F2 on post ST-001
lexi stack accept ST-001 --finding 2
```

---

## stack view

Display the full content of a Stack post, including all findings, votes, and metadata.

```
lexi stack view <post_id>
```

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `post_id` | Yes | Post ID (e.g., `ST-001`) |

**Output:** A formatted panel showing the post header (title, status, votes, tags, created date, author, file refs, concept refs), problem description, evidence items, and all findings with their votes and comments.

**Examples:**

```bash
# View a post
lexi stack view ST-001
```

---

## stack list

List Stack posts with optional filters.

```
lexi stack list [--status <status>] [--tag <tag>]
```

**Options:**

| Option | Description |
|--------|-------------|
| `--status <status>` | Filter by status: `open`, `resolved`, `outdated`, `duplicate` |
| `--tag <tag>` | Filter by tag |

**Output:** A table with columns: ID, Status, Votes, Title, Tags.

**Examples:**

```bash
# List all posts
lexi stack list

# List only open posts
lexi stack list --status open

# List posts with a specific tag
lexi stack list --tag config
```

---

## search

Search across concepts, design files, and Stack posts in a single query. This is the unified cross-artifact search command.

```
lexi search [query] [--tag <tag>] [--scope <path>]
```

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `query` | No | Free-text search query |

**Options:**

| Option | Description |
|--------|-------------|
| `--tag <tag>` | Filter by tag across all artifact types |
| `--scope <path>` | Filter by file scope path |

At least one of `query`, `--tag`, or `--scope` must be provided.

**Output:** Results grouped by artifact type (concepts, design files, Stack posts) with a formatted Rich table for each type that has matches. When the link graph index is available, search is accelerated with full-text search.

**Examples:**

```bash
# Search for a topic across all artifacts
lexi search "change detection"

# Filter by tag
lexi search --tag validation

# Combine query and scope
lexi search "parser" --scope src/lexibrary/artifacts/

# Search by tag and scope together
lexi search --tag config --scope src/lexibrary/
```

**When to use:**
- Use `search` for **discovery** -- when you want to find all artifacts related to a topic across the entire project
- Use `lookup` for **specific file context** -- when you know which file you want to edit and need its design file and dependents

---

## impact

Show reverse dependents of a source file -- which files import it and would be affected by changes.

```
lexi impact <file> [--depth N] [--quiet]
```

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `file` | Yes | Source file to analyse for reverse dependents |

**Options:**

| Option | Default | Description |
|--------|---------|-------------|
| `--depth` | 1 | Maximum traversal depth (1-3, clamped). Higher values follow transitive dependents. |
| `--quiet` | -- | Output paths only, one per line. Suitable for piping to other tools. |

**What it outputs:**

- A tree of files that depend on the given file, with design file descriptions for each
- Warning indicators when a dependent has an open stack post
- With `--quiet`, outputs bare paths only (one per line, no decoration)

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

**When to use:** After editing a file, run `lexi impact` to understand what other files might be affected by your changes. The post-edit hook runs this automatically at depth 1.

---

## Command Summary

| Command | Purpose |
|---------|---------|
| `lexi orient` | Project orientation: topology, stats, IWH signals |
| `lexi lookup <file\|dir>` | Get design file, conventions, Known Issues, IWH, and dependents |
| `lexi impact <file> [--depth] [--quiet]` | Show reverse dependents (who imports this file) |
| `lexictl index [dir] [-r]` | Generate `.aindex` routing table(s) for a directory |
| `lexi describe <dir> <desc>` | Update a directory's `.aindex` billboard description |
| `lexi concepts [topic]` | List or search concept files |
| `lexi concept new <name> [--tag]` | Create a new concept file |
| `lexi concept link <concept> <file>` | Add a wikilink from a concept to a design file |
| `lexi stack post --title --tag` | Create a new Stack Q&A post |
| `lexi stack search [query] [filters]` | Search Stack posts |
| `lexi stack finding <id> --body` | Add a finding to a Stack post |
| `lexi stack vote <id> <up\|down>` | Vote on a post or finding |
| `lexi stack accept <id> --finding` | Accept a finding (sets status to resolved) |
| `lexi stack view <id>` | Display full post content |
| `lexi stack list [filters]` | List Stack posts with optional filters |
| `lexi search [query] [filters]` | Unified cross-artifact search |

---

## lexi-research Subagent

The `lexi-research` subagent (`.claude/agents/lexi-research.md`) is a specialized deep research agent for debugging and architectural decisions.

**Tools:** Read, Bash (read-only commands only)

**When to use:** For complex bugs requiring synthesis across many Stack posts, design files, and source files. Spawn the subagent with your problem description instead of searching manually.

**Workflow:**
1. Runs `lexi orient` to understand project state
2. Searches Stack posts and design files for relevant context
3. Reads source files to understand the problem
4. Synthesizes findings into a structured analysis
5. Returns findings to the calling agent

**Restrictions:**
- Does not write code or modify files
- Does not consume IWH signals
- Does not post to the Stack -- the calling agent is responsible for posting findings
