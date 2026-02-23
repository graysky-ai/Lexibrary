## Why

Lexibrary has zero user-facing documentation. All existing docs are implementation-focused (`blueprints/`, `plans/`, `openspec/`) — useful for contributors building Lexibrary, but useless for teams adopting it. An operator running `lexictl init` for the first time has no guide explaining what Lexibrary does, how the artifact lifecycle works, how to configure it, or how to set up CI. Agents working in a Lexibrary-managed project have injected rules but no reference docs explaining the full `lexi` CLI or how to use concepts and Stack Q&A effectively. This gap blocks adoption.

## What Changes

- **New `docs/` directory** at the project root with two subdirectories: `docs/user/` (operator/team docs) and `docs/agent/` (AI agent docs).
- **15 User Docs** covering installation, conceptual overview, full configuration reference, CLI reference, project setup walkthrough, design file generation, validation, CI integration, library structure, concepts wiki, Stack Q&A, link graph, ignore patterns, troubleshooting, and upgrading.
- **11 Agent Docs** covering orientation, full `lexi` CLI reference, lookup workflow, update workflow, concepts, Stack Q&A, unified search, IWH signals, conventions, prohibited commands, and a quick-reference cheat sheet.
- **Root `docs/README.md`** — landing page linking to both doc sets with audience descriptions.
- **Backlog item closure** — marks the "Operator-facing documentation" item in `plans/BACKLOG.md` as resolved.

## Capabilities

### New Capabilities
- `user-documentation`: Complete operator-facing documentation set in `docs/user/` covering setup, configuration, workflows, artifact types, CI integration, and troubleshooting.
- `agent-documentation`: Complete agent-facing documentation set in `docs/agent/` covering orientation, CLI reference, lookup/update workflows, knowledge base usage, and a quick-reference card.

### Modified Capabilities
- None — this is a documentation-only change with no code modifications.

## Impact

- **Phase dependency:** None — documentation can be written at any time. Content reflects the current state of the codebase post-Phase 10.
- **New files:** 27 markdown files in `docs/` (1 root README + 15 user docs + 11 agent docs).
- **Modified files:** `plans/BACKLOG.md` (mark item as resolved).
- **New dependencies:** None.
- **Backward compatibility:** N/A — no code changes.
- **Risk:** Documentation can drift from code if not maintained. Mitigated by keeping docs high-level (concepts + workflows) rather than duplicating implementation details.
