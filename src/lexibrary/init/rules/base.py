"""Base rule content shared across all agent environments.

Provides the canonical Lexibrary instructions that every agent environment
(Claude Code, Cursor, Codex) should include.  Environment-specific modules
in this package call these functions to obtain content and then place it
in the appropriate file format and location.

Functions:
    get_core_rules: Shared agent rules applicable to all environments.
    get_orient_skill_content: Content for a ``/lexi-orient`` session-start skill.
    get_search_skill_content: Content for a ``/lexi-search`` cross-artifact search skill.
    get_lookup_skill_content: Content for a ``/lexi-lookup`` file lookup skill.
    get_concepts_skill_content: Content for a ``/lexi-concepts`` concept search skill.
    get_stack_skill_content: Content for a ``/lexi-stack`` Stack Q&A skill.
"""

from __future__ import annotations


def get_core_rules() -> str:
    """Return the shared Lexibrary rules for agents.

    The rules instruct agents to:

    * Read ``.lexibrary/START_HERE.md`` at session start
    * Check for IWH signals via ``lexi iwh list``
    * Run ``lexi lookup <file>`` before editing
    * Update design files after editing (set ``updated_by: agent``)
    * Run ``lexi validate`` after editing to check library health
    * Run ``lexi concepts <topic>`` before architectural decisions
    * Use ``lexi stack search`` before debugging and ``lexi stack post``
      after solving non-trivial bugs
    * Use ``lexi iwh write`` when leaving work incomplete
    * Never run ``lexictl`` commands

    Returns:
        Multiline string with all core agent rules.
    """
    return _CORE_RULES.strip()


def get_orient_skill_content() -> str:
    """Return the content for a ``/lexi-orient`` skill.

    The orient skill provides a single-command session start that:

    * Reads ``.lexibrary/START_HERE.md``
    * Checks for IWH signals via ``lexi iwh list``
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


def get_lookup_skill_content() -> str:
    """Return the content for a ``/lexi-lookup`` skill.

    The lookup skill runs ``lexi lookup <file>`` to retrieve design context
    for a source file before editing it.

    Returns:
        Multiline string with lookup skill instructions.
    """
    return _LOOKUP_SKILL.strip()


def get_concepts_skill_content() -> str:
    """Return the content for a ``/lexi-concepts`` skill.

    The concepts skill runs ``lexi concepts [topic]`` with guidance on
    ``--tag`` and ``--all`` flags for searching project conventions.

    Returns:
        Multiline string with concepts skill instructions.
    """
    return _CONCEPTS_SKILL.strip()


def get_stack_skill_content() -> str:
    """Return the content for a ``/lexi-stack`` skill.

    The stack skill provides guided prompts for ``lexi stack search``,
    ``lexi stack post``, and ``lexi stack answer`` operations.

    Returns:
        Multiline string with stack skill instructions.
    """
    return _STACK_SKILL.strip()


# ---------------------------------------------------------------------------
# Rule content templates
# ---------------------------------------------------------------------------

_CORE_RULES = """
# Lexibrary — Agent Rules

## Session Start

1. Read `.lexibrary/START_HERE.md` to understand the project structure and conventions.
2. Run `lexi iwh list` to check for IWH (I Was Here) signals left by a previous session.
   - If signals exist, run `lexi iwh read <directory>` for each to understand the context
     and consume the signal.
   - IWH files live in `.lexibrary/<mirror-path>/.iwh` (e.g., `.lexibrary/src/auth/.iwh`
     for the `src/auth/` directory).

## Before Editing Files

- Run `lexi lookup <file>` before editing any source file to understand
  its role, dependencies, and conventions.
- Read the corresponding design file in `.lexibrary/designs/` if one exists.

## After Editing Files

- Update the corresponding design file to reflect your changes.
  Set `updated_by: agent` in the frontmatter.
- Run `lexi validate` to check for broken wikilinks, stale design
  files, or other library health issues introduced by your changes.

## Architectural Decisions

- Run `lexi concepts <topic>` before making architectural decisions
  to check for existing project conventions and concepts.

## Debugging and Problem Solving

- Run `lexi stack search <query>` before starting to debug an issue
  -- a solution may already exist.
- After solving a non-trivial bug, run `lexi stack post` to document
  the problem and solution for future reference.

## Leaving Work Incomplete

- If you must stop before completing a task, run:
  `lexi iwh write <directory> --scope incomplete --body "description of what remains"`
- Use `--scope blocked` if work cannot proceed until a condition is met.
- Do NOT create an IWH signal if all work is clean and complete.

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
2. Run `lexi iwh list` to check for IWH signals across the project.
   - If any signals exist, run `lexi iwh read <directory>` for each to understand the context
     and consume the signal.
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

_LOOKUP_SKILL = """
# /lexi-lookup — File Lookup

Look up design context for a source file before editing it.

## Usage

Run `lexi lookup <file>` with the path to any source file to see:

- The corresponding design file content (role, dependencies, conventions)
- Related concepts and cross-references
- Staleness information (whether the design file is up to date)

Always run this before editing a file to understand its context and
avoid breaking conventions or dependencies.
"""

_CONCEPTS_SKILL = """
# /lexi-concepts — Concept Search

Search for project concepts, conventions, and architectural patterns.

## Usage

- `lexi concepts <topic>` — search for concepts matching a topic
- `lexi concepts --tag <tag>` — filter concepts by tag (e.g., `--tag convention`, `--tag pattern`)
- `lexi concepts --all` — list all concepts in the project wiki

Use this before making architectural decisions to check for existing
conventions, patterns, or design rationale documented in the project.
"""

_STACK_SKILL = """
# /lexi-stack — Stack Q&A

Search, post, and answer questions in the project's Stack knowledge base.

## Usage

- `lexi stack search <query>` — search for existing Q&A posts matching your query.
  Run this before debugging to check if a solution already exists.
- `lexi stack post` — create a new question post after encountering a non-trivial
  bug or issue. Document the problem clearly for future reference.
- `lexi stack answer <post-id>` — add an answer to an existing Stack post after
  solving the problem. Include the solution and any relevant context.

The Stack is the project's persistent knowledge base for debugging insights
and solutions. Contributing to it helps future sessions avoid repeating work.
"""
