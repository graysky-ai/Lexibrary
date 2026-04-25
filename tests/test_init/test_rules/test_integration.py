"""Integration tests for agent rule generation.

Exercises the full flow from ``generate_rules()`` and ``lexictl lexictl upgrade``
through to file creation, user content preservation, multi-environment support,
and gitignore integration.
"""

from __future__ import annotations

import os
from pathlib import Path

from typer.testing import CliRunner

from lexibrary.cli import lexictl_app
from lexibrary.init.rules import generate_rules, supported_environments
from lexibrary.init.rules.markers import MARKER_END, MARKER_START
from lexibrary.iwh.gitignore import ensure_iwh_gitignored

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_project(
    tmp_path: Path,
    *,
    environments: list[str] | None = None,
) -> Path:
    """Create a minimal initialised project at *tmp_path*.

    Writes the multi-root config shape (``scope_roots: [{path: .}]``) since
    the schema rejects the legacy singular ``scope_root:`` key.

    Args:
        tmp_path: Root directory to set up.
        environments: Agent environments to list in ``config.yaml``.
            Defaults to an empty list.

    Returns:
        The *tmp_path* project root.
    """
    (tmp_path / ".lexibrary").mkdir()
    envs = environments or []
    env_yaml = "\n".join(f"  - {e}" for e in envs)
    scope_roots_yaml = "scope_roots:\n  - path: .\n"
    if envs:
        config_content = f"{scope_roots_yaml}agent_environment:\n{env_yaml}\n"
    else:
        config_content = f"{scope_roots_yaml}agent_environment: []\n"
    (tmp_path / ".lexibrary" / "config.yaml").write_text(config_content)
    return tmp_path


def _invoke_setup(tmp_path: Path, args: list[str]) -> object:
    """Invoke ``lexictl`` from within *tmp_path*.

    Historically named ``_invoke_setup`` because the integration suite
    targeted ``lexictl setup`` before the rename to ``lexictl upgrade``.
    The helper itself is generic — it just changes directory and dispatches.
    """
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        return runner.invoke(lexictl_app, args)
    finally:
        os.chdir(old_cwd)


# ---------------------------------------------------------------------------
# Full flow per environment — generate_rules() API
# ---------------------------------------------------------------------------


class TestFullFlowPerEnvironment:
    """Each supported environment produces the correct files via generate_rules()."""

    def test_claude_full_flow(self, tmp_path: Path) -> None:
        """Claude generates CLAUDE.md, settings.json, hooks, and skill files."""
        results = generate_rules(tmp_path, ["claude"])

        assert "claude" in results
        paths = results["claude"]
        assert len(paths) == 14

        # CLAUDE.md
        claude_md = tmp_path / "CLAUDE.md"
        assert claude_md.exists()
        content = claude_md.read_text(encoding="utf-8")
        assert MARKER_START in content
        assert MARKER_END in content
        assert "TOPOLOGY.md" in content
        assert "lexi lookup" in content

        # Skill files
        search = tmp_path / ".claude" / "skills" / "lexi-search" / "SKILL.md"
        assert search.exists()
        assert "lexi search" in search.read_text(encoding="utf-8")

    def test_cursor_full_flow(self, tmp_path: Path) -> None:
        """Cursor generates MDC rules file, editing MDC, and skills file."""
        results = generate_rules(tmp_path, ["cursor"])

        assert "cursor" in results
        paths = results["cursor"]
        assert len(paths) == 3

        # MDC file
        mdc = tmp_path / ".cursor" / "rules" / "lexibrary.mdc"
        assert mdc.exists()
        mdc_content = mdc.read_text(encoding="utf-8")
        assert mdc_content.startswith("---\n")
        assert "alwaysApply: true" in mdc_content
        assert "TOPOLOGY.md" in mdc_content

        # Skills file
        skills = tmp_path / ".cursor" / "skills" / "lexi.md"
        assert skills.exists()
        skills_content = skills.read_text(encoding="utf-8")
        assert "lexi search" in skills_content

    def test_codex_full_flow(self, tmp_path: Path) -> None:
        """Codex generates AGENTS.md with embedded skills."""
        results = generate_rules(tmp_path, ["codex"])

        assert "codex" in results
        paths = results["codex"]
        assert len(paths) == 1

        agents_md = tmp_path / "AGENTS.md"
        assert agents_md.exists()
        content = agents_md.read_text(encoding="utf-8")
        assert MARKER_START in content
        assert MARKER_END in content
        assert "TOPOLOGY.md" in content
        assert "lexi lookup" in content
        # Codex embeds search skills inline
        assert "lexi search" in content


