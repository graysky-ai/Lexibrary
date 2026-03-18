# Using the Stack Knowledge Base

The Stack is a structured knowledge base of issues and solutions stored in `.lexibrary/stack/`. Each Stack post documents a specific issue -- what went wrong, what was tried, and the solution that worked. Posts persist across sessions so the same issue never has to be solved twice.

## Search Before Debugging

Before investing time debugging an issue, always check whether it has already been solved:

```bash
lexi stack search "config loader"
```

This searches post titles, problem descriptions, context, attempts, and finding bodies for matches. The output is a table:

```
                          Stack Posts
ID       Status    Votes  Title                                Tags
ST-001   resolved  3      Config loader silently ignores keys   config, bug
ST-005   open      1      YAML parse error on nested lists      config, yaml
```

You can filter by tag, status, scope, concept, or resolution type:

```bash
# Find resolved sweep issues
lexi stack search --tag sweep --status resolved

# Find issues related to a specific file path
lexi stack search --scope src/lexibrary/config/

# Find issues linked to a concept
lexi stack search --concept change-detection

# Find only workarounds (not permanent fixes)
lexi stack search --resolution-type workaround

# Combine query and filters
lexi stack search "timeout" --tag llm --status open
```

If you find a relevant resolved post, view the full content:

```bash
lexi stack view ST-001
```

This shows the problem description, context, evidence, attempts, all findings with votes, resolution type, and which finding was accepted. Pay special attention to the **Attempts** section -- it documents approaches that were already tried and failed, saving you from repeating them.

## Creating a Post

After solving a non-trivial bug or discovering an important pattern, create a Stack post to preserve the knowledge.

### One-Shot Post Creation (Recommended for Agents)

Use the one-shot workflow to create a fully populated post in a single command:

```bash
lexi stack post --title "Race condition in sweep watch mode" --tag sweep --tag concurrency \
  --problem "Concurrent sweep iterations cause duplicate index entries." \
  --context "Running lexictl sweep --watch with short interval." \
  --evidence "Duplicate ST-* entries in link graph after concurrent sweep" \
  --evidence "Race window is ~200ms between file scan and index write" \
  --attempts "Tried file-level locking but it caused deadlocks" \
  --attempts "Tried debouncing sweep trigger but window was too narrow"
```

To also record the solution in one step:

```bash
lexi stack post --title "Race condition in sweep watch mode" --tag sweep --tag concurrency \
  --problem "Concurrent sweep iterations cause duplicate index entries." \
  --context "Running lexictl sweep --watch with short interval." \
  --attempts "Tried file-level locking but it caused deadlocks" \
  --finding "Added a sweep-in-progress flag that prevents overlapping sweep iterations." \
  --resolve --resolution-type fix
```

This creates the post, appends finding F1, marks it accepted, sets the status to `resolved`, and records the resolution type -- all in one command.

### Scaffold Mode (Interactive Editing)

If you prefer to fill in sections manually, omit the content flags:

```bash
lexi stack post --title "Config loader silently ignores unknown keys" --tag config --tag bug
```

This creates a post with all four body sections scaffolded with HTML comment placeholders. Edit the file to fill in the sections.

### Additional Options

```bash
# Link to relevant source files
lexi stack post --title "Config loader silently ignores unknown keys" --tag config --tag bug \
  --file src/lexibrary/config/loader.py

# Link to a concept
lexi stack post --title "Pattern for retry logic" --tag resilience \
  --concept retry-pattern

# Link to a bead (work item)
lexi stack post --title "Migration script fails on empty tables" --tag migration \
  --bead lexibrary-42.3
```

### When to Create a Post

Create a Stack post when:

- **You solved a bug that took significant effort.** If it took you more than a few minutes to figure out, it is worth documenting.
- **The solution was non-obvious.** If the fix required understanding something subtle about the codebase, document it.
- **The issue might recur.** If the bug was caused by a pattern that could easily be repeated, create a post so the next agent is warned.
- **You discovered a workaround.** If something does not work as expected and you found a workaround, document both the problem and the workaround.

### When NOT to Create a Post

Do not create a post for:

- Trivial typo fixes or obvious errors
- Issues that are immediately clear from reading the error message
- Problems caused by your own misunderstanding that would not affect other agents

