"""Tests for the LLM service with mocked BAML client."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from baml_py import ClientRegistry

from lexibrary.baml_client.types import BatchFileSummary, FileSummary
from lexibrary.exceptions import LLMServiceError
from lexibrary.llm.rate_limiter import RateLimiter
from lexibrary.llm.service import (
    DirectorySummaryRequest,
    FileSummaryRequest,
    FileSummaryResult,
    LLMService,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def rate_limiter() -> RateLimiter:
    """A rate limiter with high throughput for tests."""
    return RateLimiter(requests_per_minute=6000)


@pytest.fixture()
def client_registry() -> ClientRegistry:
    """A minimal client registry for tests."""
    registry = ClientRegistry()
    registry.add_llm_client(
        name="lexibrary-summarize",
        provider="anthropic",
        options={"model": "test-model", "api_key": "test-key", "max_tokens": 100},
    )
    registry.set_primary("lexibrary-summarize")
    return registry


@pytest.fixture()
def service(rate_limiter: RateLimiter, client_registry: ClientRegistry) -> LLMService:
    """Create an LLMService with a fast rate limiter and test registry."""
    return LLMService(rate_limiter=rate_limiter, client_registry=client_registry)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestConstruction:
    """Verify LLMService accepts client_registry."""

    def test_accepts_client_registry(
        self, rate_limiter: RateLimiter, client_registry: ClientRegistry
    ) -> None:
        svc = LLMService(rate_limiter=rate_limiter, client_registry=client_registry)
        assert svc._client_registry is client_registry
        assert svc._rate_limiter is rate_limiter


# ---------------------------------------------------------------------------
# Client routing via registry
# ---------------------------------------------------------------------------


class TestClientRouting:
    """Verify that _get_baml_client uses the registry with the summarize client."""

    def test_routes_via_registry(
        self, rate_limiter: RateLimiter, client_registry: ClientRegistry
    ) -> None:
        svc = LLMService(rate_limiter=rate_limiter, client_registry=client_registry)

        with patch("lexibrary.llm.service.b") as mock_b:
            mock_b.with_options.return_value = mock_b
            svc._get_baml_client()
            mock_b.with_options.assert_called_once_with(
                client_registry=client_registry,
                client="lexibrary-summarize",
            )


# ---------------------------------------------------------------------------
# summarize_file
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_summarize_file_success(service: LLMService) -> None:
    mock_client = MagicMock()
    mock_client.SummarizeFile = AsyncMock(
        return_value=FileSummary(summary="A Python utility module.")
    )
    request = FileSummaryRequest(
        path=Path("src/utils.py"), content="def foo(): pass", language="Python"
    )

    with patch.object(service, "_get_baml_client", return_value=mock_client):
        result = await service.summarize_file(request)

    assert isinstance(result, FileSummaryResult)
    assert result.path == Path("src/utils.py")
    assert result.summary == "A Python utility module."
    mock_client.SummarizeFile.assert_awaited_once()


@pytest.mark.asyncio()
async def test_summarize_file_error_raises(service: LLMService) -> None:
    mock_client = MagicMock()
    mock_client.SummarizeFile = AsyncMock(side_effect=RuntimeError("API error"))
    request = FileSummaryRequest(path=Path("src/broken.py"), content="bad", language="Python")

    with patch.object(service, "_get_baml_client", return_value=mock_client), pytest.raises(
        LLMServiceError, match="API error"
    ):
        await service.summarize_file(request)


# ---------------------------------------------------------------------------
# summarize_files_batch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_summarize_files_batch_success(service: LLMService) -> None:
    mock_client = MagicMock()
    mock_client.SummarizeFilesBatch = AsyncMock(
        return_value=[
            BatchFileSummary(filename="a.py", summary="File A"),
            BatchFileSummary(filename="b.py", summary="File B"),
        ]
    )
    requests = [
        FileSummaryRequest(path=Path("a.py"), content="# a", language="Python"),
        FileSummaryRequest(path=Path("b.py"), content="# b", language="Python"),
    ]

    with patch.object(service, "_get_baml_client", return_value=mock_client):
        results = await service.summarize_files_batch(requests)

    assert len(results) == 2
    assert results[0].summary == "File A"
    assert results[1].summary == "File B"


@pytest.mark.asyncio()
async def test_summarize_files_batch_empty(service: LLMService) -> None:
    results = await service.summarize_files_batch([])
    assert results == []


@pytest.mark.asyncio()
async def test_summarize_files_batch_error_raises(service: LLMService) -> None:
    mock_client = MagicMock()
    mock_client.SummarizeFilesBatch = AsyncMock(side_effect=RuntimeError("API error"))
    requests = [
        FileSummaryRequest(path=Path("a.py"), content="# a", language="Python"),
        FileSummaryRequest(path=Path("b.py"), content="# b", language="Python"),
    ]

    with patch.object(service, "_get_baml_client", return_value=mock_client), pytest.raises(
        LLMServiceError, match="API error"
    ):
        await service.summarize_files_batch(requests)


# ---------------------------------------------------------------------------
# summarize_directory
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_summarize_directory_success(service: LLMService) -> None:
    mock_client = MagicMock()
    mock_client.SummarizeDirectory = AsyncMock(
        return_value="Contains utility functions for the project."
    )
    request = DirectorySummaryRequest(
        path=Path("src/utils"),
        file_list="hashing.py\npaths.py",
        subdir_list="",
    )

    with patch.object(service, "_get_baml_client", return_value=mock_client):
        result = await service.summarize_directory(request)

    assert result == "Contains utility functions for the project."


@pytest.mark.asyncio()
async def test_summarize_directory_error_raises(service: LLMService) -> None:
    mock_client = MagicMock()
    mock_client.SummarizeDirectory = AsyncMock(side_effect=RuntimeError("API error"))
    request = DirectorySummaryRequest(
        path=Path("src/utils"),
        file_list="hashing.py",
        subdir_list="",
    )

    with patch.object(service, "_get_baml_client", return_value=mock_client), pytest.raises(
        LLMServiceError, match="API error"
    ):
        await service.summarize_directory(request)
