"""Tests for init/scaffolder.py — .lexibrary/ skeleton creation."""

from __future__ import annotations

from pathlib import Path

import yaml

from lexibrarian.init.scaffolder import (
    LEXIGNORE_HEADER,
    START_HERE_PLACEHOLDER,
    _generate_config_yaml,
    _generate_lexignore,
    create_lexibrary_from_wizard,
    create_lexibrary_skeleton,
)
from lexibrarian.init.wizard import WizardAnswers
from lexibrarian.iwh.gitignore import IWH_GITIGNORE_PATTERN

# ---------------------------------------------------------------------------
# Original create_lexibrary_skeleton tests (preserved)
# ---------------------------------------------------------------------------


def test_creates_stack_directory(tmp_path: Path) -> None:
    """lexi init creates .lexibrary/stack/ directory."""
    create_lexibrary_skeleton(tmp_path)

    stack_dir = tmp_path / ".lexibrary" / "stack"
    assert stack_dir.is_dir(), ".lexibrary/stack/ should be created"
    assert (stack_dir / ".gitkeep").exists(), ".lexibrary/stack/.gitkeep should exist"


def test_does_not_create_guardrails_directory(tmp_path: Path) -> None:
    """lexi init does NOT create .lexibrary/guardrails/ directory."""
    create_lexibrary_skeleton(tmp_path)

    guardrails_dir = tmp_path / ".lexibrary" / "guardrails"
    assert not guardrails_dir.exists(), ".lexibrary/guardrails/ should NOT be created"


def test_creates_full_skeleton(tmp_path: Path) -> None:
    """lexi init creates the complete .lexibrary/ skeleton with expected dirs."""
    created = create_lexibrary_skeleton(tmp_path)

    base = tmp_path / ".lexibrary"
    assert base.is_dir()
    assert (base / "concepts").is_dir()
    assert (base / "stack").is_dir()
    assert (base / "config.yaml").is_file()
    assert (base / "START_HERE.md").is_file()
    assert (tmp_path / ".lexignore").is_file()
    assert len(created) > 0


def test_skeleton_does_not_create_handoff(tmp_path: Path) -> None:
    """create_lexibrary_skeleton does NOT create HANDOFF.md (replaced by IWH)."""
    create_lexibrary_skeleton(tmp_path)
    assert not (tmp_path / ".lexibrary" / "HANDOFF.md").exists()


def test_idempotent(tmp_path: Path) -> None:
    """Running create_lexibrary_skeleton twice returns empty list on second call."""
    create_lexibrary_skeleton(tmp_path)
    second_run = create_lexibrary_skeleton(tmp_path)
    assert second_run == [], "Second call should create nothing"


# ---------------------------------------------------------------------------
# _generate_config_yaml tests
# ---------------------------------------------------------------------------


def _make_answers(**overrides: object) -> WizardAnswers:
    """Build a WizardAnswers with sensible defaults, merging *overrides*."""
    defaults = {
        "project_name": "test-proj",
        "scope_root": "src/",
        "agent_environments": ["claude"],
        "llm_provider": "anthropic",
        "llm_model": "claude-sonnet-4-6",
        "llm_api_key_env": "ANTHROPIC_API_KEY",
        "ignore_patterns": ["dist/", "build/"],
        "token_budgets_customized": False,
        "token_budgets": {},
        "iwh_enabled": True,
        "confirmed": True,
    }
    defaults.update(overrides)
    return WizardAnswers(**defaults)  # type: ignore[arg-type]


def test_generate_config_yaml_is_valid_yaml() -> None:
    """Generated config is valid YAML that round-trips."""
    answers = _make_answers()
    output = _generate_config_yaml(answers)
    parsed = yaml.safe_load(output)
    assert isinstance(parsed, dict)


def test_generate_config_yaml_includes_all_wizard_fields() -> None:
    """Generated config includes project_name, scope_root, agent_environment, llm, iwh."""
    answers = _make_answers(
        project_name="my-app",
        scope_root="lib/",
        agent_environments=["claude", "cursor"],
        llm_provider="openai",
        llm_model="gpt-4o",
        llm_api_key_env="OPENAI_API_KEY",
        iwh_enabled=False,
    )
    output = _generate_config_yaml(answers)
    parsed = yaml.safe_load(output)

    assert parsed["project_name"] == "my-app"
    assert parsed["scope_root"] == "lib/"
    assert parsed["agent_environment"] == ["claude", "cursor"]
    assert parsed["llm"]["provider"] == "openai"
    assert parsed["llm"]["model"] == "gpt-4o"
    assert parsed["llm"]["api_key_env"] == "OPENAI_API_KEY"
    assert parsed["iwh"]["enabled"] is False


