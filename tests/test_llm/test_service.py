"""Tests for the LLM service with mocked BAML client."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from lexibrary.baml_client.types import BatchFileSummary, FileSummary
from lexibrary.llm.rate_limiter import RateLimiter
from lexibrary.llm.service import (
    DirectorySummaryRequest,
    FileSummaryRequest,
    FileSummaryResult,
    LLMService,
)


@pytest.fixture
def service() -> LLMService:
    """Create an LLMService with a fast rate limiter."""
    return LLMService(rate_limiter=RateLimiter(requests_per_minute=6000))


# --- summarize_file ---


@pytest.mark.asyncio
@patch("lexibrary.llm.service.b")
async def test_summarize_file_success(mock_b: AsyncMock, service: LLMService) -> None:
    mock_b.SummarizeFile = AsyncMock(return_value=FileSummary(summary="A Python utility module."))
    request = FileSummaryRequest(
        path=Path("src/utils.py"), content="def foo(): pass", language="Python"
    )
    result = await service.summarize_file(request)

    assert isinstance(result, FileSummaryResult)
    assert result.path == Path("src/utils.py")
    assert result.summary == "A Python utility module."
    mock_b.SummarizeFile.assert_awaited_once()


@pytest.mark.asyncio
@patch("lexibrary.llm.service.b")
async def test_summarize_file_error_fallback(mock_b: AsyncMock, service: LLMService) -> None:
    mock_b.SummarizeFile = AsyncMock(side_effect=RuntimeError("API error"))
    request = FileSummaryRequest(path=Path("src/broken.py"), content="bad", language="Python")
    result = await service.summarize_file(request)

    assert result.summary == ""
    assert result.error is True
    assert result.path == Path("src/broken.py")


# --- summarize_files_batch ---


@pytest.mark.asyncio
@patch("lexibrary.llm.service.b")
async def test_summarize_files_batch_success(mock_b: AsyncMock, service: LLMService) -> None:
    mock_b.SummarizeFilesBatch = AsyncMock(
        return_value=[
            BatchFileSummary(filename="a.py", summary="File A"),
            BatchFileSummary(filename="b.py", summary="File B"),
        ]
    )
    requests = [
        FileSummaryRequest(path=Path("a.py"), content="# a", language="Python"),
        FileSummaryRequest(path=Path("b.py"), content="# b", language="Python"),
    ]
    results = await service.summarize_files_batch(requests)

    assert len(results) == 2
    assert results[0].summary == "File A"
    assert results[1].summary == "File B"


@pytest.mark.asyncio
async def test_summarize_files_batch_empty(service: LLMService) -> None:
    results = await service.summarize_files_batch([])
    assert results == []


@pytest.mark.asyncio
@patch("lexibrary.llm.service.b")
async def test_summarize_files_batch_error_fallback(mock_b: AsyncMock, service: LLMService) -> None:
    mock_b.SummarizeFilesBatch = AsyncMock(side_effect=RuntimeError("API error"))
    requests = [
        FileSummaryRequest(path=Path("a.py"), content="# a", language="Python"),
        FileSummaryRequest(path=Path("b.py"), content="# b", language="Python"),
    ]
    results = await service.summarize_files_batch(requests)

    assert len(results) == 2
    assert all(r.summary == "" for r in results)
    assert all(r.error is True for r in results)


# --- summarize_directory ---


@pytest.mark.asyncio
@patch("lexibrary.llm.service.b")
async def test_summarize_directory_success(mock_b: AsyncMock, service: LLMService) -> None:
    mock_b.SummarizeDirectory = AsyncMock(
        return_value="Contains utility functions for the project."
    )
    request = DirectorySummaryRequest(
        path=Path("src/utils"),
        file_list="hashing.py\npaths.py",
        subdir_list="",
    )
    result = await service.summarize_directory(request)

    assert result == "Contains utility functions for the project."


@pytest.mark.asyncio
@patch("lexibrary.llm.service.b")
async def test_summarize_directory_error_fallback(mock_b: AsyncMock, service: LLMService) -> None:
    mock_b.SummarizeDirectory = AsyncMock(side_effect=RuntimeError("API error"))
    request = DirectorySummaryRequest(
        path=Path("src/utils"),
        file_list="hashing.py",
        subdir_list="",
    )
    result = await service.summarize_directory(request)

    assert result == "Summary unavailable."
