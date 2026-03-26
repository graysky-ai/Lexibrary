"""Archivist service: LLM-powered design file generation."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from baml_py import ClientRegistry
from baml_py.baml_py import BamlClientError

from lexibrary.baml_client.async_client import BamlAsyncClient, b
from lexibrary.baml_client.types import DesignFileOutput
from lexibrary.exceptions import ArchivistTruncationError
from lexibrary.llm.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

# Pattern matching truncation indicators in BAML error messages.
# Providers report truncation via stop_reason/finish_reason of "length"
# or explicit "max_tokens" messages.
_TRUNCATION_PATTERN = re.compile(
    r"stop.?reason.*length|finish.?reason.*length|max.?tokens|output.*truncat",
    re.IGNORECASE,
)


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


class ArchivistService:
    """Stateless async service for generating design files via BAML.

    Uses a BAML ``ClientRegistry`` for provider routing. Client selection is
    delegated entirely to the registry -- this service contains no
    provider-to-client mapping.

    Respects rate limiting before each LLM call. Safe for future concurrent use.
    """

    def __init__(self, rate_limiter: RateLimiter, client_registry: ClientRegistry) -> None:
        self._rate_limiter = rate_limiter
        self._client_registry = client_registry

    def _get_baml_client(self) -> BamlAsyncClient:
        """Return the BAML async client configured via the registry."""
        return b.with_options(
            client_registry=self._client_registry,
            client="lexibrary-archivist",
        )

    async def generate_design_file(self, request: DesignFileRequest) -> DesignFileResult:
        """Generate a design file for a source file via BAML.

        Respects rate limiting before the LLM call. Returns an error result
        (never raises) on LLM failure.
        """
        logger.info("Generating design file for %s", request.source_path)

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
        except BamlClientError as exc:
            if _TRUNCATION_PATTERN.search(str(exc)):
                msg = f"LLM output truncated for {request.source_path}: {exc}"
                logger.warning(msg)
                raise ArchivistTruncationError(msg) from exc
            # Non-truncation BAML client errors fall through to generic handler
            error_msg = f"LLM error generating design file for {request.source_path}: {exc}"
            logger.error(error_msg, exc_info=True)
            return DesignFileResult(
                source_path=request.source_path,
                error=True,
                error_message=error_msg,
            )
        except Exception as exc:
            error_msg = f"LLM error generating design file for {request.source_path}: {exc}"
            logger.error(error_msg, exc_info=True)
            return DesignFileResult(
                source_path=request.source_path,
                error=True,
                error_message=error_msg,
            )
