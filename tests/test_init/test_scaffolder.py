"""Tests for init/scaffolder.py — .lexibrary/ skeleton creation."""

from __future__ import annotations

from pathlib import Path

import yaml

from lexibrary.config.schema import ScopeRoot
from lexibrary.init.scaffolder import (
    _DEFAULT_LEXIGNORE_PATTERNS,
    LEXIGNORE_HEADER,
    _generate_config_yaml,
    _generate_lexignore,
    create_lexibrary_from_wizard,
    create_lexibrary_skeleton,
)
from lexibrary.init.wizard import WizardAnswers
from lexibrary.iwh.gitignore import IWH_GITIGNORE_PATTERN

# ---------------------------------------------------------------------------
# Original create_lexibrary_skeleton tests (preserved)
# ---------------------------------------------------------------------------


def test_creates_stack_directory(tmp_path: Path) -> None:
    """lexictl init creates .lexibrary/stack/ directory."""
    create_lexibrary_skeleton(tmp_path)

    stack_dir = tmp_path / ".lexibrary" / "stack"
    assert stack_dir.is_dir(), ".lexibrary/stack/ should be created"
    assert (stack_dir / ".gitkeep").exists(), ".lexibrary/stack/.gitkeep should exist"


def test_creates_conventions_directory(tmp_path: Path) -> None:
    """lexictl init creates .lexibrary/conventions/ directory with .gitkeep."""
    create_lexibrary_skeleton(tmp_path)

    conventions_dir = tmp_path / ".lexibrary" / "conventions"
    assert conventions_dir.is_dir(), ".lexibrary/conventions/ should be created"
    assert (conventions_dir / ".gitkeep").exists(), ".lexibrary/conventions/.gitkeep should exist"


def test_does_not_create_guardrails_directory(tmp_path: Path) -> None:
    """lexictl init does NOT create .lexibrary/guardrails/ directory."""
    create_lexibrary_skeleton(tmp_path)

    guardrails_dir = tmp_path / ".lexibrary" / "guardrails"
    assert not guardrails_dir.exists(), ".lexibrary/guardrails/ should NOT be created"


