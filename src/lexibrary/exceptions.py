"""Project-level exception classes for Lexibrary."""

from __future__ import annotations


class LexibraryError(Exception):
    """Base exception for all Lexibrary errors."""


class LexibraryNotFoundError(LexibraryError):
    """Raised when no .lexibrary/ directory is found walking up from the start path."""


class ConfigError(LexibraryError):
    """Invalid configuration, missing config files, bad YAML."""


class IndexingError(LexibraryError):
    """Failure during crawl, indexing, or .aindex generation."""


class LLMServiceError(LexibraryError):
    """LLM API call failure — timeout, auth, rate limit, malformed response."""


class ParseError(LexibraryError):
    """AST/file parsing failure — bad syntax, unsupported language, read error."""


class LinkGraphError(LexibraryError):
    """Link graph build or query failure."""
