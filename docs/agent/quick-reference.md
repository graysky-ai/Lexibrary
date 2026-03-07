# Quick Reference -- Agent Cheat Sheet

A single-page reference for everything an agent needs when working in a Lexibrary-managed codebase.

---

## Session Start Checklist

1. Run `lexi orient` -- get project topology, library stats, and IWH signal overview in a single command
2. If IWH signals are shown, run `lexi iwh read <dir>` for each directory you plan to work in to consume the signals

---

## Before Editing a File

1. Run `lexi lookup <file>` -- read the design file, conventions, and dependents
2. Review conventions -- follow all listed rules from the `.aindex` hierarchy

---

## After Editing a File

1. Update the design file in `.lexibrary/` -- update description, summary, and interface contract
2. Set `updated_by: agent` in the design file frontmatter

---

## Key Commands

| Command | What It Does | When to Use |
|---------|-------------|-------------|
| `lexi orient` | Show project topology, stats, IWH signals | At session start (first command) |
| `lexi lookup <file\|dir>` | Show design file, conventions, Known Issues, IWH, dependents | Before editing any source file |
| `lexi impact <file>` | Show reverse dependents (who imports it) | After editing a file, to check impact |
| `lexi search <query>` | Search concepts, design files, Stack posts | Exploring a topic or finding related artifacts |
| `lexi search --tag <tag>` | Filter search by tag | Finding all artifacts with a specific tag |
| `lexi search --scope <path>` | Filter search by directory | Narrowing results to a package |
| `lexi concepts [topic]` | List or search concepts | Before architectural decisions |
| `lexi concept new <name> [--tag]` | Create a concept file | When a pattern/term needs documenting |
| `lexi concept link <concept> <file>` | Link concept to a design file | After creating a concept |
| `lexi stack search [query]` | Search Stack posts | Before debugging an issue |
| `lexi stack post --title --tag` | Create a Stack post | After solving a non-trivial bug |
| `lexi stack finding <id> --body` | Add a finding to a post | When you have a solution |
| `lexi stack vote <id> up` | Upvote a post or finding | When a finding is helpful |
| `lexi stack accept <id> --finding <n>` | Accept a finding | When a solution is confirmed |
| `lexi stack view <id>` | View full post content | Reading a post's details |
| `lexi stack list [--status] [--tag]` | List posts with filters | Browsing open issues |
| `lexi index [dir] [-r]` | Generate `.aindex` files | After creating new files/directories |
| `lexi describe <dir> <desc>` | Update a directory billboard | When a directory's purpose changes |

---

## Common Scenarios

### Understanding a file before editing

```bash
lexi lookup src/lexibrary/config/schema.py
# Read the design file, check conventions, note dependents
# Make your edits
# Update the design file in .lexibrary/
```

### Debugging a problem

```bash
# Check if it has been solved before
lexi stack search "timeout" --tag llm

# If found, view the solution
lexi stack view ST-012

# If you solve it yourself, create a post
lexi stack post --title "LLM timeout with large files" --tag llm --tag timeout
```

### Before an architectural decision

```bash
# Check for existing conventions
lexi concepts validation

# Search for related artifacts
lexi search "validation" --scope src/lexibrary/
```

### Creating a new concept

```bash
# Verify no existing concept covers this
lexi concepts "path validation"

# Create the concept
lexi concept new path-validation --tag validation --tag paths

# Edit .lexibrary/concepts/path-validation.md to fill in the definition

# Link to relevant files
lexi concept link path-validation src/lexibrary/cli/lexi_app.py
lexi concept link path-validation src/lexibrary/config/loader.py
```

### Leaving work incomplete

```bash
# Leave a signal for the next agent
lexi iwh write src/lexibrary/config/ --scope incomplete --body "Refactoring config validation. Completed schema.py changes. Still need to update loader.py and defaults.py. Tests in test_schema.py pass."

# Leave a blocked signal
lexi iwh write src/lexibrary/daemon/ --scope blocked --body "Waiting on upstream fix for watchdog race condition."
```

### Picking up where someone left off

```bash
# Run orient to see all pending signals
lexi orient

# Read and consume a signal (deletes it after display)
lexi iwh read src/lexibrary/config/

# Complete the work described in the signal
```

---

## What NOT to Do

- Never run `lexictl` commands (init, update, validate, status, setup, sweep, daemon)
- Never modify `.lexibrary/config.yaml`
- Never delete files from `.lexibrary/` (except `.iwh` after acting on them)
- Never edit `.aindex` files directly (use `lexi describe` instead)
- Never modify staleness metadata (hashes, timestamps) in design files

---

## Further Reading

| Topic | Document |
|-------|----------|
| Session start protocol | [Orientation](orientation.md) |
| Full CLI reference | [lexi Reference](lexi-reference.md) |
| Before-edit workflow | [Lookup Workflow](lookup-workflow.md) |
| After-edit workflow | [Update Workflow](update-workflow.md) |
| Concepts wiki | [Concepts](concepts.md) |
| Stack Q&A | [Stack](stack.md) |
| Cross-artifact search | [Search](search.md) |
| IWH signals | [IWH](iwh.md) |
| What not to do | [Prohibited Commands](prohibited-commands.md) |
