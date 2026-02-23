"""Factory for creating LLMService instances configured by LLMConfig."""

from __future__ import annotations

import os

from lexibrary.config.schema import LLMConfig
from lexibrary.llm.rate_limiter import RateLimiter
from lexibrary.llm.service import LLMService

# Map config provider names to environment variable names for API keys.
_PROVIDER_ENV_KEYS: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}


def create_llm_service(config: LLMConfig) -> LLMService:
    """Create an LLMService configured for the provider specified in config.

    Sets the appropriate API key environment variable so the BAML client
    can read it at call time. Ollama requires no API key.
    """
    env_key = _PROVIDER_ENV_KEYS.get(config.provider)
    if env_key is not None:
        api_key = os.environ.get(config.api_key_env, "")
        os.environ.setdefault(env_key, api_key)

    rate_limiter = RateLimiter()
    return LLMService(rate_limiter=rate_limiter)
