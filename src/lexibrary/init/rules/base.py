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

from lexibrary.templates import read_template


def get_core_rules() -> str:
    """Return the shared Lexibrary rules for agents.

    The rules instruct agents to:

    * Run ``lexi orient`` at session start (includes topology, health, IWH)
    * Consume IWH signals if any are listed
    * Run ``lexi lookup <file>`` before editing
    * Update design files after editing (set ``updated_by: agent``)
    * Run ``lexi validate`` after editing to check library health
    * Run ``lexi concepts <topic>`` before architectural decisions
    * Use ``lexi stack search`` before debugging, delegate complex
      research to the ``lexi-research`` subagent, and ``lexi stack post``
      after solving non-trivial bugs
    * Use ``lexi iwh write`` when leaving work incomplete
    * Never run ``lexictl`` commands

    Returns:
        Multiline string with all core agent rules.
    """
    return read_template("rules/core_rules.md").strip()


def get_orient_skill_content() -> str:
    """Return the content for a ``/lexi-orient`` skill.

    The orient skill instructs agents to run ``lexi orient`` -- a single
    command that returns project topology, library stats, and IWH signals
    (peek mode).  It replaces the previous multi-step workflow of reading
    TOPOLOGY.md, running ``lexi iwh list``, and running ``lexi status``
    separately.

    Returns:
        Multiline string with orient skill instructions.
    """
    return read_template("rules/skills/lexi-orient/SKILL.md").strip()


def get_search_skill_content() -> str:
    """Return the content for a ``/lexi-search`` skill.

    The search skill wraps ``lexi search`` with "when to use" guidance
    (territory mapping before zoom-in) and describes the unified search
    across concepts, Stack posts, and design files.

    Returns:
        Multiline string with search skill instructions.
    """
    return read_template("rules/skills/lexi-search/SKILL.md").strip()


def get_lookup_skill_content() -> str:
    """Return the content for a ``/lexi-lookup`` skill.

    The lookup skill runs ``lexi lookup <file|directory>`` to retrieve
    design context, conventions, known issues, and IWH signals.  Leads
    with "when to use" guidance and documents both file and directory
    lookup modes.

    Returns:
        Multiline string with lookup skill instructions.
    """
    return read_template("rules/skills/lexi-lookup/SKILL.md").strip()


def get_concepts_skill_content() -> str:
    """Return the content for a ``/lexi-concepts`` skill.

    The concepts skill runs ``lexi concepts [topic]`` with "when to use"
    guidance (before architectural decisions, when following wikilinks)
    and documents ``--tag`` and ``--all`` flags.

    Returns:
        Multiline string with concepts skill instructions.
    """
    return read_template("rules/skills/lexi-concepts/SKILL.md").strip()


def get_stack_skill_content() -> str:
    """Return the content for a ``/lexi-stack`` skill.

    The stack skill provides "when to use" guidance (before debugging,
    after solving bugs) and documents ``lexi stack search``,
    ``lexi stack post``, and ``lexi stack finding`` operations.
    References the ``lexi-research`` subagent for complex research.

    Returns:
        Multiline string with stack skill instructions.
    """
    return read_template("rules/skills/lexi-stack/SKILL.md").strip()
