# Unified Search

The `lexi search` command searches across all artifact types -- concepts, design files, and Stack posts -- in a single query. It is the primary discovery tool for finding everything the project knows about a topic.

## The Command

```bash
lexi search [query] [--tag <tag>] [--scope <path>]
```

At least one of `query`, `--tag`, or `--scope` must be provided.

## What It Searches

Search results are grouped by artifact type:

- **Concepts** -- matched by title, aliases, tags, and body text
- **Design files** -- matched by source path, description, and tags
- **Stack posts** -- matched by title, tags, problem description, and findings

Each group is displayed as a separate table. Groups with no matches are omitted.

## Filters

### Free-text Query

```bash
lexi search "change detection"
```

Matches against titles, descriptions, summaries, and body text across all artifact types. When the link graph index is available, search uses FTS5 full-text search for relevance-ranked results.

### Tag Filter

```bash
lexi search --tag validation
```

Filters to only artifacts tagged with the specified tag. When the link graph index is available, tag search uses the index for fast O(1) lookups.

### Scope Filter

```bash
lexi search --scope src/lexibrary/config/
```

Filters to only artifacts whose source path starts with the given prefix. This is useful for narrowing results to a specific package or directory. Note: concepts are not file-scoped, so they are omitted when a scope filter is active.

### Combining Filters

Filters are AND-combined. Any combination works:

```bash
# Query + tag
lexi search "loader" --tag config

# Query + scope
lexi search "parser" --scope src/lexibrary/artifacts/

# Tag + scope
lexi search --tag config --scope src/lexibrary/

# All three
lexi search "validation" --tag config --scope src/lexibrary/config/
```

## Search vs Lookup

These two commands serve different purposes:

| | `lexi search` | `lexi lookup` |
|---|---|---|
| **Purpose** | Discovery -- find all artifacts related to a topic | Context -- get full design file for a specific source file |
| **Input** | A query, tag, or scope | A specific file path |
| **Output** | Tables of matching concepts, design files, and Stack posts | Full design file content + conventions + dependents |
| **When to use** | Exploring a topic or finding related artifacts | Looking up a specific file before editing |

### When search is the right tool

- Exploring how a feature works across the codebase
- Finding all files related to a topic (e.g., "what touches config?")
- Looking for a Stack post about a specific error or pattern
- Checking for existing concepts before making an architectural decision

### When lookup is the right tool

- Knowing exactly which file is about to be edited
- Needing the full design file with conventions and dependents
- Checking a specific file's staleness status

## Link Graph Acceleration

When the link graph index (`.lexibrary/index.db`) is available, search is accelerated:

- **Tag searches** use the `tags` table for O(1) lookups instead of scanning all artifact files
- **Free-text searches** use FTS5 full-text search for relevance-ranked results instead of substring matching

When the link graph is not available, search falls back to scanning artifact files directly. Results are the same, but scanning is slower for large projects.

The link graph is used automatically -- no configuration is needed. It is built during `lexictl update`.

## How Agents Use Search

Agents use `lexi search` as part of their standard workflow:

- **Before architectural decisions:** Agents search for existing patterns, conventions, and prior art across all artifact types to avoid reinventing solutions.
- **Before debugging:** Agents search Stack posts for known solutions to similar problems.
- **During exploration:** When navigating unfamiliar parts of the codebase, agents use search to discover related artifacts and understand how components connect.

The agent rules in CLAUDE.md instruct agents to search before making decisions and before starting to debug.

## Running Search Manually

Operators and team members can use `lexi search` directly to explore the knowledge base:

```bash
# Find everything related to authentication
lexi search "authentication"

# Find all artifacts tagged with "config"
lexi search --tag config

# Find design files in a specific directory
lexi search --scope src/lexibrary/config/

# Find Stack posts about a specific error
lexi search "timeout" --tag bug
```

Search results include artifact paths, so specific results can be explored further using `lexi lookup` (for design files), `lexi concept view` (for concepts), or `lexi stack view` (for Stack posts).

## Example Output

```bash
lexi search "config"
```

```
                     Concepts
Name                  Status  Tags            Summary
pydantic-validation   active  config, schema  Pydantic 2 BaseModel validation...

                     Design Files
Source                                Description                    Tags
src/lexibrary/config/schema.py       Pydantic 2 configuration...    config
src/lexibrary/config/loader.py       YAML config file loader...     config
src/lexibrary/config/defaults.py     Default config values...       config

                     Stack
ID       Status    Votes  Title                               Tags
ST-001   resolved  3      Config loader silently ignores keys  config, bug
```

## Related Documentation

- [CLI Reference](cli-reference.md) -- Full `search` command reference
- [Concepts](concepts.md) -- How the concepts wiki works
- [Stack](stack.md) -- How Stack Q&A works
- [Link Graph](link-graph.md) -- How the SQLite index accelerates search queries
