"""Claude Code environment rule generation.

Generates:
- ``CLAUDE.md`` -- marker-delimited Lexibrary section with core agent rules
- ``.claude/settings.json`` -- pre-approved permissions and hook configuration
- ``.claude/hooks/lexi-pre-edit.sh`` -- PreToolUse hook for auto-lookup
- ``.claude/hooks/lexi-post-edit.sh`` -- PostToolUse hook for design reminders
- ``.claude/hooks/lexi-explore-context.sh`` -- SubagentStart hook for Explore/Plan context injection
- ``.claude/agents/explore.md`` -- custom Explore agent with Lexibrary awareness
- ``.claude/commands/lexi-orient.md`` -- orient session-start command
- ``.claude/commands/lexi-search.md`` -- cross-artifact search command
- ``.claude/commands/lexi-lookup.md`` -- file lookup command
- ``.claude/commands/lexi-concepts.md`` -- concept search command
- ``.claude/commands/lexi-stack.md`` -- Stack Q&A command

The ``CLAUDE.md`` file uses marker-based section management so that
user-authored content outside the markers is preserved across updates.
``settings.json`` uses additive merge to preserve user customizations.
Command files, hook scripts, and agent files are standalone and overwritten
on each generation.
"""

from __future__ import annotations

import json
import stat
from pathlib import Path

from lexibrary.init.rules.base import (
    get_concepts_skill_content,
    get_core_rules,
    get_lookup_skill_content,
    get_orient_skill_content,
    get_search_skill_content,
    get_stack_skill_content,
)
from lexibrary.init.rules.markers import (
    append_lexibrary_section,
    has_lexibrary_section,
    replace_lexibrary_section,
)

# ---------------------------------------------------------------------------
# Permissions allow/deny lists
# ---------------------------------------------------------------------------

_PERMISSIONS_ALLOW: list[str] = [
    "Bash(lexi *)",
    "Bash(lexi concepts *)",
    "Bash(lexi concept *)",
    "Bash(lexi context-dump)",
    "Bash(lexi describe *)",
    "Bash(lexi help)",
    "Bash(lexi iwh *)",
    "Bash(lexi lookup *)",
    "Bash(lexi search *)",
    "Bash(lexi stack *)",
    "Bash(lexi status *)",
    "Bash(lexi validate *)",
]

_PERMISSIONS_DENY: list[str] = [
    "Bash(lexictl *)",
]

# ---------------------------------------------------------------------------
# Hook configurations
# ---------------------------------------------------------------------------

_HOOKS_CONFIG: dict[str, list[dict[str, object]]] = {
    "PreToolUse": [
        {
            "matcher": "Edit|Write",
            "hooks": [
                {
                    "type": "command",
                    "command": '"$CLAUDE_PROJECT_DIR"/.claude/hooks/lexi-pre-edit.sh',
                    "timeout": 10000,
                },
            ],
        },
    ],
    "PostToolUse": [
        {
            "matcher": "Edit|Write",
            "hooks": [
                {
                    "type": "command",
                    "command": '"$CLAUDE_PROJECT_DIR"/.claude/hooks/lexi-post-edit.sh',
                    "timeout": 5000,
                },
            ],
        },
    ],
    "SubagentStart": [
        {
            "matcher": "Explore|Plan",
            "hooks": [
                {
                    "type": "command",
                    "command": '"$CLAUDE_PROJECT_DIR"/.claude/hooks/lexi-explore-context.sh',
                    "timeout": 5000,
                },
            ],
        },
    ],
}

# ---------------------------------------------------------------------------
# Hook script content
# ---------------------------------------------------------------------------

_PRE_EDIT_SCRIPT = """\
#!/usr/bin/env bash
# lexi-pre-edit.sh -- Claude Code PreToolUse hook
# Runs `lexi lookup` before file edits to inject design context.

set -euo pipefail

# Read tool input JSON from stdin
INPUT=$(cat)

# Extract file_path from the tool input
FILE_PATH=$(echo "$INPUT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
# Handle both Edit and Write tool input shapes
path = data.get('file_path') or data.get('path', '')
print(path)
" 2>/dev/null || true)

if [ -z "$FILE_PATH" ]; then
    exit 0
fi

# Run lexi lookup and capture output for additionalContext
LOOKUP_OUTPUT=$(lexi lookup "$FILE_PATH" 2>/dev/null || true)

if [ -n "$LOOKUP_OUTPUT" ]; then
    python3 -c "
import sys, json
output = sys.stdin.read()
result = {'additionalContext': output}
json.dump(result, sys.stdout)
" <<< "$LOOKUP_OUTPUT"
fi

exit 0
"""

