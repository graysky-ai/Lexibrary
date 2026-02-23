"""Archivist service: LLM-powered design file and START_HERE generation."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from lexibrary.baml_client.async_client import BamlAsyncClient, b
from lexibrary.baml_client.types import DesignFileOutput, StartHereOutput
from lexibrary.config.schema import LLMConfig
from lexibrary.llm.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

# Map config provider names to BAML client names for the archivist.
_PROVIDER_CLIENT_MAP: dict[str, str] = {
    "anthropic": "AnthropicArchivist",
    "openai": "OpenAIArchivist",
}


@dataclass
class DesignFileRequest:
    """Request for generating a design file from a source file."""

    source_path: str
    source_content: str
    interface_skeleton: str | None = None
    language: str | None = None
    existing_design_file: str | None = None
    available_concepts: list[str] | None = None


@dataclass
class DesignFileResult:
    """Result of a design file generation."""

    source_path: str
    design_file_output: DesignFileOutput | None = None
    error: bool = False
    error_message: str | None = None


@dataclass
class StartHereRequest:
    """Request for generating START_HERE.md content."""

    project_name: str
    directory_tree: str
    aindex_summaries: str
    existing_start_here: str | None = None


@dataclass
class StartHereResult:
    """Result of a START_HERE.md generation."""

    start_here_output: StartHereOutput | None = None
    error: bool = False
    error_message: str | None = None


class ArchivistService:
    """Stateless async service for generating design files and START_HERE via BAML.

    Routes BAML calls to the appropriate provider client based on LLMConfig.provider.
    Respects rate limiting before each LLM call. Safe for future concurrent use.
    """

    def __init__(self, rate_limiter: RateLimiter, config: LLMConfig) -> None:
        self._rate_limiter = rate_limiter
        self._config = config
        self._client_name = _PROVIDER_CLIENT_MAP.get(config.provider)
        if self._client_name is None:
            logger.warning(
                "No archivist client mapped for provider '%s'; falling back to default BAML client",
                config.provider,
            )

    def _get_baml_client(self) -> BamlAsyncClient:
        """Return the BAML async client with provider-specific options applied."""
        if self._client_name is not None:
            return b.with_options(client=self._client_name)
        return b

    async def generate_design_file(self, request: DesignFileRequest) -> DesignFileResult:
        """Generate a design file for a source file via BAML.

        Respects rate limiting before the LLM call. Returns an error result
        (never raises) on LLM failure.
        """
        logger.info(
            "Generating design file for %s (provider=%s)",
            request.source_path,
            self._config.provider,
        )

        await self._rate_limiter.acquire()
        logger.debug("Rate limiter acquired for %s", request.source_path)

        try:
            client = self._get_baml_client()
            output = await client.ArchivistGenerateDesignFile(
                source_path=request.source_path,
                source_content=request.source_content,
                interface_skeleton=request.interface_skeleton,
                language=request.language,
                existing_design_file=request.existing_design_file,
                available_concepts=request.available_concepts,
            )
            return DesignFileResult(
                source_path=request.source_path,
                design_file_output=output,
            )
        except Exception as exc:
            error_msg = f"LLM error generating design file for {request.source_path}: {exc}"
            logger.error(error_msg, exc_info=True)
            return DesignFileResult(
                source_path=request.source_path,
                error=True,
                error_message=error_msg,
            )

    async def generate_start_here(self, request: StartHereRequest) -> StartHereResult:
        """Generate START_HERE.md content via BAML.

        Respects rate limiting before the LLM call. Returns an error result
        (never raises) on LLM failure.
        """
        logger.info(
            "Generating START_HERE.md for project '%s' (provider=%s)",
            request.project_name,
            self._config.provider,
        )

        await self._rate_limiter.acquire()
        logger.debug("Rate limiter acquired for START_HERE generation")

        try:
            client = self._get_baml_client()
            output = await client.ArchivistGenerateStartHere(
                project_name=request.project_name,
                directory_tree=request.directory_tree,
                aindex_summaries=request.aindex_summaries,
                existing_start_here=request.existing_start_here,
            )
            return StartHereResult(start_here_output=output)
        except Exception as exc:
            error_msg = f"LLM error generating START_HERE.md: {exc}"
            logger.error(error_msg, exc_info=True)
            return StartHereResult(
                error=True,
                error_message=error_msg,
            )
