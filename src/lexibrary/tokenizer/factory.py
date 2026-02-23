"""Factory for creating token counter backends.

Uses lazy imports so only the selected backend's dependencies are loaded.
This keeps startup fast — choosing "approximate" never imports tiktoken or anthropic.
"""

from __future__ import annotations

from lexibrary.config.schema import TokenizerConfig
from lexibrary.tokenizer.base import TokenCounter


def create_tokenizer(config: TokenizerConfig) -> TokenCounter:
    """Create a token counter backend from configuration.

    Args:
        config: Tokenizer configuration specifying backend and model

    Returns:
        A TokenCounter implementation matching the requested backend

    Raises:
        ValueError: If the backend name is not recognized
    """
    match config.backend:
        case "tiktoken":
            from lexibrary.tokenizer.tiktoken_counter import TiktokenCounter

            return TiktokenCounter(model=config.model)
        case "anthropic_api":
            from lexibrary.tokenizer.anthropic_counter import AnthropicCounter

            return AnthropicCounter(model=config.model)
        case "approximate":
            from lexibrary.tokenizer.approximate import ApproximateCounter

            return ApproximateCounter()
        case _:
            msg = (
                f"Unknown tokenizer backend: {config.backend!r}."
                " Expected one of: 'tiktoken', 'anthropic_api', 'approximate'"
            )
            raise ValueError(msg)