_EXPLORE_CONTEXT_SCRIPT = """\
#!/usr/bin/env bash
# lexi-explore-context.sh -- Claude Code SubagentStart hook
# Injects Lexibrary orientation context into Explore/Plan subagents.

set -euo pipefail

# Only inject context if the project has a Lexibrary index
if [ ! -d ".lexibrary" ]; then
    exit 0
fi

# Collect orientation context; fail silently on error
CONTEXT=$(lexi context-dump 2>/dev/null || true)

if [ -z "$CONTEXT" ]; then
    exit 0
fi

# Build hookSpecificOutput JSON using jq for proper escaping
jq -n --arg ctx "$CONTEXT" '{
  "hookSpecificOutput": {
    "hookEventName": "SubagentStart",
    "additionalContext": $ctx
  }
}'

exit 0
"""

# ---------------------------------------------------------------------------
# Custom Explore agent content
# ---------------------------------------------------------------------------

_EXPLORE_AGENT_CONTENT = """\
---
name: Explore
description: >-
  Explore the codebase to answer questions about how it works, find relevant
  files and code, and understand architecture and patterns.
tools:
  - Read
  - Grep
  - Glob
  - Bash
model: haiku
---

You are an exploration agent for a software codebase.

## Orientation

First, check if a `.lexibrary/` directory exists at the project root.

### If `.lexibrary/` exists (Lexibrary-indexed project)

Prefer Lexibrary commands over raw Glob/Grep. They return focused, pre-indexed
results that reduce the number of tool calls needed.

Available commands (run via Bash):

- `lexi search <query>` -- cross-artifact full-text search
- `lexi lookup <file>` -- design file, conventions, and reverse dependencies for a file
- `lexi concepts <topic>` -- domain vocabulary search
- `lexi conventions <path>` -- coding standards for a file or directory

You may still use Glob, Grep, and Read when you need raw file access, pattern
matching beyond what Lexibrary indexes, or to read specific file contents.

### If `.lexibrary/` does not exist (unindexed project)

Fall back to standard exploration using Glob, Grep, and Read.

## Output

- Be concise. Include absolute file paths and line numbers in all references.
- Return findings as a structured summary, not a narrative.

## Thoroughness

Adapt your depth based on the caller's request:

- **quick**: Limit to 2-3 tool calls maximum. Return the most likely answer fast.
- **medium** (default): Use up to 8-10 tool calls. Follow one level of cross-references.
- **very thorough**: Explore systematically across all relevant directories.
  Follow all cross-references. No tool-call limit.
"""

_POST_EDIT_SCRIPT = """\
#!/usr/bin/env bash
# lexi-post-edit.sh -- Claude Code PostToolUse hook
# Reminds agents to update design files after editing source files.

set -euo pipefail

# Read tool input JSON from stdin
INPUT=$(cat)

# Extract file_path from the tool input
FILE_PATH=$(echo "$INPUT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
path = data.get('file_path') or data.get('path', '')
print(path)
" 2>/dev/null || true)

if [ -z "$FILE_PATH" ]; then
    exit 0
fi

# Skip non-source paths -- no reminder needed for library/config files
case "$FILE_PATH" in
    *.lexibrary/*|*blueprints/*|*.claude/*|*.cursor/*)
        exit 0
        ;;
esac

# Emit a systemMessage reminder
python3 -c "
import json, sys
msg = ('Remember to update the corresponding design file '
       'after editing source files. '
       'Set updated_by: agent in the frontmatter.')
result = {'systemMessage': msg}
json.dump(result, sys.stdout)
"

exit 0
"""


# ---------------------------------------------------------------------------
# Settings.json generation
# ---------------------------------------------------------------------------


