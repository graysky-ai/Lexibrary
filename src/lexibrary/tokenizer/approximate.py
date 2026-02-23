"""Approximate token counter using character-based heuristic."""

from __future__ import annotations

from pathlib import Path

CHARS_PER_TOKEN = 4.0


class ApproximateCounter:
    """Zero-dependency token counter estimating tokens as len(text) / 4.

    Accuracy is ~20% error margin. Suitable for development or when
    tiktoken/anthropic libraries are unavailable.
    """

    def count(self, text: str) -> int:
        """Count tokens by dividing character count by 4."""
        return max(1, int(len(text) / CHARS_PER_TOKEN))

    def count_file(self, path: Path) -> int:
        """Count tokens in a file."""
        text = path.read_text(encoding="utf-8", errors="replace")
        return self.count(text)

    @property
    def name(self) -> str:
        """Return backend identifier."""
        return "approximate (chars/4)"
