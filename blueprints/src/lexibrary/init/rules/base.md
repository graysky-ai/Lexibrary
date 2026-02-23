# init/rules/base

**Summary:** Shared agent rule content templates used by all environment generators -- provides core rules, orient skill, and search skill content as multiline strings.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `get_core_rules` | `() -> str` | Return shared Lexibrarian agent rules: session start, before/after editing, architectural decisions, debugging, leaving work incomplete, prohibited commands |
| `get_orient_skill_content` | `() -> str` | Return `/lexi-orient` session-start skill: read START_HERE.md, check `.iwh`, run `lexi status` |
| `get_search_skill_content` | `() -> str` | Return `/lexi-search` cross-artifact search skill: wraps `lexi search` for concept, Stack, and design file results |

## Dependencies

- None

## Dependents

- `lexibrarian.init.rules.claude` -- calls all three functions
- `lexibrarian.init.rules.cursor` -- calls all three functions
- `lexibrarian.init.rules.codex` -- calls all three functions

## Key Concepts

- Core rules instruct agents to: read START_HERE.md, check `.iwh` signals, use `lexi lookup` before editing, update design files after editing, use concepts/stack for context, create `.iwh` when leaving work incomplete, never run `lexictl` commands
- Content is stored as module-level string constants (`_CORE_RULES`, `_ORIENT_SKILL`, `_SEARCH_SKILL`) and returned via `.strip()`
- No references to `lexictl` in agent-visible content -- only `lexi` commands are permitted for agents
