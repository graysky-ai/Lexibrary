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
        assert "START_HERE.md" in content
        assert "lexi lookup" in content

    def test_returns_all_created_paths(self, tmp_path: Path) -> None:
        """Return value includes all generated files."""
        result = generate_claude_rules(tmp_path)
        assert len(result) == 11
        filenames = [p.name for p in result]
        assert "CLAUDE.md" in filenames
        assert "settings.json" in filenames
        assert "lexi-pre-edit.sh" in filenames
        assert "lexi-post-edit.sh" in filenames
        assert "lexi-explore-context.sh" in filenames
        assert "explore.md" in filenames
        assert "lexi-orient.md" in filenames
        assert "lexi-search.md" in filenames
        assert "lexi-lookup.md" in filenames
        assert "lexi-concepts.md" in filenames
        assert "lexi-stack.md" in filenames


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
        assert "START_HERE.md" in content

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
# Command files
# ---------------------------------------------------------------------------


class TestCommandFiles:
    """Command files are created in .claude/commands/."""

    def test_creates_orient_command(self, tmp_path: Path) -> None:
        """lexi-orient.md is created in .claude/commands/."""
        generate_claude_rules(tmp_path)
        orient = tmp_path / ".claude" / "commands" / "lexi-orient.md"
        assert orient.exists()

    def test_orient_contains_start_here(self, tmp_path: Path) -> None:
        """Orient command references START_HERE.md."""
        generate_claude_rules(tmp_path)
        orient = tmp_path / ".claude" / "commands" / "lexi-orient.md"
        content = orient.read_text(encoding="utf-8")
        assert "START_HERE.md" in content

    def test_orient_contains_lexi_status(self, tmp_path: Path) -> None:
        """Orient command includes lexi status."""
        generate_claude_rules(tmp_path)
        orient = tmp_path / ".claude" / "commands" / "lexi-orient.md"
        content = orient.read_text(encoding="utf-8")
        assert "lexi status" in content

    def test_creates_search_command(self, tmp_path: Path) -> None:
        """lexi-search.md is created in .claude/commands/."""
        generate_claude_rules(tmp_path)
        search = tmp_path / ".claude" / "commands" / "lexi-search.md"
        assert search.exists()

    def test_search_contains_lexi_search(self, tmp_path: Path) -> None:
        """Search command references lexi search."""
        generate_claude_rules(tmp_path)
        search = tmp_path / ".claude" / "commands" / "lexi-search.md"
        content = search.read_text(encoding="utf-8")
        assert "lexi search" in content

    def test_command_files_overwritten_on_update(self, tmp_path: Path) -> None:
        """Command files are overwritten when regenerated."""
        orient = tmp_path / ".claude" / "commands" / "lexi-orient.md"
        orient.parent.mkdir(parents=True, exist_ok=True)
        orient.write_text("old orient content", encoding="utf-8")

        generate_claude_rules(tmp_path)

        content = orient.read_text(encoding="utf-8")
        assert "old orient content" not in content
        assert "START_HERE.md" in content

    def test_creates_commands_directory(self, tmp_path: Path) -> None:
        """The .claude/commands/ directory is created if it does not exist."""
        generate_claude_rules(tmp_path)
        assert (tmp_path / ".claude" / "commands").is_dir()

    def test_creates_lookup_command(self, tmp_path: Path) -> None:
        """lexi-lookup.md is created in .claude/commands/."""
        generate_claude_rules(tmp_path)
        lookup = tmp_path / ".claude" / "commands" / "lexi-lookup.md"
        assert lookup.exists()
        content = lookup.read_text(encoding="utf-8")
        assert "lexi lookup" in content

    def test_creates_concepts_command(self, tmp_path: Path) -> None:
        """lexi-concepts.md is created in .claude/commands/."""
        generate_claude_rules(tmp_path)
        concepts = tmp_path / ".claude" / "commands" / "lexi-concepts.md"
        assert concepts.exists()
        content = concepts.read_text(encoding="utf-8")
        assert "lexi concepts" in content

    def test_creates_stack_command(self, tmp_path: Path) -> None:
        """lexi-stack.md is created in .claude/commands/."""
        generate_claude_rules(tmp_path)
        stack = tmp_path / ".claude" / "commands" / "lexi-stack.md"
        assert stack.exists()
        content = stack.read_text(encoding="utf-8")
        assert "lexi stack" in content


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
        """settings.json contains permissions.allow list."""
        _generate_settings_json(tmp_path)
        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
        assert "permissions" in settings
        assert "allow" in settings["permissions"]
        allow = settings["permissions"]["allow"]
        assert "Bash(lexi *)" in allow
        assert "Bash(lexi lookup *)" in allow

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
        assert post_hooks[0]["hooks"][0]["timeout"] == 5000

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
        assert "Bash(lexi *)" in allow

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

    def test_post_edit_emits_system_message(self, tmp_path: Path) -> None:
        """Post-edit script emits a systemMessage reminder."""
        _generate_hook_scripts(tmp_path)
        content = (tmp_path / ".claude" / "hooks" / "lexi-post-edit.sh").read_text(encoding="utf-8")
        assert "systemMessage" in content

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

    def test_returns_three_paths(self, tmp_path: Path) -> None:
        """_generate_hook_scripts() returns paths to all three scripts."""
        result = _generate_hook_scripts(tmp_path)
        assert len(result) == 3
        filenames = [p.name for p in result]
        assert "lexi-pre-edit.sh" in filenames
        assert "lexi-post-edit.sh" in filenames
        assert "lexi-explore-context.sh" in filenames

    def test_creates_hooks_directory(self, tmp_path: Path) -> None:
        """.claude/hooks/ directory is created if it does not exist."""
        _generate_hook_scripts(tmp_path)
        assert (tmp_path / ".claude" / "hooks").is_dir()


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
        assert "lexi concepts" in content
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

    def test_returns_one_path(self, tmp_path: Path) -> None:
        """_generate_agent_files() returns path to the explore agent file."""
        result = _generate_agent_files(tmp_path)
        assert len(result) == 1
        assert result[0].name == "explore.md"

    def test_generate_claude_rules_creates_explore_agent(self, tmp_path: Path) -> None:
        """generate_claude_rules() creates .claude/agents/explore.md."""
        generate_claude_rules(tmp_path)
        explore = tmp_path / ".claude" / "agents" / "explore.md"
        assert explore.exists()
        content = explore.read_text(encoding="utf-8")
        assert "name: Explore" in content


