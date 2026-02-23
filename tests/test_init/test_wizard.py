"""Tests for the init wizard module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from rich.console import Console

from lexibrary.init.wizard import (
    WizardAnswers,
    _step_agent_environment,
    _step_ignore_patterns,
    _step_iwh,
    _step_llm_provider,
    _step_project_name,
    _step_scope_root,
    _step_summary,
    _step_token_budgets,
    run_wizard,
)


@pytest.fixture()
def console() -> Console:
    """Quiet console that doesn't write to stdout."""
    return Console(quiet=True)


# -----------------------------------------------------------------------
# WizardAnswers dataclass
# -----------------------------------------------------------------------


class TestWizardAnswers:
    def test_default_values(self) -> None:
        answers = WizardAnswers()
        assert answers.project_name == ""
        assert answers.scope_root == "."
        assert answers.agent_environments == []
        assert answers.llm_provider == "anthropic"
        assert answers.llm_model == "claude-sonnet-4-6"
        assert answers.llm_api_key_env == "ANTHROPIC_API_KEY"
        assert answers.ignore_patterns == []
        assert answers.token_budgets_customized is False
        assert answers.token_budgets == {}
        assert answers.iwh_enabled is True
        assert answers.confirmed is False

    def test_custom_values(self) -> None:
        answers = WizardAnswers(
            project_name="my-app",
            scope_root="src/",
            agent_environments=["claude", "cursor"],
            llm_provider="openai",
            llm_model="gpt-4o",
            llm_api_key_env="OPENAI_API_KEY",
            ignore_patterns=["dist/"],
            token_budgets_customized=True,
            token_budgets={"design_file_tokens": 500},
            iwh_enabled=False,
            confirmed=True,
        )
        assert answers.project_name == "my-app"
        assert answers.llm_provider == "openai"
        assert answers.confirmed is True

    def test_mutable_defaults_are_independent(self) -> None:
        a = WizardAnswers()
        b = WizardAnswers()
        a.agent_environments.append("claude")
        assert b.agent_environments == []


# -----------------------------------------------------------------------
# Step functions — use_defaults mode (no prompting)
# -----------------------------------------------------------------------


class TestStepProjectNameDefaults:
    def test_detected_from_pyproject(self, tmp_path: Path, console: Console) -> None:
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "my-app"\n', encoding="utf-8")
        result = _step_project_name(tmp_path, console, use_defaults=True)
        assert result == "my-app"

    def test_fallback_to_directory(self, tmp_path: Path, console: Console) -> None:
        result = _step_project_name(tmp_path, console, use_defaults=True)
        assert result == tmp_path.name


class TestStepScopeRootDefaults:
    def test_detected_src(self, tmp_path: Path, console: Console) -> None:
        (tmp_path / "src").mkdir()
        result = _step_scope_root(tmp_path, console, use_defaults=True)
        assert result == "src/"

    def test_default_dot(self, tmp_path: Path, console: Console) -> None:
        result = _step_scope_root(tmp_path, console, use_defaults=True)
        assert result == "."


class TestStepAgentEnvironmentDefaults:
    def test_detected_environments(self, tmp_path: Path, console: Console) -> None:
        (tmp_path / ".claude").mkdir()
        result = _step_agent_environment(tmp_path, console, use_defaults=True)
        assert result == ["claude"]

    def test_no_environments(self, tmp_path: Path, console: Console) -> None:
        result = _step_agent_environment(tmp_path, console, use_defaults=True)
        assert result == []


