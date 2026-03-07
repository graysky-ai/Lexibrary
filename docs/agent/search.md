# Unified Search

The `lexi search` command searches across all three artifact types -- concepts, design files, and Stack posts -- in a single query. Use it when you want to discover everything the project knows about a topic.

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

Filters are AND-combined. You can use any combination:

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
| **When to use** | When you want to explore or find something | When you know which file you will edit |

**Use `search` when:**
- You are new to the codebase and want to understand how a feature works
- You want to find all files related to a topic (e.g., "what touches config?")
- You are looking for a Stack post about a specific error
- You want to find concepts before making an architectural decision

**Use `lookup` when:**
- You know exactly which file you are about to edit
- You need the full design file with conventions and dependents
- You want to check a specific file's staleness status

## Link Graph Acceleration

When the link graph index (`.lexibrary/index.db`) is available, search is accelerated:

- **Tag searches** use the `tags` table for O(1) lookups instead of scanning all artifact files
- **Free-text searches** use FTS5 full-text search for relevance-ranked results instead of substring matching

When the link graph is not available, search falls back to scanning artifact files directly. Results are the same, but scanning is slower for large projects.

You do not need to do anything to use the link graph -- the `lexi search` command detects and uses it automatically.

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

## See Also

- [lexi Reference](lexi-reference.md) -- full `search` command reference
- [Concepts](concepts.md) -- detailed guide to using the concepts wiki
- [Stack](stack.md) -- detailed guide to using Stack Q&A
- [Link Graph (User Docs)](../user/link-graph.md) -- how the SQLite index accelerates search queries
