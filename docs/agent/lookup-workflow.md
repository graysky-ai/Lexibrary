# Lookup Workflow -- Before Editing a File

Before editing any source file, run `lexi lookup` to understand what you are about to change. This is the single most important habit for making safe, well-informed edits.

## The Command

```bash
lexi lookup <file>
```

Pass the path to the source file you plan to edit. The path can be absolute or relative to your current working directory.

```bash
lexi lookup src/lexibrary/config/schema.py
```

## What the Output Contains

The output has up to five sections, each providing a different kind of context.

### 1. Design File Content

The full design file for the source file, including:

- **YAML frontmatter** -- `description` (what the file does) and `updated_by` (either `archivist` for LLM-generated or `agent` for agent-maintained)
- **Summary** -- a narrative description of the file's purpose and role in the project
- **Interface contract** -- extracted function signatures, class definitions, constants, and their docstrings
- **Dependencies** -- files this file imports
- **Dependents** -- files that import this file (from frontmatter, if populated)
- **Wikilinks** -- `[[concept-name]]` references linking to relevant concept files
- **Tags** -- classification tags for searchability
- **Stack refs** -- references to related Stack Q&A posts

The design file gives you the complete picture of what the file does, how it fits into the project, and what conventions it follows.

### 2. Staleness Warning

If the source file's SHA-256 hash does not match the hash stored in the design file's metadata, a warning is printed:

```
Warning: Source file has changed since the design file was last generated.
Advise user to run lexictl update src/lexibrary/config/schema.py to refresh.
```

This means the design file may not reflect the current state of the source. The information is still useful -- just be aware it may be outdated. Do not run `lexictl update` yourself; that is an operator command.

### 3. Applicable Conventions

Conventions are inherited rules defined in `.aindex` files. The lookup command walks upward from the file's directory to the scope root, collecting conventions from every `.aindex` file along the way.

Each convention is shown with its originating directory:

```
## Applicable Conventions

**From `src/lexibrary/config/`:**

- All config models use Pydantic 2 BaseModel with model_config
- Field defaults must match defaults.py

**From `src/lexibrary/`:**

- from __future__ import annotations in every module
- Use rich.console.Console for output, never bare print()
```

These conventions are rules you must follow when editing the file. They represent project-wide and directory-specific standards.

### 4. Dependents (Imports This File)

When the link graph index is available, the lookup command shows which files import the file you are looking up:

```
## Dependents (imports this file)

- src/lexibrary/config/loader.py
- src/lexibrary/init/wizard.py
- src/lexibrary/cli/lexictl_app.py
```

This tells you what will be affected by your changes. If you modify a function signature or change a class interface, these files may need updates too.

### 5. Also Referenced By

Other inbound references beyond direct imports:

```
## Also Referenced By

- [[pydantic-validation]] (concept wikilink)
- ST-003-config-loader-silently-ignores-unknown-keys (stack post)
```

These are cross-references from concepts, Stack posts, and other design files. They provide additional context about how the file is discussed and documented across the project.

## How to Use This Information

Follow this checklist after running `lexi lookup`:

1. **Read the summary and interface contract.** Understand what the file does before changing it.
2. **Check the conventions.** Make sure your changes follow the listed rules.
3. **Review the dependents.** If you are changing a public interface (function signature, class API, exported constant), check whether dependents need updating.
4. **Note any staleness warning.** If present, the design file may be outdated -- rely on the source file itself for the current state, but use the design file for architectural context.
5. **Check wikilinks and Stack refs.** If a concept or Stack post is referenced, read it for additional context about design decisions or known issues.

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Design file found and displayed |
| 1 | File is outside `scope_root`, or no design file exists |

If exit code 1 occurs because no design file exists, the file has not yet been indexed. You can still edit it, but you will not have the context that a design file provides. The operator can generate one with `lexictl update`.

## Examples

```bash
# Look up before editing a config module
lexi lookup src/lexibrary/config/schema.py

# Look up before editing a CLI command
lexi lookup src/lexibrary/cli/lexi_app.py

# Look up a test file to understand what it covers
lexi lookup tests/test_config/test_schema.py
```

## See Also

- [Update Workflow](update-workflow.md) -- what to do after editing a file
- [lexi Reference](lexi-reference.md) -- full `lookup` command reference
- [Orientation](orientation.md) -- session start protocol (runs before any lookups)
- [Design File Generation (User Docs)](../user/design-file-generation.md) -- how design files are created and how change detection works