# ---------------------------------------------------------------------------
# Multi-environment
# ---------------------------------------------------------------------------


class TestMultiEnvironment:
    """Multiple environments can be generated in a single call."""

    def test_all_environments_simultaneously(self, tmp_path: Path) -> None:
        """All three environments can be generated at once."""
        envs = supported_environments()
        results = generate_rules(tmp_path, envs)

        assert set(results.keys()) == {"claude", "codex", "cursor", "generic"}

        # Each environment produced files
        for env_name, paths in results.items():
            assert len(paths) >= 1, f"{env_name} should produce at least one file"

        # Verify all expected files exist
        assert (tmp_path / "CLAUDE.md").exists()
        assert (tmp_path / ".claude" / "skills" / "lexi-search" / "SKILL.md").exists()
        assert (tmp_path / ".cursor" / "rules" / "lexibrary.mdc").exists()
        assert (tmp_path / ".cursor" / "skills" / "lexi.md").exists()
        assert (tmp_path / "AGENTS.md").exists()
        assert (tmp_path / "LEXIBRARY_RULES.md").exists()

    def test_claude_and_codex_coexist(self, tmp_path: Path) -> None:
        """Claude (CLAUDE.md) and Codex (AGENTS.md) are separate files."""
        generate_rules(tmp_path, ["claude", "codex"])

        claude_content = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
        agents_content = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")

        # Both have markers
        assert MARKER_START in claude_content
        assert MARKER_START in agents_content

        # Both have core rules
        assert "TOPOLOGY.md" in claude_content
        assert "TOPOLOGY.md" in agents_content

        # AGENTS.md has embedded skills; CLAUDE.md does not (uses separate skill files)
        assert "lexi search" in agents_content

    def test_multi_env_does_not_interfere(self, tmp_path: Path) -> None:
        """Generating multiple environments does not corrupt other environments' files."""
        # Generate claude first
        generate_rules(tmp_path, ["claude"])
        claude_content_before = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")

        # Now also generate codex and cursor
        generate_rules(tmp_path, ["codex", "cursor"])

        # CLAUDE.md should be unchanged (we did not regenerate it)
        claude_content_after = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
        assert claude_content_before == claude_content_after


# ---------------------------------------------------------------------------
# Setup --update refresh
# ---------------------------------------------------------------------------