def _generate_settings_json(project_root: Path) -> Path:
    """Generate ``.claude/settings.json`` with permissions and hooks.

    Creates the file if it does not exist.  If it already exists, performs
    an additive merge: Lexibrary entries are added to existing ``allow``
    and ``deny`` lists (and hook arrays) without removing user entries.
    Lists are sorted and deduplicated for idempotency.

    Non-permission, non-hook keys in the existing file are preserved.

    Args:
        project_root: Absolute path to the project root directory.

    Returns:
        Absolute path to the generated/updated settings.json file.
    """
    claude_dir = project_root / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    settings_file = claude_dir / "settings.json"

    # Load existing settings or start fresh
    if settings_file.exists():
        existing_text = settings_file.read_text(encoding="utf-8")
        settings: dict[str, object] = json.loads(existing_text)
    else:
        settings = {}

    # --- Merge permissions ---
    permissions = settings.get("permissions", {})
    if not isinstance(permissions, dict):
        permissions = {}

    existing_allow: list[str] = permissions.get("allow", [])
    if not isinstance(existing_allow, list):
        existing_allow = []

    existing_deny: list[str] = permissions.get("deny", [])
    if not isinstance(existing_deny, list):
        existing_deny = []

    merged_allow = sorted(set(existing_allow) | set(_PERMISSIONS_ALLOW))
    merged_deny = sorted(set(existing_deny) | set(_PERMISSIONS_DENY))

    permissions["allow"] = merged_allow
    permissions["deny"] = merged_deny
    settings["permissions"] = permissions

    # --- Merge hooks ---
    existing_hooks = settings.get("hooks", {})
    if not isinstance(existing_hooks, dict):
        existing_hooks = {}

    for event_type, our_entries in _HOOKS_CONFIG.items():
        existing_entries: list[dict[str, object]] = existing_hooks.get(event_type, [])
        if not isinstance(existing_entries, list):
            existing_entries = []

        # Deduplicate by checking if our hook command already exists
        existing_commands = set()
        for entry in existing_entries:
            hooks_list = entry.get("hooks", [])
            if isinstance(hooks_list, list):
                for hook in hooks_list:
                    if isinstance(hook, dict):
                        existing_commands.add(hook.get("command", ""))

        for our_entry in our_entries:
            our_hooks = our_entry.get("hooks", [])
            if isinstance(our_hooks, list):
                for hook in our_hooks:
                    if isinstance(hook, dict) and hook.get("command", "") not in existing_commands:
                        existing_entries.append(our_entry)
                        break

        existing_hooks[event_type] = existing_entries

    settings["hooks"] = existing_hooks

    settings_file.write_text(
        json.dumps(settings, indent=2) + "\n",
        encoding="utf-8",
    )
    return settings_file


# ---------------------------------------------------------------------------
# Hook script generation
# ---------------------------------------------------------------------------


