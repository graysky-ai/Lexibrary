# Using Stack Q&A

The Stack is a structured knowledge base of problems and solutions stored in `.lexibrary/stack/`. Each Stack post documents a specific issue -- what went wrong, the evidence gathered, and the solution that worked. Posts persist across sessions so the same problem never has to be solved twice.

## Search Before Debugging

Before investing time debugging an issue, always check whether it has already been solved:

```bash
lexi stack search "config loader"
```

This searches post titles and content for matches. The output is a table:

```
                          Stack Posts
ID       Status    Votes  Title                                Tags
ST-001   resolved  3      Config loader silently ignores keys   config, bug
ST-005   open      1      YAML parse error on nested lists      config, yaml
```

You can filter by tag, status, scope, or concept:

```bash
# Find resolved daemon issues
lexi stack search --tag daemon --status resolved

# Find open issues related to a specific file path
lexi stack search --scope src/lexibrary/config/

# Find issues linked to a concept
lexi stack search --concept change-detection

# Combine query and filters
lexi stack search "timeout" --tag llm --status open
```

If you find a relevant resolved post, view the full content:

```bash
lexi stack view ST-001
```

This shows the problem description, evidence, all answers with votes, and which answer was accepted.

## Creating a Post

After solving a non-trivial bug or discovering an important pattern, create a Stack post to preserve the knowledge:

```bash
lexi stack post --title "Race condition in daemon sweep" --tag daemon --tag concurrency
```

You can also link the post to source files and concepts:

```bash
lexi stack post --title "Config loader silently ignores unknown keys" --tag config --tag bug \
  --file src/lexibrary/config/loader.py \
  --concept pydantic-validation
```

The post is created at `.lexibrary/stack/ST-NNN-<slug>.md` with an auto-incremented ID and a template. After creation, fill in the `## Problem` and `### Evidence` sections in the generated file:

```markdown
## Problem

Describe the problem clearly. What was the expected behavior?
What actually happened?

### Evidence

- Error message: `KeyError: 'unknown_setting'`
- Reproduction: Add an unknown key to config.yaml and run `lexictl validate`
- Root cause: Pydantic `extra="ignore"` silently drops unknown keys
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

## Answering Posts

If you find an open Stack post and have a solution, add an answer:

```bash
lexi stack answer ST-005 --body "The YAML parse error occurs because PyYAML requires explicit list indentation. Use 2-space indentation for nested lists."
```

You can specify an author:

```bash
lexi stack answer ST-005 --body "Fixed by updating the YAML loader to use safe_load." --author claude
```

## Voting

Upvote answers that are correct and helpful:

```bash
# Upvote a post
lexi stack vote ST-001 up

# Upvote a specific answer
lexi stack vote ST-001 up --answer 2
```

Downvote answers that are incorrect or misleading (a comment is required):

```bash
lexi stack vote ST-003 down --comment "This solution introduces a memory leak in the daemon loop"
```

Voting surfaces the best answers and helps future agents identify which solutions actually work.

## Accepting Answers

When a post has a correct answer, accept it to mark the post as resolved:

```bash
lexi stack accept ST-001 --answer 2
```

This sets the post status to `resolved` and marks answer A2 as accepted.

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
| `open` | Problem reported, no accepted answer yet |
| `resolved` | An answer has been accepted |
| `outdated` | The problem or solution no longer applies (e.g., code was refactored) |
| `duplicate` | Duplicate of another post (includes `duplicate_of` reference) |

## Example Workflow

You encounter a `TimeoutError` when the LLM provider takes too long during `lexictl update`:

```bash
# 1. Search for existing solutions
lexi stack search "timeout" --tag llm

# 2. Find a relevant post
lexi stack view ST-012

# 3. The accepted answer says to increase llm.timeout in config.yaml
#    (but remember: do not modify config.yaml yourself -- that is an operator action)

# 4. If the existing answer does not fully solve your variant, add your own
lexi stack answer ST-012 --body "For Anthropic models, the timeout also needs to account for the rate limiter backoff. Setting timeout to 120 with max_retries=2 resolves the issue."

# 5. If you solve a new problem, create a post
lexi stack post --title "Rate limiter backoff causes false timeout with Anthropic" --tag llm --tag timeout \
  --file src/lexibrary/llm/rate_limiter.py
```

## See Also

- [lexi Reference](lexi-reference.md) -- full reference for all `stack` subcommands
- [Search](search.md) -- unified search that includes Stack posts alongside concepts and design files
- [Stack Q&A (User Docs)](../user/stack-qa.md) -- operator guide to Stack: post anatomy, frontmatter fields, validation, and link graph integration