class TestUpgradeRefresh:
    """``lexictl upgrade`` regenerates rules and refreshes gitignore."""

    def test_upgrade_creates_rules_and_gitignore(self, tmp_path: Path) -> None:
        """Full ``upgrade`` flow creates rule files and updates gitignore."""
        project = _setup_project(tmp_path, environments=["claude"])

        result = _invoke_setup(project, ["upgrade"])
        assert result.exit_code == 0  # type: ignore[union-attr]

        # Rules created
        assert (project / "CLAUDE.md").exists()
        assert (project / ".claude" / "skills" / "lexi-search" / "SKILL.md").exists()

        # Gitignore updated
        gitignore = project / ".gitignore"
        assert gitignore.exists()
        assert "**/.iwh" in gitignore.read_text(encoding="utf-8")

        # Output confirms success
        output = result.output  # type: ignore[union-attr]
        assert "Upgrade complete" in output

    def test_upgrade_refreshes_existing_rules(self, tmp_path: Path) -> None:
        """A second ``upgrade`` refreshes a modified CLAUDE.md back to canonical content."""
        project = _setup_project(tmp_path, environments=["claude"])

        # First run
        _invoke_setup(project, ["upgrade"])

        # Manually modify CLAUDE.md marker content to simulate stale rules
        claude_md = project / "CLAUDE.md"
        content = claude_md.read_text(encoding="utf-8")
        stale_content = content.replace("lexi lookup", "OLD_COMMAND")
        claude_md.write_text(stale_content, encoding="utf-8")

        # Second run refreshes
        result = _invoke_setup(project, ["upgrade"])
        assert result.exit_code == 0  # type: ignore[union-attr]

        refreshed = claude_md.read_text(encoding="utf-8")
        # Old content is gone, fresh content is back
        assert "OLD_COMMAND" not in refreshed
        assert "lexi lookup" in refreshed

    def test_upgrade_uses_config_environments(self, tmp_path: Path) -> None:
        """``upgrade`` reads ``agent_environment`` from config (no CLI override)."""
        project = _setup_project(tmp_path, environments=["codex"])

        result = _invoke_setup(project, ["upgrade"])
        assert result.exit_code == 0  # type: ignore[union-attr]

        # Codex file created, Claude file NOT created
        assert (project / "AGENTS.md").exists()
        assert not (project / "CLAUDE.md").exists()

    def test_upgrade_handles_multiple_envs(self, tmp_path: Path) -> None:
        """Three declared environments all get their rule files."""
        project = _setup_project(tmp_path, environments=["claude", "cursor", "codex"])

        result = _invoke_setup(project, ["upgrade"])
        assert result.exit_code == 0  # type: ignore[union-attr]

        assert (project / "CLAUDE.md").exists()
        assert (project / ".cursor" / "rules" / "lexibrary.mdc").exists()
        assert (project / "AGENTS.md").exists()

        output = result.output  # type: ignore[union-attr]
        assert "claude" in output
        assert "cursor" in output
        assert "codex" in output
        assert "Upgrade complete" in output


# ---------------------------------------------------------------------------
# User content preservation
# ---------------------------------------------------------------------------


class TestUserContentPreservation:
    """User-authored content outside markers survives regeneration."""

    def test_claude_preserves_user_content_above_markers(self, tmp_path: Path) -> None:
        """User content before the Lexibrary section in CLAUDE.md is preserved."""
        claude_md = tmp_path / "CLAUDE.md"
        user_content = "# My Project\n\nCustom project rules go here.\n"
        claude_md.write_text(user_content, encoding="utf-8")

        generate_rules(tmp_path, ["claude"])

        content = claude_md.read_text(encoding="utf-8")
        assert "# My Project" in content
        assert "Custom project rules go here." in content
        assert MARKER_START in content

    def test_claude_preserves_user_content_below_markers(self, tmp_path: Path) -> None:
        """User content after the Lexibrary section in CLAUDE.md is preserved."""
        claude_md = tmp_path / "CLAUDE.md"
        initial = f"{MARKER_START}\nold rules\n{MARKER_END}\n\n# My Footer\n\nKeep this section.\n"
        claude_md.write_text(initial, encoding="utf-8")

        generate_rules(tmp_path, ["claude"])

        content = claude_md.read_text(encoding="utf-8")
        assert "# My Footer" in content
        assert "Keep this section." in content
        assert "old rules" not in content

    def test_codex_preserves_user_content(self, tmp_path: Path) -> None:
        """User content in AGENTS.md around markers is preserved."""
        agents_md = tmp_path / "AGENTS.md"
        initial = (
            f"# My Agent Instructions\n\n"
            f"Custom instructions.\n\n"
            f"{MARKER_START}\nold lexibrary rules\n{MARKER_END}\n\n"
            f"# More Instructions"
        )
        agents_md.write_text(initial, encoding="utf-8")

        generate_rules(tmp_path, ["codex"])

        content = agents_md.read_text(encoding="utf-8")
        assert "# My Agent Instructions" in content
        assert "Custom instructions." in content
        assert "# More Instructions" in content
        assert "old lexibrary rules" not in content
        assert "TOPOLOGY.md" in content

    def test_user_content_preserved_across_multiple_updates(self, tmp_path: Path) -> None:
        """User content survives repeated regeneration cycles."""
        claude_md = tmp_path / "CLAUDE.md"
        user_before = "# Important Custom Rules\n\nDo not remove this.\n"
        claude_md.write_text(user_before, encoding="utf-8")

        # Run multiple times
        for _ in range(3):
            generate_rules(tmp_path, ["claude"])

        content = claude_md.read_text(encoding="utf-8")
        assert "# Important Custom Rules" in content
        assert "Do not remove this." in content
        # Exactly one marker pair
        assert content.count(MARKER_START) == 1
        assert content.count(MARKER_END) == 1