## Writing Good Attempts

The **Attempts** section is one of the most valuable parts of a Stack post. It saves future agents from repeating approaches that do not work. When documenting attempts:

- Describe what you tried and why it seemed reasonable
- Explain why it did not work or what went wrong
- Each attempt should be a separate bullet item passed via `--attempts`

```bash
lexi stack post --title "FTS search returns stale results" --tag search --tag fts \
  --problem "Full-text search returns results for deleted Stack posts." \
  --attempts "Tried rebuilding FTS index on every query -- too slow (>2s per search)" \
  --attempts "Tried DELETE trigger on stack table -- FTS5 does not support triggers" \
  --finding "Added a post-deletion step that removes the FTS row by rowid." \
  --resolve --resolution-type fix
```

## Adding Findings to Existing Posts

If you find an open Stack post and have a solution, add a finding:

```bash
lexi stack finding ST-005 --body "The YAML parse error occurs because PyYAML requires explicit list indentation. Use 2-space indentation for nested lists."
```

You can specify an author:

```bash
lexi stack finding ST-005 --body "Fixed by updating the YAML loader to use safe_load." --author claude
```

## Voting

Upvote findings that are correct and helpful:

```bash
# Upvote a post
lexi stack vote ST-001 up

# Upvote a specific finding
lexi stack vote ST-001 up --finding 2
```

Downvote findings that are incorrect or misleading (a comment is required):

```bash
lexi stack vote ST-003 down --comment "This solution introduces a memory leak in the sweep loop"
```

Voting surfaces the best findings and helps future agents identify which solutions actually work.

## Accepting Findings

When a post has a correct finding, accept it to mark the post as resolved:

```bash
lexi stack accept ST-001 --finding 2
```

You can also classify the resolution:

```bash
lexi stack accept ST-001 --finding 2 --resolution-type fix
```

Valid resolution types: `fix`, `workaround`, `wontfix`, `cannot_reproduce`, `by_design`.

## Listing Posts

To browse all posts or filter by status/tag:

```bash
# List all posts
lexi stack list

# List only open posts
lexi stack list --status open

# List posts with a specific tag
lexi stack list --tag config
```

## Post Lifecycle

Posts have four statuses:

| Status | Meaning |
|--------|---------|
| `open` | Issue reported, no accepted finding yet |
| `resolved` | A finding has been accepted |
| `outdated` | The issue or solution no longer applies (e.g., code was refactored) |
| `duplicate` | Duplicate of another post (includes `duplicate_of` reference) |

## Example Workflow

You encounter a `TimeoutError` when the LLM provider takes too long during `lexictl update`:

```bash
# 1. Search for existing solutions
lexi stack search "timeout" --tag llm

# 2. Find a relevant post
lexi stack view ST-012

# 3. Check the Attempts section -- what has already been tried?
#    The accepted finding says to increase llm.timeout in config.yaml
#    (but remember: do not modify config.yaml yourself -- that is an operator action)

# 4. If the existing finding does not fully solve your variant, add your own
lexi stack finding ST-012 --body "For Anthropic models, the timeout also needs to account for the rate limiter backoff. Setting timeout to 120 with max_retries=2 resolves the issue."

# 5. If you solve a new issue entirely, create a one-shot post
lexi stack post --title "Rate limiter backoff causes false timeout with Anthropic" --tag llm --tag timeout \
  --problem "Rate limiter backoff delay is not accounted for in the LLM timeout calculation." \
  --context "Running lexictl update with Anthropic provider under rate limiting." \
  --evidence "Timeout fires after 60s but backoff adds 30s of wait time" \
  --attempts "Tried increasing timeout to 120s -- worked but masks real timeout issues" \
  --finding "Added backoff duration to the timeout calculation in rate_limiter.py" \
  --resolve --resolution-type fix \
  --file src/lexibrary/llm/rate_limiter.py
```

## See Also

- [lexi Reference](lexi-reference.md) -- full reference for all `stack` subcommands
- [Search](search.md) -- unified search that includes Stack posts alongside concepts and design files
- [Stack Knowledge Base (User Docs)](../user/stack-qa.md) -- operator guide to Stack: post anatomy, frontmatter fields, validation, and link graph integration
