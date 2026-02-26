"""Tests for the init wizard module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from rich.console import Console

from lexibrary.init.wizard import (
    WizardAnswers,
    _step_agent_environment,
    _step_hooks,
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
        assert answers.llm_api_key_source == "env"
        assert answers.llm_api_key_value == ""
        assert answers.ignore_patterns == []
        assert answers.token_budgets_customized is False
        assert answers.token_budgets == {}
        assert answers.iwh_enabled is True
        assert answers.install_hooks is False
        assert answers.confirmed is False

    def test_api_key_value_empty_by_default(self) -> None:
        """llm_api_key_value is empty string by default."""
        answers = WizardAnswers()
        assert answers.llm_api_key_value == ""

    def test_api_key_source_env_by_default(self) -> None:
        """llm_api_key_source defaults to 'env'."""
        answers = WizardAnswers()
        assert answers.llm_api_key_source == "env"

    def test_api_key_value_populated_when_set(self) -> None:
        """llm_api_key_value can be set explicitly (dotenv mode)."""
        answers = WizardAnswers(
            llm_api_key_source="dotenv",
            llm_api_key_value="sk-secret-key",
        )
        assert answers.llm_api_key_source == "dotenv"
        assert answers.llm_api_key_value == "sk-secret-key"

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

    def test_detected_with_missing_subdirs_auto_accepts(
        self, tmp_path: Path, console: Console
    ) -> None:
        """Defaults mode: .claude/ exists (detected) but commands/ missing — auto-accepts."""
        (tmp_path / ".claude").mkdir()
        # .claude/commands/ doesn't exist yet — defaults mode should still proceed
        result = _step_agent_environment(tmp_path, console, use_defaults=True)
        assert result == ["claude"]


class TestStepLLMProviderDefaults:
    def test_provider_detected(
        self, tmp_path: Path, console: Console, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_HOST", raising=False)
        provider, model, env, source, value = _step_llm_provider(
            tmp_path, console, use_defaults=True
        )
        assert provider == "anthropic"
        assert model == "claude-sonnet-4-6"
        assert env == "ANTHROPIC_API_KEY"
        assert source == "env"
        assert value == ""

    def test_no_provider_detected(
        self, tmp_path: Path, console: Console, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_HOST", raising=False)
        provider, model, env, source, value = _step_llm_provider(
            tmp_path, console, use_defaults=True
        )
        assert provider == "anthropic"
        assert env == "ANTHROPIC_API_KEY"
        assert source == "env"
        assert value == ""


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


class TestStepHooksDefaults:
    def test_defaults_not_installed(self, console: Console) -> None:
        """Defaults mode returns False (conservative default for unattended mode)."""
        result = _step_hooks(console, use_defaults=True)
        assert result is False


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
    def test_user_selects_existing_env(self, tmp_path: Path, console: Console) -> None:
        """Selecting an env whose directories exist skips the create prompt."""
        (tmp_path / ".claude" / "commands").mkdir(parents=True)
        (tmp_path / ".cursor" / "rules").mkdir(parents=True)
        (tmp_path / ".cursor" / "skills").mkdir(parents=True)
        with patch("lexibrary.init.wizard.Prompt.ask", return_value="claude, cursor"):
            result = _step_agent_environment(tmp_path, console, use_defaults=False)
        assert result == ["claude", "cursor"]

    def test_user_enters_empty(self, tmp_path: Path, console: Console) -> None:
        with patch("lexibrary.init.wizard.Prompt.ask", return_value=""):
            result = _step_agent_environment(tmp_path, console, use_defaults=False)
        assert result == []

    def test_missing_dirs_user_accepts_creation(
        self, tmp_path: Path, console: Console
    ) -> None:
        """User selects 'claude' without .claude/ dir, accepts creation."""
        with (
            patch("lexibrary.init.wizard.Prompt.ask", return_value="claude"),
            patch("lexibrary.init.wizard.Confirm.ask", return_value=True),
        ):
            result = _step_agent_environment(tmp_path, console, use_defaults=False)
        assert result == ["claude"]

    def test_missing_dirs_user_declines_creation(
        self, tmp_path: Path, console: Console
    ) -> None:
        """User selects 'claude' without .claude/ dir, declines — env removed."""
        with (
            patch("lexibrary.init.wizard.Prompt.ask", return_value="claude"),
            patch("lexibrary.init.wizard.Confirm.ask", return_value=False),
        ):
            result = _step_agent_environment(tmp_path, console, use_defaults=False)
        assert result == []

    def test_missing_dirs_partial_decline(self, tmp_path: Path, console: Console) -> None:
        """One env has dirs, one doesn't — declining removes only the missing one."""
        (tmp_path / ".claude" / "commands").mkdir(parents=True)
        with (
            patch("lexibrary.init.wizard.Prompt.ask", return_value="claude, cursor"),
            patch("lexibrary.init.wizard.Confirm.ask", return_value=False),
        ):
            result = _step_agent_environment(tmp_path, console, use_defaults=False)
        assert result == ["claude"]


