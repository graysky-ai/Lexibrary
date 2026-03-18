"""Tests for lexibrary.llm.client_registry."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from lexibrary.config.schema import LexibraryConfig
from lexibrary.exceptions import ConfigError
from lexibrary.llm.client_registry import build_client_registry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(
    provider: str = "anthropic",
    model: str = "claude-sonnet-4-6",
    api_key_env: str = "ANTHROPIC_API_KEY",
    max_retries: int = 3,
    summarize_max_tokens: int = 200,
    archivist_max_tokens: int = 5000,
) -> LexibraryConfig:
    """Build a LexibraryConfig with the given LLM / token-budget overrides."""
    return LexibraryConfig(
        llm={
            "provider": provider,
            "model": model,
            "api_key_env": api_key_env,
            "max_retries": max_retries,
        },
        token_budgets={
            "summarize_max_tokens": summarize_max_tokens,
            "archivist_max_tokens": archivist_max_tokens,
        },
    )


# ---------------------------------------------------------------------------
# Two-client registration
# ---------------------------------------------------------------------------


class TestTwoClientRegistration:
    """build_client_registry registers exactly two clients and sets primary."""

    @patch("lexibrary.llm.client_registry.ClientRegistry")
    def test_registers_summarize_and_archivist_anthropic(
        self, mock_cls: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        config = _make_config()

        build_client_registry(config)
        registry = mock_cls.return_value

        # Two add_llm_client calls.
        assert registry.add_llm_client.call_count == 2

        names = [c.kwargs["name"] for c in registry.add_llm_client.call_args_list]
        assert "lexibrary-summarize" in names
        assert "lexibrary-archivist" in names

        # Primary set to summarize.
        registry.set_primary.assert_called_once_with("lexibrary-summarize")

    @patch("lexibrary.llm.client_registry.ClientRegistry")
    def test_registers_two_clients_openai(
        self, mock_cls: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
        config = _make_config(
            provider="openai",
            model="gpt-5-mini",
            api_key_env="OPENAI_API_KEY",
        )

        build_client_registry(config)
        registry = mock_cls.return_value

        assert registry.add_llm_client.call_count == 2

        for c in registry.add_llm_client.call_args_list:
            assert c.kwargs["provider"] == "openai"
            assert c.kwargs["options"]["model"] == "gpt-5-mini"


# ---------------------------------------------------------------------------
# Provider-specific token key mapping
# ---------------------------------------------------------------------------


class TestProviderTokenKey:
    """The factory uses the correct provider-specific option key."""

    @patch("lexibrary.llm.client_registry.ClientRegistry")
    def test_anthropic_uses_max_tokens(
        self, mock_cls: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        config = _make_config(provider="anthropic")

        build_client_registry(config)
        registry = mock_cls.return_value

        for c in registry.add_llm_client.call_args_list:
            opts = c.kwargs["options"]
            assert "max_tokens" in opts
            assert "max_completion_tokens" not in opts

    @patch("lexibrary.llm.client_registry.ClientRegistry")
    def test_openai_uses_max_completion_tokens(
        self, mock_cls: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        config = _make_config(
            provider="openai",
            model="gpt-5-mini",
            api_key_env="OPENAI_API_KEY",
        )

        build_client_registry(config)
        registry = mock_cls.return_value

        for c in registry.add_llm_client.call_args_list:
            opts = c.kwargs["options"]
            assert "max_completion_tokens" in opts
            assert "max_tokens" not in opts


# ---------------------------------------------------------------------------
# Token limits from config
# ---------------------------------------------------------------------------


class TestTokenLimitsFromConfig:
    """Clients use the configured token limits."""

    @patch("lexibrary.llm.client_registry.ClientRegistry")
    def test_summarize_uses_configured_limit(
        self, mock_cls: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        config = _make_config(summarize_max_tokens=300)

        build_client_registry(config)
        registry = mock_cls.return_value

        summarize_call = next(
            c
            for c in registry.add_llm_client.call_args_list
            if c.kwargs["name"] == "lexibrary-summarize"
        )
        assert summarize_call.kwargs["options"]["max_tokens"] == 300

    @patch("lexibrary.llm.client_registry.ClientRegistry")
    def test_archivist_uses_configured_limit(
        self, mock_cls: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        config = _make_config(archivist_max_tokens=8000)

        build_client_registry(config)
        registry = mock_cls.return_value

        archivist_call = next(
            c
            for c in registry.add_llm_client.call_args_list
            if c.kwargs["name"] == "lexibrary-archivist"
        )
        assert archivist_call.kwargs["options"]["max_tokens"] == 8000


# ---------------------------------------------------------------------------
# API key resolution
# ---------------------------------------------------------------------------


class TestAPIKeyResolution:
    """API key is read from the env var specified in config."""

    @patch("lexibrary.llm.client_registry.ClientRegistry")
    def test_api_key_from_configured_env_var(
        self, mock_cls: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret-123")
        config = _make_config()

        build_client_registry(config)
        registry = mock_cls.return_value

        for c in registry.add_llm_client.call_args_list:
            assert c.kwargs["options"]["api_key"] == "sk-secret-123"

    @patch("lexibrary.llm.client_registry.ClientRegistry")
    def test_custom_env_var_name(
        self, mock_cls: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MY_CUSTOM_KEY", "custom-secret")
        config = _make_config(api_key_env="MY_CUSTOM_KEY")

        build_client_registry(config)
        registry = mock_cls.return_value

        for c in registry.add_llm_client.call_args_list:
            assert c.kwargs["options"]["api_key"] == "custom-secret"

    @patch("lexibrary.llm.client_registry.ClientRegistry")
    def test_missing_env_var_uses_empty_string(
        self, mock_cls: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        config = _make_config()

        build_client_registry(config)
        registry = mock_cls.return_value

        for c in registry.add_llm_client.call_args_list:
            assert c.kwargs["options"]["api_key"] == ""


# ---------------------------------------------------------------------------
# Unlimited mode
# ---------------------------------------------------------------------------


class TestUnlimitedMode:
    """unlimited=True overrides archivist limit but not summarize."""

    @patch("lexibrary.llm.client_registry.ClientRegistry")
    def test_unlimited_anthropic_archivist_ceiling(
        self, mock_cls: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        config = _make_config(provider="anthropic", archivist_max_tokens=5000)

        build_client_registry(config, unlimited=True)
        registry = mock_cls.return_value

        archivist_call = next(
            c
            for c in registry.add_llm_client.call_args_list
            if c.kwargs["name"] == "lexibrary-archivist"
        )
        assert archivist_call.kwargs["options"]["max_tokens"] == 8192

    @patch("lexibrary.llm.client_registry.ClientRegistry")
    def test_unlimited_openai_archivist_ceiling(
        self, mock_cls: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        config = _make_config(
            provider="openai",
            model="gpt-5-mini",
            api_key_env="OPENAI_API_KEY",
            archivist_max_tokens=5000,
        )

        build_client_registry(config, unlimited=True)
        registry = mock_cls.return_value

        archivist_call = next(
            c
            for c in registry.add_llm_client.call_args_list
            if c.kwargs["name"] == "lexibrary-archivist"
        )
        assert archivist_call.kwargs["options"]["max_completion_tokens"] == 16384

    @patch("lexibrary.llm.client_registry.ClientRegistry")
    def test_unlimited_does_not_affect_summarize(
        self, mock_cls: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        config = _make_config(summarize_max_tokens=200)

        build_client_registry(config, unlimited=True)
        registry = mock_cls.return_value

        summarize_call = next(
            c
            for c in registry.add_llm_client.call_args_list
            if c.kwargs["name"] == "lexibrary-summarize"
        )
        assert summarize_call.kwargs["options"]["max_tokens"] == 200


# ---------------------------------------------------------------------------
# Unsupported provider error
# ---------------------------------------------------------------------------


class TestUnsupportedProvider:
    """Unsupported providers raise ConfigError."""

    def test_ollama_raises_config_error(self) -> None:
        config = _make_config(provider="ollama")
        with pytest.raises(ConfigError, match="Unsupported LLM provider 'ollama'"):
            build_client_registry(config)

    def test_unknown_provider_raises_config_error(self) -> None:
        config = _make_config(provider="cohere")
        with pytest.raises(ConfigError, match="Supported providers"):
            build_client_registry(config)


# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------


class TestRetryPolicy:
    """Both clients use DefaultRetry with configured max_retries."""

    @patch("lexibrary.llm.client_registry.ClientRegistry")
    def test_retry_policy_applied(
        self, mock_cls: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        config = _make_config(max_retries=3)

        build_client_registry(config)
        registry = mock_cls.return_value

        for c in registry.add_llm_client.call_args_list:
            assert c.kwargs["retry_policy"] == "DefaultRetry"


# ---------------------------------------------------------------------------
# Integration (no mock) — verifies real ClientRegistry accepts our args
# ---------------------------------------------------------------------------


class TestIntegration:
    """Integration tests using the real baml_py.ClientRegistry."""

    def test_anthropic_registry_creates_without_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        config = _make_config(provider="anthropic")
        registry = build_client_registry(config)
        assert registry is not None

    def test_openai_registry_creates_without_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        config = _make_config(
            provider="openai",
            model="gpt-5-mini",
            api_key_env="OPENAI_API_KEY",
        )
        registry = build_client_registry(config)
        assert registry is not None

    def test_unlimited_mode_creates_without_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        config = _make_config(provider="anthropic")
        registry = build_client_registry(config, unlimited=True)
        assert registry is not None
