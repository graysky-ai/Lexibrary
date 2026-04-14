"""Archivist service: LLM-powered design file generation."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from baml_py import ClientRegistry
from baml_py.baml_py import BamlClientError

from lexibrary.baml_client.async_client import BamlAsyncClient, b
from lexibrary.baml_client.types import DesignFileOutput
from lexibrary.exceptions import ArchivistTruncationError
from lexibrary.llm.client_registry import build_client_registry
from lexibrary.llm.rate_limiter import RateLimiter

if TYPE_CHECKING:
    from lexibrary.archivist.symbol_graph_context import SymbolGraphPromptContext
    from lexibrary.config.schema import LexibraryConfig

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
    """Request for generating a design file from a source file.

    ``symbol_context`` carries the optional symbol graph prompt context
    rendered by
    :func:`lexibrary.archivist.symbol_graph_context.render_symbol_graph_context`.
    Group 5 stores it on the request; group 8 wires it through to the
    BAML call site so the enums and call-path blocks reach the LLM.
    """

    source_path: str
    source_content: str
    interface_skeleton: str | None = None
    language: str | None = None
    existing_design_file: str | None = None
    available_artifacts: list[str] | None = None
    symbol_context: SymbolGraphPromptContext | None = None


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

        symbol_enums = request.symbol_context.enums_block if request.symbol_context else None
        symbol_call_paths = (
            request.symbol_context.call_paths_block if request.symbol_context else None
        )
        symbol_branch_parameters = (
            request.symbol_context.branch_parameters_block if request.symbol_context else None
        )
        include_data_flows = (
            request.symbol_context.include_data_flows if request.symbol_context else None
        )

        try:
            client = self._get_baml_client()
            output = await client.ArchivistGenerateDesignFile(
                source_path=request.source_path,
                source_content=request.source_content,
                interface_skeleton=request.interface_skeleton,
                language=request.language,
                existing_design_file=request.existing_design_file,
                available_artifacts=request.available_artifacts,
                symbol_enums=symbol_enums,
                symbol_call_paths=symbol_call_paths,
                symbol_branch_parameters=symbol_branch_parameters,
                include_data_flows=include_data_flows,
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


def build_archivist_service(
    config: LexibraryConfig,
    *,
    unlimited: bool = False,
) -> ArchivistService:
    """Construct a fresh :class:`ArchivistService` from *config*.

    Single source of truth for archivist wiring (rate limiter + BAML client
    registry). Callers should prefer this factory over instantiating
    :class:`ArchivistService` directly so CLI, hook, and service paths
    share identical construction semantics.

    Stateless: each call returns a new :class:`RateLimiter`, a new
    :class:`ClientRegistry`, and a new service. No caching — callers that
    need a shared instance must hold the returned reference themselves.

    Parameters
    ----------
    config:
        Full Lexibrary configuration (used to build the BAML client
        registry).
    unlimited:
        Forwarded to :func:`build_client_registry`. When ``True``, the
        archivist client uses a provider-specific safe ceiling instead of
        the configured ``archivist_max_tokens``.
    """
    rate_limiter = RateLimiter()
    client_registry = build_client_registry(config, unlimited=unlimited)
    return ArchivistService(rate_limiter=rate_limiter, client_registry=client_registry)
