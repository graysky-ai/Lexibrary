"""Tests for project detection functions."""

from __future__ import annotations

from pathlib import Path

import pytest

from lexibrary.init.detection import (
    DetectedLLMProvider,
    DetectedProject,
    check_existing_agent_rules,
    check_missing_agent_dirs,
    detect_agent_environments,
    detect_llm_providers,
    detect_project_name,
    detect_project_type,
    detect_scope_roots,
    get_all_agent_environments,
    get_all_llm_providers,
    suggest_ignore_patterns,
)

# -----------------------------------------------------------------------
# DetectedProject / DetectedLLMProvider named tuples
# -----------------------------------------------------------------------


class TestDetectedProject:
    def test_named_tuple_fields(self) -> None:
        result = DetectedProject(name="myproject", source="pyproject.toml")
        assert result.name == "myproject"
        assert result.source == "pyproject.toml"

    def test_tuple_unpacking(self) -> None:
        name, source = DetectedProject(name="x", source="directory")
        assert name == "x"
        assert source == "directory"


class TestDetectedLLMProvider:
    def test_named_tuple_fields(self) -> None:
        result = DetectedLLMProvider(
            provider="anthropic",
            api_key_env="ANTHROPIC_API_KEY",
            model="claude-sonnet-4-6",
        )
        assert result.provider == "anthropic"
        assert result.api_key_env == "ANTHROPIC_API_KEY"
        assert result.model == "claude-sonnet-4-6"


# -----------------------------------------------------------------------
# detect_project_name
# -----------------------------------------------------------------------


