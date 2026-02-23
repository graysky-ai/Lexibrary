"""LLM service wrapper for BAML-generated client with rate limiting and error fallback."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from lexibrary.baml_client.async_client import b
from lexibrary.baml_client.types import FileInput
from lexibrary.llm.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


@dataclass
class FileSummaryRequest:
    """Request for summarizing a single file."""

    path: Path
    content: str
    language: str
    is_truncated: bool = False


@dataclass
class FileSummaryResult:
    """Result of a file summarization."""

    path: Path
    summary: str
    error: bool = False


@dataclass
class DirectorySummaryRequest:
    """Request for summarizing a directory."""

    path: Path
    file_list: str
    subdir_list: str


class LLMService:
    """Async wrapper around the BAML client with rate limiting and error fallback."""

    def __init__(self, rate_limiter: RateLimiter) -> None:
        self._rate_limiter = rate_limiter

    async def summarize_file(self, request: FileSummaryRequest) -> FileSummaryResult:
        """Summarize a single file. Returns fallback summary on error."""
        await self._rate_limiter.acquire()
        try:
            result = await b.SummarizeFile(
                filename=request.path.name,
                language=request.language,
                content=request.content,
                is_truncated=request.is_truncated,
            )
            return FileSummaryResult(path=request.path, summary=result.summary)
        except Exception:
            logger.warning("LLM error summarizing %s", request.path, exc_info=True)
            return FileSummaryResult(path=request.path, summary="", error=True)

    async def summarize_files_batch(
        self, requests: list[FileSummaryRequest]
    ) -> list[FileSummaryResult]:
        """Summarize a batch of files. Returns fallback summaries on error."""
        if not requests:
            return []

        await self._rate_limiter.acquire()
        try:
            file_inputs = [
                FileInput(
                    filename=req.path.name,
                    language=req.language,
                    content=req.content,
                )
                for req in requests
            ]
            results = await b.SummarizeFilesBatch(files=file_inputs)
            if len(results) != len(requests):
                logger.warning(
                    "Batch returned %d results for %d files, marking as errors",
                    len(results),
                    len(requests),
                )
                return [
                    FileSummaryResult(path=req.path, summary="", error=True) for req in requests
                ]
            return [
                FileSummaryResult(path=req.path, summary=batch_result.summary)
                for req, batch_result in zip(requests, results, strict=True)
            ]
        except Exception:
            logger.warning("LLM error in batch summarization", exc_info=True)
            return [FileSummaryResult(path=req.path, summary="", error=True) for req in requests]

    async def summarize_directory(self, request: DirectorySummaryRequest) -> str:
        """Summarize a directory. Returns fallback summary on error."""
        await self._rate_limiter.acquire()
        try:
            return await b.SummarizeDirectory(
                dirname=request.path.name,
                file_list=request.file_list,
                subdir_list=request.subdir_list,
            )
        except Exception:
            logger.warning("LLM error summarizing directory %s", request.path, exc_info=True)
            return "Summary unavailable."
