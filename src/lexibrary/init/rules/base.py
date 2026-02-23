"""Base rule content shared across all agent environments.

Provides the canonical Lexibrary instructions that every agent environment
(Claude Code, Cursor, Codex) should include.  Environment-specific modules
in this package call these functions to obtain content and then place it
in the appropriate file format and location.

Functions:
    get_core_rules: Shared agent rules applicable to all environments.
    get_orient_skill_content: Content for a ``/lexi-orient`` session-start skill.
    get_search_skill_content: Content for a ``/lexi-search`` cross-artifact search skill.
"""

from __future__ import annotations


def get_core_rules() -> str:
    """Return the shared Lexibrary rules for agents.

    The rules instruct agents to:

    * Read ``.lexibrary/START_HERE.md`` at session start
    * Check for ``.iwh`` signals when entering directories
    * Run ``lexi lookup <file>`` before editing
    * Update design files after editing (set ``updated_by: agent``)
    * Run ``lexi concepts <topic>`` before architectural decisions
    * Use ``lexi stack search`` before debugging and ``lexi stack post``
      after solving non-trivial bugs
    * Create ``.iwh`` when leaving work incomplete
    * Never run ``lexictl`` commands

    Returns:
        Multiline string with all core agent rules.
    """
    return _CORE_RULES.strip()


def get_orient_skill_content() -> str:
    """Return the content for a ``/lexi-orient`` skill.

    The orient skill provides a single-command session start that:

    * Reads ``.lexibrary/START_HERE.md``
    * Checks for a project-root ``.iwh`` signal
    * Runs ``lexi status`` to display library health

    Returns:
        Multiline string with orient skill instructions.
    """
    return _ORIENT_SKILL.strip()


def get_search_skill_content() -> str:
    """Return the content for a ``/lexi-search`` skill.

    The search skill wraps ``lexi search`` to provide richer context by
    combining concept lookup, Stack search, and design file results.

    Returns:
        Multiline string with search skill instructions.
    """
    return _SEARCH_SKILL.strip()


# ---------------------------------------------------------------------------
# Rule content templates
# ---------------------------------------------------------------------------

_CORE_RULES = """
# Lexibrary — Agent Rules

## Session Start

1. Read `.lexibrary/START_HERE.md` to understand the project structure and conventions.
2. Check for `.iwh` (I Was Here) signal files when entering any directory.
   - If an `.iwh` file exists: read its contents, act on any instructions, then delete the file.

## Before Editing Files

- Run `lexi lookup <file>` before editing any source file to understand
  its role, dependencies, and conventions.
- Read the corresponding design file in `.lexibrary/` if one exists.

## After Editing Files

- Update the corresponding design file to reflect your changes.
  Set `updated_by: agent` in the frontmatter.

## Architectural Decisions

- Run `lexi concepts <topic>` before making architectural decisions
  to check for existing project conventions and concepts.

## Debugging and Problem Solving

- Run `lexi stack search <query>` before starting to debug an issue
  -- a solution may already exist.
- After solving a non-trivial bug, run `lexi stack post` to document
  the problem and solution for future reference.

## Leaving Work Incomplete

- If you must stop before completing a task, create an `.iwh` file
  in the relevant directory describing the incomplete work and next
  steps.
- Do NOT create an `.iwh` file if all work is clean and complete.

## Prohibited Commands

- Never run `lexictl` commands. These are maintenance-only operations
  reserved for project administrators.
  - Do not run `lexictl update`, `lexictl validate`, `lexictl status`,
    `lexictl init`, or any other `lexictl` subcommand.
  - Use only `lexi` commands for your work.
"""

_ORIENT_SKILL = """
# /lexi-orient — Session Start

Orientate yourself in this Lexibrary-managed project.

## Steps

1. Read `.lexibrary/START_HERE.md` to understand the project layout,
   package map, and navigation protocol.
2. Check for `.lexibrary/.iwh` — if present, read it, follow any instructions, then delete the file.
3. Run `lexi status` to see a summary of library health, including design file counts and staleness.
"""

_SEARCH_SKILL = """
# /lexi-search — Cross-Artifact Search

Search across the entire Lexibrary knowledge base for a topic.

## Usage

Run `lexi search <query>` to perform a unified search that combines:

- **Concept lookup** — matching concepts from the wiki by title, alias, or tag.
- **Stack search** — matching Stack Q&A posts by title or content.
- **Design file search** — matching design files by source path or content.

Review all results to build a complete picture before proceeding.
"""
