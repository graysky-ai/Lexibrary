"""Tests for init/rules/claude.py — Claude Code environment rule generation."""

from __future__ import annotations

import json
import stat
from pathlib import Path

from lexibrary.init.rules.claude import (
    _generate_agent_files,
    _generate_hook_scripts,
    _generate_settings_json,
    generate_claude_rules,
)
from lexibrary.init.rules.markers import MARKER_END, MARKER_START

# ---------------------------------------------------------------------------
# Create from scratch
# ---------------------------------------------------------------------------


class TestCreateFromScratch:
    """CLAUDE.md created from scratch when file does not exist."""

    def test_creates_claude_md(self, tmp_path: Path) -> None:
        """generate_claude_rules() creates CLAUDE.md at the project root."""
        generate_claude_rules(tmp_path)
        assert (tmp_path / "CLAUDE.md").exists()

    def test_claude_md_has_markers(self, tmp_path: Path) -> None:
        """Created CLAUDE.md contains both start and end markers."""
        generate_claude_rules(tmp_path)
        content = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
        assert MARKER_START in content
        assert MARKER_END in content

    def test_claude_md_has_core_rules(self, tmp_path: Path) -> None:
        """Created CLAUDE.md contains core Lexibrary rules."""
        generate_claude_rules(tmp_path)
        content = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
        assert "lexi orient" in content
        assert "lexi lookup" in content

    def test_returns_all_created_paths(self, tmp_path: Path) -> None:
        """Return value includes all generated files."""
        result = generate_claude_rules(tmp_path)
        assert len(result) == 15
        filenames = [p.name for p in result]
        assert "CLAUDE.md" in filenames
        assert "settings.json" in filenames
        assert "lexi-pre-edit.sh" in filenames
        assert "lexi-post-edit.sh" in filenames
        assert "explore.md" in filenames
        assert "plan.md" in filenames
        assert "code.md" in filenames
        assert "lexi-research.md" in filenames
        # Skill files are in per-skill subdirs; check by parent directory names
        skill_parents = {p.parent.name for p in result if p.name == "SKILL.md"}
        assert "lexi-orient" in skill_parents
        assert "lexi-search" in skill_parents
        assert "lexi-lookup" in skill_parents
        assert "lexi-concept" in skill_parents
        assert "lexi-stack" in skill_parents


# ---------------------------------------------------------------------------
# Append to existing CLAUDE.md without markers
# ---------------------------------------------------------------------------


class TestAppendToExisting:
    """Existing CLAUDE.md without markers gets section appended."""

    def test_preserves_existing_content(self, tmp_path: Path) -> None:
        """User content before the Lexibrary section is preserved."""
        claude_md = tmp_path / "CLAUDE.md"
        user_content = "# My Project\n\nCustom rules here.\n"
        claude_md.write_text(user_content, encoding="utf-8")

        generate_claude_rules(tmp_path)

        content = claude_md.read_text(encoding="utf-8")
        assert "# My Project" in content
        assert "Custom rules here." in content

    def test_appends_markers(self, tmp_path: Path) -> None:
        """Markers are appended to existing content."""
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text("# Existing content", encoding="utf-8")

        generate_claude_rules(tmp_path)

        content = claude_md.read_text(encoding="utf-8")
        assert MARKER_START in content
        assert MARKER_END in content

    def test_existing_content_before_markers(self, tmp_path: Path) -> None:
        """Existing content appears before the marker block."""
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text("# Existing content", encoding="utf-8")

        generate_claude_rules(tmp_path)

        content = claude_md.read_text(encoding="utf-8")
        existing_pos = content.index("# Existing content")
        marker_pos = content.index(MARKER_START)
        assert existing_pos < marker_pos


# ---------------------------------------------------------------------------
# Update existing marked section
# ---------------------------------------------------------------------------


class TestUpdateExistingSection:
    """CLAUDE.md with existing markers has section replaced."""

    def test_replaces_old_section(self, tmp_path: Path) -> None:
        """Old content between markers is replaced."""
        claude_md = tmp_path / "CLAUDE.md"
        old_content = (
            f"# My Rules\n\n{MARKER_START}\nold lexibrary rules\n{MARKER_END}\n\n# My Other Rules"
        )
        claude_md.write_text(old_content, encoding="utf-8")

        generate_claude_rules(tmp_path)

        content = claude_md.read_text(encoding="utf-8")
        assert "old lexibrary rules" not in content
        assert "lexi orient" in content

    def test_preserves_surrounding_content(self, tmp_path: Path) -> None:
        """Content before and after the marker block is preserved."""
        claude_md = tmp_path / "CLAUDE.md"
        old_content = (
            f"# Before Section\n\n{MARKER_START}\nold stuff\n{MARKER_END}\n\n# After Section"
        )
        claude_md.write_text(old_content, encoding="utf-8")

        generate_claude_rules(tmp_path)

        content = claude_md.read_text(encoding="utf-8")
        assert "# Before Section" in content
        assert "# After Section" in content

    def test_only_one_marker_pair(self, tmp_path: Path) -> None:
        """After update, there is exactly one start and one end marker."""
        claude_md = tmp_path / "CLAUDE.md"
        old_content = f"{MARKER_START}\nold\n{MARKER_END}"
        claude_md.write_text(old_content, encoding="utf-8")

        generate_claude_rules(tmp_path)

        content = claude_md.read_text(encoding="utf-8")
        assert content.count(MARKER_START) == 1
        assert content.count(MARKER_END) == 1


# ---------------------------------------------------------------------------
# Skill files
# ---------------------------------------------------------------------------


