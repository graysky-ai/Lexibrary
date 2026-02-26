# Plan: Hook-Based Context Injection

> **Status**: Future — extracted from the superseded
> [`plans/agent-start-plan.md`](agent-start-plan.md). Not yet scheduled.
> Activate when the agent rule template system needs deterministic context
> injection beyond what CLAUDE.md provides.

## Purpose

Deterministically inject project context into agents via Claude Code hooks
(SessionStart / SubagentStart), so agents receive critical context whether or
not they choose to read reference files.

## Pattern

Use two hook events with a shared script:

1. **`SessionStart`** — inject context into the main session on startup,
   resume, clear, and compact events.
2. **`SubagentStart`** — inject context into sub-agents, filtered by agent
   type (skip read-only agents like Explore/Plan).

Both hooks emit `additionalContext` via JSON stdout, which Claude Code adds to
the agent's system context automatically.

### Hook output format

```json
{
  "hookSpecificOutput": {
    "hookEventName": "<SessionStart|SubagentStart>",
    "additionalContext": "<injected text>"
  }
}
```

### Hook script template

```bash
#!/bin/bash
# Guard: fail open if jq is missing
if ! command -v jq &>/dev/null; then
  exit 0
fi

INPUT=$(cat)
EVENT=$(echo "$INPUT" | jq -r '.hook_event_name')
AGENT_TYPE=$(echo "$INPUT" | jq -r '.agent_type // empty')
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"

# --- Conditional filtering (SubagentStart only) ---
# Skip injection for non-coding agent types that don't need project context.
# Allowlist the skips, not the includes — safer as new agents are added.
if [ "$EVENT" = "SubagentStart" ]; then
  case "$AGENT_TYPE" in
    Explore|Plan|claude-code-guide|statusline-setup)
      exit 0  # No injection needed
      ;;
  esac
fi

# --- Build context ---
# Customize this section for whatever context you want to inject.
CONTEXT="## Project Context (injected by hook)

<your context here>
"

# Output the context injection
jq -n --arg ctx "$CONTEXT" --arg event "$EVENT" '{
  "hookSpecificOutput": {
    "hookEventName": $event,
    "additionalContext": $ctx
  }
}'
```

### Settings configuration

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/inject-context.sh",
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
            "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/inject-context.sh",
            "statusMessage": "Loading project context for sub-agent..."
          }
        ]
      }
    ]
  }
}
```

## Design Decisions

### Conditional filtering by agent type

`SubagentStart` input includes `agent_type` (the agent name). Filter with a
denylist of known read-only types:

| Skip (read-only)       | Inject (may edit files) |
|------------------------|------------------------|
| `Explore`              | `bead-agent`           |
| `Plan`                 | `general-purpose`      |
| `claude-code-guide`    | Any custom coding agent|
| `statusline-setup`     |                        |

### Context size budget

`additionalContext` is injected as a system message. Budget options:

1. **~15 lines** — key instructions + handoff state (recommended start)
2. **~50 lines** — navigation table or lookup index
3. **~240 lines** — full reference document (expensive for sub-agents)

Start small. Escalate only if agents can't orient themselves.

### SessionStart matcher values

SessionStart supports matchers: `startup`, `resume`, `clear`, `compact`.
Recommendation: inject on all (no matcher filter). The cost of a small
injection is low; the cost of a context-less agent is high.

### Duplicate injection risk

Sub-agents receive CLAUDE.md in their system prompt. If CLAUDE.md contains
the same "read X first" instruction AND the hook injects it, the agent gets
the instruction twice. Remove the CLAUDE.md instruction when the hook takes
over.

### "Pitch, don't embed" principle

Frame injected instructions as helpful ("this table maps your task to the
right files") not authoritative ("you MUST read this"). Agents respond
better to context that explains *why* rather than commands.

## Watch-Outs

- **`chmod +x`** — hook scripts must be executable; easy to forget.
- **`jq` dependency** — guard with `command -v jq` and `exit 0` (fail open).
- **Context size limits** — docs don't specify a max for `additionalContext`.
  Test with larger payloads before assuming full documents will pass through.
- **Compact preservation** — unclear whether `compact` preserves
  hook-injected context. If not, the compact matcher becomes critical for
  re-injection.

## Evidence & Sources

- **Project hooks fire for sub-agents:** GitHub issue #14859 — all hook
  events (including sub-agents) share the same session_id.
  https://github.com/anthropics/claude-code/issues/14859

- **SubagentStart/SessionStart additionalContext:** Official Claude Code
  hooks documentation.
  https://code.claude.com/docs/en/hooks

- **"Pitch, don't embed" principle:**
  https://blog.sshh.io/p/how-i-use-every-claude-code-feature

- **Community multi-agent observability:** Project hooks create a unified
  event stream across all agents in a session.
  https://github.com/disler/claude-code-hooks-multi-agent-observability

## Verification Plan

1. Add a temporary logging hook that appends to `/tmp/hook-events.log`
2. Start a session — check log for SessionStart event
3. Spawn a coding sub-agent — check log for SubagentStart event
4. Confirm the sub-agent receives the `additionalContext` (visible in transcript)
5. Spawn an Explore agent — confirm it does NOT receive injection (filtered out)
6. Remove logging hook once verified

## Open Questions

- **Max `additionalContext` size?** Not documented. Needs empirical testing.
- **Does `compact` preserve hook-injected context?** If not, re-injection on
  compact is critical.
- **PreToolUse enforcement gate?** A complementary hook could block
  Edit/Write on `src/` until blueprints are read — a safety net on top of
  injection. Defer until injection alone proves insufficient.
