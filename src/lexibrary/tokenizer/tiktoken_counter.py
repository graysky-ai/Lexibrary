"""Tiktoken-based token counter using OpenAI's BPE tokenizer."""

from __future__ import annotations

from pathlib import Path

import tiktoken


class TiktokenCounter:
    """Fast, offline token counter using tiktoken BPE encodings.

    Uses OpenAI's tiktoken library for accurate BPE token counting.
    The encoding is downloaded on first use and cached locally.
    """

    def __init__(self, model: str = "cl100k_base") -> None:
        self._model = model
        self._encoding = tiktoken.get_encoding(model)

    def count(self, text: str) -> int:
        """Count tokens using BPE encoding."""
        return len(self._encoding.encode(text))

    def count_file(self, path: Path) -> int:
        """Count tokens in a file."""
        text = path.read_text(encoding="utf-8", errors="replace")
        return self.count(text)

    @property
    def name(self) -> str:
        """Return backend identifier."""
        return f"tiktoken ({self._model})"