def test_generate_config_yaml_custom_token_budgets() -> None:
    """Custom token budgets are included when customized is True."""
    answers = _make_answers(
        token_budgets_customized=True,
        token_budgets={"start_here_tokens": 1200, "design_file_tokens": 600},
    )
    output = _generate_config_yaml(answers)
    parsed = yaml.safe_load(output)

    assert "token_budgets" in parsed
    assert parsed["token_budgets"]["start_here_tokens"] == 1200
    assert parsed["token_budgets"]["design_file_tokens"] == 600


def test_generate_config_yaml_default_token_budgets_omitted() -> None:
    """Token budgets section is omitted when not customized."""
    answers = _make_answers(token_budgets_customized=False)
    output = _generate_config_yaml(answers)
    parsed = yaml.safe_load(output)

    assert "token_budgets" not in parsed


def test_generate_config_yaml_has_header() -> None:
    """Generated config starts with a descriptive header comment."""
    answers = _make_answers()
    output = _generate_config_yaml(answers)
    assert output.startswith("# Lexibrarian project configuration")


# ---------------------------------------------------------------------------
# _generate_lexignore tests
# ---------------------------------------------------------------------------


def test_generate_lexignore_with_patterns() -> None:
    """Lexignore includes the header and provided patterns."""
    result = _generate_lexignore(["dist/", "coverage/"])
    assert "dist/" in result
    assert "coverage/" in result
    assert result.startswith(LEXIGNORE_HEADER)


def test_generate_lexignore_empty_patterns() -> None:
    """Lexignore with empty patterns returns only the header."""
    result = _generate_lexignore([])
    assert result == LEXIGNORE_HEADER


def test_generate_lexignore_has_header() -> None:
    """Lexignore always starts with a comment header."""
    result = _generate_lexignore(["node_modules/"])
    assert result.startswith("#")


# ---------------------------------------------------------------------------
# create_lexibrary_from_wizard tests
# ---------------------------------------------------------------------------


def test_wizard_creates_directory_structure(tmp_path: Path) -> None:
    """Wizard scaffolder creates .lexibrary/, concepts/, and stack/."""
    answers = _make_answers()
    create_lexibrary_from_wizard(tmp_path, answers)

    base = tmp_path / ".lexibrary"
    assert base.is_dir()
    assert (base / "concepts").is_dir()
    assert (base / "stack").is_dir()
    assert (base / "concepts" / ".gitkeep").exists()
    assert (base / "stack" / ".gitkeep").exists()


def test_wizard_config_contains_wizard_values(tmp_path: Path) -> None:
    """Config file created by wizard contains the wizard-provided values."""
    answers = _make_answers(
        project_name="my-app",
        llm_provider="anthropic",
        scope_root="src/",
    )
    create_lexibrary_from_wizard(tmp_path, answers)

    config_text = (tmp_path / ".lexibrary" / "config.yaml").read_text()
    parsed = yaml.safe_load(config_text)
    assert parsed["project_name"] == "my-app"
    assert parsed["llm"]["provider"] == "anthropic"
    assert parsed["scope_root"] == "src/"


def test_wizard_does_not_create_handoff(tmp_path: Path) -> None:
    """Wizard scaffolder does NOT create HANDOFF.md."""
    answers = _make_answers()
    create_lexibrary_from_wizard(tmp_path, answers)

    assert not (tmp_path / ".lexibrary" / "HANDOFF.md").exists()


def test_wizard_creates_lexignore_with_patterns(tmp_path: Path) -> None:
    """Wizard scaffolder creates .lexignore containing the wizard patterns."""
    answers = _make_answers(ignore_patterns=["dist/", "build/"])
    create_lexibrary_from_wizard(tmp_path, answers)

    lexignore = (tmp_path / ".lexignore").read_text()
    assert "dist/" in lexignore
    assert "build/" in lexignore


def test_wizard_creates_lexignore_empty_patterns(tmp_path: Path) -> None:
    """Wizard scaffolder creates .lexignore with header when no patterns."""
    answers = _make_answers(ignore_patterns=[])
    create_lexibrary_from_wizard(tmp_path, answers)

    lexignore = (tmp_path / ".lexignore").read_text()
    assert lexignore.startswith("#")
    # Only the header — no additional pattern lines
    assert lexignore == LEXIGNORE_HEADER


def test_wizard_returns_created_paths(tmp_path: Path) -> None:
    """Returned path list contains all created files and directories."""
    answers = _make_answers()
    created = create_lexibrary_from_wizard(tmp_path, answers)

    # Should contain directories, .gitkeep files, config, START_HERE, .lexignore
    path_strs = [str(p) for p in created]
    assert any("config.yaml" in s for s in path_strs)
    assert any("START_HERE.md" in s for s in path_strs)
    assert any(".lexignore" in s for s in path_strs)
    assert any("concepts" in s for s in path_strs)
    assert any("stack" in s for s in path_strs)