class TestSkillFiles:
    """Skill files are created in .claude/skills/."""

    def test_creates_orient_skill(self, tmp_path: Path) -> None:
        """lexi-orient/SKILL.md is created in .claude/skills/."""
        generate_claude_rules(tmp_path)
        orient = tmp_path / ".claude" / "skills" / "lexi-orient" / "SKILL.md"
        assert orient.exists()

    def test_orient_contains_lexi_orient(self, tmp_path: Path) -> None:
        """Orient skill references lexi orient."""
        generate_claude_rules(tmp_path)
        orient = tmp_path / ".claude" / "skills" / "lexi-orient" / "SKILL.md"
        content = orient.read_text(encoding="utf-8")
        assert "lexi orient" in content

    def test_orient_contains_library_stats(self, tmp_path: Path) -> None:
        """Orient skill mentions library stats."""
        generate_claude_rules(tmp_path)
        orient = tmp_path / ".claude" / "skills" / "lexi-orient" / "SKILL.md"
        content = orient.read_text(encoding="utf-8")
        lower = content.lower()
        assert "stats" in lower or "count" in lower or "topology" in lower

    def test_creates_search_skill(self, tmp_path: Path) -> None:
        """lexi-search/SKILL.md is created in .claude/skills/."""
        generate_claude_rules(tmp_path)
        search = tmp_path / ".claude" / "skills" / "lexi-search" / "SKILL.md"
        assert search.exists()

    def test_search_contains_lexi_search(self, tmp_path: Path) -> None:
        """Search skill references lexi search."""
        generate_claude_rules(tmp_path)
        search = tmp_path / ".claude" / "skills" / "lexi-search" / "SKILL.md"
        content = search.read_text(encoding="utf-8")
        assert "lexi search" in content

    def test_skill_files_overwritten_on_update(self, tmp_path: Path) -> None:
        """Skill files are overwritten when regenerated."""
        orient = tmp_path / ".claude" / "skills" / "lexi-orient" / "SKILL.md"
        orient.parent.mkdir(parents=True, exist_ok=True)
        orient.write_text("old orient content", encoding="utf-8")

        generate_claude_rules(tmp_path)

        content = orient.read_text(encoding="utf-8")
        assert "old orient content" not in content
        assert "lexi orient" in content

    def test_creates_skills_directory(self, tmp_path: Path) -> None:
        """The .claude/skills/ directory is created if it does not exist."""
        generate_claude_rules(tmp_path)
        assert (tmp_path / ".claude" / "skills").is_dir()

    def test_creates_lookup_skill(self, tmp_path: Path) -> None:
        """lexi-lookup/SKILL.md is created in .claude/skills/."""
        generate_claude_rules(tmp_path)
        lookup = tmp_path / ".claude" / "skills" / "lexi-lookup" / "SKILL.md"
        assert lookup.exists()
        content = lookup.read_text(encoding="utf-8")
        assert "lexi lookup" in content

    def test_creates_concepts_skill(self, tmp_path: Path) -> None:
        """lexi-concept/SKILL.md is created in .claude/skills/."""
        generate_claude_rules(tmp_path)
        concepts = tmp_path / ".claude" / "skills" / "lexi-concept" / "SKILL.md"
        assert concepts.exists()
        content = concepts.read_text(encoding="utf-8")
        assert "lexi concept" in content

    def test_creates_stack_skill(self, tmp_path: Path) -> None:
        """lexi-stack/SKILL.md is created in .claude/skills/."""
        generate_claude_rules(tmp_path)
        stack = tmp_path / ".claude" / "skills" / "lexi-stack" / "SKILL.md"
        assert stack.exists()
        content = stack.read_text(encoding="utf-8")
        assert "lexi stack" in content

    def test_skill_has_valid_frontmatter(self, tmp_path: Path) -> None:
        """Each skill file starts with YAML frontmatter with name and description fields."""
        import yaml

        generate_claude_rules(tmp_path)
        orient = tmp_path / ".claude" / "skills" / "lexi-orient" / "SKILL.md"
        content = orient.read_text(encoding="utf-8")
        assert content.startswith("---"), "Skill file must start with YAML frontmatter"
        # Extract content between the two --- delimiters
        end = content.index("---", 3)
        fm_text = content[3:end].strip()
        frontmatter = yaml.safe_load(fm_text)
        assert frontmatter["name"] == "lexi-orient"
        assert frontmatter["description"]

    def test_cleans_up_stale_command_files(self, tmp_path: Path) -> None:
        """Stale lexi-orient.md command file is removed during generation."""
        commands_dir = tmp_path / ".claude" / "commands"
        commands_dir.mkdir(parents=True, exist_ok=True)
        stale = commands_dir / "lexi-orient.md"
        stale.write_text("old command content", encoding="utf-8")
        assert stale.exists()

        generate_claude_rules(tmp_path)

        assert not stale.exists()

    def test_preserves_non_lexi_commands(self, tmp_path: Path) -> None:
        """Non-lexi command files in .claude/commands/ are preserved during generation."""
        commands_dir = tmp_path / ".claude" / "commands"
        commands_dir.mkdir(parents=True, exist_ok=True)
        user_cmd = commands_dir / "action.md"
        user_cmd.write_text("# My custom action", encoding="utf-8")

        generate_claude_rules(tmp_path)

        assert user_cmd.exists()


# ---------------------------------------------------------------------------
# Topology-builder skill deployment
# ---------------------------------------------------------------------------


class TestTopologyBuilderSkillDeployment:
    """Test topology-builder skill directory deployment."""

    def test_creates_topology_builder_skill_md(self, tmp_path: Path) -> None:
        """topology-builder/SKILL.md is created in .claude/skills/."""
        generate_claude_rules(tmp_path)
        skill = tmp_path / ".claude" / "skills" / "topology-builder" / "SKILL.md"
        assert skill.exists()

    def test_creates_topology_builder_assets(self, tmp_path: Path) -> None:
        """topology-builder/assets/topology_template.md is created."""
        generate_claude_rules(tmp_path)
        template = (
            tmp_path / ".claude" / "skills" / "topology-builder" / "assets" / "topology_template.md"
        )
        assert template.exists()

    def test_topology_builder_has_frontmatter(self, tmp_path: Path) -> None:
        """topology-builder/SKILL.md starts with YAML frontmatter."""
        import yaml  # noqa: PLC0415

        generate_claude_rules(tmp_path)
        skill = tmp_path / ".claude" / "skills" / "topology-builder" / "SKILL.md"
        content = skill.read_text(encoding="utf-8")
        assert content.startswith("---"), "SKILL.md must start with YAML frontmatter"
        end = content.index("---", 3)
        fm_text = content[3:end].strip()
        frontmatter = yaml.safe_load(fm_text)
        assert "name" in frontmatter
        assert "description" in frontmatter

    def test_topology_builder_in_return_paths(self, tmp_path: Path) -> None:
        """Return value includes topology-builder files."""
        result = generate_claude_rules(tmp_path)
        skill_parents = {p.parent.name for p in result if p.name == "SKILL.md"}
        assert "topology-builder" in skill_parents
        template_names = {p.name for p in result}
        assert "topology_template.md" in template_names

    def test_topology_builder_skill_overwritten_on_update(self, tmp_path: Path) -> None:
        """topology-builder files are overwritten when regenerated."""
        skill = tmp_path / ".claude" / "skills" / "topology-builder" / "SKILL.md"
        skill.parent.mkdir(parents=True, exist_ok=True)
        skill.write_text("old topology skill content", encoding="utf-8")

        generate_claude_rules(tmp_path)

        content = skill.read_text(encoding="utf-8")
        assert "old topology skill content" not in content


# ---------------------------------------------------------------------------
# Folder convention migration — all five lexi skills use per-skill subdirs
# ---------------------------------------------------------------------------


class TestFolderConventionMigration:
    """Verify all five lexi skills use the <name>/SKILL.md folder convention."""

    _LEXI_SKILLS = ["lexi-orient", "lexi-search", "lexi-lookup", "lexi-concept", "lexi-stack"]

    def test_all_lexi_skills_in_subdirs(self, tmp_path: Path) -> None:
        """Each lexi skill is deployed as <name>/SKILL.md in .claude/skills/."""
        generate_claude_rules(tmp_path)
        for skill_name in self._LEXI_SKILLS:
            skill_path = tmp_path / ".claude" / "skills" / skill_name / "SKILL.md"
            assert skill_path.exists(), f"{skill_name}/SKILL.md not found"

    def test_no_flat_skill_files(self, tmp_path: Path) -> None:
        """No flat .md skill files should exist directly in .claude/skills/."""
        generate_claude_rules(tmp_path)
        skills_dir = tmp_path / ".claude" / "skills"
        flat_md_files = list(skills_dir.glob("*.md"))
        assert flat_md_files == [], f"Unexpected flat skill files: {flat_md_files}"

    def test_each_skill_has_valid_frontmatter(self, tmp_path: Path) -> None:
        """Each lexi skill SKILL.md has name and description in frontmatter."""
        import yaml  # noqa: PLC0415

        generate_claude_rules(tmp_path)
        for skill_name in self._LEXI_SKILLS:
            skill_path = tmp_path / ".claude" / "skills" / skill_name / "SKILL.md"
            content = skill_path.read_text(encoding="utf-8")
            assert content.startswith("---"), f"{skill_name} missing frontmatter"
            end = content.index("---", 3)
            fm = yaml.safe_load(content[3:end].strip())
            assert fm["name"] == skill_name, f"{skill_name} has wrong name: {fm.get('name')}"
            assert fm.get("description"), f"{skill_name} missing description"


# ---------------------------------------------------------------------------
# Gitignore patterns include .lexibrary/tmp/
# ---------------------------------------------------------------------------


