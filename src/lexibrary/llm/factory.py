"""Factory for creating LLMService instances configured by a ClientRegistry."""

from __future__ import annotations

from baml_py import ClientRegistry

from lexibrary.llm.rate_limiter import RateLimiter
from lexibrary.llm.service import LLMService


def create_llm_service(client_registry: ClientRegistry) -> LLMService:
    """Create an LLMService configured with a pre-built ``ClientRegistry``.

    The registry already contains the ``lexibrary-summarize`` client with the
    correct provider, model, API key, and token limits. No environment variable
    manipulation is needed.
    """
    rate_limiter = RateLimiter()
    return LLMService(rate_limiter=rate_limiter, client_registry=client_registry)
