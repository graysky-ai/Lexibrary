"""Factory for building a BAML ClientRegistry from Lexibrary config."""

from __future__ import annotations

import os

from baml_py import ClientRegistry

from lexibrary.config.schema import LexibraryConfig
from lexibrary.exceptions import ConfigError

_SUPPORTED_PROVIDERS = {"anthropic", "openai"}

# Provider-specific key names for output token limits.
_TOKEN_LIMIT_KEYS: dict[str, str] = {
    "anthropic": "max_tokens",
    "openai": "max_completion_tokens",
}

# Safe ceiling values for unlimited mode, per provider.
_UNLIMITED_CEILINGS: dict[str, int] = {
    "anthropic": 8192,
    "openai": 16384,
}


def build_client_registry(
    config: LexibraryConfig,
    *,
    unlimited: bool = False,
) -> ClientRegistry:
    """Build a BAML ``ClientRegistry`` from *config*.

    Registers two named clients:

    * ``lexibrary-summarize`` -- used for file/directory summarisation.
    * ``lexibrary-archivist`` -- used for design-file generation.

    Parameters
    ----------
    config:
        Full Lexibrary configuration (needs ``config.llm`` and
        ``config.token_budgets``).
    unlimited:
        When ``True``, the archivist client uses a provider-specific safe
        ceiling instead of the configured ``archivist_max_tokens``.

    Returns
    -------
    ClientRegistry
        A registry ready to be passed to ``b.with_options(client_registry=...)``.

    Raises
    ------
    ConfigError
        If the configured provider is not in the supported set.
    """
    provider = config.llm.provider
    if provider not in _SUPPORTED_PROVIDERS:
        supported = ", ".join(sorted(_SUPPORTED_PROVIDERS))
        msg = (
            f"Unsupported LLM provider {provider!r}. "
            f"Supported providers: {supported}"
        )
        raise ConfigError(msg)

    api_key = os.environ.get(config.llm.api_key_env, "")
    token_key = _TOKEN_LIMIT_KEYS[provider]

    # Determine archivist token limit.
    if unlimited:
        archivist_limit = _UNLIMITED_CEILINGS[provider]
    else:
        archivist_limit = config.token_budgets.archivist_max_tokens

    summarize_limit = config.token_budgets.summarize_max_tokens

    registry = ClientRegistry()

    # --- lexibrary-summarize ---
    registry.add_llm_client(
        name="lexibrary-summarize",
        provider=provider,
        options={
            "model": config.llm.model,
            "api_key": api_key,
            token_key: summarize_limit,
        },
        retry_policy="DefaultRetry",
    )

    # --- lexibrary-archivist ---
    registry.add_llm_client(
        name="lexibrary-archivist",
        provider=provider,
        options={
            "model": config.llm.model,
            "api_key": api_key,
            token_key: archivist_limit,
        },
        retry_policy="DefaultRetry",
    )

    registry.set_primary("lexibrary-summarize")

    return registry