# ---------------------------------------------------------------------------
# Unsupported environment error
# ---------------------------------------------------------------------------


class TestUnsupportedEnvironment:
    """Unsupported environments raise errors with clear messages."""

    def test_generate_rules_rejects_unknown_environment(self, tmp_path: Path) -> None:
        """generate_rules() raises ValueError for unknown environments."""
        import pytest  # noqa: PLC0415

        with pytest.raises(ValueError, match="Unsupported environment"):
            generate_rules(tmp_path, ["nonexistent"])

    def test_generate_rules_error_lists_supported(self, tmp_path: Path) -> None:
        """The ValueError message lists all supported environments."""
        import pytest  # noqa: PLC0415

        with pytest.raises(ValueError, match="claude") as exc_info:
            generate_rules(tmp_path, ["fake_env"])

        error_msg = str(exc_info.value)
        for env in supported_environments():
            assert env in error_msg

    def test_upgrade_warns_on_unsupported_env_in_config(self, tmp_path: Path) -> None:
        """An unsupported environment in config surfaces as a warning, not exit-1."""
        project = _setup_project(tmp_path, environments=["nonexistent"])

        result = _invoke_setup(project, ["upgrade"])
        # ``upgrade`` is best-effort: invalid envs don't stop the rest of the
        # pipeline. The agent-rules step records the issue as a warning.
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "nonexistent" in output

    def test_mixed_valid_and_invalid_envs_rejected(self, tmp_path: Path) -> None:
        """If any environment is unsupported, the entire call is rejected."""
        import pytest  # noqa: PLC0415

        with pytest.raises(ValueError, match="Unsupported"):
            generate_rules(tmp_path, ["claude", "nonexistent"])

        # No files should have been created
        assert not (tmp_path / "CLAUDE.md").exists()


# ---------------------------------------------------------------------------
# Gitignore integration
# ---------------------------------------------------------------------------