class TestGitignorePatterns:
    """.lexibrary/tmp/ is included in generated .gitignore patterns."""

    def test_tmp_pattern_in_generated_patterns(self) -> None:
        """_GENERATED_GITIGNORE_PATTERNS includes .lexibrary/tmp/."""
        from lexibrary.init.scaffolder import _GENERATED_GITIGNORE_PATTERNS  # noqa: PLC0415

        assert ".lexibrary/tmp/" in _GENERATED_GITIGNORE_PATTERNS


# ---------------------------------------------------------------------------
# Settings.json generation
# ---------------------------------------------------------------------------


class TestSettingsJsonGeneration:
    """settings.json is generated with correct permissions."""

    def test_creates_settings_json(self, tmp_path: Path) -> None:
        """_generate_settings_json() creates .claude/settings.json."""
        _generate_settings_json(tmp_path)
        settings_file = tmp_path / ".claude" / "settings.json"
        assert settings_file.exists()

    def test_settings_has_permissions_allow(self, tmp_path: Path) -> None:
        """settings.json contains permissions.allow list with explicit entries."""
        _generate_settings_json(tmp_path)
        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
        assert "permissions" in settings
        assert "allow" in settings["permissions"]
        allow = settings["permissions"]["allow"]
        assert "Bash(lexi orient)" in allow
        assert "Bash(lexi lookup *)" in allow
        assert "Bash(lexi impact *)" in allow
        assert "Bash(lexi concept new *)" in allow
        assert "Bash(lexi convention new *)" in allow

    def test_settings_has_permissions_deny(self, tmp_path: Path) -> None:
        """settings.json contains permissions.deny list."""
        _generate_settings_json(tmp_path)
        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
        deny = settings["permissions"]["deny"]
        assert "Bash(lexictl *)" in deny

    def test_settings_has_hooks(self, tmp_path: Path) -> None:
        """settings.json contains hooks section with PreToolUse and PostToolUse."""
        _generate_settings_json(tmp_path)
        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
        assert "hooks" in settings
        assert "PreToolUse" in settings["hooks"]
        assert "PostToolUse" in settings["hooks"]

    def test_pre_tool_use_hook_config(self, tmp_path: Path) -> None:
        """PreToolUse hook matches Edit|Write tools with correct timeout."""
        _generate_settings_json(tmp_path)
        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
        pre_hooks = settings["hooks"]["PreToolUse"]
        assert len(pre_hooks) >= 1
        assert pre_hooks[0]["matcher"] == "Edit|Write"
        assert pre_hooks[0]["hooks"][0]["timeout"] == 10000

    def test_post_tool_use_hook_config(self, tmp_path: Path) -> None:
        """PostToolUse hook matches Edit|Write tools with correct timeout."""
        _generate_settings_json(tmp_path)
        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
        post_hooks = settings["hooks"]["PostToolUse"]
        assert len(post_hooks) >= 1
        assert post_hooks[0]["matcher"] == "Edit|Write"
        assert post_hooks[0]["hooks"][0]["timeout"] == 15000

    def test_creates_claude_directory(self, tmp_path: Path) -> None:
        """.claude/ directory is created if it does not exist."""
        _generate_settings_json(tmp_path)
        assert (tmp_path / ".claude").is_dir()


class TestSettingsJsonMerge:
    """settings.json merge preserves user entries."""

    def test_merges_with_existing_allow_entries(self, tmp_path: Path) -> None:
        """Existing allow entries are preserved when merging."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        existing = {
            "permissions": {
                "allow": ["Bash(my-custom-command *)"],
                "deny": [],
            }
        }
        (claude_dir / "settings.json").write_text(json.dumps(existing), encoding="utf-8")

        _generate_settings_json(tmp_path)

        settings = json.loads((claude_dir / "settings.json").read_text(encoding="utf-8"))
        allow = settings["permissions"]["allow"]
        assert "Bash(my-custom-command *)" in allow
        assert "Bash(lexi orient)" in allow

    def test_merges_with_existing_deny_entries(self, tmp_path: Path) -> None:
        """Existing deny entries are preserved when merging."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        existing = {
            "permissions": {
                "allow": [],
                "deny": ["Bash(dangerous-command *)"],
            }
        }
        (claude_dir / "settings.json").write_text(json.dumps(existing), encoding="utf-8")

        _generate_settings_json(tmp_path)

        settings = json.loads((claude_dir / "settings.json").read_text(encoding="utf-8"))
        deny = settings["permissions"]["deny"]
        assert "Bash(dangerous-command *)" in deny
        assert "Bash(lexictl *)" in deny

    def test_preserves_non_permission_keys(self, tmp_path: Path) -> None:
        """Non-permission keys in existing settings.json are preserved."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        existing = {
            "mcpServers": {"myServer": {"url": "http://localhost:3000"}},
            "permissions": {"allow": [], "deny": []},
        }
        (claude_dir / "settings.json").write_text(json.dumps(existing), encoding="utf-8")

        _generate_settings_json(tmp_path)

        settings = json.loads((claude_dir / "settings.json").read_text(encoding="utf-8"))
        assert "mcpServers" in settings
        assert settings["mcpServers"]["myServer"]["url"] == "http://localhost:3000"

    def test_merges_with_existing_user_hooks(self, tmp_path: Path) -> None:
        """User-defined hooks are preserved when merging."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        existing = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [{"type": "command", "command": "my-script.sh"}],
                    }
                ]
            }
        }
        (claude_dir / "settings.json").write_text(json.dumps(existing), encoding="utf-8")

        _generate_settings_json(tmp_path)

        settings = json.loads((claude_dir / "settings.json").read_text(encoding="utf-8"))
        pre_hooks = settings["hooks"]["PreToolUse"]
        # User hook + our hook
        assert len(pre_hooks) == 2
        commands = []
        for entry in pre_hooks:
            for hook in entry.get("hooks", []):
                commands.append(hook.get("command", ""))
        assert "my-script.sh" in commands


