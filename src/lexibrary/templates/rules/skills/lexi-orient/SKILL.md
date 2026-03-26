---
name: lexi-orient
description: Session start guidance. Run at the start of every session to get project topology, library stats, and IWH signals.
license: MIT
compatibility: Requires lexi CLI.
metadata:
  author: lexibrary
  version: "1.0"
---

Orient yourself in the project by running a single command that surfaces
topology, library health, and any context left by a previous session.

## When to use

- At the start of every session before touching any file
- After losing context mid-session (e.g., long conversation, tool error)
- When re-orienting after working in a different part of the codebase
- Before deciding which files or directories to investigate next

## Steps

1. Run `lexi orient` — no arguments required.
2. Read the **Project Topology** section to understand the directory layout
   and which modules are relevant to your task.
3. Check **Library Stats** (concepts, conventions, playbooks, open stack posts).
   A non-zero open stack post count means unresolved issues exist — run
   `lexi stack search <topic>` before debugging anything in that area.
4. Check for **IWH signals**. If any are listed, note the directories.
   Run `lexi iwh read <dir>` for each directory you are actively about to
   work in — this consumes the signal and surfaces the prior session's notes.
5. Proceed with `lexi search <query>` or `lexi lookup <file>` to zoom in.

## Examples

```
lexi orient
```

Output sections and what to do with each:

| Section | What to look for | Follow-up action |
|---------|-----------------|-----------------|
| Project Topology | Module boundaries, entry points, test layout | `lexi lookup <dir>` for unfamiliar areas |
| Library Stats | Open stack post count > 0 | `lexi stack search <topic>` before debugging |
| IWH signals | Signals in directories you will work in | `lexi iwh read <dir>` to consume and read notes |

## Edge cases

- **Sub-agents must NOT consume IWH signals.** Only the top-level orchestrating
  agent should run `lexi iwh read`. Sub-agents see the peeked signal text in
  orient output but must leave consumption to the orchestrator.
- **Only consume signals for directories you are committed to working in.**
  Consuming a signal deletes it permanently. Do not consume speculatively.
- If orient output is truncated by context limits, re-run with a narrower
  scope or use `lexi lookup <dir>` to inspect specific subtrees directly.