class TestGitignoreIntegration:
    """IWH gitignore integration works through the full flow."""

    def test_gitignore_created_when_missing(self, tmp_path: Path) -> None:
        """.gitignore is created with IWH pattern when file does not exist."""
        assert not (tmp_path / ".gitignore").exists()

        ensure_iwh_gitignored(tmp_path)

        gitignore = tmp_path / ".gitignore"
        assert gitignore.exists()
        assert "**/.iwh" in gitignore.read_text(encoding="utf-8")

    def test_gitignore_appended_when_pattern_absent(self, tmp_path: Path) -> None:
        """Pattern is appended to existing .gitignore that lacks it."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("__pycache__/\n.env\n", encoding="utf-8")

        ensure_iwh_gitignored(tmp_path)

        content = gitignore.read_text(encoding="utf-8")
        assert "__pycache__/" in content
        assert ".env" in content
        assert "**/.iwh" in content

    def test_gitignore_idempotent(self, tmp_path: Path) -> None:
        """Running ensure_iwh_gitignored twice does not duplicate the pattern."""
        ensure_iwh_gitignored(tmp_path)
        ensure_iwh_gitignored(tmp_path)

        content = (tmp_path / ".gitignore").read_text(encoding="utf-8")
        assert content.count("**/.iwh") == 1

    def test_alternative_pattern_recognized(self, tmp_path: Path) -> None:
        """An alternative IWH pattern (e.g. ``.iwh``) prevents adding ``**/.iwh``."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text(".iwh\n", encoding="utf-8")

        modified = ensure_iwh_gitignored(tmp_path)

        assert modified is False
        content = gitignore.read_text(encoding="utf-8")
        # Only the original pattern, no duplicate added
        assert content.count(".iwh") == 1

    def test_upgrade_integrates_gitignore(self, tmp_path: Path) -> None:
        """``lexictl upgrade`` includes gitignore integration."""
        project = _setup_project(tmp_path, environments=["cursor"])

        result = _invoke_setup(project, ["upgrade"])
        assert result.exit_code == 0  # type: ignore[union-attr]

        # gitignore should have been created
        gitignore = project / ".gitignore"
        assert gitignore.exists()
        assert "**/.iwh" in gitignore.read_text(encoding="utf-8")

    def test_upgrade_idempotent_gitignore(self, tmp_path: Path) -> None:
        """Running ``upgrade`` twice does not duplicate the IWH pattern."""
        project = _setup_project(tmp_path, environments=["claude"])
        (project / ".gitignore").write_text("**/.iwh\n", encoding="utf-8")

        _invoke_setup(project, ["upgrade"])
        _invoke_setup(project, ["upgrade"])

        content = (project / ".gitignore").read_text(encoding="utf-8")
        assert content.count("**/.iwh") == 1

    def test_existing_gitignore_content_preserved(self, tmp_path: Path) -> None:
        """Existing .gitignore entries are not lost when IWH pattern is added."""
        project = _setup_project(tmp_path, environments=["claude"])
        (project / ".gitignore").write_text(
            "# My ignores\n__pycache__/\n.env\nnode_modules/\n",
            encoding="utf-8",
        )

        _invoke_setup(project, ["upgrade"])

        content = (project / ".gitignore").read_text(encoding="utf-8")
        assert "__pycache__/" in content
        assert ".env" in content
        assert "node_modules/" in content
        assert "**/.iwh" in content


# ---------------------------------------------------------------------------
# End-to-end: init flow followed by lexictl upgrade
# ---------------------------------------------------------------------------


class TestEndToEndFlow:
    """Full lifecycle: generate rules, update rules, verify consistency."""

    def test_generate_then_update_preserves_structure(self, tmp_path: Path) -> None:
        """Initial generation followed by update maintains correct structure."""
        # Initial generation
        generate_rules(tmp_path, ["claude", "codex"])

        # Regenerate (update)
        generate_rules(tmp_path, ["claude", "codex"])

        claude_updated = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
        agents_updated = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")

        # Content should be well-formed (idempotent)
        assert MARKER_START in claude_updated
        assert MARKER_START in agents_updated
        assert claude_updated.count(MARKER_START) == 1
        assert agents_updated.count(MARKER_START) == 1

    def test_rules_contain_no_lexictl_references(self, tmp_path: Path) -> None:
        """Generated rule content tells agents not to use lexictl commands."""
        generate_rules(tmp_path, ["claude", "codex", "cursor"])

        claude_content = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
        agents_content = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
        mdc_content = (tmp_path / ".cursor" / "rules" / "lexibrary.mdc").read_text(encoding="utf-8")

        # All environments should warn against running lexictl
        for content in (claude_content, agents_content, mdc_content):
            assert "Never run `lexictl`" in content or "never" in content.lower()

    def test_all_environments_reference_topology(self, tmp_path: Path) -> None:
        """Every environment's rules reference TOPOLOGY.md for session start."""
        generate_rules(tmp_path, ["claude", "codex", "cursor"])

        claude_content = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
        agents_content = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
        mdc_content = (tmp_path / ".cursor" / "rules" / "lexibrary.mdc").read_text(encoding="utf-8")

        for content in (claude_content, agents_content, mdc_content):
            assert "TOPOLOGY.md" in content

    def test_all_environments_mention_iwh(self, tmp_path: Path) -> None:
        """Every environment's rules mention IWH signals."""
        generate_rules(tmp_path, ["claude", "codex", "cursor"])

        claude_content = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
        agents_content = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
        mdc_content = (tmp_path / ".cursor" / "rules" / "lexibrary.mdc").read_text(encoding="utf-8")

        for content in (claude_content, agents_content, mdc_content):
            assert "IWH" in content
