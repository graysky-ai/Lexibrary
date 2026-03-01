"""Tests for the init wizard module."""

from __future__ import annotations

from pathlib import Path
from typing import Any
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

# -----------------------------------------------------------------------
# Mock helper for questionary widgets
# -----------------------------------------------------------------------


class _MockQuestionaryResult:
    """Lightweight stand-in for a questionary widget's return value.

    ``questionary.select(...)`` and ``questionary.checkbox(...)`` return an
    intermediate *Question* object whose ``.ask()`` method actually runs the
    prompt.  In tests we replace the factory (``questionary.select``,
    ``questionary.checkbox``) with a callable that returns an instance of
    this class so that ``.ask()`` returns the predetermined *value* without
    any terminal interaction.
    """

    def __init__(self, value: Any) -> None:  # noqa: ANN401
        self._value = value

    def ask(self) -> Any:  # noqa: ANN401
        return self._value


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
        """Selecting envs whose directories exist skips the create prompt."""
        (tmp_path / ".claude" / "commands").mkdir(parents=True)
        (tmp_path / ".cursor" / "rules").mkdir(parents=True)
        (tmp_path / ".cursor" / "skills").mkdir(parents=True)
        with patch(
            "lexibrary.init.wizard.questionary.checkbox",
            return_value=_MockQuestionaryResult(["claude", "cursor"]),
        ):
            result = _step_agent_environment(tmp_path, console, use_defaults=False)
        assert result == ["claude", "cursor"]

    def test_user_selects_none(self, tmp_path: Path, console: Console) -> None:
        """User deselects all checkboxes — returns empty list."""
        with patch(
            "lexibrary.init.wizard.questionary.checkbox",
            return_value=_MockQuestionaryResult([]),
        ):
            result = _step_agent_environment(tmp_path, console, use_defaults=False)
        assert result == []

    def test_non_tty_falls_back_to_detected(self, tmp_path: Path, console: Console) -> None:
        """Non-TTY (questionary returns None) falls back to detected envs."""
        # Create .claude/ with full directory structure so no missing-dir prompt
        (tmp_path / ".claude" / "commands").mkdir(parents=True)
        with patch(
            "lexibrary.init.wizard.questionary.checkbox",
            return_value=_MockQuestionaryResult(None),
        ):
            result = _step_agent_environment(tmp_path, console, use_defaults=False)
        assert result == ["claude"]

    def test_missing_dirs_user_accepts_creation(self, tmp_path: Path, console: Console) -> None:
        """User selects 'claude' without .claude/ dir, accepts creation."""
        with (
            patch(
                "lexibrary.init.wizard.questionary.checkbox",
                return_value=_MockQuestionaryResult(["claude"]),
            ),
            patch("lexibrary.init.wizard.Confirm.ask", return_value=True),
        ):
            result = _step_agent_environment(tmp_path, console, use_defaults=False)
        assert result == ["claude"]

    def test_missing_dirs_user_declines_creation(self, tmp_path: Path, console: Console) -> None:
        """User selects 'claude' without .claude/ dir, declines — env removed."""
        with (
            patch(
                "lexibrary.init.wizard.questionary.checkbox",
                return_value=_MockQuestionaryResult(["claude"]),
            ),
            patch("lexibrary.init.wizard.Confirm.ask", return_value=False),
        ):
            result = _step_agent_environment(tmp_path, console, use_defaults=False)
        assert result == []

    def test_missing_dirs_partial_decline(self, tmp_path: Path, console: Console) -> None:
        """One env has dirs, one doesn't — declining removes only the missing one."""
        (tmp_path / ".claude" / "commands").mkdir(parents=True)
        with (
            patch(
                "lexibrary.init.wizard.questionary.checkbox",
                return_value=_MockQuestionaryResult(["claude", "cursor"]),
            ),
            patch("lexibrary.init.wizard.Confirm.ask", return_value=False),
        ):
            result = _step_agent_environment(tmp_path, console, use_defaults=False)
        assert result == ["claude"]


