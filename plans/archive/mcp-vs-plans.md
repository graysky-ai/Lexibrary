# MCP vs Slash Commands: Analysis

> **Question:** Should Lexibrary expose its capabilities via MCP tools, slash commands (skills), or both?
> **Date:** 2026-02-25

---

## The Two Approaches

### Slash Commands (Current)

Lexibrary generates skill files (`.claude/commands/lexi-*.md`, `.cursor/skills/lexi.md`) that the agent can invoke as `/lexi-lookup`, `/lexi-search`, etc. Under the hood, these expand to prompts that tell the agent to run `Bash(lexi ...)` commands.

### MCP Tools (Proposed)

Lexibrary runs as an MCP server, exposing `lexi_lookup`, `lexi_search`, etc. as native tools in the agent's tool list. The agent calls them the same way it calls `Read` or `Grep`.

---

## Comparison

| Dimension | Slash Commands | MCP Tools |
|-----------|---------------|-----------|
| **Discovery** | Agent must read rules or user must type `/lexi-*` | Tools appear in agent's tool list automatically |
| **Invocation** | User-initiated (`/lexi-lookup`) or agent reads rule and shells out | Agent can call autonomously during planning |
| **Data format** | Rich terminal output (needs parsing) | Structured JSON (native to tool protocol) |
| **Latency** | Shell spawn + CLI startup (~200-500ms) | Direct function call via stdio (~50-100ms) |
| **Permission model** | Needs `Bash(lexi *)` pre-approval | MCP tools are pre-approved by server config |
| **Error handling** | Exit codes + stderr (agent must interpret) | Structured error responses in protocol |
| **Environment support** | All (any agent can read a markdown file) | Claude Code, Cursor, VS Code, Windsurf (MCP-capable only) |
| **Maintenance** | One skill file per command per environment | One server, all tools in one place |
| **Context window cost** | Skill expansion injects prompt text | Tool schema is compact; results are structured |

---

## Where Each Wins

### Slash Commands Win When:

1. **The environment doesn't support MCP** — Generic/Codex/Aider fallback needs markdown instructions. Slash commands (or their equivalent: embedded rules) are the universal baseline.

2. **The workflow is multi-step** — `/lexi-orient` involves reading START_HERE.md, checking IWH signals, and running status. This is a scripted sequence, not a single tool call. Slash commands are natural for orchestrating multi-step workflows.

3. **The user wants to trigger it explicitly** — `/lexi-search auth` is a natural user gesture. MCP tools are agent-initiated; users don't type tool names.

4. **You need rich prompt context** — Slash commands can include instructions like "review all results before proceeding" or "if no results, try broadening the search." MCP tool descriptions are short and factual.

### MCP Tools Win When:

1. **The agent needs to decide autonomously** — When an agent is about to edit a file, it should call `lexi_lookup` without being told. MCP tools are in the planner's search space; slash commands require the agent to remember a rule.

2. **Structured data matters** — `lexi_lookup` returning JSON means the agent can reason over `conventions: [...]` and `stale: true` programmatically instead of parsing markdown tables.

3. **Latency matters** — Hooks that augment search need to be fast. MCP stdio calls avoid shell spawn overhead.

4. **Tool composition matters** — An agent can chain `lexi_lookup` → `Read` → `Edit` in one planning step. With bash commands, each step requires the agent to construct a shell command string.

5. **Reducing context window pollution** — Slash command expansions inject prompt text. MCP tool schemas are declared once at session start and referenced by name thereafter.

---

## The Real Question: Agent Autonomy

The fundamental difference is about **who initiates**:

- **Slash commands** are user-driven or rule-driven. The agent uses them because a human typed `/lexi-search` or because CLAUDE.md says "run `lexi lookup` before editing."
- **MCP tools** are agent-driven. The agent uses them because they're in its tool list and the tool description matches what it's trying to do.

For Lexibrary's goal of becoming the default search mechanism, **MCP is the stronger play**. An agent that sees `lexi_lookup` as a native tool is more likely to call it unprompted than one that has to remember a CLAUDE.md rule and construct a bash command.

But MCP alone isn't enough. Agents don't call every available tool — they call tools when the description matches their current need. If the agent is looking for "where is class X defined?" it will still reach for Grep because Grep's description matches that intent better than `lexi_search`'s description.

---

## Recommendation: Both, Layered

```
Layer 1 (Universal):    Rules in CLAUDE.md / .cursor/rules / AGENTS.md
                        "Run lexi lookup before editing" — works everywhere

Layer 2 (Enhanced):     Slash commands / skills
                        User-triggered workflows, multi-step sequences
                        "/lexi-orient" for session start

Layer 3 (Native):       MCP tools (where supported)
                        Agent-autonomous lookup, search, concepts
                        Structured data, low latency

Layer 4 (Automatic):    Hooks
                        Pre-edit lookup, post-search augmentation
                        Safety net — fires regardless of agent behavior
```

### What to build in order:

1. **Keep slash commands** — they're already built, work everywhere, and cost nothing to maintain. They remain the fallback for non-MCP environments and the entry point for user-initiated workflows.

2. **Build MCP server** — expose the core read-only tools (`lookup`, `search`, `concepts`, `status`). This is the highest-leverage addition for agent autonomy.

3. **Keep hooks** — hooks are the only mechanism that fires *regardless* of what the agent decides to do. Even with perfect MCP integration, the pre-edit hook ensures lookup always happens. Hooks are the safety net; MCP and slash commands are the happy path.

4. **Let adoption data decide** — if agents consistently call MCP tools, reduce the rule verbosity in CLAUDE.md. If they don't, strengthen the rules. The layered approach means you can tune without breaking anything.

---

## What Not to Do

- **Don't remove bash commands** — MCP is an additional surface, not a replacement. The `lexi` CLI remains the universal interface that hooks, scripts, CI, and non-MCP agents all use.
- **Don't duplicate tool descriptions in rules** — if MCP tools exist, the CLAUDE.md rules should say "use the `lexi_lookup` tool" not "run `Bash(lexi lookup ...)`." Let the agent use the native tool path.
- **Don't over-invest in MCP before measuring** — build the minimal server (2-3 tools), ship it, observe whether agents actually prefer it over bash. Expand based on data.
