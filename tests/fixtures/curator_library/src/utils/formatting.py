"""Text formatting utilities."""
from __future__ import annotations


def bold(text: str) -> str:
    """Wrap text in bold markers."""
    return f"**{text}**"


def code_block(text: str, lang: str = "") -> str:
    """Wrap text in a fenced code block."""
    return f"```{lang}\n{text}\n```"