class TestSettingsJsonIdempotency:
    """settings.json generation is idempotent."""

    def test_idempotent_generation(self, tmp_path: Path) -> None:
        """Calling _generate_settings_json() twice produces identical output."""
        _generate_settings_json(tmp_path)
        first = (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")

        _generate_settings_json(tmp_path)
        second = (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")

        assert first == second

    def test_no_duplicate_allow_entries(self, tmp_path: Path) -> None:
        """Running twice does not create duplicate allow entries."""
        _generate_settings_json(tmp_path)
        _generate_settings_json(tmp_path)

        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
        allow = settings["permissions"]["allow"]
        assert len(allow) == len(set(allow))

    def test_no_duplicate_hook_entries(self, tmp_path: Path) -> None:
        """Running twice does not create duplicate hook entries."""
        _generate_settings_json(tmp_path)
        _generate_settings_json(tmp_path)

        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
        pre_hooks = settings["hooks"]["PreToolUse"]
        assert len(pre_hooks) == 1

    def test_allow_entries_sorted(self, tmp_path: Path) -> None:
        """Allow entries are sorted after merge."""
        _generate_settings_json(tmp_path)

        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
        allow = settings["permissions"]["allow"]
        assert allow == sorted(allow)


# ---------------------------------------------------------------------------
# Hook script generation
# ---------------------------------------------------------------------------


class TestHookScriptGeneration:
    """Hook scripts are generated as executable files."""

    def test_creates_pre_edit_script(self, tmp_path: Path) -> None:
        """lexi-pre-edit.sh is created in .claude/hooks/."""
        _generate_hook_scripts(tmp_path)
        pre_edit = tmp_path / ".claude" / "hooks" / "lexi-pre-edit.sh"
        assert pre_edit.exists()

    def test_creates_post_edit_script(self, tmp_path: Path) -> None:
        """lexi-post-edit.sh is created in .claude/hooks/."""
        _generate_hook_scripts(tmp_path)
        post_edit = tmp_path / ".claude" / "hooks" / "lexi-post-edit.sh"
        assert post_edit.exists()

    def test_pre_edit_is_executable(self, tmp_path: Path) -> None:
        """Pre-edit hook script has executable permission."""
        _generate_hook_scripts(tmp_path)
        pre_edit = tmp_path / ".claude" / "hooks" / "lexi-pre-edit.sh"
        mode = pre_edit.stat().st_mode
        assert mode & stat.S_IXUSR

    def test_post_edit_is_executable(self, tmp_path: Path) -> None:
        """Post-edit hook script has executable permission."""
        _generate_hook_scripts(tmp_path)
        post_edit = tmp_path / ".claude" / "hooks" / "lexi-post-edit.sh"
        mode = post_edit.stat().st_mode
        assert mode & stat.S_IXUSR

    def test_pre_edit_contains_lexi_lookup(self, tmp_path: Path) -> None:
        """Pre-edit script runs lexi lookup."""
        _generate_hook_scripts(tmp_path)
        content = (tmp_path / ".claude" / "hooks" / "lexi-pre-edit.sh").read_text(encoding="utf-8")
        assert "lexi lookup" in content

    def test_pre_edit_reads_file_path_from_stdin(self, tmp_path: Path) -> None:
        """Pre-edit script extracts file_path from stdin JSON."""
        _generate_hook_scripts(tmp_path)
        content = (tmp_path / ".claude" / "hooks" / "lexi-pre-edit.sh").read_text(encoding="utf-8")
        assert "file_path" in content

    def test_pre_edit_uses_hook_specific_output(self, tmp_path: Path) -> None:
        """Pre-edit script uses hookSpecificOutput wrapper with jq for JSON escaping."""
        _generate_hook_scripts(tmp_path)
        content = (tmp_path / ".claude" / "hooks" / "lexi-pre-edit.sh").read_text(encoding="utf-8")
        assert "hookSpecificOutput" in content
        assert "hookEventName" in content
        assert "PreToolUse" in content
        assert "jq" in content

    def test_post_edit_uses_hook_specific_output(self, tmp_path: Path) -> None:
        """Post-edit script uses hookSpecificOutput wrapper with additionalContext."""
        _generate_hook_scripts(tmp_path)
        content = (tmp_path / ".claude" / "hooks" / "lexi-post-edit.sh").read_text(encoding="utf-8")
        assert "hookSpecificOutput" in content
        assert "hookEventName" in content
        assert "PostToolUse" in content
        assert "additionalContext" in content
        assert "systemMessage" not in content

    def test_post_edit_excludes_non_source_paths(self, tmp_path: Path) -> None:
        """Post-edit script skips .lexibrary/, blueprints/, .claude/, .cursor/ paths."""
        _generate_hook_scripts(tmp_path)
        content = (tmp_path / ".claude" / "hooks" / "lexi-post-edit.sh").read_text(encoding="utf-8")
        assert ".lexibrary/*" in content
        assert "blueprints/*" in content
        assert ".claude/*" in content
        assert ".cursor/*" in content

    def test_pre_edit_has_shebang(self, tmp_path: Path) -> None:
        """Pre-edit script starts with a shebang line."""
        _generate_hook_scripts(tmp_path)
        content = (tmp_path / ".claude" / "hooks" / "lexi-pre-edit.sh").read_text(encoding="utf-8")
        assert content.startswith("#!/")

    def test_post_edit_has_shebang(self, tmp_path: Path) -> None:
        """Post-edit script starts with a shebang line."""
        _generate_hook_scripts(tmp_path)
        content = (tmp_path / ".claude" / "hooks" / "lexi-post-edit.sh").read_text(encoding="utf-8")
        assert content.startswith("#!/")

    def test_scripts_overwritten_on_regeneration(self, tmp_path: Path) -> None:
        """Hook scripts are overwritten when regenerated."""
        hooks_dir = tmp_path / ".claude" / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        pre_edit = hooks_dir / "lexi-pre-edit.sh"
        pre_edit.write_text("old hook content", encoding="utf-8")

        _generate_hook_scripts(tmp_path)

        content = pre_edit.read_text(encoding="utf-8")
        assert "old hook content" not in content
        assert "lexi lookup" in content

    def test_returns_two_paths(self, tmp_path: Path) -> None:
        """_generate_hook_scripts() returns paths to both scripts."""
        result = _generate_hook_scripts(tmp_path)
        assert len(result) == 2
        filenames = [p.name for p in result]
        assert "lexi-pre-edit.sh" in filenames
        assert "lexi-post-edit.sh" in filenames

    def test_creates_hooks_directory(self, tmp_path: Path) -> None:
        """.claude/hooks/ directory is created if it does not exist."""
        _generate_hook_scripts(tmp_path)
        assert (tmp_path / ".claude" / "hooks").is_dir()


class TestPostEditHookSkeletonIntegration:
    """PostToolUse hook script integrates skeleton generation and enrichment queue."""

    def test_post_edit_calls_lexictl_skeleton(self, tmp_path: Path) -> None:
        """Post-edit hook script calls lexictl update --skeleton for missing design files."""
        _generate_hook_scripts(tmp_path)
        content = (tmp_path / ".claude" / "hooks" / "lexi-post-edit.sh").read_text(encoding="utf-8")
        assert "lexictl update --skeleton" in content

    def test_post_edit_checks_design_file_existence(self, tmp_path: Path) -> None:
        """Post-edit hook resolves and checks design file path."""
        _generate_hook_scripts(tmp_path)
        content = (tmp_path / ".claude" / "hooks" / "lexi-post-edit.sh").read_text(encoding="utf-8")
        assert ".lexibrary/designs/" in content
        assert "DESIGN_FILE=" in content

    def test_post_edit_resolves_project_root(self, tmp_path: Path) -> None:
        """Post-edit hook resolves the project root from CLAUDE_PROJECT_DIR."""
        _generate_hook_scripts(tmp_path)
        content = (tmp_path / ".claude" / "hooks" / "lexi-post-edit.sh").read_text(encoding="utf-8")
        assert "CLAUDE_PROJECT_DIR" in content
        assert "PROJECT_DIR" in content

    def test_post_edit_skips_git_paths(self, tmp_path: Path) -> None:
        """Post-edit hook skips .git/ paths in addition to other non-source paths."""
        _generate_hook_scripts(tmp_path)
        content = (tmp_path / ".claude" / "hooks" / "lexi-post-edit.sh").read_text(encoding="utf-8")
        assert ".git/*" in content

    def test_post_edit_emits_skeleton_generated_message(self, tmp_path: Path) -> None:
        """Post-edit hook emits message about skeleton generation."""
        _generate_hook_scripts(tmp_path)
        content = (tmp_path / ".claude" / "hooks" / "lexi-post-edit.sh").read_text(encoding="utf-8")
        assert "Auto-generated skeleton design file" in content
        assert "queued it for LLM enrichment" in content

    def test_post_edit_falls_back_to_reminder_on_failure(self, tmp_path: Path) -> None:
        """Post-edit hook falls back to reminder if skeleton generation fails."""
        _generate_hook_scripts(tmp_path)
        content = (tmp_path / ".claude" / "hooks" / "lexi-post-edit.sh").read_text(encoding="utf-8")
        assert "No design file found" in content

    def test_post_edit_emits_reminder_when_design_exists(self, tmp_path: Path) -> None:
        """Post-edit hook emits update reminder when design file already exists."""
        _generate_hook_scripts(tmp_path)
        content = (tmp_path / ".claude" / "hooks" / "lexi-post-edit.sh").read_text(encoding="utf-8")
        assert "Remember to update the corresponding design file" in content

    def test_post_edit_falls_back_without_lexibrary(self, tmp_path: Path) -> None:
        """Post-edit hook falls back gracefully when no .lexibrary directory exists."""
        _generate_hook_scripts(tmp_path)
        content = (tmp_path / ".claude" / "hooks" / "lexi-post-edit.sh").read_text(encoding="utf-8")
        # Should check for .lexibrary existence
        assert ".lexibrary" in content


class TestPostEditDependentsWarning:
    """Post-edit hook calls lexi impact to warn about downstream dependents."""

    def test_post_edit_calls_lexi_impact(self, tmp_path: Path) -> None:
        """Post-edit hook runs lexi impact --depth 1 --quiet on edited file."""
        _generate_hook_scripts(tmp_path)
        content = (tmp_path / ".claude" / "hooks" / "lexi-post-edit.sh").read_text(encoding="utf-8")
        assert "lexi impact" in content
        assert "--depth 1" in content
        assert "--quiet" in content

    def test_post_edit_appends_dependents_to_additional_context(self, tmp_path: Path) -> None:
        """Post-edit hook appends dependents list to additionalContext when present."""
        _generate_hook_scripts(tmp_path)
        content = (tmp_path / ".claude" / "hooks" / "lexi-post-edit.sh").read_text(encoding="utf-8")
        assert "Dependents that may need updating" in content
        assert "DEPENDENTS" in content

    def test_post_edit_skips_dependents_when_empty(self, tmp_path: Path) -> None:
        """Post-edit hook does not append dependents warning when none found."""
        _generate_hook_scripts(tmp_path)
        content = (tmp_path / ".claude" / "hooks" / "lexi-post-edit.sh").read_text(encoding="utf-8")
        # Should check if DEPENDENTS is non-empty before appending
        assert 'if [ -n "$DEPENDENTS" ]' in content

    def test_post_edit_impact_graceful_degradation(self, tmp_path: Path) -> None:
        """Post-edit hook continues without warning if lexi impact fails or times out."""
        _generate_hook_scripts(tmp_path)
        content = (tmp_path / ".claude" / "hooks" / "lexi-post-edit.sh").read_text(encoding="utf-8")
        # Should suppress stderr and use || true for graceful degradation
        assert "2>/dev/null" in content
        assert "|| true" in content
        # Should check if lexi command exists before calling
        assert "command -v lexi" in content


# ---------------------------------------------------------------------------
# Agent file generation
# ---------------------------------------------------------------------------


class TestAgentFileGeneration:
    """Agent definition files are generated in .claude/agents/."""

    def test_creates_explore_agent(self, tmp_path: Path) -> None:
        """explore.md is created in .claude/agents/."""
        _generate_agent_files(tmp_path)
        explore = tmp_path / ".claude" / "agents" / "explore.md"
        assert explore.exists()

    def test_creates_agents_directory(self, tmp_path: Path) -> None:
        """.claude/agents/ directory is created if it does not exist."""
        _generate_agent_files(tmp_path)
        assert (tmp_path / ".claude" / "agents").is_dir()

    def test_explore_has_yaml_frontmatter(self, tmp_path: Path) -> None:
        """explore.md starts with YAML frontmatter delimiters."""
        _generate_agent_files(tmp_path)
        content = (tmp_path / ".claude" / "agents" / "explore.md").read_text(encoding="utf-8")
        assert content.startswith("---\n")
        # Find the closing frontmatter delimiter (second ---)
        second_delim = content.index("---", 4)
        assert second_delim > 4

    def test_explore_frontmatter_has_name(self, tmp_path: Path) -> None:
        """explore.md frontmatter contains name: Explore."""
        _generate_agent_files(tmp_path)
        content = (tmp_path / ".claude" / "agents" / "explore.md").read_text(encoding="utf-8")
        assert "name: Explore" in content

    def test_explore_frontmatter_has_model(self, tmp_path: Path) -> None:
        """explore.md frontmatter specifies model: haiku."""
        _generate_agent_files(tmp_path)
        content = (tmp_path / ".claude" / "agents" / "explore.md").read_text(encoding="utf-8")
        assert "model: haiku" in content

    def test_explore_frontmatter_has_tools(self, tmp_path: Path) -> None:
        """explore.md frontmatter lists Read, Bash tools (lexi CLI replaces Grep/Glob)."""
        _generate_agent_files(tmp_path)
        content = (tmp_path / ".claude" / "agents" / "explore.md").read_text(encoding="utf-8")
        assert "- Read" in content
        assert "- Bash" in content

    def test_explore_has_lexi_commands(self, tmp_path: Path) -> None:
        """explore.md system prompt lists available lexi commands."""
        _generate_agent_files(tmp_path)
        content = (tmp_path / ".claude" / "agents" / "explore.md").read_text(encoding="utf-8")
        assert "lexi search" in content
        assert "lexi lookup" in content
        assert "lexi concept" in content
        assert "lexi conventions" in content

    def test_explore_has_fallback_instructions(self, tmp_path: Path) -> None:
        """explore.md instructs fallback to Glob/Grep/Read for unindexed projects."""
        _generate_agent_files(tmp_path)
        content = (tmp_path / ".claude" / "agents" / "explore.md").read_text(encoding="utf-8")
        assert ".lexibrary/" in content
        assert "Glob" in content
        assert "Grep" in content

    def test_explore_has_thoroughness_levels(self, tmp_path: Path) -> None:
        """explore.md system prompt describes quick/medium/thorough levels."""
        _generate_agent_files(tmp_path)
        content = (tmp_path / ".claude" / "agents" / "explore.md").read_text(encoding="utf-8")
        assert "quick" in content
        assert "medium" in content
        assert "very thorough" in content

    def test_explore_overwritten_on_regeneration(self, tmp_path: Path) -> None:
        """explore.md is overwritten when regenerated."""
        agents_dir = tmp_path / ".claude" / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        explore = agents_dir / "explore.md"
        explore.write_text("old agent content", encoding="utf-8")

        _generate_agent_files(tmp_path)

        content = explore.read_text(encoding="utf-8")
        assert "old agent content" not in content
        assert "name: Explore" in content

    def test_returns_four_paths(self, tmp_path: Path) -> None:
        """_generate_agent_files() returns paths to all four agent files."""
        result = _generate_agent_files(tmp_path)
        assert len(result) == 4
        filenames = [p.name for p in result]
        assert "explore.md" in filenames
        assert "plan.md" in filenames
        assert "code.md" in filenames
        assert "lexi-research.md" in filenames

    def test_generate_claude_rules_creates_explore_agent(self, tmp_path: Path) -> None:
        """generate_claude_rules() creates .claude/agents/explore.md."""
        generate_claude_rules(tmp_path)
        explore = tmp_path / ".claude" / "agents" / "explore.md"
        assert explore.exists()
        content = explore.read_text(encoding="utf-8")
        assert "name: Explore" in content

    # --- Explore agent: mandatory orient, stack search, IWH prohibition ---

    def test_explore_has_mandatory_orient(self, tmp_path: Path) -> None:
        """explore.md contains mandatory lexi orient first step."""
        _generate_agent_files(tmp_path)
        content = (tmp_path / ".claude" / "agents" / "explore.md").read_text(encoding="utf-8")
        assert "MANDATORY FIRST STEP" in content
        assert "lexi orient" in content

    def test_explore_has_stack_search(self, tmp_path: Path) -> None:
        """explore.md includes lexi stack search in workflow."""
        _generate_agent_files(tmp_path)
        content = (tmp_path / ".claude" / "agents" / "explore.md").read_text(encoding="utf-8")
        assert "lexi stack search" in content

    def test_explore_has_iwh_prohibition(self, tmp_path: Path) -> None:
        """explore.md prohibits IWH consumption."""
        _generate_agent_files(tmp_path)
        content = (tmp_path / ".claude" / "agents" / "explore.md").read_text(encoding="utf-8")
        assert "Do NOT run `lexi iwh read`" in content

    # --- Plan agent content tests ---

    def test_creates_plan_agent(self, tmp_path: Path) -> None:
        """plan.md is created in .claude/agents/."""
        _generate_agent_files(tmp_path)
        assert (tmp_path / ".claude" / "agents" / "plan.md").exists()

    def test_plan_has_yaml_frontmatter(self, tmp_path: Path) -> None:
        """plan.md starts with YAML frontmatter."""
        _generate_agent_files(tmp_path)
        content = (tmp_path / ".claude" / "agents" / "plan.md").read_text(encoding="utf-8")
        assert content.startswith("---\n")
        assert "name: Plan" in content

    def test_plan_has_mandatory_orient(self, tmp_path: Path) -> None:
        """plan.md contains mandatory lexi orient first step."""
        _generate_agent_files(tmp_path)
        content = (tmp_path / ".claude" / "agents" / "plan.md").read_text(encoding="utf-8")
        assert "MANDATORY FIRST STEP" in content
        assert "lexi orient" in content

    def test_plan_has_iwh_prohibition(self, tmp_path: Path) -> None:
        """plan.md prohibits IWH consumption."""
        _generate_agent_files(tmp_path)
        content = (tmp_path / ".claude" / "agents" / "plan.md").read_text(encoding="utf-8")
        assert "Do NOT run `lexi iwh read`" in content

    def test_plan_has_tools(self, tmp_path: Path) -> None:
        """plan.md frontmatter lists Glob, Grep, WebSearch tools."""
        _generate_agent_files(tmp_path)
        content = (tmp_path / ".claude" / "agents" / "plan.md").read_text(encoding="utf-8")
        assert "- Read" in content
        assert "- Bash" in content
        assert "- Glob" in content
        assert "- Grep" in content
        assert "- WebSearch" in content

    # --- Code agent content tests ---

    def test_creates_code_agent(self, tmp_path: Path) -> None:
        """code.md is created in .claude/agents/."""
        _generate_agent_files(tmp_path)
        assert (tmp_path / ".claude" / "agents" / "code.md").exists()

    def test_code_has_yaml_frontmatter(self, tmp_path: Path) -> None:
        """code.md starts with YAML frontmatter."""
        _generate_agent_files(tmp_path)
        content = (tmp_path / ".claude" / "agents" / "code.md").read_text(encoding="utf-8")
        assert content.startswith("---\n")
        assert "name: Code" in content

    def test_code_has_mandatory_orient(self, tmp_path: Path) -> None:
        """code.md contains mandatory lexi orient first step."""
        _generate_agent_files(tmp_path)
        content = (tmp_path / ".claude" / "agents" / "code.md").read_text(encoding="utf-8")
        assert "MANDATORY FIRST STEP" in content
        assert "lexi orient" in content

    def test_code_has_model_sonnet(self, tmp_path: Path) -> None:
        """code.md specifies model: sonnet."""
        _generate_agent_files(tmp_path)
        content = (tmp_path / ".claude" / "agents" / "code.md").read_text(encoding="utf-8")
        assert "model: sonnet" in content

    def test_code_has_tools(self, tmp_path: Path) -> None:
        """code.md frontmatter lists Write, Edit, TodoWrite, WebSearch tools."""
        _generate_agent_files(tmp_path)
        content = (tmp_path / ".claude" / "agents" / "code.md").read_text(encoding="utf-8")
        assert "- Write" in content
        assert "- Edit" in content
        assert "- TodoWrite" in content
        assert "- WebSearch" in content

    def test_code_has_knowledge_capture(self, tmp_path: Path) -> None:
        """code.md includes knowledge capture section with stack post, convention, concept."""
        _generate_agent_files(tmp_path)
        content = (tmp_path / ".claude" / "agents" / "code.md").read_text(encoding="utf-8")
        assert "Knowledge Capture" in content
        assert "lexi stack post" in content
        assert "lexi convention new" in content
        assert "lexi concept new" in content

    def test_code_has_iwh_write_protocol(self, tmp_path: Path) -> None:
        """code.md includes IWH write protocol for leaving work incomplete."""
        _generate_agent_files(tmp_path)
        content = (tmp_path / ".claude" / "agents" / "code.md").read_text(encoding="utf-8")
        assert "lexi iwh write" in content
        assert "--scope incomplete" in content
        assert "--scope blocked" in content

    # --- Research agent content tests ---

    def test_creates_research_agent(self, tmp_path: Path) -> None:
        """lexi-research.md is created in .claude/agents/."""
        _generate_agent_files(tmp_path)
        assert (tmp_path / ".claude" / "agents" / "lexi-research.md").exists()

    def test_research_has_yaml_frontmatter(self, tmp_path: Path) -> None:
        """lexi-research.md starts with YAML frontmatter."""
        _generate_agent_files(tmp_path)
        content = (tmp_path / ".claude" / "agents" / "lexi-research.md").read_text(encoding="utf-8")
        assert content.startswith("---\n")
        assert "name: Lexi Research" in content

    def test_research_has_tools(self, tmp_path: Path) -> None:
        """lexi-research.md frontmatter lists Read and Bash tools."""
        _generate_agent_files(tmp_path)
        content = (tmp_path / ".claude" / "agents" / "lexi-research.md").read_text(encoding="utf-8")
        assert "- Read" in content
        assert "- Bash" in content

    def test_research_has_workflow_steps(self, tmp_path: Path) -> None:
        """lexi-research.md contains the 5-step research workflow."""
        _generate_agent_files(tmp_path)
        content = (tmp_path / ".claude" / "agents" / "lexi-research.md").read_text(encoding="utf-8")
        assert "Step 1" in content
        assert "Step 2" in content
        assert "Step 3" in content
        assert "Step 4" in content
        assert "Step 5" in content

    def test_research_prohibits_code_writes(self, tmp_path: Path) -> None:
        """lexi-research.md prohibits writing or editing code."""
        _generate_agent_files(tmp_path)
        content = (tmp_path / ".claude" / "agents" / "lexi-research.md").read_text(encoding="utf-8")
        assert "Do NOT write or edit code" in content

    def test_research_prohibits_iwh_consumption(self, tmp_path: Path) -> None:
        """lexi-research.md prohibits IWH signal consumption."""
        _generate_agent_files(tmp_path)
        content = (tmp_path / ".claude" / "agents" / "lexi-research.md").read_text(encoding="utf-8")
        assert "Do NOT consume IWH signals" in content

    def test_research_prohibits_stack_posting(self, tmp_path: Path) -> None:
        """lexi-research.md prohibits posting to the stack."""
        _generate_agent_files(tmp_path)
        content = (tmp_path / ".claude" / "agents" / "lexi-research.md").read_text(encoding="utf-8")
        assert "Do NOT post to the stack" in content


# ---------------------------------------------------------------------------
# Integration tests: full generation pipeline
# ---------------------------------------------------------------------------


class TestIntegrationFullGeneration:
    """Integration: generate_claude_rules() produces all expected files.

    Verifies that a single call to generate_claude_rules() on a clean
    directory produces every expected output file including the explore
    agent definition file.
    """

    def test_all_expected_files_exist(self, tmp_path: Path) -> None:
        """Every expected output file is created on disk."""
        generate_claude_rules(tmp_path)

        expected_files = [
            tmp_path / "CLAUDE.md",
            tmp_path / ".claude" / "settings.json",
            tmp_path / ".claude" / "hooks" / "lexi-pre-edit.sh",
            tmp_path / ".claude" / "hooks" / "lexi-post-edit.sh",
            tmp_path / ".claude" / "agents" / "explore.md",
            tmp_path / ".claude" / "agents" / "plan.md",
            tmp_path / ".claude" / "agents" / "code.md",
            tmp_path / ".claude" / "agents" / "lexi-research.md",
            tmp_path / ".claude" / "skills" / "lexi-orient" / "SKILL.md",
            tmp_path / ".claude" / "skills" / "lexi-search" / "SKILL.md",
            tmp_path / ".claude" / "skills" / "lexi-lookup" / "SKILL.md",
            tmp_path / ".claude" / "skills" / "lexi-concept" / "SKILL.md",
            tmp_path / ".claude" / "skills" / "lexi-stack" / "SKILL.md",
        ]

        for expected in expected_files:
            assert expected.exists(), f"Missing expected file: {expected}"

    def test_returned_paths_match_expected_count(self, tmp_path: Path) -> None:
        """generate_claude_rules() returns exactly 15 paths."""
        result = generate_claude_rules(tmp_path)
        assert len(result) == 15

    def test_returned_paths_all_exist_on_disk(self, tmp_path: Path) -> None:
        """Every path in the returned list points to an existing file."""
        result = generate_claude_rules(tmp_path)
        for path in result:
            assert path.exists(), f"Returned path does not exist: {path}"

    def test_returned_paths_are_absolute(self, tmp_path: Path) -> None:
        """Every path in the returned list is absolute."""
        result = generate_claude_rules(tmp_path)
        for path in result:
            assert path.is_absolute(), f"Returned path is not absolute: {path}"

    def test_subagent_start_not_in_settings(self, tmp_path: Path) -> None:
        """settings.json does not include a SubagentStart hook (removed)."""
        generate_claude_rules(tmp_path)
        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
        assert "SubagentStart" not in settings["hooks"]

    def test_explore_context_script_not_generated(self, tmp_path: Path) -> None:
        """The explore-context hook script is not generated."""
        generate_claude_rules(tmp_path)
        explore_script = tmp_path / ".claude" / "hooks" / "lexi-explore-context.sh"
        assert not explore_script.exists()

    def test_stale_explore_context_script_deleted(self, tmp_path: Path) -> None:
        """A pre-existing lexi-explore-context.sh is removed during generation."""
        hooks_dir = tmp_path / ".claude" / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        stale_script = hooks_dir / "lexi-explore-context.sh"
        stale_script.write_text("#!/bin/bash\n# old script", encoding="utf-8")
        assert stale_script.exists()

        generate_claude_rules(tmp_path)

        assert not stale_script.exists()

    def test_explore_agent_content(self, tmp_path: Path) -> None:
        """The explore agent file has expected content after full generation."""
        generate_claude_rules(tmp_path)
        content = (tmp_path / ".claude" / "agents" / "explore.md").read_text(encoding="utf-8")
        assert content.startswith("---\n")
        assert "name: Explore" in content
        assert "model: haiku" in content
        assert "lexi search" in content

    def test_wildcard_absent_from_permissions(self, tmp_path: Path) -> None:
        """settings.json allow list does not contain Bash(lexi *) wildcard."""
        generate_claude_rules(tmp_path)
        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
        allow = settings["permissions"]["allow"]
        assert "Bash(lexi *)" not in allow

    def test_context_dump_absent_from_permissions(self, tmp_path: Path) -> None:
        """settings.json allow list does not include Bash(lexi context-dump)."""
        generate_claude_rules(tmp_path)
        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
        allow = settings["permissions"]["allow"]
        assert "Bash(lexi context-dump)" not in allow

    def test_orient_in_permissions(self, tmp_path: Path) -> None:
        """settings.json allow list includes Bash(lexi orient)."""
        generate_claude_rules(tmp_path)
        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
        allow = settings["permissions"]["allow"]
        assert "Bash(lexi orient)" in allow

    def test_all_hook_types_in_settings(self, tmp_path: Path) -> None:
        """settings.json contains PreToolUse and PostToolUse hooks."""
        generate_claude_rules(tmp_path)
        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
        hooks = settings["hooks"]
        assert "PreToolUse" in hooks
        assert "PostToolUse" in hooks

    def test_all_files_non_empty(self, tmp_path: Path) -> None:
        """Every generated file has non-zero size."""
        result = generate_claude_rules(tmp_path)
        for path in result:
            assert path.stat().st_size > 0, f"File is empty: {path}"

    def test_directory_structure_created(self, tmp_path: Path) -> None:
        """All required subdirectories are created."""
        generate_claude_rules(tmp_path)
        assert (tmp_path / ".claude").is_dir()
        assert (tmp_path / ".claude" / "hooks").is_dir()
        assert (tmp_path / ".claude" / "agents").is_dir()
        assert (tmp_path / ".claude" / "skills").is_dir()


# ---------------------------------------------------------------------------
# Integration tests: idempotent generation
# ---------------------------------------------------------------------------


class TestIntegrationIdempotentGeneration:
    """Integration: running generate_claude_rules() twice produces identical output.

    Verifies that the full generation pipeline is idempotent: a second call
    with no external changes produces byte-identical files.
    """

    def test_full_generation_idempotent(self, tmp_path: Path) -> None:
        """Calling generate_claude_rules() twice produces identical file contents."""
        generate_claude_rules(tmp_path)

        # Snapshot all generated file contents after first run
        first_run: dict[str, str] = {}
        for path in tmp_path.rglob("*"):
            if path.is_file():
                rel = str(path.relative_to(tmp_path))
                first_run[rel] = path.read_text(encoding="utf-8")

        # Run again
        generate_claude_rules(tmp_path)

        # Snapshot after second run
        second_run: dict[str, str] = {}
        for path in tmp_path.rglob("*"):
            if path.is_file():
                rel = str(path.relative_to(tmp_path))
                second_run[rel] = path.read_text(encoding="utf-8")

        assert first_run.keys() == second_run.keys(), (
            f"File sets differ: "
            f"only in first={first_run.keys() - second_run.keys()}, "
            f"only in second={second_run.keys() - first_run.keys()}"
        )

        for rel_path in first_run:
            assert first_run[rel_path] == second_run[rel_path], (
                f"Content differs after second run: {rel_path}"
            )

    def test_idempotent_return_value(self, tmp_path: Path) -> None:
        """generate_claude_rules() returns the same paths on both calls."""
        first = generate_claude_rules(tmp_path)
        second = generate_claude_rules(tmp_path)

        first_set = {str(p) for p in first}
        second_set = {str(p) for p in second}
        assert first_set == second_set

    def test_idempotent_settings_json(self, tmp_path: Path) -> None:
        """settings.json is byte-identical after two full generation runs."""
        generate_claude_rules(tmp_path)
        first = (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")

        generate_claude_rules(tmp_path)
        second = (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")

        assert first == second

    def test_idempotent_no_duplicate_hooks(self, tmp_path: Path) -> None:
        """No hook entries are duplicated after two full generation runs."""
        generate_claude_rules(tmp_path)
        generate_claude_rules(tmp_path)

        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
        for event_type, entries in settings["hooks"].items():
            assert len(entries) == 1, f"Expected 1 entry for {event_type}, got {len(entries)}"

    def test_idempotent_no_duplicate_permissions(self, tmp_path: Path) -> None:
        """No permission entries are duplicated after two full generation runs."""
        generate_claude_rules(tmp_path)
        generate_claude_rules(tmp_path)

        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
        allow = settings["permissions"]["allow"]
        deny = settings["permissions"]["deny"]
        assert len(allow) == len(set(allow))
        assert len(deny) == len(set(deny))

    def test_idempotent_claude_md_single_markers(self, tmp_path: Path) -> None:
        """CLAUDE.md has exactly one marker pair after two runs."""
        generate_claude_rules(tmp_path)
        generate_claude_rules(tmp_path)

        content = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
        assert content.count(MARKER_START) == 1
        assert content.count(MARKER_END) == 1

    def test_idempotent_hook_scripts_unchanged(self, tmp_path: Path) -> None:
        """All hook scripts have identical content after two runs."""
        generate_claude_rules(tmp_path)
        hooks_dir = tmp_path / ".claude" / "hooks"
        first_scripts = {}
        for script in hooks_dir.iterdir():
            first_scripts[script.name] = script.read_text(encoding="utf-8")

        generate_claude_rules(tmp_path)
        for script in hooks_dir.iterdir():
            assert first_scripts[script.name] == script.read_text(encoding="utf-8"), (
                f"Hook script changed after second run: {script.name}"
            )


# ---------------------------------------------------------------------------
# Integration tests: hook merge behavior
# ---------------------------------------------------------------------------


class TestIntegrationHookMerge:
    """Integration: existing user hooks are preserved when Lexibrary hooks are added.

    Verifies that when a project already has user-defined hooks in
    settings.json, running generate_claude_rules() adds the Lexibrary
    hooks without removing user entries.
    """

    def test_preserves_user_pre_tool_use_hooks(self, tmp_path: Path) -> None:
        """User PreToolUse hooks survive full generation."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        existing = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [{"type": "command", "command": "user-pre-hook.sh"}],
                    }
                ]
            }
        }
        (claude_dir / "settings.json").write_text(json.dumps(existing), encoding="utf-8")

        generate_claude_rules(tmp_path)

        settings = json.loads((claude_dir / "settings.json").read_text(encoding="utf-8"))
        pre_hooks = settings["hooks"]["PreToolUse"]
        commands = []
        for entry in pre_hooks:
            for hook in entry.get("hooks", []):
                commands.append(hook.get("command", ""))
        assert "user-pre-hook.sh" in commands
        assert any("lexi-pre-edit.sh" in cmd for cmd in commands)

    def test_preserves_user_subagent_start_hooks(self, tmp_path: Path) -> None:
        """User SubagentStart hooks survive full generation even though Lexibrary no longer
        adds any."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        existing = {
            "hooks": {
                "SubagentStart": [
                    {
                        "matcher": "CodeReview",
                        "hooks": [{"type": "command", "command": "user-subagent-hook.sh"}],
                    }
                ]
            }
        }
        (claude_dir / "settings.json").write_text(json.dumps(existing), encoding="utf-8")

        generate_claude_rules(tmp_path)

        settings = json.loads((claude_dir / "settings.json").read_text(encoding="utf-8"))
        subagent_hooks = settings["hooks"]["SubagentStart"]
        commands = []
        for entry in subagent_hooks:
            for hook in entry.get("hooks", []):
                commands.append(hook.get("command", ""))
        # User hook is preserved
        assert "user-subagent-hook.sh" in commands

    def test_preserves_user_permissions_with_new_hooks(self, tmp_path: Path) -> None:
        """User permissions are preserved even when new hook types are added."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        existing = {
            "permissions": {
                "allow": ["Bash(my-tool *)", "Bash(other-tool *)"],
                "deny": ["Bash(rm -rf *)"],
            },
            "hooks": {},
        }
        (claude_dir / "settings.json").write_text(json.dumps(existing), encoding="utf-8")

        generate_claude_rules(tmp_path)

        settings = json.loads((claude_dir / "settings.json").read_text(encoding="utf-8"))
        allow = settings["permissions"]["allow"]
        deny = settings["permissions"]["deny"]
        # User permissions preserved
        assert "Bash(my-tool *)" in allow
        assert "Bash(other-tool *)" in allow
        assert "Bash(rm -rf *)" in deny
        # Lexibrary permissions added (explicit, no wildcard)
        assert "Bash(lexi orient)" in allow
        assert "Bash(lexi *)" not in allow
        assert "Bash(lexi context-dump)" not in allow
        assert "Bash(lexictl *)" in deny

    def test_preserves_non_hook_settings(self, tmp_path: Path) -> None:
        """Non-hook, non-permission keys in settings.json are preserved."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        existing = {
            "mcpServers": {"custom": {"url": "http://example.com:8080"}},
            "customKey": "customValue",
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Read",
                        "hooks": [{"type": "command", "command": "user-read-hook.sh"}],
                    }
                ]
            },
        }
        (claude_dir / "settings.json").write_text(json.dumps(existing), encoding="utf-8")

        generate_claude_rules(tmp_path)

        settings = json.loads((claude_dir / "settings.json").read_text(encoding="utf-8"))
        assert settings["mcpServers"]["custom"]["url"] == "http://example.com:8080"
        assert settings["customKey"] == "customValue"

    def test_no_duplicate_hooks_with_existing_lexibrary_hooks(self, tmp_path: Path) -> None:
        """Lexibrary hooks are not duplicated when they already exist."""
        # First run creates everything
        generate_claude_rules(tmp_path)

        # Now add a user hook to PreToolUse
        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
        settings["hooks"]["PreToolUse"].append(
            {
                "matcher": "Debug",
                "hooks": [{"type": "command", "command": "user-debug-hook.sh"}],
            }
        )
        (tmp_path / ".claude" / "settings.json").write_text(
            json.dumps(settings, indent=2) + "\n", encoding="utf-8"
        )

        # Second run should not duplicate the Lexibrary hook
        generate_claude_rules(tmp_path)

        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
        pre_hooks = settings["hooks"]["PreToolUse"]
        lexi_pre_commands = [
            hook.get("command", "")
            for entry in pre_hooks
            for hook in entry.get("hooks", [])
            if "lexi-pre-edit.sh" in hook.get("command", "")
        ]
        assert len(lexi_pre_commands) == 1, (
            f"Expected exactly 1 lexi-pre-edit hook, got {len(lexi_pre_commands)}"
        )

    def test_mixed_hook_types_all_preserved(self, tmp_path: Path) -> None:
        """All hook event types are present when user has various hook types."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        existing = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [{"type": "command", "command": "user-bash-check.sh"}],
                    }
                ],
                "PostToolUse": [
                    {
                        "matcher": "Read",
                        "hooks": [{"type": "command", "command": "user-read-log.sh"}],
                    }
                ],
                "SubagentStart": [
                    {
                        "matcher": "CodeReview",
                        "hooks": [{"type": "command", "command": "user-review.sh"}],
                    }
                ],
            }
        }
        (claude_dir / "settings.json").write_text(json.dumps(existing), encoding="utf-8")

        generate_claude_rules(tmp_path)

        settings = json.loads((claude_dir / "settings.json").read_text(encoding="utf-8"))
        hooks = settings["hooks"]

        # Lexibrary hook types present
        assert "PreToolUse" in hooks
        assert "PostToolUse" in hooks
        # User SubagentStart hooks are preserved
        assert "SubagentStart" in hooks

        # PreToolUse and PostToolUse each have user hook + lexibrary hook
        for event_type in ["PreToolUse", "PostToolUse"]:
            entries = hooks[event_type]
            assert len(entries) == 2, f"Expected 2 entries for {event_type}, got {len(entries)}"
        # SubagentStart only has user hook (Lexibrary no longer adds one)
        assert len(hooks["SubagentStart"]) == 1