def test_creates_full_skeleton(tmp_path: Path) -> None:
    """lexictl init creates the complete .lexibrary/ skeleton with expected dirs."""
    created = create_lexibrary_skeleton(tmp_path)

    base = tmp_path / ".lexibrary"
    assert base.is_dir()
    assert (base / "concepts").is_dir()
    assert (base / "conventions").is_dir()
    assert (base / "stack").is_dir()
    assert (base / "config.yaml").is_file()
    assert not (base / "START_HERE.md").exists()
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
    """Build a WizardAnswers with sensible defaults, merging *overrides*.

    ``scope_roots`` accepts either a ``list[ScopeRoot]`` or, as a test
    ergonomics shortcut, a ``list[str]`` which is lifted to
    ``[ScopeRoot(path=s) for s in strings]`` before construction.
    """
    defaults: dict[str, object] = {
        "project_name": "test-proj",
        "scope_roots": [ScopeRoot(path="src/")],
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

    # Allow callers to pass scope_roots as list[str] for brevity.
    raw_roots = defaults.get("scope_roots")
    if isinstance(raw_roots, list) and raw_roots and all(isinstance(r, str) for r in raw_roots):
        defaults["scope_roots"] = [ScopeRoot(path=str(r)) for r in raw_roots]

    return WizardAnswers(**defaults)  # type: ignore[arg-type]


def test_generate_config_yaml_is_valid_yaml() -> None:
    """Generated config is valid YAML that round-trips."""
    answers = _make_answers()
    output = _generate_config_yaml(answers)
    parsed = yaml.safe_load(output)
    assert isinstance(parsed, dict)


def test_generate_config_yaml_includes_all_wizard_fields() -> None:
    """Generated config includes project_name, scope_roots, agent_environment, llm, iwh."""
    answers = _make_answers(
        project_name="my-app",
        scope_roots=[ScopeRoot(path="lib/")],
        agent_environments=["claude", "cursor"],
        llm_provider="openai",
        llm_model="gpt-4o",
        llm_api_key_env="OPENAI_API_KEY",
        iwh_enabled=False,
    )
    output = _generate_config_yaml(answers)
    parsed = yaml.safe_load(output)

    assert parsed["project_name"] == "my-app"
    assert parsed["scope_roots"] == [{"path": "lib/"}]
    assert parsed["agent_environment"] == ["claude", "cursor"]
    assert parsed["llm"]["provider"] == "openai"
    assert parsed["llm"]["model"] == "gpt-4o"
    assert parsed["llm"]["api_key_env"] == "OPENAI_API_KEY"
    assert parsed["iwh"]["enabled"] is False


def test_generate_config_yaml_custom_token_budgets() -> None:
    """Custom token budgets are included when customized is True."""
    answers = _make_answers(
        token_budgets_customized=True,
        token_budgets={"convention_file_tokens": 1200, "design_file_tokens": 600},
    )
    output = _generate_config_yaml(answers)
    parsed = yaml.safe_load(output)

    assert "token_budgets" in parsed
    assert parsed["token_budgets"]["convention_file_tokens"] == 1200
    assert parsed["token_budgets"]["design_file_tokens"] == 600


def test_generate_config_yaml_default_token_budgets_omitted() -> None:
    """Token budgets section is omitted when not customized."""
    answers = _make_answers(token_budgets_customized=False)
    output = _generate_config_yaml(answers)
    parsed = yaml.safe_load(output)

    assert "token_budgets" not in parsed


def test_generate_config_yaml_api_key_source_dotenv() -> None:
    """api_key_source appears in generated config YAML when set to 'dotenv'."""
    answers = _make_answers(llm_api_key_source="dotenv")
    output = _generate_config_yaml(answers)
    parsed = yaml.safe_load(output)

    assert parsed["llm"]["api_key_source"] == "dotenv"


def test_generate_config_yaml_default_api_key_source_is_env() -> None:
    """Default api_key_source is 'env' in generated config."""
    answers = _make_answers()
    output = _generate_config_yaml(answers)
    parsed = yaml.safe_load(output)

    assert parsed["llm"]["api_key_source"] == "env"


def test_generate_config_yaml_has_header() -> None:
    """Generated config starts with a descriptive header comment."""
    answers = _make_answers()
    output = _generate_config_yaml(answers)
    assert output.startswith("# Lexibrary project configuration")


# ---------------------------------------------------------------------------
# scope_roots YAML emission (multi-root, Block B / list-of-mappings shape)
# ---------------------------------------------------------------------------


def _assert_no_legacy_scalar(yaml_text: str) -> None:
    """Fail if ``yaml_text`` contains a ``scope_root:`` scalar anywhere.

    Masks ``scope_roots:`` (plural) first so the presence of the new key
    does not trip the check. This is the exact-string guard from task 9.5.
    """
    masked = yaml_text.replace("scope_roots:", "")
    assert "scope_root:" not in masked, (
        "found legacy `scope_root:` scalar shape in YAML output:\n" + yaml_text
    )


def test_generate_config_yaml_single_root_emits_list_of_mappings() -> None:
    """Single-root config emits ``scope_roots:`` + ``- path:``, never scalar.

    Matches Block B from the ``multi-root`` change. The canonical shape is a
    YAML list of mappings even when only one root is declared — no scalar
    shorthand like ``scope_root: src/``.
    """
    answers = _make_answers(scope_roots=[ScopeRoot(path="src/")])
    output = _generate_config_yaml(answers)

    # Exact-string assertions per task 9.5: the key followed by a list entry.
    assert "scope_roots:" in output, "emitted YAML must contain scope_roots key"
    assert "- path: src/" in output, "single root must appear as a `- path:` list entry"
    _assert_no_legacy_scalar(output)

    # Round-trip parse to confirm list-of-mappings structure.
    parsed = yaml.safe_load(output)
    assert isinstance(parsed["scope_roots"], list)
    assert parsed["scope_roots"] == [{"path": "src/"}]


def test_generate_config_yaml_multi_root_emits_list_of_mappings() -> None:
    """Multi-root config emits one ``- path:`` line per declared root, in order."""
    answers = _make_answers(
        scope_roots=[ScopeRoot(path="src/"), ScopeRoot(path="baml_src/")],
    )
    output = _generate_config_yaml(answers)

    assert "scope_roots:" in output
    assert "- path: src/" in output
    assert "- path: baml_src/" in output
    _assert_no_legacy_scalar(output)

    # Declared order must be preserved in the emitted YAML.
    src_idx = output.index("- path: src/")
    baml_idx = output.index("- path: baml_src/")
    assert src_idx < baml_idx, "scope_roots must preserve declared order"

    parsed = yaml.safe_load(output)
    assert parsed["scope_roots"] == [{"path": "src/"}, {"path": "baml_src/"}]


def test_generate_config_yaml_no_scope_roots_defaults_to_dot() -> None:
    """An empty ``scope_roots`` list in answers falls back to ``[{"path": "."}]``.

    Guards the single-line ``[{"path": "."}]`` default inside
    :func:`_generate_config_yaml` so a wizard-run that somehow produced an
    empty list still yields a valid, Pydantic-accepted config.
    """
    answers = _make_answers(scope_roots=[])
    output = _generate_config_yaml(answers)

    assert "- path: ." in output
    parsed = yaml.safe_load(output)
    assert parsed["scope_roots"] == [{"path": "."}]


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
    """Lexignore with empty patterns includes header and default .env patterns."""
    result = _generate_lexignore([])
    assert result.startswith(LEXIGNORE_HEADER)
    for pattern in _DEFAULT_LEXIGNORE_PATTERNS:
        assert pattern in result


def test_generate_lexignore_has_header() -> None:
    """Lexignore always starts with a comment header."""
    result = _generate_lexignore(["node_modules/"])
    assert result.startswith("#")


def test_generate_lexignore_always_includes_env_patterns() -> None:
    """Lexignore always includes .env, .env.*, and *.env patterns."""
    result = _generate_lexignore([])
    assert ".env\n" in result
    assert ".env.*\n" in result
    assert "*.env\n" in result


def test_generate_lexignore_env_patterns_not_duplicated() -> None:
    """User-provided .env patterns do not duplicate the defaults."""
    result = _generate_lexignore([".env", ".env.*", "*.env"])
    # Each pattern should appear exactly once
    lines = result.splitlines()
    assert lines.count(".env") == 1
    assert lines.count(".env.*") == 1
    assert lines.count("*.env") == 1


def test_default_lexignore_patterns_constant() -> None:
    """_DEFAULT_LEXIGNORE_PATTERNS contains exactly the expected .env patterns."""
    assert ".env" in _DEFAULT_LEXIGNORE_PATTERNS
    assert ".env.*" in _DEFAULT_LEXIGNORE_PATTERNS
    assert "*.env" in _DEFAULT_LEXIGNORE_PATTERNS


# ---------------------------------------------------------------------------
# Scaffolder .lexignore .env pattern tests
# ---------------------------------------------------------------------------


def test_skeleton_lexignore_contains_env_patterns(tmp_path: Path) -> None:
    """create_lexibrary_skeleton writes .env patterns to .lexignore."""
    create_lexibrary_skeleton(tmp_path)

    lexignore = (tmp_path / ".lexignore").read_text()
    assert ".env" in lexignore
    assert ".env.*" in lexignore
    assert "*.env" in lexignore


# ---------------------------------------------------------------------------
# create_lexibrary_from_wizard tests
# ---------------------------------------------------------------------------


def test_wizard_creates_directory_structure(tmp_path: Path) -> None:
    """Wizard scaffolder creates .lexibrary/, concepts/, conventions/, and stack/."""
    answers = _make_answers()
    create_lexibrary_from_wizard(tmp_path, answers)

    base = tmp_path / ".lexibrary"
    assert base.is_dir()
    assert (base / "concepts").is_dir()
    assert (base / "conventions").is_dir()
    assert (base / "stack").is_dir()
    assert (base / "concepts" / ".gitkeep").exists()
    assert (base / "conventions" / ".gitkeep").exists()
    assert (base / "stack" / ".gitkeep").exists()


def test_wizard_config_contains_wizard_values(tmp_path: Path) -> None:
    """Config file created by wizard contains the wizard-provided values."""
    answers = _make_answers(
        project_name="my-app",
        llm_provider="anthropic",
        scope_roots=[ScopeRoot(path="src/")],
    )
    create_lexibrary_from_wizard(tmp_path, answers)

    config_text = (tmp_path / ".lexibrary" / "config.yaml").read_text()
    parsed = yaml.safe_load(config_text)
    assert parsed["project_name"] == "my-app"
    assert parsed["llm"]["provider"] == "anthropic"
    assert parsed["scope_roots"] == [{"path": "src/"}]


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
    """Wizard scaffolder creates .lexignore with header and default .env patterns."""
    answers = _make_answers(ignore_patterns=[])
    create_lexibrary_from_wizard(tmp_path, answers)

    lexignore = (tmp_path / ".lexignore").read_text()
    assert lexignore.startswith("#")
    # Default .env patterns are always included even with no user patterns
    for pattern in _DEFAULT_LEXIGNORE_PATTERNS:
        assert pattern in lexignore


def test_wizard_returns_created_paths(tmp_path: Path) -> None:
    """Returned path list contains all created files and directories."""
    answers = _make_answers()
    created = create_lexibrary_from_wizard(tmp_path, answers)

    # Should contain directories, .gitkeep files, config, .lexignore
    path_strs = [str(p) for p in created]
    assert any("config.yaml" in s for s in path_strs)
    assert any(".lexignore" in s for s in path_strs)
    assert any("concepts" in s for s in path_strs)
    assert any("conventions" in s for s in path_strs)
    assert any("stack" in s for s in path_strs)


def test_wizard_does_not_create_start_here(tmp_path: Path) -> None:
    """Wizard scaffolder no longer creates START_HERE.md (dismantled)."""
    answers = _make_answers()
    create_lexibrary_from_wizard(tmp_path, answers)

    assert not (tmp_path / ".lexibrary" / "START_HERE.md").exists()


def test_wizard_import_from_init_package() -> None:
    """create_lexibrary_from_wizard is importable from lexibrary.init."""
    from lexibrary.init import create_lexibrary_from_wizard as fn

    assert callable(fn)


# ---------------------------------------------------------------------------
# IWH reference tests
# ---------------------------------------------------------------------------


def test_start_here_placeholder_removed() -> None:
    """START_HERE_PLACEHOLDER constant has been removed from scaffolder."""
    import lexibrary.init.scaffolder as mod

    assert not hasattr(mod, "START_HERE_PLACEHOLDER")


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