def test_wizard_creates_start_here(tmp_path: Path) -> None:
    """Wizard scaffolder creates START_HERE.md."""
    answers = _make_answers()
    create_lexibrary_from_wizard(tmp_path, answers)

    assert (tmp_path / ".lexibrary" / "START_HERE.md").is_file()


def test_wizard_import_from_init_package() -> None:
    """create_lexibrary_from_wizard is importable from lexibrarian.init."""
    from lexibrarian.init import create_lexibrary_from_wizard as fn

    assert callable(fn)


# ---------------------------------------------------------------------------
# IWH reference tests
# ---------------------------------------------------------------------------


def test_start_here_placeholder_references_iwh() -> None:
    """START_HERE_PLACEHOLDER mentions .iwh files for inter-agent signals."""
    assert ".iwh" in START_HERE_PLACEHOLDER
    assert "HANDOFF" not in START_HERE_PLACEHOLDER


# ---------------------------------------------------------------------------
# Gitignore integration tests
# ---------------------------------------------------------------------------


def test_skeleton_creates_gitignore_with_iwh_pattern(tmp_path: Path) -> None:
    """create_lexibrary_skeleton creates .gitignore with IWH pattern on fresh init."""
    create_lexibrary_skeleton(tmp_path)

    gitignore_path = tmp_path / ".gitignore"
    assert gitignore_path.is_file(), ".gitignore should be created"
    content = gitignore_path.read_text()
    assert IWH_GITIGNORE_PATTERN in content


def test_skeleton_appends_iwh_to_existing_gitignore(tmp_path: Path) -> None:
    """create_lexibrary_skeleton appends IWH pattern to existing .gitignore."""
    gitignore_path = tmp_path / ".gitignore"
    gitignore_path.write_text("node_modules/\n")

    create_lexibrary_skeleton(tmp_path)

    content = gitignore_path.read_text()
    assert "node_modules/" in content, "Existing patterns should be preserved"
    assert IWH_GITIGNORE_PATTERN in content


def test_skeleton_does_not_duplicate_iwh_pattern(tmp_path: Path) -> None:
    """create_lexibrary_skeleton does not duplicate IWH pattern in .gitignore."""
    gitignore_path = tmp_path / ".gitignore"
    gitignore_path.write_text(f"{IWH_GITIGNORE_PATTERN}\n")

    create_lexibrary_skeleton(tmp_path)

    content = gitignore_path.read_text()
    assert content.count(IWH_GITIGNORE_PATTERN) == 1


def test_wizard_creates_gitignore_with_iwh_pattern(tmp_path: Path) -> None:
    """create_lexibrary_from_wizard creates .gitignore with IWH pattern on fresh init."""
    answers = _make_answers()
    create_lexibrary_from_wizard(tmp_path, answers)

    gitignore_path = tmp_path / ".gitignore"
    assert gitignore_path.is_file(), ".gitignore should be created"
    content = gitignore_path.read_text()
    assert IWH_GITIGNORE_PATTERN in content


def test_wizard_appends_iwh_to_existing_gitignore(tmp_path: Path) -> None:
    """create_lexibrary_from_wizard appends IWH pattern to existing .gitignore."""
    gitignore_path = tmp_path / ".gitignore"
    gitignore_path.write_text("*.pyc\n")

    answers = _make_answers()
    create_lexibrary_from_wizard(tmp_path, answers)

    content = gitignore_path.read_text()
    assert "*.pyc" in content, "Existing patterns should be preserved"
    assert IWH_GITIGNORE_PATTERN in content


# ---------------------------------------------------------------------------
# LinkGraph index.db gitignore tests
# ---------------------------------------------------------------------------

_INDEX_DB_PATTERN = ".lexibrary/index.db"


def test_skeleton_gitignore_contains_index_db(tmp_path: Path) -> None:
    """create_lexibrary_skeleton adds .lexibrary/index.db to .gitignore."""
    create_lexibrary_skeleton(tmp_path)

    gitignore_path = tmp_path / ".gitignore"
    assert gitignore_path.is_file(), ".gitignore should be created"
    content = gitignore_path.read_text()
    assert _INDEX_DB_PATTERN in content


def test_wizard_gitignore_contains_index_db(tmp_path: Path) -> None:
    """create_lexibrary_from_wizard adds .lexibrary/index.db to .gitignore."""
    answers = _make_answers()
    create_lexibrary_from_wizard(tmp_path, answers)

    gitignore_path = tmp_path / ".gitignore"
    assert gitignore_path.is_file(), ".gitignore should be created"
    content = gitignore_path.read_text()
    assert _INDEX_DB_PATTERN in content