class TestStepLLMProviderInteractiveStorageModes:
    """Test _step_llm_provider() interactive mode covering all three storage modes.

    The wizard now uses questionary.select() for provider selection (4a) and
    storage method (4b).  Prompt.ask is used only for the env-var NAME in
    dotenv flow (4c).  The wizard never writes to .env or .gitignore.
    """

    def test_storage_mode_env(
        self, tmp_path: Path, console: Console, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """User selects 'env' storage mode — no key written, value is empty."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_HOST", raising=False)

        select_values = iter(["anthropic", "env"])
        with patch(
            "lexibrary.init.wizard.questionary.select",
            side_effect=lambda *a, **kw: _MockQuestionaryResult(next(select_values)),
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

        select_values = iter(["anthropic", "manual"])
        with patch(
            "lexibrary.init.wizard.questionary.select",
            side_effect=lambda *a, **kw: _MockQuestionaryResult(next(select_values)),
        ):
            provider, model, env, source, value = _step_llm_provider(
                tmp_path, console, use_defaults=False
            )

        assert provider == "anthropic"
        assert source == "manual"
        assert value == ""
        assert not (tmp_path / ".env").exists()

    def test_storage_mode_dotenv_asks_var_name_only(
        self, tmp_path: Path, console: Console, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """User selects 'dotenv' — wizard asks for env var NAME only, never writes .env."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_HOST", raising=False)

        select_values = iter(["anthropic", "dotenv"])
        with (
            patch(
                "lexibrary.init.wizard.questionary.select",
                side_effect=lambda *a, **kw: _MockQuestionaryResult(next(select_values)),
            ),
            patch(
                "lexibrary.init.wizard.Prompt.ask",
                return_value="ANTHROPIC_API_KEY",
            ),
        ):
            provider, model, env, source, value = _step_llm_provider(
                tmp_path, console, use_defaults=False
            )

        assert provider == "anthropic"
        assert source == "dotenv"
        assert env == "ANTHROPIC_API_KEY"
        # api_key_value is always empty in the new wizard
        assert value == ""
        # No .env file should be created by the wizard
        assert not (tmp_path / ".env").exists()

    def test_dotenv_custom_env_var_name(
        self, tmp_path: Path, console: Console, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """User can override the env var name in dotenv flow."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_HOST", raising=False)

        select_values = iter(["anthropic", "dotenv"])
        with (
            patch(
                "lexibrary.init.wizard.questionary.select",
                side_effect=lambda *a, **kw: _MockQuestionaryResult(next(select_values)),
            ),
            patch(
                "lexibrary.init.wizard.Prompt.ask",
                return_value="MY_CUSTOM_KEY",
            ),
        ):
            provider, model, env, source, value = _step_llm_provider(
                tmp_path, console, use_defaults=False
            )

        assert env == "MY_CUSTOM_KEY"
        assert source == "dotenv"
        assert value == ""

    def test_all_providers_shown_in_select(
        self, tmp_path: Path, console: Console, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """All 4 providers appear in the questionary.select() choices."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_HOST", raising=False)

        captured_kwargs: list[dict[str, object]] = []

        def _capture_select(*args: object, **kwargs: object) -> _MockQuestionaryResult:
            captured_kwargs.append(kwargs)
            # Return "anthropic" for provider, "env" for storage
            if len(captured_kwargs) == 1:
                return _MockQuestionaryResult("anthropic")
            return _MockQuestionaryResult("env")

        with patch(
            "lexibrary.init.wizard.questionary.select",
            side_effect=_capture_select,
        ):
            _step_llm_provider(tmp_path, console, use_defaults=False)

        # First select call is for provider — check all 4 are present
        assert len(captured_kwargs) >= 1
        provider_choices = captured_kwargs[0].get("choices", [])
        assert "anthropic" in provider_choices
        assert "openai" in provider_choices
        assert "google" in provider_choices
        assert "ollama" in provider_choices

    def test_detected_provider_is_default(
        self, tmp_path: Path, console: Console, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The detected provider is pre-selected as default in questionary.select()."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_HOST", raising=False)

        captured_kwargs: list[dict[str, object]] = []

        def _capture_select(*args: object, **kwargs: object) -> _MockQuestionaryResult:
            captured_kwargs.append(kwargs)
            if len(captured_kwargs) == 1:
                return _MockQuestionaryResult("openai")
            return _MockQuestionaryResult("env")

        with patch(
            "lexibrary.init.wizard.questionary.select",
            side_effect=_capture_select,
        ):
            provider, model, env, source, value = _step_llm_provider(
                tmp_path, console, use_defaults=False
            )

        assert provider == "openai"
        # First select call default should be the detected provider
        assert captured_kwargs[0].get("default") == "openai"

    def test_no_provider_detected_defaults_to_anthropic(
        self, tmp_path: Path, console: Console, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When no provider is detected, questionary.select() defaults to anthropic."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_HOST", raising=False)

        captured_kwargs: list[dict[str, object]] = []

        def _capture_select(*args: object, **kwargs: object) -> _MockQuestionaryResult:
            captured_kwargs.append(kwargs)
            if len(captured_kwargs) == 1:
                return _MockQuestionaryResult("anthropic")
            return _MockQuestionaryResult("env")

        with patch(
            "lexibrary.init.wizard.questionary.select",
            side_effect=_capture_select,
        ):
            provider, model, env, source, value = _step_llm_provider(
                tmp_path, console, use_defaults=False
            )

        assert provider == "anthropic"
        assert model == "claude-sonnet-4-6"
        assert env == "ANTHROPIC_API_KEY"
        assert source == "env"
        assert value == ""
        assert captured_kwargs[0].get("default") == "anthropic"

    def test_no_env_file_created_for_dotenv(
        self, tmp_path: Path, console: Console, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Dotenv mode no longer creates a .env file — user must do it themselves."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_HOST", raising=False)

        select_values = iter(["anthropic", "dotenv"])
        with (
            patch(
                "lexibrary.init.wizard.questionary.select",
                side_effect=lambda *a, **kw: _MockQuestionaryResult(next(select_values)),
            ),
            patch(
                "lexibrary.init.wizard.Prompt.ask",
                return_value="ANTHROPIC_API_KEY",
            ),
        ):
            _step_llm_provider(tmp_path, console, use_defaults=False)

        assert not (tmp_path / ".env").exists()
        assert not (tmp_path / ".gitignore").exists()