def _generate_hook_scripts(project_root: Path) -> list[Path]:
    """Generate executable hook scripts in ``.claude/hooks/``.

    Creates (or overwrites) the following scripts:

    - ``.claude/hooks/lexi-pre-edit.sh`` -- PreToolUse auto-lookup
    - ``.claude/hooks/lexi-post-edit.sh`` -- PostToolUse design reminder
    - ``.claude/hooks/lexi-explore-context.sh`` -- SubagentStart context injection

    All scripts are made executable (chmod +x).

    Args:
        project_root: Absolute path to the project root directory.

    Returns:
        List of absolute paths to the generated hook scripts.
    """
    hooks_dir = project_root / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    scripts: list[Path] = []

    pre_edit = hooks_dir / "lexi-pre-edit.sh"
    pre_edit.write_text(_PRE_EDIT_SCRIPT, encoding="utf-8")
    pre_edit.chmod(pre_edit.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    scripts.append(pre_edit)

    post_edit = hooks_dir / "lexi-post-edit.sh"
    post_edit.write_text(_POST_EDIT_SCRIPT, encoding="utf-8")
    post_edit.chmod(post_edit.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    scripts.append(post_edit)

    explore_context = hooks_dir / "lexi-explore-context.sh"
    explore_context.write_text(_EXPLORE_CONTEXT_SCRIPT, encoding="utf-8")
    explore_context.chmod(
        explore_context.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    )
    scripts.append(explore_context)

    return scripts


# ---------------------------------------------------------------------------
# Agent file generation
# ---------------------------------------------------------------------------


def _generate_agent_files(project_root: Path) -> list[Path]:
    """Generate custom agent definition files in ``.claude/agents/``.

    Creates (or overwrites) the following agent files:

    - ``.claude/agents/explore.md`` -- Custom Explore agent that overrides
      the built-in Explore subagent with Lexibrary-aware exploration.

    The ``.claude/agents/`` directory is created if it does not exist.

    Args:
        project_root: Absolute path to the project root directory.

    Returns:
        List of absolute paths to the generated agent files.
    """
    agents_dir = project_root / ".claude" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)

    agents: list[Path] = []

    explore_agent = agents_dir / "explore.md"
    explore_agent.write_text(_EXPLORE_AGENT_CONTENT, encoding="utf-8")
    agents.append(explore_agent)

    return agents


# ---------------------------------------------------------------------------
# Main generation function
# ---------------------------------------------------------------------------


def generate_claude_rules(project_root: Path) -> list[Path]:
    """Generate Claude Code agent rule files at *project_root*.

    Creates or updates:

    1.  ``CLAUDE.md`` -- Lexibrary section appended (new file / no markers)
        or replaced (existing markers).
    2.  ``.claude/settings.json`` -- permissions and hooks configuration.
    3.  ``.claude/hooks/lexi-pre-edit.sh`` -- PreToolUse hook script.
    4.  ``.claude/hooks/lexi-post-edit.sh`` -- PostToolUse hook script.
    5.  ``.claude/hooks/lexi-explore-context.sh`` -- SubagentStart hook script.
    6.  ``.claude/agents/explore.md`` -- custom Explore agent definition.
    7.  ``.claude/commands/lexi-orient.md`` -- orient skill command file.
    8.  ``.claude/commands/lexi-search.md`` -- search skill command file.
    9.  ``.claude/commands/lexi-lookup.md`` -- lookup skill command file.
    10. ``.claude/commands/lexi-concepts.md`` -- concepts skill command file.
    11. ``.claude/commands/lexi-stack.md`` -- stack skill command file.

    Args:
        project_root: Absolute path to the project root directory.

    Returns:
        List of absolute paths to all created or updated files.
    """
    created: list[Path] = []

    # --- CLAUDE.md ---
    claude_md = project_root / "CLAUDE.md"
    core_rules = get_core_rules()

    if claude_md.exists():
        existing = claude_md.read_text(encoding="utf-8")
        if has_lexibrary_section(existing):
            updated = replace_lexibrary_section(existing, core_rules)
        else:
            updated = append_lexibrary_section(existing, core_rules)
    else:
        updated = append_lexibrary_section("", core_rules)

    claude_md.write_text(updated, encoding="utf-8")
    created.append(claude_md)

    # --- .claude/settings.json ---
    settings_path = _generate_settings_json(project_root)
    created.append(settings_path)

    # --- .claude/hooks/ ---
    hook_paths = _generate_hook_scripts(project_root)
    created.extend(hook_paths)

    # --- .claude/agents/ ---
    agent_paths = _generate_agent_files(project_root)
    created.extend(agent_paths)

    # --- .claude/commands/ ---
    commands_dir = project_root / ".claude" / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)

    orient_file = commands_dir / "lexi-orient.md"
    orient_file.write_text(get_orient_skill_content(), encoding="utf-8")
    created.append(orient_file)

    search_file = commands_dir / "lexi-search.md"
    search_file.write_text(get_search_skill_content(), encoding="utf-8")
    created.append(search_file)

    lookup_file = commands_dir / "lexi-lookup.md"
    lookup_file.write_text(get_lookup_skill_content(), encoding="utf-8")
    created.append(lookup_file)

    concepts_file = commands_dir / "lexi-concepts.md"
    concepts_file.write_text(get_concepts_skill_content(), encoding="utf-8")
    created.append(concepts_file)

    stack_file = commands_dir / "lexi-stack.md"
    stack_file.write_text(get_stack_skill_content(), encoding="utf-8")
    created.append(stack_file)

    return created