class TestStepLLMProviderDefaults:
    def test_provider_detected(self, console: Console, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_HOST", raising=False)
        provider, model, env = _step_llm_provider(console, use_defaults=True)
        assert provider == "anthropic"
        assert model == "claude-sonnet-4-6"
        assert env == "ANTHROPIC_API_KEY"

    def test_no_provider_detected(self, console: Console, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_HOST", raising=False)
        provider, model, env = _step_llm_provider(console, use_defaults=True)
        assert provider == "anthropic"
        assert env == "ANTHROPIC_API_KEY"


class TestStepIgnorePatternsDefaults:
    def test_python_patterns(self, tmp_path: Path, console: Console) -> None:
        (tmp_path / "pyproject.toml").touch()
        result = _step_ignore_patterns(tmp_path, console, use_defaults=True)
        assert "**/migrations/" in result
        assert "**/__generated__/" in result

    def test_no_project_type(self, tmp_path: Path, console: Console) -> None:
        result = _step_ignore_patterns(tmp_path, console, use_defaults=True)
        assert result == []


class TestStepTokenBudgetsDefaults:
    def test_defaults_not_customized(self, console: Console) -> None:
        customized, budgets = _step_token_budgets(console, use_defaults=True)
        assert customized is False
        assert budgets == {}


class TestStepIWHDefaults:
    def test_defaults_enabled(self, console: Console) -> None:
        result = _step_iwh(console, use_defaults=True)
        assert result is True


class TestStepSummaryDefaults:
    def test_auto_confirms(self, console: Console) -> None:
        answers = WizardAnswers(project_name="test-proj")
        result = _step_summary(answers, console, use_defaults=True)
        assert result is True


# -----------------------------------------------------------------------
# Step functions — interactive mode (mock rich.prompt)
# -----------------------------------------------------------------------


class TestStepProjectNameInteractive:
    def test_user_accepts_detected(self, tmp_path: Path, console: Console) -> None:
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "detected"\n', encoding="utf-8")
        with patch("lexibrary.init.wizard.Prompt.ask", return_value="detected"):
            result = _step_project_name(tmp_path, console, use_defaults=False)
        assert result == "detected"

    def test_user_overrides_name(self, tmp_path: Path, console: Console) -> None:
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "detected"\n', encoding="utf-8")
        with patch("lexibrary.init.wizard.Prompt.ask", return_value="custom-name"):
            result = _step_project_name(tmp_path, console, use_defaults=False)
        assert result == "custom-name"


class TestStepScopeRootInteractive:
    def test_user_accepts_detected(self, tmp_path: Path, console: Console) -> None:
        (tmp_path / "src").mkdir()
        with patch("lexibrary.init.wizard.Prompt.ask", return_value="src/"):
            result = _step_scope_root(tmp_path, console, use_defaults=False)
        assert result == "src/"


class TestStepAgentEnvironmentInteractive:
    def test_user_selects_multiple(self, tmp_path: Path, console: Console) -> None:
        with patch("lexibrary.init.wizard.Prompt.ask", return_value="claude, cursor"):
            result = _step_agent_environment(tmp_path, console, use_defaults=False)
        assert result == ["claude", "cursor"]

    def test_user_enters_empty(self, tmp_path: Path, console: Console) -> None:
        with patch("lexibrary.init.wizard.Prompt.ask", return_value=""):
            result = _step_agent_environment(tmp_path, console, use_defaults=False)
        assert result == []


class TestStepIgnorePatternsInteractive:
    def test_user_accepts_suggestions(self, tmp_path: Path, console: Console) -> None:
        (tmp_path / "pyproject.toml").touch()
        with patch("lexibrary.init.wizard.Confirm.ask", return_value=True):
            result = _step_ignore_patterns(tmp_path, console, use_defaults=False)
        assert "**/migrations/" in result

    def test_user_rejects_and_provides_custom(self, tmp_path: Path, console: Console) -> None:
        (tmp_path / "pyproject.toml").touch()
        with (
            patch("lexibrary.init.wizard.Confirm.ask", return_value=False),
            patch("lexibrary.init.wizard.Prompt.ask", return_value="build/, dist/"),
        ):
            result = _step_ignore_patterns(tmp_path, console, use_defaults=False)
        assert result == ["build/", "dist/"]


class TestStepTokenBudgetsInteractive:
    def test_user_declines_customization(self, console: Console) -> None:
        with patch("lexibrary.init.wizard.Confirm.ask", return_value=False):
            customized, budgets = _step_token_budgets(console, use_defaults=False)
        assert customized is False
        assert budgets == {}

    def test_user_customizes_a_budget(self, console: Console) -> None:
        prompt_responses = iter(["800", "100", "500", "100", "200", "400"])
        with (
            patch("lexibrary.init.wizard.Confirm.ask", return_value=True),
            patch(
                "lexibrary.init.wizard.Prompt.ask",
                side_effect=lambda *a, **kw: next(prompt_responses),
            ),
        ):
            customized, budgets = _step_token_budgets(console, use_defaults=False)
        assert customized is True
        assert budgets == {"design_file_tokens": 500}


class TestStepIWHInteractive:
    def test_user_enables(self, console: Console) -> None:
        with patch("lexibrary.init.wizard.Confirm.ask", return_value=True):
            result = _step_iwh(console, use_defaults=False)
        assert result is True

    def test_user_disables(self, console: Console) -> None:
        with patch("lexibrary.init.wizard.Confirm.ask", return_value=False):
            result = _step_iwh(console, use_defaults=False)
        assert result is False


class TestStepSummaryInteractive:
    def test_user_confirms(self, console: Console) -> None:
        answers = WizardAnswers(project_name="test-proj")
        with patch("lexibrary.init.wizard.Confirm.ask", return_value=True):
            result = _step_summary(answers, console, use_defaults=False)
        assert result is True

    def test_user_cancels(self, console: Console) -> None:
        answers = WizardAnswers(project_name="test-proj")
        with patch("lexibrary.init.wizard.Confirm.ask", return_value=False):
            result = _step_summary(answers, console, use_defaults=False)
        assert result is False


# -----------------------------------------------------------------------
# run_wizard() — orchestrator
# -----------------------------------------------------------------------


class TestRunWizardDefaults:
    def test_use_defaults_returns_answers(
        self, tmp_path: Path, console: Console, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """use_defaults=True should return answers without prompting."""
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "my-app"\n', encoding="utf-8")
        (tmp_path / "src").mkdir()
        (tmp_path / ".claude").mkdir()
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_HOST", raising=False)

        result = run_wizard(tmp_path, console, use_defaults=True)

        assert result is not None
        assert result.confirmed is True
        assert result.project_name == "my-app"
        assert result.scope_root == "src/"
        assert result.agent_environments == ["claude"]
        assert result.llm_provider == "anthropic"
        assert result.llm_model == "claude-sonnet-4-6"
        assert result.llm_api_key_env == "ANTHROPIC_API_KEY"
        assert result.iwh_enabled is True
        assert result.token_budgets_customized is False

    def test_use_defaults_detected_project_name_from_pyproject(
        self, tmp_path: Path, console: Console, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Scenario: Defaults mode uses detected project name."""
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "my-app"\n', encoding="utf-8")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_HOST", raising=False)

        result = run_wizard(tmp_path, console, use_defaults=True)
        assert result is not None
        assert result.project_name == "my-app"

    def test_use_defaults_no_detection(
        self, tmp_path: Path, console: Console, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Bare directory should still return valid defaults."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_HOST", raising=False)

        result = run_wizard(tmp_path, console, use_defaults=True)
        assert result is not None
        assert result.confirmed is True
        assert result.project_name == tmp_path.name
        assert result.scope_root == "."
        assert result.agent_environments == []
        assert result.ignore_patterns == []


class TestRunWizardInteractive:
    def test_cancellation_returns_none(
        self, tmp_path: Path, console: Console, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """User declining at summary should return None."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_HOST", raising=False)

        prompt_values = iter(
            [
                tmp_path.name,  # step 1: project name
                ".",  # step 2: scope root
                "",  # step 3: agent environments
                "",  # step 5: custom patterns (no type detected, no suggestions)
            ]
        )
        confirm_values = iter(
            [
                False,  # step 6: don't customize budgets
                True,  # step 7: IWH enabled
                False,  # step 8: cancel at summary
            ]
        )

        with (
            patch(
                "lexibrary.init.wizard.Prompt.ask",
                side_effect=lambda *a, **kw: next(prompt_values),
            ),
            patch(
                "lexibrary.init.wizard.Confirm.ask",
                side_effect=lambda *a, **kw: next(confirm_values),
            ),
        ):
            result = run_wizard(tmp_path, console, use_defaults=False)

        assert result is None

    def test_confirmed_returns_answers(
        self, tmp_path: Path, console: Console, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """User confirming at summary should return populated answers."""
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "my-app"\n', encoding="utf-8")
        (tmp_path / "src").mkdir()
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_HOST", raising=False)

        prompt_values = iter(
            [
                "my-app",  # step 1: accept project name
                "src/",  # step 2: accept scope root
                "claude",  # step 3: agent environments
                "anthropic",  # step 4: select LLM provider
            ]
        )
        confirm_values = iter(
            [
                True,  # step 5: accept ignore patterns (python detected)
                False,  # step 6: don't customize budgets
                True,  # step 7: IWH enabled
                True,  # step 8: confirm
            ]
        )

        with (
            patch(
                "lexibrary.init.wizard.Prompt.ask",
                side_effect=lambda *a, **kw: next(prompt_values),
            ),
            patch(
                "lexibrary.init.wizard.Confirm.ask",
                side_effect=lambda *a, **kw: next(confirm_values),
            ),
        ):
            result = run_wizard(tmp_path, console, use_defaults=False)

        assert result is not None
        assert result.confirmed is True
        assert result.project_name == "my-app"
        assert result.scope_root == "src/"
        assert result.agent_environments == ["claude"]
        assert result.llm_provider == "anthropic"
