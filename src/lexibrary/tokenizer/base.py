"""Protocol definition for token counters."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class TokenCounter(Protocol):
    """Protocol for token counting backends.

    This protocol uses structural subtyping (PEP 544), meaning any class
    that implements the required methods can be used as a TokenCounter
    without explicit inheritance.

    Backends should:
    - Return non-negative token counts
    - Handle encoding errors gracefully (use errors="replace" when reading files)
    - Provide a descriptive name for debugging/logging
    """

    def count(self, text: str) -> int:
        """Count tokens in the given text.

        Args:
            text: The text to count tokens for

        Returns:
            Non-negative integer representing the token count
        """
        ...

    def count_file(self, path: Path) -> int:
        """Count tokens in a file.

        Args:
            path: Path to the file to count tokens for

        Returns:
            Non-negative integer representing the token count

        Note:
            Implementations should read files with encoding="utf-8"
            and errors="replace" to handle mixed-charset files gracefully.
        """
        ...

    @property
    def name(self) -> str:
        """Human-readable name identifying this counter backend.

        Returns:
            Descriptive string like "tiktoken (cl100k_base)" or "approximate (chars/4)"
        """
        ...
