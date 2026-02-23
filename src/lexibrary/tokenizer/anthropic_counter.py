"""Anthropic API-based token counter for Claude-accurate counts."""

from __future__ import annotations

from pathlib import Path

import anthropic


class AnthropicCounter:
    """Token counter using the Anthropic count_tokens API.

    Provides Claude-accurate token counts via network API calls.
    Requires ANTHROPIC_API_KEY environment variable to be set.
    """

    def __init__(self, model: str = "claude-sonnet-4-5-20250514") -> None:
        self._model = model
        self._client = anthropic.Anthropic()

    def count(self, text: str) -> int:
        """Count tokens via the Anthropic API."""
        response = self._client.messages.count_tokens(
            model=self._model,
            messages=[{"role": "user", "content": text}],
        )
        return response.input_tokens

    def count_file(self, path: Path) -> int:
        """Count tokens in a file."""
        text = path.read_text(encoding="utf-8", errors="replace")
        return self.count(text)

    @property
    def name(self) -> str:
        """Return backend identifier."""
        return f"anthropic ({self._model})"
