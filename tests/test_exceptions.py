"""Tests for the exception hierarchy."""

from __future__ import annotations

import pytest

from lexibrary.exceptions import (
    ConfigError,
    IndexingError,
    LexibraryError,
    LexibraryNotFoundError,
    LinkGraphError,
    LLMServiceError,
    ParseError,
)


@pytest.mark.parametrize(
    "exc_class",
    [
        LexibraryNotFoundError,
        ConfigError,
        IndexingError,
        LLMServiceError,
        ParseError,
        LinkGraphError,
    ],
)
def test_all_exceptions_inherit_from_base(exc_class: type[Exception]) -> None:
    assert issubclass(exc_class, LexibraryError)


def test_base_inherits_from_exception() -> None:
    assert issubclass(LexibraryError, Exception)


@pytest.mark.parametrize(
    "exc_class",
    [
        LexibraryError,
        ConfigError,
        IndexingError,
        LLMServiceError,
        ParseError,
        LinkGraphError,
    ],
)
def test_exception_message_preserved(exc_class: type[Exception]) -> None:
    exc = exc_class("test message")
    assert str(exc) == "test message"


def test_catch_base_catches_all_subclasses() -> None:
    for exc_class in (ConfigError, IndexingError, LLMServiceError, ParseError, LinkGraphError):
        with pytest.raises(LexibraryError):
            raise exc_class("caught")