class TestStepLLMProviderInteractiveStorageModes:
    """Test _step_llm_provider() interactive mode covering all three storage modes."""

    def test_storage_mode_env(
        self, tmp_path: Path, console: Console, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """User selects 'env' storage mode — no key written, value is empty."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_HOST", raising=False)

        prompt_values = iter(["anthropic", "env"])
        with patch(
            "lexibrary.init.wizard.Prompt.ask",
            side_effect=lambda *a, **kw: next(prompt_values),
        ):
            provider, model, env, source, value = _step_llm_provider(
                tmp_path, console, use_defaults=False
            )

        assert provider == "anthropic"
        assert source == "env"
        assert value == ""
        # No .env file should be created
        assert not (tmp_path / ".env").exists()

    def test_storage_mode_manual(
        self, tmp_path: Path, console: Console, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """User selects 'manual' storage mode — no key written, value is empty."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_HOST", raising=False)

        prompt_values = iter(["anthropic", "manual"])
        with patch(
            "lexibrary.init.wizard.Prompt.ask",
            side_effect=lambda *a, **kw: next(prompt_values),
        ):
            provider, model, env, source, value = _step_llm_provider(
                tmp_path, console, use_defaults=False
            )

        assert provider == "anthropic"
        assert source == "manual"
        assert value == ""
        # No .env file should be created
        assert not (tmp_path / ".env").exists()

    def test_storage_mode_dotenv(
        self, tmp_path: Path, console: Console, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """User selects 'dotenv' storage mode — key is written to .env."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_HOST", raising=False)

        prompt_values = iter(["anthropic", "dotenv", "sk-my-secret-key"])
        with patch(
            "lexibrary.init.wizard.Prompt.ask",
            side_effect=lambda *a, **kw: next(prompt_values),
        ):
            provider, model, env, source, value = _step_llm_provider(
                tmp_path, console, use_defaults=False
            )

        assert provider == "anthropic"
        assert source == "dotenv"
        assert value == "sk-my-secret-key"
        # .env file should be created with the key
        assert (tmp_path / ".env").exists()
        dotenv_content = (tmp_path / ".env").read_text()
        assert "ANTHROPIC_API_KEY" in dotenv_content
        # .gitignore should be created/updated with .env entry
        assert (tmp_path / ".gitignore").exists()
        gitignore_content = (tmp_path / ".gitignore").read_text()
        assert ".env" in gitignore_content

    def test_storage_mode_dotenv_appends_gitignore(
        self, tmp_path: Path, console: Console, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """dotenv mode appends .env to existing .gitignore if not already present."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_HOST", raising=False)

        # Pre-create .gitignore without .env
        (tmp_path / ".gitignore").write_text("node_modules/\n")

        prompt_values = iter(["anthropic", "dotenv", "sk-key"])
        with patch(
            "lexibrary.init.wizard.Prompt.ask",
            side_effect=lambda *a, **kw: next(prompt_values),
        ):
            _step_llm_provider(tmp_path, console, use_defaults=False)

        gitignore = (tmp_path / ".gitignore").read_text()
        assert "node_modules/" in gitignore
        assert ".env" in gitignore

    def test_no_provider_detected_uses_anthropic_default(
        self, tmp_path: Path, console: Console, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When no provider is detected, defaults to anthropic and still prompts for storage."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_HOST", raising=False)

        prompt_values = iter(["env"])
        with patch(
            "lexibrary.init.wizard.Prompt.ask",
            side_effect=lambda *a, **kw: next(prompt_values),
        ):
            provider, model, env, source, value = _step_llm_provider(
                tmp_path, console, use_defaults=False
            )

        assert provider == "anthropic"
        assert model == "claude-sonnet-4-6"
        assert env == "ANTHROPIC_API_KEY"
        assert source == "env"
        assert value == ""


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
        # Responses for: design_file_tokens, design_file_abridged_tokens,
        # aindex_tokens, concept_file_tokens, convention_file_tokens
        prompt_responses = iter(["500", "100", "200", "400", "500"])
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


