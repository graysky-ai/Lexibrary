---
name: lexi-stack
description: Stack Q&A for debugging. Use before debugging to check for existing solutions and after solving bugs to document findings.
license: MIT
compatibility: Requires lexi CLI.
metadata:
  author: lexibrary
  version: "1.0"
---

Search for existing solutions before debugging and document solved bugs so
future sessions do not repeat the same investigation.

## When to use

- Before starting to debug an issue — search first to avoid repeating work
- After solving a non-trivial bug — post the solution so the next agent benefits
- When adding a new finding to an existing open post

## Steps

1. **Search before you dig** — run `lexi stack search <query>` with keywords
   that describe the symptom or area. Read any matching posts before writing
   a single line of debug code.

2. **If no matching post exists**, proceed with your investigation. Keep notes
   on approaches that did not work — these become your `--attempts` value.

3. **After solving a bug**, post the result immediately while context is fresh:
   - Include `--problem` to describe the symptom.
   - Include `--attempts` to list dead ends — this is the most valuable field.
   - Include `--resolve` to mark the post as solved.
   - Include `--resolution-type fix` (or `workaround`, `wontfix`) as appropriate.

4. **If you have a new finding on an existing open post** — use
   `lexi stack finding <post-id>` rather than creating a duplicate post.

5. **For complex multi-post research** — delegate to the `lexi-research`
   subagent instead of chaining many `lexi stack search` calls manually.

## Examples

Search before debugging:
```
lexi stack search "config loader YAML validation error"
lexi stack search "pathspec gitwildmatch pattern"
```

Post a solved bug:
```
lexi stack post \
  --title "Config loader rejects valid YAML when anchor tags are present" \
  --tag config loader \
  --problem "PyYAML raises ScannerError on YAML anchors during config load" \
  --attempts "Tried upgrading PyYAML — version was not the issue. Tried disabling strict mode — no strict flag exists." \
  --finding "The safe_load call strips anchor support; switch to full_load for user config files." \
  --resolve \
  --resolution-type fix
```

Add a finding to an open post:
```
lexi stack finding post-42 \
  --body "Reproduced on Python 3.12 only; 3.11 is unaffected."
```

## Edge cases

- **Always include `--attempts`** — an empty attempts field is a missed
  opportunity. Even one-line notes about what you ruled out help future agents.
- **Use `--resolve` at post time** when the issue is already solved. A post
  created and immediately resolved is better than leaving a ghost open post.
- **Do not create duplicate posts.** Run `lexi stack search` first; add a
  finding to the existing post if one covers the same root cause.
- **Delegate large research tasks.** If synthesising findings requires reading
  five or more stack posts plus multiple concepts, use the `lexi-research`
  subagent. The coding agent posts the final findings — `lexi-research` does not.