class TestDetectProjectName:
    def test_from_pyproject_toml(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "my-lib"\n',
            encoding="utf-8",
        )
        result = detect_project_name(tmp_path)
        assert result == DetectedProject(name="my-lib", source="pyproject.toml")

    def test_from_package_json_when_no_pyproject(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text(
            '{"name": "my-app"}',
            encoding="utf-8",
        )
        result = detect_project_name(tmp_path)
        assert result == DetectedProject(name="my-app", source="package.json")

    def test_fallback_to_directory_name(self, tmp_path: Path) -> None:
        result = detect_project_name(tmp_path)
        assert result == DetectedProject(name=tmp_path.name, source="directory")

    def test_malformed_pyproject_falls_through(self, tmp_path: Path) -> None:
        # pyproject.toml exists but has no [project] table
        (tmp_path / "pyproject.toml").write_text(
            "[tool.ruff]\nline-length = 88\n",
            encoding="utf-8",
        )
        result = detect_project_name(tmp_path)
        assert result.source == "directory"

    def test_pyproject_no_name_key_falls_through(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            "[project]\nversion = '1.0'\n",
            encoding="utf-8",
        )
        result = detect_project_name(tmp_path)
        assert result.source == "directory"

    def test_malformed_package_json_falls_through(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text("not valid json", encoding="utf-8")
        result = detect_project_name(tmp_path)
        assert result.source == "directory"

    def test_package_json_no_name_falls_through(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text(
            '{"version": "1.0.0"}',
            encoding="utf-8",
        )
        result = detect_project_name(tmp_path)
        assert result.source == "directory"

    def test_pyproject_takes_precedence_over_package_json(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "from-toml"\n',
            encoding="utf-8",
        )
        (tmp_path / "package.json").write_text(
            '{"name": "from-json"}',
            encoding="utf-8",
        )
        result = detect_project_name(tmp_path)
        assert result == DetectedProject(name="from-toml", source="pyproject.toml")

    def test_malformed_pyproject_falls_to_package_json(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("{{invalid}}", encoding="utf-8")
        (tmp_path / "package.json").write_text(
            '{"name": "fallback-app"}',
            encoding="utf-8",
        )
        result = detect_project_name(tmp_path)
        assert result == DetectedProject(name="fallback-app", source="package.json")


# -----------------------------------------------------------------------
# detect_scope_roots
# -----------------------------------------------------------------------


class TestDetectScopeRoots:
    def test_detect_src_directory(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        result = detect_scope_roots(tmp_path)
        assert "src/" in result

    def test_detect_multiple_roots(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "lib").mkdir()
        result = detect_scope_roots(tmp_path)
        assert "src/" in result
        assert "lib/" in result

    def test_no_common_directories(self, tmp_path: Path) -> None:
        result = detect_scope_roots(tmp_path)
        assert result == []

    def test_detect_app_directory(self, tmp_path: Path) -> None:
        (tmp_path / "app").mkdir()
        result = detect_scope_roots(tmp_path)
        assert "app/" in result

    def test_detect_baml_src_directory(self, tmp_path: Path) -> None:
        """``baml_src/`` is part of the candidate list (multi-root task 9.1)."""
        (tmp_path / "baml_src").mkdir()
        result = detect_scope_roots(tmp_path)
        assert "baml_src/" in result

    def test_detect_baml_src_alongside_src(self, tmp_path: Path) -> None:
        """When both ``src/`` and ``baml_src/`` exist, both are returned.

        This is the canonical multi-root repo shape (Python sources plus
        BAML schemas) and must light up both roots by default for the
        wizard's pre-selected checkbox UX.
        """
        (tmp_path / "src").mkdir()
        (tmp_path / "baml_src").mkdir()
        result = detect_scope_roots(tmp_path)
        assert "src/" in result
        assert "baml_src/" in result

    def test_detect_baml_src_absent_when_missing(self, tmp_path: Path) -> None:
        """``baml_src/`` is not returned when the directory does not exist."""
        (tmp_path / "src").mkdir()
        result = detect_scope_roots(tmp_path)
        assert "baml_src/" not in result

    def test_candidate_declaration_order(self, tmp_path: Path) -> None:
        """Detection preserves the declared candidate order: src, lib, app, baml_src.

        The wizard's multi-select UX relies on this order, so we lock it in.
        """
        for d in ["src", "lib", "app", "baml_src"]:
            (tmp_path / d).mkdir()
        result = detect_scope_roots(tmp_path)
        assert result == ["src/", "lib/", "app/", "baml_src/"]

    def test_all_four_roots(self, tmp_path: Path) -> None:
        """All four canonical roots (including ``baml_src/``) are detected."""
        for d in ["src", "lib", "app", "baml_src"]:
            (tmp_path / d).mkdir()
        result = detect_scope_roots(tmp_path)
        assert len(result) == 4


# -----------------------------------------------------------------------
# detect_agent_environments
# -----------------------------------------------------------------------


class TestDetectAgentEnvironments:
    def test_detect_claude_from_directory(self, tmp_path: Path) -> None:
        (tmp_path / ".claude").mkdir()
        result = detect_agent_environments(tmp_path)
        assert "claude" in result

    def test_detect_claude_from_file(self, tmp_path: Path) -> None:
        (tmp_path / "CLAUDE.md").touch()
        result = detect_agent_environments(tmp_path)
        assert "claude" in result

    def test_no_duplicate_from_both_markers(self, tmp_path: Path) -> None:
        (tmp_path / ".claude").mkdir()
        (tmp_path / "CLAUDE.md").touch()
        result = detect_agent_environments(tmp_path)
        assert result.count("claude") == 1

    def test_detect_cursor(self, tmp_path: Path) -> None:
        (tmp_path / ".cursor").mkdir()
        result = detect_agent_environments(tmp_path)
        assert "cursor" in result

    def test_detect_codex(self, tmp_path: Path) -> None:
        (tmp_path / "AGENTS.md").touch()
        result = detect_agent_environments(tmp_path)
        assert "codex" in result

    def test_detect_multiple_environments(self, tmp_path: Path) -> None:
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".cursor").mkdir()
        result = detect_agent_environments(tmp_path)
        assert "claude" in result
        assert "cursor" in result

    def test_no_environments_detected(self, tmp_path: Path) -> None:
        result = detect_agent_environments(tmp_path)
        assert result == []


# -----------------------------------------------------------------------
# get_all_agent_environments
# -----------------------------------------------------------------------


class TestGetAllAgentEnvironments:
    def test_returns_all_three_environments(self) -> None:
        result = get_all_agent_environments()
        assert len(result) == 3

    def test_contains_expected_names(self) -> None:
        result = get_all_agent_environments()
        assert "claude" in result
        assert "cursor" in result
        assert "codex" in result

    def test_returns_list_of_strings(self) -> None:
        result = get_all_agent_environments()
        assert isinstance(result, list)
        for name in result:
            assert isinstance(name, str)

    def test_independent_of_filesystem(self, tmp_path: Path) -> None:
        """Result does not change based on what marker files exist on disk."""
        # No markers exist in tmp_path, but we still get all environments
        result_without_markers = get_all_agent_environments()
        # Create all markers
        (tmp_path / ".claude").mkdir()
        (tmp_path / "CLAUDE.md").touch()
        (tmp_path / ".cursor").mkdir()
        (tmp_path / "AGENTS.md").touch()
        result_with_markers = get_all_agent_environments()
        assert result_without_markers == result_with_markers

    def test_preserves_registry_order(self) -> None:
        result = get_all_agent_environments()
        assert result == ["claude", "cursor", "codex"]


# -----------------------------------------------------------------------
# check_existing_agent_rules
# -----------------------------------------------------------------------


class TestCheckExistingAgentRules:
    def test_marker_found_in_claude_md(self, tmp_path: Path) -> None:
        rules = tmp_path / "CLAUDE.md"
        rules.write_text("# Rules\n<!-- lexibrary: managed -->\n", encoding="utf-8")
        result = check_existing_agent_rules(tmp_path, "claude")
        assert result == str(rules)

    def test_no_marker_found(self, tmp_path: Path) -> None:
        rules = tmp_path / "CLAUDE.md"
        rules.write_text("# My Rules\nnothing here\n", encoding="utf-8")
        result = check_existing_agent_rules(tmp_path, "claude")
        assert result is None

    def test_rules_file_does_not_exist(self, tmp_path: Path) -> None:
        result = check_existing_agent_rules(tmp_path, "claude")
        assert result is None

    def test_marker_in_nested_claude_md(self, tmp_path: Path) -> None:
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        rules = claude_dir / "CLAUDE.md"
        rules.write_text("<!-- lexibrary: v1 -->\n", encoding="utf-8")
        result = check_existing_agent_rules(tmp_path, "claude")
        assert result == str(rules)

    def test_unknown_environment_returns_none(self, tmp_path: Path) -> None:
        result = check_existing_agent_rules(tmp_path, "unknown_env")
        assert result is None

    def test_cursor_rules_directory_check(self, tmp_path: Path) -> None:
        # .cursor/rules is a directory, not a file — should return None
        cursor_rules = tmp_path / ".cursor" / "rules"
        cursor_rules.mkdir(parents=True)
        result = check_existing_agent_rules(tmp_path, "cursor")
        assert result is None

    def test_marker_found_in_agents_md(self, tmp_path: Path) -> None:
        rules = tmp_path / "AGENTS.md"
        rules.write_text("<!-- lexibrary: section -->\n", encoding="utf-8")
        result = check_existing_agent_rules(tmp_path, "codex")
        assert result == str(rules)


# -----------------------------------------------------------------------
# check_missing_agent_dirs
# -----------------------------------------------------------------------


class TestCheckMissingAgentDirs:
    def test_claude_dirs_missing(self, tmp_path: Path) -> None:
        result = check_missing_agent_dirs(tmp_path, ["claude"])
        assert "claude" in result
        assert ".claude/" in result["claude"]
        assert ".claude/skills/" in result["claude"]

    def test_claude_dirs_exist(self, tmp_path: Path) -> None:
        (tmp_path / ".claude" / "skills").mkdir(parents=True)
        result = check_missing_agent_dirs(tmp_path, ["claude"])
        assert result == {}

    def test_claude_partial_dirs(self, tmp_path: Path) -> None:
        """Base .claude/ exists but skills/ subdir is missing."""
        (tmp_path / ".claude").mkdir()
        result = check_missing_agent_dirs(tmp_path, ["claude"])
        assert "claude" in result
        assert ".claude/skills/" in result["claude"]
        assert ".claude/" not in result["claude"]

    def test_cursor_dirs_missing(self, tmp_path: Path) -> None:
        result = check_missing_agent_dirs(tmp_path, ["cursor"])
        assert "cursor" in result
        assert ".cursor/" in result["cursor"]

    def test_cursor_dirs_exist(self, tmp_path: Path) -> None:
        (tmp_path / ".cursor" / "rules").mkdir(parents=True)
        (tmp_path / ".cursor" / "skills").mkdir(parents=True)
        result = check_missing_agent_dirs(tmp_path, ["cursor"])
        assert result == {}

    def test_codex_no_dirs_needed(self, tmp_path: Path) -> None:
        result = check_missing_agent_dirs(tmp_path, ["codex"])
        assert result == {}

    def test_multiple_envs_mixed(self, tmp_path: Path) -> None:
        (tmp_path / ".claude" / "skills").mkdir(parents=True)
        result = check_missing_agent_dirs(tmp_path, ["claude", "cursor"])
        assert "claude" not in result
        assert "cursor" in result

    def test_unknown_env_returns_empty(self, tmp_path: Path) -> None:
        result = check_missing_agent_dirs(tmp_path, ["unknown"])
        assert result == {}

    def test_empty_envs(self, tmp_path: Path) -> None:
        result = check_missing_agent_dirs(tmp_path, [])
        assert result == {}


# -----------------------------------------------------------------------
# detect_llm_providers
# -----------------------------------------------------------------------


class TestDetectLLMProviders:
    def test_anthropic_detected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_HOST", raising=False)
        result = detect_llm_providers()
        assert len(result) >= 1
        assert result[0].provider == "anthropic"
        assert result[0].api_key_env == "ANTHROPIC_API_KEY"

    def test_multiple_providers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_HOST", raising=False)
        result = detect_llm_providers()
        providers = [r.provider for r in result]
        assert providers == ["anthropic", "openai"]

    def test_no_providers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_HOST", raising=False)
        result = detect_llm_providers()
        assert result == []

    def test_priority_order(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        result = detect_llm_providers()
        # Anthropic should come first (priority order)
        assert result[0].provider == "anthropic"
        assert result[1].provider == "ollama"


# -----------------------------------------------------------------------
# get_all_llm_providers
# -----------------------------------------------------------------------


class TestGetAllLLMProviders:
    def test_returns_all_four_providers(self) -> None:
        result = get_all_llm_providers()
        assert len(result) == 4

    def test_contains_expected_providers(self) -> None:
        result = get_all_llm_providers()
        provider_names = [p.provider for p in result]
        assert "anthropic" in provider_names
        assert "openai" in provider_names
        assert "google" in provider_names
        assert "ollama" in provider_names

    def test_correct_fields_anthropic(self) -> None:
        result = get_all_llm_providers()
        anthropic = [p for p in result if p.provider == "anthropic"][0]
        assert anthropic.api_key_env == "ANTHROPIC_API_KEY"
        assert anthropic.model == "claude-sonnet-4-6"

    def test_correct_fields_openai(self) -> None:
        result = get_all_llm_providers()
        openai = [p for p in result if p.provider == "openai"][0]
        assert openai.api_key_env == "OPENAI_API_KEY"
        assert openai.model == "gpt-4o"

    def test_correct_fields_google(self) -> None:
        result = get_all_llm_providers()
        google = [p for p in result if p.provider == "google"][0]
        assert google.api_key_env == "GEMINI_API_KEY"
        assert google.model == "gemini-2.0-flash"

    def test_correct_fields_ollama(self) -> None:
        result = get_all_llm_providers()
        ollama = [p for p in result if p.provider == "ollama"][0]
        assert ollama.api_key_env == "OLLAMA_HOST"
        assert ollama.model == "llama3"

    def test_returns_detected_llm_provider_instances(self) -> None:
        result = get_all_llm_providers()
        for provider in result:
            assert isinstance(provider, DetectedLLMProvider)

    def test_independent_of_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Result does not change based on whether env vars are set."""
        # Clear all provider env vars
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_HOST", raising=False)
        result_without_env = get_all_llm_providers()

        # Set all provider env vars
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
        result_with_env = get_all_llm_providers()

        assert result_without_env == result_with_env

    def test_preserves_priority_order(self) -> None:
        result = get_all_llm_providers()
        provider_names = [p.provider for p in result]
        assert provider_names == ["anthropic", "openai", "google", "ollama"]


# -----------------------------------------------------------------------
# detect_project_type
# -----------------------------------------------------------------------


class TestDetectProjectType:
    def test_python_from_pyproject(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").touch()
        assert detect_project_type(tmp_path) == "python"

    def test_python_from_setup_py(self, tmp_path: Path) -> None:
        (tmp_path / "setup.py").touch()
        assert detect_project_type(tmp_path) == "python"

    def test_typescript(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").touch()
        (tmp_path / "tsconfig.json").touch()
        assert detect_project_type(tmp_path) == "typescript"

    def test_node_without_tsconfig(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").touch()
        assert detect_project_type(tmp_path) == "node"

    def test_rust(self, tmp_path: Path) -> None:
        (tmp_path / "Cargo.toml").touch()
        assert detect_project_type(tmp_path) == "rust"

    def test_go(self, tmp_path: Path) -> None:
        (tmp_path / "go.mod").touch()
        assert detect_project_type(tmp_path) == "go"

    def test_unknown(self, tmp_path: Path) -> None:
        assert detect_project_type(tmp_path) is None


# -----------------------------------------------------------------------
# suggest_ignore_patterns
# -----------------------------------------------------------------------


class TestSuggestIgnorePatterns:
    def test_python_patterns(self) -> None:
        result = suggest_ignore_patterns("python")
        assert "**/migrations/" in result
        assert "**/__generated__/" in result

    def test_typescript_patterns(self) -> None:
        result = suggest_ignore_patterns("typescript")
        assert "dist/" in result
        assert "build/" in result
        assert "coverage/" in result
        assert ".next/" in result

    def test_node_patterns(self) -> None:
        result = suggest_ignore_patterns("node")
        assert "dist/" in result

    def test_rust_patterns(self) -> None:
        result = suggest_ignore_patterns("rust")
        assert "target/" in result

    def test_go_patterns(self) -> None:
        result = suggest_ignore_patterns("go")
        assert "vendor/" in result

    def test_none_returns_empty(self) -> None:
        assert suggest_ignore_patterns(None) == []

    def test_unknown_type_returns_empty(self) -> None:
        assert suggest_ignore_patterns("haskell") == []
