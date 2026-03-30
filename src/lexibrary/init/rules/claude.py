"""Claude Code environment rule generation.

Generates:
- ``CLAUDE.md`` -- marker-delimited Lexibrary section with core agent rules
- ``.claude/settings.json`` -- pre-approved permissions and hook configuration
- ``.claude/hooks/lexi-pre-edit.sh`` -- PreToolUse hook for auto-lookup
- ``.claude/hooks/lexi-post-edit.sh`` -- PostToolUse hook (skeleton gen + reminders)
- ``.claude/agents/explore.md`` -- custom Explore agent with Lexibrary awareness
- ``.claude/agents/plan.md`` -- custom Plan agent with Lexibrary-first research
- ``.claude/agents/code.md`` -- custom Code agent with knowledge capture obligations
- ``.claude/agents/lexi-research.md`` -- deep research subagent for debugging
- ``.claude/skills/lexi-orient/SKILL.md`` -- orient session-start skill
- ``.claude/skills/lexi-search/SKILL.md`` -- cross-artifact search skill
- ``.claude/skills/lexi-lookup/SKILL.md`` -- file lookup skill
- ``.claude/skills/lexi-concept/SKILL.md`` -- concept search skill
- ``.claude/skills/lexi-stack/SKILL.md`` -- Stack Q&A skill
- ``.claude/skills/topology-builder/SKILL.md`` -- topology synthesis skill
- ``.claude/skills/topology-builder/assets/topology_template.md`` -- output template

The ``CLAUDE.md`` file uses marker-based section management so that
user-authored content outside the markers is preserved across updates.
``settings.json`` uses additive merge to preserve user customizations.
Skill files, hook scripts, and agent files are standalone and overwritten
on each generation.
"""

from __future__ import annotations

import json
import stat
from pathlib import Path

from lexibrary.init.rules.base import get_core_rules
from lexibrary.init.rules.markers import (
    append_lexibrary_section,
    has_lexibrary_section,
    replace_lexibrary_section,
)
from lexibrary.templates import read_template

# ---------------------------------------------------------------------------
# Permissions allow/deny lists
# ---------------------------------------------------------------------------

_PERMISSIONS_ALLOW: list[str] = [
    "Bash(lexi concept new *)",
    "Bash(lexi concepts *)",
    "Bash(lexi convention new *)",
    "Bash(lexi describe *)",
    "Bash(lexi impact *)",
    "Bash(lexi iwh *)",
    "Bash(lexi lookup *)",
    "Bash(lexi orient)",
    "Bash(lexi search *)",
    "Bash(lexi stack *)",
    "Bash(lexi status *)",
    "Bash(lexi validate *)",
]

_PERMISSIONS_DENY: list[str] = [
    "Bash(lexictl *)",
]

# ---------------------------------------------------------------------------
# Stale command files to clean up (migrated to skills)
# ---------------------------------------------------------------------------

