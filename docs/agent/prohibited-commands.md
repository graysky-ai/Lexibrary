# Prohibited Commands and Actions

Lexibrary splits its CLI into two tools: `lexi` (for agents) and `lexictl` (for operators). This separation exists for important reasons. This document explains what you must not do and why.

## Never Run `lexictl` Commands

The entire `lexictl` CLI is off-limits for agents. This includes:

| Command | What It Does | Why It Is Prohibited |
|---------|-------------|---------------------|
| `lexictl init` | Initializes Lexibrary in a project | Runs a multi-step wizard that creates config, sets up directories, and injects agent rules. Requires operator decisions. |
| `lexictl update` | Regenerates design files using LLM | Makes LLM API calls (costs money, takes time). Can overwrite agent-maintained design files. Operator should control when and what gets regenerated. |
| `lexictl validate` | Runs validation checks | Outputs diagnostics the operator uses for maintenance. Not harmful, but creates noise and is not part of the agent workflow. |
| `lexictl status` | Shows library health dashboard | Read-only, but intended for operator situational awareness, not agent consumption. |
| `lexictl setup` | Updates agent environment rules | Modifies environment-specific files (CLAUDE.md, .cursor/rules/). Operator must control what rules are injected. |
| `lexictl sweep` | Runs a one-time update sweep | Same as `update` -- makes LLM calls, expensive, operator-controlled. |
| `lexictl daemon` | Starts/stops the background daemon | Controls a persistent process. Operator manages daemon lifecycle. |

### Why This Matters

`lexictl` commands are expensive operations:

1. **LLM API calls.** `lexictl update` sends source files to an LLM provider to generate design files. Each call costs tokens and takes seconds to minutes. Running this unnecessarily wastes money and time.

2. **Operator oversight.** The operator decides when to regenerate design files, which validation issues to address, and how to configure the daemon. Agents should not make these decisions autonomously.

3. **Multi-agent conflicts.** If multiple agents run `lexictl update` simultaneously, they may overwrite each other's design files or create race conditions with the daemon.

## Never Modify `.lexibrary/config.yaml`

The configuration file controls how Lexibrary behaves -- LLM provider settings, token budgets, ignore patterns, daemon configuration, and more. Changing it can:

- Break LLM API calls (wrong provider, bad model name, missing API key)
- Change what files get indexed (scope_root, ignore patterns)
- Alter design file generation behavior (token budgets, AST settings)
- Disrupt the daemon (sweep intervals, debounce timing)

If you believe a config change is needed, document it in a Stack post or IWH file for the operator.

## Never Delete Files from `.lexibrary/` Directly

The `.lexibrary/` directory is managed by Lexibrary. Deleting files can:

- Remove design files that other agents depend on for context
- Break wikilink references between concepts and design files
- Invalidate the link graph index (which references file paths)
- Remove Stack posts with valuable problem/solution knowledge

The only exception is `.iwh` files, which you should delete after acting on them (see [IWH Signals](iwh.md)).

## Never Modify `.aindex` Files Directly

`.aindex` files are routing tables that contain directory billboards, file listings, and local conventions. They have a specific format that the system expects.

To update a directory's billboard description, use the correct command:

```bash
# Correct: use lexi describe
lexi describe src/lexibrary/config/ "Configuration schema, loader, and defaults"

# Wrong: do not edit the .aindex file directly
```

`lexi describe` ensures the `.aindex` file format remains valid and the billboard is updated without disturbing the rest of the file's content.

## Summary of Restrictions

| Action | Allowed? | Alternative |
|--------|----------|-------------|
| Run `lexi` commands | Yes | -- |
| Run `lexictl` commands | No | Ask the operator or document the need in a Stack post / IWH |
| Read files in `.lexibrary/` | Yes | Use `lexi lookup` for design files |
| Edit design files in `.lexibrary/` | Yes | Follow the [Update Workflow](update-workflow.md) |
| Modify `.lexibrary/config.yaml` | No | Document the needed change for the operator |
| Delete files from `.lexibrary/` | No | Only delete `.iwh` files after acting on them |
| Edit `.aindex` files directly | No | Use `lexi describe` to update billboards |
| Create concept files | Yes | Use `lexi concept new` |
| Create Stack posts | Yes | Use `lexi stack post` |
| Create IWH files | Yes | Write `.iwh` manually or programmatically |

## See Also

- [lexi Reference](lexi-reference.md) -- the complete set of commands you can use
- [Update Workflow](update-workflow.md) -- how to properly update design files
- [Quick Reference](quick-reference.md) -- cheat sheet including the restrictions
- [lexictl Reference (User Docs)](../user/lexictl-reference.md) -- operator CLI reference explaining what each prohibited command does