class TestStepIgnorePatternsInteractive:
    def test_user_accepts_all_suggestions(self, tmp_path: Path, console: Console) -> None:
        """User keeps all suggested patterns checked in questionary.checkbox."""
        (tmp_path / "pyproject.toml").touch()
        # Detect python patterns first to know what to return
        from lexibrary.init.detection import detect_project_type, suggest_ignore_patterns

        project_type = detect_project_type(tmp_path)
        patterns = suggest_ignore_patterns(project_type)

        with (
            patch(
                "lexibrary.init.wizard.questionary.checkbox",
                return_value=_MockQuestionaryResult(patterns),
            ),
            patch("lexibrary.init.wizard.Prompt.ask", return_value=""),
        ):
            result = _step_ignore_patterns(tmp_path, console, use_defaults=False)
        assert "**/migrations/" in result
        assert "**/__generated__/" in result

    def test_user_deselects_some_patterns(self, tmp_path: Path, console: Console) -> None:
        """User deselects some patterns via checkbox."""
        (tmp_path / "pyproject.toml").touch()
        with (
            patch(
                "lexibrary.init.wizard.questionary.checkbox",
                return_value=_MockQuestionaryResult(["**/migrations/"]),
            ),
            patch("lexibrary.init.wizard.Prompt.ask", return_value=""),
        ):
            result = _step_ignore_patterns(tmp_path, console, use_defaults=False)
        assert result == ["**/migrations/"]

    def test_user_deselects_all_and_provides_custom(self, tmp_path: Path, console: Console) -> None:
        """User deselects all checkboxes and adds custom patterns via free-text."""
        (tmp_path / "pyproject.toml").touch()
        with (
            patch(
                "lexibrary.init.wizard.questionary.checkbox",
                return_value=_MockQuestionaryResult([]),
            ),
            patch("lexibrary.init.wizard.Prompt.ask", return_value="build/, dist/"),
        ):
            result = _step_ignore_patterns(tmp_path, console, use_defaults=False)
        assert result == ["build/", "dist/"]

    def test_checkbox_plus_additional_patterns(self, tmp_path: Path, console: Console) -> None:
        """User keeps some suggestions checked and also adds custom patterns."""
        (tmp_path / "pyproject.toml").touch()
        with (
            patch(
                "lexibrary.init.wizard.questionary.checkbox",
                return_value=_MockQuestionaryResult(["**/migrations/"]),
            ),
            patch("lexibrary.init.wizard.Prompt.ask", return_value="vendor/"),
        ):
            result = _step_ignore_patterns(tmp_path, console, use_defaults=False)
        assert result == ["**/migrations/", "vendor/"]

    def test_non_tty_falls_back_to_suggestions(self, tmp_path: Path, console: Console) -> None:
        """Non-TTY (checkbox returns None) falls back to all suggested patterns."""
        (tmp_path / "pyproject.toml").touch()
        with (
            patch(
                "lexibrary.init.wizard.questionary.checkbox",
                return_value=_MockQuestionaryResult(None),
            ),
            patch("lexibrary.init.wizard.Prompt.ask", return_value=""),
        ):
            result = _step_ignore_patterns(tmp_path, console, use_defaults=False)
        assert "**/migrations/" in result


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
    """Integration tests for run_wizard() in interactive mode.

    Steps 3, 4a, 4b, and 5 now use questionary widgets, so we must mock
    ``questionary.checkbox`` and ``questionary.select`` alongside the
    traditional ``Prompt.ask`` / ``Confirm.ask`` mocks.
    """

    def test_cancellation_returns_none(
        self, tmp_path: Path, console: Console, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """User declining at summary should return None."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_HOST", raising=False)

        # Prompt.ask calls: step 1 (project name), step 2 (scope root),
        # step 5 (additional patterns — no suggestions since no project type)
        prompt_values = iter(
            [
                tmp_path.name,  # step 1: project name
                ".",  # step 2: scope root
                "",  # step 5: additional patterns
            ]
        )
        # questionary.checkbox calls: step 3 (agent envs) — no suggestions for step 5
        checkbox_values = iter(
            [
                [],  # step 3: no envs selected
            ]
        )
        # questionary.select calls: step 4a (provider), step 4b (storage)
        select_values = iter(
            [
                "anthropic",  # step 4a: provider
                "env",  # step 4b: storage
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
                "lexibrary.init.wizard.questionary.checkbox",
                side_effect=lambda *a, **kw: _MockQuestionaryResult(next(checkbox_values)),
            ),
            patch(
                "lexibrary.init.wizard.questionary.select",
                side_effect=lambda *a, **kw: _MockQuestionaryResult(next(select_values)),
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

        from lexibrary.init.detection import detect_project_type, suggest_ignore_patterns

        patterns = suggest_ignore_patterns(detect_project_type(tmp_path))

        # Prompt.ask calls: step 1, step 2, step 5 (additional patterns)
        prompt_values = iter(
            [
                "my-app",  # step 1: accept project name
                "src/",  # step 2: accept scope root
                "",  # step 5: no additional patterns
            ]
        )
        # questionary.checkbox: step 3 (agent envs), step 5 (ignore patterns)
        checkbox_values = iter(
            [
                ["claude"],  # step 3: select claude
                patterns,  # step 5: accept all suggested patterns
            ]
        )
        # questionary.select: step 4a (provider), step 4b (storage)
        select_values = iter(
            [
                "anthropic",  # step 4a: provider
                "env",  # step 4b: storage
            ]
        )
        confirm_values = iter(
            [
                True,  # step 3: create missing .claude/ dirs
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
                "lexibrary.init.wizard.questionary.checkbox",
                side_effect=lambda *a, **kw: _MockQuestionaryResult(next(checkbox_values)),
            ),
            patch(
                "lexibrary.init.wizard.questionary.select",
                side_effect=lambda *a, **kw: _MockQuestionaryResult(next(select_values)),
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

    def test_interactive_dotenv_sets_source_and_empty_value(
        self, tmp_path: Path, console: Console, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Interactive dotenv mode sets source to 'dotenv' and value to empty."""
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "my-app"\n', encoding="utf-8")
        (tmp_path / "src").mkdir()
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_HOST", raising=False)

        from lexibrary.init.detection import detect_project_type, suggest_ignore_patterns

        patterns = suggest_ignore_patterns(detect_project_type(tmp_path))

        # Prompt.ask calls: step 1, step 2, step 4c (env var name), step 5 (additional)
        prompt_values = iter(
            [
                "my-app",  # step 1: accept project name
                "src/",  # step 2: accept scope root
                "ANTHROPIC_API_KEY",  # step 4c: env var name for dotenv
                "",  # step 5: no additional patterns
            ]
        )
        # questionary.checkbox: step 3 (agent envs), step 5 (ignore patterns)
        checkbox_values = iter(
            [
                ["claude"],  # step 3: select claude
                patterns,  # step 5: accept all suggested patterns
            ]
        )
        # questionary.select: step 4a (provider), step 4b (storage = dotenv)
        select_values = iter(
            [
                "anthropic",  # step 4a: provider
                "dotenv",  # step 4b: storage
            ]
        )
        confirm_values = iter(
            [
                True,  # step 3: create missing .claude/ dirs
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
                "lexibrary.init.wizard.questionary.checkbox",
                side_effect=lambda *a, **kw: _MockQuestionaryResult(next(checkbox_values)),
            ),
            patch(
                "lexibrary.init.wizard.questionary.select",
                side_effect=lambda *a, **kw: _MockQuestionaryResult(next(select_values)),
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
        # api_key_value is always empty in the new wizard
        assert result.llm_api_key_value == ""
        # No .env file should be created by the wizard
        assert not (tmp_path / ".env").exists()

    def test_interactive_hooks_accepted(
        self, tmp_path: Path, console: Console, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Interactive mode with hooks accepted sets install_hooks=True."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_HOST", raising=False)

        # Prompt.ask: step 1, step 2, step 5 (additional patterns)
        prompt_values = iter(
            [
                tmp_path.name,  # step 1: project name
                ".",  # step 2: scope root
                "",  # step 5: additional patterns
            ]
        )
        # questionary.checkbox: step 3 (no envs)
        checkbox_values = iter(
            [
                [],  # step 3: no envs
            ]
        )
        # questionary.select: step 4a, 4b
        select_values = iter(
            [
                "anthropic",  # step 4a: provider
                "env",  # step 4b: storage
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
                "lexibrary.init.wizard.questionary.checkbox",
                side_effect=lambda *a, **kw: _MockQuestionaryResult(next(checkbox_values)),
            ),
            patch(
                "lexibrary.init.wizard.questionary.select",
                side_effect=lambda *a, **kw: _MockQuestionaryResult(next(select_values)),
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
                "",  # step 5: additional patterns
            ]
        )
        checkbox_values = iter(
            [
                [],  # step 3: no envs
            ]
        )
        select_values = iter(
            [
                "anthropic",  # step 4a: provider
                "env",  # step 4b: storage
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
                "lexibrary.init.wizard.questionary.checkbox",
                side_effect=lambda *a, **kw: _MockQuestionaryResult(next(checkbox_values)),
            ),
            patch(
                "lexibrary.init.wizard.questionary.select",
                side_effect=lambda *a, **kw: _MockQuestionaryResult(next(select_values)),
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

    def test_post_wizard_dotenv_reminder(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When dotenv storage is selected, a reminder message is printed after confirmation."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_HOST", raising=False)

        # Use a non-quiet console so we can capture output
        console = Console(file=__import__("io").StringIO(), force_terminal=True)

        # Prompt.ask: step 1, step 2, step 4c (env var name), step 5 (additional)
        prompt_values = iter(
            [
                tmp_path.name,  # step 1: project name
                ".",  # step 2: scope root
                "ANTHROPIC_API_KEY",  # step 4c: env var name
                "",  # step 5: additional patterns
            ]
        )
        checkbox_values = iter(
            [
                [],  # step 3: no envs
            ]
        )
        select_values = iter(
            [
                "anthropic",  # step 4a: provider
                "dotenv",  # step 4b: storage
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
                "lexibrary.init.wizard.questionary.checkbox",
                side_effect=lambda *a, **kw: _MockQuestionaryResult(next(checkbox_values)),
            ),
            patch(
                "lexibrary.init.wizard.questionary.select",
                side_effect=lambda *a, **kw: _MockQuestionaryResult(next(select_values)),
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

        # Verify the reminder message was printed
        output = console.file.getvalue()  # type: ignore[union-attr]
        assert "Reminder" in output
        assert "dotenv" in output
        assert "ANTHROPIC_API_KEY" in output
        assert ".env" in output