_STALE_COMMAND_FILES: list[str] = [
    "lexi-orient.md",
    "lexi-search.md",
    "lexi-lookup.md",
    "lexi-concept.md",
    "lexi-stack.md",
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
                    "timeout": 15000,
                },
            ],
        },
    ],
}


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

    Hook scripts run as **separate shell processes** invoked by Claude Code
    at specific lifecycle events.  They execute outside the agent's
    permissions system -- they are not subject to ``allow``/``deny`` rules
    in ``settings.json`` -- and communicate back to the agent exclusively
    via JSON written to stdout.

    Creates (or overwrites) the following scripts:

    - ``.claude/hooks/lexi-pre-edit.sh`` -- PreToolUse auto-lookup
    - ``.claude/hooks/lexi-post-edit.sh`` -- PostToolUse skeleton generation + design reminder

    Also removes the deprecated ``lexi-explore-context.sh`` script if it
    exists from a previous installation (the SubagentStart hook has been
    removed).

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
    pre_edit.write_text(read_template("claude/hooks/lexi-pre-edit.sh"), encoding="utf-8")
    pre_edit.chmod(pre_edit.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    scripts.append(pre_edit)

    post_edit = hooks_dir / "lexi-post-edit.sh"
    post_edit.write_text(read_template("claude/hooks/lexi-post-edit.sh"), encoding="utf-8")
    post_edit.chmod(post_edit.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    scripts.append(post_edit)

    # Clean up the removed SubagentStart hook script from previous installations
    stale_explore_context = hooks_dir / "lexi-explore-context.sh"
    if stale_explore_context.exists():
        stale_explore_context.unlink()

    return scripts


# ---------------------------------------------------------------------------
# Agent file generation
# ---------------------------------------------------------------------------


def _generate_agent_files(project_root: Path) -> list[Path]:
    """Generate custom agent definition files in ``.claude/agents/``.

    Creates (or overwrites) the following agent files:

    - ``.claude/agents/explore.md`` -- Custom Explore agent that overrides
      the built-in Explore subagent with Lexibrary-aware exploration.
    - ``.claude/agents/plan.md`` -- Custom Plan agent with Lexibrary-first
      research and structured output.
    - ``.claude/agents/code.md`` -- Custom Code agent with knowledge capture
      obligations and design file maintenance.
    - ``.claude/agents/lexi-research.md`` -- Deep research subagent for
      debugging and architectural decisions.

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
    explore_agent.write_text(read_template("claude/agents/explore.md"), encoding="utf-8")
    agents.append(explore_agent)

    plan_agent = agents_dir / "plan.md"
    plan_agent.write_text(read_template("claude/agents/plan.md"), encoding="utf-8")
    agents.append(plan_agent)

    code_agent = agents_dir / "code.md"
    code_agent.write_text(read_template("claude/agents/code.md"), encoding="utf-8")
    agents.append(code_agent)

    research_agent = agents_dir / "lexi-research.md"
    research_agent.write_text(read_template("claude/agents/lexi-research.md"), encoding="utf-8")
    agents.append(research_agent)

    return agents


# ---------------------------------------------------------------------------
# Topology-builder skill deployment
# ---------------------------------------------------------------------------


def _deploy_topology_builder_skill(project_root: Path) -> list[Path]:
    """Deploy the topology-builder skill directory to ``.claude/skills/topology-builder/``.

    Creates the AgentSkills.io directory structure with:
    - ``SKILL.md`` -- skill instructions with frontmatter
    - ``assets/topology_template.md`` -- output structure template

    The skill reads ``.lexibrary/tmp/raw-topology.md`` at invocation time
    and synthesises ``.lexibrary/TOPOLOGY.md`` using the template.

    Args:
        project_root: Absolute path to the project root directory.

    Returns:
        List of absolute paths to the created skill files.
    """
    skill_dir = project_root / ".claude" / "skills" / "topology-builder"
    assets_dir = skill_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    created: list[Path] = []

    skill_file = skill_dir / "SKILL.md"
    content = read_template("rules/skills/topology-builder/SKILL.md").strip()
    skill_file.write_text(content + "\n", encoding="utf-8")
    created.append(skill_file)

    template_file = assets_dir / "topology_template.md"
    template_content = read_template(
        "rules/skills/topology-builder/assets/topology_template.md"
    ).strip()
    template_file.write_text(template_content + "\n", encoding="utf-8")
    created.append(template_file)

    return created


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
    4.  ``.claude/hooks/lexi-post-edit.sh`` -- PostToolUse hook (skeleton + queue).
    5.  ``.claude/agents/explore.md`` -- custom Explore agent definition.
    6.  ``.claude/agents/plan.md`` -- custom Plan agent definition.
    7.  ``.claude/agents/code.md`` -- custom Code agent definition.
    8.  ``.claude/agents/lexi-research.md`` -- deep research subagent.
    9.  ``.claude/skills/lexi-orient/SKILL.md`` -- orient skill (Open Skill format).
    10. ``.claude/skills/lexi-search/SKILL.md`` -- search skill.
    11. ``.claude/skills/lexi-lookup/SKILL.md`` -- lookup skill.
    12. ``.claude/skills/lexi-concept/SKILL.md`` -- concepts skill.
    13. ``.claude/skills/lexi-stack/SKILL.md`` -- Stack Q&A skill.
    14. ``.claude/skills/topology-builder/SKILL.md`` -- topology synthesis skill.
    15. ``.claude/skills/topology-builder/assets/topology_template.md`` -- output template.

    Also removes deprecated files from prior installations:
    - ``lexi-explore-context.sh`` hook script
    - ``lexi-*.md`` command files (migrated to skills)

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

    # --- .claude/skills/ ---
    skills_dir = project_root / ".claude" / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    lexi_skills = [
        "lexi-orient",
        "lexi-search",
        "lexi-lookup",
        "lexi-concept",
        "lexi-stack",
    ]

    for skill_name in lexi_skills:
        content = read_template(f"rules/skills/{skill_name}/SKILL.md").strip()
        skill_dir = skills_dir / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(content + "\n", encoding="utf-8")
        created.append(skill_file)

    # --- .claude/skills/topology-builder/ (SKILL.md + assets/) ---
    topology_skill_paths = _deploy_topology_builder_skill(project_root)
    created.extend(topology_skill_paths)

    # --- Clean up stale command files from prior installations ---
    commands_dir = project_root / ".claude" / "commands"
    if commands_dir.is_dir():
        for filename in _STALE_COMMAND_FILES:
            stale = commands_dir / filename
            if stale.exists():
                stale.unlink()

    return created
