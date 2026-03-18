# Update Workflow -- After Editing a File

After making meaningful changes to a source file, update its design file in `.lexibrary/` so the next agent (or your future self) has accurate context.

## When to Update

Update the design file when your changes affect:

- **What the file does** -- new functionality, changed purpose, removed features
- **The public interface** -- new functions, changed signatures, renamed classes, new constants
- **Key implementation details** -- changed algorithms, new dependencies, architectural decisions
- **Dependencies** -- new imports or removed imports

## When NOT to Update

Let the operator's `lexictl update` handle it instead when:

- **Cosmetic changes** -- formatting, whitespace, comment rewording
- **Bulk refactors** -- renaming a variable across many files (the operator can regenerate all design files at once)
- **You are unsure what to write** -- an inaccurate design file is worse than a stale one

## How to Update

### Step 1: Locate the Design File

Design files live in a mirror tree under `.lexibrary/`. The path mirrors the source file path:

| Source file | Design file |
|-------------|-------------|
| `src/lexibrary/config/schema.py` | `.lexibrary/src/lexibrary/config/schema.py.md` |
| `tests/test_config/test_schema.py` | `.lexibrary/tests/test_config/test_schema.py.md` |

### Step 2: Edit the Design File

Open the design file and update the relevant sections. A design file has this structure:

```markdown
---
description: Short one-line description of what the file does
updated_by: archivist
---

## Summary

Narrative description of the file's purpose and role.

## Interface Contract

Extracted function signatures, class definitions, constants.

## Key Details

Important implementation notes, design decisions.
```

You should update:

- **`description`** in the frontmatter -- keep it a concise one-liner
- **`updated_by`** in the frontmatter -- set this to `agent` (see below)
- **Summary** -- update if the file's purpose or role changed
- **Interface Contract** -- update if you added, removed, or changed public functions/classes
- **Key Details** -- update if you changed important implementation details

### Step 3: Set `updated_by: agent`

Change the `updated_by` field in the YAML frontmatter from `archivist` to `agent`:

```yaml
---
description: Pydantic 2 configuration schema with validation
updated_by: agent
---
```

This tells the system that the design file has been manually maintained. When the operator runs `lexictl update`, the system uses `ChangeLevel` classification to decide whether to overwrite:

- If the source file has only cosmetic changes, the agent-maintained design file is preserved
- If the source file has structural changes, the system may regenerate it (but the operator is warned)

### What NOT to Touch

Do not modify these parts of the design file:

- **Staleness metadata** -- the HTML comment block at the bottom containing `source`, `source_hash`, `interface_hash`, `design_hash`, `generated`, and `generator`. This is managed by `lexictl update`
- **Generated timestamps** -- these track when the LLM last generated the file
- **Source hashes** -- these are SHA-256 hashes used for change detection

Modifying these fields will confuse the change detection system and may cause unnecessary regeneration or missed updates.

## Example

Suppose you add a new validation method to `src/lexibrary/config/schema.py`. After editing the source file:

1. Open `.lexibrary/src/lexibrary/config/schema.py.md`
2. Update the summary to mention the new validation
3. Add the new method signature to the Interface Contract section
4. Set `updated_by: agent` in the frontmatter
5. Save the file

```yaml
---
description: Pydantic 2 configuration schema with field validation and custom validators
updated_by: agent
---
```

```markdown
## Summary

Defines the LexibraryConfig Pydantic model and all sub-models for
.lexibrary/config.yaml. Includes field-level validation for paths,
token budgets, and sweep settings.

## Interface Contract

class LexibraryConfig(BaseModel):
    scope_root: str = "."
    project_name: str = ""
    ...
```

## Summary Checklist

After editing a source file:

1. Open the corresponding design file in `.lexibrary/`
2. Update the description, summary, and interface contract as needed
3. Set `updated_by: agent` in the frontmatter
4. Do not touch staleness metadata, hashes, or timestamps

## See Also

- [Lookup Workflow](lookup-workflow.md) -- what to do before editing a file
- [Prohibited Commands](prohibited-commands.md) -- why you should not run `lexictl update` yourself
- [Design File Generation (User Docs)](../user/design-file-generation.md) -- how `lexictl update` generates design files and how ChangeLevel classification works