# ---------------------------------------------------------------------------
# Integration tests: full generation pipeline
# ---------------------------------------------------------------------------


class TestIntegrationFullGeneration:
    """Integration: generate_claude_rules() produces all expected files.

    Verifies that a single call to generate_claude_rules() on a clean
    directory produces every expected output file including the new
    explore-context hook script and explore agent definition file.
    """

    def test_all_expected_files_exist(self, tmp_path: Path) -> None:
        """Every expected output file is created on disk."""
        generate_claude_rules(tmp_path)

        expected_files = [
            tmp_path / "CLAUDE.md",
            tmp_path / ".claude" / "settings.json",
            tmp_path / ".claude" / "hooks" / "lexi-pre-edit.sh",
            tmp_path / ".claude" / "hooks" / "lexi-post-edit.sh",
            tmp_path / ".claude" / "hooks" / "lexi-explore-context.sh",
            tmp_path / ".claude" / "agents" / "explore.md",
            tmp_path / ".claude" / "commands" / "lexi-orient.md",
            tmp_path / ".claude" / "commands" / "lexi-search.md",
            tmp_path / ".claude" / "commands" / "lexi-lookup.md",
            tmp_path / ".claude" / "commands" / "lexi-concepts.md",
            tmp_path / ".claude" / "commands" / "lexi-stack.md",
        ]

        for expected in expected_files:
            assert expected.exists(), f"Missing expected file: {expected}"

    def test_returned_paths_match_expected_count(self, tmp_path: Path) -> None:
        """generate_claude_rules() returns exactly 11 paths."""
        result = generate_claude_rules(tmp_path)
        assert len(result) == 11

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

    def test_explore_context_hook_in_settings(self, tmp_path: Path) -> None:
        """settings.json includes the SubagentStart hook for explore-context."""
        generate_claude_rules(tmp_path)
        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
        assert "SubagentStart" in settings["hooks"]
        subagent_hooks = settings["hooks"]["SubagentStart"]
        assert len(subagent_hooks) >= 1
        assert subagent_hooks[0]["matcher"] == "Explore|Plan"
        assert subagent_hooks[0]["hooks"][0]["timeout"] == 5000
        assert "lexi-explore-context.sh" in subagent_hooks[0]["hooks"][0]["command"]

    def test_explore_context_script_is_executable(self, tmp_path: Path) -> None:
        """The explore-context hook script is executable after full generation."""
        generate_claude_rules(tmp_path)
        explore_script = tmp_path / ".claude" / "hooks" / "lexi-explore-context.sh"
        mode = explore_script.stat().st_mode
        assert mode & stat.S_IXUSR
        assert mode & stat.S_IXGRP
        assert mode & stat.S_IXOTH

    def test_explore_context_script_content(self, tmp_path: Path) -> None:
        """The explore-context hook script has expected content markers."""
        generate_claude_rules(tmp_path)
        content = (tmp_path / ".claude" / "hooks" / "lexi-explore-context.sh").read_text(
            encoding="utf-8"
        )
        assert content.startswith("#!/")
        assert "lexi context-dump" in content
        assert "hookSpecificOutput" in content
        assert "SubagentStart" in content
        assert ".lexibrary" in content
        assert "jq" in content

    def test_explore_agent_content(self, tmp_path: Path) -> None:
        """The explore agent file has expected content after full generation."""
        generate_claude_rules(tmp_path)
        content = (tmp_path / ".claude" / "agents" / "explore.md").read_text(encoding="utf-8")
        assert content.startswith("---\n")
        assert "name: Explore" in content
        assert "model: haiku" in content
        assert "lexi search" in content

    def test_context_dump_in_permissions(self, tmp_path: Path) -> None:
        """settings.json allow list includes Bash(lexi context-dump)."""
        generate_claude_rules(tmp_path)
        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
        allow = settings["permissions"]["allow"]
        assert "Bash(lexi context-dump)" in allow

    def test_all_hook_types_in_settings(self, tmp_path: Path) -> None:
        """settings.json contains PreToolUse, PostToolUse, and SubagentStart hooks."""
        generate_claude_rules(tmp_path)
        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
        hooks = settings["hooks"]
        assert "PreToolUse" in hooks
        assert "PostToolUse" in hooks
        assert "SubagentStart" in hooks

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
        assert (tmp_path / ".claude" / "commands").is_dir()


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
    """Integration: existing user hooks are preserved when SubagentStart hook is added.

    Verifies that when a project already has user-defined hooks in
    settings.json, running generate_claude_rules() adds the Lexibrary
    hooks (including SubagentStart) without removing user entries.
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
        """User SubagentStart hooks survive full generation."""
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
        matchers = []
        for entry in subagent_hooks:
            matchers.append(entry.get("matcher", ""))
            for hook in entry.get("hooks", []):
                commands.append(hook.get("command", ""))
        # User hook is preserved
        assert "user-subagent-hook.sh" in commands
        assert "CodeReview" in matchers
        # Lexibrary hook is added
        assert any("lexi-explore-context.sh" in cmd for cmd in commands)
        assert "Explore|Plan" in matchers

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
        # Lexibrary permissions added
        assert "Bash(lexi *)" in allow
        assert "Bash(lexi context-dump)" in allow
        assert "Bash(lexictl *)" in deny
        # SubagentStart hook added despite empty hooks object
        assert "SubagentStart" in settings["hooks"]

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

        # Now add a user hook to SubagentStart
        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
        settings["hooks"]["SubagentStart"].append(
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
        subagent_hooks = settings["hooks"]["SubagentStart"]
        explore_commands = [
            hook.get("command", "")
            for entry in subagent_hooks
            for hook in entry.get("hooks", [])
            if "lexi-explore-context.sh" in hook.get("command", "")
        ]
        assert len(explore_commands) == 1, (
            f"Expected exactly 1 explore-context hook, got {len(explore_commands)}"
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

        # All three hook types present
        assert "PreToolUse" in hooks
        assert "PostToolUse" in hooks
        assert "SubagentStart" in hooks

        # Each type has user hook + lexibrary hook
        for event_type in ["PreToolUse", "PostToolUse", "SubagentStart"]:
            entries = hooks[event_type]
            assert len(entries) == 2, f"Expected 2 entries for {event_type}, got {len(entries)}"
