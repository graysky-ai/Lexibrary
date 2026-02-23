"""Tests for project detection functions."""

from __future__ import annotations

from pathlib import Path

import pytest

from lexibrary.init.detection import (
    DetectedLLMProvider,
    DetectedProject,
    check_existing_agent_rules,
    detect_agent_environments,
    detect_llm_providers,
    detect_project_name,
    detect_project_type,
    detect_scope_roots,
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

    def test_all_three_roots(self, tmp_path: Path) -> None:
        for d in ["src", "lib", "app"]:
            (tmp_path / d).mkdir()
        result = detect_scope_roots(tmp_path)
        assert len(result) == 3


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

    def test_marker_found_in_agents_md(self, tmp_path: Path) -> None:
        rules = tmp_path / "AGENTS.md"
        rules.write_text("<!-- lexibrary: section -->\n", encoding="utf-8")
        result = check_existing_agent_rules(tmp_path, "codex")
        assert result == str(rules)


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
