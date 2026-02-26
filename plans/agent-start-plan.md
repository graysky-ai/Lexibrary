# Plan: Hook-Based Agent Onboarding

> **Status**: Superseded by [`plans/start-here-dismantling.md`](start-here-dismantling.md).
>
> After the START_HERE dismantling, the generated document will be slim enough
> (~300 tokens) that agents can read it directly without hook injection. The
> hook mechanism pattern (SessionStart/SubagentStart context injection) remains
> valuable -- extract into a future `plans/hook-based-context-injection.md`
> if/when needed for the agent rule template system.
>
> **What was preserved**: The conditional filtering by agent type, the tiered
> context budget analysis (15/50/240 lines), and the hook output format
> (`hookSpecificOutput.additionalContext`) are documented in the dismantling
> plan's reconciliation section for future reference.

Deterministically inject `blueprints/START_HERE.md` context into agents via hooks,
replacing the current CLAUDE.md instruction that agents may skip.

## Background

Today, CLAUDE.md line 42 says "Read `blueprints/START_HERE.md` at the start of
every session." Agents frequently ignore this and jump straight into source files.
Hooks give us deterministic injection — the agent receives the context whether it
asks for it or not.

## Approach

Use two hooks:
1. **`SessionStart`** — inject blueprints context into the main session
2. **`SubagentStart`** — inject blueprints context into sub-agents

Both hooks output `additionalContext` in their JSON response, which Claude Code
adds to the agent's context automatically.

## Implementation

### 1. Create hook scripts

**`.claude/hooks/inject-blueprints.sh`** — shared script for both events:

```bash
#!/bin/bash
INPUT=$(cat)
EVENT=$(echo "$INPUT" | jq -r '.hook_event_name')
AGENT_TYPE=$(echo "$INPUT" | jq -r '.agent_type // empty')
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"

# --- Conditional filtering (SubagentStart only) ---
# Skip injection for non-coding agent types that don't need blueprints.
# Built-in agents like Explore and Plan are read-only research agents.
# Add custom agent names here if they don't touch source files.
if [ "$EVENT" = "SubagentStart" ]; then
  case "$AGENT_TYPE" in
    Explore|Plan|claude-code-guide|statusline-setup)
      exit 0  # No injection needed
      ;;
  esac
fi

# --- Build context ---
# Read START_HERE.md and HANDOFF.md, inject as additionalContext.
# Keep it concise — full file content is too large for context injection.
# Instead, inject the key sections: Navigation by Intent table + constraints.

CONTEXT="## Agent Onboarding Context (injected by hook)

Before editing any source file in src/, read its design file in blueprints/src/.
The source file is truth; the design file is the explanation. Keep design files
updated when you change source files.

### Current State
$(cat "$PROJECT_DIR/blueprints/HANDOFF.md" 2>/dev/null || echo 'No HANDOFF.md found.')
"

# Output the context injection
jq -n --arg ctx "$CONTEXT" --arg event "$EVENT" '{
  "hookSpecificOutput": {
    "hookEventName": $event,
    "additionalContext": $ctx
  }
}'
```

### 2. Configure hooks in settings

Add to `.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/inject-blueprints.sh",
            "statusMessage": "Loading project context..."
          }
        ]
      }
    ],
    "SubagentStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/inject-blueprints.sh",
            "statusMessage": "Loading project context for sub-agent..."
          }
        ]
      }
    ]
  }
}
```

### 3. Remove redundant CLAUDE.md instructions

Remove the Blueprints section from CLAUDE.md that currently reads:

> `blueprints/` is the knowledge layer for agents working on this codebase.
> **Read `blueprints/START_HERE.md` at the start of every session** before
> editing any source file. Before editing a specific file, read its design file
> in `blueprints/src/`. Keep design files updated when source files change.

The hook now handles this. CLAUDE.md should retain the project description,
constraints, commands, and architecture sections — just not the "read blueprints
first" instruction that's now enforced by the hook.

### 4. Update bead-agent.md

Remove any blueprint-reading instructions from the bead-agent workflow if present,
since SubagentStart will handle injection. The agent frontmatter does NOT need its
own hooks section — project-level hooks fire for sub-agents too (see evidence below).

## Watch-Outs

### Duplicate injection

Sub-agents also receive CLAUDE.md in their system prompt. If CLAUDE.md still
contains "read blueprints first" AND the SubagentStart hook injects it, the agent
gets the instruction twice. Solution: remove the instruction from CLAUDE.md (step 3).

