"""Tests for token counter backends and factory."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lexibrary.config.schema import TokenizerConfig
from lexibrary.tokenizer.anthropic_counter import AnthropicCounter
from lexibrary.tokenizer.approximate import ApproximateCounter
from lexibrary.tokenizer.factory import create_tokenizer
from lexibrary.tokenizer.tiktoken_counter import TiktokenCounter

# === Approximate Backend Tests ===


class TestApproximateCounter:
    def test_count(self) -> None:
        """100 chars should yield 25 tokens."""
        counter = ApproximateCounter()
        assert counter.count("a" * 100) == 25

    def test_minimum_one(self) -> None:
        """Empty string should return 1 (minimum)."""
        counter = ApproximateCounter()
        assert counter.count("") == 1

    def test_count_file(self, tmp_path: Path) -> None:
        """File counting should match text counting."""
        f = tmp_path / "test.txt"
        content = "Hello, world! This is a test file."
        f.write_text(content, encoding="utf-8")
        counter = ApproximateCounter()
        assert counter.count_file(f) == counter.count(content)

    def test_name(self) -> None:
        """Name should identify the backend."""
        counter = ApproximateCounter()
        assert "approximate" in counter.name
        assert "chars/4" in counter.name


# === Tiktoken Backend Tests ===


class TestTiktokenCounter:
    def test_count_hello_world(self) -> None:
        """Token count for 'Hello, world!' should be reasonable."""
        counter = TiktokenCounter()
        count = counter.count("Hello, world!")
        assert count > 0
        assert count < 10

    def test_count_file(self, tmp_path: Path) -> None:
        """File counting should match text counting."""
        f = tmp_path / "test.txt"
        content = "Hello, world! This is a test file."
        f.write_text(content, encoding="utf-8")
        counter = TiktokenCounter()
        assert counter.count_file(f) == counter.count(content)

    def test_encoding_name(self) -> None:
        """Name should contain 'tiktoken'."""
        counter = TiktokenCounter()
        assert "tiktoken" in counter.name

    def test_custom_model(self) -> None:
        """Model parameter should be reflected in name."""
        counter = TiktokenCounter(model="o200k_base")
        assert "o200k_base" in counter.name


# === Anthropic Backend Tests ===


class TestAnthropicCounter:
    @patch("lexibrary.tokenizer.anthropic_counter.anthropic.Anthropic")
    def test_count(self, mock_anthropic_cls: MagicMock) -> None:
        """count() should return the mocked input_tokens value."""
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.input_tokens = 42
        mock_client.messages.count_tokens.return_value = mock_response

        counter = AnthropicCounter(model="claude-sonnet-4-5-20250514")
        result = counter.count("Hello, world!")

        assert result == 42

    @patch("lexibrary.tokenizer.anthropic_counter.anthropic.Anthropic")
    def test_api_called_correctly(self, mock_anthropic_cls: MagicMock) -> None:
        """API should be called with correct model and message structure."""
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.input_tokens = 10
        mock_client.messages.count_tokens.return_value = mock_response

        counter = AnthropicCounter(model="claude-sonnet-4-5-20250514")
        counter.count("test text")

        mock_client.messages.count_tokens.assert_called_once_with(
            model="claude-sonnet-4-5-20250514",
            messages=[{"role": "user", "content": "test text"}],
        )

    @patch("lexibrary.tokenizer.anthropic_counter.anthropic.Anthropic")
    def test_name(self, mock_anthropic_cls: MagicMock) -> None:
        """Name should contain 'anthropic' and the model."""
        counter = AnthropicCounter(model="claude-sonnet-4-5-20250514")
        assert "anthropic" in counter.name
        assert "claude-sonnet-4-5-20250514" in counter.name


# === Factory Tests ===


class TestFactory:
    def test_factory_tiktoken(self) -> None:
        """Factory should create TiktokenCounter for 'tiktoken' backend."""
        config = TokenizerConfig(backend="tiktoken")
        counter = create_tokenizer(config)
        assert isinstance(counter, TiktokenCounter)

    @patch("lexibrary.tokenizer.anthropic_counter.anthropic.Anthropic")
    def test_factory_anthropic(self, mock_anthropic_cls: MagicMock) -> None:
        """Factory should create AnthropicCounter for 'anthropic_api' backend."""
        config = TokenizerConfig(backend="anthropic_api", model="claude-sonnet-4-5-20250514")
        counter = create_tokenizer(config)
        assert isinstance(counter, AnthropicCounter)

    def test_factory_approximate(self) -> None:
        """Factory should create ApproximateCounter for 'approximate' backend."""
        config = TokenizerConfig(backend="approximate")
        counter = create_tokenizer(config)
        assert isinstance(counter, ApproximateCounter)

    def test_factory_unknown_raises(self) -> None:
        """Factory should raise ValueError for unknown backend."""
        config = TokenizerConfig(backend="unknown")
        with pytest.raises(ValueError, match="Unknown tokenizer backend"):
            create_tokenizer(config)

    def test_factory_model_parameter(self) -> None:
        """Factory should pass model config to backend."""
        config = TokenizerConfig(backend="tiktoken", model="o200k_base")
        counter = create_tokenizer(config)
        assert isinstance(counter, TiktokenCounter)
        assert "o200k_base" in counter.name
