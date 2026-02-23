# lexi CLI Reference

Complete reference for the `lexi` command -- the agent-facing CLI for Lexibrary. Every command, subcommand, flag, and argument is documented here with usage examples.

Run `lexi --help` for a quick overview, or `lexi <command> --help` for any specific command.

---

## lookup

Look up the design file for a source file, including applicable conventions from `.aindex` hierarchy and dependents from the link graph.

```
lexi lookup <file>
```

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `file` | Yes | Path to the source file to look up |

**What it outputs:**

1. **Design file content** -- the full markdown design file including YAML frontmatter (source path, source_hash, generated timestamp, updated_by, wikilinks), summary, interface skeleton, and key details
2. **Staleness warning** -- if the source file's SHA-256 hash does not match the hash stored in the design file frontmatter, a warning is printed suggesting `lexictl update`
3. **Applicable conventions** -- conventions from `.aindex` files walked upward from the file's directory to the scope root. Each convention is shown with its originating directory
4. **Dependents** -- files that import this file (from the link graph, if available)
5. **Also referenced by** -- other inbound references: concept wikilinks, Stack post file refs, design file refs, convention concept refs

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
```

**When to use:** Always run `lexi lookup` before editing a source file. It shows you the file's purpose, interface, conventions to follow, and what depends on it.

---

## index

Generate `.aindex` routing table files for a directory. These provide a billboard summary and file listing for the directory.

```
lexi index [directory] [-r/--recursive]
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
lexi index

# Index a specific directory
lexi index src/lexibrary/config/

# Recursively index all directories under src/
lexi index src/ -r
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

## stack answer

Append a new answer to an existing Stack post.

```
lexi stack answer <post_id> --body <text> [--author <name>]
```

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `post_id` | Yes | Post ID (e.g., `ST-001`) |

**Options:**

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `--body <text>` | Yes | -- | Answer body text |
| `--author <name>` | No | `user` | Author of the answer |

The answer is appended to the post file with an auto-assigned answer number (A1, A2, etc.).

**Examples:**

```bash
# Add an answer to a post
lexi stack answer ST-001 --body "The fix is to increase the timeout in config.yaml to 120 seconds."

# Add an answer with author attribution
lexi stack answer ST-003 --body "This was caused by a race condition in the debouncer." --author claude
```

---

## stack vote

Record an upvote or downvote on a post or a specific answer.

```
lexi stack vote <post_id> <up|down> [--answer <num>] [--comment <text>] [--author <name>]
```

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `post_id` | Yes | Post ID (e.g., `ST-001`) |
| `direction` | Yes | Vote direction: `up` or `down` |

**Options:**

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `--answer <num>` | No | -- | Answer number to vote on (omit to vote on the post itself) |
| `--comment <text>` | For downvotes | -- | Comment explaining the downvote (required for downvotes) |
| `--author <name>` | No | `user` | Author of the vote |

**Examples:**

```bash
# Upvote a post
lexi stack vote ST-001 up

# Upvote a specific answer
lexi stack vote ST-001 up --answer 2

# Downvote with required comment
lexi stack vote ST-003 down --comment "This solution introduces a memory leak"
```

**When to use:** Upvote answers that are correct and helpful. Downvote answers that are incorrect or misleading (always explain why in the comment).

---

## stack accept

Mark an answer as accepted and set the post status to resolved.

```
lexi stack accept <post_id> --answer <num>
```

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `post_id` | Yes | Post ID (e.g., `ST-001`) |

**Options:**

| Option | Required | Description |
|--------|----------|-------------|
| `--answer <num>` | Yes | Answer number to accept |

**Examples:**

```bash
# Accept answer A2 on post ST-001
lexi stack accept ST-001 --answer 2
```

---

## stack view

Display the full content of a Stack post, including all answers, votes, and metadata.

```
lexi stack view <post_id>
```

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `post_id` | Yes | Post ID (e.g., `ST-001`) |

**Output:** A formatted panel showing the post header (title, status, votes, tags, created date, author, file refs, concept refs), problem description, evidence items, and all answers with their votes and comments.

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

## Command Summary

| Command | Purpose |
|---------|---------|
| `lexi lookup <file>` | Get design file, conventions, and dependents for a source file |
| `lexi index [dir] [-r]` | Generate `.aindex` routing table(s) for a directory |
| `lexi describe <dir> <desc>` | Update a directory's `.aindex` billboard description |
| `lexi concepts [topic]` | List or search concept files |
| `lexi concept new <name> [--tag]` | Create a new concept file |
| `lexi concept link <concept> <file>` | Add a wikilink from a concept to a design file |
| `lexi stack post --title --tag` | Create a new Stack Q&A post |
| `lexi stack search [query] [filters]` | Search Stack posts |
| `lexi stack answer <id> --body` | Add an answer to a Stack post |
| `lexi stack vote <id> <up\|down>` | Vote on a post or answer |
| `lexi stack accept <id> --answer` | Accept an answer (sets status to resolved) |
| `lexi stack view <id>` | Display full post content |
| `lexi stack list [filters]` | List Stack posts with optional filters |
| `lexi search [query] [filters]` | Unified cross-artifact search |