Similarly, if bead-agent.md contains its own onboarding step AND the hook fires,
that's duplication. Remove from agent .md files too.

### Conditional filtering by agent type

Not all sub-agents need blueprints context. The `SubagentStart` input includes
`agent_type` which is the agent name — built-in types like `Bash`, `Explore`,
`Plan`, or custom names from `.claude/agents/`.

Agents that DON'T need injection:
- `Explore` — read-only research, doesn't edit files
- `Plan` — architectural planning, doesn't edit files
- `claude-code-guide` — answers questions about Claude Code itself
- `statusline-setup` — configures status line settings
- `haiku` model agents used for quick lookups

Agents that DO need injection:
- `bead-agent` — implements code changes
- `general-purpose` — may edit files
- Any custom coding agent

The hook script uses a case statement to skip known non-coding types and injects
for everything else (allowlist the skips, not the includes — safer as new agents
are added).

### Context size budget

`additionalContext` is injected as a system message. START_HERE.md is ~240 lines.
Injecting the full file would consume significant context budget, especially for
sub-agents with smaller windows.

Options (in order of preference):
1. **Inject HANDOFF.md + key instructions only** (~15 lines) — enough to orient,
   agent can read START_HERE.md itself if needed
2. **Inject the Navigation by Intent table** (~50 lines) — the most valuable part
3. **Inject the full START_HERE.md** (~240 lines) — maximum context but expensive

Start with option 1. If agents still struggle to find the right files, escalate
to option 2.

### SessionStart matcher values

SessionStart supports matchers: `startup`, `resume`, `clear`, `compact`. Consider
whether to inject on ALL of these or only `startup`:
- `startup` — new session, definitely needs context
- `resume` — continuing session, agent may already have context from before
- `clear` — context was cleared, needs re-injection
- `compact` — context was compacted, may have lost the injection

Recommendation: inject on all (no matcher filter). The cost is low (~15 lines)
and the risk of a context-less agent is high.

### Hook script must be executable

`chmod +x .claude/hooks/inject-blueprints.sh` — easy to forget.

### `jq` dependency

The hook scripts use `jq` for JSON parsing. It's available on macOS (via Homebrew)
and most Linux distros. If not installed, the hook will fail silently (exit 0
would be better than crashing). Add a guard:

```bash
if ! command -v jq &>/dev/null; then
  exit 0  # Fail open — don't block the session
fi
```

## Evidence & Sources

- **Project hooks fire for sub-agents:** GitHub issue #14859 reports that all hook
  events (including from sub-agents) share the same session_id — confirming
  project-level hooks fire for sub-agent tool calls.
  https://github.com/anthropics/claude-code/issues/14859

- **SubagentStart additionalContext:** Official docs explicitly support injecting
  context into sub-agents via this mechanism.
  https://code.claude.com/docs/en/hooks

- **SessionStart additionalContext:** Official docs confirm stdout and
  additionalContext are added to Claude's context on session start.
  https://code.claude.com/docs/en/hooks

- **"Pitch, don't embed" principle:** Frame instructions as helpful ("this table
  maps your task to the right files") not authoritative ("you MUST read this").
  https://blog.sshh.io/p/how-i-use-every-claude-code-feature

- **Community multi-agent observability:** Confirms project hooks create a unified
  event stream across all agents in a session.
  https://github.com/disler/claude-code-hooks-multi-agent-observability

## Verification Plan

1. Add a temporary logging hook that appends to `/tmp/hook-events.log`
2. Start a session, check log for SessionStart event
3. Spawn a bead-agent via `/action`, check log for SubagentStart event
4. Confirm the bead-agent receives the additionalContext (visible in transcript)
5. Spawn an Explore agent, confirm it does NOT receive injection (filtered out)
6. Remove logging hook once verified

## Open Questions

- **How large can `additionalContext` be?** Docs don't specify a limit. Test with
  the full START_HERE.md to see if it's accepted or truncated.
- **Does `compact` preserve hook-injected context?** If not, the compact matcher
  becomes critical for re-injection.
- **Should we add a PreToolUse enforcement gate too?** Layer 3 from the earlier
  analysis (block Edit/Write on src/ until blueprints are read) could complement
  this approach as a safety net. Defer until we see how well injection alone works.