class TestStepHooksInteractive:
    def test_user_accepts_hooks(self, console: Console) -> None:
        """User accepts default (True) at hooks prompt."""
        with patch("lexibrary.init.wizard.Confirm.ask", return_value=True):
            result = _step_hooks(console, use_defaults=False)
        assert result is True

    def test_user_declines_hooks(self, console: Console) -> None:
        """User declines hooks installation."""
        with patch("lexibrary.init.wizard.Confirm.ask", return_value=False):
            result = _step_hooks(console, use_defaults=False)
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
        assert result.install_hooks is False
        assert result.token_budgets_customized is False

    def test_use_defaults_install_hooks_is_false(
        self, tmp_path: Path, console: Console, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Defaults mode sets install_hooks to False (conservative default)."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_HOST", raising=False)

        result = run_wizard(tmp_path, console, use_defaults=True)
        assert result is not None
        assert result.install_hooks is False

    def test_use_defaults_api_key_value_is_empty(
        self, tmp_path: Path, console: Console, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """use_defaults=True sets llm_api_key_value to empty and source to 'env'."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_HOST", raising=False)

        result = run_wizard(tmp_path, console, use_defaults=True)

        assert result is not None
        assert result.llm_api_key_source == "env"
        assert result.llm_api_key_value == ""

    def test_use_defaults_no_env_key_api_key_value_is_empty(
        self, tmp_path: Path, console: Console, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """use_defaults=True with no provider detected still has empty api_key_value."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_HOST", raising=False)

        result = run_wizard(tmp_path, console, use_defaults=True)

        assert result is not None
        assert result.llm_api_key_source == "env"
        assert result.llm_api_key_value == ""

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
                "env",  # step 4: storage method
                "",  # step 5: custom patterns (no type detected, no suggestions)
            ]
        )
        confirm_values = iter(
            [
                False,  # step 6: don't customize budgets
                True,  # step 7: IWH enabled
                False,  # step 8: don't install hooks
                False,  # step 9: cancel at summary
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
                "env",  # step 4: storage method
            ]
        )
        confirm_values = iter(
            [
                True,  # step 3: create missing .claude/ dirs
                True,  # step 5: accept ignore patterns (python detected)
                False,  # step 6: don't customize budgets
                True,  # step 7: IWH enabled
                True,  # step 8: install hooks
                True,  # step 9: confirm
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
        assert result.llm_api_key_source == "env"
        assert result.llm_api_key_value == ""
        assert result.install_hooks is True

    def test_interactive_dotenv_populates_api_key_value(
        self, tmp_path: Path, console: Console, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Interactive dotenv mode populates llm_api_key_value on the answers."""
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
                "dotenv",  # step 4: storage method
                "sk-my-secret-key",  # step 4: API key value
            ]
        )
        confirm_values = iter(
            [
                True,  # step 3: create missing .claude/ dirs
                True,  # step 5: accept ignore patterns (python detected)
                False,  # step 6: don't customize budgets
                True,  # step 7: IWH enabled
                False,  # step 8: don't install hooks
                True,  # step 9: confirm
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
        assert result.llm_api_key_source == "dotenv"
        assert result.llm_api_key_value == "sk-my-secret-key"
        # .env file should have been written
        assert (tmp_path / ".env").exists()

    def test_interactive_hooks_accepted(
        self, tmp_path: Path, console: Console, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Interactive mode with hooks accepted sets install_hooks=True."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_HOST", raising=False)

        prompt_values = iter(
            [
                tmp_path.name,  # step 1: project name
                ".",  # step 2: scope root
                "",  # step 3: agent environments
                "env",  # step 4: storage method
                "",  # step 5: custom patterns
            ]
        )
        confirm_values = iter(
            [
                False,  # step 6: don't customize budgets
                True,  # step 7: IWH enabled
                True,  # step 8: install hooks
                True,  # step 9: confirm
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
        assert result.install_hooks is True

    def test_interactive_hooks_declined(
        self, tmp_path: Path, console: Console, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Interactive mode with hooks declined sets install_hooks=False."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_HOST", raising=False)

        prompt_values = iter(
            [
                tmp_path.name,  # step 1: project name
                ".",  # step 2: scope root
                "",  # step 3: agent environments
                "env",  # step 4: storage method
                "",  # step 5: custom patterns
            ]
        )
        confirm_values = iter(
            [
                False,  # step 6: don't customize budgets
                True,  # step 7: IWH enabled
                False,  # step 8: don't install hooks
                True,  # step 9: confirm
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
        assert result.install_hooks is False
